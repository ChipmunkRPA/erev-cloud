"""A period-end step whose bundle is behind its group, on a database (item
CLOSE-PASS-BEHIND-GROUP-1 — PRODUCT DEFECT, a release blocker; read by lane ENG-FX, measured by
this lane on 2026-10-02; the supervisor's ruling of 2026-10-02 17:30; 04 T-CLS-01 "Period-end
steps" rev 1.304; 05 RCP-08 rev 1.209).

A close-run step is one transaction over every group of the entity and builds each group's
bundle at the STEP's cutoff. A command recorded and computed for a group after the step began
and before the pass reached that group left the group clean and the bundle without the
command's facts. MEASURED before the item, in the world below: the FX step posted a
remeasurement of 50.00 where 40.00 is right and wrote the group's mark forward — the run
``SUCCEEDED`` and the gate ``CLOSE_RUN_COMPLETED`` PASSED; the reclass step, held the same way,
posted 11,050.00 where 8,840.00 is right, and only the computation's mark held the gate.

THE WORLD. ``close_run_worlds.eur_receivable`` — AVM-US (USD); SF-ORD-EU-3001 delivers EUR
10,000.00 on 31 Aug 2026 and is never invoiced — with a second contract of the same terms,
SF-ORD-EU-3002, booked later: its group is passed second. THE COMMAND: an invoice of EUR
2,000.00 on SF-ORD-EU-3002 dated 31 Aug 2026 through ``POST /contracts/{id}/events``; the
append computes. THE FIGURES (PRD §2.5 rates: August's revenue rate 1.100000, its closing rate
1.105000): the remeasurement of an unbilled EUR 10,000.00 is 10,000.00 x 0.005000 = 50.00 and
of EUR 8,000.00 is 40.00; the reclass of the position is 10,000.00 x 1.105000 = 11,050.00 and
8,000.00 x 1.105000 = 8,840.00.

- THE ORACLE: the command before the run. One run posts 40.00 and 8,840.00 for SF-ORD-EU-3002
  and a second run nothing.
- THE THREE RACES: the command while the FX step, the release step or the reclass step stands
  between the two groups. The pass leaves the group out — nothing is posted from the bundle the
  group has left behind — the gate reads the run as out of date, and the second run brings the
  ledger to the oracle's, line for line.

DB-bound, on the record clock (``worlds.on_record_clock``): the step's cutoff and an event's
record time are the server's.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    period,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.close import period_end
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import booked_contract
from support.reference import PERIODS, get

AVM_US: Final = worlds.AVM_US
AUGUST: Final = "FY2026-P08"
SEPTEMBER: Final = "FY2026-P09"
BOOK: Final = "ASC606"
KEY: Final = f"{AVM_US}|{BOOK}"
FIRST: Final = close_run_worlds.EUR_CONTRACT
SECOND: Final = "SF-ORD-EU-3002"
GATE: Final = "CLOSE_RUN_COMPLETED"
FX: Final = period_end.PASSES[0]
RELEASE: Final = period_end.PASSES[1]
RECLASS: Final = period_end.PASSES[2]
STEP_OF: Final = {FX: "FX_REMEASUREMENT", RELEASE: "RELEASE_SCHEDULES", RECLASS: "NETTING_RECLASS"}
OUT_OF_DATE: Final = "Close run out of date, run it again: 1 contracts"
Ledger = dict[tuple[str, str, str], tuple[Decimal, Decimal]]


def _money(functional: str, transaction: str) -> tuple[Decimal, Decimal]:
    return Decimal(functional), Decimal(transaction)


def _fx(amount: str) -> Ledger:
    """August's FX remeasurement of a unit, functional currency alone: a gain of ``amount`` (a
    negative amount takes a gain back)."""
    gain = Decimal(amount)
    return {
        (AUGUST, "FX_REMEASUREMENT", "CONTRACT_LIABILITY"): (gain, Decimal(0)),
        (AUGUST, "FX_REMEASUREMENT", "FX_GAIN_LOSS"): (-gain, Decimal(0)),
    }


def _reclass(functional: str, transaction: str) -> Ledger:
    """August's netting reclass of an unbilled position, with its reversal on 1 September."""
    return {
        (AUGUST, "NETTING_RECLASS", "CONTRACT_LIABILITY"): _money(
            f"-{functional}", f"-{transaction}"
        ),
        (AUGUST, "NETTING_RECLASS", "UNBILLED_RECEIVABLE"): _money(functional, transaction),
        (SEPTEMBER, "NETTING_RECLASS_REVERSAL", "CONTRACT_LIABILITY"): _money(
            functional, transaction
        ),
        (SEPTEMBER, "NETTING_RECLASS_REVERSAL", "UNBILLED_RECEIVABLE"): _money(
            f"-{functional}", f"-{transaction}"
        ),
    }


REVENUE: Final[Ledger] = {
    (AUGUST, "REVENUE_RECOGNITION", "CONTRACT_LIABILITY"): _money("11000.00", "10000.00"),
    (AUGUST, "REVENUE_RECOGNITION", "REVENUE"): _money("-11000.00", "-10000.00"),
}
# What August's close posts for a unit that delivered EUR 10,000.00 and was never invoiced, and
# for one invoiced EUR 2,000.00 of it on 31 Aug 2026 (module docstring, "The figures").
UNBILLED_10000: Final[Ledger] = {**_fx("50.00"), **_reclass("11050.00", "10000.00")}
UNBILLED_8000: Final[Ledger] = {**_fx("40.00"), **_reclass("8840.00", "8000.00")}
# THE ORACLE: the ledger of the two contracts once August's close has read the invoice.
ORACLE: Final = {FIRST: {**REVENUE, **UNBILLED_10000}, SECOND: {**REVENUE, **UNBILLED_8000}}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _two_contracts(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[worlds.ReportWorld, tuple[UUID, UUID], UUID]:
    """The world of the module docstring on the record clock, January to July closed: the world,
    the two groups in the order a step takes them, and the second contract."""
    base = close_run_worlds.eur_receivable(app, keyring, clock, files)
    first = base.contracts[FIRST]
    term = {"start_date": "2026-08-01", "end_date": "2026-12-31"}
    second = booked_contract(
        base.place,
        {
            "external_id": SECOND,
            "customer_id": str(first.contract["customer_id"]),
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
                    **term,
                }
            ],
        },
        activate=True,
    )
    worlds.approved_manual_events(
        base.place,
        base.priya,
        UUID(str(second.contract["id"])),
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-08-31",
            "payload": {"obligation_key": "O1", "quantity": "100", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    world = worlds.on_record_clock(base, clock)
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before=AUGUST
    )
    groups = (
        UUID(str(first.combination_group["id"])),
        UUID(str(second.combination_group["id"])),
    )
    assert groups[0] < groups[1]  # a step takes its groups in id order
    return world, groups, UUID(str(second.contract["id"]))


def _invoice(world: worlds.ReportWorld, contract_id: UUID) -> str:
    """THE COMMAND: EUR 2,000.00 invoiced on 31 Aug 2026; the append computes. Its status."""
    sent = worlds._appended_through_api(
        world.place,
        contract_id,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-08-31",
            "payload": {
                "invoice_number": "INV-EU-2",
                "line_external_id": "INV-EU-2-1",
                "obligation_key": "O1",
                "amount": {"amount": "2000.00", "currency": "EUR"},
                "issue_date": "2026-08-31",
            },
        },
    )
    return str(sent["computation"]["status"])


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _ledger(world: worlds.ReportWorld, run: dict[str, Any] | None = None) -> dict[str, Ledger]:
    """Per contract: the functional and the transaction amount, summed by period, entry kind and
    account role — of the lines one close run sealed, or of every line the ledger holds. A sum of
    zero in both is not listed."""
    line, posting = subledger_line, subledger_posting
    statement = select(
        contract.c.external_id,
        period.c.period_key,
        line.c.entry_kind,
        line.c.account_role,
        line.c.amount_txn,
        line.c.amount_functional,
    ).select_from(
        line.join(
            posting,
            and_(
                posting.c.tenant_id == line.c.tenant_id, posting.c.id == line.c.subledger_posting_id
            ),
        )
        .join(period, and_(period.c.tenant_id == line.c.tenant_id, period.c.id == line.c.period_id))
        .join(
            contract,
            and_(contract.c.tenant_id == line.c.tenant_id, contract.c.id == line.c.contract_id),
        )
    )
    if run is not None:
        statement = statement.where(posting.c.close_run_id == UUID(str(run["id"])))
    sums: dict[str, dict[tuple[str, str, str], list[Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: [Decimal(0), Decimal(0)])
    )
    for row in _rows(world.tenant_id, statement):
        key = (
            str(row["period_key"]),
            str(getattr(row["entry_kind"], "value", row["entry_kind"])),
            str(getattr(row["account_role"], "value", row["account_role"])),
        )
        held = sums[str(row["external_id"])][key]
        held[0] += Decimal(row["amount_functional"])
        held[1] += Decimal(row["amount_txn"])
    return {
        name: {key: (held[0], held[1]) for key, held in lines.items() if held[0] or held[1]}
        for name, lines in sums.items()
    }


def _marks(world: worlds.ReportWorld, groups: tuple[UUID, UUID]) -> list[str | None]:
    rows = _rows(
        world.tenant_id,
        select(combination_group.c.id, combination_group.c.period_ends_open).where(
            combination_group.c.id.in_(groups)
        ),
    )
    by_id = {UUID(str(row["id"])): dict(row["period_ends_open"] or {}) for row in rows}
    return [by_id[group].get(KEY) for group in groups]


def _gate(world: worlds.ReportWorld) -> tuple[Any, ...]:
    state = worlds.period_state(world, AVM_US, AUGUST)
    shown = get(world.app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    (row,) = [item for item in shown.json()["checklist"] if item["code"] == GATE]
    return row["status"], row["result"]["count"], row["result"]["detail"]


def _counts(run: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """(groups passed, groups left out) of each period-end step."""
    return {
        pass_name: (
            int(runs.step(run, step)["counts"]["groups"]),
            int(runs.step(run, step)["counts"]["groups_skipped"]),
        )
        for pass_name, step in STEP_OF.items()
    }


def _held_between_the_groups(
    monkeypatch: pytest.MonkeyPatch, pass_name: str, second: UUID, command: Callable[[], str]
) -> list[str]:
    """The step of ``pass_name`` stands between its two groups: right before it locks the second
    one, the command is recorded and computed in its own request, and committed. Answers with
    the command's status, once it ran."""
    over = period_end._group_lines
    ran: list[str] = []

    def held(uow: Any, scope: Any, group_id: UUID, name: str, *rest: Any, **named: Any) -> Any:
        if name == pass_name and group_id == second and not ran:
            ran.append(command())
        return over(uow, scope, group_id, name, *rest, **named)

    monkeypatch.setattr(period_end, "_group_lines", held)
    return ran


def _raced(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    pass_name: str,
) -> tuple[worlds.ReportWorld, tuple[UUID, UUID], dict[str, Any]]:
    """August's close run with the command computed while the step of ``pass_name`` stands
    between the two groups: the world, the groups and the run."""
    world, groups, contract_id = _two_contracts(app, keyring, clock, files)
    with monkeypatch.context() as patch:
        ran = _held_between_the_groups(
            patch, pass_name, groups[1], lambda: _invoice(world, contract_id)
        )
        run = runs.closed(world, patch, entity_code=AVM_US, period_key=AUGUST)
    assert ran == ["SUCCEEDED"]  # the command ran, once, inside the step, and was computed
    assert run["status"] == "SUCCEEDED", run
    return world, groups, run


def _run_again_to_the_oracle(
    world: worlds.ReportWorld, groups: tuple[UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Ledger]:
    """The run the gate asks for: it passes both groups in every step, the ledger is THE ORACLE's
    line for line, both marks stand at 1 September and the gate passes. What it sealed."""
    again = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert again["status"] == "SUCCEEDED", again
    assert _counts(again) == {FX: (2, 0), RELEASE: (2, 0), RECLASS: (2, 0)}
    assert _ledger(world) == ORACLE
    assert _marks(world, groups) == ["2026-09-01", "2026-09-01"]
    assert _gate(world) == ("PASSED", 0, None)
    return _ledger(world, again)


# --- the oracle -----------------------------------------------------------------------------------


def test_the_command_before_the_run_is_what_augusts_close_posts(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE ORACLE. With the invoice recorded and computed before the run, one run posts for
    SF-ORD-EU-3002 the remeasurement of EUR 8,000.00, 40.00, and its reclass, 8,840.00 with the
    reversal — and for SF-ORD-EU-3001 50.00 and 11,050.00; both groups are passed and marked,
    the gate passes, and a second run posts nothing."""
    world, groups, contract_id = _two_contracts(app, keyring, clock, files)
    assert _invoice(world, contract_id) == "SUCCEEDED"
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert run["status"] == "SUCCEEDED", run
    assert _counts(run) == {FX: (2, 0), RELEASE: (2, 0), RECLASS: (2, 0)}
    assert _ledger(world, run) == {FIRST: UNBILLED_10000, SECOND: UNBILLED_8000}
    assert _ledger(world) == ORACLE
    assert _marks(world, groups) == ["2026-09-01", "2026-09-01"]
    assert _gate(world) == ("PASSED", 0, None)
    assert _run_again_to_the_oracle(world, groups, monkeypatch) == {}


# --- the three races ------------------------------------------------------------------------------


def test_a_command_computed_while_the_fx_step_stands_between_two_groups_leaves_its_group_out(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE MEASURED DEFECT. The first period-end step has passed SF-ORD-EU-3001 when the invoice
    is recorded and computed for SF-ORD-EU-3002. Its bundle, built at the step's cutoff, does
    not hold the invoice: the step leaves the group out — one group passed, one left out, no
    remeasurement posted for it — and does not mark it. The release and the reclass, later
    transactions whose cutoff covers the invoice, pass it: the reclass is the oracle's 8,840.00.
    The gate reads the run as out of date, and the run that is run again posts the
    remeasurement of EUR 8,000.00, 40.00.

    Fail-first (measured before the item): the step posted 50.00 — the remeasurement of EUR
    10,000.00 — and wrote the mark 1 September for the group; the run ``SUCCEEDED`` with no
    group left out and the gate PASSED, count 0."""
    world, groups, run = _raced(app, keyring, clock, files, monkeypatch, FX)
    assert _counts(run) == {FX: (1, 1), RELEASE: (2, 0), RECLASS: (2, 0)}
    assert _ledger(world, run) == {
        FIRST: UNBILLED_10000,
        SECOND: _reclass("8840.00", "8000.00"),  # no remeasurement from the bundle left behind
    }
    assert _marks(world, groups)[0] == "2026-09-01"
    assert _marks(world, groups)[1] != "2026-09-01"  # the step did not pass it: not marked
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)
    assert _run_again_to_the_oracle(world, groups, monkeypatch) == {SECOND: _fx("40.00")}


def test_a_command_computed_while_the_release_step_stands_between_two_groups_leaves_its_group_out(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FX step has passed and marked both groups — 50.00 each, right when it ran — and the
    release step has passed SF-ORD-EU-3001 when the invoice is computed for SF-ORD-EU-3002. The
    release step leaves the group out; the computation has lowered the group's mark to 1
    August, so the gate reads the run as out of date; the reclass, a later transaction, posts
    8,840.00. The run that is run again posts the difference of the remeasurement, -10.00.

    Fail-first: the release step passed both groups (it has no amount in this world); the mark
    and the gate were as here."""
    world, groups, run = _raced(app, keyring, clock, files, monkeypatch, RELEASE)
    assert _counts(run) == {FX: (2, 0), RELEASE: (1, 1), RECLASS: (2, 0)}
    assert _ledger(world, run) == {
        FIRST: UNBILLED_10000,
        SECOND: {**_fx("50.00"), **_reclass("8840.00", "8000.00")},
    }
    assert _marks(world, groups) == ["2026-09-01", "2026-08-01"]
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)
    assert _run_again_to_the_oracle(world, groups, monkeypatch) == {SECOND: _fx("-10.00")}


def test_a_command_computed_while_the_reclass_step_stands_between_two_groups_leaves_its_group_out(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reclass step has passed SF-ORD-EU-3001 when the invoice is computed for
    SF-ORD-EU-3002: the step leaves the group out and posts no reclass for it. The mark the
    computation lowered holds the gate, and the run that is run again posts the difference of
    the remeasurement, -10.00, and the reclass of the position the invoice left, 8,840.00.

    Fail-first (measured before the item): the step posted 11,050.00 (EUR 10,000.00) for the
    group, 2,210.00 more than its position, and the second run took 2,210.00 back."""
    world, groups, run = _raced(app, keyring, clock, files, monkeypatch, RECLASS)
    assert _counts(run) == {FX: (2, 0), RELEASE: (2, 0), RECLASS: (1, 1)}
    assert _ledger(world, run) == {FIRST: UNBILLED_10000, SECOND: _fx("50.00")}
    assert _marks(world, groups) == ["2026-09-01", "2026-08-01"]
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)
    assert _run_again_to_the_oracle(world, groups, monkeypatch) == {
        SECOND: {**_fx("-10.00"), **_reclass("8840.00", "8000.00")}
    }
