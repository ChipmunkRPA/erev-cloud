"""A combination group whose contracting entities keep different functional currencies is stored
(item CTR-BALANCE-ROWS-1; supervisor ruling R-114 (g); 04 T-CON-09 rev 1.174).

The engine names the functional balance of every measure for an entity at rate 1 and only the
remeasured ones for an entity whose books are in another currency, so the T-CON-09 rows of one
version may differ in columns. As built the rows went in one INSERT, which takes its columns from
the first: the computation of such a group was stored FAILED under an approval that had answered
200. ``tests/unit/test_computation_rows.py`` holds both row orders without a database.

World: K-04 (``support.worlds.k04_saltmarsh``) — AVM-UK with GBP books, AVM-US with USD books,
the PRD §2.5 GBP to USD rates — and two more contracts of its customer, in GBP.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    contract,
    contract_computation,
    contract_version,
    contract_version_balance,
    exception_item,
    legal_entity,
)
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import Workspace, appended, booked_contract, computed
from support.reference import approve, get, post
from support.worlds import (
    AVM_UK,
    AVM_US,
    IMPLEMENTATION_UK,
    K04,
    PLATFORM_UK,
    K04World,
    k04_saltmarsh,
)

CONTRACTS: Final = "/api/v1/contracts"
GROUPS: Final = "/api/v1/combination-groups"
BRITISH: Final = "SF-ORD-UK-2004"
AMERICAN: Final = "SF-ORD-US-3001"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def k04(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K04World:
    return k04_saltmarsh(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _combined(k04: K04World) -> tuple[UUID, UUID, UUID]:
    """``SF-ORD-UK-2004`` — contracted and performed by AVM-UK — and ``SF-ORD-US-3001`` —
    contracted and performed by AVM-US, invoiced 5,000.00 GBP on 1 April — for the customer of
    K-04, each active and computed, then combined through the routes: proposed and submitted by
    Maya, approved by Marcus. (The AVM-UK contract, the AVM-US contract, the group.)"""
    place, app = k04.report.place, k04.app
    customer = str(k04.report.contracts[K04].contract["customer_id"])
    base = {"customer_id": customer, "transaction_currency": "GBP", "inception_date": "2026-04-01"}
    british = booked_contract(
        place,
        {
            **base,
            "external_id": BRITISH,
            "contracting_entity_code": AVM_UK,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM_UK,
                    "quantity": "1",
                    "total_price": {"amount": "60000.00", "currency": "GBP"},
                    "start_date": "2026-04-01",
                    "end_date": "2027-03-31",
                },
                {
                    "obligation_key": "O2",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": "8000.00", "currency": "GBP"},
                },
            ],
        },
        activate=True,
    )
    american = booked_contract(
        place,
        {
            **base,
            "external_id": AMERICAN,
            "contracting_entity_code": AVM_US,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": "5000.00", "currency": "GBP"},
                }
            ],
        },
        activate=True,
    )
    ids = [UUID(str(booked.contract["id"])) for booked in (british, american)]
    invoice = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 4, 1),
        payload=BillingRecordedV1(
            invoice_number="INV-US-3001",
            line_external_id="INV-US-3001-1",
            amount=MoneyIn(amount="5000.00", currency="GBP"),
            issue_date=date(2026, 4, 1),
        ),
    )
    appended(place, ids[1], 2, [invoice])
    for booked in (british, american):
        computed(place, UUID(str(booked.combination_group["id"])))
    proposed = post(
        app,
        GROUPS,
        k04.report.maya,
        {
            "contract_ids": [str(value) for value in ids],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(str(proposed.json()["id"]))
    submitted = post(app, f"{GROUPS}/{group_id}/submit", k04.report.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], k04.report.marcus)
    assert approved.status_code == 200, approved.text
    groups = place.rows(select(contract.c.combination_group_id).where(contract.c.id.in_(ids)))
    assert {row["combination_group_id"] for row in groups} == {group_id}
    return ids[0], ids[1], group_id


def _balances(place: Workspace, contract_id: UUID) -> list[dict[str, Any]]:
    """The T-CON-09 rows of a contract in the ASC606 book, with the entity's code and the group
    of the version each belongs to."""
    return place.rows(
        select(
            contract_version_balance,
            legal_entity.c.code.label("entity_code"),
            contract_version.c.combination_group_id.label("group_id"),
        )
        .join(
            contract_version,
            contract_version.c.id == contract_version_balance.c.contract_version_id,
        )
        .join(legal_entity, legal_entity.c.id == contract_version_balance.c.entity_id)
        .where(
            contract_version_balance.c.contract_id == contract_id,
            contract_version_balance.c.book_code == "ASC606",
        )
    )


def test_a_group_whose_contracting_entities_keep_different_books_is_stored(k04: K04World) -> None:
    """The approval of the combination computes the group: SUCCEEDED, nothing raised. Both
    T-CON-09 rows of the version are stored, each with what the engine gave it: the AVM-US member
    keeps the contract liability its own computation stored before the combination — 5,000.00 GBP
    and its USD amount — and at rate 1 every functional figure of the AVM-UK member is its
    transaction figure. Both members' balance reads answer."""
    place, app, maya = k04.report.place, k04.app, k04.report.maya
    british, american, group_id = _combined(k04)
    computations = place.rows(
        select(contract_computation.c.status).where(
            contract_computation.c.combination_group_id == group_id
        )
    )
    assert [str(row["status"]) for row in computations] == ["SUCCEEDED"]
    raised = place.rows(
        select(exception_item.c.code).where(exception_item.c.combination_group_id == group_id)
    )
    assert raised == []

    (uk_row,) = [row for row in _balances(place, british) if row["group_id"] == group_id]
    (alone,) = [row for row in _balances(place, american) if row["group_id"] != group_id]
    (us_row,) = [row for row in _balances(place, american) if row["group_id"] == group_id]
    assert [
        (str(row["entity_code"]), str(row["txn_currency"]), str(row["functional_currency"]))
        for row in (uk_row, us_row)
    ] == [(AVM_UK, "GBP", "GBP"), (AVM_US, "GBP", "USD")]
    money = [name for name in us_row if name.endswith(("_txn", "_functional"))]
    functional = [name for name in money if name.endswith("_functional")]
    assert len(functional) == 9  # every measure of T-CON-09 that keeps a functional column
    # AVM-US: remeasured, and what its own computation stored before the combination
    liability = (us_row["contract_liability_txn"], us_row["contract_liability_functional"])
    assert liability[0] == Decimal("5000.00") and liability[1] not in (0, liability[0])
    assert {name: us_row[name] for name in money} == {name: alone[name] for name in money}
    # AVM-UK: at rate 1 the functional figure of a measure is its transaction figure
    assert uk_row["contract_asset_txn"] > 0
    for name in functional:
        assert uk_row[name] == uk_row[name.removesuffix("_functional") + "_txn"], name

    for contract_id, row, code in ((british, uk_row, AVM_UK), (american, us_row, AVM_US)):
        listed = get(app, f"{CONTRACTS}/{contract_id}/balances", maya)
        assert listed.status_code == 200, listed.text
        (shown,) = listed.json()["items"]
        assert shown["entity"]["code"] == code
        assert shown["functional"]["contract_liability"] == {
            "amount": f"{row['contract_liability_functional']:.2f}",
            "currency": str(row["functional_currency"]),
        }
