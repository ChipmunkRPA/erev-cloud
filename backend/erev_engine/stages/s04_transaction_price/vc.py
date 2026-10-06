"""Stage 04 variable consideration elements: selection, estimation methods and constraint.

ENGINE_SPEC §4.3 S04-R-04, S04-R-05, S04-R-07; §4.4 S04-INV-02; formulas
``tp.vc_expected_value.v1``, ``tp.vc_most_likely.v1``, ``tp.vc_entered.v1``,
``tp.vc_constrained.v1``; POLICIES POL-040, POL-041, POL-240, POL-244; 04 B3-D16 and dev-guide
§9.5.4 B3-DG-17 (direction: the element's T-CON-12 ``direction`` carried on
``EstimateVersionInput``, the B3-DG-17 default when the producer carried none; ENC-VC-direction).
Private to stage 04. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.bundle import DECREASE, INCREASE, VC_DECREASE_TYPES, EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    encode_key,
    judgement_names_element,
    judgement_names_subject,
)
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.state import BookContext, EventView
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["DECREASE", "INCREASE", "Element", "elements", "emit"]

KIND: Final = "VARIABLE_CONSIDERATION"
# B3-DG-17 (topics convention T-03): element types that reduce the price when no direction is given;
# the list is the bundle's (``EstimateVersionInput.resolved_direction``), named here for readers.
DECREASE_TYPES: Final = VC_DECREASE_TYPES
METHOD_FORMULAS: Final = MappingProxyType(
    {
        "EXPECTED_VALUE": "tp.vc_expected_value.v1",
        "MOST_LIKELY_AMOUNT": "tp.vc_most_likely.v1",
        "ENTERED_AMOUNT": "tp.vc_entered.v1",
    }
)
CONSTRAINED_FORMULA: Final = "tp.vc_constrained.v1"
NOT_APPLIED: Final = "NOT_APPLIED"
PREPARER_CONSTRAINED_AMOUNT: Final = "PREPARER_CONSTRAINED_AMOUNT"
ESTIMATE_MEASUREMENT_PERIOD_TP: Final = "ESTIMATE_MEASUREMENT_PERIOD_TP"
DERIVED: Final = "DERIVED"  # POL-240 default
_PORTFOLIO_PREFIX: Final = "PORTFOLIO:"


@dataclass(frozen=True, slots=True)
class Element:
    """One pinned VC element measured at ``at`` (S04-R-05, S04-R-07); amounts are signed."""

    version: EstimateVersionInput
    contract_key: str  # the member contract whose policies govern the element
    direction: str  # INCREASE | DECREASE (B3-DG-17)
    unconstrained: Fraction  # U with the direction's sign
    constrained: Fraction  # K with the direction's sign
    constraint: str  # resolved POL-041 literal
    scenarios: tuple[tuple[Fraction, Fraction], ...]  # (amount, probability) that give U


def _contract_of(st: PobState, estimate_key: str) -> str:
    """The member contract of an element key (CV-21): the contract, or for a portfolio element
    the first member of the group in the portfolio."""
    cb = st.identified.canonical
    head = estimate_key.split("/", 1)[0]
    if head.startswith(_PORTFOLIO_PREFIX):
        code = head[len(_PORTFOLIO_PREFIX) :]
        for portfolio, members in sorted(cb.group.portfolios.items()):
            if encode_key(portfolio) == code:
                found = [key for key in st.identified.member_contract_keys if key in members]
                if found:
                    return found[0]
        raise ValueError(f"{estimate_key}: no member contract belongs to the portfolio (CV-10)")
    for key in st.identified.member_contract_keys:
        if contract_subject_key(key) == head:
            return key
    raise ValueError(f"{estimate_key}: the element belongs to no member contract (CV-10)")


def direction(version: EstimateVersionInput) -> str:
    """The element's T-CON-12 ``direction`` (B3-D16) as the bundle carries it; when the producer
    carried none, ``DECREASE`` for kind ``IMPLICIT_PRICE_CONCESSION`` and the B3-DG-17 types, else
    ``INCREASE`` (``EstimateVersionInput.resolved_direction``; ENC-VC-direction)."""
    return version.resolved_direction()


def _claim_enforceable(
    ctx: BookContext, st: PobState, contract_key: str, version: EstimateVersionInput
) -> bool:
    """A reviewed ``OTHER`` outcome ``claim_enforceable = true`` naming the element (POL-244).

    D-93 (3) (Table 0.4-A; 04 T-CON-19): the outcome ``estimate_key`` is the element code of the
    record's contract, or the §0.4 qualified key; the record may sit on the contract or on the
    element's obligation (``obligation_key`` or a target obligation).
    """
    header = st.identified.canonical.contracts[contract_key].header
    obligations = [key for key in (version.obligation_key, *version.target_obligation_keys) if key]
    return any(
        record.topic == "OTHER"
        and judgement_names_subject(record.subject_key, header.external_id, obligations)
        and record.book_code in (None, ctx.book_code)
        and judgement_names_element(
            record.outcome.get("estimate_key"), version.estimate_key, version.element_code
        )
        and record.outcome.get("claim_enforceable") == "true"
        for record in header.judgements
    )


def elements(
    ctx: BookContext, st: PobState, at: date, before: EventView | None
) -> tuple[Element, ...]:
    """S04-R-04: every ``VARIABLE_CONSIDERATION`` element with a pin at ``at`` before ``before``.

    Type ``ROYALTY`` is realised through S04-R-06 (606-10-55-65), type ``USAGE`` too unless POL-240
    is ``ESTIMATE_MEASUREMENT_PERIOD_TP``, and type ``CLAIM`` enters only with the reviewed
    outcome of POL-244. Elements are returned by estimate key.
    """
    pins = st.identified.canonical.estimates
    found: list[Element] = []
    for key in sorted(pins.pins):
        version = pins.pin(key, at, before)
        if version is None or version.estimate_kind != KIND:
            continue
        contract_key = _contract_of(st, key)
        kind = version.vc_element_type
        if kind == "ROYALTY":
            continue
        if kind == "USAGE":
            method = ctx.policies.value("usage.tier_minimum_method", contract=contract_key)
            # POL-240 DERIVED gives ESTIMATE_MEASUREMENT_PERIOD_TP (PT-01): the preparer pins a
            # usage estimate only when 32-40(b) fails; realised usage has no pin (L4-3-Q-34).
            if method not in (ESTIMATE_MEASUREMENT_PERIOD_TP, DERIVED):
                continue
        if kind == "CLAIM" and not _claim_enforceable(ctx, st, contract_key, version):
            continue
        found.append(_measure(ctx, st, version, contract_key, at))
    return tuple(found)


def _invariant(invariant: str, message: str, version: EstimateVersionInput) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=version.estimate_key,
        detail={"invariant": invariant, "estimate_version_key": version.version_key},
    )


def _scenarios(version: EstimateVersionInput) -> tuple[tuple[Fraction, Fraction], ...]:
    rows: list[tuple[Fraction, Fraction]] = []
    for scenario in version.scenarios:
        amount, probability = scenario.get("amount"), scenario.get("probability")
        if amount is None or probability is None:
            raise ValueError(f"{version.version_key}: a scenario needs amount and probability")
        rows.append((to_fraction(amount), to_fraction(probability)))
    return tuple(rows)


def _unconstrained(
    version: EstimateVersionInput, sign: int
) -> tuple[Fraction, tuple[tuple[Fraction, Fraction], ...]]:
    """U by POL-040 method (S04-R-05), as a magnitude, with the scenarios that give it."""
    scenarios = _scenarios(version)
    stored = (
        None if version.unconstrained_amount is None else to_fraction(version.unconstrained_amount)
    )
    match version.method:
        case "EXPECTED_VALUE":
            if not scenarios and stored is not None:
                # The probabilities are checked at submission (S04-R-05); a version that stores U
                # without its scenarios carries U itself, as MOST_LIKELY_AMOUNT does (L4-3-Q-27).
                return stored, ()
            if not scenarios or sum((p for _, p in scenarios), Fraction(0)) != 1:
                raise ValueError(f"{version.version_key}: probabilities must sum to 1 (S04-R-05)")
            result = sum((a * p for a, p in scenarios), Fraction(0))
            used = scenarios
        case "MOST_LIKELY_AMOUNT":
            if not scenarios:
                if stored is None:
                    raise ValueError(f"{version.version_key}: MOST_LIKELY_AMOUNT needs scenarios")
                return stored, ()
            greatest = max(p for _, p in scenarios)
            # Ties: the amount giving the lower transaction price [J].
            chosen = min((a for a, p in scenarios if p == greatest), key=lambda a: sign * a)
            result, used = chosen, ((chosen, greatest),)
        case "ENTERED_AMOUNT":
            if version.constrained_amount is None:
                raise ValueError(f"{version.version_key}: ENTERED_AMOUNT needs constrained_amount")
            return to_fraction(version.constrained_amount), ()
        case _:
            raise ValueError(f"{version.version_key}: {version.method} is not a VC method (E-10)")
    if stored is not None and stored != result:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the stored unconstrained amount differs from the method result",
            subject_key=version.estimate_key,
            detail={
                "computed": format_exact(result),
                "estimate_version_key": version.version_key,
                "rule": "S04-R-05",
                "stored": format_exact(stored),
            },
        )
    return result, used


def _measure(
    ctx: BookContext,
    st: PobState,
    version: EstimateVersionInput,
    contract_key: str,
    at: date,
) -> Element:
    towards = direction(version)
    sign = -1 if towards == DECREASE else 1
    unconstrained, used = _unconstrained(version, sign)
    header = st.identified.canonical.contracts[contract_key].header
    entity = header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], at).period_key
    constraint = ctx.policies.value("vc.constraint", entity=entity, period=period)
    if constraint not in (NOT_APPLIED, PREPARER_CONSTRAINED_AMOUNT) or not isinstance(
        constraint, str
    ):
        raise ValueError(f"vc.constraint holds an unknown literal {constraint!r} (CV-17)")
    if constraint == NOT_APPLIED or version.constrained_amount is None:
        constrained = unconstrained
    else:
        constrained = to_fraction(version.constrained_amount)
    conservative = version.most_conservative_amount
    if conservative is not None and version.constrained_amount is not None:
        bounds = sorted((to_fraction(conservative), unconstrained))
        if not bounds[0] <= to_fraction(version.constrained_amount) <= bounds[1]:
            raise _invariant(
                "S04-INV-02", "the constrained amount lies outside its bounds (V6)", version
            )
    return Element(
        version=version,
        contract_key=contract_key,
        direction=towards,
        unconstrained=sign * unconstrained,
        constrained=sign * constrained,
        constraint=constraint,
        scenarios=used,
    )


def emit(ctx: BookContext, tb: TraceBuilder, element: Element, suffix: str) -> tuple[str, str]:
    """Nodes ``vc_unconstrained`` and ``vc_constrained`` of one element (§4.4); their ids."""
    version = element.version
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    formula = METHOD_FORMULAS[version.method]
    sign = "-1" if element.direction == DECREASE else "1"
    inputs: Sequence[SourceRef]
    params = {
        "direction": element.direction,
        "method": version.method,
        "sign": sign,
        "version_key": version.version_key,
    }
    if element.scenarios:
        inputs = [
            SourceRef("estimate_version", version.version_key, {"value": format_exact(amount)})
            for amount, _ in element.scenarios
        ]
        params["probabilities"] = ",".join(format_exact(p) for _, p in element.scenarios)
    else:  # the version's amount as stored: the signed value times the direction's sign
        stored = element.unconstrained if element.direction == INCREASE else -element.unconstrained
        detail = {"value": format_exact(stored)}
        inputs = [SourceRef("estimate_version", version.version_key, detail)]
        if version.method == "EXPECTED_VALUE":  # U as stored is the one certain outcome
            params["probabilities"] = "1"
    unconstrained_id = tb.node(
        measure=f"vc_unconstrained{suffix}",
        subject_key=version.estimate_key,
        period_key=None,
        value=round_half_up(element.unconstrained, minor_unit),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=formula,
        inputs=inputs,
        params=params,
        exact=element.unconstrained,
        narrative_key=formula.rsplit(".v", 1)[0],
    )
    constrained_inputs: list[str | SourceRef] = [unconstrained_id]
    source = "unconstrained"  # tp.vc_constrained.v1 reads the node, or the amount as stored
    if element.constraint != NOT_APPLIED and version.constrained_amount is not None:
        detail = {"value": format_exact(to_fraction(version.constrained_amount))}
        constrained_inputs = [SourceRef("estimate_version", version.version_key, detail)]
        source = "constrained_amount"
    constrained_id = tb.node(
        measure=f"vc_constrained{suffix}",
        subject_key=version.estimate_key,
        period_key=None,
        value=round_half_up(element.constrained, minor_unit),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=CONSTRAINED_FORMULA,
        inputs=constrained_inputs,
        params={
            "constraint": element.constraint,
            "direction": element.direction,
            "sign": sign,
            "source": source,
            "version_key": version.version_key,
        },
        exact=element.constrained,
        narrative_key=CONSTRAINED_FORMULA.rsplit(".v", 1)[0],
    )
    return unconstrained_id, constrained_id
