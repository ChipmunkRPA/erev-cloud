"""API-R-40 Reconciliations: generation, differences and sign-offs.

04 §15.3 API-R-40, §16.8 API-S-ReconciliationCreate, API-S-ReconciliationAttach,
API-S-Reconciliation, API-S-ReconciliationItem, "Reconciliation commands"; T-CLS-06 to T-CLS-08;
PRD SM-09; SCREENS_B §2.1, §2.2; BUILD_SPEC CLO-16, CLO-17. Reads need ``contract.read`` and
answer the reconciliations of the entities that permission covers. ``POST /reconciliations`` needs
``recon.prepare`` and answers 202 API-S-Job with the job's ``Location`` and the reconciliation id
header; ``attach-trial-balance`` needs ``recon.prepare`` and answers 202 API-S-Job likewise.
``PATCH …/items/{item_id}`` (``If-Match`` of the item) and ``prepare`` need ``recon.prepare``;
``sign`` and ``reopen`` need ``recon.signoff``.
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
    assert_version,
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
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import legal_entity, period, reconciliation, reconciliation_item
from erev_api.domain.close import gates, reconciliations
from erev_api.enums import BookCode, ReconciliationKind, ReconciliationStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.reconciliations import (
    ReconciliationAttachIn,
    ReconciliationCreateIn,
    ReconciliationItemOut,
    ReconciliationItemUpdateIn,
    ReconciliationOut,
    ReconciliationReopenIn,
    ReconciliationSignIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-40 Reconciliations"
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
RECONCILIATION_ID_HEADER: Final = "X-Erev-Reconciliation-Id"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "invalid-transition",
)

RECONCILIATION_LIST: Final = ListSpec(
    resource="reconciliations",
    sort_keys={
        "id": reconciliation.c.id,
        "created_at": reconciliation.c.created_at,
        "reconciliation_no": reconciliation.c.reconciliation_no,
    },
    default_sort="-id",
    filters={
        "kind": FilterSpec(
            name="kind",
            column=reconciliation.c.kind,
            kind="in",
            choices=frozenset(member.value for member in ReconciliationKind),
        ),
        "status": FilterSpec(
            name="status",
            column=reconciliation.c.status,
            kind="in",
            choices=frozenset(member.value for member in ReconciliationStatus),
        ),
        # The latest generation of its kind, entity, book and period (04 T-CLS-06; SCREENS_B §2.1).
        "is_current": FilterSpec(name="is_current", column=~gates.superseded(), kind="bool"),
    },
    custom_filters=frozenset({"entity", "book", "period"}),
)
ITEM_LIST: Final = ListSpec(
    resource="reconciliation-items",
    sort_keys={"id": reconciliation_item.c.id},
    default_sort="id",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)
ReadContext = Annotated[RequestContext, Depends(require(reconciliations.READ_PERMISSION))]
Params = Annotated[ListParams, Depends(list_params)]


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


def _etag(out: ReconciliationOut) -> str:
    return row_etag(out.row_version)


@router.get(
    "/reconciliations",
    operation_id="reconciliations_list",
    response_model=ListOut[ReconciliationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def reconciliations_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    entity: Annotated[list[str] | None, Query(description="Entity code; repeatable")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period", description="Period key")] = None,
    kind: Annotated[list[ReconciliationKind] | None, Query()] = None,
    status: Annotated[list[ReconciliationStatus] | None, Query()] = None,
    is_current: Annotated[bool | None, Query()] = None,
) -> ListOut[ReconciliationOut]:
    """The reconciliations of the caller's ``contract.read`` entities; sort ``id`` (default
    ``-id``), ``created_at`` or ``reconciliation_no``. Every generation is a row: ``is_current``
    marks the latest of its kind, entity, book and period, and filters on it."""
    del kind, status, is_current  # applied by ``paginate`` through RECONCILIATION_LIST
    statement = reconciliations.statement(ctx.principal)
    if entity:
        statement = statement.where(legal_entity.c.code.in_(entity))
    if book is not None:
        statement = statement.where(reconciliation.c.book_code == book.value)
    if period_key is not None:
        statement = statement.where(period.c.period_key == period_key)

    def page(session: Session) -> tuple[ListResult, list[ReconciliationOut]]:
        result = paginate(session, statement, RECONCILIATION_LIST, params)
        items = reconciliations.outs(session, [dict(row) for row in result.items], ctx.principal)
        return result, items

    result, items = reconciliations.read(ctx, page)
    _total(response, result)
    return ListOut[ReconciliationOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/reconciliations",
    operation_id="reconciliations_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def reconciliations_create(
    body: ReconciliationCreateIn,
    cmd: Annotated[CommandContext, Depends(command(reconciliations.PREPARE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Generate a reconciliation: 202 API-S-Job ``RECONCILIATION_GENERATE``; the job inserts the
    reconciliation in ``DRAFT`` with its totals and differences — a subledger-to-GL one without a
    source, to be compared by ``attach-trial-balance``; a billing one without a variance is
    auto-certified under a published rule. Every generation is a new reconciliation, which
    replaces the earlier ones of its kind, entity, book and period."""
    started: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        reconciliation_id, job = reconciliations.request_generation(uow, body)
        started["reconciliation_id"] = reconciliation_id
        return job

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {
            "Location": JOB_PATH.format(job_id=job.id),
            RECONCILIATION_ID_HEADER: str(started["reconciliation_id"]),
        },
    )


@router.get(
    "/reconciliations/{reconciliation_id}",
    operation_id="reconciliations_get",
    response_model=ReconciliationOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def reconciliations_get(
    reconciliation_id: uuid.UUID, response: Response, ctx: ReadContext
) -> ReconciliationOut:
    """API-S-Reconciliation with its sign-offs and its ``ETag``."""
    out = reconciliations.read(
        ctx, lambda session: reconciliations.get(session, ctx.principal, reconciliation_id)
    )
    response.headers["ETag"] = _etag(out)
    return out


@router.get(
    "/reconciliations/{reconciliation_id}/items",
    operation_id="reconciliations_items",
    response_model=ListOut[ReconciliationItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def reconciliations_items(
    reconciliation_id: uuid.UUID, response: Response, ctx: ReadContext, params: Params
) -> ListOut[ReconciliationItemOut]:
    """The differences of a reconciliation in the order they were itemised; each carries its
    ``row_version`` for the ``If-Match`` of its explanation."""

    def page(session: Session) -> tuple[ListResult, list[ReconciliationItemOut]]:
        reconciliations.row_of(session, ctx.principal, reconciliation_id)
        statement = reconciliations.items_statement(reconciliation_id)
        result = paginate(session, statement, ITEM_LIST, params)
        return result, reconciliations.item_outs(session, [dict(row) for row in result.items])

    result, items = reconciliations.read(ctx, page)
    _total(response, result)
    return ListOut[ReconciliationItemOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/reconciliations/{reconciliation_id}/attach-trial-balance",
    operation_id="reconciliations_attach_trial_balance",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def reconciliations_attach_trial_balance(
    reconciliation_id: uuid.UUID,
    body: ReconciliationAttachIn,
    cmd: Annotated[CommandContext, Depends(command(reconciliations.PREPARE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Attach the trial balance of a ``DRAFT`` subledger-to-GL reconciliation — pulled through a GL
    connection, or an uploaded file of ``account``, ``currency``, ``amount`` — and compare it: 202
    API-S-Job ``RECONCILIATION_GENERATE``. A file that cannot be compared is refused here (422
    with its rows). The source is written once; 409 ``invalid-transition`` for a reconciliation
    that has one, is not current, or whose subledger moved since it was generated."""

    def handle(uow: UnitOfWork) -> JobOut:
        return reconciliations.request_trial_balance(uow, reconciliation_id, body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )


@router.patch(
    "/reconciliations/{reconciliation_id}/items/{item_id}",
    operation_id="reconciliations_items_update",
    response_model=ReconciliationItemOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "precondition-required", "precondition-failed"),
)
def reconciliations_items_update(
    reconciliation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ReconciliationItemUpdateIn,
    cmd: Annotated[
        CommandContext, Depends(command(reconciliations.PREPARE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Explain a difference (``If-Match`` of the item) while the reconciliation is ``DRAFT``; 409
    ``invalid-transition`` afterwards."""

    def handle(uow: UnitOfWork) -> ReconciliationItemOut:
        return reconciliations.explain_item(
            uow,
            reconciliation_id=reconciliation_id,
            item_id=item_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))


@router.post(
    "/reconciliations/{reconciliation_id}/prepare",
    operation_id="reconciliations_prepare",
    response_model=ReconciliationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def reconciliations_prepare(
    reconciliation_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(reconciliations.PREPARE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Sign as preparer (``DRAFT`` → ``PREPARED``) in an MFA-verified session; every difference
    needs its explanation first. The snapshot is frozen for review."""

    def handle(uow: UnitOfWork) -> ReconciliationOut:
        return reconciliations.prepare(uow, reconciliation_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/reconciliations/{reconciliation_id}/sign",
    operation_id="reconciliations_sign",
    response_model=ReconciliationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "self-approval", "mfa-step-up-required"),
)
def reconciliations_sign(
    reconciliation_id: uuid.UUID,
    body: ReconciliationSignIn,
    cmd: Annotated[CommandContext, Depends(command(reconciliations.SIGNOFF_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Sign as reviewer (``PREPARED`` → ``REVIEWED``) with a fresh step-up verification. 403
    ``self-approval`` for a preparer of the reconciliation (DB-10); 403 ``forbidden`` for a user
    who manages integrations (SoD-7)."""

    def handle(uow: UnitOfWork) -> ReconciliationOut:
        return reconciliations.sign(uow, reconciliation_id, body)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/reconciliations/{reconciliation_id}/reopen",
    operation_id="reconciliations_reopen",
    response_model=ReconciliationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def reconciliations_reopen(
    reconciliation_id: uuid.UUID,
    body: ReconciliationReopenIn,
    cmd: Annotated[CommandContext, Depends(command(reconciliations.REOPEN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Reopen a prepared or reviewed reconciliation (``REOPENED``): its sign-offs stay as history
    and the reconciliation is generated again. A certified reconciliation answers 409: it is
    reopened only by the reopen of its period."""

    def handle(uow: UnitOfWork) -> ReconciliationOut:
        return reconciliations.reopen(uow, reconciliation_id, body)

    return run_command(cmd, deps, handle, etag=_etag)
