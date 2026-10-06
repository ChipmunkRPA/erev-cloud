"""Stage 09 redemption pattern, breakage and the unclaimed-property carve-out (ENGINE_SPEC_B §9.2.8
S09-R-27 to S09-R-31, S09-R-21, S09-R-22, S09-INV-11; POLICIES POL-055, POL-241, PT-02, ALG-05
§2.6.2 and §2.6.4; 606-10-55-46 to 55-49; ENC-8).

A ``REDEMPTION_PATTERN`` obligation (prepaid credits, gift cards, stored value) or a material-right
option of ``option_type = LOYALTY_POINTS`` recognises its allocation X over the units issued Q by
the customer's exercise pattern. Redeemed units R are the control-transferring deliveries less
returns (§9.2.4) plus the non-royalty ``USAGE_REPORTED`` quantities (drawdown, S09-R-21). The
``BREAKAGE`` estimate version in force at the date states R_exp (``expected_quantity``, including
expected rollover use under POL-241) and b (``rate``); the entitlement ratio ρ = R_exp ÷ Q + b is
at most 1 and its complement u = 1 − ρ is the unclaimed-property share, never revenue (S09-R-28).

The exact target E_total is X × the entitlement progress of §9.2.8, which this module computes as
the ``progress_ratio`` of the ``FIXED`` component (the redemption formula ids replace the units
formula), so ``revenue_target_exact`` and ``revenue_cum`` follow CV-63 unchanged: under POL-055
``PROPORTIONAL_TO_EXERCISE`` with a version, E_total ÷ X = min(1, max(R ÷ Q, ρ × min(1, R ÷
R_exp))); under ``WHEN_REMOTE`` (or without a version) R ÷ Q plus the remaining share once a
REVIEWED ``CONSTRAINT`` judgement attests remoteness (S09-R-29); at expiry (the end date passed,
``MATERIAL_RIGHT_EXPIRED`` or a termination) 1 − u (S09-R-28). The breakage part of the posted
target is C_total − min(round(X × R ÷ Q), C_total) (S09-R-27, S09-R-30; node
``breakage_revenue_cum``), and at expiry the unclaimed-property amount A − C_total is published for
stage 10 (node ``unclaimed_property_cum``; refund component ``UNCLAIMED_PROPERTY``, JET-04b).
``BREAKAGE_EXPECTED_ZERO`` and ``ESTIMATE_CONSTRAINT_RANGE`` fail closed as ``EngineError`` (§9.4);
``BREAKAGE_OVER_REDEMPTION`` is a ``WARNING`` finding. POL-241 ``FORFEIT_AT_TERM_END`` is not built
and fails closed (C-09). Every value comes from a registered formula, so the trace reproduces it
(DG-KRN-EXP-04). Private to stage 09. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, rational_param
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.s09_recognition.progress_time import Progress
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    Finding,
    ObligationState,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "BREAKAGE_MEASURE",
    "ESCHEAT_MEASURE",
    "EXPIRY_FORMULA",
    "METHOD_POLICY",
    "PROPORTIONAL",
    "PROPORTIONAL_FORMULA",
    "REMOTE_FORMULA",
    "ROLLOVER_POLICY",
    "WHEN_REMOTE",
    "EscheatComponent",
    "RedemptionTarget",
    "applies",
    "breakage_posted",
    "emit",
    "expired_on",
    "pin_at",
    "redeemed_units",
    "target",
]

METHOD_POLICY: Final = "breakage.method"  # POL-055
ROLLOVER_POLICY: Final = "credits.rollover_treatment"  # POL-241
PROPORTIONAL: Final = "PROPORTIONAL_TO_EXERCISE"
WHEN_REMOTE: Final = "WHEN_REMOTE"
EXPIRY: Final = "EXPIRY"
INCLUDING_ROLLOVER: Final = "BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE"
PROPORTIONAL_FORMULA: Final = "breakage.proportional.v1"
REMOTE_FORMULA: Final = "breakage.remote.v1"
EXPIRY_FORMULA: Final = "breakage.expiry.v1"
BREAKAGE_MEASURE: Final = "breakage_revenue_cum"
ESCHEAT_MEASURE: Final = "unclaimed_property_cum"
BREAKAGE_KIND: Final = "BREAKAGE"  # E-09
LOYALTY_POINTS: Final = "LOYALTY_POINTS"  # E-92
REDEMPTION_PATTERN: Final = "REDEMPTION_PATTERN"  # E-11
OVER_REDEMPTION: Final = "BREAKAGE_OVER_REDEMPTION"
EXPECTED_ZERO: Final = "BREAKAGE_EXPECTED_ZERO"
CONSTRAINT_RANGE: Final = "ESTIMATE_CONSTRAINT_RANGE"
_FORMULA_OF_MODE: Final[Mapping[str, str]] = MappingProxyType(
    {PROPORTIONAL: PROPORTIONAL_FORMULA, WHEN_REMOTE: REMOTE_FORMULA, EXPIRY: EXPIRY_FORMULA}
)
_STAGE: Final = 9
_KEY_ESCAPES: Final[Mapping[str, str]] = MappingProxyType(
    {"%": "%25", "/": "%2F", "@": "%40", "#": "%23", ":": "%3A"}
)  # CV-21


@dataclass(frozen=True, slots=True)
class EscheatComponent:
    """The unclaimed-property amount A − C_total of an expired redemption obligation at a period
    end (S09-R-28; §9.1 ``escheat_components``): stage 10 opens the ``UNCLAIMED_PROPERTY`` refund
    component from it (JET-04b), consumed by the remittance credit memo."""

    subject_key: str
    contract_key: str
    entity: str  # contracting entity
    period_key: str
    expired_on: date
    amount: int  # minor units
    node_id: str  # the unclaimed_property_cum node


@dataclass(frozen=True, slots=True)
class RedemptionTarget:
    """The §9.2.8 measurement of a redemption obligation at a date and position."""

    progress: Progress  # E_total ÷ X: the entitlement progress, with its formula and params
    quantity: Fraction  # Q, units or points issued
    redeemed: Fraction  # R
    mode: str  # PROPORTIONAL_TO_EXERCISE | WHEN_REMOTE | EXPIRY
    pin: EstimateVersionInput | None  # the BREAKAGE version in force
    expired_on: date | None  # the expiry date when the obligation has expired at the date
    unclaimed_share: Fraction  # u, 0 unless expired with a version stating ρ < 1
    findings: tuple[Finding, ...]


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def _encode(component: str) -> str:
    return "".join(_KEY_ESCAPES.get(character, character) for character in component)


def applies(ob: ObligationState) -> bool:
    """A ``REDEMPTION_PATTERN`` obligation, or a ``LOYALTY_POINTS`` option (S09-R-21, S09-R-31)."""
    if str(ob.recognition_method) == REDEMPTION_PATTERN:
        return True
    terms = ob.material_right
    return terms is not None and terms.terms.option_type == LOYALTY_POINTS


def pin_at(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None = None
) -> EstimateVersionInput | None:
    """The ``BREAKAGE`` version of the obligation in force at ``d`` and ``position`` (S01-R-18):
    the greatest (effective date, version number) among the versions whose applying event the
    position admits."""
    prefix = f"{_encode(ob.contract_key)}/"
    found: EstimateVersionInput | None = None
    for versions in st.estimates.pins.values():
        for pin in versions:
            version = pin.version
            if version.estimate_kind != BREAKAGE_KIND:
                continue
            if not version.estimate_key.startswith(prefix):
                continue
            if version.obligation_key != ob.obligation_key and (
                ob.obligation_key not in version.target_obligation_keys
            ):
                continue
            if version.effective_date > d:
                continue
            if position is not None and not position.admits(pin.event_order_key):
                continue
            if found is None or (version.effective_date, version.version_no) > (
                found.effective_date,
                found.version_no,
            ):
                found = version
    return found


def redeemed_units(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    d: date,
    position: Position | None = None,
) -> Fraction:
    """R: control-transferring deliveries less returns, plus non-royalty usage quantities."""
    counts = progress_events.tally(ctx, st, contract, ob, d, position)
    usage = Fraction(0)
    for ev in st.measure_events:
        if ev.event_type != "USAGE_REPORTED":
            continue
        if not progress_events.admitted(ev, d, position) or not progress_events.concerns(ev, ob):
            continue
        if ev.payload.get("is_royalty_statement") in (True, "true"):
            continue
        usage += progress_events.quantity(ev, ob)
    return max(Fraction(0), counts.counted - counts.returned + usage)


def expired_on(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None = None,
) -> date | None:
    """The date the rights lapsed, when they have by ``d`` (§9.2.8 ``expired_on``).

    A ``MATERIAL_RIGHT_EXPIRED`` naming the obligation and admitted at the position; a termination
    on or before ``d``; or the end date of the segment in force (the extended end after a rollover,
    S09-R-22) passed: from the close of that day, so a measurement positioned among the day's
    events precedes the lapse (as the return window of S09-R-26; D-87 L6-5-Q-25).
    """
    found: list[date] = []
    for ev in st.measure_events:
        if ev.event_type != "MATERIAL_RIGHT_EXPIRED":
            continue
        if progress_events.admitted(ev, d, position) and progress_events.concerns(ev, ob):
            found.append(ev.effective_date)
    if ob.terminated_on is not None and ob.terminated_on <= d:
        found.append(ob.terminated_on)
    end = seg.totals.end_date or ob.end_date
    if end is not None and (d > end or (d == end and position is None)):
        found.append(end)
    return min(found) if found else None


def _remote_attested(
    ctx: BookContext, contract: ContractView, ob: ObligationState, pin: EstimateVersionInput
) -> bool:
    """A REVIEWED ``CONSTRAINT`` judgement of the book with ``remote = true`` for the version's
    element (05 §3.6.5; 04 T-CON-19 members ``estimate_key``, ``remote``)."""
    for judgement in contract.header.judgements:
        if judgement.topic != "CONSTRAINT":
            continue
        if judgement.book_code not in (None, str(ctx.book_code)):
            continue
        if judgement.outcome.get("remote") != "true":
            continue
        named = judgement.outcome.get("estimate_key")
        if named in (None, "", pin.estimate_key, pin.element_code, pin.version_key):
            return True
    return False


def _policy(ctx: BookContext, ob: ObligationState, code: str) -> str:
    value = ctx.policies.value(
        code, contract=ob.contract_key, obligation=ob.subject_key, entity=ob.performing_entity
    )
    if not isinstance(value, str):
        raise _invariant("a breakage policy value is not a literal", ob, rule="S09-R-27", code=code)
    return value


def _evaluate(ob: ObligationState, formula_id: str, params: Mapping[str, str]) -> Fraction:
    try:
        return FORMULAS[formula_id]((), params)
    except ValueError as error:
        raise EngineError(
            "NON_FINITE_AMOUNT",
            "the redemption progress is undefined for the obligation",
            subject_key=ob.subject_key,
            formula_id=formula_id,
            detail={"rule": "CV-32"},
        ) from error


def target(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None = None,
) -> RedemptionTarget:
    """``redemption_target`` of §9.2.8 at ``d``: the entitlement progress E_total ÷ X.

    Q is ``totals.quantity`` of the segment in force (a rollover extension keeps Q, X and A,
    S09-R-22); R counts from inception, whatever the segment's basis. Q ≤ 0 fails closed.
    """
    quantity = seg.totals.quantity
    if quantity <= 0:
        raise _invariant("a redemption obligation needs the units issued", ob, rule="S09-R-27")
    if (
        ctx.policies.has(ROLLOVER_POLICY)
        and _policy(ctx, ob, ROLLOVER_POLICY) != INCLUDING_ROLLOVER
    ):
        raise _invariant(
            "the credits rollover treatment is not built",
            ob,
            rule="S09-R-22",
            treatment=_policy(ctx, ob, ROLLOVER_POLICY),
        )
    redeemed = redeemed_units(ctx, st, contract, ob, d, position)
    pin = pin_at(st, ob, d, position)
    lapsed = expired_on(st, ob, seg, d, position)
    params: dict[str, str] = {
        "as_of": d.isoformat(),
        "quantity": rational_param(quantity),
        "redeemed": rational_param(redeemed),
    }
    findings: list[Finding] = []
    unclaimed = Fraction(0)
    if lapsed is not None:
        mode = EXPIRY
        if pin is not None:
            rho = _entitlement(ob, pin, quantity)
            unclaimed = max(Fraction(0), 1 - rho)
        params["expired_on"] = lapsed.isoformat()
        params["unclaimed_share"] = rational_param(unclaimed)
    elif pin is not None and _policy(ctx, ob, METHOD_POLICY) == PROPORTIONAL:
        mode = PROPORTIONAL
        expected, rate = _members(ob, pin)
        if expected <= 0:
            raise EngineError(
                EXPECTED_ZERO,
                "a PROPORTIONAL_TO_EXERCISE breakage version expects no redemptions",
                subject_key=ob.subject_key,
                detail={"rule": "S09-R-27", "version_key": pin.version_key},
            )
        rho = _entitlement(ob, pin, quantity)
        if redeemed > expected:
            findings.append(
                Finding(
                    OVER_REDEMPTION,
                    "WARNING",
                    ob.subject_key,
                    {
                        "expected_quantity": money.format_exact(expected),
                        "redeemed": money.format_exact(redeemed),
                        "rule": "S09-R-27",
                        "version_key": pin.version_key,
                    },
                    _STAGE,
                    None,
                )
            )
        params["expected"] = rational_param(expected)
        params["rate"] = rational_param(rate)
        params["version_key"] = pin.version_key
    else:
        mode = WHEN_REMOTE
        remote = pin is not None and _remote_attested(ctx, contract, ob, pin)
        params["rate"] = rational_param(_members(ob, pin)[1] if pin is not None else Fraction(0))
        params["remote"] = "true" if remote else "false"
        if pin is not None:
            params["version_key"] = pin.version_key
    params["mode"] = mode
    formula_id = _FORMULA_OF_MODE[mode]
    frozen: Mapping[str, str] = MappingProxyType(dict(sorted(params.items())))
    value = _evaluate(ob, formula_id, frozen)
    return RedemptionTarget(
        progress=Progress(value, formula_id, frozen),
        quantity=quantity,
        redeemed=redeemed,
        mode=mode,
        pin=pin,
        expired_on=lapsed,
        unclaimed_share=unclaimed,
        findings=tuple(findings),
    )


def _members(ob: ObligationState, pin: EstimateVersionInput) -> tuple[Fraction, Fraction]:
    """(R_exp, b) of a ``BREAKAGE`` version; an absent member reads 0 (04 T-CON-13)."""
    expected = (
        Fraction(0) if pin.expected_quantity is None else money.to_fraction(pin.expected_quantity)
    )
    rate = Fraction(0) if pin.rate is None else money.to_fraction(pin.rate)
    if rate < 0 or expected < 0:
        raise _invariant(
            "a breakage version carries a negative member",
            ob,
            rule="S09-R-27",
            version_key=pin.version_key,
        )
    return expected, rate


def _entitlement(ob: ObligationState, pin: EstimateVersionInput, quantity: Fraction) -> Fraction:
    """ρ = R_exp ÷ Q + b, at most 1 (S09-R-27); above 1 raises ``ESTIMATE_CONSTRAINT_RANGE``."""
    expected, rate = _members(ob, pin)
    rho = expected / quantity + rate
    if rho > 1:
        raise EngineError(
            CONSTRAINT_RANGE,
            "the breakage entitlement ratio exceeds 1",
            subject_key=ob.subject_key,
            detail={
                "entitlement_ratio": money.format_exact(rho),
                "rule": "S09-R-27",
                "version_key": pin.version_key,
            },
        )
    return rho


def breakage_posted(
    c_total: int, x_exact: Fraction, quantity: Fraction, redeemed: Fraction, mu: int
) -> int:
    """C_breakage = C_total − min(round(X × R ÷ Q), C_total), minor units (S09-R-27, S09-INV-11)."""
    if quantity <= 0:
        raise ValueError("breakage needs the units issued")
    redeemed_posted = money.round_half_up(x_exact * redeemed / quantity, mu)
    return c_total - min(redeemed_posted, c_total)


def emit(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    part: RedemptionTarget,
    seg: AllocationSegment,
    revenue_node_id: str,
    c_total: int,
    mu: int,
) -> tuple[str, str | None]:
    """``breakage_revenue_cum`` and, at expiry with u > 0, ``unclaimed_property_cum`` (§9.5).

    Both cite the period's ``revenue_cum`` node (C_total) as their input; the breakage node reuses
    the mode's formula id with param ``part = breakage`` and the escheat node ``breakage.expiry.v1``
    with ``part = escheat``, so ``reevaluate`` recomputes each from its cited input.
    """
    sources: list[str | SourceRef] = [revenue_node_id]
    if part.pin is not None:
        detail = {
            "member": "expected_quantity",
            "value": money.format_exact(_members(ob, part.pin)[0]),
        }
        sources.append(SourceRef("estimate_version", part.pin.version_key, detail))
    breakage_id = tb.node(
        measure=BREAKAGE_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=breakage_posted(c_total, seg.x_exact, part.quantity, part.redeemed, mu),
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=part.progress.formula_id,
        inputs=sources,
        params={
            "as_of": part.progress.params["as_of"],
            "mode": part.mode,
            "part": "breakage",
            "quantity": rational_param(part.quantity),
            "redeemed": rational_param(part.redeemed),
            "x_exact": rational_param(seg.x_exact),
        },
        narrative_key=part.progress.formula_id.rsplit(".v", 1)[0],
    )
    if part.expired_on is None or part.unclaimed_share == 0:
        return breakage_id, None
    escheat_id = tb.node(
        measure=ESCHEAT_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=seg.a_posted - c_total,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=EXPIRY_FORMULA,
        inputs=[revenue_node_id],
        params={
            "a_posted": str(seg.a_posted),
            "as_of": part.progress.params["as_of"],
            "expired_on": part.expired_on.isoformat(),
            "mode": EXPIRY,
            "part": "escheat",
            "unclaimed_share": rational_param(part.unclaimed_share),
        },
        narrative_key=EXPIRY_FORMULA.rsplit(".v", 1)[0],
    )
    return breakage_id, escheat_id
