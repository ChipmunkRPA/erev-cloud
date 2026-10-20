"""Forecast downloads preserve five schemas, signed numeric values and safe text."""

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import openpyxl
import pytest
from erev_api.domain.reports.forecast_capture import Captured, Section
from erev_api.domain.reports.forecast_exports import Identity, render
from erev_api.domain.reports.outputs import Column, ReportData, RunStamp
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.problems import Problem


def fixture() -> tuple[Captured, Identity, RunStamp]:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    period = PeriodRef(
        uuid4(), "FY2026-P10", "Oct 2026", 2026, 10, 4, date(2026, 10, 1), date(2026, 10, 31)
    )
    data = ReportData(
        (Column("contract", "Contract", "code"), Column("amount", "Amount", "money")),
        (
            {
                "row_key": "one",
                "contract": "=1+1",
                "amount": {"amount": "-123.45", "currency": "USD"},
            },
        ),
        {},
    )
    captured = Captured(
        tuple(
            Section(key, title, data)
            for key, title in (
                ("revenue", "Forecast revenue by period"),
                ("billing", "Forecast billing by period"),
                ("balances", "Projected contract balances"),
                ("rpo", "Projected remaining performance obligations"),
                ("journals", "Journal preview"),
            )
        ),
        {},
        {uuid4(): (period,)},
        ("US",),
        "ASC606",
        now,
        "JSON",
    )
    identity = Identity(uuid4(), "Q4 outlook", uuid4(), "Q4 base", 2, "a" * 64)
    stamp = RunStamp(
        "forecast_outputs",
        "Forecast outputs",
        1,
        "RPT-FC-1",
        {},
        ("US",),
        "ASC606",
        "2026-10-31",
        "Scenario",
        "1.0",
        "abc",
        "Maya",
        now,
        "",
    )
    return captured, identity, stamp


def test_json_and_csv_keep_sections_and_verifiable_file_manifest() -> None:
    captured, identity, stamp = fixture()
    json_result = render(captured, identity, stamp, format="JSON")
    data = json.loads(json_result.content)
    assert len(data["sections"]) == 5
    assert data["event_set"]["version"] == 2
    assert data["horizon_periods"] == ["FY2026-P10"]
    assert json_result.dataset_sha256 == hashlib.sha256(json_result.content).hexdigest()
    output = render(replace(captured, output_format="CSV"), identity, stamp, format="CSV")
    assert (
        render(replace(captured, output_format="CSV"), identity, stamp, format="CSV").content
        == output.content
    )
    with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
        metadata = json.loads(archive.read("manifest.json"))
        assert metadata["dataset_sha256"] == json_result.dataset_sha256
        assert len(metadata["files"]) == 5 and len(archive.namelist()) == 6
        for item in metadata["files"]:
            content = archive.read(item["file"]["name"])
            assert item["sha256"] == hashlib.sha256(content).hexdigest()
            assert b"'=1+1" in content and b"-123.45" in content and b"USD" in content


def test_xlsx_preserves_metadata_numeric_money_and_literal_contract_text() -> None:
    captured, identity, stamp = fixture()
    output = render(replace(captured, output_format="XLSX"), identity, stamp, format="XLSX")
    book = openpyxl.load_workbook(io.BytesIO(output.content))
    assert len(book.worksheets) == 6 and book.sheetnames[0] == "Contents"
    for sheet in book.worksheets[1:]:
        cells = [cell for row in sheet for cell in row]
        values = [cell.value for cell in cells]
        assert "Scenario Q4 outlook" in values
        assert "Event set Q4 base v2" in values
        assert "Horizon FY2026-P10 – FY2026-P10" in values
        assert "RPT-FC-1" in values and output.dataset_sha256 in values
        assert -123.45 in values and "'=1+1" in values
        assert all(cell.data_type != "f" and cell.hyperlink is None for cell in cells)
        assert sheet.freeze_panes is not None


def test_export_refuses_wrong_scope_incomplete_sections_and_visibility_change() -> None:
    captured, identity, stamp = fixture()
    for invalid in (replace(stamp, book="IFRS15"), replace(stamp, entity_codes=("DE",))):
        with pytest.raises(Problem, match="scope"):
            render(captured, identity, invalid, format="JSON")
    with pytest.raises(Problem, match="scope"):
        render(replace(captured, sections=captured.sections[:4]), identity, stamp, format="JSON")
    with pytest.raises(Problem, match="Recapture"):
        render(replace(captured, output_format="XLSX"), identity, stamp, format="JSON")
    with pytest.raises(Problem, match="supports"):
        render(captured, identity, stamp, format="PDF")


def test_saved_forecast_dataset_pages_through_report_data_endpoint(monkeypatch) -> None:
    from erev_api.api.lists import ListParams
    from erev_api.api.v1 import reports
    from fastapi import Response

    captured, identity, stamp = fixture()
    data = json.loads(render(captured, identity, stamp, format="JSON").content)
    monkeypatch.setattr(reports.framework, "run_document", lambda *args, **kwargs: data)
    from types import SimpleNamespace

    deps = SimpleNamespace(files=None, keyring=None)
    params = ListParams(limit=1, cursor=None, sort=None, q=None, count=True, filters={})
    run_id = uuid4()
    index = reports.report_runs_data(run_id, Response(), None, deps, params)
    assert len(index.sections) == 5 and index.next_cursor
    assert index.forecast.scenario_name == "Q4 outlook"
    assert index.forecast.event_set_version == 2
    rows = reports.report_runs_data(run_id, Response(), None, deps, params, "billing")
    assert rows.items[0].row_key == "one"
    assert [column.key for column in rows.columns] == ["contract", "amount"]
    with pytest.raises(Problem):
        reports.report_runs_data(
            run_id, Response(), None, deps, replace(params, cursor=index.next_cursor), "billing"
        )


def test_catalogue_decodes_all_saved_sections_without_recapturing() -> None:
    from erev_api.domain.reports.forecast_catalogue_sources import sections

    captured, identity, stamp = fixture()
    document = json.loads(render(captured, identity, stamp, format="JSON").dataset)
    decoded = sections(document)
    assert decoded == captured.sections


@pytest.mark.parametrize("corruption", ["missing_section", "changed_billing", "changed_index"])
def test_catalogue_refuses_incomplete_or_changed_saved_sections(corruption) -> None:
    from erev_api.domain.reports.forecast_catalogue_sources import sections

    captured, identity, stamp = fixture()
    document = json.loads(render(captured, identity, stamp, format="JSON").dataset)
    if corruption == "missing_section":
        document["sections"].pop()
    elif corruption == "changed_billing":
        document["sections"][1]["tables"][0]["dataset"]["rows"][0]["amount"]["amount"] = "0.00"
    else:
        document["rows"][0]["rows"] += 1
    with pytest.raises(Problem, match="verification"):
        sections(document)
