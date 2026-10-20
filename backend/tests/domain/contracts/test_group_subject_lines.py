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
    from erev_api.db.tables import legal_entity
    from erev_api.domain.close import pass_evidence
    from erev_api.jobs.context import JobRuntime

    with fx.place.uow() as uow:
        line_id = uow.session.execute(
            select(subledger_line.c.id).where(
                subledger_line.c.contract_id.in_(members),
                subledger_line.c.entry_kind == FX,
                subledger_line.c.account_role == "CONTRACT_LIABILITY",
            )
        ).scalar_one()
        attributed = pass_evidence.liability_attribution(
            uow, line_id, owners={FIRST_UK: first_id, DELIVERED_UK: delivered_id}
        )
        assert attributed is not None
        assert attributed.amount == Decimal("1080.00")
        assert {item.contract_id for item in attributed.movements} == {delivered_id}
    reporting = worlds.ReportWorld(
        place=fx.place,
        priya=fx.priya,
        marcus=fx.marcus,
        runtime=JobRuntime(clock=fx.place.clock, keyring=fx.place.keyring, files=fx.place.files),
        entity_id=fx.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_UK)),
        contracts={},
    )
    run, rows = worlds.report_run(
        reporting,
        "contract_balance_rollforward",
        {
            "entity_codes": [AVM_UK],
            "book": "ASC606",
            "currency_view": "functional",
            "from_period_key": AUGUST,
            "to_period_key": AUGUST,
        },
    )
    fx_row = next(row for row in rows if row["row_key"] == "FX_REMEASUREMENT")
    assert sum(
        Decimal(fx_row[key]["amount"])
        for key in ("contract_liability", "contract_asset", "unbilled_receivable")
    ) == Decimal("1080.00")
    assert (
        next(item for item in run["tie_out_results"] if item["code"] == "TO_ROLLFORWARD_BALANCES")[
            "result"
        ]
        == "PASS"
    )


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
    from erev_api.domain.close import pass_evidence

    with world.place.uow() as uow:
        lines = (
            uow.session.execute(
                select(subledger_line).where(
                    subledger_line.c.contract_id.in_(members),
                    subledger_line.c.entry_kind == FX,
                    subledger_line.c.account_role == "CONTRACT_LIABILITY",
                )
            )
            .mappings()
            .all()
        )
        reversing = next(line for line in lines if line["amount_functional"] < 0)
        attributed = pass_evidence.liability_attribution(uow, reversing["id"], owners=ids)
        assert attributed is not None
        assert attributed.amount == Decimal("-50.00")
        assert len(attributed.paid_line_ids) == 1
        # The listing member has left; the original calculation still owns its
        # asset remeasurement under the delivered member, not the ledger caption.
        assert {item.contract_id for item in attributed.movements} == {ids[DELIVERED_EU]}

    september = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert september["status"] == "SUCCEEDED", september
    assert _fx_lines(world.place, members) == sorted(
        [
            *reposted,
            (DELIVERED_EU, SEPTEMBER, "CONTRACT_LIABILITY", Decimal("0.0000"), Decimal("150.0000")),
            (DELIVERED_EU, SEPTEMBER, "FX_GAIN_LOSS", Decimal("0.0000"), Decimal("-150.0000")),
        ]
    )
    run, rows = worlds.report_run(
        world,
        "contract_balance_rollforward",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "currency_view": "functional",
            "from_period_key": AUGUST,
            "to_period_key": SEPTEMBER,
        },
    )
    fx_row = next(row for row in rows if row["row_key"] == "FX_REMEASUREMENT")
    # From a zero opening, revenue first builds the asset path; endpoint
    # presentation later reclassifies it to unbilled. FX stays in its path caption.
    assert sum(
        Decimal(fx_row[key]["amount"]) for key in ("contract_asset", "unbilled_receivable")
    ) == Decimal("200.00"), fx_row
    assert fx_row["contract_liability"] == {"amount": "0.00", "currency": "USD"}
    assert (
        next(item for item in run["tie_out_results"] if item["code"] == "TO_ROLLFORWARD_BALANCES")[
            "result"
        ]
        == "PASS"
    )


@pytest.mark.parametrize("invoice_day", ["2026-08-10", "2026-08-20"])
def test_combined_credit_memo_consumes_another_members_layer(fx: FxWorld, invoice_day: str) -> None:  # noqa: F811
    from erev_api.db.tables import legal_entity
    from erev_api.jobs.context import JobRuntime
    from test_fx_remeasurement_recompute import _advance_received

    owner_id, _ = _advance_received(fx)
    issuer_id = _gateways(fx, FIRST_UK)
    _grouped(fx.app, fx.maya, fx.marcus, [owner_id, issuer_id])
    head = fx.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == issuer_id))
    _recorded(fx, issuer_id, int(head), _invoice("OTHER-ADV", invoice_day, "90000.00"))
    head = fx.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == issuer_id))
    _recorded(
        fx,
        issuer_id,
        int(head),
        {
            "event_type": "CREDIT_MEMO_RECORDED",
            "effective_date": "2026-08-20",
            "payload": {
                "credit_memo_number": "GROUP-CM",
                "obligation_key": "O1",
                "amount": {"amount": "40000.00", "currency": "USD"},
                "issue_date": "2026-08-20",
            },
        },
    )
    reporting = worlds.ReportWorld(
        place=fx.place,
        priya=fx.priya,
        marcus=fx.marcus,
        runtime=JobRuntime(clock=fx.place.clock, keyring=fx.place.keyring, files=fx.place.files),
        entity_id=fx.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_UK)),
        contracts={},
    )
    run, rows = worlds.report_run(
        reporting,
        "contract_balance_rollforward",
        {
            "entity_codes": [AVM_UK],
            "book": "ASC606",
            "currency_view": "functional",
            "from_period_key": AUGUST,
            "to_period_key": AUGUST,
        },
    )
    assert (
        next(item for item in run["tie_out_results"] if item["code"] == "TO_ROLLFORWARD_BALANCES")[
            "result"
        ]
        == "PASS"
    ), (run, rows)
    detail = [row for row in rows if row.get("contract_external_id")]
    assert detail
    assert all(Decimal(row["other"]["amount"]) == 0 for row in detail), detail
    shown = {row["contract_external_id"]: row for row in detail}
    expected = (
        {FIRST_UK: ("40000.00", "1600.00"), DELIVERED_UK: ("72000.00", "-1600.00")}
        if invoice_day.endswith("10")
        else {FIRST_UK: ("41285.71", "-714.29"), DELIVERED_UK: ("74314.29", "714.29")}
    )
    for name, (closing, transfer) in expected.items():
        assert shown[name]["closing"]["amount"] == closing
        assert shown[name]["reclassifications"]["amount"] == transfer
    from support.reference import get

    started = post(fx.app, f"/api/v1/report-runs/{run['id']}/rerun", fx.maya, {})
    assert started.status_code == 202, started.text
    completed = worlds.run_now(reporting, UUID(started.json()["id"]))
    assert completed["state"] == "SUCCEEDED", completed
    repeated = get(
        fx.app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", fx.maya
    )
    assert repeated.status_code == 200 and repeated.json()["items"] == rows, repeated.text
    if invoice_day.endswith("20"):
        translated, presented = worlds.report_run(
            reporting,
            "contract_balance_rollforward",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": "reporting",
                "from_period_key": AUGUST,
                "to_period_key": AUGUST,
            },
        )
        assert (
            next(
                check
                for check in translated["tie_out_results"]
                if check["code"] == "TO_ROLLFORWARD_BALANCES"
            )["result"]
            == "PASS"
        ), translated
        assert all(
            Decimal(row["other"]["amount"]) == 0
            for row in presented
            if row.get("contract_external_id")
        ), presented


def test_combined_historical_rates_reallocate_without_a_memo(fx: FxWorld) -> None:  # noqa: F811
    from erev_api.db.tables import legal_entity
    from erev_api.jobs.context import JobRuntime
    from support.reference import get
    from test_fx_remeasurement_recompute import _advance_received

    owner_id, _ = _advance_received(fx)
    second_id = _gateways(fx, FIRST_UK)
    _grouped(fx.app, fx.maya, fx.marcus, [owner_id, second_id])
    head = fx.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == second_id))
    _recorded(fx, second_id, int(head), _invoice("SECOND-RATE", "2026-08-20", "90000.00"))
    reporting = worlds.ReportWorld(
        place=fx.place,
        priya=fx.priya,
        marcus=fx.marcus,
        runtime=JobRuntime(clock=fx.place.clock, keyring=fx.place.keyring, files=fx.place.files),
        entity_id=fx.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_UK)),
        contracts={},
    )
    assert _fx_lines(fx.place, [owner_id, second_id]) == []
    for view in ("functional", "reporting"):
        run, rows = worlds.report_run(
            reporting,
            "contract_balance_rollforward",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": AUGUST,
                "to_period_key": SEPTEMBER,
            },
        )
        assert (
            next(
                check
                for check in run["tie_out_results"]
                if check["code"] == "TO_ROLLFORWARD_BALANCES"
            )["result"]
            == "PASS"
        ), run
        detail = {
            row["contract_external_id"]: row for row in rows if row.get("contract_external_id")
        }
        assert set(detail) == {DELIVERED_UK, FIRST_UK}
        assert all(Decimal(row["other"]["amount"]) == 0 for row in detail.values()), detail
        if view == "functional":
            for name, transfer in ((DELIVERED_UK, "1800.00"), (FIRST_UK, "-1800.00")):
                assert detail[name]["closing"] == {"amount": "73800.00", "currency": "GBP"}
                assert detail[name]["reclassifications"] == {"amount": transfer, "currency": "GBP"}
                assert detail[name]["fx_remeasurement"]["amount"] == "0.00"
        started = post(fx.app, f"/api/v1/report-runs/{run['id']}/rerun", fx.maya, {})
        assert started.status_code == 202, started.text
        finished = worlds.run_now(reporting, UUID(started.json()["id"]))
        assert finished["state"] == "SUCCEEDED", finished
        repeated = get(
            fx.app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == rows, repeated.text


def test_combined_revenue_relief_retains_the_consumed_members_owner(fx: FxWorld) -> None:  # noqa: F811
    from erev_api.db.tables import legal_entity
    from erev_api.jobs.context import JobRuntime
    from support.reference import get
    from support.worlds import approved_manual_events
    from test_fx_remeasurement_recompute import _advance_received

    source_id, _ = _advance_received(fx)
    recognizer_id = _gateways(fx, FIRST_UK)
    _grouped(fx.app, fx.maya, fx.marcus, [source_id, recognizer_id])
    head = fx.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == recognizer_id)
    )
    _recorded(fx, recognizer_id, int(head), _invoice("RECOGNIZER-ADV", "2026-08-20", "90000.00"))
    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-08-21",
            "payload": {"obligation_key": "O1", "quantity": "120", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    # The revenue adapter verifies the actual ledger line against both original
    # currencies and retains the original pre-computation paid population.
    from erev_api.domain.reports.command_fx_evidence import read_revenue

    with fx.place.uow() as uow:
        revenue_line = dict(
            uow.session.execute(
                select(subledger_line).where(
                    subledger_line.c.contract_id == recognizer_id,
                    subledger_line.c.entry_kind == "REVENUE_RECOGNITION",
                    subledger_line.c.account_role == "REVENUE",
                    subledger_line.c.amount_txn == Decimal("-54000"),
                )
            )
            .mappings()
            .one()
        )
        retained = read_revenue(uow, revenue_line)
        assert retained is not None and retained["source_kind"] == "CONTRACT_VERSION"
        assert Decimal(retained["selected_lines"][0]["amount_functional"]) == Decimal("-43200.00")
        changed = {**revenue_line, "amount_functional": Decimal("-43201")}
        with pytest.raises(ValueError, match="retained computation intent"):
            read_revenue(uow, changed)
    reporting = worlds.ReportWorld(
        place=fx.place,
        priya=fx.priya,
        marcus=fx.marcus,
        runtime=JobRuntime(clock=fx.place.clock, keyring=fx.place.keyring, files=fx.place.files),
        entity_id=fx.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_UK)),
        contracts={},
    )
    for first, view in (
        (AUGUST, "functional"),
        (AUGUST, "reporting"),
        ("FY2026-P07", "functional"),
    ):
        run, rows = worlds.report_run(
            reporting,
            "contract_balance_rollforward",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": first,
                "to_period_key": SEPTEMBER,
            },
        )
        assert (
            next(
                check
                for check in run["tie_out_results"]
                if check["code"] == "TO_ROLLFORWARD_BALANCES"
            )["result"]
            == "PASS"
        ), (run, rows)
        detail = {
            row["contract_external_id"]: row for row in rows if row.get("contract_external_id")
        }
        assert all(Decimal(row["other"]["amount"]) == 0 for row in detail.values()), detail
        if view == "functional":
            for name, closing, transfer in (
                (DELIVERED_UK, "74571.43", "2571.43"),
                (FIRST_UK, "29828.57", "-2571.43"),
            ):
                assert detail[name]["closing"]["amount"] == closing
                assert detail[name]["reclassifications"]["amount"] == transfer
            assert detail[FIRST_UK]["revenue_from_opening"]["amount"] == (
                "-43200.00" if first == AUGUST else "0.00"
            )
            assert detail[FIRST_UK]["revenue_from_period_billings"]["amount"] == (
                "0.00" if first == AUGUST else "-43200.00"
            )
        started = post(fx.app, f"/api/v1/report-runs/{run['id']}/rerun", fx.maya, {})
        assert started.status_code == 202, started.text
        finished = worlds.run_now(reporting, UUID(started.json()["id"]))
        assert finished["state"] == "SUCCEEDED", finished
        repeated = get(
            fx.app, f"/api/v1/report-runs/{started.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == rows, repeated.text
        disclosure_run, disclosure_rows = worlds.report_run(
            reporting,
            "revenue_from_opening_liability",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": first,
                "to_period_key": SEPTEMBER,
            },
        )
        summary = next(row for row in disclosure_rows if str(row["row_key"]).startswith("summary:"))
        expected_relief = -Decimal(detail[FIRST_UK]["revenue_from_opening"]["amount"])
        assert Decimal(summary["revenue_from_opening"]["amount"]) == expected_relief
        assert summary["currency"] == detail[FIRST_UK]["currency"]
        assert Decimal(summary["opening_contract_liability"]["amount"]) == sum(
            (Decimal(row["opening"]["amount"]) for row in detail.values()), Decimal(0)
        )
        income = next(row for row in disclosure_rows if row.get("contract_external_id") == FIRST_UK)
        assert income["opening_contract_liability"]["amount"] == "0.00"
        assert Decimal(income["revenue_from_opening"]["amount"]) == expected_relief
        expected_revenue = -sum(
            (
                Decimal(detail[FIRST_UK][name]["amount"])
                for name in ("revenue_from_opening", "revenue_from_period_billings")
            ),
            Decimal(0),
        )
        assert Decimal(income["revenue_recognized"]["amount"]) == expected_revenue
        assert Decimal(summary["revenue_recognized"]["amount"]) == expected_revenue
        restarted = post(fx.app, f"/api/v1/report-runs/{disclosure_run['id']}/rerun", fx.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = worlds.run_now(reporting, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        reloaded = get(
            fx.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert reloaded.status_code == 200 and reloaded.json()["items"] == disclosure_rows, (
            reloaded.text
        )
    for first, expected in ((AUGUST, "54000.00"), ("FY2026-P07", "0.00")):
        run, rows = worlds.report_run(
            reporting,
            "revenue_from_opening_liability",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": "transaction",
                "from_period_key": first,
                "to_period_key": SEPTEMBER,
            },
        )
        summary = next(row for row in rows if str(row["row_key"]).startswith("summary:"))
        recipient = next(row for row in rows if row.get("contract_external_id") == FIRST_UK)
        assert summary["revenue_from_opening"] == {"amount": expected, "currency": "USD"}
        assert recipient["revenue_from_opening"] == summary["revenue_from_opening"]
        assert recipient["opening_contract_liability"]["amount"] == "0.00"
        assert recipient["revenue_recognized"] == {"amount": "54000.00", "currency": "USD"}
        replay = post(fx.app, f"/api/v1/report-runs/{run['id']}/rerun", fx.maya, {})
        assert replay.status_code == 202, replay.text
        finished = worlds.run_now(reporting, UUID(replay.json()["id"]))
        assert finished["state"] == "SUCCEEDED", finished
        repeated = get(
            fx.app, f"/api/v1/report-runs/{replay.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == rows, repeated.text

    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-09-01",
            "payload": {"obligation_key": "O1", "quantity": "10", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    with fx.place.uow() as uow:
        later = dict(
            uow.session.execute(
                select(subledger_line)
                .where(
                    subledger_line.c.contract_id == recognizer_id,
                    subledger_line.c.account_role == "REVENUE",
                    subledger_line.c.id != revenue_line["id"],
                )
                .order_by(subledger_line.c.entry_no.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        retained = read_revenue(uow, later)
        assert retained is not None
        paid_ids = {row["id"] for row in retained["posted_lines"]}
        assert str(revenue_line["id"]) in paid_ids
        assert str(later["id"]) not in paid_ids
        assert all(row["account_role"] == "REVENUE" for row in retained["posted_lines"])

    from fractions import Fraction

    from erev_api.domain.reports.revenue_attribution import read as revenue_attribution

    with fx.place.uow() as uow:
        first_sources = revenue_attribution(uow, revenue_line["id"])
        assert first_sources.delta.amount == Fraction(revenue_line["amount_functional"])
        assert {part.contract_id for part in first_sources.delta.movements} == {source_id}
        next_sources = revenue_attribution(uow, later["id"])
        assert next_sources.delta.amount == Fraction(later["amount_functional"])
    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-09-02",
            "payload": {"obligation_key": "O1", "quantity": "10", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    with fx.place.uow() as uow:
        newest = dict(
            uow.session.execute(
                select(subledger_line)
                .where(
                    subledger_line.c.contract_id == recognizer_id,
                    subledger_line.c.account_role == "REVENUE",
                    subledger_line.c.id.not_in([revenue_line["id"], later["id"]]),
                )
                .order_by(subledger_line.c.entry_no.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        newest_sources = revenue_attribution(uow, newest["id"])
        assert newest_sources.delta.amount == Fraction(newest["amount_functional"])
        assert later["id"] in newest_sources.paid_line_ids

    final_run, final_rows = worlds.report_run(
        reporting,
        "revenue_from_opening_liability",
        {
            "entity_codes": [AVM_UK],
            "book": "ASC606",
            "currency_view": "functional",
            "from_period_key": AUGUST,
            "to_period_key": SEPTEMBER,
        },
    )
    from erev_api.db.tables import report_run

    binding = fx.place.scalar(
        select(report_run.c.source_binding).where(report_run.c.id == UUID(final_run["id"]))
    )
    retained_postings = binding["evidence"]["revenue_posted_sources_v1"]
    assert any(str(later["id"]) in item["paid_line_ids"] for item in retained_postings.values())
    income = next(row for row in final_rows if row.get("contract_external_id") == FIRST_UK)
    assert income["revenue_recognized"]["amount"] == "50400.00"
    restarted = post(fx.app, f"/api/v1/report-runs/{final_run['id']}/rerun", fx.maya, {})
    assert restarted.status_code == 202, restarted.text
    complete = worlds.run_now(reporting, UUID(restarted.json()["id"]))
    assert complete["state"] == "SUCCEEDED", complete
    repeated = get(
        fx.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data", fx.maya
    )
    assert repeated.status_code == 200 and repeated.json()["items"] == final_rows, repeated.text

    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "RETURN_RECORDED",
            "effective_date": "2026-09-03",
            "payload": {"obligation_key": "O1", "quantity": "10"},
        },
        evidence_file_ids=[],
    )
    with fx.place.uow() as uow:
        reversal = dict(
            uow.session.execute(
                select(subledger_line)
                .where(
                    subledger_line.c.contract_id == recognizer_id,
                    subledger_line.c.account_role == "REVENUE",
                    subledger_line.c.amount_txn > 0,
                )
                .order_by(subledger_line.c.entry_no.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        reversed_sources = revenue_attribution(uow, reversal["id"])
        assert reversed_sources.delta.amount == Fraction(reversal["amount_functional"])
        assert reversed_sources.delta.amount > 0
        assert {part.contract_id for part in reversed_sources.delta.movements} == {source_id}
        assert {later["id"], newest["id"]} <= set(reversed_sources.paid_line_ids)

    for view in ("transaction", "functional", "reporting"):
        returned_run, returned_rows = worlds.report_run(
            reporting,
            "revenue_from_opening_liability",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": AUGUST,
                "to_period_key": SEPTEMBER,
            },
        )
        returned_income = next(
            row for row in returned_rows if row.get("contract_external_id") == FIRST_UK
        )
        assert returned_income["revenue_recognized"] == returned_income["revenue_from_opening"]
        if view in {"transaction", "functional"}:
            assert returned_income["revenue_recognized"]["amount"] == (
                "58500.00" if view == "transaction" else "46800.00"
            )
        restarted = post(fx.app, f"/api/v1/report-runs/{returned_run['id']}/rerun", fx.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = worlds.run_now(reporting, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        repeated = get(
            fx.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == returned_rows, (
            repeated.text
        )


def test_combined_revenue_can_exhaust_another_members_advance_and_create_an_asset(
    fx: FxWorld,  # noqa: F811
) -> None:
    from erev_api.db.tables import legal_entity
    from erev_api.jobs.context import JobRuntime
    from support.reference import get
    from support.worlds import approved_manual_events

    source_id = _gateways(fx, DELIVERED_UK)
    recognizer_id = _gateways(fx, FIRST_UK)
    _recorded(fx, source_id, 2, _invoice("PARTIAL-ADV", "2026-07-01", "45000.00"))
    _grouped(fx.app, fx.maya, fx.marcus, [source_id, recognizer_id])
    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-08-21",
            "payload": {"obligation_key": "O1", "quantity": "120", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    from erev_api.db.tables import close_run
    from erev_api.domain.close import gates, period_end

    run_id, _ = runs.started(fx.app, fx.marcus, entity_code=AVM_UK, period_key=AUGUST)
    with fx.place.uow() as uow:
        run = (
            uow.session.execute(select(close_run).where(close_run.c.id == UUID(run_id)))
            .mappings()
            .one()
        )
        scope = gates.scope_of_period(uow.session, run["entity_id"], "ASC606", run["period_id"])
        assert scope is not None
        period_end.post_pass(
            uow,
            close_run_id=UUID(run_id),
            close_run_no=run["close_run_no"],
            scope=scope,
            pass_name=period_end.FX_REMEASUREMENT,
        )
        uow.commit()
    reporting = worlds.ReportWorld(
        place=fx.place,
        priya=fx.priya,
        marcus=fx.marcus,
        runtime=JobRuntime(clock=fx.place.clock, keyring=fx.place.keyring, files=fx.place.files),
        entity_id=fx.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == AVM_UK)),
        contracts={},
    )
    for view in ("functional", "reporting"):
        run, rows = worlds.report_run(
            reporting,
            "revenue_from_opening_liability",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": AUGUST,
                "to_period_key": AUGUST,
            },
        )
        income = next(row for row in rows if row.get("contract_external_id") == FIRST_UK)
        assert (
            Decimal(income["revenue_recognized"]["amount"])
            > Decimal(income["revenue_from_opening"]["amount"])
            > 0
        )
        if view == "functional":
            assert income["revenue_from_opening"]["amount"] == "36000.00"
            assert income["revenue_recognized"]["amount"] == "43470.00"
        restarted = post(fx.app, f"/api/v1/report-runs/{run['id']}/rerun", fx.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = worlds.run_now(reporting, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        repeated = get(
            fx.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == rows, repeated.text

    # A later return settles the created asset and creates a new liability at
    # the return-date rate. It must not be reported as restored opening relief.
    approved_manual_events(
        fx.place,
        fx.priya,
        recognizer_id,
        {
            "event_type": "RETURN_RECORDED",
            "effective_date": "2026-09-03",
            "payload": {"obligation_key": "O1", "quantity": "120"},
        },
        evidence_file_ids=[],
    )
    for first, view in (
        (AUGUST, "functional"),
        (AUGUST, "reporting"),
        (SEPTEMBER, "functional"),
        (SEPTEMBER, "reporting"),
    ):
        returned_run, returned_rows = worlds.report_run(
            reporting,
            "revenue_from_opening_liability",
            {
                "entity_codes": [AVM_UK],
                "book": "ASC606",
                "currency_view": view,
                "from_period_key": first,
                "to_period_key": SEPTEMBER,
            },
        )
        returned_income = next(
            row for row in returned_rows if row.get("contract_external_id") == FIRST_UK
        )
        if view == "functional":
            # Return uses retained spot .84: 54,000 * .84 = 45,360;
            # the earlier 43,470 recognition leaves net revenue -1,890.
            assert returned_income["revenue_from_opening"]["amount"] == (
                "36000.00" if first == AUGUST else "0.00"
            )
            assert returned_income["revenue_recognized"]["amount"] == (
                "-1890.00" if first == AUGUST else "-45360.00"
            )
        restarted = post(fx.app, f"/api/v1/report-runs/{returned_run['id']}/rerun", fx.maya, {})
        assert restarted.status_code == 202, restarted.text
        complete = worlds.run_now(reporting, UUID(restarted.json()["id"]))
        assert complete["state"] == "SUCCEEDED", complete
        repeated = get(
            fx.app, f"/api/v1/report-runs/{restarted.headers['x-erev-report-run-id']}/data", fx.maya
        )
        assert repeated.status_code == 200 and repeated.json()["items"] == returned_rows, (
            repeated.text
        )
