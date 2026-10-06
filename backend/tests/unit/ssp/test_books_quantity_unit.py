"""D-97 (3) / (3a) admission rules of ``erev_api.domain.ssp.books`` over a synthetic store (no
database): a ``series`` product's entry declares its E-49 basis; a ``PER_INCREMENT`` entry declares
E-125 ``quantity_unit`` and no other basis carries one; all dated entries of one product identity
within one book agree on the unit — the request's entries against each other and against the
book's STORED entries (Codex admission control at 1434d07: a stored region=US INCREMENTS entry
and a request carrying a valid region=EU SERVICE_UNITS entry is refused at admission; the engine's
later CV-45 rejection does not establish prevention here). The DB-backed evidence is
``tests/domain/ssp/test_ssp_books.py::test_d97_3_*`` in the gate chain.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from erev_api.domain.ssp import books

PRODUCTS = frozenset({"AVM-SER", "AVM-GOOD"})
CURRENCIES = frozenset({"USD"})


def draft(
    product_code: str,
    *,
    value_basis: str | None = None,
    quantity_unit: str | None = None,
    region: str | None = None,
) -> books.EntryDraft:
    return books.EntryDraft(
        product_code=product_code,
        stratification="",
        region=region,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method="observable",
        value_basis=value_basis,
        quantity_unit=quantity_unit,
        unit_list_price=None,
        midpoint_discount_ratio=None,
        range_ratio=None,
        cost_basis=None,
        margin_ratio=None,
        observable_point=None,
        revenue_account_code=None,
        distinctness="distinct",
        ranges=(
            books.BandDraft(
                band_dimension=books.BAND_NONE,
                band_from=None,
                band_to=None,
                point_value=Decimal("110.00"),
                low_value=None,
                mid_value=None,
                high_value=None,
            ),
        ),
    )


def errors_of(
    item: books.EntryDraft, *, series: frozenset[str] = frozenset({"AVM-SER"})
) -> list[str]:
    found = books.entry_errors(
        0,
        item,
        products=PRODUCTS,
        accounts=frozenset(),
        currencies=CURRENCIES,
        book_currency=None,
        series_products=series,
    )
    return [f"{error.field}: {error.message}" for error in found]


def test_d97_3a_series_product_entry_declares_its_basis() -> None:
    assert errors_of(draft("AVM-SER")) == [f"entries[0].value_basis: {books.SERIES_BASIS_REQUIRED}"]
    assert errors_of(draft("AVM-SER", value_basis="AMOUNT")) == []
    # A non-series product keeps the T-REF-30 default: an omitted basis is not a finding.
    assert errors_of(draft("AVM-GOOD")) == []
    assert errors_of(draft("AVM-GOOD", value_basis="PERCENT_OF_LIST")) == []


def test_d97_3_per_increment_entry_declares_its_quantity_unit_and_no_other_basis_does() -> None:
    assert errors_of(draft("AVM-SER", value_basis="PER_INCREMENT")) == [
        f"entries[0].quantity_unit: {books.QUANTITY_UNIT_REQUIRED}"
    ]
    for unit in ("SERVICE_UNITS", "INCREMENTS"):
        assert errors_of(draft("AVM-SER", value_basis="PER_INCREMENT", quantity_unit=unit)) == []
    for basis in ("AMOUNT", "PER_BOOKED_TERM", "PERCENT_OF_LIST"):
        assert errors_of(draft("AVM-SER", value_basis=basis, quantity_unit="INCREMENTS")) == [
            f"entries[0].quantity_unit: {books.QUANTITY_UNIT_NOT_APPLICABLE}"
        ]
    # ... also for a non-series product: the unit is meaningful for PER_INCREMENT only.
    assert errors_of(draft("AVM-GOOD", quantity_unit="SERVICE_UNITS")) == [
        f"entries[0].quantity_unit: {books.QUANTITY_UNIT_NOT_APPLICABLE}"
    ]


def _per_increment(region: str | None, unit: str) -> books.EntryDraft:
    return draft("AVM-SER", value_basis="PER_INCREMENT", quantity_unit=unit, region=region)


def test_d97_3_request_entries_of_one_product_agree() -> None:
    same = [_per_increment("US", "INCREMENTS"), _per_increment("EU", "INCREMENTS")]
    assert books.quantity_unit_errors(same) == []
    mixed = [_per_increment("US", "INCREMENTS"), _per_increment("EU", "SERVICE_UNITS")]
    (error,) = books.quantity_unit_errors(mixed)
    assert (error.field, error.message) == (
        "entries[1].quantity_unit",
        books.QUANTITY_UNIT_DISAGREES.format(index=1),
    )
    # Another product's unit is not a disagreement.
    other = [
        _per_increment("US", "INCREMENTS"),
        dataclasses.replace(_per_increment("US", "SERVICE_UNITS"), product_code="AVM-GOOD"),
    ]
    assert books.quantity_unit_errors(other) == []


def test_d97_3_stored_versus_request_disagreement_is_refused_at_admission() -> None:
    # The store holds a region=US INCREMENTS entry of AVM-SER; the request carries a valid
    # region=EU SERVICE_UNITS entry — consistent on its own, refused against the store.
    stored = {"AVM-SER": {"INCREMENTS"}}
    (error,) = books.quantity_unit_errors([_per_increment("EU", "SERVICE_UNITS")], stored)
    assert (error.field, error.message) == (
        "entries[0].quantity_unit",
        books.QUANTITY_UNIT_STORED_DISAGREES.format(unit="INCREMENTS"),
    )
    # The same unit as the store, and an unrelated product, are admitted.
    assert books.quantity_unit_errors([_per_increment("EU", "INCREMENTS")], stored) == []
    assert (
        books.quantity_unit_errors(
            [dataclasses.replace(_per_increment("EU", "SERVICE_UNITS"), product_code="AVM-GOOD")],
            stored,
        )
        == []
    )
    # A stored declaration wins over a later request entry: the earlier entry is never
    # reinterpreted, and the first request entry that departs from the store is the one refused.
    two = [_per_increment("EU", "SERVICE_UNITS"), _per_increment("APAC", "SERVICE_UNITS")]
    assert [error.field for error in books.quantity_unit_errors(two, stored)] == [
        "entries[0].quantity_unit",
        "entries[1].quantity_unit",
    ]


def test_d97_3_contradictory_stored_population_is_refused_before_writing() -> None:
    # Codex 8/9 supplemental: the retained stored rows of AVM-SER already disagree (INCREMENTS in
    # one dated version, SERVICE_UNITS in another). No first row is silently authoritative: every
    # request entry of that product is refused before anything is written, naming both units, and
    # the historical rows are neither discarded nor reinterpreted; another product is unaffected.
    stored = {"AVM-SER": {"SERVICE_UNITS", "INCREMENTS"}, "AVM-GOOD": {"INCREMENTS"}}
    for unit in ("INCREMENTS", "SERVICE_UNITS"):
        (error,) = books.quantity_unit_errors([_per_increment("EU", unit)], stored)
        assert (error.field, error.message) == (
            "entries[0].quantity_unit",
            books.QUANTITY_UNIT_STORED_CONTRADICTION.format(units="INCREMENTS, SERVICE_UNITS"),
        )
    # ... even for a request entry that declares no unit of its own (an AMOUNT entry of that
    # product).
    (error,) = books.quantity_unit_errors([draft("AVM-SER", value_basis="AMOUNT")], stored)
    assert error.field == "entries[0].quantity_unit"
    good = dataclasses.replace(_per_increment("EU", "INCREMENTS"), product_code="AVM-GOOD")
    assert books.quantity_unit_errors([good], stored) == []
