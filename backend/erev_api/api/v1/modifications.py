"""API-R-31 Modifications (04 §15.3 API-R-31, T-CON-06, §16.14 API-S-Modification; PRD SM-03, §2.5
routing row ``MODIFICATION``, ERR-53 / ERR-54; SCREENS §7.5 to §7.8; BUILD_SPEC CTR-17; D-98 140).

Reads need ``contract.read``; commands need ``modification.create``, which the handlers check for
the contracting entity. No route takes ``If-Match``; ``GET /modifications/{id}`` and every command
answering the row carry ``ETag "r<row_version>"`` (API-C-08; D-98 140-A4).
The subscription-change actions of API-R-31 are CTR-18's (D-98 140 Q-2).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Annotated, Any, Final

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
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.tables import modification
from erev_api.domain.contracts import modifications, queries, repo
from erev_api.enums import ModificationStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.modifications import (
    ModificationCreateIn,
    ModificationListItemOut,
    ModificationOut,
    ModificationSubmitIn,
    ModificationUpdateIn,
    ModificationWithdrawIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-31 Modifications"
READ: Final = "contract.read"
CREATE: Final = modifications.CREATE_PERMISSION
JOB_PATH: Final = "/api/v1/jobs/{job_id}"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "invalid-transition",
)
MODIFICATION_LIST: Final = ListSpec(
    resource="modifications",
    sort_keys={
        "id": modification.c.id,
        "modification_no": modification.c.modification_no,
        "effective_date": modification.c.effective_date,
        "created_at": modification.c.created_at,
    },
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"status", "effective_from", "effective_to"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = str(result.total_count)


def _job_headers(job: Any) -> dict[str, str]:
    return {"Location": JOB_PATH.format(job_id=job.id)}


def _etag(out: ModificationOut) -> str:
    """API-C-08: the row is IM-S with SC-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _previews(
    session: Session, deps: KernelDeps, rows: Sequence[Mapping[str, Any]]
) -> dict[uuid.UUID, Mapping[str, Any]]:
    """The retained preview documents of the rows that store one (list ``catch_up_total``)."""
    found: dict[uuid.UUID, Mapping[str, Any]] = {}
    for row in rows:
        if row["impact_preview_file_id"] is None:
            continue
        document = modifications.read_preview(session, row, files=deps.files, keyring=deps.keyring)
        if document is not None:
            found[uuid.UUID(str(row["id"]))] = document
    return found


def _with_preview(
    deps: KernelDeps,
) -> Callable[[Session, Principal, uuid.UUID], ModificationOut]:
    """A reader of one row with its stored preview, for one principal (the route holds the file
    store and keyring). The ONE place a stored preview enters an answer — the read, and the
    answer of every command that keeps the preview — so it is where the preview is withheld
    from a reader of the row who is not answered it (04 §16.10 "Who reads a stored preview",
    rev 1.300; item MOD-PREVIEW-READ-SCOPE-1): no summary, no file id, and the member that
    says so. The catch-up a list item states is stated here too, to every reader."""

    def read(session: Session, principal: Principal, modification_id: uuid.UUID) -> ModificationOut:
        row = modifications.get_modification(session, modification_id)
        stored = (
            session.execute(modification.select().where(modification.c.id == modification_id))
            .mappings()
            .one()
        )
        document = modifications.read_preview(
            session, dict(stored), files=deps.files, keyring=deps.keyring
        )
        if document is None:
            return row
        return modifications.get_modification(
            session,
            modification_id,
            preview=document,
            preview_withheld=not modifications.preview_answered(
                session, principal, modification_id
            ),
        )

    return read


def _answer(deps: KernelDeps, uow: UnitOfWork, modification_id: uuid.UUID) -> ModificationOut:
    """The answer of a command whose row keeps its retained preview — ``/submit``, ``/withdraw``
    and ``/discard`` — read as ``GET`` reads it (04 §16.14 rev 1.188; item MOD-ANSWER-PREVIEW-1,
    supervisor ruling R-119 (e)). The domain command holds no file store, so its own answer
    carried ``impact_preview: null`` beside a stored preview. ``PATCH`` and ``/classify`` clear
    the stored preview themselves; their answers carry none."""
    return _with_preview(deps)(uow.session, uow.principal, modification_id)


@router.get(
    "/contracts/{contract_id}/modifications",
    operation_id="contract_modifications_list",
    response_model=ListOut[ModificationListItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_modifications_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    deps: Deps,
    status: Annotated[list[ModificationStatus] | None, Query(description="E-26")] = None,
    effective_from: Annotated[date | None, Query()] = None,
    effective_to: Annotated[date | None, Query()] = None,
) -> ListOut[ModificationListItemOut]:
    """The contract's modifications (04 §16.14 list items); sort ``id`` (default ``-id``),
    ``modification_no``, ``effective_date`` or ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[ModificationListItemOut]]:
        repo.get_contract(session, contract_id)
        statement = modifications.modifications_statement(
            contract_id=contract_id,
            statuses=tuple(status or ()),
            effective_from=effective_from,
            effective_to=effective_to,
        )
        result = paginate(session, statement, MODIFICATION_LIST, params)
        rows = [dict(row) for row in result.items]
        return result, modifications.modification_outs(
            session, rows, previews=_previews(session, deps, rows)
        )

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[ModificationListItemOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/contracts/{contract_id}/modifications",
    operation_id="contract_modifications_create",
    status_code=201,
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def contract_modifications_create(
    contract_id: uuid.UUID,
    body: ModificationCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """A DRAFT modification of an ACTIVE contract (SM-03; REQ-MOD-001)."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        return modifications.create_modification(uow, contract_id=contract_id, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/modifications/{out.id}",
    )


@router.get(
    "/modifications/{modification_id}",
    operation_id="modifications_get",
    response_model=ModificationOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def modifications_get(
    modification_id: uuid.UUID, response: Response, ctx: ReadContext, deps: Deps
) -> ModificationOut:
    """API-S-Modification with its retained preview; ``ETag "r<row_version>"`` (API-C-08)."""
    read = _with_preview(deps)
    out: ModificationOut = queries.read(
        ctx, lambda session: read(session, ctx.principal, modification_id)
    )
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    "/modifications/{modification_id}",
    operation_id="modifications_update",
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_update(
    modification_id: uuid.UUID,
    body: ModificationUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Edit a DRAFT; an edit of a SUBMITTED row returns it to DRAFT and voids its request
    STALE_SUBJECT (SM-03; CTL-007); an edit of a REJECTED row returns it to DRAFT ("Revise"; 04
    §16.14 rev 1.236) and its rejected request stays closed. The classification and the preview
    are redone afterwards."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        return modifications.update_modification(uow, modification_id=modification_id, body=body)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/modifications/{modification_id}/classify",
    operation_id="modifications_classify",
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_classify(
    modification_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """The engine's treatment proposal per obligation (S06-R-01, S06-R-04, S06-R-05; REQ-MOD-002),
    stored as ``proposed_treatments`` / ``treatment_summary``; the response adds
    ``prefill_reasons``."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        return modifications.classify(uow, modification_id=modification_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/modifications/{modification_id}/preview",
    operation_id="modifications_preview",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_preview(
    modification_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Defer the dry run with the candidate ``CONTRACT_AMENDED`` (S06-R-02; REQ-MOD-013); the job's
    ``result.summary`` is API-S-ImpactSummary and the run stores the preview snapshot on the row."""

    def handle(uow: UnitOfWork) -> JobOut:
        return modifications.request_preview(uow, modification_id=modification_id)

    return run_command(cmd, deps, handle, status_code=202, extra_headers=_job_headers)


@router.post(
    "/modifications/{modification_id}/submit",
    operation_id="modifications_submit",
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_submit(
    modification_id: uuid.UUID,
    body: ModificationSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Route the ``MODIFICATION`` request (SM-03; REQ-PLT-015; REQ-MOD-002; PRD §2.5)."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        modifications.submit(uow, modification_id=modification_id, body=body)
        return _answer(deps, uow, modification_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/modifications/{modification_id}/withdraw",
    operation_id="modifications_withdraw",
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_withdraw(
    modification_id: uuid.UUID,
    body: ModificationWithdrawIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """The preparer withdraws the pending request; the row returns to DRAFT (SM-03)."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        modifications.withdraw(uow, modification_id=modification_id, body=body)
        return _answer(deps, uow, modification_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/modifications/{modification_id}/discard",
    operation_id="modifications_discard",
    response_model=ModificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def modifications_discard(
    modification_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Discard a DRAFT without a pending request: it becomes VOIDED (SM-03; PRD ERR-82). No
    body: the screen asks for a confirmation, not a reason."""

    def handle(uow: UnitOfWork) -> ModificationOut:
        modifications.discard(uow, modification_id=modification_id)
        return _answer(deps, uow, modification_id)

    return run_command(cmd, deps, handle, etag=_etag)
