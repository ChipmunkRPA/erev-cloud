"""The lines of an entry that belongs to the group (item BILLING-GROUP-SUBJECT-1; the supervisor's
ruling of 2026-10-02; 04 T-SL-04 ``contract_id`` rev 1.303; dev-guide DG-CMD-10 rev 1.284;
ENGINE_SPEC_B Table 14-A and S14-R-13).

Every JET-10 part — the remeasurement of a foreign-currency balance and the difference at its
settlement — is ONE entry per combination group and entity, ``<group>@<entity>``. A ledger line
needs one contract, and in a group of several contracts the entry names none. Measured before the
item, with no race in it: ``BILLING_RECORDED`` on a member of a two-contract group of a
foreign-currency entity was answered 201 with a FAILED computation (``ValueError: subject
CG-CON-000003@AVM-UK names no member contract``, an ``ENGINE_INVARIANT_VIOLATION`` item, nothing
posted), and the group could not be computed again; the FX_REMEASUREMENT pass of a close run
builds its lines through the same function.

The rule: such an entry's lines are listed under the member contract FIRST BY EXTERNAL ID among
the members the entry's entity posts for. The line belongs to the group; the contract is where it
is listed. In every case here the listing member is NOT the member that holds the balance: its
external id sorts first, and it has delivered and billed nothing.

Two worlds: the FX world of ``test_fx_remeasurement_recompute.py`` (AVM-UK in GBP, USD
contracts) for a settlement in a computation, and ``close_run_worlds.eur_receivable`` (AVM-US in
USD, EUR contracts; an unbilled receivable of EUR 10,000.00) for the period-end pass.
"""

from __future__ import annotations

from decimal import Decimal
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
    exception_item,
    period,
    subledger_line,
)
from erev_api.domain.contracts import compute_job
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.db import TestDatabase
from support.factories import GATEWAY, Workspace, activated_contract, booked_contract
from support.principals import Actor
from support.reference import approve, post
from test_combination import GROUPS
from test_fx_remeasurement_recompute import ENTITY as AVM_UK
from test_fx_remeasurement_recompute import World as FxWorld
from test_fx_remeasurement_recompute import _invoice, _recorded, delivered
from test_fx_remeasurement_recompute import world as fx  # noqa: F401  (the FX world's fixture)

AVM_US = worlds.AVM_US
FX = "FX_REMEASUREMENT"
AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
DELIVERED_UK, FIRST_UK = "NS-SO-UK-7001", "NS-SO-UK-7000"
DELIVERED_EU, FIRST_EU, LAST_EU = close_run_worlds.EUR_CONTRACT, "SF-ORD-EU-3000", "SF-ORD-EU-3002"

Line = tuple[str, str, str, Decimal, Decimal]  # (contract, period, role, transaction, functional)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


# --- the worlds' second and third contracts, and their group --------------------------------------


def _grouped(app: FastAPI, author: Actor, approver: Actor, contract_ids: list[UUID]) -> UUID:
    """The contracts combined into one group by the approved command (606-10-25-9(b))."""
    proposed = post(
        app,
        GROUPS,
        author,
        {
            "contract_ids": [str(contract_id) for contract_id in contract_ids],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: the orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = UUID(proposed.json()["id"])
    submitted = post(app, f"{GROUPS}/{group_id}/submit", author, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], approver)
    assert approved.status_code == 200, approved.text
    return group_id


def _gateways(world: FxWorld, external_id: str) -> UUID:
    """A second USD contract of AVM-UK — 200 gateway units for USD 90,000.00 from 1 July 2026,
    at list like ``NS-SO-UK-7001`` — booked and activated; nothing delivered, nothing billed."""
    body = {
        "external_id": external_id,
        "customer_id": str(world.customer_id),
        "contracting_entity_code": AVM_UK,
        "transaction_currency": "USD",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": GATEWAY,
                "quantity": "200",
                "total_price": {"amount": "90000.00", "currency": "USD"},
            }
        ],
    }
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    return UUID(str(booked.contract["id"]))


def _hours(world: worlds.ReportWorld, external_id: str) -> UUID:
    """Another EUR contract of AVM-US like ``SF-ORD-EU-3001`` — 100 hours at EUR 100.00 from
    1 August 2026 — booked and activated; no hour delivered."""
    first = world.contracts[DELIVERED_EU].contract
    booked = booked_contract(
        world.place,
        {
            "external_id": external_id,
            "customer_id": str(first["customer_id"]),
            "contracting_entity_code": AVM_US,
            "transaction_currency": "EUR",
            "inception_date": "2026-08-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": close_run_worlds.EUR_HOURS,
                    "quantity": "100",
                    "total_price": {"amount": "0.00", "currency": "EUR"},
                    "unit_price": "100.00",
                    "start_date": "2026-08-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
        activate=True,
    )
    return UUID(str(booked.contract["id"]))


# --- what the ledger holds ------------------------------------------------------------------------


def _fx_lines(place: Workspace, contract_ids: list[UUID]) -> list[Line]:
    """The ``FX_REMEASUREMENT`` lines listed under the contracts: (the contract's external id,
    posting period, account role, transaction amount, functional amount), debit positive."""
    rows = place.rows(
        select(
            contract.c.external_id,
            period.c.period_key,
            subledger_line.c.account_role,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
        )
        .select_from(
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            ).join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
        )
        .where(subledger_line.c.contract_id.in_(contract_ids), subledger_line.c.entry_kind == FX)
    )
    return sorted(
        (
            str(row["external_id"]),
            str(row["period_key"]),
            str(row["account_role"]),
            Decimal(row["amount_txn"]),
            Decimal(row["amount_functional"]),
        )
        for row in rows
    )


def _line_count(place: Workspace, contract_ids: list[UUID]) -> int:
    return int(
        place.scalar(
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.contract_id.in_(contract_ids))
        )
    )


def _fx_dimensions(place: Workspace, contract_ids: list[UUID]) -> list[dict[str, Any]]:
    rows = place.rows(
        select(subledger_line.c.dimensions, subledger_line.c.obligation_id).where(
            subledger_line.c.contract_id.in_(contract_ids), subledger_line.c.entry_kind == FX
        )
    )
    return [{**dict(row["dimensions"]), "obligation_id": row["obligation_id"]} for row in rows]


def _group_state(place: Workspace, group_id: UUID) -> dict[str, Any]:
    (group,) = place.rows(
        select(combination_group.c.code, combination_group.c.dirty_since).where(
            combination_group.c.id == group_id
        )
    )
    statuses = place.rows(
        select(contract_computation.c.status).where(
            contract_computation.c.combination_group_id == group_id
        )
    )
    return {
        "code": str(group["code"]),
        "dirty": group["dirty_since"] is not None,
        "computations": sorted(
            str(getattr(row["status"], "value", row["status"])) for row in statuses
        ),
        "items": sorted(
            str(row["code"])
            for row in place.rows(
                select(exception_item.c.code).where(
                    exception_item.c.combination_group_id == group_id
                )
            )
        ),
    }


# --- (a) a settlement in a computation ------------------------------------------------------------


def test_a_settlement_in_a_group_of_two_contracts_is_posted_under_the_first_member(
    fx: FxWorld,  # noqa: F811
) -> None:
    """``NS-SO-UK-7001`` (120 units delivered in July: USD 54,000.00, GBP 43,740.00) and
    ``NS-SO-UK-7000`` (nothing delivered) are one combination group. The invoice of USD
    54,000.00 of 20 August settles the contract asset: at the spot rate 0.84 it is GBP 45,360.00
    against the July closing carrying of 44,280.00, a difference of GBP 1,080.00 (JET-10a) —
    an entry of the group, ``<group>@AVM-UK``.

    The command computes, and the two lines of that entry are listed under ``NS-SO-UK-7000``,
    the member first by external id, with the group as their ``contract`` dimension and no
    ``contract_key``; none is listed under the contract that was invoiced. A second computation
    reads them back for the group and posts nothing."""
    delivered_id, _ = delivered(fx)
    first_id = _gateways(fx, FIRST_UK)
    members = [delivered_id, first_id]
    group_id = _grouped(fx.app, fx.maya, fx.marcus, members)
    assert _fx_lines(fx.place, members) == []
    head = int(
        fx.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == delivered_id))
    )

    _recorded(fx, delivered_id, head, _invoice("INV-UK-7001", "2026-08-20", "54000.00"))

    assert _fx_lines(fx.place, members) == [
        (FIRST_UK, AUGUST, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("1080.0000")),
        (FIRST_UK, AUGUST, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-1080.0000")),
    ]
    state = _group_state(fx.place, group_id)
    # the one item is the diagnostic of an event dated before a later one (the invoice of 20
    # August, after the combination's events of September): no finding about the computation
    assert (state["dirty"], state["items"]) == (False, ["LATE_EVENT"]), state
    assert "FAILED" not in state["computations"] and "QUARANTINED" not in state["computations"]
    for dimensions in _fx_dimensions(fx.place, members):
        assert dimensions["contract"] == state["code"]
        assert "contract_key" not in dimensions and dimensions["obligation_id"] is None

    posted = _line_count(fx.place, members)
    with fx.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id)
        uow.commit()
    assert str(getattr(again.status, "value", again.status)) == "SUCCEEDED"
    assert _line_count(fx.place, members) == posted


# --- (b) the period-end pass, and the member that leaves ------------------------------------------


def _three_in_one_group(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[worlds.ReportWorld, dict[str, UUID], UUID]:
    """``eur_receivable`` with two more EUR contracts of AVM-US, the three in one combination
    group: ``SF-ORD-EU-3000`` (first by external id, nothing delivered), ``SF-ORD-EU-3001`` (the
    world's: EUR 10,000.00 delivered on 31 August, not invoiced) and ``SF-ORD-EU-3002``."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    ids = {
        DELIVERED_EU: UUID(str(world.contracts[DELIVERED_EU].contract["id"])),
        FIRST_EU: _hours(world, FIRST_EU),
        LAST_EU: _hours(world, LAST_EU),
    }
    group_id = _grouped(app, world.maya, world.marcus, [ids[key] for key in sorted(ids)])
    return world, ids, group_id


def test_the_fx_pass_of_a_close_run_posts_for_a_group_of_several_contracts(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The period-end share. The group's unbilled receivable of EUR 10,000.00 stands at USD
    11,000.00; August's run remeasures it at the closing rate 1.105000 — 11,050.00, a gain of
    50.00 — as ``test_close_run_steps.py`` has it for the contract alone. In a group of three
    the run succeeds all the same, and the entry's two lines are listed under
    ``SF-ORD-EU-3000``. A second run of August posts nothing."""
    world, ids, _ = _three_in_one_group(app, keyring, clock, files)
    members = list(ids.values())

    august = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)

    assert (august["status"], august["current_step_code"]) == ("SUCCEEDED", None), august
    assert runs.step(august, FX)["status"] == "SUCCEEDED"
    assert _fx_lines(world.place, members) == [
        (FIRST_EU, AUGUST, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("50.0000")),
        (FIRST_EU, AUGUST, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-50.0000")),
    ]
    again = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert again["status"] == "SUCCEEDED"
    assert runs.posted(world.tenant_id, again["id"]) == []


def test_when_the_listing_member_leaves_later_lines_are_listed_under_the_next(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regrouping (04 T-SL-04 ``contract_id``), as measured. August's run lists the group's
    50.00 under ``SF-ORD-EU-3000``. That contract then leaves the group by the approved command.
    The lines already posted stay under it — the ledger is immutable — and leave the group with
    it: posted amounts are read back by the members' lines.

    So the group that remains has an August remeasurement nobody posted, and September's run is
    refused at its FX step until August's run is repeated (ruling R-112). August's second run
    posts the 50.00 again, listed under ``SF-ORD-EU-3001`` — then first of the two that remain —
    and takes it back under the member that left, whose own group has no balance: nil in sum.
    September's run then posts its 150.00 under ``SF-ORD-EU-3001``."""
    world, ids, group_id = _three_in_one_group(app, keyring, clock, files)
    members = list(ids.values())
    august = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED", august
    listed = [
        (FIRST_EU, AUGUST, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("50.0000")),
        (FIRST_EU, AUGUST, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-50.0000")),
    ]
    assert _fx_lines(world.place, members) == listed

    requested = post(
        app,
        f"{GROUPS}/{group_id}/submit",
        world.maya,
        {
            "leave_contract_ids": [str(ids[FIRST_EU])],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-EU-3000 was combined with the wrong orders.",
        },
    )
    assert requested.status_code == 200, requested.text
    approved = approve(app, requested.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    assert _fx_lines(world.place, members) == listed  # the leave itself posts no remeasurement

    refused = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    step = runs.step(refused, FX)
    assert (refused["status"], step["status"]) == ("FAILED", "FAILED"), refused
    assert step["problem"]["detail"] == (
        "Aug 2026 has period-end amounts no close run has posted; run its close first."
    )
    assert _fx_lines(world.place, members) == listed

    again = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert again["status"] == "SUCCEEDED", again
    reposted = sorted(
        [
            *listed,
            (FIRST_EU, AUGUST, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("-50.0000")),
            (FIRST_EU, AUGUST, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("50.0000")),
            (DELIVERED_EU, AUGUST, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("50.0000")),
            (DELIVERED_EU, AUGUST, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-50.0000")),
        ]
    )
    assert _fx_lines(world.place, members) == reposted

    september = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert september["status"] == "SUCCEEDED", september
    assert _fx_lines(world.place, members) == sorted(
        [
            *reposted,
            (DELIVERED_EU, SEPTEMBER, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("150.0000")),
            (DELIVERED_EU, SEPTEMBER, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-150.0000")),
        ]
    )
