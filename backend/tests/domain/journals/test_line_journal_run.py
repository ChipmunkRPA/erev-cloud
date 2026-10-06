"""Item SUBLEDGER-LINE-JOURNAL-RUN-1 (register index 265; 04 API-S-SubledgerLine ``journal_run_id``,
rev 1.288; the supervisor's ruling of 2026-10-02): a subledger line names the journal run that
journalises it, on the three reads of the schema — ``GET /subledger-lines``,
``GET /contracts/{id}/subledger-lines`` and the drill of a journal line.

The member was documented as "the non-cancelled journal run whose seal range covers the line's
posting" and answered null for every line (``subledger.line_outs``), so the column "Journal run"
of a contract's Journals tab never showed its link. A range is not the whole answer either: a run
leaves the lines of a held contract out of its range, and a later run takes them over. The member
is answered by the one rule the completeness assertion reads (``completeness.summarized``).

World: the CLO-8 journal world with CHK-022's January postings of ``Contract 1`` (Mock Entity 1)
and a posting of another contract of that entity; default grain.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Engine, event
from support.db import TestDatabase
from support.factories import run_import_job
from support.reference import approve, get, patch, post
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    FEBRUARY,
    JANUARY,
    JOURNAL_RUNS,
    JournalWorld,
    _book_kept,
    calculated_run,
    journal_world,
    post_chk_022,
    post_pre_standard,
    requested_run,
)
from test_drill_record import GRAIN, HELD, _hold, _other, _posted, _release

API: Final = "/api/v1"
REASON: Final = "Recalculate the period."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> Iterator[JournalWorld]:
    built = journal_world(app, keyring, clock, files)
    post_chk_022(built)
    yield built


def _register(world: JournalWorld, **filters: Any) -> dict[str, str | None]:
    """Contract → the one run its January lines of Mock Entity 1 name on ``GET /subledger-lines``
    (every line of a contract names the same run in these worlds: asserted)."""
    listed = get(
        world.app,
        f"{API}/subledger-lines",
        world.legacy.maya,
        {"entity": ENTITY_1, "period": JANUARY, "limit": 200, **filters},
    )
    assert listed.status_code == 200, listed.text
    named: dict[str, set[str | None]] = {}
    for item in listed.json()["items"]:
        named.setdefault(item["contract_external_id"], set()).add(item["journal_run_id"])
    assert all(len(runs) == 1 for runs in named.values()), named
    return {contract: next(iter(runs)) for contract, runs in named.items()}


def _of_contract(world: JournalWorld, contract_key: str) -> set[str | None]:
    """The runs the contract's own lines name on ``GET /contracts/{id}/subledger-lines``."""
    listed = get(
        world.app,
        f"{API}/contracts/{world.contracts[contract_key].id}/subledger-lines",
        world.legacy.maya,
        {"limit": 200, "as_of": "2023-02-28"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"]
    return {item["journal_run_id"] for item in listed.json()["items"]}


def _drilled_runs(world: JournalWorld, lines: list[dict[str, Any]]) -> set[str | None]:
    """The runs the drilled lines of a run's journal lines name."""
    named: set[str | None] = set()
    for line in lines:
        drilled = get(world.app, line["links"]["drill"], world.legacy.maya, {"limit": 200})
        assert drilled.status_code == 200, drilled.text
        named |= {item["journal_run_id"] for item in drilled.json()["items"]}
    return named


def _cancelled(world: JournalWorld, run: dict[str, Any]) -> None:
    done = post(
        world.app, f"{JOURNAL_RUNS}/{run['id']}/cancel", world.legacy.maya, {"reason": REASON}
    )
    assert done.status_code == 200, done.text


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every SQL statement the process sends while the block runs."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


@pytest.mark.slow
def test_a_line_names_the_run_that_journalises_it(world: JournalWorld) -> None:
    """The life of the member on the three reads. A line in a run's range names that run. The
    lines of a held contract, which the run left out, name none — while the hold is open and
    after its release. Once the next run has taken them over they name that run, though their
    seal lies in the first run's range. After the cancel of the taking run they name none again;
    after the cancel of both, no line names a run; and the run calculated next is named by every
    line. Before the item every line answered null."""
    other = _other(world)
    _posted(world, "line-run-jan", other, "12.00")
    assert _register(world) == {HELD: None, other: None}  # no run yet

    _hold(world)
    first, first_lines = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    assert _register(world) == {HELD: None, other: first["id"]}
    assert _of_contract(world, other) == {first["id"]}
    assert _of_contract(world, HELD) == {None}
    assert _drilled_runs(world, first_lines) == {first["id"]}

    _release(world)
    assert _register(world) == {HELD: None, other: first["id"]}  # released, taken over by none

    taking, taking_lines = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    assert (taking["coverage"]["from_chain_seq"], taking["coverage"]["to_chain_seq"]) == (
        first["coverage"]["to_chain_seq"],
        first["coverage"]["to_chain_seq"],
    )  # an empty range: what it holds, it took over
    assert _register(world) == {HELD: taking["id"], other: first["id"]}
    assert _of_contract(world, HELD) == {taking["id"]}
    assert _drilled_runs(world, taking_lines) == {taking["id"]}
    assert _drilled_runs(world, first_lines) == {first["id"]}

    _cancelled(world, taking)
    assert _register(world) == {HELD: None, other: first["id"]}
    _cancelled(world, first)
    assert _register(world) == {HELD: None, other: None}

    again, again_lines = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    assert again["coverage"]["from_chain_seq"] == 0
    assert _register(world) == {HELD: again["id"], other: again["id"]}
    assert _of_contract(world, HELD) == {again["id"]} == _of_contract(world, other)
    assert _drilled_runs(world, again_lines) == {again["id"]}


@pytest.mark.slow
def test_a_legacy_line_names_the_delta_run_that_journalises_it(world: JournalWorld) -> None:
    """A line of the LEGACY book is journalised by a ``DELTA`` run alone, in that run's delta
    range (S14-R-23): under a ``GROSS`` run of the period it names none, and the primary book's
    lines name the ``GROSS`` run; after that run's cancel a ``DELTA`` run is named by the lines
    of both books."""
    post_pre_standard(world)
    gross, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    assert _register(world) == {HELD: gross["id"]}
    assert _register(world, book="LEGACY") == {HELD: None}

    _cancelled(world, gross)
    delta, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN, mode="DELTA")
    assert _register(world) == {HELD: delta["id"]}
    assert _register(world, book="LEGACY") == {HELD: delta["id"]}


def _delta_run_of(world: JournalWorld, book: str) -> dict[str, Any]:
    """A ``DELTA`` run of ``book`` for January of Mock Entity 1, calculated as the worker does."""
    job_id, run_id = requested_run(
        world,
        {
            "entity_code": ENTITY_1,
            "book": book,
            "period_key": JANUARY,
            "grain": GRAIN,
            "mode": "DELTA",
        },
    )
    run_import_job(world.legacy.imports, job_id)
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _keeps_ifrs15(world: JournalWorld) -> None:
    """Mock Entity 1 keeps IFRS15 from January with January open, as the world keeps the LEGACY
    book (``worlds._keep_legacy_book``): the book is enabled for the workspace and kept by
    Marcus, the Tenant Admin, and its period is opened by Maya."""
    maya, marcus = world.legacy.maya, world.legacy.marcus
    listed = get(world.app, f"{API}/books", marcus, {"limit": 50})
    assert listed.status_code == 200, listed.text
    found = next(item for item in listed.json()["items"] if item["code"] == "IFRS15")
    if not found["is_enabled"]:
        enabled = patch(
            world.app,
            f"{API}/books/IFRS15",
            marcus,
            {"is_enabled": True},
            if_match=f'"r{found["row_version"]}"',
        )
        assert enabled.status_code == 200, enabled.text
    _book_kept(
        world.app,
        maya,
        marcus,
        entity_code=ENTITY_1,
        entity_id=world.entities[ENTITY_1],
        book="IFRS15",
        keys=(JANUARY,),
        first_period_key=JANUARY,
    )


@pytest.mark.slow
def test_a_legacy_line_of_two_posting_books_names_the_primary_books_run(
    world: JournalWorld,
) -> None:
    """Mock Entity 1 keeps a second posting book, IFRS15, beside ASC606. The LEGACY book takes
    no run of its own: a ``DELTA`` run of each posting book journalises January's pre-standard
    lines in its delta range, so two runs journalise one line. The line names the primary
    book's run — the LEGACY book follows the primary book — though the second book's run was
    calculated first and was the one named until then; after the cancel of the primary book's
    run the second book's is named again."""
    post_pre_standard(world)
    _keeps_ifrs15(world)
    second = _delta_run_of(world, "IFRS15")
    assert (second["book"], second["mode"], second["state"]) == ("IFRS15", "DELTA", "draft")
    assert _register(world, book="LEGACY") == {HELD: second["id"]}
    assert _register(world) == {HELD: None}  # the primary book's lines: no run of their book

    primary = _delta_run_of(world, "ASC606")
    assert _register(world, book="LEGACY") == {HELD: primary["id"]}
    assert _register(world) == {HELD: primary["id"]}

    _cancelled(world, primary)
    assert _register(world, book="LEGACY") == {HELD: second["id"]}
    assert _register(world) == {HELD: None}


@pytest.mark.slow
def test_a_line_names_a_run_of_its_own_entity_and_period_whatever_the_runs_state(
    world: JournalWorld,
) -> None:
    """The runs that can journalise a line are those of the line's OWN entity and period that
    are not cancelled, in whatever state they stand. One run of Mock Entity 1 for January is
    calculated after every posting here was sealed, so its range holds the seals of February's
    lines and of Mock Entity 2's lines too: on a page that mixes the periods, and on one that
    mixes the entities, only January's lines of Mock Entity 1 name it. Approved, the run is
    named as it was while a draft: a run that left ``draft`` journalises what it summarized."""
    assert world.contracts["Contract 2"].entity_id == world.entities[ENTITY_2]
    _posted(world, "line-run-key-feb", HELD, "30.00", period_key=FEBRUARY)
    run, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    maya = world.legacy.maya

    # two periods on one page: the contract's own lines
    own = get(
        world.app,
        f"{API}/contracts/{world.contracts[HELD].id}/subledger-lines",
        maya,
        {"limit": 200, "as_of": "2023-02-28"},
    )
    assert own.status_code == 200, own.text
    assert {(item["period_key"], item["journal_run_id"]) for item in own.json()["items"]} == {
        (JANUARY, run["id"]),
        (FEBRUARY, None),
    }

    def january() -> set[tuple[str, str | None]]:
        """(entity, run) of January's lines on the register, no entity asked for."""
        listed = get(world.app, f"{API}/subledger-lines", maya, {"period": JANUARY, "limit": 200})
        assert listed.status_code == 200, listed.text
        return {(item["entity"]["code"], item["journal_run_id"]) for item in listed.json()["items"]}

    # two entities on one page
    assert january() == {(ENTITY_1, run["id"]), (ENTITY_2, None)}

    # the run approved: named as before
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    approved = approve(world.app, request_id, world.legacy.priya)
    assert approved.status_code == 200, approved.text
    shown = get(world.app, f"{JOURNAL_RUNS}/{run['id']}", maya)
    assert shown.status_code == 200 and shown.json()["state"] == "approved", shown.text
    assert january() == {(ENTITY_1, run["id"]), (ENTITY_2, None)}


@pytest.mark.slow
def test_the_member_costs_the_same_for_one_line_and_for_a_page(
    world: JournalWorld, clock: FrozenClock
) -> None:
    """The member is answered from three statements a page — the seals of the page's postings,
    the runs of its entities and periods, and those runs' CALCULATE events — whatever the number
    of lines, and the page's own statement is not touched: a read of one line and a read of the
    period's eight send as many statements. A period without a run sends one fewer: there is no
    event to read. The events of runs calculated at two instants are still one statement: each
    is asked at the instant its run was created at, and found there."""
    other = _other(world)
    _posted(world, "line-run-cost", other, "12.00")
    maya = world.legacy.maya
    filters = {"entity": ENTITY_1, "period": JANUARY}

    def read(limit: int) -> tuple[list[dict[str, Any]], list[str]]:
        with _statements() as sent:
            listed = get(world.app, f"{API}/subledger-lines", maya, {**filters, "limit": limit})
        assert listed.status_code == 200, listed.text
        return listed.json()["items"], list(sent)

    _, without_a_run = read(200)
    run, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    one, for_one = read(1)
    page, for_page = read(200)
    assert (len(one), len(page)) == (1, 8)
    assert {item["journal_run_id"] for item in page} == {run["id"]}
    assert len(for_one) == len(for_page) == len(without_a_run) + 1

    def member(sent: list[str]) -> list[str]:
        """The statements of the member's read, by the table each asks."""
        tables = ("subledger_posting_seal", "journal_run", "audit_event")
        return [
            table
            for statement in sent
            for table in tables
            if f"FROM erev.{table}" in statement and "subledger_line" not in statement
        ]

    assert member(for_page) == ["subledger_posting_seal", "journal_run", "audit_event"]
    assert member(for_one) == member(for_page)
    assert member(without_a_run) == ["subledger_posting_seal", "journal_run"]

    # a second run, of February, calculated a second later: a page of both periods names each
    # line's run and still reads the events once — both instants are in the one statement
    _posted(world, "line-run-cost-feb", other, "7.00", period_key=FEBRUARY)
    clock.advance(timedelta(seconds=1))
    later, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN, period_key=FEBRUARY)
    assert later["created_at"] != run["created_at"]
    with _statements() as sent:
        listed = get(world.app, f"{API}/subledger-lines", maya, {"entity": ENTITY_1, "limit": 200})
    assert listed.status_code == 200, listed.text
    assert {(item["period_key"], item["journal_run_id"]) for item in listed.json()["items"]} == {
        (JANUARY, run["id"]),
        (FEBRUARY, later["id"]),
    }
    assert member(list(sent)) == ["subledger_posting_seal", "journal_run", "audit_event"]
