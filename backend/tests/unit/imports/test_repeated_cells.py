"""A cell that the rows of one object repeat is blank or equal to the first row's — item
IMPORT-HEADER-CELL-CONFLICT-1 (the supervisor's ruling of 2026-10-02; 05 IPL-05 rev 1.210; 04
table 15.4-B ``HEADER_VALUE_CONFLICT``, §16.6 rev 1.310; PRD IMP-147), the pure rule and the
census behind it.

A CSV v2 file carries the header members of an object on each of its rows (04 NC-19), and the
emitter reads them from the object's FIRST row; two templates carry the members of a line the
same way (``invoices``: the rows of one line id, one tax line a row; ``ssp_values``: the band rows
of one entry). A later row that stated another value stated what the import did not store, and
nothing said so. ``validate.repeated_conflicts`` refuses such a cell on the later row. Here:

- the census: no column of a template that makes one object of several rows stands outside its
  key, its repeated cells and the cells a row states for itself — a column added to a command's
  model cannot escape the rule unseen — and ``plans`` groups by the declared key;
- the rule over ``validate_sheet``: typed equality, the blank cell, the first row that is blank,
  the cell with a finding of its own, the row that names no object, the sentence.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from erev_api.domain.imports import csv_v2, parse, templates, validate
from erev_api.domain.imports.csv_v2.framework import LINES, CsvRow, CsvTemplate, Repeated

CODE = validate.HEADER_CONFLICT
GROUPED = sorted(code for code, template in csv_v2.TEMPLATES.items() if template.group_key)
SINGLE = sorted(code for code, template in csv_v2.TEMPLATES.items() if not template.group_key)
# 04 §16.6 "Repeated cells": the objects and their keys, and the key of a line within its object.
KEYS: Mapping[str, tuple[str, ...]] = {
    "account_mapping": ("name",),
    "bundles": ("product_code",),
    "contracts": ("external_id",),
    "estimates": ("contract", "element_code", "effective_date"),
    "fx_rates": ("fx_rate_set_code", "coverage_from", "coverage_to"),
    "invoices": ("contract", "document_kind", "invoice_number"),
    "ssp_values": ("ssp_book_code", "legacy_version_label", "effective_from_date"),
}
LINE_KEYS: Mapping[str, tuple[str, ...]] = {
    "invoices": ("lines.line_external_id",),
    "ssp_values": (
        "lines.product_code",
        "lines.stratification",
        "lines.region",
        "lines.channel",
        "lines.segment",
        "lines.deal_size_band",
        "lines.term_band",
        "lines.currency",
        "lines.method",
    ),
}
# The cells of a line that each row states for ITSELF where the rows of one line repeat the
# others: a tax line of an invoice line; a band of an SSP entry, and the entry's two declarations,
# which ``ssp_declarations`` rules with a code of their own (SSP_ENTRY_DECLARATION_DISAGREES).
OWN: Mapping[str, tuple[str, ...]] = {
    "invoices": (
        "lines.tax_lines.tax_type",
        "lines.tax_lines.jurisdiction",
        "lines.tax_lines.amount.amount",
        "lines.tax_lines.amount.currency",
        "lines.tax_lines.principal_or_agent",
    ),
    "ssp_values": (
        "lines.value_basis",
        "lines.quantity_unit",
        "lines.ranges.band_dimension",
        "lines.ranges.band_from",
        "lines.ranges.band_to",
        "lines.ranges.point_value",
        "lines.ranges.low_value",
        "lines.ranges.mid_value",
        "lines.ranges.high_value",
    ),
}


def _levels(template: CsvTemplate) -> tuple[Repeated | None, Repeated | None]:
    """(the object's repeat, the line's repeat) of a template; a repeat is a line's when its key
    is longer than the object's."""
    of_object = [item for item in template.repeats if item.key == template.group_key]
    of_line = [item for item in template.repeats if item.key != template.group_key]
    assert len(of_object) <= 1 and len(of_line) <= 1, template.code
    return (of_object[0] if of_object else None, of_line[0] if of_line else None)


def test_the_census_seven_templates_make_one_object_of_several_rows() -> None:
    """The fourteen CSV v2 templates: seven group rows into an object, each by the key the data
    model names for it, and seven do not."""
    assert {code: csv_v2.TEMPLATES[code].group_key for code in GROUPED} == KEYS
    assert SINGLE == [
        "cost_events",
        "customers",
        "gl_accounts",
        "pre_standard_revenue",
        "products",
        "progress_events",
        "usage",
    ]
    # five of the seven have a header cell outside their key; two repeat a line's cells too
    assert sorted(code for code in GROUPED if _levels(csv_v2.TEMPLATES[code])[0]) == [
        "account_mapping",
        "contracts",
        "estimates",
        "invoices",
        "ssp_values",
    ]
    assert sorted(code for code in GROUPED if _levels(csv_v2.TEMPLATES[code])[1]) == sorted(OWN)


@pytest.mark.parametrize("code", GROUPED)
def test_no_column_of_a_grouped_template_stands_outside_the_rule(code: str) -> None:
    """Every header column is of the object's key or one of its repeated cells; where the rows
    of one line repeat cells, every column of a line is of the line's key, a repeated cell or
    one the row states for itself (``OWN``, pinned here: a column added to the command's model
    turns this red until somebody says which it is). In the other templates every row is a line
    of its own."""
    template = csv_v2.TEMPLATES[code]
    names = [column.name for column in template.columns]
    header = [name for name in names if not name.startswith(f"{LINES}.")]
    lines = [name for name in names if name.startswith(f"{LINES}.")]
    of_object, of_line = _levels(template)
    assert set(template.group_key) <= set(header)
    repeated = () if of_object is None else of_object.cells
    assert sorted(header) == sorted((*template.group_key, *repeated))
    for repeat in template.repeats:
        assert set(repeat.named_by) <= set(repeat.key) and repeat.group
    if of_line is None:
        assert code not in OWN and code not in LINE_KEYS
        return
    assert of_line.key == (*template.group_key, *LINE_KEYS[code])
    assert sorted(lines) == sorted((*LINE_KEYS[code], *of_line.cells, *OWN[code]))


@pytest.mark.parametrize("code", GROUPED)
def test_every_key_holds_a_required_column(code: str) -> None:
    """A row that leaves a required key cell blank names no object, so a row without cells names
    none and the rule needs no word about blank rows; a key of optional columns alone would make
    one object of every row that leaves them blank."""
    template = csv_v2.TEMPLATES[code]
    required = {column.name for column in template.columns if column.required}
    assert required & set(template.group_key)
    for repeat in template.repeats:
        assert required & set(repeat.key), repeat.group


def _row(number: int, values: Mapping[str, Any]) -> CsvRow:
    return CsvRow(
        id=uuid.UUID(int=number),
        sheet_name="Sheet1",
        row_number=number,
        raw=dict(values),
        normalized=dict(values),
        business_key=None,
    )


@pytest.mark.parametrize("code", GROUPED)
def test_plans_group_by_the_declared_key(code: str) -> None:
    """``plans`` and the rule read ONE key: rows that agree in every key cell make one plan
    whatever else they state, and rows that differ in one key cell make two."""
    template = csv_v2.TEMPLATES[code]
    base = {column.name: "x" for column in template.columns}
    other = {name: "y" for name in base if name not in template.group_key}
    (plan,) = template.plans([_row(2, base), _row(3, {**base, **other})])
    assert [row.row_number for row in plan.rows] == [2, 3]
    for name in template.group_key:
        plans = template.plans([_row(2, base), _row(3, {**base, name: "z"})])
        assert [[row.row_number for row in plan.rows] for plan in plans] == [[2], [3]], name


@pytest.mark.parametrize("code", SINGLE)
def test_a_template_without_a_key_makes_one_object_of_each_row(code: str) -> None:
    template = csv_v2.TEMPLATES[code]
    assert template.repeats == ()
    base = {column.name: "x" for column in template.columns}
    plans = template.plans([_row(2, base), _row(3, base)])
    assert [[row.row_number for row in plan.rows] for plan in plans] == [[2], [3]]


# --- the rule ------------------------------------------------------------------------------------


def _template(code: str) -> templates.Template:
    """The ``import_template`` row of a CSV v2 template as revision 0044 seeds it."""
    return templates.Template(
        code=code,
        version=1,
        name=code,
        family="CSV_V2",
        target_object="x",
        file_format="CSV",
        sheet_rule="FIRST",
        header_match="ALIASES",
        headers=(),
        required_parameters=(),
        row_model=code,
        aggregation_rule=None,
        is_current=True,
    )


def _validated(code: str, rows: Sequence[Mapping[str, str]]) -> validate.Validation:
    names = [column.name for column in csv_v2.TEMPLATES[code].columns]
    sheet = parse.SheetRows(
        sheet_name="Sheet1",
        headers=tuple(names),
        rows=tuple(
            (number, tuple(row.get(name, "") for name in names))
            for number, row in enumerate(rows, start=2)
        ),
        formula_cells=frozenset(),
    )
    return validate.validate_sheet(_template(code), sheet)


def _found(validation: validate.Validation) -> list[tuple[int, str, str | None]]:
    return [
        (row.row_number, finding.code, finding.column)
        for row in validation.rows
        for finding in row.findings
    ]


def _message(validation: validate.Validation, number: int, column: str) -> str:
    (row,) = [item for item in validation.rows if item.row_number == number]
    (finding,) = [item for item in row.findings if item.column == column]
    return finding.message


def _rule(name: str, role: str, **cells: str) -> dict[str, str]:
    return {
        "name": name,
        "effective_from": "2026-07-01T00:00:00Z",
        "lines.account_role": role,
        "lines.gl_account_id": str(uuid.UUID(int=7)),
        "lines.priority": "10",
        **cells,
    }


def test_an_equal_or_a_blank_later_cell_is_no_finding() -> None:
    """The boundary: the file that repeats its header cells, and the file that leaves an optional
    one blank on a later row, validate as before — every row VALID."""
    validation = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-A", "REVENUE", notes="July study"),
            _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="July study"),
            _rule("AVM-MAP-A", "CONTRACT_ASSET", notes=""),
        ],
    )
    assert _found(validation) == []
    assert [row.status.value for row in validation.rows] == ["VALID", "VALID", "VALID"]


def test_a_later_row_that_states_another_value_is_refused_at_its_column() -> None:
    """The measured case: ``effective_from`` 1 July on the first row and 1 October on the second
    made a version effective 1 July and said nothing. The later row is refused at that column;
    the first row is not; the sentence says what this row states where the first row of the
    same version states another value — both rows, both values, and no word of a header."""
    validation = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-C2", "REVENUE"),
            _rule("AVM-MAP-C2", "CONTRACT_LIABILITY", effective_from="2026-10-01T00:00:00Z"),
        ],
    )
    assert _found(validation) == [(3, CODE, "effective_from")]
    assert [row.status.value for row in validation.rows] == ["VALID", "ERROR"]
    assert _message(validation, 3, "effective_from") == (
        'This row states "2026-10-01T00:00:00Z" where row 2 of the same mapping version '
        'AVM-MAP-C2 states "2026-07-01T00:00:00Z". Repeat the value of row 2 or leave this cell '
        "blank."
    )


def test_every_later_row_is_held_to_the_first_row_of_its_own_object() -> None:
    """Rows of one object need not be neighbours, the reference is the object's FIRST row (a
    third row equal to the second and not to the first is refused), and rows of another object
    are never compared."""
    validation = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-A", "REVENUE", notes="a"),
            _rule("AVM-MAP-B", "REVENUE", notes="b", effective_from="2026-08-01T00:00:00Z"),
            _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="other"),
            _rule("AVM-MAP-A", "CONTRACT_ASSET", notes="other"),
            _rule("AVM-MAP-B", "CONTRACT_ASSET", notes="b", effective_from="2026-08-01T00:00:00Z"),
        ],
    )
    assert _found(validation) == [(4, CODE, "notes"), (5, CODE, "notes")]
    assert _message(validation, 5, "notes").startswith(
        'This row states "other" where row 2 of the same mapping version AVM-MAP-A states "a".'
    )


def test_a_value_on_a_later_row_where_the_first_row_is_blank_is_a_conflict() -> None:
    """It would not be stored either: the version is read from its first row."""
    validation = _validated(
        "account_mapping",
        [_rule("AVM-MAP-A", "REVENUE"), _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="late")],
    )
    assert _found(validation) == [(3, CODE, "notes")]
    assert _message(validation, 3, "notes") == (
        'This row states "late" where row 2 of the same mapping version AVM-MAP-A leaves the '
        "cell blank. State it on row 2 or leave this cell blank."
    )


def test_an_optional_cell_may_be_repeated_or_left_blank() -> None:
    """The sentence of an optional column offers both remedies; a required column has the one
    (the amount of an invoice line, below): row validation asks every row for it."""
    validation = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-A", "REVENUE", notes="a"),
            _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="b"),
        ],
    )
    assert _message(validation, 3, "notes") == (
        'This row states "b" where row 2 of the same mapping version AVM-MAP-A states "a". '
        "Repeat the value of row 2 or leave this cell blank."
    )


def test_a_long_value_is_quoted_by_its_beginning() -> None:
    """A rationale may run to thousands of characters: the sentence quotes the first sixty and
    an ellipsis, and a value of sixty whole."""
    whole = "r" * validate.QUOTED_LENGTH
    validation = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-A", "REVENUE", notes="a"),
            _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="r" * 400),
            _rule("AVM-MAP-A", "CONTRACT_ASSET", notes=whole),
        ],
    )
    message = _message(validation, 3, "notes")
    assert message.startswith(f'This row states "{whole}…" where') and len(message) < 300
    assert _message(validation, 4, "notes").startswith(f'This row states "{whole}" where')


def _invoice(number: str, line: str, **cells: str) -> dict[str, str]:
    return {
        "contract": "NS-SO-DE-5004",
        "document_kind": "INVOICE",
        "invoice_number": number,
        "issue_date": "2026-09-12",
        "due_date": "2026-10-12",
        "lines.line_external_id": line,
        "lines.obligation_key": "O1",
        "lines.quantity": "120",
        "lines.amount.amount": "54000.00",
        "lines.amount.currency": "EUR",
        "lines.tax_lines.tax_type": "VAT",
        "lines.tax_lines.amount.amount": "10260.00",
        "lines.tax_lines.amount.currency": "EUR",
        "lines.tax_lines.principal_or_agent": "PRINCIPAL",
        **cells,
    }


def test_equality_is_of_the_cell_as_its_column_is_typed() -> None:
    """A number as a number: 120 and 120.0, 54000.00 and 54000 are one value and no finding. A
    date as a date: a CSV date is ISO alone, so the one other spelling of a day is the same text
    beside a space. Text exactly: another spelling is another value."""
    equal = _validated(
        "invoices",
        [
            _invoice("INV-1", "1"),
            _invoice(
                "INV-1",
                "1",
                **{
                    "due_date": " 2026-10-12",
                    "lines.quantity": "120.0",
                    "lines.amount.amount": "54000",
                    "lines.tax_lines.tax_type": "CITY",
                },
            ),
        ],
    )
    assert _found(equal) == []
    spelled = _validated(
        "invoices",
        [_invoice("INV-1", "1"), _invoice("INV-1", "2", **{"lines.amount.currency": "eur"})],
    )
    # another LINE of the document: its own amount and currency are its own; the document's
    # header cells are held to the first row
    assert _found(spelled) == []
    text = _validated(
        "invoices",
        [_invoice("INV-1", "1", reason="Damaged"), _invoice("INV-1", "2", reason="damaged")],
    )
    assert _found(text) == [(3, CODE, "reason")]


def test_the_rows_of_one_line_repeat_the_lines_cells() -> None:
    """``invoices``: the rows of one line id are one line and add a tax line each; the line's
    amount was read from the line's first row. A later row of the SAME line that states another
    amount is refused at the amount; its own tax line is its own."""
    validation = _validated(
        "invoices",
        [
            _invoice("INV-1", "1"),
            _invoice(
                "INV-1",
                "1",
                **{
                    "lines.amount.amount": "60000.00",
                    "lines.tax_lines.tax_type": "CITY",
                    "lines.tax_lines.amount.amount": "540.00",
                },
            ),
            _invoice("INV-1", "2", **{"lines.amount.amount": "60000.00"}),
        ],
    )
    assert _found(validation) == [(3, CODE, "lines.amount.amount")]
    assert _message(validation, 3, "lines.amount.amount") == (
        'This row states "60000.00" where row 2 of the same document line INV-1 / 1 states '
        '"54000.00". Repeat the value of row 2.'
    )


def test_a_documents_header_cells_are_held_to_its_first_row() -> None:
    validation = _validated(
        "invoices",
        [
            _invoice("INV-1", "1"),
            _invoice("INV-1", "2", due_date="2026-11-12"),
            _invoice("INV-2", "1", due_date="2026-11-12"),
        ],
    )
    assert _found(validation) == [(3, CODE, "due_date")]
    assert "where row 2 of the same document INV-1 states" in _message(validation, 3, "due_date")


def test_a_cell_with_a_finding_of_its_own_is_left_to_it() -> None:
    """A later cell that is no date is DATE_INVALID and nothing more; a first row whose cell is
    no date carries that finding, and the later rows are not held to it; a blank REQUIRED cell
    is REQUIRED_VALUE_BLANK as before, on a later row and on the first — the later rows are not
    held to a first row that states nothing where it must."""
    later = _validated(
        "invoices", [_invoice("INV-1", "1"), _invoice("INV-1", "2", due_date="first of July")]
    )
    assert _found(later) == [(3, "DATE_INVALID", "due_date")]
    first = _validated(
        "invoices", [_invoice("INV-1", "1", due_date="first of July"), _invoice("INV-1", "2")]
    )
    assert _found(first) == [(2, "DATE_INVALID", "due_date")]
    blank = _validated("invoices", [_invoice("INV-1", "1"), _invoice("INV-1", "2", issue_date="")])
    assert _found(blank) == [(3, "REQUIRED_VALUE_BLANK", "issue_date")]
    blank_first = _validated(
        "invoices", [_invoice("INV-1", "1", issue_date=""), _invoice("INV-1", "2")]
    )
    assert _found(blank_first) == [(2, "REQUIRED_VALUE_BLANK", "issue_date")]


def _entry(product: str, **cells: str) -> dict[str, str]:
    return {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": "H-1",
        "methodology_label": "Q3 list-price study",
        "lines.product_code": product,
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.value_basis": "AMOUNT",
        "lines.unit_list_price": "1000.00",
        "lines.distinctness": "distinct",
        "lines.ranges.band_dimension": "QUANTITY",
        "lines.ranges.band_from": "0",
        "lines.ranges.band_to": "100",
        "lines.ranges.point_value": "1000.00",
        **cells,
    }


def test_a_row_that_names_no_object_is_not_compared() -> None:
    """A row without its key, or whose key cell is not of its type, carries that finding and
    belongs to no object: nothing is compared with it. A row without cells is no row."""
    validation = _validated(
        "invoices",
        [
            _invoice("", "1", due_date="2026-10-12"),
            _invoice("", "1", due_date="2026-11-12"),
        ],
    )
    assert _found(validation) == [
        (2, "REQUIRED_VALUE_BLANK", "invoice_number"),
        (3, "REQUIRED_VALUE_BLANK", "invoice_number"),
    ]
    # an OPTIONAL cell of the key that is no date: the row is not of the version whose rows leave
    # that cell blank
    untyped = _validated(
        "ssp_values",
        [
            _entry("PLAT-100"),
            _entry("IMPL-PLUS", effective_from_date="first of July", methodology_label="Q4 study"),
        ],
    )
    assert _found(untyped) == [(3, "DATE_INVALID", "effective_from_date")]
    between = _validated(
        "account_mapping",
        [
            _rule("AVM-MAP-A", "REVENUE", notes="a"),
            {},
            _rule("AVM-MAP-A", "CONTRACT_LIABILITY", notes="b"),
        ],
    )
    assert [row.status.value for row in between.rows] == ["VALID", "BLANK", "ERROR"]
    assert _found(between) == [(4, CODE, "notes")]


def test_the_band_rows_of_one_entry_repeat_the_entrys_cells() -> None:
    """``ssp_values``: the band rows of one entry key are one entry, read from the entry's first
    row. A later band row that states another list price is refused there; its band is its own,
    and the entry's two declarations are left to their own rule and sentence
    (SSP_ENTRY_DECLARATION_DISAGREES, a cross rule). A member the template carries as text is
    compared as its text: 1000.00 and 1000 are two values there (04 §16.6)."""
    band = {"lines.ranges.band_from": "100", "lines.ranges.band_to": "500"}
    validation = _validated(
        "ssp_values",
        [
            _entry("PLAT-100"),
            _entry("PLAT-100", **band, **{"lines.ranges.point_value": "900.00"}),
            _entry("PLAT-100", **band, **{"lines.unit_list_price": "1200.00"}),
            _entry("PLAT-100", **band, **{"lines.value_basis": "PER_INCREMENT"}),
            _entry("PLAT-100", **band, **{"lines.unit_list_price": "1000"}),
            _entry("IMPL-PLUS", **{"lines.unit_list_price": "1200.00"}),
        ],
    )
    assert _found(validation) == [
        (4, CODE, "lines.unit_list_price"),
        (6, CODE, "lines.unit_list_price"),
    ]
    assert _message(validation, 4, "lines.unit_list_price") == (
        'This row states "1200.00" where row 2 of the same SSP entry PLAT-100 states "1000.00". '
        "Repeat the value of row 2 or leave this cell blank."
    )


def test_the_rule_reads_csv_v2_templates_alone() -> None:
    """A legacy template has no emitter of this registry and a template without a key repeats
    nothing: the rule answers nothing for either."""
    empty = validate.Validation("Sheet1", (), (), 0)
    assert validate.repeated_conflicts(_template("legacy_contract_setup"), empty) == {}
    assert validate.repeated_conflicts(_template("customers"), empty) == {}
