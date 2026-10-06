"""Row-level finding messages (04 table 15.4-A, T-IMP-05 ``message``; DEVIATIONS §5 and its
"Aggregated finding rows" rule, OQ-D11; PRD CPY-06 and the IMP copy; 03 REQ-DAT-005, REQ-DAT-006;
D-30a; legacy 01 FIX-02, FIX-08; BUILD_SPEC DIN-7).

The validation job stores each finding of a legacy v1 row as an exception item whose ``message``
names the worksheet, the Excel row, the column, the failing key and the rule id (REQ-DAT-006):

    <Sheet> row <n>, column <name>: <IMP copy> Key <business key>. (<CODE>)

- The location is PRD CPY-06, with the Excel row number (header row = 1). A finding without a
  column names the row only.
- ``Key <business key>.`` follows the copy only when the copy does not already name the row's
  T-IMP-03 ``business_key``. [J] L6-1-Q-1: most type-stage copy names only the column, while
  IMP-08, IMP-09 and IMP-12 name their own key.
- A finding on a key that several worksheet rows contribute to (DEV-012 aggregation, a duplicate
  key, a contract total) names every contributing row in ascending order, "Rows 2, 6."
  (``every_row``). The lowest row carries the item, and the parity runner reports that row as
  ``worksheet_row`` (DG-PAR-11).
- Copy that already carries its location (IMP-96 ``FORMULA_NO_CACHED_VALUE``) is kept as it is.

A CSV v2 row finding takes the CSV form of CPY-06 (D-87, L6-1-Q-2; ``csv_located``):

    Row <n>, column <label>: <IMP copy> (<CODE>)

- The column label is the name with its first letter capitalised and ``_`` and ``.`` as spaces
  (L5-1-Q-20: ``contract`` → "Contract", ``amount.amount`` → "Amount amount").
- Copy that already starts with its row location (``CONTRACT_NOT_FOUND`` and the stage 01 bounds of
  ``progress_events``, which locate their own copy) is kept as it is.
- [J] L7-4-Q-4: a finding without a column names the row only ("Row <n>: ").

File-stage findings (DEVIATIONS §5 #5 to #7; BUILD_SPEC DIN-8) have no row, so their copy names the
file instead; this module owns that copy:

- ``IMPORT_FILE_DUPLICATE`` (IMP-05, ``duplicate_file``): ``POST /imports`` refuses the upload with
  409 ``duplicate-import`` before any row or finding is written (``upload.create_import``).
- ``IMPORT_NO_DATA_ROWS`` (IMP-06, ``NO_DATA_ROWS``): a header-only sheet is ``INVALID`` with one
  file-level item (``validate.validate_sheet``).
- ``IMPORT_PROCESSING_FAILED`` (IMP-07, ``processing_failed``): an unexpected error during
  validation rolls the rows back and ends the upload ``INVALID`` with one file-level item whose
  reference is the job's request id ``job-<job id>`` (``validate.import_validate``).

[J] L6-1-Q-9: these three messages keep the PRD IMP copy without a worksheet prefix, because CPY-06
locates row findings only and DIN-1 stores IMP-06 verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final

__all__ = [
    "LOCATED_CODES",
    "NO_DATA_ROWS",
    "column_label",
    "csv_located",
    "duplicate_file",
    "every_row",
    "located",
    "processing_failed",
]

LOCATION: Final = "{sheet} row {row}, column {column}: "  # PRD CPY-06
ROW_LOCATION: Final = "{sheet} row {row}: "
CSV_LOCATION: Final = "Row {row}, column {column}: "  # PRD CPY-06, CSV form (D-87 L6-1-Q-2)
CSV_ROW_LOCATION: Final = "Row {row}: "
ROWS_SUFFIX: Final = " Rows {rows}."
KEY_SUFFIX: Final = " Key {key}."
CODE_SUFFIX: Final = " ({code})"
# IMP copy that starts with its own location (PRD IMP-96).
LOCATED_CODES: Final = frozenset({"FORMULA_NO_CACHED_VALUE"})
NO_DATA_ROWS: Final = "The file has headers but no data rows."  # PRD IMP-06


def duplicate_file(import_no: str, on: date) -> str:
    """PRD IMP-05."""
    return (
        f"This file was already imported in {import_no} on {on.isoformat()}. "
        "Nothing was imported again."
    )


def processing_failed(reference: str) -> str:
    """PRD IMP-07."""
    return f"The file could not be processed and nothing was committed. Reference {reference}."


def every_row(message: str, rows: Sequence[int]) -> str:
    """The copy of a finding several rows contribute to, naming every row ascending (OQ-D11)."""
    ordered = sorted(set(rows))
    if len(ordered) < 2:
        return message
    return message + ROWS_SUFFIX.format(rows=", ".join(str(number) for number in ordered))


def located(
    message: str,
    code: str,
    *,
    sheet_name: str,
    row_number: int,
    column: str | None = None,
    business_key: str | None = None,
) -> str:
    """The stored message of a legacy v1 row finding (module docstring)."""
    if code in LOCATED_CODES:
        return message
    if column is None:
        prefix = ROW_LOCATION.format(sheet=sheet_name, row=row_number)
    else:
        prefix = LOCATION.format(sheet=sheet_name, row=row_number, column=column)
    text = message
    if business_key and business_key not in message:
        text += KEY_SUFFIX.format(key=business_key)
    return prefix + text + CODE_SUFFIX.format(code=code)


def column_label(name: str) -> str:
    """The label of a CSV v2 column in a message: ``contract`` → "Contract" (L5-1-Q-20)."""
    text = name.replace(".", " ").replace("_", " ")
    return text[:1].upper() + text[1:]


def csv_located(message: str, code: str, *, row_number: int, column: str | None = None) -> str:
    """The stored message of a CSV v2 row finding (module docstring; D-87, L6-1-Q-2)."""
    if code in LOCATED_CODES or message.startswith(
        (CSV_ROW_LOCATION.format(row=row_number), f"Row {row_number}, column ")
    ):
        return message
    if column is None:
        prefix = CSV_ROW_LOCATION.format(row=row_number)
    else:
        prefix = CSV_LOCATION.format(row=row_number, column=column_label(column))
    return prefix + message + CODE_SUFFIX.format(code=code)
