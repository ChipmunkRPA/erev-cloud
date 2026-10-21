"""GL export evidence remains usable for spreadsheet review and arithmetic."""

import io
from dataclasses import replace

import openpyxl
import pytest
from erev_api.domain.reports.outputs.xlsx import WorkbookSection, render_xlsx, render_xlsx_pack
from tests.unit.reports.test_workbook_pack import DATA, STAMP


@pytest.mark.parametrize("packed", [False, True])
def test_gl_bridge_has_filterable_numeric_evidence_and_blank_unavailable_values(
    packed: bool,
) -> None:
    rows = (
        {
            "entity": "US",
            "role": "CONTRACT_LIABILITY",
            "currency": "USD",
            "gl": "100.00",
            "source_subledger": "120.00",
            "rollforward": "100.00",
            "subledger_gl_difference": "20.00",
            "report_subledger_difference": "-20.00",
            "difference": "0.00",
            "result": "FAIL",
            "bridge_result": "FAIL",
            "source_status": "REVIEWED",
            "reconciliation_id": "reviewed-source",
            "source_revision_id": "original-review-state",
            "source_recorded_at": "2026-10-20T12:00:00+00:00",
            "book_code": "ASC606",
            "period_key": "FY2026-P09",
        },
        {
            "entity": "GB",
            "result": "NOT_APPLICABLE",
            "source_status": "REOPENED",
            "reconciliation_id": "pending-source",
            "reason": "=Pending source review",
        },
        {
            "entity": "JP",
            "role": "CONTRACT_ASSET",
            "currency": "JPY",
            "gl": "100",
            "rollforward": "100",
            "difference": "0",
            "result": "NOT_APPLICABLE",
            "bridge_result": "NOT_APPLICABLE",
            "bridge_reason": "No retained subledger amount.",
        },
    )
    data = replace(
        DATA,
        tie_out_results=(
            {
                "code": "TO_ROLLFORWARD_EQ_GL",
                "result": "FAIL",
                "details": rows,
            },
        ),
    )
    raw = (
        render_xlsx_pack((WorkbookSection("balances", "Balances", data, STAMP),), STAMP)
        if packed
        else render_xlsx(data, STAMP)
    )
    book = openpyxl.load_workbook(io.BytesIO(raw))
    sheet = book.worksheets[-1]
    table = next(iter(sheet.tables.values()))
    assert table.autoFilter is not None
    cells = sheet[table.ref]
    headers = [cell.value for cell in cells[0]]
    records = [dict(zip(headers, row, strict=True)) for row in cells[1:]]
    first, pending, missing = records
    assert first["Subledger minus GL"].value == 20
    assert first["Report minus subledger"].value == -20
    assert first["Report minus GL"].value == 0
    assert first["Bridge result"].value == "FAIL"
    assert first["Reconciliation ID"].value == "reviewed-source"
    assert first["Captured source revision"].value == "original-review-state"
    assert first["Source state captured at"].value == "2026-10-20T12:00:00+00:00"
    assert first["Subledger minus GL"].data_type == "n"
    assert "0.00" in first["Subledger minus GL"].number_format
    assert pending["Source review status"].value == "REOPENED"
    assert pending["GL balance"].value is None
    assert pending["Unavailable reason"].value == "'=Pending source review"
    assert pending["Unavailable reason"].alignment.wrap_text
    assert missing["Retained subledger"].value is None
    assert missing["Bridge unavailable reason"].value == "No retained subledger amount."
    assert all(cell.data_type != "f" for row in cells for cell in row)
