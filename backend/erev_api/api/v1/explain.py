"""API-R-49 Explain: figure explanations, verification and calculation traces.

04 §15.3 API-R-49, §16.11 API-S-Explain, §16.14 API-S-CalcTrace, API-C-03, API-C-04, API-C-10,
API-C-11; dev-guide §5.16 DG-KRN-EXP-06; SCREENS §6.3 to §6.5 (R-19 to R-21); BUILD_SPEC CTR-19.

For ``obligation`` a to-date measure without ``period`` is the figure ``GET /obligations/{id}``
serves: the period node at the cut of ``as_of`` (04 API-C-10 and §16.11, rev 1.132), resolved here
because the kernel's explain service does not read the domain.

The routes need ``contract.read``, the permission of engine figures (SCREENS §6.1). The report-cell
route is built by RPS (BS3-D-04; [J] L4-4-Q-9) and needs the permission of the run's report, as
the routes of API-R-41 do (``_run_admitted``; supervisor ruling R-63 (a)). Reads run in a
read-only tenant session, so an object outside the caller's entities answers 404 (REQ-PLT-012).
``verify`` is a command (``Idempotency-Key``, API-C-04) whose handler only reads: it recomputes the
stored trace and changes no data; only the idempotency record is kept.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import invalid
from erev_api.auth.dependencies import require, require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.domain.contracts import obligations, queries, to_date
from erev_api.domain.reports import framework
from erev_api.enums import BookCode
from erev_api.explain import service
from erev_api.problems import Problem
from erev_api.schemas.common import MeasuredPeriodOut
from erev_api.schemas.explain import (
    CalcTraceOut,
    ExplainCellOut,
    ExplainObjectType,
    ExplainOut,
    ExplainVerifyOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-49 Explain"
READ: Final = "contract.read"
OBLIGATION: Final = "obligation"
# The to-date measures of an obligation that hold a node per period (04 API-C-10 rev 1.132).
TO_DATE: Final = frozenset({to_date.REVENUE, to_date.BILLED, to_date.PROGRESS})
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "not-found")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)


def _run_admitted(
    request: Request, ctx: Annotated[RequestContext, Depends(require_authenticated())]
) -> RequestContext:
    """The guard of the report-cell route (04 API-R-49; supervisor ruling R-63 (a)): as the routes
    of API-R-41, it is open to a principal that may run a report, and the run's report decides
    (``framework.explain_cell``); any other principal is refused 403 after one ``DENIED`` event."""
    route = request.scope.get("route")
    framework.require_admitted(
        ctx,
        method=request.method,
        path=str(getattr(route, "path", request.url.path)),
        keyring=request.app.state.keyring,
    )
    return ctx


type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type RunContext = Annotated[RequestContext, Depends(_run_admitted)]
type Period = Annotated[str | None, Query(description="Period key of a figure by period")]
type Book = Annotated[BookCode | None, Query(description="Default the primary book (API-C-11)")]
type AsOf = Annotated[date | None, Query(description="Effective cut-off (API-C-10)")]
type KnownAt = Annotated[
    datetime | None, Query(description="Record cut-off, RFC 3339 with an offset (API-C-10)")
]
type Depth = Annotated[
    int,
    Query(
        ge=0,
        le=service.MAX_DEPTH,
        description="Levels of inputs below the figure (default 6, maximum 20)",
    ),
]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _known_at(known_at: datetime | None) -> datetime | None:
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")
    return known_at


def _at_cut(
    session: Session,
    *,
    object_type: ExplainObjectType,
    object_id: uuid.UUID,
    measure: str,
    period: str | None,
    params: queries.ReadParams,
    now: datetime,
) -> tuple[str | None, MeasuredPeriodOut | None]:
    """The period key to explain and the period a to-date measure was resolved to.

    04 §16.11 (rev 1.132): for ``obligation``, a to-date measure without ``period`` is the figure
    the obligation read serves — the period node at the cut of ``as_of`` — and not the version's
    node at d_v. 404 ``not-found`` when ``as_of`` precedes the first period the version measures:
    the figure is 0 and no node holds it. Any other figure keeps ``period`` as sent."""
    name = service.MEASURE_ALIASES.get(measure, measure)
    if object_type != OBLIGATION or period is not None or name not in TO_DATE:
        return period, None
    measured = obligations.measured_period(session, object_id, name, params=params, now=now)
    if measured is None:
        raise Problem("not-found", service.NOT_TRACED)
    return measured.period_key, queries.measured_out(measured)


@router.get(
    "/explain/report-runs/{run_id}/cell",
    operation_id="explain_report_cell",
    response_model=ExplainCellOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "invalid-transition"),
)
def explain_report_cell(
    run_id: uuid.UUID,
    ctx: RunContext,
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    row_key: Annotated[str, Query(min_length=1, description="The row's row_key")],
    column_key: Annotated[str, Query(min_length=1, description="The column key of the figure")],
) -> ExplainCellOut:
    """``{value, contributors}`` of one figure of a SUCCEEDED report run, each contributor with the
    href of its own explanation (SCREENS_B SB-R-07; REQ-RPT-017). Registered before the figure
    route, whose path it would otherwise match."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return framework.explain_cell(
            ctx, session, run_id, row_key=row_key, column_key=column_key, keyring=deps.keyring
        )


@router.get(
    "/explain/{object_type}/{object_id}/{measure}",
    operation_id="explain_get",
    response_model=ExplainOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def explain_get(
    object_type: ExplainObjectType,
    object_id: uuid.UUID,
    measure: str,
    ctx: ReadContext,
    period: Period = None,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
    depth: Depth = service.DEFAULT_DEPTH,
) -> ExplainOut:
    """API-S-Explain of one figure: the stored value, its trace nodes to ``depth`` levels, the
    narrative from ``NARRATIVES``, history and drill links (REQ-RPT-017, REQ-RPT-018)."""
    cutoff = _known_at(known_at)
    book_code = None if book is None else book.value
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        period_key, measured = _at_cut(
            session,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            period=period,
            params=queries.ReadParams(book=book_code, as_of=as_of, known_at=cutoff),
            now=ctx.now,
        )
        return service.explain_measure(
            session,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            book_code=book_code,
            as_of=as_of,
            known_at=cutoff,
            now=ctx.now,
            period_key=period_key,
            depth=depth,
            measured=measured,
        )


@router.post(
    "/explain/{object_type}/{object_id}/{measure}/verify",
    operation_id="explain_verify",
    response_model=ExplainVerifyOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def explain_verify(
    object_type: ExplainObjectType,
    object_id: uuid.UUID,
    measure: str,
    cmd: Annotated[CommandContext, Depends(command(READ))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    period: Period = None,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> Response:
    """Recompute the figure's node from the stored trace with ``reevaluate`` (DG-KRN-EXP-04):
    200 ``{recomputed_value, stored_value, matches}``; no data changes. The node is the one the
    read of the same figure explains (``_at_cut``)."""

    def handle(uow: UnitOfWork) -> ExplainVerifyOut:
        cutoff = _known_at(known_at)
        book_code = None if book is None else book.value
        period_key, _ = _at_cut(
            uow.session,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            period=period,
            params=queries.ReadParams(book=book_code, as_of=as_of, known_at=cutoff),
            now=uow.now,
        )
        return service.verify_measure(
            uow.session,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            book_code=book_code,
            known_at=cutoff,
            period_key=period_key,
        )

    return run_command(cmd, deps, handle)


@router.get(
    "/calc-traces/{trace_id}",
    operation_id="calc_traces_get",
    response_model=CalcTraceOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def calc_traces_get(trace_id: uuid.UUID, ctx: ReadContext) -> CalcTraceOut:
    """API-S-CalcTrace: the stored T-ENG-03 row with every node (SCREENS R-21)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return service.calc_trace_out(session, trace_id)
