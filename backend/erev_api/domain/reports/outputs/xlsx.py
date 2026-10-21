"""XLSX outputs with the RV-07 header block (SCREENS_B RV-02, RV-07, RPT-R-03; DESIGN_SYSTEM
DS-FMT-26; 03 REQ-RPT-002, REQ-RPT-024, REQ-SEC-011; BUILD_SPEC RPS-2).

Single reports use one worksheet; render_xlsx_pack adds a contents worksheet and one
worksheet per section with its own source stamp, columns, totals and tie-outs.
The header block lists, one label and value per row: "Report" ``<name> v<version>``,
"Run", "Entity", "Book", "As of", "Source", "Engine" ``<engine version> (<build sha>)``, "Run by",
"Run at" (UTC), "Rows", "Output SHA-256", then "Parameters" with every parameter, "Control totals"
and, when the report has tie-outs, "Tie-outs". A blank row separates it from the grid header, which
is frozen. Money cells are numeric cells with the DS-FMT-26 format of the tenant negative style and
the amount's minor unit; integers are numeric; dates and timestamps are date cells
(``dd mmm yyyy``); text cells pass the formula guard and are always written as strings.
"""

from __future__ import annotations

import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

import xlsxwriter

from erev_api.domain.reports.number_formats import xlsx_number_format
from erev_api.domain.reports.outputs import (
    NOT_SHOWN,
    NOT_SHOWN_TEXT,
    Column,
    LayoutPart,
    ReportData,
    RunStamp,
    display_timestamp,
    layout,
    minor_unit,
    parameter_text,
)
from erev_api.domain.reports.outputs.sanitise import guard

MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXTENSION: Final = "xlsx"
DATE_FORMAT: Final = "dd mmm yyyy"
TIMESTAMP_FORMAT: Final = 'dd mmm yyyy hh:mm "UTC"'
INTEGER_FORMAT: Final = "0"
SHEET_NAME_LENGTH: Final = 31
_SHEET_UNSAFE: Final = re.compile(r"[\[\]:*?/\\]")
ALL_ENTITIES: Final = "All entities"
# RV-02 labels of the header block, in order.
LABEL_REPORT: Final = "Report"
LABEL_RUN: Final = "Run"
LABEL_ENTITY: Final = "Entity"
LABEL_BOOK: Final = "Book"
LABEL_AS_OF: Final = "As of"
LABEL_SOURCE: Final = "Source"
LABEL_ENGINE: Final = "Engine"
LABEL_RUN_BY: Final = "Run by"
LABEL_RUN_AT: Final = "Run at"
LABEL_ROWS: Final = "Rows"
LABEL_SHA256: Final = "Output SHA-256"
LABEL_PARAMETERS: Final = "Parameters"
LABEL_CONTROL_TOTALS: Final = "Control totals"
LABEL_TIE_OUTS: Final = "Tie-outs"


class _Formats:
    """The workbook's cell formats, one number format per minor unit (DS-FMT-26)."""

    def __init__(self, workbook: Any, style: str) -> None:
        self._workbook = workbook
        self._style = style
        self._money: dict[int, Any] = {}
        self.bold = workbook.add_format({"bold": True})
        self.wrapped = workbook.add_format({"text_wrap": True, "valign": "top"})
        self.wrapped_bold = workbook.add_format({"bold": True, "text_wrap": True})
        self.date = workbook.add_format({"num_format": DATE_FORMAT})
        self.timestamp = workbook.add_format({"num_format": TIMESTAMP_FORMAT})
        self.integer = workbook.add_format({"num_format": INTEGER_FORMAT})

    def money(self, amount: str) -> Any:
        unit = minor_unit(amount)
        if unit not in self._money:
            self._money[unit] = self._workbook.add_format(
                {"num_format": xlsx_number_format(unit, self._style)}
            )
        return self._money[unit]


def sheet_name(report_name: str) -> str:
    """A worksheet name Excel accepts: at most 31 characters, none of ``[]:*?/\\``."""
    return _SHEET_UNSAFE.sub(" ", report_name)[:SHEET_NAME_LENGTH].strip().strip("'") or "Report"


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None)


def _write_money(sheet: Any, formats: _Formats, row: int, col: int, value: Any) -> None:
    amount = str(value["amount"])
    sheet.write_number(row, col, float(Decimal(amount)), formats.money(amount))


def _write_cell(
    sheet: Any, formats: _Formats, row: int, col: int, column: Column, part: LayoutPart, value: Any
) -> None:
    if value is NOT_SHOWN:
        sheet.write_string(row, col, guard(NOT_SHOWN_TEXT))
        return
    if value is None or (column.kind == "codes" and not value):
        if column.empty_text:
            sheet.write_string(row, col, guard(column.empty_text))
        else:
            sheet.write_blank(row, col, None)
        return
    if part == "currency":
        sheet.write_string(row, col, guard(str(value["currency"])))
        return
    match column.kind:
        case "money":
            _write_money(sheet, formats, row, col, value)
        case "integer":
            sheet.write_number(row, col, int(value), formats.integer)
        case "decimal":
            # Full precision as text: a float cell would round the exact digits (04 §17.1 rule 4).
            sheet.write_string(row, col, str(value))
        case "date":
            sheet.write_datetime(
                row, col, datetime(value.year, value.month, value.day), formats.date
            )
        case "timestamp":
            sheet.write_datetime(row, col, _naive_utc(value), formats.timestamp)
        case "boolean":
            sheet.write_string(row, col, "Yes" if value else "No")
        case "codes":
            sheet.write_string(row, col, guard(", ".join(str(item) for item in value)))
        case "actor":
            sheet.write_string(row, col, guard(str(value["display_name"])))
        case _:
            sheet.write_string(row, col, guard(str(value)))


def _labelled(sheet: Any, row: int, label: str, value: str) -> int:
    sheet.write_string(row, 0, label)
    sheet.write_string(row, 1, guard(value))
    return row + 1


def _exemption_details(sheet: Any, formats: _Formats, row: int, value: Any) -> int:
    from . import rpo_exemptions as details

    records = details.records(value)
    if not records:
        return row
    sheet.write_string(row, 0, details.TITLE, formats.bold)
    sheet.write_string(row + 1, 0, details.BASIS)
    row += 2
    for col, (_, label) in enumerate(details.COLUMNS):
        sheet.write_string(row, col, label, formats.wrapped_bold)
    for record in records:
        row += 1
        for col, (key, _) in enumerate(details.COLUMNS):
            if key in details.MONEY:
                _write_money(
                    sheet,
                    formats,
                    row,
                    col,
                    {
                        "amount": record[key],
                        "currency": record["currency"],
                    },
                )
            else:
                sheet.write_string(row, col, guard(details.cell(record, key)), formats.wrapped)
    sheet.set_column(0, len(details.COLUMNS) - 1, 22)
    return row + 2


def _exemption_translation(
    sheet: Any, formats: _Formats, row: int, value: Any, *, unexplained: bool = False
) -> int:
    from . import rpo_exemptions as details

    records = details.translation_records(value)
    if not records:
        return row
    sheet.write_string(
        row,
        0,
        details.UNEXPLAINED_TITLE if unexplained else details.TRANSLATION_TITLE,
        formats.bold,
    )
    sheet.write_string(
        row + 1, 0, details.UNEXPLAINED_BASIS if unexplained else details.TRANSLATION_BASIS
    )
    row += 2
    for col, (_, label) in enumerate(details.TRANSLATION_COLUMNS):
        sheet.write_string(row, col, label, formats.wrapped_bold)
    for record in records:
        row += 1
        for col, (key, _) in enumerate(details.TRANSLATION_COLUMNS):
            if key in {"movement", "translated_movement"}:
                currency = record["currency" if key == "movement" else "translated_currency"]
                _write_money(
                    sheet, formats, row, col, {"amount": record[key], "currency": currency}
                )
            else:
                sheet.write_string(row, col, guard(str(record[key])), formats.wrapped)
    sheet.set_column(0, len(details.TRANSLATION_COLUMNS) - 1, 22)
    return row + 2


def _total(sheet: Any, formats: _Formats, row: int, key: str, value: Any) -> int:
    if key == "unexplained_details":
        return _exemption_translation(sheet, formats, row, value, unexplained=True)
    if key == "exemption_translation":
        return _exemption_translation(sheet, formats, row, value)
    if key == "exemption_changes":
        return _exemption_details(sheet, formats, row, value)
    sheet.write_string(row, 0, guard(key))
    if isinstance(value, dict) and "amount" in value and "currency" in value:
        _write_money(sheet, formats, row, 1, value)
        sheet.write_string(row, 2, guard(str(value["currency"])))
    elif isinstance(value, int) and not isinstance(value, bool):
        sheet.write_number(row, 1, value, formats.integer)
    else:
        sheet.write_string(row, 1, guard(parameter_text(value)))
    return row + 1


_GL_COLUMNS = (
    ("entity", "Entity"),
    ("role", "Balance role"),
    ("currency", "Currency"),
    ("gl", "GL balance"),
    ("source_subledger", "Retained subledger"),
    ("rollforward", "Report closing balance"),
    ("subledger_gl_difference", "Subledger minus GL"),
    ("report_subledger_difference", "Report minus subledger"),
    ("difference", "Report minus GL"),
    ("result", "Result"),
    ("bridge_result", "Bridge result"),
    ("source_status", "Source review status"),
    ("reconciliation_id", "Reconciliation ID"),
    ("book_code", "Book"),
    ("period_key", "Period"),
    ("reason", "Unavailable reason"),
    ("bridge_reason", "Bridge unavailable reason"),
)
_GL_MONEY = frozenset(key for key, _ in _GL_COLUMNS[3:9])


def _gl_details(
    sheet: Any, formats: _Formats, row: int, records: Sequence[Mapping[str, Any]]
) -> int:
    """Export retained bridge evidence as filterable numeric rows, without recalculation."""
    if not records:
        return row
    first = row
    for record in records:
        row += 1
        for col, (key, _) in enumerate(_GL_COLUMNS):
            value = record.get(key)
            if value is None:
                continue  # Unavailable evidence stays blank, never a fabricated zero.
            if key in _GL_MONEY:
                _write_money(sheet, formats, row, col, {"amount": value})
            else:
                sheet.write_string(row, col, guard(str(value)), formats.wrapped)
    sheet.add_table(
        first,
        0,
        row,
        len(_GL_COLUMNS) - 1,
        {
            "columns": [
                {"header": label, "header_format": formats.wrapped_bold} for _, label in _GL_COLUMNS
            ],
            "style": "Table Style Medium 2",
        },
    )
    sheet.set_row(first, 32)
    sheet.set_column(0, len(_GL_COLUMNS) - 1, 22)
    return row + 2


def _header_block(
    sheet: Any, formats: _Formats, data: ReportData, stamp: RunStamp, row: int = 0
) -> int:
    row = _labelled(sheet, row, LABEL_REPORT, f"{stamp.report_name} v{stamp.report_version}")
    row = _labelled(sheet, row, LABEL_RUN, stamp.report_run_no)
    row = _labelled(sheet, row, LABEL_ENTITY, ", ".join(stamp.entity_codes) or ALL_ENTITIES)
    row = _labelled(sheet, row, LABEL_BOOK, stamp.book or "")
    row = _labelled(sheet, row, LABEL_AS_OF, stamp.as_of or "")
    row = _labelled(sheet, row, LABEL_SOURCE, stamp.source)
    row = _labelled(sheet, row, LABEL_ENGINE, f"{stamp.engine_version} ({stamp.build_sha})")
    row = _labelled(sheet, row, LABEL_RUN_BY, stamp.run_by)
    row = _labelled(sheet, row, LABEL_RUN_AT, display_timestamp(stamp.run_at))
    sheet.write_string(row, 0, LABEL_ROWS)
    sheet.write_number(row, 1, data.row_count, formats.integer)
    row += 1
    row = _labelled(sheet, row, LABEL_SHA256, stamp.output_sha256)
    sheet.write_string(row, 0, LABEL_PARAMETERS, formats.bold)
    row += 1
    for key, value in sorted(stamp.parameters.items()):
        row = _labelled(sheet, row, key, parameter_text(value))
    sheet.write_string(row, 0, LABEL_CONTROL_TOTALS, formats.bold)
    row += 1
    for key, value in sorted(data.control_totals.items()):
        row = _total(sheet, formats, row, key, value)
    if data.tie_out_results:
        sheet.write_string(row, 0, LABEL_TIE_OUTS, formats.bold)
        row += 1
        for item in data.tie_out_results:
            sheet.write_string(row, 0, guard(str(item["code"])))
            sheet.write_string(row, 1, guard(str(item["result"])))
            sheet.write_string(row, 2, guard(parameter_text(item.get("expected"))))
            sheet.write_string(row, 3, guard(parameter_text(item.get("actual"))))
            row += 1
            if item["code"] == "TO_ROLLFORWARD_EQ_GL":
                row = _gl_details(sheet, formats, row, item.get("details", ()))
                continue
            for detail in item.get("details", ()):
                sheet.write_string(
                    row, 0, guard("; ".join(f"{key}: {value}" for key, value in detail.items()))
                )
                row += 1
    return row


def render_xlsx(data: ReportData, stamp: RunStamp) -> bytes:
    """The XLSX bytes of ``data`` under ``stamp``."""
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(
        buffer,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_numbers": False,
            "strings_to_urls": False,
        },
    )
    workbook.set_properties(
        {
            "title": f"{stamp.report_name} v{stamp.report_version}",
            "subject": stamp.report_run_no,
            "created": _naive_utc(stamp.run_at),
        }
    )
    sheet = workbook.add_worksheet(sheet_name(stamp.report_name))
    _grid(sheet, _Formats(workbook, stamp.negative_number_style), data, stamp)
    workbook.close()
    return buffer.getvalue()


def _grid(
    sheet: Any,
    formats: _Formats,
    data: ReportData,
    stamp: RunStamp,
    notes: tuple[str, ...] = (),
    *,
    start_row: int = 0,
    freeze: bool = True,
) -> int:
    header_row = _header_block(sheet, formats, data, stamp, start_row) + 1
    for note in notes:
        sheet.write_string(header_row, 0, guard(note))
        header_row += 1
    if notes:
        header_row += 1
    columns = layout(data)
    for col, item in enumerate(columns):
        sheet.write_string(header_row, col, guard(item.header), formats.bold)
    for offset, record in enumerate(data.rows, start=1):
        for col, item in enumerate(columns):
            _write_cell(
                sheet,
                formats,
                header_row + offset,
                col,
                item.column,
                item.part,
                record.get(item.column.key),
            )
    sheet.set_column(0, max(len(columns), 2) - 1, 20)
    if freeze:
        sheet.freeze_panes(header_row + 1, 0)
    return header_row + data.row_count + 3


@dataclass(frozen=True, slots=True)
class WorkbookSection:
    """A rendered section with its own source-run stamp and optional election notes.

    Suppressed source facts belong in retained evidence, not the rendered dataset.
    """

    key: str
    title: str
    data: ReportData
    stamp: RunStamp
    notes: tuple[str, ...] = ()
    omitted: bool = False


@dataclass(frozen=True, slots=True)
class WorkbookChapter:
    key: str
    title: str
    tables: tuple[WorkbookSection, ...]


def render_xlsx_pack(sections: tuple[WorkbookSection, ...], stamp: RunStamp) -> bytes:
    """Compatibility entry point: one table per chapter worksheet."""
    return render_xlsx_chapters(
        tuple(WorkbookChapter(s.key, s.title, (s,)) for s in sections), stamp
    )


def validate_chapters(chapters: tuple[WorkbookChapter, ...]) -> None:
    """Reject ambiguous chapter identities and amounts in omitted tables."""
    if (
        not chapters
        or len({c.key for c in chapters}) != len(chapters)
        or any(not c.key or not c.title or not c.tables for c in chapters)
    ):
        raise ValueError("a workbook requires uniquely keyed nonempty chapters")
    sections = tuple(s for chapter in chapters for s in chapter.tables)
    if len({s.key for s in sections}) != len(sections):
        raise ValueError("a workbook pack requires uniquely keyed sections")
    if any(
        not s.key
        or not s.title
        or (
            s.omitted
            and (s.data.rows or s.data.control_totals or s.data.tie_out_results or not s.notes)
        )
        for s in sections
    ):
        raise ValueError("omitted sections require a note and no rendered source rows")


def render_xlsx_chapters(chapters: tuple[WorkbookChapter, ...], stamp: RunStamp) -> bytes:
    """One sheet per chapter, with separately typed and stamped tables placed consecutively."""
    validate_chapters(chapters)
    sections = tuple(s for chapter in chapters for s in chapter.tables)
    contents = ReportData(
        (
            Column("chapter", "Chapter", "text"),
            Column("title", "Table", "text"),
            Column("status", "Status", "text"),
            Column("source_run", "Source run", "code"),
            Column("source_sha256", "Source output SHA-256", "code"),
            Column("rows", "Rows", "integer"),
            Column("worksheet", "Worksheet", "text"),
        ),
        tuple(
            {
                "row_key": section.key,
                "chapter": chapter.title,
                "title": section.title,
                "status": "Omitted" if section.omitted else "Included",
                "source_run": section.stamp.report_run_no,
                "source_sha256": section.stamp.output_sha256,
                "rows": section.data.row_count,
                "worksheet": sheet_name(f"{index:02d} {chapter.title}"),
            }
            for index, chapter in enumerate(chapters, start=1)
            for section in chapter.tables
        ),
        {
            "chapters": len(chapters),
            "tables": len(sections),
            "omitted_tables": sum(s.omitted for s in sections),
        },
    )
    buffer = io.BytesIO()
    with xlsxwriter.Workbook(
        buffer,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_numbers": False,
            "strings_to_urls": False,
        },
    ) as workbook:
        workbook.set_properties(
            {
                "title": f"{stamp.report_name} v{stamp.report_version}",
                "subject": stamp.report_run_no,
                "created": _naive_utc(stamp.run_at),
            }
        )
        formats = _Formats(workbook, stamp.negative_number_style)
        _grid(workbook.add_worksheet("Contents"), formats, contents, stamp)
        for index, chapter in enumerate(chapters, start=1):
            sheet = workbook.add_worksheet(sheet_name(f"{index:02d} {chapter.title}"))
            row = 0
            for section in chapter.tables:
                row = _grid(
                    sheet,
                    formats,
                    section.data,
                    section.stamp,
                    (chapter.title, section.title, *section.notes),
                    start_row=row,
                    freeze=row == 0,
                )
    return buffer.getvalue()
