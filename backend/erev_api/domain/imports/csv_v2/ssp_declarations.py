"""SSP declarations on import: the ``ssp_values`` cross rule (04 rev 1.19 T-IMP-01 paragraph and
table 15.4-A ``SSP_*`` declaration codes; D-97 (3), (3a); readiness SSP-IMPORT-DECLARATION; lane
F-DIN, prepared against lane ENG-C1b's contract at 053813f).

The import channel carries the T-REF-30 declarations ``lines.value_basis`` (E-49) and
``lines.quantity_unit`` (E-125) and refuses them exactly as API-S-SspEntry does, at validation and
as row-located findings (``ERROR``; the upload ends ``INVALID`` and nothing is written):

- a row of a product whose default POB template is ``series`` without a basis, or a basis outside
  E-49 → ``SSP_VALUE_BASIS_REQUIRED`` at ``lines.value_basis`` (a non-series product keeps the
  T-REF-30 default ``AMOUNT``);
- a ``PER_INCREMENT`` row without a unit, or a unit outside E-125 → ``SSP_QUANTITY_UNIT_REQUIRED``;
- a unit on any other basis → ``SSP_QUANTITY_UNIT_NOT_APPLICABLE``;
- rows of one product disagreeing among themselves, or with the book's retained stored entries →
  ``SSP_QUANTITY_UNIT_DISAGREES`` (naming the stored unit);
- a product whose stored entries already contradict each other → ``SSP_QUANTITY_UNIT_CONTRADICTION``
  (naming every stored unit, whatever basis the row declares — F-DIN-SSP-R2; the rows are neither
  discarded nor reinterpreted);
- band rows of ONE entry (L5-1-Q-22: the entry members repeated, one band per row) that declare a
  different basis or unit → ``SSP_ENTRY_DECLARATION_DISAGREES`` on the later row at the differing
  column (F-DIN-SSP-R1), so the band merge never collapses declarations into the first row's; the
  commit refuses defensively if it ever would (``ssp_values.apply``).

Messages are the API's (``erev_api.domain.ssp.books`` at ENG-C1b 053813f), so the editor, the API
and the import channel say the same thing. Nothing is inferred and nothing defaults on import.

Schema bridge (ENG-C1b integration barrier, recorded in ``docs/reviews/loop/prod/F-DIN-prep.md``):
main carries E-49 ``AMOUNT`` / ``PERCENT_OF_LIST`` and the ``ssp_entry.value_basis`` column; the
``PER_INCREMENT`` / ``PER_BOOKED_TERM`` values, the E-125 enum, the ``quantity_unit`` column
(migration 0056), ``products.series_product_ids`` and ``books.entry_errors(series_products=)``
arrive with C1b. Until then this module (1) validates the declared literals against the full E-49 /
E-125 vocabularies, (2) resolves the series predicate with the same query as C1b's
``series_product_ids`` and prefers C1b's function once it exists, (3) reads the book's stored
``quantity_unit`` only when the column exists, and (4) is the only place the import channel needs
to change when the API schema gains the members. The rule is pure over its inputs
(``declaration_findings``); ``cross_findings`` adds the two database reads.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import pob_template_version, product, ssp_book, ssp_book_version, ssp_entry
from erev_api.domain.imports import findings
from erev_api.domain.imports.csv_v2.framework import unflatten
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import Distinctness

__all__ = [
    "BASIS_COLUMN",
    "CODE_BASIS_REQUIRED",
    "CODE_ENTRY_DISAGREES",
    "CODE_UNIT_CONTRADICTION",
    "CODE_UNIT_DISAGREES",
    "CODE_UNIT_NOT_APPLICABLE",
    "CODE_UNIT_REQUIRED",
    "PER_INCREMENT",
    "QUANTITY_UNITS",
    "UNIT_COLUMN",
    "VALUE_BASES",
    "Declaration",
    "cross_findings",
    "declaration_findings",
    "declarations_of",
    "series_products",
    "stored_quantity_units",
]

# 04 table 15.4-A (rev 1.19)
CODE_BASIS_REQUIRED: Final = "SSP_VALUE_BASIS_REQUIRED"
CODE_UNIT_REQUIRED: Final = "SSP_QUANTITY_UNIT_REQUIRED"
CODE_UNIT_NOT_APPLICABLE: Final = "SSP_QUANTITY_UNIT_NOT_APPLICABLE"
CODE_UNIT_DISAGREES: Final = "SSP_QUANTITY_UNIT_DISAGREES"
CODE_UNIT_CONTRADICTION: Final = "SSP_QUANTITY_UNIT_CONTRADICTION"
CODE_ENTRY_DISAGREES: Final = "SSP_ENTRY_DECLARATION_DISAGREES"

# E-49 and E-125 vocabularies (04 §3.4; D-97 (3)): the two PER_* values and E-125 are ENG-C1b's.
PER_INCREMENT: Final = "PER_INCREMENT"
VALUE_BASES: Final = frozenset({"AMOUNT", "PERCENT_OF_LIST", PER_INCREMENT, "PER_BOOKED_TERM"})
QUANTITY_UNITS: Final = frozenset({"SERVICE_UNITS", "INCREMENTS"})

BASIS_COLUMN: Final = "lines.value_basis"
UNIT_COLUMN: Final = "lines.quantity_unit"
PRODUCT_COLUMN: Final = "lines.product_code"
BOOK_COLUMN: Final = "ssp_book_code"

# The API's messages (erev_api.domain.ssp.books at ENG-C1b 053813f), verbatim.
SERIES_BASIS_REQUIRED: Final = (
    "Choose the value basis of this series product's entry (AMOUNT, PER_INCREMENT or "
    "PER_BOOKED_TERM)."
)
QUANTITY_UNIT_REQUIRED: Final = (
    "Choose what the line quantity counts for a per-increment entry (SERVICE_UNITS or INCREMENTS)."
)
QUANTITY_UNIT_NOT_APPLICABLE: Final = (
    "A quantity unit applies to a per-increment entry only. Remove it or choose PER_INCREMENT."
)
QUANTITY_UNIT_DISAGREES: Final = (
    "Entries of one product declare one quantity unit; row {row} declares another."
)
QUANTITY_UNIT_STORED_DISAGREES: Final = (
    "Entries of this product in this SSP book declare the quantity unit {unit}."
)
QUANTITY_UNIT_STORED_CONTRADICTION: Final = (
    "Stored entries of this product in this SSP book disagree on the quantity unit ({units}); "
    "resolve them before adding or changing entries of this product."
)
BASIS_UNKNOWN: Final = "{value} is not a value basis. Choose {choices}."
ENTRY_DISAGREES: Final = (
    "The band rows of one SSP entry declare one {member}; row {first} declares {expected!r} and "
    "this row {actual!r}."
)
# The members that identify one entry within one version (ssp_values.ENTRY_KEY plus the version).
ENTRY_MEMBERS: Final = (
    "product_code",
    "stratification",
    "region",
    "channel",
    "segment",
    "deal_size_band",
    "term_band",
    "currency",
    "method",
)
UNIT_UNKNOWN: Final = "{value} is not a quantity unit. Choose {choices}."


@dataclass(frozen=True, slots=True)
class Declaration:
    """What one ``ssp_values`` row declares (None = the column was blank)."""

    row_number: int
    book_code: str
    product_code: str
    value_basis: str | None
    quantity_unit: str | None
    entry_key: tuple[str, ...] = ()  # (version label, effective from, ENTRY_MEMBERS…)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def declarations_of(rows: Sequence[tuple[int, Mapping[str, Any]]]) -> list[Declaration]:
    """The declarations of the usable rows, in row order."""
    found: list[Declaration] = []
    for number, values in sorted(rows, key=lambda item: item[0]):
        nested = unflatten(values)
        line = nested.get("lines") or {}
        found.append(
            Declaration(
                row_number=number,
                book_code=_text(values.get(BOOK_COLUMN)) or "",
                product_code=_text(line.get("product_code")) or "",
                value_basis=_text(line.get("value_basis")),
                quantity_unit=_text(line.get("quantity_unit")),
                entry_key=(
                    _text(values.get("legacy_version_label")) or "",
                    _text(values.get("effective_from_date")) or "",
                    *(_text(line.get(member)) or "" for member in ENTRY_MEMBERS),
                ),
            )
        )
    return found


def _finding(code: str, column: str, message: str, row_number: int) -> RowFinding:
    return RowFinding(
        code,
        "ERROR",
        findings.csv_located(message, code, row_number=row_number, column=column),
        column,
    )


def _choices(values: Collection[str]) -> str:
    return ", ".join(sorted(values))


def declaration_findings(
    declared: Sequence[Declaration],
    *,
    series: Collection[str],
    stored: Mapping[str, Collection[str]] | None = None,
) -> dict[int, list[RowFinding]]:
    """The refusals of the rows, in API-S-SspEntry field order per row (basis, then unit), then
    the agreement of one product's rows among themselves and with ``stored`` (product code → the
    units the book's retained stored entries declare); an earlier row is never reinterpreted by a
    later declaration. Pure: ``series`` and ``stored`` are the two facts read from the database."""
    found: dict[int, list[RowFinding]] = {}

    def add(code: str, column: str, message: str, row: Declaration) -> None:
        found.setdefault(row.row_number, []).append(_finding(code, column, message, row.row_number))

    contradictions: dict[str, str] = {}
    agreed: dict[str, str] = {}
    for code, units in (stored or {}).items():
        distinct = sorted({str(unit) for unit in units if unit is not None})
        if len(distinct) > 1:
            contradictions[code] = ", ".join(distinct)
        elif distinct:
            agreed[code] = distinct[0]
    first_of_entry: dict[tuple[str, ...], Declaration] = {}
    for row in declared:
        if row.product_code and row.product_code in contradictions:  # F-DIN-SSP-R2: any basis
            add(
                CODE_UNIT_CONTRADICTION,
                UNIT_COLUMN,
                QUANTITY_UNIT_STORED_CONTRADICTION.format(units=contradictions[row.product_code]),
                row,
            )
            continue
        if row.entry_key:  # F-DIN-SSP-R1: the band rows of one entry declare alike
            lead = first_of_entry.setdefault(row.entry_key, row)
            if lead is not row:
                disagreement = False
                for member, column, expected, actual in (
                    ("value basis", BASIS_COLUMN, lead.value_basis, row.value_basis),
                    ("quantity unit", UNIT_COLUMN, lead.quantity_unit, row.quantity_unit),
                ):
                    if expected != actual:
                        add(
                            CODE_ENTRY_DISAGREES,
                            column,
                            ENTRY_DISAGREES.format(
                                member=member,
                                first=lead.row_number,
                                expected=expected,
                                actual=actual,
                            ),
                            row,
                        )
                        disagreement = True
                if disagreement:
                    continue
        basis_ok = True
        if row.value_basis is None:
            if row.product_code in series:
                add(CODE_BASIS_REQUIRED, BASIS_COLUMN, SERIES_BASIS_REQUIRED, row)
                basis_ok = False
        elif row.value_basis not in VALUE_BASES:
            add(
                CODE_BASIS_REQUIRED,
                BASIS_COLUMN,
                BASIS_UNKNOWN.format(value=row.value_basis, choices=_choices(VALUE_BASES)),
                row,
            )
            basis_ok = False
        per_increment = row.value_basis == PER_INCREMENT
        if row.quantity_unit is not None and row.quantity_unit not in QUANTITY_UNITS:
            add(
                CODE_UNIT_REQUIRED,
                UNIT_COLUMN,
                UNIT_UNKNOWN.format(value=row.quantity_unit, choices=_choices(QUANTITY_UNITS)),
                row,
            )
            continue
        if per_increment and row.quantity_unit is None:
            add(CODE_UNIT_REQUIRED, UNIT_COLUMN, QUANTITY_UNIT_REQUIRED, row)
        elif not per_increment and basis_ok and row.quantity_unit is not None:
            add(CODE_UNIT_NOT_APPLICABLE, UNIT_COLUMN, QUANTITY_UNIT_NOT_APPLICABLE, row)
        if not row.product_code or not per_increment or row.quantity_unit is None:
            continue
        seen = agreed.setdefault(row.product_code, row.quantity_unit)
        if seen != row.quantity_unit:
            message = (
                QUANTITY_UNIT_STORED_DISAGREES.format(unit=seen)
                if stored is not None and row.product_code in stored
                else QUANTITY_UNIT_DISAGREES.format(row=row.row_number)
            )
            add(CODE_UNIT_DISAGREES, UNIT_COLUMN, message, row)
    return found


def series_products(session: Session, codes: Collection[str]) -> set[str]:
    """The codes among ``codes`` whose default POB template (T-REF-22) has a version of ``series``
    distinctness (T-REF-23) — THE predicate of ENG-C1b's ``products.series_product_ids`` (D-97
    (3a); SSP-ADMISSION-R1), read by code here; C1b's function is used once it exists."""
    wanted = sorted({code for code in codes if code})
    if not wanted:
        return set()
    try:  # schema bridge: prefer C1b's predicate when its module carries it
        from erev_api.domain.reference import products as reference_products

        by_id = getattr(reference_products, "series_product_ids", None)
    except ImportError:  # pragma: no cover - the reference package always exists
        by_id = None
    ids = {
        str(row["code"]): UUID(str(row["id"]))
        for row in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(wanted))
        ).mappings()
    }
    if by_id is not None:
        series_ids = set(by_id(session, list(ids.values())))
        return {code for code, product_id in ids.items() if product_id in series_ids}
    statement = (
        select(product.c.code)
        .select_from(
            product.join(
                pob_template_version,
                and_(
                    pob_template_version.c.tenant_id == product.c.tenant_id,
                    pob_template_version.c.pob_template_id == product.c.default_pob_template_id,
                ),
            )
        )
        .where(
            product.c.code.in_(wanted),
            pob_template_version.c.distinctness == Distinctness.SERIES.value,
        )
    )
    return {str(row[0]) for row in session.execute(statement)}


def stored_quantity_units(
    session: Session, book_code: str, codes: Collection[str]
) -> dict[str, set[str]]:
    """Product code → the ``quantity_unit`` values the book's retained stored entries declare
    (D-97 (3) agreement scope), or ``{}`` before the column exists (schema bridge)."""
    if "quantity_unit" not in ssp_entry.c or not book_code:
        return {}
    wanted = sorted({code for code in codes if code})
    if not wanted:
        return {}
    statement = (
        select(product.c.code, ssp_entry.c.quantity_unit)
        .select_from(
            ssp_entry.join(product, product.c.id == ssp_entry.c.product_id)
            .join(ssp_book_version, ssp_book_version.c.id == ssp_entry.c.ssp_book_version_id)
            .join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
        )
        .where(
            ssp_book.c.code == book_code,
            product.c.code.in_(wanted),
            ssp_entry.c.quantity_unit.is_not(None),
        )
    )
    units: dict[str, set[str]] = {}
    for code, unit in session.execute(statement):
        units.setdefault(str(code), set()).add(str(unit))
    return units


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[RowFinding]]:
    """The ``ssp_values`` CROSS_RULE: the declaration refusals over the usable rows (module
    docstring). Rows of several books are checked per book."""
    del known_at, parameters
    declared = declarations_of(rows)
    codes = {row.product_code for row in declared}
    series = series_products(session, codes)
    found: dict[int, list[RowFinding]] = {}
    for book_code in sorted({row.book_code for row in declared}):
        members = [row for row in declared if row.book_code == book_code]
        stored = stored_quantity_units(session, book_code, {row.product_code for row in members})
        for number, items in declaration_findings(members, series=series, stored=stored).items():
            found.setdefault(number, []).extend(items)
    return found
