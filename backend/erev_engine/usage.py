"""Right to invoice and usage: the realised amounts of a ``PERIOD_VC`` component (ENC-6).

ENGINE_SPEC S04-R-06 and ENGINE_SPEC_B §9.2.6: S09-R-18 (``RIGHT_TO_INVOICE``, 606-10-55-18 —
revenue equals the amount the entity has a right to invoice for performance to date; the source is
``USAGE_REPORTED.rated_amount``, else invoiced amounts net of credit memos and taxes) as completed
by D-87 L6-5-Q-16 (delivered quantity × the booking line's ``unit_price`` before the invoiced
fallback; S01-R-17 over-delivery does not apply to such a rate line), S09-R-19 (``USAGE`` under
POL-240 ``DERIVED``: usage fees counted at the end of their usage period) and S09-R-01 / S09-R-02
(both ride the ``PERIOD_VC`` component: X = A = the realised amount, the amount stage 04 prices).

A stage-neutral kernel like ``royalties``: stage 01 exempts the right-to-invoice lines from the
over-delivery check, stage 04 prices the realised amounts, stage 05 opens the marker component and
stage 09 recognises it — all from ONE source rule here, so that the transaction price and the
recognition target carry the same amounts at every date (S09-R-02; 04 DB-17 V1) and no stage
imports another stage's helpers for it (DG-ENG-07). The kernel reads stage state by attribute only
(``EventView`` under ``TYPE_CHECKING``), returns exact ``Fraction`` currency units (CV-30) and uses
the standard library alone (DG-ARC-02); no floats. Callers supply the admission predicate —
stage 09's ENG-06 position at d, stage 04's ``before`` order key (S04-R-06 counts usage by its
``usage_period_end``, not by the report date) — and convert to minor units.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erev_engine import royalties
from erev_engine.bundle import EstimateVersionInput, ProductInput, RuleSetInput, TemplateInput
from erev_engine.money import to_fraction

if TYPE_CHECKING:  # the kernel reads stage state by attribute only (DG-ARC-02 layering)
    from erev_engine.stages.state import EventView

__all__ = [
    "DERIVED",
    "ESTIMATE_MEASUREMENT_PERIOD_TP",
    "GUARD_ALLOW",
    "GUARD_ELEMENT_TYPES",
    "GUARD_FINDING",
    "GUARD_POLICY",
    "MEASURE_POLICY",
    "REALISED_METHODS",
    "RIGHT_TO_INVOICE",
    "SOURCE_DELIVERED_UNIT_PRICE",
    "SOURCE_INVOICED_NET",
    "SOURCE_USAGE_RATED",
    "TIER_MINIMUM_POLICY",
    "USAGE",
    "RtiItem",
    "RtiRealisation",
    "above_stated",
    "derived_usage",
    "expedient_blockers",
    "right_to_invoice",
    "right_to_invoice_lines",
    "template_at",
    "unit_price_of",
]

RIGHT_TO_INVOICE: Final = "RIGHT_TO_INVOICE"  # E-11
USAGE: Final = "USAGE"  # E-11
# Methods whose realised amounts ride the PERIOD_VC component (S09-R-01); their FIXED component is
# the stand-ready fee or minimum (S09-R-19, S09-R-20).
REALISED_METHODS: Final = frozenset({RIGHT_TO_INVOICE, USAGE})
TIER_MINIMUM_POLICY: Final = "usage.tier_minimum_method"  # POL-240
DERIVED: Final = "DERIVED"
ESTIMATE_MEASUREMENT_PERIOD_TP: Final = "ESTIMATE_MEASUREMENT_PERIOD_TP"
# S09-R-18 source order, as completed by D-87 L6-5-Q-16.
SOURCE_USAGE_RATED: Final = "USAGE_RATED"
SOURCE_DELIVERED_UNIT_PRICE: Final = "DELIVERED_UNIT_PRICE"
SOURCE_INVOICED_NET: Final = "INVOICED_NET"
POB_ASSIGNMENT_KIND: Final = "POB_ASSIGNMENT"  # E-55
MEASURE_POLICY: Final = "recognition.measure_of_progress"  # POL-091 (S03-R-17: level O overrides)
GUARD_POLICY: Final = "recognition.right_to_invoice_guard"  # POL-092
GUARD_ALLOW: Final = "ALLOW"
GUARD_FINDING: Final = "RTI_EXPEDIENT_NOT_APPLICABLE"  # 04 table 15.4-C (rev 1.33)
# POL-092: pricing terms that stop the invoice from corresponding directly to the value of
# performance — a tier, rebate or declining rate, or a minimum commitment (T-CON-12 element types).
GUARD_ELEMENT_TYPES: Final = frozenset({"VOLUME_TIER", "REBATE", "PRICE_PROTECTION", "USAGE"})
VARIABLE_CONSIDERATION: Final = "VARIABLE_CONSIDERATION"  # E-09
_KEY_ESCAPES: Final[Mapping[str, str]] = MappingProxyType(
    {"%": "%25", "/": "%2F", "@": "%40", "#": "%23", ":": "%3A"}
)  # CV-21, as ``royalties``
PARITY_PRESET: Final = "LEGACY_PARITY"  # DG-ENG-09
ZERO: Final = Fraction(0)


@dataclass(frozen=True, slots=True)
class RtiItem:
    """One realised amount and the event it comes from (currency units)."""

    event_key: str
    amount: Fraction


@dataclass(frozen=True, slots=True)
class RtiRealisation:
    """Realised amounts by source (S09-R-18 / D-87 L6-5-Q-16; S09-R-19)."""

    source: str  # SOURCE_* literal
    items: tuple[RtiItem, ...]
    # USAGE_REPORTED events of the obligation without ``rated_amount`` (a NON_FINITE_AMOUNT finding
    # at stage 09, §9.4); they contribute nothing.
    unrated: tuple[str, ...]

    @property
    def amount(self) -> Fraction:
        return sum((item.amount for item in self.items), ZERO)


def _text(payload: Mapping[str, object], name: str) -> str | None:
    value = payload.get(name)
    return value if isinstance(value, str) else None


def _fraction(payload: Mapping[str, object], name: str) -> Fraction | None:
    value = payload.get(name)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str | int | Decimal | Fraction):
        return to_fraction(value)
    return None


def _date(payload: Mapping[str, object], name: str) -> date | None:
    value = payload.get(name)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def above_stated(items: Sequence[RtiItem], stated: Fraction) -> tuple[RtiItem, ...]:
    """The part of the right to invoice above the line's stated price P, item by item in order
    (ENGINE_SPEC S04-R-06 rev 1.21; S09-R-18 rev 1.20; D-98 candidate 28): with c₀ the cumulative
    amount before an item and c₁ after it, the item realises max(0, c₁ − P) − max(0, c₀ − P) on the
    ``PERIOD_VC`` component — the S09-R-33 guarantee pattern; P = 0 passes every item through. Items
    that realise nothing are dropped."""
    if stated <= 0:
        return tuple(items)
    found: list[RtiItem] = []
    cumulative = ZERO
    for item in items:
        before = max(ZERO, cumulative - stated)
        cumulative += item.amount
        part = max(ZERO, cumulative - stated) - before
        if part != 0:
            found.append(RtiItem(item.event_key, part))
    return tuple(found)


def unit_price_of(booking: Mapping[str, object], obligation_key: str) -> Fraction | None:
    """The ``unit_price`` of the obligation's booking line (04 §16.1; T-CON-05), or None."""
    lines = booking.get("lines")
    if not isinstance(lines, list | tuple):
        return None
    for line in lines:
        if not isinstance(line, Mapping):
            continue
        if _text(line, "obligation_key") == obligation_key:
            return _fraction(line, "unit_price")
    return None


def _own_events(
    measure_events: Sequence[EventView],
    *,
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    admits: Callable[[EventView], bool],
) -> list[EventView]:
    return [
        ev
        for ev in measure_events
        if admits(ev) and royalties.names_obligation(ev, contract_key, obligation_key, subject_key)
    ]


def _rated(events: Sequence[EventView], at: date) -> RtiRealisation:
    """The ``rated_amount`` of non-royalty ``USAGE_REPORTED`` events whose usage period ended by
    ``at`` (S09-R-19; S04-R-06 counts by the period end, not the report date); an event without a
    usage period end counts from its report date."""
    items: list[RtiItem] = []
    unrated: list[str] = []
    for ev in events:
        if ev.event_type != "USAGE_REPORTED" or royalties.is_statement(ev):
            continue
        period_end = _date(ev.payload, "usage_period_end")
        if (period_end if period_end is not None else ev.effective_date) > at:
            continue
        rated = _fraction(ev.payload, "rated_amount")
        if rated is None:
            unrated.append(ev.event_key)
            continue
        items.append(RtiItem(ev.event_key, rated))
    return RtiRealisation(SOURCE_USAGE_RATED, tuple(items), tuple(unrated))


def derived_usage(
    measure_events: Sequence[EventView],
    *,
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    at: date,
    admits: Callable[[EventView], bool],
) -> RtiRealisation:
    """S09-R-19 (POL-240 ``DERIVED``): the rated non-royalty usage of one obligation whose usage
    period ended on or before ``at``, over the events ``admits`` accepts (S04-R-06 prices the same
    amounts)."""
    own = _own_events(
        measure_events,
        contract_key=contract_key,
        obligation_key=obligation_key,
        subject_key=subject_key,
        admits=admits,
    )
    return _rated(own, at)


def right_to_invoice(
    measure_events: Sequence[EventView],
    *,
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    booking: Mapping[str, object],
    at: date,
    admits: Callable[[EventView], bool],
) -> RtiRealisation:
    """The right to invoice of one obligation at ``at`` over the events ``admits`` accepts.

    Source order (S09-R-18; D-87 L6-5-Q-16): (1) the ``rated_amount`` of the obligation's
    non-royalty ``USAGE_REPORTED`` events whose ``usage_period_end`` is on or before ``at`` (an
    unrated event is reported, not priced); (2) with no usage event, the net delivered quantity
    (``DELIVERY_RECORDED`` less ``RETURN_RECORDED``) × the booking line's ``unit_price``, when the
    line carries one; (3) otherwise the invoiced amounts (``BILLING_RECORDED`` ``amount`` less any
    ``tax_amount``) net of ``CREDIT_MEMO_RECORDED`` amounts. Invoices without performance create no
    revenue under (1) and (2) because they are not read there.
    """
    own = _own_events(
        measure_events,
        contract_key=contract_key,
        obligation_key=obligation_key,
        subject_key=subject_key,
        admits=admits,
    )
    if any(ev.event_type == "USAGE_REPORTED" and not royalties.is_statement(ev) for ev in own):
        return _rated(own, at)
    # Deliveries, returns, invoices and credit memos count from their effective date (a price or
    # target measured at ``at`` never reads a later event, whatever the caller's position admits).
    own = [ev for ev in own if ev.effective_date <= at]
    unit_price = unit_price_of(booking, obligation_key)
    movements = [ev for ev in own if ev.event_type in ("DELIVERY_RECORDED", "RETURN_RECORDED")]
    if movements and unit_price is not None:
        items = []
        for ev in movements:
            quantity = _fraction(ev.payload, "quantity") or ZERO
            sign = -1 if ev.event_type == "RETURN_RECORDED" else 1
            items.append(RtiItem(ev.event_key, sign * quantity * unit_price))
        return RtiRealisation(SOURCE_DELIVERED_UNIT_PRICE, tuple(items), ())
    items = []
    for ev in own:
        if ev.event_type == "BILLING_RECORDED":
            amount = _fraction(ev.payload, "amount") or ZERO
            tax = _fraction(ev.payload, "tax_amount") or ZERO
            items.append(RtiItem(ev.event_key, amount - tax))
        elif ev.event_type == "CREDIT_MEMO_RECORDED":
            items.append(RtiItem(ev.event_key, -(_fraction(ev.payload, "amount") or ZERO)))
    return RtiRealisation(SOURCE_INVOICED_NET, tuple(items), ())


def _encode(component: str) -> str:
    return "".join(_KEY_ESCAPES.get(character, character) for character in component)  # CV-21


def _targets(version: EstimateVersionInput, contract_key: str, obligation_key: str) -> bool:
    """A ``VARIABLE_CONSIDERATION`` element of the contract naming the obligation (T-CON-12)."""
    if version.estimate_kind != VARIABLE_CONSIDERATION:
        return False
    if not version.estimate_key.startswith(f"{_encode(contract_key)}/"):
        return False
    return version.obligation_key == obligation_key or (
        obligation_key in version.target_obligation_keys
    )


def expedient_blockers(
    *,
    contract_key: str,
    obligation_key: str,
    booking: Mapping[str, object],
    versions: Iterable[EstimateVersionInput],
) -> tuple[str, ...]:
    """POL-092 (S09-R-18 rev 1.21; D-98 candidate 37): the reasons the right-to-invoice expedient
    does not apply to the obligation — ``ELEMENT:<type>:<estimate key>`` for every
    ``VARIABLE_CONSIDERATION`` element of a guarded type (``GUARD_ELEMENT_TYPES``) targeting it, and
    ``NONLINEAR_PRICE:<total>≠<quantity>×<unit price>`` when its booking line's ``total_price``
    differs from ``quantity × unit_price`` while both are present and the total is not 0 (an
    upfront fee or a non-constant rate; a D-87 rate line books total 0). Empty = the expedient
    applies. Sorted; exact arithmetic (CV-30)."""
    reasons: list[str] = []
    for version in versions:
        if _targets(version, contract_key, obligation_key) and (
            version.vc_element_type in GUARD_ELEMENT_TYPES
        ):
            reasons.append(f"ELEMENT:{version.vc_element_type}:{version.estimate_key}")
    lines = booking.get("lines")
    for line in lines if isinstance(lines, list | tuple) else ():
        if not isinstance(line, Mapping) or _text(line, "obligation_key") != obligation_key:
            continue
        total = _fraction(line, "total_price")
        quantity = _fraction(line, "quantity")
        unit_price = _fraction(line, "unit_price")
        if total is None or quantity is None or unit_price is None or total == 0:
            continue
        if total != quantity * unit_price:
            reasons.append(f"NONLINEAR_PRICE:{total}≠{quantity}×{unit_price}")
    return tuple(sorted(reasons))


def template_at(versions: Iterable[TemplateInput], at: date) -> TemplateInput | None:
    """The greatest version whose ``[effective_from, effective_to)`` holds ``at`` (S03-R-02)."""
    eligible = [
        version
        for version in versions
        if version.effective_from <= at
        and (version.effective_to is None or at < version.effective_to)
    ]
    return max(eligible, key=lambda version: version.version_no, default=None)


def _rule_set_in_force(rule_sets: Iterable[RuleSetInput], at: date) -> bool:
    return any(
        version.kind == POB_ASSIGNMENT_KIND
        and version.effective_from <= at
        and (version.effective_to is None or at < version.effective_to)
        for version in rule_sets
    )


def right_to_invoice_lines(
    *,
    tenant_preset: str,
    products: Mapping[str, ProductInput],
    templates: Iterable[TemplateInput],
    rule_sets: Iterable[RuleSetInput],
    bookings: Mapping[str, tuple[date, Sequence[Mapping[str, object]]]],
    subject_key: Callable[[str, str], str],
    measure_overrides: Iterable[tuple[str, object]] = (),
) -> frozenset[str]:
    """D-87 L6-5-Q-16 (the S01-R-17 exemption): the booking lines whose EFFECTIVE recognition
    method in every book is unambiguously ``RIGHT_TO_INVOICE`` — their booked quantity is a rate
    line.

    ``bookings`` maps a contract key to (its inception date, its booking lines). Stage 01 runs
    before any book stage, so a line is exempted only when its resolution needs no book: the preset
    is not ``LEGACY_PARITY`` (S03-R-18 templates never use the method), no ``POB_ASSIGNMENT`` rule
    set version is in force at the inception (the pricing date, D-18 — a rule could route the line
    elsewhere, so the check is left to fire: fail closed, visible), the product's default template
    version effective at the inception is measured ``RIGHT_TO_INVOICE`` (S03-R-02
    ``PRODUCT_DEFAULT``), and no book's level-O ``recognition.measure_of_progress`` override
    (POL-091; S03-R-17) moves the obligation to another method — ``measure_overrides`` are the
    (subject key, value) pairs of those pins across the books (ENC6-R2: an override away from
    ``RIGHT_TO_INVOICE`` withholds the exemption; an override TO it never grants one, the template
    decides). Everything else is checked as today.
    """
    if tenant_preset == PARITY_PRESET:
        return frozenset()
    moved = {subject for subject, value in measure_overrides if value != RIGHT_TO_INVOICE}
    by_code: dict[str, list[TemplateInput]] = {}
    for version in templates:
        by_code.setdefault(version.template_code, []).append(version)
    rule_versions = tuple(rule_sets)
    found: set[str] = set()
    for contract_key in sorted(bookings):
        inception, lines = bookings[contract_key]
        if _rule_set_in_force(rule_versions, inception):
            continue
        for line in lines:
            obligation = _text(line, "obligation_key")
            product_code = _text(line, "product_code")
            if obligation is None or product_code is None:
                continue
            product = products.get(product_code)
            if product is None or product.default_template_code is None:
                continue
            template = template_at(by_code.get(product.default_template_code, ()), inception)
            if template is None or template.recognition_method != RIGHT_TO_INVOICE:
                continue
            subject = subject_key(contract_key, obligation)
            if subject in moved:
                continue
            found.add(subject)
    return frozenset(found)
