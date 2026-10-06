"""The contract groups a changed rate reaches: the mark the approval of an FX rate set version
sets, with the trigger it carries (item FX-REPUBLISH-DIRTY-1; supervisor ruling R-116 (b) and the
rulings of 2026-10-02 on the lane's pre-build line; 04 T-CON-03 ``dirty_trigger`` and T-REF-11
"The groups a changed rate reaches", rev 1.297; 05 RCP-17 rev 1.206).

Measured before the item: the approval of a version that corrects a rate marked no group. Revenue
translated at the earlier average or spot rate stayed in the ledger until some event of the
contract happened to recompute it — in an open period nothing asked for it before the lock, and
behind a lock the difference was posted with the next event and told as that event's.

So the approval says which groups its version can move, in its own transaction — ``marked``, a
hook of ``approvals.subjects.FX_RATE_VERSION_APPROVED`` registered in front of
``close.rate_changes.approved`` (group rows before period-state rows, the order a computation
takes them; dev-guide DG-KRN-DB-08):

1. THE CHANGED KEYS are ``close.rate_changes.changes_statement``: one row per (set, pair, date)
   whose rate in force differs with the version and without it — a value that differs, a rate
   that appears, a rate that disappears. One statement of what a version changes, for the finding
   of a rate changed after a lock and for this mark. A version that repeats the rates in force
   changes nothing and marks nothing.
2. THE REACH of a key, per entity whose functional currency is the key's quote currency
   (``reach_statement``). Stage 12 reads one pair per group and posting entity — base the group's
   transaction currency, quote the entity's functional currency; explicit rows only — in three
   lookups (ENGINE_SPEC_B §12.2.1): the ``average`` of a period at a revenue flow dated in it, the
   ``spot`` rate that is the latest on or before a flow's date, the ``closing`` of a period at its
   end. An ``average`` or ``closing`` key reaches its own period. A ``spot`` key dated d reaches
   from the period that holds d to the period that holds the day before the pair's next spot date
   in force, in any set; without a later one, onward. A key dated after the last day of the
   entity's last postable period is read by nobody (CV-13: the replay ends there; SCH-06 marks
   when its period opens) and has no reach; an entity without a postable period has no such bound
   (CV-13's fallback).
3. THE GROUPS (``candidates_statement``): a group that has been computed, or is dirty, whose
   transaction currency is the key's base currency and for which the reach's entity posts — the
   contracting entity of a member contract or the performing entity of one of its obligations
   (RCP-04) — and which is AT WORK in the reach (``at_work``): begun by its last day (the group's
   inception, or a member event dated on or before it) and not at rest before its first day (a
   member event, a schedule line or a sealed ledger line, by its posting period, dated on or
   after it; or a position of its head version that is not nil).

WHY THE RULE LEAVES OUT NO GROUP A KEY CAN MOVE. A sealed line of a period is made of rates
dated on or before that period's last day — the average and the closing of the period or of an
earlier one, a spot rate on or before a date in it (S12-R-04 keeps a billing's layer date inside
its flow's period) — and a carry is made of its origin's. So a group at rest before the reach
holds no sealed amount the key enters and no position left to remeasure, and what it posts later
comes from a computation or a period-end pass that reads the rates then in force. A group that
has not begun by the end of the reach replays from a later day. The argument lists no kind of
flow: it rests on what a line of a period can be made of. ``tests/properties`` holds it against
the engine: whenever the recompute after a publication posts a line, ``at_work`` had said so.

WHY NOT EVERY GROUP. Over-marking costs one recompute that posts nothing and one contract
version (RCP-06 posts once), so the rule may err on that side and does: a group at work in the
reach that reads another rate type there is marked too. It does not mark a contract finished and
settled before the reach, nor a group of another pair. The inverse pair is a key of its own: a
submission derives the inverse of every rate entered (04 T-REF-12 ``is_derived``), the version
changes both rows, and the inverse reaches the entities whose functional currency is ITS quote —
a group in the quote currency of an entity whose functional currency is the base is marked by
the same approval, since stage 12 reads that row for it.

THE LIMIT: WHAT IS COMMITTED. The statements read what is committed when they run, and a
computation in flight across the approval does not read the version. Where its group is one the
version reaches, ``marked`` waits for the group's row and marks it afterwards; and a transaction
that began before the approval and computes after it finds the stamp later than its cutoff and
is not stored (04 §14.1 "A computation behind its group"). A group the version does NOT reach as
its facts stand committed — at rest in the reach until the very event that computation brings,
or not committed at all yet — is not marked, and what becomes of its computation turns on where
the approval's commit falls (04 T-REF-11, *Limits* (i): three orders, each measured). Where the
computation posts and commits before the approval commits, or the version is published after
its cutoff, it is stored on the earlier rate and its amounts stay there until the group's next
computation: the limit. Where the approval commits before the computation posts and the cutoff
admits the version, the computation is not stored at all: ``computation._rate_stamp`` no longer
finds the rates its bundle pinned in force and refuses (REQ-FX-006), the computation is stored
``FAILED`` and the group stays owed — measured the same without this module's hook, which only
lengthens the approval's transaction by the wait for the rows it marks. Closing the limit needs
a lock the approval and a computation share, or a net at the period's lock (04 T-REF-11 names
both); neither is built here.

THE MARK (``marked``): ``dirty_since`` is the later of the stamp that stands and the approval's
instant — a mark is never moved back (05 RCP-17 rev 1.207), so a computation whose bundle was
read before the approval is behind its group and is not stored — and ``dirty_trigger =
FX_REPUBLISH``. The computation that consumes the mark without first-including an event is
stored under that trigger (``contracts.bundles``), which is the proof the out-of-period register
asks for a difference posted behind a lock (ENGINE_SPEC_B S15-R-18b). The marked groups wait, as
every dirty group does, for the next command on them or the next close run's ``RECOMPUTE_DIRTY``
(RCP-19); ``NO_DIRTY_GROUPS`` holds the lock of the contracting entity meanwhile. That gate
counts a dirty group by its contracting entity: a group the rate reaches through a performing
entity alone holds the contracting entity's lock only, as for every mark.

The hook runs under the tenant's SYSTEM entity scope, as every approval hook does (supervisor
ruling R-64 (1)): what it marks does not depend on the entities its approver reads.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.dates import POSTABLE_STATES
from sqlalchemy import (
    Select,
    Text,
    Uuid,
    and_,
    any_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY

from erev_api.db.tables import (
    combination_group,
    contract,
    contract_event,
    contract_version,
    contract_version_balance,
    legal_entity,
    obligation_version,
    period,
    period_state,
    schedule_line,
    subledger_line,
)
from erev_api.domain.close import rate_changes
from erev_api.domain.contracts import bundles
from erev_api.enums import ComputationTrigger, RateType
from erev_api.logging import get_logger

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "POSITIONS",
    "TRIGGER",
    "at_work",
    "candidates_statement",
    "marked",
    "reach_of",
    "reach_statement",
    "rows_statement",
]

log = get_logger(__name__)

TRIGGER: Final = ComputationTrigger.FX_REPUBLISH  # E-87: the trigger the mark carries
SPOT: Final = RateType.SPOT.value
# T-CON-09: the transaction-currency positions a later rate still enters — the layers stage 12
# keeps open, remeasures or settles (ENGINE_SPEC_B §12.2.2, §12.2.3).
POSITIONS: Final = (
    "contract_liability_txn",
    "contract_asset_txn",
    "unbilled_receivable_txn",
    "accounts_receivable_txn",
    "refund_liability_txn",
    "return_asset_txn",
    "deposit_liability_txn",
    "customer_incentive_asset_txn",
    "consideration_payable_txn",
)


# --- the rule, pure (the statements below say the same in SQL) -----------------------------------


def reach_of(
    rate_type: str,
    on: date,
    *,
    periods: Collection[tuple[date, date]],
    horizon: date | None,
    next_spot: date | None,
) -> tuple[date, date | None] | None:
    """The reach of a changed key dated ``on`` in one entity's calendar: (first day, last day),
    the last day None where it has no end; None where the key has no reach there (module
    docstring, 2). ``periods`` are the calendar's (start, end) pairs; ``horizon`` is the last day
    of the entity's last postable period, None without one; ``next_spot`` is the pair's next spot
    date in force after ``on``."""
    if horizon is not None and on > horizon:
        return None
    holding = [(start, end) for start, end in periods if start <= on <= end]
    if len(holding) != 1:
        return None
    start, end = holding[0]
    if rate_type != SPOT:
        return (start, end) if end == on else None
    if next_spot is None:
        return (start, None)
    until = date.fromordinal(next_spot.toordinal() - 1)
    last = [
        period_end for period_start, period_end in periods if period_start <= until <= period_end
    ]
    return (start, last[0] if len(last) == 1 else None)


def at_work(
    first: date,
    last: date | None,
    *,
    inception: date,
    events: Collection[date],
    scheduled: Collection[date],
    sealed: Collection[date],
    position: bool,
) -> bool:
    """Whether a group is at work in the reach (``first``, ``last``): begun by its last day and
    not at rest before its first (module docstring, 3). ``events`` are the effective dates of its
    members' events; ``scheduled`` and ``sealed`` the period end dates of their schedule lines and
    of their sealed ledger lines (the posting period); ``position`` whether the head version
    holds a position that is not nil."""
    begun = last is None or inception <= last or any(day <= last for day in events)
    if not begun:
        return False
    return (
        position
        or any(day >= first for day in events)
        or any(day >= first for day in scheduled)
        or any(day >= first for day in sealed)
    )


# --- the statements ------------------------------------------------------------------------------


def reach_statement(version_id: UUID) -> Select[Any]:
    """One row per changed key and entity it reaches: the entity, the key's base currency and
    the reach's first and last day in that entity's calendar (``reach_to`` NULL: no end)."""
    changed = rate_changes.changes_statement(version_id).subquery("changed")
    in_force = bundles.fx_rates_in_force(None).subquery("in_force")
    is_spot = cast(changed.c.rate_type, Text) == SPOT
    next_spot = (
        select(func.min(in_force.c.effective_date))
        .where(
            cast(in_force.c.rate_type, Text) == SPOT,
            in_force.c.base_currency == changed.c.base_currency,
            in_force.c.quote_currency == changed.c.quote_currency,
            in_force.c.effective_date > changed.c.effective_date,
        )
        .correlate(changed)
        .scalar_subquery()
    )
    horizon = (
        select(func.max(period_state.c.period_end_date))
        .where(
            period_state.c.tenant_id == legal_entity.c.tenant_id,
            period_state.c.entity_id == legal_entity.c.id,
            period_state.c.state.in_(sorted(POSTABLE_STATES)),
        )
        .correlate(legal_entity)
        .scalar_subquery()
    )
    first = period.alias("reach_first")
    last = period.alias("reach_last")
    until = next_spot - 1  # the day before the pair's next spot date in force
    joined = (
        changed.join(legal_entity, legal_entity.c.functional_currency == changed.c.quote_currency)
        .join(
            first,
            and_(
                first.c.tenant_id == legal_entity.c.tenant_id,
                first.c.calendar_id == legal_entity.c.calendar_id,
                first.c.start_date <= changed.c.effective_date,
                first.c.end_date >= changed.c.effective_date,
            ),
        )
        .outerjoin(
            last,
            and_(
                is_spot,
                last.c.tenant_id == legal_entity.c.tenant_id,
                last.c.calendar_id == legal_entity.c.calendar_id,
                last.c.start_date <= until,
                last.c.end_date >= until,
            ),
        )
    )
    return (
        select(
            legal_entity.c.id.label("entity_id"),
            changed.c.base_currency,
            first.c.start_date.label("reach_from"),
            case((is_spot, last.c.end_date), else_=first.c.end_date).label("reach_to"),
        )
        .select_from(joined)
        .where(
            or_(is_spot, first.c.end_date == changed.c.effective_date),
            or_(horizon.is_(None), changed.c.effective_date <= horizon),
        )
        .distinct()
    )


def candidates_statement(version_id: UUID) -> Select[Any]:
    """The groups the version's changed keys reach (module docstring, 3): one ``group_id`` each."""
    reach = reach_statement(version_id).cte("reach")
    group = combination_group
    members = (
        select(contract.c.id)
        .where(
            contract.c.tenant_id == group.c.tenant_id, contract.c.combination_group_id == group.c.id
        )
        .correlate(group)
    )
    # Correlated by name: nested in ``posts_for``, whose own FROM does not list ``reach``, an
    # automatic correlation would join the whole of ``reach`` here — the entity of any reach row.
    performs = (
        exists()
        .where(
            obligation_version.c.tenant_id == contract.c.tenant_id,
            obligation_version.c.contract_id == contract.c.id,
            obligation_version.c.performing_entity_id == reach.c.entity_id,
        )
        .correlate(contract, reach)
    )
    posts_for = exists().where(
        contract.c.tenant_id == group.c.tenant_id,
        contract.c.combination_group_id == group.c.id,
        or_(contract.c.contracting_entity_id == reach.c.entity_id, performs),
    )
    event_by = exists().where(
        contract_event.c.tenant_id == group.c.tenant_id,
        contract_event.c.contract_id.in_(members),
        contract_event.c.effective_date <= reach.c.reach_to,
    )
    event_from = exists().where(
        contract_event.c.tenant_id == group.c.tenant_id,
        contract_event.c.contract_id.in_(members),
        contract_event.c.effective_date >= reach.c.reach_from,
    )
    scheduled_from = exists().where(
        schedule_line.c.tenant_id == group.c.tenant_id,
        schedule_line.c.contract_id.in_(members),
        schedule_line.c.period_end_date >= reach.c.reach_from,
    )
    sealed_from = exists().where(
        subledger_line.c.tenant_id == group.c.tenant_id,
        subledger_line.c.contract_id.in_(members),
        subledger_line.c.period_end_date >= reach.c.reach_from,
    )
    position = exists().where(
        contract_version.c.tenant_id == group.c.tenant_id,
        contract_version.c.contract_computation_id == group.c.head_computation_id,
        contract_version_balance.c.tenant_id == contract_version.c.tenant_id,
        contract_version_balance.c.contract_version_id == contract_version.c.id,
        or_(*(contract_version_balance.c[name] != 0 for name in POSITIONS)),
    )
    begun = or_(reach.c.reach_to.is_(None), group.c.inception_date <= reach.c.reach_to, event_by)
    return (
        select(group.c.id.label("group_id"))
        .select_from(group.join(reach, group.c.transaction_currency == reach.c.base_currency))
        .where(
            or_(group.c.head_computation_id.is_not(None), group.c.dirty_since.is_not(None)),
            posts_for,
            begun,
            or_(position, event_from, scheduled_from, sealed_from),
        )
        .distinct()
    )


def rows_statement(tenant_id: UUID, version_id: UUID) -> Select[Any]:
    """The group rows ``marked`` takes: the tenant's candidates ``FOR UPDATE`` in ascending id
    order, one statement (dev-guide DG-KRN-DB-08 (1): the order of every path that locks group
    rows; D-98 101c). No ``NOWAIT`` and no ``SKIP LOCKED``: a computation that holds a row is
    waited for, and its group is marked once it has ended."""
    candidates = candidates_statement(version_id).subquery("candidates")
    return (
        select(combination_group.c.id)
        .where(
            combination_group.c.tenant_id == tenant_id,
            combination_group.c.id.in_(select(candidates.c.group_id)),
        )
        .order_by(combination_group.c.id)
        .with_for_update()
    )


def marked(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> int:
    """The hook of a rate set version's approval, after the version is APPROVED and in the
    decision's transaction (module docstring): the groups its changed keys reach are stamped
    ``dirty_since`` — the later of the stamp that stands and the approval's instant — with
    ``dirty_trigger = FX_REPUBLISH``; returns their number. The rows are taken as
    ``rows_statement`` takes them, as ``reference.period_redirty`` does.

    The update names the rows it locked as ONE bound value, an array (``= ANY``), whatever
    their number: a list bound one value a group ends at the 65,535 bound values a PostgreSQL
    statement can carry, and a version may reach more groups than that
    (``journals.summarise.among`` states the bound, measured there)."""
    session = uow.session
    principal = uow.principal
    tenant_id = principal.tenant_id
    locked = session.scalars(rows_statement(tenant_id, version_id)).all()
    group_ids = [UUID(str(value)) for value in locked]
    if group_ids:
        session.execute(
            update(combination_group)
            .where(
                combination_group.c.tenant_id == tenant_id,
                combination_group.c.id == any_(literal(group_ids, ARRAY(Uuid()))),
            )
            .values(
                dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
                dirty_trigger=TRIGGER.value,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
                row_version=combination_group.c.row_version + 1,
            )
        )
    log.info(
        "fx_rate_version.groups_marked",
        fx_rate_set_version_id=str(version_id),
        approval_request_id=str(approval_request_id),
        group_count=len(group_ids),
    )
    return len(group_ids)
