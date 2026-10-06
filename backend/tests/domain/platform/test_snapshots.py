"""BUILD_SPEC SNP-1 acceptance tests of the tenant snapshot (05 SBX-03, SBX-06, SBX-11; T-PLT-34).

WRITTEN IN SLICES I-2 AND I-3 AND NOT RUN: the lane databases ``erev_rv_l23_*`` are Ray-side
(lane record §13.2). They need the provisioned database; the writer is slice I-3's
``PutFileWriter`` (``snapshot_job.writer_for``). The handler module is
imported inside the tests, never at module level, so collecting this file does not register the
kind while ``TENANT_SNAPSHOT`` is still in ``PENDING_JOB_HANDLERS`` (DG-ARC-08).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any, BinaryIO
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract_event,
    file_object,
    tenant_membership,
    tenant_snapshot,
)
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_retention
from erev_api.enums import JobKind, MembershipStatus
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.problems import Problem
from sqlalchemy import func, insert, select, text
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.principals import member
from support.rows import (
    RowContext,
    contract_event_values,
    insert_app_user,
    insert_contract_rows,
    membership_row,
    tenant_snapshot_values,
)
from support.snapshots import confirm_retention, run_dispatched_snapshot

KNOWN_AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
def job() -> Iterator[ModuleType]:
    """The handler module, registered for the test and deregistered afterwards (``task`` refuses a
    second registration; an already-imported module is re-registered by hand), with the engine
    release stamped as the worker's startup stamps it (05 REL-03): an unstamped process refuses
    to export (the autouse conftest fixture forgets the stamp after the test)."""
    from erev_api.domain.platform import snapshot_job

    stamp_test_release()
    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS  # the worker registers it (DG-ARC-08)
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    yield snapshot_job
    if not present:  # pop only what this fixture registered
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _confirm_retention(tenant_id: UUID, *, human: bool = True) -> UUID:
    """The human confirmation ruling Q-4 requires (slices I-5 / I-5.3 / I-5.5): the evidence is
    built in the order the database admits (support.snapshots.confirm_retention; DB-10 trigger of
    migration 0013). ``human=False`` publishes the version with no decision at all and no
    publisher — the narrower missing-human-evidence case, not the shape record_auto_approval
    leaves (Codex I55-DOC1) — so the job refuses RETENTION_UNCONFIRMED."""
    with tenant_session(_context(tenant_id)) as session:
        return confirm_retention(session, tenant_id, at=KNOWN_AT - timedelta(days=1), human=human)


def _tenant(keyring: KeyRing, clock: FrozenClock) -> UUID:
    """A production tenant whose retention families are confirmed (Codex I55-S1): created through
    ``support.principals.member`` so its admin holds an ACTIVE membership — the approver the
    shared helper selects — where a plain ``tenant_factory`` leaves the admin INVITED."""
    tenant_id = member(keyring, clock).tenant_id
    _confirm_retention(tenant_id)
    return tenant_id


def _counts(tenant_id: UUID) -> dict[str, int]:
    """Row counts of every copied table, file_object without the snapshot's own files (purpose
    SNAPSHOT_DATASET): the export writes those into the source tenant by design (T-PLT-34
    manifest_file_id → file_object) and test_source_unchanged_and_audited counts them apart."""
    from erev_api.db.tables import metadata
    from erev_api.domain.platform.snapshot_dataset import LOAD_ORDER

    with tenant_session(_context(tenant_id), read_only=True) as session:
        counts: dict[str, int] = {}
        for name in LOAD_ORDER:
            table = metadata.tables[f"erev.{name}"]
            statement = select(func.count()).select_from(table)
            if name == "file_object":
                statement = statement.where(table.c.purpose != "SNAPSHOT_DATASET")
            counts[name] = int(session.execute(statement).scalar_one())
        return counts


def _run(
    job: ModuleType, tenant_id: UUID, snapshot_id: UUID, clock: FrozenClock, runtime: JobRuntime
) -> Any:
    return registry.run_inline(
        JobKind.TENANT_SNAPSHOT,
        {
            "tenant_snapshot_id": str(snapshot_id),
            "known_at": KNOWN_AT.isoformat(),
            "purpose": "STORED_BACKUP",
        },
        tenant_id=tenant_id,
        principal=system_principal(tenant_id),
        clock=clock,
        runtime=runtime,
    )


def _snapshot(tenant_id: UUID) -> UUID:
    with tenant_session(_context(tenant_id)) as session:
        row = tenant_snapshot_values(tenant_id, known_at=KNOWN_AT)
        session.execute(insert(tenant_snapshot).values(**row))
    return UUID(str(row["id"]))


def _runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def test_snapshot_copies_facts_not_derived(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The manifest lists one JSONL file per copied dataset and none for the derived, audit,
    integration, support, credential or session tables (05 SBX-03)."""
    tenant_id = _tenant(keyring, clock)
    snapshot_id = _snapshot(tenant_id)
    _run(job, tenant_id, snapshot_id, clock, _runtime(app_settings, keyring, clock))
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
    assert row["status"] == "SUCCEEDED"
    listed = set(row["row_counts"])
    assert listed == set(sd.LOAD_ORDER)
    for name in (
        "contract_computation",
        "contract_version",
        "schedule_line",
        "calc_trace",
        "subledger_posting",
        "journal_run",
        "report_run",
        "lock_snapshot",
        "audit_event",
        "webhook_endpoint",
        "support_grant",
        "api_client",
        "user_session",
    ):
        assert name not in listed


def test_known_at_cutoff(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """A contract_event recorded after known_at is absent from the contract_event dataset (SBX-03).

    Oracle: two events on one contract, the database clock read between them as known_at (DB-08
    stamps recorded_at from the database clock, not the frozen application clock); the dataset
    holds exactly the events recorded at or before that instant — one of two."""
    tenant_id = _tenant(keyring, clock)
    with tenant_session(_context(tenant_id)) as session:
        rows = insert_contract_rows(session, tenant_id, head_stream_version=2)
        session.execute(
            insert(contract_event).values(
                **contract_event_values(
                    tenant_id,
                    contract_id=rows.contract_id,
                    contracting_entity_id=rows.entity_id,
                    stream_version=1,
                )
            )
        )
    with tenant_session(_context(tenant_id), read_only=True) as session:
        known_at = session.execute(text("SELECT now()")).scalar_one()
    # The database clock is real time; the frozen application clock stands at 2026-09-12 and the
    # job refuses a known_at later than now (SNP-1 params check) — move the clock to known_at.
    clock.set(known_at)
    with tenant_session(_context(tenant_id)) as session:
        session.execute(
            insert(contract_event).values(
                **contract_event_values(
                    tenant_id,
                    contract_id=rows.contract_id,
                    contracting_entity_id=rows.entity_id,
                    stream_version=2,
                )
            )
        )
    with tenant_session(_context(tenant_id)) as session:
        snapshot = tenant_snapshot_values(tenant_id, known_at=known_at)
        session.execute(insert(tenant_snapshot).values(**snapshot))
    outcome = registry.run_inline(
        JobKind.TENANT_SNAPSHOT,
        {
            "tenant_snapshot_id": str(snapshot["id"]),
            "known_at": known_at.isoformat(),
            "purpose": "STORED_BACKUP",
        },
        tenant_id=tenant_id,
        principal=system_principal(tenant_id),
        clock=clock,
        runtime=_runtime(app_settings, keyring, clock),
    )
    assert outcome.state == "SUCCEEDED"
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot["id"]))
            .mappings()
            .one()
        )
        total = session.execute(select(func.count()).select_from(contract_event)).scalar_one()
        by_then = session.execute(
            select(func.count())
            .select_from(contract_event)
            .where(contract_event.c.recorded_at <= known_at)
        ).scalar_one()
    assert (total, by_then) == (2, 1)
    assert row["row_counts"]["contract_event"] == by_then == 1


def test_manifest_hashes_and_counts(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Each file's SHA-256 and row count equal the manifest; manifest_sha256 equals the SHA-256 of
    the manifest bytes; status ends SUCCEEDED."""
    import hashlib
    import json

    from erev_api.files.store import open_file

    tenant_id = _tenant(keyring, clock)
    snapshot_id = _snapshot(tenant_id)
    runtime = _runtime(app_settings, keyring, clock)
    _run(job, tenant_id, snapshot_id, clock, runtime)
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        assert row["status"] == "SUCCEEDED"
        _, stream = open_file(
            session, row["manifest_file_id"], files=runtime.files, keyring=keyring
        )  # type: ignore[arg-type]
        manifest_bytes = stream.read()
        assert hashlib.sha256(manifest_bytes).hexdigest() == row["manifest_sha256"]
        manifest = json.loads(manifest_bytes)
        assert {e["name"]: e["row_count"] for e in manifest["datasets"]} == dict(row["row_counts"])
        for entry in manifest["datasets"]:
            if entry["row_count"] == 0:  # I-3: a dataset with no rows is not stored
                assert entry["sha256"] == sd.EMPTY_SHA256
                assert (
                    session.execute(
                        select(file_object).where(file_object.c.sha256 == entry["sha256"])
                    ).one_or_none()
                    is None
                )
                continue
            stored = (
                session.execute(select(file_object).where(file_object.c.sha256 == entry["sha256"]))
                .mappings()
                .one()
            )
            _, content = open_file(session, stored["id"], files=runtime.files, keyring=keyring)  # type: ignore[arg-type]
            data = content.read()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            assert data.count(b"\n") == entry["row_count"]


def test_source_unchanged_and_audited(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Row counts of every source table are unchanged and the source records one audit event
    tenant.snapshot_created (05 SBX-06, SBX-11)."""
    import json

    from erev_api.files.store import open_file

    tenant_id = _tenant(keyring, clock)
    snapshot_id = _snapshot(tenant_id)
    runtime = _runtime(app_settings, keyring, clock)
    before = _counts(tenant_id)
    _run(job, tenant_id, snapshot_id, clock, runtime)
    after = _counts(tenant_id)
    assert after == before
    with tenant_session(_context(tenant_id), read_only=True) as session:
        # the only rows the export adds to the source are its own files: one per stored dataset
        # plus the manifest (purpose SNAPSHOT_DATASET), which _counts leaves out above
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        _, stream = open_file(
            session, row["manifest_file_id"], files=runtime.files, keyring=keyring
        )  # type: ignore[arg-type]
        manifest = json.loads(stream.read())
        snapshot_files = session.execute(
            select(func.count())
            .select_from(file_object)
            .where(file_object.c.purpose == "SNAPSHOT_DATASET")
        ).scalar_one()
        assert snapshot_files == sum(1 for e in manifest["datasets"] if e["row_count"] > 0) + 1
        created = session.execute(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action == job.ACTION_CREATED)
        ).scalar_one()
    assert created == 1


class FailingStore:
    """A storage adapter that fails on its N-th put (mock adapter over the local store; slice I-3
    write-error acceptance — no live storage)."""

    backend = "local"

    def __init__(self, inner: LocalFileStore, *, fail_at: int = 3) -> None:
        self._inner = inner
        self._fail_at = fail_at
        self.puts = 0

    def put(self, storage_key: str, stream: BinaryIO) -> tuple[str, int]:
        self.puts += 1
        if self.puts == self._fail_at:
            raise OSError("simulated storage failure")
        return self._inner.put(storage_key, stream)

    def open(self, storage_key: str) -> BinaryIO:
        return self._inner.open(storage_key)

    def exists(self, storage_key: str) -> bool:
        return self._inner.exists(storage_key)


def test_write_error_ends_failed_and_names_the_written_datasets(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """A failing store ends the job and the row FAILED before any manifest exists; the failure
    audit names the datasets already stored and the one that failed (slice I-3)."""
    tenant_id = _tenant(keyring, clock)
    snapshot_id = _snapshot(tenant_id)
    store = FailingStore(LocalFileStore(app_settings.file_root))
    job_row = run_dispatched_snapshot(
        tenant_id,
        {
            "tenant_snapshot_id": str(snapshot_id),
            "known_at": KNOWN_AT.isoformat(),
            "purpose": "STORED_BACKUP",
        },
        runtime=JobRuntime(clock=clock, keyring=keyring, files=store),
        now=clock.now(),
    )  # the persisted dispatch path: run_job catches the refusal and runs on_failure (PREP-S1)
    assert job_row["state"] == "FAILED"
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        failed = (
            session.execute(
                select(audit_event.c.detail).where(audit_event.c.action == job.ACTION_FAILED)
            )
            .scalars()
            .all()
        )
    assert row["status"] == "FAILED" and row["manifest_file_id"] is None
    assert len(failed) == 1
    detail = failed[0]
    assert isinstance(detail["written"], list) and detail["failed"] is not None
    assert {e["rule_id"] for e in detail["errors"]} == {"SNP-1-WRITTEN", "SNP-1-WRITE"}


def test_unset_retention_refuses_the_job(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The refusing default (slice I-5): without a PUBLISHED TENANT version confirming the
    families the handler refuses by name at the inline boundary (the FAILED lifecycle through the
    dispatch path is pinned in tests/pg/test_snapshot_retention_evidence.py); no manifest exists."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))  # not confirmed
    snapshot_id = _snapshot(tenant_id)
    with pytest.raises(Problem) as info:  # the inline boundary (Codex PREP-S1)
        registry.run_inline(
            JobKind.TENANT_SNAPSHOT,
            {
                "tenant_snapshot_id": str(snapshot_id),
                "known_at": KNOWN_AT.isoformat(),
                "purpose": "STORED_BACKUP",
            },
            tenant_id=tenant_id,
            principal=system_principal(tenant_id),
            clock=clock,
            runtime=_runtime(app_settings, keyring, clock),
        )
    assert info.value.slug == "precondition-failed"
    # PRD ERR-77 (BUILD_SPEC SNP-5): the refusal says who sets and who approves the policy and
    # from when copies are possible; it no longer names the registry key.
    assert info.value.detail == snapshot_retention.NONE
    assert [error.rule_id for error in info.value.errors] == ["RETENTION_UNSET"]
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        stored = session.execute(
            select(func.count())
            .select_from(file_object)
            .where(file_object.c.purpose == "SNAPSHOT_DATASET")
        ).scalar_one()
    # observed narrowly: no manifest reference and no dataset file — the guard precedes dataset
    # access, not every earlier SQL statement (Codex PREP-S1)
    assert row["manifest_file_id"] is None and stored == 0


def test_a_confirmed_retention_that_is_not_in_force_yet_names_its_instant(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """PRD ERR-77 (BUILD_SPEC SNP-5; item CFG-PLATFORM-PIN-1): a policy approved by a named human
    on 12 Sep 2026 and in force from 15 Sep 2026 12:00 UTC does not cover a snapshot as of
    12 Sep — the refusal names the instant from which copies are possible. Positive control: the
    same request as of an instant after it is exported."""
    tenant_id = member(keyring, clock).tenant_id  # its admin is the named approver
    runtime = _runtime(app_settings, keyring, clock)

    def asked(known_at: datetime) -> Problem | None:
        with tenant_session(_context(tenant_id)) as session:
            row = tenant_snapshot_values(tenant_id, known_at=known_at)
            session.execute(insert(tenant_snapshot).values(**row))
        try:
            registry.run_inline(
                JobKind.TENANT_SNAPSHOT,
                {
                    "tenant_snapshot_id": str(row["id"]),
                    "known_at": known_at.isoformat(),
                    "purpose": "STORED_BACKUP",
                },
                tenant_id=tenant_id,
                principal=system_principal(tenant_id),
                clock=clock,
                runtime=runtime,
            )
        except Problem as refused:
            return refused
        return None

    with tenant_session(_context(tenant_id)) as session:
        confirm_retention(
            session, tenant_id, at=KNOWN_AT, effective_from=KNOWN_AT + timedelta(days=3)
        )
    early = asked(KNOWN_AT)
    assert early is not None and early.slug == "precondition-failed"
    assert early.detail == snapshot_retention.NOT_YET.format(
        approved="12 Sep 2026", effective="15 Sep 2026 12:00 UTC"
    )
    assert [error.rule_id for error in early.errors] == ["RETENTION_UNSET"]
    clock.advance(timedelta(days=3, minutes=1))
    assert asked(clock.now()) is None


def test_retention_without_human_evidence_refuses_the_job(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Ruling D-98 cand. 86 (slices I-5.3 / I-5.6): an in-force version published with no decision
    and no publisher — missing human evidence — refuses RETENTION_UNCONFIRMED by name before any
    count, read or write. The proper AUTO_APPROVE-decision shape is pinned by the pure test
    ``test_retention_confirmation_requires_a_named_human_approval``; a DB-bound case through a real
    ``record_auto_approval`` row is owed (lane record §13.2.26)."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    _confirm_retention(tenant_id, human=False)
    snapshot_id = _snapshot(tenant_id)
    with pytest.raises(Problem) as info:  # the inline boundary (Codex PREP-S1)
        registry.run_inline(
            JobKind.TENANT_SNAPSHOT,
            {
                "tenant_snapshot_id": str(snapshot_id),
                "known_at": KNOWN_AT.isoformat(),
                "purpose": "STORED_BACKUP",
            },
            tenant_id=tenant_id,
            principal=system_principal(tenant_id),
            clock=clock,
            runtime=_runtime(app_settings, keyring, clock),
        )
    assert info.value.slug == "precondition-failed"
    assert "RETENTION_UNCONFIRMED" in str(info.value)
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = (
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        stored = session.execute(
            select(func.count())
            .select_from(file_object)
            .where(file_object.c.purpose == "SNAPSHOT_DATASET")
        ).scalar_one()
    # observed narrowly: no manifest reference and no dataset file — the guard precedes dataset
    # access, not every earlier SQL statement (Codex PREP-S1)
    assert row["manifest_file_id"] is None and stored == 0


def test_the_copy_reads_the_tenants_memberships_alone_whoever_runs_it(
    committed_db: TestDatabase, keyring: KeyRing, job: ModuleType
) -> None:
    """Item USERS-MEMBER-TENANT-1 (dev-guide DG-KRN-DB-12; found by the independent review of the
    head): the export reads the table of every dataset whole, taken from the model by name —
    ``tenant_membership`` among them — and each read names the tenant, so that a copy holds its
    source's memberships whoever's transaction reads them. The worker reads as SYSTEM; the
    handler also runs inline under a person's principal (the perf seed). U belongs to A and to
    B under ONE membership id, as a loaded sandbox holds the memberships of its source.

    Fail-first (b2492dd4, the two reads without the tenant): with U as the reader's user A's
    dataset held three rows, U's membership of B among them, and the count said three."""
    a, b = (tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2))
    with identity_session(request_id="tests-copy-reader") as session:
        u = insert_app_user(session)
    shared = new_id()
    for tenant_id in (a, b):
        with tenant_session(_context(tenant_id)) as session:
            row = membership_row(RowContext(tenant_id, u), status=MembershipStatus.ACTIVE)
            session.execute(insert(tenant_membership).values(**(row | {"id": shared})))
    dataset = sd.inventory().dataset("tenant_membership")
    facts = {}
    for label, user_id in (("U", u), ("no user", None)):
        reader = job.DbSnapshotReader(DbContext(tenant_id=a, user_id=user_id, entity_scope="*"))
        rows = reader.rows(dataset)
        facts[label] = (
            sorted({"A" if row["tenant_id"] == a else "another" for row in rows}),
            len(rows),
            reader.counts()["tenant_membership"],
        )
    # A's members: its provisioned administrator and U.
    assert facts == {"U": (["A"], 2, 2), "no user": (["A"], 2, 2)}
