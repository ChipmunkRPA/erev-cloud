"""Stage 06 boundary measurement, segments after a native modification and catch-up nodes.

ENGINE_SPEC §6.1 (state before the event), §6.3 S06-R-14 (class D segments) and S06-R-17
(catch-up measurement, formula ``mod.catch_up.v1``); §6.6 S06-INV-02; CV-60 to CV-63.

The obligation is measured at the boundary point with the CV-63 formulas over the public
``erev_engine.progress`` functions: event-driven measures read the quantity ledger strictly before
the event (ENG-06), and time elapsed is measured at the close of d − 1, because the remaining term
of a modification starts on its effective date (ENGINE_SPEC_B EX-09-A: R_k = C(15 Sep 2026) for a
modification effective 16 Sep 2026). Cost-based measures read the ``EAC`` pin in force before the
event. A measure that stage 06 cannot measure at a boundary fails closed.

S06-R-11 remaining service (D-90b): ``remaining_scale`` gives ρ_p of a class D existing obligation
that ``eligible`` admits, Σ_L q_L × (1 − f_L(d − 1)) ÷ Σ_L q_L over the unit layers of
``unit_layers``, with f_L ALG-11 progress under ``convention_of`` over [s_L, e_p] on the
``INCEPTION`` basis and [s_p, e_p] the ``term_in_force``. The layers are reconstructed from the
``FIXED`` segment history of ``totals.quantity``; a history that does not reconcile, a quantity
change at a boundary other than a modification or a material-right exercise (``OPENING_BALANCE``
resets the layers) and ρ_p = 0 fail closed. Private to stage 06. Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Final

from erev_engine import dates, money, progress, usage
from erev_engine.enums import Distinctness
from erev_engine.errors import EngineError
from erev_engine.formulas import periods_param, rational_param
from erev_engine.stages.s09_recognition import eac_version_at, input_progress, input_target
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    LedgerPoint,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    SegmentCause,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "CATCH_UP_FORMULA",
    "Measured",
    "boundary_as_of",
    "calendar_of",
    "convention_of",
    "cumulative",
    "eligible",
    "emit_catch_up",
    "in_force",
    "inception",
    "measure",
    "minor_unit",
    "progress_undefined",
    "prospective",
    "remaining_scale",
    "series_basis_scale",
    "term_in_force",
    "to_minor",
    "unit_layers",
]

CATCH_UP_FORMULA: Final = "mod.catch_up.v1"
UNIT_MEASURES: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED", "UNITS_SINCE_BOUNDARY"})
RATIO_MEASURES: Final = frozenset({"OUTPUT_PERCENT", "MILESTONE"})
COST_MEASURES: Final = frozenset({"COST_TO_COST", "LABOUR_HOURS"})
# D-93 (4): E-49 bases a series entry declares; AMOUNT is the remaining-increments reading as is.
SERIES_BASES: Final = frozenset({"PER_INCREMENT", "PER_BOOKED_TERM"})
SERIES_TIME_UNITS: Final = frozenset({"day", "month"})
SERIES_QUANTITY_UNITS: Final = frozenset({"SERVICE_UNITS", "INCREMENTS"})  # E-125 (D-97 (3))
TIME_CONVENTION_POLICY: Final = "recognition.time_convention"
TIME_CONVENTIONS: Final = frozenset({"DAILY", "MONTHLY_EVEN", "MID_MONTH"})
FIXED: Final = "FIXED"
PROSPECTIVE: Final = "PROSPECTIVE"
INCEPTION: Final = "INCEPTION"
TIME_ELAPSED: Final = "TIME_ELAPSED"
REMAINING_SERVICE_RULE: Final = "S06-R-11"
LAYER_SEPARATOR: Final = "|"
# Boundaries that may change totals.quantity of a unit-layer history (D-90b).
QUANTITY_CAUSES: Final = frozenset(
    {SegmentCause.MODIFICATION, SegmentCause.MATERIAL_RIGHT_EXERCISE}
)


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def minor_unit(ctx: BookContext) -> int:
    """μ of the group's transaction currency (CV-33)."""
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise _invariant(
            "the transaction currency is absent from the currency table",
            ctx.txn_currency,
            rule="CV-30",
        )
    return spec.minor_unit


def to_minor(ctx: BookContext, amount: Fraction, name: str) -> int:
    """``amount`` in whole minor units; a sub-minor-unit money member raises ``ValueError``."""
    scale: int = 10 ** minor_unit(ctx)
    scaled = amount * scale
    if scaled.denominator != 1:
        raise ValueError(f"{name} is not a whole number of minor units (CV-30)")
    return scaled.numerator


def boundary_as_of(ev: EventView) -> date:
    """The date time progress is measured on at a boundary: the close of d − 1 (EX-09-A)."""
    return ev.effective_date - timedelta(days=1)


def in_force(
    st: AllocatedState, ob: ObligationState, ev: EventView, *, inclusive: bool = False
) -> AllocationSegment | None:
    """The ``FIXED`` segment in force before ``ev`` in ENG-06 order, or at it when ``inclusive``
    (CV-60)."""
    order_keys = {item.event_key: item.order_key for item in st.events}
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component != FIXED or seg.effective_date > ev.effective_date:
            continue
        if seg.event_key is not None:
            order_key = order_keys.get(seg.event_key)
            if order_key is None:
                raise _invariant(
                    "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
                )
            if order_key > ev.order_key or (order_key == ev.order_key and not inclusive):
                continue
        found = seg
    return found


@dataclass(frozen=True, slots=True)
class Measured:
    """One obligation measured at the boundary point on one segment (ENGINE_SPEC §6.1; CV-63)."""

    segment: AllocationSegment
    point: LedgerPoint  # quantity ledger strictly before the event
    progress: Fraction  # f (INCEPTION) or g (PROSPECTIVE)
    exact: Fraction  # E, currency units
    posted: int  # C, minor units
    complete: bool  # φ = 1
    delivered: Fraction  # q_p: net delivered units (delivered less returned)
    remaining_quantity: Fraction  # units still to transfer under the segment's totals


def cumulative(
    ctx: BookContext, seg: AllocationSegment, fraction: Fraction, subject_key: str
) -> tuple[Fraction, int, bool]:
    """(E, C, φ = 1) of ``seg`` at progress ``fraction`` (CV-63)."""
    if seg.basis == INCEPTION:
        exact = seg.x_exact * fraction
    elif seg.basis == PROSPECTIVE:
        exact = seg.base_revenue_exact + (seg.x_exact - seg.base_revenue_exact) * fraction
    else:
        raise _invariant("unknown segment basis", subject_key, rule="CV-60", basis=seg.basis)
    if seg.x_exact == 0:
        if seg.a_posted != 0:
            raise _invariant(
                "a zero exact allocation carries a posted allocation", subject_key, rule="CV-63"
            )
        return exact, 0, fraction == 1
    ratio = Fraction(1) if fraction == 1 else exact / seg.x_exact
    if not 0 <= ratio <= 1:
        raise _invariant("the exact target lies outside the allocation", subject_key, rule="CV-63")
    posted = money.cumulative_posted(seg.x_exact, seg.a_posted, ratio, minor_unit(ctx))
    return exact, posted, ratio == 1


def measure(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    ev: EventView,
    *,
    eac_before: bool = True,
) -> Measured:
    """``seg`` of ``ob`` at the boundary point of ``ev``: progress, E and C (CV-61 to CV-63).

    ``eac_before`` reads the ``EAC`` pin applied before the event (the state before it); otherwise
    the pin effective at d among every applied version, the updated EAC of S06-R-15.
    """
    point = st.ledger.at(ob.subject_key, before=ev)
    delivered = point.delivered_cum - point.returned_cum
    if seg.progress_measure in COST_MEASURES and seg.cause != SegmentCause.TERMINATION:
        # ENC-5: the stage 09 target of S09-R-14 to S09-R-16, uninstalled materials included, so
        # the pool, the class D base and the catch-up start from the revenue stage 09 recognised
        # (S06-R-17; S06-INV-02); f keeps the margin-bearing definition of S09-R-14.
        _eac(st, ob, seg, ev, seg.progress_measure, eac_before=eac_before)
        fraction, exact, posted, complete = input_target(
            ctx, st, ob, seg, ev.effective_date, event=ev, inclusive=not eac_before
        )
    else:
        fraction = _progress(ctx, st, ob, seg, ev, point, eac_before=eac_before)
        exact, posted, complete = cumulative(ctx, seg, fraction, ob.subject_key)
    if seg.progress_measure in UNIT_MEASURES:
        since = delivered - (seg.base_progress.delivered_cum if seg.basis == PROSPECTIVE else 0)
        remaining = seg.totals.quantity - since
    else:
        remaining = seg.totals.quantity  # no unit ledger: the totals are not consumed by units
    return Measured(seg, point, fraction, exact, posted, complete, delivered, remaining)


def _share(done: Fraction, total: Fraction) -> Fraction:
    # A remaining total of 0 gives 1 (CV-62); progress is bounded to [0, 1].
    if total <= 0:
        return Fraction(1)
    return min(Fraction(1), max(Fraction(0), done) / total)


def _progress(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    ev: EventView,
    point: LedgerPoint,
    *,
    eac_before: bool,
) -> Fraction:
    measure_name = seg.progress_measure
    prospective = seg.basis == PROSPECTIVE
    if seg.cause == SegmentCause.TERMINATION:
        return Fraction(1)  # totals that give f = 1 from d_T (S06-R-21; S09-R-06)
    if measure_name == usage.RIGHT_TO_INVOICE and ob.stated_price != 0:
        # ENC-6 (S09-R-18 rev 1.20; D-98 candidate 28): the FIXED component's progress is the right
        # to invoice before the boundary over the stated price, f = min(1, R ÷ P) (or g since the
        # segment's own boundary, §9.2.4); the part above P rides PERIOD_VC and crosses as events.
        # A P = 0 rate line takes the time-elapsed signal below (§9.2.4 rev 1.22, ENC6-R3).
        return _right_to_invoice(st, ob, seg, ev)
    if measure_name == "TIME_ELAPSED" or measure_name in usage.REALISED_METHODS:
        # ENC-6: the FIXED component of a USAGE obligation — a stand-ready fee or minimum — is
        # measured by time elapsed (ENGINE_SPEC_B S09-R-19, S09-R-20); the DERIVED fees ride the
        # PERIOD_VC component and cross the boundary as events.
        return _time(ctx, ob, seg, boundary_as_of(ev))
    if measure_name in UNIT_MEASURES:
        net = point.delivered_cum - point.returned_cum
        base = seg.base_progress.delivered_cum if prospective else Fraction(0)
        return _share(net - base, seg.totals.quantity)
    if measure_name in RATIO_MEASURES:
        output = measure_name == "OUTPUT_PERCENT"
        current = point.output_ratio if output else point.milestone_weight_cum
        base_point = _boundary_point(st, ob, seg) if prospective else None
        if base_point is None:
            return (
                progress.output_fraction(current)
                if output
                else progress.milestone_fraction(current)
            )
        base = base_point.output_ratio if output else base_point.milestone_weight_cum
        if output:
            return progress.output_fraction(current, base)
        return progress.milestone_fraction(current, base)
    if measure_name in COST_MEASURES:
        # S09-R-14 to S09-R-16 through stage 09 (ENC-5): margin-bearing costs or hours over the
        # EAC pin; the class N segment reads the updated EAC effective at d (S06-R-15).
        _eac(st, ob, seg, ev, measure_name, eac_before=eac_before)
        return input_progress(st, ob, seg, ev.effective_date, event=ev, inclusive=not eac_before)
    raise _invariant(
        "the measure of progress cannot be measured at a modification boundary",
        ob.subject_key,
        rule="S06-R-17",
        progress_measure=measure_name,
    )


def _right_to_invoice_before(st: AllocatedState, ob: ObligationState, ev: EventView) -> Fraction:
    """R before ``ev`` in ENG-06 order: the right to invoice for performance to the boundary."""
    contract = next(
        (view for view in st.contracts if view.header.external_id == ob.contract_key), None
    )
    if contract is None:
        raise _invariant(
            "the obligation's contract is absent from the state", ob.subject_key, rule="CV-45"
        )
    return usage.right_to_invoice(
        st.measure_events,
        contract_key=ob.contract_key,
        obligation_key=ob.obligation_key,
        subject_key=ob.subject_key,
        booking=contract.booking,
        at=ev.effective_date,
        admits=lambda item: item.order_key < ev.order_key,
    ).amount


def _right_to_invoice(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment, ev: EventView
) -> Fraction:
    realised = _right_to_invoice_before(st, ob, ev)
    base = Fraction(0)
    if seg.basis == PROSPECTIVE and seg.event_key is not None:
        boundary = next((item for item in st.events if item.event_key == seg.event_key), None)
        if boundary is None:
            raise _invariant(
                "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
            )
        base = _right_to_invoice_before(st, ob, boundary)
    return progress.right_to_invoice_fraction(realised, ob.stated_price, base)


def _boundary_point(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment
) -> LedgerPoint | None:
    if seg.event_key is None:
        return None
    boundary = next((item for item in st.events if item.event_key == seg.event_key), None)
    if boundary is None:
        raise _invariant("the boundary event of a segment is absent", ob.subject_key, rule="CV-60")
    return st.ledger.at(ob.subject_key, before=boundary)


def _eac(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    ev: EventView,
    measure_name: str,
    *,
    eac_before: bool,
) -> Fraction:
    """The EAC total the boundary measures with; a cost-based obligation without an element or an
    approved version fails closed (S06-R-15). The element is the segment's ``eac_element_code``
    or the ``EAC`` element naming the obligation (T-CON-12; stage 09 ``eac_keys``)."""
    pin = eac_version_at(st, ob, seg, ev.effective_date, event=ev, inclusive=not eac_before)
    if pin is None:
        raise _invariant(
            "no EAC version is pinned before the modification", ob.subject_key, rule="S06-R-15"
        )
    raw = pin.expected_total_amount if measure_name == "COST_TO_COST" else pin.expected_quantity
    if raw is None:
        raise _invariant(
            "the EAC version carries no total for the measure", ob.subject_key, rule="S06-R-15"
        )
    return money.to_fraction(raw)


def _time(ctx: BookContext, ob: ObligationState, seg: AllocationSegment, as_of: date) -> Fraction:
    convention = convention_of(ctx, ob)
    start: date | None
    if seg.basis == PROSPECTIVE:
        start = seg.effective_date
        if seg.totals.start_date is not None:
            start = max(start, seg.totals.start_date)
    else:
        start = seg.totals.start_date or ob.start_date
    end = seg.totals.end_date or ob.end_date
    if start is None or end is None:
        raise _invariant("a time-elapsed segment has no term", ob.subject_key, rule="CV-45")
    if ob.recognition_start_date is not None:
        start = max(start, ob.recognition_start_date)
    if end < start:
        return Fraction(1) if as_of >= end else Fraction(0)
    calendar = calendar_of(ctx, ob)
    return progress.time_fraction(convention, start, end, as_of, calendar=calendar)


def calendar_of(ctx: BookContext, ob: ObligationState) -> tuple[dates.DateRange, ...] | None:
    """The performing entity's accounting periods, or ``None`` for calendar months (E-50
    ``MONTHLY``); an absent entity fails closed (CV-12)."""
    entity = ctx.entities.get(ob.performing_entity)
    if entity is None:
        raise _invariant("the performing entity has no calendar", ob.subject_key, rule="CV-12")
    if entity.calendar_pattern == "MONTHLY":
        return None
    return tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))


def term_in_force(ob: ObligationState, seg: AllocationSegment) -> tuple[date, date]:
    """[s_p, e_p] of S06-R-11: the term of ``seg``, else the obligation's dates, with the start
    clamped by ``recognition_start_date`` (D-90b); a segment without a term fails closed (CV-45)."""
    start = seg.totals.start_date or ob.start_date
    end = seg.totals.end_date or ob.end_date
    if start is None or end is None:
        raise _invariant("a time-elapsed segment has no term", ob.subject_key, rule="CV-45")
    if ob.recognition_start_date is not None:
        start = max(start, ob.recognition_start_date)
    return start, end


def eligible(ob: ObligationState, seg: AllocationSegment) -> bool:
    """An obligation whose remaining service S06-R-08 and S06-R-11 measure (D-90b): not a VC line,
    not ``series``, and ``seg``, its ``FIXED`` segment in force, measures ``TIME_ELAPSED`` with a
    cause other than ``TERMINATION``."""
    return (
        not ob.is_vc_line
        and ob.distinctness != Distinctness.SERIES
        and seg.progress_measure == TIME_ELAPSED
        and seg.cause != SegmentCause.TERMINATION
    )


def unit_layers(
    ob: ObligationState, seg: AllocationSegment, term_start: date
) -> tuple[tuple[Fraction, date], ...]:
    """The unit layers (q_L, s_L) of ``ob`` through ``seg``, its ``FIXED`` segment in force (D-90b).

    The first segment's quantity starts at ``term_start`` (s_p). Walking the later ``FIXED``
    segments up to ``seg``: a rise of ``totals.quantity`` adds a layer at max(effective date, s_p);
    a fall reduces every earlier layer pro rata; an ``OPENING_BALANCE`` segment resets the layers to
    its quantity at its start. A quantity change at any other cause than a modification or a
    material-right exercise, a segment in force absent from the history, and layers that do not sum
    to ``seg.totals.quantity`` fail closed (S06-R-11). Zero layers are dropped.
    """
    fixed = [item for item in ob.segments if item.component == FIXED]
    upto = next((index for index, item in enumerate(fixed) if item is seg), None)
    if upto is None:
        raise _invariant(
            "the segment in force is not a FIXED segment of the obligation",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
        )
    layers: list[tuple[Fraction, date]] = [(fixed[0].totals.quantity, term_start)]
    previous = fixed[0].totals.quantity
    for item in fixed[1 : upto + 1]:
        quantity = item.totals.quantity
        if item.cause == SegmentCause.OPENING_BALANCE:
            opening_start = item.totals.start_date or item.effective_date
            layers = [(quantity, max(opening_start, term_start))]
        elif quantity != previous and item.cause not in QUANTITY_CAUSES:
            raise _invariant(
                "a boundary other than a modification or a material-right exercise changes the "
                "quantity of a unit-layer history",
                ob.subject_key,
                rule=REMAINING_SERVICE_RULE,
                cause=item.cause.value,
                effective_date=item.effective_date.isoformat(),
            )
        elif quantity > previous:
            layers.append((quantity - previous, max(item.effective_date, term_start)))
        elif quantity < previous:
            factor = quantity / previous
            layers = [(units * factor, start) for units, start in layers]
        previous = quantity
    kept = tuple((units, max(start, term_start)) for units, start in layers if units != 0)
    if sum((units for units, _ in kept), Fraction(0)) != seg.totals.quantity:
        raise _invariant(
            "the unit layers do not reconcile with the segment history",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
        )
    return kept


def _layer_progress(
    convention: str,
    start: date,
    end: date,
    as_of: date,
    calendar: Sequence[dates.DateRange] | None,
) -> Fraction:
    # f_L over [start, end] at the close of as_of; a layer starting after the term end completes
    # on it.
    if end < start:
        return Fraction(1) if as_of >= end else Fraction(0)
    return progress.time_fraction(convention, start, end, as_of, calendar=calendar)


def remaining_scale(
    ctx: BookContext,
    ob: ObligationState,
    before: Measured,
    ev: EventView,
    *,
    removed: Fraction,
) -> tuple[Fraction, Mapping[str, str]]:
    """ρ_p of S06-R-11 and the additive ``mod_weight`` params that record it (D-90b).

    ρ_p = Σ_L q_L × (1 − f_L(d − 1)) ÷ Σ_L q_L over ``unit_layers``; the layers sum to the quantity
    before the event, which the params tie to ``remaining_quantity`` + ``removed``. The layer over
    [s_p, e_p] is cross-checked with the boundary measure of an ``INCEPTION`` probe; layers that do
    not reconcile and ρ_p = 0 fail closed (``ENGINE_INVARIANT_VIOLATED``).
    """
    seg = before.segment
    as_of = boundary_as_of(ev)
    term_start, term_end = term_in_force(ob, seg)
    convention = convention_of(ctx, ob)
    calendar = calendar_of(ctx, ob)
    layers = unit_layers(ob, seg, term_start)
    total = sum((units for units, _ in layers), Fraction(0))
    if total <= 0 or total != before.remaining_quantity:
        raise _invariant(
            "the unit layers do not sum to the remaining quantity before the event",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
        )
    probe = _time(ctx, ob, dataclasses.replace(seg, basis=INCEPTION), as_of)
    if probe != _layer_progress(convention, term_start, term_end, as_of, calendar):
        raise _invariant(
            "the term in force disagrees with the boundary measure",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
        )
    measured = [
        _layer_progress(convention, start, term_end, as_of, calendar) for _, start in layers
    ]
    remaining = sum(
        (units * (1 - done) for (units, _), done in zip(layers, measured, strict=True)),
        Fraction(0),
    )
    rho = remaining / total
    if rho <= 0:
        raise _invariant(
            "a class D obligation measured by time elapsed has no remaining service",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
            as_of=as_of.isoformat(),
        )
    params = {
        "measure": TIME_ELAPSED,
        "convention": convention,
        "term_start": term_start.isoformat(),
        "term_end": term_end.isoformat(),
        "progress_as_of": as_of.isoformat(),
        "layer_quantities": LAYER_SEPARATOR.join(rational_param(units) for units, _ in layers),
        "layer_starts": LAYER_SEPARATOR.join(start.isoformat() for _, start in layers),
        "layer_progress": LAYER_SEPARATOR.join(rational_param(done) for done in measured),
        "remaining_scale": rational_param(rho),
        "removed": rational_param(removed),
    }
    if calendar is not None and convention != "DAILY" and term_start <= term_end:
        params["periods"] = periods_param(dates.covering_periods(calendar, term_start, term_end))
    return rho, params


def series_basis_scale(
    ctx: BookContext,
    ob: ObligationState,
    before: Measured,
    ev: EventView,
    *,
    basis: str | None,
    quantity_unit: str | None = None,
    removed: Fraction,
) -> tuple[Fraction, Mapping[str, str]] | None:
    """The S06-R-11 series factor of D-93 (4) and the additive ``mod_weight`` params that record it,
    or ``None`` when the branch does not apply.

    An existing ``series`` obligation measured by ``TIME_ELAPSED`` whose SSP entry declares
    ``PER_INCREMENT`` or ``PER_BOOKED_TERM`` (04 E-49) is priced at d over the remaining increments
    of its term in force: ρ = 1 − f(d − 1) under the pinned E-21 convention (the current period
    counts as remaining, D-90b); ``PER_BOOKED_TERM`` scales the booked-term value by ρ;
    ``PER_INCREMENT`` scales the unit value by the term's increments × ρ, the increments counted as
    the convention counts the term's periods (``progress.series_increments``: MONTHLY_EVEN whole
    plus day-prorated partial periods, MID_MONTH the counted periods, DAILY the days — Codex
    C1B-S1: one denominator for the count and for ρ) — and by the remaining quantity as the
    entry's E-125 ``quantity_unit`` declares it (D-97 (3); Codex C1B-S2: never inferred from the
    quantity): ``SERVICE_UNITS`` — each unit spans the term, value × increments × ρ × quantity;
    ``INCREMENTS`` — the quantity counts increments, value × ρ × quantity. A ``PER_INCREMENT``
    entry without a unit fails closed (stage 01 refuses it first, CV-45). ``AMOUNT`` (the
    remaining-increments reading) and the ``unit`` / ``transaction`` increments are taken as
    today. The single unit layer over [s_p, e_p] lets ``mod.weights.*`` recompute ρ with
    ``_remaining_scale``.
    """
    seg = before.segment
    if ob.distinctness != Distinctness.SERIES or basis not in SERIES_BASES:
        return None
    if seg.progress_measure != TIME_ELAPSED or seg.cause == SegmentCause.TERMINATION:
        return None
    unit = ob.series_increment_unit
    if unit not in SERIES_TIME_UNITS:
        return None
    as_of = boundary_as_of(ev)
    term_start, term_end = term_in_force(ob, seg)
    convention = convention_of(ctx, ob)
    calendar = calendar_of(ctx, ob)
    done = _layer_progress(convention, term_start, term_end, as_of, calendar)
    rho = 1 - done
    if rho <= 0:
        raise _invariant(
            "a series obligation measured by time elapsed has no remaining service",
            ob.subject_key,
            rule=REMAINING_SERVICE_RULE,
            as_of=as_of.isoformat(),
        )
    increments = progress.series_increments(
        convention, unit, term_start, term_end, calendar=calendar
    )
    if basis == "PER_INCREMENT" and quantity_unit not in SERIES_QUANTITY_UNITS:
        raise _invariant(
            "a PER_INCREMENT series entry declares quantity_unit (D-97 (3))",
            ob.subject_key,
            rule="S06-R-11",
            quantity_unit=str(quantity_unit),
        )
    multiplier = (
        increments if basis == "PER_INCREMENT" and quantity_unit == "SERVICE_UNITS" else Fraction(1)
    )
    params = {
        "measure": TIME_ELAPSED,
        "convention": convention,
        "term_start": term_start.isoformat(),
        "term_end": term_end.isoformat(),
        "progress_as_of": as_of.isoformat(),
        "layer_quantities": rational_param(before.remaining_quantity),
        "layer_starts": term_start.isoformat(),
        "layer_progress": rational_param(done),
        "remaining_scale": rational_param(rho),
        "removed": rational_param(removed),
        "series_basis": basis,
        "series_increment_unit": unit,
        "series_increments": rational_param(increments),
        "series_remaining_increments": rational_param(increments * rho),
        "series_multiplier": rational_param(multiplier),
    }
    if basis == "PER_INCREMENT":
        params["series_quantity_unit"] = str(quantity_unit)
    if calendar is not None and convention != "DAILY" and term_start <= term_end:
        params["periods"] = periods_param(dates.covering_periods(calendar, term_start, term_end))
    return rho * multiplier, params


def convention_of(ctx: BookContext, ob: ObligationState) -> str:
    """The E-21 convention pinned on the obligation, else the resolved POL-090 value (S09-R-08)."""
    if ob.ratable_convention is not None:
        return ob.ratable_convention.value
    value = ctx.policies.value(
        TIME_CONVENTION_POLICY,
        contract=ob.contract_key,
        obligation=ob.subject_key,
        entity=ob.performing_entity,
    )
    if not isinstance(value, str) or value not in TIME_CONVENTIONS:
        raise _invariant(
            "a time-elapsed obligation carries no ratable convention",
            ob.subject_key,
            rule="S09-R-08",
        )
    return value


def prospective(
    ctx: BookContext,
    ev: EventView,
    *,
    before: Measured | None,
    x_exact: Fraction,
    a_posted: int,
    totals: ProgressTotals,
    progress_measure: str,
    weight: Fraction,
    billing_plan: Fraction,
    boundary_no: int,
    cause: SegmentCause = SegmentCause.MODIFICATION,
    satisfied: int = 0,
) -> AllocationSegment:
    """The class D segment of S06-R-14: basis ``PROSPECTIVE`` from R_p, no catch-up (CV-62).

    ``before`` is the existing obligation measured at the boundary, or ``None`` for an obligation
    the modification adds (R = 0, nothing transferred). ``remaining_ssp`` records the S06-R-11
    weight, which stage 08 re-splits VC promised before the modification by (S08-R-05). ``cause``
    is ``MATERIAL_RIGHT_EXERCISE`` for the segments of an exercise (S06-R-23, S06-R-24).
    ``satisfied`` is the posted share of ΔC_sat the delivered portion receives (S06-R-09; ALG-04
    §2.5.3 adds it to R_p), so E after the boundary starts at R_p + share.
    """
    revenue = (0 if before is None else before.posted) + satisfied
    point = LedgerPoint.zero() if before is None else before.point
    delivered = Fraction(0) if before is None else before.delivered
    return AllocationSegment(
        component=FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=cause,
        basis=PROSPECTIVE,
        x_exact=x_exact,
        a_posted=a_posted,
        base_revenue_posted=revenue,
        base_revenue_exact=Fraction(revenue, 10 ** minor_unit(ctx)),
        base_progress=ProgressBase(delivered, point.costs_cum, point.hours_cum, ev.effective_date),
        totals=totals,
        progress_measure=progress_measure,
        unit_ssp=None if totals.quantity == 0 else weight / totals.quantity,
        remaining_ssp=weight,
        remaining_billing_plan=billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=boundary_no,
    )


def inception(
    ctx: BookContext,
    ev: EventView,
    *,
    source: AllocationSegment,
    x_exact: Fraction,
    a_posted: int,
    totals: ProgressTotals,
    remaining_ssp: Fraction,
    unit_ssp: Fraction | None,
    billing_plan: Fraction,
    cause: SegmentCause = SegmentCause.MODIFICATION,
) -> AllocationSegment:
    """A segment with basis ``INCEPTION`` measured from the obligation's start over ``totals``.

    Class N obligations (S06-R-15; CU = round(X′ × f′) − R_p), the receivers of satisfied
    performance (S06-R-09; f = 1, CU = the share) and the obligations re-allocated by a corrected
    SSP version pin (S06-R-26) take it; ``modification_boundary_no`` is carried.
    """
    return AllocationSegment(
        component=FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=cause,
        basis=INCEPTION,
        x_exact=x_exact,
        a_posted=a_posted,
        base_revenue_posted=0,
        base_revenue_exact=Fraction(0),
        base_progress=ProgressBase.zero(),
        totals=totals,
        progress_measure=source.progress_measure,
        unit_ssp=unit_ssp,
        remaining_ssp=remaining_ssp,
        remaining_billing_plan=billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=source.modification_boundary_no,
    )


def progress_undefined(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment, ev: EventView
) -> bool:
    """A zero progress divisor over the updated totals of an ``INCEPTION`` segment (S06-R-17)."""
    if seg.progress_measure in UNIT_MEASURES:
        return seg.totals.quantity == 0
    if seg.progress_measure in COST_MEASURES:
        return _eac(st, ob, seg, ev, seg.progress_measure, eac_before=False) == 0
    return False


def _side(measured: Measured | None, side: str) -> dict[str, str]:
    if measured is None:
        return {
            f"a_{side}": "0",
            f"complete_{side}": "false",
            f"exact_{side}": "0",
            f"x_{side}": "0",
        }
    return {
        f"a_{side}": str(measured.segment.a_posted),
        f"complete_{side}": "true" if measured.complete else "false",
        f"exact_{side}": rational_param(measured.exact),
        f"x_{side}": rational_param(measured.segment.x_exact),
    }


def emit_catch_up(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    subject_key: str,
    *,
    before: Measured | None,
    after: Measured,
    share_node: str | None,
    base: int,
    extra: Mapping[str, str] | None = None,
) -> int:
    """``catch_up@<event key>:<ob>:-``: C_after − C_before at the boundary point (S06-R-17).

    ``base`` is the posted amount the share adds to (R_p for an existing obligation, 0 for an added
    one), so the formula checks the ``mod_share`` input against ``a_after`` − ``base``.
    """
    value = after.posted - (0 if before is None else before.posted)
    exact = after.exact - (Fraction(0) if before is None else before.exact)
    params = {
        "as_of": ev.effective_date.isoformat(),
        "base": str(base),
        "cause": SegmentCause.MODIFICATION.value,
        "measured_on": (
            boundary_as_of(ev)
            if after.segment.progress_measure == "TIME_ELAPSED"
            else ev.effective_date
        ).isoformat(),
        **_side(before, "before"),
        **_side(after, "after"),
        **(extra or {}),
    }
    tb.node(
        measure=f"catch_up@{ev.event_key}",
        subject_key=subject_key,
        period_key=None,
        value=value,
        currency=ctx.txn_currency,
        minor_unit=minor_unit(ctx),
        formula_id=CATCH_UP_FORMULA,
        inputs=[] if share_node is None else [share_node],
        params=params,
        exact=exact,
        narrative_key=CATCH_UP_FORMULA.rsplit(".v", 1)[0],
    )
    return value
