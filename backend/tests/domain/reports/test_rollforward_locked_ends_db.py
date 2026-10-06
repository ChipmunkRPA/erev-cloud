"""A period end that is locked at the run's cutoff is the lock's (ENGINE_SPEC_B S15-R-20 rev
1.168; 04 §16.9 rev 1.313; item RPT-ROLLFWD-LOCKED-CLOSING-1, register index 297; the
supervisor's rulings of 2026-10-02; ruling R-72 (b)). Through the product, on the database.

Found by lane WEB-QA on the journey of the PRD: the contract balance roll-forward of AVM-US for
eight locked months, run after a contract was activated in the close of the ninth, failed its own
tie-out by the contract's schedule in those months — both ends were the balances of the contract
versions known at the run, the movements the lines by posting period.

The world here: K-01 (``SF-ORD-10001``, invoiced 120,000.00 on 1 January 2026), January and
February 2026 locked through the product, then a second contract of AVM-US with inception
1 January, activated afterwards and never invoiced: its revenue of January and February,
10,191.78 + 9,205.48 = 19,397.26, is posted in March with those months as its origin.

Measured on the code before the rule (the fail-first of the first two tests):
- January to February: ``TO_ROLLFORWARD_BALANCES`` FAIL, expected 120,193.97 against 100,796.71,
  "Other" 19,397.26 in the contract asset column;
- March alone: FAIL, expected 120,295.89 against 139,693.15 — the contract in the opening and
  again in March's lines.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract as contract_table
from erev_api.db.tables import legal_entity, lock_snapshot, period, period_lock
from erev_api.db.tables import report_run as report_run_table
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import factories, worlds
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.reference import assign, get, post
from support.worlds import AVM_US, K01, REPORT_RUN_ID_HEADER, REPORT_RUNS, ReportWorld, report_run

ROLLFORWARD: Final = "contract_balance_rollforward"
BALANCES: Final = "contract_balances"
LATE: Final = "SF-ORD-LATE-1"
JANUARY, FEBRUARY, MARCH = "FY2026-P01", "FY2026-P02", "FY2026-P03"
LIABILITY, ASSET, UNBILLED = "contract_liability", "contract_asset", "unbilled_receivable"
ZERO: Final = Decimal(0)
# Section 2 of the roll-forward: the path of one contract's detail balance
BY_CONTRACT: Final = (
    "opening",
    "billings",
    "revenue_from_opening",
    "revenue_from_period_billings",
    "reclassifications",
    "fx_remeasurement",
    "business_combinations",
    "other",
    "closing",
)
FOOTS: Final = {"TO_ROLLFORWARD_BALANCES": "PASS", "TO_BALANCES_EQ_ROLLFORWARD": "PASS"}
LOCKED_CLOSING: Final = Decimal("100796.71")  # K-01's contract liability at 28 February 2026
LATE_TWO_MONTHS: Final = Decimal("19397.26")  # the late contract's January and February
LATE_THREE_MONTHS: Final = Decimal("29589.04")  # ... and March: 120,000.00 × 90 / 365


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def ranged(first: str, last: str, **more: Any) -> dict[str, Any]:
    return {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_period_key": first,
        "to_period_key": last,
        **more,
    }


def at(period_key: str, **more: Any) -> dict[str, Any]:
    return {"entity_codes": [AVM_US], "book": "ASC606", "period_key": period_key, **more}


def amount(cell: Any) -> Decimal:
    """A money cell of a live run (API-S-Money) or of an as-locked one (the frozen text)."""
    if cell in (None, ""):
        return ZERO
    return Decimal(str(cell["amount"] if isinstance(cell, Mapping) else cell))


def ties(run: Mapping[str, Any]) -> dict[str, str]:
    return {
        item["code"]: item["result"]
        for item in run["tie_out_results"]
        if item["result"] != "NOT_APPLICABLE"
    }


def lines(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Decimal]]:
    """Section 1 of the roll-forward: per line code the three balances."""
    return {
        str(row["line_code"]): {
            name: amount(row.get(name)) for name in (LIABILITY, ASSET, UNBILLED)
        }
        for row in rows
        if row.get("line_code")
    }


def stated(liability: Decimal = ZERO, asset: Decimal = ZERO) -> dict[str, Decimal]:
    return {LIABILITY: liability, ASSET: asset, UNBILLED: ZERO}


def contracts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["contract_external_id"]): row for row in rows if row.get("contract_external_id")
    }


def world_with(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, *locked: str
) -> ReportWorld:
    """K-01 through 1 January 2026 with the periods ``locked`` locked through the product."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: journal runs are hers to approve
    world = worlds.on_record_clock(world, clock)
    for period_key in locked:
        _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=period_key)
    return world


def late_contract(world: ReportWorld) -> None:
    """A second contract of AVM-US with inception 1 January 2026, booked and activated now: the
    platform line of K-01 alone, 120,000.00 over 2026, never invoiced."""
    customer = UUID(str(world.contracts[K01].contract["customer_id"]))
    body = worlds.k01_body(customer)
    booked = factories.booked_contract(
        world.place, {**body, "external_id": LATE, "lines": [body["lines"][0]]}, activate=False
    )
    factories.activated_contract(world.place, booked)


def period_id(world: ReportWorld, period_key: str) -> UUID:
    found = worlds.period_state(world, AVM_US, period_key)
    return UUID(str(found["period"]["id"]))


def lock_of(world: ReportWorld, period_key: str) -> dict[str, Any]:
    """The ``LOCK`` record the product wrote for the period, with its cutoff."""
    rows = world.place.rows(
        select(period_lock.c.id, period_lock.c.cutoff_known_at)
        .select_from(period_lock.join(period, period.c.id == period_lock.c.period_id))
        .where(
            period_lock.c.kind == "LOCK",
            period_lock.c.entity_id == world.entity_id,
            period_lock.c.snapshot_manifest_sha256.is_not(None),
            period.c.period_key == period_key,
        )
    )
    assert len(rows) == 1, rows
    return dict(rows[0])


def recorded(world: ReportWorld, run: Mapping[str, Any]) -> dict[str, Any]:
    """What the run recorded of the period ends it asked (S15-R-24, evidence ``locked_ends``)."""
    stored = world.place.rows(
        select(report_run_table.c.source_binding).where(report_run_table.c.id == UUID(run["id"]))
    )
    return dict(dict(stored[0]["source_binding"]["evidence"])["locked_ends"])


def end_key(world: ReportWorld, period_key: str) -> str:
    return f"{world.entity_id}|{period_id(world, period_key)}"


def rerun(
    world: ReportWorld, run: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``POST /report-runs/{id}/rerun``, its job run as the worker does, the run and its rows."""
    again = post(world.app, f"{REPORT_RUNS}/{run['id']}/rerun", world.maya, {})
    assert again.status_code == 202, again.text
    finished = worlds.run_now(world, UUID(str(again.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    run_id = again.headers[REPORT_RUN_ID_HEADER]
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    listed = get(world.app, f"{REPORT_RUNS}/{run_id}/data", world.maya, {"limit": "200"})
    assert (shown.status_code, listed.status_code) == (200, 200), (shown.text, listed.text)
    return dict(shown.json()), list(listed.json()["items"])


@pytest.mark.slow
def test_locked_months_foot_after_a_contract_is_activated_late(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The roll-forward of the two locked months states what their locks state, whatever was
    recorded since: it foots, its closing is February's lock's, and the late contract is no row
    of it.

    Fail-first: ``TO_ROLLFORWARD_BALANCES`` FAIL — the closing held the late contract by its
    schedule, 19,397.26 of contract asset under "Other"."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    before, _ = report_run(world, ROLLFORWARD, ranged(JANUARY, FEBRUARY))
    assert ties(before) == FOOTS
    assert before["control_totals"]["closing_contract_liability"] == {"USD": f"{LOCKED_CLOSING}"}

    late_contract(world)
    run, rows = report_run(world, ROLLFORWARD, ranged(JANUARY, FEBRUARY))
    assert ties(run) == FOOTS
    found = lines(rows)
    assert found["OTHER"] == stated()
    assert found["CLOSING"] == stated(liability=LOCKED_CLOSING)
    by_contract = contracts(rows)
    assert set(by_contract) == {K01, LATE}  # a range from the first period lists every contract
    assert all(amount(by_contract[LATE].get(name)) == 0 for name in BY_CONTRACT)

    february = lock_of(world, FEBRUARY)
    _, frozen = report_run(
        world, ROLLFORWARD, ranged(FEBRUARY, FEBRUARY, period_lock_id=str(february["id"]))
    )
    assert lines(frozen)["CLOSING"] == found["CLOSING"]


@pytest.mark.slow
def test_the_month_after_the_locks_states_the_late_contract_as_its_movement(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """March opens at February's lock, and the late contract's revenue of three months — posted
    in March, two of them with an earlier origin — is March's activity: revenue in excess of
    billing, on the contract asset.

    Fail-first: ``TO_ROLLFORWARD_BALANCES`` FAIL — the opening held the contract already and
    March's lines counted it again, 19,397.26 the other way under "Other"."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    late_contract(world)
    run, rows = report_run(world, ROLLFORWARD, ranged(MARCH, MARCH))
    assert ties(run) == FOOTS
    found = lines(rows)
    assert found["OPENING"] == stated(liability=LOCKED_CLOSING)
    assert found["OTHER"] == stated()
    assert found["REVENUE_FROM_PERIOD_BILLINGS"][ASSET] == LATE_THREE_MONTHS
    assert found["CLOSING"][ASSET] == LATE_THREE_MONTHS
    k01_march = -found["REVENUE_FROM_OPENING"][LIABILITY]
    assert k01_march > 0
    assert found["CLOSING"][LIABILITY] == LOCKED_CLOSING - k01_march


@pytest.mark.slow
def test_contract_balances_at_a_locked_end_are_the_locks_rows(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """RPT-02 of a locked period end shows the lock's rows in a current run too — a change a
    person sees: before, the late contract was a row of February with 19,397.26 of contract
    asset. It is a row of March, the first period end that is not locked."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    late_contract(world)
    february = lock_of(world, FEBRUARY)
    run, rows = report_run(world, BALANCES, at(FEBRUARY))
    _, frozen = report_run(world, BALANCES, at(FEBRUARY, period_lock_id=str(february["id"])))
    assert ties(run) == {"TO_BALANCES_EQ_ROLLFORWARD": "PASS"}
    current, locked = contracts(rows), contracts(frozen)
    assert set(current) == set(locked) == {K01}
    measures = [name for name in locked[K01] if name.startswith(("contract_", "unbilled_"))]
    assert {LIABILITY, ASSET, UNBILLED} <= set(measures) - {"contract_external_id"}
    for name in set(measures) - {"contract_external_id"}:
        assert amount(current[K01].get(name)) == amount(locked[K01].get(name)), name
    assert amount(current[K01][LIABILITY]) == LOCKED_CLOSING

    march, rows = report_run(world, BALANCES, at(MARCH))
    assert ties(march) == {"TO_BALANCES_EQ_ROLLFORWARD": "PASS"}
    assert amount(contracts(rows)[LATE][ASSET]) == LATE_THREE_MONTHS


@pytest.mark.slow
def test_a_rerun_reads_the_locks_the_run_recorded(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """S15-R-24: the run records the locks it read — each with its cutoff and its two files —,
    and its rerun reads those locks whatever was reopened since, while a new run of the
    reopened period reads the versions, late contract and all."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    late_contract(world)
    run, _ = report_run(world, ROLLFORWARD, ranged(JANUARY, FEBRUARY))

    def read(period_key: str) -> dict[str, str]:
        lock = lock_of(world, period_key)
        hashes = {
            str(row["snapshot_kind"]): str(row["file_sha256"])
            for row in world.place.rows(
                select(lock_snapshot.c.snapshot_kind, lock_snapshot.c.file_sha256).where(
                    lock_snapshot.c.period_lock_id == lock["id"]
                )
            )
        }
        return {
            "lock_id": str(lock["id"]),
            "frozen_at": lock["cutoff_known_at"].isoformat(),
            "balances_sha256": hashes["CONTRACT_BALANCES"],
            "rollforward_sha256": hashes["CONTRACT_BALANCE_ROLLFORWARD"],
        }

    # February's end is the closing; January's is asked for the documents of the path
    january = read(JANUARY)
    assert recorded(world, run) == {
        end_key(world, JANUARY): january,
        end_key(world, FEBRUARY): read(FEBRUARY),
    }

    world = worlds.period_reopened(
        world, clock, entity_code=AVM_US, period_key=FEBRUARY, comment="A late contract"
    )
    again, rows = rerun(world, run)
    assert ties(again) == FOOTS
    assert lines(rows)["CLOSING"] == stated(liability=LOCKED_CLOSING)

    fresh, rows = report_run(world, ROLLFORWARD, ranged(JANUARY, FEBRUARY))
    assert recorded(world, fresh) == {
        end_key(world, JANUARY): january,
        end_key(world, FEBRUARY): None,
    }
    assert ties(fresh)["TO_ROLLFORWARD_BALANCES"] == "FAIL"  # a reopened period: the versions
    assert lines(rows)["OTHER"] == stated(asset=LATE_TWO_MONTHS)


@pytest.mark.slow
def test_the_record_of_the_period_decides_what_is_read(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Which lock is read. Here February alone is locked through the product; January is closed
    as the shared fixture closes an earlier period — a ``LOCK`` record that names no manifest
    and froze nothing (``support.close_world.periods_closed_before``), the record the product
    never writes.

    - That record refuses nothing: February's freeze, which opens its roll-forward at January,
      went through, and a run reads January's end from the versions.
    - February's end is its lock's; under a permanent lock it is still that ``LOCK``.
    - A run as of an instant before the lock's cutoff reads the versions."""
    world = world_with(app, keyring, clock, files, FEBRUARY)
    february = lock_of(world, FEBRUARY)
    late_contract(world)
    january_end, february_end = end_key(world, JANUARY), end_key(world, FEBRUARY)
    read = {"lock_id": str(february["id"])}

    run, rows = report_run(world, ROLLFORWARD, ranged(FEBRUARY, FEBRUARY))
    ends = recorded(world, run)
    assert ends[january_end] is None  # the fixture's record froze nothing: the versions
    assert {key: ends[february_end][key] for key in read} == read
    assert lines(rows)["CLOSING"] == stated(liability=LOCKED_CLOSING)

    periods_closed_before(
        world.place,
        world.app,
        world.maya,
        entity_id=world.entity_id,
        before=MARCH,
        permanently=True,
    )
    assert worlds.period_state(world, AVM_US, FEBRUARY)["state"] == "permanently_locked"
    run, rows = report_run(world, ROLLFORWARD, ranged(FEBRUARY, FEBRUARY))
    ends = recorded(world, run)
    assert ends[january_end] is None
    assert {key: ends[february_end][key] for key in read} == read
    assert lines(rows)["CLOSING"] == stated(liability=LOCKED_CLOSING)

    # an instant the server has seen (a run is refused a ``known_at`` later than now, and the
    # application clock of this world runs ahead of the server's) that lies before the cutoff
    earlier = world.place.scalar(select(func.now())) - timedelta(hours=1)
    assert earlier < february["cutoff_known_at"]
    run, _ = report_run(
        world, ROLLFORWARD, ranged(FEBRUARY, FEBRUARY, known_at=earlier.isoformat())
    )
    assert recorded(world, run) == {january_end: None, february_end: None}


# --- a billing document recorded after the lock of the period it is dated in ----------------------

FROM_OPENING: Final = "revenue_from_opening_liability"
AVM_DE: Final = "AVM-DE"
AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
K07_UNBILLED: Final = Decimal("89285.71")  # K-07 delivered and not invoiced, at 31 August 2026
K07_ADVANCE: Final = Decimal("10714.29")  # INV-DE-4390, 100,000.00, less what was delivered
LATE_INVOICE: Final = Decimal("60000.00")


def after_the_cutoff(world: ReportWorld, cutoff: datetime) -> None:
    """Waits until the server's clock has passed ``cutoff``. An event is stamped by the server
    (04 DB-08) and a lock's cutoff is the later of the application's instant and the server's,
    and the frozen clock of these worlds runs ahead (``on_record_clock``, the TOTP steps): an
    event recorded straight after a lock would carry an instant before the lock's cutoff, which
    no clock of a deployment gives it."""
    for _ in range(240):
        if world.place.scalar(select(func.clock_timestamp())) > cutoff:
            return
        time.sleep(0.5)
    raise AssertionError(f"the server's clock did not pass {cutoff} in two minutes")


def appended(world: ReportWorld, external_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    """``POST /contracts/{id}/events``: one event, appended and computed by the command."""
    contract_id = world.place.scalar(
        select(contract_table.c.id).where(contract_table.c.external_id == external_id)
    )
    return worlds._appended_through_api(world.place, UUID(str(contract_id)), event)


@pytest.mark.slow
def test_a_late_invoice_is_the_billing_of_the_month_it_was_recorded_in(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD J-04: K-07 of AVM-DE delivered and not invoiced, August 2026 locked; the invoice
    INV-DE-4390 of 100,000.00 dated 31 August arrives afterwards and the next command computes
    it. The entity bills in its ERP, so the invoice posts no line: it is a document of the path.

    August's lock does not hold it, so August shows no billing and closes at its lock; it is
    the billing of September, the first period whose end holds it — as a line posted with an
    earlier origin would be.

    Fail-first, on the rule without its document side: August FAIL, expected 89,285.71 against
    10,714.29 — the lock's closing with the billing still set into August by its date."""
    world = worlds.k07_august_locked(app, keyring, clock, files)
    locks = world.report.place.rows(
        select(period_lock.c.cutoff_known_at)
        .select_from(
            period_lock.join(period, period.c.id == period_lock.c.period_id).join(
                legal_entity, legal_entity.c.id == period_lock.c.entity_id
            )
        )
        .where(
            legal_entity.c.code == AVM_DE,
            period.c.period_key == AUGUST,
            period_lock.c.snapshot_manifest_sha256.is_not(None),
        )
    )
    assert len(locks) == 1, locks
    after_the_cutoff(world.report, locks[0]["cutoff_known_at"])
    world = worlds.k07_late_invoice(world, clock)
    report = world.report
    noted = appended(
        report,
        worlds.K07,
        {
            "event_type": "MEMO_UPDATED",
            "effective_date": "2026-09-10",
            "payload": {"memo_1": "Invoice INV-DE-4390 received"},
        },
    )
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]

    def of(period_key: str) -> dict[str, Any]:
        return {**ranged(period_key, period_key), "entity_codes": [AVM_DE]}

    run, rows = report_run(report, ROLLFORWARD, of(AUGUST))
    assert ties(run) == FOOTS
    found = lines(rows)
    assert found["BILLINGS"] == stated()
    assert found["CLOSING"] == stated(asset=K07_UNBILLED)

    run, rows = report_run(report, ROLLFORWARD, of(SEPTEMBER))
    assert ties(run) == FOOTS
    found = lines(rows)
    assert found["OPENING"] == stated(asset=K07_UNBILLED)
    assert found["BILLINGS"] == stated(liability=K07_ADVANCE, asset=-K07_UNBILLED)
    assert found["OTHER"] == stated()
    assert found["CLOSING"] == stated(liability=K07_ADVANCE)


@pytest.mark.slow
def test_the_opening_liability_report_opens_where_the_roll_forward_opens(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The two reports of one disclosure state one opening. Here the late contract also carries
    an invoice of 60,000.00 dated 15 January and recorded in March: by the versions it holds
    40,602.74 of contract liability at 28 February.

    March opens at February's lock in both: 100,796.71, K-01's alone, with K-01's revenue of
    March as the revenue from the opening; the late invoice is March's billing and the late
    contract's revenue is revenue from the billings of the period.

    Fail-first: the opening-liability report read the versions — opening 141,399.45 and
    39,678.90 from the opening against the roll-forward's 100,796.71 and 10,089.86."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    late_contract(world)
    after_the_cutoff(world, lock_of(world, FEBRUARY)["cutoff_known_at"])
    appended(
        world,
        LATE,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-01-15",
            "payload": {
                "invoice_number": "INV-US-LATE-1",
                "line_external_id": "INV-US-LATE-1-1",
                "obligation_key": "O1",
                "amount": {"amount": f"{LATE_INVOICE}", "currency": "USD"},
                "issue_date": "2026-01-15",
            },
        },
    )

    run, rows = report_run(world, ROLLFORWARD, ranged(JANUARY, FEBRUARY))
    assert ties(run) == FOOTS
    assert lines(rows)["CLOSING"] == stated(liability=LOCKED_CLOSING)

    run, rows = report_run(world, ROLLFORWARD, ranged(MARCH, MARCH))
    assert ties(run) == FOOTS
    found = lines(rows)
    assert found["OPENING"] == stated(liability=LOCKED_CLOSING)
    # the invoice is March's billing: it keeps its date of 15 January in the order of the path,
    # so it settles what revenue dated before it had put on the contract asset and the rest
    # opens a liability — 60,000.00 in all
    assert found["BILLINGS"][LIABILITY] - found["BILLINGS"][ASSET] == LATE_INVOICE
    assert found["OTHER"] == stated()
    k01_march = -found["REVENUE_FROM_OPENING"][LIABILITY]
    assert found["CLOSING"] == stated(
        liability=LOCKED_CLOSING - k01_march + LATE_INVOICE - LATE_THREE_MONTHS
    )

    run, rows = report_run(world, FROM_OPENING, ranged(MARCH, MARCH))
    assert run["control_totals"]["revenue_from_opening_total"] == {"USD": f"{k01_march}"}
    by_contract = contracts(rows)
    assert set(by_contract) == {K01}  # the late contract is not in the lock's opening
    assert amount(by_contract[K01]["opening_contract_liability"]) == LOCKED_CLOSING
    assert amount(by_contract[K01]["revenue_from_opening"]) == k01_march


@pytest.mark.slow
def test_the_freeze_of_the_next_period_opens_at_the_lock_before_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The datasets a lock freezes are built by the same builders
    (``reports.snapshots._wrapped``), so the freeze takes the rule: March, locked after the
    late contract was activated, freezes a roll-forward that opens at February's frozen closing
    and carries the late contract's revenue as March's movement — "Other" 0.00.

    Fail-first, as lane WEB-QA measured on the journey of the PRD (September's lock, 84,800.00):
    the frozen roll-forward opened above the closing frozen before it — here by 19,397.26 of
    contract asset — and carried that amount under "Other". A dataset frozen so is not
    rewritten; the period is reopened and locked again to freeze it anew."""
    world = world_with(app, keyring, clock, files, JANUARY, FEBRUARY)
    late_contract(world)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=MARCH)

    def frozen(period_key: str) -> dict[str, dict[str, Decimal]]:
        lock = lock_of(world, period_key)
        _, rows = report_run(
            world, ROLLFORWARD, ranged(period_key, period_key, period_lock_id=str(lock["id"]))
        )
        return lines(rows)

    march = frozen(MARCH)
    assert march["OPENING"] == frozen(FEBRUARY)["CLOSING"] == stated(liability=LOCKED_CLOSING)
    assert march["OTHER"] == stated()
    assert march["REVENUE_FROM_PERIOD_BILLINGS"][ASSET] == LATE_THREE_MONTHS
    assert march["CLOSING"][ASSET] == LATE_THREE_MONTHS
