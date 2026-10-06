"""``csv_v2.ssp_declarations`` over synthetic rows (no database): the import channel refuses the
T-REF-30 declarations exactly as API-S-SspEntry does (04 rev 1.19 table 15.4-A; D-97 (3), (3a)),
relocated to the row and column, and the schema bridge to ENG-C1b behaves as documented. The
DB-backed evidence is ``tests/domain/imports/csv_v2/test_ssp_values_declarations.py``."""

from __future__ import annotations

from collections.abc import Collection, Mapping

import pytest
from erev_api.domain.imports.csv_v2 import ssp_declarations as d
from erev_api.domain.imports.csv_v2.ssp_values import SspEntryRowIn, _declared

SERIES = frozenset({"AVM-SER"})


def row(
    number: int,
    product: str,
    basis: str | None = None,
    unit: str | None = None,
    region: str | None = None,
) -> tuple[int, dict[str, str]]:
    values = {
        "ssp_book_code": "US-LIST",
        "lines.product_code": product,
        "lines.region": region or "",
        "lines.value_basis": basis or "",
        "lines.quantity_unit": unit or "",
    }
    return number, values


def refusals(
    *rows: tuple[int, Mapping[str, str]],
    series: Collection[str] = SERIES,
    stored: Mapping[str, Collection[str]] | None = None,
) -> dict[int, list[tuple[str, str, str]]]:
    found = d.declaration_findings(d.declarations_of(list(rows)), series=series, stored=stored)
    return {
        number: [(item.code, item.column or "", item.message) for item in items]
        for number, items in found.items()
    }


def test_series_row_without_a_basis_is_refused_and_a_non_series_row_keeps_the_default() -> None:
    assert refusals(row(2, "AVM-SER"), row(3, "AVM-GOOD")) == {
        2: [
            (
                "SSP_VALUE_BASIS_REQUIRED",
                "lines.value_basis",
                f"Row 2, column Lines value basis: {d.SERIES_BASIS_REQUIRED} "
                "(SSP_VALUE_BASIS_REQUIRED)",
            )
        ]
    }
    for basis in ("AMOUNT", "PER_BOOKED_TERM", "PERCENT_OF_LIST"):
        assert refusals(row(2, "AVM-SER", basis)) == {}
    assert refusals(row(2, "AVM-GOOD", "PERCENT_OF_LIST")) == {}


def test_values_outside_the_vocabularies_are_refused_at_their_columns() -> None:
    found = refusals(row(4, "AVM-GOOD", "PER_UNIT"), row(5, "AVM-SER", "PER_INCREMENT", "SEATS"))
    assert found[4][0][:2] == ("SSP_VALUE_BASIS_REQUIRED", "lines.value_basis")
    assert "PER_UNIT is not a value basis" in found[4][0][2]
    assert found[5][0][:2] == ("SSP_QUANTITY_UNIT_REQUIRED", "lines.quantity_unit")
    assert "SEATS is not a quantity unit" in found[5][0][2]


def test_per_increment_declares_its_unit_and_no_other_basis_carries_one() -> None:
    assert refusals(row(2, "AVM-SER", "PER_INCREMENT")) == {
        2: [
            (
                "SSP_QUANTITY_UNIT_REQUIRED",
                "lines.quantity_unit",
                f"Row 2, column Lines quantity unit: {d.QUANTITY_UNIT_REQUIRED} "
                "(SSP_QUANTITY_UNIT_REQUIRED)",
            )
        ]
    }
    for unit in ("SERVICE_UNITS", "INCREMENTS"):
        assert refusals(row(2, "AVM-SER", "PER_INCREMENT", unit)) == {}
    for basis in ("AMOUNT", "PER_BOOKED_TERM", "PERCENT_OF_LIST"):
        assert [item[0] for item in refusals(row(2, "AVM-SER", basis, "INCREMENTS"))[2]] == [
            "SSP_QUANTITY_UNIT_NOT_APPLICABLE"
        ]
    # ... also for a non-series product with the omitted (defaulted) basis.
    assert [item[0] for item in refusals(row(2, "AVM-GOOD", None, "SERVICE_UNITS"))[2]] == [
        "SSP_QUANTITY_UNIT_NOT_APPLICABLE"
    ]


def test_rows_of_one_product_agree_on_the_unit_and_the_later_row_is_the_one_refused() -> None:
    # Two ENTRIES of one product (distinct regions, as C1b's test): the product-level agreement.
    same = refusals(
        row(2, "AVM-SER", "PER_INCREMENT", "INCREMENTS", region="US"),
        row(3, "AVM-SER", "PER_INCREMENT", "INCREMENTS", region="EU"),
    )
    assert same == {}
    mixed = refusals(
        row(2, "AVM-SER", "PER_INCREMENT", "INCREMENTS", region="US"),
        row(3, "AVM-SER", "PER_INCREMENT", "SERVICE_UNITS", region="EU"),
        row(4, "AVM-GOOD", "PER_INCREMENT", "SERVICE_UNITS"),  # another product: no disagreement
    )
    assert list(mixed) == [3]
    assert mixed[3] == [
        (
            "SSP_QUANTITY_UNIT_DISAGREES",
            "lines.quantity_unit",
            "Row 3, column Lines quantity unit: Entries of one product declare one quantity "
            "unit; row 3 declares another. (SSP_QUANTITY_UNIT_DISAGREES)",
        )
    ]


def test_stored_entries_of_the_book_bind_the_request_and_a_contradiction_refuses_the_product() -> (
    None
):
    stored = {"AVM-SER": {"INCREMENTS"}}
    found = refusals(
        row(2, "AVM-SER", "PER_INCREMENT", "SERVICE_UNITS", region="EU"), stored=stored
    )
    assert found[2] == [
        (
            "SSP_QUANTITY_UNIT_DISAGREES",
            "lines.quantity_unit",
            "Row 2, column Lines quantity unit: Entries of this product in this SSP book declare "
            "the quantity unit INCREMENTS. (SSP_QUANTITY_UNIT_DISAGREES)",
        )
    ]
    assert refusals(row(2, "AVM-SER", "PER_INCREMENT", "INCREMENTS"), stored=stored) == {}
    assert refusals(row(2, "AVM-GOOD", "PER_INCREMENT", "SERVICE_UNITS"), stored=stored) == {}
    contradiction = refusals(
        row(2, "AVM-SER", "PER_INCREMENT", "INCREMENTS"),
        stored={"AVM-SER": {"SERVICE_UNITS", "INCREMENTS"}},
    )
    assert contradiction[2][0][:2] == ("SSP_QUANTITY_UNIT_CONTRADICTION", "lines.quantity_unit")
    assert "disagree on the quantity unit (INCREMENTS, SERVICE_UNITS)" in contradiction[2][0][2]


def test_messages_are_the_api_messages_of_eng_c1b() -> None:
    """The editor, the API and the import channel say the same thing (053813f books.py)."""
    assert d.SERIES_BASIS_REQUIRED.startswith(
        "Choose the value basis of this series product's entry"
    )
    assert d.QUANTITY_UNIT_REQUIRED.startswith("Choose what the line quantity counts")
    assert d.QUANTITY_UNIT_NOT_APPLICABLE.endswith("Remove it or choose PER_INCREMENT.")
    assert d.QUANTITY_UNIT_STORED_CONTRADICTION.startswith("Stored entries of this product")
    assert d.VALUE_BASES == {"AMOUNT", "PERCENT_OF_LIST", "PER_INCREMENT", "PER_BOOKED_TERM"}
    assert d.QUANTITY_UNITS == {"SERVICE_UNITS", "INCREMENTS"}


def test_schema_bridge_keeps_blank_declarations_omitted_and_forwards_only_known_members() -> None:
    """A blank cell stays omitted on the row model (the API applies its default to a non-series
    product only); the request carries ``quantity_unit`` only once API-S-SspEntry has the member."""
    line = SspEntryRowIn.model_validate(
        {
            "product_code": "AVM-SER",
            "currency": "USD",
            "method": "observable",
            "distinctness": "distinct",
            "value_basis": None,
            "quantity_unit": None,
        }
    )
    assert (line.value_basis, line.quantity_unit) == (None, None)
    members = _declared(line.model_dump(exclude={"ranges"}))
    assert "value_basis" not in members and "quantity_unit" not in members
    declared = _declared(
        {"product_code": "AVM-SER", "value_basis": "AMOUNT", "quantity_unit": "INCREMENTS"}
    )
    assert declared["value_basis"] == "AMOUNT"
    from erev_api.schemas.ssp_books import SspEntryIn

    assert ("quantity_unit" in declared) == ("quantity_unit" in SspEntryIn.model_fields)


# --- F-DIN-SSP-R1 / R2 (Codex review of ad38da3) -------------------------------------------------


def band_row(
    number: int,
    product: str,
    basis: str | None,
    unit: str | None,
    band: tuple[str, str],
) -> tuple[int, dict[str, str]]:
    """Two rows of ONE entry (L5-1-Q-22): the entry members repeated, one band per row."""
    values = {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": "2026-H2",
        "effective_from_date": "2026-07-01",
        "lines.product_code": product,
        "lines.stratification": "",
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.value_basis": basis or "",
        "lines.quantity_unit": unit or "",
        "lines.ranges.band_dimension": "QUANTITY",
        "lines.ranges.band_from": band[0],
        "lines.ranges.band_to": band[1],
    }
    return number, values


@pytest.mark.parametrize(
    ("basis", "unit"), [("PER_INCREMENT", "INCREMENTS"), ("PER_BOOKED_TERM", None)]
)
@pytest.mark.parametrize("amount_first", [True, False])
def test_r1_band_rows_of_one_entry_must_declare_alike(
    basis: str, unit: str | None, amount_first: bool
) -> None:
    """F-DIN-SSP-R1: the later band row of one entry declaring another basis (or unit) is refused
    at its column, in both orders, so the band merge never collapses declarations into the
    first row's."""
    first, second = (
        (
            band_row(2, "AVM-SER", "AMOUNT", None, ("0", "10")),
            band_row(3, "AVM-SER", basis, unit, ("10", "20")),
        )
        if amount_first
        else (
            band_row(2, "AVM-SER", basis, unit, ("0", "10")),
            band_row(3, "AVM-SER", "AMOUNT", None, ("10", "20")),
        )
    )
    found = refusals(first, second)
    assert list(found) == [3]
    codes = [item[0] for item in found[3]]
    assert "SSP_ENTRY_DECLARATION_DISAGREES" in codes
    columns = {item[1] for item in found[3] if item[0] == "SSP_ENTRY_DECLARATION_DISAGREES"}
    assert "lines.value_basis" in columns


def test_r1_matching_band_rows_still_merge_and_other_entries_are_independent() -> None:
    same = refusals(
        band_row(2, "AVM-SER", "AMOUNT", None, ("0", "10")),
        band_row(3, "AVM-SER", "AMOUNT", None, ("10", "20")),
        band_row(4, "AVM-GOOD", "PERCENT_OF_LIST", None, ("0", "5")),  # another entry
        band_row(5, "AVM-GOOD", "PERCENT_OF_LIST", None, ("5", "9")),
    )
    assert same == {}
    unit_mismatch = refusals(
        band_row(2, "AVM-SER", "PER_INCREMENT", "INCREMENTS", ("0", "10")),
        band_row(3, "AVM-SER", "PER_INCREMENT", "SERVICE_UNITS", ("10", "20")),
    )
    assert [item[0] for item in unit_mismatch[3]] and "lines.quantity_unit" in {
        item[1] for item in unit_mismatch[3]
    }


@pytest.mark.parametrize("basis", ["AMOUNT", "PER_BOOKED_TERM", "PERCENT_OF_LIST"])
def test_r2_stored_contradiction_refuses_any_row_of_that_product(basis: str) -> None:
    """F-DIN-SSP-R2: with stored units {INCREMENTS, SERVICE_UNITS} for the product, a row of any
    basis is refused (C1b's quantity_unit_errors checks the contradiction for ANY entry first)."""
    stored = {"AVM-SER": {"INCREMENTS", "SERVICE_UNITS"}}
    found = refusals(row(2, "AVM-SER", basis), stored=stored)
    assert [item[0] for item in found.get(2, [])] == ["SSP_QUANTITY_UNIT_CONTRADICTION"]
    assert refusals(row(2, "AVM-GOOD", basis), stored=stored) == {}  # another product: admitted
    assert refusals(row(2, "AVM-SER", "AMOUNT"), stored={"AVM-SER": {"INCREMENTS"}}) == {}
