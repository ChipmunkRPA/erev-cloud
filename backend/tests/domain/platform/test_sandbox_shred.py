"""A sandbox destroys nothing it shares (item FILE-SHRED-SCOPE-1, part B1; the supervisor's
rulings of 2026-10-01 on the independent review of the ``EVIDENCE_SHRED`` merge 58eba434; 05 §10
SBX-08 rev 1.164, SBX-03, §6.17 PRV-07; 04 API-R-12 and §16.10 rev 1.225; PRD BR-FC-03 rev 1.156;
03 REQ-PLT-022, REQ-PLT-024; CTL-043).

A sandbox copy carries ``file_object`` rows with the storage keys of their source, and a shred
destroys the wrapped key at that storage key. Issued in the sandbox it destroyed the production
file — outside production's holds, approval and audit. Measured on the head before the rule:
after each of the three attempts below production's content read answered 404 ``FILE_SHREDDED``
while its row's ``shredded_at`` was NULL and its audit chain held neither an approval nor a
``file_object.shred``.

What a sandbox stored itself is its own: the object lies under the sandbox's own key, a reset
supersedes the sandbox and deletes nothing, so without a shred of its own such a document had no
erasure path at all. The three commands are admitted for it.

The world, through the product where the product has a command for it: a production workspace
with Tess (Tenant Admin: ``settings.manage``) and Carla (Controller), an attachment of a contract
that no record holds, the sources of two committed imports — each held by its import, a hold an
approved ``EVIDENCE_SHRED`` request lifts — and one such request pending when the copy is taken;
then the ``SANDBOX_COPY`` through the dispatched ``TENANT_SNAPSHOT`` job. The contract and the
two imports are rows, as in ``test_sandbox_load.py``'s plumbing world: this module is about the
stored objects, not about a computation.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.release import current_release
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    contract_event,
    file_attachment,
    file_object,
    tenant_snapshot,
)
from erev_api.domain.platform import guards, privacy
from erev_api.domain.platform import sandboxes as sb
from erev_api.enums import FilePurpose, JobKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, get, post, reject, slug
from support.rows import (
    contract_event_values,
    insert_contract_rows,
    insert_import_upload,
    tenant_snapshot_values,
)
from support.snapshots import (
    confirm_retention,
    cutoff_after,
    enter_workspace,
    run_dispatched_snapshot,
)
from support.stored_files import Stored, store

FILES = "/api/v1/files"
APPROVALS = "/api/v1/approvals"
REASON = "DSR-2026-0917: erase the person's data in this document"
RETENTION_FROM = FROZEN_AT - timedelta(days=1)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)
    stamp_test_release()
    application.state.engine_release = current_release()
    return application


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@pytest.fixture(autouse=True)
def snapshot_handler() -> Iterator[None]:
    """``TENANT_SNAPSHOT`` registered as the worker's import of its handler module registers it
    (DG-ARC-08), with the engine release stamped as the worker's startup stamps it."""
    from erev_api.domain.platform import snapshot_job

    stamp_test_release()
    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    yield
    if not present:
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@dataclass(frozen=True, slots=True)
class Copied:
    """A production workspace, its sandbox copy, and the two people in each of them."""

    production: UUID
    sandbox: UUID
    letter: Stored  # an attachment of a contract: no record holds it
    memo: Stored  # a second one, for the positive control
    source_a: Stored  # the source of a committed import
    source_b: Stored  # the source of another, with a shred request pending at the copy
    own_note: Stored  # stored in the sandbox after the copy: an attachment of the copied contract
    own_source: Stored  # stored in the sandbox: the source of an import committed there
    pending_request_id: str
    tess_in_sandbox: Actor
    carla_in_sandbox: Actor
    tess_in_production: Actor
    carla_in_production: Actor


@pytest.fixture
def copied(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime, files: LocalFileStore
) -> Copied:
    root = member(keyring, clock, name="tess")
    assign(root, "tenant_admin")
    tess = enrolled(app, clock, root)
    carla_member = colleague(root.tenant_id, "carla")
    assign(carla_member, "controller")
    carla = enrolled(app, clock, carla_member)
    production = root.tenant_id
    with tenant_session(_context(production)) as session:
        confirm_retention(session, production, at=RETENTION_FROM)
        rows = insert_contract_rows(session, production, head_stream_version=1)
        session.execute(
            insert(contract_event).values(
                **contract_event_values(
                    production,
                    contract_id=rows.contract_id,
                    contracting_entity_id=rows.entity_id,
                    stream_version=1,
                )
            )
        )
    kept = {"clock": clock, "keyring": keyring, "files": files}
    letter = store(production, FilePurpose.ATTACHMENT, "side-letter", **kept)
    memo = store(production, FilePurpose.ATTACHMENT, "memo", **kept)
    source_a = store(production, FilePurpose.IMPORT_SOURCE, "customers-a", **kept)
    source_b = store(production, FilePurpose.IMPORT_SOURCE, "customers-b", **kept)
    with tenant_session(_context(production)) as session:
        for attached in (letter, memo):
            session.execute(
                insert(file_attachment).values(
                    tenant_id=production,
                    id=uuid4(),
                    file_object_id=attached.id,
                    subject_type="contract",
                    subject_id=rows.contract_id,
                    created_by_kind="SYSTEM",
                )
            )
        for source in (source_a, source_b):
            insert_import_upload(
                session, tenant_id=production, file_object_id=source.id, status="COMMITTED"
            )
    # The third door: a request opened in production and PENDING when the copy is taken.
    asked = post(app, f"{FILES}/{source_b.id}/request-shred", tess, {"reason": REASON})
    assert asked.status_code == 200, asked.text
    pending_request_id = str(asked.json()["approval_request_id"])

    known_at = cutoff_after(production, clock)
    with tenant_session(_context(production)) as session:
        snapshot = tenant_snapshot_values(production, known_at=known_at, purpose="SANDBOX_COPY")
        session.execute(insert(tenant_snapshot).values(**snapshot))
    snapshot_id = UUID(str(snapshot["id"]))
    sandbox = UUID(int=int(snapshot_id) ^ 1)  # a distinct pre-allocated id
    # A sandbox's code is cut from its name and is unique in the deployment
    # (``SANDBOX_NAME_TAKEN``), and tenants stay for the session: each use of this world names
    # its own copy, so that two tests of the module can each load one. The name takes the END of
    # the snapshot's id: an id is a UUIDv7 (04 NC-04), whose first eight digits are its clock's
    # and stay the same for 65 seconds — two copies of one session shared them on a fast database.
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "SANDBOX_COPY",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox,
            name=f"Rehearsal {snapshot_id.hex[-12:]}",
            requested_by=root.user_id,
            restore=False,
        ),
    }
    result = run_dispatched_snapshot(production, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    # What the sandbox stores itself, after the copy: a note attached to the copied contract and
    # the source of an import committed there.
    own = {**kept, "kind": TenantKind.SANDBOX}
    own_note = store(sandbox, FilePurpose.ATTACHMENT, "sandbox-note", **own)
    own_source = store(sandbox, FilePurpose.IMPORT_SOURCE, "sandbox-customers", **own)
    with tenant_session(_context(sandbox)) as session:
        session.execute(
            insert(file_attachment).values(
                tenant_id=sandbox,
                id=uuid4(),
                file_object_id=own_note.id,
                subject_type="contract",
                subject_id=rows.contract_id,
                created_by_kind="SYSTEM",
            )
        )
        insert_import_upload(
            session, tenant_id=sandbox, file_object_id=own_source.id, status="COMMITTED"
        )
    # The cutoff moved the clock past every session opened before it: both sign in again.
    return Copied(
        production=production,
        sandbox=sandbox,
        letter=letter,
        memo=memo,
        source_a=source_a,
        source_b=source_b,
        own_note=own_note,
        own_source=own_source,
        pending_request_id=pending_request_id,
        tess_in_sandbox=enter_workspace(app, clock, tess, sandbox),
        carla_in_sandbox=enter_workspace(app, clock, carla, sandbox),
        tess_in_production=enter_workspace(app, clock, tess, production),
        carla_in_production=enter_workspace(app, clock, carla, production),
    )


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _file(tenant_id: UUID, file_id: UUID) -> dict[str, Any]:
    (row,) = _rows(
        tenant_id,
        select(file_object.c.storage_key, file_object.c.shredded_at).where(
            file_object.c.id == file_id
        ),
    )
    return row


def _request_status(tenant_id: UUID, request_id: str) -> str:
    (row,) = _rows(
        tenant_id,
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id)),
    )
    return str(row["status"])


def _refused_in_the_sandbox(response: HttpResponse) -> None:
    """403 ``sandbox-restricted`` with the refusal's own line: the status first, so that an
    answer that is no refusal fails on its status and shows its text."""
    assert response.status_code == 403, response.text
    assert slug(response) == guards.SLUG, response.text
    assert response.json()["detail"] == privacy.SANDBOX_SHRED


def _still_read_in_production(app: FastAPI, world: Copied, stored: Stored) -> None:
    """Production reads the bytes it stored, and its row says nothing was shredded."""
    served = get(app, f"{FILES}/{stored.id}/content", world.carla_in_production)
    assert served.status_code == 200, served.text
    assert served.content == stored.content
    assert _file(world.production, stored.id)["shredded_at"] is None


def _shred_events(tenant_id: UUID) -> list[tuple[str, str, UUID | None, Any]]:
    """(action, outcome, file, the refusal's problem) of the shred events of a workspace, in
    chain order."""
    return [
        (
            str(row["action"]),
            str(getattr(row["outcome"], "value", row["outcome"])),
            row["object_id"],
            (row["detail"] or {}).get("problem"),
        )
        for row in _rows(
            tenant_id,
            select(
                audit_event.c.action,
                audit_event.c.outcome,
                audit_event.c.object_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.action.in_([privacy.SHRED_ACTION, "file_object.request_shred"]))
            .order_by(audit_event.c.chain_seq),
        )
    ]


@pytest.mark.control("CTL-043")
def test_file_shred_scope_1_a_sandbox_destroys_nothing_it_shares(
    app: FastAPI, copied: Copied
) -> None:
    """The three doors of the review's finding B1, each refused in the sandbox by the sandbox
    rule with its ``DENIED`` event, and production's content still read byte for byte after
    each: the direct ``file.shred`` of a file no record holds; ``request-shred`` of a file a
    record holds; and the approval, in the sandbox, of a request that was pending when the copy
    was taken. The copied request stays PENDING there and can be rejected. What the sandbox
    stored itself is its own to erase: the same commands shred its note directly, and its
    import's source through a request its Controller approves — content gone in the sandbox,
    nothing of production touched. Positive controls: in production the same three commands do
    what they did — the attachment is shredded directly, the request is opened and its approval
    shreds, the pending request is approved."""
    world = copied
    tess, carla = world.tess_in_sandbox, world.carla_in_sandbox
    # The copy shares what it was copied from: the same storage key under another workspace.
    for stored in (world.letter, world.source_a, world.source_b):
        key = _file(world.sandbox, stored.id)["storage_key"]
        assert key == _file(world.production, stored.id)["storage_key"]
        assert key.startswith(f"{world.production}/")
    assert _request_status(world.sandbox, world.pending_request_id) == "PENDING"
    # Every stored file of the sandbox has a key of the form the rule reads — three segments,
    # the first the id of the workspace that stored the object: its source's, or its own.
    keys = [
        str(row["storage_key"]) for row in _rows(world.sandbox, select(file_object.c.storage_key))
    ]
    assert all(len(key.split("/")) == 3 for key in keys), keys
    assert {key.split("/")[0] for key in keys} == {str(world.production), str(world.sandbox)}

    # 1. The direct shred of a file no record holds.
    _refused_in_the_sandbox(post(app, f"{FILES}/{world.letter.id}/shred", tess, {"reason": REASON}))
    _still_read_in_production(app, world, world.letter)

    # 2. The request for a file a record holds: nothing is opened for the sandbox to approve.
    _refused_in_the_sandbox(
        post(app, f"{FILES}/{world.source_a.id}/request-shred", tess, {"reason": REASON})
    )
    _still_read_in_production(app, world, world.source_a)

    # 3. The request that was pending at the copy: its approval is refused, it stays PENDING ...
    _refused_in_the_sandbox(approve(app, world.pending_request_id, carla))
    assert _request_status(world.sandbox, world.pending_request_id) == "PENDING"
    assert (
        _rows(
            world.sandbox,
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(world.pending_request_id)
            ),
        )
        == []
    )
    _still_read_in_production(app, world, world.source_b)

    # Each attempt is on the sandbox's own chain as the command refused, and no file of the
    # sandbox says it was shredded.
    assert _shred_events(world.sandbox) == [
        (privacy.SHRED_ACTION, "DENIED", world.letter.id, guards.SLUG),
        ("file_object.request_shred", "DENIED", world.source_a.id, guards.SLUG),
        (privacy.SHRED_ACTION, "DENIED", world.source_b.id, guards.SLUG),
    ]
    for stored in (world.letter, world.source_a, world.source_b):
        assert _file(world.sandbox, stored.id)["shredded_at"] is None
    # ... and the sandbox can close its copy of the request: a rejection destroys nothing.
    rejected = reject(app, world.pending_request_id, carla, "A sandbox shreds nothing.")
    assert rejected.status_code == 200, rejected.text
    assert _request_status(world.sandbox, world.pending_request_id) == "REJECTED"
    _still_read_in_production(app, world, world.source_b)

    # What the sandbox stored itself lies under its own key and is its own to erase. Its note
    # is read there, shredded directly, and gone there ...
    for stored in (world.own_note, world.own_source):
        assert _file(world.sandbox, stored.id)["storage_key"].startswith(f"{world.sandbox}/")
    note = f"{FILES}/{world.own_note.id}"
    before = get(app, f"{note}/content", carla)
    assert before.status_code == 200 and before.content == world.own_note.content, before.text
    erased = post(app, f"{note}/shred", tess, {"reason": REASON})
    assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text
    gone = get(app, f"{note}/content", carla)
    assert (gone.status_code, slug(gone)) == (404, "not-found"), gone.text
    assert [error["rule_id"] for error in gone.json()["errors"]] == ["FILE_SHREDDED"]
    # ... and the source of its own committed import through a request its Controller approves.
    asked = post(app, f"{FILES}/{world.own_source.id}/request-shred", tess, {"reason": REASON})
    assert asked.status_code == 200, asked.text
    assert approve(app, str(asked.json()["approval_request_id"]), carla).status_code == 200
    assert _file(world.sandbox, world.own_source.id)["shredded_at"] is not None
    assert [event[:3] for event in _shred_events(world.sandbox)][3:] == [
        (privacy.SHRED_ACTION, "SUCCESS", world.own_note.id),
        ("file_object.request_shred", "SUCCESS", world.own_source.id),
        (privacy.SHRED_ACTION, "SUCCESS", world.own_source.id),
    ]
    # Nothing of production was touched: no shred is on its chain, and its files are read.
    assert [event[:2] for event in _shred_events(world.production)] == [
        ("file_object.request_shred", "SUCCESS")
    ]
    for stored in (world.letter, world.source_a, world.source_b):
        _still_read_in_production(app, world, stored)

    # Positive controls, in production: the three commands do what they did.
    tess, carla = world.tess_in_production, world.carla_in_production
    shredded = post(app, f"{FILES}/{world.memo.id}/shred", tess, {"reason": REASON})
    assert shredded.status_code == 200, shredded.text
    requested = post(app, f"{FILES}/{world.source_a.id}/request-shred", tess, {"reason": REASON})
    assert requested.status_code == 200, requested.text
    assert approve(app, str(requested.json()["approval_request_id"]), carla).status_code == 200
    assert approve(app, world.pending_request_id, carla).status_code == 200
    for stored in (world.memo, world.source_a, world.source_b):
        assert _file(world.production, stored.id)["shredded_at"] is not None
        gone = get(app, f"{FILES}/{stored.id}/content", carla)
        assert (gone.status_code, slug(gone)) == (404, "not-found"), gone.text
        assert [error["rule_id"] for error in gone.json()["errors"]] == ["FILE_SHREDDED"]
    # What production erased is gone for its copy as well (05 SBX-08: the key is shared, and the
    # marker decides): the copy's row was never stamped, and its read answers by name.
    for stored in (world.memo, world.source_a, world.source_b):
        assert _file(world.sandbox, stored.id)["shredded_at"] is None
        copy = get(app, f"{FILES}/{stored.id}/content", world.carla_in_sandbox)
        assert (copy.status_code, slug(copy)) == (404, "not-found"), copy.text
        assert [error["rule_id"] for error in copy.json()["errors"]] == ["FILE_SHREDDED"]
    # The file production did not shred is still production's to read.
    _still_read_in_production(app, world, world.letter)


@pytest.mark.control("CTL-043")
def test_file_shred_durable_order_1_a_sandbox_finishes_only_what_it_owns(
    app: FastAPI,
    copied: Copied,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item FILE-SHRED-DURABLE-ORDER-1 (05 PRV-07 b rev 1.171) meets SBX-08. A shred is decided
    on the row and its key destroyed afterwards, so a copy taken in between carries the mark and
    its source's key. The sandbox never finishes that shred: the command is refused there as for
    every shared file, the sweep SCH-16 reads own keys only, the function behind every road
    refuses the row itself, and no alert is raised for it — the source finishes its own shred,
    and the copy refuses the file by its row meanwhile. What the
    sandbox decided for a file it stored itself is finished there, by the sweep too; and it is
    finished even after the sandbox was archived, as a reset archives the sandbox it replaces —
    measured: the system's sweep still writes in an archived workspace, so an own file whose
    completion was owed at the reset does not keep its key."""
    from erev_api.auth.principal import system_principal
    from erev_api.db.tables import tenant
    from erev_api.domain.platform import shred_completion
    from erev_api.files.store import open_file, shred_marker_key, sidecar_key
    from erev_api.jobs.context import system_unit_of_work
    from sqlalchemy import update

    world = copied
    raised: list[Any] = []

    class Recording:
        def raise_alert(self, alert: Any) -> tuple[str, ...]:
            raised.append(alert)
            return ("list",)

    worker = JobRuntime(clock=clock, keyring=keyring, files=files, alerts=Recording())

    def full(tenant_id: UUID, file_id: UUID) -> dict[str, Any]:
        (row,) = _rows(tenant_id, select(file_object).where(file_object.c.id == file_id))
        return row

    def owed(tenant_id: UUID, file_id: UUID) -> tuple[bool, bool]:
        row = full(tenant_id, file_id)
        return (row["shredded_at"] is not None, row["shred_completed_at"] is not None)

    def away(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("the store did not answer")

    # The copied memo as a copy taken between a decision and its completion carries it: marked,
    # as the decision marks a row, with the source's key standing.
    memo_key = str(full(world.sandbox, world.memo.id)["storage_key"])
    assert memo_key.startswith(f"{world.production}/")
    with tenant_session(_context(world.sandbox)) as session:
        session.execute(
            update(file_object)
            .where(file_object.c.id == world.memo.id)
            .values(shredded_at=clock.now(), shredded_by_kind="SYSTEM", shred_reason=REASON)
        )
    # The command that would finish it is refused in the sandbox: the key is its source's.
    _refused_in_the_sandbox(
        post(app, f"{FILES}/{world.memo.id}/shred", world.tess_in_sandbox, {"reason": REASON})
    )

    # The sandbox's own note, decided there while the store is away: its completion is owed.
    with monkeypatch.context() as patch:
        patch.setattr(privacy.lifecycle, "shred_sidecar", away)
        decided = post(
            app, f"{FILES}/{world.own_note.id}/shred", world.tess_in_sandbox, {"reason": REASON}
        )
    assert decided.status_code == 200, decided.text
    assert owed(world.sandbox, world.own_note.id) == (True, False)

    clock.advance(shred_completion.GRACE)
    swept = shred_completion.run(worker, alert=True)
    assert (swept.completed, swept.failed, swept.alerted) == (1, 0, ())
    assert owed(world.sandbox, world.own_note.id) == (True, True)
    # The one function behind the roads refuses the copied row itself, whoever calls it ...
    with system_unit_of_work(
        worker, system_principal(world.sandbox), request_id="tests-own-key"
    ) as uow:
        finished = privacy.complete_shred(uow, world.memo.id, road=privacy.ROAD_SWEEP, files=files)
        assert finished is None
    # ... and the copied row is as it was: decided, never completed here, its source's key and
    # no marker in the store, and production reads its memo.
    assert owed(world.sandbox, world.memo.id) == (True, False)
    assert (files.exists(sidecar_key(memo_key)), files.exists(shred_marker_key(memo_key))) == (
        True,
        False,
    )
    with tenant_session(_context(world.production), read_only=True) as session:
        _row, stream = open_file(session, world.memo.id, files=files, keyring=keyring)
        assert stream.read() == world.memo.content

    # A second own file, decided while the store is away, in a sandbox that is then archived.
    late = store(
        world.sandbox,
        FilePurpose.ATTACHMENT,
        "sandbox-late-note",
        clock=clock,
        keyring=keyring,
        files=files,
        kind=TenantKind.SANDBOX,
    )
    with monkeypatch.context() as patch:
        patch.setattr(privacy.lifecycle, "shred_sidecar", away)
        decided = post(app, f"{FILES}/{late.id}/shred", world.tess_in_sandbox, {"reason": REASON})
    assert decided.status_code == 200, decided.text
    assert owed(world.sandbox, late.id) == (True, False)
    with tenant_session(_context(world.sandbox)) as session:
        archived = session.execute(
            update(tenant)
            .where(tenant.c.id == world.sandbox, tenant.c.status == "ACTIVE")
            .values(status="ARCHIVED", updated_at=clock.now(), updated_by_kind="SYSTEM")
            .returning(tenant.c.id)
        ).first()
    assert archived is not None
    clock.advance(shred_completion.OVERDUE)
    swept = shred_completion.run(worker, alert=True)
    assert (swept.completed, swept.failed, swept.alerted) == (1, 0, ())
    assert owed(world.sandbox, late.id) == (True, True)
    # An hour and more after its mark the copied row is still not completed here, and that is
    # no alert: it is not the sandbox's key.
    assert owed(world.sandbox, world.memo.id) == (True, False)
    assert raised == []


def test_sbx_file_read_1_a_copy_reads_the_files_it_was_copied_with(
    app: FastAPI,
    copied: Copied,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item SBX-FILE-READ-1 (05 SBX-03 rev 1.196; 04 T-PLT-29 rev 1.274). A copy carries its
    source's ``file_object`` rows with their storage keys, and content under a data key was
    sealed with the SOURCE's id in its associated data — while every reader named the row's own
    workspace. Measured before the rule: in the sandbox the download of a copied attachment and
    of a copied import source answered 500 without a ``file.download`` event, the verifier said
    ``undecryptable`` for both, and ``erev verify`` failed for every sandbox that carried one.

    The copy reads what it was copied with: the download answers production's bytes and writes
    its event on the sandbox's chain; the verifier says ``ok`` and the verification of the
    sandbox counts no failed file; bytes the copy already carries are stored under no key of
    its own (the write side, stated and unchanged); the rewrap of a copied file works from its
    key. Once production shreds a file the copy answers 404 ``FILE_SHREDDED`` and its verifier
    ``shredded`` — from the destruction of the key, not from production's decision: while a
    decided shred is not completed the copy still reads, and that is stated, not closed (the
    copy's row is never stamped).

    No new door: the row of a third workspace that names production's key opens nothing —
    ``open_file`` refuses it by name, its read through the product answers 500 with no
    ``file.download`` event and the log line ``files.foreign_storage_key``, the verifier says
    ``foreign_storage_key`` — and production opens nothing of its sandbox. Positive controls:
    production reads its own files, the sandbox its own note."""
    from erev_api.controls import recovery
    from erev_api.db.tables import tenant
    from erev_api.files import lifecycle
    from erev_api.files.store import ForeignStorageKey, open_file, storage_key

    world = copied
    carla = world.carla_in_sandbox

    def full(tenant_id: UUID, file_id: UUID) -> dict[str, Any]:
        (row,) = _rows(tenant_id, select(file_object).where(file_object.c.id == file_id))
        return row

    def downloads(tenant_id: UUID, file_id: UUID) -> list[str]:
        return [
            str(getattr(row["outcome"], "value", row["outcome"]))
            for row in _rows(
                tenant_id,
                select(audit_event.c.outcome)
                .where(audit_event.c.action == "file.download", audit_event.c.object_id == file_id)
                .order_by(audit_event.c.chain_seq),
            )
        ]

    def verified(tenant_id: UUID, file_id: UUID, *, source: UUID | None) -> str:
        status, _kek = recovery.check_file(
            full(tenant_id, file_id), files=files, keyring=keyring, source_tenant_id=source
        )
        return status

    # The copy's rows lie under production's keys, and the copy reads them: the bytes, the
    # event of the read on its own chain, and the verifier's word.
    for stored in (world.letter, world.source_a):
        assert _file(world.sandbox, stored.id)["storage_key"].startswith(f"{world.production}/")
        served = get(app, f"{FILES}/{stored.id}/content", carla)
        assert served.status_code == 200, served.text
        assert served.content == stored.content
        assert downloads(world.sandbox, stored.id) == ["SUCCESS"]
        assert downloads(world.production, stored.id) == []
        assert verified(world.sandbox, stored.id, source=world.production) == "ok"
    # ``erev verify`` over the sandbox: no failed file (two were ``undecryptable``).
    (code,) = _rows(world.sandbox, select(tenant.c.code).where(tenant.c.id == world.sandbox))
    document = recovery.verify_all_tenants(
        keyring=keyring,
        files=files,
        clock=clock,
        request_id="tests-sbx-file-read",
        tenant_codes=[str(code["code"])],
    )
    (workspace,) = document["tenants"]
    statuses = {entry["file_id"]: entry["status"] for entry in workspace["files"]["entries"]}
    assert workspace["files"]["failed"] == 0, statuses
    assert {statuses[str(stored.id)] for stored in (world.letter, world.source_a)} == {"ok"}

    # The write side is stated and unchanged (05 SBX-03; 04 T-PLT-29: one row per workspace,
    # content and purpose): the copy stores bytes it already carries under no key of its own —
    # the store answers the copied row, and the file stays shared with its source.
    carried = full(world.sandbox, world.source_a.id)
    same_bytes = store(
        world.sandbox,
        FilePurpose.IMPORT_SOURCE,
        "customers-a",
        clock=clock,
        keyring=keyring,
        files=files,
        kind=TenantKind.SANDBOX,
        content=world.source_a.content,
    )
    assert same_bytes.id == world.source_a.id
    assert full(world.sandbox, same_bytes.id)["storage_key"] == carried["storage_key"]
    own_form = storage_key(world.sandbox, FilePurpose.IMPORT_SOURCE, str(carried["sha256"]))
    assert not files.exists(own_form)

    # A rewrap of a copied file takes its workspace from the key: both workspaces still read.
    memo_key = str(_file(world.sandbox, world.memo.id)["storage_key"])
    assert lifecycle.rewrap_sidecar(files, keyring, memo_key).changed
    for reader in (carla, world.carla_in_production):
        again = get(app, f"{FILES}/{world.memo.id}/content", reader)
        assert again.status_code == 200 and again.content == world.memo.content, again.text

    # Production shreds the letter: the copy answers by name, and its verifier says shredded
    # although the copy's own row was never stamped.
    erased = post(
        app, f"{FILES}/{world.letter.id}/shred", world.tess_in_production, {"reason": REASON}
    )
    assert erased.status_code == 200, erased.text
    gone = get(app, f"{FILES}/{world.letter.id}/content", carla)
    assert (gone.status_code, slug(gone)) == (404, "not-found"), gone.text
    assert [error["rule_id"] for error in gone.json()["errors"]] == ["FILE_SHREDDED"]
    assert _file(world.sandbox, world.letter.id)["shredded_at"] is None
    assert verified(world.sandbox, world.letter.id, source=world.production) == "shredded"

    # What ends the copy's read is the destruction of the key, not production's decision (05
    # SBX-03 rev 1.196; PRV-07 b): the copy's row is never stamped, and the marker is written
    # with the destruction. While a decided shred is not completed — here the store's part
    # fails once — production refuses by its row and the copy still reads; the command sent
    # again completes it, and the copy answers by name.
    def away(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("the store did not answer")

    memo_shred = f"{FILES}/{world.memo.id}/shred"
    with monkeypatch.context() as patch:
        patch.setattr(privacy.lifecycle, "shred_sidecar", away)
        decided = post(app, memo_shred, world.tess_in_production, {"reason": REASON})
    assert decided.status_code == 200, decided.text
    at_home = full(world.production, world.memo.id)
    assert at_home["shredded_at"] is not None and at_home["shred_completed_at"] is None
    refused_at_home = get(app, f"{FILES}/{world.memo.id}/content", world.carla_in_production)
    assert (refused_at_home.status_code, slug(refused_at_home)) == (404, "not-found")
    assert verified(world.production, world.memo.id, source=None) == "shredded_sidecar_present"
    still = get(app, f"{FILES}/{world.memo.id}/content", carla)
    assert still.status_code == 200 and still.content == world.memo.content, still.text
    assert verified(world.sandbox, world.memo.id, source=world.production) == "ok"
    completed = post(app, memo_shred, world.tess_in_production, {"reason": REASON})
    assert completed.status_code == 200, completed.text
    assert full(world.production, world.memo.id)["shred_completed_at"] is not None
    ended = get(app, f"{FILES}/{world.memo.id}/content", carla)
    assert (ended.status_code, slug(ended)) == (404, "not-found"), ended.text
    assert [error["rule_id"] for error in ended.json()["errors"]] == ["FILE_SHREDDED"]
    assert verified(world.sandbox, world.memo.id, source=world.production) == "shredded"

    # No new door. A row that names the object of a workspace that is neither its own nor its
    # sandbox's source opens nothing. By its facts each row below is its reader's own upload,
    # so the read reaches the store: 500, as an integrity fault is answered, no event of the
    # read, the log line that names the row, and the verifier's status of its own.
    def foreign_row(tenant_id: UUID, like: dict[str, Any], *, stored_by: UUID) -> UUID:
        file_id = uuid4()
        with tenant_session(_context(tenant_id)) as session:
            session.execute(
                insert(file_object).values(
                    tenant_id=tenant_id,
                    id=file_id,
                    sha256=like["sha256"],
                    size_bytes=like["size_bytes"],
                    media_type=like["media_type"],
                    purpose=like["purpose"],
                    storage_backend=like["storage_backend"],
                    storage_key=like["storage_key"],
                    created_at=clock.now(),
                    created_by=stored_by,
                    created_by_kind="USER",
                )
            )
        return file_id

    def opens_nothing(tenant_id: UUID, file_id: UUID, reader: Actor) -> None:
        with tenant_session(_context(tenant_id), read_only=True) as session:
            with pytest.raises(ForeignStorageKey):
                open_file(session, file_id, files=files, keyring=keyring)
        refused = get(app, f"{FILES}/{file_id}/content", reader)
        assert refused.status_code == 500, refused.text
        assert downloads(tenant_id, file_id) == []
        assert verified(tenant_id, file_id, source=None) == "foreign_storage_key"

    # A third workspace's row that names production's key ...
    outsider = member(keyring, clock, name="mallory")
    assign(outsider, "tenant_admin")
    mallory = enrolled(app, clock, outsider)
    named = full(world.production, world.source_a.id)
    foreign_id = foreign_row(outsider.tenant_id, named, stored_by=outsider.user_id)
    opens_nothing(outsider.tenant_id, foreign_id, mallory)
    # ... and production opens nothing its sandbox stored: the rule has one direction.
    own = full(world.sandbox, world.own_note.id)
    carla_at_home = world.carla_in_production
    reversed_id = foreign_row(world.production, own, stored_by=carla_at_home.member.user_id)
    opens_nothing(world.production, reversed_id, carla_at_home)
    faults = [
        line
        for line in (json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip())
        if line["event"] == "files.foreign_storage_key"
    ]
    assert {fault["level"] for fault in faults} == {"error"}
    assert {(fault["tenant_id"], fault["file_id"], fault["storage_key"]) for fault in faults} == {
        (str(outsider.tenant_id), str(foreign_id), named["storage_key"]),
        (str(world.production), str(reversed_id), own["storage_key"]),
    }

    # Positive controls: each workspace reads what it stored itself.
    _still_read_in_production(app, world, world.source_a)
    assert verified(world.production, world.source_a.id, source=None) == "ok"
    note = get(app, f"{FILES}/{world.own_note.id}/content", carla)
    assert note.status_code == 200 and note.content == world.own_note.content, note.text
    assert verified(world.sandbox, world.own_note.id, source=world.production) == "ok"
