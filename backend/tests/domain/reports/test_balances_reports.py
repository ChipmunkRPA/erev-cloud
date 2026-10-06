"""Revenue waterfall, contract balances and contract balance rollforwards (SCREENS_B §5.6.1 RPT-01
to RPT-04; ENGINE_SPEC_B §15.2.1, §15.2.2, EX-15-B; 04 table 10-T, API-R-49; PRD WLD-K-01,
WLD-X-02, WLD-X-03; 03 REQ-RPT-004 to REQ-RPT-007, REQ-RPT-017; CTL-030; BUILD_SPEC RPS-3).

World: ``support.worlds.k01_pellworth`` (PRD §2.6 and §2.7): AVM-US with FY2026-P01 to P09 open,
K-01 ``SF-ORD-10001`` booked, activated, billed 135,000.00 and computed at the frozen clock
2026-09-12T12:00:00Z. The computation posts the revenue of every open period, so September 2026
holds 9,764.38 (WLD-X-02) and the contract liability is 39,708.49 at 31 Aug 2026 and 29,944.11 at
30 Sep 2026 (WLD-X-03). Report runs play the worker as ``test_framework.py`` does.

R-RC-1 (spec questions under XR-14, not built): ``test_prior_period_obligation_revenue_k06`` with
``revenue_from_prior_period_obligations`` (RPT-05, EDS-4);
``test_rollforward_other_needs_explanation`` (CLO-16); ``test_as_locked_run_reads_snapshot``
(CLO-6); and the K-03 figures of ``test_contract_balances_k01_k03`` (CLO-7). See
docs/reviews/loop/sprint/L6-3.md.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import revenue_from_opening_liability as opening
from erev_api.domain.reports.builders.contract_balance_rollforward import LINES, Flow, path
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.reference import get, slug
from support.worlds import (
    AVM_US,
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    journal_run,
    k01_pellworth,
    recalculated_journal,
    report_run,
    revenue_without_contributors,
)

CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
O1_ROW: Final = f"obligation:{K01}:O1"
K01_BALANCE_ROW: Final = f"contract:{K01}:{AVM_US}"
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
D = Decimal


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def tie(run: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    (found,) = [item for item in run["tie_out_results"] if item["code"] == code]
    return found


@pytest.mark.slow
def test_waterfall_k01_sep_2026(world: ReportWorld) -> None:
    run, rows = report_run(
        world,
        "revenue_waterfall",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "from_period_key": "FY2026-P01",
            "to_period_key": "FY2026-P12",
            "as_of": "2026-09-30",
            "row_dimension": "OBLIGATION",
        },
    )
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    o1 = found[O1_ROW]
    assert (o1["contract_external_id"], o1["obligation_key"], o1["product_code"]) == (
        K01,
        "O1",
        "AVM-PLAT-ENT",
    )
    assert o1["period:FY2026-P09"] == usd("9764.38")  # WLD-X-02
    assert o1["period:FY2026-P10"] == usd("10089.86")  # scheduled after the as-of period
    assert (o1["awaiting_trigger"], o1["total"]) == (usd("0.00"), usd("118800.00"))
    assert found[f"obligation:{K01}:O2"]["period:FY2026-P02"] == usd("9720.00")
    assert found["TOTAL:USD"]["total"] == usd("135000.00")
    assert run["control_totals"] == {
        "recognized_total": {"USD": "105055.89"},  # WLD-X-03 cumulative revenue at 30 Sep 2026
        "scheduled_total": {"USD": "29944.11"},
        "awaiting_trigger_total": {"USD": "0.00"},
    }
    explained = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": O1_ROW, "column_key": "period:FY2026-P09"},
    )
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert body["value"] == usd("9764.38")
    assert body["contributors"]["next_cursor"] is None
    items = body["contributors"]["items"]
    schedule_lines = [item for item in items if item["object_type"] == "schedule_line"]
    assert [(item["measure"], item["value"]) for item in schedule_lines] == [
        ("amount", usd("9764.38"))
    ]
    assert [item["value"] for item in items if item["object_type"] == "subledger_line"] == [
        usd("-9764.38")
    ]
    # SB-R-07: a contributor opens its own explanation.
    opened = get(world.app, schedule_lines[0]["href"], world.maya)
    assert opened.status_code == 200, opened.text
    assert opened.json()["value"] == usd("9764.38")
    unknown = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": "obligation:SF-ORD-99999:O9", "column_key": "period:FY2026-P09"},
    )
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    by_contract = keyed(report_run(world, "revenue_waterfall", SEPTEMBER)[1])
    assert by_contract[f"contract:{K01}"]["period:FY2026-P09"] == usd("9764.38")


@pytest.mark.slow
@pytest.mark.control("CTL-030")
def test_ctl_030_waterfall_ties_to_journal_revenue(world: ReportWorld) -> None:
    first = journal_run(world)
    assert first["totals"]["credit_functional"] == usd("9764.38")
    run, _ = report_run(world, "revenue_waterfall", SEPTEMBER)
    assert tie(run, tie_outs.TO_WATERFALL_EQ_JE_REVENUE) == {
        "code": "TO_WATERFALL_EQ_JE_REVENUE",
        "result": "PASS",
        "expected": [usd("9764.38")],
        "actual": [usd("9764.38")],
        "difference": [usd("0.00")],
    }
    revenue_without_contributors(world, "250.00")
    second = recalculated_journal(world, first)
    assert second["totals"]["credit_functional"] == usd("10014.38")
    run, _ = report_run(world, "revenue_waterfall", SEPTEMBER)
    assert tie(run, tie_outs.TO_WATERFALL_EQ_JE_REVENUE) == {
        "code": "TO_WATERFALL_EQ_JE_REVENUE",
        "result": "FAIL",
        "expected": [usd("10014.38")],
        "actual": [usd("9764.38")],
        # [J] D-88 L7-3-Q-3: actual − expected, filled when the run is serialised.
        "difference": [usd("-250.00")],
    }
    restricted, _ = report_run(
        world, "revenue_waterfall", {**SEPTEMBER, "contract_external_id": K01}
    )
    assert tie(restricted, tie_outs.TO_WATERFALL_EQ_JE_REVENUE)["result"] == "NOT_APPLICABLE"


@pytest.mark.slow
def test_contract_balances_k01_k03(world: ReportWorld) -> None:
    for period_key, liability in (("FY2026-P08", "39708.49"), ("FY2026-P09", "29944.11")):
        run, rows = report_run(
            world,
            "contract_balances",
            {"entity_codes": [AVM_US], "book": "ASC606", "period_key": period_key},
        )
        row = keyed(rows)[K01_BALANCE_ROW]
        assert (row["contract_external_id"], row["entity_code"], row["customer_name"]) == (
            K01,
            AVM_US,
            "Pellworth Logistics Inc. (Demo)",
        )
        assert row["contract_liability"] == usd(liability)  # WLD-X-03
        assert (row["contract_asset"], row["unbilled_receivable"]) == (usd("0.00"), usd("0.00"))
        assert row["refund_liability"] == usd("0.00")  # its own column, never netted (POL-127)
        assert run["control_totals"]["contract_liability"] == {"USD": liability}
        assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD)["result"] == "PASS"
        assert tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "NOT_APPLICABLE"


@pytest.mark.slow
def test_rollforward_k01_sep_2026(world: ReportWorld) -> None:
    run, rows = report_run(world, "contract_balance_rollforward", SEPTEMBER)
    found = keyed(rows)
    assert [(line, found[line]["contract_liability"]["amount"]) for line in LINES] == [
        ("OPENING", "39708.49"),
        ("BILLINGS", "0.00"),
        ("REVENUE_FROM_OPENING", "-9764.38"),
        ("REVENUE_FROM_PERIOD_BILLINGS", "0.00"),
        ("RECLASSIFICATIONS", "0.00"),
        ("FX_REMEASUREMENT", "0.00"),
        ("BUSINESS_COMBINATIONS", "0.00"),
        ("OTHER", "0.00"),
        ("CLOSING", "29944.11"),
    ]
    assert found["OPENING"]["line_label"] == "Opening balance"
    by_contract = found[K01_BALANCE_ROW]
    assert (by_contract["section"], by_contract["opening"], by_contract["closing"]) == (
        2,
        usd("39708.49"),
        usd("29944.11"),
    )
    assert by_contract["revenue_from_opening"] == usd("-9764.38")
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"
    assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD) == {
        "code": "TO_BALANCES_EQ_ROLLFORWARD",
        "result": "PASS",
        "expected": [usd("29944.11")],
        "actual": [usd("29944.11")],
        "difference": [usd("0.00")],
    }
    assert tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "NOT_APPLICABLE"


@pytest.mark.slow
def test_revenue_from_opening_liability_k01(world: ReportWorld) -> None:
    run, rows = report_run(world, "revenue_from_opening_liability", SEPTEMBER)
    found = keyed(rows)
    row = found[K01_BALANCE_ROW]
    assert (
        row["section"],
        row["opening_contract_liability"],
        row["revenue_recognized"],
        row["revenue_from_opening"],
    ) == (2, usd("39708.49"), usd("9764.38"), usd("9764.38"))
    summary = found["summary:USD"]
    assert (summary["section"], summary["revenue_from_opening"]) == (1, usd("9764.38"))
    assert run["control_totals"]["footnote"] == (
        "Measured first-in first-out within each contract "
        "(accounting.rollforward.opening_liability_consumption = FIFO_WITHIN_CONTRACT)."
    )


def test_opening_liability_footnote_names_applied_option() -> None:
    """D-87 L6-3-Q-23: the footnote names the option applied, FIFO_WITHIN_CONTRACT; an entity that
    resolves FIFO_WITHIN_POB adds that per-obligation consumption is not yet available."""
    assert opening.footnote(["FIFO_WITHIN_CONTRACT"]) == (
        "Measured first-in first-out within each contract "
        "(accounting.rollforward.opening_liability_consumption = FIFO_WITHIN_CONTRACT)."
    )
    assert opening.footnote(["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"]) == (
        "Measured first-in first-out within each contract (FIFO_WITHIN_CONTRACT applied). The "
        "policy accounting.rollforward.opening_liability_consumption names FIFO_WITHIN_POB; "
        "per-obligation consumption is not yet available."
    )


def test_rollforward_path_ex_15_b() -> None:
    """ENGINE_SPEC_B EX-15-B: opening liability 5,000.00; 10 Apr delivery revenue 8,000.00; 20 Apr
    invoice 4,000.00; 25 Apr catch-up 200.00; 30 Apr time-elapsed revenue 600.00."""
    flows = [Flow(D("8000.00"), True), Flow(D("-4000.00"), False), Flow(D("200.00"), True)]
    flows.append(Flow(D("600.00"), True))
    opening = {
        "contract_liability": D("5000.00"),
        "contract_asset": D(0),
        "unbilled_receivable": D(0),
    }
    closing = {
        "contract_liability": D("200.00"),
        "contract_asset": D(0),
        "unbilled_receivable": D(0),
    }
    lines = path(opening, flows, closing)
    liability = {line: lines[line]["contract_liability"] for line in LINES}
    asset = {line: lines[line]["contract_asset"] for line in LINES}
    assert (liability["REVENUE_FROM_OPENING"], liability["BILLINGS"]) == (
        D("-5000.00"),
        D("1000.00"),
    )
    assert (liability["REVENUE_FROM_PERIOD_BILLINGS"], liability["OTHER"]) == (D("-800.00"), D(0))
    assert (asset["REVENUE_FROM_PERIOD_BILLINGS"], asset["BILLINGS"], asset["OTHER"]) == (
        D("3000.00"),
        D("-3000.00"),
        D(0),
    )
    for balance in ("contract_liability", "contract_asset", "unbilled_receivable"):
        assert sum(lines[line][balance] for line in LINES if line != "CLOSING") == closing[balance]
    # An unexplained difference is shown as OTHER (S15-R-07).
    shifted = path(opening, flows, {**closing, "contract_liability": D("150.00")})
    assert shifted["OTHER"]["contract_liability"] == D("-50.00")
