"""The ``IMPORT_VALIDATE`` job: header check, row validation, findings and control totals (05 §5.5
IPL-02 to IPL-06, §5.6 execution profile; 04 T-IMP-02, T-IMP-03, tables 15.4-A and 15.4-B; PRD
SM-05, IMP copy; 03 REQ-DAT-005 to REQ-DAT-007; BUILD_SPEC DIN-1).

``validate_sheet`` is pure: it checks the headers (``EXACT_SET``; ``ALIASES`` without a mapping
profile checks required and unknown columns), counts data rows (trailing blank rows are not rows;
an interior blank row is ``BLANK``), refuses a header-only sheet and a sheet above 50,000 data rows,
and coerces every cell by its header type:

- ``identifier``, ``text``: the cell text; numbers through their shortest decimal string, so
  ``00042`` stays ``"00042"`` and ``0.1`` is ``"0.1"``;
- ``label``: as text, and a spreadsheet date as ``YYYY-MM-DD`` (LM-SSP-08);
- ``amount``, ``quantity``, ``ratio``: a ``Decimal`` from the number or numeric text, else
  ``VALUE_NOT_NUMERIC``;
- ``date``: a spreadsheet date, an Excel serial number (1900 system) or ISO ``YYYY-MM-DD``, else
  ``DATE_INVALID``.

A blank required cell is ``REQUIRED_VALUE_BLANK``; a formula without a cached value is
``FORMULA_NO_CACHED_VALUE``. A row without findings passes its per-row Pydantic model, whose JSON is
``normalized``. Then the one cross-row rule that reads the file alone: a cell that the rows of one
object of a CSV v2 file repeat is blank or equal to the first of those rows, else
``HEADER_VALUE_CONFLICT`` on the later row (``repeated_conflicts``; 05 IPL-05 rev 1.210).

The job moves the upload UPLOADED → VALIDATING in one transaction, then in a second transaction
writes one ``import_row`` per data row once, raises one exception item (source ``IMPORT``) per
finding, stores the counts and ``control_totals.source``, and ends ``VALIDATED``, or ``INVALID``
when any finding is an ``ERROR`` (IPL-05). An unexpected error rolls that transaction back and ends
the upload ``INVALID`` with ``IMPORT_PROCESSING_FAILED`` (L4-1-Q-31).

[J] L4-1-Q-28: this item enforces the generic type-stage codes only; the template rules of table
15.4-A (for example ``SSP_DISTINCT_FLAG_INVALID``) and the cross-row and cross-file codes belong to
the items that build each template's emitter (DIN-4 to DIN-6), which extend ``ROW_RULES``. Since
DIN-4 ``ROW_RULES`` holds the legacy v1 row rules (``legacy_v1.ROW_RULES``), and ``cross_checked``
runs the legacy cross-row and cross-file rules (``legacy_v1.CROSS_RULES``) over the usable rows
with the stored state of the tenant.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.db import errors as db_errors
from erev_api.db import new_id
from erev_api.db.tables import import_row, import_upload
from erev_api.db.transitions import apply
from erev_api.domain.imports import (
    csv_v2,
    findings,
    job_hooks,
    legacy_v1,
    mapping_profiles,
    parse,
    scope,
    templates,
)
from erev_api.domain.imports.csv_v2 import framework as csv_framework
from erev_api.domain.imports.exceptions import raise_exception_item, severity_of
from erev_api.domain.imports.findings import located
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import ExceptionSource, ImportRowStatus, ImportStatus, JobKind
from erev_api.files.store import open_file
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.logging import get_logger, register_logger_fields

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "MAX_DATA_ROWS",
    "ROW_MODELS",
    "Finding",
    "RowResult",
    "Validation",
    "coerce",
    "fail_validation",
    "import_validate",
    "incomplete_units",
    "repeated_conflicts",
    "start_validation",
    "validate_sheet",
    "validate_upload",
]

FindingSeverity = Literal["ERROR", "WARNING", "INFO"]
OBJECT_TYPE: Final = "import_upload"
VALIDATE_ACTION: Final = "import_upload.validate"
IMPORT_HREF: Final = "/api/v1/imports/{import_id}"
# 05 UPL-07; REQ-SEC-012.
MAX_DATA_ROWS: Final = 50_000
INSERT_BATCH: Final = 1_000
# 05 §5.6: IMPORT_VALIDATE takes 2 attempts with a 10 second wait.
VALIDATE_RETRY: Final = RetryPolicy(max_attempts=2, backoff_seconds=(10,))
EXCEL_EPOCH: Final = date(1899, 12, 30)
EXCEL_MAX_SERIAL: Final = 2_958_465  # 9999-12-31
_NUMBER: Final = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_ISO_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LOGGER: Final = "erev_api.domain.imports.validate"

register_logger_fields(_LOGGER, ("import_upload_id", "error_class"))


@dataclass(frozen=True, slots=True)
class Finding:
    """One §15.4 finding; ``column`` and ``row_number`` are set for row messages."""

    code: str
    severity: FindingSeverity
    message: str
    column: str | None = None
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class RowResult:
    row_number: int
    raw: Mapping[str, str | None]
    normalized: Mapping[str, Any] | None
    status: ImportRowStatus
    business_key: str | None
    row_sha256: str
    findings: tuple[Finding, ...]
    aggregated_into: int | None = None  # the lead row of an AGGREGATED row (BUILD_SPEC DIN-5)
    # The subject the row belongs to (``scope.TemplateScope.unit``: its contract, or the SSP
    # version of a legacy SKU SSP row), as the row's TYPED cell reads — so a refused row and a
    # usable row of one subject carry the same text (rulings R-98 (10), R-109 (c)).
    unit_key: str | None = None


@dataclass(frozen=True, slots=True)
class Validation:
    sheet_name: str
    findings: tuple[Finding, ...]  # file-level findings
    rows: tuple[RowResult, ...]
    data_rows: int


@dataclass(frozen=True, slots=True)
class Outcome:
    status: ImportStatus
    counts: Mapping[str, int]
    exception_count: int


@dataclass(slots=True)
class _Row:
    findings: list[Finding] = field(default_factory=list)
    typed: dict[str, Any] = field(default_factory=dict)


# --- per-row models (IPL-04) --------------------------------------------------------------------

_PYTHON_TYPES: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "identifier": str,
        "text": str,
        "label": str,
        "amount": Decimal,
        "quantity": Decimal,
        "ratio": Decimal,
        "date": date,
    }
)


def _row_model(class_name: str, code: str) -> type[BaseModel]:
    """A frozen Pydantic model whose fields carry the template's header names as aliases."""
    fields: dict[str, Any] = {}
    for index, (name, kind, required) in enumerate(templates.LEGACY_HEADER_TYPES[code]):
        python_type: Any = _PYTHON_TYPES[kind]
        annotation: Any = python_type if required else python_type | None
        default: Any = ... if required else None
        fields[f"column_{index}"] = (annotation, Field(default, alias=name))
    return create_model(
        class_name, __config__=ConfigDict(extra="forbid", frozen=True, strict=False), **fields
    )


LegacySkuSspRow: Final = _row_model("LegacySkuSspRow", "legacy_sku_ssp")
LegacyContractSetupRow: Final = _row_model("LegacyContractSetupRow", "legacy_contract_setup")
LegacyProgressTrackingRow: Final = _row_model(
    "LegacyProgressTrackingRow", "legacy_progress_tracking"
)
LegacyContractModificationRow: Final = _row_model(
    "LegacyContractModificationRow", "legacy_contract_modification"
)
# The templates whose rows this platform can validate; POST /imports refuses the others until their
# items register a model (L4-1-Q-26).
ROW_MODELS: Final[Mapping[str, type[BaseModel]]] = MappingProxyType(
    {
        "legacy_sku_ssp": LegacySkuSspRow,
        "legacy_contract_setup": LegacyContractSetupRow,
        "legacy_progress_tracking": LegacyProgressTrackingRow,
        "legacy_contract_modification": LegacyContractModificationRow,
        # CSV v2 templates with an emitter (DIN-3, DIN-9; L5-1-Q-4, L5-1-Q-23).
        **csv_v2.ROW_MODELS,
    }
)
# Template-specific row rules, added by the items that build each template (DIN-4 to DIN-6).
type RowRule = Callable[[Mapping[str, Any]], Sequence[Finding]]


def _finding(found: RowFinding, row_number: int | None = None) -> Finding:
    return Finding(found.code, found.severity, found.message, found.column, row_number)


def _adapted(rule: legacy_v1.RowRule) -> RowRule:
    """A legacy v1 row rule answering ``Finding`` objects."""

    def checked(typed: Mapping[str, Any]) -> Sequence[Finding]:
        return [_finding(found) for found in rule(typed)]

    return checked


ROW_RULES: Final[dict[str, tuple[RowRule, ...]]] = {
    code: tuple(_adapted(rule) for rule in rules) for code, rules in legacy_v1.ROW_RULES.items()
}


# --- messages (PRD §5.5 IMP copy) ---------------------------------------------------------------


def header_mismatch(template_name: str, missing: Sequence[str], extra: Sequence[str]) -> str:
    """IMP-01."""
    return (
        f"The file does not match the {template_name} template. "
        f"Missing: {', '.join(missing) or 'none'}. Extra: {', '.join(extra) or 'none'}."
    )


NO_DATA_ROWS: Final = findings.NO_DATA_ROWS  # IMP-06 (BUILD_SPEC DIN-8)


def row_limit(sheet_name: str, count: int) -> str:
    """IMP-42."""
    return (
        f"Sheet {sheet_name} has {count:,} data rows. "
        f"Split the file so that each sheet has at most {MAX_DATA_ROWS:,} rows."
    )


def processing_failed(reference: str) -> str:
    """IMP-07 (``findings.processing_failed``; BUILD_SPEC DIN-8)."""
    return findings.processing_failed(reference)


def required_blank(column: str) -> str:
    """IMP-03."""
    return f"{column} is required."


def not_numeric(column: str, value: str) -> str:
    """IMP-02."""
    return f'{column} must be a number. Found "{value}".'


def date_invalid(column: str) -> str:
    """IMP-17."""
    return f"{column} is not a date. Use YYYY-MM-DD or an Excel date."


def formula_without_value(sheet_name: str, row_number: int, column: str) -> str:
    """IMP-96."""
    return (
        f"Sheet {sheet_name}, row {row_number}, column {column}: the cell holds a formula without "
        "a saved value. Open the file in Excel, save it and upload it again."
    )


HEADER_CONFLICT: Final = "HEADER_VALUE_CONFLICT"
QUOTED_LENGTH: Final = 60  # a cell quoted in a finding: a rationale may run to thousands


def _quoted(value: str) -> str:
    text = value if len(value) <= QUOTED_LENGTH else f"{value[:QUOTED_LENGTH]}…"
    return f'"{text}"'


def header_conflict(
    group: str, first: int, expected: str | None, actual: str, *, required: bool
) -> str:
    """IMP-147: this row states ``actual`` in a cell that the rows of ``group`` repeat, where row
    ``first``, the first of them, states ``expected`` — None where that row leaves the cell
    blank. ``group`` is an object or a line of it, so the sentence sends nobody to a header."""
    if expected is None:
        return (
            f"This row states {_quoted(actual)} where row {first} of the same {group} leaves the "
            f"cell blank. State it on row {first} or leave this cell blank."
        )
    remedy = "" if required else " or leave this cell blank"
    return (
        f"This row states {_quoted(actual)} where row {first} of the same {group} states "
        f"{_quoted(expected)}. Repeat the value of row {first}{remedy}."
    )


# --- coercion (REQ-DAT-007) ---------------------------------------------------------------------


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or isinstance(value, datetime | date):
        return None
    text = parse.cell_text(value)
    if text is None:
        return None
    text = text.strip()
    if _NUMBER.fullmatch(text) is None:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        serial = Decimal(parse.cell_text(value) or "")
        if serial != serial.to_integral_value() or not 1 <= serial <= EXCEL_MAX_SERIAL:
            return None
        return EXCEL_EPOCH + timedelta(days=int(serial))
    if isinstance(value, str) and _ISO_DATE.fullmatch(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def coerce(kind: str, value: Any) -> tuple[Any, str | None]:
    """The typed value of a cell under a header type and the §15.4 code of a failure."""
    if _blank(value):
        return None, None
    if kind in templates.NUMERIC_TYPES:
        number = _decimal(value)
        return (None, "VALUE_NOT_NUMERIC") if number is None else (number, None)
    if kind == "date":
        found = _date(value)
        return (None, "DATE_INVALID") if found is None else (found, None)
    if kind == "label" and isinstance(value, datetime | date):
        return (value.date() if isinstance(value, datetime) else value).isoformat(), None
    return parse.cell_text(value), None


def _key_text(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _sha256(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


# --- the pure validation ------------------------------------------------------------------------


def _columns(
    template: templates.Template, headers: Sequence[Any]
) -> tuple[dict[str, int], list[str], list[str]]:
    """The column index of each found header, and the missing and extra header names (IPL-03)."""
    found: dict[str, int] = {}
    extra: list[str] = []
    for index, cell in enumerate(headers):
        name = parse.cell_text(cell)
        if name is None or name == "":
            continue
        if name in found:
            extra.append(name)
            continue
        found[name] = index
    expected = [header.name for header in template.headers]
    if template.header_match == "EXACT_SET":
        missing = [name for name in expected if name not in found]
    else:
        missing = [
            header.name
            for header in template.headers
            if header.required and header.name not in found
        ]
    known = set(expected)
    extra = [name for name in found if name not in known] + extra
    return found, missing, extra


def _row(
    template: templates.Template,
    model: type[BaseModel],
    sheet: parse.SheetRows,
    columns: Mapping[str, int],
    number: int,
    cells: Sequence[Any],
) -> RowResult:
    def cell(name: str) -> Any:
        index = columns.get(name)
        return None if index is None or index >= len(cells) else cells[index]

    raw = {header.name: parse.cell_text(cell(header.name)) for header in template.headers}
    digest = _sha256(raw)
    if all(_blank(value) for value in cells):
        return RowResult(number, raw, None, ImportRowStatus.BLANK, None, digest, ())
    state = _Row()
    for header in template.headers:
        index = columns.get(header.name)
        if index is not None and (number, index) in sheet.formula_cells:
            state.findings.append(
                Finding(
                    "FORMULA_NO_CACHED_VALUE",
                    "ERROR",
                    formula_without_value(sheet.sheet_name, number, header.name),
                    header.name,
                    number,
                )
            )
            continue
        value = cell(header.name)
        typed, code = coerce(header.type, value)
        if code == "VALUE_NOT_NUMERIC":
            text = parse.cell_text(value) or ""
            state.findings.append(
                Finding(code, "ERROR", not_numeric(header.name, text), header.name, number)
            )
        elif code == "DATE_INVALID":
            state.findings.append(
                Finding(code, "ERROR", date_invalid(header.name), header.name, number)
            )
        elif typed is None and header.required:
            state.findings.append(
                Finding(
                    "REQUIRED_VALUE_BLANK",
                    "ERROR",
                    required_blank(header.name),
                    header.name,
                    number,
                )
            )
        state.typed[header.name] = typed
    for rule in ROW_RULES.get(template.code, ()):
        state.findings.extend(
            finding if finding.row_number is not None else _at(finding, number)
            for finding in rule(state.typed)
        )
    key_values = [state.typed.get(name) for name in _key_columns(template.code)]
    business_key = " / ".join(_key_text(value) for value in key_values if value is not None) or None
    unit = scope.scope_of(template.code).unit
    unit_key = None if unit is None else scope.key_text(state.typed.get(unit[0]))
    severities = {finding.severity for finding in state.findings}
    if "ERROR" in severities:
        return RowResult(
            number,
            raw,
            None,
            ImportRowStatus.ERROR,
            business_key,
            digest,
            tuple(state.findings),
            unit_key=unit_key,
        )
    normalized = model.model_validate(state.typed).model_dump(mode="json", by_alias=True)
    status = ImportRowStatus.WARNING if "WARNING" in severities else ImportRowStatus.VALID
    return RowResult(
        number,
        raw,
        normalized,
        status,
        business_key,
        digest,
        tuple(state.findings),
        unit_key=unit_key,
    )


def _key_columns(code: str) -> tuple[str, ...]:
    """The T-IMP-03 ``business_key`` columns: legacy key columns, or a CSV v2 key column."""
    found = csv_v2.TEMPLATES.get(code)
    return (found.key_column,) if found is not None else tuple(templates.KEY_COLUMNS.get(code, ()))


def _at(finding: Finding, number: int) -> Finding:
    return Finding(finding.code, finding.severity, finding.message, finding.column, number)


def validate_sheet(template: templates.Template, sheet: parse.SheetRows) -> Validation:
    """IPL-03 to IPL-05 for one sheet, without side effects."""
    model = ROW_MODELS.get(template.code)
    if model is None:
        raise LookupError(f"template {template.code} has no row model")
    template = csv_framework.effective(template, csv_v2.TEMPLATES)
    columns, missing, extra = _columns(template, sheet.headers)
    if missing or extra:
        finding = Finding(
            "TEMPLATE_HEADER_MISMATCH", "ERROR", header_mismatch(template.name, missing, extra)
        )
        return Validation(sheet.sheet_name, (finding,), (), 0)
    rows = list(sheet.rows)
    while rows and all(_blank(value) for value in rows[-1][1]):
        rows.pop()
    data_rows = sum(1 for _, cells in rows if not all(_blank(value) for value in cells))
    if data_rows == 0:
        return Validation(
            sheet.sheet_name, (Finding("IMPORT_NO_DATA_ROWS", "ERROR", NO_DATA_ROWS),), (), 0
        )
    if data_rows > MAX_DATA_ROWS:
        finding = Finding(
            "IMPORT_ROW_LIMIT_EXCEEDED", "ERROR", row_limit(sheet.sheet_name, data_rows)
        )
        return Validation(sheet.sheet_name, (finding,), (), data_rows)
    results = tuple(_row(template, model, sheet, columns, number, cells) for number, cells in rows)
    validation = Validation(sheet.sheet_name, (), results, data_rows)
    return _with_findings(validation, repeated_conflicts(template, validation))


def _repeat_key(
    headers: Mapping[str, templates.Header], row: RowResult, columns: Sequence[str]
) -> tuple[str, ...] | None:
    """The text of a row's ``columns`` as ``csv_v2.framework.grouped`` reads them — a blank cell
    "" — or None for a row that names no group: a required cell of the key is blank, or a cell
    of the key is not of its column's type. Such a row carries that finding already."""
    parts: list[str] = []
    for column in columns:
        cell = row.raw.get(column)
        typed, failed = coerce(headers[column].type, cell)
        if failed is not None or (typed is None and headers[column].required):
            return None
        parts.append("" if typed is None else _key_text(typed))
    return tuple(parts)


def repeated_conflicts(
    template: templates.Template, validation: Validation
) -> dict[int, list[RowFinding]]:
    """05 IPL-05 rev 1.210; 04 table 15.4-B ``HEADER_VALUE_CONFLICT`` (item
    IMPORT-HEADER-CELL-CONFLICT-1; the supervisor's ruling of 2026-10-02). The rows of one object
    of a CSV v2 file — and, in two templates, the rows of one line of it — repeat cells that the
    template's emitter reads from the FIRST of those rows (``csv_v2.framework.Repeated``): a
    later row that states another value stated something the import would not store, and
    nothing said so. Such a cell is refused on the later row at its column, naming both rows and
    both values.

    Equality is of the cell as the template types its column (``coerce``): a date as a date, a
    number as a number, text exactly. A blank later cell is the first row's value. A value on a
    later row where the first row is blank is a conflict too — it would not be stored either —
    unless the column is required: the first row then carries its own finding. A cell that is
    not of its column's type is left to that finding, on whichever row it stands. Pure: the file
    alone, every row in file order, no stored row. A CSV cell is its text (``parse.read_csv``),
    so ``raw`` is the cell as the row's own validation typed it; a row without cells names no
    group, every key holding a required column."""
    emitter = csv_v2.TEMPLATES.get(template.code)
    if emitter is None:
        return {}
    headers = {header.name: header for header in template.headers}
    found: dict[int, list[RowFinding]] = {}
    for repeat in emitter.repeats:
        leads: dict[tuple[str, ...], RowResult] = {}
        for row in validation.rows:
            key = _repeat_key(headers, row, repeat.key)
            if key is None:
                continue
            lead = leads.setdefault(key, row)
            if lead is row:
                continue
            for column in repeat.cells:
                stated, first = row.raw.get(column), lead.raw.get(column)
                if _blank(stated) or stated == first:
                    continue
                header = headers[column]
                actual, failed = coerce(header.type, stated)
                expected, lead_failed = coerce(header.type, first)
                if failed is not None or lead_failed is not None or actual == expected:
                    continue
                if expected is None and header.required:
                    continue
                names = [lead.raw.get(name) for name in repeat.named_by]
                named = " / ".join(str(text) for text in names if not _blank(text))
                message = header_conflict(
                    f"{repeat.group} {named}".strip(),
                    lead.row_number,
                    None if expected is None else str(first),
                    str(stated),
                    required=header.required,
                )
                found.setdefault(row.row_number, []).append(
                    RowFinding(HEADER_CONFLICT, "ERROR", message, column)
                )
    return found


SUM_BY_KEY: Final = "SUM_BY_KEY"  # 04 T-IMP-01 ``aggregation_rule``


def aggregated(template: templates.Template, validation: Validation) -> Validation:
    """04 T-IMP-01 ``aggregation_rule = SUM_BY_KEY`` (ENGINE_SPEC S01-R-07; REQ-REC-025; BUILD_SPEC
    DIN-5): among the usable rows of one business key the lowest row leads, and every later row is
    ``AGGREGATED`` into it and keeps its values, which the template sums. [J] L5-1-Q-24: the lead
    row keeps its own status."""
    if template.aggregation_rule != SUM_BY_KEY or not validation.rows:
        return validation
    usable = (ImportRowStatus.VALID, ImportRowStatus.WARNING)
    leads: dict[str, int] = {}
    rows: list[RowResult] = []
    for row in validation.rows:
        if row.normalized is None or row.business_key is None or row.status not in usable:
            rows.append(row)
            continue
        lead = leads.setdefault(row.business_key, row.row_number)
        if lead == row.row_number:
            rows.append(row)
        else:
            rows.append(
                dataclasses.replace(row, status=ImportRowStatus.AGGREGATED, aggregated_into=lead)
            )
    return dataclasses.replace(validation, rows=tuple(rows))


# Supervisor rulings R-98 (10) and R-109 (b), (c); 04 table 15.4-B (rev 1.147); PRD IMP-134.
CONTRACT_INCOMPLETE: Final = "IMPORT_CONTRACT_INCOMPLETE"
# PRD IMP-134: ``unit`` is what the rows build together (``scope.TemplateScope.unit``: "contract",
# "SSP version", "bundle", "mapping version", "SSP book", "rate set"), ``short`` the word its rows
# are called by.
UNIT_INCOMPLETE: Final = (
    "Another row of {unit} {name} was refused, so none of its rows is loaded. "
    "Correct that row and upload the {short}'s rows again."
)


def unit_incomplete(unit: str, name: str) -> str:
    """PRD IMP-134."""
    return UNIT_INCOMPLETE.format(unit=unit, name=name, short=unit.rsplit(" ", 1)[-1])


def incomplete_units(template_code: str, validation: Validation) -> dict[int, list[RowFinding]]:
    """Supervisor rulings R-98 (10), R-109 (c) and R-116 (g): in quarantine mode (REQ-DAT-008)
    the approval or accounting subject the rows build loads whole or not at all — the contract of
    a template with a contract column, the SSP book version of the legacy SKU SSP template, and
    the bundle, the mapping version, the version of an SSP book and the rate set version a CSV v2
    file builds from several rows (``scope.TemplateScope.unit``). The usable rows of such a
    subject one of whose rows was
    refused — by a type rule, a cross-row or cross-file rule, or because it names an entity
    outside the uploader's scope — are refused with it (``IMPORT_CONTRACT_INCOMPLETE``, by row
    number): the commit would otherwise book the contract from the lines that remain, amend it
    by half an amendment, load events whose cross-row checks counted the refused row, or approve
    a version that is not the study that was uploaded. The subject is the exact text of the
    typed cell that names it (``RowResult.unit_key``); a template without one keeps the
    row-by-row semantics."""
    unit = scope.scope_of(template_code).unit
    if unit is None:
        return {}
    column, kind = unit
    refused = {
        item.unit_key
        for item in validation.rows
        if item.status is ImportRowStatus.ERROR and item.unit_key is not None
    }
    found: dict[int, list[RowFinding]] = {}
    for item in validation.rows:
        if item.normalized is not None and item.unit_key in refused:
            message = unit_incomplete(kind, str(item.unit_key))
            found[item.row_number] = [RowFinding(CONTRACT_INCOMPLETE, "ERROR", message, column)]
    return found


def cross_checked(
    session: Session,
    template: templates.Template,
    validation: Validation,
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> Validation:
    """The template's cross-row and cross-file rules over the usable rows (BUILD_SPEC DIN-4 to
    DIN-6; L4-1-Q-28): a row that gains an ERROR finding becomes ``ERROR`` without ``normalized``,
    one that gains a WARNING becomes ``WARNING``."""
    code = template.code
    rule = legacy_v1.CROSS_RULES.get(code) or csv_v2.CROSS_RULES.get(code)
    if rule is None or not validation.rows:
        return validation
    usable = [(row.row_number, row.normalized) for row in validation.rows if row.normalized]
    found = rule(session, usable, known_at=known_at, parameters=parameters) if usable else {}
    return _with_findings(validation, found)


def _cells(item: RowResult) -> Mapping[str, Any]:
    """The cells of a row by template header, as the entity scope reads them: the normalised value
    where the row has one — what the commands will act on — else the cell as read."""
    return {**item.raw, **(item.normalized or {})}


def _with_findings(validation: Validation, found: Mapping[int, Sequence[RowFinding]]) -> Validation:
    """``validation`` with the row findings ``found`` (by row number): a row that gains an ERROR
    becomes ``ERROR`` without ``normalized``, one that gains a WARNING becomes ``WARNING``."""
    if not found:
        return validation
    rows: list[RowResult] = []
    for row in validation.rows:
        extra = found.get(row.row_number, ())
        if not extra:
            rows.append(row)
            continue
        findings = (*row.findings, *(_finding(item, row.row_number) for item in extra))
        severities = {finding.severity for finding in findings}
        if "ERROR" in severities:
            rows.append(
                dataclasses.replace(
                    row, findings=findings, status=ImportRowStatus.ERROR, normalized=None
                )
            )
        elif "WARNING" in severities:
            rows.append(dataclasses.replace(row, findings=findings, status=ImportRowStatus.WARNING))
        else:
            rows.append(dataclasses.replace(row, findings=findings))
    return dataclasses.replace(validation, rows=tuple(rows))


def control_totals(template: templates.Template, validation: Validation) -> dict[str, Any]:
    """IPL-06 ``control_totals.source``: data rows, amount sums per amount column, and the SHA-256
    of the rows' canonical hashes in row order (L4-1-Q-32)."""
    data = [row for row in validation.rows if row.status is not ImportRowStatus.BLANK]
    sums: dict[str, str] = {}
    for header in template.headers:
        if header.type != "amount":
            continue
        total = sum(
            (
                Decimal(str(row.normalized[header.name]))
                for row in data
                if row.normalized is not None and row.normalized.get(header.name) is not None
            ),
            Decimal(0),
        )
        sums[header.name] = format(total, "f")
    digest = hashlib.sha256("\n".join(row.row_sha256 for row in data).encode()).hexdigest()
    return {
        "source": {"rows": validation.data_rows, "amount_sums": sums, "sha256": digest},
        "loaded": None,
    }


# --- persistence --------------------------------------------------------------------------------


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _locked(session: Session, upload_id: UUID) -> Mapping[str, Any] | None:
    row = (
        session.execute(
            select(import_upload).where(import_upload.c.id == upload_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def start_validation(uow: UnitOfWork, upload_id: UUID) -> bool:
    """UPLOADED → VALIDATING; True when the upload is VALIDATING afterwards (a retried attempt)."""
    row = _locked(uow.session, upload_id)
    if row is None:
        return False
    status = str(row["status"])
    if status == ImportStatus.UPLOADED.value:
        apply(
            uow.session,
            OBJECT_TYPE,
            upload_id,
            to_status=ImportStatus.VALIDATING.value,
            set_values=_stamps(uow),
            expected_status=status,
        )
        return True
    return status == ImportStatus.VALIDATING.value


def _insert_rows(
    uow: UnitOfWork,
    upload_id: UUID,
    validation: Validation,
    progress: Callable[[int, int | None], None] | None,
) -> dict[int, UUID]:
    principal = uow.principal
    ids: dict[int, UUID] = {}
    batch: list[dict[str, Any]] = []
    total = len(validation.rows)
    for done, row in enumerate(validation.rows, start=1):
        row_id = new_id()
        ids[row.row_number] = row_id
        batch.append(
            {
                "tenant_id": principal.tenant_id,
                "id": row_id,
                "import_upload_id": upload_id,
                "sheet_name": validation.sheet_name,
                "row_number": row.row_number,
                "raw": dict(row.raw),
                "normalized": None if row.normalized is None else dict(row.normalized),
                "row_sha256": row.row_sha256,
                "status": row.status.value,
                "business_key": row.business_key,
                "aggregated_into_row_id": (
                    None if row.aggregated_into is None else ids[row.aggregated_into]
                ),
                "created_at": uow.now,
                "created_by": principal.id,
                "created_by_kind": principal.kind.value,
            }
        )
        if len(batch) == INSERT_BATCH or done == total:
            uow.session.execute(insert(import_row), batch)
            batch = []
            if progress is not None:
                progress(done, total)
    return ids


def _stored_message(
    template: templates.Template | None,
    sheet_name: str,
    finding: Finding,
    business_key: str | None,
) -> str:
    """BUILD_SPEC DIN-7: a legacy v1 row finding names its location, key and code
    (``findings.located``); a CSV v2 row finding takes the CSV form of CPY-06
    (``findings.csv_located``; D-87, L6-1-Q-2); file-level findings keep their copy."""
    if template is None or finding.row_number is None:
        return finding.message
    if template.family == "CSV_V2":
        return findings.csv_located(
            finding.message, finding.code, row_number=finding.row_number, column=finding.column
        )
    if template.family != "LEGACY_V1":
        return finding.message
    return located(
        finding.message,
        finding.code,
        sheet_name=sheet_name,
        row_number=finding.row_number,
        column=finding.column,
        business_key=business_key,
    )


def _raise(
    uow: UnitOfWork,
    upload_id: UUID,
    finding: Finding,
    *,
    row_id: UUID | None = None,
    business_key: str | None = None,
    message: str | None = None,
    named: tuple[UUID, UUID] | None = None,
) -> None:
    """One finding as an exception item of the upload. ``named`` is the existing contract the
    finding's row names with its contracting entity (``scope.named_contract``; 04 T-IMP-05 rev
    1.218, item EXC-IMPORT-SCOPE-1): the item then names both and is read as any item of that
    entity; a file-level finding, and a row whose contract does not exist or lies outside the
    scope the upload writes with, names neither and is read by the readers of the import."""
    subject = str(upload_id)
    if finding.row_number is not None:
        subject = f"{upload_id}:{finding.row_number}:{finding.column}"
    raise_exception_item(
        uow,
        source=ExceptionSource.IMPORT,
        code=finding.code,
        severity=severity_of(finding.severity),
        message=finding.message if message is None else message,
        dedupe=f"{ExceptionSource.IMPORT.value}:{finding.code}:{subject}",
        field=finding.column,
        business_key=business_key,
        import_upload_id=upload_id,
        import_row_id=row_id,
        contract_id=None if named is None else named[0],
        entity_id=None if named is None else named[1],
    )


def _finish(
    uow: UnitOfWork,
    upload_id: UUID,
    template: templates.Template | None,
    validation: Validation,
    progress: Callable[[int, int | None], None] | None = None,
    *,
    quarantine: bool = False,
    named_entity_ids: frozenset[UUID] | None = None,
    named_contracts: Mapping[int, tuple[UUID, UUID]] | None = None,
) -> Outcome:
    ids = _insert_rows(uow, upload_id, validation, progress)
    exceptions = 0
    for finding in validation.findings:
        _raise(uow, upload_id, finding)
        exceptions += 1
    for row in validation.rows:
        for finding in row.findings:
            _raise(
                uow,
                upload_id,
                finding,
                row_id=ids[row.row_number],
                business_key=row.business_key,
                message=_stored_message(template, validation.sheet_name, finding, row.business_key),
                named=None if named_contracts is None else named_contracts.get(row.row_number),
            )
            exceptions += 1
    by_status = {status: 0 for status in ImportRowStatus}
    for row in validation.rows:
        by_status[row.status] += 1
    errors = any(finding.severity == "ERROR" for finding in validation.findings) or (
        by_status[ImportRowStatus.ERROR] > 0
    )
    # REQ-DAT-008 (BUILD_SPEC DIN-3): in quarantine mode ERROR rows stay behind with their open
    # exception items and the valid rows go on, unless a file-level finding stops the file.
    file_errors = any(finding.severity == "ERROR" for finding in validation.findings)
    usable = by_status[ImportRowStatus.VALID] + by_status[ImportRowStatus.WARNING]
    quarantined = quarantine and not file_errors and usable > 0
    target = ImportStatus.INVALID if errors and not quarantined else ImportStatus.VALIDATED
    counts = {
        "row_count": validation.data_rows,
        "valid_row_count": by_status[ImportRowStatus.VALID],
        "warning_count": by_status[ImportRowStatus.WARNING],
        "error_count": by_status[ImportRowStatus.ERROR],
    }
    totals = (
        None if template is None or not validation.rows else control_totals(template, validation)
    )
    apply(
        uow.session,
        OBJECT_TYPE,
        upload_id,
        to_status=target.value,
        set_values={
            **counts,
            "control_totals": totals,
            # 04 T-IMP-02 rev 1.107: written once with the result; None leaves the upload
            # unresolved (a file that could not be read spans every entity)
            **(
                {}
                if named_entity_ids is None
                else {"named_entity_ids": sorted(named_entity_ids, key=str)}
            ),
            **_stamps(uow),
        },
        expected_status=ImportStatus.VALIDATING.value,
    )
    uow.audit(
        action=VALIDATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=upload_id,
        before={"status": ImportStatus.VALIDATING.value},
        after={"status": target.value, **counts, "exception_items": exceptions},
    )
    if target is ImportStatus.VALIDATED:
        # PRD SM-05: validation runs on into the dry-run diff (05 IPL-07; BUILD_SPEC DIN-3).
        uow.defer(
            JobKind.IMPORT_DIFF,
            {"import_upload_id": str(upload_id)},
            subject_type=OBJECT_TYPE,
            subject_id=upload_id,
        )
    public_counts = {
        "rows": counts["row_count"],
        "valid": counts["valid_row_count"],
        "warnings": counts["warning_count"],
        "errors": counts["error_count"],
    }
    return Outcome(status=target, counts=public_counts, exception_count=exceptions)


def validate_upload(
    uow: UnitOfWork,
    upload_id: UUID,
    *,
    progress: Callable[[int, int | None], None] | None = None,
) -> Outcome | None:
    """IPL-02 to IPL-06 for a VALIDATING upload; None when the upload is no longer VALIDATING."""
    session = uow.session
    row = _locked(session, upload_id)
    if row is None or str(row["status"]) != ImportStatus.VALIDATING.value:
        return None
    template = templates.find_template(
        session, str(row["template_code"]), int(row["template_version"])
    )
    if template is None:
        raise LookupError(f"import template {row['template_code']} is absent")
    template = csv_framework.effective(template, csv_v2.TEMPLATES)
    _, stream = open_file(session, row["file_object_id"], files=uow.files, keyring=uow.keyring)
    try:
        with stream:
            sheet = (
                parse.read_xlsx(stream)
                if template.file_format == "XLSX"
                else parse.read_csv(stream)
            )
    except parse.ParseError:
        return fail_validation(uow, upload_id, locked=True)
    attributes: Mapping[int, Mapping[str, str]] = {}
    found = (
        None
        if row["mapping_profile_id"] is None
        else mapping_profiles.profile(session, UUID(str(row["mapping_profile_id"])))
    )
    if found is not None:
        # BUILD_SPEC DIN-10: the file is read through its mapping profile (REQ-DAT-013).
        mapped = mapping_profiles.mapped_sheet(sheet, found)
        sheet, attributes = mapped.sheet, mapped.custom_attributes
    validated = validate_sheet(template, sheet)
    if attributes:
        rows = tuple(
            dataclasses.replace(
                item,
                normalized=mapping_profiles.attributed(
                    item.normalized, attributes.get(item.row_number)
                ),
            )
            for item in validated.rows
        )
        validated = dataclasses.replace(validated, rows=rows)
    # 05 IPL-05 rev 1.46 and 1.86 (rulings R-29 and R-98; SC-2): the entities every data row
    # names are resolved with this job's every-entity session and stored with the result. A row
    # naming an entity outside the uploader's scope for the template's write permission is
    # refused by name FIRST (R-98 (6)), so that the cross-row and cross-file rules — which read
    # stored state INSIDE that scope, but also tables no entity scope narrows (an SSP book's
    # entries) — never examine it and quote nothing of what it names.
    quarantine = bool(row["is_quarantine_mode"])
    data = [item for item in validated.rows if item.status is not ImportRowStatus.BLANK]
    resolution = scope.resolve(session, template.code, [_cells(item) for item in data])
    bounds = scope.uploader_bounds(session, row, template.code, at=uow.now)
    scoped = _with_findings(
        validated,
        scope.findings(
            template.code, [(item.row_number, _cells(item)) for item in data], resolution, bounds
        ),
    )
    with scope.narrowed(uow, bounds.db_scope):
        validation = cross_checked(
            session,
            template,
            aggregated(template, scoped),
            known_at=uow.now,
            parameters=dict(row["parameters"] or {}),
        )
    if quarantine:
        # R-98 (10), R-109 (c), R-116 (g): in quarantine mode a contract — or the SSP version
        # of a legacy SKU SSP file, a bundle, a mapping version, the version of an SSP book, a
        # rate set version — commits whole or not at all
        validation = _with_findings(validation, incomplete_units(template.code, validation))
    refused = {item.row_number for item in validation.rows if item.status is ImportRowStatus.ERROR}
    # R-114 (g): which rows name the entity they write for (the first row of a contract in the
    # legacy setup; every row elsewhere), read in the file's order as the scope resolved them
    writing = dict(
        zip(
            (item.row_number for item in data),
            scope.writing_rows(template.code, [_cells(item) for item in data]),
            strict=True,
        )
    )
    for item in validation.rows:
        if item.normalized is None or item.aggregated_into in refused:
            # R-98 (5): the refusal of a key is carried by its lead row (``findings.every_row``).
            # A row aggregated into a refused lead never commits: outside quarantine mode the
            # file is INVALID, in quarantine mode the row was refused with its contract above
            continue
        if scope.outside(
            template.code,
            _cells(item),
            resolution,
            bounds,
            writes=writing.get(item.row_number, True),
        ):
            # fail closed (IMPORT_PROCESSING_FAILED): no rule above refused a usable row that
            # names an entity outside the uploader's scope
            raise LookupError(
                f"row {item.row_number} of {template.code} names an entity outside the "
                "uploader's scope and no rule refused it"
            )
    return _finish(
        uow,
        upload_id,
        template,
        validation,
        progress,
        quarantine=quarantine,
        # a file whose rows were not read (a header mismatch, no data rows, the row limit) names
        # nothing this job examined, and a row naming a reference that does not resolve names
        # something this job could not place (R-98 (2)): the upload stays unresolved
        named_entity_ids=resolution.named if validated.rows else None,
        # EXC-IMPORT-SCOPE-1: a finding on a row names the existing contract of that row and
        # its entity, when the contract lies inside the scope the upload writes with
        named_contracts={
            item.row_number: named
            for item in validation.rows
            if item.findings
            and (named := scope.named_contract(template.code, _cells(item), resolution, bounds))
            is not None
        },
    )


def fail_validation(uow: UnitOfWork, upload_id: UUID, *, locked: bool = False) -> Outcome | None:
    """VALIDATING → INVALID with ``IMPORT_PROCESSING_FAILED``; nothing else is written."""
    if not locked:
        row = _locked(uow.session, upload_id)
        if row is None or str(row["status"]) != ImportStatus.VALIDATING.value:
            return None
    finding = Finding("IMPORT_PROCESSING_FAILED", "ERROR", processing_failed(uow.ctx.request_id))
    return _finish(uow, upload_id, None, Validation(parse.CSV_SHEET, (finding,), (), 0))


def _retryable(error: BaseException) -> bool:
    """Whether the work that met ``error`` may succeed when it is done again (supervisor rulings
    R-105 (2) and R-108 (2); ``db.errors.is_transient``): a database error of a transient class —
    a lock that was not granted, a deadlock, a serialization failure, a cancelled statement,
    resources, a lost connection. Such an error says nothing about the file: the handler stores
    nothing for the upload and lets it through, the attempt fails, and the job is settled by its
    retry policy (dev-guide DG-KRN-JOB-05); the kind's failure hook ends the upload when the job
    ends FAILED."""
    raised = db_errors.database_error_in(error)
    return raised is not None and db_errors.is_transient(raised)


def validation_job_failed(
    uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]
) -> None:
    """The job's failure hook (05 §5.6 rev 1.185; supervisor rulings R-108 (2) and R-105 (2) and
    the supervisor's ruling of 2026-10-02; ``job_hooks``). The handler ends the upload itself for
    every error it stores; this is for the job that ends FAILED without the handler's own ending:
    a last attempt that met a transient database error, which the handler lets through
    (``_retryable``); a fault before the upload entered the job's state, which stands outside the
    handler's catch-all; and a worker that died. The upload it finds ``UPLOADED`` or ``VALIDATING``
    ends ``INVALID`` with ``IMPORT_PROCESSING_FAILED`` under the job's reference, as after an error
    the handler stores: no upload waits behind a validation job that has ended.

    An upload in any other status is left alone, and so is one whose row another transaction
    holds (``job_hooks.held_status``). The uploader started the job, so the job's own
    notification tells the uploader (05 JOB-07). The kind registers no ``failed_item``: the
    upload's finding is the item of a failed validation (``jobs.registry.task``)."""
    del problem  # the finding names the job by the hook's own request id (``job-<id>``)
    upload_id = UUID(str(params["import_upload_id"]))
    found = job_hooks.held_status(
        uow.session, upload_id, (ImportStatus.UPLOADED, ImportStatus.VALIDATING)
    )
    if found is None:
        return
    if found == ImportStatus.UPLOADED.value:
        start_validation(uow, upload_id)
    fail_validation(uow, upload_id, locked=True)


@task(JobKind.IMPORT_VALIDATE, retry=VALIDATE_RETRY, on_failure=validation_job_failed)
def import_validate(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``IMPORT_VALIDATE`` (05 §5.6 queue ``imports``): validate one upload."""
    upload_id = UUID(str(params["import_upload_id"]))
    href = IMPORT_HREF.format(import_id=upload_id)
    with ctx.unit_of_work() as uow:
        started = start_validation(uow, upload_id)
        uow.commit()
    if not started:
        return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": {}})
    try:
        with ctx.unit_of_work() as uow:
            outcome = validate_upload(uow, upload_id, progress=ctx.progress)
            uow.commit()
    except Exception as error:
        if _retryable(error):
            # R-108 (2), R-105 (2): a wait is no finding about the file. The attempt fails and is
            # retried (``VALIDATE_RETRY``); ``validation_job_failed`` ends the upload with the job.
            raise
        get_logger(_LOGGER).error(
            "import.validation_failed",
            import_upload_id=str(upload_id),
            error_class=type(error).__name__,
        )
        with ctx.unit_of_work() as uow:
            outcome = fail_validation(uow, upload_id)
            uow.commit()
    if outcome is None:
        return JobOutcome(state="SUCCEEDED", result={"href": href, "counts": {}})
    state: Literal["SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"] = (
        "SUCCEEDED" if outcome.exception_count == 0 else "SUCCEEDED_WITH_EXCEPTIONS"
    )
    return JobOutcome(state=state, result={"href": href, "counts": dict(outcome.counts)})
