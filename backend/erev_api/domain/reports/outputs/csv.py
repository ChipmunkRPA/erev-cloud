"""CSV outputs (SCREENS_B RV-07, RPT-R-02, RPT-R-03; DESIGN_SYSTEM DS-FMT-25; 03 REQ-RPT-024,
REQ-SEC-011; BUILD_SPEC RPS-2).

One header row of the ``layout`` headers, then one line per row, CRLF-terminated UTF-8 without a
byte order mark. Values are raw (DS-FMT-25): money amounts as signed decimal strings with a
hyphen-minus and no grouping, integers without grouping, dates ``YYYY-MM-DD``, timestamps RFC 3339
UTC, flags ``true`` or ``false``, code lists joined with ", ". Text cells pass the formula guard;
numeric cells never do. ``canonical`` is the same text before the guard — the machine value a frozen
lock snapshot stores (RPS-SNAP A4 13.1); ``cell`` = ``canonical`` + the guard for the text kinds.
The run's JSON manifest travels beside the file (``manifest.py``).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Final

from erev_api.domain.reports.outputs import (
    NOT_SHOWN,
    Column,
    LayoutPart,
    ReportData,
    layout,
    utc_text,
)
from erev_api.domain.reports.outputs.sanitise import guard

MEDIA_TYPE: Final = "text/csv"
EXTENSION: Final = "csv"
LINE_TERMINATOR: Final = "\r\n"


# the kinds whose text is a machine value (DS-FMT-25 / DS-FMT-26): never guarded
MACHINE_KINDS: Final = frozenset({"money", "integer", "decimal", "date", "timestamp", "boolean"})


def canonical(column: Column, part: LayoutPart, value: Any) -> str:
    """The DS-FMT-25 text of one cell WITHOUT the spreadsheet formula guard: the canonical value a
    machine reader compares (RPS-SNAP A4 13.1 — the frozen lock-snapshot cells; identity is the
    admitted value itself). ``cell`` is this text with the guard applied for the text kinds.
    A cell that is not shown (``NOT_SHOWN``) is written as an empty one."""
    if value is None or value is NOT_SHOWN:
        return ""
    if part == "currency":
        return str(value["currency"])
    match column.kind:
        case "money":
            return str(value["amount"])
        case "integer":
            return str(int(value))
        case "decimal":
            return str(value)
        case "date":
            return str(value.isoformat())
        case "timestamp":
            return utc_text(value)
        case "boolean":
            return "true" if value else "false"
        case "codes":
            return ", ".join(str(item) for item in value)
        case "actor":
            return str(value["display_name"])
        case _:
            return str(value)


def export_cell(kind: str, text: str) -> str:
    """The export-boundary guard for a frozen text cell of a DECLARED kind (RPS-SNAP A4 13.1;
    Codex 1739 §3 (c)): a machine kind (``MACHINE_KINDS``) is written as stored — a declared money
    cell ``-5.00`` follows the numeric branch — every other kind, and an undeclared one, passes the
    formula guard, so a code id ``-1`` stays text and is guarded. The frozen bytes are never
    changed; this is the served copy."""
    return text if kind in MACHINE_KINDS else guard(text)


def cell(column: Column, part: LayoutPart, value: Any) -> str:
    """The DS-FMT-25 text of one cell as a spreadsheet export writes it: ``canonical`` with the
    formula guard on the text kinds (REQ-SEC-011); numeric, date, timestamp and boolean cells never
    pass the guard."""
    text = canonical(column, part, value)
    if value is None or (part != "currency" and column.kind in MACHINE_KINDS):
        return text
    return guard(text)


def render_csv(data: ReportData) -> bytes:
    """The CSV bytes of ``data``."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=LINE_TERMINATOR)
    columns = layout(data)
    writer.writerow([guard(item.header) for item in columns])
    for row in data.rows:
        writer.writerow(
            [cell(item.column, item.part, row.get(item.column.key)) for item in columns]
        )
    return buffer.getvalue().encode("utf-8")
