"""Stage 14 manual adjustment lines (ENGINE_SPEC_B §14.1, Table 14-A "Manual adjustment",
S14-R-09a; §9.2.11 S09-R-41; 04 T-SL-05, E-93; 05 RCP-05; supervisor ruling R-51 (a)).

An approved T-SL-05 adjustment of kind ``MANUAL_JOURNAL`` or ``ACCOUNT_RECLASS`` reaches the engine
as ``MANUAL_ADJUSTMENT_APPLIED`` with the approved adjustment in its payload (the bundle builder
resolves the row into natural keys, L1-3-Q-14): ``kind`` (E-93), ``book_code``, ``entity_code``
(the adjustment entity), ``period_key`` (the adjustment period P), ``obligation_key`` when the lines
belong to an obligation, and ``lines`` [{``account_role``, ``amount_txn``}], signed, debit positive.

Each approved line is a share of the role key (book, adjustment entity, the obligation or
``<contract>@<entity>``, ``MANUAL_ADJUSTMENT``, role): the cumulative target of a role key through
a period end is the signed sum of the lines of the adjustments whose period is on or before it.
The amounts are ``EVENT`` class and carry no ``TIME`` share (Table 14-A). The delta rule then
treats them as every other target (S14-R-04 to S14-R-08): a ledger that holds the approved lines —
the platform posts them when the adjustment is approved, with the accounts as approved (04
T-SL-05) — shows posted = target and nothing is emitted; a ledger that does not hold them receives
them from stage 14, account by T-REF-15 (S14-R-14); an adjustment whose event is voided has no
target, so its posted lines are reversed. Lines of one role net within their role key: a
reclassification between two accounts of one role has a target of 0 and is never derived here.

An adjustment applies in the book it names (``book_code``; a payload without one applies in every
book). 1.0 limit (ruling R-51): the contract is in its entity's functional currency — a T-SL-05
line states one amount and no rate reference, so a foreign-currency line could not name its rate
(S14-INV-08) — and an adjustment of another contract is refused by name. Each line therefore has
one amount in both currencies, and the opposed-sign form of S14-R-10 cannot arise from it.
Private to stage 14 (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.money import format_money, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    obligation_subject_key,
)
from erev_engine.stages.s14_posting.targets import RoleKey, RoleTarget
from erev_engine.stages.s14_posting.templates import INTERCOMPANY_ROLES, RESERVED_ROLES
from erev_engine.stages.state import AllocatedState, BookContext, EventView
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["ENTRY_KIND", "EVENT_TYPE", "KINDS", "applies_in_book", "merged", "role_targets"]

EVENT_TYPE: Final = "MANUAL_ADJUSTMENT_APPLIED"
ENTRY_KIND: Final = "MANUAL_ADJUSTMENT"  # 04 E-29
KINDS: Final = frozenset({"MANUAL_JOURNAL", "ACCOUNT_RECLASS"})  # 04 E-93 kinds with lines
# Roles a manual line cannot name: the reserved ones (D-14a), the roles that need a clearing
# purpose or a counterparty the T-SL-05 line shape does not carry, and ROUNDING (S14-R-11).
_REFUSED_ROLES: Final = frozenset(
    {*RESERVED_ROLES, *INTERCOMPANY_ROLES, "BILLING_CLEARING", "ROUNDING"}
)
RULE: Final = "S14-R-09a"


def applies_in_book(ctx: BookContext, payload: Mapping[str, object]) -> bool:
    """Whether an adjustment payload applies in ``ctx``'s book: it names the book, or names none
    (S09-R-41; T-SL-05 ``book_code``)."""
    named = payload.get("book_code")
    return named is None or named == str(ctx.book_code)


@dataclass(frozen=True, slots=True)
class _Line:
    """One approved line as a share of its role key from ``position`` on."""

    position: int  # index of the adjustment period in the entity's calendar
    txn: int  # signed minor units, debit positive
    functional: int  # the same amount: the contract is in the functional currency
    source: SourceRef  # the event, naming the line and carrying its transaction amount


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"rule": RULE, "event_key": ev.event_key, **detail},
    )


def _minor(value: object, minor_unit: int, ev: EventView, member: str) -> int:
    """``value`` (a plain decimal) in whole minor units; anything else is a malformed payload."""
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        raise _invariant("a manual line amount is malformed", ev, member=member)
    scale: int = 10**minor_unit
    try:
        scaled = to_fraction(value) * scale
    except (TypeError, ValueError) as error:
        raise _invariant("a manual line amount is malformed", ev, member=member) from error
    if scaled.denominator != 1:
        raise _invariant("a manual line amount is below the minor unit", ev, member=member)
    return scaled.numerator


def _text(payload: Mapping[str, object], member: str, ev: EventView) -> str:
    value = payload.get(member)
    if not isinstance(value, str) or not value:
        raise _invariant(f"a manual adjustment names no {member}", ev, member=member)
    return value


def _lines_of(ctx: BookContext, ev: EventView, shares: dict[RoleKey, list[_Line]]) -> None:
    """Add the approved lines of one event to ``shares``; the lines of an adjustment balance, as
    the sealed posting does (04 DB-06)."""
    payload = ev.payload
    entity = _text(payload, "entity_code", ev)
    calendar = ctx.entities.get(entity)
    if calendar is None:
        raise _invariant("a manual adjustment names an entity the bundle lacks", ev, entity=entity)
    period_key = _text(payload, "period_key", ev)
    position = next(
        (index for index, item in enumerate(calendar.periods) if item.period_key == period_key),
        None,
    )
    if position is None:
        raise _invariant(
            "a manual adjustment names no period of the calendar", ev, period_key=period_key
        )
    obligation_key = payload.get("obligation_key")
    if obligation_key is not None and not isinstance(obligation_key, str):
        raise _invariant("a manual adjustment obligation key is malformed", ev)
    subject_key = (
        contract_entity_subject_key(ev.contract_key, entity)
        if obligation_key is None
        else obligation_subject_key(ev.contract_key, obligation_key)
    )
    rows = payload.get("lines")
    if not isinstance(rows, list | tuple) or len(rows) < 2:  # noqa: PLR2004 - a balanced entry
        raise _invariant("a manual adjustment carries fewer than two lines", ev)
    if calendar.functional_currency != ctx.txn_currency:
        raise _invariant(
            "a manual journal needs a contract in the entity's functional currency",
            ev,
            functional_currency=calendar.functional_currency,
            txn_currency=ctx.txn_currency,
        )
    unit = ctx.currencies[ctx.txn_currency].minor_unit
    total = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise _invariant("a manual line is malformed", ev, line=str(index))
        role = row.get("account_role")
        if not isinstance(role, str) or not role or role in _REFUSED_ROLES:
            raise _invariant(
                "a manual line names a role it cannot carry", ev, line=str(index), role=str(role)
            )
        amount = _minor(row.get("amount_txn"), unit, ev, f"lines[{index}].amount_txn")
        if amount == 0:
            raise _invariant("a manual line carries no amount", ev, line=str(index))
        total += amount
        key = RoleKey(str(ctx.book_code), entity, subject_key, ENTRY_KIND, role, None, None)
        source = SourceRef(
            "contract_event",
            ev.event_key,
            {"member": f"lines[{index}].amount_txn", "value": format_money(amount, unit)},
        )
        shares.setdefault(key, []).append(_Line(position, amount, amount, source))
    if total:
        raise _invariant(
            "the lines of a manual adjustment do not balance", ev, amount_txn=str(total)
        )


def role_targets(ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> tuple[RoleTarget, ...]:
    """The cumulative role targets of the approved manual lines of ``ctx``'s book, per role key
    and period end from the first adjustment period through the horizon (S14-R-09a)."""
    shares: dict[RoleKey, list[_Line]] = {}
    for ev in st.measure_events:
        if ev.event_type != EVENT_TYPE:
            continue
        kind = ev.payload.get("kind")
        if kind not in KINDS or not applies_in_book(ctx, ev.payload):
            continue  # a schedule kind changes stage 09 targets (S09-R-38 to R-40), no lines
        _lines_of(ctx, ev, shares)
    out: list[RoleTarget] = []
    for key in sorted(shares, key=RoleKey.sort_key):
        calendar = ctx.entities[key.entity]
        functional_currency = calendar.functional_currency
        lines = shares[key]
        horizon = ctx.horizon.get(key.entity)
        last = next(
            (index for index, item in enumerate(calendar.periods) if item.period_key == horizon),
            -1,
        )
        for index in range(min(line.position for line in lines), last + 1):
            current = [line for line in lines if line.position <= index]
            amount_txn = sum(line.txn for line in current)
            amount_functional = sum(line.functional for line in current)
            period_key = calendar.periods[index].period_key
            node_id = tb.node(
                measure="posting_target",
                subject_key=key.node_subject,
                period_key=period_key,
                value=amount_txn,
                currency=ctx.txn_currency,
                minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
                formula_id="post.role_target.v1",
                inputs=[line.source for line in current],
                params={
                    "amount_functional": str(amount_functional),
                    "signs": "|".join("1" for _ in current),
                    "time": "0",
                },
                narrative_key="post.role_target",
            )
            out.append(
                RoleTarget(
                    key=key,
                    period_key=period_key,
                    txn_currency=ctx.txn_currency,
                    functional_currency=functional_currency,
                    amount_txn=amount_txn,
                    amount_functional=amount_functional,
                    time_txn=0,
                    time_functional=0,
                    passes=(),
                    rates=(),
                    node_id=node_id,
                )
            )
    return tuple(out)


def merged(parts: Sequence[RoleTarget], manual: Sequence[RoleTarget]) -> tuple[RoleTarget, ...]:
    """The role targets of the Table 14-A parts with the manual ones, by role key; the two sets
    share no role key (the entry kind ``MANUAL_ADJUSTMENT`` belongs to this module alone)."""
    if any(target.key.entry_kind == ENTRY_KIND for target in parts):
        raise ValueError("a Table 14-A part carries the MANUAL_ADJUSTMENT entry kind (S14-R-09a)")
    if not manual:
        return tuple(parts)
    combined = (*parts, *manual)
    ranked = sorted(
        range(len(combined)), key=lambda index: (RoleKey.sort_key(combined[index].key), index)
    )
    return tuple(combined[index] for index in ranked)
