"""``COA_SYNC`` pure logic (03 REQ-INT-008; 04 T-INT-02 ``kind``, T-INT-04; 05 §5.2 ``GLAdapter``;
BUILD_SPEC DIN-14) — CPU only: the run-kind rules of ``/sync``, the chart-source registry, the
NetSuite source built from a connection's context, the plan's deactivation rule, the chart totals
and the BUILD_SPEC module path ``adapters/gl/protocol.py``. The database behaviour is in
``tests/domain/integrations/test_coa_sync.py``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from erev_api.adapters.gl import netsuite, protocol
from erev_api.adapters.mocks import admin
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.domain.integrations import coa_sync, commands, ports, sync
from erev_api.domain.journals import ports as gl_ports
from fastapi import FastAPI
from support.http import asgi_client

MOCKS = "/api/v1/__mocks__"


def _connection(adapter: str, **over: Any) -> dict[str, Any]:
    return {"adapter": adapter, "direction": "BOTH", "status": "ACTIVE", "config": {}, **over}


def test_coa_sync_is_a_run_kind_of_a_chart_serving_adapter_only() -> None:
    """04 T-INT-02 ``kind``; 03 REQ-INT-008: ``/sync`` admits ``COA_SYNC`` for NetSuite — the GL
    adapter that serves a chart — and refuses it by name for every other adapter; a NetSuite
    connection runs no inbound kind."""
    assert commands._kind_errors(_connection("NETSUITE"), "COA_SYNC") == []
    for adapter in ("SALESFORCE", "STRIPE", "CSV_GL", "QUICKBOOKS_ONLINE"):
        [refused] = commands._kind_errors(_connection(adapter), "COA_SYNC")
        assert refused.field == "kind" and refused.rule_id == "T-INT-02"
        assert refused.message == commands.KIND_NOT_CHART.format(kind="COA_SYNC", adapter=adapter)
    for kind in ("INBOUND_POLL", "RECONCILIATION_SWEEP", "TRIAL_BALANCE_PULL", "JOURNAL_EXPORT"):
        [refused] = commands._kind_errors(_connection("NETSUITE"), kind)
        assert refused.field == "kind", kind
    assert commands.CHART_KIND == coa_sync.COA_SYNC == "COA_SYNC"
    assert commands.CHART_ADAPTERS == {netsuite.CODE}


def test_chart_source_registry_fails_closed_and_builds_from_the_connection() -> None:
    """DG-LAY-03: a composition root registers the NetSuite chart source; without a registration a
    ``COA_SYNC`` fails closed; the source reads the connection's base URL, client and
    ``config.max_attempts``."""
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={ns_mock.CODE: ns_mock.NetSuiteMock()}, faults=admin.Faults()
    )
    for router in (admin.router, ns_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    context = ports.InboundContext(
        tenant_code="quayside",
        base_url=f"{MOCKS}{ns_mock.PREFIX}",
        config={"max_attempts": 2},
        client=asgi_client(app),
    )
    previous = dict(ports.CHART_SOURCES)
    try:
        ports.CHART_SOURCES.clear()
        with pytest.raises(LookupError, match="NETSUITE"):
            ports.chart_source_for("NETSUITE", context)
        netsuite.register()
        source = ports.chart_source_for("NETSUITE", context)
    finally:
        ports.CHART_SOURCES.clear()
        ports.CHART_SOURCES.update(previous)
    assert isinstance(source, netsuite.NetSuiteGl) and source._max_attempts == 2
    assert [account.code for account in source.pull_erp_accounts()] == ["1100", "2100", "4050"]
    assert [value.code for value in source.pull_dimension_values("department")] == [
        "Customer Success",
        "Legacy Services",
        "Sales",
    ]
    default = netsuite.chart_source(dataclasses.replace(context, config={}))
    assert default._max_attempts == netsuite.MAX_ATTEMPTS


def test_chart_probe_is_a_single_attempt_and_fails_closed() -> None:
    """04 §16.14 rev 1.115 (ruling R-45, point 4): ``sync._probe_chart`` — "Test connection" of a
    chart-serving connection — builds the chart source with ONE attempt whatever the connection's
    ``config.max_attempts`` says, reads the chart once and never waits a backoff; a transient or a
    permanent answer, an empty chart, a connection without a base URL and a root that registered no
    source or no client are FAILUREs, never an error."""
    app = FastAPI()
    mock = ns_mock.NetSuiteMock()
    app.state.mocks = admin.MockWorld(adapters={ns_mock.CODE: mock}, faults=admin.Faults())
    for router in (admin.router, ns_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    base = f"{MOCKS}{ns_mock.PREFIX}"
    route = f"{ns_mock.PREFIX}/record/v1/account"
    target = _connection("NETSUITE", base_url=base, config={"max_attempts": 5})
    slept: list[float] = []
    built: list[netsuite.NetSuiteGl] = []

    def source(context: ports.InboundContext) -> netsuite.NetSuiteGl:
        built.append(netsuite.chart_source(context, sleep=slept.append))
        return built[-1]

    def probe(connection: dict[str, Any] = target) -> sync.ProbeResult:
        return sync._probe_chart(connection, tenant_code="quayside")

    assert commands.CHART_ADAPTERS is ports.CHART_ADAPTERS == frozenset({netsuite.CODE})
    sources = dict(ports.CHART_SOURCES)
    client = sync._HOOKS.get("http")
    try:
        ports.register_chart_source(netsuite.CODE, source)
        sync.register_http_client_factory(lambda base_url: asgi_client(app))
        assert probe() == sync.ProbeResult(
            "SUCCESS", f"NETSUITE reachable at {base}; 3 account(s) in the chart"
        )
        assert built[-1]._max_attempts == 1 and mock.served == ["account:list"]

        app.state.mocks.faults.add(route, admin.FaultKind.RATE_LIMIT, 3)
        assert probe() == sync.ProbeResult("FAILURE", "Transient: HTTP 429")
        assert built[-1].attempts == [("/record/v1/account", 429)] and slept == []
        [queued] = app.state.mocks.faults.snapshot()
        assert queued["remaining"] == 2  # one request was sent
        app.state.mocks.faults.clear()
        app.state.mocks.faults.add(route, admin.FaultKind.PERMANENT_ERROR, 1)
        assert probe() == sync.ProbeResult("FAILURE", "Permanent: HTTP 400")

        mock.scenario = dataclasses.replace(mock.scenario, accounts=())
        assert probe() == sync.ProbeResult(
            "FAILURE", f"NETSUITE at {base} stated an empty chart of accounts"
        )
        assert probe({**target, "base_url": None}) == sync.ProbeResult(
            "FAILURE", "Permanent: the connection has no base_url"
        )
        sync.register_http_client_factory(None)
        assert probe().result == "FAILURE" and probe().detail.startswith("LookupError: no HTTP")
        sync.register_http_client_factory(lambda base_url: asgi_client(app))
        ports.CHART_SOURCES.clear()
        assert probe() == sync.ProbeResult(
            "FAILURE", "LookupError: no chart-of-accounts source is registered for NETSUITE"
        )
    finally:
        ports.CHART_SOURCES.clear()
        ports.CHART_SOURCES.update(sources)
        sync.register_http_client_factory(client)
    assert slept == []


def test_plan_deactivates_what_the_erp_dropped_and_leaves_what_it_never_knew() -> None:
    """DIN-14 "an account absent from the ERP chart is set ``is_active = false`` and never
    deleted": an account the sync created (ERP origin) and one it mapped (a link to an ERP record)
    are the ERP's; a workspace account with neither is not."""
    workspace = (
        coa_sync.WorkspaceAccount("1100", "Cash", "ASSET", "D", True, "MANUAL_UI", "101"),
        coa_sync.WorkspaceAccount("4050", "Platform", "REVENUE", "C", True, "NETSUITE", "103"),
        coa_sync.WorkspaceAccount("6000", "Workspace-only", "EXPENSE", "D", True, "MANUAL_UI"),
        coa_sync.WorkspaceAccount("7000", "Retired before", "EXPENSE", "D", False, "NETSUITE", "9"),
    )
    plan = coa_sync.plan_chart_sync((), workspace)
    assert plan.deactivations == ("1100", "4050")  # 6000 untouched; 7000 is inactive already
    assert plan.inserts == () and plan.mappings == () and plan.conflicts == ()
    # an inactive ERP account the workspace never held is not brought in
    dormant = coa_sync.ErpAccountInput("55", "8000", "Dormant", "EXPENSE", "D", is_active=False)
    assert coa_sync.plan_chart_sync((dormant,), ()).is_noop


def test_chart_totals_and_dimensions_of() -> None:
    """T-INT-02 ``source_totals`` / ``loaded_totals`` of a chart: a count and a digest, no amount;
    equal sets agree whatever their order, and a missing account changes both."""
    rows = [("101", "1100", "Cash", True), ("102", "2100", "Deferred revenue - current", True)]
    totals = coa_sync.chart_totals(rows)
    assert (totals.count, dict(totals.amount_by_currency)) == (2, {})
    assert totals.as_json() == {"count": 2, "amount_by_currency": {}, "sha256": totals.sha256}
    assert coa_sync.chart_totals(list(reversed(rows))).sha256 == totals.sha256
    partial = coa_sync.chart_totals(rows[:1])
    assert ports.compare_totals(totals, partial) == "CONTROL_TOTAL_MISMATCH"
    assert ports.compare_totals(totals, coa_sync.chart_totals(rows)) == "SUCCEEDED"
    assert coa_sync.dimensions_of({"config": {}}) == ("department",)
    assert coa_sync.dimensions_of({"config": None}) == coa_sync.DEFAULT_DIMENSIONS
    assert coa_sync.dimensions_of({"config": {"dimensions": ["class", "department", "class"]}}) == (
        "class",
        "department",
    )
    counts = coa_sync.ChartCounts(fetched=3, accounts_created=1)
    counts.failures.append({"step": coa_sync.REFERENCE_STEP})
    assert counts.as_json()["failures"] == 1 and counts.as_json()["accounts_created"] == 1


def test_gl_protocol_module_is_the_domain_port() -> None:
    """BUILD_SPEC DIN-14 path ``adapters/gl/protocol.py`` (05 §5.2; DG-LAY-03): the protocol is
    the domain port's, re-exported with the trial-balance members, and the NetSuite adapter
    implements it. Posting and the trial balance are built since BUILD_SPEC CLO-15 (they refused
    here by name before): a ledger that cannot be reached is ``Transient``, never a refusal of the
    adapter itself (ADP-12)."""
    assert protocol.GLAdapter is gl_ports.GLAdapter
    assert protocol.ChartSource is ports.ChartSource
    assert protocol.Permanent is gl_ports.Permanent
    assert protocol.TrialBalanceLine is gl_ports.TrialBalanceLine
    assert protocol.TrialBalanceDetail is gl_ports.TrialBalanceDetail
    for name in (
        "validate_accounts",
        "post_chunk",
        "get_posting",
        "pull_chart_of_accounts",
        "pull_trial_balance",
    ):
        assert callable(getattr(netsuite.NetSuiteGl, name)), name
    assert netsuite.NetSuiteGl.code == "NETSUITE"
    gl: gl_ports.GLAdapter = netsuite.NetSuiteGl(
        gl_ports.GLContext(tenant_code="quayside", accounts=()), client=object(), base_url="/m"
    )
    with pytest.raises(gl_ports.Transient, match="connection error"):
        gl.get_posting("erev:quayside:JR-000001:1:1")
