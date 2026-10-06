"""API-R-18 Calendars and periods: period reads, ``open``, soft close and the close cockpit.

04 §15.3 API-R-18, §16.8 API-S-Period, API-S-PeriodCockpit, "Period commands", API-C-03, API-C-08,
API-C-11; BUILD_SPEC RFD-2, CLO-3, CLO-4. Reads need ``config.read`` and return only the period
states of entities in the principal's scope, with the close blockers of API-S-Period. ``open``
needs ``period.close``, or ``settings.manage`` while setup is incomplete — the stamp unset and the
conditions of PRD BR-PLT-02 not holding (``setup.rule_ended``; SCREENS_B OQ-B-19): the permission
depends on tenant state, so the route uses
``command(per_subject=True)``, the handler authorises, then checks ``If-Match``. The calendar routes
of API-R-18 live in ``calendars.py`` and the close task routes in ``close_checklist_templates.py``.
CLO-3 adds ``start-close`` and ``cancel-close`` (``period.close``, ``If-Match`` required) and the
transition history. CLO-4 adds the cockpit and checklist reads and the ``sign`` and ``waive``
commands (``period.close``, ``If-Match`` of the period state). A read appends no audit event and
writes nothing unless the stored checklist differs from what the reader must see — then the route
materialises it as the SYSTEM principal, without audit events (``commands.materialise_checklist``;
security finding SC-8, supervisor ruling R-32; 04 T-CLS-03 rev 1.106) — the one event such a read
appends is the lapse of a waiver its gate has outgrown (rev 1.305). The data-quality monitors
run before ``start-close`` and ``request-lock`` (``commands.run_period_monitors``, SYSTEM, their
own unit of work) and in the scheduled sweep (05 SCH-10), never on a GET.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    expected_version,
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
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.db.tables import period_state, period_state_transition
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import queries as close_queries
from erev_api.domain.reference import commands
from erev_api.domain.reference import periods as close_rules
from erev_api.enums import BookCode, PeriodState
from erev_api.problems import Problem
from erev_api.schemas.close import (
    ChecklistItemOut,
    ChecklistSignIn,
    ChecklistWaiveIn,
    ChecklistWaiverOut,
    PeriodCockpitOut,
)
from erev_api.schemas.common import ListOut
from erev_api.schemas.periods import (
    PeriodCancelCloseIn,
    PeriodLockRequestIn,
    PeriodLockRequestOut,
    PeriodLockRowOut,
    PeriodOpenIn,
    PeriodOut,
    PeriodPermanentLockRequestIn,
    PeriodPermanentLockRequestOut,
    PeriodReopenRequestIn,
    PeriodReopenRequestOut,
    PeriodStartCloseIn,
    PeriodTransitionOut,
)
from erev_api.uow import UnitOfWork, unit_of_work

TAG: Final = "API-R-18 Calendars and periods"
READ_PERMISSION: Final = "config.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
PERIOD_LIST: Final = ListSpec(
    resource="periods",
    sort_keys={"id": period_state.c.id, "period_end_date": period_state.c.period_end_date},
    default_sort="period_end_date",
    filters={
        "state": FilterSpec(
            name="state",
            column=period_state.c.state,
            kind="in",
            choices=frozenset(member.value for member in PeriodState),
        ),
    },
    custom_filters=frozenset({"entity", "book", "period", "fiscal_year"}),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def period_etag(out: PeriodOut) -> str:
    """API-C-08: the ETag of a period state is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/periods",
    operation_id="periods_list",
    response_model=ListOut[PeriodOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def periods_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    entity: Annotated[list[str] | None, Query(description="Entity code or id; repeatable")] = None,
    book: Annotated[BookCode | None, Query(description="Default: the primary book")] = None,
    period: Annotated[
        str | None, Query(description="Period key or id (API-C-11): that period alone")
    ] = None,
    state: Annotated[list[PeriodState] | None, Query()] = None,
    fiscal_year: Annotated[int | None, Query(ge=1900, le=2999)] = None,
) -> ListOut[PeriodOut]:
    """API-S-Period rows of the entities in scope for one book, each with its newest close run
    and its current lock; ``blockers`` is null in a row of the list — ``GET /periods/{id}`` and
    the cockpit answer the counts (04 §16.8 rev 1.199). Sort ``period_end_date`` (default) or
    ``id``."""
    result, items = close_queries.list_period_views(
        ctx,
        entities=entity or (),
        book_code=None if book is None else book.value,
        period_value=period,
        fiscal_year=fiscal_year,
        page=lambda session, statement: paginate(session, statement, PERIOD_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PeriodOut](
        items=[PeriodOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.get(
    "/periods/{period_id}",
    operation_id="periods_get",
    response_model=PeriodOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def periods_get(
    period_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> PeriodOut:
    """One period state with its close blockers and ``ETag``; 404 outside the principal's entity
    scope."""
    out = PeriodOut.model_validate(close_queries.get_period_view(ctx, period_id))
    response.headers["ETag"] = period_etag(out)
    return out


@router.post(
    "/periods/{period_id}/open",
    operation_id="periods_open",
    response_model=PeriodOut,
    responses=problem_responses(
        *_READ_PROBLEMS,
        "mfa-required",
        "validation-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
        "not-found",
        "precondition-failed",
        "precondition-required",
        "invalid-transition",
    ),
)
def periods_open(
    period_id: uuid.UUID,
    body: PeriodOpenIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Open a future period (``future`` → ``open``); ``If-Match`` required. Periods open in
    order: 409 ``invalid-transition`` while the previous period of the entity and book is
    future."""

    def handle(uow: UnitOfWork) -> PeriodOut:
        commands.open_period(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(
                expected_version(cmd.ctx.if_match, "row"), actual
            ),
        )
        shown = close_queries.period_view(uow.session, period_id)
        if shown is None:
            raise Problem("not-found")
        return PeriodOut.model_validate(shown)

    return run_command(cmd, deps, handle, etag=period_etag)


_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "precondition-failed",
    "precondition-required",
    "invalid-transition",
)


@router.post(
    "/periods/{period_id}/start-close",
    operation_id="periods_start_close",
    response_model=PeriodOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def periods_start_close(
    period_id: uuid.UUID,
    body: PeriodStartCloseIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.CLOSE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start soft close (``open`` or ``reopened`` → ``closing``); ``If-Match`` required (CLO-3).
    The data-quality monitors of the period run first."""

    def handle(uow: UnitOfWork) -> PeriodOut:
        _monitored(cmd.ctx, deps, period_id)
        return close_commands.start_close(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=period_etag)


@router.post(
    "/periods/{period_id}/cancel-close",
    operation_id="periods_cancel_close",
    response_model=PeriodOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def periods_cancel_close(
    period_id: uuid.UUID,
    body: PeriodCancelCloseIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.CLOSE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """End soft close with a reason of the table 3.4-R subset: the period returns to the state its
    soft close started from — ``open``, or ``reopened`` for a period that has been locked before
    (PRD SM-07; 04 §16.8 rev 1.170); ``If-Match`` required (CLO-3)."""

    def handle(uow: UnitOfWork) -> PeriodOut:
        return close_commands.cancel_close(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=period_etag)


TRANSITION_LIST: Final = ListSpec(
    resource="period-transitions",
    sort_keys={
        "id": period_state_transition.c.id,
        "created_at": period_state_transition.c.created_at,
    },
    default_sort="-id",
    filters={},
)


@router.get(
    "/periods/{period_id}/transitions",
    operation_id="periods_transitions_list",
    response_model=ListOut[PeriodTransitionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def periods_transitions_list(
    period_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[PeriodTransitionOut]:
    """The state history of a period: from and to state, reason, comment and actor; sort ``id``
    (default ``-id``, newest first) or ``created_at``."""

    def page(
        session: Session, statement: Select[Any]
    ) -> tuple[ListResult, list[PeriodTransitionOut]]:
        result = paginate(session, statement, TRANSITION_LIST, params)
        return result, close_queries.transition_outs(session, result.items)

    result, items = close_queries.list_transitions(ctx, period_id, page=page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PeriodTransitionOut](items=items, next_cursor=result.next_cursor)


# --- the close cockpit (CLO-4) -------------------------------------------------------------------


def _materialised(ctx: RequestContext, deps: KernelDeps, state_id: uuid.UUID) -> None:
    """The checklist of a period the reader sees, brought up to date as the SYSTEM principal: the
    items of every active template exist and each automatic gate holds its evaluated result
    (T-CLS-03). Nothing is committed unless a row had to be written, and no audit event is written
    in either case — a GET is a read (security finding SC-8; supervisor ruling R-32) — but for
    the lapse of a waiver its gate has outgrown, which is on the trail whoever stores it (04
    T-CLS-03 rev 1.305; the supervisor's ruling of 2026-10-02 20:22). 404 ``not-found`` outside
    the reader's scope."""
    close_queries.visible_scope(ctx, state_id)
    system = dataclasses.replace(ctx, principal=system_principal(ctx.principal.tenant_id))
    with unit_of_work(system, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
        if close_commands.materialise_checklist(uow, state_id=state_id):
            uow.commit()


def _monitored(ctx: RequestContext, deps: KernelDeps, state_id: uuid.UUID) -> None:
    """Run the data-quality monitors of a period the caller may close, as the SYSTEM principal in
    their own unit of work, before a period command evaluates its gates: the findings and the
    ``close.run_monitors`` audit event stay recorded when the command is then refused. The
    monitors ran on every cockpit GET until security finding SC-8; they now run here, in the close
    run and in the scheduled sweep (05 SCH-10). 404 ``not-found`` outside the caller's scope or
    without ``period.close`` for the period's entity."""
    scope = close_queries.visible_scope(ctx, state_id)
    require_for_entity(ctx, close_rules.CLOSE_PERMISSION, scope.entity_id)
    system = dataclasses.replace(ctx, principal=system_principal(ctx.principal.tenant_id))
    with unit_of_work(system, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
        close_commands.run_period_monitors(uow, state_id=state_id)
        uow.commit()


@router.get(
    "/periods/{period_id}/cockpit",
    operation_id="periods_cockpit",
    response_model=PeriodCockpitOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def periods_cockpit(
    period_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> PeriodCockpitOut:
    """API-S-PeriodCockpit: the period with its blockers, the checklist in template sequence, the
    journal preview, the days-to-close KPI and the derived blockers (REQ-CLS-008, -020)."""
    _materialised(ctx, deps, period_id)
    return PeriodCockpitOut.model_validate(close_queries.cockpit(ctx, period_id))


@router.get(
    "/periods/{period_id}/checklist",
    operation_id="periods_checklist",
    response_model=ListOut[ChecklistItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def periods_checklist(
    period_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> ListOut[ChecklistItemOut]:
    """The checklist of a period: the system gates in sequence, then the tenant's close tasks; one
    page (the checklist is bounded by the tenant's templates)."""
    _materialised(ctx, deps, period_id)
    items = [
        ChecklistItemOut.model_validate(item) for item in close_queries.checklist(ctx, period_id)
    ]
    return ListOut[ChecklistItemOut](items=items, next_cursor=None)


@router.post(
    "/periods/{period_id}/checklist/{item_id}/sign",
    operation_id="periods_checklist_sign",
    response_model=ChecklistItemOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def periods_checklist_sign(
    period_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistSignIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.CLOSE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Sign a manual close task (PASSED with a PREPARER sign-off); an MFA-verified session and
    ``If-Match`` of the period state are required."""

    def handle(uow: UnitOfWork) -> ChecklistItemOut:
        return close_commands.sign_checklist_item(
            uow,
            state_id=period_id,
            item_id=item_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle)


@router.post(
    "/periods/{period_id}/checklist/{item_id}/waive",
    operation_id="periods_checklist_waive",
    response_model=ChecklistWaiverOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def periods_checklist_waive(
    period_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistWaiveIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.CLOSE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request a waiver of a gate or task that has not passed: an ``EXCEPTION_WAIVER`` request for
    an ``exception.waive`` holder other than the requester (BS4-D-07); ``If-Match`` required."""

    def handle(uow: UnitOfWork) -> ChecklistWaiverOut:
        return close_commands.waive_checklist_item(
            uow,
            state_id=period_id,
            item_id=item_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle)


# --- lock, permanent lock and the lock history (CLO-6) -------------------------------------------


@router.post(
    "/periods/{period_id}/request-lock",
    operation_id="periods_request_lock",
    response_model=PeriodLockRequestOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "close-gates-failed", "earlier-period-open"),
)
def periods_request_lock(
    period_id: uuid.UUID,
    body: PeriodLockRequestIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.CLOSE_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a ``closing`` period for lock (04 §16.8; BS4-D-08): every automatic gate must pass,
    the certification comment is required, and the ``PERIOD_LOCK`` approval a Controller decides
    executes the lock; ``If-Match`` required (CLO-6). The data-quality monitors of the period run
    first, so ``DATA_QUALITY_CLEAR`` is evaluated on current findings. Periods lock in order: 409
    ``earlier-period-open`` while an earlier period of the entity and book is open, in soft close
    or reopened."""

    def handle(uow: UnitOfWork) -> PeriodLockRequestOut:
        _monitored(cmd.ctx, deps, period_id)
        return close_commands.request_lock(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle)


@router.post(
    "/periods/{period_id}/request-permanent-lock",
    operation_id="periods_request_permanent_lock",
    response_model=PeriodPermanentLockRequestOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def periods_request_permanent_lock(
    period_id: uuid.UUID,
    body: PeriodPermanentLockRequestIn,
    cmd: Annotated[
        CommandContext, Depends(command(close_rules.LOCK_PERMISSION, precondition="row"))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request the permanent lock of a ``closed`` period once every earlier period is permanently
    locked. The request needs ``period.lock`` for the period's entity (PRD ACT-27, SM-07; 04
    API-R-18 rev 1.156) and a second Controller's approval executes it — the requester cannot
    decide it; ``If-Match`` required (CLO-6)."""

    def handle(uow: UnitOfWork) -> PeriodPermanentLockRequestOut:
        return close_commands.request_permanent_lock(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle)


@router.post(
    "/periods/{period_id}/request-reopen",
    operation_id="periods_request_reopen",
    response_model=PeriodReopenRequestOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "later-period-closed"),
)
def periods_request_reopen(
    period_id: uuid.UUID,
    body: PeriodReopenRequestIn,
    cmd: Annotated[
        CommandContext,
        Depends(command(close_rules.REOPEN_REQUEST_PERMISSION, precondition="row")),
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request the reopening of a ``closed`` period (04 §16.8; SM-07; REQ-CLS-011): a reason of the
    request-reopen subset and a comment; 409 ``later-period-closed`` while a later period of the
    entity and book is closed or permanently locked (BR-CLS-05; ERR-16). Two approvers holding
    ``period.reopen_approve`` other than the requester, at least one a Controller, execute it;
    ``If-Match`` required (CLO-7)."""

    def handle(uow: UnitOfWork) -> PeriodReopenRequestOut:
        return close_commands.request_reopen(
            uow,
            state_id=period_id,
            body=body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle)


@router.get(
    "/periods/{period_id}/locks",
    operation_id="periods_locks_list",
    response_model=ListOut[PeriodLockRowOut],
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def periods_locks_list(
    period_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> ListOut[PeriodLockRowOut]:
    """The T-CLS-04 lock, reopen and permanent-lock records of a period, newest first (CLO-6)."""
    rows = close_queries.locks(ctx, period_id)
    return ListOut[PeriodLockRowOut](
        items=[PeriodLockRowOut.model_validate(row) for row in rows], next_cursor=None
    )
