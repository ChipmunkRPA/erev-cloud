"""API-R-37 Manual adjustments.

04 §15.3 API-R-37, §16.14 "API-R-37 shapes", T-SL-05, E-93, E-94; PRD SM-10, §2.5 routing rows
``MANUAL_ADJUSTMENT``, BR-CLS-04; 03 REQ-JE-019, REQ-REC-023, REQ-CLS-003; BUILD_SPEC CLO-12. Reads
need ``contract.read`` and show an adjustment only to a holder of it FOR the adjustment's entity
(REQ-PLT-012; ruling R-28: outside it 404). ``POST`` and ``PATCH``, ``preview`` (202 API-S-Job) and
``discard`` need ``adjustment.create`` for the entity. ``submit``, ``withdraw`` and
``request-defer-past-lock`` authorise in the handler, because their permission depends on the
adjustment: ``submit`` needs ``adjustment.create``, or ``period.lock`` in its place while the
period is ``closing`` (BR-CLS-04); ``withdraw`` and ``request-defer-past-lock`` take either for the
entity — the routes guard with a signed-in session and the command answers 403 or 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require, require_for_entity
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import manual_adjustment
from erev_api.domain.journals import adjustments
from erev_api.enums import BookCode, ManualAdjustmentKind, ManualAdjustmentStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.manual_adjustments import (
    ManualAdjustmentCreateIn,
    ManualAdjustmentDeferIn,
    ManualAdjustmentDiscardIn,
    ManualAdjustmentOut,
    ManualAdjustmentSubmitIn,
    ManualAdjustmentUpdateIn,
    ManualAdjustmentWithdrawIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-37 Manual adjustments"
RESOURCE: Final = f"{API_PREFIX}/manual-adjustments"
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "release-mismatch",
)

ADJUSTMENT_LIST: Final = ListSpec(
    resource="manual-adjustments",
    sort_keys={
        "id": manual_adjustment.c.id,
        "created_at": manual_adjustment.c.created_at,
        "adjustment_no": manual_adjustment.c.adjustment_no,
        "effective_date": manual_adjustment.c.effective_date,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=manual_adjustment.c.status,
            kind="in",
            choices=frozenset(member.value for member in ManualAdjustmentStatus),
        ),
        "kind": FilterSpec(
            name="kind",
            column=manual_adjustment.c.kind,
            kind="in",
            choices=frozenset(member.value for member in ManualAdjustmentKind),
        ),
    },
    custom_filters=frozenset({"entity", "book", "period"}),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)
ReadContext = Annotated[RequestContext, Depends(require(adjustments.READ_PERMISSION))]
Params = Annotated[ListParams, Depends(list_params)]
Deps = Annotated[KernelDeps, Depends(kernel_deps)]
Create = Annotated[CommandContext, Depends(command(adjustments.CREATE_PERMISSION))]
Edit = Annotated[
    CommandContext, Depends(command(adjustments.CREATE_PERMISSION, precondition="row"))
]
PerSubject = Annotated[CommandContext, Depends(command(per_subject=True))]


def _etag(out: ManualAdjustmentOut) -> str:
    return row_etag(out.row_version)


@router.get(
    "/manual-adjustments",
    operation_id="manual_adjustments_list",
    response_model=ListOut[ManualAdjustmentOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def manual_adjustments_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    entity: Annotated[list[str] | None, Query(description="Entity code; repeatable")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period", description="Period key")] = None,
    status: Annotated[list[ManualAdjustmentStatus] | None, Query()] = None,
    kind: Annotated[list[ManualAdjustmentKind] | None, Query()] = None,
) -> ListOut[ManualAdjustmentOut]:
    """Manual adjustments of the entities the caller reads contracts for; filters ``entity``,
    ``book``, ``period``, ``status`` and ``kind``; sort ``id`` (default ``-id``), ``created_at``,
    ``adjustment_no`` or ``effective_date``."""
    del status, kind  # applied by ``paginate`` through ADJUSTMENT_LIST
    statement = adjustments.adjustments_statement(
        entities=entity or (), book=book, period_key=period_key
    )
    scope = ctx.principal.permission_scopes.get(adjustments.READ_PERMISSION)
    if scope is not None and scope != "*":
        statement = statement.where(manual_adjustment.c.entity_id.in_(sorted(scope)))

    def page(session: Session) -> tuple[ListResult, list[ManualAdjustmentOut]]:
        result = paginate(session, statement, ADJUSTMENT_LIST, params)
        return result, adjustments.adjustment_outs(
            session, [dict(row) for row in result.items], reader=ctx.principal
        )

    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result, items = page(session)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ManualAdjustmentOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/manual-adjustments",
    operation_id="manual_adjustments_create",
    status_code=201,
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "ledger-unbalanced", "period-closed"),
)
def manual_adjustments_create(body: ManualAdjustmentCreateIn, cmd: Create, deps: Deps) -> Response:
    """Prepare a DRAFT adjustment of a contract: 201 API-S-ManualAdjustment with ``Location`` and
    ``ETag``. ``amount_functional_abs`` is derived by a dry run; journal lines that do not balance
    answer 422 ``ledger-unbalanced``."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.create(uow, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{RESOURCE}/{out.id}",
        etag=_etag,
    )


@router.get(
    "/manual-adjustments/{adjustment_id}",
    operation_id="manual_adjustments_get",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def manual_adjustments_get(
    adjustment_id: uuid.UUID, response: Response, ctx: ReadContext
) -> ManualAdjustmentOut:
    """API-S-ManualAdjustment with its ``ETag``; 404 outside the caller's entities."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        out = adjustments.get_adjustment(session, adjustment_id, reader=ctx.principal)
    require_for_entity(ctx, adjustments.READ_PERMISSION, out.entity.id)
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    "/manual-adjustments/{adjustment_id}",
    operation_id="manual_adjustments_update",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "invalid-transition",
        "ledger-unbalanced",
        "period-closed",
        "precondition-failed",
        "precondition-required",
    ),
)
def manual_adjustments_update(
    adjustment_id: uuid.UUID, body: ManualAdjustmentUpdateIn, cmd: Edit, deps: Deps
) -> Response:
    """Edit a DRAFT (If-Match); a REJECTED adjustment returns to DRAFT with the changes."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.update(
            uow, adjustment_id=adjustment_id, body=body, expected_version=cmd.expected_version
        )

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/manual-adjustments/{adjustment_id}/preview",
    operation_id="manual_adjustments_preview",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def manual_adjustments_preview(adjustment_id: uuid.UUID, cmd: Create, deps: Deps) -> Response:
    """Defer the impact preview: 202 API-S-Job with the job's ``Location``; the job's
    ``result.summary`` is API-S-ImpactSummary of the group with the adjustment applied."""

    def handle(uow: UnitOfWork) -> JobOut:
        return adjustments.preview(uow, adjustment_id=adjustment_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )


@router.post(
    "/manual-adjustments/{adjustment_id}/submit",
    operation_id="manual_adjustments_submit",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "period-closed"),
)
def manual_adjustments_submit(
    adjustment_id: uuid.UUID, body: ManualAdjustmentSubmitIn, cmd: PerSubject, deps: Deps
) -> Response:
    """Submit for approval: 200 API-S-ManualAdjustment with ``approval_request_id``. From USD
    10,000.00 an attachment is required (422 naming ``attachments``) and a Controller holds the
    second step; in a ``closing`` period the submitter holds ``period.lock`` (BR-CLS-04)."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.submit(uow, adjustment_id=adjustment_id, body=body)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/manual-adjustments/{adjustment_id}/withdraw",
    operation_id="manual_adjustments_withdraw",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def manual_adjustments_withdraw(
    adjustment_id: uuid.UUID, body: ManualAdjustmentWithdrawIn, cmd: PerSubject, deps: Deps
) -> Response:
    """The preparer withdraws the pending request; the adjustment returns to DRAFT."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.withdraw(uow, adjustment_id=adjustment_id, body=body)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/manual-adjustments/{adjustment_id}/discard",
    operation_id="manual_adjustments_discard",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def manual_adjustments_discard(
    adjustment_id: uuid.UUID, body: ManualAdjustmentDiscardIn, cmd: Create, deps: Deps
) -> Response:
    """Discard a DRAFT: it becomes VOIDED and stops counting as pending; ``reason`` is required."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.discard(uow, adjustment_id=adjustment_id, body=body)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/manual-adjustments/{adjustment_id}/request-defer-past-lock",
    operation_id="manual_adjustments_request_defer_past_lock",
    response_model=ManualAdjustmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def manual_adjustments_request_defer_past_lock(
    adjustment_id: uuid.UUID, body: ManualAdjustmentDeferIn, cmd: PerSubject, deps: Deps
) -> Response:
    """Ask to defer a SUBMITTED adjustment past the period lock: its pending posting request is
    replaced by a deferral request on the same routing; approval sets ``is_deferred_past_lock``,
    and the adjustment no longer holds the lock (REQ-JE-019)."""

    def handle(uow: UnitOfWork) -> ManualAdjustmentOut:
        return adjustments.request_defer_past_lock(uow, adjustment_id=adjustment_id, body=body)

    return run_command(cmd, deps, handle, etag=_etag)
