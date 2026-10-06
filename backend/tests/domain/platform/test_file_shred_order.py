"""Decide, then destroy (item FILE-SHRED-DURABLE-ORDER-1; the supervisor's ruling of 2026-10-01 on
finding B4 of the independent review of the ``EVIDENCE_SHRED`` merge 58eba434; 05 §6.17 PRV-07 b,
§7.2 OPR-10, §7.4 OPR-24 and §5.7 SCH-16, rev 1.171; 04 T-PLT-29 rev 1.237; runbook RB-14).

The shred of a file destroyed its key first and recorded the decision afterwards, in one
transaction: the marker and the delete of the wrapped key came before the row's mark, the audit
event and the commit. Measured on the head before this order, with the commit made to fail the
way it fails in production — the audit chain head held by another transaction past the 10 s
lock timeout — ``file.shred`` and the approval of an ``EVIDENCE_SHRED`` request each answered
409 ``lock-conflict`` "… so nothing was saved" with the key destroyed, the content gone, the row
unmarked and no event on the chain: an irreversible destruction that the chain never recorded.

The order now: the command's transaction marks the row and writes ``file_object.shred``, and
touches nothing of the store; the key is destroyed after that commit, and
``file_object.shred_complete`` carries the store's report, written by whatever finishes — the
command's own continuation, ``file.shred`` sent again, or the sweep SCH-16.

The first three tests are the witnesses of the ruling, red on the head for the reason measured:
the 409's sentence made true on both paths, and the completion's own commit failing after the
store's part. The others hold the two later roads, the store's outage with its operator alert,
and a key that came back beside the shred.

The world, through the product where the product has a command for it: a workspace with Tess
(Tenant Admin: ``settings.manage``) and Carla (Controller), attachments of a contract that no
record holds, and the source of a committed import, which an approved request shreds. The
contract and the import are rows, as in ``test_sandbox_shred.py``: this module is about the
stored object and its record.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls import recovery
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_chain_head,
    audit_event,
    file_attachment,
    file_object,
)
from erev_api.domain.platform import privacy
from erev_api.enums import FilePurpose
from erev_api.files.store import (
    GenerationConflict,
    LocalFileStore,
    shred_marker_key,
    sidecar_key,
)
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import approve, assign, get, post, slug
from support.rows import insert_contract_rows, insert_import_upload
from support.stored_files import Stored, store

FILES = "/api/v1/files"
REASON = "DSR-2026-0917: erase the person's data in this document"
SHRED = "file_object.shred"
COMPLETE = "file_object.shred_complete"
NOTHING_SAVED = (
    "The records this request needed were held by another change for longer than the platform "
    "waits, so nothing was saved. Resubmit the request."
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


class Alerts:
    """The operator-alert sinks of a worker, as a list."""

    def __init__(self) -> None:
        self.raised: list[Any] = []

    def raise_alert(self, alert: Any) -> tuple[str, ...]:
        self.raised.append(alert)
        return ("list",)


@dataclass(frozen=True, slots=True)
class World:
    """A workspace, its two people, and the files of a test by name."""

    app: FastAPI
    tenant_id: UUID
    tess: Actor
    carla: Actor
    files: LocalFileStore
    keyring: KeyRing
    clock: FrozenClock
    runtime: JobRuntime
    alerts: Alerts
    contract_id: UUID

    def attachment(self, name: str) -> Stored:
        """An attachment of the contract: a stored file that no record holds."""
        stored = store(
            self.tenant_id,
            FilePurpose.ATTACHMENT,
            name,
            clock=self.clock,
            keyring=self.keyring,
            files=self.files,
        )
        with tenant_session(_context(self.tenant_id)) as session:
            session.execute(
                insert(file_attachment).values(
                    tenant_id=self.tenant_id,
                    id=uuid4(),
                    file_object_id=stored.id,
                    subject_type="contract",
                    subject_id=self.contract_id,
                    created_by_kind="SYSTEM",
                )
            )
        return stored

    def import_source(self, name: str) -> Stored:
        """The source of a committed import: held, and shredded by an approved request."""
        stored = store(
            self.tenant_id,
            FilePurpose.IMPORT_SOURCE,
            name,
            clock=self.clock,
            keyring=self.keyring,
            files=self.files,
        )
        with tenant_session(_context(self.tenant_id)) as session:
            insert_import_upload(
                session, tenant_id=self.tenant_id, file_object_id=stored.id, status="COMMITTED"
            )
        return stored


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> World:
    root = member(keyring, clock, name="tess")
    assign(root, "tenant_admin")
    carla_member = colleague(root.tenant_id, "carla")
    assign(carla_member, "controller")
    with tenant_session(_context(root.tenant_id)) as session:
        contract_id = insert_contract_rows(session, root.tenant_id).contract_id
    alerts = Alerts()
    return World(
        app=app,
        tenant_id=root.tenant_id,
        tess=enrolled(app, clock, root),
        carla=enrolled(app, clock, carla_member),
        files=files,
        keyring=keyring,
        clock=clock,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files, alerts=alerts),
        alerts=alerts,
        contract_id=contract_id,
    )


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _row(world: World, stored: Stored) -> dict[str, Any]:
    (row,) = _rows(world.tenant_id, select(file_object).where(file_object.c.id == stored.id))
    return row


def _answer(response: HttpResponse) -> tuple[int, str | None, list[str | None]]:
    """(status, problem, rules) — no problem and no rule for an answer that is none."""
    if response.status_code < 400:
        return (response.status_code, None, [])
    errors = response.json().get("errors") or []
    return (response.status_code, slug(response), [error.get("rule_id") for error in errors])


def _store(world: World, stored: Stored) -> dict[str, bool]:
    key = str(_row(world, stored)["storage_key"])
    return {
        "marker": world.files.exists(shred_marker_key(key)),
        "sidecar": world.files.exists(sidecar_key(key)),
    }


def _events(world: World, stored: Stored) -> list[dict[str, Any]]:
    """The shred events of the file, in chain order: the decision and the completion."""
    return _rows(
        world.tenant_id,
        select(
            audit_event.c.action,
            audit_event.c.outcome,
            audit_event.c.actor_id,
            audit_event.c.actor_kind,
            audit_event.c.on_behalf_of_id,
            audit_event.c.detail,
        )
        .where(audit_event.c.object_id == stored.id, audit_event.c.action.in_([SHRED, COMPLETE]))
        .order_by(audit_event.c.chain_seq),
    )


def _actions(world: World, stored: Stored) -> list[tuple[str, str]]:
    return [
        (str(event["action"]), str(getattr(event["outcome"], "value", event["outcome"])))
        for event in _events(world, stored)
    ]


def _read(world: World, stored: Stored) -> tuple[int, Any]:
    """The content read by Carla: (200, the bytes) or (the status, the rules)."""
    response = get(world.app, f"{FILES}/{stored.id}/content", world.carla)
    if response.status_code == 200:
        return (200, response.content)
    errors = response.json().get("errors") or []
    return (response.status_code, [error.get("rule_id") for error in errors])


def _untouched(world: World, stored: Stored) -> None:
    """Nothing was saved and nothing destroyed: the row unmarked, no event, the key and no
    marker in the store, the content served."""
    row = _row(world, stored)
    assert (row["shredded_at"], row.get("shred_completed_at")) == (None, None)
    assert _actions(world, stored) == []
    assert _store(world, stored) == {"marker": False, "sidecar": True}
    assert _read(world, stored) == (200, stored.content)


def _decided_and_completed(world: World, stored: Stored, *, road: str) -> dict[str, Any]:
    """The shred is on the row and on the chain, decision first; the key is gone. The
    completion's detail."""
    row = _row(world, stored)
    assert row["shredded_at"] is not None and row["shred_completed_at"] is not None
    assert row["shred_completed_at"] >= row["shredded_at"]
    assert _actions(world, stored) == [(SHRED, "SUCCESS"), (COMPLETE, "SUCCESS")]
    decision, completion = (event["detail"] for event in _events(world, stored))
    # The decision carries no report of the store: nothing was touched when it was written.
    assert not {"marker_created", "deleted_generations", "irreversible_after"} & set(decision)
    assert completion["road"] == road
    assert completion["decided_at"] == row["shredded_at"].isoformat()
    assert completion["marker_at"] is not None
    assert _store(world, stored) == {"marker": True, "sidecar": False}
    assert _read(world, stored) == (404, ["FILE_SHREDDED"])
    shown = get(world.app, f"{FILES}/{stored.id}", world.carla)
    assert shown.status_code == 200 and shown.json()["shred_completed_at"] is not None, shown.text
    return dict(completion)


def _while_the_chain_head_is_held(
    tenant_id: UUID, run_request: Callable[[], HttpResponse]
) -> HttpResponse:
    """Run the request while another transaction holds the workspace's audit chain head: the
    request's commit — the chain head is the last lock of a transaction — waits for it until the
    platform's 10 s lock timeout, as it does when two commits of a workspace meet a slow third.
    The holder lets go once the request has answered."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = run_request()
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertion below
            outcome["error"] = exc

    with observing_checkouts() as backends, tenant_session(_context(tenant_id)) as holder:
        holder_pid = backend_pid(holder)
        holder.execute(
            select(audit_chain_head.c.tenant_id)
            .where(audit_chain_head.c.tenant_id == tenant_id)
            .with_for_update()
        )
        request = threading.Thread(target=run, name="request-behind-the-chain-head")
        request.start()
        # Watched while it runs: a loaded machine takes its time to reach the commit, and a
        # request that answers without having waited for the chain head fails here by name.
        await_lock_wait(
            holder,
            holder_pid=holder_pid,
            backends=backends,
            timeout=180.0,
            expect="audit_chain_head",
            while_running=request.is_alive,
        )
        request.join(timeout=120)
        assert not request.is_alive(), "the request did not answer at its lock timeout"
    assert "error" not in outcome, outcome
    return outcome["result"]


class StoreStep:
    """What a test puts in place of ``lifecycle.shred_sidecar`` — the store's part of a shred —
    to make it meet what it can meet in production. It runs the real function unless told
    otherwise, and counts its calls."""

    def __init__(self, world: World, real: Callable[..., Any]) -> None:
        self._world = world
        self._real = real
        self.calls = 0
        self.mode = "work"
        self._holders: list[Any] = []

    def __call__(self, files: Any, storage_key: str, *, session: Any = None) -> Any:
        self.calls += 1
        if self.mode == "away":
            raise OSError("the store did not answer")
        if self.mode == "restored":
            # The store's part runs, and something brings the wrapped key back beside it: what
            # the hosted store reports as a generation still live after the passes.
            key = sidecar_key(storage_key)
            with files.open(key) as stored:
                wrapped = stored.read()
            self._real(files, storage_key, session=session)
            files.put(key, io.BytesIO(wrapped))
            raise GenerationConflict(f"{key} is still live at generation 1 after shredding")
        report = self._real(files, storage_key, session=session)
        if self.mode == "commit-fails":
            # The store's part is done; before the transaction that records it commits, another
            # transaction takes the workspace's audit chain head and keeps it past the timeout.
            scope = tenant_session(_context(self._world.tenant_id))
            holder = scope.__enter__()
            holder.execute(
                select(audit_chain_head.c.tenant_id)
                .where(audit_chain_head.c.tenant_id == self._world.tenant_id)
                .with_for_update()
            )
            self._holders.append((scope, holder))
        return report

    def release(self) -> None:
        for scope, holder in self._holders:
            holder.rollback()
            scope.__exit__(None, None, None)
        self._holders.clear()


@contextmanager
def _store_step(world: World, monkeypatch: pytest.MonkeyPatch, mode: str) -> Iterator[StoreStep]:
    """``lifecycle.shred_sidecar`` behaves as ``mode`` says for the block, and is itself after."""
    step = StoreStep(world, privacy.lifecycle.shred_sidecar)
    step.mode = mode
    with monkeypatch.context() as patch:
        patch.setattr(privacy.lifecycle, "shred_sidecar", step)
        try:
            yield step
        finally:
            step.release()


def _shred(world: World, stored: Stored) -> HttpResponse:
    return post(world.app, f"{FILES}/{stored.id}/shred", world.tess, {"reason": REASON})


def _shred_under(world: World, stored: Stored, key: str) -> HttpResponse:
    """``file.shred`` under a named ``Idempotency-Key``; ``_shred`` sends a fresh one each time."""
    headers = cookie_headers(world.tess.token, world.tess.csrf_token, key=False)
    headers["Idempotency-Key"] = key
    path = f"{FILES}/{stored.id}/shred"
    return call(world.app, "POST", path, json={"reason": REASON}, headers=headers)


# --- the three witnesses of the ruling ------------------------------------------------------------


def test_file_shred_durable_order_1_a_shred_that_is_not_saved_destroys_nothing(
    world: World,
) -> None:
    """``file.shred`` whose commit loses its wait for the audit chain head answers 409
    ``lock-conflict``, "… so nothing was saved" — and nothing was destroyed either: the row is
    unmarked, the chain holds no shred, the key stands and the content is served. Sent again,
    the command decides and completes: the decision on the chain first, then the completion
    with the store's report. Measured on the head before this order: the same 409 with the
    marker written, the key gone and the content 404 ``FILE_SHREDDED``."""
    letter = world.attachment("side-letter")
    lost = _while_the_chain_head_is_held(world.tenant_id, lambda: _shred(world, letter))
    assert _answer(lost) == (409, "lock-conflict", ["LOCK_TIMEOUT"]), lost.text
    assert lost.json()["detail"] == NOTHING_SAVED
    _untouched(world, letter)

    again = _shred(world, letter)
    assert again.status_code == 200 and again.json()["shredded_at"] is not None, again.text
    completion = _decided_and_completed(world, letter, road="command")
    assert (completion["marker_created"], completion["deleted_generations"]) == (True, [1])
    decision, completed = _events(world, letter)
    assert decision["actor_id"] == completed["actor_id"] == world.tess.member.user_id


def test_file_shred_durable_order_1_an_approval_that_is_not_saved_destroys_nothing(
    world: World,
) -> None:
    """The same for the approved shred of evidence: an approval whose commit loses its wait for
    the chain head answers 409, the request stays PENDING and the file is as it was. Decided
    again, the approval stands and the key is destroyed after its commit, by the principal that
    decided — SYSTEM on behalf of the requester. Measured on the head before this order: 409
    with the request PENDING, the row unmarked, no event — and the content gone."""
    source = world.import_source("customers")
    asked = post(world.app, f"{FILES}/{source.id}/request-shred", world.tess, {"reason": REASON})
    assert asked.status_code == 200, asked.text
    request_id = str(asked.json()["approval_request_id"])

    def status() -> str:
        (row,) = _rows(
            world.tenant_id,
            select(approval_request.c.status).where(approval_request.c.id == UUID(request_id)),
        )
        return str(getattr(row["status"], "value", row["status"]))

    lost = _while_the_chain_head_is_held(
        world.tenant_id, lambda: approve(world.app, request_id, world.carla)
    )
    assert _answer(lost) == (409, "lock-conflict", ["LOCK_TIMEOUT"]), lost.text
    assert status() == "PENDING"
    _untouched(world, source)

    decided = approve(world.app, request_id, world.carla)
    assert decided.status_code == 200 and status() == "APPROVED", decided.text
    completion = _decided_and_completed(world, source, road="command")
    assert (completion["marker_created"], completion["deleted_generations"]) == (True, [1])
    for event in _events(world, source):
        kind = str(getattr(event["actor_kind"], "value", event["actor_kind"]))
        assert (kind, event["on_behalf_of_id"]) == ("SYSTEM", world.tess.member.user_id), event


def test_file_shred_durable_order_1_a_completion_that_is_not_recorded_is_found_by_the_next_road(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: the decision is committed, the store's part is done, and the transaction
    that records the completion fails at its commit — a crash between the store's delete and
    the completion's event. The command has answered 200 with the decision; the row says that
    the completion is owed; the chain holds the decision and no completion. The next road runs
    the same function: it finds the marker, deletes nothing, and records the completion with
    the marker's own instant — ``file.shred`` sent again under a new ``Idempotency-Key`` (the
    same key replays the first answer and does nothing), as the administrator who sent it, and
    the sweep, as SYSTEM. Measured on the head before this order: the command itself answered
    409, because the store's part ran inside its transaction — the decision was lost and the key
    was gone."""
    first = world.attachment("side-letter")
    second = world.attachment("memo")
    keys = {first.id: f"k-{uuid4()}", second.id: f"k-{uuid4()}"}
    answers = []
    for stored in (first, second):
        with _store_step(world, monkeypatch, "commit-fails") as step:
            answers.append(_shred_under(world, stored, keys[stored.id]))
        assert step.calls == 1
    assert [answer.status_code for answer in answers] == [200, 200], [a.text for a in answers]
    for stored, answer in zip((first, second), answers, strict=True):
        body = answer.json()
        assert body["shredded_at"] is not None and body["shred_completed_at"] is None
        row = _row(world, stored)
        assert row["shredded_at"] is not None and row["shred_completed_at"] is None
        assert _actions(world, stored) == [(SHRED, "SUCCESS")]
        assert _store(world, stored) == {"marker": True, "sidecar": False}
        assert _read(world, stored) == (404, ["FILE_SHREDDED"])

    # The same request under the same key is a replay (04 API-C-04): the stored first answer,
    # and nothing is done — the completion stays owed.
    replayed = _shred_under(world, first, keys[first.id])
    assert replayed.status_code == 200 and replayed.headers.get("Idempotent-Replay") == "true"
    assert replayed.json() == answers[0].json()
    assert _row(world, first)["shred_completed_at"] is None
    assert _actions(world, first) == [(SHRED, "SUCCESS")]

    # Road two: the command sent again under a new key finishes it and answers what it did.
    retried = _shred(world, first)
    assert retried.status_code == 200, retried.text
    assert retried.json()["shred_completed_at"] is not None
    completion = _decided_and_completed(world, first, road="retry")
    assert (completion["marker_created"], completion["deleted_generations"]) == (False, [])
    assert _events(world, first)[1]["actor_id"] == world.tess.member.user_id
    # A completed shred is refused as before, by name.
    refused = _shred(world, first)
    assert _answer(refused) == (409, "invalid-transition", ["FILE_SHREDDED"]), refused.text

    # Road three: the sweep, once the command's own continuation has had its turn.
    from erev_api.domain.platform import shred_completion

    early = shred_completion.run(world.runtime, alert=False)
    assert (early.completed, early.failed) == (0, 0)
    world.clock.advance(shred_completion.GRACE)
    swept = shred_completion.run(world.runtime, alert=True)
    assert (swept.completed, swept.failed, swept.alerted) == (1, 0, ())
    row = _row(world, second)
    assert row["shred_completed_at"] == world.clock.now()
    decision, completed = _events(world, second)
    detail = completed["detail"]
    assert (detail["road"], detail["marker_created"], detail["deleted_generations"]) == (
        "sweep",
        False,
        [],
    )
    assert detail["marker_at"] is not None and detail["decided_at"] == (
        row["shredded_at"].isoformat()
    )
    kind = str(getattr(completed["actor_kind"], "value", completed["actor_kind"]))
    assert (kind, completed["actor_id"], completed["on_behalf_of_id"]) == ("SYSTEM", None, None)
    assert world.alerts.raised == []
    # Nothing is left for a later run.
    again = shred_completion.run(world.runtime, alert=True)
    assert (again.completed, again.failed, again.alerted) == (0, 0, ())


# --- the store's outage, the sweep and the operator alert -----------------------------------------


def test_file_shred_durable_order_1_a_store_that_is_away_leaves_the_decision_and_alerts(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store does not answer when the command's continuation runs. The command answers 200:
    the shred is decided, durably. Every reader of the workspace refuses the file by its row,
    the verifier says that the key still stands (``shredded_sidecar_present``), and nothing of
    the store was touched; the command sent again meanwhile fails and changes nothing. The
    sweep tries again at each run; a file still not completed 60
    minutes after its decision is told to the operators by the run at the full hour — the
    workspace, how many, how old; no file — and by no other run. When the store answers again
    the sweep completes the shred, as SYSTEM, and the alert stops."""
    from erev_api.controls.operator_alerts import RUNBOOK, SEVERITY, OperatorAlertKind
    from erev_api.domain.platform import shred_completion

    letter = world.attachment("side-letter")
    with _store_step(world, monkeypatch, "away") as step:
        decided = _shred(world, letter)
        assert decided.status_code == 200 and decided.json()["shredded_at"] is not None
        assert step.calls == 1
        row = _row(world, letter)
        assert row["shredded_at"] is not None and row["shred_completed_at"] is None
        assert _actions(world, letter) == [(SHRED, "SUCCESS")]
        assert _store(world, letter) == {"marker": False, "sidecar": True}
        assert _read(world, letter) == (404, ["FILE_SHREDDED"])
        status, _kek = recovery.check_file(row, files=world.files, keyring=world.keyring)
        assert status == "shredded_sidecar_present"

        # Sent again while the store is still away, the command fails as every command fails
        # that needs the store, and changes nothing: the decision stands, no completion.
        still = _shred(world, letter)
        assert still.status_code == 500, still.text
        assert step.calls == 2
        assert _row(world, letter)["shred_completed_at"] is None
        assert _actions(world, letter) == [(SHRED, "SUCCESS")]

        # The sweep leaves the command's continuation its turn, then tries at every run.
        early = shred_completion.run(world.runtime, alert=True)
        assert (early.completed, early.failed, early.alerted) == (0, 0, ())
        world.clock.advance(shred_completion.GRACE)
        tried = shred_completion.run(world.runtime, alert=True)
        assert (tried.completed, tried.failed, tried.alerted) == (0, 1, ())
        assert world.alerts.raised == []

        # Sixty minutes after the decision: the run at the full hour tells the operators.
        world.clock.advance(shred_completion.OVERDUE - shred_completion.GRACE)
        between = shred_completion.run(world.runtime, alert=False)
        assert (between.failed, between.alerted) == (1, ())
        assert world.alerts.raised == []
        hourly = shred_completion.run(world.runtime, alert=True)
        assert (hourly.completed, hourly.failed, hourly.alerted) == (0, 1, (world.tenant_id,))
        (alert,) = world.alerts.raised
        assert alert.kind is OperatorAlertKind.FILE_SHRED_INCOMPLETE
        assert (SEVERITY[alert.kind], RUNBOOK[alert.kind]) == ("WARNING", "RB-14")
        assert dict(alert.fields) == {
            "tenant_id": str(world.tenant_id),
            "files": 1,
            "oldest_minutes": 60,
        }
        assert _actions(world, letter) == [(SHRED, "SUCCESS")]

    # The store answers again: the next run completes the shred and raises nothing.
    back = shred_completion.run(world.runtime, alert=True)
    assert (back.completed, back.failed, back.alerted) == (1, 0, ())
    assert len(world.alerts.raised) == 1
    row = _row(world, letter)
    assert row["shred_completed_at"] == world.clock.now()
    assert _actions(world, letter) == [(SHRED, "SUCCESS"), (COMPLETE, "SUCCESS")]
    detail = _events(world, letter)[1]["detail"]
    assert (detail["road"], detail["marker_created"], detail["deleted_generations"]) == (
        "sweep",
        True,
        [1],
    )
    assert _store(world, letter) == {"marker": True, "sidecar": False}
    status, _kek = recovery.check_file(row, files=world.files, keyring=world.keyring)
    assert status == "shredded"


def test_file_shred_durable_order_1_a_key_that_came_back_is_refused_by_name_and_deleted_next(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store reports a wrapped key still live after the shred's passes — something restored
    it beside the shred (``GenerationConflict``). On the command's continuation that is a failed
    completion like any other: the decision stands and the row refuses every read, although the
    key is in the store again beside its marker. Sent again while it lasts, ``file.shred``
    answers 409 ``lock-conflict`` — nothing was saved — and not a 500; once nothing brings the
    key back, the same command deletes the generation that returned and records the
    completion."""
    letter = world.attachment("side-letter")
    with _store_step(world, monkeypatch, "restored"):
        decided = _shred(world, letter)
        assert decided.status_code == 200, decided.text
        assert _actions(world, letter) == [(SHRED, "SUCCESS")]
        assert _store(world, letter) == {"marker": True, "sidecar": True}
        assert _read(world, letter) == (404, ["FILE_SHREDDED"])

        refused = _shred(world, letter)
        assert _answer(refused) == (409, "lock-conflict", []), refused.text
        assert refused.json()["detail"] == (
            "Another change to the same records was being saved at the same moment, so nothing "
            "was saved. Resubmit the request."
        )
        assert _row(world, letter)["shred_completed_at"] is None
        assert _actions(world, letter) == [(SHRED, "SUCCESS")]

    finished = _shred(world, letter)
    assert finished.status_code == 200, finished.text
    completion = _decided_and_completed(world, letter, road="retry")
    assert (completion["marker_created"], completion["deleted_generations"]) == (False, [1])


def test_file_shred_durable_order_1_a_completed_shred_is_completed_once(world: World) -> None:
    """The plain case, and the positive control of the roads: the command's own continuation
    completes the shred before the request is answered, and a later road finds nothing to do —
    one decision and one completion on the chain, no alert."""
    from erev_api.domain.platform import shred_completion

    letter = world.attachment("side-letter")
    assert _shred(world, letter).status_code == 200
    _decided_and_completed(world, letter, road="command")
    world.clock.advance(shred_completion.OVERDUE)
    swept = shred_completion.run(world.runtime, alert=True)
    assert (swept.completed, swept.failed, swept.alerted) == (0, 0, ())
    assert _actions(world, letter) == [(SHRED, "SUCCESS"), (COMPLETE, "SUCCESS")]
    assert world.alerts.raised == []
