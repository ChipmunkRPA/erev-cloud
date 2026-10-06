"""Stage 09 recognition components and cumulative targets (ENGINE_SPEC_B §9.2; ENC-1 to ENC-9).

An obligation's posted revenue target is the sum of its component targets (S09-R-01 to S09-R-03):
``FIXED`` over its allocation segments by the obligation's measure (CV-60 to CV-63), and
``PERIOD_VC`` as realised usage amounts with X = A = the amount and f = 1 (S09-R-02, S09-R-19).
Event-driven measures (``POINT_IN_TIME``, ``UNITS_DELIVERED``, ``OUTPUT_PERCENT``, ``MILESTONE``)
come from ``progress_events`` (ENC-3, ENC-4), input measures (``COST_TO_COST``, ``LABOUR_HOURS``,
``COST_RECOVERY``, with zero-margin uninstalled materials) from ``progress_inputs`` (ENC-5), and
returns within the units measures from ``returns`` (ENC-7). ``Evaluator`` applies S09-R-41 in
order: segment targets, manual adjustments in ENG-06 order (``manual``), recognition holds
(``holds``), then the V4 status guard; the V5 start
applies with the guard (S02-R-03, S02-R-05, S09-INV-05, S09-INV-06). Targets are evaluated at every
period end of the performing entity from the group's inception period through the horizon, and a
deterministic component (``is_deterministic``) through the period containing its term end (C-04,
C-05; S09-R-50). Each period amount
is decomposed by cause (``decompose``). A ``LEASE`` repurchase outcome produces no targets
(S09-R-13). ``REDEMPTION_PATTERN`` obligations and loyalty-point options measure their ``FIXED``
component by the entitlement progress of ``breakage`` (§9.2.8; ENC-8), a ``ROYALTY``-method
licence measures its guarantee on the licence pattern (S09-R-33), and the ``ROYALTY`` component
adds the realised royalties of ``royalty`` (§9.2.9). The unbuilt measures fail closed with
``ENGINE_INVARIANT_VIOLATED`` rather than return partial output (C-09). Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates, money, progress, usage
from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s09_recognition import (
    breakage,
    decompose,
    holds,
    manual,
    progress_events,
    progress_inputs,
    progress_time,
    returns,
    royalty,
    step1,
)
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.s09_recognition.progress_time import Progress
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EventView,
    Finding,
    ObligationState,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "COMPONENTS",
    "OVER_TIME_CRITERIA",
    "RECOGNISING_STATUSES",
    "Evaluation",
    "Evaluator",
    "FixedPart",
    "RealisedAmount",
    "StageTargets",
    "active_segment",
    "emit_target",
    "evaluate",
    "evaluation_periods",
    "is_deterministic",
    "minor_unit",
    "period_vc_realised",
    "revenue_targets",
    "segment_target",
    "status_guard",
    "target_at",
    "validate",
]

COMPONENTS: Final = ("FIXED", "PERIOD_VC", "ROYALTY")  # §9.2.1, §0.3 `#<component code>`
OVER_TIME_CRITERIA: Final = frozenset({"OT_A", "OT_B", "OT_C"})  # 04 E-20; 606-10-25-27
POINT_IN_TIME_METHODS: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED", "MANUAL"})  # T-REF-23
RECOGNISING_STATUSES: Final = frozenset({"ACTIVE", "COMPLETED", "TERMINATED"})  # S02-INV-01
REVENUE_CUM_FORMULA: Final = "rec.revenue_cum.v1"
INCEPTION_EXACT_FORMULA: Final = "rec.target_exact.inception.v1"
PROSPECTIVE_EXACT_FORMULA: Final = "rec.target_exact.prospective.v1"
_STAGE: Final = 9


@dataclass(frozen=True, slots=True)
class FixedPart:
    """The ``FIXED`` component at a date: segment in force, progress, E and posted C (CV-63)."""

    segment: AllocationSegment
    progress: Progress
    exact: Fraction  # E, currency units
    posted: int  # C, minor units
    complete: bool  # φ = 1, so C = A
    returns: returns.ReturnTarget | None = None  # ALG-06 target of a units obligation (S09-R-23)
    # Uninstalled materials of a cost-to-cost target (S09-R-14): E = f × (X − UM_exp) + UM_inc
    materials: progress_inputs.Materials | None = None
    findings: tuple[Finding, ...] = ()  # NON_FINITE_AMOUNT of an input measure (§9.4)
    redemption: breakage.RedemptionTarget | None = None  # §9.2.8 measurement (S09-R-27)


@dataclass(frozen=True, slots=True)
class RealisedAmount:
    """A realised ``PERIOD_VC`` amount: X = A = the amount (S09-R-02)."""

    event_key: str
    amount: int  # minor units


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The posted obligation target at one date, with its parts and guard (S09-R-03, S09-R-41)."""

    subject_key: str
    as_of: date  # the evaluation date; the freeze date under S02-R-05
    guard: str | None  # "V4:<E-17 status>", "V5" or "S09-R-13:LEASE" when the target is 0
    fixed: FixedPart | None
    realised: tuple[RealisedAmount, ...]
    findings: tuple[Finding, ...]
    value: int  # posted target after S09-R-41, minor units
    exact: Fraction  # Σ E_c of the segment targets, currency units
    segments_value: int = 0  # C_p = Σ_c C_c before manual adjustments and holds
    adjustments: tuple[manual.Applied, ...] = ()
    hold: holds.Frozen | None = None
    # S02-R-04 (rev 1.6; D-91 gaps (v)): (the target before netting, R25_p) when the contract's
    # 606-10-25-7 revenue attributed to the obligation nets the STEP1_MET target.
    netting: tuple[int, int] | None = None
    royalty: royalty.RoyaltyPart | None = None  # the ROYALTY component (§9.2.9)

    @property
    def adjusted(self) -> bool:
        """A manual adjustment, a hold or the S02-R-04 netting changed the segment target."""
        return self.guard is None and (
            bool(self.adjustments) or self.hold is not None or self.netting is not None
        )


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def minor_unit(ctx: BookContext) -> int:
    """μ of the group's transaction currency (C-01)."""
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the transaction currency is absent from the currency table",
            detail={"rule": "CV-30", "currency": ctx.txn_currency},
        )
    return spec.minor_unit


def validate(ob: ObligationState) -> None:
    """CV-45 checks of the obligation terms stage 09 relies on (REQ-REC-002; T-REF-23; CV-60)."""
    pattern = str(ob.satisfaction_pattern)
    criterion = ob.over_time_criterion
    method = str(ob.recognition_method)
    if pattern == "OVER_TIME" and criterion not in OVER_TIME_CRITERIA:
        raise _invariant(
            "an over-time obligation needs a 606-10-25-27 criterion",
            ob,
            rule="REQ-REC-002",
            over_time_criterion=criterion,
        )
    if pattern == "POINT_IN_TIME":
        if criterion != "NOT_APPLICABLE":
            raise _invariant(
                "a point-in-time obligation carries an over-time criterion",
                ob,
                rule="REQ-REC-002",
                over_time_criterion=criterion,
            )
        # A ROYALTY-method licence of functional IP: the guarantee follows the point-in-time
        # licence pattern and the royalties their own component (S09-R-33; POL-024).
        royalty_licence = method == "ROYALTY" and str(ob.obligation_kind) == "LICENCE"
        if method not in POINT_IN_TIME_METHODS and not royalty_licence:
            raise _invariant(
                "a point-in-time obligation uses an over-time measure",
                ob,
                rule="T-REF-23",
                recognition_method=method,
            )
    for seg in ob.segments:
        if seg.component not in COMPONENTS:
            raise _invariant("unknown recognition component", ob, rule="S09-R-01")
    effective = [seg.effective_date for seg in ob.segments]
    if effective != sorted(effective):
        raise _invariant("allocation segments are not in effective-date order", ob, rule="CV-60")


def active_segment(
    ob: ObligationState,
    component: str,
    d: date,
    *,
    st: AllocatedState | None = None,
    position: Position | None = None,
) -> AllocationSegment | None:
    """The last segment of ``component`` effective on or before ``d`` (CV-60; S09-R-04).

    With a ``position`` a segment counts only when its boundary event precedes it in ENG-06 order,
    so an event on the boundary date with a lower position is measured in the previous segment.
    Before an ``OPENING_BALANCE`` segment is in force, that segment applies with progress 0, so
    every target up to the cutover equals the imported baseline (S09-R-07; S07-INV-01).
    """
    found: tuple[int, AllocationSegment] | None = None
    opening: tuple[int, AllocationSegment] | None = None
    for index, seg in enumerate(ob.segments):
        if seg.component != component:
            continue
        if opening is None and seg.cause == SegmentCause.OPENING_BALANCE:
            opening = (index, seg)
        if seg.effective_date > d:
            continue
        if position is not None and seg.event_key is not None:
            if st is None:
                raise ValueError("a position needs the state that orders boundary events")
            if not position.admits(progress_events.boundary_key(st, ob, seg)):
                continue
        found = (index, seg)
    if opening is not None and (found is None or found[0] < opening[0]):
        return opening[1]
    return None if found is None else found[1]


def status_guard(ctx: BookContext, contract: ContractView, d: date) -> tuple[str | None, date]:
    """(guard, as_of) of the V4 guard at ``d`` (S02-R-03, S02-R-05; S02-INV-01; S09-INV-05).

    Revenue is recognised while the book status is ``ACTIVE``, ``COMPLETED`` or ``TERMINATED``.
    After a recognising status turns ``NOT_A_CONTRACT``, the target stays frozen at C of the
    transition date (S02-R-05). Every other interval gives 0.
    """
    history = contract.status_in_book.get(str(ctx.book_code))
    if history is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the contract carries no status for the book",
            subject_key=contract.header.external_id,
            detail={"rule": "S02-R-03", "book_code": str(ctx.book_code)},
        )
    current: str | None = None
    frozen_at: date | None = None
    for when, status in history:
        if when > d:
            break
        if status == "NOT_A_CONTRACT" and current in RECOGNISING_STATUSES:
            frozen_at = when
        elif status != "NOT_A_CONTRACT":
            frozen_at = None
        current = status
    if current in RECOGNISING_STATUSES:
        return None, d
    if current == "NOT_A_CONTRACT" and frozen_at is not None:
        return None, frozen_at
    return f"V4:{current or 'NONE'}", d


def segment_target(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    custodial_start: date | None = None,
    position: Position | None = None,
) -> FixedPart:
    """``fixed_target`` of §9.2.2 for one segment at ``d``: E per CV-63 and C by ALG-01 §2.1.3.

    A units obligation with returns follows ALG-06 instead (S09-R-23 to S09-R-25): E comes from
    ``returns.target`` and C = ``cumulative_posted``(X, A, E ÷ X).
    """
    method = str(ob.recognition_method)
    prog: Progress
    redemption: breakage.RedemptionTarget | None = None
    materials: progress_inputs.Materials | None = None
    findings: tuple[Finding, ...] = ()
    if breakage.applies(ob):
        # §9.2.8: the entitlement progress E_total ÷ X of the redemption pattern (S09-R-27).
        redemption = breakage.target(ctx, st, contract, ob, seg, d, position=position)
        prog = redemption.progress
    elif method == "TIME_ELAPSED":
        prog = progress_time.progress(ctx, ob, seg, d, custodial_start=custodial_start)
    elif method == "ROYALTY":
        # S09-R-33: the guarantee (the FIXED component) follows the licence pattern, point in
        # time for a right to use and time elapsed for a right to access (POL-024, stage 03).
        if str(ob.satisfaction_pattern) == "POINT_IN_TIME":
            prog = progress_events.progress(
                ctx, st, contract, ob, seg, d, position=position, method="POINT_IN_TIME"
            )
        else:
            prog = progress_time.progress(ctx, ob, seg, d, custodial_start=custodial_start)
    elif method in progress_events.EVENT_FORMULAS:
        prog = progress_events.progress(ctx, st, contract, ob, seg, d, position=position)
        returns_target = returns.target(ctx, st, contract, ob, seg, d, position=position)
        if returns_target is not None:
            return _returns_part(ctx, ob, seg, prog, returns_target)
    elif method in progress_inputs.INPUT_METHODS:
        measured = progress_inputs.progress(st, ob, seg, d, position=position)
        prog, materials, findings = measured.progress, measured.materials, measured.findings
    elif method == usage.RIGHT_TO_INVOICE and ob.stated_price == 0:
        # ENC6-R3 (S09-R-18 / §9.2.4 rev 1.22): a D-87 rate line (P = 0, X = 0) carries no revenue
        # on FIXED; its progress is time elapsed over the service term — the S09-R-46 completion
        # signal — never the f = 1 convention of an empty denominator. No end date: never complete.
        prog = _open_term_or_time(ctx, ob, seg, d, custodial_start=custodial_start)
    elif method == usage.RIGHT_TO_INVOICE:
        # ENC-6 (S09-R-18 rev 1.20; D-98 candidate 28): the FIXED component is the line's stated
        # price P and the right to invoice R is its output measure of progress, f = min(1, R ÷ P);
        # R above P rides the PERIOD_VC component (S09-R-01, S04-R-06).
        prog = _right_to_invoice_progress(st, contract, ob, seg, d, position=position)
    elif method in usage.REALISED_METHODS:
        # ENC-6 (S09-R-19, S09-R-20): the FIXED component of a usage obligation is its stand-ready
        # fee or minimum (0 in the corpus keys), measured by time elapsed; the DERIVED fees ride the
        # PERIOD_VC component (S09-R-01).
        prog = progress_time.progress(ctx, ob, seg, d, custodial_start=custodial_start)
    else:
        raise _invariant(
            "the measure of progress is not built", ob, rule="S09-R-02", recognition_method=method
        )
    if seg.basis not in ("INCEPTION", "PROSPECTIVE"):
        raise _invariant("unknown segment basis", ob, rule="CV-60", basis=seg.basis)
    exact = _exact_target(seg, prog.value, materials)
    if seg.x_exact == 0:
        if seg.a_posted != 0:
            raise _invariant(
                "a zero exact allocation carries a posted allocation", ob, rule="CV-63"
            )
        return FixedPart(
            seg, prog, exact, 0, prog.value == 1, None, materials, findings, redemption
        )
    complete_by_progress = prog.value == 1 and materials is None
    ratio = Fraction(1) if complete_by_progress else exact / seg.x_exact
    if not 0 <= ratio <= 1:
        raise _invariant("the exact target lies outside the allocation", ob, rule="CV-63")
    posted = money.cumulative_posted(seg.x_exact, seg.a_posted, ratio, minor_unit(ctx))
    return FixedPart(seg, prog, exact, posted, ratio == 1, None, materials, findings, redemption)


def is_deterministic(ob: ObligationState) -> bool:
    """Whether time alone places the amounts of the obligation's ``FIXED`` component: the one
    predicate of S09-R-45 (rev 1.126; supervisor ruling R-116 (a)).

    The component is measured by time elapsed and carries an allocation. A ``TIME_ELAPSED``
    obligation is deterministic by its method. A ``USAGE`` obligation — its stand-ready fee or
    minimum (S09-R-19, S09-R-20) — and a ``ROYALTY`` obligation whose licence is not point in time
    — its guarantee (S09-R-33) — are when a ``FIXED`` segment holds an exact or a posted allocation
    other than 0: the methods whose ``FIXED`` progress ``segment_target`` takes from
    ``progress_time``. A ``RIGHT_TO_INVOICE`` obligation never is (its ``FIXED`` component is
    measured by the right to invoice, S09-R-18; a rate line by the completion signal of its term),
    and neither is a ``USAGE`` or ``ROYALTY`` obligation measured by its redemption pattern
    (§9.2.8). For ``TIME_ELAPSED`` the method alone decides, as before rev 1.126.

    Read at three places: the scheduled amount and ``is_released_at_close`` (``schedule``;
    S09-R-45, S09-R-49), the projection to the term end (``evaluation_periods``; S09-R-50) and the
    current part of a contract liability (stage 10; S10-R-24). The release of a loss provision
    (stage 11; S11-R-17) does not read it: it asks the method of every unit obligation, because its
    question is the whole of a unit's remaining revenue.
    """
    method = str(ob.recognition_method)
    if method == "TIME_ELAPSED":
        return True
    if breakage.applies(ob):
        return False
    by_time = method == usage.USAGE or (
        method == "ROYALTY" and str(ob.satisfaction_pattern) != "POINT_IN_TIME"
    )
    return by_time and any(
        seg.component == "FIXED" and (seg.x_exact != 0 or seg.a_posted != 0) for seg in ob.segments
    )


def _exact_target(
    seg: AllocationSegment, f: Fraction, materials: progress_inputs.Materials | None
) -> Fraction:
    """E of §9.2.2 (CV-63), or with uninstalled materials E = f × (X − UM_exp) + UM_inc and, since
    a boundary, b_k + g × (X − b_k − (UM_exp − UM_k)) + (UM_inc − UM_k) (S09-R-14; D-76)."""
    if seg.basis == "INCEPTION":
        if materials is None:
            return seg.x_exact * f
        return f * (seg.x_exact - materials.expected) + materials.incurred
    base = seg.base_revenue_exact
    if materials is None:
        return base + (seg.x_exact - base) * f
    remaining = seg.x_exact - base - (materials.expected - materials.base_incurred)
    return base + f * remaining + (materials.incurred - materials.base_incurred)


def _returns_part(
    ctx: BookContext,
    ob: ObligationState,
    seg: AllocationSegment,
    prog: Progress,
    returns_target: returns.ReturnTarget,
) -> FixedPart:
    exact = returns_target.exact
    if seg.x_exact == 0:
        if seg.a_posted != 0 or exact != 0:
            raise _invariant("a zero exact allocation carries a returns target", ob, rule="CV-63")
        return FixedPart(seg, prog, exact, 0, True, returns_target)
    ratio = exact / seg.x_exact
    if not 0 <= ratio <= 1:
        raise _invariant("the returns target lies outside the allocation", ob, rule="S09-R-23")
    posted = money.cumulative_posted(seg.x_exact, seg.a_posted, ratio, minor_unit(ctx))
    return FixedPart(seg, prog, exact, posted, ratio == 1, returns_target)


def _payload_date(value: object, ob: ObligationState, event_key: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise _invariant("a payload date is malformed", ob, rule="CV-45", event_key=event_key)


def _payload_number(value: object, ob: ObligationState, event_key: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        raise _invariant("a payload amount is malformed", ob, rule="CV-45", event_key=event_key)
    return money.to_fraction(value)


def period_vc_realised(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    d: date,
    *,
    position: Position | None = None,
) -> tuple[tuple[RealisedAmount, ...], tuple[Finding, ...]]:
    """Realised ``PERIOD_VC`` amounts at ``d`` (S09-R-18, S09-R-19; S04-R-06; ENC-6).

    A ``RIGHT_TO_INVOICE`` obligation follows the S09-R-18 source order as completed by D-87
    L6-5-Q-16 (``erev_engine.usage.right_to_invoice``); a ``USAGE`` obligation counts its rated
    non-royalty ``USAGE_REPORTED`` events at the end of their usage period
    (``erev_engine.usage.derived_usage``) — the one source rule stage 04 prices (DG-ENG-07). A
    usage event without ``rated_amount`` raises the finding ``NON_FINITE_AMOUNT`` (§9.4) and
    contributes nothing.
    """

    def admits(ev: EventView) -> bool:
        return progress_events.admitted(ev, d, position)

    if str(ob.recognition_method) == usage.RIGHT_TO_INVOICE:
        realisation = usage.right_to_invoice(
            st.measure_events,
            contract_key=ob.contract_key,
            obligation_key=ob.obligation_key,
            subject_key=ob.subject_key,
            booking=_contract_of(st, ob).booking,
            at=d,
            admits=admits,
        )
        # S09-R-18 rev 1.20 / S04-R-06 rev 1.21: only the right to invoice above the stated price
        # P is a PERIOD_VC amount; up to P it is the FIXED component's progress (D-98 candidate 28).
        above = usage.above_stated(realisation.items, ob.stated_price)
        return _realised_amounts(ctx, ob, replace(realisation, items=above), rule="S09-R-18")
    realisation = usage.derived_usage(
        st.measure_events,
        contract_key=ob.contract_key,
        obligation_key=ob.obligation_key,
        subject_key=ob.subject_key,
        at=d,
        admits=admits,
    )
    return _realised_amounts(ctx, ob, realisation, rule="S09-R-19")


def _realised_amounts(
    ctx: BookContext, ob: ObligationState, realisation: usage.RtiRealisation, *, rule: str
) -> tuple[tuple[RealisedAmount, ...], tuple[Finding, ...]]:
    """Each realised item as an X = A amount in minor units (S09-R-02); an unrated usage event is
    a ``NON_FINITE_AMOUNT`` finding under ``rule`` (§9.4) and contributes nothing."""
    scale: int = 10 ** minor_unit(ctx)
    realised: list[RealisedAmount] = []
    for item in realisation.items:
        scaled = item.amount * scale
        if scaled.denominator != 1:
            raise _invariant(
                "a realised amount has more places than the currency",
                ob,
                rule="CV-45",
                event_key=item.event_key,
                source=realisation.source,
            )
        realised.append(RealisedAmount(item.event_key, scaled.numerator))
    findings = tuple(
        Finding(
            "NON_FINITE_AMOUNT",
            "ERROR",
            ob.subject_key,
            {"reason": "USAGE_RATED_AMOUNT_MISSING", "rule": rule},
            _STAGE,
            event_key,
        )
        for event_key in realisation.unrated
    )
    return tuple(realised), findings


RTI_FORMULA: Final = "rec.progress.right_to_invoice.v1"


def _right_to_invoice_at(
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    at: date,
    admits: Callable[[EventView], bool],
) -> Fraction:
    """R: the right to invoice for performance to ``at`` over the admitted events (S09-R-18)."""
    return usage.right_to_invoice(
        st.measure_events,
        contract_key=ob.contract_key,
        obligation_key=ob.obligation_key,
        subject_key=ob.subject_key,
        booking=contract.booking,
        at=at,
        admits=admits,
    ).amount


def _open_term_or_time(
    ctx: BookContext,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    custodial_start: date | None,
) -> Progress:
    """The completion signal of a zero `RIGHT_TO_INVOICE` FIXED component (ENC6-R3): time elapsed
    over [start, end]; without an end date the line never completes (f = 0, ``OPEN_TERM``)."""
    end = seg.totals.end_date or ob.end_date
    start = seg.totals.start_date or ob.start_date
    if start is None or end is None:
        params = {
            "as_of": d.isoformat(),
            "realised": "0",
            "reason": "OPEN_TERM",
            "stated": rational_param(ob.stated_price),
        }
        return Progress(Fraction(0), RTI_FORMULA, MappingProxyType(params))
    return progress_time.progress(ctx, ob, seg, d, custodial_start=custodial_start)


def _right_to_invoice_progress(
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None,
) -> Progress:
    """S09-R-18 rev 1.20 (D-98 candidate 28): f = min(1, R ÷ P) with P the obligation's stated
    price, or g = min(1, (R − R_k) ÷ (P − R_k)) since the segment's boundary event, R_k the right
    to invoice before it (ENG-06 order; §9.2.4). Params reproduce the value (S09-INV-10)."""
    realised = _right_to_invoice_at(
        st, contract, ob, d, lambda ev: progress_events.admitted(ev, d, position)
    )
    params = {
        "as_of": d.isoformat(),
        "realised": rational_param(realised),
        "stated": rational_param(ob.stated_price),
    }
    base = Fraction(0)
    if seg.basis == "PROSPECTIVE" and seg.event_key is not None:
        boundary = next((ev for ev in st.events if ev.event_key == seg.event_key), None)
        if boundary is None:
            raise _invariant("the boundary event of a segment is absent", ob, rule="CV-60")
        base = _right_to_invoice_at(
            st, contract, ob, boundary.effective_date, lambda ev: ev.order_key < boundary.order_key
        )
        params["base_realised"] = rational_param(base)
    value = progress.right_to_invoice_fraction(realised, ob.stated_price, base)
    return Progress(value, RTI_FORMULA, MappingProxyType(dict(sorted(params.items()))))


def _contract_of(st: AllocatedState, ob: ObligationState) -> ContractView:
    for view in st.contracts:
        if view.header.external_id == ob.contract_key:
            return view
    raise _invariant("the obligation's contract is absent from the state", ob, rule="CV-45")


def _custodial_start(
    ctx: BookContext, st: AllocatedState, contract: ContractView, ob: ObligationState
) -> date | None:
    if str(ob.obligation_kind) != "CUSTODIAL":
        return None
    return progress_events.first_bill_and_hold_transfer(ctx, st, contract)


class Evaluator:
    """Posted targets of one obligation at any date and ENG-06 position (S09-R-41).

    Segment targets (§9.2.2 to §9.2.7), then manual adjustments in ENG-06 order (§9.2.11), then
    recognition holds (§9.2.12), then the V4 status guard. Results are memoised per date and
    position, because the manual rules and the hold level read targets at other dates.
    """

    def __init__(
        self,
        ctx: BookContext,
        st: AllocatedState,
        ob: ObligationState,
        contract: ContractView | None = None,
        attribution: step1.Attribution | None = None,
    ) -> None:
        validate(ob)
        entity = ctx.entities.get(ob.performing_entity)
        if entity is None:
            raise _invariant("the performing entity has no calendar", ob, rule="CV-12")
        self.ctx = ctx
        self.st = st
        self.ob = ob
        self.contract = _contract_of(st, ob) if contract is None else contract
        # S14-R-25 attribution of the contract's 25-7 revenue, resolved once per state so every
        # evaluator of the book nets the same shares (S02-R-04; D-91 gaps (v)).
        self.attribution = (
            step1.attributions(st).get(ob.contract_key) if attribution is None else attribution
        )
        self.custodial_start = _custodial_start(ctx, st, self.contract, ob)
        self.mu = minor_unit(ctx)
        self.periods: tuple[PeriodInput, ...] = tuple(
            sorted(entity.periods, key=lambda period: (period.start_date, period.end_date))
        )
        self.adjustments = manual.adjustments(ctx, st, ob)
        self._segments: dict[tuple[date, Position | None], Evaluation] = {}
        self._adjusted: dict[
            tuple[date, Position | None, int], tuple[int, tuple[manual.Applied, ...]]
        ] = {}

    def segments(self, d: date, position: Position | None = None) -> Evaluation:
        """C_p(d) = Σ_c C_c(d) after the V5 start and the V4 status guard (S09-R-03)."""
        key = (d, position)
        cached = self._segments.get(key)
        if cached is None:
            cached = self._evaluate_segments(d, position)
            self._segments[key] = cached
        return cached

    def segment_value(self, d: date, position: Position | None = None) -> int:
        """The segment target at ``d`` and ``position``, minor units."""
        return self.segments(d, position).value

    def segment_exact(self, d: date, position: Position | None = None) -> Fraction:
        """The exact segment target Σ E_c at ``d`` and ``position``, currency units."""
        return self.segments(d, position).exact

    def posted_value(self, d: date, position: Position | None = None) -> int:
        """The posted target after S09-R-41 at ``d`` and ``position``, minor units."""
        return self.posted(d, position).value

    def _evaluate_segments(self, d: date, position: Position | None) -> Evaluation:
        ctx, st, contract, ob = self.ctx, self.st, self.contract, self.ob
        guard, as_of = status_guard(ctx, contract, d)
        if (
            guard is None
            and ob.recognition_start_date is not None
            and as_of < ob.recognition_start_date
        ):
            guard = "V5"
        if guard is None and progress_events.repurchase_outcome(ctx, contract, ob) == "LEASE":
            guard = "S09-R-13:LEASE"
        if guard is not None:
            return Evaluation(ob.subject_key, as_of, guard, None, (), (), 0, Fraction(0))
        fixed: FixedPart | None = None
        findings: tuple[Finding, ...] = ()
        seg = active_segment(ob, "FIXED", as_of, st=st, position=position)
        if seg is not None:
            fixed = segment_target(
                ctx,
                st,
                contract,
                ob,
                seg,
                as_of,
                custodial_start=self.custodial_start,
                position=position,
            )
            if position is None:
                findings = progress_events.trigger_findings(ctx, st, contract, ob, as_of)
                findings += fixed.findings  # NON_FINITE_AMOUNT of an input measure (§9.4)
                if fixed.redemption is not None:
                    findings += fixed.redemption.findings
        realised: tuple[RealisedAmount, ...] = ()
        if active_segment(ob, "PERIOD_VC", as_of, st=st, position=position) is not None:
            realised, usage_findings = period_vc_realised(ctx, st, ob, as_of, position=position)
            if position is None:
                findings += usage_findings
        royalties: royalty.RoyaltyPart | None = None
        if active_segment(ob, "ROYALTY", as_of, st=st, position=position) is not None:
            # §9.2.9: realised royalties, recognised once the licence is satisfied (S09-R-33).
            satisfied = fixed is not None and fixed.progress.value > 0
            royalties = royalty.target(
                ctx, st, ob, as_of, satisfied=satisfied, position=position, mu=self.mu
            )
        realised_minor = sum(item.amount for item in realised)
        recognised = 0 if royalties is None else royalties.recognised
        value = realised_minor + recognised + (0 if fixed is None else fixed.posted)
        exact = Fraction(realised_minor + recognised, 10**self.mu) + (
            Fraction(0) if fixed is None else fixed.exact
        )
        return Evaluation(
            ob.subject_key,
            as_of,
            None,
            fixed,
            realised,
            findings,
            value,
            exact,
            value,
            royalty=royalties,
        )

    @staticmethod
    def _allocation(ev: Evaluation) -> int:
        realised = sum(item.amount for item in ev.realised)
        realised += 0 if ev.royalty is None else ev.royalty.realised
        return realised + (0 if ev.fixed is None else ev.fixed.segment.a_posted)

    def adjusted(
        self, d: date, position: Position | None = None, count: int | None = None
    ) -> tuple[int, tuple[manual.Applied, ...]]:
        """The target after the first ``count`` manual adjustments (all by default), S09-R-41."""
        limit = len(self.adjustments) if count is None else count
        key = (d, position, limit)
        cached = self._adjusted.get(key)
        if cached is not None:
            return cached
        seg_ev = self.segments(d, position)
        result: tuple[int, tuple[manual.Applied, ...]] = (seg_ev.value, ())
        if seg_ev.guard is None:
            value = seg_ev.value
            applied: list[manual.Applied] = []
            for index, adj in enumerate(self.adjustments[:limit]):
                if not progress_events.admitted(adj.event, seg_ev.as_of, position):
                    continue
                spec = self._adjustment(index, adj, seg_ev)
                if spec is None:
                    continue
                formula_id, params = spec
                value = manual.evaluate(self.ob, formula_id, value, params, self.mu)
                applied.append(manual.Applied(adj, formula_id, params, value))
            result = (value, tuple(applied))
        self._adjusted[key] = result
        return result

    def _adjustment(
        self, index: int, adj: manual.Adjustment, seg_ev: Evaluation
    ) -> tuple[str, Mapping[str, str]] | None:
        d, ob, mu = seg_ev.as_of, self.ob, self.mu
        allocation = self._allocation(seg_ev)
        formula_id = manual.TARGET_FORMULAS[adj.kind]
        if adj.kind == "MANUAL_RELEASE":  # S09-R-38: every period ending on or after P
            if d < adj.period.start_date:
                return None
            c_p = self.adjusted(adj.period.end_date, None, index)[0]
            params = manual.release_params(adj, as_of=d, c_p=c_p, allocation=allocation, mu=mu)
            return formula_id, params
        if adj.kind == "MANUAL_DEFER":  # S09-R-39: period P only
            if not adj.period.start_date <= d <= adj.period.end_date:
                return None
            previous = manual.previous_period(self.periods, adj.period)
            c_prev = 0 if previous is None else self.adjusted(previous.end_date, None, index)[0]
            params = manual.defer_params(adj, as_of=d, c_prev=c_prev, allocation=allocation, mu=mu)
            return formula_id, params
        first = adj.listed[0][0]  # S09-R-40: SCHEDULE_OVERRIDE
        if d < first.start_date:
            return None
        previous = manual.previous_period(self.periods, first)
        cumulative = 0 if previous is None else self.adjusted(previous.end_date, None, index)[0]
        latest: tuple[PeriodInput, int] | None = None
        for period, amount in adj.listed:
            cumulative += money.round_half_up(amount, mu)
            bounded = (
                0 <= cumulative <= allocation if allocation >= 0 else allocation <= cumulative <= 0
            )
            if not bounded:
                raise _invariant(
                    "a schedule override lies outside the allocation",
                    ob,
                    rule="S09-R-40",
                    event_key=adj.event.event_key,
                )
            if period.start_date <= d <= period.end_date:
                params = manual.override_params(
                    adj, as_of=d, allocation=allocation, mu=mu, target=cumulative
                )
                return formula_id, params
            if period.end_date < d:
                latest = (period, cumulative)
        if latest is None:
            return None
        period, t_k = latest
        fixed = seg_ev.fixed
        at_k = self.segments(period.end_date).fixed
        if fixed is None or at_k is None:
            raise _invariant("a schedule override needs a FIXED component", ob, rule="S09-R-40")
        params = manual.override_params(
            adj,
            as_of=d,
            allocation=fixed.segment.a_posted,
            mu=mu,
            t_k=t_k,
            x_exact=fixed.segment.x_exact,
            f_t=fixed.progress.value,
            f_k=at_k.progress.value,
        )
        return formula_id, params

    def posted(self, d: date, position: Position | None = None) -> Evaluation:
        """The posted target at ``d``: segments, manual adjustments, holds, V4 guard (S09-R-41)."""
        seg_ev = self.segments(d, position)
        if seg_ev.guard is not None:
            return seg_ev
        value, applied = self.adjusted(d, position)
        frozen: holds.Frozen | None = None
        hold = holds.open_at(
            holds.intervals(self.st, self.ob, seg_ev.as_of, position), seg_ev.as_of
        )
        if hold is not None:
            before = Position(hold.applied.order_key, inclusive=False)
            level = self.adjusted(hold.applied.effective_date - timedelta(days=1), before)[0]
            params = holds.freeze_params(
                hold,
                as_of=seg_ev.as_of,
                level=level,
                allocation=self._allocation(seg_ev),
                mu=self.mu,
            )
            held = manual.evaluate(self.ob, holds.FREEZE_FORMULA, value, params, self.mu)
            frozen = holds.Frozen(hold, params, held)
            value = held
        netting: tuple[int, int] | None = None
        if self.attribution is not None and str(self.ob.scope_flag) == "IN_SCOPE_606":
            # S02-R-04 (rev 1.6): the STEP1_MET target is max(C_p(d) − R25_p, 0), R25_p the
            # 606-10-25-7 revenue attributed to the obligation through d (D-91 gaps (v)).
            r25, _ = step1.share(
                self.attribution, self.ob.subject_key, seg_ev.as_of, self.mu, position=position
            )
            if r25 > 0:
                netting = (value, r25)
                value = max(value - r25, 0)
        return replace(seg_ev, value=value, adjustments=applied, hold=frozen, netting=netting)


def evaluate(
    ctx: BookContext, st: AllocatedState, contract: ContractView, ob: ObligationState, d: date
) -> Evaluation:
    """The posted target of ``ob`` at ``d`` (S09-R-41)."""
    return Evaluator(ctx, st, ob, contract).posted(d)


def target_at(ctx: BookContext, st: AllocatedState, ob: ObligationState, d: date) -> Evaluation:
    """The obligation's posted target at any date ``d``, including dates within a period."""
    return Evaluator(ctx, st, ob).posted(d)


def _horizon(ctx: BookContext, ob: ObligationState) -> tuple[tuple[PeriodInput, ...], PeriodInput]:
    entity = ctx.entities.get(ob.performing_entity)
    horizon_key = ctx.horizon.get(ob.performing_entity)
    if entity is None or horizon_key is None:
        raise _invariant("the performing entity has no calendar or horizon", ob, rule="CV-13")
    ordered = tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))
    horizon = next((period for period in ordered if period.period_key == horizon_key), None)
    if horizon is None:
        raise _invariant("the horizon period is absent from the calendar", ob, rule="CV-13")
    return ordered, horizon


def evaluation_periods(
    ctx: BookContext, st: AllocatedState, ob: ObligationState
) -> tuple[PeriodInput, ...]:
    """Periods of the performing entity from the group's inception period through the horizon.

    A deterministic component (``is_deterministic``) extends them through the period containing its
    term end (C-04, C-05; S09-R-50).
    """
    ordered, horizon = _horizon(ctx, ob)
    entity = ctx.entities[ob.performing_entity]
    first = dates.period_of(entity, st.inception_date)
    last_end = horizon.end_date
    if is_deterministic(ob):
        for seg in ob.segments:
            end = seg.totals.end_date or ob.end_date
            if seg.component == "FIXED" and end is not None:
                last_end = max(last_end, dates.period_of(entity, end).end_date)
    return tuple(
        period
        for period in ordered
        if period.start_date >= first.start_date and period.end_date <= last_end
    )


def _emit_components(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    ev: Evaluation,
    emitted: set[str],
    measure: str,
    return_state: returns.ReturnState | None = None,
    st: AllocatedState | None = None,
    component_nodes: dict[str, str] | None = None,
) -> str:
    """Trace nodes of the segment target of one period (ENGINE_SPEC_B §9.5; CV-50 to CV-54).

    ``component_nodes`` receives the ``royalty_revenue_cum``, ``breakage_revenue_cum`` and
    ``unclaimed_property_cum`` node ids emitted for the period (ENC-8), keyed by measure.
    """
    mu = minor_unit(ctx)
    as_of = ev.as_of.isoformat()
    params: dict[str, str] = {"as_of": as_of}
    inputs: list[str | SourceRef] = []
    if ev.guard is not None:
        params["guard"] = ev.guard
        _emit_unmeasured_progress(tb, ob, period_key, as_of, ev.guard)
    else:
        if ev.fixed is None:
            _emit_unmeasured_progress(tb, ob, period_key, as_of, "no-fixed-component")
        if ev.fixed is not None:
            fixed = ev.fixed
            seg = fixed.segment
            progress_id = tb.node(
                measure="progress_ratio",
                subject_key=ob.subject_key,
                period_key=period_key,
                value=fixed.progress.value,
                currency=None,
                minor_unit=None,
                formula_id=fixed.progress.formula_id,
                inputs=[],
                params=fixed.progress.params,
                narrative_key=fixed.progress.formula_id.rsplit(".v", 1)[0],
            )
            if fixed.returns is not None:
                exact_id = returns.emit(
                    tb, ob, period_key, fixed.returns, emitted, state=return_state
                )
            else:
                exact_params = {
                    "as_of": as_of,
                    "progress": rational_param(fixed.progress.value),
                    "x_exact": rational_param(seg.x_exact),
                }
                exact_formula = INCEPTION_EXACT_FORMULA
                if seg.basis == "PROSPECTIVE":
                    exact_formula = PROSPECTIVE_EXACT_FORMULA
                    exact_params["base_revenue_exact"] = rational_param(seg.base_revenue_exact)
                if fixed.materials is not None:  # S09-R-14 zero-margin materials (D-76)
                    exact_formula = progress_inputs.UNINSTALLED_FORMULA
                    exact_params.update(fixed.materials.params())
                exact_id = tb.node(
                    measure="revenue_target_exact",
                    subject_key=f"{ob.subject_key}#FIXED",
                    period_key=period_key,
                    value=fixed.exact,
                    currency=None,
                    minor_unit=None,
                    formula_id=exact_formula,
                    inputs=[progress_id],
                    params=exact_params,
                    narrative_key=exact_formula.rsplit(".v", 1)[0],
                )
            inputs.append(exact_id)
            params["fixed"] = "true"
            params["x_exact"] = rational_param(seg.x_exact)
            params["a_posted"] = str(seg.a_posted)
            if fixed.complete:
                params["complete"] = "true"
        for item in ev.realised:
            inputs.append(
                SourceRef(
                    "contract_event",
                    item.event_key,
                    {"member": "rated_amount", "value": money.format_money(item.amount, mu)},
                )
            )
        if ev.royalty is not None:
            if st is None:
                raise _invariant("the ROYALTY component needs the state", ob, rule="S09-R-01")
            royalty_id = royalty.emit(tb, ctx, st, ob, period_key, ev.royalty, emitted, mu=mu)
            inputs.append(royalty_id)  # a realised amount of rec.revenue_cum.v1 (S09-R-02)
            if component_nodes is not None:
                component_nodes[royalty.ROYALTY_MEASURE] = royalty_id
    node_id = tb.node(
        measure=measure,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=ev.segments_value,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=REVENUE_CUM_FORMULA,
        inputs=inputs,
        params=params,
        exact=ev.exact,
        narrative_key=REVENUE_CUM_FORMULA.rsplit(".v", 1)[0],
    )
    if ev.guard is None and ev.fixed is not None and ev.fixed.redemption is not None:
        breakage_id, escheat_id = breakage.emit(
            tb,
            ctx,
            ob,
            period_key,
            ev.fixed.redemption,
            ev.fixed.segment,
            node_id,
            ev.fixed.posted,
            mu,
        )
        if component_nodes is not None:
            component_nodes[breakage.BREAKAGE_MEASURE] = breakage_id
            if escheat_id is not None:
                component_nodes[breakage.ESCHEAT_MEASURE] = escheat_id
    return node_id


UNMEASURED_PROGRESS_FORMULA: Final = "rec.progress.unmeasured.v1"


def _emit_unmeasured_progress(
    tb: TraceBuilder, ob: ObligationState, period_key: str, as_of: str, reason: str
) -> str:
    """The ``progress_ratio`` node of a period (or ``-``) whose target is under a guard or has no
    ``FIXED`` component: the rule-produced 0 of S02-R-03 with its reason — the guard string with
    its status, or ``no-fixed-component`` — and date (ENGINE_SPEC CV-50 rev 1.31; T1F-LP-PR-1),
    so the T-CON-11 column always links a truthful producer, never the missing-node zero default."""
    return tb.node(
        measure="progress_ratio",
        subject_key=ob.subject_key,
        period_key=None if period_key == "-" else period_key,
        value=Fraction(0),
        currency=None,
        minor_unit=None,
        formula_id=UNMEASURED_PROGRESS_FORMULA,
        inputs=[],
        params={"as_of": as_of, "reason": reason},
        narrative_key=UNMEASURED_PROGRESS_FORMULA.rsplit(".v", 1)[0],
    )


def _traces_returns(ev: Evaluation) -> bool:
    """Whether ``_emit_components`` reaches ``returns.emit`` with an expected-units node for
    ``ev``: no guard, a ``FIXED`` part with a returns target, and that target's E (not a
    ``RESTORE_REMAINING_QUANTITY`` reversal chain)."""
    return (
        ev.guard is None
        and ev.fixed is not None
        and ev.fixed.returns is not None
        and ev.fixed.returns.expected is not None
    )


def _emit(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    ev: Evaluation,
    emitted: set[str],
    return_state: returns.ReturnState | None = None,
    st: AllocatedState | None = None,
    component_nodes: dict[str, str] | None = None,
) -> str:
    """The ``revenue_cum`` node of one period, after the S09-R-41 chain (§9.5).

    Without adjustments or holds the component node is ``revenue_cum`` itself. Otherwise the chain
    is ``segment_target`` → ``manual_adjusted_target@<event key>`` per adjustment →
    ``hold_frozen_target`` → ``revenue_cum`` (L1-3-Q-17). A ``return_state`` (a period end of a
    returnable obligation) adds the S09-R-23a units nodes beside the expected-units node (D-91).
    """
    if not ev.adjusted:
        return _emit_components(
            tb,
            ctx,
            ob,
            period_key,
            ev,
            emitted,
            "revenue_cum",
            return_state=return_state,
            st=st,
            component_nodes=component_nodes,
        )
    mu = minor_unit(ctx)
    last = _emit_components(
        tb,
        ctx,
        ob,
        period_key,
        ev,
        emitted,
        "segment_target",
        return_state=return_state,
        st=st,
        component_nodes=component_nodes,
    )
    for applied in ev.adjustments:
        last = tb.node(
            measure=f"manual_adjusted_target@{applied.adjustment.event.event_key}",
            subject_key=ob.subject_key,
            period_key=period_key,
            value=applied.value,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=applied.formula_id,
            inputs=[last],
            params=applied.params,
            narrative_key=applied.formula_id.rsplit(".v", 1)[0],
        )
    if ev.hold is not None:
        last = tb.node(
            measure="hold_frozen_target",
            subject_key=ob.subject_key,
            period_key=period_key,
            value=ev.hold.value,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=holds.FREEZE_FORMULA,
            inputs=[last],
            params=ev.hold.params,
            narrative_key=holds.FREEZE_FORMULA.rsplit(".v", 1)[0],
        )
    if ev.netting is not None:
        # S02-R-04 (rev 1.6; D-91 gaps (v)): max(C_p − R25_p, 0), citing the stage 09 share node
        # of the period (ENGINE_SPEC_B S14-R-25), which step1.emit published before this chain.
        before, r25 = ev.netting
        last = tb.node(
            measure=step1.NETTED_MEASURE,
            subject_key=ob.subject_key,
            period_key=period_key,
            value=max(before - r25, 0),
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=step1.NET_FORMULA,
            inputs=[last, step1.share_node_id(ob.subject_key, period_key)],
            params={"as_of": ev.as_of.isoformat(), "r25": str(r25), "rule": "S02-R-04"},
            narrative_key=step1.NET_FORMULA.rsplit(".v", 1)[0],
        )
    return tb.node(
        measure="revenue_cum",
        subject_key=ob.subject_key,
        period_key=period_key,
        value=ev.value,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=REVENUE_CUM_FORMULA,
        inputs=[last],
        params={"adjusted": "true", "as_of": ev.as_of.isoformat()},
        narrative_key=REVENUE_CUM_FORMULA.rsplit(".v", 1)[0],
    )


def emit_target(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    ev: Evaluation,
    emitted: set[str],
    st: AllocatedState | None = None,
) -> str:
    """The ``revenue_cum`` node chain of ``ev`` at a period end, or with ``-`` at the version date
    (§9.5); ``emitted`` holds the ``return_reversal@`` and ``royalty_true_up@`` nodes already
    emitted (CV-50). ``st`` is needed for an obligation with a ``ROYALTY`` component."""
    return _emit(tb, ctx, ob, period_key, ev, emitted, st=st)


@dataclass(frozen=True, slots=True)
class StageTargets:
    """The stage 09 targets of one book (§9.1).

    ``evaluators`` keeps the evaluator of every obligation with targets and ``emitted`` the
    ``return_reversal@`` nodes, so the obligation measures and schedules reuse both (ENC-10).
    ``deposit_revenue_shares`` are the S14-R-25 ``deposit_revenue_share`` and
    ``deposit_revenue_time_share`` targets per obligation and period end (D-91 gaps (iv)).
    """

    revenue_targets: tuple[Target, ...]
    revenue_by_cause: tuple[Target, ...]
    return_states: Mapping[tuple[str, str], returns.ReturnState]  # (subject key, period key)
    findings: tuple[Finding, ...]
    evaluators: Mapping[str, Evaluator] = MappingProxyType({})  # subject key -> evaluator
    emitted: frozenset[str] = frozenset()
    # ENC-8: unclaimed-property amounts at expiry (S09-R-28) and royalty coverage gaps (S09-R-34).
    escheat_components: tuple[breakage.EscheatComponent, ...] = ()
    close_gate_facts: tuple[royalty.CoverageGap, ...] = ()
    deposit_revenue_shares: tuple[Target, ...] = ()


def _component_causes(
    evaluation: Evaluation,
    nodes: Mapping[str, str],
    previous: Mapping[str, str],
    previous_evaluation: Evaluation | None,
    mu: int,
) -> tuple[decompose.ComponentCause, ...]:
    """The ``BREAKAGE`` and ``ROYALTY`` causes of a period from the component nodes (S09-R-35).

    ``BREAKAGE`` = ΔC_breakage of the redemption target (S09-R-30) and ``ROYALTY`` = Δ of the
    recognised ``ROYALTY`` component; each cites the period's component node and the previous
    period's when it exists. A guarded period contributes the reversal of the previous cumulative.
    """
    found: list[decompose.ComponentCause] = []

    def cumulative(ev: Evaluation | None, measure: str) -> int:
        if ev is None or ev.guard is not None:
            return 0
        if measure == breakage.BREAKAGE_MEASURE:
            fixed = ev.fixed
            if fixed is None or fixed.redemption is None:
                return 0
            part = fixed.redemption
            return breakage.breakage_posted(
                fixed.posted, fixed.segment.x_exact, part.quantity, part.redeemed, mu
            )
        return 0 if ev.royalty is None else ev.royalty.recognised

    for measure, cause in (
        (breakage.BREAKAGE_MEASURE, "BREAKAGE"),
        (royalty.ROYALTY_MEASURE, "ROYALTY"),
    ):
        if measure not in nodes and measure not in previous:
            continue
        delta = cumulative(evaluation, measure) - cumulative(previous_evaluation, measure)
        cited = tuple(nodes[m] for m in (measure,) if m in nodes) + tuple(
            previous[m] for m in (measure,) if m in previous
        )
        found.append(decompose.ComponentCause(cause, delta, cited))
    return tuple(found)


def revenue_targets(ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> StageTargets:
    """Targets per obligation and period end, causes, return states and findings (§9.1)."""
    targets: list[Target] = []
    by_cause: list[Target] = []
    return_states: dict[tuple[str, str], returns.ReturnState] = {}
    findings: dict[tuple[int, str, str, str, bytes], Finding] = {}
    emitted: set[str] = set()
    evaluators: dict[str, Evaluator] = {}
    escheat: list[breakage.EscheatComponent] = []
    facts: list[royalty.CoverageGap] = []
    shares: list[Target] = []
    attributed = step1.attributions(st)  # S14-R-25; fails closed on TOTAL_WEIGHT_ZERO
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        validate(ob)
        if str(ob.scope_flag) != "IN_SCOPE_606":
            continue  # S09-INV-05; REQ-CON-016: no targets outside Topic 606
        contract = _contract_of(st, ob)
        if progress_events.repurchase_outcome(ctx, contract, ob) == "LEASE":
            continue  # S09-R-13: routed to Topic 842, no targets and no schedule
        attribution = attributed.get(ob.contract_key)
        evaluator = Evaluator(ctx, st, ob, contract, attribution)
        evaluators[ob.subject_key] = evaluator
        cited = decompose.cited_posted(tb, evaluator.mu)  # S09-R-36
        previous_node: str | None = None
        previous_value = 0
        previous_nodes: dict[str, str] = {}
        previous_evaluation: Evaluation | None = None
        for period in evaluation_periods(ctx, st, ob):
            if attribution is not None:  # the share nodes the revenue chain and stage 14 cite
                shares.extend(
                    step1.emit(tb, ctx, attribution, ob, period.period_key, period.end_date)
                )
            evaluation = evaluator.posted(period.end_date)
            return_state: returns.ReturnState | None = None
            if ob.subject_key in st.return_paths:
                seg = active_segment(ob, "FIXED", period.end_date)
                return_state = returns.return_state(ctx, st, contract, ob, seg, period.end_date)
            component_nodes: dict[str, str] = {}
            node_id = _emit(
                tb,
                ctx,
                ob,
                period.period_key,
                evaluation,
                emitted,
                return_state=return_state,
                st=st,
                component_nodes=component_nodes,
            )
            if return_state is not None:
                if _traces_returns(evaluation):  # S09-R-23a nodes emitted by returns.emit
                    return_state = replace(
                        return_state,
                        e_b_node_id=returns.refundable_units_node_id(ob, period.period_key),
                    )
                return_states[(ob.subject_key, period.period_key)] = return_state
            targets.append(
                Target(
                    book_code=ctx.book_code,
                    entity=ob.performing_entity,
                    subject_key=ob.subject_key,
                    measure="revenue_cum",
                    period_key=period.period_key,
                    cause=None,
                    value=evaluation.value,
                    exact=None if evaluation.adjusted else evaluation.exact,
                    node_id=node_id,
                )
            )
            found = decompose.points(
                st,
                ob,
                period,
                posted=evaluator.posted_value,
                segments=evaluator.segment_value,
                cited=cited,
            )
            components = _component_causes(
                evaluation, component_nodes, previous_nodes, previous_evaluation, evaluator.mu
            )
            amounts = decompose.sequential(previous_value, evaluation.value, found, components)
            by_cause.extend(
                decompose.emit(
                    tb,
                    ctx,
                    ob,
                    period.period_key,
                    as_of=period.end_date,
                    mu=evaluator.mu,
                    current_node=node_id,
                    previous_node=previous_node,
                    found=found,
                    amounts=amounts,
                    components=components,
                )
            )
            fixed = evaluation.fixed
            if (
                evaluation.guard is None
                and fixed is not None
                and fixed.redemption is not None
                and fixed.redemption.expired_on is not None
                and breakage.ESCHEAT_MEASURE in component_nodes
            ):
                escheat.append(
                    breakage.EscheatComponent(
                        ob.subject_key,
                        ob.contract_key,
                        ob.contracting_entity,
                        period.period_key,
                        fixed.redemption.expired_on,
                        fixed.segment.a_posted - fixed.posted,
                        component_nodes[breakage.ESCHEAT_MEASURE],
                    )
                )
            if evaluation.royalty is not None:
                facts.extend(
                    royalty.coverage_gaps(
                        ctx,
                        st,
                        ob,
                        period.end_date,
                        period.period_key,
                        satisfied=evaluation.royalty.satisfied,
                    )
                )
            previous_node, previous_value = node_id, evaluation.value
            previous_nodes, previous_evaluation = component_nodes, evaluation
            for finding in evaluation.findings:
                findings.setdefault(finding.sort_key(), finding)
        boundaries = decompose.boundary_points(
            st, ob, segments=evaluator.segment_value, cited=cited, exacts=evaluator.segment_exact
        )
        _, horizon = _horizon(ctx, ob)
        decompose.emit_catch_up_measures(
            tb, ctx, ob, boundaries, as_of=horizon.end_date, mu=evaluator.mu
        )
    return StageTargets(
        revenue_targets=tuple(targets),
        revenue_by_cause=tuple(by_cause),
        return_states=MappingProxyType(dict(sorted(return_states.items()))),
        findings=tuple(findings[key] for key in sorted(findings)),
        evaluators=MappingProxyType(evaluators),
        emitted=frozenset(emitted),
        escheat_components=tuple(escheat),
        close_gate_facts=tuple(facts),
        deposit_revenue_shares=tuple(shares),
    )
