"""API-R-36 Subledger (04 §15.3 API-R-36, §16 API-S-SubledgerLine, API-C-09 to API-C-11; T-SL-01,
T-SL-02; BUILD_SPEC CTR-3).

The world is ``support.factories.k11_world`` (PRD §2.6 for K-11): K-11 is booked, activated as the
SYSTEM principal, delivers 120 O1 units effective 2026-09-12 and is computed through
``support.factories.engine()`` (the ENGINE_SPEC §0.5 fake until END-9 lands, the real engine in the
L3 merge gate; V-C). Maya (Revenue Accountant) reads with ``contract.read``.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import obligation, period
from erev_api.domain.contracts.commands import BookedContract
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import K11World, computed, delivered_k11, k11_world
from support.reference import fields, get, slug

LINES = "/api/v1/subledger-lines"
POSTINGS = "/api/v1/subledger-postings"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    return k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _computed_k11(world: K11World) -> tuple[BookedContract, Mapping[str, Any]]:
    booked = delivered_k11(world)
    _, _, stored = computed(world.place, booked.combination_group["id"])
    return booked, stored


def test_subledger_lines_filters(world: K11World) -> None:
    booked, stored = _computed_k11(world)
    contract_id = booked.contract["id"]
    listed = get(
        world.app,
        LINES,
        world.place.author,
        {"contract": str(contract_id), "account_role": "REVENUE", "book": "ASC606"},
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["next_cursor"] is None
    o1 = world.place.scalar(select(obligation.c.id).where(obligation.c.obligation_key == "O1"))
    items = body["items"]
    assert items and all(
        (candidate["account_role"], candidate["origin_period_key"]) == ("REVENUE", None)
        for candidate in items
    )
    (item,) = [candidate for candidate in items if candidate["obligation_id"] == str(o1)]
    assert (
        item["posting_id"],
        item["posting_kind"],
        item["book"],
        item["period_key"],
        item["is_post_reopen"],
        item["effective_date"],
        item["entry_kind"],
        item["account_role"],
        item["dr_cr"],
        item["amount_txn"],
        item["amount_functional"],
        item["fx_rate"],
        item["contract_id"],
        item["obligation_id"],
        item["contract_version_id"],
        item["schedule_line_id"],
        item["journal_run_id"],
        item["reason_code"],
    ) == (
        stored["subledger_posting_ids"]["ASC606"],
        "ENGINE_COMPUTE",
        "ASC606",
        "FY2026-P09",
        False,
        "2026-09-12",
        "REVENUE_RECOGNITION",
        "REVENUE",
        "C",
        {"amount": "-53504.59", "currency": "EUR"},
        {"amount": "-53504.59", "currency": "EUR"},
        None,
        str(contract_id),
        str(o1),
        stored["contract_version_ids"]["ASC606"],
        None,
        None,
        None,
    )
    assert (item["entity"]["code"], item["entity"]["id"]) == ("AVM-DE", str(world.entity_id))
    assert (item["account"]["code"], item["account"]["name"]) == ("4000", "Revenue - products")
    assert item["recorded_at"] == "2026-09-12T12:00:00Z"
    assert item["links"] == {
        "explain": f"/api/v1/explain/subledger_line/{item['id']}/amount",
        "event": None,
        "schedule_line": None,
        "source_row": None,
    }


def test_subledger_line_filters_pages_refusals_and_posting(world: K11World) -> None:
    booked, stored = _computed_k11(world)
    maya = world.place.author
    contract = str(booked.contract["id"])

    def amounts(params: Mapping[str, Any]) -> list[tuple[str, str, str | None]]:
        response = get(world.app, LINES, maya, params)
        assert response.status_code == 200, response.text
        return sorted(
            (item["account_role"], item["amount_txn"]["amount"], item["obligation_id"])
            for item in response.json()["items"]
        )

    o1 = str(world.place.scalar(select(obligation.c.id).where(obligation.c.obligation_key == "O1")))
    everything = amounts({"contract": contract})
    assert {
        ("CONTRACT_LIABILITY", "53504.59", o1),
        ("REVENUE", "-53504.59", o1),
    } <= set(everything)
    assert amounts({"entity": "AVM-DE", "period": "FY2026-P09"}) == everything
    assert amounts({"entity": str(world.entity_id)}) == everything
    assert amounts({"entity": "AVM-US"}) == []
    assert amounts({"period": "FY2026-P08"}) == []
    assert amounts({"origin_period": "FY2026-P09"}) == []
    assert amounts({"book": "IFRS15"}) == []
    assert amounts({"contract": str(uuid4())}) == []
    assert amounts({"known_at": "2026-09-12T12:00:00Z"}) == everything
    assert amounts({"known_at": "2026-09-12T11:59:59Z"}) == []

    counted = get(world.app, LINES, maya, {"contract": contract, "count": "true"})
    assert counted.headers["X-Erev-Total-Count"] == str(len(everything))
    paged: list[str] = []
    cursor: str | None = None
    while True:
        params = {"contract": contract, "limit": "1", "sort": "recorded_at"}
        if cursor is not None:
            params["cursor"] = cursor
        page = get(world.app, LINES, maya, params)
        assert page.status_code == 200, page.text
        paged += [item["id"] for item in page.json()["items"]]
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
    assert len(paged) == len(set(paged)) == len(everything)

    for params in (
        {"account_role": "RETAINED"},
        {"book": "GAAP"},
        {"contract": "not-a-uuid"},
        {"known_at": "yesterday"},
    ):
        refused = get(world.app, LINES, maya, params)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    naive = get(world.app, LINES, maya, {"known_at": "2026-09-12T12:00:00"})
    assert (naive.status_code, fields(naive)) == (422, [("known_at", "API-C-09")]), naive.text
    unsorted = get(world.app, LINES, maya, {"sort": "amount"})
    assert (unsorted.status_code, fields(unsorted)) == (422, [("sort", "API-C-09")]), unsorted.text

    posting_id = stored["subledger_posting_ids"]["ASC606"]
    shown = get(world.app, f"{POSTINGS}/{posting_id}", maya)
    assert shown.status_code == 200, shown.text
    posting = shown.json()
    assert (
        posting["id"],
        posting["book"],
        posting["posting_kind"],
        posting["idempotency_key"],
        posting["contract_computation_id"],
        posting["combination_group_id"],
        posting["reverses_posting_id"],
    ) == (
        posting_id,
        "ASC606",
        "ENGINE_COMPUTE",
        f"compute:{stored['id']}",
        str(stored["id"]),
        str(booked.combination_group["id"]),
        None,
    )
    september = world.place.scalar(select(period.c.id).where(period.c.period_key == "FY2026-P09"))
    seal = posting["seal"]
    assert (seal["chain_seq"], seal["line_count"], seal["prev_seal_sha256"]) == (
        1,
        len(everything),
        None,
    )
    assert len(seal["seal_sha256"]) == 64
    debits = sum(
        (Decimal(amount) for _, amount, _ in everything if Decimal(amount) > 0), Decimal(0)
    )
    assert seal["control_totals"] == [
        {
            "entity_id": str(world.entity_id),
            "period_id": str(UUID(str(september))),
            "currency": "EUR",
            "debit_txn": format(debits.quantize(Decimal("0.0001")), "f"),
            "credit_txn": format(debits.quantize(Decimal("0.0001")), "f"),
            "debit_functional": format(debits.quantize(Decimal("0.0001")), "f"),
            "credit_functional": format(debits.quantize(Decimal("0.0001")), "f"),
        }
    ]
    missing = get(world.app, f"{POSTINGS}/{uuid4()}", maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text
