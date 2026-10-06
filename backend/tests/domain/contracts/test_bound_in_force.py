"""A delivery is checked against the quantity in force (04 §16.3 "The quantity a delivery is
checked against", rev 1.232; dev-guide DG-KRN-EVT-02 rev 1.223; item EVT-BOUND-AFTER-MOD-1;
control CTL-008; 03 REQ-REC-024 "unless a modification is processed first"; BUILD_SPEC CTR-5).

The bound of the events channel read the quantities of the booking and nothing after it.
Measured through the product before the rule, on WLD-K-11 ``NS-SO-DE-5004`` (O1: 200 gateways,
120 delivered): after an applied amendment of +50 a delivery of 100 was refused "requested 100,
remaining 80" — units 201 to 250 could be delivered through this route by nobody; after an
applied amendment of -60 a delivery of 40 was taken and approved, 160 delivered of 140 in force,
the computation ``SUCCEEDED`` with revenue equal to the whole allocation; 15 units were taken on
an obligation an amendment had added with 10. Shown by this module on the code before the rule:
an obligation a regroup had moved had no bound on the contract it had joined (961 of its 960
seat-months were stored), and a delivery was still taken on an obligation an amendment had
removed.

Each test applies the change through its own commands and then records as Maya; what is taken is
approved by Priya, so the append reads the same quantities as the route.

DB-bound. Worlds: ``k11`` as in ``test_manual_events`` with the EUR to USD spot rate a EUR
modification routes at (ROUTING-FX-1); the two drafts of ``test_regroup``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
import test_modifications as mods
import test_regroup as regroups
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    contract_computation,
    contract_event,
    event_submission,
)
from erev_api.enums import ContractEventType
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    K11World,
    Workspace,
    computed,
    delivered_k11,
    k02_world,
    k11_world,
)
from support.http import HttpResponse
from support.reference import approve, assign, fields, post, slug
from support.worlds import approved_manual_events, submitted_manual_events

CONTRACTS = "/api/v1/contracts"
K11 = "NS-SO-DE-5004"
OVER = "{contract}, obligation {key} ({product}): requested {requested}, remaining {remaining}."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _spot(world: K11World, clock: FrozenClock) -> None:
    """EUR to USD spot 1.11 approved: a EUR modification routes at it (ROUTING-FX-1)."""
    maya = world.place.author
    rate_set = post(
        world.app,
        "/api/v1/fx-rate-sets",
        maya,
        {"code": "TREASURY-SPOT", "name": "Treasury spot rates", "rate_type": "spot"},
    )
    assert rate_set.status_code == 201, rate_set.text
    draft = post(
        world.app,
        f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
        maya,
        {
            "coverage_from": "2026-09-01",
            "coverage_to": "2026-12-31",
            "rates": [
                {
                    "base_currency": "EUR",
                    "quote_currency": "USD",
                    "rate": "1.11",
                    "effective_date": "2026-09-15",
                }
            ],
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        world.app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        maya,
        {"comment": "Treasury statement"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    clock.advance(timedelta(minutes=1))
    approved = approve(world.app, submitted.json()["pending_approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # modification.approve, event.approve
    _spot(world, clock)
    return world


def _delivered_contract(world: K11World) -> UUID:
    """K-11 active and computed with 120 of the 200 O1 units delivered."""
    booked = delivered_k11(world)
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return UUID(str(booked.contract["id"]))


def _amended(
    world: K11World,
    runtime: JobRuntime,
    clock: FrozenClock,
    contract_id: UUID,
    body: dict[str, Any],
) -> dict[str, Any]:
    """One modification through its commands to ``APPLIED``: its ``CONTRACT_AMENDED``."""
    created = mods._create(world, contract_id, body)  # type: ignore[arg-type]
    mods._classify(world, created["id"])  # type: ignore[arg-type]
    mods._preview(world, created["id"], runtime)  # type: ignore[arg-type]
    request_id = mods._submit(world, created["id"])  # type: ignore[arg-type]
    clock.advance(timedelta(minutes=1))
    decided = approve(world.app, request_id, world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    row = mods._row(world, created["id"])  # type: ignore[arg-type]
    assert (str(row["status"]), str(row["treatment_summary"])) == ("APPLIED", "PROSPECTIVE"), row
    amended = mods._events(world, contract_id, ContractEventType.CONTRACT_AMENDED)  # type: ignore[arg-type]
    clock.advance(timedelta(minutes=1))
    return dict(amended[-1])


def _change(delta: str, amount: str, reference: str) -> dict[str, Any]:
    return {
        "effective_date": "2026-09-16",
        "kind": "QUANTITY_CHANGE",
        "reference": reference,
        "lines": [
            {
                "obligation_key": "O1",
                "action": "CHANGE",
                "quantity_delta": delta,
                "consideration_delta": {"amount": amount, "currency": "EUR"},
            }
        ],
        "rationale": "The gateway quantity of the order changes.",
    }


def _delivery(key: str, quantity: str) -> dict[str, Any]:
    return {
        "event_type": "DELIVERY_RECORDED",
        "effective_date": "2026-09-20",
        "payload": {"obligation_key": key, "quantity": quantity, "trigger": "DELIVERY"},
    }


def _head(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def _sent(place: Workspace, contract_id: UUID, item: dict[str, Any]) -> HttpResponse:
    return post(
        place.app,
        f"{CONTRACTS}/{contract_id}/events",
        place.author,
        {"events": [item], "evidence_file_ids": []},
        if_match=f'"s{_head(place, contract_id)}"',
    )


def _written(place: Workspace) -> tuple[int, ...]:
    """What a refused delivery leaves as it was: submissions, requests, events, computations."""
    return tuple(
        int(place.scalar(select(func.count()).select_from(table)))
        for table in (event_submission, approval_request, contract_event, contract_computation)
    )


def _refused(place: Workspace, contract_id: UUID, item: dict[str, Any], detail: str) -> None:
    before = _written(place)
    refused = _sent(place, contract_id, item)
    # the status first: without the rule the request is stored and answered 201
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("events.0.payload.quantity", "PROGRESS_OVER_DELIVERY")]
    body = refused.json()
    assert (body["detail"], body["errors"][0]["message"]) == (detail, detail)
    assert _written(place) == before


def _delivered(place: Workspace, contract_id: UUID, key: str) -> Decimal:
    rows = place.rows(
        select(contract_event.c.payload).where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == ContractEventType.DELIVERY_RECORDED.value,
        )
    )
    return sum(
        (
            Decimal(str(row["payload"]["quantity"]))
            for row in rows
            if row["payload"]["obligation_key"] == key
        ),
        Decimal(0),
    )


def test_evt_bound_after_mod_1_an_increased_quantity_is_delivered_in_full(
    k11: K11World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """An applied amendment of +50 puts 250 units in force, 130 of them undelivered. The 130 are
    taken; one more is refused. Before the rule the bound stood at the booked 200 and refused
    every delivery beyond it."""
    contract_id = _delivered_contract(k11)
    place = k11.place
    _amended(k11, runtime, clock, contract_id, _change("50", "22500.00", "CR-DE-5004-UP"))

    _refused(
        place,
        contract_id,
        _delivery("O1", "131"),
        OVER.format(contract=K11, key="O1", product="AVM-GW", requested="131", remaining="130"),
    )
    taken = approved_manual_events(
        place, k11.priya, contract_id, _delivery("O1", "130"), evidence_file_ids=[]
    )
    assert taken["computation"]["status"] == "SUCCEEDED"
    assert _delivered(place, contract_id, "O1") == Decimal(250)
    _refused(
        place,
        contract_id,
        _delivery("O1", "1"),
        OVER.format(contract=K11, key="O1", product="AVM-GW", requested="1", remaining="0"),
    )


def test_evt_bound_after_mod_1_a_reduced_quantity_binds_the_route_and_the_append(
    k11: K11World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """An applied amendment of -60 leaves 140 units in force, 20 of them undelivered. A delivery
    of 40 stored BEFORE the amendment is stale at its approval (04 T-CON-24 "Checked again where
    it is appended"); sent after it, it is refused by name; 20 are taken. Before the rule both
    were taken: 160 delivered of 140, remaining -20."""
    contract_id = _delivered_contract(k11)
    place = k11.place
    stored = submitted_manual_events(
        place, contract_id, _delivery("O1", "40"), evidence_file_ids=[]
    )
    _amended(k11, runtime, clock, contract_id, _change("-60", "-27000.00", "CR-DE-5004-DOWN"))
    head = _head(place, contract_id)

    stale = approve(k11.app, stored["approval_request_id"], k11.priya)

    # the status first: without the rule the approval appends and 160 of 140 are delivered
    assert stale.status_code == 409, stale.text
    assert slug(stale) == "stale-approval"
    request = place.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(stored["approval_request_id"])
        )
    )[0]
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert not place.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(stored["approval_request_id"])
        )
    )
    assert (_head(place, contract_id), _delivered(place, contract_id, "O1")) == (head, 120)
    _refused(
        place,
        contract_id,
        _delivery("O1", "40"),
        OVER.format(contract=K11, key="O1", product="AVM-GW", requested="40", remaining="20"),
    )
    taken = approved_manual_events(
        place, k11.priya, contract_id, _delivery("O1", "20"), evidence_file_ids=[]
    )
    assert taken["computation"]["status"] == "SUCCEEDED"
    assert _delivered(place, contract_id, "O1") == Decimal(140)


def test_evt_bound_after_mod_1_an_added_obligation_is_bound_by_its_quantity(
    k11: K11World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """An applied amendment adds O3 with 10 gateways (below their standalone price, so that the
    line is no separate contract). 15 are refused, 10 are taken. Before the rule an obligation
    the booking did not name had no bound at all."""
    contract_id = _delivered_contract(k11)
    place = k11.place
    body = {
        "effective_date": "2026-09-16",
        "kind": "ADD_OBLIGATION",
        "reference": "CR-DE-5004-ADD",
        "lines": [
            {
                "obligation_key": "O3",
                "action": "ADD",
                "product_code": "AVM-GW",
                "quantity_delta": "10",
                "consideration_delta": {"amount": "2500.00", "currency": "EUR"},
            }
        ],
        "rationale": "Ten more gateways as a new line, at a discount.",
    }
    _amended(k11, runtime, clock, contract_id, body)

    _refused(
        place,
        contract_id,
        _delivery("O3", "15"),
        OVER.format(contract=K11, key="O3", product="AVM-GW", requested="15", remaining="10"),
    )
    taken = approved_manual_events(
        place, k11.priya, contract_id, _delivery("O3", "10"), evidence_file_ids=[]
    )
    assert taken["computation"]["status"] == "SUCCEEDED"
    assert _delivered(place, contract_id, "O3") == Decimal(10)
    # the booked obligation beside it keeps its own bound (PRD J-04-ALT-1's sentence)
    _refused(
        place,
        contract_id,
        _delivery("O1", "90"),
        OVER.format(contract=K11, key="O1", product="AVM-GW", requested="90", remaining="80"),
    )


def test_evt_bound_after_mod_1_a_removed_obligation_takes_no_further_delivery(
    k11: K11World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """An applied amendment removes O1 — a ``REMOVE`` line that gives the price back and states
    no quantity (ENGINE_SPEC S06-R-21: the line removes the remaining quantity or term). The
    obligation takes no further delivery; the obligation beside it does. Before the rule the 80
    units of the booking were still taken."""
    contract_id = _delivered_contract(k11)
    place = k11.place
    body = {
        "effective_date": "2026-09-16",
        "kind": "REMOVE_OBLIGATION",
        "reference": "CR-DE-5004-REMOVE",
        "lines": [
            {
                "obligation_key": "O1",
                "action": "REMOVE",
                "consideration_delta": {"amount": "-36000.00", "currency": "EUR"},
            }
        ],
        "rationale": "The customer takes no further gateways.",
    }
    amended = _amended(k11, runtime, clock, contract_id, body)
    assert [line["quantity_delta"] for line in amended["payload"]["lines"]] == ["0"]

    _refused(
        place,
        contract_id,
        _delivery("O1", "1"),
        OVER.format(contract=K11, key="O1", product="AVM-GW", requested="1", remaining="0"),
    )
    stored = _sent(place, contract_id, _delivery("O2", "1"))
    assert stored.status_code == 201, stored.text


def test_evt_bound_after_mod_1_a_regrouped_obligation_is_bound_where_it_went(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A regroup of two drafts moves O2 (960 seat-months) from ``SF-ORD-10002`` to
    ``SF-ORD-10003``. On the contract it joined it is bound by its quantity; on the contract it
    left it takes no delivery. Before the rule it was the other way round: no bound where it
    went, and its booked quantity where it no longer was."""
    world = k02_world(app, keyring, clock, files)
    place = world.place
    source_id, source_group = regroups._draft(world, "SF-ORD-10002")
    target_id, target_group = regroups._draft(world, "SF-ORD-10003", lines="one")
    computed(place, source_group)
    computed(place, target_group)
    moved = post(
        app,
        f"{CONTRACTS}/{source_id}/regroup",
        place.author,
        {"obligation_keys": ["O2"], "target_contract_id": str(target_id), "comment": "Same order."},
    )
    assert moved.status_code == 201, moved.text
    clock.advance(timedelta(minutes=1))

    _refused(
        place,
        target_id,
        _delivery("O2", "961"),
        OVER.format(
            contract="SF-ORD-10003",
            key="O2",
            product="AVM-SEAT-MO",
            requested="961",
            remaining="960",
        ),
    )
    _refused(
        place,
        source_id,
        _delivery("O2", "1"),
        OVER.format(
            contract="SF-ORD-10002", key="O2", product="AVM-SEAT-MO", requested="1", remaining="0"
        ),
    )
    # the positive controls: the moved quantity where it went, and the obligation that stayed
    for contract_id, key, quantity in ((target_id, "O2", "960"), (source_id, "O1", "1440")):
        stored = _sent(place, contract_id, _delivery(key, quantity))
        assert stored.status_code == 201, stored.text
        assert set(stored.json()) == {"event_submission_id", "approval_request_id"}
