"""A rate changed after a lock: the finding ``FX_RATE_CHANGED_AFTER_LOCK`` (item
CLO-RATE-AFTER-RUN-1, second part; the supervisor's ruling of 2026-10-02 08:56, point 4; 04 §15.4,
T-REF-11 "A rate changed after a lock" and T-IMP-05, rev 1.291; PRD BR-DAT-04).

A close run that read a rate before it was corrected is asked for again by its gate
(``close.run_inputs``) — while the period can still be run. A period that is ``closed`` or
``permanently_locked`` takes no run: the next postable period's run posts the difference, as an
amount of that period. Measured before the item: after a closing rate of a locked August was
corrected, nothing was raised, and September's run posted August's 100.00 with its own 50.00.
Rev 1.297 of 04 (item FX-REPUBLISH-DIRTY-1; PRD IMP-144 rev 1.200): that is the period-end
remeasurement of a balance still open. The amounts of events at a changed rate are posted by
the recompute of the groups the approval marks (``close.rate_reach``), with the closed period
of each event as origin period; and where a later period is closed too, a corrected closing
rate may leave nothing to post. The message's last part says the three.

So the approval of a rate set version says what it changes, in its own transaction — ``approved``,
the hook the reference commands register on the approval (``approvals.subjects``):

1. ``span_statement``: the dates of the rates the version changes — the rows in force with the
   version against the rows in force as if it did not exist, both through
   ``contracts.bundles.fx_rates_in_force``, THE admission of a rate, read whenever a version was
   published. A rate whose value differs, a rate that appears and a rate that disappears (a
   higher version whose coverage holds a date answers for every pair of that date) are changes;
   a version that repeats the values in force changes nothing, and nothing more is read. An
   item names and counts the rates a person entered: the inverses a submission derives from
   them change with them and are not listed beside them.
2. ``states_statement``: every period state that is not ``future`` and whose period ends on or
   after the first changed date, ``FOR SHARE``. A lock decision holds its state row ``FOR
   UPDATE`` before it evaluates its gates (``close.commands``), so a decision in flight either
   ends first — this read waits for it and then reads the period ``closed`` — or evaluates after
   this approval's commit, when its close-run gate reads the version (``run_inputs.standing``
   takes no time bound for that reason). Without the row lock a decision that had evaluated its
   gates could close the period on the old rate while this hook read it ``closing``: neither the
   gate nor a finding. A reopen decision is serialised the same way: it ends first and the period
   is no longer closed, or it waits and settles the items this hook raised. ``future`` rows are
   left alone: a lock decision takes the next period's ``future`` row ``NOWAIT``. A wait beyond
   the platform's ``lock_timeout`` ends the approval's decision 409 ``lock-conflict``, nothing
   saved: it is sent again when the decision it waited for has ended.
3. For each state that is ``closed`` or ``permanently_locked`` and whose period holds a changed
   date: ONE exception item — source ``CLOSE``, ``WARNING``, its entity, and as its period the
   period the difference posts to (``periods.posting_period`` of the closed period's last day;
   none while no later period is postable, and an item without a period is every period's of its
   entity). A ``WARNING`` item of this source counts in ``EXCEPTIONS_CLEARED`` and in
   ``blockers.exceptions_open`` of its period (``close.gates``), so the cockpit of the period the
   amount lands in shows it and that period's lock waits for one of the two roads. The key
   carries the period state and the version: a second correction is a second item, never an
   occurrence of one that was accepted. The Revenue Accountants and the Controllers whose roles
   cover the entity are told (NTF-11).

The two roads. REOPEN: the reopen decision of that entity, book and period settles its open items
— ``settle_reopened``, RESOLVED by the system — since the period is no longer closed and its next
lock needs a close run that read the rates in force. ACCEPT: the waiver of PRD SM-06, nothing of
this module. No person resolves or dismisses the item (``imports.exceptions``: its input is
committed, and only the system finds its condition gone).

Tenant-wide, as the gate's read is and for its reason: which rates a period's passes read is not
derived from a list of pairs or groups. The price: an entity the rate cannot touch gets its item,
and its acceptance is one waiver. The item names rates, never an amount — nothing computes the
difference at the approval; what is posted, where and with which origin period is the last
part of the message (PRD IMP-144 rev 1.200).

The hook runs under the tenant's SYSTEM entity scope, as every approval hook does (supervisor
ruling R-64 (1)): what it raises does not depend on the entities its approver reads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, select

from erev_api import periods
from erev_api.approvals import subjects
from erev_api.db.tables import (
    exception_item,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    legal_entity,
    period,
    period_state,
)
from erev_api.domain.contracts import bundles
from erev_api.domain.imports import exceptions
from erev_api.enums import (
    BookCode,
    ExceptionSeverity,
    ExceptionSource,
    NotificationKind,
    PeriodState,
)
from erev_api.events.notifications import notify, role_holders
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.domain.close.gates import PeriodScope
    from erev_api.uow import UnitOfWork

__all__ = [
    "CODE",
    "RateChange",
    "approved",
    "changes_statement",
    "message",
    "roads",
    "settle_reopened",
    "span_statement",
    "states_statement",
]

CODE: Final = "FX_RATE_CHANGED_AFTER_LOCK"  # 04 §15.4
LOCKED: Final = frozenset({PeriodState.CLOSED.value, PeriodState.PERMANENTLY_LOCKED.value})
EXCEPTION_OBJECT: Final = "exception_item"
TOLD: Final = ("controller", "revenue_accountant")  # T-PLT-09 role codes (PRD NTF-11)
# The rates an item's payload lists; the message names the first and counts the rest.
PAYLOAD_RATES: Final = 50
NO_LATER_PERIOD: Final = "period-closed"  # ``periods.posting_period``: no later period is postable
# The item's message, in its parts (PRD IMP-144).
MESSAGE: Final = (
    "{period} is {state} for {entity} in book {book}. The approval of version {version_no} of "
    "rate set {set_code} changed {count} exchange {rates} dated in it: {first}{more}. {roads} "
    "The difference is not computed here. What remains of it to post goes to {posting}. The "
    "contracts the changed rates reach are recalculated by the next close run of their "
    "contracting entity or by the next change to them: what the rates change in the amounts of "
    "their events is posted with the closed period of each event as origin period, and the "
    "out-of-period register lists it as Fx republish or with the event that carried it. The close "
    "run of {posting} posts what remains of a period-end remeasurement as an amount of that "
    "period, without an origin period. Where nothing remains nothing is posted: a closing rate of "
    "a period that is followed by another closed period moves an amount between the two for a "
    "balance open through both."
)
STATES: Final[Mapping[str, str]] = {
    PeriodState.CLOSED.value: "closed",
    PeriodState.PERMANENTLY_LOCKED.value: "permanently locked",
}
CHANGED: Final = "{base}/{quote} {rate_type} rate of {on} from {before} to {after}"
APPEARED: Final = "{base}/{quote} {rate_type} rate of {on}, {after} where there was none"
REMOVED: Final = "{base}/{quote} {rate_type} rate of {on}, none where it was {before}"
MORE: Final = ", and {n} more"
# The roads the states leave when the item is raised (PRD BR-CLS-05: a period is not reopened
# while a later period of the entity and book is closed or permanently locked).
REOPEN_OR_ACCEPT: Final = (
    "Reopen the period to restate it, or request a waiver to accept the difference."
)
LATER_FIRST_OR_ACCEPT: Final = (
    "To restate it, reopen the later closed periods first and then this one; or request a "
    "waiver to accept the difference."
)
ACCEPT_ONLY: Final = "The period cannot be reopened. Request a waiver to accept the difference."
NEXT_TO_OPEN: Final = "the next period to open"
REOPENED: Final = (
    "{period} was reopened for {entity} in book {book}. Its next lock needs a close run that "
    "read the rates in force."
)


@dataclass(frozen=True, slots=True)
class RateChange:
    """One rate a version changes: its value in force without the version and with it. None
    before: the rate appears with the version; None after: it disappears with it."""

    set_code: str
    rate_type: str
    base_currency: str
    quote_currency: str
    effective_date: date
    before: Decimal | None
    after: Decimal | None
    # An inverse or a triangulated rate the submission derived from the rates entered (T-REF-12).
    is_derived: bool = False


def _of_the_versions_set(version_id: UUID) -> ColumnElement[bool]:
    approved_version = fx_rate_set_version.alias("approved_version")
    return (
        fx_rate_set.c.id
        == select(approved_version.c.fx_rate_set_id)
        .where(approved_version.c.id == version_id)
        .scalar_subquery()
    )


def changes_statement(version_id: UUID) -> Select[Any]:
    """One row per rate the version changes (module docstring, 1): the rates in force of its set
    with the version, full-joined on set, pair and date to the rates in force without it, where
    the two values are distinct. Both sides are ``bundles.fx_rates_in_force`` with no time bound,
    so inside the approval's transaction the side without the version is what was in force
    before it."""
    of_set = _of_the_versions_set(version_id)
    after = (
        bundles.fx_rates_in_force(None)
        .add_columns(fx_rate.c.is_derived)
        .where(of_set)
        .subquery("rates_after")
    )
    before = (
        bundles.fx_rates_in_force(None, without=version_id)
        .add_columns(fx_rate.c.is_derived)
        .where(of_set)
        .subquery("rates_before")
    )
    same_rate = and_(
        before.c.code == after.c.code,
        before.c.base_currency == after.c.base_currency,
        before.c.quote_currency == after.c.quote_currency,
        before.c.effective_date == after.c.effective_date,
    )
    return (
        select(
            func.coalesce(after.c.code, before.c.code).label("set_code"),
            func.coalesce(after.c.rate_type, before.c.rate_type).label("rate_type"),
            func.coalesce(after.c.base_currency, before.c.base_currency).label("base_currency"),
            func.coalesce(after.c.quote_currency, before.c.quote_currency).label("quote_currency"),
            func.coalesce(after.c.effective_date, before.c.effective_date).label("effective_date"),
            before.c.rate.label("rate_before"),
            after.c.rate.label("rate_after"),
            func.coalesce(after.c.is_derived, before.c.is_derived).label("is_derived"),
        )
        .select_from(after.join(before, same_rate, full=True))
        .where(before.c.rate.is_distinct_from(after.c.rate))
    )


def span_statement(version_id: UUID) -> Select[Any]:
    """The first and the last date of the rates the version changes, and their number: one row."""
    changed = changes_statement(version_id).subquery("changed")
    return select(
        func.min(changed.c.effective_date), func.max(changed.c.effective_date), func.count()
    )


def states_statement(first: date) -> Select[Any]:
    """Every period state that is not ``future`` and whose period ends on or after ``first``, with
    its entity and period, each state row held ``FOR SHARE`` to the end of the transaction (module
    docstring, 2): one statement, in the order of period start, then state id — the order the
    rows of a window are taken in (dev-guide DG-KRN-DB-08 (1c)). A row a decision holds is waited
    for, and is then read as that decision left it."""
    return (
        select(
            period_state.c.id,
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.state,
            legal_entity.c.code.label("entity_code"),
            period.c.period_key,
            period.c.start_date,
            period.c.end_date,
        )
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            ).join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
        )
        .where(
            period_state.c.period_end_date >= first,
            period_state.c.state != PeriodState.FUTURE.value,
        )
        .order_by(period.c.start_date, period_state.c.id)
        .with_for_update(read=True, of=period_state)
    )


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _rate(value: Decimal) -> str:
    return format(Decimal(value).normalize(), "f")


def _named(change: RateChange) -> str:
    members = {
        "base": change.base_currency,
        "quote": change.quote_currency,
        "rate_type": change.rate_type,
        "on": change.effective_date.isoformat(),
    }
    if change.before is None and change.after is not None:
        return APPEARED.format(**members, after=_rate(change.after))
    if change.after is None and change.before is not None:
        return REMOVED.format(**members, before=_rate(change.before))
    if change.before is None or change.after is None:
        raise ValueError("a rate that is in force neither with nor without the version")
    return CHANGED.format(**members, before=_rate(change.before), after=_rate(change.after))


def roads(state: str, later: Sequence[str]) -> str:
    """The roads sentence for a period in ``state`` whose later periods of the same entity and
    book that are closed or permanently locked are in ``later`` (their states)."""
    permanent = PeriodState.PERMANENTLY_LOCKED.value
    if state == permanent or permanent in later:
        return ACCEPT_ONLY
    return LATER_FIRST_OR_ACCEPT if later else REOPEN_OR_ACCEPT


def message(
    *,
    period_key: str,
    state: str,
    later: Sequence[str],
    entity_code: str,
    book_code: str,
    version_no: int,
    changes: Sequence[RateChange],
    posting_period_key: str | None,
) -> str:
    """The item's message (PRD IMP-144): the closed period, the version, the first changed rate
    with both values and the number of the others, the roads the states leave, and where what
    remains of the difference is posted — it is not computed at the approval; the recompute of
    the marked groups posts event amounts with their origin period, the next run what remains
    of a period-end remeasurement without one (rev 1.200)."""
    if not changes:
        raise ValueError("an item without a changed rate")
    count = len(changes)
    return MESSAGE.format(
        period=period_key,
        state=STATES[state],
        entity=entity_code,
        book=book_code,
        version_no=version_no,
        set_code=changes[0].set_code,
        count=count,
        rates="rate" if count == 1 else "rates",
        first=_named(changes[0]),
        more="" if count == 1 else MORE.format(n=count - 1),
        roads=roads(state, later),
        posting=posting_period_key or NEXT_TO_OPEN,
    )


def _changes(uow: UnitOfWork, version_id: UUID, first: date, last: date) -> list[RateChange]:
    changed = changes_statement(version_id).subquery("changed")
    rows = uow.session.execute(
        select(changed)
        .where(changed.c.effective_date >= first, changed.c.effective_date <= last)
        .order_by(
            changed.c.effective_date,
            changed.c.base_currency,
            changed.c.quote_currency,
        )
    ).all()
    return [
        RateChange(
            set_code=str(row.set_code),
            rate_type=_text(row.rate_type),
            base_currency=str(row.base_currency).strip(),
            quote_currency=str(row.quote_currency).strip(),
            effective_date=row.effective_date,
            before=None if row.rate_before is None else Decimal(row.rate_before),
            after=None if row.rate_after is None else Decimal(row.rate_after),
            is_derived=bool(row.is_derived),
        )
        for row in rows
    ]


def _posting_period(uow: UnitOfWork, state: Any) -> periods.PeriodRef | None:
    """The period an amount of the closed period posts to now (DG-KRN-TIME-04), or None while no
    later period of the entity and book is postable."""
    try:
        posting, _origin = periods.posting_period(
            uow.session,
            entity_id=UUID(str(state.entity_id)),
            book_code=BookCode(_text(state.book_code)),
            effective_date=state.end_date,
        )
    except Problem as refused:
        if refused.slug != NO_LATER_PERIOD:
            raise
        return None
    return posting


def approved(uow: UnitOfWork, version_id: UUID, approval_request_id: UUID) -> tuple[UUID, ...]:
    """The hook of a rate set version's approval, after the version is APPROVED and in the
    decision's transaction (module docstring): the items raised, in the order of period start,
    then period state."""
    session = uow.session
    first, last, count = session.execute(span_statement(version_id)).one()
    if not count:
        return ()
    states = session.execute(states_statement(first)).all()
    touched = [
        state
        for state in states
        if _text(state.state) in LOCKED and state.start_date <= last and state.end_date >= first
    ]
    if not touched:
        return ()
    changes = _changes(
        uow,
        version_id,
        min(state.start_date for state in touched),
        max(state.end_date for state in touched),
    )
    version_no = int(
        session.execute(
            select(fx_rate_set_version.c.version_no).where(fx_rate_set_version.c.id == version_id)
        ).scalar_one()
    )
    raised: list[UUID] = []
    told: dict[UUID, list[UUID]] = {}
    for state in touched:
        every = [
            change
            for change in changes
            if state.start_date <= change.effective_date <= state.end_date
        ]
        if not every:
            continue
        # the rates a person entered; the inverses derived from them follow and are not named
        dated = [change for change in every if not change.is_derived] or every
        entity_id = UUID(str(state.entity_id))
        book_code = _text(state.book_code)
        posting = _posting_period(uow, state)
        text = message(
            period_key=str(state.period_key),
            state=_text(state.state),
            later=[
                _text(other.state)
                for other in states
                if other.entity_id == state.entity_id
                and other.book_code == state.book_code
                and other.start_date > state.end_date
                and _text(other.state) in LOCKED
            ],
            entity_code=str(state.entity_code),
            book_code=book_code,
            version_no=version_no,
            changes=dated,
            posting_period_key=None if posting is None else posting.period_key,
        )
        item = exceptions.raise_exception_item(
            uow,
            source=ExceptionSource.CLOSE,
            code=CODE,
            severity=ExceptionSeverity.WARNING,
            message=text,
            dedupe=exceptions.dedupe_key(ExceptionSource.CLOSE, CODE, f"{state.id}:{version_id}"),
            business_key=f"{dated[0].set_code} v{version_no}",
            entity_id=entity_id,
            period_id=None if posting is None else posting.id,
            source_payload={
                "fx_rate_set_version_id": str(version_id),
                "fx_rate_set_code": dated[0].set_code,
                "version_no": version_no,
                "approval_request_id": str(approval_request_id),
                "period_state_id": str(state.id),
                "period_key": str(state.period_key),
                "book_code": book_code,
                "state": _text(state.state),
                "posting_period_key": None if posting is None else posting.period_key,
                "rates_changed": len(dated),
                "rates": [
                    {
                        "rate_type": change.rate_type,
                        "base_currency": change.base_currency,
                        "quote_currency": change.quote_currency,
                        "effective_date": change.effective_date.isoformat(),
                        "before": None if change.before is None else _rate(change.before),
                        "after": None if change.after is None else _rate(change.after),
                    }
                    for change in dated[:PAYLOAD_RATES]
                ],
            },
        )
        raised.append(item.id)
        if not item.created:
            continue
        if entity_id not in told:
            told[entity_id] = role_holders(
                session, role_codes=TOLD, entity_id=entity_id, at=uow.now
            )
        notify(
            uow,
            recipient_membership_ids=told[entity_id],
            kind=NotificationKind.EXCEPTION_ASSIGNED,
            title=f"Exception: {CODE}",  # PRD NTF-11
            body=text,
            link_path=subjects.EXCEPTION_LINK.format(item_id=item.id),
            subject_type=EXCEPTION_OBJECT,
            subject_id=item.id,
        )
    return tuple(raised)


def settle_reopened(uow: UnitOfWork, scope: PeriodScope) -> tuple[UUID, ...]:
    """The reopen decision of ``scope`` settles the open items of its period state (module
    docstring, "The two roads"): RESOLVED by the system, in the decision's transaction. An item a
    person's command holds is waited for — no later run would settle it."""
    key = exceptions.dedupe_key(ExceptionSource.CLOSE, CODE, f"{scope.state_id}:")
    open_ids = uow.session.scalars(
        select(exception_item.c.id)
        .where(
            exception_item.c.code == CODE,
            exception_item.c.dedupe_key.startswith(key, autoescape=True),
            exception_item.c.status.in_(exceptions.OPEN_STATUSES),
        )
        .order_by(exception_item.c.exception_no)
    ).all()
    return exceptions.settle_gone(
        uow,
        [UUID(str(item_id)) for item_id in open_ids],
        resolution=REOPENED.format(
            period=scope.period_key, entity=scope.entity_code, book=scope.book_code
        ),
        wait=True,
    )
