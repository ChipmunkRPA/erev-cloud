"""Stage 03 bundle explosion and the SSP points it reads (ENGINE_SPEC S03-R-03; S05-R-02 to R-06).

Private to stage 03. A bundle line becomes one draft per component valid at the pricing date, and
its price is split by ``largest_remainder`` over the components' point SSPs (``relative_ssp``) or
their ``split_ratio`` (``fixed_percentage``). The SSP reader follows the ``resolve_ssp(ctx, draft,
at, price=None)`` contract of ENGINE_SPEC §5.2: book (S05-R-02), version (S05-R-03), entry
(S05-R-04) and the point or midpoint at quantity (S05-R-06). Stage 05 owns conversion (S05-R-05),
so an entry outside the transaction currency gives no point here. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Final

from erev_engine import dates
from erev_engine.bundle import (
    BundleComponentInput,
    ContractInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
)
from erev_engine.errors import EngineError
from erev_engine.money import largest_remainder, to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.templates import (
    PRICE_BUNDLE,
    BundleSplit,
    RawLine,
    decision,
    line_facts,
)
from erev_engine.stages.state import BookContext, Finding

__all__ = ["SspValues", "explode", "point_ssp", "ssp_entry", "ssp_values"]

RELATIVE_SSP: Final = "relative_ssp"
FIXED_PERCENTAGE: Final = "fixed_percentage"
LEGACY_SSP_BOOK: Final = "LEGACY-SKU-SSP"  # S05-R-02 (3)
_DEFAULT_VERSION_BASIS: Final = "LATEST_APPROVED_EFFECTIVE_AT_INCEPTION"
_RECORDED: Final = "recorded"  # stage 05 ``ssp_books.RECORDED`` (S05-R-03), read here first
_DIMENSIONS: Final = ("region", "channel", "segment", "deal_size_band", "term_band")


def explode(
    ctx: BookContext,
    st: IdentifiedState,
    raws: Sequence[RawLine],
    findings: MutableSequence[Finding],
) -> list[RawLine]:
    """S03-R-03: replace every bundle line by its components; other lines pass unchanged.

    Component ``obligation_key`` = ``<bundle line key>.<sequence, two digits>``; Q = bundle Q ×
    ``quantity_per_bundle``; parent = the bundle line. A component without a point SSP yields
    ``SSP_KEY_NOT_FOUND`` (``ERROR``) and the bundle line gives no draft. A bundle without a valid
    component raises ``EngineError("ENGINE_INVARIANT_VIOLATED")``.
    """
    exploded: list[RawLine] = []
    for raw in raws:
        product = st.canonical.group.products.get(raw.product_code)
        if product is None or not product.is_bundle:
            exploded.append(raw)
            continue
        components = [c for c in product.components if _valid(c, raw)]
        if not components:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a bundle has no component valid at the pricing date",
                subject_key=raw.subject_key,
                detail={"rule": "S03-R-03", "product_code": product.code},
            )
        parts = [
            dataclasses.replace(
                raw,
                obligation_key=f"{raw.obligation_key}.{component.sequence:02d}",
                product_code=component.component_product_code,
                quantity=raw.quantity * to_fraction(component.quantity_per_bundle),
                bundle_parent_obligation_key=raw.obligation_key,
                bundle_product_code=product.code,
                price_basis=PRICE_BUNDLE,
            )
            for component in components
        ]
        basis, weights = _weights(ctx, st, components, parts, findings)
        if weights is not None:
            exploded.extend(_split(ctx, raw, parts, basis, weights))
    return exploded


def ssp_entry(ctx: BookContext, st: IdentifiedState, raw: RawLine) -> SspEntryInput | None:
    """The SSP entry of a line at its pricing date (S05-R-02 to S05-R-04), or ``None``."""
    header = st.canonical.contracts[raw.contract_key].header
    book = _book(ctx, st, raw, header)
    version = None if book is None else _version(ctx, st, raw, book)
    return None if version is None else _entry(version, raw, header, ctx.txn_currency)


@dataclass(frozen=True, slots=True)
class SspValues:
    """Extended SSP values of a line at its quantity (S05-R-06); an absent value is ``None``."""

    version_key: str
    entry: SspEntryInput
    low: Fraction | None
    mid: Fraction | None
    high: Fraction | None
    point: Fraction | None


def ssp_values(ctx: BookContext, st: IdentifiedState, raw: RawLine) -> SspValues | None:
    """Book, version, entry and extended values at ``raw.pricing_date`` (S05-R-02 to S05-R-06).

    ``None`` when no entry resolves, when the entry is not in the transaction currency (stage 05
    owns S05-R-05 conversion), or when the entry carries no value (residual, formula).
    """
    header = st.canonical.contracts[raw.contract_key].header
    book = _book(ctx, st, raw, header)
    version = None if book is None else _version(ctx, st, raw, book)
    entry = None if version is None else _entry(version, raw, header, ctx.txn_currency)
    if version is None or entry is None or entry.currency != ctx.txn_currency:
        return None
    values = _extended(entry, raw)
    return None if values is None else SspValues(version.version_key, entry, *values)


def point_ssp(ctx: BookContext, st: IdentifiedState, raw: RawLine) -> Fraction | None:
    """The point SSP at quantity, or the range midpoint (S05-R-06 with ``price = None``)."""
    values = ssp_values(ctx, st, raw)
    if values is None:
        return None
    return values.point if values.point is not None else values.mid


def _valid(component: BundleComponentInput, raw: RawLine) -> bool:
    at = raw.pricing_date
    return component.valid_from <= at and (component.valid_to is None or at < component.valid_to)


def _weights(
    ctx: BookContext,
    st: IdentifiedState,
    components: Sequence[BundleComponentInput],
    parts: Sequence[RawLine],
    findings: MutableSequence[Finding],
) -> tuple[str, list[Fraction] | None]:
    bases = {component.split_basis for component in components}
    if len(bases) != 1 or not bases <= {RELATIVE_SSP, FIXED_PERCENTAGE}:
        raise ValueError(f"{parts[0].bundle_parent_obligation_key}: components mix split_basis")
    basis = next(iter(bases))
    if basis == FIXED_PERCENTAGE:
        ratios = [component.split_ratio for component in components]
        if any(ratio is None for ratio in ratios):
            raise ValueError("fixed_percentage components need split_ratio (T-REF-21)")
        exact = [to_fraction(ratio) for ratio in ratios if ratio is not None]
        if sum(exact, Fraction(0)) != 1:
            raise ValueError("split_ratio of a bundle must sum to 1 (T-REF-21)")
        return basis, exact
    weights: list[Fraction] = []
    for part in parts:
        point = point_ssp(ctx, st, part)
        if point is None:
            detail = {
                "product_code": part.product_code,
                "rule": "S03-R-03",
                "ssp_version_label": part.ssp_version_label or "",
                "stratification": part.stratification or "",
            }
            findings.append(
                Finding("SSP_KEY_NOT_FOUND", "ERROR", part.subject_key, detail, 3, None)
            )
        else:
            weights.append(point)
    return basis, weights if len(weights) == len(parts) else None


def _split(
    ctx: BookContext,
    raw: RawLine,
    parts: Sequence[RawLine],
    basis: str,
    weights: Sequence[Fraction],
) -> list[RawLine]:
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    total = raw.stated_price * scale
    if total.denominator != 1:
        raise ValueError(f"{raw.subject_key}: the bundle price is not whole minor units")
    keys = [part.obligation_key for part in parts]
    shares = largest_remainder(total.numerator, list(weights), keys)
    split = BundleSplit(raw.obligation_key, raw.stated_price, basis, tuple(keys), tuple(weights))
    return [
        dataclasses.replace(part, stated_price=Fraction(share, scale), split=split)
        for part, share in zip(parts, shares, strict=True)
    ]


def _recorded(ctx: BookContext, raw: RawLine) -> str | None:
    """The version key recorded for the own pricing of the line's obligation (S05-R-03): every
    reader of this module prices an obligation's own line at its own pricing date."""
    try:
        basis = ctx.policies.value(
            "ssp.version_basis", contract=raw.contract_key, obligation=raw.subject_key
        )
    except ValueError:  # a stage 05 key; absent from a bundle that stage 05 never reads
        return None
    return basis.get(_RECORDED) if isinstance(basis, Mapping) else None


def _read_back(basis: object) -> bool:
    """Whether a POL-070 value is the orchestrator's read-back of recorded versions."""
    return isinstance(basis, Mapping) and any(
        member == _RECORDED or member.startswith(_RECORDED + "@") for member in basis
    )


def _book(ctx: BookContext, st: IdentifiedState, raw: RawLine, header: ContractInput) -> str | None:
    cb = st.canonical
    books = cb.ssp_books.versions
    recorded = _recorded(ctx, raw)
    if recorded is not None:  # the recorded version names its book (S05-R-02 is not run again)
        return next(
            (
                code
                for code in sorted(books)
                if any(version.version_key == recorded for version in books[code])
            ),
            None,
        )
    facts = line_facts(raw, cb.group.products.get(raw.product_code), header)
    matched = decision(st, "SSP_ASSIGNMENT", facts, raw.pricing_date, "ssp_book_code")
    if matched is not None:
        return matched[0] if matched[0] in books else None
    scoped: list[tuple[int, str]] = []
    for code in sorted(books):
        version = _version(ctx, st, raw, code)
        if version is None:
            continue
        members = (
            (version.scope_entity_code, raw.performing_entity),
            (version.scope_currency, header.transaction_currency),
            (version.scope_channel, header.channel),
            (version.scope_segment, None),
        )
        if all(value is None or value == fact for value, fact in members):
            scoped.append((-sum(value is not None for value, _ in members), code))
    if scoped:
        return min(scoped)[1]
    if ctx.tenant_preset == "LEGACY_PARITY" and LEGACY_SSP_BOOK in books:
        return LEGACY_SSP_BOOK
    return None


def _version(
    ctx: BookContext, st: IdentifiedState, raw: RawLine, code: str
) -> SspVersionInput | None:
    cb = st.canonical
    versions = cb.ssp_books.versions.get(code, ())
    recorded = _recorded(ctx, raw)
    if recorded is not None:
        return next((version for version in versions if version.version_key == recorded), None)
    try:
        basis = ctx.policies.value(
            "ssp.version_basis", contract=raw.contract_key, obligation=raw.subject_key
        )
        if _read_back(basis):  # records of other pricings only: resolve below the obligation
            basis = ctx.policies.value("ssp.version_basis", contract=raw.contract_key)
    except ValueError:  # a stage 05 key; absent from a bundle that stage 05 never reads
        basis = _DEFAULT_VERSION_BASIS
    if basis == "NAMED_VERSION":
        label = raw.ssp_version_label
        named = [
            v
            for v in versions
            if label is not None and label in (v.legacy_version_label, v.version_key)
        ]
        return max(named, key=lambda version: version.version_no, default=None)
    at = raw.pricing_date
    eligible = [
        version
        for version in versions
        if version.approved_at <= cb.bundle.known_at
        and (version.effective_from_date is None or version.effective_from_date <= at)
        and (version.effective_to_date is None or at <= version.effective_to_date)
    ]
    return max(eligible, key=lambda version: version.version_no, default=None)


def _entry(
    version: SspVersionInput, raw: RawLine, header: ContractInput, currency: str
) -> SspEntryInput | None:
    facts = (header.region, header.channel, None, None, None)
    stratification = raw.stratification or ""
    best: tuple[tuple[int, bool, str], SspEntryInput] | None = None
    for entry in version.entries:
        if entry.product_code != raw.product_code or entry.stratification != stratification:
            continue
        values = (entry.region, entry.channel, entry.segment, entry.deal_size_band, entry.term_band)
        if any(v is not None and v != fact for v, fact in zip(values, facts, strict=True)):
            continue
        rank = (-sum(v is not None for v in values), entry.currency != currency, entry.entry_key)
        if best is None or rank < best[0]:
            best = (rank, entry)
    return None if best is None else best[1]


_Extended = tuple[Fraction | None, Fraction | None, Fraction | None, Fraction | None]


def _extended(entry: SspEntryInput, raw: RawLine) -> _Extended | None:
    """(low, mid, high, point) at the line quantity (S05-R-06); ``None`` without any value."""
    quantity = raw.quantity
    if entry.method in ("residual", "formula"):
        return None  # residual candidates and E-47 formula carry no point (S05-R-04, S05-R-06)
    if entry.method == "legacy_range":
        price = _required(entry.unit_list_price, entry, "unit_list_price")
        discount = _required(entry.midpoint_discount_ratio, entry, "midpoint_discount_ratio")
        mid = quantity * price * (1 - discount)
        if entry.range_ratio is None:
            return None, mid, None, None
        spread = to_fraction(entry.range_ratio)
        return mid * (1 - spread), mid, mid * (1 + spread), None
    if entry.method == "cost_plus_margin" and not entry.ranges:
        cost = _required(entry.cost_basis, entry, "cost_basis")
        point = quantity * cost * (1 + _required(entry.margin_ratio, entry, "margin_ratio"))
        return None, None, None, point
    row = _band_row(entry, raw)
    if row is None:
        return None
    scale = quantity
    if entry.value_basis == "PERCENT_OF_LIST":
        scale *= _required(entry.unit_list_price, entry, "unit_list_price")

    def scaled(value: Decimal | None) -> Fraction | None:
        return None if value is None else scale * to_fraction(value)

    extended = (
        scaled(row.low_value),
        scaled(row.mid_value),
        scaled(row.high_value),
        scaled(row.point_value),
    )
    return None if all(value is None for value in extended) else extended


def _band_row(entry: SspEntryInput, raw: RawLine) -> SspRangeInput | None:
    for row in entry.ranges:
        dimension = row.band_dimension
        if dimension == "NONE":
            return row
        measure: Fraction
        if dimension == "QUANTITY":
            measure = raw.quantity
        elif dimension == "TERM_MONTHS":
            start, end = raw.line_start_date, raw.line_end_date
            if start is None or end is None:
                continue
            measure = Fraction(dates.month_ends_between(start - timedelta(1), end))
        elif dimension == "DEAL_SIZE":
            return None  # banded by the allocation basis, known at stage 05 only
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
