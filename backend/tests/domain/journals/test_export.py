"""CLO-13 GL adapter interface, CSV export and the journal export relay; CLO-14 acknowledgement,
retry and the acknowledgement lock gate (05 §5.2 ADP-10 to ADP-15, §5.4 ADP-30 to ADP-34; 03
REQ-JE-011 to REQ-JE-013, REQ-JE-016; 04 T-SL-07, T-SL-10, T-INT-03, §16.7 "Journal commands",
DB-15; PRD SM-08, BR-JE-02, BR-JE-03, NTF-10; CTL-021; BUILD_SPEC CLO-13, CLO-14; security
finding SC-N1, ruling R-32).

World: ``support.worlds.journal_world`` with the CHK-022 intents posted (L6-3-Q-1). Maya calculates
and submits the Mock Entity 1 FY2023-P01 run and Priya approves it, so approval writes the export
message. Jobs run as the worker runs them, with the GL adapter each test registers (DG-LAY-03). The
sandbox test runs the export commands over probe rows of a sandbox tenant row (``support.rows``).

[J] L6-3-Q-10: after the transient failure the message is ``FAILED``, due again 30 s later, not
``PENDING`` (``erev_api.domain.journals.export``). The ``failed`` batch state that L6-3-Q-13 left
to CLO-14 is asserted here: a refused batch is ``failed``, not ``approved``.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import threading
import zipfile
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db import new_id
from erev_api.db.session import (
    DbContext,
    name_platform_tenant,
    platform_session,
    set_tenant_context,
    tenant_session,
)
from erev_api.db.tables import (
    control_execution,
    exception_item,
    gl_account,
    job,
    journal_batch,
    journal_line,
    journal_run,
    notification,
    outbox_message,
    posting_ack,
    webhook_delivery,
)
from erev_api.db.tables.platform import audit_chain_head, audit_event
from erev_api.domain.close import gates
from erev_api.domain.journals import commands, export, ports
from erev_api.enums import GlAdapter, JobKind, OutboxTopic, PrincipalKind, TenantKind
from erev_api.events import outbox, webhooks
from erev_api.events.outbox import RelayStats
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.schemas.journals import JournalRunCancelIn, JournalRunExportIn
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from support.db import TestDatabase
from support.factories import run_import_job
from support.http import HttpRequest, mock_transport
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.journal_lines import insert_behind_the_guard
from support.principals import Actor, colleague, sign_in, workspace
from support.reference import approve, assign, fields, get, periods, post, slug
from support.rows import insert_journal_rows, insert_sandbox_tenant
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    JANUARY,
    JOURNAL_RUNS,
    RUN_ID_HEADER,
    JournalWorld,
    journal_world,
    post_chk_022,
)

CSV_HEADER: Final = [
    "posting_period",
    "entity",
    "currency",
    "je_id",
    "external_id",
    "account",
    "debit",
    "credit",
    "dimensions",
    "memo",
    "source_references",
    # 03 REQ-JE-011 rev 1.68 (ruling R-110): the functional currency and amounts of every line
    "functional_currency",
    "debit_functional",
    "credit_functional",
]
TASK: Final = text("SELECT queue_name, status FROM procrastinate_jobs WHERE id = :id")
MESSAGE_XMIN: Final = text("SELECT xmin::text FROM erev.outbox_message WHERE id = :id")
REQUEST_XMIN: Final = text("SELECT xmin::text FROM erev.approval_request WHERE id = :id")
BATCH_XMIN: Final = text("SELECT xmin::text FROM erev.journal_batch WHERE id = :id")


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
    post_chk_022(built)
    return built


@pytest.fixture
def csv_gl(monkeypatch: pytest.MonkeyPatch) -> None:
    """The composition root's CSV adapter (``erev_api.worker``)."""
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, CsvGl)


class _Ledger:
    """An ERP-like ledger behind the batches' adapter: it acknowledges a posting with a document id
    and answers a repeated external id with the first result; ``transient`` failures come first."""

    def __init__(self, *, transient: int = 0) -> None:
        self.transient = transient
        self.calls: list[str] = []
        self.lookups: list[str] = []
        self.posted: dict[str, ports.PostingResult] = {}

    def factory(self, context: ports.GLContext) -> ports.GLAdapter:
        return _LedgerGl(self, context)


class _LedgerGl:
    def __init__(self, ledger: _Ledger, context: ports.GLContext) -> None:
        self._ledger = ledger
        self._csv = CsvGl(context)

    @property
    def code(self) -> Literal["NETSUITE"]:
        return "NETSUITE"

    def validate_accounts(
        self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
    ) -> ports.ValidationResult:
        return self._csv.validate_accounts(accounts, dimensions)

    def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
        ledger = self._ledger
        ledger.calls.append(chunk.external_id)
        if ledger.transient:
            ledger.transient -= 1
            raise ports.Transient("The probe ledger timed out.")
        found = ledger.posted.get(chunk.external_id)
        if found is None:
            found = ports.PostingResult(
                external_id=chunk.external_id,
                status="POSTED",
                gl_document_id=f"GL-JE-{len(ledger.posted) + 1:06d}",
                gl_posted_date=chunk.period_end_date,
                response_sha256=hashlib.sha256(chunk.external_id.encode("utf-8")).hexdigest(),
            )
            ledger.posted[chunk.external_id] = found
        return found

    def get_posting(self, external_id: str) -> ports.PostingResult | None:
        self._ledger.lookups.append(external_id)
        return self._ledger.posted.get(external_id)

    def pull_chart_of_accounts(self) -> Sequence[ports.AccountRef]:
        return self._csv.pull_chart_of_accounts()

    def pull_trial_balance(
        self, entity: ports.EntityRef, period: ports.PeriodRef, accounts: Sequence[str]
    ) -> ports.TrialBalance:
        return self._csv.pull_trial_balance(entity, period, accounts)


class _Stopped(BaseException):
    """The relay's process stops: no handler below the worker catches it."""


def _rows(world: JournalWorld, statement: Any) -> list[dict[str, Any]]:
    return world.legacy.imports.rows(statement)


def _context(world: JournalWorld) -> DbContext:
    return DbContext(tenant_id=world.legacy.tenant_id, user_id=None, entity_scope="*")


def _approved(world: JournalWorld) -> tuple[str, dict[str, Any], str]:
    """Maya calculates and submits the January run of Mock Entity 1; Priya approves it. (run id,
    its batch, approval request id)."""
    app, maya = world.app, world.legacy.maya
    created = post(app, JOURNAL_RUNS, maya, {"entity_code": ENTITY_1, "period_key": JANUARY})
    assert created.status_code == 202, created.text
    run_import_job(world.legacy.imports, UUID(str(created.json()["id"])))
    run_id = str(created.headers[RUN_ID_HEADER])
    submitted = post(app, f"{JOURNAL_RUNS}/{run_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    approved = approve(app, request_id, world.legacy.priya)
    assert approved.status_code == 200, approved.text
    shown = _run(world, run_id)
    assert shown["state"] == "approved"
    [batch] = shown["batches"]
    return run_id, batch, request_id


def _run(world: JournalWorld, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    body: dict[str, Any] = shown.json()
    return body


def _messages(world: JournalWorld) -> list[dict[str, Any]]:
    return _rows(
        world,
        select(outbox_message)
        .where(outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value)
        .order_by(outbox_message.c.created_at, outbox_message.c.id),
    )


def _acks(world: JournalWorld, batch_id: str) -> list[tuple[str, str | None]]:
    return [
        (str(row["ack_kind"]), row["gl_document_id"])
        for row in _rows(
            world,
            select(posting_ack.c.ack_kind, posting_ack.c.gl_document_id)
            .where(posting_ack.c.journal_batch_id == UUID(batch_id))
            .order_by(posting_ack.c.received_at, posting_ack.c.id),
        )
    ]


def _export_job(world: JournalWorld, run_id: str) -> UUID:
    exported = post(
        world.app, f"{JOURNAL_RUNS}/{run_id}/export", world.legacy.maya, {"adapter": "CSV"}
    )
    assert exported.status_code == 202, exported.text
    body = exported.json()
    assert (body["kind"], exported.headers["Location"]) == (
        "JOURNAL_EXPORT",
        f"/api/v1/jobs/{body['id']}",
    )
    return UUID(str(body["id"]))


def _relayer(world: JournalWorld) -> JobContext:
    tenant_id = world.legacy.tenant_id
    return JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.OUTBOX_RELAY,
        principal=system_principal(tenant_id),
        runtime=world.legacy.imports.runtime,
        persisted=False,
    )


def _relay_jobs(world: JournalWorld, state: str) -> list[UUID]:
    return [
        UUID(str(row["id"]))
        for row in _rows(
            world,
            select(job.c.id)
            .where(job.c.kind == JobKind.OUTBOX_RELAY.value, job.c.state == state)
            .order_by(job.c.created_at, job.c.id),
        )
    ]


@pytest.mark.slow
def test_csv_export_and_manifest(world: JournalWorld, csv_gl: None, clock: FrozenClock) -> None:
    maya = world.legacy.maya
    run_id, batch, _ = _approved(world)
    job_id = _export_job(world, run_id)
    run_import_job(world.legacy.imports, job_id)
    finished = get(world.app, f"/api/v1/jobs/{job_id}", maya).json()
    assert (finished["state"], finished["result"]["href"]) == (
        "SUCCEEDED",
        f"/api/v1/journal-runs/{run_id}",
    )
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "exported",
        ["exported"],
    )
    assert shown["exported_at"] is not None

    downloaded = get(world.app, f"/api/v1/journal-batches/{batch['id']}/download", maya)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(downloaded.content))
    name = str(batch["external_id"]).replace(":", "_")
    assert sorted(archive.namelist()) == [f"{name}.csv", f"{name}.manifest.json"]
    csv_bytes = archive.read(f"{name}.csv")
    [header, *rows] = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
    assert header == CSV_HEADER
    assert sorted((row[5], row[6], row[7]) for row in rows) == [
        ("21001", "295.69", "0.00"),
        ("5001", "0.00", "128.84"),
        ("5002", "0.00", "118.53"),
        ("5003", "0.00", "48.32"),
    ]
    assert {tuple(row[:5]) for row in rows} == {
        (JANUARY, ENTITY_1, "USD", "JE-Mock Entity 1-000001", batch["external_id"])
    }
    assert all(json.loads(row[8]) is not None and row[9] and row[10] for row in rows)
    # The entity keeps its books in the batch's currency: the functional columns repeat the amounts.
    assert all((row[11], row[12], row[13]) == ("USD", row[6], row[7]) for row in rows)
    manifest = json.loads(archive.read(f"{name}.manifest.json"))
    assert (manifest["row_count"], manifest["totals"], manifest["sha256"]) == (
        4,
        {"debit": "295.69", "credit": "295.69"},
        hashlib.sha256(csv_bytes).hexdigest(),
    )
    assert (manifest["currency"], manifest["functional_currency"]) == ("USD", "USD")
    assert manifest["totals_functional"] == manifest["totals"]
    assert manifest["columns"] == CSV_HEADER
    [stored] = _rows(
        world,
        select(journal_batch.c.export_sha256, journal_batch.c.export_file_id).where(
            journal_batch.c.id == UUID(batch["id"])
        ),
    )
    assert stored["export_file_id"] is not None
    assert stored["export_sha256"] == hashlib.sha256(downloaded.content).hexdigest()
    # A CSV export waits for the person who imports it to confirm it (ADP-33).
    assert _acks(world, batch["id"]) == []


@pytest.mark.slow
def test_download_needs_journal_or_report_export(world: JournalWorld) -> None:
    """D-87 L6-3-Q-12: ``GET /journal-batches/{id}/download`` accepts ``journal.export`` or
    ``report.export`` for the batch's entity. A viewer (``report.export`` without
    ``journal.export``) gets 409 for the draft batch and the ZIP once the run is approved; a viewer
    of Mock Entity 2 only gets 404; a member holding neither gets 403 and one ``DENIED`` event."""
    app, maya, tenant_id = world.app, world.legacy.maya, world.legacy.tenant_id
    actors = {}
    for name, entity_ids in (("vera", ()), ("otto", (world.entities[ENTITY_2],))):
        someone = colleague(tenant_id, name)
        assign(someone, "viewer", entity_ids=entity_ids)
        actors[name] = workspace(app, someone, sign_in(app, someone.email))
    analyst = colleague(tenant_id, "sami")
    assign(analyst, "ssp_analyst")
    actors["sami"] = workspace(app, analyst, sign_in(app, analyst.email))

    created = post(app, JOURNAL_RUNS, maya, {"entity_code": ENTITY_1, "period_key": JANUARY})
    assert created.status_code == 202, created.text
    run_import_job(world.legacy.imports, UUID(str(created.json()["id"])))
    run_id = str(created.headers[RUN_ID_HEADER])
    [draft] = _run(world, run_id)["batches"]
    path = f"/api/v1/journal-batches/{draft['id']}/download"
    refused = get(app, path, actors["vera"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text

    submitted = post(app, f"{JOURNAL_RUNS}/{run_id}/submit", maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, str(submitted.json()["approval_request_id"]), world.legacy.priya)
    assert approved.status_code == 200, approved.text

    downloaded = get(app, path, actors["vera"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-type"] == "application/zip"
    name = str(draft["external_id"]).replace(":", "_")
    names = sorted(zipfile.ZipFile(io.BytesIO(downloaded.content)).namelist())
    assert names == [f"{name}.csv", f"{name}.manifest.json"]
    elsewhere = get(app, path, actors["otto"])
    assert (elsewhere.status_code, slug(elsewhere)) == (404, "not-found"), elsewhere.text
    neither = get(app, path, actors["sami"])
    assert (neither.status_code, slug(neither)) == (403, "forbidden"), neither.text
    denied = _rows(
        world,
        select(audit_event.c.action, audit_event.c.outcome).where(
            audit_event.c.object_id == UUID(draft["id"]), audit_event.c.outcome == "DENIED"
        ),
    )
    assert [(str(row["action"]), str(row["outcome"])) for row in denied] == [
        ("journal_batch.download", "DENIED")
    ]


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_ctl_021_export_idempotent(world: JournalWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    run_id, batch, request_id = _approved(world)

    [message] = _messages(world)
    assert (
        message["dedupe_key"],
        message["aggregate_type"],
        str(message["aggregate_id"]),
        message["status"],
    ) == (batch["external_id"], "journal_batch", batch["id"], "PENDING")
    [stored] = _rows(
        world,
        select(journal_batch.c.outbox_message_id).where(journal_batch.c.id == UUID(batch["id"])),
    )
    assert stored["outbox_message_id"] == message["id"]
    # The message, the batch and the decided request share the approval transaction (ADP-30).
    with tenant_session(_context(world), read_only=True) as session:
        transaction_ids = [
            session.execute(query, {"id": value}).scalar_one()
            for query, value in (
                (MESSAGE_XMIN, message["id"]),
                (BATCH_XMIN, UUID(batch["id"])),
                (REQUEST_XMIN, UUID(request_id)),
            )
        ]
    assert len(set(transaction_ids)) == 1, transaction_ids

    first, second = _export_job(world, run_id), _export_job(world, run_id)
    assert len(_messages(world)) == 1
    for job_id in (first, second):
        run_import_job(world.legacy.imports, job_id)
    assert ledger.calls == [batch["external_id"]]
    assert _acks(world, batch["id"]) == [("POSTED", "GL-JE-000001")]
    [message] = _messages(world)
    assert message["status"] == "DISPATCHED"
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
    # Exporting the acknowledged run again returns the existing records (BR-JE-02).
    run_import_job(world.legacy.imports, _export_job(world, run_id))
    assert (len(_messages(world)), ledger.calls, len(_acks(world, batch["id"]))) == (
        1,
        [batch["external_id"]],
        1,
    )


@pytest.mark.slow
def test_relay_transient_then_success(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    ledger = _Ledger(transient=1)
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    relayer = _relayer(world)
    topic = OutboxTopic.JOURNAL_EXPORT

    start = clock.now()
    assert outbox.relay_messages(relayer, [message["id"]], topic=topic) == RelayStats(
        claimed=1, dispatched=0, failed=1, dead=0
    )
    [failed] = _messages(world)
    assert (
        failed["status"],
        failed["attempt_count"],
        failed["next_attempt_at"],
        failed["last_error"],
    ) == ("FAILED", 1, start + timedelta(seconds=30), "Transient")
    assert _run(world, run_id)["batches"][0]["state"] == "approved"
    assert _acks(world, batch["id"]) == []

    clock.advance(timedelta(seconds=29))
    assert outbox.relay_messages(relayer, [message["id"]], topic=topic).claimed == 0
    clock.advance(timedelta(seconds=1))
    assert outbox.relay_messages(relayer, [message["id"]], topic=topic) == RelayStats(
        claimed=1, dispatched=1, failed=0, dead=0
    )
    [sent] = _messages(world)
    assert (sent["status"], sent["attempt_count"], sent["dispatched_at"]) == (
        "DISPATCHED",
        1,
        clock.now(),
    )
    assert _acks(world, batch["id"]) == [("POSTED", "GL-JE-000001")]
    # ADP-12: the retry looks the posting up first; the ledger holds none, so it posts.
    assert ledger.lookups == [batch["external_id"]]
    assert ledger.calls == [batch["external_id"], batch["external_id"]]
    assert _run(world, run_id)["state"] == "acknowledged"


@pytest.mark.slow
def test_relay_permanent_failure_dead_at_once(world: JournalWorld, csv_gl: None) -> None:
    """ADP-12 ``Permanent``: an account outside the batch entity's chart posts nothing, ends the
    message ``DEAD`` on the first attempt and keeps the adapter's message on the batch, which is
    ``failed`` with its run (CLO-14; ADP-12 "``journal_batch.state = failed``"; SMAP-08)."""
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    # Account 5003 now applies only to Mock Entity 2 (T-REF-13 entity_ids).
    with tenant_session(_context(world)) as session:
        session.execute(
            update(gl_account)
            .where(gl_account.c.id == world.accounts["5003"])
            .values(entity_ids=[world.entities[ENTITY_2]])
        )

    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=0, failed=0, dead=1)
    [dead] = _messages(world)
    assert (dead["status"], dead["attempt_count"], dead["last_error"]) == ("DEAD", 1, "Permanent")
    [stored] = _rows(
        world,
        select(
            journal_batch.c.state,
            journal_batch.c.attempt_count,
            journal_batch.c.last_error,
            journal_batch.c.export_file_id,
        ).where(journal_batch.c.id == UUID(batch["id"])),
    )
    assert (
        str(stored["state"]),
        stored["attempt_count"],
        stored["last_error"],
        stored["export_file_id"],
    ) == ("failed", 1, "Account 5003 is not in the chart of accounts.", None)
    # D-87 L6-5-Q-1: the batch reads carry the attempts and the last error (SF-06:run-batches).
    shown = get(world.app, f"/api/v1/journal-batches/{batch['id']}", world.legacy.maya)
    assert shown.status_code == 200, shown.text
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/batches", world.legacy.maya)
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    expected = (1, "Account 5003 is not in the chart of accounts.")
    for read in (shown.json(), item, _run(world, run_id)["batches"][0]):
        assert (read["attempt_count"], read["last_error"]) == expected
    assert _run(world, run_id)["state"] == "failed"
    actions = [
        str(row["action"])
        for row in _rows(
            world,
            select(audit_event.c.action)
            .where(audit_event.c.object_id == UUID(batch["id"]))
            .order_by(audit_event.c.chain_seq),
        )
    ]
    assert "journal_batch.export_failed" in actions
    assert "journal_batch.export" not in actions


@pytest.mark.slow
def test_a_line_added_after_the_approval_is_never_sent(
    world: JournalWorld, csv_gl: None, committed_db: TestDatabase
) -> None:
    """Item JRN-DISPATCH-RECOUNT-1 (independent security review, finding N2 (a); 05 ADP-31): the
    approval of a run covers its batch's stored ``line_count`` and totals. A line that reaches the
    approved batch behind the commands changes what would leave and none of those figures, so
    the dispatch counts and totals the lines again and refuses on a difference: nothing is sent,
    the batch is ``failed`` with the difference named, and a retry is refused the same way.

    The second half of the finding is built since revision 0104 (04 DB-16 rev 1.205; supervisor
    ruling R-112 (b) (6)): ``tg_journal_line__batch_draft`` refuses that line to the application's
    database role, ``EREV-JE-003``. The line is therefore written behind the guard
    (``insert_behind_the_guard``), and the recount is witnessed as the layer that stands when the
    guard is passed (STALE TEST WORLD under that ruling: the insert as the application's role)."""
    run_id, batch, _ = _approved(world)
    batch_id = UUID(batch["id"])
    [message] = _messages(world)
    # the liability line of the batch once more
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
        f"EREV-JE-003: journal batch {batch['id']} is approved, so journal line {copied['id']} "
        "cannot join it: a batch takes lines only while it is draft"
    )
    insert_behind_the_guard(committed_db, _context(world), copied)
    refusal = (
        f"Batch {batch['external_id']} differs from what was calculated and approved: lines 5, "
        "stored 4; transaction debits 591.38 USD, stored 295.69; functional debits 591.38 USD, "
        "stored 295.69. Nothing was sent."
    )

    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=0, failed=0, dead=1)

    def stored() -> tuple[Any, ...]:
        [row] = _rows(
            world,
            select(
                journal_batch.c.state,
                journal_batch.c.last_error,
                journal_batch.c.export_file_id,
                journal_batch.c.exported_at,
            ).where(journal_batch.c.id == batch_id),
        )
        return (str(row["state"]), row["last_error"], row["export_file_id"], row["exported_at"])

    assert stored() == ("failed", refusal, None, None)
    assert _acks(world, batch["id"]) == [("REJECTED", None)]
    assert _run(world, run_id)["state"] == "failed"
    # the batch's own figures are what was approved: the added line changed none of them
    shown = _run(world, run_id)["batches"][0]
    assert (shown["line_count"], shown["total_debit_txn"]["amount"]) == (4, "295.69")

    # a retry sends nothing either: the difference stands until the run is calculated again
    retried = post(world.app, f"/api/v1/journal-batches/{batch['id']}/retry", world.legacy.maya, {})
    assert retried.status_code == 202, retried.text
    run_import_job(world.legacy.imports, UUID(str(retried.json()["id"])))
    assert stored() == ("failed", refusal, None, None)
    assert _acks(world, batch["id"]) == [("REJECTED", None), ("REJECTED", None)]


@pytest.mark.slow
def test_sweeper_redefers_stuck_messages(
    world: JournalWorld,
    monkeypatch: pytest.MonkeyPatch,
    clock: FrozenClock,
    app_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id, batch, _ = _approved(world)
    settings = app_settings.model_copy(update={"run_dir": tmp_path / ".run"})
    runtime = dataclasses.replace(
        world.legacy.imports.runtime,
        email=build_email_sender(settings, clock),
        public_origin=settings.public_origin,
    )
    imports = dataclasses.replace(world.legacy.imports, runtime=runtime)
    [message] = _messages(world)

    def stopping(context: ports.GLContext) -> ports.GLAdapter:
        raise _Stopped

    # A relay stops while it dispatches the export message, which stays DISPATCHING.
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, stopping)
    with pytest.raises(_Stopped):
        outbox.relay_messages(_relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT)
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, CsvGl)
    [stranded] = _messages(world)
    assert stranded["status"] == "DISPATCHING"

    # Every relay already deferred runs and sends the workspace's emails; the fresh claim holds.
    for relay_id in _relay_jobs(world, "QUEUED"):
        run_import_job(imports, relay_id)
    assert _relay_jobs(world, "QUEUED") == []
    assert _messages(world)[0]["status"] == "DISPATCHING"

    clock.advance(timedelta(minutes=15))
    outbox.sweep(clock)
    assert _relay_jobs(world, "QUEUED") == []
    clock.advance(timedelta(seconds=1))
    outbox.sweep(clock)
    [redeferred] = _relay_jobs(world, "QUEUED")
    [queued] = _rows(world, select(job.c.procrastinate_job_id).where(job.c.id == redeferred))
    with tenant_session(_context(world), read_only=True) as session:
        task = session.execute(TASK, {"id": queued["procrastinate_job_id"]}).mappings().one()
    assert (task["queue_name"], task["status"]) == ("outbox", "todo")

    run_import_job(imports, redeferred)
    [sent] = _messages(world)
    assert (sent["status"], sent["attempt_count"]) == ("DISPATCHED", 0)
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "exported",
        ["exported"],
    )
    [stored] = _rows(
        world, select(journal_batch.c.export_file_id).where(journal_batch.c.id == UUID(batch["id"]))
    )
    assert stored["export_file_id"] is not None


def test_sandbox_adapter_export_forbidden(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    sandbox = insert_sandbox_tenant(keyring)
    context = DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
    # The audit chain head provisioning writes last (04 §14.3), so the commands can audit.
    with platform_session(
        "provisioning", actor_user_id=None, request_id="tests-sandbox-chain", keyring=keyring
    ) as session:
        name_platform_tenant(session, sandbox)
        set_tenant_context(session, context)
        session.execute(
            insert(audit_chain_head).values(
                tenant_id=sandbox, last_chain_seq=0, updated_at=clock.now()
            )
        )
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, sandbox)
        for table, row_id in ((journal_batch, rows.batch["id"]), (journal_run, rows.run["id"])):
            session.execute(update(table).where(table.c.id == row_id).values(state="approved"))
    run_id, batch_id = rows.run["id"], rows.batch["id"]
    exporter = Principal(
        kind=PrincipalKind.USER,
        id=new_id(),
        tenant_id=sandbox,
        membership_id=None,
        display_name="Sandbox exporter",
        roles=("revenue_accountant",),
        permissions=frozenset({export.EXPORT_PERMISSION}),
        permission_scopes={export.EXPORT_PERMISSION: "*"},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=clock.now(),
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    ctx = RequestContext(
        principal=exporter,
        tenant_kind=TenantKind.SANDBOX,
        request_id="tests-sandbox-export",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)

    # Approval writes no export message in a sandbox (ADP-34).
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        assert export.enqueue_run(uow, run_id) == 0
        uow.commit()
    with (
        pytest.raises(Problem) as refused,
        unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow,
    ):
        export.export_run(uow, run_id, JournalRunExportIn(adapter=GlAdapter.NETSUITE))
    assert (refused.value.slug, refused.value.status, refused.value.detail) == (
        "sandbox-restricted",
        403,
        "Sandbox workspaces cannot post or export journals.",
    )

    download = export.download_batch(ctx, batch_id, files=files, keyring=keyring)
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    name = str(rows.batch["external_id"]).replace(":", "_")
    [header, *lines] = list(csv.reader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))
    assert (header, len(lines)) == (CSV_HEADER, 2)
    manifest = json.loads(archive.read(f"{name}.manifest.json"))
    assert (manifest["row_count"], manifest["totals"]) == (
        2,
        {"debit": "295.69", "credit": "295.69"},
    )

    with tenant_session(context, read_only=True) as session:
        messages = session.execute(select(func.count()).select_from(outbox_message)).scalar_one()
        stored = session.execute(
            select(
                journal_batch.c.state,
                journal_batch.c.outbox_message_id,
                journal_batch.c.export_file_id,
            ).where(journal_batch.c.id == batch_id)
        ).one()
        audits = [
            (str(row.action), str(row.outcome))
            for row in session.execute(
                select(audit_event.c.action, audit_event.c.outcome)
                .where(audit_event.c.object_id.in_([run_id, batch_id]))
                .order_by(audit_event.c.chain_seq)
            )
        ]
    assert (messages, str(stored.state), stored.outbox_message_id, stored.export_file_id) == (
        0,
        "approved",
        None,
        None,
    )
    assert audits == [
        ("journal_run.request_export", "DENIED"),
        ("journal_batch.download", "SUCCESS"),
    ]


# --- CLO-14: acknowledgement, retry and the acknowledgement lock gate -----------------------------

BOOK: Final = "ASC606"
BATCHES: Final = "/api/v1/journal-batches"
PERIODS: Final = "/api/v1/periods"
REJECTED_ACCOUNT: Final = "Account 5003 is not in the chart of accounts."


def _exported(world: JournalWorld) -> tuple[str, dict[str, Any]]:
    """The January run of Mock Entity 1 approved and exported through the CSV adapter: the run is
    ``exported`` and its batch waits for the person who imports the file (ADP-33)."""
    run_id, batch, _ = _approved(world)
    run_import_job(world.legacy.imports, _export_job(world, run_id))
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "exported",
        ["exported"],
    )
    return run_id, batch


def _acknowledge(world: JournalWorld, batch_id: str, actor: Actor, body: dict[str, Any]) -> Any:
    return post(world.app, f"{BATCHES}/{batch_id}/acknowledge", actor, body)


def _gate(world: JournalWorld, code: str = "BATCHES_ACKNOWLEDGED") -> gates.GateResult:
    with world.legacy.place().uow() as uow:
        results = gates.evaluate_gates(
            uow, world.entities[ENTITY_1], BOOK, world.periods[JANUARY][0]
        )
        uow.commit()
    (found,) = [result for result in results if result.gate_check_code == code]
    return found


def _january(world: JournalWorld, actor: Actor) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, actor, entity=ENTITY_1, book=BOOK)
        if item["period"]["period_key"] == JANUARY
    ]
    return dict(found)


def _lock_refusal(world: JournalWorld) -> list[str]:
    """The gate codes that refuse ``POST /periods/{id}/request-lock`` for January now."""
    marcus = world.legacy.marcus
    january = _january(world, marcus)
    refused = post(
        world.app,
        f"{PERIODS}/{january['id']}/request-lock",
        marcus,
        {"certification_comment": "January 2023 close complete"},
        if_match=f'"r{january["row_version"]}"',
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    return [str(error["rule_id"]) for error in refused.json()["errors"]]


def _executions(world: JournalWorld, batch_id: str) -> list[tuple[str, int, int, dict[str, Any]]]:
    """(result, population, exceptions, detail) of the batch's CTL-021 executions, oldest first."""
    return [
        (
            str(row["result"]),
            int(row["population_count"]),
            int(row["exception_count"]),
            dict(row["detail"]),
        )
        for row in _rows(
            world,
            select(control_execution)
            .where(
                control_execution.c.control_id == "CTL-021",
                control_execution.c.run_ref_id == UUID(batch_id),
            )
            .order_by(control_execution.c.executed_at, control_execution.c.id),
        )
    ]


BATCH_EVENTS: Final = ("journal_batch.exported", "journal_batch.acknowledged")
WEBHOOK_ENDPOINTS: Final = "/api/v1/webhook-endpoints"
WEBHOOK_DELIVERIES: Final = "/api/v1/webhook-deliveries"
HOOK_URL: Final = "https://hooks.example/erev"
ENVELOPE: Final = {"id", "kind", "tenant_code", "occurred_at", "data"}


def _subscribed(world: JournalWorld) -> Actor:
    """An Integration Admin (``webhook.manage``) registers an endpoint for the two journal batch
    kinds through ``POST /webhook-endpoints``; the admin, who also reads the delivery log."""
    someone = colleague(world.legacy.tenant_id, "nikhil")
    assign(someone, "integration_admin")
    nikhil = workspace(world.app, someone, sign_in(world.app, someone.email))
    created = post(
        world.app, WEBHOOK_ENDPOINTS, nikhil, {"url": HOOK_URL, "event_kinds": list(BATCH_EVENTS)}
    )
    assert created.status_code == 201, created.text
    return nikhil


def _delivery_log(world: JournalWorld, reader: Actor, kind: str) -> list[dict[str, Any]]:
    """``GET /webhook-deliveries`` of one event kind."""
    listed = get(world.app, WEBHOOK_DELIVERIES, reader, {"event_kind": kind})
    assert listed.status_code == 200, listed.text
    return list(listed.json()["items"])


def _delivered(world: JournalWorld) -> list[HttpRequest]:
    """One ``WEBHOOK_DELIVERY`` run as the worker would, through a mock transport that answers
    200; the requests the endpoint received."""
    received: list[HttpRequest] = []

    def respond(request: HttpRequest) -> int:
        received.append(request)
        return 200

    runtime = dataclasses.replace(
        world.legacy.imports.runtime,
        webhooks=WebhookClient(
            env=Environment.TEST,
            transport=mock_transport(respond),
            resolve=lambda host, port: ["93.184.216.34"],
        ),
    )
    tenant_id = world.legacy.tenant_id
    worker = JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.WEBHOOK_DELIVERY,
        principal=system_principal(tenant_id),
        runtime=runtime,
        persisted=False,
    )
    stats = webhooks.deliver(worker)
    assert (stats.succeeded, stats.failed, stats.abandoned) == (len(received), 0, 0), stats
    return received


def _announced(world: JournalWorld) -> list[tuple[str, dict[str, Any]]]:
    """(event kind, the envelope's ``data``) of every webhook delivery, exported first."""
    rows = _rows(world, select(webhook_delivery.c.event_kind, webhook_delivery.c.payload))
    found = [(str(row["event_kind"]), dict(row["payload"]["data"])) for row in rows]
    return sorted(found, key=lambda item: BATCH_EVENTS.index(item[0]))


def _batch_data(run_id: str, batch: dict[str, Any]) -> dict[str, Any]:
    """05 NTR-10: ids and hrefs only."""
    return {
        "id": batch["id"],
        "href": f"/api/v1/journal-batches/{batch['id']}",
        "journal_run_id": run_id,
        "journal_run_href": f"/api/v1/journal-runs/{run_id}",
    }


@pytest.mark.slow
def test_req_plt_034_journal_batch_exported_is_delivered(world: JournalWorld, csv_gl: None) -> None:
    """03 REQ-PLT-034 (ruling R-75 (c)): the export of a batch writes one ``journal_batch.exported``
    delivery for a subscribed endpoint, in the transaction that exports the batch; the worker
    posts the signed envelope and the delivery log shows it ``SUCCEEDED``. ``data`` holds the ids
    and hrefs of the batch and its run (05 NTR-10). Before CLO-14 nothing emitted the kind."""
    nikhil = _subscribed(world)
    run_id, batch = _exported(world)
    [pending] = _delivery_log(world, nikhil, "journal_batch.exported")
    assert (pending["status"], pending["attempt_count"]) == ("PENDING", 0)
    envelope = pending["payload"]
    assert set(envelope) == ENVELOPE
    assert (envelope["kind"], envelope["data"]) == (
        "journal_batch.exported",
        _batch_data(run_id, batch),
    )
    assert _delivery_log(world, nikhil, "journal_batch.acknowledged") == []

    [request] = _delivered(world)
    # the client connects to the address it checked; the name travels in Host (05 SAR-15)
    assert (request.method, request.headers["Host"], request.url.path) == (
        "POST",
        "hooks.example",
        "/erev",
    )
    assert json.loads(request.content) == envelope
    assert request.headers["X-Erev-Signature"].startswith("t=")
    [done] = _delivery_log(world, nikhil, "journal_batch.exported")
    assert (done["id"], done["status"], done["last_response_status"]) == (
        pending["id"],
        "SUCCEEDED",
        200,
    )
    # a repeated export command exports nothing again and announces nothing
    run_import_job(world.legacy.imports, _export_job(world, run_id))
    assert len(_delivery_log(world, nikhil, "journal_batch.exported")) == 1


@pytest.mark.slow
def test_req_plt_034_journal_batch_acknowledged_is_delivered(
    world: JournalWorld, csv_gl: None
) -> None:
    """03 REQ-PLT-034 (ruling R-75 (c)): recording the ERP reference of an exported batch writes
    one ``journal_batch.acknowledged`` delivery in the acknowledging transaction; a refused
    acknowledgement writes none. Before CLO-14 nothing emitted the kind."""
    nikhil = _subscribed(world)
    run_id, batch = _exported(world)
    assert _delivery_log(world, nikhil, "journal_batch.acknowledged") == []
    recorded = _acknowledge(
        world, batch["id"], world.legacy.maya, {"gl_document_id": "NS-JE-10045"}
    )
    assert recorded.status_code == 201, recorded.text
    [pending] = _delivery_log(world, nikhil, "journal_batch.acknowledged")
    envelope = pending["payload"]
    assert set(envelope) == ENVELOPE
    assert (pending["status"], envelope["kind"], envelope["data"]) == (
        "PENDING",
        "journal_batch.acknowledged",
        _batch_data(run_id, batch),
    )
    again = _acknowledge(world, batch["id"], world.legacy.maya, {"gl_document_id": "NS-JE-10046"})
    assert again.status_code == 409, again.text
    assert len(_delivery_log(world, nikhil, "journal_batch.acknowledged")) == 1

    received = _delivered(world)
    assert sorted(json.loads(request.content)["kind"] for request in received) == sorted(
        BATCH_EVENTS
    )
    [done] = _delivery_log(world, nikhil, "journal_batch.acknowledged")
    assert (done["status"], done["last_response_status"]) == ("SUCCEEDED", 200)
    topics = [str(row["topic"]) for row in _rows(world, select(outbox_message.c.topic))]
    assert topics.count("WEBHOOK") == 2  # one message per delivery (DG-KRN-EVT-07)


@pytest.mark.slow
@pytest.mark.control("CTL-021")
def test_ctl_021_unacknowledged_batch_blocks_lock(world: JournalWorld, csv_gl: None) -> None:
    """CTL-021 (REQ-JE-016): an ``exported`` batch without acknowledgement makes
    ``BATCHES_ACKNOWLEDGED`` ``FAILED`` (count 1) and ``request-lock`` returns 409
    ``close-gates-failed`` naming the gate; after ``acknowledge`` the gate is ``PASSED``."""
    maya = world.legacy.maya
    run_id, batch = _exported(world)
    failed = _gate(world)
    assert (failed.status.value, failed.count, failed.detail) == (
        "FAILED",
        1,
        "Unacknowledged batches: 1",
    )
    january = _january(world, maya)
    started = post(
        world.app,
        f"{PERIODS}/{january['id']}/start-close",
        maya,
        {"comment": "January close in progress"},
        if_match=f'"r{january["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    assert "BATCHES_ACKNOWLEDGED" in _lock_refusal(world)

    recorded = _acknowledge(world, batch["id"], maya, {"gl_document_id": "NS-JE-10045"})
    assert recorded.status_code == 201, recorded.text
    passed = _gate(world)
    assert (passed.status.value, passed.count, passed.detail) == ("PASSED", 0, None)
    assert "BATCHES_ACKNOWLEDGED" not in _lock_refusal(world)
    assert _run(world, run_id)["state"] == "acknowledged"
    assert _executions(world, batch["id"]) == [
        (
            "PASS",
            1,
            0,
            {
                "status": "acknowledged",
                "ack_kind": "MANUAL_CONFIRMATION",
                "gl_document_id": "NS-JE-10045",
            },
        )
    ]


@pytest.mark.slow
def test_csv_acknowledge_requires_document_id(world: JournalWorld, csv_gl: None) -> None:
    """BUILD_SPEC CLO-14 (BR-JE-03; ADP-33): ``acknowledge`` without ``gl_document_id`` returns 422
    ``validation-failed``; with one it creates a ``posting_ack`` ``MANUAL_CONFIRMATION`` and the
    batch is ``acknowledged``; when every batch is acknowledged the run is ``acknowledged``."""
    maya, priya = world.legacy.maya, world.legacy.priya
    run_id, batch = _exported(world)
    missing = _acknowledge(world, batch["id"], maya, {})
    assert (missing.status_code, slug(missing)) == (422, "validation-failed"), missing.text
    assert fields(missing) == [("gl_document_id", None)]
    blank = _acknowledge(world, batch["id"], maya, {"gl_document_id": "   "})
    assert (blank.status_code, slug(blank)) == (422, "validation-failed"), blank.text
    assert _acks(world, batch["id"]) == [] and _run(world, run_id)["state"] == "exported"
    # the command is the exporter's: a Revenue Reviewer approves runs and does not hold it
    not_priya = _acknowledge(world, batch["id"], priya, {"gl_document_id": "NS-JE-10045"})
    assert (not_priya.status_code, slug(not_priya)) == (403, "forbidden"), not_priya.text
    unknown = _acknowledge(world, str(new_id()), maya, {"gl_document_id": "NS-JE-10045"})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    body = {
        "gl_document_id": "NS-JE-10045",
        "gl_posted_date": "2023-01-31",
        "message": "Imported into the ledger by Maya",
    }
    recorded = _acknowledge(world, batch["id"], maya, body)
    assert recorded.status_code == 201, recorded.text
    ack = recorded.json()
    assert (ack["ack_kind"], ack["gl_document_id"], ack["gl_posted_date"], ack["message"]) == (
        "MANUAL_CONFIRMATION",
        "NS-JE-10045",
        "2023-01-31",
        "Imported into the ledger by Maya",
    )
    assert ack["recorded_by"]["id"] == str(maya.member.user_id) and ack["response_sha256"] is None
    assert _acks(world, batch["id"]) == [("MANUAL_CONFIRMATION", "NS-JE-10045")]
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
    assert shown["acknowledged_at"] is not None
    read = get(world.app, f"{BATCHES}/{batch['id']}", maya).json()
    assert read["acknowledged_at"] is not None
    assert [item["id"] for item in read["acknowledgements"]] == [ack["id"]]
    # API-S-JournalRun ``batches`` rev 1.221: the file of a CSV batch is its export, not a
    # hand-over — the batch holds a file and an export time, and was never handed over
    assert read["exported_at"] is not None and read["handed_over_at"] is None
    # an acknowledged batch takes no second confirmation
    again = _acknowledge(world, batch["id"], maya, {"gl_document_id": "NS-JE-10046"})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert again.json()["detail"] == "Only an exported batch can be acknowledged."
    assert _acks(world, batch["id"]) == [("MANUAL_CONFIRMATION", "NS-JE-10045")]
    actions = [
        str(row["action"])
        for row in _rows(
            world,
            select(audit_event.c.action)
            .where(audit_event.c.object_id == UUID(batch["id"]))
            .order_by(audit_event.c.chain_seq),
        )
    ]
    assert actions.count("journal_batch.acknowledge") == 1


@pytest.mark.slow
def test_acknowledge_waits_for_the_export(world: JournalWorld) -> None:
    """An ``approved`` batch that was not exported yet is not acknowledged: 409."""
    _, batch, _ = _approved(world)
    early = _acknowledge(world, batch["id"], world.legacy.maya, {"gl_document_id": "NS-JE-10045"})
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert _acks(world, batch["id"]) == []


def _account_5003(world: JournalWorld, entity_ids: list[UUID]) -> None:
    """T-REF-13 ``entity_ids`` of account 5003: the entities it applies to (none = every entity)."""
    with tenant_session(_context(world)) as session:
        session.execute(
            update(gl_account)
            .where(gl_account.c.id == world.accounts["5003"])
            .values(entity_ids=entity_ids)
        )


@pytest.mark.slow
def test_permanent_failure(world: JournalWorld, csv_gl: None) -> None:
    """BUILD_SPEC CLO-14 (ADP-12; SM-08; NTF-10): ``Permanent`` sets the batch ``failed``, raises an
    exception item of source ``JOURNAL`` with the adapter message and notification
    ``EXPORT_FAILED``; ``retry`` moves it back to ``exported``."""
    maya, marcus = world.legacy.maya, world.legacy.marcus
    _subscribed(world)
    run_id, batch, _ = _approved(world)
    _account_5003(world, [world.entities[ENTITY_2]])  # no longer an account of Mock Entity 1
    earlier = {row["id"] for row in _rows(world, select(notification.c.id))}
    run_import_job(world.legacy.imports, _export_job(world, run_id))

    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == ("failed", ["failed"])
    failed = shown["batches"][0]
    assert (failed["attempt_count"], failed["last_error"]) == (1, REJECTED_ACCOUNT)
    assert _acks(world, batch["id"]) == [("REJECTED", None)]
    [dead] = _messages(world)
    assert (dead["status"], dead["last_error"]) == ("DEAD", "Permanent")
    [item] = _rows(world, select(exception_item).where(exception_item.c.source == "JOURNAL"))
    assert (str(item["code"]), str(item["severity"]), str(item["status"]), item["message"]) == (
        "JOURNAL_EXPORT_FAILED",
        "BLOCKING",
        "OPEN",
        REJECTED_ACCOUNT,
    )
    assert (item["entity_id"], item["period_id"], item["business_key"]) == (
        world.entities[ENTITY_1],
        world.periods[JANUARY][0],
        batch["external_id"],
    )
    notified = _rows(
        world,
        select(notification).where(notification.c.kind == "EXPORT_FAILED"),
    )
    # PRD NTF-10: the exporter (Maya asked for the export) and the Controllers (Marcus)
    assert {row["recipient_membership_id"] for row in notified} == {
        maya.member.membership_id,
        marcus.member.membership_id,
    }
    assert {(row["title"], row["body"], row["link_path"]) for row in notified} == {
        (
            f"Journal export failed: {shown['run_no']}",
            "CSV rejected 1 chunks: Account 5003 is not in the chart of accounts. Retry after "
            "correcting the cause; retries do not duplicate postings.",
            f"/journals/runs/{run_id}",
        )
    }
    assert _executions(world, batch["id"]) == [
        ("FAIL", 1, 1, {"status": "failed", "ack_kind": "REJECTED", "gl_document_id": None})
    ]
    unacknowledged = _gate(world)
    assert (unacknowledged.status.value, unacknowledged.count) == ("FAILED", 1)
    # Ruling R-71 (b): E-34 has no pair approved → failed, so the batch passed ``exported``
    # inside the failing transaction, and that leg is not observable — no export time, file or
    # export event, no notification but EXPORT_FAILED, no webhook message; the audit event of
    # the refusal carries the adapter's message.
    assert (shown["exported_at"], failed["exported_at"], failed["acknowledged_at"]) == (
        None,
        None,
        None,
    )
    events = _rows(
        world,
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after)
        .where(audit_event.c.object_id == UUID(batch["id"]))
        .order_by(audit_event.c.chain_seq),
    )
    assert [str(row["action"]) for row in events] == ["journal_batch.export_failed"]
    assert (events[0]["before"], events[0]["after"]["state"], events[0]["after"]["last_error"]) == (
        {"state": "approved"},
        "failed",
        REJECTED_ACCOUNT,
    )
    assert events[0]["after"]["run_state"] == "failed"
    sent = [
        (str(row["kind"]), str(row["subject_type"]), str(row["subject_id"]))
        for row in _rows(world, select(notification))
        if row["id"] not in earlier
    ]
    assert set(sent) == {("EXPORT_FAILED", "journal_batch", batch["id"])} and len(sent) == 2
    topics = {str(row["topic"]) for row in _rows(world, select(outbox_message.c.topic))}
    assert "WEBHOOK" not in topics and "JOURNAL_EXPORT" in topics
    assert _announced(world) == []  # with an endpoint subscribed to both batch kinds

    # the cause is corrected, then the batch is sent again
    _account_5003(world, [])
    early = post(world.app, f"{BATCHES}/{batch['id']}/acknowledge", maya, {"gl_document_id": "X"})
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    retried = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert retried.status_code == 202, retried.text
    job_body = retried.json()
    assert (job_body["kind"], retried.headers["Location"]) == (
        "JOURNAL_EXPORT",
        f"/api/v1/jobs/{job_body['id']}",
    )
    repeated = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert repeated.status_code == 202, repeated.text
    messages = _messages(world)
    assert [(row["status"], row["dedupe_key"]) for row in messages] == [
        ("DEAD", batch["external_id"]),
        ("PENDING", f"{batch['external_id']}#1"),
    ]
    for job_id in (job_body["id"], repeated.json()["id"]):
        run_import_job(world.legacy.imports, UUID(str(job_id)))

    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "exported",
        ["exported"],
    )
    sent = shown["batches"][0]
    assert (sent["attempt_count"], sent["last_error"]) == (2, None)
    assert [row["status"] for row in _messages(world)] == ["DEAD", "DISPATCHED"]
    assert _acks(world, batch["id"]) == [("REJECTED", None)]  # a CSV export waits for its person
    [resolved] = _rows(world, select(exception_item).where(exception_item.c.id == item["id"]))
    assert (str(resolved["status"]), resolved["resolution"]) == (
        "RESOLVED",
        "The batch was exported by a retry.",
    )
    downloaded = get(world.app, f"{BATCHES}/{batch['id']}/download", maya)
    assert downloaded.status_code == 200, downloaded.text
    # the retry exported the batch: that is the first time the export is announced
    assert _announced(world) == [("journal_batch.exported", _batch_data(run_id, batch))]
    # exported again: nothing is left to retry, and the person who imports the file confirms it
    done = post(world.app, f"{BATCHES}/{batch['id']}/retry", maya, {})
    assert (done.status_code, slug(done)) == (409, "invalid-transition"), done.text
    assert done.json()["detail"] == "Only a failed batch can be retried."
    confirmed = _acknowledge(world, batch["id"], maya, {"gl_document_id": "NS-JE-10045"})
    assert confirmed.status_code == 201, confirmed.text
    assert _run(world, run_id)["state"] == "acknowledged"


@pytest.mark.slow
def test_last_transient_attempt_fails_the_batch(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """ADP-31: after the last attempt of the ADP-12 schedule the message is ``DEAD`` and the batch
    is ``failed`` with the adapter's message, as for a permanent refusal; a retry then finds the
    ledger answering and the ERP document acknowledges the batch."""
    ledger = _Ledger(transient=export.RETRY_ATTEMPTS)
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    _subscribed(world)
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    relayer, topic = _relayer(world), OutboxTopic.JOURNAL_EXPORT
    for attempt in range(1, export.RETRY_ATTEMPTS + 1):
        stats = outbox.relay_messages(relayer, [message["id"]], topic=topic)
        last = attempt == export.RETRY_ATTEMPTS
        assert stats == RelayStats(claimed=1, dispatched=0, failed=0 if last else 1, dead=int(last))
        state = _run(world, run_id)["batches"][0]["state"]
        assert state == ("failed" if last else "approved"), (attempt, state)
        clock.advance(export.export_delay(attempt))
    [dead] = _messages(world)
    assert (dead["status"], dead["attempt_count"], dead["last_error"]) == (
        "DEAD",
        export.RETRY_ATTEMPTS,
        "Transient",
    )
    failed = _run(world, run_id)
    assert (failed["state"], failed["batches"][0]["last_error"]) == (
        "failed",
        "The probe ledger timed out.",
    )
    assert _acks(world, batch["id"]) == [("REJECTED", None)]
    assert _announced(world) == []  # eight attempts and a failed batch announce nothing

    retried = post(world.app, f"{BATCHES}/{batch['id']}/retry", world.legacy.maya, {})
    assert retried.status_code == 202, retried.text
    run_import_job(world.legacy.imports, UUID(str(retried.json()["id"])))
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
    assert _acks(world, batch["id"]) == [("REJECTED", None), ("POSTED", "GL-JE-000001")]
    # ADP-12: the retry asked the ledger for the posting before it posted
    assert ledger.lookups == [batch["external_id"]] * export.RETRY_ATTEMPTS
    assert _executions(world, batch["id"])[-1] == (
        "PASS",
        1,
        0,
        {"status": "acknowledged", "ack_kind": "POSTED", "gl_document_id": "GL-JE-000001"},
    )
    # the ERP's receipt exports and acknowledges the batch in one transaction: both are announced
    data = _batch_data(run_id, batch)
    assert _announced(world) == [
        ("journal_batch.exported", data),
        ("journal_batch.acknowledged", data),
    ]


# --- SC-N1 (ruling R-32): cancel against dispatch -------------------------------------------------

IN_PROGRESS: Final = (
    "An export of this journal run is in progress: batch {external_id} is being sent. It cannot "
    "be cancelled while a batch is being sent. An interrupted export resumes about 15 minutes "
    "after it stopped."
)


@pytest.mark.slow
def test_sc_n1_cancel_is_refused_while_a_batch_is_being_sent(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security finding SC-N1: the relay has claimed the export message and ``dispatch_batch`` has
    re-read the batch under its row lock; a cancel issued now — between that read and the adapter
    call — is refused, so the ledger never receives a posting of a cancelled run. Before the fix
    the cancel succeeded here and the chunk was posted all the same."""
    ledger = _Ledger()
    attempts: list[Any] = []
    target: dict[str, str] = {}

    class _CancellingGl(_LedgerGl):
        def validate_accounts(
            self, accounts: Sequence[ports.AccountRef], dimensions: Sequence[ports.DimensionRef]
        ) -> ports.ValidationResult:
            attempts.append(
                post(
                    world.app,
                    f"{JOURNAL_RUNS}/{target['run_id']}/cancel",
                    world.legacy.maya,
                    {"reason": "Wrong period"},
                )
            )
            return super().validate_accounts(accounts, dimensions)

    monkeypatch.setitem(
        ports.GL_ADAPTERS, GlAdapter.CSV, lambda context: _CancellingGl(ledger, context)
    )
    run_id, batch, _ = _approved(world)
    target["run_id"] = run_id
    [message] = _messages(world)
    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    [refused] = attempts
    assert refused.status_code == 409, refused.text  # before the fix: 200, and the chunk posted
    assert slug(refused) == "invalid-transition"
    assert refused.json()["detail"] == IN_PROGRESS.format(external_id=batch["external_id"])
    assert ledger.calls == [batch["external_id"]]
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
    # the export is done: the run is past cancelling for the usual reason
    late = post(
        world.app, f"{JOURNAL_RUNS}/{run_id}/cancel", world.legacy.maya, {"reason": "Wrong period"}
    )
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text
    assert late.json()["detail"] == "A journal run can be cancelled only before it is exported."


@pytest.mark.slow
def test_sc_n1_dispatch_waits_for_a_cancel_and_sends_nothing(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other order, observed: a cancel holds the run and batch rows (its transaction is open)
    when the relay claims the export message; ``dispatch_batch`` is seen WAITING for the run row,
    the adapter is not called meanwhile, and once the cancel commits the dispatch finds the batch
    cancelled and sends nothing. Before the fix the dispatch read the state without a lock, saw
    ``approved`` and posted the chunk while the cancel was committing."""
    ledger = _Ledger()
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    outcome: dict[str, Any] = {}

    def dispatch() -> None:
        try:
            outcome["stats"] = outbox.relay_messages(
                _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
            )
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    relay = threading.Thread(target=dispatch, name="sc-n1-dispatch")
    started = False
    try:
        with observing_checkouts() as backends, world.legacy.place().uow() as uow:
            holder_pid = backend_pid(uow.session)
            cancelled = commands.cancel_run(
                uow, UUID(run_id), JournalRunCancelIn(reason="Wrong period")
            )
            assert cancelled.state.value == "cancelled"
            relay.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=20.0,
                expect="journal_run",
            )
            assert blocked_pid != holder_pid and relay.is_alive(), (blocked_pid, blocked_in)
            assert ledger.calls == []  # nothing is sent while the batch's state is undecided
            uow.commit()
    finally:
        if started:
            relay.join(timeout=30.0)
    assert not relay.is_alive() and "error" not in outcome, outcome
    assert outcome["stats"] == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    assert (ledger.calls, ledger.lookups) == ([], [])
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "cancelled",
        ["cancelled"],
    )
    assert _acks(world, batch["id"]) == []
    [settled] = _messages(world)
    assert settled["status"] == "DISPATCHED"  # the claimed message is settled; it sent nothing


def _cancel(world: JournalWorld, run_id: str) -> Any:
    return post(
        world.app,
        f"{JOURNAL_RUNS}/{run_id}/cancel",
        world.legacy.maya,
        {"reason": "Wrong period"},
    )


@pytest.mark.slow
def test_sc_n1_a_stranded_claim_refuses_the_cancel_until_the_export_completes(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Ruling R-75: a relay stops while it holds its claim — the message stays ``DISPATCHING``.
    The cancel is refused whatever the age of the claim, because only the ledger knows whether
    the chunk arrived; the relay that takes the message again after 15 minutes (ADP-32) completes
    the export, and the run is then past cancelling for the usual reason."""
    ledger = _Ledger()
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    topic = OutboxTopic.JOURNAL_EXPORT
    in_progress = IN_PROGRESS.format(external_id=batch["external_id"])

    def stopping(context: ports.GLContext) -> ports.GLAdapter:
        raise _Stopped

    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, stopping)
    with pytest.raises(_Stopped):
        outbox.relay_messages(_relayer(world), [message["id"]], topic=topic)
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    assert _messages(world)[0]["status"] == "DISPATCHING"

    # at once, at +15 minutes (the relay does not take the claim yet, ADP-32) and at +16 minutes
    for wait in (timedelta(0), timedelta(minutes=15), timedelta(minutes=1)):
        clock.advance(wait)
        if wait == timedelta(minutes=15):
            stats = outbox.relay_messages(_relayer(world), [message["id"]], topic=topic)
            assert stats.claimed == 0
        refused = _cancel(world, run_id)
        assert refused.status_code == 409, (wait, refused.text)
        assert (slug(refused), refused.json()["detail"]) == ("invalid-transition", in_progress)
    assert _run(world, run_id)["state"] == "approved" and ledger.calls == []

    # the relay's recovery completes the export
    stats = outbox.relay_messages(_relayer(world), [message["id"]], topic=topic)
    assert stats == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    assert ledger.calls == [batch["external_id"]]
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
    late = _cancel(world, run_id)
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text
    assert late.json()["detail"] == "A journal run can be cancelled only before it is exported."


@pytest.mark.slow
def test_sc_n1_a_run_cancelled_before_any_claim_is_never_sent(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror case (ruling R-75): the cancel commits before any relay claims the export
    message. The relay then claims the message, ``dispatch_batch`` finds the batch ``cancelled``
    under its locks, the ledger is never called, and the message is settled."""
    ledger = _Ledger()
    monkeypatch.setitem(ports.GL_ADAPTERS, GlAdapter.CSV, ledger.factory)
    nikhil = _subscribed(world)
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    assert message["status"] == "PENDING"
    cancelled = _cancel(world, run_id)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"

    stats = outbox.relay_messages(
        _relayer(world), [message["id"]], topic=OutboxTopic.JOURNAL_EXPORT
    )
    assert stats == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    assert (ledger.calls, ledger.lookups) == ([], [])
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "cancelled",
        ["cancelled"],
    )
    assert _acks(world, batch["id"]) == []
    assert [row["status"] for row in _messages(world)] == ["DISPATCHED"]
    assert [_delivery_log(world, nikhil, kind) for kind in BATCH_EVENTS] == [[], []]


@pytest.mark.slow
def test_sc_n1_a_relay_that_stopped_after_the_ledger_accepted_posts_nothing_twice(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """The case ruling R-75 closes: the ledger accepted the chunk and the relay stopped before
    the batch was recorded. The batch still reads ``approved``, so a cancel admitted now would
    leave a ledger document of a cancelled batch. It is refused; the recovering relay sends the
    chunk again, the ledger answers that it holds the document (``Duplicate``), and the batch is
    acknowledged with the first document id — one posting in the ledger (BR-JE-02)."""
    ledger = _Ledger()

    class _StoppingAfterPosting(_LedgerGl):
        def post_chunk(self, chunk: ports.JournalChunk) -> ports.PostingResult:
            held = ledger.posted.get(chunk.external_id)
            if held is not None:
                ledger.calls.append(chunk.external_id)
                raise ports.Duplicate(chunk.external_id, str(held.gl_document_id))
            super().post_chunk(chunk)
            raise _Stopped

    monkeypatch.setitem(
        ports.GL_ADAPTERS, GlAdapter.CSV, lambda context: _StoppingAfterPosting(ledger, context)
    )
    run_id, batch, _ = _approved(world)
    [message] = _messages(world)
    topic = OutboxTopic.JOURNAL_EXPORT
    with pytest.raises(_Stopped):
        outbox.relay_messages(_relayer(world), [message["id"]], topic=topic)
    assert list(ledger.posted) == [batch["external_id"]]  # the ledger holds the document
    assert _run(world, run_id)["batches"][0]["state"] == "approved"  # and nothing recorded it
    assert _acks(world, batch["id"]) == []

    clock.advance(timedelta(minutes=15, seconds=1))
    refused = _cancel(world, run_id)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == IN_PROGRESS.format(external_id=batch["external_id"])

    stats = outbox.relay_messages(_relayer(world), [message["id"]], topic=topic)
    assert stats == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    assert ledger.calls == [batch["external_id"], batch["external_id"]]
    assert list(ledger.posted) == [batch["external_id"]]
    assert _acks(world, batch["id"]) == [("DUPLICATE", "GL-JE-000001")]
    shown = _run(world, run_id)
    assert (shown["state"], [item["state"] for item in shown["batches"]]) == (
        "acknowledged",
        ["acknowledged"],
    )
