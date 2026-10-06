"""Stage 04 expected returns: returnable obligations, return paths and the expected-returns memo.

ENGINE_SPEC S04-R-08 (with S04-R-08a), S04-R-08b; finding ``RETURN_ESTIMATE_MISSING``; formula
``tp.returns_expected.v1``; ENGINE_SPEC_B §9.2.7, S09-R-23; POLICIES ALG-06 §2.7.1 to §2.7.5
(CHK-029, CHK-060), POL-051 to POL-053; 04 T-CON-13 ``RETURN_RATE`` parameters. Private to stage 04.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import EstimateVersionInput, ResolvedPolicyInput
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    encode_key,
    obligation_subject_key,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.state import (
    BookContext,
    EstimatePins,
    EventView,
    Finding,
    Quota1,
    ReturnPath,
    ReturnPin,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ACTUAL_RETURNS_ONLY",
    "EXPECTED_RETURNS",
    "FORMULA",
    "KIND",
    "MODEL",
    "Measured",
    "Returnable",
    "emit",
    "findings",
    "measure",
    "path",
    "returnable",
]

KIND: Final = "RETURN_RATE"
FORMULA: Final = "tp.returns_expected.v1"
MODEL: Final = "returns.model"  # POL-051
REVERSAL: Final = "returns.reversal_rate"  # POL-052
SCOPE: Final = "returns.returned_units_scope"  # POL-053
EXPECTED_RETURNS: Final = "EXPECTED_RETURNS"
ACTUAL_RETURNS_ONLY: Final = "ACTUAL_RETURNS_ONLY"
_OVERRIDE_LEVELS: Final = frozenset({"O", "C"})
_PORTFOLIO_PREFIX: Final = "PORTFOLIO:"
_STAGE: Final = 4


@dataclass(frozen=True, slots=True)
class Returnable:
    """A returnable obligation (S04-R-08a) with the ``RETURN_RATE`` elements that target it."""

    obligation: PobDraft
    estimate_keys: tuple[str, ...]  # ascending
    model: str  # resolved POL-051 literal


@dataclass(frozen=True, slots=True)
class Measured:
    """The expected-returns reduction of one returnable obligation at a position (S04-R-08)."""

    obligation: PobDraft
    rate: Fraction  # r_p = x_exact ÷ Q of the segment in force
    returned: Fraction  # Y_p, units returned to the position
    expected: Fraction  # E_p, expected further returns
    posted: int  # −round(r_p × (Y_p + E_p)), minor units
    pin: EstimateVersionInput | None
    returns: tuple[tuple[EventView, Fraction], ...]  # (RETURN_RECORDED, quantity)


def returnable(ctx: BookContext, st: PobState) -> tuple[Returnable, ...]:
    """S04-R-08a: obligations targeted by a ``RETURN_RATE`` element, or whose ``returns.model`` is
    ``EXPECTED_RETURNS`` at level O, C or P. A framework default alone never makes an obligation
    returnable (OQ-A-15). ``VC_LINE`` obligations are never returnable."""
    found: list[Returnable] = []
    for ob in st.obligations:
        if ob.is_vc_line:
            continue
        keys = _elements(st, ob)
        model, set_at_level = _policy(ctx, st, ob, MODEL)
        if keys or (model == EXPECTED_RETURNS and set_at_level):
            found.append(Returnable(ob, keys, model or ACTUAL_RETURNS_ONLY))
    return tuple(found)


def path(ctx: BookContext, st: PobState, item: Returnable) -> ReturnPath:
    """S04-R-08b without ``r``: stage 05 publishes r = x_exact ÷ Q once the allocation exists.

    ``estimate_key`` is the first targeting element (empty without one); the pins are its approved
    versions by (effective date, version number); ``p_ref`` is the stated unit price (L2-2-Q-7);
    ``policy`` holds the resolved POL-051 to POL-053 values.
    """
    ob = item.obligation
    if ob.quantity == 0:
        raise ValueError(f"{ob.subject_key}: a returnable obligation has quantity 0")
    key = item.estimate_keys[0] if item.estimate_keys else ""
    versions = {
        applied.version.version_key: applied.version
        for applied in st.identified.canonical.estimates.pins.get(key, ())
    }
    ordered = sorted(versions.values(), key=lambda v: (v.effective_date, v.version_no))
    policy = {
        code: value
        for code in (MODEL, REVERSAL, SCOPE)
        if (value := _policy(ctx, st, ob, code)[0]) is not None
    }
    return ReturnPath(
        estimate_key=key,
        pins=tuple(_pin(version) for version in ordered),
        r=(),
        p_ref=ob.stated_price / ob.quantity,
        policy=MappingProxyType(dict(sorted(policy.items()))),
    )


def findings(ctx: BookContext, st: PobState, items: Sequence[Returnable]) -> tuple[Finding, ...]:
    """``RETURN_ESTIMATE_MISSING`` (``ERROR``): an ``EXPECTED_RETURNS`` obligation of a contract
    whose latest status is not ``DRAFT``, with no targeting pin at its first transfer and no
    reviewed ``OTHER`` outcome ``returns_immaterial = true``. An obligation not yet transferred has
    no first transfer, so it raises nothing (L2-2-Q-8)."""
    pins = st.identified.canonical.estimates
    found: list[Finding] = []
    for item in items:
        ob = item.obligation
        if item.model != EXPECTED_RETURNS or _latest_status(st, ob.contract_key) == "DRAFT":
            continue
        first = next((ev.effective_date for ev, _ in _events(st, ob, "DELIVERY_RECORDED")), None)
        if first is None:
            continue
        if any(pins.pin(key, first) is not None for key in item.estimate_keys):
            continue
        if _immaterial(ctx, st, ob):
            continue
        detail = {
            "first_transfer": first.isoformat(),
            "obligation_key": ob.obligation_key,
            "rule": "S04-R-08",
        }
        found.append(
            Finding("RETURN_ESTIMATE_MISSING", "ERROR", ob.subject_key, detail, _STAGE, None)
        )
    return tuple(sorted(found, key=Finding.sort_key))


def measure(
    ctx: BookContext,
    st: PobState,
    items: Sequence[Returnable],
    at: date,
    before: EventView | None,
    rates: Mapping[str, Fraction],
) -> tuple[Measured, ...]:
    """S04-R-08 per returnable obligation with a rate in ``rates``.

    Y = units returned by ``RETURN_RECORDED`` events to the position; E = the pinned
    ``expected_quantity`` (a portfolio pin without it: ``rate`` × units transferred, PT-06) less
    units returned after the pin's effective date, never below 0, and 0 from ``window_end_date``
    (the right expires at the end of that day, so E counts while ``at`` < window end; D-87
    L6-5-Q-25), under ``ACTUAL_RETURNS_ONLY`` or without a pin. The reduction is
    −round(r × (Y + E)).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    pins = st.identified.canonical.estimates
    found: list[Measured] = []
    for item in items:
        ob = item.obligation
        rate = rates.get(ob.subject_key)
        if rate is None:
            continue
        returns = tuple(_events(st, ob, "RETURN_RECORDED", at, before))
        returned = sum((quantity for _, quantity in returns), Fraction(0))
        pin = _latest_pin(pins, item.estimate_keys, at, before)
        expected = Fraction(0)
        if item.model != ACTUAL_RETURNS_ONLY and pin is not None:
            window = payload_date(pin.parameters, "window_end_date")
            if window is None or at < window:
                if pin.expected_quantity is not None:
                    base = to_fraction(pin.expected_quantity)
                elif pin.rate is not None:
                    transferred = sum(
                        (q for _, q in _events(st, ob, "DELIVERY_RECORDED", at, before)),
                        Fraction(0),
                    )
                    base = to_fraction(pin.rate) * transferred
                else:
                    raise ValueError(f"{pin.version_key}: RETURN_RATE needs expected_quantity")
                after = sum(
                    (q for ev, q in returns if ev.effective_date > pin.effective_date),
                    Fraction(0),
                )
                expected = max(Fraction(0), base - after)
        posted = -round_half_up(rate * (returned + expected), minor_unit)
        found.append(Measured(ob, rate, returned, expected, posted, pin, returns))
    return tuple(found)


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject_key: str,
    quota: Quota1,
    measured: Sequence[Measured],
) -> str:
    """Node ``expected_returns_amount`` (§4.4; ``tp.returns_expected.v1``); its id."""
    inputs: list[str | SourceRef] = []
    for item in measured:
        if item.pin is not None:
            detail = {"value": format_exact(item.expected)}
            inputs.append(SourceRef("estimate_version", item.pin.version_key, detail))
        inputs.extend(
            SourceRef("contract_event", event.event_key, {"value": format_exact(quantity)})
            for event, quantity in item.returns
        )
    params = {
        "expected": ",".join(format_exact(item.expected) for item in measured),
        "obligations": ",".join(item.obligation.subject_key for item in measured),
        "returned": ",".join(format_exact(item.returned) for item in measured),
        "signs": ",".join("-" for _ in measured),
        "unit_rates": ",".join(format_exact(item.rate) for item in measured),
    }
    return tb.node(
        measure=measure_name,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=FORMULA,
        inputs=inputs,
        params=params,
        exact=quota.exact,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )


def _pin(version: EstimateVersionInput) -> ReturnPin:
    params = version.parameters
    quantity = version.expected_quantity
    # A portfolio pin that states only the rate carries it, so stage 09 measures E on the units
    # each member transferred, as ``measure`` does (PT-06; L5-3-Q-3).
    rate = None if quantity is not None or version.rate is None else to_fraction(version.rate)
    return ReturnPin(
        effective_date=version.effective_date,
        version_key=version.version_key,
        expected_quantity=Fraction(0) if quantity is None else to_fraction(quantity),
        carrying_cost_per_unit=payload_fraction(params, "carrying_cost_per_unit"),
        recovery_cost_per_unit=payload_fraction(params, "recovery_cost_per_unit"),
        window_end_date=payload_date(params, "window_end_date"),
        rate=rate,
    )


def _policy(ctx: BookContext, st: PobState, ob: PobDraft, code: str) -> tuple[str | None, bool]:
    """(literal, set at level O, C or P): obligation or contract overrides, then the product and
    template ``policy_values`` (level P), then the resolved value."""
    try:
        resolved: ResolvedPolicyInput | None = ctx.policies.resolved(
            code, contract=ob.contract_key, obligation=ob.subject_key, entity=ob.performing_entity
        )
    except ValueError:  # the code is not declared in the bundle (CV-17)
        resolved = None
    value = None if resolved is None or not isinstance(resolved.value, str) else resolved.value
    if resolved is not None and resolved.level in _OVERRIDE_LEVELS and value is not None:
        return value, True
    cb = st.identified.canonical
    product = cb.group.products.get(ob.product_code)
    template = next(
        (
            version
            for version in cb.templates.versions.get(ob.template_code, ())
            if version.version_key == ob.template_version_key
        ),
        None,
    )
    for values in (
        None if product is None else product.policy_values,
        None if template is None else template.policy_values,
    ):
        literal = None if values is None else values.get(code)
        if literal is not None:
            return literal, True
    return value, resolved is not None and resolved.level == "P" and value is not None


def _elements(st: PobState, ob: PobDraft) -> tuple[str, ...]:
    """``RETURN_RATE`` element keys of the obligation's contract (or a portfolio containing it)
    whose ``obligation_key`` or ``target_obligation_keys`` name the obligation."""
    pins = st.identified.canonical.estimates.pins
    keys: list[str] = []
    for key in sorted(pins):
        applied = pins[key]
        if not applied:
            continue
        version = applied[-1].version
        if version.estimate_kind != KIND or not _belongs(st, key, ob.contract_key):
            continue
        targets = version.target_obligation_keys or (
            () if version.obligation_key is None else (version.obligation_key,)
        )
        if ob.obligation_key in targets:
            keys.append(key)
    return tuple(keys)


def _belongs(st: PobState, estimate_key: str, contract_key: str) -> bool:
    head = estimate_key.split("/", 1)[0]
    if head == contract_subject_key(contract_key):
        return True
    if not head.startswith(_PORTFOLIO_PREFIX):
        return False
    code = head[len(_PORTFOLIO_PREFIX) :]
    return any(
        encode_key(portfolio) == code and contract_key in members
        for portfolio, members in st.identified.canonical.group.portfolios.items()
    )


def _latest_pin(
    pins: EstimatePins, keys: Sequence[str], at: date, before: EventView | None
) -> EstimateVersionInput | None:
    found: EstimateVersionInput | None = None
    for key in keys:
        version = pins.pin(key, at, before)
        if version is None:
            continue
        if found is None or (version.effective_date, version.version_no) > (
            found.effective_date,
            found.version_no,
        ):
            found = version
    return found


def _events(
    st: PobState,
    ob: PobDraft,
    event_type: str,
    at: date | None = None,
    before: EventView | None = None,
) -> Iterator[tuple[EventView, Fraction]]:
    """(event, quantity) of the obligation's measure events of ``event_type`` in ENG-06 order,
    before ``before`` and on or before ``at``; a missing quantity raises ``ValueError``."""
    for event in st.identified.canonical.measure_events:
        if before is not None and event.order_key >= before.order_key:
            return
        if event.event_type != event_type or event.contract_key != ob.contract_key:
            continue
        if at is not None and event.effective_date > at:
            continue
        named = ob.subject_key in event.obligation_subject_keys or (
            payload_text(event.payload, "obligation_key") == ob.obligation_key
        )
        if not named:
            continue
        quantity = payload_fraction(event.payload, "quantity")
        if quantity is None:
            raise ValueError(f"{event.event_key}: a {event_type} event needs quantity (CV-45)")
        yield event, quantity


def _immaterial(ctx: BookContext, st: PobState, ob: PobDraft) -> bool:
    header = st.identified.canonical.contracts[ob.contract_key].header
    contract = header.external_id
    subjects = {
        contract,
        contract_subject_key(contract),
        f"{contract}/{ob.obligation_key}",
        obligation_subject_key(contract, ob.obligation_key),
    }
    return any(
        record.topic == "OTHER"
        and record.subject_key in subjects
        and record.book_code in (None, ctx.book_code)
        and record.outcome.get("obligation_key") == ob.obligation_key
        and record.outcome.get("returns_immaterial") == "true"
        for record in header.judgements
    )


def _latest_status(st: PobState, contract_key: str) -> str:
    segments = st.identified.timelines.get(contract_key, ())
    return segments[-1].status if segments else "DRAFT"
