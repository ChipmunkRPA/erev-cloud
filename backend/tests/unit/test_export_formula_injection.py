"""REQ-SEC-011 formula-injection guard on the CSV and XLSX report writers (05 UPL-20, UPL-21;
SCREENS_B RV-07; BUILD_SPEC SOP-8, RPS-2). CPU only."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl
from erev_api.domain.reports.outputs import Column, ReportData, RunStamp
from erev_api.domain.reports.outputs.csv import render_csv
from erev_api.domain.reports.outputs.sanitise import FORMULA_TRIGGERS, guard
from erev_api.domain.reports.outputs.xlsx import render_xlsx

TRIGGERING = ("=SUM(A1)", "+1", "-1", "@x", "\tTab", "\rReturn")
COLUMNS = (
    Column("label", "Label", "text"),
    Column("code", "Code", "code"),
    Column("tags", "Tags", "codes"),
    Column("who", "Who", "actor"),
    Column("amount", "Amount", "money"),
    Column("qty", "Quantity", "integer"),
    Column("ratio", "Ratio", "decimal"),
)


def _rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, text in enumerate(TRIGGERING):
        rows.append(
            {
                "row_key": f"r{index}",
                "label": text,
                "code": text,
                "tags": [text, "safe"],
                "who": {"id": "00000000-0000-4000-8000-000000000001", "display_name": text},
                "amount": {"amount": "-1.00", "currency": "USD"},
                "qty": 7,
                "ratio": "-0.5",
            }
        )
    return tuple(rows)


def _stamp() -> RunStamp:
    return RunStamp(
        report_code="=CMD",
        report_name="+Injected name",
        report_version=1,
        report_run_no="RR-0001",
        parameters={"note": "@param"},
        entity_codes=("US",),
        book="ASC606",
        as_of="2026-09-21",
        source="test",
        engine_version="0.0.0",
        build_sha="0" * 40,
        run_by="-Tomas",
        run_at=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        output_sha256="0" * 64,
    )


def _is_decimal(text: str) -> bool:
    try:
        Decimal(text)
    except InvalidOperation:
        return False
    return True


def test_guard_prefixes_exactly_the_trigger_characters() -> None:
    assert FORMULA_TRIGGERS == ("=", "+", "-", "@", "\t", "\r")
    for text in TRIGGERING:
        assert guard(text) == "'" + text
    for text in ("plain", "1,234.56", "x=1", "a+b", "", " -1"):
        assert guard(text) == text


def test_req_sec_011_prefix() -> None:
    """The CSV and XLSX writers prefix ``=SUM(A1)``, ``+1``, ``-1``, ``@x``, a leading tab and a
    leading carriage return with an apostrophe in every text cell (text, code, codes, actor) and
    keep numeric cells numeric (money, integer, decimal)."""
    data = ReportData(columns=COLUMNS, rows=_rows(), control_totals={})

    parsed = list(csv.reader(io.StringIO(render_csv(data).decode("utf-8"), newline="")))
    header, *body = parsed
    assert header[0] == "Label" and "Amount (USD)" in header
    assert len(body) == len(TRIGGERING)
    for text, row in zip(TRIGGERING, body, strict=True):
        label, code, tags, who, amount, qty, ratio = row
        assert label == "'" + text and code == "'" + text and who == "'" + text
        assert tags == "'" + text + ", safe"
        assert (amount, qty, ratio) == ("-1.00", "7", "-0.5"), "numeric cells stay raw"
    for row in body:
        for cell in row:
            assert not cell.startswith(FORMULA_TRIGGERS) or _is_decimal(cell), cell

    workbook = openpyxl.load_workbook(io.BytesIO(render_xlsx(data, _stamp())), read_only=True)
    strings: list[str] = []
    numbers: list[float] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str):
                    strings.append(value)
                elif isinstance(value, int | float):
                    numbers.append(float(value))
    for text in TRIGGERING:
        # XML normalises a bare carriage return, so the control character may not round-trip;
        # the apostrophe in front of the trigger must.
        assert any(s.startswith("'") and text.strip("\t\r") in s for s in strings), text
    # ``decimal`` columns are decimal strings written as they are, without the guard (RPS-5; the
    # writers' contract): every unguarded string that starts with a trigger must be such a number.
    unguarded = [s for s in strings if s.startswith(FORMULA_TRIGGERS) and not _is_decimal(s)]
    assert unguarded == [], f"text written as a formula trigger: {unguarded!r}"
    assert "-0.5" in strings, "the decimal-kind cell is the raw decimal string"
    assert -1.0 in numbers and 7.0 in numbers, "money and integer cells are numbers"
