"""Item JRN-EMPTY-RUN-1 (the supervisor's ruling of 2026-10-01 on this lane's measurement; 04
§16.7 API-S-JournalRunCreate and ``submit`` rev 1.248; PRD SM-08 and ERR-96 rev 1.174; BUILD_SPEC
CLO-8, CLO-11): a journal run that would summarize nothing.

Measured before the item: ``POST /journal-runs`` for an entity, book and period that a run already
covered answered 202 and its job made a second ``draft`` run — no line, no batch, coverage
``(n, n]``. While it stood the run before it could not be cancelled ("Journal run JR-000002 was
calculated after this run …"); it was submitted, approved and "exported" over no message, and
stayed ``approved``. A period without activity locked on its empty first run.

Two rules. Where a run of the period that is not cancelled stands, no further run is made without
a line: the command answers 409 by the run's number (PRD ERR-96) and its job asks again under the
coverage lock. Where the period has no such run the run is made although it has no line — the
lock gates need a run — and it is the period's run as it stands: it is not submitted, and the
period locks on it.

The refusal says that a new run would hold no line; it does not say that the period is
journalised. The last two witnesses are the cases in which it is met and the period is not: the
postings beyond the run are under a journal-export hold, and a run left postings out under such a
hold that is still open. Each ends with the operator's way: the release, after which the next run
holds the postings (in the second case it takes them over, item JRN-HELD-AFTER-EXPORT-1).

Worlds: February 2023 of Mock Entity 1 with two revenue entries (that of ``test_chunking``) for
a run that has lines, and the close world's September 2026 of AVM-US, which holds no posting, for
the empty first run, the real lock decision and the two postings under a hold.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract_event,
    contract_hold,
    exception_item,
    gl_account,
    job,
    journal_run,
)
from erev_api.domain.journals import summarise
from erev_api.enums import ChecklistStatus, JobKind, PeriodState
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.problems import TYPE_BASE, Problem
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session
from support.close_world import (
    CloseWorld,
    SealedActivity,
    close_world,
    sealed_activity,
    system_session,
)
from support.db import TestDatabase
from support.factories import run_import_job
from support.reference import approve, get, periods, post, slug
from support.rows import contract_hold_values, gl_account_values
from support.worlds import (
    ENTITY_1,
    FEBRUARY,
    JOURNAL_RUNS,
    RUN_ID_HEADER,
    JournalWorld,
    journal_world,
    post_lines,
)
from test_chunking import DEFAULT_GRAIN, _calculated, _pair
from test_closed_period_guard import KEY as SEPTEMBER
from test_closed_period_guard import _calculated as _run_of_september
from test_closed_period_guard import _pending_lock, _soft_close
from test_closed_period_guard import _runs as _runs_of_september
from test_closed_period_guard import _state as _september
from test_completeness import PERIOD_END, _completeness, _release_hold

BOOK: Final = "ASC606"
RULE: Final = "RUN_NOTHING_PENDING"
TRANSITION: Final = f"{TYPE_BASE}invalid-transition"
NOTHING_PENDING: Final = (
    "Journal run {run} is the latest run of {period} for {entity} in book ASC606, and there is "
    "nothing for a new run to summarize."
)
NO_LINES: Final = "Journal run {run} has no journal lines: there is nothing to approve."
REASON: Final = "The period is calculated again."
TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> JournalWorld:
    """February 2023 of Mock Entity 1 with one revenue entry for each of two contracts."""
    built = journal_world(app, keyring, clock, files)
    first, second = _pair(built)
    for key, contract_key, revenue, amount in (
        ("empty-run-contract-1", first, "5001", "100.00"),
        ("empty-run-contract-2", second, "5002", "50.00"),
    ):
        _revenue(built, key, contract_key, revenue, amount)
    return built


@pytest.fixture
def close(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


# --- helpers --------------------------------------------------------------------------------------


def _revenue(world: JournalWorld, key: str, contract_key: str, account: str, amount: str) -> int:
    """One sealed revenue entry of February for the contract; the posting's chain sequence."""
    return post_lines(
        world,
        key=key,
        contract_key=contract_key,
        period_key=FEBRUARY,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", amount, "POB #1"),
                    ("REVENUE", account, f"-{amount}", "POB #1"),
                ],
            )
        ],
    )


def _request(world: JournalWorld) -> Any:
    """``POST /journal-runs`` for February of Mock Entity 1, as Maya."""
    body = {"entity_code": ENTITY_1, "period_key": FEBRUARY, "grain": DEFAULT_GRAIN}
    return post(world.app, JOURNAL_RUNS, world.legacy.maya, body)


def _context(world: JournalWorld) -> DbContext:
    return DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")


def _runs(world: JournalWorld) -> list[tuple[str, str, int]]:
    """(run no, state, line count) of the tenant's journal runs, oldest first."""
    with tenant_session(_context(world), read_only=True) as session:
        rows = session.execute(
            select(journal_run.c.run_no, journal_run.c.state, journal_run.c.line_count).order_by(
                journal_run.c.created_at, journal_run.c.run_no
            )
        ).all()
    return [
        (str(row.run_no), str(getattr(row.state, "value", row.state)), int(row.line_count))
        for row in rows
    ]


def _calculations(world: JournalWorld) -> int:
    """The number of ``JOURNAL_RUN_CALCULATE`` jobs of the tenant."""
    with tenant_session(_context(world), read_only=True) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(job)
                .where(job.c.kind == JobKind.JOURNAL_RUN_CALCULATE.value)
            ).scalar_one()
        )


def _settled(world: JournalWorld, job_id: UUID, attempts: int = 3) -> dict[str, Any]:
    """The worker runs the job attempt by attempt until it settles; its row."""

    def row() -> dict[str, Any]:
        with tenant_session(_context(world), read_only=True) as session:
            found = session.execute(
                select(job.c.state, job.c.problem, job.c.result).where(job.c.id == job_id)
            )
            return dict(found.mappings().one())

    for attempt in range(1, attempts + 1):
        with tenant_session(_context(world)) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(TASK_FETCHED, {"id": task_id})
        run_job(
            job_id, world.legacy.tenant_id, attempt=attempt, runtime=world.legacy.imports.runtime
        )
        if str(row()["state"]) in ("SUCCEEDED", "FAILED"):
            break
    return row()


def _february(world: JournalWorld) -> str:
    """The name of February 2023 as the product shows it."""
    (found,) = [
        item
        for item in periods(world.app, world.legacy.maya, entity=ENTITY_1)
        if item["period"]["period_key"] == FEBRUARY
    ]
    return str(found["period"]["name"])


def _errors(body: dict[str, Any]) -> list[tuple[str | None, str, str]]:
    return [(item["field"], item["rule_id"], item["message"]) for item in body["errors"]]


def _failed_job_items(world: JournalWorld) -> list[tuple[str, str, str, str]]:
    """(severity, status, dedupe key, message) of the tenant's ``JOB_FAILED`` items (05 JOB-07)."""
    with tenant_session(_context(world), read_only=True) as session:
        rows = session.execute(
            select(
                exception_item.c.severity,
                exception_item.c.status,
                exception_item.c.dedupe_key,
                exception_item.c.message,
            ).where(exception_item.c.code == "JOB_FAILED")
        ).all()
    return [
        (
            str(getattr(row.severity, "value", row.severity)),
            str(getattr(row.status, "value", row.status)),
            str(row.dedupe_key),
            str(row.message),
        )
        for row in rows
    ]


def _accounts(session: Session, close: CloseWorld) -> tuple[dict[str, Any], dict[str, Any]]:
    """The revenue account 5001 and the unbilled receivable 1201 of the close world."""
    revenue = gl_account_values(close.tenant_id, code="5001")
    unbilled = gl_account_values(close.tenant_id, code="1201")
    session.execute(insert(gl_account).values(**revenue))
    session.execute(insert(gl_account).values(**unbilled))
    return revenue, unbilled


def _delivery(
    session: Session,
    close: CloseWorld,
    accounts: tuple[dict[str, Any], dict[str, Any]],
    external_id: str,
    amount: str,
) -> SealedActivity:
    """One sealed posting of September for a contract of its own: revenue ``amount`` on 5001 and
    its unbilled receivable on 1201 (that of ``test_completeness``)."""
    revenue, unbilled = accounts
    return sealed_activity(
        session,
        close,
        account=revenue,
        period_id=close.period_id,
        period_end_date=PERIOD_END,
        amounts=[Decimal(amount)],
        external_id=external_id,
        obligation_key="O1",
        with_schedule_line=True,
        offset_account=unbilled,
        offset_columns={"account_role": "UNBILLED_RECEIVABLE"},
    )


def _held(session: Session, close: CloseWorld, activity: SealedActivity, reason: str) -> UUID:
    """An open ``journal_export`` hold on the activity's contract, applied the day before; its
    id."""
    applied_event_id = session.execute(
        select(contract_event.c.id).where(contract_event.c.contract_id == activity.contract_id)
    ).scalar_one()
    hold = contract_hold_values(
        close.tenant_id,
        contract_id=activity.contract_id,
        applied_event_id=applied_event_id,
        hold_type="journal_export",
        reason=reason,
        applied_at=close.place.clock.now() - timedelta(days=1),
    )
    session.execute(insert(contract_hold).values(**hold))
    return UUID(str(hold["id"]))


def _refused_in_september(close: CloseWorld, run_no: str) -> None:
    """``POST /journal-runs`` for September of AVM-US answers the refusal of PRD ERR-96 by
    ``run_no`` and writes neither a run nor a job."""
    runs = _runs_of_september(close)
    refused = post(
        close.app, JOURNAL_RUNS, close.maya, {"entity_code": "AVM-US", "period_key": SEPTEMBER}
    )
    assert refused.status_code == 409, refused.text
    sentence = NOTHING_PENDING.format(run=run_no, period="Sep 2026", entity="AVM-US")
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert _errors(refused.json()) == [(None, RULE, sentence)]
    assert RUN_ID_HEADER not in refused.headers
    assert _runs_of_september(close) == runs


# --- no further run without a line (PRD ERR-96) ---------------------------------------------------


@pytest.mark.slow
def test_no_run_is_made_where_a_run_covers_every_posting(world: JournalWorld) -> None:
    """04 §16.7 API-S-JournalRunCreate rev 1.248 (PRD ERR-96): February's run stands and covers
    both postings of the period. A second ``POST /journal-runs`` answers 409 by the run's number,
    defers no job and writes no run. Before the item it answered 202 and its job made
    ``JR-000002`` without a line, which then refused the cancel of the run before it; now that
    run is the period's latest and is cancelled as such, after which the period is calculated
    again."""
    first = _calculated(world)
    assert (first["state"], first["totals"]["line_count"] > 0) == ("draft", True)
    runs, jobs = _runs(world), _calculations(world)

    refused = _request(world)
    assert refused.status_code == 409, refused.text  # before the item: 202
    sentence = NOTHING_PENDING.format(run=first["run_no"], period=_february(world), entity=ENTITY_1)
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert _errors(refused.json()) == [(None, RULE, sentence)]
    assert RUN_ID_HEADER not in refused.headers
    assert (_runs(world), _calculations(world)) == (runs, jobs)

    # before the item: 409, "Journal run JR-000002 was calculated after this run …"
    path = f"{JOURNAL_RUNS}/{first['id']}/cancel"
    cancelled = post(world.app, path, world.legacy.maya, {"reason": REASON})
    assert (cancelled.status_code, cancelled.json()["state"]) == (200, "cancelled"), cancelled.text
    again = _calculated(world)  # no run that is not cancelled: the period is calculated again
    assert (again["state"], again["totals"]["line_count"]) == (
        "draft",
        first["totals"]["line_count"],
    )
    assert again["run_no"] != first["run_no"]


@pytest.mark.slow
def test_a_run_is_made_again_once_a_posting_lies_beyond_the_runs(world: JournalWorld) -> None:
    """The refusal ends with the next posting: a revenue entry sealed in February after its run
    is beyond what the run covers, so a second run is made. It starts where the first ends
    (DB-16) and holds the two lines of that entry alone."""
    first = _calculated(world)
    late, _ = _pair(world)
    _revenue(world, "empty-run-late", late, "5001", "25.00")

    second = _calculated(world)
    assert (second["state"], second["totals"]["line_count"]) == ("draft", 2)
    assert second["coverage"]["from_chain_seq"] == first["coverage"]["to_chain_seq"]
    assert second["coverage"]["to_chain_seq"] > first["coverage"]["to_chain_seq"]
    assert second["totals"]["debit_functional"]["amount"] == "25.00"
    refused = _request(world)  # and now nothing lies beyond the second run
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == NOTHING_PENDING.format(
        run=second["run_no"], period=_february(world), entity=ENTITY_1
    )


@pytest.mark.slow
def test_two_calculations_accepted_at_once_end_in_one_run(world: JournalWorld) -> None:
    """The command asks on a plain read, so two commands sent before either job has run are both
    accepted. The job asks again under the coverage lock of the entity, book and period: the
    first makes the run, and the second ends ``FAILED`` with the problem of PRD ERR-96 and writes
    no run. Before the item the second job SUCCEEDED and its run without lines stood after the
    first. As any calculation that failed, the second job leaves the ``INFO`` item of 05 JOB-07
    for the entity, book and period (lane OPS's item JOB-FAILED-ITEM-1): it names the sentence,
    no gate counts it, and it is dismissed with a comment or settled by the key's next run."""
    one, two = _request(world), _request(world)
    assert (one.status_code, two.status_code) == (202, 202), (one.text, two.text)
    run_import_job(world.legacy.imports, UUID(str(one.json()["id"])))
    [(run_no, state, lines)] = _runs(world)
    assert (state, lines > 0) == ("draft", True)

    finished = _settled(world, UUID(str(two.json()["id"])))
    assert str(finished["state"]) == "FAILED", finished  # before the item: SUCCEEDED
    problem = finished["problem"]
    sentence = NOTHING_PENDING.format(run=run_no, period=_february(world), entity=ENTITY_1)
    assert (problem["type"], problem["status"], problem["detail"]) == (TRANSITION, 409, sentence)
    assert [(item["field"], item["rule_id"]) for item in problem["errors"]] == [(None, RULE)]
    assert _runs(world) == [(run_no, state, lines)]
    missing = get(world.app, f"{JOURNAL_RUNS}/{two.headers[RUN_ID_HEADER]}", world.legacy.maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text
    [(severity, status, key, message)] = _failed_job_items(world)
    record = f"{world.entities[ENTITY_1]}:{BOOK}:{world.periods[FEBRUARY][0]}"
    assert (severity, status) == ("INFO", "OPEN")
    assert key == f"JOURNAL:JOB_FAILED:JOURNAL_RUN_CALCULATE:{record}"
    assert sentence.removesuffix(".") in message


@pytest.mark.slow
def test_inside_a_close_run_the_calculation_makes_no_run_and_raises_nothing(
    world: JournalWorld,
) -> None:
    """The close run's ``JOURNAL_SUMMARIZATION`` step asks its own question before it calls the
    calculation (``close_runs._journal_pending``), on a plain read; a run made between that read
    and the coverage lock leaves it nothing to summarize. The step then calculates nothing and
    does not fail: called under a ``CLOSE_RUN`` job the calculation writes no run and answers no
    counts, where the job of ``POST /journal-runs`` raises the problem of PRD ERR-96."""
    first = _calculated(world)
    runs = _runs(world)
    tenant_id = world.legacy.tenant_id
    params = {
        "journal_run_id": str(new_id()),
        "entity_id": str(world.entities[ENTITY_1]),
        "book_code": BOOK,
        "period_id": str(world.periods[FEBRUARY][0]),
        "mode": first["mode"],
        "grain": first["grain"],
        "cutoff_known_at": world.legacy.imports.runtime.clock.now().isoformat(),
        "close_run_id": None,
    }

    def job_of(kind: JobKind) -> JobContext:
        return JobContext(
            job_id=new_id(),
            tenant_id=tenant_id,
            kind=kind,
            principal=system_principal(tenant_id),
            runtime=world.legacy.imports.runtime,
            persisted=False,
        )

    stepped = summarise.calculate_run(job_of(JobKind.CLOSE_RUN), params)
    assert (stepped.state, stepped.result["counts"]) == ("SUCCEEDED", {})
    assert _runs(world) == runs
    with pytest.raises(Problem) as refused:
        summarise.calculate_run(job_of(JobKind.JOURNAL_RUN_CALCULATE), params)
    assert (refused.value.slug, refused.value.errors[0].rule_id) == ("invalid-transition", RULE)
    assert _runs(world) == runs


# --- the empty first run of a period without activity ---------------------------------------------


@pytest.mark.slow
def test_the_first_run_of_a_period_without_activity_is_made_and_the_period_locks_on_it(
    close: CloseWorld, clock: FrozenClock
) -> None:
    """04 §16.7 API-S-JournalRunCreate rev 1.248: September 2026 of AVM-US holds no posting. Its
    first run is made all the same — the lock gates need a run that is not cancelled — as a
    ``draft`` run without a line or a batch. A second is refused by the first's number (before
    the item: a second empty run). The period's lock is then requested and decided by two
    Controllers on that run as it stands: that is the ordinary end of an empty first run."""
    _soft_close(close)
    run_id = _run_of_september(close)
    [(run_no, state, lines)] = _runs_of_september(close)
    assert (state, lines) == ("draft", 0)
    shown = get(close.app, f"{JOURNAL_RUNS}/{run_id}", close.maya)
    assert (shown.status_code, shown.json()["batches"]) == (200, [])

    _refused_in_september(close, run_no)  # before the item: 202 and a second empty run

    request_id, controller = _pending_lock(close, clock)
    decided = approve(close.app, request_id, controller)
    assert decided.status_code == 200, decided.text
    assert _september(close)["state"] == PeriodState.CLOSED.value
    assert _runs_of_september(close) == [(run_no, "draft", 0)]


@pytest.mark.slow
def test_an_empty_run_is_not_submitted(close: CloseWorld) -> None:
    """04 §16.7 ``submit`` rev 1.248: the first run of a period without activity has no journal
    line, so there is nothing a second person could approve and nothing would leave eRev. The
    submission answers 409 by the run's number and opens no request; the run is cancelled as any
    draft run is. Before the item it was submitted (200), approved, and "exported" over no
    message."""
    _soft_close(close)
    run_id = _run_of_september(close)
    [(run_no, _, lines)] = _runs_of_september(close)
    assert lines == 0

    refused = post(close.app, f"{JOURNAL_RUNS}/{run_id}/submit", close.maya, {})
    assert refused.status_code == 409, refused.text  # before the item: 200
    sentence = NO_LINES.format(run=run_no)
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert _errors(refused.json()) == [("state", "E-34", sentence)]
    shown = get(close.app, f"{JOURNAL_RUNS}/{run_id}", close.maya)
    assert (shown.json()["state"], shown.json()["approval_request_id"]) == ("draft", None)

    path = f"{JOURNAL_RUNS}/{run_id}/cancel"
    cancelled = post(close.app, path, close.maya, {"reason": REASON})
    assert (cancelled.status_code, cancelled.json()["state"]) == (200, "cancelled"), cancelled.text


# --- the refusal is not a statement that the period is journalised --------------------------------


@pytest.mark.slow
def test_a_further_run_waits_for_the_release_of_a_journal_export_hold(close: CloseWorld) -> None:
    """04 §16.7 API-S-JournalRunCreate rev 1.248, case (2) of the refusal: September's run stands
    and the one posting sealed since belongs to a contract under a journal-export hold. A run
    would leave it out (S14-R-17), so it would hold no line, and none is made — the sentence names
    the latest run and claims no coverage, and ``JE_COMPLETE`` goes on naming the posting as held.
    Before the item a second run was made without lines, and the held posting lay inside its
    range: released, it was reached by no further run until that run was cancelled. Now the
    release is the way: the next run starts where the first ends and holds the posting."""
    with system_session(close) as session:
        accounts = _accounts(session, close)
        _delivery(session, close, accounts, "SF-ORD-20001", "-250.00")
    first_id = _run_of_september(close)
    [(first_no, _, first_lines)] = _runs_of_september(close)
    assert first_lines == 2
    with system_session(close) as session:
        disputed = _delivery(session, close, accounts, "SF-ORD-20002", "-100.00")
        hold_id = _held(session, close, disputed, "Customer dispute on invoice INV-US-20002")

    _refused_in_september(close, first_no)  # before the item: 202 and a second run, no line
    held = _completeness(close)
    assert (held.status, held.count, held.run_count) == (ChecklistStatus.FAILED, 1, 1)
    assert {item.hold_id for item in held.held} == {hold_id} and held.uncovered == ()

    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_id, disputed.contract_id)
    second_id = _run_of_september(close)
    assert [(state, lines) for _, state, lines in _runs_of_september(close)] == [
        ("draft", 2),
        ("draft", 2),
    ]
    first = get(close.app, f"{JOURNAL_RUNS}/{first_id}", close.maya).json()
    second = get(close.app, f"{JOURNAL_RUNS}/{second_id}", close.maya).json()
    assert second["coverage"]["from_chain_seq"] == first["coverage"]["to_chain_seq"]
    assert second["totals"]["debit_functional"]["amount"] == "100.00"
    complete = _completeness(close)
    assert (complete.status, complete.count, complete.run_count) == (ChecklistStatus.PASSED, 0, 2)


@pytest.mark.slow
def test_postings_a_run_left_out_are_taken_over_once_their_hold_is_released(
    close: CloseWorld,
) -> None:
    """Case (3) of the refusal: September's first run was calculated while the period's one posting
    was under a journal-export hold, so it left the posting out and has no line. While the hold is
    open a new run would hold no line — the posting lies inside the first run's range, and a line
    under a hold is not taken over — so it is refused by the first run's number, while
    ``JE_COMPLETE`` names the posting as held: the sentence says nothing else. Before item
    JRN-EMPTY-RUN-1 a second run without lines was made here.

    Once the hold is released the next run takes the posting over (item JRN-HELD-AFTER-EXPORT-1;
    ENGINE_SPEC_B S14-R-17 rev 1.164; 04 T-SL-06 rev 1.267): it starts where the first run ends
    and holds the two lines. Until that item the command was refused after the release as well
    and the remedy was the cancel of the run that left the posting out — which this witness
    asserted under the name ``…_are_reached_once_that_run_is_cancelled`` (STALE EXPECTATION by the
    supervisor's ruling of 2026-10-02)."""
    with system_session(close) as session:
        accounts = _accounts(session, close)
        disputed = _delivery(session, close, accounts, "SF-ORD-20003", "-100.00")
        hold_id = _held(session, close, disputed, "Customer dispute on invoice INV-US-20003")
    first_id = _run_of_september(close)
    [(first_no, state, lines)] = _runs_of_september(close)
    assert (state, lines) == ("draft", 0)

    _refused_in_september(close, first_no)  # before JRN-EMPTY-RUN-1: 202 and a run, no line
    held = _completeness(close)
    assert (held.status, held.count, held.run_count) == (ChecklistStatus.FAILED, 1, 1)
    assert {item.hold_id for item in held.held} == {hold_id} and held.uncovered == ()

    close.place.clock.advance(timedelta(minutes=5))
    _release_hold(close, hold_id, disputed.contract_id)
    released = _completeness(close)
    assert (released.status, released.count, released.held) == (ChecklistStatus.FAILED, 1, ())
    assert {item.subledger_line_id for item in released.uncovered} == set(disputed.line_ids)

    second_id = _run_of_september(close)  # until JRN-HELD-AFTER-EXPORT-1: 409, PRD ERR-96
    assert [(state, lines) for _, state, lines in _runs_of_september(close)] == [
        ("draft", 0),
        ("draft", 2),
    ]
    first = get(close.app, f"{JOURNAL_RUNS}/{first_id}", close.maya).json()
    second = get(close.app, f"{JOURNAL_RUNS}/{second_id}", close.maya).json()
    assert second["coverage"]["from_chain_seq"] == first["coverage"]["to_chain_seq"]
    assert second["totals"]["debit_functional"]["amount"] == "100.00"
    complete = _completeness(close)
    assert (complete.status, complete.count, complete.run_count) == (ChecklistStatus.PASSED, 0, 2)
