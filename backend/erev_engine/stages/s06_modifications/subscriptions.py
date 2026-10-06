"""Stage 06 subscription commands and credit rollover (ENGINE_SPEC §6.4 S06-R-19; ENGINE_SPEC_B
§9.2.6 S09-R-22, stage 06 part; REQ-MOD-012, REQ-MOD-017).

The platform builds the lines of a subscription command (API-R-31 ``subscription-changes``), and
stage 06 proposes and applies them as §6.2 and §6.3. ``lines`` builds the T-CON-06 lines of
``UPGRADE``, ``DOWNGRADE``, ``CO_TERM``, ``RENEWAL``, ``EARLY_RENEWAL`` and ``CANCELLATION`` for one
subscription obligation. ``check`` refuses a modification of one of those E-25 kinds whose lines do
not have the S06-R-19 shape (CV-45). Each command receives the S06-R-04 test first, so a renewal
priced at its d SSP is proposed as a separate contract. A ``CANCELLATION`` is a termination: the
platform appends ``CONTRACT_TERMINATED`` for its approved modification (S06-R-21).

A renewal that carries unconsumed prepaid credits is a ``CONTRACT_AMENDED`` of kind ``RENEWAL`` on
the source contract. Its ``CHANGE`` line on the redemption obligation has ΔQ = ΔC = 0 and a later
``end_date``. The obligation takes a ``PROSPECTIVE`` segment with the same ``x_exact`` and
``a_posted`` and joins no pool, so the unredeemed consideration stays with the obligation it was
paid for. The renewal's own consideration is booked as its own contract with
``renewal_of_contract_key`` lineage (S09-R-22). Private to stage 06. Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.enums import RecognitionMethod
from erev_engine.stages.s01_canonicalize import payload_date
from erev_engine.stages.s06_modifications import segments
from erev_engine.stages.s06_modifications.classify import ModificationLine, ModificationView
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    ProgressBase,
    SegmentCause,
)

__all__ = [
    "KINDS",
    "SubscriptionCommand",
    "check",
    "extension_segment",
    "lines",
    "redemption_measure",
    "rollover_extensions",
]

UPGRADE: Final = "UPGRADE"
DOWNGRADE: Final = "DOWNGRADE"
CO_TERM: Final = "CO_TERM"
RENEWAL: Final = "RENEWAL"
EARLY_RENEWAL: Final = "EARLY_RENEWAL"
CANCELLATION: Final = "CANCELLATION"
# E-25 subscription kinds (04 §3.4; API-R-31 subscription-change actions).
KINDS: Final = frozenset({UPGRADE, DOWNGRADE, CO_TERM, RENEWAL, EARLY_RENEWAL, CANCELLATION})
ADD: Final = "ADD"
CHANGE: Final = "CHANGE"
REMOVE: Final = "REMOVE"
_DAY: Final = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class SubscriptionCommand:
    """One API-R-31 subscription change of a subscription obligation (E-25 kind; T-CON-06)."""

    kind: str
    effective_date: date  # d
    quantity_delta: Decimal = Decimal(0)  # ΔQ of the command's main line
    consideration_delta: Decimal = Decimal(0)  # ΔC of the command's main line
    added_obligation_key: str | None = None  # CO_TERM, RENEWAL, EARLY_RENEWAL
    renewal_end_date: date | None = None  # RENEWAL, EARLY_RENEWAL
    current_term_consideration_delta: Decimal = Decimal(0)  # EARLY_RENEWAL price change


def _line(
    key: str,
    action: str,
    product_code: str | None,
    quantity: Decimal,
    consideration: Decimal,
    start: date,
    end: date,
) -> Mapping[str, object]:
    members: dict[str, object] = {
        "action": action,
        "consideration_delta": consideration,
        "end_date": end,
        "obligation_key": key,
        "quantity_delta": quantity,
        "start_date": start,
    }
    if product_code is not None:
        members["product_code"] = product_code
    return MappingProxyType(members)


def _require(condition: bool, command: SubscriptionCommand, message: str) -> None:
    if not condition:
        raise ValueError(f"{command.kind}: {message} (S06-R-19)")


def _renewal(ob: ObligationState, command: SubscriptionCommand, end: date) -> Mapping[str, object]:
    key, renewal_end = command.added_obligation_key, command.renewal_end_date
    _require(key is not None, command, "a renewal names added_obligation_key")
    _require(renewal_end is not None and renewal_end > end, command, "the renewal term ends later")
    _require(command.quantity_delta > 0, command, "a renewal adds a positive quantity")
    _require(command.consideration_delta >= 0, command, "a renewal adds non-negative consideration")
    assert key is not None and renewal_end is not None
    return _line(
        key,
        ADD,
        ob.product_code,
        command.quantity_delta,
        command.consideration_delta,
        end + _DAY,
        renewal_end,
    )


def lines(ob: ObligationState, command: SubscriptionCommand) -> tuple[Mapping[str, object], ...]:
    """The T-CON-06 lines of one subscription command on ``ob`` (S06-R-19).

    ``UPGRADE``: a ``CHANGE`` line for the remaining term with ΔQ > 0 or ΔC > 0. ``DOWNGRADE``: a
    ``CHANGE`` line with ΔQ < 0 or ΔC < 0; removed units reduce the carried units (POL-081).
    ``CO_TERM``: an ``ADD`` line from d to the original end date. ``RENEWAL``: an ``ADD`` line from
    the day after the original end date to ``renewal_end_date``. ``EARLY_RENEWAL``: the renewal
    line, effective d on or before the original end, and any price change of the current term as a
    ``CHANGE`` line. ``CANCELLATION``: a ``REMOVE`` line for the remaining term, applied through
    ``CONTRACT_TERMINATED``. A command out of shape raises ``ValueError``.
    """
    d, end, product = command.effective_date, ob.end_date, ob.product_code
    if end is None:
        raise ValueError(f"{ob.subject_key}: a subscription command needs a term end (S06-R-19)")
    dq, dc = command.quantity_delta, command.consideration_delta
    match command.kind:
        case "UPGRADE":
            _require(d <= end, command, "an upgrade is effective within the term")
            _require(dq >= 0 and dc >= 0 and (dq > 0 or dc > 0), command, "an upgrade adds")
            return (_line(ob.obligation_key, CHANGE, product, dq, dc, d, end),)
        case "DOWNGRADE":
            _require(d <= end, command, "a downgrade is effective within the term")
            _require(dq <= 0 and dc <= 0 and (dq < 0 or dc < 0), command, "a downgrade reduces")
            return (_line(ob.obligation_key, CHANGE, product, dq, dc, d, end),)
        case "CO_TERM":
            key = command.added_obligation_key
            _require(key is not None, command, "a co-term line names added_obligation_key")
            _require(d <= end, command, "a co-term line starts within the term")
            _require(dq > 0 and dc >= 0, command, "a co-term line adds units")
            assert key is not None
            return (_line(key, ADD, product, dq, dc, d, end),)
        case "RENEWAL":
            return (_renewal(ob, command, end),)
        case "EARLY_RENEWAL":
            _require(d <= end, command, "an early renewal is effective before the original end")
            renewal = _renewal(ob, command, end)
            change = command.current_term_consideration_delta
            if change == 0:
                return (renewal,)
            current = _line(ob.obligation_key, CHANGE, product, Decimal(0), change, d, end)
            return (renewal, current)
        case "CANCELLATION":
            _require(d <= end, command, "a cancellation is effective within the term")
            _require(dq <= 0 and dc <= 0, command, "a cancellation removes")
            return (_line(ob.obligation_key, REMOVE, product, dq, dc, d, end),)
    raise ValueError(f"{command.kind} is not a subscription command (E-25; S06-R-19)")


def _extends(line: ModificationLine, ob: ObligationState | None, end: date | None) -> bool:
    """A rollover extension: a ``CHANGE`` line with ΔQ = ΔC = 0 moving a redemption obligation's
    end date later (S09-R-22)."""
    return (
        ob is not None
        and ob.recognition_method == RecognitionMethod.REDEMPTION_PATTERN
        and line.action == CHANGE
        and line.quantity_delta == 0
        and line.consideration_delta == 0
        and end is not None
        and ob.end_date is not None
        and end > ob.end_date
    )


def _renews(line: ModificationLine, ends: set[date], start: date | None, end: date | None) -> bool:
    return (
        line.action == ADD
        and line.quantity_delta > 0
        and line.consideration_delta >= 0
        and start is not None
        and start - _DAY in ends
        and end is not None
        and end >= start
    )


def _remaining_term(
    ob: ObligationState | None, start: date | None, end: date | None, d: date
) -> bool:
    return ob is not None and (start is None or start == d) and (end is None or end == ob.end_date)


def _shaped(
    kind: str, line: ModificationLine, ob: ObligationState | None, ends: set[date], d: date
) -> tuple[bool, bool]:
    """(the line has the S06-R-19 shape of ``kind``, the line is a renewal line)."""
    start, end = payload_date(line.members, "start_date"), payload_date(line.members, "end_date")
    dq, dc = line.quantity_delta, line.consideration_delta
    match kind:
        case "UPGRADE":
            grows = dq >= 0 and dc >= 0 and (dq > 0 or dc > 0)
            return line.action == CHANGE and grows and _remaining_term(ob, start, end, d), False
        case "DOWNGRADE":
            shrinks = dq <= 0 and dc <= 0 and (dq < 0 or dc < 0)
            return line.action == CHANGE and shrinks and _remaining_term(ob, start, end, d), False
        case "CO_TERM":
            ok = line.action == ADD and dq > 0 and dc >= 0 and start == d and end in ends
            return ok, False
        case "RENEWAL":
            renews = _renews(line, ends, start, end)
            return renews or _extends(line, ob, end), renews
        case "EARLY_RENEWAL":
            renews = _renews(line, ends, start, end) and start is not None and d <= start - _DAY
            price = line.action == CHANGE and dq == 0 and _remaining_term(ob, start, end, d)
            return renews or price or _extends(line, ob, end), renews
    ok = line.action == REMOVE and dq <= 0 and dc <= 0  # CANCELLATION
    return ok, False


def check(mod: ModificationView, existing: Sequence[ObligationState]) -> None:
    """A modification of an E-25 subscription kind has the S06-R-19 line shapes (CV-45)."""
    if mod.kind not in KINDS:
        return
    if not mod.lines:
        raise ValueError(f"{mod.modification_key}: a {mod.kind} modification has lines (S06-R-19)")
    by_key = {ob.obligation_key: ob for ob in existing}
    ends = {ob.end_date for ob in existing if ob.end_date is not None}
    renewals = 0
    for line in mod.lines:
        ok, renews = _shaped(
            mod.kind, line, by_key.get(line.obligation_key), ends, mod.effective_date
        )
        if not ok:
            raise ValueError(
                f"{mod.modification_key}: line {line.obligation_key} does not have the "
                f"{mod.kind} shape (S06-R-19)"
            )
        renewals += renews
    if mod.kind == EARLY_RENEWAL and renewals == 0:
        raise ValueError(f"{mod.modification_key}: an early renewal adds a renewal line (S06-R-19)")


def rollover_extensions(
    mod: ModificationView, existing: Sequence[ObligationState]
) -> Mapping[str, date]:
    """Obligation key → extended end date of every rollover extension of a renewal (S09-R-22)."""
    if mod.kind not in (RENEWAL, EARLY_RENEWAL):
        return MappingProxyType({})
    by_key = {ob.obligation_key: ob for ob in existing}
    found: dict[str, date] = {}
    for line in mod.lines:
        end = payload_date(line.members, "end_date")
        if end is not None and _extends(line, by_key.get(line.obligation_key), end):
            found[line.obligation_key] = end
    return MappingProxyType(dict(sorted(found.items())))


def extension_segment(
    ev: EventView, seg: AllocationSegment, end: date, *, cause: SegmentCause
) -> AllocationSegment:
    """The ``PROSPECTIVE`` segment of a rollover extension: the same X and A over the longer term.

    The base is 0 with no transferred units, so the redemption revenue E = X × redeemed ÷ Q is
    continuous across the boundary (ENGINE_SPEC_B §9.2.8).
    """
    return AllocationSegment(
        component=segments.FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=cause,
        basis=segments.PROSPECTIVE,
        x_exact=seg.x_exact,
        a_posted=seg.a_posted,
        base_revenue_posted=0,
        base_revenue_exact=Fraction(0),
        base_progress=ProgressBase(Fraction(0), Fraction(0), Fraction(0), ev.effective_date),
        totals=dataclasses.replace(seg.totals, end_date=end),
        progress_measure=seg.progress_measure,
        unit_ssp=seg.unit_ssp,
        remaining_ssp=seg.remaining_ssp,
        remaining_billing_plan=seg.remaining_billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=seg.modification_boundary_no,
    )


def redemption_measure(
    ctx: BookContext, st: AllocatedState, ob: ObligationState, seg: AllocationSegment, ev: EventView
) -> segments.Measured:
    """A redemption obligation measured at the boundary by redeemed units ÷ Q (S09-R-21).

    Redeemed units are net delivered units plus drawdown usage. Breakage is left out: it is the
    same before and after an extension, so the catch-up of S06-R-17 is 0 by construction.
    """
    point = st.ledger.at(ob.subject_key, before=ev)
    delivered = point.delivered_cum - point.returned_cum
    redeemed = max(Fraction(0), delivered + point.usage_quantity_cum)
    total = seg.totals.quantity
    fraction = Fraction(1) if total <= 0 else min(Fraction(1), redeemed / total)
    exact, posted, complete = segments.cumulative(ctx, seg, fraction, ob.subject_key)
    return segments.Measured(
        seg, point, fraction, exact, posted, complete, delivered, total - redeemed
    )
