"""Stage 09 event-driven measures of progress (ENGINE_SPEC_B §9.2.4; ENC-1, ENC-3, ENC-4, ENC-7).

``POINT_IN_TIME`` counts the quantities of control-transferring ``DELIVERY_RECORDED`` events: the
S09-R-11 triggers permitted by the resolved POL-095 option, ``BILL_AND_HOLD`` only under the four
S09-R-12 criteria, and only ``CONTROL_TRANSFER`` while a S09-R-13 ``FINANCING`` repurchase option
is open. ``UNITS_DELIVERED`` counts every permitted trigger (S09-R-10). Units returned
(``RETURN_RECORDED``) reduce both counts (§9.2.4 "less returns"); expected returns and the POL-052
reversal rate are applied by ``returns`` (§9.2.7). ``OUTPUT_PERCENT`` and ``MILESTONE`` read the
latest cumulative ratio or weight at or before the date. Since a ``PROSPECTIVE`` boundary each
measure restarts over the remaining totals (CV-62). A ``Position`` restricts the events to those
at or before an ENG-06 position within the date (S09-R-04, §9.2.10). Every value comes from its
registered formula, so the trace node reproduces it (DG-KRN-EXP-04). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, rational_param
from erev_engine.money import to_fraction
from erev_engine.stages.s09_recognition.progress_time import Progress
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EventView,
    Finding,
    ObligationState,
    OrderKey,
)

__all__ = [
    "BILL_AND_HOLD_CRITERIA",
    "CONTROL_TRIGGERS",
    "EVENT_FORMULAS",
    "MILESTONE_FORMULA",
    "OUTPUT_PERCENT_FORMULA",
    "POINT_IN_TIME_FORMULA",
    "REPURCHASE_OUTCOMES",
    "TRIGGER_OPTIONS",
    "UNITS_FORMULA",
    "Position",
    "Tally",
    "admitted",
    "bill_and_hold_criteria_met",
    "boundary_key",
    "concerns",
    "control_trigger_option",
    "first_bill_and_hold_transfer",
    "hold_reason",
    "option_expired",
    "progress",
    "quantity",
    "remaining_quantity",
    "repurchase_outcome",
    "tally",
    "trigger_findings",
]

# S09-R-11: triggers that transfer control; BILL_AND_HOLD does so only under S09-R-12.
CONTROL_TRIGGERS: Final = frozenset({"DELIVERY", "ACCEPTANCE", "SELL_THROUGH", "CONTROL_TRANSFER"})
_TRIGGERS: Final = CONTROL_TRIGGERS | {"BILL_AND_HOLD"}  # 04 §16.3 DELIVERY_RECORDED.trigger
# POL-095 recognition.control_trigger: the triggers each option permits (S09-R-11; D-77 item 8).
TRIGGER_OPTIONS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "ANY_TRANSFER": _TRIGGERS,
        "ACCEPTANCE_ONLY": frozenset({"ACCEPTANCE", "CONTROL_TRANSFER"}),
        "SELL_THROUGH_ONLY": frozenset({"SELL_THROUGH", "CONTROL_TRANSFER"}),
    }
)
# 04 T-CON-19 questionnaire members, 606-10-55-83(a) to (d) (ENGINE_SPEC Table 0.4-A).
BILL_AND_HOLD_CRITERIA: Final = (
    "reason_substantive",
    "identified_as_customer_product",
    "ready_for_physical_transfer",
    "cannot_use_or_direct_to_another_customer",
)
REPURCHASE_OUTCOMES: Final = frozenset({"FINANCING", "LEASE", "RIGHT_OF_RETURN", "SALE"})  # POL-233
POINT_IN_TIME_FORMULA: Final = "rec.progress.point_in_time.v1"
UNITS_FORMULA: Final = "rec.progress.units.v1"
OUTPUT_PERCENT_FORMULA: Final = "rec.progress.output_percent.v1"
MILESTONE_FORMULA: Final = "rec.progress.milestone.v1"
EVENT_FORMULAS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "POINT_IN_TIME": POINT_IN_TIME_FORMULA,
        "UNITS_DELIVERED": UNITS_FORMULA,
        "OUTPUT_PERCENT": OUTPUT_PERCENT_FORMULA,
        "MILESTONE": MILESTONE_FORMULA,
    }
)
# Reasons a delivery is counted as delivered without a control transfer (trace params "reason").
TRIGGER_NOT_PERMITTED: Final = "TRIGGER_NOT_PERMITTED"  # S09-R-11
CRITERIA_UNMET: Final = "BILL_AND_HOLD_CRITERIA_UNMET"  # S09-R-12
REPURCHASE_OPTION_OPEN: Final = "REPURCHASE_OPTION_OPEN"  # S09-R-13 FINANCING
_STAGE: Final = 9


@dataclass(frozen=True, slots=True)
class Position:
    """An ENG-06 position within a date: events at or before ``order_key``, or strictly before."""

    order_key: OrderKey
    inclusive: bool

    def admits(self, key: OrderKey) -> bool:
        """Whether an event with ENG-06 key ``key`` precedes the position (CV-20)."""
        return key <= self.order_key if self.inclusive else key < self.order_key


@dataclass(frozen=True, slots=True)
class Tally:
    """Units counted, returned and held back for one obligation at a date."""

    counted: Fraction
    returned: Fraction
    held: tuple[tuple[EventView, str], ...]  # (delivery, reason) not transferring control


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def admitted(ev: EventView, d: date, position: Position | None = None) -> bool:
    """The event is effective on or before ``d`` and precedes ``position`` when one is given."""
    return ev.effective_date <= d and (position is None or position.admits(ev.order_key))


def concerns(ev: EventView, ob: ObligationState) -> bool:
    """The event names the obligation, by subject key or by its payload ``obligation_key``."""
    if ob.subject_key in ev.obligation_subject_keys:
        return True
    return ev.contract_key == ob.contract_key and ev.payload.get("obligation_key") == (
        ob.obligation_key
    )


def _judgements(
    ctx: BookContext, contract: ContractView, topic: str, obligation_key: str
) -> list[Mapping[str, str]]:
    # REVIEWED records only reach the bundle (T-CON-19); None as book_code means every book.
    return [
        judgement.outcome
        for judgement in contract.header.judgements
        if judgement.topic == topic
        and judgement.book_code in (None, str(ctx.book_code))
        and judgement.outcome.get("obligation_key") == obligation_key
    ]


def _bill_and_hold_gap(ctx: BookContext, contract: ContractView, obligation_key: str) -> str:
    """Empty when a record meets all four criteria; else the unmet members, or ``NO_JUDGEMENT``."""
    records = _judgements(ctx, contract, "BILL_AND_HOLD", obligation_key)
    if not records:
        return "NO_JUDGEMENT"
    gaps = [
        ",".join(member for member in BILL_AND_HOLD_CRITERIA if outcome.get(member) != "true")
        for outcome in records
    ]
    return "" if "" in gaps else gaps[0]


def bill_and_hold_criteria_met(
    ctx: BookContext, contract: ContractView, obligation_key: str
) -> bool:
    """A REVIEWED ``BILL_AND_HOLD`` judgement of the book, all four members ``true`` (S09-R-12)."""
    return _bill_and_hold_gap(ctx, contract, obligation_key) == ""


def repurchase_outcome(ctx: BookContext, contract: ContractView, ob: ObligationState) -> str | None:
    """The REVIEWED ``REPURCHASE_CLASSIFICATION`` outcome of the obligation, if any (S09-R-13)."""
    outcomes = {
        outcome.get("outcome")
        for outcome in _judgements(ctx, contract, "REPURCHASE_CLASSIFICATION", ob.obligation_key)
    }
    if not outcomes:
        return None
    if len(outcomes) > 1 or not outcomes <= REPURCHASE_OUTCOMES:
        raise _invariant(
            "the repurchase classification is not one POL-233 outcome", ob, rule="S09-R-13"
        )
    return str(next(iter(outcomes)))


def control_trigger_option(ctx: BookContext, ob: ObligationState) -> str:
    """The resolved POL-095 ``recognition.control_trigger`` option (levels P, O; pin K)."""
    option = ctx.policies.value(
        "recognition.control_trigger",
        contract=ob.contract_key,
        obligation=ob.subject_key,
        entity=ob.performing_entity,
    )
    if not isinstance(option, str) or option not in TRIGGER_OPTIONS:
        raise _invariant("the control-trigger option is unknown", ob, rule="S09-R-11")
    return option


def hold_reason(
    ctx: BookContext,
    contract: ContractView,
    ob: ObligationState,
    ev: EventView,
    *,
    option: str,
    outcome: str | None,
) -> str | None:
    """None when the delivery counts; otherwise why it does not transfer control."""
    trigger = ev.payload.get("trigger")
    if trigger not in _TRIGGERS:
        raise _invariant(
            "a delivery carries an unknown trigger", ob, rule="CV-45", event_key=ev.event_key
        )
    if outcome == "FINANCING" and trigger != "CONTROL_TRANSFER":
        return REPURCHASE_OPTION_OPEN
    if trigger not in TRIGGER_OPTIONS[option]:
        return TRIGGER_NOT_PERMITTED
    if (
        trigger == "BILL_AND_HOLD"
        and str(ob.recognition_method) == "POINT_IN_TIME"
        and not bill_and_hold_criteria_met(ctx, contract, ob.obligation_key)
    ):
        return CRITERIA_UNMET
    return None


def quantity(ev: EventView, ob: ObligationState) -> Fraction:
    """The non-negative payload ``quantity`` of a measure event (CV-45)."""
    raw = ev.payload.get("quantity")
    if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal | Fraction):
        raise _invariant(
            "a measure event carries no quantity", ob, rule="CV-45", event_key=ev.event_key
        )
    value = to_fraction(raw)
    if value < 0:
        raise _invariant(
            "a measure event quantity is negative", ob, rule="CV-45", event_key=ev.event_key
        )
    return value


def tally(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    d: date,
    position: Position | None = None,
) -> Tally:
    """N (counted deliveries) and Y (returns) effective on or before ``d`` (§9.2.4)."""
    option = control_trigger_option(ctx, ob)
    outcome = repurchase_outcome(ctx, contract, ob)
    counted = returned = Fraction(0)
    held: list[tuple[EventView, str]] = []
    for ev in st.measure_events:
        if not admitted(ev, d, position) or not concerns(ev, ob):
            continue
        if ev.event_type == "RETURN_RECORDED":
            returned += quantity(ev, ob)
        elif ev.event_type == "DELIVERY_RECORDED":
            reason = hold_reason(ctx, contract, ob, ev, option=option, outcome=outcome)
            if reason is None:
                counted += quantity(ev, ob)
            else:
                held.append((ev, reason))
    return Tally(counted, returned, tuple(held))


def first_bill_and_hold_transfer(
    ctx: BookContext, st: AllocatedState, contract: ContractView
) -> date | None:
    """Effective date of the contract's first bill-and-hold control transfer (S09-R-09, -12)."""
    for ev in st.measure_events:
        obligation_key = ev.payload.get("obligation_key")
        if (
            ev.contract_key == contract.header.external_id
            and ev.event_type == "DELIVERY_RECORDED"
            and ev.payload.get("trigger") == "BILL_AND_HOLD"
            and isinstance(obligation_key, str)
            and bill_and_hold_criteria_met(ctx, contract, obligation_key)
        ):
            return ev.effective_date
    return None


def boundary_key(st: AllocatedState, ob: ObligationState, seg: AllocationSegment) -> OrderKey:
    """ENG-06 key of the boundary event that created ``seg`` (CV-60)."""
    for ev in st.events:
        if ev.event_key == seg.event_key:
            return ev.order_key
    raise _invariant("the boundary event of a segment is absent", ob, rule="CV-60")


def _latest_ratio(
    st: AllocatedState,
    ob: ObligationState,
    *,
    event_type: str,
    member: str,
    d: date,
    position: Position | None = None,
) -> Fraction:
    """The member of the latest admitted event at or before ``d``; 0 before any."""
    latest: tuple[OrderKey, Fraction] | None = None
    for ev in st.measure_events:
        if ev.event_type != event_type or not admitted(ev, d, position) or not concerns(ev, ob):
            continue
        if event_type == "PROGRESS_RECORDED" and ev.payload.get("measure") != "OUTPUT_PERCENT":
            continue
        raw = ev.payload.get(member)
        if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal | Fraction):
            raise _invariant(
                "a progress event carries no ratio", ob, rule="CV-45", event_key=ev.event_key
            )
        if latest is None or ev.order_key > latest[0]:
            latest = (ev.order_key, to_fraction(raw))
    return Fraction(0) if latest is None else latest[1]


def _evaluate(ob: ObligationState, formula_id: str, params: dict[str, str]) -> Progress:
    frozen = MappingProxyType(dict(sorted(params.items())))
    try:
        value = FORMULAS[formula_id]((), frozen)
    except ValueError as error:
        raise EngineError(
            "NON_FINITE_AMOUNT",
            "progress is undefined for the obligation",
            subject_key=ob.subject_key,
            formula_id=formula_id,
            detail={"rule": "CV-32"},
        ) from error
    return Progress(value, formula_id, frozen)


def option_expired(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None = None
) -> EventView | None:
    """The ``MATERIAL_RIGHT_EXPIRED`` naming a material-right obligation, admitted at ``d`` and
    ``position``, or None (S06-R-25; ALG-05 §2.6.4: the remaining allocation is recognised)."""
    if str(ob.obligation_kind) != "MATERIAL_RIGHT":
        return None
    for ev in st.measure_events:
        if ev.event_type != "MATERIAL_RIGHT_EXPIRED":
            continue
        if admitted(ev, d, position) and concerns(ev, ob):
            return ev
    return None


def progress(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None = None,
    method: str | None = None,
) -> Progress:
    """f(d) on the inception basis, or g(d) since a boundary, for an event-driven measure.

    ``method`` measures the segment by another E-11 event-driven measure than the obligation's own:
    the ``FIXED`` guarantee of a ``ROYALTY`` licence follows the licence pattern (S09-R-33).
    """
    method = str(ob.recognition_method) if method is None else method
    formula_id = EVENT_FORMULAS.get(method)
    if formula_id is None:
        raise _invariant("the measure is not event driven", ob, rule="S09-R-02", method=method)
    prospective = seg.basis == "PROSPECTIVE"
    params: dict[str, str] = {"as_of": d.isoformat()}
    if method in ("POINT_IN_TIME", "UNITS_DELIVERED"):
        counts = tally(ctx, st, contract, ob, d, position)
        base = seg.base_progress.delivered_cum if prospective else Fraction(0)
        params["base"] = rational_param(base)
        params["quantity"] = rational_param(seg.totals.quantity)
        params["returned"] = rational_param(counts.returned)
        member = "transferred" if method == "POINT_IN_TIME" else "delivered"
        params[member] = rational_param(counts.counted)
        if counts.held:
            params["reason"] = ",".join(sorted({reason for _, reason in counts.held}))
        outcome = repurchase_outcome(ctx, contract, ob)
        if outcome is not None:
            params["repurchase"] = outcome
        expired = option_expired(st, ob, d, position)
        if expired is not None:  # JET-08 expiry: the option's remaining allocation (S06-R-25)
            params["expired"] = "true"
            params["expired_on"] = expired.effective_date.isoformat()
        return _evaluate(ob, formula_id, params)
    event_type, member = (
        ("PROGRESS_RECORDED", "cumulative_progress_ratio")
        if method == "OUTPUT_PERCENT"
        else ("MILESTONE_ACHIEVED", "cumulative_weight")
    )
    current = _latest_ratio(st, ob, event_type=event_type, member=member, d=d, position=position)
    base = Fraction(0)
    if prospective:
        boundary = boundary_key(st, ob, seg)
        before = Position(boundary, inclusive=False)
        base = _latest_ratio(
            st, ob, event_type=event_type, member=member, d=boundary[0], position=before
        )
    params["base"] = rational_param(base)
    params["ratio" if method == "OUTPUT_PERCENT" else "weight"] = rational_param(current)
    return _evaluate(ob, formula_id, params)


def trigger_findings(
    ctx: BookContext, st: AllocatedState, contract: ContractView, ob: ObligationState, d: date
) -> tuple[Finding, ...]:
    """``BILL_AND_HOLD_CRITERIA_UNMET`` once per obligation and delivery on or before ``d``."""
    if str(ob.recognition_method) != "POINT_IN_TIME":
        return ()
    findings: list[Finding] = []
    for ev, reason in tally(ctx, st, contract, ob, d).held:
        if reason != CRITERIA_UNMET:
            continue
        detail = {"rule": "S09-R-12", "unmet": _bill_and_hold_gap(ctx, contract, ob.obligation_key)}
        findings.append(
            Finding(CRITERIA_UNMET, "WARNING", ob.subject_key, detail, _STAGE, ev.event_key)
        )
    return tuple(findings)


def remaining_quantity(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None = None,
) -> Fraction:
    """Undelivered quantity at ``d`` over the segment totals (T-CON-11 ``remaining_quantity``).

    POL-053 (S09-R-24; ALG-06 §2.7.3). Under ``RESTORE_REMAINING_QUANTITY`` returned units are
    deliverable again, so the remaining quantity is Q′ − (N − Y − N_k). Under
    ``REDUCE_CONTRACT_QUANTITY`` returned units leave the contract, so a return leaves Q′ − N
    unchanged; since a boundary N counts the deliveries after it, which are N − Y_k − N_k with
    Y_k the units returned before the boundary (N_k is net of them; L1-3-Q-10).
    """
    counts = tally(ctx, st, contract, ob, d, position)
    scope = ctx.policies.value(
        "returns.returned_units_scope",
        contract=ob.contract_key,
        obligation=ob.subject_key,
        entity=ob.performing_entity,
    )
    path = st.return_paths.get(ob.subject_key)
    if path is not None and "returns.returned_units_scope" in path.policy:
        scope = path.policy["returns.returned_units_scope"]
    prospective = seg.basis == "PROSPECTIVE"
    base = seg.base_progress.delivered_cum if prospective else Fraction(0)
    if scope == "RESTORE_REMAINING_QUANTITY":
        return seg.totals.quantity - (counts.counted - counts.returned - base)
    if scope != "REDUCE_CONTRACT_QUANTITY":
        raise _invariant("the returned-units scope is unknown", ob, rule="S09-R-24")
    if not prospective:
        return seg.totals.quantity - counts.counted
    boundary = boundary_key(st, ob, seg)
    before = tally(ctx, st, contract, ob, boundary[0], Position(boundary, inclusive=False))
    return seg.totals.quantity - (counts.counted - before.returned - base)
