"""SCH-06 ``period_open_redirty`` — the groups a ``future`` → ``open`` transition re-marks dirty
(05 §SCH SCH-06; RCP-04; RCP-17; 04 T-PLT-46 partial-origin rule; Codex production-20260922-0349,
0403 §1, 0644 §1, 0708 §2, 0720).

Run inside the shared opening core (``commands.open_future_period``), so the manual
``POST /periods/{id}/open`` and the SCH-05 scheduler mark the same groups in the same transaction.
For the opened period P of entity X and book B — X being the POSTING entity: the contracting
entity of the contract or the performing entity of any of its obligations (RCP-04, TZ-04, JET-13;
Codex production-20260922-0403 §1) — the clean groups marked are those with:
(a) a member event whose ``effective_date`` falls in P (RCP-04: nothing was posted while P was
    ``future``), or a schedule line of X in P (a performing-entity portion whose posting deferred);
(b) an unresolved closed origin — a member event, a posted line's period or origin period, or
    a schedule line of X and B in a ``closed`` / ``permanently_locked`` period Q of X that ends
    before P starts and has no ``open`` / ``closing`` / ``reopened`` period between Q and P: P is
    Q's first later postable period (S08-R-08 re-applied, the DB mirror of
    ``upgrade_report.conservative_origins`` + ``unresolved_origins``). A ``future`` period inside
    the gap is not an origin (it waits for its own opening);
(c) conservatively, a retained obligation version that X performs in B — the event-only deferred
    case whose contracting-entity event a caller scoped to X cannot see (Codex 0708 §2; 0720).
    Bounded by the performing entity and the opened book only: no date window, because
    retrospective modifications and closed-origin catch-ups concern obligations whose window may
    have ended. Over-marking costs a recompute (idempotent; RCP-06 posts once), never a posting.
Visibility (Codex production-20260922-0644 §1 SCH06-PERFORMING-ENTITY-1): ``contract`` and
``contract_event`` are RLS-TE on the contracting entity, hidden from a caller scoped to the
performing entity, so the X-visible channels — schedule lines, obligation versions, posted lines —
resolve the group through the contract's CURRENT ``combination_group_member`` row (T-CON-04, RLS-T;
``valid_to_known_at IS NULL``; one per contract, written at contract creation and rolled by
``combination._move``). The event channels keep the contract join: those are the contracting
entity's own rows, right for the callers who see them (SYSTEM, the contracting entity's people).
A posted line's historical ``subledger_posting.combination_group_id`` stays a conservative
candidate beside the current membership (a posting whose members have all moved still wakes the
group it was posted for). No row-level security is bypassed or broadened.
Only ``dirty_since IS NULL`` rows are stamped (existing stamps survive); the groups are locked FOR
UPDATE in ascending id order (D-98 101c) after the period state row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from erev_engine.dates import POSTABLE_STATES
from sqlalchemy import ColumnElement, Label, Select, Table, and_, or_, select, union, update
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    obligation_version,
    period,
    period_state,
    schedule_line,
    subledger_line,
    subledger_posting,
)
from erev_api.uow import UnitOfWork

CLOSED_STATES = frozenset({"closed", "permanently_locked"})  # E-04, as S08 reads them


@dataclass(frozen=True, slots=True)
class PeriodStateRow:
    period_id: UUID
    start_date: date
    end_date: date
    state: str


def deferred_gap(rows: Sequence[PeriodStateRow], *, opened_start: date) -> tuple[UUID, ...]:
    """The closed / permanently locked periods whose first later postable period is the one that
    opens on ``opened_start``: every closed period after the latest postable period that starts
    before ``opened_start`` (or every earlier closed period when there is none). Periods in other
    states inside that span (``future``) are not origins."""
    boundary = max(
        (
            row.end_date
            for row in rows
            if row.state in POSTABLE_STATES and row.start_date < opened_start
        ),
        default=None,
    )
    return tuple(
        row.period_id
        for row in sorted(rows, key=lambda item: item.start_date)
        if row.state in CLOSED_STATES
        and row.end_date < opened_start
        and (boundary is None or row.start_date > boundary)
    )


def period_states_of(session: Session, *, entity_id: UUID, book_code: str) -> list[PeriodStateRow]:
    rows = session.execute(
        select(period.c.id, period.c.start_date, period.c.end_date, period_state.c.state)
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(period_state.c.entity_id == entity_id, period_state.c.book_code == book_code)
    ).all()
    return [
        PeriodStateRow(UUID(str(row.id)), row.start_date, row.end_date, str(row.state))
        for row in rows
    ]


def _current_member_of(table: Table) -> ColumnElement[bool]:
    """Join condition to the CURRENT membership row of ``table``'s contract (T-CON-04, RLS-T)."""
    return and_(
        combination_group_member.c.tenant_id == table.c.tenant_id,
        combination_group_member.c.contract_id == table.c.contract_id,
        combination_group_member.c.valid_to_known_at.is_(None),
    )


def _current_group() -> Label[Any]:
    return combination_group_member.c.combination_group_id.label("group_id")


def candidate_selects(
    *,
    tenant_id: UUID,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    start_date: date,
    end_date: date,
    gap_period_ids: Sequence[UUID],
) -> dict[str, Select[Any]]:
    """The named candidate populations of ``redirty_groups``, each selecting one ``group_id``
    column, for the opened period of ``entity_id`` and ``book_code`` and its deferred gap:
    ``events_in_period`` and ``events_in_gap`` (rule (a) / (b) events, through the contract row);
    ``scheduled_in_period`` and ``scheduled_in_gap`` (schedule lines, through current membership);
    ``performing_groups`` (rule (c)); ``posted_in_gap_current`` and ``posted_in_gap_historical``
    (posted lines in the gap, through current membership and the posting's historical group)."""
    events_of_entity = contract_event.join(
        contract,
        and_(
            contract.c.tenant_id == contract_event.c.tenant_id,
            contract.c.id == contract_event.c.contract_id,
        ),
    )
    # The entity being opened is the POSTING entity (RCP-04, TZ-04): the contracting entity of
    # the contract, or the performing entity of any of its obligations (JET-13; Codex 0403 §1).
    performed_here = (
        select(obligation_version.c.contract_id)
        .where(
            obligation_version.c.tenant_id == contract.c.tenant_id,
            obligation_version.c.contract_id == contract.c.id,
            obligation_version.c.performing_entity_id == entity_id,
        )
        .exists()
    )
    posts_here = or_(contract.c.contracting_entity_id == entity_id, performed_here)
    named: dict[str, Select[Any]] = {}
    named["events_in_period"] = (
        select(contract.c.combination_group_id.label("group_id"))
        .select_from(events_of_entity)
        .where(
            posts_here,
            contract_event.c.effective_date >= start_date,
            contract_event.c.effective_date <= end_date,
        )
    )
    # A performing-entity portion whose posting deferred while the period was future left its
    # schedule lines behind (T-ENG-02 entity_id = performing entity): they wake the group too. The
    # group is the contract's CURRENT membership, never the hidden contract row (Codex 0644 §1).
    scheduled_lines = schedule_line.join(
        combination_group_member, _current_member_of(schedule_line)
    )
    named["scheduled_in_period"] = (
        select(_current_group())
        .select_from(scheduled_lines)
        .where(
            schedule_line.c.entity_id == entity_id,
            schedule_line.c.book_code == book_code,
            schedule_line.c.period_id == period_id,
        )
    )
    # Rule (c): every retained obligation version this entity performs in this book, through the
    # contract's CURRENT membership (never the version's own historical group).
    named["performing_groups"] = (
        select(_current_group())
        .select_from(
            obligation_version.join(
                combination_group_member, _current_member_of(obligation_version)
            )
        )
        .where(
            obligation_version.c.performing_entity_id == entity_id,
            obligation_version.c.book_code == book_code,
        )
    )
    if not gap_period_ids:
        return named
    gap = list(gap_period_ids)
    gap_periods = (
        select(period.c.start_date, period.c.end_date)
        .where(period.c.tenant_id == tenant_id, period.c.id.in_(gap))
        .subquery()
    )
    named["events_in_gap"] = (
        select(contract.c.combination_group_id.label("group_id"))
        .select_from(events_of_entity)
        .where(
            posts_here,
            select(gap_periods.c.start_date)
            .where(
                contract_event.c.effective_date >= gap_periods.c.start_date,
                contract_event.c.effective_date <= gap_periods.c.end_date,
            )
            .exists(),
        )
    )
    # Posted lines of the opened entity and book in the gap (their period or origin period): the
    # contract's CURRENT group, and — conservatively — the group the posting was made for.
    posted_in_gap = and_(
        subledger_line.c.entity_id == entity_id,
        subledger_line.c.book_code == book_code,
        or_(subledger_line.c.period_id.in_(gap), subledger_line.c.origin_period_id.in_(gap)),
    )
    named["posted_in_gap_current"] = (
        select(_current_group())
        .select_from(
            subledger_line.join(combination_group_member, _current_member_of(subledger_line))
        )
        .where(posted_in_gap)
    )
    named["posted_in_gap_historical"] = (
        select(subledger_posting.c.combination_group_id.label("group_id"))
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
        )
        .where(posted_in_gap)
    )
    named["scheduled_in_gap"] = (
        select(_current_group())
        .select_from(scheduled_lines)
        .where(
            schedule_line.c.entity_id == entity_id,
            schedule_line.c.book_code == book_code,
            schedule_line.c.period_id.in_(gap),
        )
    )
    return named


def redirty_groups(
    uow: UnitOfWork,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    start_date: date,
    end_date: date,
    gap_period_ids: Sequence[UUID],
) -> int:
    """Mark dirty every clean combination group of the entity affected by the opening (rules (a),
    (b) and (c) above); returns the number marked."""
    principal = uow.principal
    tenant_id = principal.tenant_id
    candidates = candidate_selects(
        tenant_id=tenant_id,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        start_date=start_date,
        end_date=end_date,
        gap_period_ids=gap_period_ids,
    )
    affected = union(*candidates.values()).subquery()
    locked = uow.session.scalars(
        select(combination_group.c.id)
        .where(
            combination_group.c.tenant_id == tenant_id,
            combination_group.c.id.in_(select(affected.c.group_id)),
            combination_group.c.dirty_since.is_(None),
        )
        .order_by(combination_group.c.id)
        .with_for_update()
    ).all()
    group_ids = [UUID(str(value)) for value in locked]
    if not group_ids:
        return 0
    uow.session.execute(
        update(combination_group)
        .where(combination_group.c.tenant_id == tenant_id, combination_group.c.id.in_(group_ids))
        .values(
            dirty_since=uow.now,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=combination_group.c.row_version + 1,
        )
    )
    return len(group_ids)
