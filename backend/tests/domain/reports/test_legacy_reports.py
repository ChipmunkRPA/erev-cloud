"""Contract history, latest status, legacy exports and the legacy journal summary (SCREENS_B §5.6.2
RPT-09 to RPT-12, §5.6.3 RPT-13; 04 §17.1, §17.2; D-12, D-33; legacy 06 §7.3 TC-REP-01 to TC-REP-07,
TC-JE-11; PRD J-15.8, J-21.6, WLD-X-26, WLD-X-28; POLICIES CHK-020; 03 REQ-RPT-012, REQ-RPT-013,
REQ-SEC-006, REQ-JE-008; BUILD_SPEC RPS-5).

Worlds, each committed once per module in its own tenant through ``support.parity.scenario`` (the
legacy UAT replay of DG-PAR-04; the tenant code keeps the worlds apart, L6-3-Q-38):

- ``shipped``: golden steps 01 to 04, the legacy "Shipped" state (SSPs, setup 1.1 and 2.1, delivery
  1.31).
- ``je11``: the shipped state and the TC-JE-11 uploads: Contract 2 POB #2 delivery of 1 unit dated
  2023-03-31, committed first, then Contract 2 POB #1 billing 500.00 dated 2023-02-28.
- ``final``: golden steps 01 to 14, the "Full UAT" final state (WLD-X-28).

The January journals read ``shipped`` (L7-1-Q-4): dae887a resolves the SKU revenue accounts, and the
parity world posts Contract 2's JET-06 reclass through ``support/parity/netting.py`` (L7-1-Q-6 (a))
until CLO-20.

Report runs play the worker as ``support.worlds.report_run`` does, as ak-preparer (Revenue
Accountant: ``report.run`` and ``report.export``).
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.config import Settings, get_settings
from erev_api.domain.reports.legacy_columns import NAMES, POSITION_CONTRACT_LEVEL
from support.db import TestDatabase
from support.factories import run_import_job, workbook_bytes
from support.legacy_replay import ENTITIES, LegacyWorld, committed
from support.parity import scenario
from support.parity.scenario import ParityScenario
from support.reference import get, post
from support.worlds import REPORT_RUN_ID_HEADER

pytestmark = pytest.mark.slow

REPORT_RUNS: Final = "/api/v1/report-runs"
ASC606: Final = "ASC606"
C1: Final = "Contract 1"
C2: Final = "Contract 2"
C3: Final = "Contract 3"
C4: Final = "Contract 4"
SHIPPED_STEP: Final = "04"
FINAL_STEP: Final = "14"
HISTORY: Final = "contract_history"
LEGACY_HISTORY: Final = "legacy_contract_history_export"
LATEST: Final = "latest_contract_status"
LEGACY_LATEST: Final = "legacy_latest_contract_export"
JE_SUMMARY: Final = "legacy_je_summary"
CONTRACT_NAME: Final = NAMES[0]
POB_ID: Final = NAMES[1]
CURRENT_PERIOD: Final = NAMES[12]
BILLING_CUM: Final = NAMES[62]
REVENUE_CUM: Final = NAMES[60]
TIME_LOG: Final = NAMES[68]
JANUARY: Final = {
    "entity_codes": list(ENTITIES),
    "book": ASC606,
    "from_date": "2023-01-01",
    "to_date": "2023-01-31",
}
PROGRESS_TEMPLATE: Final = "legacy_progress_tracking"
PROGRESS_HEADERS: Final = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Current Delivery",
    "Current Billing",
    "Current Pre-ASC606 Revenue (Net Design Only)",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
# Legacy 06 TC-JE-11, in processing order.
TC_JE_11_UPLOADS: Final = (
    (
        "TC-JE-11 progress 3.31.2023.xlsx",
        "2023-03-31",
        (C2, "POB #2", "Software 1", 1, 0, 0, "TC-JE-11", "Delivery", "03.31.23"),
    ),
    (
        "TC-JE-11 progress 2.28.2023.xlsx",
        "2023-02-28",
        (C2, "POB #1", "Hardware 1", 0, 500, 0, "TC-JE-11", "Billing", "02.28.23"),
    ),
)

type Rows = list[dict[str, Any]]


def _settings(tmp_path_factory: pytest.TempPathFactory, name: str) -> Settings:
    root: Path = tmp_path_factory.mktemp(name)
    return get_settings().model_copy(update={"file_root": root})


def _replayed(
    tmp_path_factory: pytest.TempPathFactory, keyring: KeyRing, name: str, step: str
) -> ParityScenario:
    built = scenario.build(_settings(tmp_path_factory, name), keyring, tenant_code=f"rps-5-{name}")
    built.through(step)
    return built


@pytest.fixture(scope="module")
def shipped(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> ParityScenario:
    del test_database  # the session's migrated database, which the world commits to
    return _replayed(tmp_path_factory, keyring, "shipped", SHIPPED_STEP)


@pytest.fixture(scope="module")
def je11(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> ParityScenario:
    del test_database
    built = _replayed(tmp_path_factory, keyring, "tc-je-11", SHIPPED_STEP)
    for name, effective_date, row in TC_JE_11_UPLOADS:
        done = committed(
            built.advance(),
            name,
            workbook_bytes("Sheet1", PROGRESS_HEADERS, [row]),
            PROGRESS_TEMPLATE,
            {"effective_date": effective_date},
        )
        assert done["status"] == "COMMITTED", done
    return built


@pytest.fixture(scope="module")
def final(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> ParityScenario:
    del test_database
    return _replayed(tmp_path_factory, keyring, "final", FINAL_STEP)


def _run(
    world: LegacyWorld,
    code: str,
    parameters: Mapping[str, Any],
    *,
    output_format: str = "JSON",
) -> tuple[dict[str, Any], Rows]:
    """``POST /report-runs``, the job run as the worker does, then API-S-ReportRun and, for a JSON
    run, its data rows."""
    started = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {"report_code": code, "parameters": dict(parameters), "output_format": output_format},
    )
    assert started.status_code == 202, started.text
    run_import_job(world.imports, UUID(str(started.json()["id"])))
    run_id = started.headers[REPORT_RUN_ID_HEADER]
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    run = dict(shown.json())
    assert run["status"] == "SUCCEEDED", run
    rows: Rows = []
    if output_format == "JSON":
        listed = get(world.app, f"{REPORT_RUNS}/{run_id}/data", world.maya, {"limit": "200"})
        assert listed.status_code == 200, listed.text
        rows = list(listed.json()["items"])
    return run, rows


def _legacy_shape(rows: Sequence[Mapping[str, Any]]) -> None:
    """Each row carries exactly its row key and the 71 legacy names. The run data are the stored
    canonical dataset, whose object keys are sorted; the CSV header proves the legacy order."""
    for row in rows:
        assert sorted(row) == sorted(["row_key", *NAMES]), sorted(row)


def _section(rows: Sequence[Mapping[str, Any]], section: str) -> Rows:
    return [dict(row) for row in rows if row["section"] == section]


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def test_tc_rep_01_history_january(shipped: ParityScenario) -> None:
    run, rows = _run(shipped.world, LEGACY_HISTORY, JANUARY)
    assert (run["row_count"], len(rows)) == (16, 16)
    _legacy_shape(rows)
    assert len(NAMES) == 71
    # Setup versions dated 2023-01-01 and delivery versions dated 2023-01-31, contract by contract.
    assert Counter(row[CURRENT_PERIOD] for row in rows) == {
        "2023-01-01 00:00:00": 8,
        "2023-01-31 00:00:00": 8,
    }
    assert [(row[CONTRACT_NAME], row[CURRENT_PERIOD]) for row in rows] == [
        (contract, f"2023-01-{day} 00:00:00")
        for contract in (C1, C2)
        for day in ("01", "31")
        for _ in range(4)
    ]
    history, items = _run(shipped.world, HISTORY, JANUARY)
    assert (history["row_count"], history["control_totals"]["contract_count"]) == (16, 2)
    assert [item["row_key"] for item in items[:4]] == [
        f"version:{C1}:1:{key}" for key in ("POB #1", "POB #2", "POB #3", "POB #4")
    ]
    delivered = next(item for item in items if item["row_key"] == f"version:{C1}:2:POB #1")
    assert delivered["effective_date"] == "2023-01-31"
    assert delivered["revenue_cum"] == _usd("128.84")
    assert "DELIVERY_RECORDED" in delivered["cause_event_types"]


def test_tc_rep_02_one_contract(shipped: ParityScenario) -> None:
    parameters = {**JANUARY, "to_date": "2023-12-31", "contract_external_id": C2}
    run, rows = _run(shipped.world, LEGACY_HISTORY, parameters)
    assert run["row_count"] == 8
    assert {row[CONTRACT_NAME] for row in rows} == {C2}
    history, items = _run(shipped.world, HISTORY, parameters)
    assert history["row_count"] == 8
    assert {item["contract_external_id"] for item in items} == {C2}


def test_tc_rep_03_latest_status(shipped: ParityScenario) -> None:
    parameters = {"entity_codes": list(ENTITIES), "book": ASC606, "as_of": "2023-12-31"}
    run, rows = _run(shipped.world, LATEST, parameters)
    assert run["row_count"] == 16
    assert Counter((row["contract_external_id"], row["effective_date"]) for row in rows) == {
        (C1, "2023-01-31"): 4,
        (C2, "2023-01-31"): 4,
        (C3, "2023-02-01"): 4,
        (C4, "2023-02-01"): 4,
    }
    one, found = _run(shipped.world, LATEST, {**parameters, "contract_external_id": C1})
    assert one["row_count"] == 4
    assert [row["row_key"] for row in found] == [
        f"obligation:{C1}:{key}" for key in ("POB #1", "POB #2", "POB #3", "POB #4")
    ]
    legacy, exported = _run(shipped.world, LEGACY_LATEST, parameters)
    assert legacy["row_count"] == 16
    _legacy_shape(exported)


@pytest.mark.parametrize("code", [HISTORY, LEGACY_HISTORY])
def test_tc_rep_04_injection_name(shipped: ParityScenario, code: str) -> None:
    run, rows = _run(
        shipped.world,
        code,
        {**JANUARY, "to_date": "2023-12-31", "contract_external_id": 'x" OR 1=1 OR "x'},
    )
    assert (run["row_count"], rows) == (0, [])


@pytest.mark.parametrize("code", [HISTORY, LEGACY_HISTORY])
def test_tc_rep_05_quote_in_name(shipped: ParityScenario, code: str) -> None:
    run, rows = _run(
        shipped.world,
        code,
        {**JANUARY, "to_date": "2023-12-31", "contract_external_id": 'Contract "1'},
    )
    assert (run["status"], run["problem"], run["row_count"], rows) == ("SUCCEEDED", None, 0, [])


@pytest.mark.parametrize("code", [HISTORY, LEGACY_HISTORY])
def test_tc_rep_06_start_after_end(shipped: ParityScenario, code: str) -> None:
    world = shipped.world
    refused = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {
            "report_code": code,
            "parameters": {**JANUARY, "from_date": "2023-12-31", "to_date": "2023-01-01"},
            "output_format": "JSON",
        },
    )
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert problem["type"].endswith("/validation-failed"), problem
    assert [(item["field"], item["rule_id"]) for item in problem["errors"]] == [
        ("parameters.from_date", "REQ-RPT-012")
    ]


def test_tc_rep_07_latest_as_of(je11: ParityScenario) -> None:
    parameters = {"entity_codes": list(ENTITIES), "book": ASC606, "contract_external_id": C2}
    run, rows = _run(je11.world, LATEST, {**parameters, "as_of": "2023-03-31"})
    assert run["row_count"] == 4
    assert {row["effective_date"] for row in rows} == {"2023-03-31"}
    assert len({row["version_no"] for row in rows}) == 1
    found = {row["obligation_key"]: row for row in rows}
    # The version holds both TC-JE-11 events: the 2023-02-28 billing processed last and the
    # 2023-03-31 delivery.
    assert found["POB #1"]["billed_cum"] == _usd("500.00")
    assert found["POB #2"]["revenue_cum"] == _usd("104.62")
    # As of 2023-02-28 the latest effective version is the January delivery, not the version
    # processed last (legacy: the Feb-dated versions).
    before, earlier = _run(je11.world, LATEST, {**parameters, "as_of": "2023-02-28"})
    assert before["row_count"] == 4
    assert {row["effective_date"] for row in earlier} == {"2023-01-31"}


def test_legacy_header_71_columns(shipped: ParityScenario) -> None:
    run, _ = _run(shipped.world, LEGACY_HISTORY, JANUARY, output_format="CSV")
    output = get(shipped.world.app, run["output"]["href"], shipped.world.maya)
    assert output.status_code == 200, output.text
    header = next(csv.reader(io.StringIO(output.content.decode("utf-8"))))
    assert header == list(NAMES)
    _, rows = _run(shipped.world, LEGACY_HISTORY, JANUARY)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row[CONTRACT_NAME], row[TIME_LOG]), []).append(row)
    for members in groups.values():
        position = sum((Decimal(row[BILLING_CUM]) for row in members), Decimal(0)) - sum(
            (Decimal(row[REVENUE_CUM]) for row in members), Decimal(0)
        )
        assert {Decimal(row[POSITION_CONTRACT_LEVEL]) for row in members} == {position}
    delivered = {
        row[CONTRACT_NAME]: row[POSITION_CONTRACT_LEVEL]
        for row in rows
        if row[CURRENT_PERIOD] == "2023-01-31 00:00:00"
    }
    # Billing − revenue, without inversion, as 04 1.66 §17.1 rule 4 writes LM-CL-67 (D-98
    # candidate 89; integrated batch #7 ci return): the posted billing cumulative (LM-CL-63)
    # minus the EXACT revenue cumulative (LM-CL-61: the row's own trace node value +
    # rounding_residue, exact decimal text, never rounded) — Contract 1 300.00 −
    # 295.688800792864222002; Contract 2 0 − 58.846153846153846154
    assert delivered == {C1: "4.311199207135777998", C2: "-58.846153846153846154"}


def test_legacy_latest_export_final_state(final: ParityScenario) -> None:
    run, rows = _run(
        final.world,
        LEGACY_LATEST,
        {"entity_codes": list(ENTITIES), "book": ASC606, "as_of": "2023-10-31"},
    )
    assert run["row_count"] == 17
    _legacy_shape(rows)
    assert Counter(row[CONTRACT_NAME] for row in rows) == {C1: 4, C2: 4, C3: 5, C4: 4}
    assert {row[POSITION_CONTRACT_LEVEL] for row in rows} == {"0"}
    assert len({(row[CONTRACT_NAME], row[POB_ID]) for row in rows}) == 17


def _by_account(rows: Rows) -> list[tuple[str, str, str]]:
    return [
        (row["account"], row["debit"]["amount"], row["credit"]["amount"])
        for row in _section(rows, "by_account")
    ]


def test_legacy_je_summary_january_gross(shipped: ParityScenario) -> None:
    run, rows = _run(shipped.world, JE_SUMMARY, {**JANUARY, "mode": "GROSS"})
    assert _by_account(rows) == [
        ("5001", "0.00", "187.69"),
        ("5002", "0.00", "118.53"),
        ("5003", "0.00", "48.32"),
        ("15002", "58.85", "0.00"),
        ("21001", "295.69", "0.00"),
    ]
    totals = run["control_totals"]
    assert (totals["mode"], totals["lines"]) == ("GROSS", 6)
    assert (totals["total_debit"], totals["total_credit"], totals["net"]) == (
        {"USD": "354.54"},
        {"USD": "354.54"},
        {"USD": "0.00"},
    )
    assert [
        (row["row_key"], row["debit"]["amount"], row["credit"]["amount"], row["balanced"])
        for row in _section(rows, "by_entity")
    ] == [
        ("entity:Mock Entity 1", "295.69", "295.69", True),
        ("entity:Mock Entity 2", "58.85", "58.85", True),
    ]
    items = {row["row_key"]: row["amount"]["amount"] for row in _section(rows, "line_items")}
    assert items[f"item:{C1}:21001"] == "295.69"
    assert items[f"item:{C2} POB #1 Hardware 1:5001"] == "-58.85"


def test_legacy_je_summary_january_delta(shipped: ParityScenario) -> None:
    run, rows = _run(shipped.world, JE_SUMMARY, {**JANUARY, "mode": "DELTA"})
    assert _by_account(rows) == [
        ("5001", "0.00", "187.69"),
        ("5002", "0.00", "52.53"),
        ("5003", "39.68", "0.00"),
        ("15002", "58.85", "0.00"),
        ("21001", "141.69", "0.00"),
    ]
    totals = run["control_totals"]
    assert (totals["mode"], totals["total_debit"], totals["total_credit"]) == (
        "DELTA",
        {"USD": "240.22"},
        {"USD": "240.22"},
    )
