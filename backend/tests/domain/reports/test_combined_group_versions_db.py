"""A contract combined after it was computed in its own group, in the reports and at the lock
(items RPT-FORMER-GROUP-VERSIONS-1 and RPT-FORMER-GROUP-READERS-1; supervisor rulings R-115 (a)
and R-117 (a) of 2026-09-30; 04 T-CON-04 reading rule, API-R-35; ENGINE_SPEC S02-R-09, S02-R-10;
ENGINE_SPEC_B S15-R-07a, S15-R-08, S15-R-12, S15-R-18, S15-R-24, S15-R-24a; SCREENS_B RPT-02,
RPT-03, RPT-06, RPT-07, RPT-09 to RPT-11).

A version counts for a member contract only while that contract is a member of the version's
group. A group keeps its versions when its contract leaves it, and the reports read "each group's
latest version": after an approved combination each member was read twice. Measured before, in
this world: RPT-02 held two rows per member with one row key (and its tie-out failed); the lock's
``CONTRACT_BALANCES`` and ``RPO`` datasets were refused for a duplicate row key, so September
could not be locked; RPO stated 218,841.25 and 79,849.31; the RPO rollforward ``NEW_CONTRACTS``
312,000.00; RPT-11 listed each obligation twice.

World (``combined``), through the product's commands at the frozen clock 2026-09-12T12:00:00Z:
``worlds.k02_marrowby_commission`` (WLD-K-02) with ``worlds.k09_orrin_vale`` (WLD-K-09
``SF-ORD-10417``: 30 seats, 108,000.00 from 01 Sep 2026 to 31 Aug 2029, INV-US-3101 36,000.00 on
01 Sep 2026) and a second order of the customer, ``SF-ORD-10418`` (10 seats, 48,000.00 from
01 Sep 2026 to 31 Aug 2027, INV-US-3102 48,000.00 on 01 Sep 2026) — each booked, activated and
computed in its own group. Maya then proposes and submits the combination of the two orders
(606-10-25-9(b)) and Marcus approves it: the group is computed from its inception and
re-allocates 156,000.00 as 117,000.00 and 39,000.00 (3 : 1, the seats). September revenue:
117,000.00 × 30 / 1,096 = 3,202.55 and 39,000.00 × 30 / 365 = 3,205.48.

Item RPT-FORMER-GROUP-READERS-1 (the last section). Each contract is read from the last version
along its chain: the versions computed with it among their members, membership after membership.
Measured before, in this world: the contract history listed both versions of an order under one
row key with "Version" 1, 1; ``GET /schedule-lines`` listed 2,956.20 beside 3,202.55 and the
cost line twice; the close monitors read two liability layers and two recognitions per order;
and with the combined group's computation deferred — a group above the inline budget — RPT-02
and the waterfall stated neither order until the job had run.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    contract_version,
    customer,
    job,
    period_lock,
)
from erev_api.domain.close import gates, monitors
from erev_api.domain.contracts import bundles, combination
from erev_api.domain.reports import locked, tie_outs
from erev_api.domain.reports.builders import ReportParams, revenue_waterfall
from erev_api.enums import ContractEventType, JobKind
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from support import worlds
from support.db import TestDatabase
from support.factories import appended, booked_contract, computed, seat_body, seat_line
from support.reference import approve, assign, get, post
from support.worlds import (
    AVM_US,
    K02,
    K09,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    SEPTEMBER_2026,
    ReportWorld,
    report_run,
)

SECOND: Final = "SF-ORD-10418"
GROUPS: Final = "/api/v1/combination-groups"
AT_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026}
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
BY_CONTRACT: Final = {**AT_SEPTEMBER, "row_dimension": "CONTRACT"}
LIABILITY: Final = "contract_liability"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def two_orders(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """K-02, K-09 and the second order, each computed in its own group; nothing combined."""
    world = worlds.k09_orrin_vale(worlds.k02_marrowby_commission(app, keyring, clock, files))
    place = world.place
    buyer = place.scalar(select(customer.c.id).where(customer.c.code == "C-09"))
    line = seat_line("O1", seats="10", price="48000.00", start="2026-09-01", end="2027-08-31")
    body = seat_body(UUID(str(buyer)), external_id=SECOND, inception="2026-09-01", lines=[line])
    booked = booked_contract(place, body, activate=True)
    invoice = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 9, 1),
        payload=BillingRecordedV1(
            invoice_number="INV-US-3102",
            line_external_id="INV-US-3102-1",
            obligation_key="O1",
            amount=MoneyIn(amount="48000.00", currency="USD"),
            issue_date=date(2026, 9, 1),
        ),
    )
    appended(place, UUID(str(booked.contract["id"])), 2, [invoice])
    computed(place, UUID(str(booked.combination_group["id"])))
    return dataclasses.replace(
        world, contracts=MappingProxyType({**world.contracts, SECOND: booked})
    )


def combine(world: ReportWorld) -> UUID:
    """The two orders combined by the approved command (ENGINE_SPEC S02-R-10); the group's id."""
    proposed = post(
        world.app,
        GROUPS,
        world.maya,
        {
            "contract_ids": [str(world.contracts[name].contract["id"]) for name in (K09, SECOND)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = proposed.json()["id"]
    submitted = post(world.app, f"{GROUPS}/{group_id}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    return UUID(group_id)


@pytest.fixture
def combined(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    world = two_orders(app, keyring, clock, files)
    combine(world)
    return world


def rerun(world: ReportWorld, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``POST /report-runs/{id}/rerun``, the job run as the worker does, the run and its rows."""
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    new_id = started.headers[REPORT_RUN_ID_HEADER]
    finished = worlds.run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(world.app, f"{REPORT_RUNS}/{new_id}", world.maya)
    listed = get(world.app, f"{REPORT_RUNS}/{new_id}/data", world.maya, {"limit": "200"})
    assert shown.status_code == 200 and listed.status_code == 200, (shown.text, listed.text)
    return dict(shown.json()), list(listed.json()["items"])


def now(world: ReportWorld) -> datetime:
    """The server's present: versions and memberships are stamped by it (DB-08)."""
    found: datetime = world.place.scalar(select(func.clock_timestamp()))
    return found


def amount(cell: Any) -> str:
    return str(cell["amount"]) if isinstance(cell, Mapping) else str(cell)


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows), [row["row_key"] for row in rows]  # no row key repeats
    return found


def tie(run: Mapping[str, Any], code: str) -> tuple[str, str | None]:
    (found,) = [item for item in run["tie_out_results"] if item["code"] == code]
    difference = found["difference"]
    return str(found["result"]), None if not difference else str(difference[0]["amount"])


# --- the latest at the cutoff: the balance reports -----------------------------------------------


@pytest.mark.slow
def test_a_combined_member_has_one_balance_row(combined: ReportWorld) -> None:
    """RPT-02 at 30 Sep 2026 (S15-R-07a): one row per member contract, from the combined group's
    version — billed less revenue, 36,000.00 − 3,202.55 and 48,000.00 − 3,205.48 — and K-02
    beside them; the rows equal the rollforward's closing. Before: each member twice under one
    row key, the second row the balance of the group it had left (33,043.80 and 44,054.79), and
    ``TO_BALANCES_EQ_ROLLFORWARD`` FAIL."""
    run, rows = report_run(combined, "contract_balances", AT_SEPTEMBER)
    found = keyed(rows)
    assert {key: amount(row[LIABILITY]) for key, row in found.items()} == {
        f"contract:{K02}:{AVM_US}": "30246.58",
        f"contract:{K09}:{AVM_US}": "32797.45",
        f"contract:{SECOND}:{AVM_US}": "44794.52",
        "TOTAL:USD": "107838.55",
    }
    assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD) == ("PASS", "0.00")


@pytest.mark.slow
def test_the_rollforward_of_a_combined_member_closes_at_its_one_balance(
    combined: ReportWorld,
) -> None:
    """RPT-03 for September 2026: the invoices under ``BILLINGS``, the revenue the combined group
    recognizes for each member against them, and a closing that equals RPT-02. Before:
    ``TO_BALANCES_EQ_ROLLFORWARD`` FAIL by the former groups' balances, and which version a
    member's row was read from was not determined."""
    run, rows = report_run(combined, "contract_balance_rollforward", SEPTEMBER)
    section_1 = {
        str(row["line_code"]): amount(row[LIABILITY])
        for row in rows
        if row["line_code"] and amount(row[LIABILITY]) != "0.00"
    }
    assert section_1 == {
        "OPENING": "40109.59",  # K-02 at 31 Aug 2026
        "BILLINGS": "84000.00",
        "REVENUE_FROM_OPENING": "-9863.01",  # K-02
        "REVENUE_FROM_PERIOD_BILLINGS": "-6408.03",
        "CLOSING": "107838.55",
    }
    by_contract = {
        str(row["contract_external_id"]): (
            amount(row["billings"]),
            amount(row["revenue_from_period_billings"]),
            amount(row["other"]),
            amount(row["closing"]),
        )
        for row in rows
        if row.get("contract_external_id") in (K09, SECOND)
    }
    assert by_contract == {
        K09: ("36000.00", "-3202.55", "0.00", "32797.45"),
        SECOND: ("48000.00", "-3205.48", "0.00", "44794.52"),
    }
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES) == ("PASS", "0.00")
    assert tie(run, tie_outs.TO_BALANCES_EQ_ROLLFORWARD) == ("PASS", "0.00")


# --- the version at a date: RPO, its rollforward, the latest status -------------------------------


@pytest.mark.slow
def test_rpo_states_a_combined_member_once(combined: ReportWorld) -> None:
    """RPT-06 at 30 Sep 2026 (S15-R-08): allocated less revenue to date by the combined group's
    version — 117,000.00 − 3,202.55 and 39,000.00 − 3,205.48 — and K-02's 150,246.58. Before:
    218,841.25 and 79,849.31, the former group's remaining 105,043.80 and 44,054.79 on top."""
    run, rows = report_run(combined, "rpo", BY_CONTRACT)
    found = keyed(rows)
    assert {key: amount(row["total"]) for key, row in found.items() if row["section"] == 1} == {
        f"contract:{K02}": "150246.58",
        f"contract:{K09}": "113797.45",
        f"contract:{SECOND}": "35794.52",
        "TOTAL:USD": "299838.55",
    }
    assert run["control_totals"]["total"] == {"USD": "299838.55"}


@pytest.mark.slow
def test_the_rpo_rollforward_shows_the_combination_under_modifications(
    combined: ReportWorld,
) -> None:
    """RPT-07 for September 2026 (S15-R-12, S15-R-24a): each order is a new contract at its booked
    price, and the combination re-allocates 9,000.00 from the second order to the first under
    ``MODIFICATIONS`` — nothing in all. ``NEW_CONTRACTS`` 156,000.00; before, 312,000.00 with
    ``UNEXPLAINED`` 0.00 and revenue 13,309.44 for the 6,408.03 posted."""
    run, rows = report_run(combined, "rpo_rollforward", SEPTEMBER)
    lines = {
        str(row["line_code"]): amount(row["rpo"])
        for row in rows
        if row["section"] == 1 and amount(row["rpo"]) != "0.00"
    }
    assert lines == {
        "OPENING": "160109.59",  # K-02 at 31 Aug 2026
        "NEW_CONTRACTS": "156000.00",
        "REVENUE": "-16271.04",  # 9,863.01 + 3,202.55 + 3,205.48
        "CLOSING": "299838.55",
    }
    by_contract = {
        str(row["contract_external_id"]): {
            name: amount(row[name])
            for name in ("new_contracts", "modifications", "revenue", "unexplained", "closing")
        }
        for row in rows
        if row["section"] == 2 and row["contract_external_id"] in (K09, SECOND)
    }
    assert by_contract == {
        K09: {
            "new_contracts": "108000.00",
            "modifications": "9000.00",
            "revenue": "-3202.55",
            "unexplained": "0.00",
            "closing": "113797.45",
        },
        SECOND: {
            "new_contracts": "48000.00",
            "modifications": "-9000.00",
            "revenue": "-3205.48",
            "unexplained": "0.00",
            "closing": "35794.52",
        },
    }
    assert tie(run, "TO_RPO_ROLLFORWARD_EQ_RPO") == ("PASS", "0.00")


@pytest.mark.slow
def test_the_latest_status_lists_a_combined_member_once(combined: ReportWorld) -> None:
    """RPT-11 as of 30 Sep 2026: one row per obligation, the combined group's version. Before:
    two rows with one row key for each member's obligation."""
    _, rows = report_run(
        combined,
        "latest_contract_status",
        {"entity_codes": [AVM_US], "book": "ASC606", "as_of": "2026-09-30"},
    )
    found = keyed(rows)
    assert sorted(found) == [
        f"obligation:{K02}:O1",
        f"obligation:{K09}:O1",
        f"obligation:{SECOND}:O1",
    ]


# --- the lock -------------------------------------------------------------------------------------


@pytest.mark.slow
def test_the_period_is_locked_after_an_approved_combination(
    combined: ReportWorld, clock: FrozenClock
) -> None:
    """September 2026 locked through the product after the combination: the twelve datasets are
    frozen; ``CONTRACT_BALANCES`` and ``RPO`` hold one row per member. Before: the lock decision
    was refused — "the CONTRACT_BALANCES dataset cannot be frozen (the rows do not form a dataset:
    duplicate row_key 'contract:SF-ORD-10417:AVM-US')", rule ``S15-R-18`` — as was ``RPO``."""
    world = combined
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=SEPTEMBER_2026)
    period_id = UUID(str(worlds.period_state(world, AVM_US, SEPTEMBER_2026)["period"]["id"]))
    lock_id = world.place.scalar(
        select(period_lock.c.id).where(
            period_lock.c.period_id == period_id, period_lock.c.kind == "LOCK"
        )
    )
    with world.place.uow() as uow:
        balances = locked.report_data(
            locked.locked_dataset(uow, report_code="contract_balances", lock_id=lock_id)
        )
        rpo = locked.report_data(locked.locked_dataset(uow, report_code="rpo", lock_id=lock_id))
    assert sorted(str(row["row_key"]) for row in balances.rows) == [
        f"contract:{K02}:{AVM_US}",
        f"contract:{K09}:{AVM_US}",
        f"contract:{SECOND}:{AVM_US}",
    ]
    assert sorted(str(row["row_key"]) for row in rpo.rows) == [
        f"obligation:{AVM_US}:{K02}:O1",
        f"obligation:{AVM_US}:{K09}:O1",
        f"obligation:{AVM_US}:{SECOND}:O1",
    ]


# --- the cutoff and the binding -------------------------------------------------------------------


@pytest.mark.slow
def test_a_cutoff_before_the_combination_reads_the_former_groups(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The rule is at the run's cutoff (record time): before the combination was recorded each
    order's own group holds it and is read; after it the combined group alone. The former groups
    keep their versions either way — they are history, not deleted."""
    world = two_orders(app, keyring, clock, files)
    place = world.place
    members = [UUID(str(world.contracts[name].contract["id"])) for name in (K09, SECOND)]

    def groups_read(cutoff: datetime) -> set[UUID]:
        with place.uow() as uow:
            ids = list(
                uow.session.execute(
                    tie_outs.latest_versions(uow.session, book_code="ASC606", cutoff=cutoff)
                ).scalars()
            )
            return {
                UUID(str(value))
                for value in uow.session.execute(
                    select(contract_version.c.combination_group_id).where(
                        contract_version.c.id.in_(ids)
                    )
                ).scalars()
            }

    own = {
        UUID(str(row["combination_group_id"]))
        for row in place.rows(
            select(combination_group_member.c.combination_group_id).where(
                combination_group_member.c.contract_id.in_(members)
            )
        )
    }
    assert len(own) == 2
    before = now(world)
    assert own <= groups_read(before)
    joint = combine(world)
    read = groups_read(now(world))
    assert joint in read and not (own & read)
    # the same instant as before the combination still answers the former groups
    assert own <= groups_read(before) and joint not in groups_read(before)


@pytest.mark.slow
def test_a_run_bound_before_the_combination_reproduces_after_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """S15-R-24: a bound run keeps its bound version ids. RPT-02 run before the combination and
    rerun after it reads the former groups' versions again and reproduces its output
    (CTL-029 PASS)."""
    world = two_orders(app, keyring, clock, files)
    original, rows = report_run(world, "contract_balances", AT_SEPTEMBER)
    stated = {str(row["row_key"]): amount(row[LIABILITY]) for row in rows}
    assert stated[f"contract:{K09}:{AVM_US}"] == "33043.80"  # 36,000.00 − 2,956.20, on its own
    assert stated[f"contract:{SECOND}:{AVM_US}"] == "44054.79"  # 48,000.00 − 3,945.21
    combine(world)
    again, rows = rerun(world, str(original["id"]))
    assert {str(row["row_key"]): amount(row[LIABILITY]) for row in rows} == stated
    assert again["output"]["sha256"] == original["output"]["sha256"]


# --- item RPT-FORMER-GROUP-READERS-1: the chain in the history, the lists and the monitors --------

HISTORY: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_date": "2026-01-01",
    "to_date": "2026-09-30",
}
AS_OF_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": "ASC606", "as_of": "2026-09-30"}
SCHEDULE_LINES: Final = "/api/v1/schedule-lines"
WRONG_ORDER: Final = "SF-ORD-10418 was combined with the wrong order."


def history_rows(world: ReportWorld, code: str) -> list[dict[str, Any]]:
    _, rows = report_run(world, code, HISTORY)
    keyed(rows)  # no row key repeats
    return rows


def versions_stated(world: ReportWorld) -> dict[str, int]:
    """RPT-11 at 30 Sep 2026: the "Version" of each contract's row."""
    _, rows = report_run(world, "latest_contract_status", AS_OF_SEPTEMBER)
    return {
        str(row["contract_external_id"]): int(row["version_no"]) for row in keyed(rows).values()
    }


def liabilities(world: ReportWorld) -> dict[str, str]:
    """RPT-02 at 30 Sep 2026: the contract liability by row key; no row key repeats."""
    _, rows = report_run(world, "contract_balances", AT_SEPTEMBER)
    return {key: amount(row[LIABILITY]) for key, row in keyed(rows).items()}


def september_revenue(world: ReportWorld) -> dict[str, str]:
    """The revenue waterfall for September 2026: the total by row key."""
    _, rows = report_run(world, "revenue_waterfall", SEPTEMBER)
    return {key: amount(row["total"]) for key, row in keyed(rows).items()}


def september_lines(world: ReportWorld, name: str) -> list[tuple[str, str]]:
    """``GET /schedule-lines`` of one contract for September 2026: schedule kind and amount."""
    listed = get(
        world.app,
        SCHEDULE_LINES,
        world.maya,
        {
            "contract": str(world.contracts[name].contract["id"]),
            "from_period": SEPTEMBER_2026,
            "to_period": SEPTEMBER_2026,
            "limit": "200",
        },
    )
    assert listed.status_code == 200, listed.text
    return sorted(
        (str(item["schedule_kind"]), amount(item["amount"])) for item in listed.json()["items"]
    )


def monitor_inputs(world: ReportWorld) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """What the close monitors read for AVM-US and September 2026: the contract-liability layers
    (layer key, open balance) and the period's recognitions (contract, amount)."""
    place = world.place
    period_id = UUID(str(worlds.period_state(world, AVM_US, SEPTEMBER_2026)["period"]["id"]))
    names = {
        UUID(str(row["id"])): str(row["external_id"])
        for row in place.rows(select(contract.c.id, contract.c.external_id))
    }
    with place.uow() as uow:
        scope = gates.scope_of_period(uow.session, world.entity_id, "ASC606", period_id)
        assert scope is not None
        inputs = monitors.collect_inputs(uow.session, scope)
    layers = sorted((item.layer_key, f"{item.open_balance:.2f}") for item in inputs.layers)
    recognitions = sorted(
        (names[item.contract_id], f"{item.amount:.2f}") for item in inputs.recognitions
    )
    return layers, recognitions


def waterfall_obligations(world: ReportWorld) -> list[tuple[str, str]]:
    """The obligation rows the waterfall's population reads for September 2026: contract and
    obligation key, one entry per row read."""
    params = ReportParams(
        report_code="revenue_waterfall",
        report_version=1,
        parameters=dict(SEPTEMBER),
        entity_ids=(world.entity_id,),
        known_at=world.place.clock.now(),
    )
    with world.place.uow() as uow:
        found = revenue_waterfall.population(uow.session, params)
    return sorted((item.external_id, item.obligation_key) for item in found.obligations)


def layer(name: str, balance: str) -> tuple[str, str]:
    # These fixtures each bill in EV-000003. The monitor reads the persisted originating
    # layer, not a synthetic contract-level net balance (T-CON-18 / POL-161).
    return f"CONTRACT_LIABILITY:{name}/EV-000003", balance


def deferred(monkeypatch: pytest.MonkeyPatch) -> None:
    """From here on a combination change defers the computation of its groups, as it does for a
    group above the inline budget of 200 obligations (dev-guide DG-CMD-09): the budget is set
    below the size of every group."""
    monkeypatch.setattr(combination, "OBLIGATION_BUDGET", 0)


def queued_computations(world: ReportWorld) -> dict[UUID, UUID]:
    """The queued ``CONTRACT_COMPUTE`` jobs: combination group → job."""
    found = world.place.rows(
        select(job.c.id, job.c.params).where(
            job.c.kind == "CONTRACT_COMPUTE", job.c.state == "QUEUED"
        )
    )
    return {
        UUID(str(row["params"]["combination_group_ids"][0])): UUID(str(row["id"])) for row in found
    }


def computed_now(world: ReportWorld, job_id: UUID) -> None:
    finished = worlds.run_now(world, job_id)
    assert finished["state"] == "SUCCEEDED", finished


# The server raises the code itself, as it does when its lock table is full (RES-53-COMPUTE-1).
OUT_OF_SHARED_MEMORY: Final = text(
    "DO $fault$ BEGIN RAISE EXCEPTION 'out of shared memory' USING ERRCODE = '53200'; END $fault$"
)
TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def last_attempt(world: ReportWorld, job_id: UUID) -> dict[str, Any]:
    """The worker runs the job's task as the last attempt its retry policy allows; API-S-Job."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(TASK_FETCHED, {"id": task_id})
    attempts = registry.HANDLERS[JobKind.CONTRACT_COMPUTE].retry.max_attempts
    registry.run_job(job_id, world.tenant_id, attempt=attempts, runtime=world.runtime)
    shown = get(world.app, f"/api/v1/jobs/{job_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def history_keys(world: ReportWorld) -> list[str]:
    """RPT-09: the row keys of the contract history, in the report's order."""
    return [str(row["row_key"]) for row in history_rows(world, "contract_history")]


def each_order_as_its_own_group_last_computed_it(world: ReportWorld, joint: UUID) -> None:
    """The combined group holds both orders, has no version and awaits its computation: RPT-02,
    the schedule lines and the monitors read each order once, from its own group's version, and
    the period's lock gate counts the group."""
    assert not world.place.rows(
        select(contract_version.c.id).where(contract_version.c.combination_group_id == joint)
    )
    assert liabilities(world) == {
        f"contract:{K02}:{AVM_US}": "30246.58",
        f"contract:{K09}:{AVM_US}": "33043.80",
        f"contract:{SECOND}:{AVM_US}": "44054.79",
        "TOTAL:USD": "107345.17",
    }
    assert september_lines(world, K09) == [("COST_AMORTIZATION", "177.37"), ("REVENUE", "2956.20")]
    assert september_lines(world, SECOND) == [("REVENUE", "3945.21")]
    layers, recognitions = monitor_inputs(world)
    assert layers == [layer(K02, "30246.58"), layer(K09, "33043.80"), layer(SECOND, "44054.79")]
    assert recognitions == [(K02, "9863.01"), (K09, "2956.20"), (SECOND, "3945.21")]
    # The counts are the single read's: a row of the list answers them null (04 §16.8 rev 1.199).
    state_id = worlds.period_state(world, AVM_US, SEPTEMBER_2026)["id"]
    shown = get(world.app, f"/api/v1/periods/{state_id}", world.maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["blockers"]["groups_dirty"] == 1


@pytest.mark.slow
def test_the_history_numbers_a_contracts_versions_along_its_chain(combined: ReportWorld) -> None:
    """RPT-09, RPT-10 and RPT-11 (supervisor ruling R-117 (a)): ``version_no`` counts the versions
    of one group, so each order held a version 1 twice. Its versions are numbered along its chain
    in record order — the own group's version 1, the combined group's version 2 — in the row key,
    the "Version" column and the order of the rows; K-02, which never changed its group, keeps
    its number. Before: ``version:SF-ORD-10417:1:O1`` twice (108,000.00 and 117,000.00), "Version"
    1, 1, and RPT-11 "Version" 1 for the combined group's version."""
    expected = [
        (f"version:{K02}:1:O1", 1, "240000.00"),
        (f"version:{K09}:1:O1", 1, "108000.00"),
        (f"version:{K09}:2:O1", 2, "117000.00"),
        (f"version:{SECOND}:1:O1", 1, "48000.00"),
        (f"version:{SECOND}:2:O1", 2, "39000.00"),
    ]
    stated = [
        (str(row["row_key"]), int(row["version_no"]), amount(row["allocated_amount"]))
        for row in history_rows(combined, "contract_history")
    ]
    assert stated == expected
    legacy = history_rows(combined, "legacy_contract_history_export")
    assert [(str(row["row_key"]), str(row["Original Allocation"])) for row in legacy] == [
        (key, allocated.removesuffix(".00")) for key, _, allocated in expected
    ]
    assert versions_stated(combined) == {K02: 1, K09: 2, SECOND: 2}


@pytest.mark.slow
def test_the_schedule_lines_and_the_monitors_read_a_combined_member_once(
    combined: ReportWorld,
) -> None:
    """``GET /schedule-lines`` (04 API-R-35) and the close monitors' inputs read each contract
    from the version it is read from, the combined group's. Before: the lines of the own groups'
    last versions beside them — REVENUE 2,956.20 and 3,945.21, the cost line twice — and two
    liability layers (33,043.80; 44,054.79) and two recognitions per order."""
    assert september_lines(combined, K09) == [
        ("COST_AMORTIZATION", "177.37"),
        ("REVENUE", "3202.55"),
    ]
    assert september_lines(combined, SECOND) == [("REVENUE", "3205.48")]
    # Group FIFO consumes 3,202.55 + 3,205.48 from the first invoice's 36,000;
    # the second invoice's 48,000 is untouched. Together the open layers equal
    # 84,000 billed - 6,408.03 recognized = 77,591.97, without former-group layers.
    layers, recognitions = monitor_inputs(combined)
    assert layers == [layer(K02, "30246.58"), layer(K09, "29591.97"), layer(SECOND, "48000.00")]
    assert recognitions == [(K02, "9863.01"), (K09, "3202.55"), (SECOND, "3205.48")]


@pytest.mark.slow
def test_a_member_is_read_from_its_own_group_until_the_combined_group_is_computed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approved combination of a group above the inline budget defers the group's computation
    (DG-CMD-09). Until the job has run each order stays where it was last computed, once: its own
    group's version — 36,000.00 − 2,956.20 and 48,000.00 − 3,945.21 — in RPT-02, the waterfall,
    the schedule lines, the monitors and RPT-11. After the job: the combined group's version.
    Before: in that window RPT-02 stated K-02's 30,246.58 alone (total 30,246.58) and the
    waterfall K-02's 9,863.01 alone — the group that holds the two orders had no version, and
    the groups with their versions held no member."""
    world = two_orders(app, keyring, clock, files)
    deferred(monkeypatch)
    joint = combine(world)
    jobs = queued_computations(world)
    assert list(jobs) == [joint]

    assert liabilities(world) == {
        f"contract:{K02}:{AVM_US}": "30246.58",
        f"contract:{K09}:{AVM_US}": "33043.80",
        f"contract:{SECOND}:{AVM_US}": "44054.79",
        "TOTAL:USD": "107345.17",
    }
    assert september_revenue(world) == {
        f"contract:{K02}": "9863.01",
        f"contract:{K09}": "2956.20",
        f"contract:{SECOND}": "3945.21",
        "TOTAL:USD": "16764.42",
    }
    assert september_lines(world, K09) == [("COST_AMORTIZATION", "177.37"), ("REVENUE", "2956.20")]
    assert september_lines(world, SECOND) == [("REVENUE", "3945.21")]
    layers, recognitions = monitor_inputs(world)
    assert layers == [layer(K02, "30246.58"), layer(K09, "33043.80"), layer(SECOND, "44054.79")]
    assert recognitions == [(K02, "9863.01"), (K09, "2956.20"), (SECOND, "3945.21")]
    assert versions_stated(world) == {K02: 1, K09: 1, SECOND: 1}
    assert history_keys(world) == [f"version:{name}:1:O1" for name in (K02, K09, SECOND)]

    computed_now(world, jobs[joint])
    assert liabilities(world) == {
        f"contract:{K02}:{AVM_US}": "30246.58",
        f"contract:{K09}:{AVM_US}": "32797.45",
        f"contract:{SECOND}:{AVM_US}": "44794.52",
        "TOTAL:USD": "107838.55",
    }
    assert september_revenue(world) == {
        f"contract:{K02}": "9863.01",
        f"contract:{K09}": "3202.55",
        f"contract:{SECOND}": "3205.48",
        "TOTAL:USD": "16271.04",
    }
    assert september_lines(world, K09) == [("COST_AMORTIZATION", "177.37"), ("REVENUE", "3202.55")]
    assert september_lines(world, SECOND) == [("REVENUE", "3205.48")]
    layers, recognitions = monitor_inputs(world)
    assert layers == [layer(K02, "30246.58"), layer(K09, "29591.97"), layer(SECOND, "48000.00")]
    assert recognitions == [(K02, "9863.01"), (K09, "3202.55"), (SECOND, "3205.48")]
    assert versions_stated(world) == {K02: 1, K09: 2, SECOND: 2}
    assert history_keys(world) == [
        f"version:{K02}:1:O1",
        f"version:{K09}:1:O1",
        f"version:{K09}:2:O1",
        f"version:{SECOND}:1:O1",
        f"version:{SECOND}:2:O1",
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class Halfway:
    """The LEAVE window after one of its two computations: RPT-02's liability of the first order
    and of the leaver with the report's total, and September's revenue of each."""

    first: str
    leaver: str
    total: str
    first_revenue: str
    leaver_revenue: str


# the leaver's own group is computed, the first order still stands in the combined group's version
LEAVER_COMPUTED: Final = Halfway("32797.45", "44054.79", "107098.82", "3202.55", "3945.21")
# the remaining group is computed without the leaver, which still stands in the version before
REMAINDER_COMPUTED: Final = Halfway("33043.80", "44794.52", "108084.90", "2956.20", "3205.48")


@pytest.mark.slow
@pytest.mark.parametrize(
    ("leaver_first", "halfway"),
    [(True, LEAVER_COMPUTED), (False, REMAINDER_COMPUTED)],
    ids=["the leaver's group first", "the remaining group first"],
)
def test_a_contract_that_leaves_is_read_once_while_the_groups_await_their_computations(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    leaver_first: bool,
    halfway: Halfway,
) -> None:
    """The second order leaves the combined group again (an approved LEAVE, reason
    DATA_CORRECTION) and returns to its own group; both computations are deferred and run in
    either order. Each contract is read once at every step, as last computed: both from the
    combined group's version until a job has run; then the one whose group is computed from its
    group's new version while the other still stands in the combined group's version before
    the leave; and both from their groups' new versions at the end. The remaining group's new
    version was computed without the leaver and is no version of it, although its record time
    lies before the leave. The history numbers the three versions of each order 1, 2, 3. RPT-02
    run between the two jobs and rerun at the end repeats itself pair for pair (S15-R-24a (d)).
    Before, by the group: the leaver's own group held a member again and its version from
    before the combination was read beside the combined group's — RPT-02 held
    ``contract:SF-ORD-10418:AVM-US`` twice (44,054.79 and 44,794.52; total 151,893.34)."""
    world = two_orders(app, keyring, clock, files)
    joint = combine(world)
    deferred(monkeypatch)
    leaver = str(world.contracts[SECOND].contract["id"])
    requested = post(
        world.app,
        f"{GROUPS}/{joint}/submit",
        world.maya,
        {"leave_contract_ids": [leaver], "reason_code": "DATA_CORRECTION", "comment": WRONG_ORDER},
    )
    assert requested.status_code == 200, requested.text
    approved = approve(world.app, requested.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    jobs = queued_computations(world)
    (own,) = [group_id for group_id in jobs if group_id != joint]
    order = (own, joint) if leaver_first else (joint, own)

    def stated() -> tuple[dict[str, str], list[tuple[str, str]], list[tuple[str, str]]]:
        found = liabilities(world)
        found.pop(f"contract:{K02}:{AVM_US}")
        return found, september_lines(world, K09), september_lines(world, SECOND)

    # nothing computed yet: both orders as the combined group last stated them
    assert stated() == (
        {
            f"contract:{K09}:{AVM_US}": "32797.45",
            f"contract:{SECOND}:{AVM_US}": "44794.52",
            "TOTAL:USD": "107838.55",
        },
        [("COST_AMORTIZATION", "177.37"), ("REVENUE", "3202.55")],
        [("REVENUE", "3205.48")],
    )
    layers, _ = monitor_inputs(world)
    assert layers == [layer(K02, "30246.58"), layer(K09, "29591.97"), layer(SECOND, "48000.00")]

    # one group is computed; the combined group's version before the leave still carries the
    # rows of both orders, and each is read from one version only
    computed_now(world, jobs[order[0]])
    assert stated() == (
        {
            f"contract:{K09}:{AVM_US}": halfway.first,
            f"contract:{SECOND}:{AVM_US}": halfway.leaver,
            "TOTAL:USD": halfway.total,
        },
        [("COST_AMORTIZATION", "177.37"), ("REVENUE", halfway.first_revenue)],
        [("REVENUE", halfway.leaver_revenue)],
    )
    layers, recognitions = monitor_inputs(world)
    assert layers == [
        layer(K02, "30246.58"),
        # Still-combined versions retain group FIFO: 36,000 - 3,202.55 - 3,205.48
        # in the first billing layer, with the second billing layer's 48,000 untouched.
        # Only the newly computed member returns to its standalone layer balance.
        layer(K09, "29591.97" if leaver_first else "33043.80"),
        layer(SECOND, "44054.79" if leaver_first else "48000.00"),
    ]
    assert recognitions == [
        (K02, "9863.01"),
        (K09, halfway.first_revenue),
        (SECOND, halfway.leaver_revenue),
    ]
    # measured before: the waterfall read the leaver's obligation from both versions
    assert waterfall_obligations(world) == [(K02, "O1"), (K09, "O1"), (SECOND, "O1")]
    in_window, window_rows = report_run(world, "contract_balances", AT_SEPTEMBER)

    # the other group is computed: each order alone again, at its booked price
    computed_now(world, jobs[order[1]])
    assert stated() == (
        {
            f"contract:{K09}:{AVM_US}": "33043.80",
            f"contract:{SECOND}:{AVM_US}": "44054.79",
            "TOTAL:USD": "107345.17",
        },
        [("COST_AMORTIZATION", "177.37"), ("REVENUE", "2956.20")],
        [("REVENUE", "3945.21")],
    )
    assert [
        (str(row["row_key"]), amount(row["allocated_amount"]))
        for row in history_rows(world, "contract_history")
        if row["contract_external_id"] in (K09, SECOND)
    ] == [
        (f"version:{K09}:1:O1", "108000.00"),
        (f"version:{K09}:2:O1", "117000.00"),
        (f"version:{K09}:3:O1", "108000.00"),
        (f"version:{SECOND}:1:O1", "48000.00"),
        (f"version:{SECOND}:2:O1", "39000.00"),
        (f"version:{SECOND}:3:O1", "48000.00"),
    ]
    assert versions_stated(world) == {K02: 1, K09: 3, SECOND: 3}
    # the run taken between the jobs, rerun now: its bound versions, each contract from its own
    again, again_rows = rerun(world, str(in_window["id"]))
    assert {str(row["row_key"]): amount(row[LIABILITY]) for row in again_rows} == {
        f"contract:{K02}:{AVM_US}": "30246.58",
        f"contract:{K09}:{AVM_US}": halfway.first,
        f"contract:{SECOND}:{AVM_US}": halfway.leaver,
        "TOTAL:USD": halfway.total,
    }
    assert again_rows == window_rows
    assert again["output"]["sha256"] == in_window["output"]["sha256"]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (RuntimeError("the computation gave way"), "FAILED"),
        (EngineError("SSP_KEY_NOT_FOUND", "No approved SSP for the key."), "QUARANTINED"),
    ],
    ids=["failed", "quarantined"],
)
def test_a_refused_computation_leaves_each_member_where_it_was_last_computed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: str,
) -> None:
    """The combined group's deferred computation is refused — a defect inside it (stored FAILED)
    or a stop of the engine (stored QUARANTINED): the job ends with exceptions (dev-guide
    DG-CMD-09), no version is written and the group keeps awaiting its computation. Each order is
    still read once, from its own group's version, by RPT-02, the schedule lines and the
    monitors, for as long as that lasts; the period's lock gate counts the group. Before: both
    orders were missing from RPT-02 from the approval on, and nothing brought them back."""
    world = two_orders(app, keyring, clock, files)
    deferred(monkeypatch)
    joint = combine(world)
    jobs = queued_computations(world)

    def gives_way(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(bundles, "build", gives_way)
    finished = worlds.run_now(world, jobs[joint])
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS", finished
    assert finished["result"]["counts"] == {
        "groups": 1,
        "succeeded": 0,
        "quarantined": int(status == "QUARANTINED"),
        "failed": int(status == "FAILED"),
    }
    assert [
        str(row["status"])
        for row in world.place.rows(
            select(contract_computation.c.status).where(
                contract_computation.c.combination_group_id == joint
            )
        )
    ] == [status]
    each_order_as_its_own_group_last_computed_it(world, joint)


@pytest.mark.slow
def test_a_computation_job_that_fails_leaves_each_member_where_it_was_last_computed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The combined group's deferred computation never comes about: the server cannot do it at
    that moment (SQLSTATE 53200, raised by the server in the computation's own session), which
    is no result of a computation — nothing is stored (05 RCP-20; item RES-53-COMPUTE-1) — and
    the last attempt the job's retry policy allows ends the job FAILED. The group holds both
    orders and has no version until somebody computes it again. Each order is still read once,
    from its own group's version, and the period's lock gate counts the group. Before: as in the
    deferred window, without an end — neither order in RPT-02."""
    world = two_orders(app, keyring, clock, files)
    deferred(monkeypatch)
    joint = combine(world)
    jobs = queued_computations(world)
    build = bundles.build

    def out_of_shared_memory(session: Session, *args: Any, **kwargs: Any) -> Any:
        session.execute(OUT_OF_SHARED_MEMORY)
        return build(session, *args, **kwargs)

    monkeypatch.setattr(bundles, "build", out_of_shared_memory)
    finished = last_attempt(world, jobs[joint])
    assert finished["state"] == "FAILED", finished
    assert not world.place.rows(
        select(contract_computation.c.id).where(
            contract_computation.c.combination_group_id == joint
        )
    )
    each_order_as_its_own_group_last_computed_it(world, joint)


# --- RPT-21: the version an allocation row names (item S-1) --------------------------------------


@pytest.mark.slow
def test_the_allocations_report_names_a_version_by_its_number_along_the_chain(
    combined: ReportWorld,
) -> None:
    """RPT-21 (item S-1 of lane F-RPS-REG, after supervisor ruling R-117 (a)): the row key ends in
    the number of the version the row is read from. ``version_no`` counts the versions of one
    group, so the combined group's first version was 1 for each order — the number the contract
    history gives the order's version in its OWN group (108,000.00 and 48,000.00), which this
    report does not show. The key carries the number along the contract's chain, the one RPT-09
    gives the same version; K-02, which never changed its group, keeps its number. Before:
    ``allocation:SF-ORD-10417:O1:1`` and ``allocation:SF-ORD-10418:O1:1`` for the allocations of
    117,000.00 and 39,000.00."""
    stated = [
        (str(row["row_key"]), amount(row["allocated_amount"]))
        for row in history_rows(combined, "allocations_by_ssp_version")
    ]
    assert stated == [
        (f"allocation:{K02}:O1:1", "240000.00"),
        (f"allocation:{K09}:O1:2", "117000.00"),
        (f"allocation:{SECOND}:O1:2", "39000.00"),
        ("TOTAL:USD", "396000.00"),
    ]
    history = {
        str(row["row_key"]): amount(row["allocated_amount"])
        for row in history_rows(combined, "contract_history")
    }
    # the contract history states the same versions under the same numbers
    assert history[f"version:{K09}:2:O1"] == "117000.00"
    assert history[f"version:{SECOND}:2:O1"] == "39000.00"
