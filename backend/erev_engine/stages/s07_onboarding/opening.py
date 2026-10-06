"""Stage 07 opening balances (ENGINE_SPEC §7.1 to §7.3 S07-R-01 to S07-R-05, §7.5; ENB-9).

``parse`` reads the ``OPENING_BALANCE_ESTABLISHED`` payload (04 §16.3), ``consistency`` applies
S07-R-03 and returns ``OPENING_BALANCE_INCONSISTENT`` findings, and ``establish`` gives every
obligation of the contract a ``PROSPECTIVE`` segment with cause ``OPENING_BALANCE`` under POL-210
``OPENING_BALANCES_AT_CUTOVER`` (S07-R-04) and records its ``OpeningBaseline`` (S07-R-05). The
segment's base progress is the quantity ledger at the boundary (CV-62), and its remaining term
starts the day after the cutover, because the imported cumulative revenue covers the cutover date.
A contract whose inception is after the cutover carries the event on its inception date with nil
cumulative members (S07-R-01, S07-R-03, rev 1.38): nothing precedes the cutover. A business
combination has no such case.
The shared state has no member for baselines or onboarding differences, so they travel on
``ObligationState.opening`` next to the payload values (L1-3-Q-25). Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates, money
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    SegmentCause,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "BASELINE_FORMULA",
    "BUSINESS_COMBINATION",
    "EVENT_TYPE",
    "FINDING_CODE",
    "OPENING_BALANCES",
    "RECOMPUTE",
    "SEGMENT_FORMULA",
    "SEPARATOR",
    "TOLERANCE",
    "OnboardingDifference",
    "OpeningBaseline",
    "Payload",
    "Row",
    "apportion",
    "baseline_of",
    "consistency",
    "contract_obligations",
    "differences_of",
    "establish",
    "minor_unit",
    "opening_segment",
    "parse",
    "payload_ref",
    "required_in_force",
    "view",
]

EVENT_TYPE: Final = "OPENING_BALANCE_ESTABLISHED"
FINDING_CODE: Final = "OPENING_BALANCE_INCONSISTENT"
CUTOVER_CODE: Final = "ONBOARDING_CUTOVER_NOT_PERIOD_END"  # S07-R-01 rev 1.18 (D-98 candidate 22)
BUSINESS_COMBINATION: Final = "BUSINESS_COMBINATION"
REASONS: Final = frozenset({"BUSINESS_COMBINATION", "LEGACY_MIGRATION", "SYSTEM_ONBOARDING"})
OPENING_BALANCES: Final = "OPENING_BALANCES_AT_CUTOVER"
RECOMPUTE: Final = "RECOMPUTE_FROM_INCEPTION"
MEMBERS: Final = (  # 04 §16.3 obligations[] members besides obligation_key
    "billed_cum",
    "catch_up_cum",
    "delivered_quantity_cum",
    "deposit_liability",  # optional (04 §16.3 rev 1.26; S07-R-07 rev 1.18): None when absent
    "netting_reclass_amount",
    "position_obligation",
    "pre_standard_revenue_cum",
    "remaining_allocation",
    "remaining_billing",
    "remaining_quantity",
    "remaining_ssp",
    "revenue_cum",
    "ssp_delivered_cum",
)
REQUIRED: Final = frozenset({"remaining_allocation", "remaining_quantity", "revenue_cum"})
# Members that hold history through the cutover: nil for a contract that begins after it (S07-R-03).
CUMULATIVE: Final = (
    "billed_cum",
    "catch_up_cum",
    "delivered_quantity_cum",
    "deposit_liability",
    "netting_reclass_amount",
    "position_obligation",
    "pre_standard_revenue_cum",
    "revenue_cum",
    "ssp_delivered_cum",
)
# Optional members stage 14 never reads as 0 when absent (S07-R-07 rev 1.18; D-98 cand. 22, 35).
OPTIONAL_MEMBERS: Final = ("billed_cum", "deposit_liability")
TOLERANCE: Final = Fraction(1, 10_000)  # Σ X_i against the contract price (S07-R-03; D-17)
SEGMENT_FORMULA: Final = "onb.opening_segment.v1"
BASELINE_FORMULA: Final = "onb.baseline.v1"
SEPARATOR: Final = "|"  # list separator of formula params
_STAGE: Final = 7


@dataclass(frozen=True, slots=True)
class OpeningBaseline:
    """The cumulative amounts the ERP already holds at cutover (ENGINE_SPEC §7.1; ALG-01 §2.1.3)."""

    subject_key: str
    cutover_date: date
    revenue_cum: int  # posted-basis minor units, CV-63 at cutover
    billed_cum: int
    deposit_liability: (
        int | None
    )  # the optional payload member; None when absent (S07-R-07 rev 1.18)
    pre_standard_revenue_cum: int
    method: str  # OPENING_BALANCES_AT_CUTOVER | RECOMPUTE_FROM_INCEPTION
    node_id: str  # opening_revenue_cum@<event key>:<ob>:-
    # OPTIONAL_MEMBERS the payload omitted (S07-R-07 rev 1.18): stage 14 refuses a non-zero
    # recomputed target of such a member instead of reading 0 (ONBOARDING_MEMBER_MISSING).
    absent_members: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class OnboardingDifference:
    """One ``ONBOARDING_DIFFERENCE``: posted once, dated the cutover, by stage 14 (S07-R-07)."""

    subject_key: str
    role: str  # E-44 revenue relief role driven by a cumulative target
    cutover_date: date
    event_key: str
    imported: int  # minor units
    recomputed: int  # minor units
    amount: int  # recomputed − imported, minor units
    node_id: str  # onboarding_difference@<event key>:<ob>:-


@dataclass(frozen=True, slots=True)
class Row:
    """One ``obligations[]`` member of the payload, numbers as ``Fraction`` (CV-30)."""

    obligation_key: str
    values: Mapping[str, Fraction]
    raw: Mapping[str, object]

    def value(self, member: str) -> Fraction:
        """The member, 0 when absent."""
        return self.values.get(member, Fraction(0))

    def absent(self, members: Sequence[str]) -> frozenset[str]:
        """The optional members the payload omits (S07-R-07 rev 1.18: never read as 0)."""
        return frozenset(member for member in members if member not in self.values)

    def optional(self, member: str, mu: int) -> int | None:
        """The member rounded to minor units, None when the payload omits it (never read as 0:
        S07-R-07 rev 1.18, ``ONBOARDING_MEMBER_MISSING`` when stage 14 needs it)."""
        value = self.values.get(member)
        return None if value is None else money.round_half_up(value, mu)

    @property
    def x_exact(self) -> Fraction:
        """X_i = ``revenue_cum`` + ``remaining_allocation`` (S07-R-03)."""
        return self.value("revenue_cum") + self.value("remaining_allocation")


@dataclass(frozen=True, slots=True)
class Payload:
    """The parsed event payload and the malformed-row findings of S07-R-03."""

    reason: str
    cutover_date: date
    rows: Mapping[str, Row]  # obligation key -> row
    fair_value: Fraction | None  # fair_value_contract_liability (S07-R-08)
    findings: tuple[Finding, ...]


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"event_key": ev.event_key, **detail},
    )


def minor_unit(ctx: BookContext) -> int:
    """μ of the group's transaction currency (CV-33)."""
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the transaction currency is absent from the currency table",
            detail={"rule": "CV-30", "currency": ctx.txn_currency},
        )
    return spec.minor_unit


def _finding(ev: EventView, subject_key: str, check: str, **detail: str) -> Finding:
    return Finding(
        FINDING_CODE,
        "ERROR",
        subject_key,
        {"rule": "S07-R-03", "check": check, **detail},
        _STAGE,
        ev.event_key,
    )


def _number(value: object) -> Fraction | None:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        return None
    try:
        return money.to_fraction(value)
    except (ArithmeticError, ValueError):
        return None


def _effective(ev: EventView, reason: str, cutover: date, inception: date | None) -> bool:
    """S07-R-01 (rev 1.38): the event is effective on its cutover date, or on the contract's
    inception date when that is later — the contract then holds no history at the cutover and the
    event establishes nil opening state; an event before inception is S01-R-15's. A business
    combination has no such case: a contract that begins after the acquisition date is not an
    acquired contract (PT-11)."""
    if ev.effective_date == cutover:
        return True
    return (
        reason != BUSINESS_COMBINATION
        and inception is not None
        and cutover < inception == ev.effective_date
    )


def parse(ev: EventView, *, inception: date | None = None) -> Payload:
    """The payload of ``OPENING_BALANCE_ESTABLISHED`` (S07-R-01; 04 §16.3).

    A wrong event type, reason, cutover date or row key is a bundle-assembly error (CV-45). A row
    listed twice, or a member that is absent (when required) or not a number, is a finding.
    ``inception`` is the inception date of the event's contract, which alone admits an effective
    date after the cutover (``_effective``).
    """
    if ev.event_type != EVENT_TYPE:
        raise _invariant("stage 07 applies OPENING_BALANCE_ESTABLISHED only", ev, rule="S07-R-01")
    payload = ev.payload
    reason = payload.get("reason")
    if not isinstance(reason, str) or reason not in REASONS:
        raise _invariant("an opening balance carries an unknown reason", ev, rule="CV-45")
    cutover = payload.get("cutover_date")
    if isinstance(cutover, str):
        cutover = date.fromisoformat(cutover)
    if not isinstance(cutover, date) or not _effective(ev, reason, cutover, inception):
        raise _invariant("the cutover date is not the effective date", ev, rule="S07-R-01")
    raw_rows = payload.get("obligations")
    if not isinstance(raw_rows, list | tuple):
        raise _invariant("an opening balance carries no obligations", ev, rule="CV-45")
    rows: dict[str, Row] = {}
    findings: list[Finding] = []
    for item in raw_rows:
        key = item.get("obligation_key") if isinstance(item, Mapping) else None
        if not isinstance(item, Mapping) or not isinstance(key, str) or not key:
            raise _invariant("an opening balance row has no obligation key", ev, rule="CV-45")
        subject_key = f"{ev.contract_key}/{key}"
        if key in rows:
            findings.append(_finding(ev, subject_key, "duplicate_row", obligation_key=key))
            continue
        values: dict[str, Fraction] = {}
        for member in MEMBERS:
            number = _number(item.get(member)) if member in item else None
            if number is None:
                if member in item or member in REQUIRED:
                    findings.append(
                        _finding(ev, subject_key, "member", member=member, obligation_key=key)
                    )
                continue
            values[member] = number
        rows[key] = Row(key, MappingProxyType(values), MappingProxyType(dict(item)))
    fair_value: Fraction | None = None
    raw_fair_value = payload.get("fair_value_contract_liability")
    # The optional member (04 §16.3: O, only with BUSINESS_COMBINATION) is stored as ``null`` when
    # unset; that specific null is absence — never 0 (D-98 candidate 127, Codex 0533 F1). S07-R-08
    # still requires it for an IFRS15 business combination (``consistency``); a present non-null
    # value that is not a number stays a member finding; an explicit zero is the value 0.
    if raw_fair_value is not None:
        fair_value = _number(raw_fair_value)
        if fair_value is None:
            findings.append(
                _finding(ev, ev.contract_key, "member", member="fair_value_contract_liability")
            )
    return Payload(reason, cutover, MappingProxyType(rows), fair_value, tuple(findings))


def contract_obligations(st: AllocatedState, ev: EventView) -> tuple[ObligationState, ...]:
    """The obligations of the event's contract, in subject-key order."""
    return tuple(ob for ob in st.obligations if ob.contract_key == ev.contract_key)


def _in_force(st: AllocatedState, ob: ObligationState, ev: EventView) -> AllocationSegment | None:
    order_keys = {item.event_key: item.order_key for item in st.events}
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component != "FIXED" or seg.effective_date > ev.effective_date:
            continue
        if seg.event_key is not None:
            order_key = order_keys.get(seg.event_key)
            if order_key is None:
                raise _invariant("the boundary event of a segment is absent", ev, rule="CV-60")
            if order_key >= ev.order_key:
                continue
        found = seg
    return found


def required_in_force(st: AllocatedState, ob: ObligationState, ev: EventView) -> AllocationSegment:
    """The ``FIXED`` segment in force before ``ev`` in ENG-06 order (CV-60)."""
    seg = _in_force(st, ob, ev)
    if seg is None:
        raise _invariant(
            "an obligation has no allocation before the cutover",
            ev,
            rule="CV-60",
            obligation_key=ob.obligation_key,
        )
    return seg


def consistency(
    ctx: BookContext, st: AllocatedState, ev: EventView, payload: Payload
) -> tuple[Finding, ...]:
    """S07-R-03 over the contract; every failure is ``OPENING_BALANCE_INCONSISTENT`` (``ERROR``).

    X_i and ``revenue_cum`` share a sign or one is 0, |``revenue_cum``| ≤ |X_i| and
    ``remaining_quantity`` ≥ 0 per row; every booked obligation has exactly one row and every row a
    booked obligation; and Σ X_i equals the contract price, Σ a_posted in force, within 1e-4. An
    IFRS15 business combination needs ``fair_value_contract_liability`` (S07-R-08).
    """
    mu = minor_unit(ctx)
    findings = list(payload.findings)
    obligations = contract_obligations(st, ev)
    # S07-R-01 rev 1.18 (D-98 candidate 22): the cutover is a period end of every contracting
    # entity, so the deemed-posted baseline and the S07-R-07 differences hold pre-cutover history
    # only; a mid-period cutover fails closed (CV-15).
    for entity in sorted({ob.contracting_entity for ob in obligations}):
        calendar = ctx.entities.get(entity)
        if calendar is None:
            continue
        period = dates.period_of(calendar, payload.cutover_date)
        if period.end_date != payload.cutover_date:
            findings.append(
                Finding(
                    CUTOVER_CODE,
                    "ERROR",
                    ev.contract_key,
                    {
                        "cutover_date": payload.cutover_date.isoformat(),
                        "entity": entity,
                        "period_end": period.end_date.isoformat(),
                        "period_key": period.period_key,
                        "rule": "S07-R-01",
                    },
                    _STAGE,
                    ev.event_key,
                )
            )
    booked = {ob.obligation_key for ob in obligations}
    for ob in obligations:
        if ob.obligation_key not in payload.rows:
            findings.append(
                _finding(ev, ob.subject_key, "missing_row", obligation_key=ob.obligation_key)
            )
    for key in sorted(payload.rows):
        if key not in booked:
            findings.append(
                _finding(ev, f"{ev.contract_key}/{key}", "unknown_obligation", obligation_key=key)
            )
    complete = not findings
    total = Fraction(0)
    price = 0
    for ob in obligations:
        price += required_in_force(st, ob, ev).a_posted
        row = payload.rows.get(ob.obligation_key)
        if row is None:
            continue
        x_exact, revenue = row.x_exact, row.value("revenue_cum")
        total += x_exact
        key = ob.obligation_key
        if revenue * x_exact < 0:
            findings.append(_finding(ev, ob.subject_key, "sign", obligation_key=key))
        if abs(revenue) > abs(x_exact):
            findings.append(_finding(ev, ob.subject_key, "magnitude", obligation_key=key))
        if row.value("remaining_quantity") < 0:
            findings.append(_finding(ev, ob.subject_key, "remaining_quantity", obligation_key=key))
        if payload.cutover_date < ev.effective_date:
            # S07-R-01: the contract begins after the cutover, so it holds no history at it; a
            # row that carries any is the legacy database read past the cutover (fails closed)
            for member in CUMULATIVE:
                if row.value(member) != 0:
                    findings.append(
                        _finding(
                            ev,
                            ob.subject_key,
                            "history_before_inception",
                            member=member,
                            obligation_key=key,
                        )
                    )
    if complete and abs(total - Fraction(price, 10**mu)) > TOLERANCE:
        findings.append(
            _finding(
                ev,
                ev.contract_key,
                "transaction_price",
                allocations=money.format_exact(total),
                transaction_price=money.format_money(price, mu),
            )
        )
    ifrs = ctx.framework == "IFRS15"
    if payload.reason == BUSINESS_COMBINATION and ifrs and payload.fair_value is None:
        findings.append(_finding(ev, ev.contract_key, "fair_value"))
    return tuple(sorted(findings, key=Finding.sort_key))


def apportion(total: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
    """ALG-01 §2.1.2; nothing to apportion over zero weights gives zero shares."""
    if total == 0 and sum(weights, Fraction(0)) == 0:
        return [0] * len(keys)
    return money.largest_remainder(total, list(weights), list(keys))


def payload_ref(ev: EventView, obligation_key: str, member: str, value: Fraction) -> SourceRef:
    """A payload member of one row as a trace source (CV-53)."""
    detail = {
        "member": f"obligations[{obligation_key}].{member}",
        "value": money.format_exact(value),
    }
    return SourceRef("contract_event", ev.event_key, detail)


def opening_segment(
    st: AllocatedState,
    ob: ObligationState,
    previous: AllocationSegment,
    ev: EventView,
    row: Row,
    *,
    cutover: date,
    x_exact: Fraction,
    a_posted: int,
    base_exact: Fraction,
    base_posted: int,
) -> AllocationSegment:
    """The ``OPENING_BALANCE`` segment of S07-R-04 and S07-R-08. Its remaining term starts the day
    after ``cutover``, the date the imported cumulative amounts cover, which is the event's own
    date unless the contract begins after the cutover (S07-R-01)."""
    point = st.ledger.at(ob.subject_key, before=ev)
    quantity = row.value("remaining_quantity")
    remaining_ssp = row.value("remaining_ssp")
    measure = str(ob.recognition_method)
    return AllocationSegment(
        component="FIXED",
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=SegmentCause.OPENING_BALANCE,
        basis="PROSPECTIVE",
        x_exact=x_exact,
        a_posted=a_posted,
        base_revenue_posted=base_posted,
        base_revenue_exact=base_exact,
        base_progress=ProgressBase(
            point.delivered_cum - point.returned_cum,
            point.costs_cum,
            point.hours_cum,
            ev.effective_date,
        ),
        totals=ProgressTotals(
            quantity,
            previous.totals.eac_element_code,
            cutover + timedelta(days=1),
            previous.totals.end_date or ob.end_date,
        ),
        progress_measure="UNITS_SINCE_BOUNDARY" if measure == "UNITS_DELIVERED" else measure,
        unit_ssp=Fraction(0) if quantity == 0 else remaining_ssp / quantity,
        remaining_ssp=remaining_ssp,
        remaining_billing_plan=row.value("remaining_billing"),
        estimate_pair=(None, None),
        modification_boundary_no=previous.modification_boundary_no,
    )


def view(
    row: Row,
    payload: Payload,
    ev: EventView,
    baseline: OpeningBaseline,
    differences: tuple[OnboardingDifference, ...],
    *,
    measurement: str | None = None,
) -> Mapping[str, object]:
    """``ObligationState.opening``: the row values, the event members, baseline and differences."""
    values: dict[str, object] = dict(row.raw)
    values.update(
        {
            "baseline": baseline,
            "cutover_date": payload.cutover_date,
            "differences": differences,
            "event_key": ev.event_key,
            "reason": payload.reason,
        }
    )
    if measurement is not None:
        values["measurement"] = measurement
    return MappingProxyType(values)


def baseline_of(ob: ObligationState) -> OpeningBaseline | None:
    """The opening baseline stage 07 recorded for the obligation, if any (S07-R-05)."""
    value = None if ob.opening is None else ob.opening.get("baseline")
    return value if isinstance(value, OpeningBaseline) else None


def differences_of(ob: ObligationState) -> tuple[OnboardingDifference, ...]:
    """The onboarding differences recorded for the obligation (S07-R-07; S07-INV-03)."""
    value = None if ob.opening is None else ob.opening.get("differences")
    if not isinstance(value, tuple):
        return ()
    return tuple(item for item in value if isinstance(item, OnboardingDifference))


def establish(
    ctx: BookContext, st: AllocatedState, ev: EventView, payload: Payload, tb: TraceBuilder
) -> AllocatedState:
    """S07-R-04 and S07-R-05 under ``OPENING_BALANCES_AT_CUTOVER``.

    ``a_posted`` = ``largest_remainder``(TP_c, [X_j], keys) over the contract, with TP_c the posted
    allocations in force before the event; C_0 = ``cumulative_posted``(X_i, A_i, revenue_cum ÷ X_i).
    """
    mu = minor_unit(ctx)
    cutover = payload.cutover_date.isoformat()
    obligations = contract_obligations(st, ev)
    previous = {ob.subject_key: required_in_force(st, ob, ev) for ob in obligations}
    price = sum(seg.a_posted for seg in previous.values())
    keys = [ob.subject_key for ob in obligations]
    weights = [payload.rows[ob.obligation_key].x_exact for ob in obligations]
    shares = apportion(price, weights, keys)
    if sum(shares) != price:
        raise _invariant(
            "the opening allocations do not sum to the price", ev, invariant="S07-INV-02"
        )
    common = {
        "cutover_date": cutover,
        "keys": SEPARATOR.join(keys),
        "tp_posted": str(price),
        "weights": SEPARATOR.join(rational_param(weight) for weight in weights),
    }
    replaced: dict[str, ObligationState] = {}
    for ob, x_exact, a_posted in zip(obligations, weights, shares, strict=True):
        row = payload.rows[ob.obligation_key]
        revenue = row.value("revenue_cum")
        c_0 = (
            0 if x_exact == 0 else money.cumulative_posted(x_exact, a_posted, revenue / x_exact, mu)
        )
        revenue_ref = payload_ref(ev, ob.obligation_key, "revenue_cum", revenue)
        remaining_ref = payload_ref(
            ev, ob.obligation_key, "remaining_allocation", row.value("remaining_allocation")
        )
        tb.node(
            measure=f"opening_allocation@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=a_posted,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=SEGMENT_FORMULA,
            inputs=[revenue_ref, remaining_ref],
            params={**common, "key": ob.subject_key},
            exact=x_exact,
            narrative_key=SEGMENT_FORMULA.rsplit(".v", 1)[0],
        )
        node_id = tb.node(
            measure=f"opening_revenue_cum@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=c_0,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=BASELINE_FORMULA,
            inputs=[revenue_ref],
            params={
                "a_posted": str(a_posted),
                "cutover_date": cutover,
                "mode": "cutover",
                "x_exact": rational_param(x_exact),
            },
            exact=revenue,
            narrative_key=BASELINE_FORMULA.rsplit(".v", 1)[0],
        )
        seg = opening_segment(
            st,
            ob,
            previous[ob.subject_key],
            ev,
            row,
            cutover=payload.cutover_date,
            x_exact=x_exact,
            a_posted=a_posted,
            base_exact=revenue,
            base_posted=c_0,
        )
        baseline = OpeningBaseline(
            subject_key=ob.subject_key,
            cutover_date=payload.cutover_date,
            revenue_cum=c_0,
            billed_cum=money.round_half_up(row.value("billed_cum"), mu),
            deposit_liability=row.optional("deposit_liability", mu),
            pre_standard_revenue_cum=money.round_half_up(row.value("pre_standard_revenue_cum"), mu),
            method=OPENING_BALANCES,
            node_id=node_id,
            absent_members=row.absent(OPTIONAL_MEMBERS),
        )
        replaced[ob.subject_key] = replace(
            ob,
            segments=(*ob.segments, seg),
            opening=view(row, payload, ev, baseline, differences_of(ob)),
        )
    return replace(st, obligations=tuple(replaced.get(ob.subject_key, ob) for ob in st.obligations))
