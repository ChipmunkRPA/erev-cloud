"""NetSuite chart-of-accounts sync over a database (03 REQ-INT-008, REQ-REF-007, REQ-REF-009; 04
T-REF-13 ``gl_account``, T-REF-17 ``dimension_value``, T-INT-02 ``kind`` ``COA_SYNC``, T-INT-04
``external_id_map``; 05 §5.2 ``GLAdapter.pull_chart_of_accounts``, ADP-12, ADP-20; PRD J-23.7,
ACT-45; BUILD_SPEC DIN-14 named cases ``test_coa_sync_creates_and_updates_accounts``,
``test_dimension_values_synced``, ``test_inactive_account_deactivated_not_deleted`` and
``test_sync_requires_integration_manage``).

DB-bound: every test needs the test database. World: ``support.integrations`` — the J-23 tenant —
whose chart holds 1100 Cash and 2100 under an older name, both created through ``POST
/gl-accounts``, and an ACTIVE NetSuite connection over the in-process mock (chart 1100, 2100, 4050;
departments Sales, Customer Success and the inactive Legacy Services). The connection carries no
``secret_ref``: a mock connection sends no credential (05 KEY-09).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl import netsuite
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    dimension_definition,
    dimension_value,
    external_id_map,
    gl_account,
    sync_run,
)
from erev_api.domain.integrations import ports
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.integrations import (
    INTEGRATIONS,
    IntegrationWorld,
    connection,
    integration_world,
    queue_fault,
    sync,
)
from support.principals import colleague, enrolled
from support.reference import assign, get, post
from support.reference import gl_account as new_account

MOCK_BASE = f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}"
COA_SYNC = "COA_SYNC"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Iterator[IntegrationWorld]:
    with integration_world(app, keyring, clock, app_settings) as built:

        def backoff(seconds: float) -> None:
            clock.advance(timedelta(seconds=seconds))

        # ADP-12: the chart source's backoff moves the frozen clock instead of sleeping
        ports.register_chart_source(
            netsuite.CODE, lambda context: netsuite.chart_source(context, sleep=backoff)
        )
        try:
            yield built
        finally:
            netsuite.register()  # the composition root's factory (real sleep) for later modules


def _workspace_chart(world: IntegrationWorld) -> None:
    """The chart before the first sync: 1100 as the ERP names it, 2100 under its older name."""
    new_account(world.app, world.nikhil, code="1100", name="Cash")
    new_account(
        world.app,
        world.nikhil,
        code="2100",
        name="Deferred revenue",
        account_type="LIABILITY",
        normal_balance="C",
    )


def _netsuite(world: IntegrationWorld, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "netsuite-quayside",
        "name": "NetSuite (mock)",
        "adapter": "NETSUITE",
        "direction": "BOTH",
        "base_url": MOCK_BASE,
    }
    body.update(over)
    return connection(world, **body)


def _mock(world: IntegrationWorld) -> ns_mock.NetSuiteMock:
    adapter = world.app.state.mocks.adapters[ns_mock.CODE]
    assert isinstance(adapter, ns_mock.NetSuiteMock)
    return adapter


def _accounts(world: IntegrationWorld) -> dict[str, dict[str, Any]]:
    return {str(row["code"]): row for row in world.rows(select(gl_account))}


def _links(world: IntegrationWorld, object_type: str) -> dict[str, dict[str, Any]]:
    """The live T-INT-04 links of ``object_type`` by ERP record id."""
    rows = world.rows(
        select(external_id_map).where(
            external_id_map.c.object_type == object_type, external_id_map.c.valid_to.is_(None)
        )
    )
    return {str(row["external_id"]): row for row in rows}


def test_coa_sync_creates_and_updates_accounts(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-14 / 03 REQ-INT-008, REQ-REF-007: a ``COA_SYNC`` over the mock chart holding
    1100, 2100 and a new 4050 inserts 4050 with ``source_system = NETSUITE``, updates the name of
    2100, maps each account in ``external_id_map`` (``object_type = gl_account``) and records
    ``sync_run.record_count = 3``."""
    _workspace_chart(world)
    target = _netsuite(world)
    before = _accounts(world)
    assert sorted(before) == ["1100", "2100"]
    queue_fault(world, f"{ns_mock.PREFIX}/record/v1/account", "RATE_LIMIT")  # retried (ADP-12)

    row, finished = sync(world, target, kind=COA_SYNC)

    assert (row["kind"], row["status"]) == (COA_SYNC, "SUCCEEDED"), row["problem"]
    assert row["record_count"] == 3 and row["exception_count"] == 0 and row["problem"] is None
    assert row["source_totals"]["count"] == 3 == row["loaded_totals"]["count"]
    assert row["source_totals"]["sha256"] == row["loaded_totals"]["sha256"]
    assert row["source_totals"]["amount_by_currency"] == {}  # a chart carries no amount
    assert row["checkpoint_after"] == row["checkpoint_before"]  # a chart sync moves no checkpoint
    assert finished["state"] == "SUCCEEDED" and finished["result"]["kind"] == COA_SYNC
    counts = finished["result"]["counts"]
    assert counts["fetched"] == 3 and counts["failures"] == 0 and counts["conflicts"] == 0
    assert (counts["accounts_created"], counts["accounts_renamed"]) == (1, 1)
    # 1100 keeps its name and gains its link, so no account is "unchanged" by the first sync
    assert (counts["accounts_unchanged"], counts["accounts_mapped"]) == (0, 3)
    assert (counts["accounts_deactivated"], counts["accounts_reactivated"]) == (0, 0)

    chart = _accounts(world)
    assert sorted(chart) == ["1100", "2100", "4050"]
    created = chart["4050"]
    assert (
        created["name"],
        created["account_type"],
        created["normal_balance"],
        created["source_system"],
        created["is_active"],
    ) == ("Platform subscription revenue", "REVENUE", "C", "NETSUITE", True)
    assert created["entity_ids"] == [] and created["required_dimensions"] == []
    assert created["created_by_kind"] == "SYSTEM"
    renamed = chart["2100"]
    assert renamed["name"] == "Deferred revenue - current"  # was "Deferred revenue"
    assert renamed["id"] == before["2100"]["id"] and renamed["row_version"] == 2
    assert renamed["source_system"] == before["2100"]["source_system"] == "MANUAL_UI"
    assert renamed["updated_by_kind"] == "SYSTEM"
    assert chart["1100"]["row_version"] == 1 and chart["1100"]["name"] == "Cash"  # unchanged

    links = _links(world, "gl_account")
    assert {external: link["internal_id"] for external, link in links.items()} == {
        "101": chart["1100"]["id"],
        "102": chart["2100"]["id"],
        "103": chart["4050"]["id"],
    }
    assert all(
        link["integration_connection_id"] == UUID(target["id"]) and link["sync_run_id"] == row["id"]
        for link in links.values()
    )

    # every change is the reference command's: validated and audited as a person's would be
    actions = [
        (event["action"], event["actor_kind"])
        for event in world.rows(
            select(audit_event)
            .where(audit_event.c.object_type == "gl_account")
            .order_by(audit_event.c.chain_seq)
        )
    ]
    assert actions[-2:] == [("gl_account.create", "SYSTEM"), ("gl_account.update", "SYSTEM")]
    shown = get(world.app, f"/api/v1/gl-accounts/{created['id']}", world.nikhil)
    assert shown.status_code == 200 and shown.json()["source_system"] == "NETSUITE"
    assert _mock(world).served.count("account:list") == 1  # the 429 was retried, then one read

    # a second sync over the unchanged chart changes nothing (idempotent)
    again, again_job = sync(world, target, kind=COA_SYNC)
    assert again["status"] == "SUCCEEDED" and again["record_count"] == 3
    repeat = again_job["result"]["counts"]
    assert (repeat["accounts_created"], repeat["accounts_renamed"], repeat["accounts_mapped"]) == (
        0,
        0,
        0,
    )
    assert repeat["accounts_unchanged"] == 3
    assert {code: a["row_version"] for code, a in _accounts(world).items()} == {
        "1100": 1,
        "2100": 2,
        "4050": 1,
    }
    assert sorted(_links(world, "gl_account")) == ["101", "102", "103"]


def test_dimension_values_synced(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-14 / 03 REQ-INT-008, REQ-REF-009: department values from the mock are
    inserted as ``dimension_value`` rows of ``department`` and mapped (``object_type =
    dimension_value``); a value the ERP marks inactive is not brought in."""
    _workspace_chart(world)
    target = _netsuite(world)
    [department] = world.rows(
        select(dimension_definition).where(dimension_definition.c.code == "department")
    )
    assert department["is_builtin"] is True
    assert world.rows(select(dimension_value)) == []

    row, finished = sync(world, target, kind=COA_SYNC)

    assert row["status"] == "SUCCEEDED", row["problem"]
    counts = finished["result"]["counts"]
    assert counts["dimension_values_fetched"] == 3  # Sales, Customer Success, Legacy Services
    assert (counts["dimension_values_created"], counts["dimension_values_mapped"]) == (2, 2)
    values = {
        str(value["code"]): value
        for value in world.rows(
            select(dimension_value).where(
                dimension_value.c.dimension_definition_id == department["id"]
            )
        )
    }
    assert sorted(values) == ["Customer Success", "Sales"]  # Legacy Services is inactive in the ERP
    assert all(value["is_active"] and value["parent_value_id"] is None for value in values.values())
    assert {code: value["name"] for code, value in values.items()} == {
        "Customer Success": "Customer Success",
        "Sales": "Sales",
    }
    links = _links(world, "dimension_value")
    assert {external: link["internal_id"] for external, link in links.items()} == {
        "11": values["Sales"]["id"],
        "12": values["Customer Success"]["id"],
    }
    assert all(link["sync_run_id"] == row["id"] for link in links.values())
    listed = get(world.app, "/api/v1/dimensions/department/values", world.nikhil)
    assert listed.status_code == 200, listed.text
    assert sorted(item["code"] for item in listed.json()["items"]) == ["Customer Success", "Sales"]
    assert row["record_count"] == 3  # the accounts: dimension values are not chart records

    # the ERP retires a value: the next sync deactivates it, and never deletes it
    mock = _mock(world)
    mock.scenario = dataclasses.replace(
        mock.scenario,
        departments=tuple(
            {**item, "isInactive": True} if item["name"] == "Sales" else item
            for item in mock.scenario.departments
        ),
    )
    _, later_job = sync(world, target, kind=COA_SYNC)
    assert later_job["result"]["counts"]["dimension_values_deactivated"] == 1
    [sales] = world.rows(select(dimension_value).where(dimension_value.c.code == "Sales"))
    assert sales["is_active"] is False and sales["id"] == values["Sales"]["id"]


def test_inactive_account_deactivated_not_deleted(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-14: an account absent from the ERP chart is set ``is_active = false`` and
    never deleted — the account the sync created and the one it mapped alike — and so is one the
    ERP marks inactive; an account the ERP never knew is untouched."""
    _workspace_chart(world)
    new_account(
        world.app,
        world.nikhil,
        code="6000",
        name="Workspace-only expense",
        account_type="EXPENSE",
        normal_balance="D",
    )
    target = _netsuite(world)
    first, _ = sync(world, target, kind=COA_SYNC)
    assert first["status"] == "SUCCEEDED" and sorted(_accounts(world)) == [
        "1100",
        "2100",
        "4050",
        "6000",
    ]
    ids = {code: account["id"] for code, account in _accounts(world).items()}

    # the ERP drops 4050 (created by the sync) and 1100 (mapped by it), and retires 2100
    mock = _mock(world)
    mock.scenario = dataclasses.replace(
        mock.scenario,
        accounts=tuple(
            {**account, "isInactive": True}
            for account in mock.scenario.accounts
            if account["acctNumber"] == "2100"
        ),
    )
    row, finished = sync(world, target, kind=COA_SYNC)

    assert row["status"] == "SUCCEEDED", row["problem"]
    assert row["record_count"] == 1  # the one account the ERP still states
    counts = finished["result"]["counts"]
    assert counts["accounts_deactivated"] == 3 and counts["accounts_created"] == 0
    chart = _accounts(world)
    assert {code: account["id"] for code, account in chart.items()} == ids  # nothing deleted
    assert {code: account["is_active"] for code, account in chart.items()} == {
        "1100": False,
        "2100": False,
        "4050": False,
        "6000": True,  # never the ERP's: left alone
    }
    assert chart["4050"]["source_system"] == "NETSUITE" and chart["4050"]["row_version"] == 2
    assert sorted(_links(world, "gl_account")) == ["101", "102", "103"]  # the links stay

    # the ERP states 4050 again: the same row is reactivated, not a second one inserted
    mock.reset()
    back, back_job = sync(world, target, kind=COA_SYNC)
    assert (
        back["status"] == "SUCCEEDED" and back_job["result"]["counts"]["accounts_reactivated"] == 3
    )
    restored = _accounts(world)
    assert {code: account["id"] for code, account in restored.items()} == ids
    assert all(account["is_active"] for account in restored.values())


def test_conflicting_account_is_named_and_left_alone(world: IntegrationWorld) -> None:
    """``coa_sync`` module contract: a workspace account with the ERP's code and another type or
    normal balance is a conflict — the run ends FAILED naming it (failure step ``reference``), the
    account is left alone, and every other account is applied."""
    new_account(world.app, world.nikhil, code="1100", name="Cash")
    new_account(  # the ERP states 2100 as a liability with a credit balance
        world.app, world.nikhil, code="2100", name="Deferred revenue", account_type="ASSET"
    )
    target = _netsuite(world)
    row, finished = sync(world, target, kind=COA_SYNC)

    assert row["status"] == "FAILED" and finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    [failure] = row["problem"]["failures"]
    assert (failure["step"], failure["object_type"], failure["external_id"], failure["code"]) == (
        "reference",
        "gl_account",
        "102",
        "2100",
    )
    assert "workspace ASSET/D vs ERP LIABILITY/C" in failure["error"]
    assert row["record_count"] == 3
    assert (row["source_totals"]["count"], row["loaded_totals"]["count"]) == (3, 2)
    chart = _accounts(world)
    assert (chart["2100"]["account_type"], chart["2100"]["name"]) == ("ASSET", "Deferred revenue")
    assert chart["4050"]["source_system"] == "NETSUITE"  # the rest of the chart was applied
    assert sorted(_links(world, "gl_account")) == ["101", "103"]


def test_unreachable_chart_fails_the_run_and_changes_nothing(world: IntegrationWorld) -> None:
    """05 ADP-12: a chart the ERP refuses (a permanent 400) ends the run FAILED with a ``fetch``
    failure and leaves the workspace's chart as it was."""
    _workspace_chart(world)
    target = _netsuite(world)
    queue_fault(world, f"{ns_mock.PREFIX}/record/v1/account", "PERMANENT_ERROR")
    row, _ = sync(world, target, kind=COA_SYNC)
    assert row["status"] == "FAILED" and row["record_count"] == 0
    [failure] = row["problem"]["failures"]
    assert (failure["step"], failure["object_type"]) == ("fetch", "gl_account")
    assert sorted(_accounts(world)) == ["1100", "2100"] and _links(world, "gl_account") == {}

    # an EMPTY chart is no chart: it never deactivates the accounts the ERP gave (fail closed)
    synced, _ = sync(world, target, kind=COA_SYNC)
    assert synced["status"] == "SUCCEEDED" and sorted(_accounts(world)) == ["1100", "2100", "4050"]
    mock = _mock(world)
    mock.scenario = dataclasses.replace(mock.scenario, accounts=())
    empty, _ = sync(world, target, kind=COA_SYNC)
    assert empty["status"] == "FAILED" and empty["record_count"] == 0
    [stated] = empty["problem"]["failures"]
    assert stated["step"] == "fetch" and "empty chart of accounts" in stated["error"]
    assert all(account["is_active"] for account in _accounts(world).values())


def test_test_connection_is_one_single_attempt_read_of_the_chart(world: IntegrationWorld) -> None:
    """04 §16.14 rev 1.115 (ruling R-45, point 4): "Test connection" of a NetSuite connection is
    ONE single-attempt read of the chart of accounts. SUCCESS states how many accounts the chart
    holds and applies none of them; a rate limit the ``COA_SYNC`` run would wait out and retry
    (ADP-12) is a FAILURE after the one attempt, with no backoff; a refusal and an empty chart are
    FAILUREs too. (The probe asked the inbound registry for a ``NETSUITE`` adapter and always
    answered ``LookupError``.)"""
    _workspace_chart(world)
    target = _netsuite(world)
    before = _accounts(world)
    mock = _mock(world)
    started = world.clock.now()
    route = f"{ns_mock.PREFIX}/record/v1/account"

    tested = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_test_result"] == "SUCCESS"
    assert tested.json()["last_test_detail"] == (
        f"NETSUITE reachable at {MOCK_BASE}; 3 account(s) in the chart"
    )
    assert tested.json()["last_sync_run"]["status"] == "SUCCEEDED"
    assert mock.served == ["account:list"]  # the chart, read once; no dimension, no subsidiary
    # the probe reads; it applies nothing: no account, no link, no COA_SYNC run
    assert _accounts(world) == before and _links(world, "gl_account") == {}
    assert [run["kind"] for run in world.rows(select(sync_run))] == ["TEST_CONNECTION"]

    # a rate limit is retried by the COA_SYNC run (ADP-12); the probe makes its one attempt
    queue_fault(world, route, "RATE_LIMIT", count=2)
    limited = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert limited.status_code == 200, limited.text
    assert limited.json()["last_test_result"] == "FAILURE"
    assert limited.json()["last_test_detail"] == "Transient: HTTP 429"
    assert limited.json()["last_sync_run"]["status"] == "FAILED"
    assert world.clock.now() == started  # no backoff was waited
    assert mock.served == ["account:list"]  # the faulted request never reached the chart
    # exactly one of the two queued faults was consumed: the next probe meets the other
    second = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert second.json()["last_test_detail"] == "Transient: HTTP 429"
    third = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert third.json()["last_test_result"] == "SUCCESS" and len(mock.served) == 2

    queue_fault(world, route, "PERMANENT_ERROR")
    refused = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert refused.status_code == 200, refused.text
    assert refused.json()["last_test_result"] == "FAILURE"
    assert refused.json()["last_test_detail"] == "Permanent: HTTP 400"

    # an empty chart is no chart (a role that may not list accounts reads as one): FAILURE
    mock.scenario = dataclasses.replace(mock.scenario, accounts=())
    empty = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert empty.status_code == 200, empty.text
    assert empty.json()["last_test_result"] == "FAILURE"
    assert empty.json()["last_test_detail"] == (
        f"NETSUITE at {MOCK_BASE} stated an empty chart of accounts"
    )
    assert _accounts(world) == before and world.clock.now() == started


def test_inactive_erp_account_the_workspace_never_held_is_not_brought_in(
    world: IntegrationWorld,
) -> None:
    """``coa_sync`` module contract: an account the ERP states inactive and the workspace never
    held is read, counted and left out — reflected, so both totals agree and the run SUCCEEDED."""
    _workspace_chart(world)
    target = _netsuite(world)
    mock = _mock(world)
    dormant = {
        "id": "190",
        "acctNumber": "9990",
        "acctName": "Dormant clearing",
        "acctType": "OthCurrLiab",
        "isInactive": True,
    }
    mock.scenario = dataclasses.replace(mock.scenario, accounts=(*mock.scenario.accounts, dormant))
    row, finished = sync(world, target, kind=COA_SYNC)
    assert row["status"] == "SUCCEEDED", row["problem"]
    assert row["record_count"] == 4
    assert row["source_totals"] == row["loaded_totals"] and row["source_totals"]["count"] == 4
    assert finished["result"]["counts"]["accounts_created"] == 1  # 4050 only
    assert sorted(_accounts(world)) == ["1100", "2100", "4050"]
    assert sorted(_links(world, "gl_account")) == ["101", "102", "103"]


def test_sync_requires_integration_manage(world: IntegrationWorld, clock: FrozenClock) -> None:
    """BUILD_SPEC DIN-14 / PRD ACT-45: a Viewer's ``/sync`` returns 403 ``forbidden`` and queues
    nothing; a kind the connection's adapter cannot run is 422."""
    target = _netsuite(world)
    someone = colleague(world.tenant_id, "vera")
    assign(someone, "viewer")
    viewer = enrolled(world.app, clock, someone)
    refused = post(world.app, f"{INTEGRATIONS}/{target['id']}/sync", viewer, {"kind": COA_SYNC})
    assert refused.status_code == 403, refused.text
    assert refused.json()["type"].endswith("/forbidden")
    assert world.rows(select(sync_run)) == []

    # the Integration Admin may ask; a chart sync is a run kind of a chart-serving adapter only
    crm = connection(
        world,
        code="sf-quayside",
        name="Salesforce (mock)",
        adapter="SALESFORCE",
        direction="INBOUND",
        base_url=f"{mocks.MOCKS_PREFIX}/salesforce",
    )
    wrong = post(world.app, f"{INTEGRATIONS}/{crm['id']}/sync", world.nikhil, {"kind": COA_SYNC})
    assert wrong.status_code == 422, wrong.text
    poll = post(world.app, f"{INTEGRATIONS}/{target['id']}/sync", world.nikhil, {})
    assert poll.status_code == 422, poll.text  # INBOUND_POLL is not a NetSuite run kind
    accepted = post(
        world.app, f"{INTEGRATIONS}/{target['id']}/sync", world.nikhil, {"kind": COA_SYNC}
    )
    assert accepted.status_code == 202, accepted.text
    [queued] = world.rows(select(sync_run))
    assert (queued["kind"], queued["status"]) == (COA_SYNC, "QUEUED")
