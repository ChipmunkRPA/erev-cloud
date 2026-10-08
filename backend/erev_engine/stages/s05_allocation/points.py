"""Stage 05 SSP points: extended values, the point for a stated price, bypasses and trace.

ENGINE_SPEC S05-R-06 (extended values), S05-R-07 (POLICIES §3.4; POL-071, POL-072), S05-R-08
(option and ``VC_LINE`` bypasses); trace node ``original_ssp_selected:<ob>:-`` (formula
``ssp.point.v1``). ``SSP_POINT_POLICIES`` is the POLICIES §3.4 table as data (§0.10). Private to
stage 05. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.bundle import MaterialRightInput, SspEntryInput, SspRangeInput
from erev_engine.enums import SspMethod, SspValueBasis
from erev_engine.money import format_exact, to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import RawLine
from erev_engine.stages.state import BookContext, SspResolution
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "BYPASS_OPTION_METHODS",
    "POINT",
    "RESIDUAL",
    "SSP_POINT_POLICIES",
    "VC_LINE",
    "Extended",
    "Point",
    "combine",
    "emit",
    "extend",
    "option_ssp",
    "select",
]

INSIDE_POLICY: Final = "ssp.inside_range_point"  # POL-071
OUTSIDE_POLICY: Final = "ssp.outside_range_point"  # POL-072
# POLICIES §3.4: the literal of each policy and the value it selects.
SSP_POINT_POLICIES: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        INSIDE_POLICY: MappingProxyType({"CONTRACT_PRICE": "PRICE", "MIDPOINT": "MID"}),
        OUTSIDE_POLICY: MappingProxyType(
            {
                "NEAREST_BOUND": "NEAREST",
                "MIDPOINT": "MID",
                "LOW_POINT": "LOW",
                "HIGH_POINT": "HIGH",
                "OBSERVABLE_POINT": "OBSERVABLE",
            }
        ),
    }
)
POINT: Final = "POINT"  # a point entry, or a call without a price (S05-R-06)
RESIDUAL: Final = "RESIDUAL"  # a residual candidate without a value (S05-R-12)
VC_LINE: Final = "VC_LINE"  # S05-R-08 bypass of a parity VC line
# S05-R-08: options whose SSP is the option SSP of S03-R-07, never range-tested.
BYPASS_OPTION_METHODS: Final = frozenset({"ENTERED_AMOUNT", "DISCOUNT_X_LIKELIHOOD"})
FORMULA_ID: Final = "ssp.point.v1"


@dataclass(frozen=True, slots=True)
class Extended:
    """Extended values at the line quantity in transaction currency (S05-R-06)."""

    unit_list_price: Fraction | None  # converted
    low: Fraction | None
    mid: Fraction | None
    high: Fraction | None
    point: Fraction | None
    observable: Fraction | None  # Q × observable_point, converted (S05-R-07)
    residual: bool


@dataclass(frozen=True, slots=True)
class Point:
    """The selected SSP for a stated price (S05-R-07)."""

    selected: Fraction
    in_range: bool | None
    policy: str  # the POL-071 or POL-072 literal applied, POINT or RESIDUAL
    observable_missing: bool


def extend(
    entry: SspEntryInput, line: RawLine, factor: Fraction, allocation_basis: Fraction | None
) -> Extended | None:
    """S05-R-06 at quantity Q with conversion ``factor`` (S05-R-05); ``None`` when no band row
    applies or the row carries no value.

    ``legacy_range``: mid = Q × L × (1 − d), ends mid × (1 ∓ r). ``AMOUNT`` rows: Q × row values;
    ``PERCENT_OF_LIST``: the same times ``unit_list_price``. ``cost_plus_margin`` without a band:
    point = Q × ``cost_basis`` × (1 + ``margin_ratio``). ``residual``: no value; a band row gives
    the observable range [low, high] that S05-R-12 checks R against. The band is sign aware: low is
    the smaller end and high the larger, so a negative quantity keeps low ≤ high (REQ-SSP-004
    native branch; the legacy 03 §3.1 negative branch selects the same point). A missing required
    member raises ``ValueError`` (CV-45).
    """
    quantity = line.quantity
    residual = entry.method == SspMethod.RESIDUAL
    if residual and not entry.ranges:
        return Extended(None, None, None, None, None, None, True)
    list_price = None if entry.unit_list_price is None else to_fraction(entry.unit_list_price)
    converted_list = None if list_price is None else list_price * factor
    observable = (
        None
        if entry.observable_point is None
        else quantity * to_fraction(entry.observable_point) * factor
    )
    if entry.method == SspMethod.LEGACY_RANGE:
        price = _required(entry.unit_list_price, entry, "unit_list_price")
        discount = _required(entry.midpoint_discount_ratio, entry, "midpoint_discount_ratio")
        mid = quantity * price * factor * (1 - discount)
        if entry.range_ratio is None:
            return Extended(converted_list, None, mid, None, None, observable, False)
        spread = to_fraction(entry.range_ratio)
        low, high = sorted((mid * (1 - spread), mid * (1 + spread)))
        return Extended(converted_list, low, mid, high, None, observable, False)
    if entry.method == SspMethod.COST_PLUS_MARGIN and not entry.ranges:
        cost = _required(entry.cost_basis, entry, "cost_basis")
        margin = _required(entry.margin_ratio, entry, "margin_ratio")
        point = quantity * cost * factor * (1 + margin)
        return Extended(converted_list, None, None, None, point, observable, False)
    row = _band_row(entry, line, allocation_basis)
    empty = Extended(None, None, None, None, None, None, True) if residual else None
    if row is None:
        return empty
    scale = quantity * factor
    if entry.value_basis == SspValueBasis.PERCENT_OF_LIST:
        scale *= _required(entry.unit_list_price, entry, "unit_list_price")

    def scaled(value: Decimal | None) -> Fraction | None:
        return None if value is None else scale * to_fraction(value)

    band_low, band_high = scaled(row.low_value), scaled(row.high_value)
    band_mid = scaled(row.mid_value)
    band_point = None if residual else scaled(row.point_value)
    if band_low is not None and band_high is not None:
        band_low, band_high = sorted((band_low, band_high))
    if all(value is None for value in (band_low, band_mid, band_high, band_point)):
        return empty
    return Extended(converted_list, band_low, band_mid, band_high, band_point, observable, residual)


def select(
    extended: Extended, price: Fraction | None, inside: object, outside: object, entry_key: str
) -> Point:
    """S05-R-07 (POLICIES §3.4) for stated price ``price``.

    Point entries: the point whatever P. ``price = None``: the point or the midpoint (S03-R-03).
    Range entries: inside [low, high] inclusive, ``CONTRACT_PRICE`` → P and ``MIDPOINT`` → mid;
    outside, ``NEAREST_BOUND`` → the nearer bound, ``MIDPOINT`` → mid, ``LOW_POINT`` → low,
    ``HIGH_POINT`` → high, ``OBSERVABLE_POINT`` → Q × ``observable_point``, or the nearer bound
    with ``observable_missing``. An unknown literal raises ``ValueError`` (CV-17).
    """
    if extended.residual:
        return Point(Fraction(0), None, RESIDUAL, False)
    if extended.point is not None:
        return Point(extended.point, None, POINT, False)
    low, mid, high = extended.low, extended.mid, extended.high
    if price is None or low is None or high is None:
        if mid is None:
            raise ValueError(f"{entry_key}: a range entry needs a midpoint (T-REF-30)")
        return Point(mid, None, POINT, False)
    inside_rule = SSP_POINT_POLICIES[INSIDE_POLICY].get(str(inside))
    outside_rule = SSP_POINT_POLICIES[OUTSIDE_POLICY].get(str(outside))
    if inside_rule is None or outside_rule is None:
        raise ValueError(f"{INSIDE_POLICY} or {OUTSIDE_POLICY} holds an unknown literal (CV-17)")
    if low <= price <= high:
        if inside_rule == "PRICE":
            return Point(price, True, str(inside), False)
        return Point(_mid(mid, entry_key), True, str(inside), False)
    nearer = low if price < low else high
    missing = False
    match outside_rule:
        case "NEAREST":
            selected = nearer
        case "MID":
            selected = _mid(mid, entry_key)
        case "LOW":
            selected = low
        case "HIGH":
            selected = high
        case _:
            missing = extended.observable is None
            selected = nearer if extended.observable is None else extended.observable
    return Point(selected, False, str(outside), missing)


def combine(parts: Sequence[SspResolution]) -> SspResolution:
    """The resolution of an obligation made of several lines: the host's keys, and the sums of
    the extended and selected values (S03-R-05 and S03-R-13 SSP weights are sums).

    An extended value absent on any part is absent on the sum; ``in_range`` is False when any part
    is outside its range, True when every part is inside, else None.
    """
    host = parts[0]
    if len(parts) == 1:
        return host

    def total(values: Sequence[Fraction | None]) -> Fraction | None:
        present = [value for value in values if value is not None]
        return sum(present, Fraction(0)) if len(present) == len(values) else None

    flags = [part.in_range for part in parts]
    in_range = False if False in flags else (True if all(flags) else None)
    return dataclasses.replace(
        host,
        range_key=host.range_key
        if all(part.range_key == host.range_key for part in parts)
        else None,
        low=total([part.low for part in parts]),
        mid=total([part.mid for part in parts]),
        high=total([part.high for part in parts]),
        selected=sum((part.selected for part in parts), Fraction(0)),
        in_range=in_range,
        residual_candidate=any(part.residual_candidate for part in parts),
    )


def option_ssp(
    st: IdentifiedState, terms: MaterialRightInput, at: date
) -> tuple[Fraction, SourceRef] | None:
    """S03-R-07 ``DISCOUNT_X_LIKELIHOOD``: SSP_opt = ``expected_purchase_amount`` ×
    ``incremental_discount_ratio`` × L, with L the ``rate`` of the ``EXERCISE_LIKELIHOOD`` pin at
    ``at``. ``None`` when 0 ≤ L ≤ 1 or ratio ≥ 0 fails (the caller raises ``NON_FINITE_AMOUNT``).
    A missing member or pin raises ``ValueError`` (CV-45)."""
    if terms.expected_purchase_amount is None or terms.incremental_discount_ratio is None:
        raise ValueError(f"{terms.obligation_key}: DISCOUNT_X_LIKELIHOOD needs its amounts")
    if terms.likelihood_estimate_key is None:
        raise ValueError(f"{terms.obligation_key}: DISCOUNT_X_LIKELIHOOD needs a likelihood")
    pin = st.canonical.estimates.pin(terms.likelihood_estimate_key, at)
    if pin is None or pin.rate is None:
        raise ValueError(f"{terms.likelihood_estimate_key}: no EXERCISE_LIKELIHOOD pin at {at}")
    likelihood = to_fraction(pin.rate)
    ratio = to_fraction(terms.incremental_discount_ratio)
    if not 0 <= likelihood <= 1 or ratio < 0:
        return None
    value = to_fraction(terms.expected_purchase_amount) * ratio * likelihood
    source = SourceRef("estimate_version", pin.version_key, {"value": format_exact(likelihood)})
    return value, source


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    subject_key: str,
    resolution: SspResolution,
    price: Fraction | None,
    sources: Sequence[SourceRef],
    merged: Sequence[str] = (),
    event_key: str | None = None,
) -> str:
    """Node ``original_ssp_selected:<ob>:-`` (§5.5: version key, entry key, low, mid, high,
    policy; also book, method, rate key, price, ``in_range`` and merged candidates). With
    ``event_key`` the node is the boundary's ``original_ssp_selected@<event key>:<ob>:-`` — the
    corrected selected SSP of an S06-R-26 repin or the SSP of a line a boundary creates (CV-50,
    D-98 candidates 123 and 124), the same params and canonical sources as at inception."""

    def text(value: Fraction | None) -> str:
        return "" if value is None else format_exact(value)

    in_range = "" if resolution.in_range is None else str(resolution.in_range).lower()
    params = {
        "book_code": resolution.book_code,
        "entry_key": resolution.entry_key,
        "high": text(resolution.high),
        "in_range": in_range,
        "low": text(resolution.low),
        "merged": ",".join(merged),
        "method": resolution.method,
        "mid": text(resolution.mid),
        "policy": resolution.point_policy,
        "price": text(price),
        "rate_key": resolution.rate_key or "",
        "residual_candidate": "true" if resolution.residual_candidate else "false",
        "value": format_exact(resolution.selected),
        "version_key": resolution.version_key,
    }
    measure = "original_ssp_selected" if event_key is None else f"original_ssp_selected@{event_key}"
    return tb.node(
        measure=measure,
        subject_key=subject_key,
        period_key=None,
        value=resolution.selected,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=FORMULA_ID,
        inputs=list(sources),
        params=params,
        narrative_key="ssp.point",
    )


def _mid(mid: Fraction | None, entry_key: str) -> Fraction:
    if mid is None:
        raise ValueError(f"{entry_key}: MIDPOINT needs a midpoint value (T-REF-30)")
    return mid


def _band_row(
    entry: SspEntryInput, line: RawLine, allocation_basis: Fraction | None
) -> SspRangeInput | None:
    """The first row whose ``band_from ≤ value < band_to`` for its ``band_dimension``."""
    for row in entry.ranges:
        dimension = row.band_dimension
        if dimension == "NONE":
            return row
        measure: Fraction
        if dimension == "QUANTITY":
            measure = line.quantity
        elif dimension == "DEAL_SIZE":
            if allocation_basis is None:
                continue
            measure = allocation_basis
        elif dimension == "TERM_MONTHS":
            start, end = line.line_start_date, line.line_end_date
            if start is None or end is None:
                continue
            measure = Fraction(dates.month_ends_between(start - timedelta(1), end))
        else:
            raise ValueError(f"{entry.entry_key}: unknown band_dimension {dimension!r}")
        low, high = row.band_from, row.band_to
        if (low is None or to_fraction(low) <= measure) and (
            high is None or measure < to_fraction(high)
        ):
            return row
    return None


def _required(value: Decimal | None, entry: SspEntryInput, name: str) -> Fraction:
    if value is None:
        raise ValueError(f"{entry.entry_key}: {entry.method} needs {name}")
    return to_fraction(value)


band_row = _band_row  # the snapshot nodes cite the row a line resolved through (ENG-T1F)
