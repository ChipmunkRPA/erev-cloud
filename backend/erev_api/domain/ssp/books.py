"""SSP books, versions and entries (04 T-REF-28 to T-REF-31, E-47, E-49, API-R-26, §16.4, table
15.4-A ``SSP_DUPLICATE_KEY``; 03 REQ-SSP-002, REQ-SSP-003, REQ-SSP-007; ENGINE_SPEC §1.4 S01-R-05;
POLICIES §3.1, §3.4; PRD §2.6, SM-04; SCREENS §11.4; SCREENS_B RPT-20; BUILD_SPEC RFD-12).

Pure rules, copy and the version diff; ``domain.ssp.commands`` and ``domain.ssp.queries`` write and
read the rows.

Entries (T-REF-30; L2-1-Q-26, L2-1-Q-27). An entry keys on product, stratification, the optional
dimension keys region, channel, segment, deal-size band and term band, and currency: a blank
dimension key is none and a blank stratification is ``""`` (``ux_ssp_entry__key``). It carries one
E-47 method, and ``formula`` is reserved (REQ-SSP-010). A ``legacy_range`` entry names the list
price L, the midpoint discount d (0 ≤ d < 1) and the range r (r ≥ 0), and the server derives its
single ``NONE`` band: mid = L × (1 − d), low = mid × (1 − r), high = mid × (1 + r) at full precision
(S01-R-05; T-REF-31); a client band is refused. Every other entry sends 1 to 20 bands, each with a
point or a mid value per unit, or as a ratio of list price under ``PERCENT_OF_LIST`` (E-49).

Diff (REQ-SSP-007; 04 §16.4; RPT-20; L2-1-Q-28). The entries of two versions pair by key. Keys of
the version only are ``added``, keys of the other version only are ``removed``, and paired entries
whose method, basis, attributes, account, distinctness or bands differ are ``changed``, with
``mid_change_ratio`` = (after mid − before mid) ÷ before mid of the ``NONE`` band, or null when a
side has no mid value or the before value is 0.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal
from types import MappingProxyType
from typing import Any, Final, NamedTuple

from erev_api.domain.reference.products import exact_text
from erev_api.enums import SspMethod, SspValueBasis
from erev_api.problems import ProblemError
from erev_api.schemas.ssp_books import MAX_BANDS

OBJECT_BOOK: Final = "ssp_book"
OBJECT_VERSION: Final = "ssp_book_version"
OBJECT_ENTRY: Final = "ssp_entry"
OBJECT_RANGE: Final = "ssp_range"
RULE_BOOK: Final = "T-REF-28"
RULE_VERSION: Final = "T-REF-29"
RULE_ENTRY: Final = "T-REF-30"
RULE_RANGE: Final = "T-REF-31"
RULE_METHOD: Final = "E-47"
RULE_DUPLICATE_KEY: Final = "SSP_DUPLICATE_KEY"  # 04 table 15.4-A
RULE_SCOPE: Final = "DB-05"
# 04 §16.10 rev 1.110 (security ruling R-27): the scope is part of a SUBMITTED version's content.
RULE_SCOPE_UNDER_APPROVAL: Final = "REQ-PLT-014"
# T-REF-28 scope columns and, [J], the resolution mode freeze once a version is APPROVED (DB-05;
# BUILD_SPEC RFD-13), by API member.
SCOPE_MEMBERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "entity_id": "entity_code",
        "currency": "currency",
        "channel": "channel",
        "segment": "segment",
        "resolution_mode": "resolution_mode",
    }
)
EFFECTIVE_DATE: Final = "EFFECTIVE_DATE"
BY_LABEL: Final = "BY_LABEL"
BAND_NONE: Final = "NONE"
BAND_DIMENSIONS: Final = (BAND_NONE, "QUANTITY", "DEAL_SIZE", "TERM_MONTHS")
DIMENSION_KEYS: Final = ("region", "channel", "segment", "deal_size_band", "term_band")
ATTRIBUTES: Final = (
    "unit_list_price",
    "midpoint_discount_ratio",
    "range_ratio",
    "cost_basis",
    "margin_ratio",
    "observable_point",
)
BAND_VALUES: Final = (
    "band_from",
    "band_to",
    "point_value",
    "low_value",
    "mid_value",
    "high_value",
)
# NUMERIC(38,18): at most 20 integer digits (TY-02).
EXACT_LIMIT: Final = Decimal(10) ** 20
# Wide enough that no product of two NUMERIC(38,18) values is rounded before it is stored.
_WIDE: Final = Context(prec=80)

# [J] Copy the documents leave open; RPT-20 validation copy for ``against``.
CODE_TAKEN: Final = "SSP book code {code} is already used."
ENTITY_UNKNOWN: Final = "Choose an existing entity."
CURRENCY_UNKNOWN: Final = "Choose an active ISO 4217 currency."
CURRENCY_IN_USE: Final = "Entries of this book use another currency. Change those entries first."
SCOPE_FROZEN: Final = (
    "The scope of this SSP book cannot change once a version is approved. Create another book."
)
SCOPE_UNDER_APPROVAL: Final = (
    "The scope of this SSP book cannot change while a version is submitted for approval. "
    "Withdraw the version, change the scope and submit it again."
)
LABEL_TAKEN: Final = "Another version of this book uses the label {label}."
EFFECTIVE_ORDER: Final = "Effective to must be on or after effective from."
COPY_UNKNOWN: Final = "Choose a version of this SSP book to copy."
AGAINST_OTHER_BOOK: Final = "Choose a version of the same SSP book."
NOT_DRAFT: Final = "This version is no longer a draft, so it cannot change."
PRODUCT_UNKNOWN: Final = "Choose an existing product."
# D-97 (3a) / (3): a series product's entry declares its E-49 basis; a PER_INCREMENT entry declares
# its E-125 quantity unit; the entries of one product agree on that unit.
SERIES_BASIS_REQUIRED: Final = (
    "Choose the value basis of this series product's entry (AMOUNT, PER_INCREMENT or "
    "PER_BOOKED_TERM)."
)
QUANTITY_UNIT_REQUIRED: Final = (
    "Choose what the line quantity counts for a per-increment entry (SERVICE_UNITS or INCREMENTS)."
)
QUANTITY_UNIT_DISAGREES: Final = (
    "Entries of one product declare one quantity unit; entries[{index}] declares another."
)
QUANTITY_UNIT_STORED_DISAGREES: Final = (
    "Entries of this product in this SSP book declare the quantity unit {unit}."
)
QUANTITY_UNIT_STORED_CONTRADICTION: Final = (
    "Stored entries of this product in this SSP book disagree on the quantity unit ({units}); "
    "resolve them before adding or changing entries of this product."
)
QUANTITY_UNIT_NOT_APPLICABLE: Final = (
    "A quantity unit applies to a per-increment entry only. Remove it or choose PER_INCREMENT."
)
ACCOUNT_UNKNOWN: Final = "Choose an active GL account."
BOOK_CURRENCY: Final = "This SSP book holds values in {currency}."
FORMULA_RESERVED: Final = "Formula SSPs are not available yet. Choose another method."
LIST_PRICE_REQUIRED: Final = "Enter the unit list price of a legacy range entry."
DISCOUNT_REQUIRED: Final = "Enter the midpoint discount of a legacy range entry."
RANGE_REQUIRED: Final = "Enter the range (±) of a legacy range entry."
DISCOUNT_BOUNDS: Final = "Enter a midpoint discount of at least 0% and below 100%."
RANGE_NEGATIVE: Final = "Enter a range (±) of zero or more."
OBSERVABLE_NEGATIVE: Final = "Enter an observable point of zero or more."
DERIVED_TOO_LARGE: Final = "The derived high value is too large. Enter a smaller price or range."
BANDS_DERIVED: Final = (
    "The band of a legacy range entry is derived from its list price, discount and range. "
    "Leave out ranges."
)
BANDS_REQUIRED: Final = "Enter 1 to 20 bands."
BAND_VALUE_REQUIRED: Final = "Enter a point or a mid value."
BAND_ORDER: Final = "Low, mid and high must be in ascending order."
BAND_BOUNDS_NONE: Final = "A band without a band dimension has no from or to value."
BAND_FROM_REQUIRED: Final = "Enter where the band starts."
BAND_TO_ORDER: Final = "The band must end after it starts."
BAND_TWICE: Final = "Another band of this entry starts at the same value."
DUPLICATE_KEY: Final = (
    "Entry {first} already uses this product, stratification, dimension keys and currency."
)


class EntryKey(NamedTuple):
    """The T-REF-30 key of an entry within its version, with the product as its code."""

    product_code: str
    stratification: str
    region: str | None
    channel: str | None
    segment: str | None
    deal_size_band: str | None
    term_band: str | None
    currency: str


@dataclass(frozen=True, slots=True)
class BandDraft:
    """One T-REF-31 band with parsed decimals."""

    band_dimension: str
    band_from: Decimal | None
    band_to: Decimal | None
    point_value: Decimal | None
    low_value: Decimal | None
    mid_value: Decimal | None
    high_value: Decimal | None


@dataclass(frozen=True, slots=True)
class EntryDraft:
    """One entry of ``POST /ssp-book-versions/{id}/entries`` with trimmed keys and parsed decimals;
    ``ranges`` is None when the member was not sent."""

    product_code: str
    stratification: str
    region: str | None
    channel: str | None
    segment: str | None
    deal_size_band: str | None
    term_band: str | None
    currency: str
    method: str
    value_basis: str | None  # None = not sent; AMOUNT for a non-series product (D-97 (3a))
    quantity_unit: str | None  # E-125; required with PER_INCREMENT (D-97 (3))
    unit_list_price: Decimal | None
    midpoint_discount_ratio: Decimal | None
    range_ratio: Decimal | None
    cost_basis: Decimal | None
    margin_ratio: Decimal | None
    observable_point: Decimal | None
    revenue_account_code: str | None
    distinctness: str
    ranges: tuple[BandDraft, ...] | None

    @property
    def key(self) -> EntryKey:
        return EntryKey(
            self.product_code,
            self.stratification,
            self.region,
            self.channel,
            self.segment,
            self.deal_size_band,
            self.term_band,
            self.currency,
        )


def text_key(value: str | None) -> str | None:
    """A dimension key or optional free text with surrounding spaces removed; blank is none."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def decimal_or_none(value: str | None) -> Decimal | None:
    """An API-C-06 decimal string as a Decimal."""
    return None if value is None else Decimal(value)


def _error(field: str, message: str, rule_id: str = RULE_ENTRY) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def legacy_band(unit_list_price: Decimal, discount: Decimal, range_ratio: Decimal) -> BandDraft:
    """The ``NONE`` band of a ``legacy_range`` entry at full precision (S01-R-05; T-REF-31)."""
    mid = _WIDE.multiply(unit_list_price, _WIDE.subtract(Decimal(1), discount))
    return BandDraft(
        band_dimension=BAND_NONE,
        band_from=None,
        band_to=None,
        point_value=None,
        low_value=_WIDE.multiply(mid, _WIDE.subtract(Decimal(1), range_ratio)),
        mid_value=mid,
        high_value=_WIDE.multiply(mid, _WIDE.add(Decimal(1), range_ratio)),
    )


def _legacy_errors(where: str, draft: EntryDraft) -> list[ProblemError]:
    errors: list[ProblemError] = []
    for member, message in (
        ("unit_list_price", LIST_PRICE_REQUIRED),
        ("midpoint_discount_ratio", DISCOUNT_REQUIRED),
        ("range_ratio", RANGE_REQUIRED),
    ):
        if getattr(draft, member) is None:
            errors.append(_error(f"{where}.{member}", message))
    return errors


def _attribute_errors(where: str, draft: EntryDraft) -> list[ProblemError]:
    """T-REF-30 column checks in field order."""
    errors: list[ProblemError] = []
    discount = draft.midpoint_discount_ratio
    if discount is not None and not Decimal(0) <= discount < 1:
        errors.append(_error(f"{where}.midpoint_discount_ratio", DISCOUNT_BOUNDS))
    if draft.range_ratio is not None and draft.range_ratio < 0:
        errors.append(_error(f"{where}.range_ratio", RANGE_NEGATIVE))
    if draft.observable_point is not None and draft.observable_point < 0:
        errors.append(_error(f"{where}.observable_point", OBSERVABLE_NEGATIVE))
    return errors


def band_errors(where: str, bands: Sequence[BandDraft]) -> list[ProblemError]:
    """T-REF-31 findings of the bands of one entry, in band order (L2-1-Q-27)."""
    if not 1 <= len(bands) <= MAX_BANDS:
        return [_error(f"{where}.ranges", BANDS_REQUIRED, RULE_RANGE)]
    errors: list[ProblemError] = []
    starts: set[tuple[str, Decimal | None]] = set()
    for index, band in enumerate(bands):
        path = f"{where}.ranges[{index}]"
        if band.band_dimension == BAND_NONE:
            if band.band_from is not None or band.band_to is not None:
                errors.append(_error(f"{path}.band_from", BAND_BOUNDS_NONE, RULE_RANGE))
        elif band.band_from is None:
            errors.append(_error(f"{path}.band_from", BAND_FROM_REQUIRED, RULE_RANGE))
        elif band.band_to is not None and band.band_to <= band.band_from:
            errors.append(_error(f"{path}.band_to", BAND_TO_ORDER, RULE_RANGE))
        if band.point_value is None and band.mid_value is None:
            errors.append(_error(f"{path}.point_value", BAND_VALUE_REQUIRED, RULE_RANGE))
        present = [
            value
            for value in (band.low_value, band.mid_value, band.high_value)
            if value is not None
        ]
        if present != sorted(present):
            errors.append(_error(f"{path}.mid_value", BAND_ORDER, RULE_RANGE))
        start = (band.band_dimension, band.band_from)
        if start in starts:
            errors.append(_error(f"{path}.band_from", BAND_TWICE, RULE_RANGE))
        starts.add(start)
    return errors


def entry_errors(
    index: int,
    draft: EntryDraft,
    *,
    products: Collection[str],
    accounts: Collection[str],
    currencies: Collection[str],
    book_currency: str | None,
    series_products: Collection[str] = (),
) -> list[ProblemError]:
    """The findings of one entry in API-S-SspEntry field order. ``products``, ``accounts`` and
    ``currencies`` hold the visible product codes, active GL account codes and active currencies
    among the request's entries; ``series_products`` the codes whose default POB template declares
    ``series`` distinctness (D-97 (3a): their entries declare an explicit ``value_basis``)."""
    where = f"entries[{index}]"
    errors: list[ProblemError] = []
    if draft.product_code not in products:
        errors.append(_error(f"{where}.product_code", PRODUCT_UNKNOWN))
    elif draft.value_basis is None and draft.product_code in series_products:
        errors.append(_error(f"{where}.value_basis", SERIES_BASIS_REQUIRED))
    per_increment = draft.value_basis == SspValueBasis.PER_INCREMENT.value
    if per_increment and draft.quantity_unit is None:
        errors.append(_error(f"{where}.quantity_unit", QUANTITY_UNIT_REQUIRED))
    elif not per_increment and draft.quantity_unit is not None:
        errors.append(_error(f"{where}.quantity_unit", QUANTITY_UNIT_NOT_APPLICABLE))
    if draft.currency not in currencies:
        errors.append(_error(f"{where}.currency", CURRENCY_UNKNOWN))
    elif book_currency is not None and draft.currency != book_currency:
        errors.append(_error(f"{where}.currency", BOOK_CURRENCY.format(currency=book_currency)))
    if draft.method == SspMethod.FORMULA.value:
        errors.append(_error(f"{where}.method", FORMULA_RESERVED, RULE_METHOD))
    legacy = draft.method == SspMethod.LEGACY_RANGE.value
    if legacy:
        errors += _legacy_errors(where, draft)
    errors += _attribute_errors(where, draft)
    if draft.revenue_account_code is not None and draft.revenue_account_code not in accounts:
        errors.append(_error(f"{where}.revenue_account_code", ACCOUNT_UNKNOWN))
    if legacy:
        if draft.ranges is not None:
            errors.append(_error(f"{where}.ranges", BANDS_DERIVED, RULE_RANGE))
        elif not errors:
            (band,) = derived_bands(draft)
            if band.high_value is not None and abs(band.high_value) >= EXACT_LIMIT:
                errors.append(_error(f"{where}.range_ratio", DERIVED_TOO_LARGE, RULE_RANGE))
    elif draft.method != SspMethod.FORMULA.value:
        errors += band_errors(where, draft.ranges or ())
    return errors


def derived_bands(draft: EntryDraft) -> tuple[BandDraft, ...]:
    """The bands to store: the derived ``NONE`` band of a valid ``legacy_range`` entry, otherwise
    the bands sent."""
    if draft.method == SspMethod.LEGACY_RANGE.value:
        if (
            draft.unit_list_price is None
            or draft.midpoint_discount_ratio is None
            or draft.range_ratio is None
        ):
            return ()
        return (
            legacy_band(draft.unit_list_price, draft.midpoint_discount_ratio, draft.range_ratio),
        )
    return draft.ranges or ()


def quantity_unit_errors(
    drafts: Sequence[EntryDraft], stored: Mapping[str, Collection[str]] | None = None
) -> list[ProblemError]:
    """D-97 (3): all dated entries of one product in one SSP book agree on ``quantity_unit`` —
    ``stored`` maps product codes to the units the book's retained stored entries declare; a
    request entry of a product whose stored rows already contradict each other is refused (naming
    every stored unit; the rows are neither discarded nor reinterpreted), and a request entry
    declaring another unit than the book or than an earlier request entry is refused at its
    ``quantity_unit``. An earlier entry is never reinterpreted by a later declaration."""
    contradictions: dict[str, str] = {}
    declared: dict[str, str] = {}
    for code, units in (stored or {}).items():
        found = sorted(set(units))
        if len(found) > 1:
            contradictions[code] = ", ".join(found)
        elif found:
            declared[code] = found[0]
    errors: list[ProblemError] = []
    for index, draft in enumerate(drafts):
        if draft.product_code in contradictions:
            errors.append(
                _error(
                    f"entries[{index}].quantity_unit",
                    QUANTITY_UNIT_STORED_CONTRADICTION.format(
                        units=contradictions[draft.product_code]
                    ),
                )
            )
            continue
        if draft.quantity_unit is None:
            continue
        seen = declared.setdefault(draft.product_code, draft.quantity_unit)
        if seen != draft.quantity_unit:
            message = (
                QUANTITY_UNIT_STORED_DISAGREES.format(unit=seen)
                if stored is not None and draft.product_code in stored
                else QUANTITY_UNIT_DISAGREES.format(index=index)
            )
            errors.append(_error(f"entries[{index}].quantity_unit", message))
    return errors


def duplicate_key_errors(drafts: Sequence[EntryDraft]) -> list[ProblemError]:
    """``SSP_DUPLICATE_KEY`` for each entry repeating the key of an earlier entry of the request
    (04 table 15.4-A; REQ-SSP-003; L2-1-Q-26)."""
    first: dict[EntryKey, int] = {}
    errors: list[ProblemError] = []
    for index, draft in enumerate(drafts):
        if draft.key in first:
            message = DUPLICATE_KEY.format(first=first[draft.key] + 1)
            errors.append(_error(f"entries[{index}]", message, RULE_DUPLICATE_KEY))
        else:
            first[draft.key] = index
    return errors


def key_of(entry: Mapping[str, Any]) -> EntryKey:
    """The key of an API-S-SspEntry item."""
    return EntryKey(
        str(entry["product_code"]),
        str(entry["stratification"]),
        entry["region"],
        entry["channel"],
        entry["segment"],
        entry["deal_size_band"],
        entry["term_band"],
        str(entry["currency"]),
    )


def _sort_key(key: EntryKey) -> tuple[str, ...]:
    return tuple("" if value is None else value for value in key)


def _content(entry: Mapping[str, Any]) -> dict[str, Any]:
    """An entry's content: every member but its id (decimals are canonical API-C-06 text)."""
    return {name: value for name, value in entry.items() if name != "id"}


def none_band_mid(entry: Mapping[str, Any]) -> Decimal | None:
    """The mid value of the entry's ``NONE`` band, or None."""
    for band in entry["ranges"]:
        if band["band_dimension"] == BAND_NONE:
            return decimal_or_none(band["mid_value"])
    return None


def mid_change_ratio(before: Mapping[str, Any], after: Mapping[str, Any]) -> str | None:
    """(after mid − before mid) ÷ before mid of the ``NONE`` bands; null when a side has no mid
    value or the before value is 0 (04 §16.4)."""
    old, new = none_band_mid(before), none_band_mid(after)
    if old is None or new is None or old == 0:
        return None
    return exact_text(_WIDE.divide(_WIDE.subtract(new, old), old).quantize(Decimal("1e-18")))


def diff(
    entries: Sequence[Mapping[str, Any]], against: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """``GET /ssp-book-versions/{id}/diff``: ``entries`` of the version against ``against``, each
    list in key order."""
    after = {key_of(entry): entry for entry in entries}
    before = {key_of(entry): entry for entry in against}
    added = [after[key] for key in sorted(after.keys() - before.keys(), key=_sort_key)]
    removed = [before[key] for key in sorted(before.keys() - after.keys(), key=_sort_key)]
    changed = [
        {
            "key": key._asdict(),
            "before": before[key],
            "after": after[key],
            "mid_change_ratio": mid_change_ratio(before[key], after[key]),
        }
        for key in sorted(after.keys() & before.keys(), key=_sort_key)
        if _content(before[key]) != _content(after[key])
    ]
    return {"added": added, "removed": removed, "changed": changed}
