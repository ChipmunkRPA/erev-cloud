"""API-R-44 Exceptions: the shared exception queue and its commands.

04 §15.3 API-R-44, §16.14 exception item additions, T-IMP-05, E-42 to E-44, E-106, E-117, API-C-08,
API-C-11; PRD SM-06, BR-DAT-04, ACT-17, ACT-18; SCREENS §13.4; 03 REQ-DAT-009; BUILD_SPEC DIN-11.
Reads need ``contract.read``; commands need ``exception.resolve``, which the handlers check for the
item's entity. Single-item responses carry ``ETag`` ``"r<row_version>"``; no route takes
``If-Match``, because API-C-08 requires it for contract commands and configuration updates only.
No route deletes an item (REQ-DAT-009). Every route answers for the items the caller may read
(``exceptions.readable``; 04 T-IMP-05 "An item that names no entity: who reads it", rev 1.218):
the item of an import that names no entity is listed, read and acted on by the readers of its
import, and its id answers 404 to anyone else, as an unknown one.

The list sorts by ``severity`` (the default: BLOCKING, WARNING, INFO, then newest first by the
time-ordered id), ``created_at`` or ``-created_at``. ``entity`` takes an entity code or id and
``period`` a ``period_key`` or id (API-C-11); ``owner`` takes ``me`` or a membership id.

One attribution of an item to an entity (04 T-IMP-05 "An item that names no entity", §16.14,
rev 1.206; supervisor ruling R-121 (i); item CLO-QUARANTINE-READ-1): ``entity`` lists the items
that are the entity's by the close gates' rule (``gates.item_of_entity``) — the item names the
entity, a contract of it, a contract group holding a contract of it, or nothing and is the
entity's by its import or its connection, or every entity's — and not only the items whose own
column holds the entity. ``blocking`` takes the id of one API-S-Period — an entity, book and
period — and lists the subset the close gates count for it: the gates' own predicate
(``gates.blocking_exceptions``), so ``blockers.exceptions_open`` and the list cannot part.
``period`` compares the item's own column: an engine item carries no period.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

import sqlalchemy as sa
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
    invalid,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import exception_item, legal_entity, period
from erev_api.domain.close import gates
from erev_api.domain.imports import exceptions, queries
from erev_api.enums import ExceptionSeverity, ExceptionSource, ExceptionStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.exceptions import (
    ExceptionAssignIn,
    ExceptionCommentIn,
    ExceptionItemOut,
    ExceptionResolveIn,
    WaiverRequestedOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-44 Exceptions"
READ: Final = "contract.read"
RESOLVE: Final = exceptions.RESOLVE_PERMISSION
ME: Final = "me"
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "invalid-transition",
)


def _choices(literals: Any) -> frozenset[str]:
    return frozenset(item.value for item in literals)


EXCEPTION_LIST: Final = ListSpec(
    resource="exceptions",
    sort_keys={
        "id": exception_item.c.id,
        "severity": exception_item.c.severity,
        "created_at": exception_item.c.created_at,
    },
    default_sort="severity",
    directions={"severity": "asc"},  # E-43 order BLOCKING, WARNING, INFO (04 API-R-44)
    filters={
        "status": FilterSpec(
            "status", exception_item.c.status, "exact", choices=_choices(ExceptionStatus)
        ),
        "severity": FilterSpec(
            "severity", exception_item.c.severity, "exact", choices=_choices(ExceptionSeverity)
        ),
        "source": FilterSpec(
            "source", exception_item.c.source, "exact", choices=_choices(ExceptionSource)
        ),
        "code": FilterSpec("code", exception_item.c.code, "exact"),
        "contract": FilterSpec("contract", exception_item.c.contract_id, "exact"),
        "import_upload_id": FilterSpec(
            "import_upload_id", exception_item.c.import_upload_id, "exact"
        ),
        "sync_run_id": FilterSpec("sync_run_id", exception_item.c.sync_run_id, "exact"),
    },
    search_columns=(
        exception_item.c.exception_no,
        exception_item.c.title,
        exception_item.c.message,
        exception_item.c.business_key,
    ),
    custom_filters=frozenset({"blocking", "entity", "owner", "period"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _etag(out: ExceptionItemOut) -> str:
    return row_etag(out.row_version)


def _id_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _code_or_id(
    column: sa.ColumnElement[Any],
    values: tuple[str, ...],
    id_column: sa.ColumnElement[Any],
    key_column: sa.ColumnElement[Any],
) -> sa.ColumnElement[bool]:
    """API-C-11: each value is an id, or a code or key resolved through ``key_column``."""
    ids = [found for value in values if (found := _id_or_none(value)) is not None]
    keys = [value for value in values if _id_or_none(value) is None]
    clauses: list[sa.ColumnElement[bool]] = []
    if ids:
        clauses.append(column.in_(ids))
    if keys:
        clauses.append(column.in_(sa.select(id_column).where(key_column.in_(keys))))
    return sa.or_(*clauses)


def _blocking(session: Session, values: tuple[str, ...]) -> sa.ColumnElement[bool]:
    """``blocking``: the items the close gates count for one period state. A period the caller
    cannot read — unknown, or of an entity outside the caller's scope (T-REF-06 is RLS-TE) —
    lists nothing, as an unknown ``contract`` id does."""
    if len(values) != 1:
        raise invalid("blocking", "Send blocking once.")
    state_id = _id_or_none(values[0])
    if state_id is None:
        raise invalid("blocking", "blocking must be a period id.")
    scope = gates.period_scope(session, state_id)
    return sa.false() if scope is None else gates.blocking_exceptions(scope)


def _of_entities(session: Session, values: tuple[str, ...]) -> sa.ColumnElement[bool]:
    """``entity``: the items of the named entities by the gates' attribution. Each value is an
    id or a code (API-C-11), resolved among the entities the caller reads (T-REF-01 is RLS-TE);
    a value that names none of them lists nothing, as an unknown code did before."""
    ids = [found for value in values if (found := _id_or_none(value)) is not None]
    codes = [value for value in values if _id_or_none(value) is None]
    named: list[sa.ColumnElement[bool]] = []
    if ids:
        named.append(legal_entity.c.id.in_(ids))
    if codes:
        named.append(legal_entity.c.code.in_(codes))
    entity_ids = session.scalars(sa.select(legal_entity.c.id).where(sa.or_(*named))).all()
    if not entity_ids:
        return sa.false()
    return sa.or_(*(gates.item_of_entity(entity_id) for entity_id in entity_ids))


def _statement(
    session: Session, ctx: RequestContext, filters: dict[str, tuple[str, ...]]
) -> sa.Select[Any]:
    """The item statement with the custom filters of the module docstring, for the items the
    caller may read (``exceptions.readable``; 04 T-IMP-05 rev 1.218, item EXC-IMPORT-SCOPE-1):
    beside the row policy, the item of an import that names no entity is listed for the
    readers of that import only — under ``entity`` and ``blocking`` as under no filter."""
    statement = exceptions.item_select().where(exceptions.readable(ctx.principal))
    blocking = filters.get("blocking")
    if blocking:
        statement = statement.where(_blocking(session, blocking))
    entities = filters.get("entity")
    if entities:
        statement = statement.where(_of_entities(session, entities))
    periods = filters.get("period")
    if periods:
        statement = statement.where(
            _code_or_id(exception_item.c.period_id, periods, period.c.id, period.c.period_key)
        )
    owners = filters.get("owner")
    if owners:
        if len(owners) != 1:
            raise invalid("owner", "Send owner once.")
        (owner,) = owners
        if owner == ME:
            membership = ctx.principal.membership_id
            statement = statement.where(
                sa.false()
                if membership is None
                else exception_item.c.owner_membership_id == membership
            )
        else:
            found = _id_or_none(owner)
            if found is None:
                raise invalid("owner", "owner must be me or a membership id.")
            statement = statement.where(exception_item.c.owner_membership_id == found)
    return statement


@router.get(
    "/exceptions",
    operation_id="exceptions_list",
    response_model=ListOut[ExceptionItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def exceptions_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[list[ExceptionStatus] | None, Query(description="E-44")] = None,
    severity: Annotated[list[ExceptionSeverity] | None, Query(description="E-43")] = None,
    source: Annotated[list[ExceptionSource] | None, Query(description="E-42")] = None,
    code: Annotated[list[str] | None, Query(description="A 04 §15.4 code")] = None,
    contract: Annotated[list[uuid.UUID] | None, Query(description="A contract id")] = None,
    entity: Annotated[
        list[str] | None, Query(description="An entity code or id: the items that are the entity's")
    ] = None,
    owner: Annotated[str | None, Query(description="me or a membership id")] = None,
    period: Annotated[list[str] | None, Query(description="A period_key or id")] = None,
    blocking: Annotated[
        str | None, Query(description="An API-S-Period id: the items its close gates count")
    ] = None,
    import_upload_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    sync_run_id: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> ListOut[ExceptionItemOut]:
    """Exception items; sort ``severity`` (default), ``created_at`` or ``-created_at``."""
    filters = {name: tuple(values) for name, values in params.filters.items()}

    def page(session: Session) -> tuple[ListResult, list[ExceptionItemOut]]:
        result = paginate(session, _statement(session, ctx, filters), EXCEPTION_LIST, params)
        return result, exceptions.item_outs(session, result.items, ctx.principal)

    result, items = queries.read(ctx, page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ExceptionItemOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/exceptions/{item_id}",
    operation_id="exceptions_get",
    response_model=ExceptionItemOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def exceptions_get(item_id: uuid.UUID, response: Response, ctx: ReadContext) -> ExceptionItemOut:
    """Every T-IMP-05 column with ``available_actions`` and ``dismiss_blocked_reason``."""
    out = queries.read(ctx, lambda session: exceptions.get_item(session, ctx.principal, item_id))
    response.headers["ETag"] = _etag(out)
    return out


@router.post(
    "/exceptions/{item_id}/assign",
    operation_id="exceptions_assign",
    response_model=ExceptionItemOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def exceptions_assign(
    item_id: uuid.UUID,
    body: ExceptionAssignIn,
    cmd: Annotated[CommandContext, Depends(command(RESOLVE))],
    deps: Deps,
) -> Response:
    """Record the owner; OPEN becomes IN_PROGRESS and the owner is notified (NTF-11)."""

    def handle(uow: UnitOfWork) -> ExceptionItemOut:
        return exceptions.assign(uow, item_id=item_id, owner_membership_id=body.owner_membership_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/exceptions/{item_id}/resolve",
    operation_id="exceptions_resolve",
    response_model=ExceptionItemOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def exceptions_resolve(
    item_id: uuid.UUID,
    body: ExceptionResolveIn,
    cmd: Annotated[CommandContext, Depends(command(RESOLVE))],
    deps: Deps,
) -> Response:
    """Mark the item resolved once the server finds its condition cleared."""

    def handle(uow: UnitOfWork) -> ExceptionItemOut:
        return exceptions.resolve(uow, item_id=item_id, resolution=body.resolution)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/exceptions/{item_id}/reprocess",
    operation_id="exceptions_reprocess",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def exceptions_reprocess(
    item_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(RESOLVE))],
    deps: Deps,
) -> Response:
    """Reprocess a remediable item's input; the job resolves the item when it is processed."""

    def handle(uow: UnitOfWork) -> JobOut:
        return exceptions.request_reprocess(uow, item_id=item_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda out: JOB_PATH.format(job_id=out.id),
    )


@router.post(
    "/exceptions/{item_id}/request-waiver",
    operation_id="exceptions_request_waiver",
    response_model=WaiverRequestedOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def exceptions_request_waiver(
    item_id: uuid.UUID,
    body: ExceptionCommentIn,
    cmd: Annotated[CommandContext, Depends(command(RESOLVE))],
    deps: Deps,
) -> Response:
    """Open an ``EXCEPTION_WAIVER`` request, approved by an ``exception.waive`` holder other than
    the requester and the item owner (PRD SM-06)."""

    def handle(uow: UnitOfWork) -> WaiverRequestedOut:
        return exceptions.request_waiver(uow, item_id=item_id, comment=body.comment)

    return run_command(cmd, deps, handle)


@router.post(
    "/exceptions/{item_id}/dismiss",
    operation_id="exceptions_dismiss",
    response_model=ExceptionItemOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def exceptions_dismiss(
    item_id: uuid.UUID,
    body: ExceptionCommentIn,
    cmd: Annotated[CommandContext, Depends(command(RESOLVE))],
    deps: Deps,
) -> Response:
    """Dismiss an item whose input was never committed, with a comment (PRD BR-DAT-04)."""

    def handle(uow: UnitOfWork) -> ExceptionItemOut:
        return exceptions.dismiss(uow, item_id=item_id, comment=body.comment)

    return run_command(cmd, deps, handle, etag=_etag)
