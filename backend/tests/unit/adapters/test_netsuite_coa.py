"""DIN-14, CPU only: the NetSuite chart-of-accounts mock, the ``NETSUITE`` GL adapter's chart and
dimension pulls, and the pure ``coa_sync`` planner (05 ADP-12, ADP-20 to ADP-23; 03 REQ-INT-008;
PRD J-23.7; BUILD_SPEC DIN-14). The acceptance figures (1100, 2100 and a new 4050; the name of
2100 updated; an absent account deactivated, never deleted; department values) are asserted here
on the plan; the ``COA_SYNC`` run that applies a plan, the ``sync_run`` ledger and the
``/integrations/{id}/sync`` route are tested in ``tests/domain/integrations/test_coa_sync.py``.
The adapter's journal posting and trial balance (BUILD_SPEC CLO-15) are tested in
``test_gl_adapters.py``; until that item the adapter refused them by name, and the test that
pinned the refusal went with it."""

from __future__ import annotations

import pytest
from erev_api.adapters.gl import netsuite
from erev_api.adapters.mocks import admin
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.domain.integrations import coa_sync
from erev_api.domain.journals import ports
from fastapi import FastAPI
from support.http import asgi_client

MOCKS = "/api/v1/__mocks__"
CONTEXT = ports.GLContext(tenant_code="quayside", accounts=())


def mock_app() -> FastAPI:
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={ns_mock.CODE: ns_mock.NetSuiteMock()}, faults=admin.Faults()
    )
    for router in (admin.router, ns_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    return app


def adapter(app: FastAPI, sleeps: list[float]) -> netsuite.NetSuiteGl:
    return netsuite.NetSuiteGl(
        CONTEXT, client=asgi_client(app), base_url=f"{MOCKS}{ns_mock.PREFIX}", sleep=sleeps.append
    )


def queue_fault(app: FastAPI, route: str, kind: str, count: int = 1) -> None:
    with asgi_client(app) as client:
        response = client.post(
            f"{MOCKS}/__admin/faults", json={"route": route, "kind": kind, "count": count}
        )
        assert response.status_code == 201, response.text


WORKSPACE = (
    coa_sync.WorkspaceAccount("1100", "Cash", "ASSET", "D", True, "NETSUITE", external_id="101"),
    coa_sync.WorkspaceAccount(
        "2100", "Deferred revenue", "LIABILITY", "C", True, "NETSUITE", "102"
    ),
    coa_sync.WorkspaceAccount("2200", "Old accrual", "LIABILITY", "C", True, "NETSUITE", "199"),
    coa_sync.WorkspaceAccount("6000", "Manual expense", "EXPENSE", "D", True, "MANUAL_UI"),
)


def test_chart_pull_answers_account_refs_in_number_order() -> None:
    sleeps: list[float] = []
    gl = adapter(mock_app(), sleeps)
    chart = gl.pull_chart_of_accounts()
    assert [(a.code, a.name) for a in chart] == [
        ("1100", "Cash"),
        ("2100", "Deferred revenue - current"),
        ("4050", "Platform subscription revenue"),
    ]
    erp = gl.pull_erp_accounts()
    assert [(a.code, a.account_type, a.normal_balance, a.external_id) for a in erp] == [
        ("1100", "ASSET", "D", "101"),
        ("2100", "LIABILITY", "C", "102"),
        ("4050", "REVENUE", "C", "103"),
    ]
    checked = gl.validate_accounts([ports.AccountRef("4050", ""), ports.AccountRef("9999", "")], [])
    assert checked.errors == ("Account 9999 is not in the NetSuite chart of accounts.",)
    assert sleeps == []


def test_rate_limit_and_server_error_are_retried_on_the_adp12_schedule() -> None:
    app = mock_app()
    sleeps: list[float] = []
    gl = adapter(app, sleeps)
    queue_fault(app, f"{ns_mock.PREFIX}/record/v1/account", "RATE_LIMIT")
    queue_fault(app, f"{ns_mock.PREFIX}/record/v1/account", "SERVER_ERROR")
    assert len(gl.pull_chart_of_accounts()) == 3
    assert [status for _, status in gl.attempts] == [429, 500, 200]
    assert sleeps == [30.0, 60.0]
    queue_fault(app, f"{ns_mock.PREFIX}/record/v1/account", "PERMANENT_ERROR")
    with pytest.raises(ports.Permanent):
        gl.pull_chart_of_accounts()


def test_dimension_values_are_pulled_with_their_activity() -> None:
    values = adapter(mock_app(), []).pull_dimension_values("department")
    assert [(v.code, v.is_active, v.external_id) for v in values] == [
        ("Customer Success", True, "12"),
        ("Legacy Services", False, "13"),
        ("Sales", True, "11"),
    ]


def test_plan_chart_sync_inserts_renames_deactivates_and_never_deletes() -> None:
    """DIN-14 acceptance on the plan: 4050 inserted with source_system NETSUITE, 2100 renamed, the
    workspace's ERP-origin 2200 absent from the chart deactivated (never deleted), the manual
    6000 untouched, 1100 unchanged; mappings bind codes to ERP record ids."""
    erp = tuple(
        coa_sync.ErpAccountInput(
            a.external_id, a.code, a.name, a.account_type, a.normal_balance, a.is_active
        )
        for a in adapter(mock_app(), []).pull_erp_accounts()
    )
    plan = coa_sync.plan_chart_sync(erp, WORKSPACE)
    assert [(a.code, a.name) for a in plan.inserts] == [("4050", "Platform subscription revenue")]
    assert plan.renames == (("2100", "Deferred revenue", "Deferred revenue - current"),)
    assert plan.deactivations == ("2200",)
    assert plan.unchanged == ("1100",)
    assert plan.mappings == (coa_sync.MappingRow("gl_account", "4050", "103"),)
    assert plan.conflicts == () and plan.is_noop is False
    assert coa_sync.SOURCE_SYSTEM == "NETSUITE"
    # Replanning after the plan is applied is a no-op (idempotent sync).
    applied = (
        coa_sync.WorkspaceAccount("1100", "Cash", "ASSET", "D", True, "NETSUITE", "101"),
        coa_sync.WorkspaceAccount(
            "2100", "Deferred revenue - current", "LIABILITY", "C", True, "NETSUITE", "102"
        ),
        coa_sync.WorkspaceAccount(
            "2200", "Old accrual", "LIABILITY", "C", False, "NETSUITE", "199"
        ),
        coa_sync.WorkspaceAccount(
            "4050", "Platform subscription revenue", "REVENUE", "C", True, "NETSUITE", "103"
        ),
        coa_sync.WorkspaceAccount("6000", "Manual expense", "EXPENSE", "D", True, "MANUAL_UI"),
    )
    again = coa_sync.plan_chart_sync(erp, applied)
    assert again.is_noop and again.unchanged == ("1100", "2100", "4050")


def test_plan_chart_sync_reports_a_type_conflict_and_reactivates() -> None:
    erp = (
        coa_sync.ErpAccountInput("101", "1100", "Cash", "ASSET", "D"),
        coa_sync.ErpAccountInput("105", "6000", "Expense", "EXPENSE", "D"),
        coa_sync.ErpAccountInput(
            "106", "3000", "Retained earnings", "EQUITY", "C", is_active=False
        ),
    )
    workspace = (
        coa_sync.WorkspaceAccount("1100", "Cash", "ASSET", "D", False, "NETSUITE", "101"),
        coa_sync.WorkspaceAccount("6000", "Expense", "REVENUE", "C", True, "MANUAL_UI"),
    )
    plan = coa_sync.plan_chart_sync(erp, workspace)
    assert plan.reactivations == ("1100",)
    assert plan.conflicts == ("6000: workspace REVENUE/C vs ERP EXPENSE/D",)
    assert plan.inserts == ()  # an inactive ERP account is never inserted


def test_plan_dimension_sync_for_departments() -> None:
    values = adapter(mock_app(), []).pull_dimension_values("department")
    erp = tuple(coa_sync.ErpValueInput(v.external_id, v.code, v.name, v.is_active) for v in values)
    plan = coa_sync.plan_dimension_sync(
        "department", erp, (coa_sync.WorkspaceValue("Sales", "Sales", True, "11"),)
    )
    assert plan.dimension_code == "department"
    assert [v.code for v in plan.inserts] == [
        "Customer Success"
    ]  # inactive Legacy Services is not inserted
    assert plan.unchanged == ("Sales",) and plan.deactivations == ()
    assert plan.mappings == (coa_sync.MappingRow("dimension_value", "Customer Success", "12"),)


def test_factory_binds_client_and_base_url() -> None:
    app = mock_app()
    build = netsuite.netsuite_factory(asgi_client(app), f"{MOCKS}{ns_mock.PREFIX}")
    gl = build(CONTEXT)
    assert gl.code == "NETSUITE" and len(gl.pull_chart_of_accounts()) == 3
