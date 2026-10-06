"""Close reads (04 §16.8 API-R-18, API-S-Period, API-S-PeriodCockpit, T-REF-07, T-CLS-03, T-CLS-08;
BUILD_SPEC CLO-3, CLO-4).

``list_transitions`` pages the ``period_state_transition`` history of one visible period state:
from and to state, reason, comment and actor, newest first by default. ``period_view`` is
API-S-Period with the close blockers, the latest close run, the current lock and the lock whose
datasets stand (``period_locks``; ``lock_records``);
``list_period_views`` is a page of them without the blockers (04 §16.8 rev 1.199: the counts cost
a statement over 23 tables for each row, and no reader takes them from the list); ``cockpit`` is
API-S-PeriodCockpit and ``checklist`` its checklist rows. Queries never write (DG-CMD-13): the
checklist items a cockpit shows are created and evaluated by the commands that evaluate gates, and
are brought up to date for a reader by ``commands.materialise_checklist`` — without audit events
but for the lapse of a waiver its gate has outgrown (04 T-CLS-03 rev 1.305), and only when a row
differs from what the reader must see (security finding SC-8).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

from erev_engine.currencies import ISO_4217
from sqlalchemy import ColumnElement, FromClause, Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import system_entity_scope, tenant_session
from erev_api.db.tables import (
    approval_request,
    close_checklist_item,
    close_checklist_template,
    close_run,
    legal_entity,
    lock_snapshot,
    period,
    period_lock,
    period_state,
    period_state_transition,
    signoff,
    subledger_line,
    tenant_membership,
)
from erev_api.domain.close import gates, lock_records
from erev_api.domain.platform import actors, approval_queries
from erev_api.domain.reference import queries as reference_queries
from erev_api.enums import PrincipalKind, SnapshotKind
from erev_api.money import money_out
from erev_api.problems import Problem
from erev_api.schemas.periods import PeriodTransitionOut

REQUEST_NO: Final = "approval_request_no"


def _request_no(request_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> Any:
    """The number of the approval request a row names, read with the row: one lookup on the
    request's primary key under the reader's own row scope (04 §16.8, rev 1.207; item
    CLO-LOCKS-READ-1). A period's lock and reopen requests name the period's entity (T-PLT-17),
    so whoever reads the period reads the number; the request itself stays behind API-R-09."""
    return (
        select(approval_request.c.request_no)
        .where(approval_request.c.tenant_id == tenant_id, approval_request.c.id == request_id)
        .scalar_subquery()
        .label(REQUEST_NO)
    )


TRANSITION_COLUMNS: Final = (
    period_state_transition.c.id,
    period_state_transition.c.period_state_id,
    period_state_transition.c.from_state,
    period_state_transition.c.to_state,
    period_state_transition.c.reason_code,
    period_state_transition.c.comment,
    period_state_transition.c.approval_request_id,
    _request_no(period_state_transition.c.approval_request_id, period_state_transition.c.tenant_id),
    period_state_transition.c.period_lock_id,
    period_state_transition.c.close_run_id,
    period_state_transition.c.created_at,
    period_state_transition.c.created_by,
    period_state_transition.c.created_by_kind,
)
LOCKED_STATES: Final = frozenset({"closed", "permanently_locked"})
# The ``actors.named`` value and the stored kind a lock row is read with, for ``_lock_out`` alone
# (dev-guide DG-API-11).
_LOCK_CREATED_BY_NAMED: Final = "created_by__named"
_LOCK_CREATOR: Final = (
    period_lock.c.created_by_kind,
    actors.named(period_lock.c.created_by, tenant_id=period_lock.c.tenant_id).label(
        _LOCK_CREATED_BY_NAMED
    ),
)
# the period state a lock row of a page belongs to (``_locks_of``); no API member
_LOCK_OF_STATE: Final = "of_state__id"
_LOCK_READ_ONLY: Final = frozenset({"created_by_kind", _LOCK_CREATED_BY_NAMED, _LOCK_OF_STATE})
# The members of API-S-Period ``current_lock`` and ``dataset_lock`` (04 §16.8), and the prefix
# the second is read under in the statement that reads the first (``period_locks``).
_LOCK_MEMBERS: Final = (
    "id",
    "kind",
    "created_at",
    "created_by",
    "ledger_head_chain_seq",
    "snapshot_manifest_sha256",
)
_DATASET_LOCK: Final = "dataset_lock__"
DAYS_TO_CLOSE_PERIODS: Final = 3  # REQ-CLS-020: the last three periods


def transitions_statement(state_id: UUID) -> Select[Any]:
    """The transitions of one period state (T-REF-07)."""
    return select(*TRANSITION_COLUMNS).where(period_state_transition.c.period_state_id == state_id)


def transition_outs(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> list[PeriodTransitionOut]:
    """API rows of ``transitions_statement`` with the actors' display names."""
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    return [
        PeriodTransitionOut.model_validate(
            {
                **{key: row[key] for key in row if key not in ("created_by", "created_by_kind")},
                "created_by": approval_queries.actor(
                    row["created_by"], str(row["created_by_kind"]), names
                ),
            }
        )
        for row in rows
    ]


def list_transitions[T](
    ctx: RequestContext, state_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the history of a period state; 404 ``not-found`` outside the principal's
    entity scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        visible = session.execute(
            select(period_state.c.id).where(period_state.c.id == state_id)
        ).scalar_one_or_none()
        if visible is None:
            raise Problem("not-found")
        return page(session, transitions_statement(state_id))


# --- API-S-Period with blockers (CLO-4) ----------------------------------------------------------


def _close_run_out(row: Mapping[Any, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": gates._text(row["status"]),
        "current_step_code": row["current_step_code"],
    }


def close_run_ref(session: Session, scope: gates.PeriodScope) -> dict[str, Any] | None:
    """API-S-Period ``close_run``: the newest close run of the entity, book and period."""
    row = (
        session.execute(
            select(close_run.c.id, close_run.c.status, close_run.c.current_step_code)
            .where(
                close_run.c.entity_id == scope.entity_id,
                close_run.c.book_code == scope.book_code,
                close_run.c.period_id == scope.period_id,
            )
            .order_by(close_run.c.created_at.desc(), close_run.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if row is None else _close_run_out(row)


def _close_runs_of(session: Session, state_ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """``close_run_ref`` for a page: the newest close run of each of the period states, in ONE
    statement — the runs of the states' entity, book and period, the newest of each state first
    (``DISTINCT ON``). A state without a run has no entry."""
    of_state = and_(
        close_run.c.tenant_id == period_state.c.tenant_id,
        close_run.c.entity_id == period_state.c.entity_id,
        close_run.c.book_code == period_state.c.book_code,
        close_run.c.period_id == period_state.c.period_id,
    )
    rows = session.execute(
        select(
            period_state.c.id.label("state_id"),
            close_run.c.id,
            close_run.c.status,
            close_run.c.current_step_code,
        )
        .select_from(period_state.join(close_run, of_state))
        .where(period_state.c.id.in_(state_ids))
        .distinct(period_state.c.id)
        .order_by(period_state.c.id, close_run.c.created_at.desc(), close_run.c.id.desc())
    ).mappings()
    return {UUID(str(row["state_id"])): _close_run_out(row) for row in rows}


def _lock_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """The API members of a T-CLS-04 row read with ``_LOCK_CREATOR``: ``created_by`` is
    API-S-Actor, the person whose decision executed the lock, reopen or permanent lock."""
    return {
        **{name: value for name, value in row.items() if name not in _LOCK_READ_ONLY},
        "kind": gates._text(row["kind"]),
        "created_by": actors.actor(
            row["created_by"], row["created_by_kind"], row[_LOCK_CREATED_BY_NAMED]
        ),
    }


def _lock_members(table: FromClause, prefix: str = "") -> tuple[ColumnElement[Any], ...]:
    """The API members of a T-CLS-04 row of ``table`` with who created it, as ``_lock_out`` reads
    them, each labelled with ``prefix``."""
    return (
        *(table.c[name].label(prefix + name) for name in _LOCK_MEMBERS),
        table.c.created_by_kind.label(f"{prefix}created_by_kind"),
        actors.named(table.c.created_by, tenant_id=table.c.tenant_id).label(
            prefix + _LOCK_CREATED_BY_NAMED
        ),
    )


# A period's current lock record and, beside it, the ``LOCK`` record whose datasets stand — the
# record itself, the one a permanent lock names, or none (``lock_records.stands_for``): one
# statement reads both, for one period and for a page.
_PERIOD_LOCKS: Final = (
    *_lock_members(period_lock),
    *_lock_members(lock_records.DATASET_LOCK, _DATASET_LOCK),
)
_WITH_DATASET_LOCK: Final = period_lock.outerjoin(
    lock_records.DATASET_LOCK, lock_records.stands_for(period_lock)
)
type PeriodLocks = tuple[dict[str, Any] | None, dict[str, Any] | None]


def _period_locks(row: Mapping[str, Any]) -> PeriodLocks:
    """``current_lock`` and ``dataset_lock`` of one row of ``_PERIOD_LOCKS``; the second is None
    where the outer join found no record."""
    current = {name: value for name, value in row.items() if not name.startswith(_DATASET_LOCK)}
    standing = {
        name.removeprefix(_DATASET_LOCK): value
        for name, value in row.items()
        if name.startswith(_DATASET_LOCK)
    }
    return _lock_out(current), None if standing["id"] is None else _lock_out(standing)


def period_locks(session: Session, scope: gates.PeriodScope) -> PeriodLocks:
    """API-S-Period ``current_lock`` and ``dataset_lock`` (04 §16.8, rev 1.301; item
    PERMLOCK-DATASETS-1): the T-CLS-04 row ``period_state.current_lock_id`` names, and the
    ``LOCK`` record whose datasets stand for the period — only a ``LOCK`` freezes datasets, so
    for a permanently locked period that is the lock its ``PERMANENT_LOCK`` record follows, and
    under a ``REOPEN`` record it is none (``lock_records``). Who created each is read with it;
    both are ONE statement."""
    if scope.current_lock_id is None:
        return None, None
    row = (
        session.execute(
            select(*_PERIOD_LOCKS)
            .select_from(_WITH_DATASET_LOCK)
            .where(period_lock.c.id == scope.current_lock_id)
        )
        .mappings()
        .first()
    )
    return (None, None) if row is None else _period_locks(dict(row))


def _locks_of(session: Session, state_ids: Sequence[UUID]) -> dict[UUID, PeriodLocks]:
    """``period_locks`` for a page: the current lock record of each of the period states and
    the record whose datasets stand, with who created each, in ONE statement. A state that names
    no lock has no entry."""
    names_lock = and_(
        period_lock.c.tenant_id == period_state.c.tenant_id,
        period_lock.c.id == period_state.c.current_lock_id,
    )
    rows = session.execute(
        select(period_state.c.id.label(_LOCK_OF_STATE), *_PERIOD_LOCKS)
        .select_from(
            period_state.join(period_lock, names_lock).outerjoin(
                lock_records.DATASET_LOCK, lock_records.stands_for(period_lock)
            )
        )
        .where(period_state.c.id.in_(state_ids))
    ).mappings()
    return {UUID(str(row[_LOCK_OF_STATE])): _period_locks(dict(row)) for row in rows}


def with_close(session: Session, shown: Mapping[str, Any]) -> dict[str, Any]:
    """API-S-Period ``shown`` with its blockers, close run, current lock and the lock whose
    datasets stand (04 §16.8). The blocker counts are read under the tenant's SYSTEM entity scope
    (supervisor rulings R-42 (d) and R-121 (i); 04 §16.8 ``blockers``, rev 1.206): a count is a
    fact about the period's lock, the same for every reader of the period — an item the reader
    may not read is counted and not shown. Only the counts: the rows this function returns are
    read in the reader's scope."""
    scope = gates.period_scope(session, UUID(str(shown["id"])))
    if scope is None:
        return dict(shown)
    with system_entity_scope(session):
        blockers = gates.blocker_counts(session, scope)
    current, standing = period_locks(session, scope)
    return {
        **shown,
        "blockers": blockers,
        "close_run": close_run_ref(session, scope),
        "current_lock": current,
        "dataset_lock": standing,
    }


def period_view(session: Session, state_id: UUID) -> dict[str, Any] | None:
    """API-S-Period of a visible period state with its close facts, or None."""
    shown = reference_queries.period_row(session, state_id)
    return None if shown is None else with_close(session, shown)


def get_period_view(ctx: RequestContext, state_id: UUID) -> dict[str, Any]:
    """``GET /periods/{id}``; 404 ``not-found`` outside the principal's scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        found = period_view(session, state_id)
    if found is None:
        raise Problem("not-found")
    return found


def list_period_views[T: reference_queries.Page](
    ctx: RequestContext,
    *,
    entities: Sequence[str],
    book_code: str | None,
    fiscal_year: int | None,
    page: Callable[[Session, Select[Any]], T],
    period_value: str | None = None,
) -> tuple[T, list[dict[str, Any]]]:
    """One page of API-S-Period rows (API-C-11): ``entities`` are codes or ids, ``book``
    defaults to the primary book, and ``period_value`` — a period key or id — keeps the rows of
    that period alone (SCREENS_B §5.5: one period of every entity in scope).

    A row carries its newest close run, its current lock and the lock whose datasets stand,
    read for the WHOLE page in two statements, and no ``blockers`` (04 §16.8 rev 1.199 and rev
    1.301; dev-guide DG-LST-10): the twelve counts
    are one statement over 23 tables for each period, which the single read (``period_view``), the
    cockpit and the commands' answers pay for one period — a page of 200 paid it 200 times, on the
    read every screen makes for its context, for a member no reader takes from the list."""
    ids: list[UUID] = []
    codes: list[str] = []
    for value in entities:
        try:
            ids.append(UUID(value))
        except ValueError:
            codes.append(value)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        statement = reference_queries.period_select().where(
            period_state.c.book_code == (book_code or reference_queries.primary_book_code(session))
        )
        if entities:
            statement = statement.where(
                or_(legal_entity.c.id.in_(ids), legal_entity.c.code.in_(codes))
            )
        if fiscal_year is not None:
            statement = statement.where(period.c.fiscal_year == fiscal_year)
        if period_value is not None:
            try:
                statement = statement.where(period.c.id == UUID(period_value))
            except ValueError:
                statement = statement.where(period.c.period_key == period_value)
        result = page(session, statement)
        state_ids = [UUID(str(row["id"])) for row in result.items]
        runs = _close_runs_of(session, state_ids) if state_ids else {}
        locks = _locks_of(session, state_ids) if state_ids else {}
        items = [
            {
                **reference_queries.period_out(row),
                "blockers": None,
                "close_run": runs.get(state_id),
                "current_lock": locks.get(state_id, (None, None))[0],
                "dataset_lock": locks.get(state_id, (None, None))[1],
            }
            for state_id, row in zip(state_ids, result.items, strict=True)
        ]
        return result, items


def visible_scope(ctx: RequestContext, state_id: UUID) -> gates.PeriodScope:
    """The scope of a period state visible to the principal; 404 ``not-found`` otherwise."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope = gates.period_scope(session, state_id)
    if scope is None:
        raise Problem("not-found")
    return scope


# --- the cockpit (API-S-PeriodCockpit) -----------------------------------------------------------


def checklist_statement(scope: gates.PeriodScope) -> Select[Any]:
    """The period's items of active templates with their templates, sign-offs and owners, in
    template sequence: the system gates, then the tenant's close tasks (SCREENS_B §1.1)."""
    joined = (
        close_checklist_item.join(
            close_checklist_template,
            and_(
                close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            ),
        )
        .outerjoin(
            signoff,
            and_(
                signoff.c.tenant_id == close_checklist_item.c.tenant_id,
                signoff.c.id == close_checklist_item.c.signoff_id,
            ),
        )
        .outerjoin(
            tenant_membership,
            and_(
                tenant_membership.c.tenant_id == close_checklist_item.c.tenant_id,
                tenant_membership.c.id == close_checklist_item.c.owner_membership_id,
            ),
        )
    )
    return (
        select(
            close_checklist_item.c.id,
            close_checklist_template.c.code,
            close_checklist_template.c.name,
            close_checklist_template.c.gate_kind,
            close_checklist_template.c.gate_check_code,
            close_checklist_template.c.is_blocking,
            close_checklist_item.c.status,
            tenant_membership.c.user_id.label("owner_user_id"),
            close_checklist_item.c.due_date,
            close_checklist_item.c.result,
            signoff.c.signer_id,
            signoff.c.signed_at,
            close_checklist_item.c.waiver_approval_request_id,
            close_checklist_item.c.row_version,
        )
        .select_from(joined)
        .where(
            close_checklist_item.c.entity_id == scope.entity_id,
            close_checklist_item.c.book_code == scope.book_code,
            close_checklist_item.c.period_id == scope.period_id,
            close_checklist_template.c.is_active.is_(True),
        )
        .order_by(close_checklist_template.c.sequence, close_checklist_template.c.id)
    )


def checklist_items(session: Session, scope: gates.PeriodScope) -> list[dict[str, Any]]:
    """API-S-PeriodCockpit ``checklist`` rows of a period."""
    rows = list(session.execute(checklist_statement(scope)).mappings())
    names = approval_queries.display_names(
        session, [row["signer_id"] for row in rows] + [row["owner_user_id"] for row in rows]
    )
    user = PrincipalKind.USER.value
    pending = gates.remark_pending(session, scope)
    items: list[dict[str, Any]] = []
    for row in rows:
        stored = row["result"]
        items.append(
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "gate_kind": gates._text(row["gate_kind"]),
                "gate_check_code": row["gate_check_code"],
                "is_blocking": bool(row["is_blocking"]),
                "status": gates._text(row["status"]),
                "owner": None
                if row["owner_user_id"] is None
                else approval_queries.actor(row["owner_user_id"], user, names),
                "due_date": row["due_date"],
                "result": None
                if stored is None
                else {
                    "count": stored.get("count"),
                    "detail": stored.get("detail"),
                    "evaluated_at": stored.get("evaluated_at"),
                },
                "signoff": None
                if row["signer_id"] is None
                else {
                    "signer": approval_queries.actor(row["signer_id"], user, names),
                    "signed_at": row["signed_at"],
                },
                "waiver_approval_request_id": row["waiver_approval_request_id"],
                # R-55 (c): journal balancing, journal completeness and the certification are
                # never waivable, nor the close run (R-114 (b)); R-106 (a): nor NO_DIRTY_GROUPS
                # while the period's re-marking has not succeeded; every other gate and task is.
                "is_waivable": gates.waivable(row["gate_check_code"], remark_pending=pending),
                "row_version": row["row_version"],
            }
        )
    return items


def journal_preview(session: Session, scope: gates.PeriodScope) -> dict[str, Any]:
    """API-S-PeriodCockpit ``journal_preview``: the period's subledger lines summed by account role
    in functional currency; ``balanced`` when debits equal credits (REQ-CLS-008)."""
    amount = subledger_line.c.amount_functional
    debit = func.coalesce(func.sum(case((subledger_line.c.dr_cr == "D", amount), else_=0)), 0)
    credit = func.coalesce(func.sum(case((subledger_line.c.dr_cr == "C", -amount), else_=0)), 0)
    rows = session.execute(
        select(subledger_line.c.account_role, debit.label("debit"), credit.label("credit"))
        .where(
            subledger_line.c.entity_id == scope.entity_id,
            subledger_line.c.book_code == scope.book_code,
            subledger_line.c.period_id == scope.period_id,
        )
        .group_by(subledger_line.c.account_role)
        .order_by(subledger_line.c.account_role)
    ).mappings()
    currency = scope.functional_currency
    by_role: list[dict[str, Any]] = []
    total_debit = Decimal(0)
    total_credit = Decimal(0)
    for row in rows:
        role_debit = Decimal(row["debit"])
        role_credit = Decimal(row["credit"])
        total_debit += role_debit
        total_credit += role_credit
        by_role.append(
            {
                "account_role": gates._text(row["account_role"]),
                "debit": money_out(role_debit, currency, ISO_4217),
                "credit": money_out(role_credit, currency, ISO_4217),
            }
        )
    return {
        "debit_functional": money_out(total_debit, currency, ISO_4217),
        "credit_functional": money_out(total_credit, currency, ISO_4217),
        "difference_functional": money_out(total_debit - total_credit, currency, ISO_4217),
        "balanced": total_debit == total_credit,
        "by_account_role": by_role,
    }


def days_to_close(session: Session, scope: gates.PeriodScope) -> list[dict[str, Any]]:
    """``kpis.days_to_close_last_three``: this period and the two before it, oldest first. For a
    period in state ``closed`` or ``permanently_locked``, days = the date of its current lock's
    ``created_at`` in ``legal_entity.time_zone`` minus ``period.end_date``, in calendar days; any
    other state has no days (SCREENS_B §1.1 "In progress"; REQ-CLS-020; [J] D-88 L7-2-Q-8)."""
    rows = session.execute(
        select(
            period.c.period_key,
            period_state.c.state,
            period.c.end_date,
            legal_entity.c.time_zone,
            period_lock.c.created_at.label("locked_at"),
        )
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
            .outerjoin(
                period_lock,
                and_(
                    period_lock.c.tenant_id == period_state.c.tenant_id,
                    period_lock.c.id == period_state.c.current_lock_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period_state.c.period_end_date <= scope.end_date,
        )
        .order_by(period_state.c.period_end_date.desc())
        .limit(DAYS_TO_CLOSE_PERIODS)
    ).mappings()
    shown = []
    for row in rows:
        locked = row["locked_at"] is not None and str(row["state"]) in LOCKED_STATES
        days = None
        if locked:
            local = row["locked_at"].astimezone(ZoneInfo(str(row["time_zone"])))
            days = (local.date() - row["end_date"]).days
        shown.append({"period_key": row["period_key"], "days": days})
    return list(reversed(shown))


def cockpit(ctx: RequestContext, state_id: UUID) -> dict[str, Any]:
    """``GET /periods/{id}/cockpit`` (API-S-PeriodCockpit); 404 ``not-found`` outside the scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        shown = period_view(session, state_id)
        scope = gates.period_scope(session, state_id)
        if shown is None or scope is None:
            raise Problem("not-found")
        derived = gates.derived_counts(session, scope, known_at=ctx.now)
        return {
            "period": shown,
            "checklist": checklist_items(session, scope),
            "journal_preview": journal_preview(session, scope),
            "kpis": {
                "days_to_close_last_three": days_to_close(session, scope),
                "reconciliations_reviewed": gates.reconciliations_reviewed(
                    session, scope, known_at=ctx.now
                ),
            },
            "derived_blockers": [{"code": code, "count": count} for code, count in derived.items()],
            # D-90a QA-L9-7: the same counts for every reader (SCREENS_B §1.1 rev 1.3).
            "pending_requests": [
                {"subject_type": subject_type, "count": count}
                for subject_type, count in gates.pending_request_counts(session, scope).items()
            ],
        }


def checklist(ctx: RequestContext, state_id: UUID) -> list[dict[str, Any]]:
    """``GET /periods/{id}/checklist``: the checklist rows of a visible period state."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope = gates.period_scope(session, state_id)
        if scope is None:
            raise Problem("not-found")
        return checklist_items(session, scope)


# --- period locks (CLO-6) ------------------------------------------------------------------------


_SNAPSHOT_ORDER: Final = {kind.value: index for index, kind in enumerate(SnapshotKind)}


def _lock_snapshots(session: Session, lock_ids: Sequence[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    """Per lock record the datasets it froze — kind, row count and file hash of each T-CLS-05
    row, in E-64 order — read in one statement for the whole list. The file id and the control
    totals are not read: they stay with the reads of the dataset itself."""
    found: dict[UUID, list[dict[str, Any]]] = {}
    if not lock_ids:
        return found
    rows = session.execute(
        select(
            lock_snapshot.c.period_lock_id,
            lock_snapshot.c.snapshot_kind,
            lock_snapshot.c.row_count,
            lock_snapshot.c.file_sha256,
        ).where(lock_snapshot.c.period_lock_id.in_(lock_ids))
    ).mappings()
    for row in rows:
        found.setdefault(UUID(str(row["period_lock_id"])), []).append(
            {
                "snapshot_kind": gates._text(row["snapshot_kind"]),
                "row_count": int(row["row_count"]),
                "file_sha256": str(row["file_sha256"]),
            }
        )
    for snapshots in found.values():
        snapshots.sort(key=lambda item: _SNAPSHOT_ORDER[item["snapshot_kind"]])
    return found


def _waiver_numbers(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """The numbers of the waiver requests the certifications of ``rows`` name, by request id —
    one statement, and none where no gate was waived."""
    ids = sorted(
        {
            UUID(str(gate["waiver_approval_request_id"]))
            for row in rows
            for gate in row["certification"]
            if gate.get("waiver_approval_request_id") is not None
        }
    )
    if not ids:
        return {}
    found = session.execute(
        select(approval_request.c.id, approval_request.c.request_no).where(
            approval_request.c.id.in_(ids)
        )
    )
    return {str(row.id): str(row.request_no) for row in found}


def _certification(
    stored: Sequence[Mapping[str, Any]], numbers: Mapping[str, str]
) -> list[dict[str, Any]]:
    """T-CLS-04 ``certification`` as stored, each waived gate with its waiver request's
    number."""
    return [
        {
            **gate,
            "waiver_approval_request_no": numbers.get(str(gate.get("waiver_approval_request_id"))),
        }
        for gate in stored
    ]


def list_locks(session: Session, scope: gates.PeriodScope) -> list[dict[str, Any]]:
    """``GET /periods/{id}/locks``: the T-CLS-04 rows of the period, newest first, each with
    what it certified and froze (04 §16.8 API-S-PeriodLock, rev 1.207; item CLO-LOCKS-READ-1):
    its gate results, its ledger head hash, the number of its request and its datasets. The
    statements do not grow with the records: the rows, the datasets of all of them, and the
    waiver requests their certifications name. ``audit_head_hmac`` is not read."""
    rows = [
        dict(row)
        for row in session.execute(
            select(
                period_lock.c.id,
                period_lock.c.kind,
                period_lock.c.created_at,
                period_lock.c.created_by,
                period_lock.c.approval_request_id,
                _request_no(period_lock.c.approval_request_id, period_lock.c.tenant_id),
                period_lock.c.reason_code,
                period_lock.c.comment,
                period_lock.c.certification,
                period_lock.c.ledger_head_chain_seq,
                period_lock.c.ledger_head_sha256,
                period_lock.c.audit_head_chain_seq,
                period_lock.c.snapshot_manifest_sha256,
                period_lock.c.previous_lock_id,
                period_lock.c.diff_report_file_id,
                period_lock.c.cutoff_known_at,
                *_LOCK_CREATOR,
            )
            .where(
                period_lock.c.entity_id == scope.entity_id,
                period_lock.c.book_code == scope.book_code,
                period_lock.c.period_id == scope.period_id,
            )
            .order_by(period_lock.c.created_at.desc(), period_lock.c.id.desc())
        ).mappings()
    ]
    snapshots = _lock_snapshots(session, [UUID(str(row["id"])) for row in rows])
    numbers = _waiver_numbers(session, rows)
    return [
        {
            **_lock_out(row),
            "reason_code": None if row["reason_code"] is None else gates._text(row["reason_code"]),
            "certification": _certification(row["certification"], numbers),
            "snapshots": snapshots.get(UUID(str(row["id"])), []),
        }
        for row in rows
    ]


def locks(ctx: RequestContext, state_id: UUID) -> list[dict[str, Any]]:
    """``GET /periods/{id}/locks``; 404 ``not-found`` outside the reader's scope."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        scope = gates.period_scope(session, state_id)
        if scope is None:
            raise Problem("not-found")
        return list_locks(session, scope)
