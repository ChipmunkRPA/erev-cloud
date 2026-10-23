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
from uuid import UUID

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
from support.principals import carrying, enrolled
from support.reference import assign, get, post, slug
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
    run_now,
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


@pytest.mark.slow
def test_rollforward_compares_uploaded_gl_role_balances(
    world: ReportWorld, clock: FrozenClock
) -> None:
    from support import reconciliations as recon

    draft = recon.generated(
        world.app,
        world.maya,
        world.runtime,
        entity_code=AVM_US,
        period_key=SEPTEMBER_2026,
        kind=recon.SUBLEDGER_TO_GL,
        book="ASC606",
    )
    file_id = recon.uploaded(
        world.app,
        world.maya,
        "rollforward-tb.csv",
        recon.trial_balance_csv(
            [
                ("2100", "USD", "-29944.11"),
                ("1200", "USD", "0"),
                ("1105", "USD", "0"),
            ]
        ),
    )
    recon.attached(world.app, world.maya, world.runtime, draft["id"], {"file_id": file_id})
    pending, _ = report_run(world, "contract_balance_rollforward", SEPTEMBER)
    assert tie(pending, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "NOT_APPLICABLE"
    assign(world.priya.member, "revenue_reviewer")
    world = carrying(world, maya=enrolled(world.app, clock, world.maya.member))
    for item in recon.items_of(world.app, world.maya, draft["id"]):
        explained = recon.explain(
            world.app,
            world.maya,
            item,
            "This focused trial balance includes the three contract balance roles only.",
        )
        assert explained.status_code == 200, explained.text
    prepared = recon.prepare(world.app, world.maya, draft["id"])
    assert prepared.status_code == 200, prepared.text
    signed = recon.sign(world.app, world.priya, draft["id"])
    assert signed.status_code == 200, signed.text
    accepted_runs = []
    for code, parameters in (
        ("contract_balance_rollforward", SEPTEMBER),
        (
            "contract_balances",
            {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026},
        ),
    ):
        run, _ = report_run(world, code, parameters)
        result = tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)
        assert result["result"] == "PASS", result["details"]
        assert len(result["details"]) == 3
        assert result["details"][0]["reconciliation_id"] == draft["id"]
        assert all(row["bridge_result"] == "PASS" for row in result["details"])
        assert all(D(row["subledger_gl_difference"]) == 0 for row in result["details"])
        assert all(D(row["report_subledger_difference"]) == 0 for row in result["details"])
        accepted_runs.append(run)
    reopened = recon.reopen(world.app, world.marcus, draft["id"], "Updated GL needs review")
    assert reopened.status_code == 200, reopened.text
    current, _ = report_run(world, "contract_balance_rollforward", SEPTEMBER)
    assert tie(current, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "NOT_APPLICABLE"
    for retained in (pending, *accepted_runs):
        restarted = post(world.app, f"/api/v1/report-runs/{retained['id']}/rerun", world.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = run_now(world, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        rebuilt = get(
            world.app,
            f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}",
            world.maya,
        )
        assert rebuilt.status_code == 200, rebuilt.text
        assert tie(rebuilt.json(), tie_outs.TO_ROLLFORWARD_EQ_GL) == tie(
            retained, tie_outs.TO_ROLLFORWARD_EQ_GL
        )


@pytest.mark.slow
def test_foreign_contract_balances_use_dated_functional_targets(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from support import close_run_worlds
    from support import close_runs as runs
    from support import reconciliations as recon

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root)
    )
    for period_key in ("FY2026-P08", "FY2026-P09"):
        closed = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=period_key)
        assert closed["status"] == "SUCCEEDED"
        world = runs.journal_posted(world, clock, closed["journal_run_id"])
    for period_key, expected in (("FY2026-P08", "11050.00"), ("FY2026-P09", "11200.00")):
        draft = recon.generated(
            app,
            world.maya,
            world.runtime,
            entity_code=AVM_US,
            period_key=period_key,
            kind=recon.SUBLEDGER_TO_GL,
            book="ASC606",
        )
        file_id = recon.uploaded(
            app,
            world.maya,
            f"functional-{period_key}.csv",
            recon.trial_balance_csv(
                [
                    ("1105", "USD", expected),
                    ("2100", "USD", "0"),
                    ("4010", "USD", "-11000.00"),
                    ("7200", "USD", str(D("11000") - D(expected))),
                ]
            ),
        )
        reconciled = recon.attached(
            app, world.maya, world.runtime, draft["id"], {"file_id": file_id}
        )
        assert reconciled["variance_count"] == 0
        if period_key == "FY2026-P08":
            world = carrying(world, maya=enrolled(app, clock, world.maya.member))
        prepared = recon.prepare(app, world.maya, draft["id"])
        assert prepared.status_code == 200, prepared.text
        signed = recon.sign(app, world.priya, draft["id"])
        assert signed.status_code == 200, signed.text
        params = {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "period_key": period_key,
            "currency_view": "functional",
        }
        run, rows = report_run(world, "contract_balances", params)
        row = keyed(rows)[f"contract:{close_run_worlds.EUR_CONTRACT}:{AVM_US}"]
        assert row["unbilled_receivable"] == usd(expected)
        assert row["currency"] == "USD"
        assert tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "PASS"
        assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD)["result"] == "PASS"
        movement_run, movement_rows = report_run(
            world,
            "contract_balance_rollforward",
            {
                "entity_codes": [AVM_US],
                "book": "ASC606",
                "currency_view": "functional",
                "from_period_key": period_key,
                "to_period_key": period_key,
            },
        )
        movement = keyed(movement_rows)
        assert movement["CLOSING"]["unbilled_receivable"] == usd(expected)
        fx = movement["FX_REMEASUREMENT"]
        assert sum(
            D(fx[role]["amount"])
            for role in ("contract_liability", "contract_asset", "unbilled_receivable")
        ) == (D("50") if period_key.endswith("08") else D("150"))
        assert tie(movement_run, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"
        assert tie(movement_run, tie_outs.TO_ROLLFORWARD_EQ_GL)["result"] == "PASS"
        assert tie(movement_run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD)["result"] == "PASS"

        _, txn = report_run(world, "contract_balances", {**params, "currency_view": "transaction"})
        assert keyed(txn)[row["row_key"]]["unbilled_receivable"] == {
            "amount": "10000.00",
            "currency": "EUR",
        }


@pytest.mark.slow
@pytest.mark.parametrize("currency_view", ["functional", "reporting"])
def test_functional_balance_reads_locked_endpoint_and_reruns(
    currency_view: str,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    from support import close_run_worlds, worlds
    from support.reference import post

    world, _ = close_run_worlds.august_locked(
        app, keyring, clock, LocalFileStore(app_settings.file_root), monkeypatch
    )
    run, rows = report_run(
        world,
        "contract_balances",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "period_key": "FY2026-P08",
            "currency_view": currency_view,
        },
    )
    row = keyed(rows)[f"contract:{close_run_worlds.EUR_CONTRACT}:{AVM_US}"]
    assert row["unbilled_receivable"] == usd("11050.00")
    movement, movement_rows = report_run(
        world,
        "contract_balance_rollforward",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "currency_view": currency_view,
            "from_period_key": "FY2026-P08",
            "to_period_key": "FY2026-P08",
        },
    )
    assert keyed(movement_rows)["CLOSING"]["unbilled_receivable"] == usd("11050.00")
    assert tie(movement, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"
    started = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    finished = worlds.run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    repeated = get(
        app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["items"] == rows


@pytest.mark.slow
@pytest.mark.parametrize("billing_mode", ["ERP", "ENGINE"])
def test_functional_rollforward_invoice_uses_layer_carrying(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    billing_mode: str,
) -> None:
    from datetime import date
    from uuid import UUID

    from erev_api.db.tables import contract
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn
    from erev_api.money import MoneyIn
    from sqlalchemy import select
    from support import close_run_worlds
    from support import close_runs as runs
    from support.factories import appended, computed

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root)
    )
    if billing_mode == "ENGINE":
        from erev_api.db.session import DbContext, tenant_session
        from erev_api.enums import RegistryCategory, RegistryScope
        from support.rows import publish_registry_version

        with tenant_session(
            DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        ) as session:
            publish_registry_version(
                session,
                tenant_id=world.tenant_id,
                category=RegistryCategory.ACCOUNTING_POLICY,
                scope=RegistryScope.ENTITY,
                entity_id=world.entity_id,
                values={"billing.posting": "ENGINE"},
                at=clock.now(),
            )
    held = world.contracts[close_run_worlds.EUR_CONTRACT]
    identity = UUID(str(held.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == identity)
    )
    day = date(2026, 9, 15)
    appended(
        world.place,
        identity,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=day,
                payload=BillingRecordedV1(
                    invoice_number="EUR-INVOICE",
                    line_external_id="EUR-INVOICE-1",
                    obligation_key="O1",
                    issue_date=day,
                    amount=MoneyIn(amount="10000.00", currency="EUR"),
                ),
            )
        ],
    )
    computed(world.place, UUID(str(held.combination_group["id"])))
    for key in ("FY2026-P08", "FY2026-P09"):
        closed = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=key)
        assert closed["status"] == "SUCCEEDED"
        world = runs.journal_posted(world, clock, closed["journal_run_id"])
    run, rows = report_run(
        world,
        "contract_balance_rollforward",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "currency_view": "functional",
            "from_period_key": "FY2026-P09",
            "to_period_key": "FY2026-P09",
        },
    )
    figures = keyed(rows)
    assert figures["OPENING"]["unbilled_receivable"] == usd("11050.00")
    spot = D(close_run_worlds.EUR_SEPTEMBER[0]) * 10000
    assert figures["BILLINGS"]["unbilled_receivable"] == usd(f"{-spot:.2f}")
    assert figures["FX_REMEASUREMENT"]["unbilled_receivable"] == usd(f"{spot - D('11050'):.2f}")
    assert figures["CLOSING"]["unbilled_receivable"] == usd("0.00")
    from erev_api.db.tables import report_run as report_run_table
    from erev_api.domain.reports.builders import SourceBinding

    binding = SourceBinding.from_stored(
        world.place.scalar(
            select(report_run_table.c.source_binding).where(
                report_run_table.c.id == UUID(run["id"])
            )
        )
    )
    assert binding is not None
    event_sources = binding.evidence["event_posted_fx_v1"]
    assert event_sources
    assert all(item["evidence"] for item in event_sources.values())
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"

    from support import worlds
    from support.reference import post

    started = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    finished = worlds.run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    repeated = get(
        app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["items"] == rows


@pytest.mark.slow
def test_reporting_balances_translate_and_pin_closing_rates(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    from datetime import timedelta
    from uuid import UUID

    from support import close_run_worlds, worlds
    from support.reference import approve, post

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root), reporting_currency="EUR"
    )
    listed = get(app, "/api/v1/fx-rate-sets", world.maya, {"limit": 50})
    assert listed.status_code == 200, listed.text
    (closing_set,) = [
        item for item in listed.json()["items"] if item["code"] == "AVM-RATES-CLOSING"
    ]

    def publish(rate: str) -> None:
        draft = post(
            app,
            f"/api/v1/fx-rate-sets/{closing_set['id']}/versions",
            world.maya,
            {
                "coverage_from": "2026-08-01",
                "coverage_to": "2026-08-31",
                "rates": [
                    {
                        "base_currency": "USD",
                        "quote_currency": "EUR",
                        "period_key": "FY2026-P08",
                        "rate": rate,
                    }
                ],
            },
        )
        assert draft.status_code == 201, draft.text
        submitted = post(
            app,
            f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
            world.maya,
            {"comment": "Reporting rate"},
            if_match=f'"r{draft.json()["row_version"]}"',
        )
        assert submitted.status_code == 200, submitted.text
        clock.advance(timedelta(minutes=1))
        decided = approve(app, submitted.json()["pending_approval_request_id"], world.marcus)
        assert decided.status_code == 200, decided.text

    publish("0.900001")
    params = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "period_key": "FY2026-P08",
        "currency_view": "reporting",
    }
    run, rows = report_run(world, "contract_balances", params)
    row = keyed(rows)[f"contract:{close_run_worlds.EUR_CONTRACT}:{AVM_US}"]
    assert row["unbilled_receivable"] == {"amount": "9945.01", "currency": "EUR"}
    assert row["functional_currency"] == "USD"
    assert D(row["closing_fx_rate"]) == D("0.900001")
    assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD)["result"] == "PASS"
    publish("0.8")
    _, fresh_rows = report_run(world, "contract_balances", params)
    assert keyed(fresh_rows)[row["row_key"]]["unbilled_receivable"] == {
        "amount": "8840.00",
        "currency": "EUR",
    }
    started = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    finished = worlds.run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    repeated = get(
        app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["items"] == rows


@pytest.mark.slow
def test_reporting_rollforward_translates_each_period_and_reruns(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import UUID

    from support import close_run_worlds, worlds
    from support import close_runs as runs
    from support.reference import post

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root), reporting_currency="EUR"
    )
    for period_key in ("FY2026-P08", "FY2026-P09"):
        closed = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=period_key)
        assert closed["status"] == "SUCCEEDED"
        world = runs.journal_posted(world, clock, closed["journal_run_id"])
    params = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "currency_view": "reporting",
        "from_period_key": "FY2026-P08",
        "to_period_key": "FY2026-P09",
        "balance_role": "UNBILLED_RECEIVABLE",
    }
    run, rows = report_run(world, "contract_balance_rollforward", params)
    by_key = keyed(rows)
    assert by_key["OPENING"]["unbilled_receivable"] == {"currency": "EUR", "amount": "0.00"}
    assert by_key["CLOSING"]["unbilled_receivable"] == {"currency": "EUR", "amount": "10000.00"}
    assert sum(
        D(by_key["FX_REMEASUREMENT"][role]["amount"])
        for role in ("contract_liability", "contract_asset", "unbilled_receivable")
    ) == D("180.59")
    assert by_key["TRANSLATION"]["unbilled_receivable"] == {"currency": "EUR", "amount": "-180.59"}
    contract_row = by_key[f"contract:{close_run_worlds.EUR_CONTRACT}:{AVM_US}"]
    assert contract_row["translation"] == by_key["TRANSLATION"]["unbilled_receivable"]
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"
    assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD)["result"] == "PASS"
    # A newly published closing rate changes live reporting, not the retained source run.
    world = close_run_worlds.closing_rates(world, clock, {"FY2026-P09": "1.25"})
    _, fresh = report_run(world, "contract_balance_rollforward", params)
    assert keyed(fresh)["CLOSING"]["unbilled_receivable"] == {
        "currency": "EUR",
        "amount": "8960.00",
    }
    started = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    finished = worlds.run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    repeated = get(
        app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["items"] == rows


def test_reporting_months_preserve_range_opening_liability() -> None:
    from datetime import date
    from uuid import UUID

    from erev_api.domain.reports.builders.contract_balance_rollforward import (
        LIABILITY,
        Entry,
        period_paths,
    )

    august = tie_outs.PeriodRef(
        UUID(int=8),
        "FY2026-P08",
        "August",
        2026,
        8,
        3,
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    september = tie_outs.PeriodRef(
        UUID(int=9),
        "FY2026-P09",
        "September",
        2026,
        9,
        3,
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    months = period_paths(
        {LIABILITY: D("100")},
        [
            Entry((august.end,), Flow(D("-100"), False, "BILLING"), august.id),
            Entry((september.end,), Flow(D("150"), True, "REVENUE"), september.id),
        ],
        [(august, {LIABILITY: D("200")}), (september, {LIABILITY: D("50")})],
    )
    assert months[august.id]["BILLINGS"][LIABILITY] == D("100")
    assert months[september.id]["OPENING"][LIABILITY] == D("200")
    assert months[september.id]["REVENUE_FROM_OPENING"][LIABILITY] == D("-100")
    assert months[september.id]["REVENUE_FROM_PERIOD_BILLINGS"][LIABILITY] == D("-50")
    assert months[september.id]["CLOSING"][LIABILITY] == D("50")


@pytest.mark.slow
def test_foreign_aging_uses_remeasured_functional_shares_and_retains_dates(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    from support import close_run_worlds

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root)
    )
    for period_key, expected, bucket in (
        ("FY2026-P08", "11050.00", "bucket_0_30"),
        ("FY2026-P09", "11200.00", "bucket_0_30"),
    ):
        params = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": period_key}
        _, original = report_run(world, "balance_aging", params)
        (source,) = [row for row in original if row["row_key"].startswith("contract:")]
        assert source["total"] == {"currency": "EUR", "amount": "10000.00"}
        for view in ("functional", "reporting"):
            run, rows = report_run(world, "balance_aging", {**params, "currency_view": view})
            (row,) = [row for row in rows if row["row_key"].startswith("contract:")]
            assert row[bucket] == row["total"] == {"currency": "USD", "amount": expected}
            assert run["tie_out_results"][0]["result"] == "PASS"
            restarted = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
            assert restarted.status_code == 202, restarted.text
            complete = run_now(world, UUID(restarted.json()["id"]))
            assert complete["state"] == "SUCCEEDED", complete
            rebuilt = get(
                world.app,
                f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}",
                world.maya,
            )
            assert rebuilt.status_code == 200, rebuilt.text
            assert rebuilt.json()["control_totals"] == run["control_totals"]


@pytest.mark.slow
def test_priced_right_to_invoice_advance_billing_keeps_performance_and_aging(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    from datetime import date

    from erev_api.db.tables import contract, subledger_line
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn
    from sqlalchemy import func, select
    from support import close_run_worlds
    from support.factories import appended, computed

    world = close_run_worlds.eur_receivable(
        app, keyring, clock, LocalFileStore(app_settings.file_root)
    )
    booked = world.contracts[close_run_worlds.EUR_CONTRACT]
    contract_id = UUID(str(booked.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=day,
                payload=BillingRecordedV1.model_validate(
                    {
                        "invoice_number": f"RTI-ADV-{day}",
                        "line_external_id": f"RTI-ADV-{day}-1",
                        "obligation_key": "O1",
                        "amount": {"amount": amount, "currency": "EUR"},
                        "issue_date": day.isoformat(),
                    }
                ),
            )
            for day, amount in ((date(2026, 8, 1), "15000.00"), (date(2026, 9, 1), "5000.00"))
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    assert world.place.scalar(
        select(func.sum(subledger_line.c.amount_txn)).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.book_code == "ASC606",
            subledger_line.c.account_role == "REVENUE",
        )
    ) == D("-10000.00")
    params = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P09"}
    run, rows = report_run(world, "balance_aging", {**params, "currency_view": "functional"})
    (row,) = [item for item in rows if item["row_key"].startswith("contract:")]
    assert row["balance_role"] == "Contract liability"
    assert row["bucket_31_90"] == {"currency": "USD", "amount": "5500.00"}
    assert row["bucket_0_30"] == {"currency": "USD", "amount": "5550.00"}
    assert row["total"] == {"currency": "USD", "amount": "11050.00"}
    assert run["tie_out_results"][0]["result"] == "PASS"


@pytest.mark.slow
def test_historical_gl_never_falls_back_after_latest_source_changes(
    world: ReportWorld, clock: FrozenClock
) -> None:
    from datetime import timedelta

    from support import reconciliations as recon
    from support.record_clock import on_record_time

    world = on_record_time(world)
    assign(world.priya.member, "revenue_reviewer")
    world = carrying(world, maya=enrolled(world.app, clock, world.maya.member))
    file_id = recon.uploaded(
        world.app,
        world.maya,
        "historical-gl.csv",
        recon.trial_balance_csv(
            [
                ("2100", "USD", "-29944.11"),
                ("1200", "USD", "0"),
                ("1105", "USD", "0"),
            ]
        ),
    )

    def reviewed() -> dict[str, Any]:
        draft = recon.generated(
            world.app,
            world.maya,
            world.runtime,
            entity_code=AVM_US,
            period_key=SEPTEMBER_2026,
            kind=recon.SUBLEDGER_TO_GL,
            book="ASC606",
        )
        recon.attached(world.app, world.maya, world.runtime, draft["id"], {"file_id": file_id})
        for item in recon.items_of(world.app, world.maya, draft["id"]):
            response = recon.explain(
                world.app, world.maya, item, "Three balance roles in this trial balance."
            )
            assert response.status_code == 200, response.text
        prepared = recon.prepare(world.app, world.maya, draft["id"])
        assert prepared.status_code == 200, prepared.text
        signed = recon.sign(world.app, world.priya, draft["id"])
        assert signed.status_code == 200, signed.text
        return draft

    older = reviewed()
    clock.advance(timedelta(minutes=1))
    latest = reviewed()
    assert latest["id"] != older["id"]
    cutoff = clock.now().isoformat()
    selectors = (
        ("contract_balance_rollforward", SEPTEMBER),
        (
            "contract_balances",
            {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026},
        ),
    )
    accepted = []
    for code, parameters in selectors:
        run, _ = report_run(world, code, {**parameters, "known_at": cutoff})
        result = tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)
        assert result["result"] == "PASS", result
        assert result["details"][0]["reconciliation_id"] == latest["id"]
        accepted.append(run)
    clock.advance(timedelta(minutes=1))
    reopened = recon.reopen(world.app, world.marcus, latest["id"], "Review a later GL revision")
    assert reopened.status_code == 200, reopened.text
    unavailable = []
    for code, parameters in selectors:
        run, _ = report_run(world, code, {**parameters, "known_at": cutoff})
        result = tie(run, tie_outs.TO_ROLLFORWARD_EQ_GL)
        assert result["result"] == "NOT_APPLICABLE", result
        (detail,) = result["details"]
        assert detail["reconciliation_id"] == latest["id"]
        assert "changed after the report cutoff" in detail["reason"]
        assert "source_status" not in detail and "gl" not in detail
        unavailable.append(run)
    # Previously captured accepted evidence stays accepted; new unavailable evidence stays so.
    for retained in (*accepted, *unavailable):
        restarted = post(world.app, f"/api/v1/report-runs/{retained['id']}/rerun", world.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = run_now(world, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        rebuilt = get(
            world.app,
            f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}",
            world.maya,
        )
        assert rebuilt.status_code == 200, rebuilt.text
        assert tie(rebuilt.json(), tie_outs.TO_ROLLFORWARD_EQ_GL) == tie(
            retained, tie_outs.TO_ROLLFORWARD_EQ_GL
        )


@pytest.mark.slow
def test_opening_liability_pob_public_report_and_retained_rerun(world, monkeypatch):
    from types import SimpleNamespace
    from erev_api.domain.reports import opening_consumption_policy as policy

    monkeypatch.setattr(policy, "resolve", lambda *a, **k: SimpleNamespace(value="FIFO_WITHIN_POB"))
    run, rows = report_run(world, "revenue_from_opening_liability", SEPTEMBER)
    row = keyed(rows)[K01_BALANCE_ROW]
    assert row["revenue_from_opening"] == usd("9764.38")
    assert "FIFO_WITHIN_POB uses each obligation" in run["control_totals"]["footnote"]

    def changed_policy(*args, **kwargs):
        raise AssertionError("A bound rerun must not consult current policy")

    monkeypatch.setattr(policy, "resolve", changed_policy)
    restarted = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert restarted.status_code == 202, restarted.text
    complete = run_now(world, UUID(restarted.json()["id"]))
    assert complete["state"] == "SUCCEEDED", complete
    rebuilt = get(
        world.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}", world.maya
    )
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["control_totals"] == run["control_totals"]


@pytest.mark.slow
def test_opening_pob_uses_locked_source_versions(app, keyring, clock, app_settings, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import select
    from support import close_run_worlds, worlds
    from erev_api.db.tables import report_run as report_run_table
    from erev_api.domain.reports import opening_consumption_policy as policy
    from erev_api.domain.reports.builders import SourceBinding

    world, _ = close_run_worlds.august_locked(
        app, keyring, clock, LocalFileStore(app_settings.file_root), monkeypatch
    )
    worlds._appended_through_api(
        world.place,
        UUID(str(world.contracts[close_run_worlds.EUR_CONTRACT].contract["id"])),
        {
            "event_type": "MEMO_UPDATED",
            "effective_date": "2026-09-15",
            "payload": {"memo_1": "Post-lock version for original opening evidence verification"},
        },
    )
    world = worlds.on_record_clock(world, clock)
    monkeypatch.setattr(policy, "resolve", lambda *a, **k: SimpleNamespace(value="FIFO_WITHIN_POB"))
    run, rows = report_run(world, "revenue_from_opening_liability", SEPTEMBER)
    binding = SourceBinding.from_stored(
        world.place.scalar(
            select(report_run_table.c.source_binding).where(
                report_run_table.c.id == UUID(run["id"])
            )
        )
    )
    assert binding is not None
    facts = binding.evidence["opening_relief_pob_v1"]
    assert facts
    for item in facts.values():
        saved = item["frozen_opening"]
        original = world.place.scalar(
            select(report_run_table.c.source_binding).where(
                report_run_table.c.id == UUID(saved["source_run_id"])
            )
        )
        assert saved["version"] in original["versions"]["ASC606"]
        assert saved["version"] != item["version"]
        assert D(item["relief"]) <= D(item["opening_cap"])
    monkeypatch.setattr(
        policy,
        "resolve",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Frozen rerun consulted current policy")
        ),
    )
    restarted = post(world.app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert restarted.status_code == 202, restarted.text
    complete = run_now(world, UUID(restarted.json()["id"]))
    assert complete["state"] == "SUCCEEDED", complete
    rebuilt = get(
        world.app,
        f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data",
        world.maya,
    )
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["items"] == rows
