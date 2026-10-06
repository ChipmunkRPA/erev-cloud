"""Item JRN-FAILED-CANCEL-1 (supervisor ruling R-112 (c)): the ways out of a failed journal run
(04 T-SL-07 "The ways out of ``failed``", §16.7 "Journal commands" rev 1.159, E-34; 05 ADP-12,
ADP-33, §5.6; PRD SM-08, BR-JE-03, ERR-73, ERR-74, ERR-79; dev-guide DG-KRN-JOB-05; CTL-021;
BUILD_SPEC CLO-14 rev 1.20) — and item JRN-DISPATCH-DEAD-1 (rulings R-118 (k) and R-119 (c); 05
ADP-31, ADP-32 rev 1.98): a dispatch that dies of an error of eRev's own leaves a ``failed``
batch, so those ways out apply to it — and item JRN-CANCEL-APPROVED-PENDING-1 (ruling R-119 (c);
04 §16.7 ``cancel`` (c) rev 1.204; 05 ADP-31 rev 1.143; PRD SM-08 and NTF-10 rev 1.133): a run
without a failed batch is not cancelled while one of its batches waits to be sent again after a
failed attempt — and item JRN-RETRY-CLAIMED-1 (the supervisor's ruling of 2026-10-01 08:31; 04
§16.7 ``retry`` rev 1.221; 05 ADP-32 rev 1.160): a retry writes no message beside one that is not
settled, and the export job names the batches that wait — and, for item JR-CLOSED-PERIOD-GUARD-1
(04 §16.7 ``cancel`` (d) rev 1.205; PRD ERR-86), the cancel of a failed run in a closed period,
beside the three batch commands such a period still takes (PRD SM-08 rev 1.167).

World: that of ``test_chunking`` — February 2023 of Mock Entity 1 with one revenue entry per
contract on the shared contract liability account, an Integration Admin's NetSuite connection and
the app's own NetSuite mock, reached by the worker's adapter over ASGI. A batch is made to fail
by the mock's ``PERMANENT_ERROR`` fault (HTTP 400 before anything is stored); the ledger "holds a
failed batch" when the chunk reached it through an attempt whose answer never arrived. Jobs run as
the worker runs them.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl import netsuite
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    control_execution,
    exception_item,
    job,
    journal_batch,
    journal_line,
    journal_run,
    notification,
    outbox_message,
)
from erev_api.db.tables.platform import audit_event
from erev_api.domain.close import gates
from erev_api.domain.journals import commands, export, ports
from erev_api.enums import GlAdapter, JobKind, OutboxTopic
from erev_api.events import outbox
from erev_api.events.outbox import RelayStats
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, run_job
from erev_api.main import create_app
from erev_api.problems import LOCK_CONFLICT_DETAIL, STATEMENT_TIMEOUT_DETAIL, TYPE_BASE, Problem
from fastapi import FastAPI
from sqlalchemy import Engine, event, func, insert, select, text
from sqlalchemy.exc import DBAPIError
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.http import asgi_client
from support.journal_lines import insert_behind_the_guard
from support.principals import colleague, sign_in, workspace
from support.reference import approve, assign, get, patch, periods, post, slug
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    FEBRUARY,
    JOURNAL_RUNS,
    JournalWorld,
    journal_world,
    post_lines,
)
from test_chunking import (
    INTEGRATIONS,
    MOCK_BASE,
    _admin,
    _approved,
    _calculated,
    _connection,
    _exported,
    _netsuite,
    _pair,
    _receipts,
    _relayer,
    _rows,
    _run,
    _tenant_code,
)

BATCHES: Final = "/api/v1/journal-batches"
JOBS: Final = "/api/v1/jobs"
BOOK: Final = "ASC606"
LEDGER: Final = "NetSuite (mock)"  # the connection's name: the ledger a refusal names
REASON: Final = "The ledger refuses the entry as generated; recalculate after the mapping fix."
TRANSITION: Final = f"{TYPE_BASE}invalid-transition"
TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
CANCEL_WAITS: Final = (
    "An export of this journal run is in progress: batch {external_id} is waiting to be sent. "
    "It cannot be cancelled until the batch has been sent or has failed."
)
CANCEL_ATTEMPTED: Final = (
    "An export of this journal run is in progress: an attempt to send batch {external_id} failed "
    "and it will be sent again. It cannot be cancelled until the batch has been sent or has "
    "failed."
)
BEFORE_EXPORT: Final = "A journal run can be cancelled only before it is exported."
RETRY_BEING_SENT: Final = (
    "Batch {external_id} is being sent. It cannot be retried while it is being sent. An "
    "interrupted export resumes about 15 minutes after it stopped."
)
# 04 §16.7 rev 1.247 (item JRN-EXIT-SETTLE-1): the exits of a batch the ledger may still take.
SETTLING: Final = (
    "The last attempt to send batch {external_id} ended less than 15 minutes ago without the "
    "ledger's refusal, so the ledger may still take it."
)
LEDGER_ACCEPTED: Final = "The ledger accepted batch {external_id} and does not show it yet."
CANCEL_SETTLING: Final = (
    SETTLING + " This journal run cannot be cancelled yet. Ask again in about {wait}, or retry "
    "the batch."
)
CANCEL_ACCEPTED: Final = (
    LEDGER_ACCEPTED + " This journal run cannot be cancelled. Retry the batch: a retry asks the "
    "ledger first."
)
HAND_SETTLING: Final = (
    SETTLING + " It cannot be handed over yet. Ask again in about {wait}, or retry the batch."
)
HAND_ACCEPTED: Final = (
    LEDGER_ACCEPTED + " It cannot be handed over. Retry the batch: a retry asks the ledger first."
)
WAIT: Final = timedelta(minutes=15)  # how long the exits leave the ledger after such a death
DUE_AGAIN: Final = RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
DIED: Final = RelayStats(claimed=1, dispatched=0, failed=0, dead=1)


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
    built = journal_world(app, keyring, clock, files)
    first, second = _pair(built)
    for key, contract_key, revenue, amount in (
        ("exit-contract-1", first, "5001", "100.00"),
        ("exit-contract-2", second, "5002", "50.00"),
    ):
        post_lines(
            built,
            key=key,
            contract_key=contract_key,
            period_key=FEBRUARY,
            entries=[
                (
                    "REVENUE_RECOGNITION",
                    [
                        ("CONTRACT_LIABILITY", "21001", amount, "POB #1"),
                        ("REVENUE", revenue, f"-{amount}", "POB #1"),
                    ],
                )
            ],
        )
    return built


# --- helpers --------------------------------------------------------------------------------------


def _context(world: JournalWorld) -> DbContext:
    return DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")


def _faults(world: JournalWorld, kind: str, count: int = 1) -> None:
    """Queue an ADP-21 fault for the next ``count`` requests to the mock's journal route."""
    with asgi_client(world.app) as client:
        queued = client.post(
            f"{mocks.MOCKS_PREFIX}/__admin/faults",
            json={"route": ns_mock.JOURNAL_ROUTE, "kind": kind, "count": count},
        )
        assert queued.status_code == 201, queued.text


def _work(world: JournalWorld, job_id: Any, attempt: int = 1) -> dict[str, Any]:
    """The worker fetches the job's task and runs attempt ``attempt``; API-S-Job afterwards."""
    tenant_id = world.legacy.tenant_id
    with tenant_session(_context(world)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == UUID(str(job_id)))
        ).scalar_one()
        session.execute(TASK_FETCHED, {"id": task_id})
    run_job(UUID(str(job_id)), tenant_id, attempt=attempt, runtime=world.legacy.imports.runtime)
    shown = get(world.app, f"{JOBS}/{job_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _cancel(world: JournalWorld, run_id: str) -> Any:
    return post(world.app, f"{JOURNAL_RUNS}/{run_id}/cancel", world.legacy.maya, {"reason": REASON})


def _states(world: JournalWorld, run_id: str) -> tuple[str, list[str]]:
    """The run's state and its batches' states in chunk order."""
    shown = _run(world, run_id)
    ordered = sorted(shown["batches"], key=lambda item: (item["batch_no"], item["chunk_no"]))
    return shown["state"], [item["state"] for item in ordered]


def _failed_run(
    world: JournalWorld,
    monkeypatch: pytest.MonkeyPatch,
    clock: FrozenClock,
    *,
    chunks: int = 1,
    refused: int = 1,
) -> tuple[ns_mock.NetSuiteMock, dict[str, Any], list[dict[str, Any]]]:
    """An approved February run of ``chunks`` NetSuite chunks whose first ``refused`` chunks the
    ledger refused and whose other chunk it acknowledged: (the mock, the run, its batches in
    chunk order)."""
    mock = _netsuite(world, monkeypatch)
    config = {} if chunks == 1 else {"config": {"max_lines_per_chunk": 2}}
    _connection(world, _admin(world, clock), **config)
    run = _approved(world)
    batches = sorted(run["batches"], key=lambda item: item["chunk_no"])
    assert [item["adapter"] for item in batches] == ["NETSUITE"] * chunks
    _faults(world, "PERMANENT_ERROR", refused)
    _exported(world, run["id"])
    expected = ["failed"] * refused + ["acknowledged"] * (chunks - refused)
    assert _states(world, run["id"]) == ("failed", expected)
    assert mock.posting_count == chunks - refused
    return mock, run, batches


def _asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The external ids the NetSuite adapter is asked for from now on (ADP-12 ``get_posting``)."""
    asked: list[str] = []
    original = netsuite.NetSuiteGl.get_posting

    def recording(self: netsuite.NetSuiteGl, external_id: str) -> ports.PostingResult | None:
        asked.append(external_id)
        return original(self, external_id)

    monkeypatch.setattr(netsuite.NetSuiteGl, "get_posting", recording)
    return asked


def _lost_posting(world: JournalWorld, batch: dict[str, Any]) -> str:
    """The ledger takes the chunk through an attempt whose answer never reached the product: it
    holds the document, eRev no receipt. The ledger's document."""
    lost = ports.gl_adapter_for(
        GlAdapter.NETSUITE,
        ports.GLContext(tenant_code=_tenant_code(batch), accounts=(), base_url=MOCK_BASE),
    )
    with tenant_session(_context(world), read_only=True) as session:
        chunk = export.chunk_of(session, UUID(batch["id"]))
    return str(lost.post_chunk(chunk).gl_document_id)


def _items(world: JournalWorld, batch: dict[str, Any]) -> list[tuple[str, str | None]]:
    """(status, resolution) of the batch's ``JOURNAL_EXPORT_FAILED`` items."""
    rows = _rows(
        world,
        select(exception_item.c.status, exception_item.c.resolution)
        .where(
            exception_item.c.code == export.EXPORT_FAILED_CODE,
            exception_item.c.business_key == batch["external_id"],
        )
        .order_by(exception_item.c.created_at, exception_item.c.id),
    )
    return [(str(row["status"]), row["resolution"]) for row in rows]


def _events(world: JournalWorld, object_id: str, prefix: str) -> list[dict[str, Any]]:
    """The audit events of an object whose action starts with ``prefix``, in chain order."""
    return _rows(
        world,
        select(
            audit_event.c.action,
            audit_event.c.outcome,
            audit_event.c.actor_kind,
            audit_event.c.actor_id,
            audit_event.c.on_behalf_of_id,
            audit_event.c.comment,
            audit_event.c.detail,
            audit_event.c.after,
        )
        .where(audit_event.c.object_id == UUID(object_id), audit_event.c.action.like(f"{prefix}%"))
        .order_by(audit_event.c.chain_seq),
    )


def _executions(world: JournalWorld, batch_id: str) -> list[tuple[str, dict[str, Any]]]:
    """(result, detail) of the CTL-021 executions of a batch, oldest first."""
    rows = _rows(
        world,
        select(control_execution.c.result, control_execution.c.detail)
        .where(
            control_execution.c.control_id == export.CONTROL_ID,
            control_execution.c.run_ref_id == UUID(batch_id),
        )
        .order_by(control_execution.c.executed_at, control_execution.c.id),
    )
    return [(str(row["result"]), dict(row["detail"])) for row in rows]


def _export_jobs(world: JournalWorld, run_id: str) -> int:
    [row] = _rows(
        world,
        select(func.count().label("n"))
        .select_from(job)
        .where(job.c.kind == JobKind.JOURNAL_EXPORT.value, job.c.subject_id == UUID(run_id)),
    )
    return int(row["n"])


def _stored(world: JournalWorld, batch_id: str) -> dict[str, Any]:
    [row] = _rows(world, select(journal_batch).where(journal_batch.c.id == UUID(batch_id)))
    return row


def _refusal(finished: dict[str, Any], job_id: str) -> tuple[str, str, list[tuple[str, str]]]:
    """(type, detail, [(field, rule id)]) of ``result.refusal``; its message is its detail and its
    instance the job."""
    refusal = finished["result"]["refusal"]
    assert refusal["instance"] == f"{JOBS}/{job_id}"
    assert [item["message"] for item in refusal["errors"]] == [refusal["detail"]]
    return (
        refusal["type"],
        refusal["detail"],
        [(item["field"], item["rule_id"]) for item in refusal["errors"]],
    )


def _gate(world: JournalWorld, code: str = "BATCHES_ACKNOWLEDGED") -> gates.GateResult:
    with world.legacy.place().uow() as uow:
        results = gates.evaluate_gates(
            uow, world.entities[ENTITY_1], BOOK, world.periods[FEBRUARY][0]
        )
        uow.commit()
    (found,) = [result for result in results if result.gate_check_code == code]
    return found


# --- cancel ---------------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_failed_run_is_cancelled_once_its_ledger_holds_none_of_it(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``cancel`` rev 1.159 (ruling R-112 (c)): the cancel of a ``failed`` run answers 202
    and changes nothing itself; its job asks the ledger for the failed batch by its external id
    and, the ledger holding none, cancels run and batch in one transaction — the exception item
    resolved with the reason, a CTL-021 execution, the ``journal_run.cancel`` event. The period is
    then calculated again as a ``draft`` with a new run number and new external ids, entry numbers
    continue, and after approval and export the ledger holds the period once."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    maya = world.legacy.maya
    assert _items(world, batch) == [("OPEN", None)]
    asked = _asked(monkeypatch)

    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    queued = accepted.json()
    assert (queued["kind"], queued["state"], accepted.headers["Location"]) == (
        "JOURNAL_EXPORT",
        "QUEUED",
        f"{JOBS}/{queued['id']}",
    )
    # the command decides nothing: stored facts cannot say whether the ledger holds the batch
    assert _states(world, run["id"]) == ("failed", ["failed"]) and asked == []

    finished = _work(world, queued["id"])
    assert (finished["state"], finished["problem"]) == ("SUCCEEDED", None)
    assert finished["result"] == {
        "href": f"{JOURNAL_RUNS}/{run['id']}",
        "counts": {"asked": 1, "held": 0, "cancelled": 1},
        "outcome": "CANCELLED",
    }
    assert asked == [batch["external_id"]] and mock.posting_count == 0
    cancelled = _run(world, run["id"])
    assert (cancelled["state"], [item["state"] for item in cancelled["batches"]]) == (
        "cancelled",
        ["cancelled"],
    )
    assert cancelled["cancelled_at"] is not None and cancelled["exported_at"] is None
    assert _items(world, batch) == [("RESOLVED", f"The journal run was cancelled: {REASON}")]
    assert _receipts(world, run) == [(1, "REJECTED", None)]
    assert _executions(world, batch["id"]) == [
        ("FAIL", {"status": "failed", "ack_kind": "REJECTED", "gl_document_id": None}),
        (
            "PASS",
            {"status": "cancelled", "ack_kind": None, "gl_document_id": None, "ledger_asked": True},
        ),
    ]
    request, decision = _events(world, run["id"], "journal_run.")[-2:]
    assert (request["action"], request["outcome"], request["actor_kind"], request["comment"]) == (
        "journal_run.request_cancel",
        "SUCCESS",
        "USER",
        REASON,
    )
    assert request["after"]["job_id"] == queued["id"]
    # the decision is the job's, for the person who asked; the screen's banner reads its comment
    assert (
        decision["action"],
        decision["outcome"],
        decision["actor_kind"],
        decision["on_behalf_of_id"],
        decision["comment"],
    ) == ("journal_run.cancel", "SUCCESS", "SYSTEM", maya.member.user_id, REASON)
    assert decision["after"]["ledger_asked"] == [batch["external_id"]]

    # DB-16: the next run starts where the non-cancelled runs of the key end
    again = _calculated(world)
    [fresh] = again["batches"]
    assert (again["state"], again["run_no"] != run["run_no"], fresh["batch_no"]) == (
        "draft",
        True,
        1,
    )
    assert fresh["external_id"] != batch["external_id"]
    assert again["je_range"]["first_je_no"] > run["je_range"]["last_je_no"]
    submitted = post(world.app, f"{JOURNAL_RUNS}/{again['id']}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.legacy.priya)
    assert decided.status_code == 200, decided.text
    _exported(world, again["id"])
    assert _states(world, again["id"]) == ("acknowledged", ["acknowledged"])
    assert mock.posting_count == 1
    assert mock.journal(fresh["external_id"]) is not None
    assert mock.journal(batch["external_id"]) is None


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_batch_the_ledger_holds_is_acknowledged_and_the_cancel_refused(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD ERR-73: the ledger took the chunk although the batch is ``failed`` — a timeout can
    follow an acceptance. The job records the ``DUPLICATE`` receipt with the ledger's document,
    batch and run are ``acknowledged``, and nothing is cancelled: the job ends
    ``SUCCEEDED_WITH_EXCEPTIONS`` with ``result.outcome`` ``NOT_CANCELLED`` and the refusal as a
    problem object, and a ``journal_run.cancel`` event with outcome ``DENIED`` records it."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    document = _lost_posting(world, batch)
    assert (document, mock.posting_count, _states(world, run["id"])) == (
        "JE-NS-88001",
        1,
        ("failed", ["failed"]),
    )

    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    finished = _work(world, job_id)
    assert (finished["state"], finished["problem"]) == ("SUCCEEDED_WITH_EXCEPTIONS", None)
    assert (finished["result"]["outcome"], finished["result"]["counts"]) == (
        "NOT_CANCELLED",
        {"asked": 1, "held": 1, "cancelled": 0},
    )
    sentence = (
        f"{LEDGER} holds batch {batch['external_id']} as JE-NS-88001. The batch is acknowledged "
        f"and journal run {run['run_no']} is not cancelled."
    )
    assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "REJECTED", None), (1, "DUPLICATE", "JE-NS-88001")]
    assert mock.posting_count == 1
    assert _items(world, batch) == [("RESOLVED", "The ledger holds the batch as JE-NS-88001.")]
    assert _executions(world, batch["id"])[-1] == (
        "PASS",
        {"status": "acknowledged", "ack_kind": "DUPLICATE", "gl_document_id": "JE-NS-88001"},
    )
    denied = _events(world, run["id"], "journal_run.cancel")
    assert [(item["outcome"], item["actor_kind"], item["comment"]) for item in denied] == [
        ("DENIED", "SYSTEM", REASON)
    ]
    # ``field`` and ``counts`` since 04 rev 1.246: what an attempt that is run again returns
    assert denied[0]["detail"] == {
        "problem": "invalid-transition",
        "field": "state",
        "rule_id": "E-34",
        "message": sentence,
        "job_id": job_id,
        "counts": {"asked": 1, "held": 1, "cancelled": 0},
    }
    # a run that is in the ledger is cancelled no more
    late = _cancel(world, run["id"])
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text


@pytest.mark.slow
def test_an_unreachable_ledger_changes_nothing(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """A ledger that cannot be reached leaves everything as it is: the attempt fails and is
    queued again on the ADP-12 schedule, run and batch stay ``failed``, no receipt and no decision
    is written. After the last attempt the job is ``FAILED`` with the sentence; once the ledger
    answers, the cancel is asked again and done."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]

    _faults(world, "SERVER_ERROR")
    retried = _work(world, job_id)
    assert (retried["state"], retried["problem"], retried["result"]) == ("QUEUED", None, None)
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _receipts(world, run) == [(1, "REJECTED", None)]
    assert _events(world, run["id"], "journal_run.cancel") == []
    assert _items(world, batch) == [("OPEN", None)]

    _faults(world, "SERVER_ERROR")
    ended = _work(world, job_id, attempt=8)
    assert (ended["state"], ended["result"]) == ("FAILED", None)
    assert (ended["problem"]["type"], ended["problem"]["detail"]) == (
        TRANSITION,
        "The ledger could not be reached, so nothing was changed: NetSuite answered HTTP 500. "
        "Ask again when the ledger answers.",
    )
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _events(world, run["id"], "journal_run.cancel") == []

    again = _cancel(world, run["id"])
    assert again.status_code == 202, again.text
    assert _work(world, again.json()["id"])["result"]["outcome"] == "CANCELLED"
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0


# --- hand-over ------------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_run_partly_in_a_ledger_is_not_cancelled_and_its_failed_batch_is_handed_over(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD ERR-74 and the hand-over (04 §16.7 rev 1.159; 05 ADP-33): with one chunk acknowledged
    and one failed, the cancel answers 409 and starts no job — a recalculation would send the
    acknowledged lines again under new external ids. The failed batch is handed over instead:
    after the question to the ledger its file is stored, the batch is ``exported`` without a
    message or a receipt, ``BATCHES_ACKNOWLEDGED`` counts it, and ``acknowledge`` with the
    ledger's document ends batch and run ``acknowledged``."""
    mock, run, [failed, posted] = _failed_run(world, monkeypatch, clock, chunks=2)
    maya = world.legacy.maya
    jobs = _export_jobs(world, run["id"])

    refused = _cancel(world, run["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    sentence = (
        f"Journal run {run['run_no']} has a batch that a ledger holds or that was handed out "
        f"({posted['external_id']}). Retry its failed batch, or hand it over for manual posting."
    )
    assert refused.json()["detail"] == sentence
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        ("state", "E-34", sentence)
    ]
    assert _export_jobs(world, run["id"]) == jobs
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])

    # a batch that is not failed is not handed over
    other = post(world.app, f"{BATCHES}/{posted['id']}/hand-over", maya, {})
    assert (other.status_code, other.json()["detail"]) == (
        409,
        "Only a failed batch can be handed over.",
    )

    # the hand-over is the exporter's command, and the cancel the runner's, for the run's entity
    not_priya = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", world.legacy.priya, {})
    assert (not_priya.status_code, slug(not_priya)) == (403, "forbidden"), not_priya.text
    unknown = post(world.app, f"{BATCHES}/{new_id()}/hand-over", maya, {})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    someone = colleague(world.legacy.tenant_id, "otto")
    assign(someone, "revenue_accountant", entity_ids=(world.entities[ENTITY_2],))
    otto = workspace(world.app, someone, sign_in(world.app, someone.email))
    for path, body in (
        (f"{BATCHES}/{failed['id']}/hand-over", {}),
        (f"{JOURNAL_RUNS}/{run['id']}/cancel", {"reason": REASON}),
    ):
        hidden = post(world.app, path, otto, body)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    assert _export_jobs(world, run["id"]) == jobs

    asked = _asked(monkeypatch)
    messages = len(
        _rows(
            world,
            select(outbox_message.c.id).where(
                outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value
            ),
        )
    )
    before = _stored(world, failed["id"])
    # API-S-JournalRun ``batches`` rev 1.221: no batch of the run was handed over yet
    assert [item["handed_over_at"] for item in _run(world, run["id"])["batches"]] == [None, None]
    accepted = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", maya, {})
    assert accepted.status_code == 202, accepted.text
    queued = accepted.json()
    assert (queued["kind"], accepted.headers["Location"]) == (
        "JOURNAL_EXPORT",
        f"{JOBS}/{queued['id']}",
    )
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])
    twice = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", maya, {})
    assert (twice.status_code, twice.json()["detail"]) == (
        409,
        "A hand-over of this batch is already under way.",
    )
    finished = _work(world, queued["id"])
    assert (finished["state"], finished["result"]) == (
        "SUCCEEDED",
        {
            "href": f"{JOURNAL_RUNS}/{run['id']}",
            "counts": {"asked": 1, "held": 0, "handed_over": 1},
            "outcome": "HANDED_OVER",
        },
    )
    assert asked == [failed["external_id"]] and mock.posting_count == 1
    assert _states(world, run["id"]) == ("exported", ["exported", "acknowledged"])
    # API-S-JournalRun ``batches`` rev 1.221: the batch says when it was handed over — the
    # instant its file was stored. The chunk the ledger posted was exported too, and says nothing
    shown = {item["id"]: item for item in _run(world, run["id"])["batches"]}
    instant = shown[failed["id"]]["handed_over_at"]
    assert instant is not None and instant == shown[failed["id"]]["exported_at"]
    assert shown[posted["id"]]["exported_at"] is not None
    assert shown[posted["id"]]["handed_over_at"] is None
    after = _stored(world, failed["id"])
    assert after["exported_at"] is not None and after["export_file_id"] is not None
    assert (after["last_error"], after["attempt_count"]) == (None, before["attempt_count"] + 1)
    # no message and no receipt: the batch waits for the person who posts it
    assert after["outbox_message_id"] == before["outbox_message_id"]
    assert (
        len(
            _rows(
                world,
                select(outbox_message.c.id).where(
                    outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value
                ),
            )
        )
        == messages
    )
    assert _receipts(world, run) == [(1, "REJECTED", None), (2, "POSTED", "JE-NS-88001")]
    assert _items(world, failed) == [("RESOLVED", "The batch was handed over for manual posting.")]
    handed = _events(world, failed["id"], "journal_batch.")[-2:]
    assert [(item["action"], item["outcome"], item["actor_kind"]) for item in handed] == [
        ("journal_batch.request_hand_over", "SUCCESS", "USER"),
        ("journal_batch.hand_over", "SUCCESS", "SYSTEM"),
    ]
    assert handed[1]["after"]["posting_status"] == "EXPORTED"

    downloaded = get(world.app, f"{BATCHES}/{failed['id']}/download", maya)
    assert downloaded.status_code == 200, downloaded.text
    assert hashlib.sha256(downloaded.content).hexdigest() == after["export_sha256"].strip()
    name = failed["external_id"].replace(":", "_")
    archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
    assert sorted(archive.namelist()) == [f"{name}.csv", f"{name}.manifest.json"]

    waiting = _gate(world)
    assert (waiting.status.value, waiting.count, waiting.detail) == (
        "FAILED",
        1,
        "Unacknowledged batches: 1",
    )
    # no batch is failed any more: the run is an exported run, and stays one
    exported = _cancel(world, run["id"])
    assert (exported.status_code, exported.json()["detail"]) == (
        409,
        "A journal run can be cancelled only before it is exported.",
    )

    recorded = post(
        world.app,
        f"{BATCHES}/{failed['id']}/acknowledge",
        maya,
        {"gl_document_id": "JE-NS-MANUAL-7", "gl_posted_date": "2023-02-28"},
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["ack_kind"] == "MANUAL_CONFIRMATION"
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    # acknowledged, the batch still says that — and when — it was handed over
    read = get(world.app, f"{BATCHES}/{failed['id']}", maya)
    assert read.status_code == 200 and read.json()["handed_over_at"] == instant
    assert (_gate(world).status.value, _gate(world).count) == ("PASSED", 0)
    assert mock.posting_count == 1  # eRev sent nothing more: the second document is the person's


@pytest.mark.slow
def test_a_run_with_a_batch_handed_out_is_not_cancelled(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD ERR-74, "or that was handed out": with both chunks failed the run could be cancelled,
    but once one of them was handed over its file is outside eRev — a person may have posted it —
    so the cancel is refused by that batch's name and the other failed batch leaves by a retry or
    by its own hand-over."""
    mock, run, [first, second] = _failed_run(world, monkeypatch, clock, chunks=2, refused=2)
    maya = world.legacy.maya
    accepted = post(world.app, f"{BATCHES}/{first['id']}/hand-over", maya, {})
    assert accepted.status_code == 202, accepted.text
    assert _work(world, accepted.json()["id"])["result"]["outcome"] == "HANDED_OVER"
    # SMAP-08: a failed batch beside an exported one rolls the run up to ``exported``
    assert _states(world, run["id"]) == ("exported", ["exported", "failed"])

    refused = _cancel(world, run["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == (
        f"Journal run {run['run_no']} has a batch that a ledger holds or that was handed out "
        f"({first['external_id']}). Retry its failed batch, or hand it over for manual posting."
    )

    retried = post(world.app, f"{BATCHES}/{second['id']}/retry", maya, {})
    assert retried.status_code == 202, retried.text
    _work(world, retried.json()["id"])
    assert _states(world, run["id"]) == ("exported", ["exported", "acknowledged"])
    assert mock.posting_count == 1 and mock.journal(first["external_id"]) is None


class _RefusingCsv(CsvGl):
    """eRev's own check refuses the chunk before a file exists (05 ADP-12 ``Permanent``)."""

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        raise ports.Permanent("Account 5001 is not in the chart of accounts.")


@pytest.mark.slow
def test_a_csv_batch_is_not_handed_over_and_its_failed_run_is_cancelled_without_a_ledger(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``CSV`` batch fails only before a file exists, so there is no ledger to ask: the
    hand-over is refused by name, and the cancel's job asks nobody and cancels."""
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, _RefusingCsv)
    run = _approved(world)
    [batch] = run["batches"]
    assert batch["adapter"] == "CSV"
    _exported(world, run["id"])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    maya = world.legacy.maya

    refused = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == (
        "A CSV batch is not handed over. Correct what its export named and retry it, or cancel "
        "the journal run."
    )

    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    finished = _work(world, accepted.json()["id"])
    assert (finished["state"], finished["result"]["outcome"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        "CANCELLED",
        {"asked": 0, "held": 0, "cancelled": 1},
    )
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"])
    assert _executions(world, batch["id"])[-1] == (
        "PASS",
        {"status": "cancelled", "ack_kind": None, "gl_document_id": None, "ledger_asked": False},
    )


@pytest.mark.slow
def test_a_ledger_that_cannot_be_asked_is_a_refusal_not_a_failed_attempt(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``cancel`` rev 1.159: "could not be reached" is a failed attempt the schedule
    repeats; "cannot be asked" is a decision. When the ledger refuses the question itself, or the
    batch's connection is disabled, the job ends with the refusal in its result at once, nothing
    is changed and nobody is asked for a disabled connection; with the connection enabled again
    and the ledger answering, the same cancel is done."""
    mock = _netsuite(world, monkeypatch)
    admin = _admin(world, clock)
    connection = _connection(world, admin)
    run = _approved(world)
    [batch] = run["batches"]
    _faults(world, "PERMANENT_ERROR")
    _exported(world, run["id"])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    asked = _asked(monkeypatch)

    def refused(sentence: str) -> None:
        accepted = _cancel(world, run["id"])
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["id"]
        finished = _work(world, job_id)
        assert (finished["state"], finished["result"]["outcome"], finished["problem"]) == (
            "SUCCEEDED_WITH_EXCEPTIONS",
            "NOT_CANCELLED",
            None,
        )
        assert finished["result"]["counts"] == {"asked": 0, "held": 0, "cancelled": 0}
        assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
        assert _states(world, run["id"]) == ("failed", ["failed"])
        assert _receipts(world, run) == [(1, "REJECTED", None)]

    # the ledger refuses the question: its answer is a decision, no attempt is repeated
    _faults(world, "PERMANENT_ERROR")
    refused("The ledger could not be asked, so nothing was changed: NetSuite answered HTTP 400.")
    assert asked == [batch["external_id"]]

    # the batch's connection is disabled: there is nobody to ask, and nobody is asked
    path = f"{INTEGRATIONS}/{connection['id']}"
    disabled = patch(
        world.app, path, admin, {"status": "DISABLED"}, if_match=f'"r{connection["row_version"]}"'
    )
    assert disabled.status_code == 200, disabled.text
    asked.clear()
    refused(
        "The ledger could not be asked, so nothing was changed: general ledger connection "
        "netsuite-mock is disabled."
    )
    assert asked == []
    assert [item["outcome"] for item in _events(world, run["id"], "journal_run.cancel")] == [
        "DENIED",
        "DENIED",
    ]

    enabled = patch(
        world.app,
        path,
        admin,
        {"status": "ACTIVE"},
        if_match=f'"r{disabled.json()["row_version"]}"',
    )
    assert enabled.status_code == 200, enabled.text
    again = _cancel(world, run["id"])
    assert again.status_code == 202, again.text
    assert _work(world, again.json()["id"])["result"]["outcome"] == "CANCELLED"
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0


# --- beside a retry -------------------------------------------------------------------------------


@pytest.mark.slow
def test_a_batch_being_sent_is_neither_handed_over_nor_its_run_cancelled(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Rulings R-75 and R-112 (c): while a relay holds the message of a retried batch the ledger
    is, or may have been, called, and only the ledger knows the outcome. Neither exit of the
    failed batch is taken beside it: the hand-over and the cancel each answer 409 naming the
    batch, and no job is started. Nor is the batch retried again beside the claim (04 §16.7
    ``retry`` rev 1.221): the command answers 409 and starts no job either."""
    _, run, [batch] = _failed_run(world, monkeypatch, clock)
    maya = world.legacy.maya
    retry = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert retry.status_code == 202, retry.text
    current = _stored(world, batch["id"])["outbox_message_id"]
    # the relay claims the retry's message and has not come back yet
    claimed = outbox._claim(_relayer(world), message_id=current, topic=OutboxTopic.JOURNAL_EXPORT)
    assert claimed is not None and claimed.id == current
    jobs = _export_jobs(world, run["id"])

    again = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert (again.status_code, again.json()["detail"]) == (
        409,
        RETRY_BEING_SENT.format(external_id=batch["external_id"]),
    )
    assert _stored(world, batch["id"])["outbox_message_id"] == current

    handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert (handed.status_code, handed.json()["detail"]) == (
        409,
        f"Batch {batch['external_id']} is being sent. It cannot be handed over while it is "
        "being sent.",
    )
    cancelled = _cancel(world, run["id"])
    assert (cancelled.status_code, cancelled.json()["detail"]) == (
        409,
        commands.EXPORT_IN_PROGRESS.format(external_id=batch["external_id"]),
    )
    assert _export_jobs(world, run["id"]) == jobs
    assert _states(world, run["id"]) == ("failed", ["failed"])


@pytest.mark.slow
def test_a_cancel_waits_for_a_retry_and_is_not_asked_twice(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Ruling R-112 (c): "no message of the run is claimed or pending". While the retry of a
    failed batch waits to be sent the cancel answers 409 and starts no job — the relay will call
    the ledger; once the retry has ended the cancel is accepted, and a second cancel is refused
    while the first is under way."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    maya = world.legacy.maya
    retry = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert retry.status_code == 202, retry.text
    jobs = _export_jobs(world, run["id"])

    waits = _cancel(world, run["id"])
    assert (waits.status_code, slug(waits)) == (409, "invalid-transition"), waits.text
    assert waits.json()["detail"] == CANCEL_WAITS.format(external_id=batch["external_id"])
    handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert (handed.status_code, handed.json()["detail"]) == (
        409,
        f"Batch {batch['external_id']} is waiting to be sent again. It cannot be handed over "
        "until that retry has ended.",
    )
    assert _export_jobs(world, run["id"]) == jobs

    _faults(world, "PERMANENT_ERROR")  # the retry asks the ledger first and is refused again
    _work(world, retry.json()["id"])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _stored(world, batch["id"])["attempt_count"] == 2

    first = _cancel(world, run["id"])
    assert first.status_code == 202, first.text
    second = _cancel(world, run["id"])
    assert (second.status_code, second.json()["detail"]) == (
        409,
        "A cancellation of this journal run is already under way.",
    )
    assert _work(world, first.json()["id"])["result"]["outcome"] == "CANCELLED"
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0
    # the job has ended: the question is whether the run can be cancelled, and it no longer can
    third = _cancel(world, run["id"])
    assert (third.status_code, slug(third)) == (409, "invalid-transition"), third.text


@pytest.mark.slow
@pytest.mark.parametrize("sent", [True, False], ids=["sent-again", "still-to-be-sent"])
def test_a_batch_sent_again_while_the_ledger_is_asked_is_not_cancelled(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock, sent: bool
) -> None:
    """The answer of the ledger is good for the batch as it stood when it was asked. The job's
    own transaction therefore decides again under the locks: a retry that ran between the
    question and that transaction may have reached the ledger — the batch's attempt count is no
    longer the one asked about — and a retry that still waits to be sent will reach it. Either
    way nothing is cancelled and the job says why; asked again once the retry has ended, the run
    is cancelled."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    maya = world.legacy.maya
    original = netsuite.NetSuiteGl.get_posting
    retries: list[str] = []

    def retried_meanwhile(
        self: netsuite.NetSuiteGl, external_id: str
    ) -> ports.PostingResult | None:
        found = original(self, external_id)
        if not retries:
            # another person retries the batch while the cancel's job waits for the ledger
            retry = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
            assert retry.status_code == 202, retry.text
            retries.append(retry.json()["id"])
            if sent:
                _faults(world, "PERMANENT_ERROR")
                _work(world, retry.json()["id"])
        return found

    monkeypatch.setattr(netsuite.NetSuiteGl, "get_posting", retried_meanwhile)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    finished = _work(world, job_id)
    assert len(retries) == 1
    assert (finished["state"], finished["result"]["outcome"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_CANCELLED",
    )
    sentence = (
        f"Batch {batch['external_id']} was sent again while the ledger was asked, so nothing was "
        "changed. Ask again."
        if sent
        else CANCEL_WAITS.format(external_id=batch["external_id"])
    )
    assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _stored(world, batch["id"])["attempt_count"] == (2 if sent else 1)
    assert [item["outcome"] for item in _events(world, run["id"], "journal_run.cancel")] == [
        "DENIED"
    ]
    if not sent:
        _faults(world, "PERMANENT_ERROR")  # the retry ends: the ledger refuses the batch again
        _work(world, retries[0])
        assert _stored(world, batch["id"])["attempt_count"] == 2

    again = _cancel(world, run["id"])
    assert again.status_code == 202, again.text
    assert _work(world, again.json()["id"])["result"]["outcome"] == "CANCELLED"
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0
    assert [item["outcome"] for item in _events(world, run["id"], "journal_run.cancel")] == [
        "DENIED",
        "SUCCESS",
    ]


@pytest.mark.slow
def test_a_failed_run_under_a_later_run_is_not_cancelled(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Ruling R-52 (b) holds for a failed run as for an approved one: a run that was calculated
    after it for the same entity, book and period starts where the failed run ends, so the
    failed run's seals would be left to no run. The later run is cancelled first."""
    _, run, _ = _failed_run(world, monkeypatch, clock)
    post_lines(
        world,
        key="exit-later",
        contract_key=_pair(world)[0],
        period_key=FEBRUARY,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", "21001", "10.00", "POB #1"),
                    ("REVENUE", "5001", "-10.00", "POB #1"),
                ],
            )
        ],
    )
    later = _calculated(world)
    assert (later["state"], later["id"] != run["id"]) == ("draft", True)
    jobs = _export_jobs(world, run["id"])

    refused = _cancel(world, run["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == (
        f"Journal run {later['run_no']} was calculated after this run for the same entity, book "
        f"and period. Cancel {later['run_no']} first."
    )
    assert _export_jobs(world, run["id"]) == jobs

    first = _cancel(world, later["id"])
    assert (first.status_code, first.json()["state"]) == (200, "cancelled"), first.text
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    assert _work(world, accepted.json()["id"])["result"]["outcome"] == "CANCELLED"
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"])


# --- the recount ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_a_batch_that_gained_a_line_is_neither_handed_over_nor_downloaded(
    world: JournalWorld,
    monkeypatch: pytest.MonkeyPatch,
    clock: FrozenClock,
    committed_db: TestDatabase,
) -> None:
    """PRD ERR-79 and the hand-over's recount (05 ADP-31; security finding N2 (a)): a batch is
    rendered from its lines wherever no stored file exists, so every such way out counts and
    totals them against the figures the run was approved with. A line added behind the commands
    refuses the download (409) and the hand-over (``result.refusal``); the batch stays ``failed``
    without a file. Since revision 0104 the application's role cannot add that line — the batch
    is not ``draft`` (04 DB-16 ``tg_journal_line__batch_draft``, ``EREV-JE-003``) — so it is
    written behind the guard: the recount is the layer that stands when the guard is passed."""
    _, run, [batch] = _failed_run(world, monkeypatch, clock)
    maya = world.legacy.maya
    batch_id = UUID(batch["id"])
    path = f"{BATCHES}/{batch['id']}/download"
    rendered = get(world.app, path, maya)
    assert rendered.status_code == 200, rendered.text  # control: the approved lines download

    with tenant_session(_context(world), read_only=True) as session:
        copied = dict(
            session.execute(
                select(journal_line).where(
                    journal_line.c.journal_batch_id == batch_id,
                    journal_line.c.gl_account_code == "21001",
                )
            )
            .mappings()
            .one()
        )
    copied.update(id=new_id(), line_no=99)
    with pytest.raises(DBAPIError) as guarded, tenant_session(_context(world)) as session:
        session.execute(insert(journal_line).values(**copied))
    assert str(guarded.value.orig.diag.message_primary) == (
        f"EREV-JE-003: journal batch {batch['id']} is failed, so journal line {copied['id']} "
        "cannot join it: a batch takes lines only while it is draft"
    )
    insert_behind_the_guard(committed_db, _context(world), copied)
    differs = (
        f"Batch {batch['external_id']} differs from what was calculated and approved: lines 4, "
        "stored 3; transaction debits 300.00 USD, stored 150.00; functional debits 300.00 USD, "
        "stored 150.00."
    )

    refused = get(world.app, path, maya)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == f"{differs} It cannot be downloaded."
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        ("lines", "BATCH_RECOUNT", f"{differs} It cannot be downloaded.")
    ]

    accepted = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]["outcome"], finished["result"]["counts"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_HANDED_OVER",
        {"asked": 1, "held": 0, "handed_over": 0},
    )
    assert _refusal(finished, job_id) == (
        TRANSITION,
        f"{differs} It cannot be handed over.",
        [("lines", "BATCH_RECOUNT")],
    )
    stored = _stored(world, batch["id"])
    assert (str(stored["state"]), stored["export_file_id"], stored["exported_at"]) == (
        "failed",
        None,
        None,
    )
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert [
        (item["action"], item["outcome"])
        for item in _events(world, batch["id"], "journal_batch.hand_over")
    ] == [("journal_batch.hand_over", "DENIED")]
    [row] = _rows(world, select(journal_run.c.state).where(journal_run.c.id == UUID(run["id"])))
    assert str(row["state"]) == "failed"


# --- a dispatch that dies of an error of eRev's own (item JRN-DISPATCH-DEAD-1) --------------------


def _impatient(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ADP-12 schedule without its waits: every attempt is due at once, so the clock — and
    with it the sessions of the world — stays where it is while the schedule runs out."""
    monkeypatch.setitem(
        outbox.SCHEDULES,
        OutboxTopic.JOURNAL_EXPORT,
        outbox.DispatchSchedule(
            max_attempts=export.RETRY_ATTEMPTS, delay=lambda attempt: timedelta(0)
        ),
    )


def _raising(error: Exception) -> Callable[..., Any]:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise error

    return refuse


def _message(world: JournalWorld, batch_id: str) -> dict[str, Any]:
    """The batch's export message."""
    [row] = _rows(
        world,
        select(outbox_message).where(
            outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value,
            outbox_message.c.aggregate_id == UUID(batch_id),
        ),
    )
    return row


def _relayed(world: JournalWorld, message: dict[str, Any], times: int = 1) -> list[RelayStats]:
    return [
        outbox.relay_messages(_relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT)
        for _ in range(times)
    ]


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_dispatch_that_dies_of_an_error_of_its_own_leaves_a_failed_batch(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Item JRN-DISPATCH-DEAD-1 (rulings R-118 (k) and R-119 (c); 05 ADP-31 rev 1.98), as
    measured: the ledger accepts the chunk and the transaction that records its receipt is
    cancelled at every attempt of the ADP-12 schedule. Until this item the message died
    ``DEAD | 8 | Problem`` beside a batch that stayed ``approved`` — nothing sent it again, no
    retry or hand-over applied, and the cancel of the run answered 200 although the ledger held
    the chunk, so the recalculated run would have posted the period twice. Now the relay's last
    failed attempt records the batch ``failed`` whatever the class of the error, naming the
    problem, and the cancel asks the ledger: it finds the document, acknowledges the batch and
    cancels nothing."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    message = _message(world, batch["id"])
    _impatient(monkeypatch)
    cancelled = Problem("statement-timeout", STATEMENT_TIMEOUT_DETAIL)
    with monkeypatch.context() as broken:
        broken.setattr(export, "record_posting", _raising(cancelled))
        attempts = _relayed(world, message, export.RETRY_ATTEMPTS)
    assert attempts == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)] * 7 + [
        RelayStats(claimed=1, dispatched=0, failed=0, dead=1)
    ]
    assert mock.posting_count == 1  # the ledger took the chunk at the first attempt

    dead = _message(world, batch["id"])
    assert (dead["status"], dead["attempt_count"], dead["last_error"]) == (
        "DEAD",
        8,
        "statement-timeout",
    )
    sentence = (
        "eRev could not complete the export (statement-timeout); the ledger may hold the batch."
    )
    stored = _stored(world, batch["id"])
    assert (str(stored["state"]), stored["attempt_count"], stored["last_error"]) == (
        "failed",
        1,
        sentence,
    )
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _receipts(world, run) == [(1, "REJECTED", None)]
    assert _items(world, batch) == [("OPEN", None)]
    assert _executions(world, batch["id"]) == [
        ("FAIL", {"status": "failed", "ack_kind": "REJECTED", "gl_document_id": None})
    ]
    # PRD NTF-10 rev 1.133: the ledger rejected nothing, and the notification does not say so
    notified = _rows(
        world,
        select(notification.c.title, notification.c.body, notification.c.subject_id).where(
            notification.c.kind == "EXPORT_FAILED"
        ),
    )
    assert {(row["title"], row["body"], str(row["subject_id"])) for row in notified} == {
        (
            f"Journal export failed: {run['run_no']}",
            "eRev could not complete the export through NETSUITE (statement-timeout); the "
            "ledger may hold the batch. Retry it: a retry asks the ledger first, so nothing "
            "posts twice.",
            batch["id"],
        )
    }

    # the cancel no longer decides on stored facts: its job asks the ledger and finds the document
    # — 15 minutes on, since the message did not die of the ledger's refusal (04 §16.7 rev 1.247;
    # item JRN-EXIT-SETTLE-1: until then the cancel answers 409)
    clock.advance(WAIT)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]["outcome"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_CANCELLED",
    )
    assert _refusal(finished, job_id)[1] == (
        f"{LEDGER} holds batch {batch['external_id']} as JE-NS-88001. The batch is acknowledged "
        f"and journal run {run['run_no']} is not cancelled."
    )
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "REJECTED", None), (1, "DUPLICATE", "JE-NS-88001")]
    assert mock.posting_count == 1


@pytest.mark.slow
def test_a_message_is_not_dead_while_its_batch_cannot_be_recorded_failed(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Item JRN-DISPATCH-DEAD-1 (05 ADP-31, ADP-32 rev 1.98): when the cause sits on the run's own
    rows — here the read under the run and batch locks answers ``lock-conflict`` every time — the
    record of the failure cannot be written either. The message is then not settled: it stays
    claimed after the last attempt, so the batch is not left ``approved`` beside a dead message
    and the run is not cancelled meanwhile; once the lock is gone the relay takes the message
    again after 15 minutes and the dispatch completes."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    message = _message(world, batch["id"])
    _impatient(monkeypatch)
    held = Problem("lock-conflict", LOCK_CONFLICT_DETAIL)
    with monkeypatch.context() as broken:
        broken.setattr(export, "_locked_batch", _raising(held))
        attempts = _relayed(world, message, export.RETRY_ATTEMPTS)
    assert attempts == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)] * 7 + [
        RelayStats(claimed=1, dispatched=0, failed=0, dead=0)
    ]
    claimed = _message(world, batch["id"])
    assert (claimed["status"], claimed["attempt_count"], claimed["last_error"]) == (
        "DISPATCHING",
        7,
        "lock-conflict",
    )
    stored = _stored(world, batch["id"])
    assert (str(stored["state"]), stored["attempt_count"], stored["last_error"]) == (
        "approved",
        0,
        None,
    )
    assert _states(world, run["id"]) == ("approved", ["approved"]) and mock.posting_count == 0
    # a claimed message refuses the cancel of its run, whatever its age (ruling R-75)
    refused = _cancel(world, run["id"])
    assert (refused.status_code, refused.json()["detail"]) == (
        409,
        commands.EXPORT_IN_PROGRESS.format(external_id=batch["external_id"]),
    )
    assert _relayed(world, message) == [RelayStats(claimed=0, dispatched=0, failed=0, dead=0)]

    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=1, failed=0, dead=0)]
    done = _message(world, batch["id"])
    assert (done["status"], done["attempt_count"], done["last_error"]) == ("DISPATCHED", 7, None)
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "POSTED", "JE-NS-88001")] and mock.posting_count == 1


# --- a run without a failed batch, after an attempt (item JRN-CANCEL-APPROVED-PENDING-1) ----------


def _cancel_events(world: JournalWorld, run_id: str) -> list[str]:
    """The actions of the run's cancel events: the request of a failed run's cancel and the
    decision."""
    return [
        item["action"]
        for item in _events(world, run_id, "journal_run.")
        if item["action"] in ("journal_run.request_cancel", "journal_run.cancel")
    ]


@pytest.mark.slow
def test_an_approved_run_is_not_cancelled_after_an_attempt_the_ledger_took(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``cancel`` (c) rev 1.204 (item JRN-CANCEL-APPROVED-PENDING-1; ruling R-119 (c)),
    as measured: the first attempt to send the chunk times out after the ledger stored the
    journal. The message is ``FAILED`` and due again, no relay holds it and the batch still reads
    ``approved`` — until this item the cancel answered 200 here, and the run calculated next would
    have posted the period a second time under new external ids. The cancel is now refused by the
    batch's name and changes nothing; the next attempt asks the ledger before it sends, finds the
    document and acknowledges batch and run, and the ledger holds one posting."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    message = _message(world, batch["id"])
    asked = _asked(monkeypatch)
    _faults(world, "TIMEOUT")
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)]
    due = _message(world, batch["id"])
    assert (due["status"], due["attempt_count"], due["last_error"]) == ("FAILED", 1, "Transient")
    # the ledger holds the chunk; eRev has no receipt, no claim and an approved batch
    assert mock.posting_count == 1 and asked == []
    assert _states(world, run["id"]) == ("approved", ["approved"])
    assert _receipts(world, run) == []
    jobs = _export_jobs(world, run["id"])

    refused = _cancel(world, run["id"])
    assert refused.status_code == 409, refused.text  # before the item: 200
    sentence = CANCEL_ATTEMPTED.format(external_id=batch["external_id"])
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        ("state", "E-34", sentence)
    ]
    assert _states(world, run["id"]) == ("approved", ["approved"])
    assert _export_jobs(world, run["id"]) == jobs and _cancel_events(world, run["id"]) == []

    # the message is due again 30 seconds after its first failure, not before (ADP-12)
    assert _relayed(world, message) == [RelayStats(claimed=0, dispatched=0, failed=0, dead=0)]
    clock.advance(export.export_delay(1))
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=1, failed=0, dead=0)]
    assert asked == [batch["external_id"]] and mock.posting_count == 1
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "POSTED", "JE-NS-88001")]
    late = _cancel(world, run["id"])
    assert (late.status_code, late.json()["detail"]) == (409, BEFORE_EXPORT)


@pytest.mark.slow
def test_a_run_refused_after_a_failed_attempt_is_cancelled_once_its_batch_has_failed(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """The way on from refusal (c): "until the batch has been sent or has failed". Here the
    ledger never answers. The cancel is refused after each of the seven attempts that leave the
    message due again — the product cannot tell an attempt the ledger never saw from one it took;
    the eighth attempt of the ADP-12 schedule leaves batch and run ``failed`` (05 ADP-31), and the
    cancel of the failed run answers 202, asks the ledger, finds nothing and cancels."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    message = _message(world, batch["id"])
    _impatient(monkeypatch)
    _faults(world, "SERVER_ERROR", export.RETRY_ATTEMPTS)
    sentence = CANCEL_ATTEMPTED.format(external_id=batch["external_id"])
    for attempt in range(1, export.RETRY_ATTEMPTS):
        assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)]
        refused = _cancel(world, run["id"])
        assert (refused.status_code, refused.json()["detail"]) == (409, sentence), attempt
    assert _states(world, run["id"]) == ("approved", ["approved"])
    assert _cancel_events(world, run["id"]) == []

    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=0, failed=0, dead=1)]
    assert _states(world, run["id"]) == ("failed", ["failed"]) and mock.posting_count == 0
    # the ledger never answered, so it is asked 15 minutes after the last attempt and not before
    # (04 §16.7 rev 1.247; item JRN-EXIT-SETTLE-1: until then the cancel answers 409)
    clock.advance(WAIT)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    finished = _work(world, accepted.json()["id"])
    assert (finished["state"], finished["result"]["outcome"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        "CANCELLED",
        {"asked": 1, "held": 0, "cancelled": 1},
    )
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0
    assert _cancel_events(world, run["id"]) == ["journal_run.request_cancel", "journal_run.cancel"]


@pytest.mark.slow
def test_the_cancel_names_the_batch_that_was_attempted_not_one_never_sent(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Refusal (c) reads what was attempted, not what waits: of two chunks the second was sent
    once and the ledger did not answer, while no relay has claimed the first chunk's message
    (``PENDING`` — nothing was sent for it, and it refuses nothing). The cancel names the second
    batch. A batch being sent is named before it (refusal (b))."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    run = _approved(world)
    first, second = sorted(run["batches"], key=lambda item: item["chunk_no"])
    _faults(world, "SERVER_ERROR")
    attempted = _relayed(world, _message(world, second["id"]))
    assert attempted == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)]
    waiting = _message(world, first["id"])
    assert [waiting["status"], _message(world, second["id"])["status"]] == ["PENDING", "FAILED"]

    refused = _cancel(world, run["id"])
    assert (refused.status_code, refused.json()["detail"]) == (
        409,
        CANCEL_ATTEMPTED.format(external_id=second["external_id"]),
    )
    assert _states(world, run["id"]) == ("approved", ["approved", "approved"])

    claimed = outbox._claim(
        _relayer(world), message_id=waiting["id"], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert claimed is not None and claimed.id == waiting["id"]
    sending = _cancel(world, run["id"])
    assert (sending.status_code, sending.json()["detail"]) == (
        409,
        commands.EXPORT_IN_PROGRESS.format(external_id=first["external_id"]),
    )
    assert _states(world, run["id"]) == ("approved", ["approved", "approved"])
    assert mock.posting_count == 0


@pytest.mark.slow
def test_a_retry_due_again_refuses_the_exits_of_its_batch_and_not_of_another(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Ruling R-112 (c) for a retry that was attempted: of two failed chunks the second is
    retried, the ledger does not answer, and the retry's message is ``FAILED`` and due again.
    Like a retry no relay has taken yet it refuses the cancel of the run and the hand-over of its
    own batch — the relay will call the ledger again. It does not refuse the hand-over of the
    other failed batch, whose message is settled."""
    _, run, [first, second] = _failed_run(world, monkeypatch, clock, chunks=2, refused=2)
    maya = world.legacy.maya
    retry = post(world.app, f"{BATCHES}/{second['id']}/retry", maya, {})
    assert retry.status_code == 202, retry.text
    current = _stored(world, second["id"])["outbox_message_id"]
    _faults(world, "SERVER_ERROR")
    stats = outbox.relay_messages(_relayer(world), [current], topic=OutboxTopic.JOURNAL_EXPORT)
    assert stats == RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
    assert [_message_status(world, item["id"]) for item in (first, second)] == ["DEAD", "FAILED"]
    jobs = _export_jobs(world, run["id"])

    waits = _cancel(world, run["id"])
    assert (waits.status_code, waits.json()["detail"]) == (
        409,
        CANCEL_WAITS.format(external_id=second["external_id"]),
    )
    own = post(world.app, f"{BATCHES}/{second['id']}/hand-over", maya, {})
    assert (own.status_code, own.json()["detail"]) == (
        409,
        f"Batch {second['external_id']} is waiting to be sent again. It cannot be handed over "
        "until that retry has ended.",
    )
    assert _export_jobs(world, run["id"]) == jobs
    assert _states(world, run["id"]) == ("failed", ["failed", "failed"])
    other = post(world.app, f"{BATCHES}/{first['id']}/hand-over", maya, {})
    assert other.status_code == 202, other.text


def _message_status(world: JournalWorld, batch_id: str) -> str:
    """The status of the batch's current export message (``outbox_message_id``)."""
    [row] = _rows(
        world,
        select(outbox_message.c.status).where(
            outbox_message.c.id == _stored(world, batch_id)["outbox_message_id"]
        ),
    )
    return str(row["status"])


@contextmanager
def _message_reads() -> Iterator[list[str]]:
    """The statements that read the export messages of a run's batches — ``journal_batch`` joined
    to ``outbox_message`` — while the block runs."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        if "journal_batch JOIN" in statement and "outbox_message ON" in statement:
            seen.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


@pytest.mark.slow
def test_a_cancel_reads_the_messages_of_its_run_once(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``cancel`` (c) rev 1.204: what a cancel or a hand-over decides about the export
    messages of its run it reads in ONE statement under its locks. A relay claims a message
    without those locks, so two reads — one for a claimed message, one for a message due again —
    see two snapshots, and a message claimed between them is missed by both: the batch would be
    cancelled, or handed over, beside a dispatch that follows an attempt the ledger may have
    taken. Counted for the cancel of an approved run, for the cancel of a failed run and for the
    hand-over, each at the command and in the job's own deciding transaction. Before this item
    the two exits of a failed batch read twice."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    maya = world.legacy.maya
    counted: dict[str, int] = {}

    # an approved run none of whose messages a relay has claimed is cancelled at once
    run = _approved(world)
    assert _message(world, run["batches"][0]["id"])["status"] == "PENDING"
    with _message_reads() as reads:
        cancelled = _cancel(world, run["id"])
    assert cancelled.status_code == 200, cancelled.text
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"])
    counted["the cancel of an approved run"] = len(reads)

    # a failed run: the command, and the job's last transaction, which decides again
    run = _approved(world)
    _faults(world, "PERMANENT_ERROR")
    _exported(world, run["id"])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    with _message_reads() as reads:
        accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    counted["the cancel of a failed run"] = len(reads)
    with _message_reads() as reads:
        finished = _work(world, accepted.json()["id"])
    assert finished["result"]["outcome"] == "CANCELLED", finished
    counted["its job"] = len(reads)

    # a hand-over: the command and its job
    run = _approved(world)
    [batch] = run["batches"]
    _faults(world, "PERMANENT_ERROR")
    _exported(world, run["id"])
    assert _states(world, run["id"]) == ("failed", ["failed"])
    with _message_reads() as reads:
        handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert handed.status_code == 202, handed.text
    counted["the hand-over"] = len(reads)
    with _message_reads() as reads:
        finished = _work(world, handed.json()["id"])
    assert finished["result"]["outcome"] == "HANDED_OVER", finished
    counted["the hand-over's job"] = len(reads)

    assert counted == {
        "the cancel of an approved run": 1,
        "the cancel of a failed run": 1,
        "its job": 1,
        "the hand-over": 1,
        "the hand-over's job": 1,
    }
    assert mock.posting_count == 0


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_failed_batch_the_ledger_holds_is_acknowledged_and_not_handed_over(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD ERR-73, its second ending (04 §16.7 ``hand-over`` rev 1.159; 05 ADP-33): the hand-over
    asks the ledger as the cancel does. The ledger took the failed chunk through an attempt whose
    answer was lost, so the job records the ``DUPLICATE`` receipt with the ledger's document, the
    batch — and, its other chunk being acknowledged, the run — is ``acknowledged``, no file is
    stored, and the job ends ``SUCCEEDED_WITH_EXCEPTIONS`` with ``result.outcome``
    ``NOT_HANDED_OVER`` and the refusal; a ``journal_batch.hand_over`` event with outcome
    ``DENIED`` records it."""
    mock, run, [failed, posted] = _failed_run(world, monkeypatch, clock, chunks=2)
    maya = world.legacy.maya
    document = _lost_posting(world, failed)
    assert (document, mock.posting_count) == ("JE-NS-88002", 2)
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])
    before = _stored(world, failed["id"])

    accepted = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", maya, {})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    finished = _work(world, job_id)
    assert (finished["state"], finished["problem"]) == ("SUCCEEDED_WITH_EXCEPTIONS", None)
    assert (finished["result"]["outcome"], finished["result"]["counts"]) == (
        "NOT_HANDED_OVER",
        {"asked": 1, "held": 1, "handed_over": 0},
    )
    sentence = (
        f"{LEDGER} holds batch {failed['external_id']} as JE-NS-88002. The batch is acknowledged "
        "and is not handed over."
    )
    assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    assert _receipts(world, run) == [
        (1, "REJECTED", None),
        (1, "DUPLICATE", "JE-NS-88002"),
        (2, "POSTED", "JE-NS-88001"),
    ]
    # nothing was handed out: no file, and the ledger holds what it held
    after = _stored(world, failed["id"])
    assert (after["export_file_id"], after["attempt_count"]) == (
        None,
        before["attempt_count"] + 1,
    )
    assert mock.posting_count == 2
    assert _items(world, failed) == [("RESOLVED", "The ledger holds the batch as JE-NS-88002.")]
    assert _executions(world, failed["id"])[-1] == (
        "PASS",
        {"status": "acknowledged", "ack_kind": "DUPLICATE", "gl_document_id": "JE-NS-88002"},
    )
    decisions = _events(world, failed["id"], "journal_batch.hand_over")
    assert [(item["outcome"], item["actor_kind"]) for item in decisions] == [("DENIED", "SYSTEM")]
    # ``field`` and ``counts`` since 04 rev 1.246, as on the cancel's event
    assert decisions[0]["detail"] == {
        "problem": "invalid-transition",
        "field": "state",
        "rule_id": "E-34",
        "message": sentence,
        "job_id": job_id,
        "counts": {"asked": 1, "held": 1, "handed_over": 0},
    }
    late = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", maya, {})
    assert (late.status_code, late.json()["detail"]) == (
        409,
        "Only a failed batch can be handed over.",
    )
    assert (_gate(world).status.value, _gate(world).count) == ("PASSED", 0)


# --- a retry beside a message that is not settled (item JRN-RETRY-CLAIMED-1) ----------------------


def _export_messages(world: JournalWorld, batch_id: str) -> list[tuple[str, str, int]]:
    """(dedupe key, status, attempts) of every export message written for the batch: the first
    under the batch's external id, a retry's under ``<external id>#<attempt count>``."""
    rows = _rows(
        world,
        select(outbox_message.c.dedupe_key, outbox_message.c.status, outbox_message.c.attempt_count)
        .where(
            outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value,
            outbox_message.c.aggregate_id == UUID(batch_id),
        )
        .order_by(outbox_message.c.dedupe_key),
    )
    return [(str(row["dedupe_key"]), str(row["status"]), int(row["attempt_count"])) for row in rows]


def _stopped_after_the_failure(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> tuple[ns_mock.NetSuiteMock, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """An approved February run of one NetSuite chunk that the ledger refused, whose worker
    stopped between the two transactions that end such a dispatch (05 ADP-32 rev 1.160): the dead
    hook committed the batch ``failed``, and the record of the message's ``DEAD`` was never
    written — the message is still ``DISPATCHING``. (the mock, the run, the batch, the message)."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    message = _message(world, batch["id"])
    _faults(world, "PERMANENT_ERROR")
    with monkeypatch.context() as broken:
        broken.setattr(outbox, "_record", _raising(RuntimeError("the worker stopped")))
        with pytest.raises(RuntimeError, match="the worker stopped"):
            _relayed(world, message)
    assert _states(world, run["id"]) == ("failed", ["failed"])
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "DISPATCHING", 0)]
    assert (_stored(world, batch["id"])["attempt_count"], mock.posting_count) == (1, 0)
    return mock, run, batch, message


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_a_batch_whose_message_is_claimed_is_not_retried(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``retry`` rev 1.221 (item JRN-RETRY-CLAIMED-1; the supervisor's ruling of
    2026-10-01 08:31; a PRODUCT DEFECT of BUILD_SPEC CLO-14), as measured: the batch is ``failed``
    and its message still claimed. Until this item the retry answered 202 and wrote a second
    message, which the batch then named; the first, still due to be dispatched, was the batch's
    message for no cancel and no hand-over — the retry refused by the ledger as well, the cancel
    of the run was accepted beside the claim and done by its job, and the first message's
    dispatch posted: a cancelled run with a journal in the ledger. Now the retry answers 409 by
    the batch's name and writes nothing — the claimed message is the retry. Neither exit is taken
    beside the claim; 15 minutes after it the message is dispatched again, as a retry: it asks
    the ledger first, posts, and batch and run are ``acknowledged`` with one posting."""
    mock, run, batch, message = _stopped_after_the_failure(world, monkeypatch, clock)
    maya = world.legacy.maya
    jobs = _export_jobs(world, run["id"])

    refused = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert refused.status_code == 409, refused.text  # before the item: 202
    sentence = RETRY_BEING_SENT.format(external_id=batch["external_id"])
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        ("state", "E-34", sentence)
    ]
    # nothing was written: one message, which the batch names; no job and no retry event
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "DISPATCHING", 0)]
    assert _stored(world, batch["id"])["outbox_message_id"] == message["id"]
    assert _export_jobs(world, run["id"]) == jobs
    assert _events(world, batch["id"], "journal_batch.retry") == []

    # neither exit of the failed batch is taken beside the claim (rulings R-75 and R-112 (c))
    handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert (handed.status_code, handed.json()["detail"]) == (
        409,
        f"Batch {batch['external_id']} is being sent. It cannot be handed over while it is "
        "being sent.",
    )
    cancelled = _cancel(world, run["id"])
    assert (cancelled.status_code, cancelled.json()["detail"]) == (
        409,
        commands.EXPORT_IN_PROGRESS.format(external_id=batch["external_id"]),
    )
    assert _export_jobs(world, run["id"]) == jobs
    assert _states(world, run["id"]) == ("failed", ["failed"])

    # the claim is taken again 15 minutes after it was made, not before (ADP-32), and that
    # dispatch of a failed batch is the retry: the ledger is asked before anything is sent
    asked = _asked(monkeypatch)
    assert _relayed(world, message) == [RelayStats(claimed=0, dispatched=0, failed=0, dead=0)]
    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=1, failed=0, dead=0)]
    # asked twice: the question before the chunk is sent — the ledger holds nothing — and the
    # adapter's own read of the document it then stored
    assert asked == [batch["external_id"]] * 2 and mock.posting_count == 1
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "REJECTED", None), (1, "POSTED", "JE-NS-88001")]
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "DISPATCHED", 0)]
    assert _items(world, batch) == [("RESOLVED", "The batch was exported by a retry.")]
    late = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert (late.status_code, late.json()["detail"]) == (
        409,
        "Only a failed batch can be retried.",
    )


@pytest.mark.slow
def test_a_message_due_again_after_a_stop_is_the_retry_and_gets_no_second_message(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """The same stop, one step on (04 §16.7 ``retry`` rev 1.221): the message is taken again
    after its 15 minutes, the ledger does not answer, and the message is ``FAILED`` and due again
    beside the ``failed`` batch. It is the batch's FIRST message — its key is the external id, not
    a retry's ``<external id>#<attempt count>`` — so the retry command found no message of its
    own key and wrote a second one beside it, by the same road as beside a claim. Now the message
    the batch names is the retry while it is still to be sent or due again: the command answers
    202 as a repeated retry always did and writes no message; its job finds nothing due and says
    so — ``result.waiting`` names the batch and the instant its message is due (the supervisor's
    ruling of 2026-10-01 11:30: the message keeps its schedule); the exits are refused as beside
    any retry; and the message's next attempt posts."""
    mock, run, batch, message = _stopped_after_the_failure(world, monkeypatch, clock)
    maya = world.legacy.maya
    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    _faults(world, "SERVER_ERROR")
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)]
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "FAILED", 1)]
    assert _states(world, run["id"]) == ("failed", ["failed"]) and mock.posting_count == 0
    assert _stored(world, batch["id"])["attempt_count"] == 1
    due = clock.now() + export.export_delay(1)  # 30 seconds after the failed attempt (ADP-12)

    retry = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert retry.status_code == 202, retry.text
    # before the item: a second message, ``<external id>#1``, and the batch named that one
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "FAILED", 1)]
    assert _stored(world, batch["id"])["outbox_message_id"] == message["id"]
    finished = _work(world, retry.json()["id"])
    assert (finished["state"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        {"messages": 1, "claimed": 0, "dispatched": 0, "failed": 0, "dead": 0},
    )
    [waiting] = finished["result"]["waiting"]
    assert (waiting["journal_batch_id"], waiting["external_id"]) == (
        batch["id"],
        batch["external_id"],
    )
    assert _instant(waiting["next_attempt_at"]) == due
    retried = _events(world, batch["id"], "journal_batch.retry")
    assert [(item["outcome"], item["after"]["outbox_message_id"]) for item in retried] == [
        ("SUCCESS", str(message["id"]))
    ]

    # the exits read the message the batch names — the one that is due again
    waits = _cancel(world, run["id"])
    assert (waits.status_code, waits.json()["detail"]) == (
        409,
        CANCEL_WAITS.format(external_id=batch["external_id"]),
    )
    handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", maya, {})
    assert (handed.status_code, handed.json()["detail"]) == (
        409,
        f"Batch {batch['external_id']} is waiting to be sent again. It cannot be handed over "
        "until that retry has ended.",
    )

    clock.advance(export.export_delay(1))
    assert _relayed(world, message) == [RelayStats(claimed=1, dispatched=1, failed=0, dead=0)]
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "DISPATCHED", 1)]
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "REJECTED", None), (1, "POSTED", "JE-NS-88001")]
    assert mock.posting_count == 1


def _instant(value: str) -> datetime:
    """The instant of an RFC 3339 text in UTC as the API writes it (``…Z``)."""
    assert value.endswith("Z"), value
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


@pytest.mark.slow
def test_the_export_job_says_which_batches_wait_and_from_when(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 rev 1.221 (the supervisor's ruling of 2026-10-01 11:30): the ``JOURNAL_EXPORT``
    job of ``export`` and of ``retry`` names in ``result.waiting`` the batches it leaves to be
    sent again, each with the instant from which its message is due — so that its ending is not a
    bare success over a batch that was not sent. Of two chunks the ledger answers 500 for the
    first and takes the second: the job counts one failed and one dispatched and names the first
    chunk, due 30 seconds on (ADP-12). Asked again before that it claims nothing and names the
    chunk still; after it the chunk is sent and nothing waits. Before the member the three
    results differed in their counts alone."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    run = _approved(world)
    first, second = sorted(run["batches"], key=lambda item: item["chunk_no"])

    def exported() -> dict[str, Any]:
        requested = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/export", world.legacy.maya, {})
        assert requested.status_code == 202, requested.text
        finished = _work(world, requested.json()["id"])
        assert finished["state"] == "SUCCEEDED", finished
        return dict(finished["result"])

    _faults(world, "SERVER_ERROR")
    attempted = exported()
    assert attempted["counts"] == {
        "messages": 2,
        "claimed": 2,
        "dispatched": 1,
        "failed": 1,
        "dead": 0,
    }
    [waiting] = attempted["waiting"]
    assert sorted(waiting) == ["external_id", "journal_batch_id", "next_attempt_at"]
    assert (waiting["journal_batch_id"], waiting["external_id"]) == (
        first["id"],
        first["external_id"],
    )
    assert _instant(waiting["next_attempt_at"]) == clock.now() + export.export_delay(1)
    assert _states(world, run["id"])[1] == ["approved", "acknowledged"]

    again = exported()  # before the 30 seconds are over: nothing is due
    assert again["counts"] == {
        "messages": 2,
        "claimed": 0,
        "dispatched": 0,
        "failed": 0,
        "dead": 0,
    }
    assert again["waiting"] == attempted["waiting"]

    clock.advance(export.export_delay(1))
    sent = exported()
    assert sent["counts"] == {
        "messages": 2,
        "claimed": 1,
        "dispatched": 1,
        "failed": 0,
        "dead": 0,
    }
    assert sent["waiting"] == []
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    assert mock.posting_count == 2 and second["id"] != first["id"]


# --- a failed run in a closed period (item JR-CLOSED-PERIOD-GUARD-1; review finding F7) -----------

MARCH: Final = "FY2023-P03"
RUN_PERIOD_CLOSED: Final = "RUN_PERIOD_CLOSED"


def _locked_with_a_failed_batch(world: JournalWorld) -> str:
    """January and February 2023 of Mock Entity 1 ``closed`` while February's run stands
    ``failed`` — what a waiver of ``BATCHES_ACKNOWLEDGED`` leaves (the gate is waivable). Fixture
    state through the close domain's own writers, no gate evaluated (``periods_closed_before``).
    Returns the sentence PRD ERR-86 gives the cancel of that run."""
    maya = world.legacy.maya
    periods_closed_before(
        world.legacy.place(),
        world.app,
        maya,
        entity_id=world.entities[ENTITY_1],
        before=MARCH,
        entity_code=ENTITY_1,
    )
    (february,) = [
        item
        for item in periods(world.app, maya, entity=ENTITY_1)
        if item["period"]["period_key"] == FEBRUARY
    ]
    assert february["state"] == "closed", february
    return (
        f"{february['period']['name']} is closed for {ENTITY_1} in book {BOOK}. A journal run of "
        "a closed period cannot be cancelled."
    )


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_failed_run_of_a_closed_period_is_not_cancelled(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD ERR-86 for the exit of a failed run (04 §16.7 ``cancel`` (d) rev 1.205; item
    JR-CLOSED-PERIOD-GUARD-1; independent review of the failed-run exits, finding F7): a period
    can lock with a failed batch under a waiver, and the cancel of that run would leave its
    lines without a live run — none can be calculated until a reopen. The command reads the
    period's state row after the run row, the batch rows and the coverage lock
    (``failed_exits._standing``) and answers 409 ``period-closed``: no job is started and the
    ledger is not asked. Before the item it answered 202 and its job cancelled the run."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    sentence = _locked_with_a_failed_batch(world)
    jobs = _export_jobs(world, run["id"])
    asked = _asked(monkeypatch)

    refused = _cancel(world, run["id"])
    assert refused.status_code == 409, refused.text  # before the item: 202
    assert (slug(refused), refused.json()["detail"]) == ("period-closed", sentence)
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        (None, RUN_PERIOD_CLOSED, sentence)
    ]
    assert _export_jobs(world, run["id"]) == jobs and asked == []
    assert _states(world, run["id"]) == ("failed", ["failed"]) and mock.posting_count == 0
    assert _stored(world, batch["id"])["attempt_count"] == 1


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_cancel_accepted_before_the_lock_is_refused_by_its_job_after_it(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Finding F7, the job: the cancel of a failed run is accepted while February is open, and
    the period locks before the job runs. The job asks the ledger, which holds nothing, and its
    deciding transaction reads the period's state row as the command does: nothing is cancelled,
    the job ends ``SUCCEEDED_WITH_EXCEPTIONS`` with ``result.outcome`` ``NOT_CANCELLED`` and the
    problem of PRD ERR-86 as ``result.refusal``, and a ``journal_run.cancel`` event with outcome
    ``DENIED`` records it. Before the item the job cancelled the run of the closed period."""
    mock, run, [batch] = _failed_run(world, monkeypatch, clock)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    sentence = _locked_with_a_failed_batch(world)

    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]["outcome"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_CANCELLED",
    )  # before the item: SUCCEEDED, CANCELLED
    assert _refusal(finished, job_id) == (
        f"{TYPE_BASE}period-closed",
        sentence,
        [(None, RUN_PERIOD_CLOSED)],
    )
    assert _states(world, run["id"]) == ("failed", ["failed"]) and mock.posting_count == 0
    assert [item["outcome"] for item in _events(world, run["id"], "journal_run.cancel")] == [
        "DENIED"
    ]
    assert str(_stored(world, batch["id"])["state"]) == "failed"


@pytest.mark.slow
def test_the_export_of_a_closed_period_is_completed_by_the_three_batch_commands(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """PRD SM-08 "Retry export" rev 1.167 (the supervisor's ruling of 2026-10-01 on the
    acceptance of item JR-CLOSED-PERIOD-GUARD-1): a period that locked with failed batches under
    a waiver takes no calculation and no cancel of a run (ERR-86), and it still takes the three
    commands that complete the export of the population its lock certified. With both chunks of
    February's run failed and February closed, the first chunk is handed over, the second is
    retried — the ledger posts it and its receipt acknowledges it — and the first is
    acknowledged with the document a person posted: the run ends ``acknowledged`` batch by
    batch, and February is closed throughout."""
    mock, run, [first, second] = _failed_run(world, monkeypatch, clock, chunks=2, refused=2)
    sentence = _locked_with_a_failed_batch(world)
    maya = world.legacy.maya
    refused = _cancel(world, run["id"])
    assert (refused.status_code, refused.json()["detail"]) == (409, sentence), refused.text

    handed = post(world.app, f"{BATCHES}/{first['id']}/hand-over", maya, {})
    assert handed.status_code == 202, handed.text
    assert _work(world, handed.json()["id"])["result"]["outcome"] == "HANDED_OVER"
    assert _states(world, run["id"]) == ("exported", ["exported", "failed"])

    retried = post(world.app, f"{BATCHES}/{second['id']}/retry", maya, {})
    assert retried.status_code == 202, retried.text
    finished = _work(world, retried.json()["id"])
    assert (finished["state"], finished["result"]["waiting"]) == ("SUCCEEDED", [])
    assert _states(world, run["id"]) == ("exported", ["exported", "acknowledged"])
    assert mock.posting_count == 1 and mock.journal(first["external_id"]) is None

    recorded = post(
        world.app,
        f"{BATCHES}/{first['id']}/acknowledge",
        maya,
        {"gl_document_id": "JE-NS-MANUAL-7", "gl_posted_date": "2023-02-28"},
    )
    assert recorded.status_code == 201, recorded.text
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    (february,) = [
        item
        for item in periods(world.app, maya, entity=ENTITY_1)
        if item["period"]["period_key"] == FEBRUARY
    ]
    assert february["state"] == "closed", february


# --- an exit's job that is run again (item JRN-EXIT-JOB-IDEMPOTENT-1; review finding F10) ---------


def _handler_alone(world: JournalWorld, job_id: str) -> JobOutcome:
    """The job's handler run as the worker runs it, and its outcome dropped: the worker stopped
    after the handler returned and before the kernel recorded the job's end, which
    ``registry._execute`` does in a transaction of its own. The job's row stays as it was —
    ``RUNNING`` in a worker, which the sweeper queues again while attempts remain."""
    tenant_id = world.legacy.tenant_id
    with tenant_session(_context(world), read_only=True) as session:
        row = session.execute(
            select(job.c.params, job.c.created_by).where(job.c.id == UUID(job_id))
        ).one()
    # A context WITHOUT a job row (``persisted=False``): the handler commits what it decides
    # and nothing is written on the job's row, which stays as it was. Since 05 JOB-04 and
    # JOB-06 rev 1.200 a context with a job row is the registry's and runs as an attempt of
    # a RUNNING job; here the job is still QUEUED — no worker has taken it — so an attempt's
    # door would refuse the handler's first unit of work.
    jc = JobContext(
        job_id=UUID(job_id),
        tenant_id=tenant_id,
        kind=JobKind.JOURNAL_EXPORT,
        principal=system_principal(tenant_id, on_behalf_of_id=row.created_by),
        runtime=world.legacy.imports.runtime,
        persisted=False,
    )
    return export.export_job(jc, registry.handler_params(row.params))


@pytest.mark.slow
def test_a_cancel_job_that_is_run_again_returns_what_it_decided(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``cancel`` rev 1.246 (item JRN-EXIT-JOB-IDEMPOTENT-1; review finding F10): the
    handler cancels the run and the worker stops before the job's end is recorded, so the kernel
    runs the job again. Until this item the second attempt decided again: it found a cancelled
    run and ended ``SUCCEEDED_WITH_EXCEPTIONS`` with ``NOT_CANCELLED``, "A journal run can be
    cancelled only before it is exported.", with a ``DENIED`` event after the ``SUCCESS`` one.
    Now it reads the decision event of its own job and ends as that records — ``CANCELLED`` with
    the same counts — asking no ledger and writing no event."""
    _, run, [batch] = _failed_run(world, monkeypatch, clock)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    asked = _asked(monkeypatch)
    decided = {
        "href": f"{JOURNAL_RUNS}/{run['id']}",
        "counts": {"asked": 1, "held": 0, "cancelled": 1},
        "outcome": "CANCELLED",
    }

    lost = _handler_alone(world, job_id)
    assert (lost.state, dict(lost.result)) == ("SUCCEEDED", decided)
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"])
    assert asked == [batch["external_id"]]

    finished = _work(world, job_id)
    # before the item: SUCCEEDED_WITH_EXCEPTIONS, NOT_CANCELLED, counts all 0
    assert (finished["state"], finished["result"]) == ("SUCCEEDED", decided)
    assert asked == [batch["external_id"]]  # the ledger is not asked a second time
    events = _events(world, run["id"], "journal_run.cancel")
    # before the item: a second event, DENIED, after the SUCCESS it contradicts
    assert [(item["outcome"], item["after"]["job_id"]) for item in events] == [("SUCCESS", job_id)]
    assert events[0]["after"]["counts"] == decided["counts"]


@pytest.mark.slow
def test_a_hand_over_job_that_is_run_again_returns_what_it_decided(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``hand-over`` rev 1.246: the same stop after a hand-over. Until this item the
    second attempt ended ``NOT_HANDED_OVER``, "Only a failed batch can be handed over.", with a
    ``DENIED`` event after the ``SUCCESS`` one. Now it ends ``HANDED_OVER`` with the same counts,
    the ledger is not asked again and the batch is not touched: one event, which names its job."""
    _, run, [batch] = _failed_run(world, monkeypatch, clock)
    accepted = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", world.legacy.maya, {})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    asked = _asked(monkeypatch)
    decided = {
        "href": f"{JOURNAL_RUNS}/{run['id']}",
        "counts": {"asked": 1, "held": 0, "handed_over": 1},
        "outcome": "HANDED_OVER",
    }

    lost = _handler_alone(world, job_id)
    assert (lost.state, dict(lost.result)) == ("SUCCEEDED", decided)
    handed = _stored(world, batch["id"])
    assert str(handed["state"]) == "exported" and handed["export_file_id"] is not None

    finished = _work(world, job_id)
    # before the item: SUCCEEDED_WITH_EXCEPTIONS, NOT_HANDED_OVER, counts all 0
    assert (finished["state"], finished["result"]) == ("SUCCEEDED", decided)
    assert asked == [batch["external_id"]]
    again = _stored(world, batch["id"])
    assert (again["export_file_id"], again["attempt_count"], again["row_version"]) == (
        handed["export_file_id"],
        handed["attempt_count"],
        handed["row_version"],
    )
    events = _events(world, batch["id"], "journal_batch.hand_over")
    assert [(item["outcome"], item["after"]["job_id"]) for item in events] == [("SUCCESS", job_id)]
    assert events[0]["after"]["counts"] == decided["counts"]


@pytest.mark.slow
def test_a_refused_exit_that_is_run_again_says_the_same_and_writes_no_second_event(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """A decision not to cancel is returned the same way (04 §16.7 rev 1.246): the ledger holds
    the failed batch, the first attempt acknowledges it and writes its ``DENIED`` event, and the
    worker stops. Until this item the second attempt found no failed batch, asked nobody and
    refused with another sentence — PRD ERR-74 where the first had said ERR-73 — in a second
    ``DENIED`` event. Now it returns the refusal its job recorded, with the same counts."""
    _, run, [batch] = _failed_run(world, monkeypatch, clock)
    document = _lost_posting(world, batch)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    asked = _asked(monkeypatch)
    sentence = (
        f"{LEDGER} holds batch {batch['external_id']} as {document}. The batch is acknowledged "
        f"and journal run {run['run_no']} is not cancelled."
    )
    counts = {"asked": 1, "held": 1, "cancelled": 0}

    lost = _handler_alone(world, job_id)
    assert (lost.state, lost.result["outcome"], lost.result["counts"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_CANCELLED",
        counts,
    )
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])

    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        dict(lost.result),
    )  # before the item: the sentence of PRD ERR-74 and counts all 0
    assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
    assert asked == [batch["external_id"]]
    events = _events(world, run["id"], "journal_run.cancel")
    assert [(item["outcome"], item["detail"]["message"]) for item in events] == [
        ("DENIED", sentence)
    ]  # before the item: two DENIED events, the second with the other sentence
    assert events[0]["detail"] == {
        "problem": "invalid-transition",
        "field": "state",
        "rule_id": "E-34",
        "message": sentence,
        "job_id": job_id,
        "counts": counts,
    }


# --- a batch the ledger may still take (item JRN-EXIT-SETTLE-1; review finding F9) ----------------


def _never_answered(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock, fault: str
) -> tuple[ns_mock.NetSuiteMock, dict[str, Any], dict[str, Any]]:
    """An approved February run of one NetSuite chunk whose eight attempts (the ADP-12 schedule
    without its waits) all met ``fault`` on the ledger's journal route: seven leave the message
    due again and the eighth dead, the batch ``failed``. (the mock, the run, the batch)."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    _impatient(monkeypatch)
    _faults(world, fault, export.RETRY_ATTEMPTS)
    attempts = _relayed(world, _message(world, batch["id"]), export.RETRY_ATTEMPTS)
    assert attempts == [DUE_AGAIN] * (export.RETRY_ATTEMPTS - 1) + [DIED]
    assert _states(world, run["id"]) == ("failed", ["failed"])
    return mock, run, batch


def _exits(world: JournalWorld, run: dict[str, Any], batch: dict[str, Any]) -> tuple[Any, Any]:
    """The answers of the two exits of a failed batch: the cancel of its run, its hand-over."""
    handed = post(world.app, f"{BATCHES}/{batch['id']}/hand-over", world.legacy.maya, {})
    return _cancel(world, run["id"]), handed


@pytest.mark.slow
def test_a_batch_the_ledger_accepted_and_does_not_show_is_neither_cancelled_nor_handed_over(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 rev 1.247 (item JRN-EXIT-SETTLE-1; review finding F9), through the mock's
    ``READ_LAG`` (05 ADP-21 rev 1.175): the ledger accepts the chunk and shows nothing, so each
    of the eight attempts ends in the adapter's ``Accepted``. The batch is ``failed`` with the
    adapter's message, its message is dead of ``Accepted``, and the ledger holds the journal.
    Until this item the cancel was accepted at once, its job read "not found" and cancelled: a
    cancelled run with a journal in the ledger. Now the cancel and the hand-over answer 409 by
    the batch's name — 16 minutes later too: the ledger said yes — and once the ledger shows the
    journal the retry finds it: batch and run ``acknowledged``, one posting."""
    mock, run, batch = _never_answered(world, monkeypatch, clock, "READ_LAG")
    external_id = batch["external_id"]
    dead = _message(world, batch["id"])
    assert (str(dead["status"]), dead["attempt_count"], dead["last_error"]) == (
        "DEAD",
        export.RETRY_ATTEMPTS,
        "Accepted",
    )
    assert _stored(world, batch["id"])["last_error"] == (
        f"{external_id} was accepted and cannot be read back yet"
    )
    # the ledger holds the journal and shows it to nobody
    assert (mock.posting_count, mock.journal(external_id)) == (1, None)
    jobs = _export_jobs(world, run["id"])

    for moment in ("at once", "16 minutes later"):
        cancelled, handed = _exits(world, run, batch)
        # before the item: 202, and the cancel's job cancelled the run
        assert (cancelled.status_code, handed.status_code) == (409, 409), moment
        sentence = CANCEL_ACCEPTED.format(external_id=external_id)
        assert (slug(cancelled), cancelled.json()["detail"]) == ("invalid-transition", sentence)
        assert [
            (item["field"], item["rule_id"], item["message"]) for item in cancelled.json()["errors"]
        ] == [("state", "E-34", sentence)]
        assert handed.json()["detail"] == HAND_ACCEPTED.format(external_id=external_id)
        if moment == "at once":
            clock.advance(timedelta(minutes=16))
    assert _export_jobs(world, run["id"]) == jobs
    assert _states(world, run["id"]) == ("failed", ["failed"])

    # the ledger shows what it took; the retry asks first, finds the journal and sends nothing
    with asgi_client(world.app) as client:
        shown = client.post(f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}/__erp/journals/release")
    assert (shown.status_code, shown.json()["released"]) == (200, 1), shown.text
    retried = post(world.app, f"{BATCHES}/{batch['id']}/retry", world.legacy.maya, {})
    assert retried.status_code == 202, retried.text
    finished = _work(world, retried.json()["id"])
    assert finished["result"]["counts"] == {
        "messages": 1,
        "claimed": 1,
        "dispatched": 1,
        "failed": 0,
        "dead": 0,
    }
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert _receipts(world, run) == [(1, "REJECTED", None), (1, "POSTED", "JE-NS-88001")]
    assert mock.posting_count == 1


@pytest.mark.slow
def test_the_exits_wait_fifteen_minutes_after_a_death_the_ledger_did_not_refuse(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 rev 1.247: the ledger answered 500 to all eight attempts, so nobody knows
    whether one of them landed, and a request it did not answer can still be applied. For 15
    minutes from the end of the last attempt the cancel and the hand-over answer 409 and name
    the minutes left — 15 at once, 1 in the last half minute. Then the cancel is accepted, its
    job asks the ledger, which holds nothing, and cancels. Before the item both exits were taken
    at once."""
    mock, run, batch = _never_answered(world, monkeypatch, clock, "SERVER_ERROR")
    external_id = batch["external_id"]
    assert _message(world, batch["id"])["last_error"] == "Transient"
    jobs = _export_jobs(world, run["id"])

    for wait in ("15 minutes", "1 minute"):
        cancelled, handed = _exits(world, run, batch)
        assert (cancelled.status_code, handed.status_code) == (409, 409), wait  # before: 202, 202
        sentence = CANCEL_SETTLING.format(external_id=external_id, wait=wait)
        assert (slug(cancelled), cancelled.json()["detail"]) == ("invalid-transition", sentence)
        assert [
            (item["field"], item["rule_id"], item["message"]) for item in cancelled.json()["errors"]
        ] == [("state", "E-34", sentence)]
        assert handed.json()["detail"] == HAND_SETTLING.format(external_id=external_id, wait=wait)
        clock.advance(timedelta(minutes=14, seconds=30) if wait == "15 minutes" else timedelta(0))
    assert _export_jobs(world, run["id"]) == jobs and mock.posting_count == 0

    clock.advance(timedelta(seconds=30))  # the fifteen minutes are over
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    finished = _work(world, accepted.json()["id"])
    assert (finished["state"], finished["result"]["outcome"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        "CANCELLED",
        {"asked": 1, "held": 0, "cancelled": 1},
    )
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"]) and mock.posting_count == 0


@pytest.mark.slow
def test_a_cancel_accepted_after_the_wait_is_refused_by_its_job_when_the_batch_died_again(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 rev 1.247, the job: the rule is read again in the deciding transaction. The
    cancel is accepted once the 15 minutes are over; before its job runs the batch is retried
    and the retry's eight attempts are not answered either, so the batch is ``failed`` again
    with a message that has just died. The job asks the ledger — "not found" — and does not
    cancel: ``NOT_CANCELLED`` with the wait's sentence, as a ``DENIED`` event. Before the item
    it cancelled. The retry itself is held back by no wait: it is taken again at once."""
    mock, run, batch = _never_answered(world, monkeypatch, clock, "SERVER_ERROR")
    external_id = batch["external_id"]
    maya = world.legacy.maya
    clock.advance(WAIT)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]

    retried = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert retried.status_code == 202, retried.text
    retry = {"id": _stored(world, batch["id"])["outbox_message_id"]}
    _faults(world, "SERVER_ERROR", export.RETRY_ATTEMPTS)
    assert _relayed(world, retry, export.RETRY_ATTEMPTS)[-1] == DIED
    again = _stored(world, batch["id"])
    assert (str(again["state"]), again["attempt_count"]) == ("failed", 2)

    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]["outcome"], finished["result"]["counts"]) == (
        "SUCCEEDED_WITH_EXCEPTIONS",
        "NOT_CANCELLED",
        {"asked": 1, "held": 0, "cancelled": 0},
    )  # before the item: SUCCEEDED, CANCELLED
    sentence = CANCEL_SETTLING.format(external_id=external_id, wait="15 minutes")
    assert _refusal(finished, job_id) == (TRANSITION, sentence, [("state", "E-34")])
    assert _states(world, run["id"]) == ("failed", ["failed"]) and mock.posting_count == 0
    events = _events(world, run["id"], "journal_run.cancel")
    assert [(item["outcome"], item["detail"]["message"]) for item in events] == [
        ("DENIED", sentence)
    ]

    # the retry is not held back by the wait the exits observe
    once_more = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert once_more.status_code == 202, once_more.text


# --- the run's retry (item JRN-RUN-RETRY-1) -------------------------------------------------------


def _run_export(world: JournalWorld, run_id: str) -> Any:
    return post(world.app, f"{JOURNAL_RUNS}/{run_id}/export", world.legacy.maya, {})


def _written(world: JournalWorld, run_id: str) -> int:
    """``messages_written`` of the run's last ``journal_run.request_export`` event."""
    last = _events(world, run_id, "journal_run.request_export")[-1]
    return int(last["after"]["messages_written"])


def _two_chunks_one_stopped(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> tuple[ns_mock.NetSuiteMock, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """An approved February run of two NetSuite chunks, both refused by the ledger. The first
    chunk's worker stopped between the batch's ``failed`` and the record of its message's
    ``DEAD`` (05 ADP-32 rev 1.160), so that message is still claimed; the second chunk's message
    is ``DEAD``. (the mock, the run, the first batch, the second)."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock), config={"max_lines_per_chunk": 2})
    run = _approved(world)
    first, second = sorted(run["batches"], key=lambda item: item["chunk_no"])
    _faults(world, "PERMANENT_ERROR", 2)
    with monkeypatch.context() as broken:
        broken.setattr(outbox, "_record", _raising(RuntimeError("the worker stopped")))
        with pytest.raises(RuntimeError, match="the worker stopped"):
            _relayed(world, _message(world, first["id"]))
    assert _relayed(world, _message(world, second["id"])) == [DIED]
    assert _states(world, run["id"]) == ("failed", ["failed", "failed"])
    assert _export_messages(world, first["id"]) == [(first["external_id"], "DISPATCHING", 0)]
    assert _export_messages(world, second["id"]) == [(second["external_id"], "DEAD", 1)]
    assert mock.posting_count == 0
    return mock, run, first, second


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_the_export_of_a_failed_run_retries_its_failed_batches(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``export`` rev 1.244 (item JRN-RUN-RETRY-1), as measured: both chunks of the run
    failed and the ledger would take them now. Until this item the run's ``export`` wrote
    nothing — each failed batch has its first message, which is ``DEAD`` — and its job ended
    ``SUCCEEDED`` over a run that stayed ``failed``. Now the command reads the run's messages
    once, writes each batch its retry message ``<external id>#<attempt count>``, re-points the
    batch and records its ``journal_batch.retry`` event as the batch's own command does. A
    second press writes nothing more: those messages are the retry. The job sends both, and
    batch and run are ``acknowledged``."""
    mock, run, batches = _failed_run(world, monkeypatch, clock, chunks=2, refused=2)
    before = {item["id"]: _stored(world, item["id"])["outbox_message_id"] for item in batches}

    with _message_reads() as reads:
        requested = _run_export(world, run["id"])
    assert requested.status_code == 202, requested.text
    assert len(reads) == 1  # one read of the run's messages decides every batch
    job_id = requested.json()["id"]
    assert _written(world, run["id"]) == 2  # before the item: 0
    for item in batches:
        key = item["external_id"]
        # before the item: the dead first message alone
        assert _export_messages(world, item["id"]) == [(key, "DEAD", 1), (f"{key}#1", "PENDING", 0)]
        stored = _stored(world, item["id"])
        assert (str(stored["state"]), stored["attempt_count"]) == ("failed", 1)
        assert stored["outbox_message_id"] != before[item["id"]]
        [retried] = _events(world, item["id"], "journal_batch.retry")
        assert (retried["outcome"], retried["actor_kind"]) == ("SUCCESS", "USER")
        assert retried["after"] == {
            "state": "failed",
            "attempt_count": 1,
            "outbox_message_id": str(stored["outbox_message_id"]),
            "job_id": job_id,
        }

    # a second press: the messages still to be sent are the retry, and nothing more is written
    again = _run_export(world, run["id"])
    assert again.status_code == 202, again.text
    assert _written(world, run["id"]) == 0
    for item in batches:
        assert len(_export_messages(world, item["id"])) == 2
        assert len(_events(world, item["id"], "journal_batch.retry")) == 1

    finished = _work(world, job_id)
    assert (finished["state"], finished["result"]["counts"], finished["result"]["waiting"]) == (
        "SUCCEEDED",
        {"messages": 2, "claimed": 2, "dispatched": 2, "failed": 0, "dead": 0},
        [],
    )  # before the item: claimed 0, dispatched 0, and the run still failed
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    assert mock.posting_count == 2
    for item in batches:
        assert _items(world, item) == [("RESOLVED", "The batch was exported by a retry.")]


@pytest.mark.slow
def test_the_export_of_a_run_partly_in_a_ledger_retries_its_failed_batch_alone(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``export`` rev 1.244: of two chunks the ledger holds one and refused the other.
    The run's ``export`` writes one retry message, for the failed batch; the acknowledged batch
    is not touched and nothing of it is sent again."""
    mock, run, [failed, posted] = _failed_run(world, monkeypatch, clock, chunks=2)
    acknowledged = _stored(world, posted["id"])

    requested = _run_export(world, run["id"])
    assert requested.status_code == 202, requested.text
    assert _written(world, run["id"]) == 1  # before the item: 0
    key = failed["external_id"]
    assert _export_messages(world, failed["id"]) == [(key, "DEAD", 1), (f"{key}#1", "PENDING", 0)]
    assert _export_messages(world, posted["id"]) == [(posted["external_id"], "DISPATCHED", 0)]
    assert _stored(world, posted["id"])["row_version"] == acknowledged["row_version"]
    assert _events(world, posted["id"], "journal_batch.retry") == []

    finished = _work(world, requested.json()["id"])
    assert finished["result"]["counts"] == {
        "messages": 2,
        "claimed": 1,
        "dispatched": 1,
        "failed": 0,
        "dead": 0,
    }
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged", "acknowledged"])
    assert mock.posting_count == 2


@pytest.mark.slow
def test_the_export_of_a_failed_run_is_refused_whole_beside_a_claimed_message(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``export`` rev 1.244, all or nothing: the first failed chunk's message is still
    claimed and the second's is settled. The command answers 409 by the claimed batch's name —
    the sentence of the batch's own retry — and writes nothing for EITHER batch: no message, no
    event, no job. Skipping the claimed batch and retrying the rest would answer 202 over a
    batch nothing was done for. Before the item the command answered 202 and wrote nothing."""
    _, run, first, second = _two_chunks_one_stopped(world, monkeypatch, clock)
    jobs = _export_jobs(world, run["id"])
    asked = len(_events(world, run["id"], "journal_run.request_export"))

    refused = _run_export(world, run["id"])
    assert refused.status_code == 409, refused.text  # before the item: 202
    sentence = RETRY_BEING_SENT.format(external_id=first["external_id"])
    assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", sentence)
    assert [(e["field"], e["rule_id"], e["message"]) for e in refused.json()["errors"]] == [
        ("state", "E-34", sentence)
    ]
    assert _export_messages(world, first["id"]) == [(first["external_id"], "DISPATCHING", 0)]
    assert _export_messages(world, second["id"]) == [(second["external_id"], "DEAD", 1)]
    for item in (first, second):
        assert _events(world, item["id"], "journal_batch.retry") == []
    assert _export_jobs(world, run["id"]) == jobs
    assert len(_events(world, run["id"], "journal_run.request_export")) == asked
    assert _states(world, run["id"]) == ("failed", ["failed", "failed"])


@pytest.mark.slow
def test_the_export_of_a_failed_run_leaves_a_message_that_is_due_again_to_itself(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``export`` rev 1.244: the first failed chunk's message was taken again after the
    stop, the ledger did not answer, and it is due again; the second chunk's message is dead.
    The run's ``export`` writes nothing for the first — that message is its retry and keeps its
    schedule — and one retry message for the second. Its job sends the second and names the
    first in ``result.waiting`` with the instant it is due. Before the item nothing was written
    for either, and the second chunk stayed ``failed``."""
    mock, run, first, second = _two_chunks_one_stopped(world, monkeypatch, clock)
    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    _faults(world, "SERVER_ERROR")
    assert _relayed(world, _message(world, first["id"])) == [DUE_AGAIN]
    assert _export_messages(world, first["id"]) == [(first["external_id"], "FAILED", 1)]
    due = clock.now() + export.export_delay(1)

    requested = _run_export(world, run["id"])
    assert requested.status_code == 202, requested.text
    assert _written(world, run["id"]) == 1  # before the item: 0
    assert _export_messages(world, first["id"]) == [(first["external_id"], "FAILED", 1)]
    assert _events(world, first["id"], "journal_batch.retry") == []
    key = second["external_id"]
    assert _export_messages(world, second["id"]) == [(key, "DEAD", 1), (f"{key}#1", "PENDING", 0)]

    finished = _work(world, requested.json()["id"])
    assert (finished["state"], finished["result"]["counts"]) == (
        "SUCCEEDED",
        {"messages": 2, "claimed": 1, "dispatched": 1, "failed": 0, "dead": 0},
    )
    [waiting] = finished["result"]["waiting"]
    assert (waiting["journal_batch_id"], waiting["external_id"]) == (
        first["id"],
        first["external_id"],
    )
    assert _instant(waiting["next_attempt_at"]) == due
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])
    assert mock.posting_count == 1


@pytest.mark.slow
def test_the_export_of_an_approved_run_reads_no_message_and_writes_as_before(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 §16.7 ``export`` rev 1.244, what is unchanged: a run without a failed batch is exported
    as before — the approval wrote its message, the command writes none and reads none, and its
    job sends the batch."""
    mock = _netsuite(world, monkeypatch)
    _connection(world, _admin(world, clock))
    run = _approved(world)
    [batch] = run["batches"]
    with _message_reads() as reads:
        requested = _run_export(world, run["id"])
    assert requested.status_code == 202, requested.text
    assert reads == [] and _written(world, run["id"]) == 0
    assert _export_messages(world, batch["id"]) == [(batch["external_id"], "PENDING", 0)]
    finished = _work(world, requested.json()["id"])
    assert (finished["result"]["counts"], finished["result"]["waiting"]) == (
        {"messages": 1, "claimed": 1, "dispatched": 1, "failed": 0, "dead": 0},
        [],
    )
    assert _states(world, run["id"]) == ("acknowledged", ["acknowledged"])
    assert mock.posting_count == 1


# --- the export job states its mode (item JRN-JOB-MODE-1; 04 API-S-Job and §16.7 rev 1.281) -------


def _under_way(world: JournalWorld, run_id: str) -> list[tuple[str, str | None]]:
    """(id, mode) of the run's ``JOURNAL_EXPORT`` jobs that are queued or running, by the list
    read the run page makes for them (``GET /jobs`` by kind, state and subject) — the read on
    which a frame finds a job it did not start."""
    listed = get(
        world.app,
        JOBS,
        world.legacy.maya,
        {
            "kind": ["JOURNAL_EXPORT"],
            "state": ["QUEUED", "RUNNING"],
            "subject_type": export.OBJECT_TYPE,
            "subject_id": run_id,
            "limit": 10,
        },
    )
    assert listed.status_code == 200, listed.text
    return [(item["id"], item["mode"]) for item in listed.json()["items"]]


@pytest.mark.slow
def test_the_export_job_states_its_mode_and_a_retry_names_its_batch(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 API-S-Job ``mode`` and §16.7 ``retry`` rev 1.281 (item JRN-JOB-MODE-1; the supervisor's
    ruling of 2026-10-02 on lane F-CLO-WEB's judgement K3). The run's export and the retry of a
    batch deferred one job with the same params, so nothing a reader of the job is told
    distinguished them, and API-S-Job answered ``mode`` null for every ``JOURNAL_EXPORT`` job —
    the exits' included, whose mode stood in their params alone. Now each of the four commands'
    jobs answers its mode on the 202, on ``GET /jobs/{id}`` and in the list of the run's jobs
    under way; the relay's result repeats it and, for a retry, names the batch. A job deferred
    as before the item, without a mode, answers null, states nothing in its result, and relays
    all the same.

    One chunk of two is failed and the ledger refuses it again each time, so the run stays
    ``failed`` from one command to the next."""
    _mock, run, [failed, posted] = _failed_run(world, monkeypatch, clock, chunks=2)
    maya = world.legacy.maya
    run_id = UUID(str(run["id"]))

    # a job as the commands deferred it before the item: no mode in its params
    with world.legacy.place().uow() as uow:
        old = uow.defer(
            JobKind.JOURNAL_EXPORT,
            {"journal_run_id": str(run_id)},
            subject_type=export.OBJECT_TYPE,
            subject_id=run_id,
        )
        uow.commit()
    shown = get(world.app, f"{JOBS}/{old['id']}", maya)
    assert (shown.status_code, shown.json()["mode"]) == (200, None), shown.text
    assert _under_way(world, run["id"]) == [(str(old["id"]), None)]
    ended = _work(world, old["id"])
    assert (ended["state"], ended["mode"]) == ("SUCCEEDED", None)
    assert sorted(ended["result"]) == ["counts", "href", "waiting"]

    # the retry of the failed batch
    _faults(world, "PERMANENT_ERROR")
    retried = post(world.app, f"{BATCHES}/{failed['id']}/retry", maya, {})
    assert retried.status_code == 202, retried.text
    assert (retried.json()["kind"], retried.json()["mode"]) == ("JOURNAL_EXPORT", "RETRY")
    assert _under_way(world, run["id"]) == [(retried.json()["id"], "RETRY")]
    ended = _work(world, retried.json()["id"])
    assert (ended["state"], ended["mode"]) == ("SUCCEEDED", "RETRY")
    assert (ended["result"]["mode"], ended["result"]["batch"]) == (
        "RETRY",
        {"id": failed["id"], "external_id": failed["external_id"]},
    )
    assert sorted(ended["result"]) == ["batch", "counts", "href", "mode", "waiting"]
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])

    # the run's export, which retries the same batch (rev 1.244): it names no batch
    _faults(world, "PERMANENT_ERROR")
    requested = _run_export(world, run["id"])
    assert requested.status_code == 202, requested.text
    assert (requested.json()["kind"], requested.json()["mode"]) == ("JOURNAL_EXPORT", "EXPORT")
    assert _under_way(world, run["id"]) == [(requested.json()["id"], "EXPORT")]
    ended = _work(world, requested.json()["id"])
    assert (ended["state"], ended["mode"], ended["result"]["mode"]) == (
        "SUCCEEDED",
        "EXPORT",
        "EXPORT",
    )
    assert sorted(ended["result"]) == ["counts", "href", "mode", "waiting"]
    assert _states(world, run["id"]) == ("failed", ["failed", "acknowledged"])

    # the hand-over: its job answers the mode; its result is the exit's own, as before
    handed = post(world.app, f"{BATCHES}/{failed['id']}/hand-over", maya, {})
    assert handed.status_code == 202, handed.text
    assert (handed.json()["kind"], handed.json()["mode"]) == ("JOURNAL_EXPORT", "HAND_OVER")
    # the read on which the run page finds an exit among the jobs under way
    assert _under_way(world, run["id"]) == [(handed.json()["id"], "HAND_OVER")]
    ended = _work(world, handed.json()["id"])
    assert (ended["state"], ended["mode"], ended["result"]["outcome"]) == (
        "SUCCEEDED",
        "HAND_OVER",
        "HANDED_OVER",
    )
    assert sorted(ended["result"]) == ["counts", "href", "outcome"]
    assert _states(world, run["id"]) == ("exported", ["exported", "acknowledged"])
    assert posted["id"] != failed["id"]


@pytest.mark.slow
def test_the_cancel_of_a_failed_run_answers_its_mode(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """04 API-S-Job ``mode`` rev 1.281 (item JRN-JOB-MODE-1), the fourth command: the job of the
    cancel of a run with a failed batch answers ``CANCEL`` on the 202, on ``GET /jobs/{id}`` and
    in the list of the run's jobs under way, where it answered null — a frame that finds the job
    under way reads from the route what the run page of lane F-CLO-WEB compares against."""
    _mock, run, [_batch] = _failed_run(world, monkeypatch, clock)
    accepted = _cancel(world, run["id"])
    assert accepted.status_code == 202, accepted.text
    assert (accepted.json()["kind"], accepted.json()["mode"]) == ("JOURNAL_EXPORT", "CANCEL")
    queued = get(world.app, f"{JOBS}/{accepted.json()['id']}", world.legacy.maya)
    assert (queued.json()["state"], queued.json()["mode"]) == ("QUEUED", "CANCEL")
    # ... and in the list read on which the run page finds an exit among the jobs under way
    assert _under_way(world, run["id"]) == [(accepted.json()["id"], "CANCEL")]
    ended = _work(world, accepted.json()["id"])
    assert (ended["state"], ended["mode"], ended["result"]["outcome"]) == (
        "SUCCEEDED",
        "CANCEL",
        "CANCELLED",
    )
    assert _states(world, run["id"]) == ("cancelled", ["cancelled"])
