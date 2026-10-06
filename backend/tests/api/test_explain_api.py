"""API-R-49 Explain (04 §15.3 API-R-49, §16.11 API-S-Explain, §16.14 API-S-CalcTrace, T-ENG-03;
dev-guide §5.16 DG-KRN-EXP-01 to DG-KRN-EXP-07; 05 §3.10 RCP-24 to RCP-27; PRD WLD-X-02; 03
REQ-RPT-017, REQ-RPT-018, REQ-PLT-012; BUILD_SPEC CTR-19).

The world is the CTR-2 world of ``tests/domain/contracts/test_computation.py`` (PRD §2.6): Maya
(Revenue Accountant, SSP Analyst) prepares the reference data; Priya (SSP Approver) approves US-LIST
2026-H1 and Marcus (Controller) the templates and AVM-MAP-2026-01, both enrolled in MFA. AVM-US
(America/New_York) keeps FY2026-P01 to P09 open; TPL-SUB-DAILY and TPL-SVC-PCT are the defaults of
AVM-PLAT-ENT and AVM-IMPL-STD. K-01 ``SF-ORD-10001`` (PRD WLD-K-01: O1 120,000.00 USD over 2026, O2
15,000.00 USD) is booked, activated and computed through ``support.factories.engine()``, which is
``erev_engine.compute`` since END-9. The frozen clock reads 2026-09-12T12:00:00Z.

R-RC-1: ``test_history_lists_estimate_pairs`` (K-06 estimate version 2) moves post-rc with CTR-12
(L4-4-Q-11); ``test_history_lists_changed_versions_newest_first`` covers the history rule without
estimates.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    audit_event,
    calc_trace,
    contract_computation,
    contract_version,
    contract_version_balance,
    obligation,
    obligation_version,
    period,
    schedule_line,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.contracts.commands import BookedContract
from erev_api.enums import ContractEventType
from erev_api.events.payloads import SignificantChangeFlaggedV1
from erev_api.events.stream import EventIn
from erev_api.explain import store
from erev_api.explain.narratives import NARRATIVES, render
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.trace import TraceNode
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    TPL_SUB_DAILY,
    TPL_SVC_PCT,
    Workspace,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    point_entry,
    product_with_template,
    published_mapping,
    published_template,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, entity, fields, get, holding, post, slug

EXPLAIN = "/api/v1/explain"
CALC_TRACES = "/api/v1/calc-traces"
PLATFORM = "AVM-PLAT-ENT"
IMPLEMENTATION = "AVM-IMPL-STD"
PLATFORM_CASE = {
    "obligation_key": "POB-01",
    "product_code": PLATFORM,
    "quantity": "1",
    "total_price": "120000.00",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
}
IMPLEMENTATION_CASE = {
    "obligation_key": "POB-01",
    "product_code": IMPLEMENTATION,
    "quantity": "1",
    "total_price": "15000.00",
}
SEPTEMBER = "FY2026-P09"
K01_O1_SEPTEMBER = "revenue_by_cause:SF-ORD-10001/O1/NORMAL:FY2026-P09"
O1_CUMULATIVE_SEPTEMBER = "revenue_cum:SF-ORD-10001/O1:FY2026-P09"
O1_CUMULATIVE_AUGUST = "revenue_cum:SF-ORD-10001/O1:FY2026-P08"
CLOCK_AT = "2026-09-12T12:00:00Z"


@dataclass(frozen=True, slots=True)
class World:
    place: Workspace
    calendar_id: str
    customer_id: UUID

    @property
    def app(self) -> FastAPI:
        return self.place.app

    @property
    def maya(self) -> Actor:
        return self.place.author


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (("priya", ("ssp_approver",)), ("marcus", ("controller", "ssp_approver"))):
        someone = colleague(maya_member.tenant_id, name)
        for role in roles:
            assign(someone, role)
        approvers[name] = enrolled(app, clock, someone)
    calendar_id, _ = world_calendar(app, maya)
    buyer = customer_id(app, maya, code="C-01", name="Pellworth Logistics Inc. (Demo)")
    products = {
        PLATFORM: product_with_template(
            app,
            maya,
            code=PLATFORM,
            name="Platform, enterprise tier",
            revenue_category="SUBSCRIPTION",
        ),
        IMPLEMENTATION: product_with_template(
            app, maya, code=IMPLEMENTATION, name="Implementation", revenue_category="SERVICES"
        ),
    }
    daily = published_template(
        app,
        maya,
        approvers["marcus"],
        code="TPL-SUB-DAILY",
        outputs=TPL_SUB_DAILY,
        case_line=PLATFORM_CASE,
    )
    percent = published_template(
        app,
        maya,
        approvers["marcus"],
        code="TPL-SVC-PCT",
        outputs=TPL_SVC_PCT,
        case_line=IMPLEMENTATION_CASE,
    )
    set_default_template(app, maya, products[PLATFORM], daily["template_id"])
    set_default_template(app, maya, products[IMPLEMENTATION], percent["template_id"])
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        ssp_book(app, maya),
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[
            point_entry(PLATFORM, "132000.00", value_basis="AMOUNT"),  # series: D-97 (3a)
            point_entry(IMPLEMENTATION, "18000.00", "cost_plus_margin"),
        ],
    )
    published_mapping(app, maya, approvers["marcus"])
    stamp_test_release()
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), maya)
    return World(place=place, calendar_id=calendar_id, customer_id=buyer)


def k01_computed(world: World) -> tuple[BookedContract, Mapping[str, Any]]:
    """PRD WLD-K-01 booked, activated and computed once."""
    body = {
        "external_id": "SF-ORD-10001",
        "customer_id": str(world.customer_id),
        "contracting_entity_code": "AVM-US",
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PLATFORM,
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
            {
                "obligation_key": "O2",
                "product_code": IMPLEMENTATION,
                "quantity": "1",
                "total_price": {"amount": "15000.00", "currency": "USD"},
            },
        ],
    }
    booked = booked_contract(world.place, body, activate=True)
    _, _, stored = computed(world.place, booked.combination_group["id"])
    return booked, stored


def september_line(world: World) -> dict[str, Any]:
    """The K-01 O1 FY2026-P09 schedule line of the latest contract version."""
    statement = (
        select(
            schedule_line.c.id,
            schedule_line.c.amount,
            schedule_line.c.subject_id,
            schedule_line.c.contract_version_id,
            contract_version.c.version_no,
            contract_version.c.calc_trace_id,
        )
        .select_from(
            schedule_line.join(period, period.c.id == schedule_line.c.period_id)
            .join(obligation, obligation.c.id == schedule_line.c.subject_id)
            .join(contract_version, contract_version.c.id == schedule_line.c.contract_version_id)
        )
        .where(period.c.period_key == SEPTEMBER, obligation.c.obligation_key == "O1")
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    (line,) = world.place.rows(statement)
    return line


def stored_nodes(world: World, trace_id: Any) -> dict[str, TraceNode]:
    (row,) = world.place.rows(select(calc_trace).where(calc_trace.c.id == trace_id))
    return {node.id: node for node in store.trace_from_row(row).nodes}


def version_known_at(world: World, version_id: Any) -> datetime:
    """``contract_version.known_at``: the latest record time of the included events."""
    known_at = world.place.scalar(
        select(contract_version.c.known_at).where(contract_version.c.id == version_id)
    )
    assert isinstance(known_at, datetime)
    return known_at


def from_template(sentence: str, narrative_key: str) -> bool:
    """The sentence is the ``NARRATIVES`` template of the key with its placeholders filled."""
    parts = re.split(r"\{[^{}]*\}", NARRATIVES[narrative_key])
    return re.fullmatch(".+?".join(re.escape(part) for part in parts), sentence) is not None


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def explain_path(object_type: str, object_id: Any, measure: str) -> str:
    return f"{EXPLAIN}/{object_type}/{object_id}/{measure}"


def test_explain_k01_o1_september_schedule(world: World) -> None:
    booked, _ = k01_computed(world)
    line = september_line(world)
    nodes = stored_nodes(world, line["calc_trace_id"])
    response = get(
        world.app,
        explain_path("schedule_line", line["id"], "amount"),
        world.maya,
        {"book": "ASC606"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # REQ-RPT-018; PRD WLD-X-02 88,855.89 − 79,091.51: the stored amount exactly.
    assert body["value"] == usd("9764.38")
    assert Decimal(body["value"]["amount"]) == line["amount"]
    assert body["object"] == {
        "type": "schedule_line",
        "id": str(line["id"]),
        "measure": "amount",
        "period_key": SEPTEMBER,
    }
    assert (body["calc_trace_id"], body["root_node_id"]) == (
        str(line["calc_trace_id"]),
        K01_O1_SEPTEMBER,
    )
    engine_version = world.place.scalar(
        select(calc_trace.c.engine_version).where(calc_trace.c.id == line["calc_trace_id"])
    )
    assert body["engine_version"] == engine_version
    assert body["context"] == {
        "book": "ASC606",
        "as_of": "2026-09-12",
        "known_at": CLOCK_AT,
        "contract_version_id": str(line["contract_version_id"]),
        "version_no": 1,
        # 04 API-S-Context rev 1.132 (supervisor ruling R-76 (c)): when the computation made the
        # version; a schedule line is no to-date measure, so no period is named.
        "computed_at": CLOCK_AT,
        "measured_period": None,
    }
    root = body["nodes"][0]
    assert (
        root["id"],
        root["measure"],
        root["value"],
        root["currency"],
        root["formula_id"],
        root["rounding_residue"],
        root["inputs"],
    ) == (
        K01_O1_SEPTEMBER,
        "revenue_by_cause",
        "9764.38",
        "USD",
        "rec.decompose.sequential.v1",
        "0",
        [{"node_id": O1_CUMULATIVE_SEPTEMBER}, {"node_id": O1_CUMULATIVE_AUGUST}],
    )
    returned = {node["id"]: node for node in body["nodes"]}
    assert (
        returned[O1_CUMULATIVE_SEPTEMBER]["value"],
        returned[O1_CUMULATIVE_SEPTEMBER]["rounding_residue"],
        returned[O1_CUMULATIVE_AUGUST]["value"],
        returned[O1_CUMULATIVE_AUGUST]["rounding_residue"],
    ) == ("88855.89", "0.000410958904109589", "79091.51", "-0.003150684931506849")
    # Every returned node is the stored node, unchanged (DG-KRN-EXP-01, DG-KRN-EXP-03).
    for node in body["nodes"]:
        kept = nodes[node["id"]]
        assert (
            node["measure"],
            node["value"],
            node["currency"],
            node["formula_id"],
            node["params"],
            node["rounding_residue"],
        ) == (
            kept.measure,
            kept.value,
            kept.currency,
            kept.formula_id,
            dict(kept.params),
            kept.rounding_residue,
        )
    # DG-KRN-EXP-06: at most 6 levels below the figure.
    level = {K01_O1_SEPTEMBER: 0}
    for node in body["nodes"]:
        for item in node["inputs"]:
            if "node_id" in item:
                level.setdefault(item["node_id"], level[node["id"]] + 1)
    assert set(level) == set(returned)
    assert (len(body["nodes"]), max(level.values())) == (7, 3)
    assert all(value <= 6 for value in level.values())
    # The narrative is rendered only from NARRATIVES, one sentence per returned node.
    assert body["narrative"] == [
        render(
            nodes[node["id"]],
            {item: nodes[item] for item in nodes[node["id"]].inputs if isinstance(item, str)},
        )
        for node in body["nodes"]
    ]
    assert all(
        from_template(sentence, nodes[node["id"]].narrative_key)
        for sentence, node in zip(body["narrative"], body["nodes"], strict=True)
    )
    assert body["narrative"][0] == (
        "Revenue for FY2026-P09 by cause: the catch-ups and event effects cited, with normal "
        "revenue taking the rest of the period amount = USD 9,764.38."
    )
    (history,) = body["history"]
    assert datetime.fromisoformat(history["known_at"]) == version_known_at(
        world, line["contract_version_id"]
    )
    assert body["history"] == [
        {
            "contract_version_id": str(line["contract_version_id"]),
            "version_no": 1,
            "known_at": history["known_at"],
            "value": "9764.38",
            "delta": None,
            "cause": "CONTRACT_ACTIVATED",
            "estimate_version_pair": None,
            "origin_period_key": None,
        }
    ]
    contract_id = booked.contract["id"]
    assert body["drill"] == {
        "contract_href": f"/api/v1/contracts/{contract_id}",
        "obligation_href": f"/api/v1/obligations/{line['subject_id']}",
        "schedule_lines_href": f"/api/v1/contracts/{contract_id}/schedule?book=ASC606",
        "subledger_lines_href": (
            f"/api/v1/subledger-lines?contract={contract_id}&book=ASC606&period=FY2026-P09"
        ),
        "source_rows": [],
    }


def row_counts(world: World) -> dict[str, int]:
    tables = (
        calc_trace,
        contract_computation,
        contract_version,
        obligation_version,
        schedule_line,
        subledger_posting,
        subledger_line,
        audit_event,
    )
    return {
        table.name: int(world.place.scalar(select(func.count()).select_from(table)))
        for table in tables
    }


def test_verify_recomputes_stored_value(world: World) -> None:
    k01_computed(world)
    line = september_line(world)
    before = row_counts(world)
    response = post(
        world.app, f"{explain_path('schedule_line', line['id'], 'amount')}/verify", world.maya, {}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "recomputed_value": "9764.38",
        "stored_value": "9764.38",
        "matches": True,
    }
    assert row_counts(world) == before


def test_calc_trace_route(world: World) -> None:
    k01_computed(world)
    line = september_line(world)
    (row,) = world.place.rows(select(calc_trace).where(calc_trace.c.id == line["calc_trace_id"]))
    response = get(world.app, f"{CALC_TRACES}/{row['id']}", world.maya)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body["id"],
        body["contract_version_id"],
        body["combination_group_id"],
        body["book"],
        body["format_version"],
        body["engine_version"],
        body["trace_sha256"],
        body["node_count"],
        body["root_measures"],
    ) == (
        str(row["id"]),
        str(line["contract_version_id"]),
        str(row["combination_group_id"]),
        "ASC606",
        1,
        row["engine_version"],
        row["trace_sha256"],
        row["node_count"],
        row["root_measures"],
    )
    assert body["node_count"] == len(body["trace"]["nodes"]) == len(stored_nodes(world, row["id"]))
    assert body["trace"] == row["trace"]
    assert store.trace_from_row({**row, "trace": body["trace"]}).sha256() == body["trace_sha256"]
    missing = get(world.app, f"{CALC_TRACES}/{uuid4()}", world.maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text


def test_depth_limit(world: World) -> None:
    k01_computed(world)
    line = september_line(world)
    path = explain_path("schedule_line", line["id"], "amount")
    refused = get(world.app, path, world.maya, {"depth": "21"})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [field for field, _ in fields(refused)] == ["query.depth"]
    for depth, count in ((0, 1), (1, 3), (20, 7)):
        shown = get(world.app, path, world.maya, {"depth": str(depth)})
        assert shown.status_code == 200, shown.text
        assert (len(shown.json()["nodes"]), len(shown.json()["narrative"])) == (count, count)


def test_explain_out_of_scope_404(world: World) -> None:
    k01_computed(world)
    line = september_line(world)
    germany = entity(
        world.app,
        world.maya,
        code="AVM-DE",
        calendar_id=world.calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    someone = colleague(world.place.tenant_id, "dieter")
    scoped = holding(world.app, someone, "revenue_accountant", entity_ids=[UUID(germany["id"])])
    path = explain_path("schedule_line", line["id"], "amount")
    for response in (
        get(world.app, path, scoped),
        post(world.app, f"{path}/verify", scoped, {}),
        get(world.app, f"{CALC_TRACES}/{line['calc_trace_id']}", scoped),
    ):
        assert (response.status_code, slug(response)) == (404, "not-found"), response.text
    shown = get(world.app, path, world.maya)
    assert shown.status_code == 200, shown.text


def money_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def test_explain_object_types_and_refusals(world: World) -> None:
    booked, stored = k01_computed(world)
    maya = world.maya
    version_id = stored["contract_version_ids"]["ASC606"]
    (o1,) = world.place.rows(
        select(obligation_version).where(
            obligation_version.c.contract_version_id == version_id,
            obligation_version.c.obligation_key == "O1",
        )
    )
    (revenue_line,) = world.place.rows(
        select(subledger_line.c.id, subledger_line.c.amount_txn)
        .select_from(subledger_line.join(period, period.c.id == subledger_line.c.period_id))
        .where(
            period.c.period_key == SEPTEMBER,
            subledger_line.c.account_role == "REVENUE",
            subledger_line.c.obligation_id == o1["obligation_id"],
        )
    )
    (balance,) = world.place.rows(
        select(contract_version_balance.c.id, contract_version_balance.c.contract_asset_txn).where(
            contract_version_balance.c.contract_version_id == version_id
        )
    )

    def explained(object_type: str, object_id: Any, measure: str, **params: str) -> Any:
        path = explain_path(object_type, object_id, measure)
        response = get(world.app, path, maya, params)
        assert response.status_code == 200, (path, response.text)
        query = "&".join(f"{name}={value}" for name, value in sorted(params.items()))
        verified = post(world.app, f"{path}/verify" + (f"?{query}" if query else ""), maya, {})
        assert verified.status_code == 200, (path, verified.text)
        assert verified.json()["matches"] is True, (path, verified.json())
        return response.json()

    shown = explained("contract_version", version_id, "transaction_price")
    assert (shown["value"], shown["root_node_id"], shown["nodes"][0]["formula_id"]) == (
        usd("135000.00"),
        "transaction_price:CG-CON-000001:-",
        "tp.buildup.v1",
    )
    assert (shown["drill"]["contract_href"], shown["drill"]["obligation_href"]) == (
        f"/api/v1/contracts/{booked.contract['id']}",
        None,
    )
    shown = explained("obligation_version", o1["id"], "revenue_cum")
    assert (shown["value"], shown["root_node_id"]) == (
        usd(money_text(o1["revenue_cum"])),
        o1["trace_nodes"]["revenue_cum"],
    )
    # 04 §16.11 rev 1.132 (supervisor ruling R-76 (a)): the Explain of an obligation's to-date
    # measure is the figure GET /obligations/{id} serves, the period node at the cut of ``as_of``
    # (today, 12 September: PRD WLD-X-02 88,855.89), not the version's node at d_v.
    shown = explained("obligation", o1["obligation_id"], "revenue_to_date", book="ASC606")
    assert (
        shown["root_node_id"],
        shown["value"],
        shown["object"]["period_key"],
        shown["context"]["contract_version_id"],
        shown["context"]["measured_period"],
    ) == (
        "revenue_cum:SF-ORD-10001/O1:FY2026-P09",
        usd("88855.89"),
        SEPTEMBER,
        version_id,
        {"period_key": SEPTEMBER, "end_date": "2026-09-30"},
    )
    served = get(world.app, f"/api/v1/obligations/{o1['obligation_id']}", maya)
    assert served.status_code == 200, served.text
    assert served.json()["to_date"]["revenue"] == shown["value"]
    shown = explained("obligation", o1["obligation_id"], "revenue", period=SEPTEMBER)
    assert (shown["value"], shown["root_node_id"], shown["object"]["period_key"]) == (
        usd("9764.38"),
        K01_O1_SEPTEMBER,
        SEPTEMBER,
    )
    shown = explained("subledger_line", revenue_line["id"], "amount")
    assert (shown["value"], shown["root_node_id"]) == (
        usd("-9764.38"),
        "posting_delta:SF-ORD-10001/O1/REVENUE_RECOGNITION/REVENUE/EVENT:FY2026-P09",
    )
    assert Decimal(shown["value"]["amount"]) == revenue_line["amount_txn"]
    shown = explained("contract_version_balance", balance["id"], "contract_asset")
    assert (shown["value"], shown["root_node_id"], shown["object"]["period_key"]) == (
        usd(money_text(balance["contract_asset_txn"])),
        "contract_asset:SF-ORD-10001@AVM-US:FY2026-P09",
        SEPTEMBER,
    )

    for path, params in (
        (explain_path("journal_line", uuid4(), "amount"), {}),
        (explain_path("schedule_line", uuid4(), "amount"), {}),
        (explain_path("schedule_line", september_line(world)["id"], "quantity"), {}),
        (explain_path("obligation_version", o1["id"], "unknown_measure"), {}),
        (explain_path("contract_version", version_id, "transaction_price"), {"period": SEPTEMBER}),
    ):
        refused = get(world.app, path, maya, params)
        assert (refused.status_code, slug(refused)) == (404, "not-found"), (path, refused.text)
    line_path = explain_path("schedule_line", september_line(world)["id"], "amount")
    naive = get(world.app, line_path, maya, {"known_at": "2026-09-12T12:00:00"})
    assert (naive.status_code, fields(naive)) == (422, [("known_at", "API-C-09")]), naive.text
    unknown = get(world.app, explain_path("report_run", uuid4(), "amount"), maya)
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text


def test_explain_resolves_a_member_balance_under_the_engines_subject_key(world: World) -> None:
    """Key audit of supervisor ruling R-16 (2026-09-29; ENGINE_SPEC CV-21; ENGINE_SPEC_B
    S15-R-07a): a member's balance nodes sit under ``<contract>@<entity>`` with both components
    CV-21-encoded, and Explain resolves them under that key. A contract whose external id holds
    every delimiter — 120,000.00 over 2026, unbilled: the contract asset is 120,000.00 × days ÷
    365 — explains its stored figure (September, 89,753.42) and an earlier period end (August,
    79,890.41), each verified. Fail-first: the prefix was joined from the raw ids and both
    requests answered 404 "The calculation trace holds no node for this figure." """
    body = {
        "external_id": "A:B/C@D#E%",
        "customer_id": str(world.customer_id),
        "contracting_entity_code": "AVM-US",
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PLATFORM,
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            }
        ],
    }
    booked = booked_contract(world.place, body, activate=True)
    _, _, stored = computed(world.place, booked.combination_group["id"])
    (balance,) = world.place.rows(
        select(contract_version_balance.c.id, contract_version_balance.c.contract_asset_txn).where(
            contract_version_balance.c.contract_version_id
            == stored["contract_version_ids"]["ASC606"]
        )
    )
    subject = "A%3AB%2FC%40D%23E%25@AVM-US"  # `%` first, then `/` `@` `#` `:` (CV-21)
    path = explain_path("contract_version_balance", balance["id"], "contract_asset")
    for params, period_key, amount in (
        ({}, SEPTEMBER, "89753.42"),
        ({"period": "FY2026-P08"}, "FY2026-P08", "79890.41"),
    ):
        shown = get(world.app, path, world.maya, params)
        assert shown.status_code == 200, shown.text
        found = shown.json()
        assert (found["value"], found["root_node_id"], found["object"]["period_key"]) == (
            usd(amount),
            f"contract_asset:{subject}:{period_key}",
            period_key,
        )
        query = "".join(f"?{name}={value}" for name, value in params.items())
        verified = post(world.app, f"{path}/verify{query}", world.maya, {})
        assert verified.status_code == 200, verified.text
        assert verified.json()["matches"] is True, verified.json()
    assert money_text(balance["contract_asset_txn"]) == "89753.42"  # the stored latest figure


def test_history_lists_changed_versions_newest_first(world: World) -> None:
    booked, _ = k01_computed(world)
    first = september_line(world)
    appended(
        world.place,
        booked.contract["id"],
        2,
        [
            EventIn(
                event_type=ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
                effective_date=date(2026, 2, 1),
                payload=SignificantChangeFlaggedV1(description="Customer asked for a review"),
            )
        ],
    )
    computed(world.place, booked.combination_group["id"])
    line = september_line(world)
    assert (line["version_no"], line["id"] != first["id"]) == (2, True)
    response = get(world.app, explain_path("schedule_line", line["id"], "amount"), world.maya)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["value"], body["context"]["version_no"]) == (usd("9764.38"), 2)
    # Version 2 leaves the figure unchanged, so only version 1 is listed.
    (history,) = body["history"]
    assert datetime.fromisoformat(history["known_at"]) == version_known_at(
        world, first["contract_version_id"]
    )
    assert body["history"] == [
        {
            "contract_version_id": str(first["contract_version_id"]),
            "version_no": 1,
            "known_at": history["known_at"],
            "value": "9764.38",
            "delta": None,
            "cause": "CONTRACT_ACTIVATED",
            "estimate_version_pair": None,
            "origin_period_key": None,
        }
    ]
