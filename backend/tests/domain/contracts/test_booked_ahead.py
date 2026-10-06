"""A contract booked ahead of the open periods is stored and computed (item
ENG-S10-FUTURE-INCEPTION-1; ENGINE_SPEC_B C-05, S10-R-22 and S12-R-13 rev 1.100; ENGINE_SPEC
CV-13; 05 RCP-15 "Period range"; supervisor ruling R-107 (a) of 2026-09-30).

The finding. ``POST /contracts`` with an inception date after the contracting entity's last open
period answered 201 and stored the contract, while its provisional computation crashed in stage
10 (``IndexError`` in ``_version_period``: no period from the group's inception lies inside the
horizon) and, with that reader guarded, in stage 12 (``covering_periods``: "end must not precede
start"). The draft form reaches it with any future start date.

The rule. Such a contract computes: a version that recognises and presents nothing yet, with its
allocation and schedule as for any other contract; the version-date ``netting_reclass_amount`` is
0 with a node of its own formula, which the explain route renders. The period set is per
contracting entity, so an entity that is behind does not stop another entity of the same group.

Worlds: PRD §2.6 seats (``support.factories.seat_world``): AVM-US (USD) with FY2026-P01 to P09
open; the frozen clock reads 2026-09-12T12:00:00Z. The second case adds AVM-CA on the same
calendar with FY2026-P01 to P06 open. Maya (Revenue Accountant) books through the route; Marcus
(Controller) approves the combination. The engine-level witnesses are
``tests/engine/s10_billing_balances/test_s10_no_measured_period.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    contract_version,
    contract_version_balance,
    exception_item,
    obligation_version,
    subledger_line,
)
from erev_api.domain.contracts.commands import BookedContract
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    Workspace,
    activated_contract,
    computed,
    open_periods,
    seat_body,
    seat_line,
    seat_world,
)
from support.reference import ENTITIES, approve, entity, get, post

CONTRACTS = "/api/v1/contracts"
GROUPS = "/api/v1/combination-groups"
EXPLAIN = "/api/v1/explain"
NETTING = "netting_reclass_amount"
NO_PERIOD = "pos.reclass_attribution.no_measured_period.v1"
ATTRIBUTED = "pos.reclass_attribution.pob_debit_positions.v1"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def _created(world: SeatWorld, body: dict[str, Any]) -> tuple[UUID, UUID]:
    """``POST /contracts``: 201; the contract id and the id of its group."""
    created = post(world.app, CONTRACTS, world.place.author, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    return contract_id, UUID(str(group_id))


def _activated(place: Workspace, contract_id: UUID, group_id: UUID) -> None:
    """The approved activation as the fixtures run it (BS3-D-19): it computes and fails closed."""
    booked = BookedContract(
        contract={"id": contract_id},
        combination_group={"id": group_id},
        member={},
        obligations=(),
        event={},
    )
    activated_contract(place, booked)


def _computations(place: Workspace, group_id: UUID) -> list[tuple[str, Any]]:
    rows = place.rows(
        select(contract_computation.c.status, contract_computation.c.problem)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    )
    return [(str(row["status"]), row["problem"]) for row in rows]


def _head_is_latest(place: Workspace, group_id: UUID) -> bool:
    """The group is clean: its head is its latest computation, which succeeded."""
    latest = place.rows(
        select(contract_computation.c.id, contract_computation.c.status)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )
    head = place.scalar(
        select(combination_group.c.head_computation_id).where(combination_group.c.id == group_id)
    )
    return [(row["id"], str(row["status"])) for row in latest] == [(head, "SUCCEEDED")]


def _versions(place: Workspace, group_id: UUID) -> list[tuple[str, int, str]]:
    rows = place.rows(
        select(
            contract_version.c.book_code,
            contract_version.c.version_no,
            contract_version.c.status_in_book,
        )
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no)
    )
    return [(str(r["book_code"]), int(r["version_no"]), str(r["status_in_book"])) for r in rows]


def _latest_obligation(place: Workspace, contract_id: UUID) -> dict[str, Any]:
    (row,) = place.rows(
        select(
            obligation_version.c.id,
            obligation_version.c.netting_reclass_amount,
            obligation_version.c.netting_reclass_role,
            obligation_version.c.trace_nodes,
        )
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(obligation_version.c.version_no.desc())
        .limit(1)
    )
    return row


def _count(place: Workspace, table: Any, contract_id: UUID) -> int:
    return int(
        place.scalar(
            select(func.count()).select_from(table).where(table.c.contract_id == contract_id)
        )
    )


def _exceptions(place: Workspace) -> list[tuple[str, str]]:
    rows = place.rows(select(exception_item.c.code, exception_item.c.severity))
    return sorted((str(row["code"]), str(row["severity"])) for row in rows)


def test_a_contract_booked_ahead_of_the_open_periods_is_stored_and_computed(
    seats: SeatWorld,
) -> None:
    """Ten seats for 24,000.00 USD from 1 November 2026, booked on 12 September with AVM-US open
    to September. The route answers 201 and the provisional computation succeeds: one version,
    the group's head, no exception item, nothing presented and nothing posted; the obligation's
    ``netting_reclass_amount`` is 0 with a node the explain route renders. The activation computes
    as well and still posts nothing. Once October and November are open the same contract posts
    its November revenue — nothing was lost by booking ahead."""
    app, place, maya = seats.app, seats.place, seats.place.author
    line = seat_line("O1", seats="10", price="24000.00", start="2026-11-01", end="2027-10-31")
    body = seat_body(
        seats.customers["C-09"], external_id="SF-ORD-30111", inception="2026-11-01", lines=[line]
    )
    contract_id, group_id = _created(seats, body)
    assert _computations(place, group_id) == [("SUCCEEDED", None)]
    assert _head_is_latest(place, group_id)
    assert _versions(place, group_id) == [("ASC606", 1, "DRAFT")]
    assert _exceptions(place) == []
    assert _count(place, contract_version_balance, contract_id) == 0
    assert _count(place, subledger_line, contract_id) == 0
    obligation = _latest_obligation(place, contract_id)
    assert (obligation[NETTING], obligation["netting_reclass_role"]) == (0, None)
    explained = get(app, f"{EXPLAIN}/obligation_version/{obligation['id']}/{NETTING}", maya)
    assert explained.status_code == 200, explained.text
    assert explained.json()["root_node_id"] == obligation["trace_nodes"][NETTING]
    assert [node["formula_id"] for node in explained.json()["nodes"]] == [NO_PERIOD]
    assert explained.json()["narrative"] == [
        "Period-end reclass at the version date 01 Nov 2026: no accounting period from the "
        "contract's inception on is open for its contracting entity yet, so none is evaluated "
        "and nothing is attributed to this obligation = USD 0.00."
    ]

    _activated(place, contract_id, group_id)
    assert _computations(place, group_id) == [("SUCCEEDED", None), ("SUCCEEDED", None)]
    assert _head_is_latest(place, group_id)
    assert _versions(place, group_id)[-1] == ("ASC606", 2, "ACTIVE")
    assert _exceptions(place) == []
    assert _count(place, contract_version_balance, contract_id) == 0
    assert _count(place, subledger_line, contract_id) == 0

    open_periods(app, maya, entity_code="AVM-US", keys=["FY2026-P10", "FY2026-P11"])
    _, output, _ = computed(place, group_id)
    (book,) = output.books
    assert sorted({row.period_key for row in book.balances}) == ["FY2026-P11"]
    (november,) = [item for item in book.schedules if item.period_key == "FY2026-P11"]
    posted = [
        (intent.posting_period_key, line.account_role, line.side, line.amount_txn)
        for intent in book.posting_intents
        for line in intent.lines
        if line.account_role == "REVENUE"
    ]
    assert posted == [("FY2026-P11", "REVENUE", "C", november.amount)]
    assert november.amount == 197260  # 24,000.00 × 30 ÷ 365
    assert _count(place, subledger_line, contract_id) > 0
    assert _exceptions(place) == []


def test_an_entity_behind_does_not_stop_the_other_entity_of_a_combined_group(
    seats: SeatWorld,
) -> None:
    """Two seat orders of one customer from 1 August 2026: SF-ORD-30121 in AVM-US (open to
    September) and SF-ORD-30122 in AVM-CA, whose last open period is June. The second is booked
    ahead of its entity's periods: stored, computed, activated, nothing posted. Combined by the
    approved command the group has two contracting entities; its computation succeeds, AVM-US is
    presented and posted for August and September, and AVM-CA is neither."""
    app, place, maya = seats.app, seats.place, seats.place.author
    shown = get(app, f"{ENTITIES}/{seats.entity_id}", maya)
    assert shown.status_code == 200, shown.text
    entity(app, maya, code="AVM-CA", calendar_id=str(shown.json()["calendar_id"]))
    open_periods(app, maya, entity_code="AVM-CA", keys=[f"FY2026-P{n:02d}" for n in range(1, 7)])

    def order(external_id: str, entity_code: str, seat_count: str, price: str) -> dict[str, Any]:
        line = seat_line("O1", seats=seat_count, price=price, start="2026-08-01", end="2027-07-31")
        body = seat_body(
            seats.customers["C-09"], external_id=external_id, inception="2026-08-01", lines=[line]
        )
        return {**body, "contracting_entity_code": entity_code}

    first, first_group = _created(seats, order("SF-ORD-30121", "AVM-US", "30", "72000.00"))
    _activated(place, first, first_group)
    assert _count(place, subledger_line, first) > 0
    second, second_group = _created(seats, order("SF-ORD-30122", "AVM-CA", "10", "24000.00"))
    assert _computations(place, second_group) == [("SUCCEEDED", None)]
    _activated(place, second, second_group)
    assert _computations(place, second_group) == [("SUCCEEDED", None), ("SUCCEEDED", None)]
    assert _head_is_latest(place, second_group)
    assert _count(place, subledger_line, second) == 0
    assert _count(place, contract_version_balance, second) == 0

    proposed = post(
        app,
        GROUPS,
        maya,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(app, f"{GROUPS}/{group_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.json()["approval_request_id"], seats.marcus)
    assert decided.status_code == 200, decided.text
    status = place.scalar(
        select(combination_group.c.status).where(combination_group.c.id == group_id)
    )
    assert str(status) == "APPLIED"
    assert _computations(place, group_id) == [("SUCCEEDED", None)]
    assert _head_is_latest(place, group_id)
    assert _count(place, contract_version_balance, first) > 0
    assert _count(place, contract_version_balance, second) == 0
    assert _count(place, subledger_line, second) == 0

    _, output, _ = computed(place, group_id)
    (book,) = output.books
    assert book.posting_intents == ()
    assert {row.subject_key for row in book.balances} == {"SF-ORD-30121@AVM-US"}
    assert sorted({row.period_key for row in book.balances}) == ["FY2026-P08", "FY2026-P09"]
    formulas = {node.id: node.formula_id for node in book.trace.nodes}
    by_contract = {
        str(version.columns["obligation_key"]) + "@" + version.subject_key.split("/")[0]: version
        for version in book.obligation_versions
    }
    behind = by_contract["O1@SF-ORD-30122"]
    assert (behind.columns[NETTING], behind.columns["netting_reclass_role"]) == (0, None)
    assert formulas[behind.trace_nodes[NETTING]] == NO_PERIOD
    assert formulas[by_contract["O1@SF-ORD-30121"].trace_nodes[NETTING]] == ATTRIBUTED
    # The one item is the S02-R-14 suggestion the second booking raised: nothing of a computation.
    assert _exceptions(place) == [("COMBINATION_SUGGESTED", "WARNING")]
