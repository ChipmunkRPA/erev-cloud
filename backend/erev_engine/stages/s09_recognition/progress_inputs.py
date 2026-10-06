"""Stage 09 input measures of progress (ENGINE_SPEC_B §9.2.5 S09-R-14 to S09-R-17; ENC-5).

``COST_TO_COST`` measures margin-bearing ``PROGRESS_INPUT`` costs over the ``EAC`` pin net of the
expected uninstalled materials: costs flagged ``is_wasted`` leave the numerator (606-10-55-21(a))
and costs flagged ``is_uninstalled_material`` leave both the numerator and the margin-bearing
allocation, earning revenue equal to their cost (606-10-55-21(b); POL-091; D-76). The expected
materials are the ``EAC`` parameter ``uninstalled_materials_cost``, else the materials incurred to
date (04 T-CON-13; OQ-B-05). ``LABOUR_HOURS`` reads the latest ``PROGRESS_RECORDED.hours_to_date``
over the pin's ``expected_quantity`` (S09-R-15). ``COST_RECOVERY`` recognises min(X, costs) while
no pin exists and becomes cost to cost from the first pin (606-10-25-37; S09-R-16). Costs above the
EAC net of materials cap f at 1 (S09-R-17). A cost-based obligation with costs and no pin gives
f = 0 and its costs wait (S09-R-16; stage 11 raises ``LOSS_EAC_MISSING`` in 605-35 scope).

The ``EAC`` pin in force at a date and ENG-06 position follows S01-R-18 over the element that names
the obligation (T-CON-12 ``obligation_id``, an ``OBLIGATIONS`` target, or an unnamed element of a
sole-obligation contract), with the S06-R-15 reading of a class N segment: the version effective at
the modification date counts from that boundary on, whatever the position of its
``ESTIMATE_CHANGED`` event, so stage 09 measures the segment with the same updated EAC stage 06
used for its catch-up. Stage 06 measures its boundaries through ``progress`` as well, so allocation
and recognition read one progress function (§9.1). Every value comes from its registered formula
(DG-KRN-EXP-04). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, rational_param
from erev_engine.money import to_fraction
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s09_recognition.progress_events import Position, admitted, concerns
from erev_engine.stages.s09_recognition.progress_time import Progress
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    EventView,
    Finding,
    ObligationState,
    SegmentCause,
)

__all__ = [
    "COST_RECOVERY_FORMULA",
    "COST_TO_COST_FORMULA",
    "INPUT_FORMULAS",
    "INPUT_METHODS",
    "LABOUR_HOURS_FORMULA",
    "UNINSTALLED_FORMULA",
    "UNINSTALLED_PARAMETER",
    "CostInputs",
    "InputProgress",
    "Materials",
    "cost_inputs",
    "eac_keys",
    "eac_version",
    "hours_to_date",
    "names",
    "progress",
]

COST_TO_COST_FORMULA: Final = "rec.progress.cost_to_cost.v1"
LABOUR_HOURS_FORMULA: Final = "rec.progress.labour_hours.v1"
COST_RECOVERY_FORMULA: Final = "rec.progress.cost_recovery.v1"
UNINSTALLED_FORMULA: Final = "rec.uninstalled_materials.v1"
INPUT_FORMULAS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "COST_TO_COST": COST_TO_COST_FORMULA,
        "LABOUR_HOURS": LABOUR_HOURS_FORMULA,
        "COST_RECOVERY": COST_RECOVERY_FORMULA,
    }
)
INPUT_METHODS: Final = frozenset(INPUT_FORMULAS)
UNINSTALLED_PARAMETER: Final = "uninstalled_materials_cost"  # 04 T-CON-13 EAC parameter
_COST_EVENT: Final = "COST_INCURRED"
_PROGRESS_INPUT: Final = "PROGRESS_INPUT"
_PROGRESS_EVENT: Final = "PROGRESS_RECORDED"
_EAC: Final = "EAC"
_EAC_IAS37: Final = "EAC_IAS37"  # the IAS 37.68A element stage 11 reads (S11-R-15), never progress
_NON_FINITE: Final = "NON_FINITE_AMOUNT"
_NET_NOT_POSITIVE: Final = "EAC_NET_OF_MATERIALS_NOT_POSITIVE"
_HOURS_MISSING: Final = "EXPECTED_HOURS_MISSING"
_TERMINATION_RULE: Final = "S09-R-06"
_BEFORE_BOUNDARY: Final = (
    "BEFORE_BOUNDARY"  # an OPENING_BALANCE segment before its cutover (S09-R-07)
)
_STAGE: Final = 9


@dataclass(frozen=True, slots=True)
class CostInputs:
    """``PROGRESS_INPUT`` costs of one obligation to a date and position, by S09-R-14 class."""

    margin_bearing: Fraction  # K_prog: neither wasted nor uninstalled materials
    uninstalled: Fraction  # UM_inc: costs flagged is_uninstalled_material
    wasted: Fraction  # costs flagged is_wasted (never in the EAC)

    @property
    def total(self) -> Fraction:
        """Every progress cost incurred, the S09-R-16 cost-recovery numerator."""
        return self.margin_bearing + self.uninstalled + self.wasted


@dataclass(frozen=True, slots=True)
class Materials:
    """Uninstalled materials of a cost-to-cost target (S09-R-14; ``rec.uninstalled_materials``)."""

    expected: Fraction  # UM_exp: the EAC parameter, else the materials incurred to date
    incurred: Fraction  # UM_inc: materials whose control has transferred, to the date
    base_incurred: Fraction  # UM_k at a PROSPECTIVE boundary; 0 on the inception basis

    def params(self) -> dict[str, str]:
        found = {
            "uninstalled_expected": rational_param(self.expected),
            "uninstalled_incurred": rational_param(self.incurred),
        }
        if self.base_incurred != 0:
            found["base_uninstalled"] = rational_param(self.base_incurred)
        return found


@dataclass(frozen=True, slots=True)
class InputProgress:
    """Progress of an input measure with the materials its target carries and its findings."""

    progress: Progress
    materials: Materials | None  # None when no uninstalled materials are expected or incurred
    findings: tuple[Finding, ...]
    eac: EstimateVersionInput | None  # the pin measured with, if any


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def _flag(payload: Mapping[str, object], member: str) -> bool:
    return payload.get(member) in (True, "true")


def _amount(ev: EventView, ob: ObligationState, member: str) -> Fraction:
    raw = ev.payload.get(member)
    if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal | Fraction):
        raise _invariant(
            f"a measure event carries no {member}", ob, rule="CV-45", event_key=ev.event_key
        )
    value = to_fraction(raw)
    if value < 0:
        raise _invariant(
            f"a measure event {member} is negative", ob, rule="CV-45", event_key=ev.event_key
        )
    return value


def _sole(st: AllocatedState, ob: ObligationState) -> bool:
    return sum(1 for item in st.obligations if item.contract_key == ob.contract_key) == 1


def names(st: AllocatedState, ev: EventView, ob: ObligationState) -> bool:
    """The event names the obligation, or names none on a sole-obligation contract (S01-R-16)."""
    if concerns(ev, ob):
        return True
    return (
        ev.contract_key == ob.contract_key
        and ev.payload.get("obligation_key") is None
        and not ev.obligation_subject_keys
        and _sole(st, ob)
    )


def cost_inputs(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None = None
) -> CostInputs:
    """``PROGRESS_INPUT`` costs of ``ob`` on or before ``d`` at ``position`` (S09-R-14)."""
    margin = uninstalled = wasted = Fraction(0)
    for ev in st.measure_events:
        if ev.event_type != _COST_EVENT or ev.payload.get("purpose") != _PROGRESS_INPUT:
            continue
        if not admitted(ev, d, position) or not names(st, ev, ob):
            continue
        amount = _amount(ev, ob, "amount")
        if _flag(ev.payload, "is_uninstalled_material"):
            uninstalled += amount
        elif _flag(ev.payload, "is_wasted"):
            wasted += amount
        else:
            margin += amount
    return CostInputs(margin, uninstalled, wasted)


def hours_to_date(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None = None
) -> Fraction:
    """The latest ``PROGRESS_RECORDED.hours_to_date`` with ``measure = LABOUR_HOURS`` (S09-R-15)."""
    latest: tuple[tuple[date, int, str], Fraction] | None = None
    for ev in st.measure_events:
        if ev.event_type != _PROGRESS_EVENT or ev.payload.get("measure") != "LABOUR_HOURS":
            continue
        if not admitted(ev, d, position) or not names(st, ev, ob):
            continue
        if ev.payload.get("hours_to_date") is None:
            continue
        if latest is None or ev.order_key > latest[0]:
            latest = (ev.order_key, _amount(ev, ob, "hours_to_date"))
    return Fraction(0) if latest is None else latest[1]


def eac_keys(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment | None = None
) -> tuple[str, ...]:
    """Estimate keys of the ``EAC`` element measuring ``ob`` (T-CON-12; S09-R-14).

    The segment's ``eac_element_code`` when stage 06 or a test named one; otherwise the contract's
    ``EAC`` elements that name the obligation (``obligation_key``, or an ``OBLIGATIONS`` target),
    or an unnamed element when the obligation is the contract's only one (S11-R-15 reads the
    ``EAC_IAS37`` element for loss tests; it never measures progress). More than one element
    fails closed.
    """
    if seg is not None and seg.totals.eac_element_code is not None:
        return (obligation_subject_key(ob.contract_key, seg.totals.eac_element_code),)
    contract = contract_subject_key(ob.contract_key)
    sole = _sole(st, ob)
    found: list[str] = []
    for key in sorted(st.estimates.pins):
        if key.rsplit("/", 1)[0] != contract:
            continue
        pins = st.estimates.pins[key]
        if not pins:
            continue
        version = pins[0].version
        if version.estimate_kind != _EAC or version.element_code == _EAC_IAS37:
            continue
        named = version.obligation_key == ob.obligation_key or (
            ob.obligation_key in version.target_obligation_keys
        )
        unnamed = version.obligation_key is None and not version.target_obligation_keys
        if named or (unnamed and sole):
            found.append(key)
    if len(found) > 1:
        raise _invariant(
            "more than one EAC element measures the obligation",
            ob,
            rule="S09-R-14",
            estimate_keys=",".join(found),
        )
    return tuple(found)


def _boundary_order_key(
    st: AllocatedState, ob: ObligationState, event_key: str
) -> tuple[date, int, str]:
    for ev in st.events:
        if ev.event_key == event_key:
            return ev.order_key
    raise _invariant("the boundary event of a segment is absent", ob, rule="CV-60")


def _updated_through(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None
) -> date | None:
    """The latest class N boundary in force: its EAC pin effective at d counts from it on
    (S06-R-15), whatever the ENG-06 position of the version's ``ESTIMATE_CHANGED`` event."""
    latest: date | None = None
    for seg in ob.segments:
        if (
            seg.component != "FIXED"
            or seg.basis != "INCEPTION"
            or seg.cause != SegmentCause.MODIFICATION
            or seg.event_key is None
            or seg.effective_date > d
        ):
            continue
        if position is not None and not position.admits(_boundary_order_key(st, ob, seg.event_key)):
            continue
        latest = seg.effective_date if latest is None else max(latest, seg.effective_date)
    return latest


def eac_version(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment | None,
    d: date,
    position: Position | None = None,
) -> EstimateVersionInput | None:
    """The ``EAC`` version in force for ``ob`` at ``d`` and ``position`` (S01-R-18; S06-R-15).

    The version with the greatest ``effective_date`` on or before ``d`` (ties: greater
    ``version_no``) among versions whose ``ESTIMATE_CHANGED`` event the position admits, plus,
    from a class N boundary on, every version effective on or before that boundary date.
    """
    keys = eac_keys(st, ob, seg)
    if not keys:
        return None
    through = _updated_through(st, ob, d, position)
    candidates: list[EstimateVersionInput] = []
    for key in keys:
        for pin in st.estimates.pins.get(key, ()):
            version = pin.version
            if version.effective_date > d:
                continue
            if position is None or position.admits(pin.applies()):  # D-92 (1)/(1a)
                candidates.append(version)
            elif through is not None and version.effective_date <= through:
                candidates.append(version)
    return max(
        candidates,
        key=lambda version: (version.effective_date, version.version_no),
        default=None,
    )


def _evaluate(ob: ObligationState, formula_id: str, params: dict[str, str]) -> Progress:
    frozen = MappingProxyType(dict(sorted(params.items())))
    try:
        value = FORMULAS[formula_id]((), frozen)
    except ValueError as error:
        raise EngineError(
            _NON_FINITE,
            "progress is undefined for the obligation",
            subject_key=ob.subject_key,
            formula_id=formula_id,
            detail={"rule": "CV-32"},
        ) from error
    return Progress(value, formula_id, frozen)


def _finding(ob: ObligationState, reason: str, rule: str, eac: EstimateVersionInput) -> Finding:
    detail = {"reason": reason, "rule": rule, "eac_version": eac.version_key}
    return Finding(_NON_FINITE, "ERROR", ob.subject_key, detail, _STAGE, None)


def _before_boundary(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment
) -> tuple[date, Position]:
    if seg.event_key is None:
        raise _invariant("a PROSPECTIVE segment has no boundary event", ob, rule="CV-62")
    boundary = _boundary_order_key(st, ob, seg.event_key)
    return boundary[0], Position(boundary, inclusive=False)


def _parameter(eac: EstimateVersionInput, ob: ObligationState) -> Fraction | None:
    raw = eac.parameters.get(UNINSTALLED_PARAMETER)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal | Fraction):
        raise _invariant(
            "the EAC parameter uninstalled_materials_cost is malformed",
            ob,
            rule="S09-R-14",
            eac_version=eac.version_key,
        )
    value = to_fraction(raw)
    if value < 0:
        raise _invariant(
            "the EAC parameter uninstalled_materials_cost is negative",
            ob,
            rule="S09-R-14",
            eac_version=eac.version_key,
        )
    return value


def _cost_to_cost(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None,
    eac: EstimateVersionInput,
    params: dict[str, str],
) -> InputProgress:
    costs = cost_inputs(st, ob, d, position)
    if eac.expected_total_amount is None:
        raise _invariant(
            "an EAC version measuring cost to cost has no expected_total_amount",
            ob,
            rule="S09-R-14",
            eac_version=eac.version_key,
        )
    total = to_fraction(eac.expected_total_amount)
    parameter = _parameter(eac, ob)
    expected = costs.uninstalled if parameter is None else parameter
    base_costs = base_materials = Fraction(0)
    if seg.basis == "PROSPECTIVE":
        boundary_date, before = _before_boundary(st, ob, seg)
        at_boundary = cost_inputs(st, ob, boundary_date, before)
        base_costs, base_materials = at_boundary.margin_bearing, at_boundary.uninstalled
        params["base_costs"] = rational_param(base_costs)
    params["costs"] = rational_param(costs.margin_bearing)
    params["eac"] = rational_param(total)
    params["eac_version"] = eac.version_key
    params["uninstalled_expected"] = rational_param(expected)
    if costs.wasted != 0:
        params["wasted"] = rational_param(costs.wasted)
    findings: tuple[Finding, ...] = ()
    if total - expected <= 0 and costs.margin_bearing > 0:
        params["reason"] = _NET_NOT_POSITIVE
        findings = (_finding(ob, _NET_NOT_POSITIVE, "S09-R-14", eac),)
    materials: Materials | None = None
    if expected != 0 or costs.uninstalled != 0:
        materials = Materials(expected, costs.uninstalled, base_materials)
    return InputProgress(_evaluate(ob, COST_TO_COST_FORMULA, params), materials, findings, eac)


def _labour_hours(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None,
    eac: EstimateVersionInput,
    params: dict[str, str],
) -> InputProgress:
    hours = hours_to_date(st, ob, d, position)
    if seg.basis == "PROSPECTIVE":
        boundary_date, before = _before_boundary(st, ob, seg)
        params["base_hours"] = rational_param(hours_to_date(st, ob, boundary_date, before))
    params["hours"] = rational_param(hours)
    params["eac_version"] = eac.version_key
    findings: tuple[Finding, ...] = ()
    if eac.expected_quantity is None:
        params["reason"] = _HOURS_MISSING
        if hours > 0:
            findings = (_finding(ob, _HOURS_MISSING, "S09-R-15", eac),)
    else:
        params["expected_hours"] = rational_param(to_fraction(eac.expected_quantity))
    return InputProgress(_evaluate(ob, LABOUR_HOURS_FORMULA, params), None, findings, eac)


def _cost_recovery(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None,
    params: dict[str, str],
) -> InputProgress:
    """E = min(X, costs) on the inception basis; since a boundary the costs incurred since it over
    the remaining allocation X − b_k, so an imported baseline is never counted twice (CV-62)."""
    costs = cost_inputs(st, ob, d, position)
    if seg.basis == "PROSPECTIVE":
        boundary_date, before = _before_boundary(st, ob, seg)
        params["base_costs"] = rational_param(cost_inputs(st, ob, boundary_date, before).total)
        params["base_revenue_exact"] = rational_param(seg.base_revenue_exact)
    params["costs"] = rational_param(costs.total)
    params["x_exact"] = rational_param(seg.x_exact)
    return InputProgress(_evaluate(ob, COST_RECOVERY_FORMULA, params), None, (), None)


def _precedes_boundary(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None,
) -> bool:
    """The evaluation precedes the segment's boundary event: only an ``OPENING_BALANCE`` segment is
    in force before its cutover, where it applies with progress 0 (S09-R-07; S07-INV-01)."""
    if seg.basis != "PROSPECTIVE" or seg.event_key is None:
        return False
    boundary = _boundary_order_key(st, ob, seg.event_key)
    if d < boundary[0]:
        return True
    return position is not None and not position.admits(boundary)


def _waiting(
    ob: ObligationState, method: str, params: dict[str, str], *, hours: bool
) -> InputProgress:
    """f = 0 while no ``EAC`` pin exists: the costs wait (S09-R-16); no stage 09 finding."""
    params["reason"] = "EAC_PIN_MISSING"
    if hours:
        params["hours"] = "0"
        params["expected_hours"] = "0"
    else:
        params["costs"] = "0"
        params["eac"] = "0"
        params["uninstalled_expected"] = "0"
    return InputProgress(_evaluate(ob, INPUT_FORMULAS[method], params), None, (), None)


def progress(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None = None,
) -> InputProgress:
    """f(d) on the inception basis, or g(d) since a boundary, of an input measure (§9.2.5).

    ``COST_RECOVERY`` measures min(X, costs) ÷ X while no ``EAC`` pin exists and cost to cost from
    the first pin (S09-R-16). A ``TERMINATION`` segment gives f = 1 from its effective date
    (S09-R-06). A cost-based obligation without a pin gives f = 0 and its costs wait.
    """
    method = str(ob.recognition_method)
    formula_id = INPUT_FORMULAS.get(method)
    if formula_id is None:
        raise _invariant("the measure is not an input measure", ob, rule="S09-R-02", method=method)
    params: dict[str, str] = {"as_of": d.isoformat()}
    if seg.cause == SegmentCause.TERMINATION:
        params["rule"] = _TERMINATION_RULE
        return InputProgress(_evaluate(ob, formula_id, params), None, (), None)
    if _precedes_boundary(st, ob, seg, d, position):
        params["reason"] = _BEFORE_BOUNDARY  # the target is the imported baseline (S09-R-07)
        return InputProgress(_evaluate(ob, formula_id, params), None, (), None)
    eac = eac_version(st, ob, seg, d, position)
    if method == "COST_RECOVERY":
        if eac is None:
            return _cost_recovery(st, ob, seg, d, position, params)
        params["measure"] = "COST_RECOVERY"  # S09-R-16: cost to cost from the first pin
        return _cost_to_cost(st, ob, seg, d, position, eac, params)
    if method == "LABOUR_HOURS":
        if eac is None:
            return _waiting(ob, method, params, hours=True)
        return _labour_hours(st, ob, seg, d, position, eac, params)
    if eac is None:
        return _waiting(ob, method, params, hours=False)
    return _cost_to_cost(st, ob, seg, d, position, eac, params)
