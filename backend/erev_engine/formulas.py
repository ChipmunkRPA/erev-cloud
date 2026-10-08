"""Formula registry for trace re-evaluation (dev-guide §5.16 DG-KRN-EXP-04; ENGINE_SPEC CV-52).

A formula id ``<area>.<name>.v<n>`` names a pure function of a node's input values, in input
order, and its params. Posted amounts enter and leave in currency units; a posted node carries its
minor unit in ``params["minor_unit"]``. Stage items register their formula ids here as they land.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates, progress
from erev_engine.enums import ContractStatus
from erev_engine.money import (
    EXACT_PLACES,
    cumulative_posted,
    format_exact,
    largest_remainder,
    round_half_up,
    to_fraction,
)

__all__ = [
    "EXACT_INPUT_FORMULAS",
    "FORMULAS",
    "FORMULA_ID",
    "Formula",
    "minor_unit_of",
    "periods_param",
    "rational_param",
    "rpo_bands",
]

Formula = Callable[[Sequence[Fraction], Mapping[str, str]], Fraction]

FORMULA_ID: Final = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)+\.v[0-9]+")
_MINOR_UNIT: Final = re.compile(r"[0-9]{1,2}")
_RATIONAL: Final = re.compile(r"-?[0-9]+(?:/[0-9]+)?")
_ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def rational_param(x: Fraction) -> str:
    """An exact rational as a node parameter: ``"<n>"`` or ``"<n>/<d>"`` (no precision lost)."""
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def periods_param(periods: Iterable[dates.DateRange]) -> str:
    """Accounting periods as ``start/end`` ISO pairs joined by ``;`` (ALG-11 calendar input)."""
    return ";".join(f"{p.start_date.isoformat()}/{p.end_date.isoformat()}" for p in periods)


def minor_unit_of(params: Mapping[str, str]) -> int:
    """The minor unit a posted node records in ``params["minor_unit"]``."""
    value = params.get("minor_unit")
    if value is None or not _MINOR_UNIT.fullmatch(value):
        raise ValueError("params must hold minor_unit as a decimal string")
    return int(value)


def _require_arity(inputs: Sequence[Fraction], arity: int, formula_id: str) -> None:
    if len(inputs) != arity:
        raise ValueError(f"{formula_id} takes {arity} inputs, not {len(inputs)}")


def _cumulative_posted(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.cumulative_posted.v1``: inputs (X, A, f); C_t of ALG-01 §2.1.3 in currency units."""
    _require_arity(inputs, 3, "sched.cumulative_posted.v1")
    exact_allocation, posted_allocation, progress = inputs
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    posted_minor = posted_allocation * scale
    if posted_minor.denominator != 1:
        raise ValueError("the posted allocation is not a whole number of minor units")
    posted = cumulative_posted(exact_allocation, posted_minor.numerator, progress, minor_unit)
    return Fraction(posted, scale)


def _period_difference(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.period_difference.v1``: inputs (C_t, C_(t−1)); the period amount C_t − C_(t−1)."""
    _require_arity(inputs, 2, "sched.period_difference.v1")
    current, previous = inputs
    return current - previous


# --- Stage 09 recognition (ENGINE_SPEC_B §9.5; BUILD_SPEC ENC-1) ----------------------------------


def _param(params: Mapping[str, str], name: str) -> str:
    value = params.get(name)
    if value is None:
        raise ValueError(f"params must hold {name}")
    return value


def _rational(params: Mapping[str, str], name: str) -> Fraction:
    value = _param(params, name)
    if not _RATIONAL.fullmatch(value):
        raise ValueError(f"params {name} must be an integer or a ratio of integers")
    return Fraction(value)


def _date(params: Mapping[str, str], name: str) -> date:
    value = _param(params, name)
    if not _ISO_DATE.fullmatch(value):
        raise ValueError(f"params {name} must be a YYYY-MM-DD date")
    return date.fromisoformat(value)


def _calendar(params: Mapping[str, str]) -> tuple[dates.MonthPeriod, ...] | None:
    # Absent: calendar months (E-50 MONTHLY); otherwise the entity's covering periods.
    value = params.get("periods")
    if value is None:
        return None
    periods = []
    for pair in value.split(";"):
        start, _, end = pair.partition("/")
        if not (_ISO_DATE.fullmatch(start) and _ISO_DATE.fullmatch(end)):
            raise ValueError("params periods must be start/end ISO date pairs")
        periods.append(dates.MonthPeriod(date.fromisoformat(start), date.fromisoformat(end)))
    return tuple(periods)


def _time_elapsed(convention: str, params: Mapping[str, str]) -> Fraction:
    """ALG-11 f(as_of) over [start, end] with the stage 09 edges (S09-R-06, S09-R-09, CV-62)."""
    start, end, as_of = _date(params, "start"), _date(params, "end"), _date(params, "as_of")
    if params.get("pending") == "true":  # custodial start not yet known (S09-R-09)
        return Fraction(0)
    if params.get("rule") == "S09-R-06" or start > end:  # termination, or no remaining term
        return Fraction(1) if as_of >= start else Fraction(0)
    return progress.time_fraction(convention, start, end, as_of, calendar=_calendar(params))


def _time_formula(convention: str) -> Formula:
    formula_id = f"rec.progress.time_elapsed.{convention.lower()}.v1"

    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``rec.progress.time_elapsed.<convention>.v1``: no inputs; params start, end, as_of."""
        _require_arity(inputs, 0, formula_id)
        return _time_elapsed(convention, params)

    return formula


def _prospective_segment(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.prospective_segment.v1``: g(as_of) since a boundary (CV-62; ALG-11 rule 5).

    No inputs. Params ``measure`` ``TIME_ELAPSED`` with ``convention``, ``start`` (the boundary
    date), ``end`` and ``as_of``: the convention restarts over the remaining term.
    """
    _require_arity(inputs, 0, "rec.progress.prospective_segment.v1")
    measure = _param(params, "measure")
    if measure != "TIME_ELAPSED":
        raise ValueError(f"rec.progress.prospective_segment.v1 does not measure {measure}")
    return _time_elapsed(_param(params, "convention"), params)


def _point_in_time(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.point_in_time.v1``: (N_c − Y − N_k) ÷ Q′, capped at 1 (§9.2.4; CV-61, CV-62).

    ``transferred`` counts control-transferring deliveries only (S09-R-11 to S09-R-13); ``returned``
    is the units returned (§9.2.4 "less returns"); ``base`` is N_k since a boundary.
    """
    _require_arity(inputs, 0, "rec.progress.point_in_time.v1")
    if params.get("expired") == "true":  # JET-08: an expired option recognises its remainder
        return Fraction(1)
    net = _rational(params, "transferred") - _rational(params, "returned")
    return progress.units_fraction(net - _rational(params, "base"), _rational(params, "quantity"))


def _units(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.units.v1``: (N − Y − N_k) ÷ Q′ over every delivery, capped at 1 (S09-R-10).

    Q′ is ``totals.quantity`` of the segment in force, the remaining quantity RQ_k since a boundary
    (CV-62). A remaining total of 0 with nothing delivered since the boundary gives 1.
    """
    _require_arity(inputs, 0, "rec.progress.units.v1")
    if params.get("expired") == "true":  # JET-08: an expired option recognises its remainder
        return Fraction(1)
    net = _rational(params, "delivered") - _rational(params, "returned")
    return progress.units_fraction(net - _rational(params, "base"), _rational(params, "quantity"))


def _output_percent(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.output_percent.v1``: p(d), or (p(d) − p_k) ÷ (1 − p_k) since a boundary."""
    _require_arity(inputs, 0, "rec.progress.output_percent.v1")
    return progress.output_fraction(_rational(params, "ratio"), _rational(params, "base"))


def _milestone(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.milestone.v1``: w(d), or (w(d) − w_k) ÷ (1 − w_k) since a boundary."""
    _require_arity(inputs, 0, "rec.progress.milestone.v1")
    return progress.milestone_fraction(_rational(params, "weight"), _rational(params, "base"))


def _optional_rational(params: Mapping[str, str], name: str, default: Fraction) -> Fraction:
    return _rational(params, name) if name in params else default


def _right_to_invoice(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.right_to_invoice.v1``: the right to invoice R over the line's stated price P,
    capped at 1 (ENGINE_SPEC_B S09-R-18 rev 1.20, §9.2.4; D-98 candidate 28; ENC-6).

    No inputs. Params ``realised`` (R for performance to ``as_of``, S09-R-18 source order),
    ``stated`` (P) and, since a boundary, ``base_realised`` (R_k before it): f = min(1, R ÷ P),
    g = min(1, (R − R_k) ÷ (P − R_k)); a denominator that is not positive gives 1 (only read with
    P > 0: a P = 0 component takes the time-elapsed signal, §9.2.4 rev 1.16, or ``reason``
    ``OPEN_TERM`` = 0 without an end date); R below R_k gives 0.
    """
    formula_id = "rec.progress.right_to_invoice.v1"
    _require_arity(inputs, 0, formula_id)
    if params.get("reason") == "OPEN_TERM":
        return Fraction(0)  # ENC6-R3: a zero rate line without an end date never completes
    stated = _rational(params, "stated")
    base = _optional_rational(params, "base_realised", Fraction(0))
    if stated < 0 or base < 0:
        raise ValueError(f"{formula_id}: stated and base_realised must be non-negative")
    return progress.right_to_invoice_fraction(_rational(params, "realised"), stated, base)


def _cost_to_cost(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.cost_to_cost.v1``: margin-bearing costs ÷ (EAC − expected uninstalled
    materials), capped at 1 (S09-R-14, S09-R-17; ENC-5).

    No inputs. Params ``costs`` (margin-bearing ``PROGRESS_INPUT`` costs to ``as_of``: wasted and
    uninstalled-material costs excluded), ``eac`` (the pin's ``expected_total_amount``),
    ``uninstalled_expected`` (the ``EAC`` parameter ``uninstalled_materials_cost``, else the
    materials incurred to date) and, since a boundary, ``base_costs`` (K_k, the margin-bearing
    costs before it; CV-62). A ``reason`` of ``EAC_NET_OF_MATERIALS_NOT_POSITIVE`` records the
    S09-R-14 ``NON_FINITE_AMOUNT`` case and gives 0.
    """
    formula_id = "rec.progress.cost_to_cost.v1"
    _require_arity(inputs, 0, formula_id)
    if params.get("rule") == "S09-R-06":
        return Fraction(1)  # a TERMINATION segment is complete from its effective date
    if params.get("reason") == "BEFORE_BOUNDARY":
        return Fraction(0)  # an OPENING_BALANCE segment before its cutover (S09-R-07)
    costs = _rational(params, "costs")
    denominator = _rational(params, "eac") - _rational(params, "uninstalled_expected")
    base = _optional_rational(params, "base_costs", Fraction(0))
    if costs < 0 or base < 0 or base > costs:
        raise ValueError(f"{formula_id}: costs and base_costs must be non-negative and ordered")
    if params.get("reason") == "EAC_NET_OF_MATERIALS_NOT_POSITIVE":
        if denominator > 0:
            raise ValueError(f"{formula_id}: reason recorded with a positive denominator")
        return Fraction(0)
    if denominator <= 0:
        if costs == 0:
            return Fraction(0)
        raise ValueError(f"{formula_id}: EAC net of materials is not positive")
    if base > 0 and denominator - base <= 0:
        return Fraction(1)  # the boundary consumed the whole EAC (CV-62)
    return progress.cost_fraction(costs - base, denominator - base)


def _labour_hours(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.labour_hours.v1``: hours to date ÷ expected total hours, capped at 1
    (S09-R-15; ENC-5).

    No inputs. Params ``hours`` (the latest ``PROGRESS_RECORDED.hours_to_date`` with ``measure``
    ``LABOUR_HOURS`` at or before ``as_of``), ``expected_hours`` (the ``EAC`` pin's
    ``expected_quantity``) and, since a boundary, ``base_hours`` (h_k; CV-62). A ``reason`` of
    ``EXPECTED_HOURS_MISSING`` records the S09-R-15 ``NON_FINITE_AMOUNT`` case and gives 0.
    """
    formula_id = "rec.progress.labour_hours.v1"
    _require_arity(inputs, 0, formula_id)
    if params.get("rule") == "S09-R-06":
        return Fraction(1)  # a TERMINATION segment is complete from its effective date
    if params.get("reason") == "BEFORE_BOUNDARY":
        return Fraction(0)  # an OPENING_BALANCE segment before its cutover (S09-R-07)
    hours = _rational(params, "hours")
    base = _optional_rational(params, "base_hours", Fraction(0))
    if hours < 0 or base < 0 or base > hours:
        raise ValueError(f"{formula_id}: hours and base_hours must be non-negative and ordered")
    if params.get("reason") == "EXPECTED_HOURS_MISSING":
        if "expected_hours" in params:
            raise ValueError(f"{formula_id}: reason recorded with expected hours")
        return Fraction(0)
    expected = _rational(params, "expected_hours")
    if expected <= 0:
        if hours == 0:
            return Fraction(0)
        raise ValueError(f"{formula_id}: expected hours are not positive")
    if base > 0 and expected - base <= 0:
        return Fraction(1)
    return progress.hours_fraction(hours - base, expected - base)


def _cost_recovery(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.cost_recovery.v1``: f = min(X, costs incurred to date) ÷ X while no
    approved ``EAC`` pin exists (606-10-25-37; S09-R-16; ENC-5).

    No inputs. Params ``costs`` (every ``PROGRESS_INPUT`` cost to ``as_of``) and ``x_exact`` (X of
    the segment in force). Since a boundary (``base_costs`` K_k and ``base_revenue_exact`` b_k
    present) g = min(1, (costs − K_k) ÷ (X − b_k)): the costs incurred since the boundary over the
    remaining allocation, so the revenue at the boundary is never counted twice (CV-62). X ≤ 0, or
    no remaining allocation, gives 0; ``reason`` ``BEFORE_BOUNDARY`` gives 0 (S09-R-07).
    """
    formula_id = "rec.progress.cost_recovery.v1"
    _require_arity(inputs, 0, formula_id)
    if params.get("rule") == "S09-R-06":
        return Fraction(1)  # a TERMINATION segment is complete from its effective date
    if params.get("reason") == "BEFORE_BOUNDARY":
        return Fraction(0)
    costs = _rational(params, "costs")
    allocation = _rational(params, "x_exact")
    if costs < 0:
        raise ValueError(f"{formula_id}: costs must be non-negative")
    if "base_revenue_exact" in params:
        base_costs = _optional_rational(params, "base_costs", Fraction(0))
        remaining = allocation - _rational(params, "base_revenue_exact")
        if base_costs < 0 or base_costs > costs:
            raise ValueError(f"{formula_id}: base_costs must be non-negative and not above costs")
        if remaining <= 0:
            return Fraction(0)
        return min(Fraction(1), (costs - base_costs) / remaining)
    if allocation <= 0:
        return Fraction(0)
    return min(Fraction(1), costs / allocation)


def _uninstalled_materials(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.uninstalled_materials.v1``: input (f); the exact target of a cost-to-cost component
    with uninstalled materials (S09-R-14; POL-091; D-76; ENC-5).

    Inception basis: E = f × (X − UM_exp) + UM_inc, with ``x_exact``, ``uninstalled_expected``
    (UM_exp) and ``uninstalled_incurred`` (UM_inc, the materials whose control has transferred).
    Since a boundary (``base_revenue_exact`` b_k and ``base_uninstalled`` UM_k present): E = b_k +
    g × (X − b_k − (UM_exp − UM_k)) + (UM_inc − UM_k). The materials earn revenue equal to their
    cost and never enter the margin-bearing progress.
    """
    formula_id = "rec.uninstalled_materials.v1"
    progress_exact = _exact_progress(inputs, params, formula_id)
    allocation = _rational(params, "x_exact")
    expected = _rational(params, "uninstalled_expected")
    incurred = _rational(params, "uninstalled_incurred")
    if expected < 0 or incurred < 0:
        raise ValueError(f"{formula_id}: uninstalled materials must be non-negative")
    if "base_revenue_exact" not in params:
        return progress_exact * (allocation - expected) + incurred
    base = _rational(params, "base_revenue_exact")
    base_materials = _optional_rational(params, "base_uninstalled", Fraction(0))
    remaining = allocation - base - (expected - base_materials)
    return base + progress_exact * remaining + (incurred - base_materials)


def _exact_param(
    inputs: Sequence[Fraction], params: Mapping[str, str], name: str, formula_id: str
) -> Fraction:
    # A node value is an 18-place string, so a product of it would amplify its rounding. The exact
    # value travels in params[name] and must agree with the single node input it cites (CV-52).
    _require_arity(inputs, 1, formula_id)
    exact = _rational(params, name)
    if format_exact(exact) != format_exact(inputs[0]):
        raise ValueError(f"{formula_id}: params {name} disagrees with its input")
    return exact


def _exact_progress(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> Fraction:
    return _exact_param(inputs, params, "progress", formula_id)


PROGRESS_UNMEASURED_REASONS: Final = frozenset({"V5", "S09-R-13:LEASE", "no-fixed-component"})


def _progress_unmeasured(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.progress.unmeasured.v1`` (ENGINE_SPEC CV-50 rev 1.31; ENGINE_SPEC_B §9.5 rev 1.36;
    T1F-LP-PR-1): the progress of an obligation whose target is under a V4 / V5 / S09-R-13 guard,
    or which has no ``FIXED`` component — 0 BY RULE (S02-R-03), never a measurement. Arity 0;
    params ``as_of`` and ``reason`` (the guard string with its status, ``V5``, ``S09-R-13:LEASE``
    or ``no-fixed-component``) record why, so the zero replays with its cause."""
    formula_id = "rec.progress.unmeasured.v1"
    _require_arity(inputs, 0, formula_id)
    reason = params.get("reason", "")
    if not (reason.startswith("V4:") or reason in PROGRESS_UNMEASURED_REASONS):
        raise ValueError(
            f"{formula_id}: params reason {reason!r} names no guard or missing component"
        )
    if "as_of" not in params:
        raise ValueError(f"{formula_id}: params as_of is required")
    return Fraction(0)


def _exact_endpoint(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.exact_endpoint.v1`` (ENGINE_SPEC CV-64 rev 1.30; T1F-89-1): the exact revenue target E
    at ONE ENG-06 endpoint (before / after) of an admitted event — Σ of the ``FIXED`` exact
    endpoint node and the admitted realised ``PERIOD_VC`` amounts (money sources). Params
    ``exact`` — the raw E — is accepted only when it binds to the cited inputs within the CV-51
    limit and is returned (the sum stands without it); a guarded endpoint (params ``guard``) takes
    no inputs and is the defined 0 (S02-R-03)."""
    formula_id = "rec.exact_endpoint.v1"
    if "guard" in params:
        _require_arity(inputs, 0, formula_id)
        return Fraction(0)
    total = sum(inputs, Fraction(0))
    if "exact" not in params:
        return total
    exact = _rational(params, "exact")
    if not binds_encoded(exact, inputs):
        raise ValueError(
            f"{formula_id}: params exact {rational_param(exact)} is not bound to the cited inputs "
            f"{rational_param(total)} (CV-51 encoding limit)"
        )
    return exact


def _exact_difference(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.exact_difference.v1`` (CV-64 rev 1.30): inputs (after, before) — the two exact endpoint
    nodes of one admitted event, fixed signs; params ``after`` / ``before`` are the raw operands,
    each accepted only when it binds to its cited input within the CV-51 limit; returns after −
    before (raw when the params are given, the decoded difference otherwise)."""
    formula_id = "rec.exact_difference.v1"
    _require_arity(inputs, 2, formula_id)
    if ("after" in params) != ("before" in params):
        raise ValueError(f"{formula_id}: params after and before come together")
    if "after" in params:
        after, before = _rational(params, "after"), _rational(params, "before")
        for name, operand, cited in (("after", after, inputs[0]), ("before", before, inputs[1])):
            if not binds_encoded(operand, [cited]):
                raise ValueError(
                    f"{formula_id}: params {name} {rational_param(operand)} is not bound to the "
                    f"cited input {rational_param(cited)} (CV-51 encoding limit)"
                )
    else:
        after, before = inputs[0], inputs[1]
    return after - before


def _exact_activity(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.exact_activity.v1`` (CV-64 rev 1.30): the exact revenue activity of a version — Σ of
    the admitted events' ``revenue_exact_delta@`` nodes, multiplicity preserved (no admitted
    event: the defined 0). Params ``exact`` — the raw sum — is accepted only when it binds to the
    inputs' sum within the CV-51 limit and is returned; the sum stands without it."""
    formula_id = "rec.exact_activity.v1"
    total = sum(inputs, Fraction(0))
    if "exact" not in params:
        return total
    exact = _rational(params, "exact")
    if not binds_encoded(exact, inputs):
        raise ValueError(
            f"{formula_id}: params exact {rational_param(exact)} is not bound to the cited inputs "
            f"{rational_param(total)} (CV-51 encoding limit)"
        )
    return exact


def _target_exact_inception(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.target_exact.inception.v1``: input (f); E = X × f (CV-61, CV-63)."""
    progress_exact = _exact_progress(inputs, params, "rec.target_exact.inception.v1")
    return _rational(params, "x_exact") * progress_exact


def _target_exact_prospective(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.target_exact.prospective.v1``: input (g); E = b + (X − b) × g (CV-62, CV-63)."""
    progress_exact = _exact_progress(inputs, params, "rec.target_exact.prospective.v1")
    base = _rational(params, "base_revenue_exact")
    return base + (_rational(params, "x_exact") - base) * progress_exact


def _revenue_cum(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.revenue_cum.v1``: C_p = Σ_c C_c (S09-R-03), in currency units.

    With ``params["fixed"] == "true"`` the first input is E of the ``FIXED`` component, posted as
    ``cumulative_posted(X, A, φ)`` with X and A from params and φ = E ÷ X, or φ = 1 when
    ``params["complete"] == "true"`` (CV-63; the exact input is an 18-place string, so completion
    is recorded rather than inferred). Every other input is a realised ``PERIOD_VC`` amount, for
    which X = A = the amount and f = 1 (S09-R-02). A ``guard`` param (V4 status or V5 start)
    gives 0.
    """
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    if params.get("adjusted") == "true":  # the last node of S09-R-41: manual adjustments, holds
        _require_arity(inputs, 1, "rec.revenue_cum.v1")
        return inputs[0]
    if "guard" in params:
        _require_arity(inputs, 0, "rec.revenue_cum.v1")
        return Fraction(0)
    realised = list(inputs)
    posted = 0
    if params.get("fixed") == "true":
        if not realised:
            raise ValueError("rec.revenue_cum.v1 needs the FIXED exact target as its first input")
        exact = realised.pop(0)
        exact_allocation = _rational(params, "x_exact")
        posted_allocation = int(_rational(params, "a_posted"))
        if exact_allocation != 0:
            complete = params.get("complete") == "true"
            ratio = Fraction(1) if complete else exact / exact_allocation
            posted = cumulative_posted(exact_allocation, posted_allocation, ratio, minor_unit)
    for amount in realised:
        scaled = amount * scale
        if scaled.denominator != 1:
            raise ValueError("a realised amount is not a whole number of minor units")
        posted += scaled.numerator
    return Fraction(posted, scale)


# --- Stage 09 breakage and royalties (ENGINE_SPEC_B §9.2.8, §9.2.9; BUILD_SPEC ENC-8) ------------


def _breakage_part(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> Fraction:
    """The posted parts of a redemption target, in currency units (S09-R-27, S09-R-28).

    ``part = breakage``: input 0 is C_total; C_breakage = C_total − min(round(X × R ÷ Q), C_total)
    with X ``x_exact``, R ``redeemed`` and Q ``quantity``. ``part = escheat``: A − C_total with A
    ``a_posted`` in minor units (the unclaimed-property amount at expiry). Further inputs are the
    cited estimate version (its ``expected_quantity``), read for lineage only.
    """
    if not inputs:
        raise ValueError(f"{formula_id} needs the cumulative target as input 0")
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    total = _minor_value(inputs[0], minor_unit, formula_id)
    part = _param(params, "part")
    if part == "breakage":
        quantity = _rational(params, "quantity")
        if quantity <= 0:
            raise ValueError(f"{formula_id} needs the units issued")
        redeemed = round_half_up(
            _rational(params, "x_exact") * _rational(params, "redeemed") / quantity, minor_unit
        )
        return Fraction(total - min(redeemed, total), scale)
    if part == "escheat":
        return Fraction(int(_rational(params, "a_posted")) - total, scale)
    raise ValueError(f"{formula_id} does not know the part {part}")


def _breakage_formula(formula_id: str, mode: str) -> Formula:
    """A redemption formula: the entitlement progress E_total ÷ X (§9.2.8), or a posted part.

    ``PROPORTIONAL_TO_EXERCISE``: min(1, max(R ÷ Q, ρ × min(1, R ÷ R_exp))) with ρ = R_exp ÷ Q +
    b (params ``redeemed``, ``quantity``, ``expected``, ``rate``); ``WHEN_REMOTE``: min(1, R ÷ Q +
    b_r) where b_r = ``rate`` only when ``remote = true`` (S09-R-29); ``EXPIRY``: 1 − u (param
    ``unclaimed_share``, S09-R-28). A ``part`` param selects the posted parts instead.
    """

    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        if "part" in params:
            return _breakage_part(inputs, params, formula_id)
        _require_arity(inputs, 0, formula_id)
        if mode == "EXPIRY":
            share = _rational(params, "unclaimed_share")
            if not 0 <= share <= 1:
                raise ValueError(f"{formula_id}: the unclaimed share lies in [0, 1]")
            return 1 - share
        quantity = _rational(params, "quantity")
        redeemed = _rational(params, "redeemed")
        if quantity <= 0 or redeemed < 0:
            raise ValueError(f"{formula_id} needs positive units issued and redeemed units")
        if mode == "WHEN_REMOTE":
            rate = _rational(params, "rate") if params.get("remote") == "true" else Fraction(0)
            return min(Fraction(1), redeemed / quantity + rate)
        expected, rate = _rational(params, "expected"), _rational(params, "rate")
        if expected <= 0:
            raise ValueError(f"{formula_id}: expected redemptions must be positive")
        rho = expected / quantity + rate
        if rho > 1:
            raise ValueError(f"{formula_id}: the entitlement ratio exceeds 1")
        return min(
            Fraction(1), max(redeemed / quantity, rho * min(Fraction(1), redeemed / expected))
        )

    return formula


def _royalty_realised(formula_id: str) -> Formula:
    """``royalty.accrual.v1`` and ``royalty.minimum_guarantee.v1``: the recognised royalty of the
    ``ROYALTY`` component (S09-R-02, S09-R-33). Inputs are the counted statements and accrual
    versions (currency units); the value is max(0, Σ inputs − ``guarantee``) while ``satisfied``
    is ``true``, else 0 (the amounts await the licence's satisfaction)."""

    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        if _param(params, "satisfied") != "true":
            return Fraction(0)
        guarantee = _rational(params, "guarantee")
        return max(Fraction(0), sum(inputs, Fraction(0)) - guarantee)

    return formula


def _royalty_true_up(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``royalty.report_true_up.v1``: a statement (input 0) less the prior measurement of its usage
    period that it replaces (inputs 1 to n: the accruals it supersedes, or the statement it
    corrects), the JET-04a true-up of the statement event (S09-R-32). Param ``replaces``
    (``accrual`` or ``statement``) names the kind of measurement replaced; the arithmetic is
    the same for both."""
    if not inputs:
        raise ValueError("royalty.report_true_up.v1 needs the statement as input 0")
    return inputs[0] - sum(inputs[1:], Fraction(0))


# --- Stage 09 returns within the units measures (ENGINE_SPEC_B §9.2.7; BUILD_SPEC ENC-7) ---------

_REDUCE: Final = "REDUCE_CONTRACT_QUANTITY"
_RESTORE: Final = "RESTORE_REMAINING_QUANTITY"


def _expected_units(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.expected_units.v1``: E of ALG-06 step 1 at ``as_of`` (§9.2.7 ``return_state``).

    Input: the ``expected_quantity`` of the ``RETURN_RATE`` version in force, absent when none is.
    Params ``model`` (POL-051), ``scope`` (POL-053), ``returned_after`` (units returned after the
    version date), ``kept`` (N − Y), ``as_of`` and optional ``window_end``. E = max(0, expected −
    returned_after), never above the units kept; 0 from ``window_end`` (S09-R-26 from the end of
    the window end date; D-87 L6-5-Q-25) unless param ``expiry_pending`` is ``true`` on that day
    (a measurement among the day's events, before the expiry), under ``ACTUAL_RETURNS_ONLY`` and
    under ``RESTORE_REMAINING_QUANTITY`` (S09-R-24).
    """
    if len(inputs) > 1:
        raise ValueError(f"returns.expected_units.v1 takes at most 1 input, not {len(inputs)}")
    model, scope = _param(params, "model"), _param(params, "scope")
    if not inputs or model == "ACTUAL_RETURNS_ONLY" or scope == _RESTORE:
        return Fraction(0)
    if "window_end" in params:
        as_of, window_end = _date(params, "as_of"), _date(params, "window_end")
        pending = as_of == window_end and params.get("expiry_pending") == "true"
        if as_of >= window_end and not pending:
            return Fraction(0)
    expected = max(Fraction(0), inputs[0] - _rational(params, "returned_after"))
    return min(expected, max(Fraction(0), _rational(params, "kept")))


def _deliver(
    revenue: Fraction, x_exact: Fraction, remaining: Fraction, units: Fraction
) -> Fraction:
    # Revenue after `units` more deliveries, each at the refreshed unit rate (X − e) ÷ remaining
    # quantity (legacy 02 §3.7). The product of the refreshes telescopes; a delivery that reaches
    # the remaining quantity completes the segment (S09-R-10).
    if units <= 0:
        return revenue
    if remaining <= 0 or units >= remaining:
        return x_exact
    return x_exact - (x_exact - revenue) * (remaining - units) / remaining


def _bounded(revenue: Fraction, x_exact: Fraction) -> Fraction:
    # S09-INV-01 bound of an exact target: between 0 and X.
    return min(max(revenue, min(Fraction(0), x_exact)), max(Fraction(0), x_exact))


def _revenue_target(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.revenue_target.v1``: exact ``FIXED`` target of a units obligation with returns.

    ``scope`` ``REDUCE_CONTRACT_QUANTITY`` (S09-R-23; ALG-06 step 2): input E, the
    ``return_expected_units`` node, exactly in ``expected``; params ``unit_rate`` r,
    ``transferred`` N and ``returned`` Y; E_exact = r × (N − Y − E).

    ``RESTORE_REMAINING_QUANTITY`` (S09-R-24, S09-R-25): input the exact revenue after the latest
    return, a ``return_reversal@<event key>`` node, exactly in ``revenue_at_return``; params
    ``x_exact``, ``quantity`` Q′, ``kept_at_return`` and ``kept`` (units kept since the boundary):
    the deliveries since that return earn the refreshed unit rate.
    """
    formula_id = "returns.revenue_target.v1"
    scope = _param(params, "scope")
    if scope == _REDUCE:
        expected = _exact_param(inputs, params, "expected", formula_id)
        units = _rational(params, "transferred") - _rational(params, "returned") - expected
        return _rational(params, "unit_rate") * units
    if scope == _RESTORE:
        revenue = _exact_param(inputs, params, "revenue_at_return", formula_id)
        kept_at_return = _rational(params, "kept_at_return")
        remaining = _rational(params, "quantity") - kept_at_return
        units = _rational(params, "kept") - kept_at_return
        return _deliver(revenue, _rational(params, "x_exact"), remaining, units)
    raise ValueError(f"{formula_id} does not measure scope {scope}")


def _excess_reversal(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.excess_reversal.v1``: exact revenue after one return (S09-R-24, S09-R-25).

    Under POL-053 ``RESTORE_REMAINING_QUANTITY`` E = 0, so every returned unit is in excess of E and
    reverses at the POL-052 rate. Input: the previous ``return_reversal@`` node, exactly in
    ``revenue_prev``; or none, with ``base_revenue_exact`` b of the segment. Params ``x_exact``,
    ``quantity`` Q′, ``kept_prev`` and ``kept_before`` (units kept since the boundary after the
    previous return and before this one), ``base_kept`` N_k and ``returned``. The deliveries since
    the previous return earn the refreshed unit rate; then ``rate`` ``CURRENT_REMAINING_RATE``
    reverses at (X − e) ÷ (Q′ − kept), or at e ÷ N when nothing remains (X × f ÷ N; DEV-060), and
    ``AVERAGE_CARRYING_RATE`` at the posted cumulative revenue (params ``a_posted``,
    ``minor_unit``) ÷ the units kept. The result is bounded by S09-INV-01.
    """
    formula_id = "returns.excess_reversal.v1"
    if "base_revenue_exact" in params:
        _require_arity(inputs, 0, formula_id)
        previous = _rational(params, "base_revenue_exact")
    else:
        previous = _exact_param(inputs, params, "revenue_prev", formula_id)
    x_exact, quantity = _rational(params, "x_exact"), _rational(params, "quantity")
    kept_prev, kept_before = _rational(params, "kept_prev"), _rational(params, "kept_before")
    revenue = _deliver(previous, x_exact, quantity - kept_prev, kept_before - kept_prev)
    remaining = quantity - kept_before
    units_kept = _rational(params, "base_kept") + kept_before
    option = _param(params, "rate")
    if option == "CURRENT_REMAINING_RATE" and remaining > 0:
        rate = (x_exact - revenue) / remaining
    elif option in ("CURRENT_REMAINING_RATE", "AVERAGE_CARRYING_RATE"):
        if units_kept <= 0:
            raise ValueError(f"{formula_id}: no units are kept before the return")
        carried = revenue
        if option == "AVERAGE_CARRYING_RATE":
            minor_unit = minor_unit_of(params)
            ratio = Fraction(0) if x_exact == 0 else _bounded(revenue, x_exact) / x_exact
            posted_allocation = int(_rational(params, "a_posted"))
            posted = cumulative_posted(x_exact, posted_allocation, ratio, minor_unit)
            carried = Fraction(posted, 10**minor_unit)
        rate = carried / units_kept
    else:
        raise ValueError(f"{formula_id} does not know the reversal rate {option}")
    return _bounded(revenue - rate * _rational(params, "returned"), x_exact)


# --- Stage 09 causes, manual adjustments and holds (ENGINE_SPEC_B §9.2.10 to §9.2.12; ENC-9) -----


def _minor(params: Mapping[str, str], name: str) -> int:
    value = _rational(params, name)
    if value.denominator != 1:
        raise ValueError(f"params {name} must be whole minor units")
    return value.numerator


def _posted_input(inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str) -> int:
    # The target before the adjustment, a posted node: whole minor units.
    _require_arity(inputs, 1, formula_id)
    scale: int = 10 ** minor_unit_of(params)
    scaled = inputs[0] * scale
    if scaled.denominator != 1:
        raise ValueError(f"{formula_id}: the input target is below the minor unit")
    return scaled.numerator


def _toward(amount: Fraction, allocation: int, minor_unit: int) -> int:
    # A manual amount moves the target towards A: mirrored for A < 0 (S09-R-38, S09-R-39).
    magnitude = round_half_up(amount, minor_unit)
    return magnitude if allocation >= 0 else -magnitude


def _manual_release(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.manual_release.v1``: min(A, max(C(t), C(P) + m)), mirrored for A < 0 (S09-R-38).

    Input C(t), the target before the adjustment. Params ``c_p`` C(P) and ``allocation`` A in
    minor units, ``basis`` and ``value``: m = ``amount`` towards A, ``ratio`` × (A − C(P)) rounded
    half up, or A − C(P) for ``remaining``.
    """
    formula_id = "sched.manual_release.v1"
    minor_unit = minor_unit_of(params)
    current = _posted_input(inputs, params, formula_id)
    c_p, allocation = _minor(params, "c_p"), _minor(params, "allocation")
    basis, value = _param(params, "basis"), _rational(params, "value")
    if basis == "amount":
        released = _toward(value, allocation, minor_unit)
    elif basis == "ratio":
        released = round_half_up(value * Fraction(allocation - c_p, 10**minor_unit), minor_unit)
    elif basis == "remaining":
        released = allocation - c_p
    else:
        raise ValueError(f"{formula_id} does not know the basis {basis}")
    level = c_p + released
    if allocation >= 0:
        result = min(allocation, max(current, level))
    else:
        result = max(allocation, min(current, level))
    return Fraction(result, 10**minor_unit)


def _manual_defer(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.manual_defer.v1``: in period P, max(C(P − 1), C(P) − m), mirrored (S09-R-39).

    Input C(P), the target before the adjustment. Params ``c_prev`` C(P − 1) and ``allocation`` in
    minor units, ``basis`` and ``value``: m = ``amount`` towards A, ``ratio`` × (C(P) − C(P − 1))
    rounded half up, or the whole period amount for ``remaining``. Later periods keep C(t).
    """
    formula_id = "sched.manual_defer.v1"
    minor_unit = minor_unit_of(params)
    current = _posted_input(inputs, params, formula_id)
    c_prev, allocation = _minor(params, "c_prev"), _minor(params, "allocation")
    basis, value = _param(params, "basis"), _rational(params, "value")
    period_amount = current - c_prev
    if basis == "amount":
        deferred = _toward(value, allocation, minor_unit)
    elif basis == "ratio":
        deferred = round_half_up(value * Fraction(period_amount, 10**minor_unit), minor_unit)
    elif basis == "remaining":
        deferred = period_amount
    else:
        raise ValueError(f"{formula_id} does not know the basis {basis}")
    level = current - deferred
    result = max(c_prev, level) if allocation >= 0 else min(c_prev, level)
    return Fraction(result, 10**minor_unit)


def _override_respread(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.override_respread.v1``: a schedule override (S09-R-40).

    Input C(t), the target before the adjustment. ``mode`` ``listed``: the listed cumulative
    target T_j (param ``target``). ``respread`` after the latest listed period t_k:
    ``cumulative_posted``(X, A, (T_k + (X − T_k) × g) ÷ X) with g = (f(t) − f(t_k)) ÷ (1 − f(t_k)),
    and g = 1 when f(t_k) = 1; params ``t_k``, ``allocation`` (minor units), ``x_exact``, ``f_t``
    and ``f_k``.
    """
    formula_id = "sched.override_respread.v1"
    minor_unit = minor_unit_of(params)
    _posted_input(inputs, params, formula_id)
    scale: int = 10**minor_unit
    mode = _param(params, "mode")
    if mode == "listed":
        return Fraction(_minor(params, "target"), scale)
    if mode != "respread":
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    t_k = Fraction(_minor(params, "t_k"), scale)
    x_exact, allocation = _rational(params, "x_exact"), _minor(params, "allocation")
    f_t, f_k = _rational(params, "f_t"), _rational(params, "f_k")
    if x_exact == 0:
        return t_k
    g = Fraction(1) if f_k == 1 else min(Fraction(1), max(Fraction(0), (f_t - f_k) / (1 - f_k)))
    ratio = min(Fraction(1), max(Fraction(0), (t_k + (x_exact - t_k) * g) / x_exact))
    return Fraction(cumulative_posted(x_exact, allocation, ratio, minor_unit), scale)


def _hold_freeze(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sched.hold_freeze.v1``: min(C(t), L) for A ≥ 0, max(C(t), L) for A < 0 (S09-R-43).

    Input C(t), the target before the hold. Params ``level`` L and ``allocation`` A, minor units.
    """
    formula_id = "sched.hold_freeze.v1"
    current = _posted_input(inputs, params, formula_id)
    level, allocation = _minor(params, "level"), _minor(params, "allocation")
    result = min(current, level) if allocation >= 0 else max(current, level)
    return Fraction(result, 10 ** minor_unit_of(params))


def _decompose_sequential(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.decompose.sequential.v1``: a period amount by E-28 line type (S09-R-35, S09-R-36).

    A ``cause`` other than ``NORMAL`` sums its inputs: the stage 06 and stage 08 ``catch_up@``
    nodes and the event deltas that source references carry; with params ``signs`` (one ``+`` or
    ``-`` per input, comma-separated) it sums them signed, the component causes ``BREAKAGE`` and
    ``ROYALTY`` citing the period's and the previous period's component nodes (S09-R-35; ENC-8).
    ``NORMAL`` takes C_t, then C_(t−1) when ``previous`` is true, then every other cause node of
    the period, and returns C_t − C_(t−1) − Σ others, so the decomposition sums exactly to the
    period amount (S09-INV-04).
    """
    if _param(params, "cause") != "NORMAL":
        if "signs" in params:
            signs = params["signs"].split(",") if params["signs"] else []
            if len(signs) != len(inputs) or any(sign not in ("+", "-") for sign in signs):
                raise ValueError("rec.decompose.sequential.v1: signs must give + or - per input")
            return sum(
                (
                    value if sign == "+" else -value
                    for sign, value in zip(signs, inputs, strict=True)
                ),
                Fraction(0),
            )
        return sum(inputs, Fraction(0))
    values = list(inputs)
    if not values:
        raise ValueError("rec.decompose.sequential.v1 needs the current target for NORMAL")
    current = values.pop(0)
    previous = Fraction(0)
    if params.get("previous") == "true":
        if not values:
            raise ValueError("rec.decompose.sequential.v1 needs the previous target")
        previous = values.pop(0)
    return current - previous - sum(values, Fraction(0))


def _catch_up_sum(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.catch_up.sum.v1``: the sum of the catch-ups it cites (Table 0.9-A; REQ-MOD-015)."""
    return sum(inputs, Fraction(0))


def _legacy_fold(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``books.legacy_fold.v1``: cumulative pre-standard revenue, the sum of the signed amounts of
    the ``PRE_STANDARD_REVENUE_RECORDED`` events it cites (ENGINE_SPEC_B §13.2.4, §13.5; END-8)."""
    return sum(inputs, Fraction(0))


# --- Stage 09 obligation measures (ENGINE_SPEC_B §9.2.13; BUILD_SPEC ENC-10) ----------------------


def _remaining(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.remaining.v1``: a remaining measure at the version date (§9.5; Table 0.9-A).

    ``kind`` ``allocation``: input C(d_v), the ``revenue_cum`` node; A − C with params ``allocated``
    (A in minor units) and ``minor_unit``. ``kind`` ``quantity``: no inputs; Q′ less the units
    consumed from it under POL-053, params ``quantity`` and ``consumed`` (T-CON-11
    ``remaining_quantity``).
    """
    formula_id = "rec.remaining.v1"
    kind = _param(params, "kind")
    if kind == "allocation":
        _require_arity(inputs, 1, formula_id)
        return Fraction(_minor(params, "allocated"), 10 ** minor_unit_of(params)) - inputs[0]
    if kind == "quantity":
        _require_arity(inputs, 0, formula_id)
        return _rational(params, "quantity") - _rational(params, "consumed")
    raise ValueError(f"{formula_id} does not know the kind {kind}")


def _scheduled(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.scheduled.v1``: the amount a deterministic pattern still places (S09-R-45).

    Input C(d_v), the ``revenue_cum`` node. ``pattern`` ``DETERMINISTIC`` with ``held`` false gives
    A_FIXED − (C − realised): the time-elapsed ``FIXED`` allocation less its posted target, with
    params ``allocated`` and ``realised`` (the realised ``PERIOD_VC`` amounts inside C) in minor
    units. ``EVENT_DRIVEN``, or an open recognition hold, gives 0 (S09-R-44, S09-R-45).
    """
    formula_id = "rec.scheduled.v1"
    _require_arity(inputs, 1, formula_id)
    pattern = _param(params, "pattern")
    if pattern not in ("DETERMINISTIC", "EVENT_DRIVEN"):
        raise ValueError(f"{formula_id} does not know the pattern {pattern}")
    if pattern == "EVENT_DRIVEN" or _param(params, "held") == "true":
        return Fraction(0)
    scale: int = 10 ** minor_unit_of(params)
    fixed_posted = inputs[0] - Fraction(_minor(params, "realised"), scale)
    return Fraction(_minor(params, "allocated"), scale) - fixed_posted


def _allocation_adjustment(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.allocation_adjustment.v1`` (T-CON-11 ``allocation_adjustment`` re-measured at the
    version date; Codex T1F-R3): the ``allocated_amount`` node less the stated-price node (params
    ``signs`` ``+,-``), or less params ``stated_price`` (minor units) when no stated-price node
    exists."""
    total = _signed_sum(inputs, params, "rec.allocation_adjustment.v1")
    if "stated_price" in params:
        total -= Fraction(_minor(params, "stated_price"), 10 ** minor_unit_of(params))
    return _as_node(total, params)


def _allocation_state(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.allocation.v1`` (T-CON-11 ``allocated_amount`` / ``allocated_exact``; S09-R-23): the
    allocation of the FIXED segment in force at d_v plus the realised PERIOD_VC amounts, net of
    the returns reduction under REDUCE. ``kind`` ``posted``: params ``allocated`` (minor units) and
    ``minor_unit``; ``kind`` ``exact``: params ``exact`` (a rational, currency units). The inputs
    are lineage only: the segment's allocation node when one exists. The posted
    form also records the separately traced realized allocation component, with
    the corresponding revenue target as period lineage."""
    kind = _param(params, "kind")
    if kind == "posted":
        return Fraction(_minor(params, "allocated"), 10 ** minor_unit_of(params))
    if kind == "exact":
        return _rational(params, "exact")
    raise ValueError(f"rec.allocation.v1 does not know the kind {kind!r}")


def _segment_state(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.segment_state.v1`` (T-CON-11 ``quantity``, ``unit_ssp``, ``remaining_ssp``): the
    named member of the FIXED segment in force at d_v (stage 05 inception or the last stage 06
    boundary), params ``member`` and ``value`` (a rational); inputs are lineage only."""
    _param(params, "member")
    return _rational(params, "value")


def _mod_stated_price(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.stated_price.v1`` (T-CON-11 ``stated_price`` after a boundary; D-97 (8) T1F-Q-3 (c)):
    the previous stated price — the previous node when cited, else params ``previous`` (minor
    units) — plus the boundary's posted consideration change cited as a source value."""
    scale = 10 ** minor_unit_of(params)
    base = Fraction(_minor(params, "previous"), scale) if "previous" in params else Fraction(0)
    return base + sum(inputs, Fraction(0))


def _mod_allocation_adjustment(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.allocation_adjustment.v1`` (T-CON-11 ``allocation_adjustment`` after a boundary; D-97
    (8) T1F-Q-3 (c)): the allocation of the FIXED segment in force less the stated price after the
    boundary. The allocation is the first input, or params ``allocated`` (minor units) when the
    boundary emitted no allocation node; the stated price is the last input, or params
    ``stated_price`` (minor units) when no stated-price node exists."""
    scale = 10 ** minor_unit_of(params)
    values = list(inputs)
    allocated = (
        Fraction(_minor(params, "allocated"), scale) if "allocated" in params else values.pop(0)
    )
    stated = (
        Fraction(_minor(params, "stated_price"), scale)
        if "stated_price" in params
        else values.pop()
    )
    if values:
        raise ValueError("mod.allocation_adjustment.v1: unexpected inputs")
    return allocated - stated


def _contract_sum(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``books.contract_sum.v1`` (stage 13 output measures; D-97 (8) T1F-Q-1 (A)): the signed sum
    of the cited obligation nodes (params ``signs``) plus params ``default_allocations`` (minor
    units): the allocation of obligations without stage 09 measures that no node carries."""
    total = _signed_sum(inputs, params, "books.contract_sum.v1")
    if "default_allocations" in params:
        total += Fraction(_minor(params, "default_allocations"), 10 ** minor_unit_of(params))
    return _as_node(total, params)


def binds_encoded(operand: Fraction, cited: Sequence[Fraction]) -> bool:
    """Emission-time binding of a raw operand to the cited nodes' EXACT values (DG-KRN-EXP-03:
    ``value + rounding_residue``; D-98 candidate 117 F1). Each trace value and residue is a CV-51
    ``format_exact`` encoding — half up at ``EXACT_PLACES`` — so a node's exact value is within
    half a unit at 18 places of the true rational and a non-terminating quota (1/3) cannot be
    reconstructed exactly from any node; the contract is the bound itself — ``len(cited)``
    half-units at 18 places — with no equality claim beyond it (for n ≥ 2 a sum of terminating
    reconstructions may still differ from the raw value by up to the bound; Codex 0304)."""
    bound = Fraction(len(cited), 2 * 10**EXACT_PLACES)
    return bool(abs(operand - sum(cited, Fraction(0))) <= bound)


def _unit_revenue_rate(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``books.unit_revenue_rate.v1`` (stage 13 output step; ENGINE_SPEC CV-47 (b), D-98 candidates
    88 and 117): inputs (allocation source(s)..., quantity), all exact — the allocation per unit,
    the allocation being the sum of every input but the last. Params ``zero`` names the value for
    a zero quantity: ``"0"`` (the remaining rate, legacy 01 §3.7 NaN → 0); otherwise a zero
    quantity raises ``ValueError`` (the original rate is NULL, no node).

    Registered in ``EXACT_INPUT_FORMULAS``: ``reevaluate`` supplies each cited node's DG-KRN-EXP-03
    exact value (recomputed value + stored ``rounding_residue``), the same reconstruction the
    emitting step reads through ``TraceBuilder.exact`` — one reconstruction at both levels."""
    if len(inputs) < 2:
        raise ValueError(f"books.unit_revenue_rate.v1 takes at least 2 inputs, not {len(inputs)}")
    *allocation_inputs, quantity_input = inputs
    # The operands travel in params: the raw quota and raw quantity of the original rate (D-98
    # candidate 117 — an encoded node value is not the raw rational), the exact remaining
    # allocation (value + residue, CV-51) of the remaining rate. Without a param the exact input
    # values stand.
    allocation = (
        _rational(params, "allocation")
        if "allocation" in params
        else sum(allocation_inputs, Fraction(0))
    )
    quantity = _rational(params, "quantity") if "quantity" in params else quantity_input
    # The ORIGINAL rate carries both raw operands; each is accepted only when it binds to its cited
    # source(s) under the CV-51 limit (``binds_encoded``: half a unit at 18 places per
    # independently encoded component; the whole contract) — the quota
    # to the sum of the producers' exact values (the inception relative node with the targeted
    # shares; the repin's share; a created obligation's creation producer), the quantity to the
    # quantity node — so a stale or unrelated citation fails re-evaluation (D-98 candidate 117 F1;
    # Codex 0235: cited 600 beside raw 600.5, cited Q 1 beside 2, cited Q 0.1 beside 0.2 are all
    # refused). No minor-unit tolerance exists. The REMAINING rate carries the allocation param
    # alone — the exact value of the posted remaining_allocation node (lane T1's matter).
    if "allocation" in params and "quantity" in params:
        for name, operand, cited in (
            ("allocation", allocation, list(allocation_inputs)),
            ("quantity", quantity, [quantity_input]),
        ):
            if not binds_encoded(operand, cited):
                raise ValueError(
                    f"books.unit_revenue_rate.v1: params {name} {rational_param(operand)} is not "
                    f"bound to the cited input {rational_param(sum(cited, Fraction(0)))} "
                    "(CV-51 encoding limit)"
                )
    if quantity == 0:
        if params.get("zero") == "0":
            return Fraction(0)
        raise ValueError("books.unit_revenue_rate.v1: the quantity is zero")
    return allocation / quantity


def _original_total(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.original_total.v1`` (S05-R-10 totals; the CV-50 link of ``original_allocated_exact``;
    D-98 candidate 121): the exact CURRENT original allocation over the node(s) that produced it —
    at inception with targeted shares the relative ``original_allocated_exact`` node and the
    ``targeted_vc_allocated@`` shares, after an S06-R-26 repin or at an obligation's creation the
    producing share / allocation node. Registered in ``EXACT_INPUT_FORMULAS`` (exact inputs). Param
    ``exact`` — the raw rational total — is accepted only when it binds to the inputs' sum within
    the CV-51 limit (``binds_encoded``) and is returned; without it the sum stands."""
    if not inputs:
        raise ValueError("alloc.original_total.v1 takes at least 1 input")
    total = sum(inputs, Fraction(0))
    if "exact" not in params:
        return total
    exact = _rational(params, "exact")
    if not binds_encoded(exact, inputs):
        raise ValueError(
            f"alloc.original_total.v1: params exact {rational_param(exact)} is not bound to the "
            f"cited inputs {rational_param(total)} (CV-51 encoding limit)"
        )
    return exact


def _original_total_amount(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.original_total_amount.v1`` (S05-R-10 totals; the CV-50 link of
    ``original_allocated_amount``; D-98 candidate 121): the posted CURRENT original allocation —
    Σ of the cited POSTED contributions, each counted once. This is the column's actual
    computation (Codex 0312): S05-R-10 sums the posted base share and every posted targeted share
    separately, a repin or a creation preserves its apportioned posted share, and nothing posts the
    raw total again — so the amount is never a re-rounding of the exact total (a one-cent pool over
    three equal weights gives one key a posted cent whose raw share rounds to zero). An ordinary
    formula (recomputed values; not in ``EXACT_INPUT_FORMULAS``)."""
    if not inputs:
        raise ValueError("alloc.original_total_amount.v1 takes at least 1 input")
    return sum(inputs, Fraction(0))


def _version_adjustment(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``books.version_adjustment.v1`` (stage 13 output measures; D-97 (8) T1F-Q-1 (A)): the last
    build-up member (one input) plus params ``adjustment`` (minor units), the version-date
    re-measurement (returns memo, routed-out lease allocation, sales tax at d_v)."""
    _require_arity(inputs, 1, "books.version_adjustment.v1")
    return inputs[0] + Fraction(_minor(params, "adjustment"), 10 ** minor_unit_of(params))


def _awaiting(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.awaiting.v1``: inputs (remaining allocation, scheduled); allocated − recognised −
    scheduled (S09-R-45; S09-INV-03)."""
    _require_arity(inputs, 2, "rec.awaiting.v1")
    remaining, scheduled = inputs
    return remaining - scheduled


# --- Stage 07 onboarding (ENGINE_SPEC §7.5; BUILD_SPEC ENB-9) ------------------------------------

_SEPARATOR: Final = "|"


def _list(params: Mapping[str, str], name: str) -> list[str]:
    value = _param(params, name)
    return value.split(_SEPARATOR) if value else []


def _rationals(params: Mapping[str, str], name: str) -> list[Fraction]:
    items = _list(params, name)
    for item in items:
        if not _RATIONAL.fullmatch(item):
            raise ValueError(f"params {name} must list integers or ratios of integers")
    return [Fraction(item) for item in items]


def _minor_value(value: Fraction, minor_unit: int, formula_id: str) -> int:
    scale: int = 10**minor_unit
    scaled = value * scale
    if scaled.denominator != 1:
        raise ValueError(f"{formula_id}: an amount is not a whole number of minor units")
    return scaled.numerator


def _apportion(total: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
    # ALG-01 §2.1.2; nothing to apportion over zero weights gives zero shares (S07-R-04, X_i = 0).
    if total == 0 and sum(weights, Fraction(0)) == 0:
        return [0] * len(keys)
    return largest_remainder(total, list(weights), list(keys))


def _keyed_share(
    total: int, params: Mapping[str, str], *, weights: str = "weights", keys: str = "keys"
) -> int:
    # The share of params["key"] in largest_remainder(total, weights, keys).
    names = _list(params, keys)
    values = _rationals(params, weights)
    key = _param(params, "key")
    if len(names) != len(values) or key not in names:
        raise ValueError("params keys, weights and key disagree")
    return _apportion(total, values, names)[names.index(key)]


def _opening_segment(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``onb.opening_segment.v1``: A_i = largest_remainder(TP_c, [X_j], keys)[i] (S07-R-04).

    Inputs: the payload ``revenue_cum`` and ``remaining_allocation`` of the obligation, whose sum
    X_i is its entry in ``weights``. Params ``tp_posted`` (TP_c, minor units), ``weights`` (X_j),
    ``keys`` (obligation subject keys separated by ``|``), ``key`` and ``minor_unit``.
    """
    formula_id = "onb.opening_segment.v1"
    _require_arity(inputs, 2, formula_id)
    minor_unit = minor_unit_of(params)
    names, values = _list(params, "keys"), _rationals(params, "weights")
    key = _param(params, "key")
    if len(names) != len(values) or key not in names:
        raise ValueError(f"{formula_id}: params keys, weights and key disagree")
    if format_exact(inputs[0] + inputs[1]) != format_exact(values[names.index(key)]):
        raise ValueError(f"{formula_id}: revenue_cum + remaining_allocation is not the weight")
    return Fraction(_keyed_share(_minor(params, "tp_posted"), params), 10**minor_unit)


def _opening_baseline(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``onb.baseline.v1``: the posted cumulative revenue at the cutover (S07-R-04 to S07-R-08).

    Input: the payload ``revenue_cum``. ``mode`` ``cutover``: C_0 = ``cumulative_posted``(X, A,
    revenue_cum ÷ X), 0 when X = 0, with params ``x_exact`` and ``a_posted`` (minor units);
    ``imported``: the imported amount rounded half up (CV-35); ``fair_value``: 0, because the
    IFRS15 book recognises the fair-valued liability from 0.
    """
    formula_id = "onb.baseline.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    mode = _param(params, "mode")
    posted = 0
    if mode == "cutover":
        x_exact = _rational(params, "x_exact")
        if x_exact != 0:
            posted_allocation = _minor(params, "a_posted")
            posted = cumulative_posted(x_exact, posted_allocation, inputs[0] / x_exact, minor_unit)
    elif mode == "imported":
        posted = round_half_up(inputs[0], minor_unit)
    elif mode != "fair_value":
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    return Fraction(posted, 10**minor_unit)


def _onboarding_difference(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``onb.difference.v1``: recomputed posted target at the cutover − imported (S07-R-07).

    Input: the ``opening_revenue_cum`` node of the imported cumulative. Params ``role``,
    ``recomputed`` and ``imported`` (minor units); the input equals ``imported``.
    """
    formula_id = "onb.difference.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    _param(params, "role")
    imported = _minor(params, "imported")
    if _minor_value(inputs[0], minor_unit, formula_id) != imported:
        raise ValueError(f"{formula_id}: params imported disagrees with its input")
    return Fraction(_minor(params, "recomputed") - imported, 10**minor_unit)


def _fair_value_split(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``onb.ifrs_fair_value_split.v1``: largest_remainder(V, weights, keys)[i] (S07-R-08).

    Input: the payload ``fair_value_contract_liability`` V. Params ``weights`` (the remaining
    allocations measured in the ASC606 book), ``keys``, ``key`` and ``minor_unit``.
    """
    formula_id = "onb.ifrs_fair_value_split.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    share = _keyed_share(_minor_value(inputs[0], minor_unit, formula_id), params)
    return Fraction(share, 10**minor_unit)


# --- Stage 08 estimate reassessment (ENGINE_SPEC §8.6; BUILD_SPEC ENB-10) ------------------------


def _estimate_pin(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.pin.v1``: the member of the version pinned from its effective date (S08-R-01).

    Input: the version member its source reference carries (``constrained_amount``,
    ``expected_total_amount``, ``expected_quantity`` or ``rate``). Params ``v_new``, ``v_old``,
    ``kind`` and ``effective_date``.
    """
    _require_arity(inputs, 1, "estimate.pin.v1")
    _param(params, "v_new")
    return inputs[0]


def _tp_delta(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.tp_delta.v1``: inputs (basis before, basis after); ΔTP = after − before."""
    _require_arity(inputs, 2, "estimate.tp_delta.v1")
    before, after = inputs
    return after - before


def _route_inception(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.route.inception.v1``: Δ_p on the inception basis (S08-R-04, S08-R-07).

    Input: the ``tp_delta`` node. ``mode`` ``incremental``: largest_remainder(ΔTP, weights,
    keys)[p]; ``reapportion``: largest_remainder(``basis_after``, weights, keys)[p] −
    ``a_before``, in minor units. Params ``weights``, ``keys``, ``key`` and ``minor_unit``.
    """
    formula_id = "estimate.route.inception.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    mode = _param(params, "mode")
    if mode == "incremental":
        share = _keyed_share(_minor_value(inputs[0], minor_unit, formula_id), params)
    elif mode == "reapportion":
        share = _keyed_share(_minor(params, "basis_after"), params) - _minor(params, "a_before")
    else:
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    return Fraction(share, 10**minor_unit)


def _route_inception_v2(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.route.inception.v2``: Δ_p on the inception basis (S08-R-04, S08-R-07 rev 1.6;
    D-91).

    Input: the ``tp_delta`` node. ``mode`` ``incremental``: largest_remainder(ΔTP, ``ssp_weights``,
    ``keys``)[``key``]; ``reapportion``: largest_remainder(``basis_after``, ``quotas_after``,
    ``keys``)[``key``] − ``a_before``, in minor units, so the quotas in force are carried and the
    posted price is one apportionment over the exact quotas after the change. Params
    ``minor_unit``. v1 stays registered for stored traces.
    """
    formula_id = "estimate.route.inception.v2"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    mode = _param(params, "mode")
    if mode == "incremental":
        total = _minor_value(inputs[0], minor_unit, formula_id)
        share = _keyed_share(total, params, weights="ssp_weights")
    elif mode == "reapportion":
        share = _keyed_share(_minor(params, "basis_after"), params, weights="quotas_after")
        share -= _minor(params, "a_before")
    else:
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    return Fraction(share, 10**minor_unit)


def _route_32_45(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.route.32_45.v1``: Δ_p routed through 25-13(a) boundaries (S08-R-05).

    Input: the ``tp_delta`` node. Δ_pre = largest_remainder(ΔTP, ``pre_weights``, ``pre_keys``).
    At each boundary j = 1 to ``steps`` the shares of ``satisfied_<j>`` stay with those
    obligations, and the sum of the other shares is apportioned over ``post_keys_<j>`` by
    ``post_weights_<j>``. Params ``key`` and ``minor_unit``.
    """
    formula_id = "estimate.route.32_45.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    names = _list(params, "pre_keys")
    total = _minor_value(inputs[0], minor_unit, formula_id)
    shares = dict(
        zip(names, _apportion(total, _rationals(params, "pre_weights"), names), strict=True)
    )
    kept: dict[str, int] = {}
    for step in range(1, _minor(params, "steps") + 1):
        satisfied = set(_list(params, f"satisfied_{step}"))
        pool = 0
        for name, share in shares.items():
            if name in satisfied:
                kept[name] = kept.get(name, 0) + share
            else:
                pool += share
        post = _list(params, f"post_keys_{step}")
        weights = _rationals(params, f"post_weights_{step}")
        shares = dict(zip(post, _apportion(pool, weights, post), strict=True))
    key = _param(params, "key")
    return Fraction(kept.get(key, 0) + shares.get(key, 0), 10**minor_unit)


def _posted_side(params: Mapping[str, str], side: str, minor_unit: int) -> int:
    # C = cumulative_posted(X, A, φ) with φ = E ÷ X, or 1 at completion, and 0 when X = 0 (CV-63).
    x_exact = _rational(params, f"x_{side}")
    if x_exact == 0:
        return 0
    complete = params.get(f"complete_{side}") == "true"
    ratio = Fraction(1) if complete else _rational(params, f"exact_{side}") / x_exact
    return cumulative_posted(x_exact, _minor(params, f"a_{side}"), ratio, minor_unit)


def _estimate_catch_up(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.catch_up.v1``: CU = C_after(d) − C_before(d) at one position (S08-R-06).

    Input: the ``tp_share`` node Δ_p, equal to ``a_after`` − ``a_before``. Params ``x_``, ``a_``,
    ``exact_`` and ``complete_`` members ``before`` and ``after`` of the FIXED component,
    ``v_old``, ``v_new``, ``progress`` f(d) and ``as_of``; a ``guard`` (V4, V5) gives 0.
    """
    formula_id = "estimate.catch_up.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    share = _minor(params, "a_after") - _minor(params, "a_before")
    if _minor_value(inputs[0], minor_unit, formula_id) != share:
        raise ValueError(f"{formula_id}: the share disagrees with the allocations")
    if "guard" in params:
        return Fraction(0)
    after = _posted_side(params, "after", minor_unit)
    before = _posted_side(params, "before", minor_unit)
    return Fraction(after - before, 10**minor_unit)


# --- Stages 01 to 05: ingest, Step 1, obligations, price, allocation (ENGINE_SPEC §1.5 to §5.5;
# BUILD_SPEC ENA-13) ------------------------------------------------------------------------------

_DECIMAL_TEXT: Final = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_TOLERANCE: Final = Fraction(1, 10**12)  # a check on inputs encoded at EXACT_PLACES


def _decimal_text(value: str, name: str) -> Fraction:
    if not _DECIMAL_TEXT.fullmatch(value):
        raise ValueError(f"params {name} must be a decimal string")
    return to_fraction(value)


def _decimal(params: Mapping[str, str], name: str) -> Fraction:
    return _decimal_text(_param(params, name), name)


def _decimals(params: Mapping[str, str], name: str, separator: str = ",") -> list[Fraction]:
    value = _param(params, name)
    return [_decimal_text(item, name) for item in value.split(separator)] if value else []


def _index(params: Mapping[str, str], count: int, formula_id: str) -> int:
    index = _minor(params, "index")
    if not 0 <= index < count:
        raise ValueError(f"{formula_id}: params index lies outside the inputs")
    return index


def _signed_sum(inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str) -> Fraction:
    # Σ sign × input; params["signs"] holds one sign per input ("+,-" or "+-"), else every "+".
    raw = params.get("signs")
    signs = ["+"] * len(inputs) if raw is None else (raw.split(",") if "," in raw else list(raw))
    if len(signs) != len(inputs) or any(sign not in ("+", "-") for sign in signs):
        raise ValueError(f"{formula_id}: params signs disagree with its inputs")
    return sum(
        (value if sign == "+" else -value for sign, value in zip(signs, inputs, strict=True)),
        Fraction(0),
    )


def _as_node(value: Fraction, params: Mapping[str, str]) -> Fraction:
    # A posted node (params minor_unit) holds round_half_up(value) in currency units.
    if "minor_unit" not in params:
        return value
    minor_unit = minor_unit_of(params)
    return Fraction(round_half_up(value, minor_unit), 10**minor_unit)


def _input_echo(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``input.echo.v1`` (ENGINE_SPEC CV-52, CV-53; D-97 (8)): the identity over one input, the
    canonical input field (a ``SourceRef`` carrying its value) or the node a stored column copies;
    rounded half up for a posted node."""
    _require_arity(inputs, 1, "input.echo.v1")
    return _as_node(inputs[0], params)


def _unit_ssp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.unit_ssp.v1`` (S05-R-16 ``original_unit_ssp``): inputs (selected SSP, quantity);
    SSP ÷ Q. A zero quantity raises ``ValueError`` (the column is NULL, no node is emitted).

    Optional params ``ssp`` / ``quantity`` (CV-50 rev 1.29; D-98 123 / 124; Codex 0954): the RAW
    operands of a boundary's ``original_unit_ssp@<event>`` node, each accepted only when it binds
    to its cited input within the CV-51 limit (``binds_encoded``), so a converted non-terminating
    SSP over a fractional quantity replays to the raw quotient the column publishes. Without the
    params the decoded inputs stand (the stage 05 inception node, unchanged)."""
    _require_arity(inputs, 2, "alloc.unit_ssp.v1")
    if ("ssp" in params) != ("quantity" in params):
        raise ValueError("alloc.unit_ssp.v1: params ssp and quantity come together")
    if "ssp" in params:
        ssp, quantity = _rational(params, "ssp"), _rational(params, "quantity")
        for name, operand, cited in (("ssp", ssp, inputs[0]), ("quantity", quantity, inputs[1])):
            if not binds_encoded(operand, [cited]):
                raise ValueError(
                    f"alloc.unit_ssp.v1: params {name} {rational_param(operand)} is not bound to "
                    f"the cited input {rational_param(cited)} (CV-51 encoding limit)"
                )
    else:
        ssp, quantity = inputs[0], inputs[1]
    if quantity == 0:
        raise ValueError("alloc.unit_ssp.v1: the quantity is zero")
    return ssp / quantity


def _original_weight(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.original_weight.v1`` (CV-50 rev 1.29; D-98 candidate 124; Codex 0954): the governed
    ``allocation_weight`` ratio w ÷ Σw of a boundary that creates an obligation — inputs (the own
    weight node, the total node), exact (``EXACT_INPUT_FORMULAS``); params ``weight`` / ``total``
    are the RAW operands, each accepted only when it binds to its cited input within the CV-51
    limit, and the raw ratio is returned; without them the decoded quotient stands."""
    formula_id = "alloc.original_weight.v1"
    _require_arity(inputs, 2, formula_id)
    if ("weight" in params) != ("total" in params):
        raise ValueError(f"{formula_id}: params weight and total come together")
    if "weight" in params:
        weight, total = _rational(params, "weight"), _rational(params, "total")
        for name, operand, cited in (("weight", weight, inputs[0]), ("total", total, inputs[1])):
            if not binds_encoded(operand, [cited]):
                raise ValueError(
                    f"{formula_id}: params {name} {rational_param(operand)} is not bound to the "
                    f"cited input {rational_param(cited)} (CV-51 encoding limit)"
                )
    else:
        weight, total = inputs[0], inputs[1]
    if total == 0:
        raise ValueError(f"{formula_id}: Σw is 0 — no weight ratio")
    return weight / total


def _signed_formula(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """The signed sum of the inputs (params ``signs``), rounded half up for a posted node."""
        return _as_node(_signed_sum(inputs, params, formula_id), params)

    return formula


def _cpc_share_based(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.cpc_share_based.v1`` (ENGINE_SPEC S04-R-17 rev 1.6; ENGINE_SPEC_B S10-R-26; D-91).

    Inputs: the award's grant-date fair value F (the ``estimate_version`` source), then the related
    obligations' posted ``revenue_cum`` nodes and their posted ``concession_created_cum`` nodes.
    R = the signed sum of ``inputs[1:]`` per params ``signs`` (one sign per input after the first;
    no floor). The value is 0 while params ``vesting_probable`` is not ``true`` or ``period_end``
    precedes ``grant_date`` (POL-246 LATER_OF); E = params ``expected`` ≤ 0 gives 0 when R = 0 and
    raises otherwise (NON_FINITE_AMOUNT, CV-32); else round_half_up(min(F, F × R ÷ E)) at the
    posted minor unit (CV-35). The producer, this replay and the tests share one signed policy.
    """
    formula_id = "tp.cpc_share_based.v1"
    if not inputs:
        raise ValueError(f"{formula_id} takes the award's grant-date fair value first")
    fair = inputs[0]
    related = _signed_sum(inputs[1:], params, formula_id)
    zero = _as_node(Fraction(0), params)
    if _param(params, "vesting_probable") != "true":
        return zero
    if _date(params, "period_end") < _date(params, "grant_date"):
        return zero
    expected = _decimal(params, "expected")
    if expected <= 0:
        if related == 0:
            return zero
        raise ValueError(
            f"{formula_id}: expected related revenue is not positive (NON_FINITE_AMOUNT)"
        )
    return _as_node(min(fair, fair * related / expected), params)


def _event_25_7(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``step1.event_25_7.v1``: the deposit balance recognised as revenue under 606-10-25-7: the
    signed sum of the deposit movements cited (params ``signs``), capped at params ``limit`` when
    present, the stated consideration less the revenue already recognised under S02-R-07 (D-91
    gaps (vi); rev 1.6). A stored node without ``limit`` re-evaluates as before (DG-KRN-EXP-04).
    """
    formula_id = "step1.event_25_7.v1"
    value = _signed_sum(inputs, params, formula_id)
    limit = params.get("limit")
    if limit is not None:
        value = min(value, _decimal_text(limit, "limit"))
    return _as_node(value, params)


def _deposit_revenue_share(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``step1.deposit_revenue_share.v1`` (ENGINE_SPEC_B S14-R-25; D-91 gaps (iv)): the
    obligation's share of the contract's 606-10-25-7 revenue.

    The inputs are the stage 02 recognitions (``deposit_to_revenue@…`` nodes) whose sum, rounded
    half up at the minor unit (CV-35), is apportioned by ``largest_remainder`` over params
    ``weights`` (``|``-separated rationals) and ``keys`` (the contract's ``IN_SCOPE_606``
    obligations); params ``index`` selects the share of params ``key``, and ``basis`` records the
    weight basis (``ALLOCATION``, ``SSP`` or ``STATED_PRICE``). A zero total gives 0 without an
    apportionment.
    """
    formula_id = "step1.deposit_revenue_share.v1"
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    keys = _list(params, "keys")
    weights = _rationals(params, "weights")
    if len(keys) != len(weights) or not keys:
        raise ValueError(f"{formula_id}: params keys and weights disagree")
    index = _index(params, len(keys), formula_id)
    if keys[index] != _param(params, "key"):
        raise ValueError(f"{formula_id}: params key is not keys[index]")
    total = round_half_up(sum(inputs, Fraction(0)), minor_unit)
    if total == 0:
        return Fraction(0)
    return Fraction(largest_remainder(total, weights, keys)[index], scale)


def _step1_net(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rec.step1_net.v1`` (ENGINE_SPEC S02-R-04 rev 1.6; D-91 gaps (v)): the STEP1_MET target
    net of the 606-10-25-7 revenue attributed to the obligation, max(C_p − R25_p, 0): inputs
    (the target before netting, the ``deposit_revenue_share`` node), posted at the minor unit.
    """
    _require_arity(inputs, 2, "rec.step1_net.v1")
    return _as_node(max(inputs[0] - inputs[1], Fraction(0)), params)


def _status(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``step1.status.v1``: the E-17 ordinal of params ``status``, its 1-based position in 04 §3.4.

    Input: the event that opened the status segment, valued at params ``value``.
    """
    formula_id = "step1.status.v1"
    _require_arity(inputs, 1, formula_id)
    literals = [status.value for status in ContractStatus]
    status = _param(params, "status")
    if status not in literals:
        raise ValueError(f"{formula_id}: unknown status {status!r}")
    ordinal = Fraction(literals.index(status) + 1)
    if inputs[0] != ordinal:
        raise ValueError(f"{formula_id}: the input disagrees with the status")
    return ordinal


def _enforceable_term(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``step1.enforceable_term.v1``: the ordinal day number of params ``date`` (S02-R-06); the
    booking input, when present, carries the same ordinal."""
    ordinal = Fraction(_date(params, "date").toordinal())
    if len(inputs) > 1 or (inputs and inputs[0] != ordinal):
        raise ValueError("step1.enforceable_term.v1: the booking input disagrees with the date")
    return ordinal


def _obligation_parts(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pob.template_match.v1`` and ``pob.merge.v1``: the sum of the member lines' parts (quantity
    or stated price) cited by the booking inputs, else params ``value`` (S03-R-01, S03-R-05)."""
    return sum(inputs, Fraction(0)) if inputs else _decimal(params, "value")


def _bundle_split(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pob.bundle_split.v1``: largest_remainder(bundle price, weights, keys)[index] (S03-R-03).

    Input: the bundle line price, else params ``value``. Params ``weights`` and ``keys`` separated
    by ``,``, ``index`` and ``minor_unit``.
    """
    formula_id = "pob.bundle_split.v1"
    if len(inputs) > 1:
        raise ValueError(f"{formula_id} takes at most one input")
    minor_unit = minor_unit_of(params)
    price = inputs[0] if inputs else _decimal(params, "value")
    names = _param(params, "keys").split(",")
    weights = _decimals(params, "weights")
    if len(names) != len(weights):
        raise ValueError(f"{formula_id}: params keys and weights disagree")
    index = _index(params, len(names), formula_id)
    share = _apportion(_minor_value(price, minor_unit, formula_id), weights, names)[index]
    return Fraction(share, 10**minor_unit)


def _option_ssp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pob.option_ssp.v1``: the S03-R-07 option SSP, posted.

    ``reason = NOT_MATERIAL`` → 0. ``DISCOUNT_X_LIKELIHOOD`` → ``expected_purchase_amount`` ×
    ``incremental_discount_ratio`` × L, with L the estimate input. Otherwise the SSP entry input.
    """
    formula_id = "pob.option_ssp.v1"
    if params.get("reason") == "NOT_MATERIAL":
        return Fraction(0)
    if not inputs:
        raise ValueError(f"{formula_id} needs the likelihood or entry input")
    if _param(params, "method") != "DISCOUNT_X_LIKELIHOOD":
        return _as_node(inputs[0], params)
    likelihood = inputs[0]
    if abs(likelihood - _decimal(params, "likelihood")) > _TOLERANCE:
        raise ValueError(f"{formula_id}: the likelihood input disagrees with params")
    amount = _decimal(params, "expected_purchase_amount")
    return _as_node(amount * _decimal(params, "incremental_discount_ratio") * likelihood, params)


def _agent_net(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pob.agent_net.v1`` (S03-R-09): role ``gross`` → the booked line price P; role ``retained``
    → R from the gross memo input: ``COMMISSION_RATE`` ρ → largest_remainder(P, [ρ, 1 − ρ])[0];
    ``FIXED_FEE`` → ``amount``; ``SUPPLIER_COST`` → P − ``amount``."""
    formula_id = "pob.agent_net.v1"
    _require_arity(inputs, 1, formula_id)
    gross = inputs[0]
    role = _param(params, "role")
    if role == "gross":
        return _as_node(gross, params)
    if role != "retained":
        raise ValueError(f"{formula_id} does not know the role {role}")
    basis = _param(params, "basis")
    if basis == "COMMISSION_RATE":
        minor_unit = minor_unit_of(params)
        rate = _decimal(params, "rate")
        retained = largest_remainder(
            _minor_value(gross, minor_unit, formula_id), [rate, 1 - rate], ["retained", "supplier"]
        )[0]
        return Fraction(retained, 10**minor_unit)
    amount = _decimal(params, "amount")
    if basis == "FIXED_FEE":
        return _as_node(amount, params)
    if basis == "SUPPLIER_COST":
        return _as_node(gross - amount, params)
    raise ValueError(f"{formula_id} does not know the basis {basis}")


def _realised_usage(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.realised_usage.v1`` (S04-R-06): Σ rated amounts; with a minimum ``guarantee`` netted
    under POL-057, the amount above it, never below 0."""
    total = sum(inputs, Fraction(0))
    guarantee = _decimal(params, "guarantee")
    return _as_node(total if guarantee == 0 else max(Fraction(0), total - guarantee), params)


def _sign(params: Mapping[str, str], formula_id: str) -> int:
    value = _param(params, "sign")
    if value not in ("1", "-1"):
        raise ValueError(f"{formula_id}: params sign must be 1 or -1")
    return int(value)


def _vc_expected_value(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.vc_expected_value.v1`` (S04-R-05): sign × Σ amount × probability over the scenario
    inputs, with params ``probabilities`` separated by ``,``."""
    formula_id = "tp.vc_expected_value.v1"
    probabilities = _decimals(params, "probabilities")
    if len(probabilities) != len(inputs):
        raise ValueError(f"{formula_id}: params probabilities disagree with the inputs")
    weighted = sum((a * p for a, p in zip(inputs, probabilities, strict=True)), Fraction(0))
    return _as_node(_sign(params, formula_id) * weighted, params)


def _vc_single(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """The element amount input (the most likely scenario or the entered amount) × sign."""
        _require_arity(inputs, 1, formula_id)
        return _as_node(_sign(params, formula_id) * inputs[0], params)

    return formula


def _vc_constrained(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.vc_constrained.v1`` (S04-R-07): the ``vc_unconstrained`` node input, or, with params
    ``source = constrained_amount``, the preparer's constrained amount as stored × sign."""
    formula_id = "tp.vc_constrained.v1"
    _require_arity(inputs, 1, formula_id)
    source = params.get("source", "unconstrained")
    if source == "unconstrained":
        return _as_node(inputs[0], params)
    if source == "constrained_amount":
        return _as_node(_sign(params, formula_id) * inputs[0], params)
    raise ValueError(f"{formula_id} does not know the source {source}")


def _concession(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.concession_implicit.v1`` (S04-R-09): −round(κ × Σ fixed consideration) over the stated
    price inputs; κ = the rate input (``basis = RATE``), else (fixed − the expected total input) ÷
    fixed (``EXPECTED_TOTAL_AMOUNT``); with ``CONSTRAINED_AMOUNT`` the component is −round(the
    constrained amount input) (D-87 L6-5-Q-12 (ii))."""
    formula_id = "tp.concession_implicit.v1"
    if not inputs:
        raise ValueError(f"{formula_id} needs the estimate input")
    minor_unit = minor_unit_of(params)
    fixed = sum(inputs[1:], Fraction(0))
    basis = _param(params, "basis")
    if basis == "CONSTRAINED_AMOUNT":
        return Fraction(-round_half_up(inputs[0], minor_unit), 10**minor_unit)
    if basis == "RATE":
        kappa = inputs[0]
    elif basis == "EXPECTED_TOTAL_AMOUNT":
        kappa = Fraction(0) if fixed == 0 else (fixed - inputs[0]) / fixed
    else:
        raise ValueError(f"{formula_id} does not know the basis {basis}")
    return Fraction(-round_half_up(kappa * fixed, minor_unit), 10**minor_unit)


def _returns_expected(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.returns_expected.v1`` (S04-R-08): −Σ round(r × (Y + E)) over params ``unit_rates``,
    ``returned`` and ``expected``, one member per obligation separated by ``,``; the inputs are the
    pins and return events cited."""
    formula_id = "tp.returns_expected.v1"
    minor_unit = minor_unit_of(params)
    rates = _decimals(params, "unit_rates")
    returned = _decimals(params, "returned")
    expected = _decimals(params, "expected")
    if not len(rates) == len(returned) == len(expected):
        raise ValueError(f"{formula_id}: params unit_rates, returned and expected disagree")
    total = sum(
        -round_half_up(r * (y + e), minor_unit)
        for r, y, e in zip(rates, returned, expected, strict=True)
    )
    return Fraction(total, 10**minor_unit)


def _noncash(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.noncash.v1`` (S04-R-18): Σ round(units × fair value) of the item inputs; with params
    ``completed``, round(Σ units × fair value × completed): the asset recognised."""
    minor_unit = minor_unit_of(params)
    if "completed" in params:
        return _as_node(sum(inputs, Fraction(0)) * _decimal(params, "completed"), params)
    return Fraction(sum(round_half_up(value, minor_unit) for value in inputs), 10**minor_unit)


def _warranty_accrual(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``tp.warranty_accrual.v1`` (S04-R-19): round(``cost_per_unit`` × ``units``); the ledger
    input, when present, carries the units transferred."""
    units = _decimal(params, "units")
    if len(inputs) > 1 or (inputs and inputs[0] != units):
        raise ValueError("tp.warranty_accrual.v1: the ledger input disagrees with params units")
    return _as_node(_decimal(params, "cost_per_unit") * units, params)


def _gap_test(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sfc.gap_test.v1`` (S04-R-10): W − ordinal(T_p) in days; 0 without a payment schedule."""
    _require_arity(inputs, 0, "sfc.gap_test.v1")
    if "weighted_payment_ordinal" not in params:
        return Fraction(0)
    return _decimal(params, "weighted_payment_ordinal") - _decimal(params, "transfer_ordinal")


def _periodic(params: Mapping[str, str], annual_rate: Fraction, formula_id: str) -> Fraction:
    compounding = _param(params, "compounding")
    if compounding == "MONTHLY":
        return annual_rate / 12
    if compounding == "ANNUAL":
        return annual_rate
    raise ValueError(f"{formula_id} does not know the compounding {compounding}")


def _cash_selling_price(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sfc.cash_selling_price.v1`` (S04-R-12): the obligation's share of round(CSP).

    Inputs: the annual rate, then the payments. CSP = Σ payment ÷ (1 + j)^n (``DEFERRED``) or
    Σ payment × (1 + j)^n (``ADVANCE``) with params ``counts`` and ``compounding``; the share is
    largest_remainder(round(CSP), ``weights``, ``keys`` separated by ``|``)[``index``].
    """
    formula_id = "sfc.cash_selling_price.v1"
    if len(inputs) < 2:
        raise ValueError(f"{formula_id} needs the rate and at least one payment")
    minor_unit = minor_unit_of(params)
    growth = 1 + _periodic(params, inputs[0], formula_id)
    counts = [int(count) for count in _param(params, "counts").split(",")]
    payments = inputs[1:]
    if len(counts) != len(payments):
        raise ValueError(f"{formula_id}: params counts disagree with the payments")
    kind = _param(params, "kind")
    if kind == "ADVANCE" and "shares" in params:  # D-87 L5-3-Q-8: counts are grid steps
        paid: dict[int, Fraction] = {}
        for amount, count in zip(payments, counts, strict=True):
            paid[count] = paid.get(count, Fraction(0)) + amount
        csp = _level_csp(paid, _step_shares(params), growth - 1)
    elif kind == "ADVANCE":
        csp = sum((a * growth**n for a, n in zip(payments, counts, strict=True)), Fraction(0))
    elif kind == "DEFERRED":
        csp = sum((a / growth**n for a, n in zip(payments, counts, strict=True)), Fraction(0))
    else:
        raise ValueError(f"{formula_id} does not know the kind {kind}")
    names = _list(params, "keys")
    weights = _decimals(params, "weights")
    if len(names) != len(weights):
        raise ValueError(f"{formula_id}: params keys and weights disagree")
    index = _index(params, len(names), formula_id)
    return Fraction(
        _apportion(round_half_up(csp, minor_unit), weights, names)[index], 10**minor_unit
    )


def _step_shares(params: Mapping[str, str]) -> dict[int, Fraction]:
    """Params ``shares``: ``<step>:<g>`` separated by ``,`` with g an integer or ratio (D-87
    L5-3-Q-8)."""
    found: dict[int, Fraction] = {}
    for item in _param(params, "shares").split(","):
        raw_step, _, raw_share = item.partition(":")
        if not _RATIONAL.fullmatch(raw_share):
            raise ValueError("params shares must list <step>:<ratio of integers>")
        at = _minor({"step": raw_step}, "step")
        found[at] = found.get(at, Fraction(0)) + Fraction(raw_share)
    return found


def _level_csp(
    payments: Mapping[int, Fraction], shares: Mapping[int, Fraction], periodic: Fraction
) -> Fraction:
    """The advance CSP of D-87 L5-3-Q-8: X = Σ pay_i·v^(n_i) ÷ Σ_k g_k·v^k, v = 1 ÷ (1 + j)."""
    v = 1 / (1 + periodic)
    denominator = sum((g * v**k for k, g in shares.items()), Fraction(0))
    if denominator == 0:
        raise ValueError("params shares must hold a positive revenue share")
    return sum((a * v**n for n, a in payments.items()), Fraction(0)) / denominator


def _schedule_grid(
    params: Mapping[str, str], annual_rate: Fraction, steps: int, formula_id: str
) -> tuple[Fraction, Fraction]:
    """(Σ interest, balance) after ``steps`` months of the S04-R-12 grid: params ``opening``,
    ``payments`` (``<step>:<amount>`` separated by ``,``), ``kind`` and ``compounding``."""
    periodic = _periodic(params, annual_rate, formula_id)
    monthly = _param(params, "compounding") == "MONTHLY"
    advance = _param(params, "kind") == "ADVANCE"
    paid: dict[int, Fraction] = {}
    for item in _param(params, "payments").split(","):
        raw_step, _, raw_amount = item.partition(":")
        at = _minor({"step": raw_step}, "step")
        paid[at] = paid.get(at, Fraction(0)) + _decimal_text(raw_amount, "payments")
    shares = _step_shares(params) if "shares" in params else {}  # D-87 L5-3-Q-8 relief X·g_k
    level = _level_csp(paid, shares, periodic) if shares else Fraction(0)
    balance = _decimal(params, "opening")
    year_opening = balance
    interest_total = Fraction(0)
    for step in range(1, steps + 1):
        if monthly:
            interest = balance * periodic
        else:
            if (step - 1) % 12 == 0:
                year_opening = balance
            interest = year_opening * periodic / 12
        amount = paid.get(step, Fraction(0))
        balance = balance + interest + (amount if advance else -amount)
        balance -= level * shares.get(step, Fraction(0))
        interest_total += interest
    return interest_total, balance


def _effective_interest(compounding: str) -> Formula:
    formula_id = f"sfc.effective_interest.{compounding.lower()}.v1"

    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``sfc.effective_interest.<compounding>.v1`` (S04-R-12, S04-R-12a): round(Σ interest of
        the ``months`` elapsed grid months); while accretion is suspended,
        cumulative_posted(x, x, ``weight``) with x the params ``suspended_interest``. Inputs: the
        annual rate and the schedule total."""
        _require_arity(inputs, 2, formula_id)
        if _param(params, "compounding") != compounding:
            raise ValueError(f"{formula_id}: params compounding is not {compounding}")
        minor_unit = minor_unit_of(params)
        if "weight" in params:
            x_int = _decimal(params, "suspended_interest")
            posted = cumulative_posted(
                x_int,
                _minor_value(x_int, minor_unit, formula_id),
                _decimal(params, "weight"),
                minor_unit,
            )
            return Fraction(posted, 10**minor_unit)
        steps = _minor(params, "months")
        total, _ = _schedule_grid(params, inputs[0], steps, formula_id)
        return _as_node(total, params)

    return formula


def _accretion(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``sfc.accretion.v1`` (S04-R-13): the financed balance after params ``months`` grid months.

    ``mode = zero``: 0, before the grid origin or from the transfer of an advance. ``grid``: the
    S04-R-12 balance from params ``annual_rate``, ``opening`` and ``payments``. ``suspended``
    (S04-R-12a): ``cash_selling_price`` + ``recognised`` − the payments through the step. Inputs:
    the cumulative interest node and the payments through the step.
    """
    formula_id = "sfc.accretion.v1"
    _require_arity(inputs, 2, formula_id)
    mode = _param(params, "mode")
    if mode == "zero":
        return Fraction(0)
    steps = _minor(params, "months")
    if mode == "grid":
        _, balance = _schedule_grid(params, _decimal(params, "annual_rate"), steps, formula_id)
        return _as_node(balance, params)
    if mode == "suspended":
        balance = (
            _decimal(params, "cash_selling_price") + _decimal(params, "recognised") - inputs[1]
        )
        return _as_node(balance, params)
    raise ValueError(f"{formula_id} does not know the mode {mode}")


_RANGE_POINTS: Final = frozenset(
    {"CONTRACT_PRICE", "MIDPOINT", "LOW_POINT", "HIGH_POINT", "NEAREST_BOUND"}
)


def _ssp_point(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ssp.point.v1`` (S05-R-06 to S05-R-08): the selected SSP of one obligation.

    A single line under a range policy selects from params ``price``, ``low``, ``mid`` and ``high``
    (``CONTRACT_PRICE`` → P; ``MIDPOINT`` → mid; ``LOW_POINT`` → low; ``HIGH_POINT`` → high;
    ``NEAREST_BOUND`` → the nearer bound). ``VC_LINE`` and ``RESIDUAL`` give 0. A point entry or an
    entered option in the transaction currency gives its entry input. Merged lines, converted
    entries, ``OBSERVABLE_POINT`` and likelihood options keep the selection recorded in params
    ``value``, which their inputs do not rebuild.
    """
    policy = _param(params, "policy")
    if policy in ("VC_LINE", "RESIDUAL"):
        return Fraction(0)
    single = params.get("merged", "") == ""
    if single and policy in _RANGE_POINTS:
        if policy == "MIDPOINT":
            return _decimal(params, "mid")
        price = _decimal(params, "price")
        if policy == "CONTRACT_PRICE":
            return price
        low, high = _decimal(params, "low"), _decimal(params, "high")
        if policy == "LOW_POINT":
            return low
        if policy == "HIGH_POINT":
            return high
        return low if price < low else high
    converted = params.get("rate_key", "") != ""
    if single and not converted and policy in ("POINT", "ENTERED_AMOUNT") and len(inputs) == 1:
        return inputs[0]
    return _decimal(params, "value")


def _select_version(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ssp.select_version.v1`` (S05-R-03): the greatest eligible version number input."""
    if not inputs:
        raise ValueError("ssp.select_version.v1 needs an eligible version")
    return max(inputs)


def _extend(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ssp.extend.v1`` (S05-R-06): the product of the inputs (Q × the unit value × factors)."""
    product = Fraction(1)
    for value in inputs:
        product *= value
    return product


def _legacy_range(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ssp.legacy_range.v1`` (S05-R-06 ``legacy_range``; T-CON-11 ``original_ssp_mid`` /
    ``original_ssp_low`` / ``original_ssp_high``; lane ENG-T1F, Codex T1F-R1): inputs (Q, L, d[, r]
    [, f]) — the quantity node, the entry's ``unit_list_price`` and ``midpoint_discount_ratio``,
    its ``range_ratio`` when params ``has_range`` is ``true`` and the POL-079 conversion factor when
    params ``converted`` is ``true``; mid = Q × L × f × (1 − d), low = mid × (1 − r), high = mid ×
    (1 + r) per params ``bound``."""
    has_range = _param(params, "has_range") == "true"
    converted = _param(params, "converted") == "true"
    arity = 3 + int(has_range) + int(converted)
    _require_arity(inputs, arity, "ssp.legacy_range.v1")
    quantity, list_price, discount = inputs[0], inputs[1], inputs[2]
    rest = list(inputs[3:])
    ratio = rest.pop(0) if has_range else None
    factor = rest.pop(0) if converted else Fraction(1)
    mid = quantity * list_price * factor * (1 - discount)
    bound = _param(params, "bound")
    if bound == "mid":
        return mid
    if ratio is None:
        raise ValueError("ssp.legacy_range.v1: a bound needs the range ratio")
    if bound == "low":
        return mid * (1 - ratio)
    if bound == "high":
        return mid * (1 + ratio)
    raise ValueError(f"ssp.legacy_range.v1 does not know the bound {bound!r}")


def _convert(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ssp.convert.v1`` (S05-R-05): inputs (value, spot rate); value × rate."""
    _require_arity(inputs, 2, "ssp.convert.v1")
    return inputs[0] * inputs[1]


def _relative_ssp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.relative_ssp.v1`` (S05-R-10, S05-R-13): role ``total`` → Σ weight inputs; ``weight``
    → w_p ÷ Σw; ``exact`` → the pool input × w_p ÷ Σw over inputs (pool, w_p, Σw), or the pool
    input × the weight input over two inputs (CV-34). Three inputs keep x_p exact when w_p ÷ Σw
    has no 18-place encoding (L4-3-Q-1)."""
    formula_id = "alloc.relative_ssp.v1"
    role = _param(params, "role")
    if role == "total":
        return sum(inputs, Fraction(0))
    if role == "exact" and len(inputs) == 3:
        if inputs[2] == 0:
            raise ValueError(f"{formula_id}: the total weight is 0")
        return inputs[0] * inputs[1] / inputs[2]
    _require_arity(inputs, 2, formula_id)
    if role == "weight":
        if inputs[1] == 0:
            raise ValueError(f"{formula_id}: the total weight is 0")
        return inputs[0] / inputs[1]
    if role == "exact":
        return inputs[0] * inputs[1]
    raise ValueError(f"{formula_id} does not know the role {role}")


def _largest_remainder_share(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.largest_remainder.v1`` (S05-R-10, S05-R-13): the posted share
    largest_remainder(T, w, keys)[index] of the pool input T over the weight inputs, with params
    ``keys`` separated by ``,``; role ``adjustment`` (S05-R-16): the signed inputs, a_p − P.

    With 2n + 1 inputs the n normalised weight nodes are followed by the n unnormalised weights
    w_p, and the apportionment reads w_p: an 18-place weight node can break an ALG-01 tie on the
    fractional remainder (DG-AK-54; L4-3-Q-9). Each weight node must equal w_p ÷ Σw within the
    encoding tolerance. With n + 1 inputs the weight nodes are the weights, as stored traces hold.
    """
    formula_id = "alloc.largest_remainder.v1"
    if params.get("role") == "adjustment":
        return _as_node(_signed_sum(inputs, params, formula_id), params)
    minor_unit = minor_unit_of(params)
    names = _param(params, "keys").split(",")
    count = len(names)
    if len(inputs) == 2 * count + 1:
        normalised, weights = inputs[1 : count + 1], inputs[count + 1 :]
        total_weight = sum(weights, Fraction(0))
        if total_weight != 0 and any(
            abs(node - weight / total_weight) > _TOLERANCE
            for node, weight in zip(normalised, weights, strict=True)
        ):
            raise ValueError(f"{formula_id}: the weight nodes disagree with the weights")
    elif len(inputs) == count + 1:
        weights = inputs[1:]
    else:
        raise ValueError(f"{formula_id}: params keys disagree with the weight inputs")
    index = _index(params, count, formula_id)
    total = _minor_value(inputs[0], minor_unit, formula_id)
    return Fraction(_apportion(total, weights, names)[index], 10**minor_unit)


def _targeted_vc(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.targeted_vc.v1`` (S05-R-14): role ``remainder`` → the basis less every targeted K
    (signed inputs); role ``share`` → largest_remainder(K, SSP of the targets, keys)[index], with K
    the first input and params ``keys`` separated by ``|``."""
    formula_id = "alloc.targeted_vc.v1"
    role = _param(params, "role")
    if role == "remainder":
        return _as_node(_signed_sum(inputs, params, formula_id), params)
    if role != "share":
        raise ValueError(f"{formula_id} does not know the role {role}")
    minor_unit = minor_unit_of(params)
    names = _list(params, "keys")
    if len(inputs) != len(names) + 1:
        raise ValueError(f"{formula_id}: params keys disagree with the SSP inputs")
    index = _index(params, len(names), formula_id)
    total = _minor_value(inputs[0], minor_unit, formula_id)
    return Fraction(_apportion(total, inputs[1:], names)[index], 10**minor_unit)


def _discount_exception(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``alloc.discount_exception.v1`` (S05-R-11).

    Role ``share`` → B × SSP_p ÷ Σ SSP of the bundle (inputs: the bundle node, then the members'
    SSPs, p at ``index``). Mode ``remainder`` → B = T − Σ SSP of the others (signed inputs). Mode
    ``residual`` → B = S_b, the last input, with params ``proposed_residual`` = T − Σ SSP of the
    others − S_b.
    """
    formula_id = "alloc.discount_exception.v1"
    if params.get("role") == "share":
        members = inputs[1:]
        total = sum(members, Fraction(0))
        if not inputs or total == 0:
            raise ValueError(f"{formula_id}: the bundle members have no SSP")
        return inputs[0] * members[_index(params, len(members), formula_id)] / total
    mode = _param(params, "mode")
    if mode == "remainder":
        return _signed_sum(inputs, params, formula_id)
    if mode == "residual":
        if not inputs:
            raise ValueError(f"{formula_id} needs the bundle price input")
        price = inputs[-1]
        proposed = _signed_sum(inputs[:-1], params, formula_id) - price
        if abs(proposed - _decimal(params, "proposed_residual")) > _TOLERANCE:
            raise ValueError(f"{formula_id}: params proposed_residual disagrees with the inputs")
        return price
    raise ValueError(f"{formula_id} does not know the mode {mode}")


_INCEPTION_FORMULAS: Final[Mapping[str, Formula]] = MappingProxyType({
    "alloc.discount_exception.v1": _discount_exception,
    "alloc.largest_remainder.v1": _largest_remainder_share,
    "alloc.relative_ssp.v1": _relative_ssp,
    "alloc.residual.v1": _signed_formula("alloc.residual.v1"),
    "alloc.targeted_vc.v1": _targeted_vc,
    "alloc.unit_ssp.v1": _unit_ssp,
    "ingest.ledger_sum.v1": _signed_formula("ingest.ledger_sum.v1"),
    "input.echo.v1": _input_echo,
    "pob.agent_net.v1": _agent_net,
    "pob.bundle_split.v1": _bundle_split,
    "pob.merge.v1": _obligation_parts,
    "pob.option_ssp.v1": _option_ssp,
    "pob.template_match.v1": _obligation_parts,
    "sfc.accretion.v1": _accretion,
    "sfc.cash_selling_price.v1": _cash_selling_price,
    "sfc.effective_interest.annual.v1": _effective_interest("ANNUAL"),
    "sfc.effective_interest.monthly.v1": _effective_interest("MONTHLY"),
    "sfc.gap_test.v1": _gap_test,
    "ssp.convert.v1": _convert,
    "ssp.extend.v1": _extend,
    "ssp.legacy_range.v1": _legacy_range,
    "ssp.point.v1": _ssp_point,
    "ssp.select_version.v1": _select_version,
    "step1.deposit.v1": _signed_formula("step1.deposit.v1"),
    "step1.deposit_revenue_share.v1": _deposit_revenue_share,
    "step1.enforceable_term.v1": _enforceable_term,
    "step1.event_25_7.v1": _event_25_7,
    "step1.status.v1": _status,
    "step1.transition_catch_up.v1": _signed_formula("step1.transition_catch_up.v1"),
    "tp.buildup.v1": _signed_formula("tp.buildup.v1"),
    "tp.concession_implicit.v1": _concession,
    "tp.cpc_reduction.v1": _signed_formula("tp.cpc_reduction.v1"),
    "tp.cpc_release.v1": _signed_formula("tp.cpc_release.v1"),
    "tp.cpc_share_based.v1": _cpc_share_based,
    "tp.fixed.v1": _signed_formula("tp.fixed.v1"),
    "tp.noncash.v1": _noncash,
    "tp.realised_usage.v1": _realised_usage,
    "tp.returns_expected.v1": _returns_expected,
    "tp.tax_excluded.v1": _signed_formula("tp.tax_excluded.v1"),
    "tp.vc_constrained.v1": _vc_constrained,
    "tp.vc_entered.v1": _vc_single("tp.vc_entered.v1"),
    "tp.vc_expected_value.v1": _vc_expected_value,
    "tp.vc_most_likely.v1": _vc_single("tp.vc_most_likely.v1"),
    "tp.warranty_accrual.v1": _warranty_accrual,
})  # fmt: skip


# --- Stage 06 modifications (ENGINE_SPEC §6.6; BUILD_SPEC ENB-2, ENB-3) ---------------------------


_TIME_ELAPSED: Final = "TIME_ELAPSED"


def _mod_weights_d18(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.weights.d18.v1``: w_p of S06-R-11 under POL-080 ``D18_DEFAULT``.

    Inputs: the SSP resolutions the weight sums, as source references. Params ``parts`` (the exact
    selected SSP of each input) and ``class``: ``D`` gives Σ parts; ``N`` gives (1 − ``progress``)
    × ``ssp0`` + Σ parts − ``removed`` × ``u0``. A class ``D`` node with ``measure`` scales its
    first part, the remaining units, by ρ_p of ``_remaining_scale`` (D-90b); a node without
    ``measure`` evaluates as before.
    """
    formula_id = "mod.weights.d18.v1"
    parts = _weight_parts(inputs, params, formula_id)
    label = _param(params, "class")
    if label == "D":
        rho = _remaining_scale(params, formula_id)
        if rho is None:
            return sum(parts, Fraction(0))
        if not parts:
            raise ValueError(f"{formula_id}: a scaled weight has a remaining-units part")
        return parts[0] * rho * _series_multiplier(params, formula_id) + sum(parts[1:], Fraction(0))
    if label == "N":
        return _nondistinct_weight(sum(parts, Fraction(0)), params)
    raise ValueError(f"{formula_id} does not know the class {label}")


def _weight_parts(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> list[Fraction]:
    parts = _rationals(params, "parts")
    if len(parts) != len(inputs):
        raise ValueError(f"{formula_id}: params parts disagree with the inputs")
    return parts


def _layer_progress(
    convention: str,
    start: date,
    end: date,
    as_of: date,
    calendar: Sequence[dates.DateRange] | None,
) -> Fraction:
    # f_L over [start, end] at the close of as_of; a layer starting after the term end completes on
    # it (stage 06 segments._layer_progress).
    if end < start:
        return Fraction(1) if as_of >= end else Fraction(0)
    return progress.time_fraction(convention, start, end, as_of, calendar=calendar)


def _remaining_scale(params: Mapping[str, str], formula_id: str) -> Fraction | None:
    """ρ_p of S06-R-11 recomputed from the unit-layer params (D-90b), or ``None`` without
    ``measure``.

    A scaled node is class ``D`` measured by ``TIME_ELAPSED`` at ``progress_as_of`` = ``as_of`` −
    1 day. Its layers (``layer_quantities``, ``layer_starts``, ``layer_progress``) have one start
    on or after ``term_start`` each, sum to ``remaining_quantity`` + ``removed``, and reproduce
    ``layer_progress`` under ``convention`` over [s_L, ``term_end``] with the ``periods`` calendar;
    ``remaining_scale`` equals Σ q_L × (1 − f_L) ÷ Σ q_L, above 0. Any disagreement raises
    ``ValueError``.
    """
    if "measure" not in params:
        return None
    measure = _param(params, "measure")
    if measure != _TIME_ELAPSED:
        raise ValueError(
            f"{formula_id}: remaining service is measured by time elapsed, not {measure}"
        )
    if _param(params, "class") != "D":
        raise ValueError(f"{formula_id}: a scaled weight is class D")
    as_of = _date(params, "as_of") - timedelta(days=1)
    if _date(params, "progress_as_of") != as_of:
        raise ValueError(f"{formula_id}: progress is measured at the close of the day before d")
    quantities = _rationals(params, "layer_quantities")
    starts = _list(params, "layer_starts")
    recorded = _rationals(params, "layer_progress")
    if not quantities or not (len(quantities) == len(starts) == len(recorded)):
        raise ValueError(f"{formula_id}: the unit layers disagree")
    if not all(_ISO_DATE.fullmatch(item) for item in starts):
        raise ValueError(f"{formula_id}: params layer_starts must list YYYY-MM-DD dates")
    layer_starts = [date.fromisoformat(item) for item in starts]
    term_start, term_end = _date(params, "term_start"), _date(params, "term_end")
    if min(layer_starts) < term_start:
        raise ValueError(f"{formula_id}: a unit layer starts before the term in force")
    total = sum(quantities, Fraction(0))
    carried = _rational(params, "remaining_quantity") + _rational(params, "removed")
    if total <= 0 or total != carried:
        raise ValueError(
            f"{formula_id}: the unit layers do not sum to the remaining quantity plus the removed"
            " units"
        )
    convention = _param(params, "convention")
    calendar = _calendar(params)
    measured = [_layer_progress(convention, s, term_end, as_of, calendar) for s in layer_starts]
    if measured != recorded:
        raise ValueError(f"{formula_id}: layer_progress disagrees with the term and convention")
    remaining = sum((q * (1 - f) for q, f in zip(quantities, measured, strict=True)), Fraction(0))
    rho = remaining / total
    if rho <= 0:
        raise ValueError(f"{formula_id}: a class D obligation has no remaining service")
    if _rational(params, "remaining_scale") != rho:
        raise ValueError(f"{formula_id}: remaining_scale disagrees with the unit layers")
    return rho


def _series_multiplier(params: Mapping[str, str], formula_id: str) -> Fraction:
    """The D-93 (4) series factor beside ρ: 1 without ``series_basis``; ``PER_BOOKED_TERM`` 1;
    ``PER_INCREMENT`` the increments of [``term_start``, ``term_end``] in ``series_increment_unit``
    as ``convention`` counts them (``progress.series_increments``; Codex C1B-S1), whatever the
    quantity (Codex C1B-S2). ``series_increments``, ``series_remaining_increments`` (increments ×
    ``remaining_scale``) and ``series_multiplier`` must agree with the recomputation (ENGINE_SPEC
    S06-R-11 series row)."""
    basis = params.get("series_basis")
    if basis is None:
        return Fraction(1)
    if basis not in ("PER_INCREMENT", "PER_BOOKED_TERM"):
        raise ValueError(f"{formula_id}: unknown series_basis {basis}")
    unit = _param(params, "series_increment_unit")
    if unit not in ("day", "month"):
        raise ValueError(f"{formula_id}: series_increment_unit {unit} is not a time increment")
    term_start, term_end = _date(params, "term_start"), _date(params, "term_end")
    increments = progress.series_increments(
        _param(params, "convention"), unit, term_start, term_end, calendar=_calendar(params)
    )
    if _rational(params, "series_increments") != increments:
        raise ValueError(f"{formula_id}: series_increments disagrees with the term in force")
    remaining = increments * _rational(params, "remaining_scale")
    if _rational(params, "series_remaining_increments") != remaining:
        raise ValueError(f"{formula_id}: series_remaining_increments disagrees with ρ")
    if basis == "PER_INCREMENT":
        # D-97 (3): the entry's E-125 quantity unit, never inferred from the quantity.
        quantity_unit = _param(params, "series_quantity_unit")
        if quantity_unit not in ("SERVICE_UNITS", "INCREMENTS"):
            raise ValueError(f"{formula_id}: unknown series_quantity_unit {quantity_unit}")
        multiplier = increments if quantity_unit == "SERVICE_UNITS" else Fraction(1)
    else:
        multiplier = Fraction(1)
    if _rational(params, "series_multiplier") != multiplier:
        raise ValueError(f"{formula_id}: series_multiplier disagrees with the basis")
    return multiplier


def _nondistinct_weight(added: Fraction, params: Mapping[str, str]) -> Fraction:
    # Class N: (1 − f_p(d)) × SSP0_p + added goods at d − removed goods × u0_p (S06-R-11).
    inception = (1 - _rational(params, "progress")) * _rational(params, "ssp0")
    return inception + added - _rational(params, "removed") * _rational(params, "u0")


def _mod_weights_inception_all(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.weights.inception_all.v1``: w_p of S06-R-11 under POL-080 ``INCEPTION_ALL``.

    Inputs and ``parts`` as ``mod.weights.d18.v1``. ``class`` ``D``: ρ_p × ``remaining_quantity``
    × ``u0`` + Σ parts, with ρ_p of ``_remaining_scale`` when the node carries ``measure`` and 1
    otherwise (D-90b); ``N``: as ``mod.weights.d18.v1``.
    """
    formula_id = "mod.weights.inception_all.v1"
    total = sum(_weight_parts(inputs, params, formula_id), Fraction(0))
    label = _param(params, "class")
    if label == "D":
        rho = _remaining_scale(params, formula_id)
        carried = _rational(params, "remaining_quantity") * _rational(params, "u0")
        scale = Fraction(1) if rho is None else rho * _series_multiplier(params, formula_id)
        return carried * scale + total
    if label == "N":
        return _nondistinct_weight(total, params)
    raise ValueError(f"{formula_id} does not know the class {label}")


def _mod_pool_by_line(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.pool.by_line.v1``: Σ over ``keys`` of (``allocations`` − ``revenue`` +
    ``consideration``), minor units (S06-R-12 ``ATTRIBUTE_BY_LINE``). No inputs."""
    formula_id = "mod.pool.by_line.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    names = _list(params, "keys")
    allocations = _rationals(params, "allocations")
    revenue = _rationals(params, "revenue")
    consideration = _rationals(params, "consideration")
    if not len(names) == len(allocations) == len(revenue) == len(consideration):
        raise ValueError(
            f"{formula_id}: params keys, allocations, revenue and consideration disagree"
        )
    total = (
        sum(allocations, Fraction(0)) - sum(revenue, Fraction(0)) + sum(consideration, Fraction(0))
    )
    scale: int = 10**minor_unit
    return total / scale


def _mod_satisfied_performance(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.satisfied_performance.v1``: largest_remainder(``total``, ``weights``, ``keys``)[key].

    ΔC_sat in minor units over the original posted allocations of the receivers (S06-R-09,
    S06-R-10). No inputs; params ``key``, ``settlement``, ``mode`` and ``minor_unit``.
    """
    formula_id = "mod.satisfied_performance.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    _param(params, "settlement")
    return Fraction(_keyed_share(_minor(params, "total"), params), 10**minor_unit)


def _mod_pool_remaining_tp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.pool.remaining_tp.v1``: S06-R-12 and S06-R-13 under POL-103 ``REMAINING_TP``.

    ``role`` ``pool``: no inputs; Pool = Σ ``allocations`` − Σ ``revenue`` + ``consideration`` −
    ``satisfied`` + ``vc_delta``, in minor units. ``role`` ``share``: input the pool node;
    largest_remainder(Pool, ``weights``, ``keys``)[``key``]. Params ``minor_unit``.
    """
    formula_id = "mod.pool.remaining_tp.v1"
    minor_unit = minor_unit_of(params)
    role = _param(params, "role")
    if role == "pool":
        _require_arity(inputs, 0, formula_id)
        names = _list(params, "keys")
        allocations = _rationals(params, "allocations")
        revenue = _rationals(params, "revenue")
        if not len(names) == len(allocations) == len(revenue):
            raise ValueError(f"{formula_id}: params keys, allocations and revenue disagree")
        remaining = sum(allocations, Fraction(0)) - sum(revenue, Fraction(0))
        adjustments = (
            _minor(params, "consideration")
            - _minor(params, "satisfied")
            + _minor(params, "vc_delta")
        )
        scale: int = 10**minor_unit
        return (remaining + adjustments) / scale
    if role == "share":
        _require_arity(inputs, 1, formula_id)
        total = _minor_value(inputs[0], minor_unit, formula_id)
        return Fraction(_keyed_share(total, params), 10**minor_unit)
    raise ValueError(f"{formula_id} does not know the role {role}")


def _mod_pool_total_tp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.pool.total_tp.v1``: S06-R-12 and S06-R-13 under POL-103 ``TOTAL_TP``.

    ``role`` ``pool``: no inputs; TP′ = ``tp`` + ``consideration``, in minor units. ``role``
    ``share``: input the pool node; largest_remainder(TP′, ``weights``, ``keys``)[``key``], the
    weights being delivered plus remaining SSP of every obligation, class S included. Params
    ``minor_unit``. Registered for the stage key (ENB-13); the native route fails closed on
    ``TOTAL_TP`` (S06-R-06), so no stage 06 node uses it yet.
    """
    formula_id = "mod.pool.total_tp.v1"
    minor_unit = minor_unit_of(params)
    role = _param(params, "role")
    if role == "pool":
        _require_arity(inputs, 0, formula_id)
        total = _minor(params, "tp") + _minor(params, "consideration")
        return Fraction(total, 10**minor_unit)
    if role == "share":
        _require_arity(inputs, 1, formula_id)
        total = _minor_value(inputs[0], minor_unit, formula_id)
        return Fraction(_keyed_share(total, params), 10**minor_unit)
    raise ValueError(f"{formula_id} does not know the role {role}")


def _mod_classify(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.classify.v1``: f_p(d) of one obligation at a modification, with its S06-R-05 class.

    No inputs. Params ``value`` (f_p(d)), ``class``, ``reason`` and ``progress_measure``. Class
    ``S`` holds exactly when f_p(d) = 1; classes ``D`` and ``N`` hold below 1, and an added or
    unstarted obligation is ``D`` at 0.
    """
    formula_id = "mod.classify.v1"
    _require_arity(inputs, 0, formula_id)
    _param(params, "progress_measure")
    value = to_fraction(_param(params, "value"))
    label, reason = _param(params, "class"), _param(params, "reason")
    if label not in ("S", "D", "N") or (label == "S") != (value == 1):
        raise ValueError(f"{formula_id}: class {label} disagrees with progress {value}")
    if reason in ("UNSTARTED", "NEW_DISTINCT", "NEW_UNSTARTED") and (label != "D" or value != 0):
        raise ValueError(f"{formula_id}: reason {reason} is class D at progress 0")
    return value


def _mod_price_test(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.price_test.v1``: ΔC_m of an added line and its S06-R-04 price test (POL-101).

    Input: the SSP entry as a source reference, absent without a resolvable SSP. Params ``value``
    (ΔC_m), ``basis``, ``passed``, ``point``, ``low``, ``high`` and ``point_tolerance_pct``.
    ``ATTESTED`` passes; ``POINT`` passes when |ΔC_m − point| ≤ tolerance × |point|; ``RANGE`` when
    low ≤ ΔC_m ≤ high; ``NO_SSP`` fails. A ``passed`` param that disagrees raises ``ValueError``.
    """
    formula_id = "mod.price_test.v1"
    if len(inputs) > 1:
        raise ValueError(f"{formula_id} takes at most one input")
    value = to_fraction(_param(params, "value"))
    basis = _param(params, "basis")
    if basis == "ATTESTED":
        passed = True
    elif basis == "NO_SSP":
        passed = False
    elif basis == "POINT":
        point = to_fraction(_param(params, "point"))
        passed = abs(value - point) <= to_fraction(_param(params, "point_tolerance_pct")) * abs(
            point
        )
    elif basis == "RANGE":
        low, high = sorted(
            (to_fraction(_param(params, "low")), to_fraction(_param(params, "high")))
        )
        passed = low <= value <= high
    else:
        raise ValueError(f"{formula_id} does not know the basis {basis}")
    if _param(params, "passed") != ("true" if passed else "false"):
        raise ValueError(f"{formula_id}: params passed disagrees with the test")
    return value


def _mod_catch_up(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.catch_up.v1``: CU = C_after − C_before at the boundary point (S06-R-17; CV-63).

    Input: the ``mod_share`` node s_p when the obligation takes a pool share, equal to ``a_after``
    − ``base`` (R_p for an existing obligation, 0 for an added one). Params ``x_``, ``a_``,
    ``exact_`` and ``complete_`` members ``before`` and ``after``, ``base``, ``cause``, ``as_of``.
    """
    formula_id = "mod.catch_up.v1"
    if len(inputs) > 1:
        raise ValueError(f"{formula_id} takes at most one input")
    minor_unit = minor_unit_of(params)
    _param(params, "cause")
    if inputs:
        share = _minor(params, "a_after") - _minor(params, "base")
        if _minor_value(inputs[0], minor_unit, formula_id) != share:
            raise ValueError(f"{formula_id}: the share disagrees with the allocation after")
    after = _posted_side(params, "after", minor_unit)
    before = _posted_side(params, "before", minor_unit)
    return Fraction(after - before, 10**minor_unit)


def _mod_termination(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.termination.v1``: an ended obligation's allocation, or a termination refund (S06-R-21).

    ``role`` ``allocation``: inputs the obligation's pool share and, when present, its share of
    satisfied performance; value = ``revenue_before`` (C_before(d_T), minor units) + Σ inputs.
    ``role`` ``refund``: no inputs; value = ``refund_amount``. Params ``minor_unit``.
    """
    formula_id = "mod.termination.v1"
    minor_unit = minor_unit_of(params)
    role = _param(params, "role")
    if role == "allocation":
        if len(inputs) > 2:
            raise ValueError(f"{formula_id} takes at most two inputs")
        shares = sum(_minor_value(value, minor_unit, formula_id) for value in inputs)
        return Fraction(_minor(params, "revenue_before") + shares, 10**minor_unit)
    if role == "refund":
        _require_arity(inputs, 0, formula_id)
        return Fraction(_minor(params, "refund_amount"), 10**minor_unit)
    raise ValueError(f"{formula_id} does not know the role {role}")


def _mod_exercise_continuation(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.exercise.continuation.v1``: allocations at a material-right exercise (S06-R-23).

    ``role`` ``option``: no inputs; value = ``revenue_before``, C_o(x), the option's closing
    allocation. ``role`` ``goods``: inputs the SSP at x of every optioned good (``mod_weight``
    nodes); value = largest_remainder(``option_allocation`` − ``option_revenue`` + ``additional``,
    inputs, ``keys``)[``key``], that is M + C_add apportioned over G. Params ``minor_unit``.
    """
    formula_id = "mod.exercise.continuation.v1"
    minor_unit = minor_unit_of(params)
    role = _param(params, "role")
    if role == "option":
        _require_arity(inputs, 0, formula_id)
        return Fraction(_minor(params, "revenue_before"), 10**minor_unit)
    if role == "goods":
        names = _list(params, "keys")
        key = _param(params, "key")
        if len(names) != len(inputs) or key not in names:
            raise ValueError(f"{formula_id}: params keys disagree with the inputs")
        total = (
            _minor(params, "option_allocation")
            - _minor(params, "option_revenue")
            + _minor(params, "additional")
        )
        return Fraction(_apportion(total, list(inputs), names)[names.index(key)], 10**minor_unit)
    raise ValueError(f"{formula_id} does not know the role {role}")


def _mod_exercise_modification(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.exercise.modification.v1``: the lines a material-right exercise builds (S06-R-24).

    No inputs. The option is removed (``removed_quantity``; its remaining allocation joins the
    pool), and each optioned good in ``keys`` is added with ΔC_m (``consideration``, minor units).
    Value = Σ ΔC_m, which must equal ``additional``, C_add. Params ``minor_unit``.
    """
    formula_id = "mod.exercise.modification.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    names = _list(params, "keys")
    consideration = _rationals(params, "consideration")
    if len(names) != len(consideration):
        raise ValueError(f"{formula_id}: params keys and consideration disagree")
    _rational(params, "removed_quantity")
    total = sum(consideration, Fraction(0))
    if total != _minor(params, "additional"):
        raise ValueError(
            f"{formula_id}: the added lines disagree with the additional consideration"
        )
    scale: int = 10**minor_unit
    return total / scale


# --- Stage 06 legacy templates (ENGINE_SPEC §6.5; BUILD_SPEC ENB-6, ENB-7) -----------------------


def _mod_legacy_mod_ssp(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.legacy.mod_ssp.v1``: Σ over the lines of clamp(billing, low, high) (S06-R-28).

    Params ``quantities``, ``billings``, ``lows`` and ``highs`` list one entry per line. The band is
    the file version's extended range for the line quantity, so the legacy sign-aware branch picks
    the nearest bound and a quantity of 0 gives 0. Inputs: the SSP entries the lines resolve, as
    source references; params ``sources`` is their number.
    """
    formula_id = "mod.legacy.mod_ssp.v1"
    quantities, billings = _rationals(params, "quantities"), _rationals(params, "billings")
    lows, highs = _rationals(params, "lows"), _rationals(params, "highs")
    if not quantities or not len(quantities) == len(billings) == len(lows) == len(highs):
        raise ValueError(f"{formula_id}: params quantities, billings, lows and highs disagree")
    if len(inputs) != _minor(params, "sources"):
        raise ValueError(f"{formula_id}: params sources disagrees with the inputs")
    total = Fraction(0)
    for quantity, billing, low, high in zip(quantities, billings, lows, highs, strict=True):
        if low > high or (quantity == 0 and (low != 0 or high != 0)):
            raise ValueError(f"{formula_id}: a band is inverted or a zero quantity has a band")
        total += min(max(billing, low), high)
    return total


def _legacy_amount(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> Fraction:
    # A_i = largest_remainder(tp_posted, weights, keys)[key] (S06-R-29; PJR-1); the optional input
    # is the obligation's allocated_exact node, equal to its weight.
    if len(inputs) > 1:
        raise ValueError(f"{formula_id} takes at most one input")
    minor_unit = minor_unit_of(params)
    names, values = _list(params, "keys"), _rationals(params, "weights")
    key = _param(params, "key")
    if len(names) != len(values) or key not in names:
        raise ValueError(f"{formula_id}: params keys, weights and key disagree")
    if inputs and format_exact(inputs[0]) != format_exact(values[names.index(key)]):
        raise ValueError(f"{formula_id}: the input is not the weight of key")
    return Fraction(_keyed_share(_minor(params, "tp_posted"), params), 10**minor_unit)


def _mod_legacy_retrospective(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.legacy.retrospective.v1``: the retrospective template (S06-R-28; legacy 04 §3.5).

    ``role`` ``exact``: X′_key = r_c × (CRS_key + SSPDel_key), where CRS_j = max(0,
    ``remaining_ssp``_j + ``mod_ssp``_j), TP_c = Σ ``remaining_allocation`` + Σ ``billing`` + Σ
    ``revenue``, SSP_c = Σ CRS + Σ ``ssp_delivered`` and r_c = TP_c ÷ SSP_c; params list one entry
    per ``keys``. Inputs: the ``mod_ssp`` nodes of ``line_keys``, equal to their ``mod_ssp``
    entries. ``role`` ``amount``: largest_remainder(``tp_posted``, ``weights``, ``keys``)[key].
    """
    formula_id = "mod.legacy.retrospective.v1"
    role = _param(params, "role")
    if role == "amount":
        return _legacy_amount(inputs, params, formula_id)
    if role not in ("exact", "total_ssp", "weight"):
        raise ValueError(f"{formula_id} does not know the role {role}")
    names, key = _list(params, "keys"), _param(params, "key")
    columns = [
        _rationals(params, name)
        for name in (
            "revenue",
            "remaining_allocation",
            "remaining_ssp",
            "ssp_delivered",
            "billing",
            "mod_ssp",
        )
    ]
    revenue, remaining, ssp, delivered, billing, mod_ssp = columns
    line_keys = _list(params, "line_keys")
    if any(len(column) != len(names) for column in columns) or key not in names:
        raise ValueError(f"{formula_id}: params keys and columns disagree")
    if len(line_keys) != len(inputs) or not set(line_keys) <= set(names):
        raise ValueError(f"{formula_id}: params line_keys disagree with the inputs")
    for name, value in zip(line_keys, inputs, strict=True):
        if format_exact(value) != format_exact(mod_ssp[names.index(name)]):
            raise ValueError(f"{formula_id}: an input is not the mod SSP of its key")
    current = [max(Fraction(0), item + change) for item, change in zip(ssp, mod_ssp, strict=True)]
    total_ssp = sum(current, Fraction(0)) + sum(delivered, Fraction(0))
    if role == "total_ssp":
        # Σ CRS_j: the stored ``original_total_contract_ssp`` of an obligation the template
        # creates (CV-50 rev 1.29; D-98 candidate 124) — the template's own per-key parameters.
        return sum(current, Fraction(0))
    if total_ssp == 0:
        raise ValueError(f"{formula_id}: SSP_c is 0 (NON_FINITE_AMOUNT)")
    index = names.index(key)
    if role == "weight":
        # (CRS_key + SSPDel_key) ÷ SSP_c: the governed ``allocation_weight`` ratio of the
        # retrospective template — its actual basis, NOT the stored total (Codex 0354).
        return (current[index] + delivered[index]) / total_ssp
    price = sum(remaining, Fraction(0)) + sum(billing, Fraction(0)) + sum(revenue, Fraction(0))
    return price / total_ssp * (current[index] + delivered[index])


def _mod_legacy_prospective(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.legacy.prospective.v1``: the prospective template (S06-R-28; legacy 03 §3.4 to §3.6).

    ``role`` ``exact``: X′_key = ``revenue``_key + s_key. Per key j: RemQty′_j =
    ``remaining_quantity``_j + ``quantity``_j; w_j = max(0, ``remaining_ssp``_j + ``mod_ssp``_j),
    or 0 when RemQty′_j = 0 (DEV-055); Pool = Σ ``remaining_allocation`` + Σ ``billing``; W = Σ w;
    s_j = Pool × w_j ÷ W. When W = 0 the pool is satisfied performance (DEV-054): the keys with
    RemQty′ = 0 and ``original_posted`` > 0 share it by ``original_posted``. ``revenue_after`` must
    be the template revenue E′: X′ for a receiver of satisfied performance; ``delivered`` ÷
    (``delivered`` + RemQty′) × X′ for a ``nondistinct`` key with W ≠ 0 and a non-zero divisor; E
    otherwise.
    Inputs: the ``mod_ssp`` nodes of ``line_keys``, equal to their ``mod_ssp`` entries. ``role``
    ``amount``: as ``mod.legacy.retrospective.v1``.
    """
    formula_id = "mod.legacy.prospective.v1"
    role = _param(params, "role")
    if role == "amount":
        return _legacy_amount(inputs, params, formula_id)
    if role not in ("exact", "total_ssp", "weight"):
        raise ValueError(f"{formula_id} does not know the role {role}")
    names, key = _list(params, "keys"), _param(params, "key")
    columns = [
        _rationals(params, name)
        for name in (
            "revenue",
            "remaining_allocation",
            "remaining_quantity",
            "remaining_ssp",
            "delivered",
            "quantity",
            "billing",
            "mod_ssp",
            "original_posted",
        )
    ]
    revenue, remaining, quantities, ssp, delivered, changes, billing, mod_ssp, posted = columns
    flags = _list(params, "nondistinct")
    line_keys = _list(params, "line_keys")
    if (
        any(len(column) != len(names) for column in columns)
        or len(flags) != len(names)
        or not set(flags) <= {"true", "false"}
        or key not in names
    ):
        raise ValueError(f"{formula_id}: params keys and columns disagree")
    if len(line_keys) != len(inputs) or not set(line_keys) <= set(names):
        raise ValueError(f"{formula_id}: params line_keys disagree with the inputs")
    for name, value in zip(line_keys, inputs, strict=True):
        if format_exact(value) != format_exact(mod_ssp[names.index(name)]):
            raise ValueError(f"{formula_id}: an input is not the mod SSP of its key")
    after = [item + change for item, change in zip(quantities, changes, strict=True)]
    weights = [
        Fraction(0) if units == 0 else max(Fraction(0), item + change)
        for units, item, change in zip(after, ssp, mod_ssp, strict=True)
    ]
    pool = sum(remaining, Fraction(0)) + sum(billing, Fraction(0))
    total = sum(weights, Fraction(0))
    index = names.index(key)
    if role == "total_ssp":
        # Σ w_j = Σ RemSSP′_j: the stored ``original_total_contract_ssp`` of an obligation the
        # template creates (CV-50 rev 1.29; D-98 candidate 124) — the template's own parameters.
        return total
    if role == "weight":
        # w_key ÷ Σ w: the governed ``allocation_weight`` ratio of the prospective template.
        if total == 0:
            raise ValueError(f"{formula_id}: Σ w is 0 — no weight ratio (DEV-054)")
        return weights[index] / total
    receiver = False
    if total != 0:
        share = pool * weights[index] / total
    else:
        members = [units == 0 and amount > 0 for units, amount in zip(after, posted, strict=True)]
        basis = sum(
            (amount for amount, member in zip(posted, members, strict=True) if member), Fraction(0)
        )
        if basis == 0 and pool != 0:
            raise ValueError(f"{formula_id}: nothing absorbs the pool (NON_FINITE_AMOUNT)")
        receiver = basis != 0 and members[index]
        share = pool * posted[index] / basis if receiver else Fraction(0)
    x_exact = revenue[index] + share
    divisor = delivered[index] + after[index]
    if receiver:
        expected = x_exact
    elif total != 0 and flags[index] == "true" and divisor != 0:
        expected = delivered[index] / divisor * x_exact
    else:
        expected = revenue[index]
    if _rational(params, "revenue_after") != expected:
        raise ValueError(f"{formula_id}: params revenue_after is not the template revenue")
    return x_exact


def _mod_legacy_pob_vc(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``mod.legacy.pob_vc.v1``: the POB-specific price change (S06-R-28; legacy 05 §3.4, §3.5).

    ``role`` ``exact``: no inputs; X′ = ``remaining_allocation`` + ``billing`` + ``revenue``, the
    targeted obligation's allocation with the change M. Params ``remaining_ssp`` and
    ``ssp_delivered`` give W and SSPDel, and ``revenue_after`` must equal (A1 + E) ÷ W × SSPDel,
    or E when W = 0. ``role`` ``amount``: as ``mod.legacy.retrospective.v1``.
    """
    formula_id = "mod.legacy.pob_vc.v1"
    role = _param(params, "role")
    if role == "amount":
        return _legacy_amount(inputs, params, formula_id)
    if role != "exact":
        raise ValueError(f"{formula_id} does not know the role {role}")
    _require_arity(inputs, 0, formula_id)
    revenue = _rational(params, "revenue")
    total = _rational(params, "remaining_allocation") + _rational(params, "billing") + revenue
    delivered = _rational(params, "ssp_delivered")
    weight = _rational(params, "remaining_ssp") + delivered
    expected = revenue if weight == 0 else total / weight * delivered
    if _rational(params, "revenue_after") != expected:
        raise ValueError(f"{formula_id}: params revenue_after is not the template revenue")
    return total


# --- Stage 10 billing (ENGINE_SPEC_B §10.2.1, §10.2.2, §10.5; BUILD_SPEC ENC-11) -----------------


def _attribution(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``bil.attribution.v1``: billing attributed to one obligation (S10-R-01, S10-R-03).

    ``mode`` ``sum``: Σ inputs, the signed referenced lines and the attributed cumulative for
    ``billed_cum``, or the document shares for ``billed_attributed_cum``. ``apportion``: input the
    signed unreferenced total T of one document, negative for a credit memo; |T| is apportioned by
    largest remainder over params ``weights`` and ``keys``, the sign applied after apportioning, and
    the share of ``key`` is returned (POLICIES ALG-02 step 3; CHK-003c).
    """
    formula_id = "bil.attribution.v1"
    mode = _param(params, "mode")
    if mode == "sum":
        return sum(inputs, Fraction(0))
    if mode != "apportion":
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    total = _minor_value(inputs[0], minor_unit, formula_id)
    share = _keyed_share(abs(total), params)
    return Fraction(-share if total < 0 else share, 10**minor_unit)


def _remaining_billing(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``bil.remaining_billing.v1``: input ``billed_cum`` at the version date (S10-R-05).

    round(plan) − (billed − ``billed_before``): the billing plan of the segment in force (params
    ``plan``, exact currency units) less the billing since its boundary (``billed_before`` in minor
    units; 0 on the inception basis); ENGINE_SPEC Table 0.9-A.
    """
    formula_id = "bil.remaining_billing.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    plan = round_half_up(_rational(params, "plan"), minor_unit)
    return Fraction(plan + _minor(params, "billed_before"), 10**minor_unit) - inputs[0]


def _unconditional_billing(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``bil.unconditional_date.v1``: Σ inputs, the attributed billing of the documents whose lines
    are unconditional by ``as_of``, less credit memos (S10-R-06 to S10-R-08)."""
    return sum(inputs, Fraction(0))


# --- Stage 10 positions, refund liabilities, return assets (ENGINE_SPEC_B §10.2.3 to §10.2.5) ---


def _signed_sum_listed(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> Fraction:
    # Σ sign_i × input_i with params signs "+|-|..." naming one sign per input.
    signs = _list(params, "signs")
    if len(signs) != len(inputs) or any(sign not in ("+", "-") for sign in signs):
        raise ValueError(f"{formula_id}: params signs must give + or - for every input")
    return sum(
        (value if sign == "+" else -value for sign, value in zip(signs, inputs, strict=True)),
        Fraction(0),
    )


def _net_position(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.net_position.v1``: NP = B_u + DT + NC + IE − II − R_ctl − RC − RL (S10-R-09).

    Inputs are the component nodes and source references of one (group, contracting entity) at a
    period end, each signed by params ``signs``: unconditional billing, deposits transferred,
    noncash unconditional amounts and interest expense enter with +; revenue targets, concessions
    created, interest income, the receivable contra and the open refund-liability components with
    −; the credit-memo consumption of a concession component with + (L2-4-Q-13).
    """
    return _signed_sum_listed(inputs, params, "pos.net_position.v1")


def _position_obligation(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.obligation.v1`` (S10-R-12): mode ``difference``: ``billed_cum`` − ``revenue_cum``
    (input 1, absent for an obligation without revenue targets); mode ``sum``: Σ inputs, the
    obligation positions of one contract and contracting entity."""
    formula_id = "pos.obligation.v1"
    mode = _param(params, "mode")
    if mode == "sum":
        return sum(inputs, Fraction(0))
    if mode != "difference":
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    if len(inputs) not in (1, 2):
        raise ValueError(f"{formula_id} takes 1 or 2 inputs, not {len(inputs)}")
    return inputs[0] - (inputs[1] if len(inputs) == 2 else Fraction(0))


def _refund_return(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rl.return.v1``: round(p_ref × E_b), the refund liability for expected returns of units
    billed (POLICIES ALG-06 step 3; ENGINE_SPEC_B §10.2.4)."""
    formula_id = "rl.return.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    amount = round_half_up(_rational(params, "p_ref") * _rational(params, "e_b"), minor_unit)
    return Fraction(amount, 10**minor_unit)


def _refund_return_v2(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rl.return.v2``: round(p_ref × E_b) with E_b the ``return_refundable_units`` node (input
    0) stage 09 published (POLICIES ALG-06 step 3; ENGINE_SPEC_B §10.2.4; D-91 C606-01 (7)).
    ``rl.return.v1`` stays registered for stored traces (DG-KRN-EXP-04)."""
    formula_id = "rl.return.v2"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    amount = round_half_up(_rational(params, "p_ref") * inputs[0], minor_unit)
    return Fraction(amount, 10**minor_unit)


def _units_billed(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.units_billed.v1``: U_b of ALG-06 step 3 (ENGINE_SPEC_B S09-R-23a; D-91).

    Σ over the inputs, each a counted ``BILLING_RECORDED`` source: a direct line contributes its
    cited amount; an unreferenced document (its input index listed in params ``apportioned``, ``|``
    separated) contributes largest_remainder(its cited total in minor units, ``weights_<i>``,
    ``keys_<i>``)[``key``] ÷ 10^``minor_unit``, the S10-R-01 share recomputed rather than replayed
    (lists ``|`` separated). The total is divided by ``p_ref``; ``p_ref`` = 0 gives 0.
    """
    formula_id = "returns.units_billed.v1"
    p_ref = _rational(params, "p_ref")
    if p_ref == 0:
        return Fraction(0)
    apportioned = (
        {int(index) for index in _list(params, "apportioned")} if "apportioned" in params else set()
    )
    if any(index >= len(inputs) for index in apportioned):
        raise ValueError(f"{formula_id}: params apportioned names an absent input")
    minor_unit = minor_unit_of(params)
    total = Fraction(0)
    for index, value in enumerate(inputs):
        if index in apportioned:
            share = _keyed_share(
                _minor_value(value, minor_unit, formula_id),
                params,
                weights=f"weights_{index}",
                keys=f"keys_{index}",
            )
            total += Fraction(share, 10**minor_unit)
        else:
            total += value
    return total / p_ref


def _refundable_units(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.refundable_units.v1``: E_b = max(0, min(E, U_b − Y)) (ALG-06 step 3; S09-R-23a).

    Inputs: the ``return_expected_units`` node E and the ``return_units_billed`` node U_b; param
    ``returned_units`` Y.
    """
    formula_id = "returns.refundable_units.v1"
    _require_arity(inputs, 2, formula_id)
    expected, units = inputs
    return max(Fraction(0), min(expected, units - _rational(params, "returned_units")))


def _refund_vc_target(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rl.vc_target.v1``: the ``refund_liability_target`` of the pinned version (input 0), rounded
    half up to the minor unit; 0 without an input (§10.2.4; 04 T-CON-13 rev 1.2).

    Mode ``excess`` (D-87 L5-3-Q-7 = L6-5-Q-11, a version without a target): max(0, min(K,
    ``billed`` − ``revenue`` − ``other`` − ``taken``)), with K the constrained reduction (input 0)
    rounded half up and the params in whole minor units."""
    formula_id = "rl.vc_target.v1"
    if params.get("mode") == "excess":
        _require_arity(inputs, 1, formula_id)
        minor_unit = minor_unit_of(params)
        excess = (
            _minor(params, "billed")
            - _minor(params, "revenue")
            - _minor(params, "other")
            - _minor(params, "taken")
        )
        share = max(0, min(round_half_up(inputs[0], minor_unit), excess))
        return Fraction(share, 10**minor_unit)
    if len(inputs) > 1:
        raise ValueError(f"{formula_id} takes 0 or 1 inputs, not {len(inputs)}")
    minor_unit = minor_unit_of(params)
    value = inputs[0] if inputs else Fraction(0)
    return Fraction(round_half_up(value, minor_unit), 10**minor_unit)


def _refund_event_component(formula_id: str) -> Formula:
    """An event-created component (S10-R-14, S10-R-15).

    Mode ``open``: the created amount (input 0) less the consumptions cited (inputs 1 to n). Mode
    ``apportion``: the share of params ``key`` in the largest-remainder apportionment of the created
    amount (input 0) over params ``keys`` and ``weights`` (ALG-01 §2.1.2).
    """

    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        mode = _param(params, "mode")
        if mode == "open":
            if not inputs:
                raise ValueError(f"{formula_id} needs the created amount as input 0")
            return inputs[0] - sum(inputs[1:], Fraction(0))
        if mode != "apportion":
            raise ValueError(f"{formula_id} does not know the mode {mode}")
        _require_arity(inputs, 1, formula_id)
        minor_unit = minor_unit_of(params)
        total = _minor_value(inputs[0], minor_unit, formula_id)
        return Fraction(_keyed_share(total, params), 10**minor_unit)

    return formula


def _refund_consumption(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``rl.consumption.v1``: the part of one credit memo (input 0, its amount) that consumes a
    component: min(``open_before``, max(0, amount − ``taken_before``)), where ``taken_before`` is
    the memo amount already taken by earlier components (S10-R-14; S10-INV-07)."""
    formula_id = "rl.consumption.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    amount = _minor_value(inputs[0], minor_unit, formula_id)
    take = min(_minor(params, "open_before"), max(0, amount - _minor(params, "taken_before")))
    return Fraction(take, 10**minor_unit)


def _return_asset(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``returns.return_asset.v1`` (S10-R-16): mode ``balance``: round(``unit`` × ``expected``),
    with unit = max(0, k − c_rec); mode ``derecognised``: Σ round(``unit`` × q_i) over params
    ``quantities``, min(units returned, E before the return) per return event (JET-07d)."""
    formula_id = "returns.return_asset.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    unit = _rational(params, "unit")
    mode = _param(params, "mode")
    if mode == "balance":
        amount = round_half_up(unit * _rational(params, "expected"), minor_unit)
    elif mode == "derecognised":
        amount = sum(round_half_up(unit * q, minor_unit) for q in _rationals(params, "quantities"))
    else:
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    return Fraction(amount, 10**minor_unit)


# --- Stage 10 receivables and presentation split (ENGINE_SPEC_B §10.2.6, §10.2.7; ENC-13) -------


def _split_ca_ur(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.split_ca_ur.v1``: input the ``net_position`` node (ALG-02 steps 2, 3 and 6).

    U = Σ max(0, R_p − B_p) over params ``relief`` and ``billed`` (minor units, one pair per
    obligation with an unconditional right; S10-R-20). Mode ``cl``: max(0, NP); ``ur``: min(D, U)
    with D = max(0, −NP); ``ca``: D − UR. Mode ``parts`` (ENC-14): inputs are
    ``netting_reclass_amount`` nodes and params ``parts`` the part of each in the role presented,
    summed: UR and CA under POL-121 ``CUMULATIVE_SSP_DELIVERED`` (ALG-02 step 5) and the member
    balances of S10-R-23. Mode ``member_cl``: input the group's contract liability, apportioned by
    largest remainder over params ``keys`` and ``weights``; the share of ``key`` (S10-R-23).
    """
    formula_id = "pos.split_ca_ur.v1"
    mode = _param(params, "mode")
    if mode == "parts":
        return _reclass_parts(inputs, params, formula_id)
    if mode == "member_cl":
        _require_arity(inputs, 1, formula_id)
        minor_unit = minor_unit_of(params)
        liability = _minor_value(inputs[0], minor_unit, formula_id)
        share = _share_of(
            liability, _list(params, "keys"), _rationals(params, "weights"), _param(params, "key")
        )
        return Fraction(share, 10**minor_unit)
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    net = _minor_value(inputs[0], minor_unit, formula_id)
    relief, billed = _rationals(params, "relief"), _rationals(params, "billed")
    if len(relief) != len(billed):
        raise ValueError(f"{formula_id}: params relief and billed disagree")
    unconditional = sum(
        (max(Fraction(0), r - b) for r, b in zip(relief, billed, strict=True)), Fraction(0)
    )
    debit = max(0, -net)
    receivable = min(Fraction(debit), unconditional)
    if mode == "cl":
        amount = Fraction(max(0, net))
    elif mode == "ur":
        amount = receivable
    elif mode == "ca":
        amount = debit - receivable
    else:
        raise ValueError(f"{formula_id} does not know the mode {mode}")
    scale: int = 10**minor_unit
    return amount / scale


def _receivable_contra(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.receivable_contra.v1``: round(B_u × κ), input the unconditional billing excluding tax,
    params ``kappa`` (S10-R-18; POLICIES JET-04c; CHK-138)."""
    formula_id = "pos.receivable_contra.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    return Fraction(
        round_half_up(inputs[0] * _rational(params, "kappa"), minor_unit), 10**minor_unit
    )


def _ar_balance(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``bil.ar_balance.v1``: Σ inputs, the unconditional invoice totals including tax less the
    credit memos and cash payments applied to them (S10-R-19)."""
    return sum(inputs, Fraction(0))


def _accretion_attribution(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.accretion_attribution.v1``: the share of params ``key`` in the largest-remainder
    apportionment of the net accretion, Σ inputs signed by params ``signs`` (JET-11a income +,
    JET-11b expense −), over params ``keys`` and ``weights`` (S10-R-20; D-76; CV-34)."""
    formula_id = "pos.accretion_attribution.v1"
    minor_unit = minor_unit_of(params)
    net = _minor_value(_signed_sum_listed(inputs, params, formula_id), minor_unit, formula_id)
    return Fraction(_keyed_share(net, params), 10**minor_unit)


# --- Stage 10 reclass attribution and current parts (ENGINE_SPEC_B §10.2.7, §10.2.8; ENC-14) ---


def _share_of(total: int, keys: Sequence[str], weights: Sequence[Fraction], key: str) -> int:
    # The share of ``key`` in largest_remainder(total, weights, keys); 0 when nothing is apportioned
    # or ``key`` is outside the pool (ALG-01 §2.1.2).
    if len(keys) != len(weights):
        raise ValueError("params keys and weights disagree")
    if total == 0 or key not in keys:
        return 0
    return _apportion(total, weights, keys)[list(keys).index(key)]


def _reclass_parts(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> Fraction:
    # Σ params parts, one per input node, each within 0 and its node's value (S10-INV-03).
    minor_unit = minor_unit_of(params)
    parts = _rationals(params, "parts")
    if len(parts) != len(inputs):
        raise ValueError(f"{formula_id}: params parts must give one part per input")
    scale: int = 10**minor_unit
    for part, value in zip(parts, inputs, strict=True):
        if part.denominator != 1 or not 0 <= Fraction(part, scale) <= value:
            raise ValueError(f"{formula_id}: a part lies outside its attribution")
    return sum(parts, Fraction(0)) / scale


def _reclass_pob_debit_positions(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.reclass_attribution.pob_debit_positions.v1``: input the ``net_position`` node.

    D = max(0, −NP); U = Σ max(0, R_p − B_p) over params ``relief`` and ``billed`` (minor units, one
    pair per obligation of params ``ur_keys``, whose right is unconditional); UR = min(D, U); CA =
    D − UR. UR is apportioned by largest remainder over ``ur_keys`` with weights max(0, R_p − B_p),
    CA over params ``ca_keys`` and ``ca_weights`` (the ALG-02 step 5 fallback chain the engine
    selected, recorded in ``ca_basis``); the value is the UR share plus the CA share of ``key``
    (POLICIES ALG-02 step 5; S10-R-22; CHK-010).
    """
    formula_id = "pos.reclass_attribution.pob_debit_positions.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    net = _minor_value(inputs[0], minor_unit, formula_id)
    relief, billed = _rationals(params, "relief"), _rationals(params, "billed")
    ur_keys = _list(params, "ur_keys")
    if not len(relief) == len(billed) == len(ur_keys):
        raise ValueError(f"{formula_id}: params relief, billed and ur_keys disagree")
    ur_weights = [max(Fraction(0), r - b) for r, b in zip(relief, billed, strict=True)]
    unconditional = sum(ur_weights, Fraction(0))
    if unconditional.denominator != 1:
        raise ValueError(f"{formula_id}: relief and billed must be whole minor units")
    debit = max(0, -net)
    receivable = min(debit, unconditional.numerator)
    key = _param(params, "key")
    share = _share_of(receivable, ur_keys, ur_weights, key)
    share += _share_of(
        debit - receivable, _list(params, "ca_keys"), _rationals(params, "ca_weights"), key
    )
    return Fraction(share, 10**minor_unit)


def _reclass_cumulative_ssp_delivered(
    inputs: Sequence[Fraction], params: Mapping[str, str]
) -> Fraction:
    """``pos.reclass_attribution.cumulative_ssp_delivered.v1``: input the ``net_position`` node.

    D = max(0, −NP) apportioned by largest remainder over the non-VC obligations of params ``keys``
    with ``weights``, the first set whose sum is not 0 of cumulative SSP delivered, cumulative
    revenue, posted allocation and resolved SSP (``basis``); the share of ``key``, 0 for a VC line
    (POL-121 parity; DEV-057, DEV-058; CHK-011).
    """
    formula_id = "pos.reclass_attribution.cumulative_ssp_delivered.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    debit = max(0, -_minor_value(inputs[0], minor_unit, formula_id))
    share = _share_of(
        debit, _list(params, "keys"), _rationals(params, "weights"), _param(params, "key")
    )
    return Fraction(share, 10**minor_unit)


def _reclass_no_measured_period(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.reclass_attribution.no_measured_period.v1``: no input, 0.

    The contracting entity of obligation ``key`` has no period from the group's inception period
    inside its evaluation horizon (ENGINE_SPEC_B C-05), so no period-end reclass exists to attribute
    at the version date ``as_of`` (S10-R-22 rev 1.100).
    """
    formula_id = "pos.reclass_attribution.no_measured_period.v1"
    _require_arity(inputs, 0, formula_id)
    _param(params, "as_of")
    _param(params, "key")
    return Fraction(0)


def _current_split(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``pos.current_split.v1``: current parts of the presented balances (S10-R-24, S10-R-25).

    Mode ``none`` (POL-124 ``NONE``): no inputs, 0. ``cl``: input the contract liability; min(CL,
    max(0, Σ params ``relief``)), the revenue relief expected within 12 months per obligation in
    minor units. ``ca``: first input the contract asset, then ``netting_reclass_amount`` nodes of
    obligations ending within 12 months or without an end date, params ``parts`` their contract
    asset parts; min(CA, Σ parts). ``ur``: input the unbilled receivable, all current.
    """
    formula_id = "pos.current_split.v1"
    mode = _param(params, "mode")
    if mode == "none":
        _require_arity(inputs, 0, formula_id)
        return Fraction(0)
    if mode == "ur":
        _require_arity(inputs, 1, formula_id)
        return inputs[0]
    if mode == "cl":
        _require_arity(inputs, 1, formula_id)
        scale: int = 10 ** minor_unit_of(params)
        relief = sum(_rationals(params, "relief"), Fraction(0)) / scale
        return min(inputs[0], max(Fraction(0), relief))
    if mode == "ca":
        if not inputs:
            raise ValueError(f"{formula_id} mode ca takes the contract asset first")
        return min(inputs[0], _reclass_parts(inputs[1:], params, formula_id))
    raise ValueError(f"{formula_id} does not know the mode {mode}")


# --- Stage 11 contract costs (ENGINE_SPEC_B §11.2.1 to §11.2.5; ENC-15) ---

_EXPENSE_REASONS: Final = frozenset(
    {"NOT_INCREMENTAL", "EXPEDIENT_ONE_YEAR", "FULFILMENT_NOT_ATTESTED", "CONTRACT_NOT_ACTIVE"}
)

# Formulas whose node-id inputs ``reevaluate`` supplies as DG-KRN-EXP-03 EXACT values (the
# recomputed value plus the input node's stored ``rounding_residue``), so that a raw operand bound
# at emission through ``TraceBuilder.exact`` meets the SAME reconstruction on re-evaluation (D-98
# candidate 117 F1, Codex 0235; dev-guide clause under DG-KRN-EXP-04, number pending). Every other
# formula receives the recomputed values.
EXACT_INPUT_FORMULAS: Final[frozenset[str]] = frozenset(
    {"alloc.original_total.v1", "alloc.original_weight.v1", "books.unit_revenue_rate.v1"}
)
_MINOR_INTEGER: Final = re.compile(r"-?[0-9]+")


def _cost_capitalise(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.capitalise.v1``: input the ``COST_INCURRED`` amount, capitalised as it stands; params
    record the gate result and the policy values (S11-R-01 to S11-R-04; JET-09a, 09a′)."""
    _require_arity(inputs, 1, "cost.capitalise.v1")
    return inputs[0]


def _cost_expense_reason(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.expense_reason.v1``: input the amount of a cost not capitalised; params ``reason``
    (§11.1 ``expensed_costs``; 340-40-25-3, 25-4, 25-5; S11-R-01)."""
    formula_id = "cost.expense_reason.v1"
    _require_arity(inputs, 1, formula_id)
    if _param(params, "reason") not in _EXPENSE_REASONS:
        raise ValueError(f"{formula_id}: params reason is unknown")
    return inputs[0]


def _cost_segments(params: Mapping[str, str], formula_id: str) -> list[tuple[date, date, int]]:
    # params segments "start/end/base;..." with ISO dates and whole minor units, ascending.
    value = _param(params, "segments")
    segments: list[tuple[date, date, int]] = []
    for item in value.split(";") if value else []:
        start, end, base = (item.split("/") + ["", "", ""])[:3]
        if not (
            _ISO_DATE.fullmatch(start)
            and _ISO_DATE.fullmatch(end)
            and _MINOR_INTEGER.fullmatch(base)
        ):
            raise ValueError(f"{formula_id}: params segments must be start/end/base triples")
        segments.append((date.fromisoformat(start), date.fromisoformat(end), int(base)))
    return segments


def _amortise_straight_line(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.amortise.straight_line.v1``: input the ``cost_capitalised`` node.

    Σ over params ``segments`` (start/end/base, ascending) of ALG-01 §2.1.3 over each base at f =
    ALG-11 ``convention`` over [start, end], evaluated at ``as_of`` for the last segment and at the
    day before the next segment starts otherwise; ``periods`` holds the entity calendar (S11-R-06,
    S11-R-07; JET-09b).
    """
    formula_id = "cost.amortise.straight_line.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    as_of = _date(params, "as_of")
    convention = _param(params, "convention")
    calendar = _calendar(params)
    segments = _cost_segments(params, formula_id)
    total = 0
    for index, (start, end, base) in enumerate(segments):
        if as_of < start:
            break
        stop = segments[index + 1][0] - timedelta(days=1) if index + 1 < len(segments) else as_of
        d = min(as_of, stop)
        if d < start:
            progress_ratio = Fraction(0)
        elif start > end:
            progress_ratio = Fraction(1)
        else:
            progress_ratio = progress.time_fraction(convention, start, end, d, calendar=calendar)
        total += cumulative_posted(Fraction(base, scale), base, progress_ratio, minor_unit)
    return Fraction(total, scale)


def _amortise_proportional(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.amortise.proportional.v1``: input the ``cost_capitalised`` node; Σ over params
    ``segments`` (base/progress) of ALG-01 §2.1.3 over each base at its progress, the related
    revenue since the segment start over the allocation not recognised at its start (POL-143)."""
    formula_id = "cost.amortise.proportional.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    value = _param(params, "segments")
    total = 0
    for item in value.split(";") if value else []:
        base, _, ratio = item.partition("/")
        if not (_MINOR_INTEGER.fullmatch(base) and _RATIONAL.fullmatch(ratio)):
            raise ValueError(f"{formula_id}: params segments must be base/progress pairs")
        total += cumulative_posted(
            Fraction(int(base), scale), int(base), Fraction(ratio), minor_unit
        )
    return Fraction(total, scale)


def _cost_recoverable(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.recoverable.v1``: inputs the related obligations' posted revenue targets.

    consideration − Σ inputs + renewal − max(0, eac − costs), params in minor units: the
    unconstrained, credit-adjusted consideration allocated to the related obligations, the
    anticipated renewals of the ``RENEWAL_EXPECTATION`` version in force, the latest ``EAC``
    expected total (``none``: remaining costs 0) and the progress costs incurred (340-40-35-3, 35-4;
    S11-R-09; D-76).
    """
    scale: int = 10 ** minor_unit_of(params)
    eac = _param(params, "eac")
    remaining = 0 if eac == "none" else max(0, _minor(params, "eac") - _minor(params, "costs"))
    amount = _minor(params, "consideration") + _minor(params, "renewal") - remaining
    return Fraction(amount, scale) - sum(inputs, Fraction(0))


def _cost_impair(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.impair.us.v1``: input the ``cost_recoverable`` node.

    Params ``carrying`` (minor units per asset of ``keys``, after amortisation and before the test),
    ``key`` and ``previous``. The impairment min(total, max(0, total − recoverable)) of the total
    carrying amount is apportioned by carrying amount; previous + the share of ``key`` (S11-R-08 rev
    1.3; JET-09c).
    """
    formula_id = "cost.impair.us.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    recoverable = _minor_value(inputs[0], minor_unit, formula_id)
    carrying = _rationals(params, "carrying")
    total = sum(carrying, Fraction(0))
    if total.denominator != 1:
        raise ValueError(f"{formula_id}: params carrying must be whole minor units")
    impairment = min(total.numerator, max(0, total.numerator - recoverable)) if total > 0 else 0
    share = _share_of(impairment, _list(params, "keys"), carrying, _param(params, "key"))
    return Fraction(_minor(params, "previous") + share, 10**minor_unit)


def _cost_reversal(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.impair.ifrs_reversal.v1``: input the ``cost_recoverable`` node.

    ``previous`` under POL-144 ``PROHIBITED`` or when the group was impaired at ``as_of``. Otherwise
    the recoverable amount is shared by ``weights`` over ``keys`` and previous + min(open, max(0,
    min(share, unimpaired) − carrying)) is returned, params in minor units (S11-R-10; IFRS 15.104;
    JET-09d; S11-INV-04).
    """
    formula_id = "cost.impair.ifrs_reversal.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    scale: int = 10**minor_unit
    previous = _minor(params, "previous")
    if _param(params, "policy") != "REQUIRED_CAPPED" or _param(params, "impaired_now") == "true":
        return Fraction(previous, scale)
    weights = _rationals(params, "weights")
    if sum(weights, Fraction(0)) <= 0:
        return Fraction(previous, scale)
    recoverable = _minor_value(inputs[0], minor_unit, formula_id)
    share = _share_of(recoverable, _list(params, "keys"), weights, _param(params, "key"))
    raised = max(0, min(share, _minor(params, "unimpaired")) - _minor(params, "carrying"))
    return Fraction(previous + min(raised, _minor(params, "open")), scale)


def _cost_carrying(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.carrying.v1``: Σ inputs signed by params ``signs``: capitalised +, amortised −,
    impaired −, reversed +, clawback −, accelerated − (S11-INV-01)."""
    return _signed_sum_listed(inputs, params, "cost.carrying.v1")


# --- Stage 11 clawbacks, acceleration and loss provisions (ENGINE_SPEC_B §11.2.6, §11.2.7) ---

_FLAGS: Final = frozenset({"true", "false"})
_ACCELERATE: Final = "ACCELERATE_TO_REMAINING_BENEFIT"


def _whole(values: Sequence[Fraction], name: str, count: int, formula_id: str) -> list[int]:
    # params ``name`` lists ``count`` whole minor-unit amounts.
    if len(values) != count or any(value.denominator != 1 for value in values):
        raise ValueError(f"{formula_id}: params {name} must list {count} whole minor-unit amounts")
    return [value.numerator for value in values]


def _cost_clawback(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.clawback.v1``: inputs the amounts of the ``COST_INCURRED`` clawbacks that named the
    asset's payee and plan through ``as_of``, in ENG-06 order.

    Params ``carrying`` (the asset's carrying amount after amortisation through each clawback date)
    and ``taken_before`` (the part of each amount taken from older capitalisations), one per input
    in minor units: Σ min(max(0, amount − taken_before), carrying) (S11-R-12; JET-09f).
    """
    formula_id = "cost.clawback.v1"
    minor_unit = minor_unit_of(params)
    count = len(inputs)
    carrying = _whole(_rationals(params, "carrying"), "carrying", count, formula_id)
    taken = _whole(_rationals(params, "taken_before"), "taken_before", count, formula_id)
    total = 0
    for amount, before, value in zip(inputs, taken, carrying, strict=True):
        total += min(max(0, _minor_value(amount, minor_unit, formula_id) - before), value)
    return Fraction(total, 10**minor_unit)


def _cost_accelerate(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``cost.accelerate.v1``: input the ``cost_capitalised`` node.

    Params per ``CONTRACT_TERMINATED`` affecting the related obligations through ``as_of``
    (``events``): ``policy`` (POL-145 at the termination date), ``carrying`` (after amortisation
    through that date), ``before`` and ``after`` (remaining allocation of the related obligations,
    minor units) and ``all_ended``. ρ = 0 when every related obligation ended, 1 when ``before`` is
    0, else min(1, after ÷ before); Σ round(carrying × (1 − ρ)) over the events under
    ``ACCELERATE_TO_REMAINING_BENEFIT`` (S11-R-13; JET-09e; CHK-112).
    """
    formula_id = "cost.accelerate.v1"
    _require_arity(inputs, 1, formula_id)
    minor_unit = minor_unit_of(params)
    count = len(_list(params, "events"))
    policies = _list(params, "policy")
    ended = _list(params, "all_ended")
    if len(policies) != count or len(ended) != count or any(flag not in _FLAGS for flag in ended):
        raise ValueError(f"{formula_id}: params policy and all_ended must give one value per event")
    carrying = _whole(_rationals(params, "carrying"), "carrying", count, formula_id)
    before = _whole(_rationals(params, "before"), "before", count, formula_id)
    after = _whole(_rationals(params, "after"), "after", count, formula_id)
    total = 0
    for index in range(count):
        if policies[index] != _ACCELERATE:
            continue
        if ended[index] == "true":
            ratio = Fraction(0)
        elif before[index] == 0:
            ratio = Fraction(1)
        else:
            ratio = min(Fraction(1), Fraction(max(0, after[index]), before[index]))
        total += round_half_up(Fraction(carrying[index]) * (1 - ratio), 0)
    return Fraction(total, 10**minor_unit)


def _loss_tp_unconstrained(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``loss.tp_unconstrained.v1``: no inputs.

    Params ``total`` (currency units: the latest stage 04 unconstrained, credit-adjusted build-up
    total at ``as_of``, or the contract's exact allocation when ``source`` is ``allocation``),
    ``unit_weight`` and ``contract_weight`` (Σ x_exact of the unit's and of the contract's
    obligations): round(total × unit_weight ÷ contract_weight), round(total) when the contract
    weight is 0 (S11-R-11a, S11-R-11b; POL-153).
    """
    formula_id = "loss.tp_unconstrained.v1"
    _require_arity(inputs, 0, formula_id)
    minor_unit = minor_unit_of(params)
    total = _rational(params, "total")
    contract_weight = _rational(params, "contract_weight")
    exact = (
        total
        if contract_weight == 0
        else total * _rational(params, "unit_weight") / contract_weight
    )
    return Fraction(round_half_up(exact, minor_unit), 10**minor_unit)


def _loss_eac(params: Mapping[str, str]) -> int | None:
    # params ``eac``: the EAC total costs in minor units, or ``none``.
    return None if _param(params, "eac") == "none" else _minor(params, "eac")


def _loss_expected_margin(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``loss.expected_margin.v1``: input the ``tp_unconstrained_credit_adjusted`` node; the
    expected consideration less params ``eac`` (0 when ``none``) (T-CON-17 ``expected_margin``)."""
    formula_id = "loss.expected_margin.v1"
    _require_arity(inputs, 1, formula_id)
    eac = _loss_eac(params) or 0
    return inputs[0] - Fraction(eac, 10 ** minor_unit_of(params))


def _loss_required_provision(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``loss.required_provision.v1``: first input the ``tp_unconstrained_credit_adjusted`` node,
    then the unit obligations' posted revenue targets.

    Params ``eac`` and ``costs`` (the progress-input costs to date), minor units: 0 when ``eac`` is
    ``none``; else max(0, max(0, eac − TP_u) − max(0, costs − Σ revenue)) (S11-R-14; POL-153;
    JET-12; S11-INV-05).
    """
    formula_id = "loss.required_provision.v1"
    if not inputs:
        raise ValueError(f"{formula_id} takes the expected consideration first")
    eac = _loss_eac(params)
    if eac is None:
        return Fraction(0)
    minor_unit = minor_unit_of(params)
    consideration = _minor_value(inputs[0], minor_unit, formula_id)
    revenue = sum(_minor_value(value, minor_unit, formula_id) for value in inputs[1:])
    total_loss = max(0, eac - consideration)
    margin_loss = max(0, _minor(params, "costs") - revenue)
    return Fraction(max(0, total_loss - margin_loss), 10**minor_unit)


def _loss_movement(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``loss.movement.v1``: inputs the required provision at ``as_of`` and, when the unit was
    tested at an earlier period end, the previous required provision; their difference (S11-R-14;
    JET-12)."""
    if len(inputs) not in (1, 2):
        raise ValueError(f"loss.movement.v1 takes 1 or 2 inputs, not {len(inputs)}")
    return inputs[0] - (inputs[1] if len(inputs) == 2 else Fraction(0))


def _prior_period(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``estimate.prior_period.v1``: revenue from performance before the period (S08-R-14 to 16).

    Inputs: the posted part of each boundary k = 1 to ``boundaries``, which equals
    round(``e_after_<k>`` − ``e_before_<k>``). Each late carry i = 1 to ``carries`` adds
    ``late_target_<i>`` − ``late_posted_<i>`` (minor units). Params ``minor_unit``,
    ``period_start``, ``rule_<k>`` and ``late_origin_<i>``.
    """
    formula_id = "estimate.prior_period.v1"
    minor_unit = minor_unit_of(params)
    boundaries = _minor(params, "boundaries")
    _require_arity(inputs, boundaries, formula_id)
    total = 0
    for index in range(1, boundaries + 1):
        change = _rational(params, f"e_after_{index}") - _rational(params, f"e_before_{index}")
        part = round_half_up(change, minor_unit)
        if _minor_value(inputs[index - 1], minor_unit, formula_id) != part:
            raise ValueError(f"{formula_id}: a boundary part disagrees with its exact values")
        total += part
    for index in range(1, _minor(params, "carries") + 1):
        total += _minor(params, f"late_target_{index}") - _minor(params, f"late_posted_{index}")
    return Fraction(total, 10**minor_unit)


# --- Stage 08 late events (ENGINE_SPEC §8.4, §8.6; BUILD_SPEC ENB-11) ----------------------------

_LOCKED_STATES: Final = frozenset({"closed", "permanently_locked"})


def _late_assign(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``late.assign.v1``: periods carried from the effective to the posting period (S08-R-08).

    No inputs. Params ``states``: the E-04 states of the book from the effective (origin) period
    through the posting period, in calendar order. The first is ``closed`` or
    ``permanently_locked``, and the last is the first ``open``, ``closing`` or ``reopened`` state.
    Params ``origin_period_key``, ``posting_period_key``, ``effective_date`` and ``event_key``.
    """
    formula_id = "late.assign.v1"
    _require_arity(inputs, 0, formula_id)
    _param(params, "origin_period_key")
    _param(params, "posting_period_key")
    states = _list(params, "states")
    if len(states) < 2 or states[0] not in _LOCKED_STATES:
        raise ValueError(f"{formula_id}: the effective period is not closed or locked")
    carried = next(
        (index for index, state in enumerate(states) if state in dates.POSTABLE_STATES), None
    )
    if carried != len(states) - 1:
        raise ValueError(f"{formula_id}: the posting period is not the first postable period")
    return Fraction(carried)


# --- Stage 12 intercompany pairs (ENGINE_SPEC_B §12.5; BUILD_SPEC END-3) -------------------------


def _ent_pair(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ent.pair.v1``: an intercompany pair amount of one period (S12-R-15; POL-171).

    ``output`` ``TXN``: Σ ``amounts``, the signed revenue amounts in transaction minor units, and
    no inputs. ``CONTRACTING``: Σ sign × input over the functional layer pieces of those revenue
    flows in the contracting entity (ALG-07 step 5), one ``signs`` entry per input.
    """
    formula_id = "ent.pair.v1"
    output = _param(params, "output")
    if output == "TXN":
        _require_arity(inputs, 0, formula_id)
        amounts = _rationals(params, "amounts")
        if not amounts or any(amount.denominator != 1 for amount in amounts):
            raise ValueError(f"{formula_id}: params amounts must list whole minor units")
        scale: int = 10 ** minor_unit_of(params)
        return sum(amounts, Fraction(0)) / scale
    if output == "CONTRACTING":
        signs = _list(params, "signs")
        if len(signs) != len(inputs):
            raise ValueError(f"{formula_id}: params signs must name one sign per input")
        total = Fraction(0)
        for sign, value in zip(signs, inputs, strict=True):
            if sign not in ("1", "-1"):
                raise ValueError(f"{formula_id}: a sign is 1 or -1")
            total += value if sign == "1" else -value
        return total
    raise ValueError(f"{formula_id}: params output must be TXN or CONTRACTING")


def _ent_performing_rate(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``ent.performing_revenue_rate.v1``: Σ round(amount × rate) at the performing minor unit.

    Params ``amounts`` (signed transaction minor units), ``txn_minor_unit``, and per amount
    ``rates`` and ``rate_inputs``: a ``true`` rate is the next ``fx_rate`` source input and equals
    its stated rate; a ``false`` rate is 1 (equal currencies). ``rate_types`` names the POL-162
    rate of each amount (S12-R-15; ALG-07 step 5).
    """
    formula_id = "ent.performing_revenue_rate.v1"
    minor_unit = minor_unit_of(params)
    txn_minor_unit = _minor(params, "txn_minor_unit")
    amounts = _rationals(params, "amounts")
    rates = _rationals(params, "rates")
    flags = _list(params, "rate_inputs")
    if not amounts or not len(amounts) == len(rates) == len(flags):
        raise ValueError(f"{formula_id}: amounts, rates and rate_inputs must align")
    remaining = list(inputs)
    total = 0
    for amount, stated, flag in zip(amounts, rates, flags, strict=True):
        if amount.denominator != 1:
            raise ValueError(f"{formula_id}: params amounts must list whole minor units")
        if flag == "true":
            if not remaining:
                raise ValueError(f"{formula_id}: a rate input is missing")
            rate = remaining.pop(0)
        elif flag == "false":
            rate = Fraction(1)
        else:
            raise ValueError(f"{formula_id}: params rate_inputs must list true or false")
        if rate != stated or rate <= 0:
            raise ValueError(f"{formula_id}: a rate input disagrees with params rates")
        total += round_half_up(amount / 10**txn_minor_unit * rate, minor_unit)
    if remaining:
        raise ValueError(f"{formula_id}: more rate inputs than rate_inputs name")
    return Fraction(total, 10**minor_unit)


# --- Stage 12 foreign currency (ENGINE_SPEC_B §12.5; BUILD_SPEC END-1) ---------------------------


def _fx_rate(
    inputs: Sequence[Fraction], params: Mapping[str, str], formula_id: str
) -> tuple[Fraction, Sequence[Fraction]]:
    """The conversion rate and the other inputs (ENGINE_SPEC_B §12.5; S12-R-01).

    With ``rate_input`` true the rate is the first input, an ``fx_rate`` source reference; with
    ``false`` the currencies are equal and the rate is 1. ``params["rate"]`` states the rate.
    """
    stated = _rational(params, "rate")
    flag = _param(params, "rate_input")
    if flag == "true":
        if not inputs:
            raise ValueError(f"{formula_id}: the rate input is missing")
        rate, rest = inputs[0], inputs[1:]
    elif flag == "false":
        rate, rest = Fraction(1), inputs
    else:
        raise ValueError(f"{formula_id}: params rate_input must be true or false")
    if rate != stated or rate <= 0:
        raise ValueError(f"{formula_id}: the rate input disagrees with params rate")
    return rate, rest


def _fx_converted(params: Mapping[str, str], rate: Fraction) -> int:
    # round(transaction exact × rate) at the functional minor unit (S12-R-02).
    amount = Fraction(_minor(params, "amount_txn"), 10 ** _minor(params, "txn_minor_unit"))
    return round_half_up(amount * rate, minor_unit_of(params))


def _fx_create(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.layer.create.v1``, ``fx.asset_layer.create.v1``: round(amount × rate) (S12-R-02).

        Inputs: the rate (``rate_input`` true). Params ``amount_txn``, ``txn_minor_unit``, ``rate``,
        ``rate_type``, ``effective_date`` and ``minor_unit``.
        """
        rate, rest = _fx_rate(inputs, params, formula_id)
        _require_arity(rest, 0, formula_id)
        return Fraction(_fx_converted(params, rate), 10 ** minor_unit_of(params))

    return formula


def _fx_consume(formula_id: str, *, pro_rata: bool) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.layer.consume.fifo.v1``, ``fx.layer.consume.pro_rata.v1``: layer relief (S12-R-05).

        Input: the layer's historical functional amount (its creation node). Params ``take``,
        ``consumed_before``, ``txn_original`` and ``basis`` ``HISTORICAL``. The relief is
        ``cumulative_posted`` over the historical amount at (before + take) ÷ original less the same
        at before ÷ original. Pro rata (S12-R-07): ``take`` is share ``index`` of the largest
        remainder apportionment of ``debit`` over ``weights``, the open balances in layer-key order.
        """
        minor_unit = minor_unit_of(params)
        take = _minor(params, "take")
        if pro_rata:
            weights = _rationals(params, "weights")
            index = _minor(params, "index")
            keys = [f"{position:06d}" for position in range(len(weights))]
            shares = largest_remainder(_minor(params, "debit"), weights, keys)
            if not 0 <= index < len(shares) or shares[index] != take:
                raise ValueError(f"{formula_id}: the share disagrees with the apportionment")
        basis = _param(params, "basis")
        if basis == "RATE":
            # POL-163 override (S12-R-10): round(take × the debit's rate), rate as an input.
            rate, rest = _fx_rate(inputs, params, formula_id)
            _require_arity(rest, 0, formula_id)
            if _minor(params, "amount_txn") != take:
                raise ValueError(f"{formula_id}: params amount_txn disagrees with take")
            return Fraction(_fx_converted(params, rate), 10**minor_unit)
        if basis != "HISTORICAL":
            raise ValueError(f"{formula_id}: unknown relief basis")
        _require_arity(inputs, 1, formula_id)
        original = _minor_value(inputs[0], minor_unit, formula_id)
        txn_original = _minor(params, "txn_original")
        before = _minor(params, "consumed_before")
        if txn_original <= 0 or before < 0 or take <= 0 or before + take > txn_original:
            raise ValueError(f"{formula_id}: the relief lies outside the layer")
        exact = Fraction(original, 10**minor_unit)
        after_cum = cumulative_posted(
            exact, original, Fraction(before + take, txn_original), minor_unit
        )
        before_cum = cumulative_posted(exact, original, Fraction(before, txn_original), minor_unit)
        return Fraction(after_cum - before_cum, 10**minor_unit)

    return formula


def _fx_difference(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.credit_memo_difference.v1``, ``fx.monetary_liability.recognition_difference.v1``.

        round(amount × spot) − the functional debits of the contract liability (S12-R-08,
        S12-R-19). Inputs: the spot rate, then the ``reliefs`` debit nodes. Params as
        ``fx.layer.create.v1``.
        """
        rate, reliefs = _fx_rate(inputs, params, formula_id)
        _require_arity(reliefs, _minor(params, "reliefs"), formula_id)
        at_spot = Fraction(_fx_converted(params, rate), 10 ** minor_unit_of(params))
        return at_spot - sum(reliefs, Fraction(0))

    return formula


def _fx_settle(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.settlement.spot.v1``, ``fx.monetary_liability.settle.v1``: a portion leaving.

        Params ``amount_txn`` (the portion), ``open_before``, ``carrying_before`` and ``output``.
        ``SHARE``: the carrying share ``cumulative_posted``(carrying, carrying, portion ÷ open), no
        inputs. ``AMOUNT``: round(portion × rate). ``DIFFERENCE``: AMOUNT − SHARE. AMOUNT and
        DIFFERENCE take the rate as ``fx.layer.create.v1`` does (S12-R-09, S12-R-20).
        """
        minor_unit = minor_unit_of(params)
        take = _minor(params, "amount_txn")
        open_before = _minor(params, "open_before")
        carrying = _minor(params, "carrying_before")
        if take <= 0 or open_before < take:
            raise ValueError(f"{formula_id}: the portion lies outside the layer")
        share = cumulative_posted(
            Fraction(carrying, 10**minor_unit), carrying, Fraction(take, open_before), minor_unit
        )
        output = _param(params, "output")
        if output == "SHARE":
            _require_arity(inputs, 0, formula_id)
            return Fraction(share, 10**minor_unit)
        rate, rest = _fx_rate(inputs, params, formula_id)
        _require_arity(rest, 0, formula_id)
        amount = _fx_converted(params, rate)
        if output == "AMOUNT":
            return Fraction(amount, 10**minor_unit)
        if output == "DIFFERENCE":
            return Fraction(amount - share, 10**minor_unit)
        raise ValueError(f"{formula_id}: params output must be SHARE, AMOUNT or DIFFERENCE")

    return formula


def _fx_remeasure(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.remeasure.closing.v1``, ``fx.monetary_liability.remeasure.closing.v1``.

        round(open amount × closing rate) − ``carrying_before`` (S12-R-09 to S12-R-11). Inputs and
        params as ``fx.layer.create.v1`` with ``amount_txn`` = the open transaction amount.
        """
        rate, rest = _fx_rate(inputs, params, formula_id)
        _require_arity(rest, 0, formula_id)
        remeasured = _fx_converted(params, rate) - _minor(params, "carrying_before")
        return Fraction(remeasured, 10 ** minor_unit_of(params))

    return formula


def _fx_functional_member(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``fx.functional_member.v1`` (T-CON-09 ``_functional`` columns of a foreign-currency entity
    per member and period; D-97 (8) T1F-Q-4): the functional amount stage 12 measured for the
    member, params ``value`` (functional minor units); the inputs are lineage only (the reclass,
    promised and release targets behind the presented and incentive amounts)."""
    return Fraction(_minor(params, "value"), 10 ** minor_unit_of(params))


def _fx_signed_sum(formula_id: str) -> Formula:
    def formula(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
        """``fx.revenue_functional.v1``, ``fx.gain_loss.sum.v1``: Σ sign × input (§12.5).

        Params ``signs``: ``1`` or ``-1`` per input, joined by ``|``. The first input of a
        cumulative node is the node of the previous period.
        """
        signs = _list(params, "signs")
        if len(signs) != len(inputs):
            raise ValueError(f"{formula_id}: params signs must name one sign per input")
        total = Fraction(0)
        for sign, value in zip(signs, inputs, strict=True):
            if sign == "1":
                total += value
            elif sign == "-1":
                total -= value
            else:
                raise ValueError(f"{formula_id}: a sign is 1 or -1")
        return total

    return formula


# --- Stage 14 posting (ENGINE_SPEC_B §14.6; BUILD_SPEC END-5, END-6) -----------------------------


def _post_role_target(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``post.role_target.v1``: the cumulative signed target of a role key (S14-R-01, S14-R-04).

    Params ``signs``: ``1``, ``-1`` or ``0`` per input, joined by ``|``; ``0`` cites a node without
    adding it (for example the stage 12 functional amount behind a transaction amount). A share of
    a split side names ``weights`` and ``keys`` (joined by ``|``), ``index`` and ``side`` (``1`` or
    ``-1``): the signed sum is apportioned in minor units with ``largest_remainder``, and the share
    at ``index`` takes the side's sign (S14-R-10; CV-36).
    """
    formula_id = "post.role_target.v1"
    signs = _list(params, "signs")
    if len(signs) != len(inputs):
        raise ValueError(f"{formula_id}: params signs must name one sign per input")
    total = Fraction(0)
    for sign, value in zip(signs, inputs, strict=True):
        if sign not in ("1", "-1", "0"):
            raise ValueError(f"{formula_id}: a sign is 1, -1 or 0")
        total += int(sign) * value
    if "weights" not in params:
        return total
    minor_unit = minor_unit_of(params)
    scaled = total * 10**minor_unit
    if scaled.denominator != 1:
        raise ValueError(f"{formula_id}: a split total must be whole minor units")
    keys = _list(params, "keys")
    shares = largest_remainder(scaled.numerator, _rationals(params, "weights"), keys)
    index = int(_param(params, "index"))
    side = _param(params, "side")
    if side not in ("1", "-1") or not 0 <= index < len(keys):
        raise ValueError(f"{formula_id}: params side is 1 or -1 and index names a key")
    return Fraction(int(side) * shares[index], 10**minor_unit)


def _post_delta(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``post.delta.v1``: the period target of the posting classes less posted by origin (S14-R-04).

    Inputs: the ``posting_target`` node of the period, the node of the previous period when params
    ``previous`` is ``true``, then the posted total (a source reference). Params ``class``: ``ALL``
    (a closed-period carry), ``EVENT`` or ``TIME``; ``time`` and ``time_previous``: the ``TIME``
    parts of the two targets in minor units (RCP-07).
    """
    formula_id = "post.delta.v1"
    previous = _param(params, "previous")
    if previous not in ("true", "false"):
        raise ValueError(f"{formula_id}: params previous is true or false")
    _require_arity(inputs, 3 if previous == "true" else 2, formula_id)
    current, posted = inputs[0], inputs[-1]
    before = inputs[1] if previous == "true" else Fraction(0)
    scale: int = 10 ** minor_unit_of(params)
    time_now = Fraction(_minor(params, "time"), scale)
    time_before = Fraction(_minor(params, "time_previous"), scale)
    posting_class = _param(params, "class")
    if posting_class == "ALL":
        movement = current - before
    elif posting_class == "TIME":
        movement = time_now - time_before
    elif posting_class == "EVENT":
        movement = (current - time_now) - (before - time_before)
    else:
        raise ValueError(f"{formula_id}: params class is ALL, EVENT or TIME")
    return movement - posted


def _post_account_resolution(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``post.account_resolution.v1``: the T-REF-15 step that resolved a line's account (S14-R-14).

    Input: the source reference of the obligation override or the mapping rule, carrying the step.
    Params ``step``: ``1`` (obligation or template override) or ``3`` (mapping rule);
    ``account_code`` and ``mapping_version_key``.
    """
    formula_id = "post.account_resolution.v1"
    _require_arity(inputs, 1, formula_id)
    step = _param(params, "step")
    if step not in ("1", "3") or inputs[0] != int(step):
        raise ValueError(f"{formula_id}: params step is 1 or 3 and equals its source")
    return Fraction(int(step))


# --- Stage 15 remaining performance obligations (ENGINE_SPEC_B §15.2.3, §15.5; EDS-1) ------------


def rpo_bands(total_minor: int, placed: Sequence[int]) -> list[int]:
    """S15-R-10 band amounts of an obligation's RPO after exemptions, minor units.

    The placed amounts when they sum to ``total_minor``; otherwise ``total_minor`` apportioned over
    the positive placed amounts with ``largest_remainder`` (keys are the band indices); with no
    positive placed amount, everything in band 0.
    """
    if not placed:
        raise ValueError("an RPO has at least one time band (POL-201)")
    if sum(placed) == total_minor:
        return list(placed)
    weights = [Fraction(max(amount, 0)) for amount in placed]
    if sum(weights) == 0:
        return [total_minor, *([0] * (len(placed) - 1))]
    return largest_remainder(total_minor, weights, [str(index) for index in range(len(placed))])


def _disc_rpo(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``disc.rpo.v1``: the remaining performance obligation (S15-R-08).

    ``kind`` ``obligation``: inputs (``scheduled_amount``, ``awaiting_trigger_amount``) of stage 09
    at d_v; their sum when params ``included`` is ``true`` (E-22 ``UNSATISFIED`` or
    ``PARTIALLY_SATISFIED``), else 0; a third input, the ``deposit_revenue_share`` node at d_v, is
    deducted and the result floored at 0 (the 606-10-25-7 revenue attributed to the obligation,
    ENGINE_SPEC_B S14-R-25; D-91 gaps (v), (vii)). ``included`` is also false for an obligation
    of a contract that is ``NOT_A_CONTRACT`` in the book at d_v (params ``excluded``). ``kind``
    ``group``: the signed sum of the inputs with params ``signs`` (``+`` or ``-`` per input,
    ``|``-separated). Stage 15 feeds the obligation RPO nodes with ``+`` only, so the value is
    T-CON-08 ``rpo_amount`` gross of the S15-R-09 exemptions (S15-R-08 rev 1.26; D-98 candidates
    91 / 91a); when an expedient applies, the additive params ``excluded`` (Σ exempt, minor units)
    and ``exempt_nodes`` (the ``rpo_excluded`` node ids, ``|``-separated) state the net as value −
    ``excluded`` (gross = net + exempt). The exempt amounts are never netting inputs.
    """
    formula_id = "disc.rpo.v1"
    kind = _param(params, "kind")
    if kind == "obligation":
        if len(inputs) not in (2, 3):
            raise ValueError(f"{formula_id} takes 2 or 3 inputs, not {len(inputs)}")
        included = _param(params, "included")
        if included not in ("true", "false"):
            raise ValueError(f"{formula_id}: params included is true or false")
        if included != "true":
            return Fraction(0)
        remaining = inputs[0] + inputs[1]
        if len(inputs) == 3:  # less the 25-7 revenue attributed to the obligation (D-91; S14-R-25)
            remaining = max(remaining - inputs[2], Fraction(0))
        return remaining
    if kind == "group":
        signs = _list(params, "signs")
        if len(signs) != len(inputs) or any(sign not in ("+", "-") for sign in signs):
            raise ValueError(f"{formula_id}: params signs holds + or - per input")
        return sum(
            (value if sign == "+" else -value for sign, value in zip(signs, inputs, strict=True)),
            Fraction(0),
        )
    raise ValueError(f"{formula_id} does not know the kind {kind}")


def _disc_prior_period_sum(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``disc.prior_period_sum.v1`` (ENGINE_SPEC_B §15.2.4 S15-R-13, S15-R-14; EDS-4): Σ of the
    ``revenue_prior_period`` obligation nodes of one contract and contracting entity for a period;
    params ``count`` (the arity) and ``period``."""
    formula_id = "disc.prior_period_sum.v1"
    _require_arity(inputs, _minor(params, "count"), formula_id)
    return sum(inputs, Fraction(0))


def _disc_rpo_exemption(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``disc.rpo_exemption.v1``: the amount one practical expedient omits from an obligation's
    RPO (S15-R-09). Inputs: the obligation's ``rpo_amount``, then the amounts of the expedients
    applied before this one. ``basis`` ``ALL`` omits what remains; ``AMOUNT`` omits at most params
    ``amount`` (minor units, with ``minor_unit``) of a positive remainder. Params ``policy`` names
    the POL id.
    """
    formula_id = "disc.rpo_exemption.v1"
    if not inputs:
        raise ValueError(f"{formula_id} takes the obligation's rpo_amount first")
    _param(params, "policy")
    remaining = inputs[0] - sum(inputs[1:], Fraction(0))
    basis = _param(params, "basis")
    if basis == "ALL":
        return remaining
    if basis == "AMOUNT":
        cap = Fraction(_minor(params, "amount"), 10 ** minor_unit_of(params))
        return min(remaining, cap) if remaining > 0 else Fraction(0)
    raise ValueError(f"{formula_id} does not know the basis {basis}")


def _disc_rpo_band(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    """``disc.rpo_band.v1``: an obligation's RPO after exemptions in time band ``index`` (S15-R-10).

    Inputs: the obligation's ``rpo_amount``, then its exempt amounts. Params ``placed`` lists the
    amounts placed per band before exemptions (minor units, ``|``-separated), ``index``,
    ``minor_unit`` and, for explain, ``bounds``. The band amounts are ``rpo_bands`` of the
    non-exempt total over the placed amounts.
    """
    formula_id = "disc.rpo_band.v1"
    if not inputs:
        raise ValueError(f"{formula_id} takes the obligation's rpo_amount first")
    scale: int = 10 ** minor_unit_of(params)
    total = (inputs[0] - sum(inputs[1:], Fraction(0))) * scale
    if total.denominator != 1:
        raise ValueError(f"{formula_id}: the RPO is not a whole number of minor units")
    placed = []
    for item in _list(params, "placed"):
        if not _RATIONAL.fullmatch(item) or "/" in item:
            raise ValueError(f"{formula_id}: params placed lists whole minor units")
        placed.append(int(item))
    index = _param(params, "index")
    if not index.isdigit() or int(index) >= len(placed):
        raise ValueError(f"{formula_id}: params index names a placed band")
    return Fraction(rpo_bands(total.numerator, placed)[int(index)], scale)


FORMULAS: Final[Mapping[str, Formula]] = MappingProxyType(
    {
        **_INCEPTION_FORMULAS,
        "bal.member_sum.v1": _signed_formula("bal.member_sum.v1"),
        "bil.ar_balance.v1": _ar_balance,
        "bil.attribution.v1": _attribution,
        "bil.billed_amount.v1": _signed_formula("bil.billed_amount.v1"),
        "bil.remaining_billing.v1": _remaining_billing,
        "bil.unconditional_date.v1": _unconditional_billing,
        "books.contract_sum.v1": _contract_sum,
        "books.unit_revenue_rate.v1": _unit_revenue_rate,
        "alloc.original_total.v1": _original_total,
        "alloc.original_total_amount.v1": _original_total_amount,
        "alloc.original_weight.v1": _original_weight,
        "books.legacy_fold.v1": _legacy_fold,
        "books.version_adjustment.v1": _version_adjustment,
        "cost.accelerate.v1": _cost_accelerate,
        "cost.member_sum.v1": _signed_formula("cost.member_sum.v1"),
        "cost.amortise.proportional.v1": _amortise_proportional,
        "cost.amortise.straight_line.v1": _amortise_straight_line,
        "cost.capitalise.v1": _cost_capitalise,
        "cost.carrying.v1": _cost_carrying,
        "cost.clawback.v1": _cost_clawback,
        "cost.expense_reason.v1": _cost_expense_reason,
        "cost.impair.ifrs_reversal.v1": _cost_reversal,
        "cost.impair.us.v1": _cost_impair,
        "cost.recoverable.v1": _cost_recoverable,
        "disc.prior_period_sum.v1": _disc_prior_period_sum,
        "disc.rpo.v1": _disc_rpo,
        "disc.rpo_band.v1": _disc_rpo_band,
        "disc.rpo_exemption.v1": _disc_rpo_exemption,
        "ent.pair.v1": _ent_pair,
        "ent.performing_revenue_rate.v1": _ent_performing_rate,
        "estimate.catch_up.v1": _estimate_catch_up,
        "estimate.pin.v1": _estimate_pin,
        "estimate.prior_period.v1": _prior_period,
        "estimate.route.32_45.v1": _route_32_45,
        "estimate.route.inception.v1": _route_inception,
        "estimate.route.inception.v2": _route_inception_v2,
        "estimate.tp_delta.v1": _tp_delta,
        "fx.asset_layer.create.v1": _fx_create("fx.asset_layer.create.v1"),
        "fx.credit_memo_difference.v1": _fx_difference("fx.credit_memo_difference.v1"),
        "fx.gain_loss.sum.v1": _fx_signed_sum("fx.gain_loss.sum.v1"),
        "fx.layer.consume.fifo.v1": _fx_consume("fx.layer.consume.fifo.v1", pro_rata=False),
        "fx.layer.consume.pro_rata.v1": _fx_consume("fx.layer.consume.pro_rata.v1", pro_rata=True),
        "fx.layer.create.v1": _fx_create("fx.layer.create.v1"),
        "fx.monetary_liability.create.v1": _fx_create("fx.monetary_liability.create.v1"),
        "fx.monetary_liability.recognition_difference.v1": _fx_difference(
            "fx.monetary_liability.recognition_difference.v1"
        ),
        "fx.monetary_liability.remeasure.closing.v1": _fx_remeasure(
            "fx.monetary_liability.remeasure.closing.v1"
        ),
        "fx.monetary_liability.settle.v1": _fx_settle("fx.monetary_liability.settle.v1"),
        "fx.remeasure.closing.v1": _fx_remeasure("fx.remeasure.closing.v1"),
        "fx.revenue_functional.v1": _fx_signed_sum("fx.revenue_functional.v1"),
        "fx.functional_member.v1": _fx_functional_member,
        "fx.settlement.spot.v1": _fx_settle("fx.settlement.spot.v1"),
        "late.assign.v1": _late_assign,
        "loss.expected_margin.v1": _loss_expected_margin,
        "loss.movement.v1": _loss_movement,
        "loss.required_provision.v1": _loss_required_provision,
        "loss.tp_unconstrained.v1": _loss_tp_unconstrained,
        "mod.allocation_adjustment.v1": _mod_allocation_adjustment,
        "mod.catch_up.v1": _mod_catch_up,
        "mod.classify.v1": _mod_classify,
        "mod.exercise.continuation.v1": _mod_exercise_continuation,
        "mod.exercise.modification.v1": _mod_exercise_modification,
        "mod.legacy.mod_ssp.v1": _mod_legacy_mod_ssp,
        "mod.legacy.pob_vc.v1": _mod_legacy_pob_vc,
        "mod.legacy.prospective.v1": _mod_legacy_prospective,
        "mod.legacy.retrospective.v1": _mod_legacy_retrospective,
        "mod.pool.by_line.v1": _mod_pool_by_line,
        "mod.pool.remaining_tp.v1": _mod_pool_remaining_tp,
        "mod.pool.total_tp.v1": _mod_pool_total_tp,
        "mod.price_test.v1": _mod_price_test,
        "mod.satisfied_performance.v1": _mod_satisfied_performance,
        "mod.stated_price.v1": _mod_stated_price,
        "mod.termination.v1": _mod_termination,
        "mod.weights.d18.v1": _mod_weights_d18,
        "mod.weights.inception_all.v1": _mod_weights_inception_all,
        "onb.baseline.v1": _opening_baseline,
        "onb.difference.v1": _onboarding_difference,
        "onb.ifrs_fair_value_split.v1": _fair_value_split,
        "onb.opening_segment.v1": _opening_segment,
        "pos.accretion_attribution.v1": _accretion_attribution,
        "pos.current_split.v1": _current_split,
        "pos.net_position.v1": _net_position,
        "pos.obligation.v1": _position_obligation,
        "pos.receivable_contra.v1": _receivable_contra,
        "pos.reclass_attribution.cumulative_ssp_delivered.v1": _reclass_cumulative_ssp_delivered,
        "pos.reclass_attribution.no_measured_period.v1": _reclass_no_measured_period,
        "pos.reclass_attribution.pob_debit_positions.v1": _reclass_pob_debit_positions,
        "pos.split_ca_ur.v1": _split_ca_ur,
        "post.account_resolution.v1": _post_account_resolution,
        "post.delta.v1": _post_delta,
        "post.role_target.v1": _post_role_target,
        "rec.activity_sum.v1": _signed_formula("rec.activity_sum.v1"),
        "rec.allocation.v1": _allocation_state,
        "rec.allocation_adjustment.v1": _allocation_adjustment,
        "rec.awaiting.v1": _awaiting,
        "rec.catch_up.sum.v1": _catch_up_sum,
        "rec.decompose.sequential.v1": _decompose_sequential,
        # Component views reuse the same arithmetic primitives with separate explain narratives.
        "rec.period_vc_revenue.v1": _decompose_sequential,
        "rec.realised_allocation.v1": _allocation_state,
        "rec.schedule.fixed.v1": _decompose_sequential,
        "rec.progress.cost_recovery.v1": _cost_recovery,
        "rec.progress.cost_to_cost.v1": _cost_to_cost,
        "rec.progress.labour_hours.v1": _labour_hours,
        "rec.progress.milestone.v1": _milestone,
        "rec.progress.output_percent.v1": _output_percent,
        "rec.progress.point_in_time.v1": _point_in_time,
        "rec.progress.prospective_segment.v1": _prospective_segment,
        "rec.progress.right_to_invoice.v1": _right_to_invoice,
        "rec.progress.time_elapsed.daily.v1": _time_formula("DAILY"),
        "rec.progress.time_elapsed.mid_month.v1": _time_formula("MID_MONTH"),
        "rec.progress.time_elapsed.monthly_even.v1": _time_formula("MONTHLY_EVEN"),
        "rec.progress.units.v1": _units,
        "rec.progress.unmeasured.v1": _progress_unmeasured,
        "rec.exact_activity.v1": _exact_activity,
        "rec.exact_difference.v1": _exact_difference,
        "rec.exact_endpoint.v1": _exact_endpoint,
        "rec.remaining.v1": _remaining,
        "rec.revenue_cum.v1": _revenue_cum,
        "rec.scheduled.v1": _scheduled,
        "rec.segment_state.v1": _segment_state,
        "rec.step1_net.v1": _step1_net,
        "rec.target_exact.inception.v1": _target_exact_inception,
        "rec.target_exact.prospective.v1": _target_exact_prospective,
        "rec.uninstalled_materials.v1": _uninstalled_materials,
        "returns.excess_reversal.v1": _excess_reversal,
        "returns.expected_units.v1": _expected_units,
        "returns.return_asset.v1": _return_asset,
        "returns.revenue_target.v1": _revenue_target,
        "rl.concession.v1": _refund_event_component("rl.concession.v1"),
        "rl.consumption.v1": _refund_consumption,
        "rl.return.v1": _refund_return,
        "rl.termination.v1": _refund_event_component("rl.termination.v1"),
        "rl.unclaimed_property.v1": _refund_event_component("rl.unclaimed_property.v1"),
        "rl.vc_target.v1": _refund_vc_target,
        "sched.cumulative_posted.v1": _cumulative_posted,
        "sched.hold_freeze.v1": _hold_freeze,
        "sched.manual_defer.v1": _manual_defer,
        "sched.manual_release.v1": _manual_release,
        "sched.override_respread.v1": _override_respread,
        "sched.period_difference.v1": _period_difference,
        # D-91 (ENG-B1): S09-R-23a units billed, E_b and the RETURN component citing it.
        "returns.units_billed.v1": _units_billed,
        "returns.refundable_units.v1": _refundable_units,
        "rl.return.v2": _refund_return_v2,
        # ENC-8: redemption pattern, breakage and royalties (ENGINE_SPEC_B §9.2.8, §9.2.9, §9.5).
        "breakage.proportional.v1": _breakage_formula(
            "breakage.proportional.v1", "PROPORTIONAL_TO_EXERCISE"
        ),
        "breakage.remote.v1": _breakage_formula("breakage.remote.v1", "WHEN_REMOTE"),
        "breakage.expiry.v1": _breakage_formula("breakage.expiry.v1", "EXPIRY"),
        "royalty.accrual.v1": _royalty_realised("royalty.accrual.v1"),
        "royalty.minimum_guarantee.v1": _royalty_realised("royalty.minimum_guarantee.v1"),
        "royalty.report_true_up.v1": _royalty_true_up,
    }
)
