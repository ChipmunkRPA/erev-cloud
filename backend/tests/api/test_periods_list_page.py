"""``GET /periods`` answers a page in a constant number of statements (04 §16.8 API-S-Period rev
1.199; dev-guide DG-LST-10; supervisor ruling of 2026-10-01, item PERF-PERIODS-LIST-1).

The list is read by every screen for its context. A row carried the twelve blocker counts, each
row's from a statement over 23 tables built and planned for that row alone, beside a read of the
row's scope and one of its close run: a page of 200 was 600 statements and seconds, and its
transaction ended holding a lock on a ledger partition for every row. No reader takes the counts
from the list. A row now carries its newest close run and its current lock, read for the whole
page in two statements, and ``blockers`` null; ``GET /periods/{id}``, the cockpit and the
commands' answers carry the counts as before.

DB-bound: the reference routes build the calendars and entities; the close world's own writers
lock the periods, the product reopens one, and two close runs are stored for one period.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import close_run
from erev_api.domain.close import gates
from erev_api.enums import CloseRunStatus
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert
from support.close_world import (
    CloseWorld,
    actor_with_role,
    close_world,
    periods_closed_before,
    reviewed_error_judgement,
    system_session,
)
from support.db import TestDatabase
from support.plans import sent
from support.principals import enrolled, member
from support.reference import PERIODS, approve, assign, calendar, entity, get, periods, post
from support.rows import close_run_values

# Tables only the blocker counts read (``gates.blocker_statement``): none is read for a page.
GATE_TABLES = (
    "erev.exception_item",
    "erev.contract_hold",
    "erev.judgement_record",
    "erev.approval_request",
    "erev.import_upload",
    "erev.sync_run",
    "erev.combination_group",
    "erev.journal_batch",
    "erev.reconciliation",
    "erev.manual_adjustment",
    "erev.subledger_line",
)
ENTITIES = ("AVM-US", "AVM-DE", "AVM-UK", "AVM-JP")
YEARS = tuple(range(2018, 2035))  # 204 periods an entity: more than a full page
REOPEN_REASON = "Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _page(app: FastAPI, actor: Any, **params: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The rows of one ``GET /periods`` and every statement the application sent for it."""
    with sent() as seen:
        listed = get(app, PERIODS, actor, params)
    assert listed.status_code == 200, listed.text
    return list(listed.json()["items"]), [statement for statement, _ in seen]


def test_dg_lst_10_a_page_of_periods_is_read_in_a_constant_number_of_statements(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """A page of 200 period states of one entity, a page of 200 over four entities and a page of
    three are each the same number of statements: the page, its close runs and its locks — three
    that read ``period_state`` — beside what every request reads for its session. Before: three
    statements more for EACH row, one of them over the gate tables."""
    someone = member(keyring, clock)
    for role in ("tenant_admin", "controller"):
        assign(someone, role)
    actor = enrolled(app, clock, someone)
    calendar_id = calendar(app, actor, years=YEARS)
    for code in ENTITIES:
        entity(app, actor, code=code, calendar_id=calendar_id)

    one, of_one = _page(app, actor, entity="AVM-DE", limit=200)
    four, of_four = _page(app, actor, limit=200)
    few, of_few = _page(app, actor, entity="AVM-DE", limit=3)
    assert (len(one), len(four), len(few)) == (200, 200, 3)
    assert {row["entity"]["code"] for row in one} == {"AVM-DE"}
    assert {row["entity"]["code"] for row in four} == set(ENTITIES)

    assert len(of_one) == len(of_four) == len(of_few)
    for statements in (of_one, of_four, of_few):
        reads = [statement for statement in statements if "erev.period_state" in statement]
        assert len(reads) == 3, reads
        assert sum("erev.close_run" in statement for statement in reads) == 1
        assert sum("erev.period_lock" in statement for statement in reads) == 1
        named = [table for table in GATE_TABLES if any(table in s for s in statements)]
        assert named == []
    # ... and no row of a page carries the counts
    assert {row["blockers"] for row in (*one, *four, *few)} == {None}


def test_api_c_11_the_list_takes_one_period_of_every_entity_in_scope(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """04 API-R-18 (rev 1.199; API-C-11): ``GET /periods?period=<key>&book=<book>`` answers the
    row of that period for every entity in scope — what SCREENS_B §5.5 binds for the close
    dashboard — and combines with ``entity``; the parameter takes the period's id as well, and a
    key or id no calendar holds matches no rows. Before: 422, "period is not a filter of
    periods"."""
    someone = member(keyring, clock)
    for role in ("tenant_admin", "controller"):
        assign(someone, role)
    actor = enrolled(app, clock, someone)
    calendar_id = calendar(app, actor, years=(2026, 2027))
    for code in ENTITIES:
        entity(app, actor, code=code, calendar_id=calendar_id)

    rows = periods(app, actor, period="FY2026-P09", book="ASC606")
    assert sorted((row["entity"]["code"], row["period"]["period_key"]) for row in rows) == [
        (code, "FY2026-P09") for code in sorted(ENTITIES)
    ]
    assert {row["blockers"] for row in rows} == {None}
    (one,) = periods(app, actor, period="FY2026-P09", entity="AVM-DE")
    assert (one["entity"]["code"], one["period"]["period_key"]) == ("AVM-DE", "FY2026-P09")
    by_id = periods(app, actor, period=one["period"]["id"])
    assert sorted(row["id"] for row in by_id) == sorted(row["id"] for row in rows)
    assert periods(app, actor, period="FY2031-P01") == []
    assert periods(app, actor, period="00000000-0000-4000-8000-000000000000") == []
    # ... and the cursor of a page belongs to its period like to any other filter
    first = get(app, PERIODS, actor, {"period": "FY2026-P09", "limit": 2})
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str)
    other = get(app, PERIODS, actor, {"period": "FY2026-P10", "limit": 2, "cursor": cursor})
    assert other.status_code == 422, other.text
    rest = get(app, PERIODS, actor, {"period": "FY2026-P09", "limit": 2, "cursor": cursor})
    assert rest.status_code == 200, rest.text
    walked = [row["id"] for row in (*first.json()["items"], *rest.json()["items"])]
    assert sorted(walked) == sorted(row["id"] for row in rows)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _close_runs(world: CloseWorld, clock: FrozenClock, state: dict[str, Any]) -> UUID:
    """Two close runs of the period, a failed one and a later one that succeeded; the later id."""
    earlier, later = (
        close_run_values(
            world.tenant_id,
            entity_id=world.entity_id,
            period_id=UUID(str(state["period"]["id"])),
            status=status.value,
            current_step_code=step,
            created_at=clock.now() + timedelta(minutes=minutes),
        )
        for status, step, minutes in (
            (CloseRunStatus.FAILED, "EXCEPTION_CHECK", 1),
            (CloseRunStatus.SUCCEEDED, None, 2),
        )
    )
    with system_session(world) as session:
        session.execute(insert(close_run), [earlier, later])
    return UUID(str(later["id"]))


def test_a_row_of_the_list_is_the_single_read_without_its_blockers(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Row for row, every member of the list's answer equals ``GET /periods/{id}`` — the newest
    close run and the current lock included — except ``blockers``, which the list answers null and
    the single read answers as before. The world: FY2026-P01 to P08 of AVM-US locked, P09 locked
    and reopened (its current lock is the ``REOPEN`` record), the fifteen periods after it future;
    P08 with two close runs, every other period with none."""
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before="FY2026-P10"
    )
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    by_key = {row["period"]["period_key"]: row for row in periods(world.app, world.maya)}
    september = by_key["FY2026-P09"]
    requested = post(
        world.app,
        f"{PERIODS}/{september['id']}/request-reopen",
        priya,
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": REOPEN_REASON,
        },
        if_match=f'"r{september["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    for approver in (marcus, elena):
        decided = approve(world.app, str(requested.json()["approval_request_id"]), approver)
        assert decided.status_code == 200, decided.text
    newest_run = _close_runs(world, clock, by_key["FY2026-P08"])

    listed = periods(world.app, world.maya, entity="AVM-US")
    assert len(listed) == 24  # FY2026 and FY2027 (``world_calendar``)
    for row in listed:
        single = get(world.app, f"{PERIODS}/{row['id']}", world.maya)
        assert single.status_code == 200, single.text
        shown = single.json()
        assert sorted(shown["blockers"]) == sorted(gates.BLOCKER_KEYS)
        assert row == {**shown, "blockers": None}, row["period"]["period_key"]

    # ... and the world is the one the docstring names
    by_key = {row["period"]["period_key"]: row for row in listed}
    assert [row["period"]["period_key"] for row in listed] == sorted(by_key)  # in period order
    assert [row["state"] for row in listed] == ["closed"] * 8 + ["reopened"] + ["future"] * 15
    kinds = [None if row["current_lock"] is None else row["current_lock"]["kind"] for row in listed]
    assert kinds == ["LOCK"] * 8 + ["REOPEN"] + [None] * 15
    assert by_key["FY2026-P09"]["current_lock"]["created_by"]["display_name"]
    runs = {key: row["close_run"] for key, row in by_key.items() if row["close_run"] is not None}
    assert runs == {
        "FY2026-P08": {"id": str(newest_run), "status": "SUCCEEDED", "current_step_code": None}
    }
