"""Computed versions, schedules and calculation traces (04 T-CON-07 to T-CON-09, T-CON-11, T-ENG-01
to T-ENG-03, §14.1 DB-17; dev-guide §6.1 DG-CMD-04, DG-CMD-10, §5.15 DG-KRN-REG-02, 03, §5.16
DG-KRN-EXP-05; 05 RCP-15, RCP-21; PRD WLD-K-01, WLD-X-01, WLD-X-02; 03 REQ-REF-015, REQ-SSP-011,
REQ-SSP-014, REQ-REC-020, REQ-CON-014; CTL-011; BUILD_SPEC CTR-2).

Maya holds Revenue Accountant and SSP Analyst and prepares every configuration; Priya (SSP Approver)
approves the SSP book and Marcus (Controller) the templates and the mapping, both enrolled in MFA.
The reference data of PRD §2.6 is created through the RFD routes: a January calendar for 2026 and
2027 whose AVM-US periods FY2026-P01 to P09 are open, customer C-01, templates TPL-SUB-DAILY and
TPL-SVC-PCT (effective 2026-01-01) as the defaults of AVM-PLAT-ENT and AVM-IMPL-STD, US-LIST 2026-H1
(AVM-PLAT-ENT observable point 132,000.00; AVM-IMPL-STD cost plus margin point 18,000.00) and
AVM-MAP-2026-01. K-01 (PRD WLD-K-01, ``SF-ORD-10001``) is booked and activated through the contract
commands. ``support.factories.engine()`` computes: the ENGINE_SPEC §0.5 fake until END-9 lands in
this checkout, ``erev_engine.compute`` in the L3 merge gate (V-C). The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    calc_trace,
    combination_group,
    computation_evidence,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    file_object,
    ledger_chain_head,
    obligation_version,
    period,
    product,
    registry_version,
    schedule,
    schedule_line,
    ssp_entry,
    ssp_range,
    subledger_posting,
)
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.contracts import computation_evidence as evidence_writer
from erev_api.domain.contracts.replay_verify import Trigger, VerificationRow
from erev_api.domain.platform import file_evidence
from erev_api.domain.reports import computation_sources
from erev_api.enums import ContractEventType
from erev_api.events.payloads import SignificantChangeFlaggedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.explain import store
from erev_api.files.store import LocalFileStore, open_file, store_file
from erev_api.jobs.context import JobContext
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine import ENGINE_VERSION, upgrade
from erev_engine.bundle import OutputBundle
from erev_engine.errors import EngineError
from erev_engine.trace import reevaluate
from fastapi import FastAPI
from sqlalchemy import exc, func, insert, select, update
from support.db import TestDatabase
from support.factories import (
    TPL_SUB_DAILY,
    TPL_SVC_PCT,
    Workspace,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    engine,
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
from support.reference import assign, get, holding

PLATFORM = "AVM-PLAT-ENT"
IMPLEMENTATION = "AVM-IMPL-STD"
PLATFORM_LINE = {
    "obligation_key": "POB-01",
    "product_code": PLATFORM,
    "quantity": "1",
    "total_price": "120000.00",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
}
IMPLEMENTATION_LINE = {
    "obligation_key": "POB-01",
    "product_code": IMPLEMENTATION,
    "quantity": "1",
    "total_price": "15000.00",
}


@dataclass(frozen=True, slots=True)
class World:
    place: Workspace
    priya: Actor
    marcus: Actor
    calendar_id: str
    entity_id: UUID
    customer_id: UUID
    templates: Mapping[str, Mapping[str, str]]
    book_id: str
    h1_id: str
    mapping_id: str

    @property
    def app(self) -> FastAPI:
        return self.place.app


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
    calendar_id, entity_id = world_calendar(app, maya)
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
    templates = {
        "TPL-SUB-DAILY": published_template(
            app,
            maya,
            approvers["marcus"],
            code="TPL-SUB-DAILY",
            outputs=TPL_SUB_DAILY,
            case_line=PLATFORM_LINE,
        ),
        "TPL-SVC-PCT": published_template(
            app,
            maya,
            approvers["marcus"],
            code="TPL-SVC-PCT",
            outputs=TPL_SVC_PCT,
            case_line=IMPLEMENTATION_LINE,
        ),
    }
    set_default_template(app, maya, products[PLATFORM], templates["TPL-SUB-DAILY"]["template_id"])
    set_default_template(
        app, maya, products[IMPLEMENTATION], templates["TPL-SVC-PCT"]["template_id"]
    )
    book_id = ssp_book(app, maya)
    h1_id = approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        book_id,
        label="2026-H1",
        effective_from="2026-01-01",
        entries=[
            point_entry(PLATFORM, "132000.00", value_basis="AMOUNT"),  # series: D-97 (3a)
            point_entry(IMPLEMENTATION, "18000.00", "cost_plus_margin"),
        ],
    )
    mapping_id = published_mapping(app, maya, approvers["marcus"])
    stamp_test_release()
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), maya)
    return World(
        place=place,
        priya=approvers["priya"],
        marcus=approvers["marcus"],
        calendar_id=calendar_id,
        entity_id=entity_id,
        customer_id=buyer,
        templates=templates,
        book_id=book_id,
        h1_id=h1_id,
        mapping_id=mapping_id,
    )


def k01(world: World) -> Any:
    """PRD WLD-K-01 booked and activated."""
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
    return booked_contract(world.place, body, activate=True)


def flag_change(world: World, contract_id: UUID, expected: int) -> None:
    """``SIGNIFICANT_CHANGE_FLAGGED`` effective 2026-02-01, a new fact for the next computation."""
    with world.place.uow() as uow:
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=expected,
            events=[
                EventIn(
                    event_type=ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
                    effective_date=date(2026, 2, 1),
                    payload=SignificantChangeFlaggedV1(description="Customer asked for a review"),
                )
            ],
            origin="UI",
        )
        uow.commit()


def count(world: World, table: Any) -> int:
    return int(world.place.scalar(select(func.count()).select_from(table)))


def test_bundle_pins_reference_versions(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    bundle, _, stored = computed(world.place, group_id)
    # RCP-15: the members, their stream, the pinned reference data and the calendar.
    assert bundle.group.group_key == "CG-CON-000001"
    assert bundle.group.member_contract_keys == ("SF-ORD-10001",)
    assert [(event.stream_version, event.event_type) for event in bundle.events] == [
        (1, "CONTRACT_BOOKED"),
        (2, "CONTRACT_ACTIVATED"),
    ]
    first_lines = bundle.events[0].payload["lines"]
    assert isinstance(first_lines, list)
    assert first_lines[0]["total_price"] == "120000.00"
    assert [version.version_key for version in bundle.ssp_versions] == ["US-LIST@v1"]
    assert [item.version_key for item in bundle.pob_template_versions] == [
        "TPL-SUB-DAILY@v1",
        "TPL-SVC-PCT@v1",
    ]
    assert [(item.code, item.default_template_code) for item in bundle.group.products] == [
        (IMPLEMENTATION, "TPL-SVC-PCT"),
        (PLATFORM, "TPL-SUB-DAILY"),
    ]
    (book_input,) = bundle.books
    assert (book_input.book_code, book_input.is_primary, book_input.entity_codes) == (
        "ASC606",
        True,
        ("AVM-US",),
    )
    assert book_input.account_mapping.version_key == "AVM-MAP-2026-01@v1"
    (avm_us,) = bundle.entities
    states = {period_input.period_key: period_input.states for period_input in avm_us.periods}
    assert (len(avm_us.periods), states["FY2026-P09"], states["FY2026-P10"]) == (
        24,
        (("ASC606", "open"),),
        (("ASC606", "future"),),
    )
    assert bundle.group.previous_stream_heads == ()
    # REQ-REF-015: the computation names every pinned version.
    (row,) = world.place.rows(select(contract_computation))
    published = world.place.rows(
        select(registry_version.c.id).where(registry_version.c.status == "PUBLISHED")
    )
    refs = row["pinned_refs"]
    # 04 T-CON-07 rev 1.110 (security ruling R-21): the computation of a contract past DRAFT also
    # records each product as it used it — the ``ProductInput`` members and the level-P values
    # of the product's obligations — and the next computation reads the product from here.
    unset: dict[str, Any] = {
        "sku_number": None,
        "product_family": None,
        "principal_agent": "PRINCIPAL",
        "distinctness_default": "distinct",
        "unit_of_measure": "EA",
        "is_bundle": False,
        "is_franchisor_preopening_service": False,
        "policy_values": {},
        "assurance_cost_per_unit": None,
        "components": [],
    }
    assert refs == {
        "ssp_book_version_ids": [world.h1_id],
        "registry_version_ids": sorted(str(item["id"]) for item in published),
        "rule_set_version_ids": [],
        "pob_template_version_ids": sorted(item["version_id"] for item in world.templates.values()),
        "account_mapping_version_id": world.mapping_id,
        "fx_rate_set_version_ids": [],
        "calendar_ids": [world.calendar_id],
        "estimate_version_ids": [],
        "products": {
            IMPLEMENTATION: {
                **unset,
                "revenue_category": "SERVICES",
                "default_template_code": "TPL-SVC-PCT",
                "obligation_policies": {},
            },
            PLATFORM: {
                **unset,
                "revenue_category": "SUBSCRIPTION",
                "default_template_code": "TPL-SUB-DAILY",
                "obligation_policies": {
                    "recognition.time_convention": {
                        "value": "DAILY",
                        "source": "TPL-SUB-DAILY@v1",
                    }
                },
            },
        },
    }
    assert published
    assert (row["id"], row["trigger"], row["status"], row["engine_version"]) == (
        stored["id"],
        "COMMAND",
        "SUCCEEDED",
        ENGINE_VERSION,
    )
    assert row["stream_heads"] == {str(booked.contract["id"]): 2}
    # DG-KRN-REG-02: pin K values are recorded on the version with their level and source.
    (version,) = world.place.rows(select(contract_version))
    assert version["pinned_policies"]["ssp.outside_range_point"] == {
        "value": "NEAREST_BOUND",
        "level": "DEFAULT",
        "source_id": POLICY_PARAMETERS["ssp.outside_range_point"].source_ref,
    }
    assert all(POLICY_PARAMETERS[code].pin == "K" for code in version["pinned_policies"]), (
        "pin P values resolve per posting period"
    )


def test_allocation_lineage_k01(world: World) -> None:
    booked = k01(world)
    computed(world.place, booked.combination_group["id"])
    entries = {
        item["code"]: str(item["id"])
        for item in world.place.rows(
            select(ssp_entry.c.id, product.c.code)
            .select_from(ssp_entry.join(product, product.c.id == ssp_entry.c.product_id))
            .where(ssp_entry.c.ssp_book_version_id == UUID(world.h1_id))
        )
    }
    rows = world.place.rows(
        select(obligation_version).order_by(obligation_version.c.obligation_key)
    )
    # PRD WLD-X-01: 135,000 × 132,000 ÷ 150,000 and the remainder to O2.
    assert [
        (
            item["obligation_key"],
            item["product_code"],
            item["stated_price"],
            item["original_ssp_selected"],
            item["allocated_amount"],
            item["allocation_weight"],
            item["allocated_exact"],
            item["allocation_adjustment"],
        )
        for item in rows
    ] == [
        (
            "O1",
            PLATFORM,
            Decimal("120000.00"),
            Decimal(132000),
            Decimal("118800.00"),
            Decimal("0.88"),
            Decimal(118800),
            Decimal("-1200.00"),
        ),
        (
            "O2",
            IMPLEMENTATION,
            Decimal("15000.00"),
            Decimal(18000),
            Decimal("16200.00"),
            Decimal("0.12"),
            Decimal(16200),
            Decimal("1200.00"),
        ),
    ]
    # REQ-SSP-011: the version, entry, bounds, in-range flag and selected SSP of each obligation; a
    # point entry has no low, mid or high and no in-range flag (S05-R-07).
    assert [
        (
            str(item["ssp_book_version_id"]),
            str(item["ssp_entry_id"]),
            item["ssp_version_label"],
            item["original_ssp_low"],
            item["original_ssp_mid"],
            item["original_ssp_high"],
            item["original_ssp_in_range"],
        )
        for item in rows
    ] == [
        (world.h1_id, entries[PLATFORM], "2026-H1", None, None, None, None),
        (world.h1_id, entries[IMPLEMENTATION], "2026-H1", None, None, None, None),
    ]
    assert [item["ssp_method"] for item in rows] == ["observable", "cost_plus_margin"]
    (version,) = world.place.rows(select(contract_version))
    assert (version["transaction_price"], version["total_ssp"], version["book_code"]) == (
        Decimal("135000.00"),
        Decimal(150000),
        "ASC606",
    )
    assert sum(item["allocated_amount"] for item in rows) == version["transaction_price"]
    for item in rows:
        assert item["allocated_amount"] == (
            item["revenue_cum"] + item["scheduled_amount"] + item["awaiting_trigger_amount"]
        )


def snapshot(world: World) -> dict[int, list[tuple[Any, ...]]]:
    rows = world.place.rows(
        select(
            obligation_version.c.version_no,
            obligation_version.c.obligation_key,
            obligation_version.c.ssp_book_version_id,
            obligation_version.c.ssp_entry_id,
            obligation_version.c.original_ssp_selected,
            obligation_version.c.allocation_weight,
            obligation_version.c.allocated_amount,
        ).order_by(obligation_version.c.version_no, obligation_version.c.obligation_key)
    )
    found: dict[int, list[tuple[Any, ...]]] = {}
    for item in rows:
        found.setdefault(item["version_no"], []).append(tuple(list(item.values())[1:]))
    return found


def test_ssp_snapshot_survives_later_publication(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    h2_id = approved_ssp_version(
        world.app,
        world.place.author,
        [world.priya, world.marcus],
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=[
            point_entry(PLATFORM, "140000.00", value_basis="AMOUNT"),
            point_entry(IMPLEMENTATION, "20000.00", "cost_plus_margin"),
        ],
    )
    bundle, _, stored = computed(world.place, group_id)
    assert [version.version_key for version in bundle.ssp_versions] == ["US-LIST@v1", "US-LIST@v2"]
    assert stored["pinned_refs"]["ssp_book_version_ids"] == sorted([world.h1_id, h2_id])
    # REQ-SSP-014: version 2 keeps the inception snapshot of every obligation.
    found = snapshot(world)
    assert sorted(found) == [1, 2]
    assert found[2] == found[1]
    assert [str(item[1]) for item in found[2]] == [world.h1_id, world.h1_id]


def test_schedules_versioned_never_deleted(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    first = world.place.rows(select(schedule_line).order_by(schedule_line.c.period_end_date))
    flag_change(world, booked.contract["id"], 2)
    computed(world.place, group_id)
    headers = world.place.rows(
        select(schedule.c.contract_version_id, schedule.c.schedule_kind, schedule.c.line_count)
    )
    versions = {
        item["version_no"]: item["id"]
        for item in world.place.rows(select(contract_version.c.version_no, contract_version.c.id))
    }
    assert sorted(
        (item["contract_version_id"], item["schedule_kind"]) for item in headers
    ) == sorted([(versions[1], "REVENUE"), (versions[2], "REVENUE")])
    # REQ-REC-020: the lines of version 1 stay as they were.
    kept = world.place.rows(
        select(schedule_line).where(schedule_line.c.contract_version_id == versions[1])
    )
    assert sorted(first, key=lambda item: str(item["id"])) == sorted(
        kept, key=lambda item: str(item["id"])
    )
    later = world.place.rows(
        select(schedule_line).where(schedule_line.c.contract_version_id == versions[2])
    )
    assert len(later) == len(first) == 12
    # PRD WLD-X-02: 88,855.89 − 79,091.51.
    september = world.place.rows(
        select(
            contract_version.c.version_no,
            schedule_line.c.amount,
            schedule_line.c.cumulative_amount,
            schedule_line.c.line_type,
            schedule_line.c.is_released_at_close,
        )
        .select_from(
            schedule_line.join(period, period.c.id == schedule_line.c.period_id).join(
                contract_version, contract_version.c.id == schedule_line.c.contract_version_id
            )
        )
        .where(period.c.period_key == "FY2026-P09")
        .order_by(contract_version.c.version_no)
    )
    assert [tuple(item.values()) for item in september] == [
        (1, Decimal("9764.38"), Decimal("88855.89"), "NORMAL", True),
        (2, Decimal("9764.38"), Decimal("88855.89"), "NORMAL", True),
    ]
    assert all(item["line_count"] == 12 for item in headers)


def test_l8_e_rate_stamp_takes_the_latest_rate_ref() -> None:
    """D-88 L7-6-Q-1: T-SL-04 holds one ``fx_rate_id``, so a foreign-currency line is stamped with
    the RateRef of the latest effective date, ties to the greatest rate key; a RateRef the bundle
    does not pin, or whose version differs, raises (REQ-FX-006)."""
    from erev_engine.bundle import FxRateInput

    def rate(key: str, on: date) -> FxRateInput:
        return FxRateInput(key, "FX@v1", "spot", "GBP", "USD", on, None, Decimal("1.2700"))

    pinned = {
        item.rate_key: item
        for item in (
            rate("FX@v1/spot/GBP/USD/2026-04-01", date(2026, 4, 1)),
            rate("FX@v1/spot/GBP/USD/2026-05-31", date(2026, 5, 31)),
            rate("FX@v1/average/GBP/USD/2026-05-31", date(2026, 5, 31)),
        )
    }
    version = UUID(int=9)
    ids = {
        key: (UUID(int=index), version, Decimal("1.2700") + index)
        for index, key in enumerate(pinned)
    }
    april, may, may_average = (
        (("FX@v1/spot/GBP/USD/2026-04-01", "FX@v1"),),
        (("FX@v1/spot/GBP/USD/2026-05-31", "FX@v1"),),
        (("FX@v1/average/GBP/USD/2026-05-31", "FX@v1"),),
    )
    # L8-merge: the stamp carries the rate of that fx_rate row, so T-SL-04 fx_rate is never NULL
    # beside fx_rate_id (API-S-SubledgerLine and the T-SL-06 drill format it).
    assert computation._rate_stamp("L", april, pinned, ids) == (
        UUID(int=0),
        version,
        Decimal("1.2700"),
    )
    assert computation._rate_stamp("L", (*april, *may), pinned, ids) == (
        UUID(int=1),
        version,
        Decimal("2.2700"),
    )
    # Same effective date: the greatest rate key wins ("FX@v1/spot/..." > "FX@v1/average/...").
    assert computation._rate_stamp("L", (*may_average, *may), pinned, ids) == (
        UUID(int=1),
        version,
        Decimal("2.2700"),
    )
    with pytest.raises(ValueError, match="does not pin"):
        computation._rate_stamp("L", (("FX@v1/spot/GBP/USD/2026-06-30", "FX@v1"),), pinned, ids)
    with pytest.raises(ValueError, match="does not pin"):
        computation._rate_stamp("L", (("FX@v1/spot/GBP/USD/2026-04-01", "FX@v2"),), pinned, ids)


def test_persist_idempotent_on_input_hash(world: World) -> None:
    booked = k01(world)
    run = engine()
    with world.place.uow() as uow:
        bundle = bundles.build(uow.session, booked.combination_group["id"], uow.now)
        output = run(bundle)
        first = computation.persist(uow, bundle, output)
        uow.commit()
    tables = (
        contract_computation,
        contract_version,
        obligation_version,
        schedule,
        schedule_line,
        calc_trace,
        computation_evidence,
        ledger_chain_head,
        subledger_posting,
        file_object,
        audit_event,
    )
    before = [count(world, table) for table in tables]
    with world.place.uow() as uow:
        second = computation.persist(uow, bundle, output)
        uow.commit()
    # RCP-21: the same input hash and engine version answer the stored computation.
    assert (first["replayed"], second["replayed"], second["id"]) == (False, True, first["id"])
    assert second["contract_version_ids"] == first["contract_version_ids"]
    assert second["input_sha256"] == bundle.sha256()
    assert [count(world, table) for table in tables] == before


def test_calc_trace_stored_and_reevaluates(world: World) -> None:
    booked = k01(world)
    _, output, _ = computed(world.place, booked.combination_group["id"])
    (trace_row,) = world.place.rows(select(calc_trace))
    (version,) = world.place.rows(select(contract_version))
    assert (version["calc_trace_id"], trace_row["contract_version_id"]) == (
        trace_row["id"],
        version["id"],
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        loaded = store.load_trace(session, version["id"])
    assert loaded is not None
    assert loaded == output.books[0].trace
    assert (
        trace_row["trace_sha256"],
        trace_row["node_count"],
        trace_row["book_code"],
        trace_row["format_version"],
        trace_row["engine_version"],
        trace_row["root_measures"],
    ) == (
        loaded.sha256(),
        len(loaded.nodes),
        "ASC606",
        1,
        ENGINE_VERSION,
        dict(loaded.root_measures),
    )
    assert loaded.nodes
    # DG-KRN-EXP-04, 05: every stored node re-evaluates to its stored value.
    assert reevaluate(loaded) == {node.id: node.value for node in loaded.nodes}
    node_ids = {node.id for node in loaded.nodes}
    for item in world.place.rows(select(obligation_version.c.trace_nodes)):
        assert set(item["trace_nodes"].values()) <= node_ids
    lines = world.place.rows(select(schedule_line.c.trace_node_id))
    assert {item["trace_node_id"] for item in lines} <= node_ids
    tampered = {**trace_row, "trace_sha256": "0" * 64}
    with pytest.raises(store.TraceIntegrityError):
        store.trace_from_row(tampered)


def test_versions_immutable_and_hashed(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    bundle, output, stored = computed(world.place, group_id)
    events = world.place.rows(
        select(contract_event.c.id, contract_event.c.recorded_at).order_by(
            contract_event.c.stream_version
        )
    )
    (row,) = world.place.rows(select(contract_computation))
    (version,) = world.place.rows(select(contract_version))
    assert (row["engine_version"], row["input_sha256"], row["known_at"]) == (
        ENGINE_VERSION,
        bundle.sha256(),
        max(item["recorded_at"] for item in events),
    )
    assert (
        version["contract_computation_id"],
        version["cause_event_ids"],
        version["output_sha256"],
        version["version_no"],
        version["previous_version_id"],
        version["known_at"],
    ) == (row["id"], [item["id"] for item in events], output.sha256(), 1, None, row["known_at"])
    assert world.place.scalar(select(contract.c.latest_computation_id)) == stored["id"]
    group = world.place.rows(
        select(combination_group.c.head_computation_id, combination_group.c.dirty_since)
    )
    assert group == [{"head_computation_id": stored["id"], "dirty_since": None}]
    # REQ-CON-014: erev_app holds no UPDATE on a computed version.
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                update(contract_version)
                .where(contract_version.c.id == version["id"])
                .values(transaction_price=Decimal("1"))
            )
        savepoint.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    assert world.place.scalar(select(contract_version.c.transaction_price)) == Decimal("135000")
    # The next version names the events it first includes and its predecessor.
    flag_change(world, booked.contract["id"], 2)
    computed(world.place, group_id)
    latest = world.place.rows(select(contract_version).where(contract_version.c.version_no == 2))
    flagged = world.place.scalar(
        select(contract_event.c.id).where(contract_event.c.stream_version == 3)
    )
    assert (latest[0]["previous_version_id"], latest[0]["cause_event_ids"]) == (
        version["id"],
        [flagged],
    )


def without_lineage(output: OutputBundle) -> OutputBundle:
    book_output = output.books[0]
    first = book_output.obligation_versions[0]
    broken = replace(
        first,
        columns=MappingProxyType(
            {**first.columns, "ssp_book_version_key": None, "ssp_entry_key": None}
        ),
    )
    books = (
        replace(book_output, obligation_versions=(broken, *book_output.obligation_versions[1:])),
        *output.books[1:],
    )
    return replace(output, books=books)


@pytest.mark.control("CTL-011")
def test_ctl_011_allocation_lineage_recorded_per_obligation(world: World) -> None:
    booked = k01(world)
    run = engine()
    with world.place.uow() as uow:
        bundle = bundles.build(uow.session, booked.combination_group["id"], uow.now)
        output = run(bundle)
        with pytest.raises(EngineError) as excinfo:
            computation.persist(uow, bundle, without_lineage(output))
    error = excinfo.value
    assert (error.code, error.subject_key) == ("ENGINE_INVARIANT_VIOLATED", "SF-ORD-10001/O1")
    assert error.detail == {
        "control": "CTL-011",
        "rule": "REQ-SSP-011",
        "book_code": "ASC606",
        "columns": "ssp_book_version_key,ssp_entry_key",
        "count": "1",
    }
    assert computation.lineage_findings(bundle, output) == []
    for table in (contract_computation, contract_version, obligation_version, calc_trace):
        assert count(world, table) == 0
    # With lineage on every obligation the computation persists.
    with world.place.uow() as uow:
        stored = computation.persist(uow, bundle, output)
        uow.commit()
    assert count(world, obligation_version) == 2
    assert stored["replayed"] is False


@pytest.mark.control("CTL-011")
def test_computation_persists_selected_range_identity(world: World) -> None:
    booked = k01(world)
    with world.place.uow() as uow:
        bundle = bundles.build(uow.session, booked.combination_group["id"], uow.now)
        output = engine()(bundle)
        index = bundles.index(uow.session, bundle)
        keys = [item.columns.get("ssp_range_key") for item in output.books[0].obligation_versions]
        assert any(keys)
        computation.persist(uow, bundle, output)
        uow.commit()
    with world.place.uow() as uow:
        rows = uow.session.execute(
            select(
                obligation_version.c.ssp_range_id,
                obligation_version.c.ssp_entry_id,
            )
        ).all()
        actual = {row.ssp_range_id for row in rows if row.ssp_range_id is not None}
        assert actual == {index.ssp_ranges[str(key)] for key in keys if key is not None}
        for row in rows:
            if row.ssp_range_id is not None:
                assert (
                    uow.session.scalar(
                        select(ssp_range.c.ssp_entry_id).where(ssp_range.c.id == row.ssp_range_id)
                    )
                    == row.ssp_entry_id
                )


def test_computation_retains_typed_original_evidence(world: World) -> None:
    booked = k01(world)
    with world.place.uow() as uow:
        bundle = bundles.build(uow.session, booked.combination_group["id"], uow.now)
        output = engine()(bundle)
        cutoffs = dict(
            uow.session.execute(
                select(ledger_chain_head.c.book_code, ledger_chain_head.c.last_chain_seq)
            )
            .tuples()
            .all()
        )
        produced = computation.persist(uow, bundle, output)
        row = (
            uow.session.execute(
                select(computation_evidence).where(
                    computation_evidence.c.contract_computation_id == produced["id"]
                )
            )
            .mappings()
            .one()
        )
        assert row["captured"] == "AT_COMPUTATION"
        assert row["ledger_cutoff"] == {
            book.book_code: cutoffs[book.book_code] for book in bundle.books
        }
        assert row["input_sha256"] == bundle.sha256()
        assert row["output_sha256"] == output.sha256()
        assert row["book_codes"] == [
            book.book_code for book in output.books if book.contract_version is not None
        ]
        contents = []
        for name in ("input", "output"):
            meta, stream = open_file(
                uow.session, row[f"{name}_file_id"], files=uow.files, keyring=uow.keyring
            )
            with stream:
                content = stream.read()
            assert (
                hashlib.sha256(content).hexdigest() == row[f"{name}_file_sha256"] == meta["sha256"]
            )
            assert meta["purpose"] == f"COMPUTATION_{name.upper()}"
            assert uow.files.exists(str(meta["storage_key"]) + ".dek")
            holds = file_evidence.holds_in(uow.session, row[f"{name}_file_id"])
            assert any(hold.reference.table == "computation_evidence" for hold in holds)
            assert file_evidence.first_refusing(holds) is not None
            contents.append(content)
        restored = upgrade.decode_input(contents[0])
        assert restored == bundle
        assert restored.known_at == bundle.known_at
        assert engine()(restored).sha256() == output.sha256()
        assert contents[1] == upgrade.encode_output(output)
        uow.commit()
    # Evidence is append-only, just like the computed versions it proves.
    with (
        pytest.raises(
            exc.ProgrammingError, match="permission denied for table computation_evidence"
        ),
        world.place.uow() as uow,
    ):
        uow.session.execute(
            update(computation_evidence)
            .where(computation_evidence.c.contract_computation_id == produced["id"])
            .values(input_sha256="0" * 64)
        )
        uow.commit()


def test_computation_evidence_failure_rolls_back_before_posting(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    booked = k01(world)
    observed_tables = (
        contract_computation,
        computation_evidence,
        contract_version,
        subledger_posting,
        file_object,
    )
    before = [count(world, table) for table in observed_tables]
    store_original = store_file
    calls = 0

    def fail_output(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated output storage failure")
        return store_original(*args, **kwargs)

    monkeypatch.setattr(evidence_writer, "store_file", fail_output)
    with pytest.raises(OSError, match="simulated output storage failure"), world.place.uow() as uow:
        bundle = bundles.build(uow.session, booked.combination_group["id"], uow.now)
        computation.persist(uow, bundle, engine()(bundle))
        uow.commit()
    assert calls == 2
    assert [count(world, table) for table in observed_tables] == before


def test_computation_evidence_links_predecessor_and_has_no_generic_download(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    (first,) = world.place.rows(select(computation_evidence))
    assert first["previous_computation_id"] is None
    flag_change(world, booked.contract["id"], 2)
    computed(world.place, group_id)
    rows = world.place.rows(select(computation_evidence))
    assert len(rows) == 2
    second = next(
        row for row in rows if row["contract_computation_id"] != first["contract_computation_id"]
    )
    assert second["previous_computation_id"] == first["contract_computation_id"]
    assert (
        next(
            row
            for row in rows
            if row["contract_computation_id"] == first["contract_computation_id"]
        )
        == first
    )
    for row in rows:
        for column in ("input_file_id", "output_file_id"):
            for suffix in ("", "/content"):
                response = get(
                    world.app, f"/api/v1/files/{row[column]}{suffix}", world.place.author
                )
                assert response.status_code == 404, response.text


def test_report_reads_original_computation_after_group_advances(world: World) -> None:
    booked = k01(world)
    group_id = booked.combination_group["id"]
    bundle, output, first = computed(world.place, group_id)
    flag_change(world, booked.contract["id"], 2)
    _, second_output, second = computed(world.place, group_id)
    report_only = replace(
        world.place.principal,
        permissions=world.place.principal.permissions - {"contract.read"},
    )
    with world.place.uow(report_only) as uow:
        retained = computation_sources.read_for_report(uow, first["id"])
        assert retained.bundle == bundle
        assert retained.engine_release_id == first["engine_release_id"]
        assert retained.output_sha256 == output.sha256()
        assert engine()(retained.bundle).sha256() == output.sha256()
        assert retained.previous_computation_id is None
        assert retained.bundle.events[-1].stream_version == 2
        assert retained.output == upgrade.output_mapping(output)

        latest = computation_sources.read_for_report(uow, second["id"])
        assert latest.previous_computation_id == first["id"]
        assert latest.output_sha256 == second_output.sha256()


@pytest.mark.parametrize("name", ["input", "output"])
@pytest.mark.parametrize(
    "fault", ["bytes", "purpose", "size", "digest", "forged metadata", "missing"]
)
def test_report_refuses_corrupt_computation_files(
    world: World, monkeypatch: pytest.MonkeyPatch, fault: str, name: str
) -> None:
    booked = k01(world)
    _, _, produced = computed(world.place, booked.combination_group["id"])
    streams: list[io.BytesIO] = []

    def altered(*args: Any, **kwargs: Any) -> Any:
        meta, stream = open_file(*args, **kwargs)
        with stream:
            content = stream.read()
        if str(meta["purpose"]) != f"COMPUTATION_{name.upper()}":
            return meta, io.BytesIO(content)
        if fault == "missing":
            raise FileNotFoundError("retained file absent")
        changed = dict(meta)
        if fault == "forged metadata":
            content += b" "
            changed["size_bytes"] = len(content)
            changed["sha256"] = hashlib.sha256(content).hexdigest()
        if fault == "bytes":
            content += b" "
        if fault == "purpose":
            changed["purpose"] = "REPORT_OUTPUT"
        if fault == "size":
            changed["size_bytes"] += 1
        if fault == "digest":
            changed["sha256"] = "0" * 64
        result = io.BytesIO(content)
        streams.append(result)
        return changed, result

    monkeypatch.setattr(computation_sources, "open_file", altered)
    with world.place.uow() as uow, pytest.raises(Problem) as caught:
        computation_sources.read_for_report(uow, produced["id"])
    assert caught.value.slug == "validation-failed"
    reason = "EVIDENCE_MISSING" if fault == "missing" else "EVIDENCE_HASH_MISMATCH"
    assert caught.value.errors[0].rule_id == f"{name.upper()}_{reason}"
    assert (streams or fault == "missing") and all(stream.closed for stream in streams)


@pytest.mark.parametrize(
    "scope",
    [
        "no report permission",
        "hidden entity",
        "hidden failed",
        "different tenant",
        "system",
    ],
)
def test_report_authorizes_computation_before_reading_files(
    world: World, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    booked = k01(world)
    _, _, produced = computed(world.place, booked.combination_group["id"])
    if scope == "hidden failed":
        (source,) = world.place.rows(
            select(contract_computation).where(contract_computation.c.id == produced["id"])
        )
        failed_id = UUID(int=7788)
        with world.place.uow() as uow:
            with uow.as_system():
                uow.session.execute(
                    insert(contract_computation).values(
                        **{
                            **source,
                            "id": failed_id,
                            "status": "FAILED",
                            "problem": {"detail": "failure"},
                        }
                    )
                )
            uow.commit()
        produced = {**produced, "id": failed_id}
    principal = world.place.principal
    if scope == "no report permission":
        principal = replace(principal, permissions=principal.permissions - {"report.run"})
    elif scope == "different tenant":
        principal = replace(principal, tenant_id=UUID(int=999))
    elif scope == "system":
        principal = system_principal(principal.tenant_id)
    else:
        principal = replace(
            principal,
            permission_scopes={
                **principal.permission_scopes,
                "report.run": frozenset({UUID(int=999)}),
            },
        )

    def unread(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Evidence files must not be read for an unauthorized caller")

    monkeypatch.setattr(computation_sources, "open_file", unread)
    with world.place.uow(principal) as uow, pytest.raises(Problem) as caught:
        computation_sources.read_for_report(uow, produced["id"])
    assert caught.value.slug == (
        "not-found"
        if scope in {"hidden entity", "hidden failed", "different tenant"}
        else "forbidden"
    )


def test_report_missing_evidence_never_rebuilds_current_inputs(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    booked = k01(world)
    # Simulate a computation written before 0160: it has versions but no retained files.
    monkeypatch.setattr(evidence_writer, "retain", lambda *args, **kwargs: None)
    _, _, produced = computed(world.place, booked.combination_group["id"])

    def forbidden_rebuild(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Missing historical evidence cannot use current inputs or files")

    monkeypatch.setattr(bundles, "build", forbidden_rebuild)
    monkeypatch.setattr(computation_sources, "open_file", forbidden_rebuild)
    with world.place.uow() as uow, pytest.raises(Problem) as caught:
        computation_sources.read_for_report(uow, produced["id"])
    assert caught.value.errors[0].rule_id == "INPUT_EVIDENCE_MISSING"


def test_verification_schema_guards_execution_identity_and_acceptance(world: World) -> None:
    from uuid import uuid4

    from erev_api.db.tables import (
        computation_verification,
        release_validation,
        release_validation_attempt,
        release_validation_group,
    )
    from erev_api.db.transitions import apply
    from erev_api.enums import JobKind
    from erev_api.jobs.registry import insert_job

    booked = k01(world)
    group_id = booked.combination_group["id"]
    _, output, source = computed(world.place, group_id)
    with world.place.uow() as uow:
        stamps = {
            "tenant_id": uow.principal.tenant_id,
            "created_at": uow.now,
            "created_by": uow.principal.id,
            "created_by_kind": uow.principal.kind.value,
        }
        mutable = {
            **stamps,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        }
        release_id, attempt_id, selected_id = uuid4(), uuid4(), uuid4()
        uow.session.execute(
            insert(release_validation).values(
                **mutable,
                id=release_id,
                engine_release_id=source["engine_release_id"],
                effective_level="MINOR",
                status="RUNNING",
            )
        )
        uow.session.execute(
            insert(release_validation_attempt).values(
                **mutable,
                id=attempt_id,
                release_validation_id=release_id,
                attempt_no=1,
                seed=20260912,
                population={},
                required_entity_ids=[world.entity_id],
                status="RUNNING",
            )
        )
        uow.session.execute(
            insert(release_validation_group).values(
                **mutable,
                id=selected_id,
                release_validation_attempt_id=attempt_id,
                combination_group_id=group_id,
                source_computation_id=None if source is None else source["id"],
                selection="OPEN_ACTIVITY",
                strata=[],
                rank_sha256="a" * 64,
                orchestration_state="RUNNING",
            )
        )
        job_row = insert_job(
            uow.session,
            JobKind.REPLAY_VERIFY,
            {},
            tenant_id=uow.principal.tenant_id,
            now=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind,
            lock=f"verify:{group_id}",
        )
        row = {
            **stamps,
            "source_computation_id": source["id"],
            "combination_group_id": group_id,
            "trigger": "REPLAY_VERIFY",
            "source_engine_release_id": source["engine_release_id"],
            "source_engine_version": ENGINE_VERSION,
            "process_engine_release_id": source["engine_release_id"],
            "process_engine_version": ENGINE_VERSION,
            "engine_executed": True,
            "executed_engine_release_id": source["engine_release_id"],
            "executed_engine_version": ENGINE_VERSION,
            "actual_output_sha256": output.sha256(),
            "outcome": "MATCH",
            "release_validation_attempt_id": attempt_id,
            "job_id": job_row["id"],
            "task_id": 11,
            "attempt": 1,
            "duration_ms": 10,
        }
        bad_cases: list[dict[str, Any]] = [
            {"executed_engine_release_id": None},
            {"executed_engine_version": None},
            {"engine_executed": False},
            {
                "engine_executed": False,
                "executed_engine_release_id": None,
                "executed_engine_version": None,
            },
            {"source_engine_version": None},
            {"executed_engine_version": "9.9.9"},
            {"source_computation_id": None},
            {"trigger": "EVENT"},
            {"outcome": "ERROR"},
            {"attempt": 0},
            {"duration_ms": -1},
        ]
        for change in bad_cases:
            with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
                uow.session.execute(
                    insert(computation_verification).values(**{**row, **change, "id": uuid4()})
                )
        error_id = uuid4()
        uow.session.execute(
            insert(computation_verification).values(
                **{
                    **row,
                    "id": error_id,
                    "actual_output_sha256": None,
                    "outcome": "ERROR",
                    "reason": "ENGINE_ERROR",
                }
            )
        )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            apply(
                uow.session,
                "release_validation_group",
                selected_id,
                to_status="COMPLETE",
                expected_status="RUNNING",
                expected_row_version=1,
                set_values={"accepted_verification_id": error_id},
            )
        match_id = uuid4()
        good = {**row, "id": match_id, "task_id": 12, "attempt": 2}
        uow.session.execute(insert(computation_verification).values(**good))
        other_attempt, other_result = uuid4(), uuid4()
        uow.session.execute(
            insert(release_validation_attempt).values(
                **mutable,
                id=other_attempt,
                release_validation_id=release_id,
                attempt_no=2,
                seed=20260912,
                population={},
                required_entity_ids=[world.entity_id],
                status="RUNNING",
            )
        )
        uow.session.execute(
            insert(computation_verification).values(
                **{**good, "id": other_result, "release_validation_attempt_id": other_attempt}
            )
        )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            apply(
                uow.session,
                "release_validation_group",
                selected_id,
                to_status="COMPLETE",
                expected_status="RUNNING",
                expected_row_version=1,
                set_values={"accepted_verification_id": other_result},
            )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            uow.session.execute(insert(computation_verification).values(**{**good, "id": uuid4()}))
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            uow.session.execute(
                update(computation_verification)
                .where(computation_verification.c.id == match_id)
                .values(duration_ms=20)
            )
        apply(
            uow.session,
            "release_validation_group",
            selected_id,
            to_status="COMPLETE",
            expected_status="RUNNING",
            expected_row_version=1,
            set_values={"accepted_verification_id": match_id},
        )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            uow.session.execute(
                update(release_validation_attempt)
                .where(release_validation_attempt.c.id == attempt_id)
                .values(population={"changed": True})
            )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            apply(
                uow.session,
                "release_validation",
                release_id,
                to_status="PASSED",
                expected_status="RUNNING",
                expected_row_version=1,
                set_values={"enabled_at": uow.now, "accepted_attempt_id": attempt_id},
            )
        apply(
            uow.session,
            "release_validation_attempt",
            attempt_id,
            to_status="COMPLETE",
            expected_status="RUNNING",
            expected_row_version=1,
            set_values={},
        )
        apply(
            uow.session,
            "release_validation",
            release_id,
            to_status="PASSED",
            expected_status="RUNNING",
            expected_row_version=1,
            set_values={"enabled_at": uow.now, "accepted_attempt_id": attempt_id},
        )

        apply(
            uow.session,
            "release_validation_attempt",
            other_attempt,
            to_status="COMPLETE",
            expected_status="RUNNING",
            expected_row_version=1,
            set_values={},
        )
        with pytest.raises(exc.DBAPIError), uow.session.begin_nested():
            uow.session.execute(
                update(release_validation)
                .where(release_validation.c.id == release_id)
                .values(accepted_attempt_id=other_attempt)
            )
        uow.commit()
    from alembic import command
    from erev_api.db.session import DbContext, tenant_session
    from support.db import alembic_config

    # Published evidence remains visible to its tenant and hidden from an unrelated tenant.
    for tenant_id, expected in ((world.place.principal.tenant_id, 3), (uuid4(), 0)):
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            assert (
                session.scalar(select(func.count()).select_from(computation_verification))
                == expected
            )
    # A populated evidence schema must not silently disappear on downgrade.
    with pytest.raises(exc.DBAPIError):
        command.downgrade(alembic_config(), "0160")


@dataclass(frozen=True)
class VerificationCase:
    context: JobContext
    decision: VerificationRow
    selection_id: UUID
    group_id: UUID
    contract_id: UUID


def verification_case(
    world: World, *, with_source: bool = True, queued_only: bool = False
) -> VerificationCase:
    from uuid import uuid4

    from erev_api.controls.release import current_release
    from erev_api.db.tables import (
        release_validation,
        release_validation_attempt,
        release_validation_group,
    )
    from erev_api.db.transitions import apply
    from erev_api.domain.contracts.release_validation import ExecutionToken
    from erev_api.domain.contracts.replay_verify import (
        EvidenceFacts,
        ProcessFacts,
        SourceFacts,
        verify,
    )
    from erev_api.enums import JobKind
    from erev_api.jobs.context import JobAttempt, JobContext, JobRuntime
    from erev_api.jobs.registry import dispatch, insert_job

    booked = k01(world)
    group_id = booked.combination_group["id"]
    bundle, output, source = computed(world.place, group_id) if with_source else (None, None, None)
    release = current_release()
    assert release is not None
    assert source is None or release.id == source["engine_release_id"]
    with world.place.uow() as uow:
        stamps = {
            "tenant_id": uow.principal.tenant_id,
            "created_at": uow.now,
            "created_by": uow.principal.id,
            "created_by_kind": uow.principal.kind.value,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        }
        validation_id, attempt_id, selection_id = uuid4(), uuid4(), uuid4()
        uow.session.execute(
            insert(release_validation).values(
                **stamps,
                id=validation_id,
                engine_release_id=release.id,
                effective_level="MINOR",
                status="RUNNING",
            )
        )
        uow.session.execute(
            insert(release_validation_attempt).values(
                **stamps,
                id=attempt_id,
                release_validation_id=validation_id,
                attempt_no=1,
                seed=20260912,
                population={},
                required_entity_ids=[world.entity_id],
                status="RUNNING",
            )
        )
        queued = insert_job(
            uow.session,
            JobKind.REPLAY_VERIFY,
            {
                "release_validation_attempt_id": str(attempt_id),
                "combination_group_id": str(group_id),
                "trigger": "REPLAY_VERIFY",
            },
            subject_type="combination_group",
            subject_id=group_id,
            tenant_id=uow.principal.tenant_id,
            now=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind,
            lock=f"verify:{group_id}",
        )
        task = dispatch(
            uow.session,
            job_id=queued["id"],
            tenant_id=uow.principal.tenant_id,
            queue="compute",
            now=uow.now,
        )
        if not queued_only:
            apply(
                uow.session,
                "job",
                queued["id"],
                to_status="RUNNING",
                expected_status="QUEUED",
                expected_row_version=1,
                set_values={"started_at": uow.now},
            )
        uow.session.execute(
            insert(release_validation_group).values(
                **stamps,
                id=selection_id,
                release_validation_attempt_id=attempt_id,
                combination_group_id=group_id,
                source_computation_id=None if source is None else source["id"],
                selection="OPEN_ACTIVITY",
                strata=[],
                rank_sha256="a" * 64,
                orchestration_state="PENDING" if queued_only else "RUNNING",
                child_job_id=queued["id"],
            )
        )
        runtime = JobRuntime(
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
            engine_release=release,
            attempt=JobAttempt(queued["id"], uow.principal.tenant_id, task, 1),
        )
        context = JobContext(
            job_id=queued["id"],
            tenant_id=uow.principal.tenant_id,
            kind=JobKind.REPLAY_VERIFY,
            principal=uow.principal,
            runtime=runtime,
        )
        uow.commit()
    if source is None:
        from erev_api.domain.contracts.replay_verify import no_source

        decision = no_source(
            trigger="REPLAY_VERIFY",
            group_id=group_id,
            process=ProcessFacts(release.id, release.engine_version),
            token=ExecutionToken(queued["id"], task, 1),
            attempt_id=attempt_id,
        )
        return VerificationCase(context, decision, selection_id, group_id, booked.contract["id"])
    assert bundle is not None and output is not None
    input_bytes, output_bytes = upgrade.encode_input(bundle), upgrade.encode_output(output)
    decision = verify(
        trigger="REPLAY_VERIFY",
        source=SourceFacts(
            source["id"],
            group_id,
            release.id,
            release.engine_version,
            source["input_sha256"],
            {"ASC606": output.sha256()},
            source["cutoff_at"],
        ),
        evidence=EvidenceFacts(
            input_bytes,
            upgrade.raw_digest(input_bytes),
            output_bytes,
            upgrade.raw_digest(output_bytes),
            output.sha256(),
            ("ASC606",),
            {"format_version": bundle.format_version, "engine_version": bundle.engine_version},
        ),
        process=ProcessFacts(release.id, release.engine_version),
        engine=engine(),
        token=ExecutionToken(queued["id"], task, 1),
        attempt_id=attempt_id,
    )
    return VerificationCase(context, decision, selection_id, group_id, booked.contract["id"])


def test_verification_store_atomic_result_pointer_and_duplicate(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from erev_api.db.tables import (
        computation_verification,
        release_validation_group,
        subledger_posting,
    )
    from erev_api.domain.contracts import verification_store

    case = verification_case(world)
    with world.place.uow() as uow:
        before = [
            uow.session.scalar(select(func.count()).select_from(table))
            for table in (contract_computation, contract_version, subledger_posting)
        ]
    original = verification_store._Store.set_orchestration

    def fail_pointer(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("pointer write interrupted")

    monkeypatch.setattr(verification_store._Store, "set_orchestration", fail_pointer)
    with pytest.raises(RuntimeError, match="interrupted"), world.place.uow() as uow:
        verification_store.persist(uow, case.decision, context=case.context, duration_ms=10)
        uow.commit()
    monkeypatch.setattr(verification_store._Store, "set_orchestration", original)
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 0
        first = verification_store.persist(uow, case.decision, context=case.context, duration_ms=10)
        assert first.result == "inserted" and first.row_id == first.accepted_id
        (event,) = uow.audit_events
        assert event["action"] == "release_validation_group.verify"
        assert event["object_id"] == case.selection_id
        assert event["detail"]["contract_id"] == str(case.contract_id)
        uow.commit()
    with world.place.uow() as uow:
        again = verification_store.persist(uow, case.decision, context=case.context, duration_ms=20)
        assert again.result == "duplicate" and again.row_id == first.row_id
        assert not uow.audit_events
        selected = (
            uow.session.execute(
                select(release_validation_group).where(
                    release_validation_group.c.id == case.selection_id
                )
            )
            .mappings()
            .one()
        )
        assert selected["orchestration_state"] == "COMPLETE"
        assert selected["accepted_verification_id"] == first.row_id
        row = uow.session.execute(select(computation_verification)).mappings().one()
        assert row["actual_output_sha256"] == case.decision.actual_output_sha256
        assert row["duration_ms"] == 10
        assert before == [
            uow.session.scalar(select(func.count()).select_from(table))
            for table in (contract_computation, contract_version, subledger_posting)
        ]
        uow.commit()


@pytest.mark.parametrize("failure", ["stale task", "changed head", "wrong token", "wrong release"])
def test_verification_store_refuses_changed_execution_or_selection(
    world: World, failure: str
) -> None:
    from erev_api.db.tables import computation_verification, job
    from erev_api.domain.contracts import verification_store
    from erev_api.jobs.context import JobLost

    case = verification_case(world)
    decision = case.decision
    if failure == "stale task":
        with world.place.uow() as uow:
            uow.session.execute(
                update(job).where(job.c.id == case.context.job_id).values(procrastinate_job_id=None)
            )
            uow.commit()
    elif failure == "changed head":
        flag_change(world, case.contract_id, 2)
        computed(world.place, case.group_id)
    elif failure == "wrong token":
        decision = replace(decision, token=replace(decision.token, attempt=2))
    else:
        decision = replace(decision, process_engine_version="9.9.9")
    with pytest.raises((Problem, JobLost)), world.place.uow() as uow:
        verification_store.persist(uow, decision, context=case.context, duration_ms=10)
        uow.commit()
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 0


def test_verification_store_keeps_error_then_accepts_retry(world: World) -> None:
    from erev_api.db.tables import computation_verification, release_validation_group
    from erev_api.db.transitions import apply
    from erev_api.domain.contracts import verification_store
    from erev_api.enums import VerificationOutcome
    from erev_api.jobs.registry import dispatch
    from sqlalchemy import text

    case = verification_case(world)
    error = replace(
        case.decision,
        outcome=VerificationOutcome.ERROR,
        reason="ENGINE_ERROR",
        actual_output_sha256=None,
    )
    with world.place.uow() as uow:
        first = verification_store.persist(uow, error, context=case.context, duration_ms=10)
        assert first.accepted_id is None
        selected = (
            uow.session.execute(
                select(release_validation_group).where(
                    release_validation_group.c.id == case.selection_id
                )
            )
            .mappings()
            .one()
        )
        assert selected["orchestration_state"] == "RUNNING"
        assert selected["accepted_verification_id"] is None
        uow.commit()
    with world.place.uow() as uow:
        uow.session.execute(
            text("UPDATE procrastinate_jobs SET status='failed' WHERE id=:id"),
            {"id": case.context.task_id},
        )
        apply(
            uow.session,
            "job",
            case.context.job_id,
            to_status="QUEUED",
            expected_status="RUNNING",
            expected_row_version=1,
            set_values={},
        )
        task = dispatch(
            uow.session,
            job_id=case.context.job_id,
            tenant_id=uow.principal.tenant_id,
            queue="compute",
            now=uow.now,
            attempt=2,
        )
        apply(
            uow.session,
            "job",
            case.context.job_id,
            to_status="RUNNING",
            expected_status="QUEUED",
            expected_row_version=1,
            set_values={},
        )
        for old, new, version in (("RUNNING", "RETRYABLE", 1), ("RETRYABLE", "RUNNING", 2)):
            apply(
                uow.session,
                "release_validation_group",
                case.selection_id,
                to_status=new,
                expected_status=old,
                expected_row_version=version,
                set_values={"row_version": version + 1},
            )
        uow.commit()
    previous = case.context.runtime.attempt
    assert previous is not None
    context = JobContext(
        job_id=case.context.job_id,
        tenant_id=case.context.tenant_id,
        kind=case.context.kind,
        principal=case.context.principal,
        runtime=replace(
            case.context.runtime, attempt=replace(previous, task_id=task, attempt_number=2)
        ),
    )
    retry = replace(case.decision, token=replace(case.decision.token, task_id=task, attempt=2))
    with world.place.uow() as uow:
        second = verification_store.persist(uow, retry, context=context, duration_ms=20)
        assert second.accepted_id == second.row_id and second.row_id != first.row_id
        rows = (
            uow.session.execute(
                select(computation_verification.c.outcome).order_by(
                    computation_verification.c.attempt
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["ERROR", "MATCH"]
        uow.commit()


def test_validation_population_reads_heads_activity_and_methods(world: World) -> None:
    from erev_api.domain.contracts.validation_population import read

    booked = k01(world)
    group_id = booked.combination_group["id"]
    with world.place.uow() as uow:
        before = read(uow)
        group = next(item for item in before.groups if item.group_id == group_id)
        assert group.open_activity
        assert before.required_entity_ids == (world.entity_id,)
        assert group.head_computation_id is None and group.strata == frozenset()
    _, _, source = computed(world.place, group_id)
    with world.place.uow() as uow:
        population = read(uow)
        group = next(item for item in population.groups if item.group_id == group_id)
        assert group.head_computation_id == source["id"]
        assert group.open_activity
        assert group.strata == frozenset({("ASC606", "TIME_ELAPSED"), ("ASC606", "OUTPUT_PERCENT")})
        assert population.required_entity_ids == (world.entity_id,)


def test_validation_population_refuses_partial_entity_scope(world: World) -> None:
    from erev_api.domain.contracts.validation_population import read

    principal = replace(world.place.principal, entity_scope=(world.entity_id,))
    with world.place.uow(principal) as uow, pytest.raises(Problem, match="complete tenant"):
        read(uow)


def test_validation_population_empty_other_tenant(world: World) -> None:
    from erev_api.domain.contracts.validation_population import read

    k01(world)
    principal = replace(world.place.principal, tenant_id=UUID(int=999))
    with world.place.uow(principal) as uow:
        population = read(uow)
        assert population.groups == ()
        assert population.required_entity_ids == ()


def test_validation_population_future_activity_is_not_open(world: World) -> None:
    from erev_api.domain.contracts.validation_population import read

    booked = booked_contract(
        world.place,
        {
            "external_id": "FUTURE-POPULATION",
            "customer_id": str(world.customer_id),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-10-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM,
                    "quantity": "1",
                    "total_price": {"amount": "120.00", "currency": "USD"},
                    "start_date": "2026-10-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
        activate=False,
    )
    with world.place.uow() as uow:
        population = read(uow)
        group = next(
            item for item in population.groups if item.group_id == booked.combination_group["id"]
        )
        assert not group.open_activity
        assert group.head_computation_id is None
        assert group.strata == frozenset()
        assert population.required_entity_ids == (world.entity_id,)


def test_validation_population_requires_sealed_ledger_activity(world: World) -> None:
    from erev_api.db.tables import subledger_line, subledger_posting, subledger_posting_seal
    from erev_api.domain.contracts.validation_population import read
    from support.rows import (
        insert_ledger_parts,
        ledger_seal_values,
        subledger_line_values,
        subledger_posting_values,
    )

    with world.place.uow() as uow:
        tenant_id = world.place.tenant_id
        parts = insert_ledger_parts(uow.session, tenant_id)
        posting = subledger_posting_values(tenant_id, parts=parts)
        uow.session.execute(insert(subledger_posting).values(**posting))
        lines = [
            subledger_line_values(tenant_id, posting=posting, parts=parts, amount=amount)
            for amount in (Decimal("10.00"), Decimal("-10.00"))
        ]
        uow.session.execute(insert(subledger_line), lines)
        before = next(group for group in read(uow).groups if group.group_id == parts.chain.group_id)
        assert not before.open_activity  # this probe has no contract events or current members
        seal = ledger_seal_values(uow.session, tenant_id, posting=posting, lines=lines)
        uow.session.execute(insert(subledger_posting_seal).values(**seal))
        after = next(group for group in read(uow).groups if group.group_id == parts.chain.group_id)
        assert after.open_activity
        uow.commit()


def pending_validation(world: World) -> UUID:
    from erev_api.controls.release import current_release
    from erev_api.db import new_id
    from erev_api.db.tables import release_validation

    release = current_release()
    assert release is not None
    validation_id = new_id()
    with world.place.uow() as uow:
        uow.session.execute(
            insert(release_validation).values(
                tenant_id=world.place.tenant_id,
                id=validation_id,
                engine_release_id=release.id,
                effective_level="MINOR",
                status="PENDING",
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
                updated_at=uow.now,
                updated_by=uow.principal.id,
                updated_by_kind=uow.principal.kind.value,
            )
        )
        uow.commit()
    return validation_id


def test_validation_attempt_freeze_preserves_selection_on_retry(world: World) -> None:
    from erev_api.db.tables import job, release_validation_attempt, release_validation_group
    from erev_api.domain.contracts.validation_attempts import freeze

    booked = k01(world)
    group_id = booked.combination_group["id"]
    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        jobs_before = uow.session.scalar(select(func.count()).select_from(job))
        first = freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912)
        assert first.created
        assert len(uow.audit_events) == 1
        uow.commit()
    # The frozen NO_SOURCE remains NO_SOURCE even after a computation becomes available.
    computed(world.place, group_id)
    with world.place.uow() as uow:
        again = freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912)
        assert again.id == first.id and not again.created
        assert not uow.audit_events
        attempt = uow.session.execute(select(release_validation_attempt)).mappings().one()
        assert attempt["status"] == "SELECTED"
        assert attempt["required_entity_ids"] == [world.entity_id]
        assert attempt["population"]["no_source"] == 1
        selected = uow.session.execute(select(release_validation_group)).mappings().one()
        assert selected["source_computation_id"] is None
        assert selected["combination_group_id"] == group_id
        assert selected["selection"] == "OPEN_ACTIVITY"
        assert selected["child_job_id"] is None and selected["orchestration_state"] == "PENDING"
        assert uow.session.scalar(select(func.count()).select_from(job)) == jobs_before
        uow.commit()


def test_validation_attempt_freeze_rolls_back_selection_failure(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from erev_api.db.tables import release_validation_attempt, release_validation_group
    from erev_api.domain.contracts.validation_attempts import freeze

    k01(world)
    validation_id = pending_validation(world)
    with (
        pytest.raises(RuntimeError, match="selection insert interrupted"),
        world.place.uow() as uow,
    ):
        execute = uow.session.execute

        def fail_selection(statement: Any, *args: Any, **kwargs: Any) -> Any:
            if getattr(statement, "table", None) is release_validation_group:
                raise RuntimeError("selection insert interrupted")
            return execute(statement, *args, **kwargs)

        monkeypatch.setattr(uow.session, "execute", fail_selection)
        freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912)
        uow.commit()
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(release_validation_attempt)) == 0
        assert uow.session.scalar(select(func.count()).select_from(release_validation_group)) == 0
        assert freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912).created
        uow.commit()


@pytest.mark.parametrize(
    "case",
    ["different seed", "active predecessor", "skipped number", "partial scope", "other tenant"],
)
def test_validation_attempt_freeze_refuses_invalid_redraw(world: World, case: str) -> None:
    from erev_api.domain.contracts.validation_attempts import freeze

    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912)
        uow.commit()
    principal = world.place.principal
    if case == "partial scope":
        principal = replace(principal, entity_scope=(world.entity_id,))
    elif case == "other tenant":
        principal = replace(principal, tenant_id=UUID(int=999))
    number = 2 if case == "active predecessor" else 3 if case == "skipped number" else 1
    with world.place.uow(principal) as uow, pytest.raises(Problem):
        freeze(
            uow,
            validation_id=validation_id,
            attempt_no=number,
            seed=99 if case == "different seed" else 20260912,
        )


def test_validation_attempt_freeze_serializes_duplicate_creators(world: World) -> None:
    import threading

    from erev_api.db.tables import release_validation_attempt
    from erev_api.domain.contracts.validation_attempts import FrozenAttempt, freeze
    from support.interleave import await_lock_wait, backend_pid, observing_checkouts

    validation_id = pending_validation(world)
    results: list[FrozenAttempt] = []
    errors: list[Exception] = []

    def duplicate() -> None:
        try:
            with world.place.uow() as uow:
                results.append(
                    freeze(uow, validation_id=validation_id, attempt_no=1, seed=20260912)
                )
                uow.commit()
        except Exception as error:
            errors.append(error)

    request = threading.Thread(target=duplicate, name="freeze-duplicate")
    try:
        with observing_checkouts() as backends, world.place.uow() as holder:
            first = freeze(holder, validation_id=validation_id, attempt_no=1, seed=20260912)
            holder_pid = backend_pid(holder.session)
            request.start()
            blocked_pid, _ = await_lock_wait(
                holder.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=15,
                expect="release_validation",
            )
            assert blocked_pid != holder_pid and request.is_alive()
            holder.commit()
    finally:
        if request.ident is not None:
            request.join(timeout=30)
    assert not request.is_alive() and not errors
    assert results == [FrozenAttempt(first.id, False)]
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(release_validation_attempt)) == 1


def test_validation_attempt_resolves_seed_once_and_keeps_it_on_retry(world: World) -> None:
    from erev_api.db.tables import release_validation_attempt, release_validation_group
    from erev_api.db.transitions import apply
    from erev_api.domain.contracts.validation_attempts import freeze
    from erev_api.enums import RegistryCategory
    from support.rows import publish_registry_version

    k01(world)
    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        first = freeze(uow, validation_id=validation_id, attempt_no=1)
        row = uow.session.execute(select(release_validation_attempt)).mappings().one()
        assert row["seed"] == 20260912
        original_rank = uow.session.scalar(select(release_validation_group.c.rank_sha256))
        uow.commit()
    with world.place.uow() as uow:
        publish_registry_version(
            uow.session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.PLATFORM,
            values={"platform.replay_seed": 123},
            at=uow.now,
        )
        uow.commit()
    with world.place.uow() as uow:
        assert freeze(uow, validation_id=validation_id, attempt_no=1).id == first.id
        assert not uow.audit_events
        apply(
            uow.session,
            "release_validation_attempt",
            first.id,
            to_status="SUPERSEDED",
            expected_status="SELECTED",
            expected_row_version=1,
            set_values={"row_version": 2},
        )
        uow.commit()
    with world.place.uow() as uow:
        second = freeze(uow, validation_id=validation_id, attempt_no=2)
        assert second.created and second.id != first.id
        rows = (
            uow.session.execute(
                select(release_validation_attempt).order_by(release_validation_attempt.c.attempt_no)
            )
            .mappings()
            .all()
        )
        assert [row["seed"] for row in rows] == [20260912, 123]
        rank = uow.session.scalar(
            select(release_validation_group.c.rank_sha256).where(
                release_validation_group.c.release_validation_attempt_id == second.id
            )
        )
        assert rank != original_rank
        uow.commit()


def test_validation_attempt_start_is_atomic_and_idempotent(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from erev_api.db.tables import release_validation, release_validation_attempt
    from erev_api.domain.contracts import validation_attempts

    k01(world)
    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        attempt = validation_attempts.freeze(uow, validation_id=validation_id, attempt_no=1)
        uow.commit()
    from erev_api.db.transitions import apply as apply_transition

    def fail_attempt(session: Any, table: str, *args: Any, **kwargs: Any) -> Any:
        if table == "release_validation_attempt":
            raise RuntimeError("attempt transition interrupted")
        return apply_transition(session, table, *args, **kwargs)

    monkeypatch.setattr(validation_attempts, "apply", fail_attempt)
    with pytest.raises(RuntimeError, match="interrupted"), world.place.uow() as uow:
        validation_attempts.start(uow, validation_id=validation_id, attempt_id=attempt.id)
        uow.commit()
    monkeypatch.setattr(validation_attempts, "apply", apply_transition)
    with world.place.uow() as uow:
        assert uow.session.scalar(select(release_validation.c.status)) == "PENDING"
        assert uow.session.scalar(select(release_validation_attempt.c.status)) == "SELECTED"
        assert validation_attempts.start(uow, validation_id=validation_id, attempt_id=attempt.id)
        assert [event["action"] for event in uow.audit_events] == [
            "release_validation_attempt.start"
        ]
        uow.commit()
    with world.place.uow() as uow:
        assert not validation_attempts.start(
            uow, validation_id=validation_id, attempt_id=attempt.id
        )
        assert not uow.audit_events
        assert uow.session.scalar(select(release_validation.c.status)) == "RUNNING"
        assert uow.session.scalar(select(release_validation_attempt.c.status)) == "RUNNING"
        assert uow.session.scalar(select(release_validation.c.row_version)) == 2
        assert uow.session.scalar(select(release_validation_attempt.c.row_version)) == 2
        uow.commit()


@pytest.mark.parametrize("change", ["head", "event", "group", "running event"])
def test_validation_attempt_start_refuses_population_drift(world: World, change: str) -> None:
    from erev_api.domain.contracts.validation_attempts import freeze, start
    from support.rows import insert_contract_rows

    booked = k01(world)
    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        attempt = freeze(uow, validation_id=validation_id, attempt_no=1)
        if change == "running event":
            assert start(uow, validation_id=validation_id, attempt_id=attempt.id)
        uow.commit()
    if change == "head":
        computed(world.place, booked.combination_group["id"])
    elif change in {"event", "running event"}:
        flag_change(world, booked.contract["id"], 2)
    else:
        with world.place.uow() as uow:
            insert_contract_rows(uow.session, world.place.tenant_id)
            uow.commit()
    with world.place.uow() as uow, pytest.raises(Problem, match="population changed"):
        start(uow, validation_id=validation_id, attempt_id=attempt.id)


def test_validation_attempt_start_refuses_legacy_unfingerprinted_attempt(world: World) -> None:
    from erev_api.db.tables import release_validation_attempt
    from erev_api.domain.contracts.validation_attempts import start

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    with world.place.uow() as uow:
        parent_id = uow.session.scalar(
            select(release_validation_attempt.c.release_validation_id).where(
                release_validation_attempt.c.id == attempt_id
            )
        )
        assert parent_id is not None
        with pytest.raises(Problem, match="population changed"):
            start(uow, validation_id=parent_id, attempt_id=attempt_id)
        assert not uow.audit_events


@pytest.mark.parametrize("state", ["SELECTED", "RUNNING", "COMPLETE", "INCOMPLETE"])
def test_validation_attempt_supersede_and_replace_atomically(world: World, state: str) -> None:
    from erev_api.db.tables import release_validation_attempt, release_validation_group
    from erev_api.db.transitions import apply
    from erev_api.domain.contracts.validation_attempts import freeze, start, supersede

    booked = k01(world)
    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        first = freeze(uow, validation_id=validation_id, attempt_no=1)
        if state != "SELECTED":
            start(uow, validation_id=validation_id, attempt_id=first.id)
        if state in {"COMPLETE", "INCOMPLETE"}:
            apply(
                uow.session,
                "release_validation_attempt",
                first.id,
                to_status=state,
                expected_status="RUNNING",
                set_values={},
            )
        frozen = dict(uow.session.execute(select(release_validation_attempt)).mappings().one())
        groups = [
            dict(row) for row in uow.session.execute(select(release_validation_group)).mappings()
        ]
        uow.commit()
    flag_change(world, booked.contract["id"], 2)
    with pytest.raises(RuntimeError, match="replacement interrupted"), world.place.uow() as uow:
        assert supersede(uow, validation_id=validation_id, attempt_id=first.id)
        freeze(uow, validation_id=validation_id, attempt_no=2)
        raise RuntimeError("replacement interrupted")
    with world.place.uow() as uow:
        assert uow.session.scalar(select(release_validation_attempt.c.status)) == state
        assert supersede(uow, validation_id=validation_id, attempt_id=first.id)
        second = freeze(uow, validation_id=validation_id, attempt_no=2)
        assert start(uow, validation_id=validation_id, attempt_id=second.id)
        assert not supersede(uow, validation_id=validation_id, attempt_id=first.id)
        assert [event["action"] for event in uow.audit_events].count(
            "release_validation_attempt.supersede"
        ) == 1
        old = (
            uow.session.execute(
                select(release_validation_attempt).where(
                    release_validation_attempt.c.id == first.id
                )
            )
            .mappings()
            .one()
        )
        assert old["status"] == "SUPERSEDED"
        for key in (
            "population",
            "seed",
            "required_entity_ids",
            "dataset_file_id",
            "report_run_id",
        ):
            assert old[key] == frozen[key]
        assert old["row_version"] == frozen["row_version"] + 1
        assert groups == [
            dict(row)
            for row in uow.session.execute(
                select(release_validation_group).where(
                    release_validation_group.c.release_validation_attempt_id == first.id
                )
            ).mappings()
        ]
        uow.commit()


def test_validation_attempt_supersede_rejects_late_result(world: World) -> None:
    from erev_api.db.tables import computation_verification, release_validation_attempt
    from erev_api.domain.contracts.validation_attempts import supersede
    from erev_api.domain.contracts.verification_store import persist

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    with world.place.uow() as uow:
        validation_id = uow.session.scalar(
            select(release_validation_attempt.c.release_validation_id)
        )
        assert validation_id is not None
        assert supersede(uow, validation_id=validation_id, attempt_id=attempt_id)
        uow.commit()
    with world.place.uow() as uow, pytest.raises(Problem, match="running frozen validation"):
        persist(uow, case.decision, context=case.context, duration_ms=10)
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 0


@pytest.mark.parametrize(
    "case", ["partial scope", "other tenant", "wrong parent", "pending approval", "linked approval"]
)
def test_validation_attempt_supersede_refuses_unsafe_context(world: World, case: str) -> None:
    from erev_api.db.tables import approval_request, release_validation_attempt
    from erev_api.db.transitions import apply
    from erev_api.domain.contracts.validation_attempts import freeze, start, supersede
    from support.rows import approval_request_values

    validation_id = pending_validation(world)
    with world.place.uow() as uow:
        attempt = freeze(uow, validation_id=validation_id, attempt_no=1)
        if case == "pending approval":
            start(uow, validation_id=validation_id, attempt_id=attempt.id)
            apply(
                uow.session,
                "release_validation",
                validation_id,
                to_status="PENDING_APPROVAL",
                expected_status="RUNNING",
                set_values={},
            )
        elif case == "linked approval":
            request = approval_request_values(world.place.tenant_id)
            uow.session.execute(insert(approval_request).values(**request))
            uow.session.execute(
                update(release_validation_attempt)
                .where(release_validation_attempt.c.id == attempt.id)
                .values(approval_request_id=request["id"])
            )
        uow.commit()
    principal = world.place.principal
    if case == "partial scope":
        principal = replace(principal, entity_scope=(world.entity_id,))
    elif case == "other tenant":
        principal = replace(principal, tenant_id=UUID(int=999))
    elif case == "wrong parent":
        validation_id = UUID(int=999)
    with world.place.uow(principal) as uow, pytest.raises(Problem):
        supersede(uow, validation_id=validation_id, attempt_id=attempt.id)
    with world.place.uow() as uow:
        assert uow.session.scalar(select(release_validation_attempt.c.status)) != "SUPERSEDED"


def test_replay_sources_loads_frozen_evidence_after_head_changes(world: World) -> None:
    from erev_api.domain.contracts.replay_sources import load
    from erev_api.domain.contracts.replay_verify import verify

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    flag_change(world, case.contract_id, 2)
    _, _, newer = computed(world.place, case.group_id)
    assert newer["id"] != case.decision.source_computation_id
    with world.place.uow() as uow:
        loaded = load(
            uow,
            context=case.context,
            attempt_id=attempt_id,
            group_id=case.group_id,
            trigger="REPLAY_VERIFY",
        )
        assert loaded.source is not None and loaded.evidence is not None
        assert loaded.source.computation_id == case.decision.source_computation_id
        assert loaded.token == case.decision.token
        row = verify(
            trigger="REPLAY_VERIFY",
            source=loaded.source,
            evidence=loaded.evidence,
            process=loaded.process,
            engine=engine(),
            token=loaded.token,
            attempt_id=attempt_id,
        )
        assert row == case.decision
        uow.commit()


@pytest.mark.parametrize(
    "case_name",
    [
        "partial scope",
        "superseded",
        "runtime mismatch",
        "missing file",
        "missing output",
        "corrupt input and missing output",
        "storage failure",
        "input metadata",
        "output metadata",
    ],
)
def test_replay_sources_refusals_before_execution(
    world: World, monkeypatch: pytest.MonkeyPatch, case_name: str
) -> None:
    from erev_api.db.tables import release_validation_attempt
    from erev_api.domain.contracts import replay_sources
    from erev_api.domain.contracts.replay_verify import verify
    from erev_api.domain.contracts.validation_attempts import supersede

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    principal = world.place.principal
    if case_name == "partial scope":
        principal = replace(principal, entity_scope=(world.entity_id,))
    if case_name == "superseded":
        with world.place.uow() as uow:
            validation_id = uow.session.scalar(
                select(release_validation_attempt.c.release_validation_id)
            )
            assert validation_id is not None
            supersede(uow, validation_id=validation_id, attempt_id=attempt_id)
            uow.commit()
    if case_name == "runtime mismatch":
        release = case.context.runtime.engine_release
        assert release is not None
        context = case.context
        case = replace(
            case,
            context=JobContext(
                job_id=context.job_id,
                tenant_id=context.tenant_id,
                kind=context.kind,
                principal=context.principal,
                runtime=replace(
                    context.runtime, engine_release=replace(release, engine_version="9.9.9")
                ),
            ),
        )
    opened: list[UUID] = []
    original = open_file

    def observe(*args: Any, **kwargs: Any) -> Any:
        opened.append(args[1])
        if case_name in {"partial scope", "superseded", "runtime mismatch"}:
            pytest.fail("a refused replay must not open a file")
        if case_name == "missing file" or (
            case_name in {"missing output", "corrupt input and missing output"} and len(opened) == 2
        ):
            raise FileNotFoundError("missing retained file")
        if case_name == "storage failure":
            raise PermissionError("storage unavailable")
        meta, stream = original(*args, **kwargs)
        if case_name == "corrupt input and missing output":
            with stream:
                content = stream.read()
            stream = io.BytesIO(content + b" ")
        if (case_name == "input metadata" and len(opened) == 1) or (
            case_name == "output metadata" and len(opened) == 2
        ):
            meta = {**meta, "media_type": "text/plain"}
        return meta, stream

    monkeypatch.setattr(replay_sources, "open_file", observe)
    with world.place.uow(principal) as uow:
        if case_name in {"partial scope", "superseded", "storage failure"}:
            with pytest.raises(PermissionError if case_name == "storage failure" else Problem):
                replay_sources.load(
                    uow,
                    context=case.context,
                    attempt_id=attempt_id,
                    group_id=case.group_id,
                    trigger="REPLAY_VERIFY",
                )
            return
        loaded = replay_sources.load(
            uow,
            context=case.context,
            attempt_id=attempt_id,
            group_id=case.group_id,
            trigger="REPLAY_VERIFY",
        )
        assert loaded.source is not None

        def never_execute(bundle: Any) -> Any:
            pytest.fail("invalid or missing evidence must not execute the engine")

        row = verify(
            trigger="REPLAY_VERIFY",
            source=loaded.source,
            evidence=loaded.evidence,
            process=loaded.process,
            engine=never_execute,
            token=loaded.token,
            attempt_id=attempt_id,
        )
        expected = {
            "runtime mismatch": "SOURCE_RUNTIME_UNAVAILABLE",
            "missing file": "INPUT_EVIDENCE_MISSING",
            "missing output": "OUTPUT_EVIDENCE_MISSING",
            "corrupt input and missing output": "INPUT_EVIDENCE_HASH_MISMATCH",
            "input metadata": "INPUT_EVIDENCE_HASH_MISMATCH",
            "output metadata": "OUTPUT_EVIDENCE_HASH_MISMATCH",
        }
        assert row.reason == expected[case_name] and not row.engine_executed
        if case_name == "runtime mismatch":
            assert not opened
        uow.commit()


@pytest.mark.parametrize("wrong", ["task", "tenant", "release"])
def test_replay_sources_rejects_foreign_execution_before_file_access(
    world: World, monkeypatch: pytest.MonkeyPatch, wrong: str
) -> None:
    from erev_api.domain.contracts import replay_sources
    from erev_api.jobs.context import JobLost

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    context = case.context
    runtime = context.runtime
    assert runtime.attempt is not None and runtime.engine_release is not None
    if wrong == "task":
        assert runtime.attempt.task_id is not None
        runtime = replace(
            runtime, attempt=replace(runtime.attempt, task_id=runtime.attempt.task_id + 10000)
        )
    elif wrong == "release":
        assert runtime.engine_release is not None
        runtime = replace(runtime, engine_release=replace(runtime.engine_release, id=UUID(int=999)))
    changed = JobContext(
        job_id=context.job_id,
        tenant_id=UUID(int=999) if wrong == "tenant" else context.tenant_id,
        kind=context.kind,
        principal=context.principal,
        runtime=runtime,
    )

    def forbidden_file(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("foreign execution opened retained evidence")

    monkeypatch.setattr(replay_sources, "open_file", forbidden_file)
    with world.place.uow() as uow, pytest.raises(JobLost if wrong == "task" else Problem):
        replay_sources.load(
            uow,
            context=changed,
            attempt_id=attempt_id,
            group_id=case.group_id,
            trigger="REPLAY_VERIFY",
        )


@pytest.mark.parametrize("trigger", ["REPLAY_VERIFY", "UPGRADE_VALIDATE"])
@pytest.mark.parametrize("outcome", ["MATCH", "ERROR", "NO_SOURCE"])
def test_replay_execution_commits_only_evidence_and_reuses_result(
    world: World, monkeypatch: pytest.MonkeyPatch, outcome: str, trigger: Trigger
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager

    from erev_api.db.tables import computation_verification, release_validation_group
    from erev_api.domain.contracts import replay_sources
    from erev_api.domain.contracts.replay_execution import execute_running
    from erev_api.uow import UnitOfWork

    case = verification_case(world, with_source=outcome != "NO_SOURCE")
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None
    original = case.context.unit_of_work
    active = 0
    calls = 0

    @contextmanager
    def tracked_unit() -> Iterator[UnitOfWork]:
        nonlocal active
        with original() as uow:
            active += 1
            try:
                yield uow
            finally:
                active -= 1

    monkeypatch.setattr(case.context, "unit_of_work", tracked_unit)

    def compute_once(bundle: Any) -> Any:
        nonlocal calls
        assert active == 0, "engine ran inside a database unit of work"
        calls += 1
        assert calls == 1 and outcome != "NO_SOURCE"
        if outcome == "ERROR":
            raise EngineError("ENGINE_INVARIANT_VIOLATED", "retry probe")
        return engine()(bundle)

    with world.place.uow() as uow:
        before = [
            uow.session.scalar(select(func.count()).select_from(table))
            for table in (contract_computation, contract_version, subledger_posting)
        ]
    result = execute_running(
        case.context,
        attempt_id=attempt_id,
        group_id=case.group_id,
        trigger=trigger,
        engine=compute_once,
    )
    assert result.outcome.value == outcome and result.accepted == (outcome != "ERROR")

    def no_file(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("committed result retry reopened evidence")

    monkeypatch.setattr(replay_sources, "open_file", no_file)
    repeated = execute_running(
        case.context,
        attempt_id=attempt_id,
        group_id=case.group_id,
        trigger=trigger,
        engine=compute_once,
    )
    assert repeated == result
    with pytest.raises(Problem, match="stored replay result"):
        execute_running(
            case.context,
            attempt_id=attempt_id,
            group_id=case.group_id,
            trigger="UPGRADE_VALIDATE" if trigger == "REPLAY_VERIFY" else "REPLAY_VERIFY",
            engine=compute_once,
        )
    assert calls == (0 if outcome == "NO_SOURCE" else 1)
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 1
        row = uow.session.execute(select(computation_verification)).mappings().one()
        assert row["engine_executed"] == (outcome != "NO_SOURCE")
        assert (
            row["actual_output_sha256"] is None
            if outcome != "MATCH"
            else row["actual_output_sha256"] is not None
        )
        assert uow.session.scalar(select(release_validation_group.c.orchestration_state)) == (
            "RUNNING" if outcome == "ERROR" else "COMPLETE"
        )
        assert before == [
            uow.session.scalar(select(func.count()).select_from(table))
            for table in (contract_computation, contract_version, subledger_posting)
        ]


def test_replay_execution_refuses_head_changed_during_engine(world: World) -> None:
    from erev_api.db.tables import computation_verification
    from erev_api.domain.contracts.replay_execution import execute_running

    case = verification_case(world)
    attempt_id = case.decision.release_validation_attempt_id
    assert attempt_id is not None

    def change_head(bundle: Any) -> Any:
        flag_change(world, case.contract_id, 2)
        computed(world.place, case.group_id)
        return engine()(bundle)

    with pytest.raises(Problem, match="head changed"):
        execute_running(
            case.context,
            attempt_id=attempt_id,
            group_id=case.group_id,
            trigger="REPLAY_VERIFY",
            engine=change_head,
        )
    with world.place.uow() as uow:
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 0


def test_replay_job_scheduler_completes_selected_group(world: World) -> None:
    from erev_api.db.tables import computation_verification, job, release_validation_group
    from erev_api.domain.contracts import replay_job  # registers the worker handler
    from erev_api.enums import JobKind
    from erev_api.jobs.registry import HANDLERS, run_job

    assert HANDLERS[JobKind.REPLAY_VERIFY].handler is replay_job.replay
    case = verification_case(world, queued_only=True)
    run_job(
        case.context.job_id,
        world.place.tenant_id,
        attempt=1,
        runtime=replace(case.context.runtime, attempt=None),
        delivered_task_id=case.context.task_id,
    )
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(select(job.c.state).where(job.c.id == case.context.job_id))
            == "SUCCEEDED"
        )
        assert (
            uow.session.scalar(select(release_validation_group.c.orchestration_state)) == "COMPLETE"
        )
        assert uow.session.scalar(select(computation_verification.c.outcome)) == "MATCH"


def test_replay_job_scheduler_retries_error_then_exhausts(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from erev_api.db.tables import computation_verification, job, release_validation_group
    from erev_api.domain.contracts import replay_job
    from erev_api.domain.contracts.replay_execution import execute_running
    from erev_api.jobs.registry import run_job
    from sqlalchemy import text

    case = verification_case(world, queued_only=True)

    def fail_engine(bundle: Any) -> Any:
        raise EngineError("ENGINE_INVARIANT_VIOLATED", "retry probe")

    def execute(context: JobContext, **kwargs: Any) -> Any:
        return execute_running(context, **kwargs, engine=fail_engine)

    monkeypatch.setattr(replay_job, "execute_running", execute)
    for attempt in (1, 2, 3):
        with world.place.uow() as uow:
            task_id = uow.session.scalar(
                select(job.c.procrastinate_job_id).where(job.c.id == case.context.job_id)
            )
            uow.session.execute(
                text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                {"id": task_id},
            )
            uow.commit()
        run_job(
            case.context.job_id,
            world.place.tenant_id,
            attempt=attempt,
            runtime=replace(case.context.runtime, attempt=None),
            delivered_task_id=task_id,
        )
        with world.place.uow() as uow:
            uow.session.execute(
                text("UPDATE procrastinate_jobs SET status = 'succeeded' WHERE id = :id"),
                {"id": task_id},
            )
            assert uow.session.scalar(
                select(job.c.state).where(job.c.id == case.context.job_id)
            ) == ("FAILED" if attempt == 3 else "QUEUED")
            assert uow.session.scalar(select(release_validation_group.c.orchestration_state)) == (
                "FAILED_EXHAUSTED" if attempt == 3 else "RETRYABLE"
            )
            assert (
                uow.session.scalar(select(release_validation_group.c.accepted_verification_id))
                is None
            )
            assert (
                uow.session.scalar(select(func.count()).select_from(computation_verification))
                == attempt
            )
            uow.commit()


@pytest.mark.parametrize("during_engine", [False, True])
def test_replay_job_cancellation_preserves_no_accepted_result(
    world: World, monkeypatch: pytest.MonkeyPatch, during_engine: bool
) -> None:
    from erev_api.db.tables import computation_verification, job, release_validation_group
    from erev_api.domain.contracts import replay_job
    from erev_api.domain.contracts.replay_execution import execute_running
    from erev_api.domain.platform.jobs import cancel_job
    from erev_api.jobs.registry import run_job

    case = verification_case(world, queued_only=True)

    def cancel() -> None:
        with world.place.uow() as uow:
            cancel_job(uow, case.context.job_id)
            uow.commit()

    def cancel_while_computing(bundle: Any) -> Any:
        cancel()
        return engine()(bundle)

    def execute(context: JobContext, **kwargs: Any) -> Any:
        return execute_running(context, **kwargs, engine=cancel_while_computing)

    if during_engine:
        monkeypatch.setattr(replay_job, "execute_running", execute)
        run_job(
            case.context.job_id,
            world.place.tenant_id,
            attempt=1,
            runtime=replace(case.context.runtime, attempt=None),
            delivered_task_id=case.context.task_id,
        )
    else:
        cancel()
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(select(job.c.state).where(job.c.id == case.context.job_id))
            == "CANCELLED"
        )
        assert (
            uow.session.scalar(select(release_validation_group.c.orchestration_state))
            == "CANCELLED"
        )
        assert (
            uow.session.scalar(select(release_validation_group.c.accepted_verification_id)) is None
        )
        assert uow.session.scalar(select(func.count()).select_from(computation_verification)) == 0


def test_replay_job_cancel_does_not_wait_on_worker_commit(world: World) -> None:
    from erev_api.db.tables import job
    from erev_api.domain.contracts import replay_job
    from erev_api.domain.platform.jobs import cancel_job

    assert replay_job.guard_cancel is not None
    case = verification_case(world)
    with case.context.unit_of_work() as worker:
        with world.place.uow() as caller, pytest.raises(Problem) as refused:
            cancel_job(caller, case.context.job_id)
        assert refused.value.slug == "lock-conflict"
        worker.commit()
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(
                select(job.c.cancel_requested_at).where(job.c.id == case.context.job_id)
            )
            is None
        )


def test_replay_job_refuses_cancel_after_acceptance(world: World) -> None:
    from erev_api.db.tables import job, release_validation_group
    from erev_api.domain.contracts import replay_job
    from erev_api.domain.platform.jobs import cancel_job

    case = verification_case(world)
    result = replay_job.replay(
        case.context,
        {
            "release_validation_attempt_id": str(case.decision.release_validation_attempt_id),
            "combination_group_id": str(case.group_id),
            "trigger": "REPLAY_VERIFY",
        },
    )
    assert result.result["outcome"] == "MATCH"
    with world.place.uow() as uow, pytest.raises(Problem) as refused:
        cancel_job(uow, case.context.job_id)
    assert refused.value.slug == "invalid-transition"
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(
                select(job.c.cancel_requested_at).where(job.c.id == case.context.job_id)
            )
            is None
        )
        assert (
            uow.session.scalar(select(release_validation_group.c.orchestration_state)) == "COMPLETE"
        )


def test_replay_job_failure_cleanup_rolls_back_while_worker_is_active(world: World) -> None:
    from erev_api.db.tables import job, release_validation_group
    from erev_api.domain.contracts import replay_job
    from erev_api.jobs.registry import fail_attempt

    assert replay_job.failed is not None
    case = verification_case(world)
    with case.context.unit_of_work() as worker:
        with pytest.raises(Problem) as refused:
            fail_attempt(
                case.context.job_id,
                world.place.tenant_id,
                attempt=3,
                error=RuntimeError("failure probe"),
                runtime=replace(case.context.runtime, attempt=None),
                task_id=case.context.task_id,
            )
        assert refused.value.slug == "lock-conflict"
        worker.commit()
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(select(job.c.state).where(job.c.id == case.context.job_id))
            == "RUNNING"
        )
        assert (
            uow.session.scalar(select(release_validation_group.c.orchestration_state)) == "RUNNING"
        )
