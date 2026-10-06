"""SNP-2 sandbox load and determinism verification — the database witnesses (BUILD_SPEC SNP-2
acceptance; 05 SBX-02 to SBX-06 rev 1.20; 04 rev 1.67; D-98 candidate 137). Written in lane F-SNP
without a database; first measured in a lane database by lane FIX-D1 (2026-09-29), which added the
copy-phase witnesses at the end of the module (05 SBX-04 rev 1.30).

The K-03 copy case (BUILD_SPEC ``test_sandbox_copy_k03``; build-spec fragment 14 rev 1.5,
supervisor ruling R-43 (c)) runs on the world BUILD_SPEC names: ``worlds.k03_castellan``, the
cost-to-cost project ``PRJ-CB-2026-01`` through the product's commands (on main since RPS-10 and
RPS-11), taken through J-06 and J-10 to WLD-X-12 — the farthest state ``tests/support/worlds.py``
builds. It replaces the two named substitutions of the D-98 137 ruling on the k03 dependency,
which held "until the K03 world exists": a lane-built world of directly inserted rows (ONE
combination group without a member, which no engine can compute — D-98 137 amendment 4 R1, a
QUARANTINED group is not a recompute) and then ``worlds.k01_pellworth`` (lane FIX-D1; supervisor
ruling 2026-09-30).

Still owed, to SNP-2b (supervisor ruling R-10): the WLD-X-13 state BUILD_SPEC first named —
cumulative revenue 829,852.94 after the J-14 correction posted in reopened September, Sep 2026
``closed`` and Oct 2026 ``open`` after the re-lock. It needs the source's lock chain on this
world and the close run the sandbox cannot replay yet; that figure is not asserted here.

The manual-adjustment edge of the ``stream`` component (ruling R-43 (b)) runs on WLD-K-01 with a
``MANUAL_RELEASE`` prepared, approved and posted through the product's CLO-12 commands — it
stood on directly inserted rows until those commands landed — and verifies the copy's figures.

The other cases keep the minimal world of ``_world``: they witness the load's plumbing, not a
computation.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.secrets.provision import TenantKeyProvisioningError
from erev_api.auth.keyring import DerivedTenantKeyProvisioner, KeyRing, in_adapter_namespace
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db import transitions as tx
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_request,
    audit_event,
    contract_event,
    contract_version,
    exception_item,
    file_object,
    import_upload,
    integration_connection,
    ledger_chain_head,
    legal_entity,
    manual_adjustment,
    metadata,
    notification,
    obligation,
    outbox_message,
    period_state,
    registry_version,
    role,
    role_assignment,
    security_event,
    support_grant,
    tenant,
    tenant_membership,
    tenant_snapshot,
    user_session,
    webhook_delivery,
    webhook_endpoint,
)
from erev_api.domain.imports import scope as import_scope
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_export as sx
from erev_api.enums import FilePurpose, JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session
from support.adapter_secrets import keyring_with, tenant_ref
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import call
from support.links import emailed_token
from support.principals import PASSWORD, Actor, Member, enrolled, member
from support.reference import approve, assign, get, post
from support.rows import (
    contract_event_values,
    file_object_values,
    insert_contract_rows,
    insert_import_upload,
    insert_sealed_webhook_endpoint,
    integration_connection_values,
    legal_entity_values,
    tenant_snapshot_values,
)
from support.snapshots import (
    LOAD_RECOMPUTE_ACTIONS,
    confirm_retention,
    cutoff_after,
    enter_workspace,
    load_chain,
    load_outcome,
    load_step,
    run_dispatched_snapshot,
    unexplained_load_events,
)
from support.worlds import (
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    k01_pellworth,
    k03_castellan,
    k03_change_order,
    k03_september,
)

# The retention confirmation is in force from the day before the frozen application clock. The
# snapshot cutoff is NOT a constant: a world lives on two clocks (the frozen application clock and
# the database's real one, which stamps DB-08 ``recorded_at`` and the defaulted ``created_at`` of
# the rows ``_world`` inserts), so each case takes ``known_at`` from the database once its world
# is complete (``support.snapshots.cutoff_after``) — a cutoff on the frozen clock cuts those rows
# out of the snapshot (ruling Q-6), and the copy is then correctly smaller than the source.
RETENTION_FROM = FROZEN_AT - timedelta(days=1)
# SNAPSHOT_DATASET files and the AUDIT_DIGEST load report are the job's own rows in the source.
_JOB_FILE_PURPOSES = ("SNAPSHOT_DATASET", "AUDIT_DIGEST")
ADJUSTMENTS = "/api/v1/manual-adjustments"
SCHEDULE_LINES = "/api/v1/schedule-lines"
OCTOBER_2026 = "FY2026-P10"


@pytest.fixture
def job() -> Iterator[ModuleType]:
    """The handler module, registered for the test, with the engine release stamped as the worker's
    startup stamps it (05 REL-03): an unstamped process refuses to export, and the autouse conftest
    fixture forgets the stamp after every test (05 REL-05) — so the stamp is per test, the shape of
    ``test_snapshots.py``."""
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
    if not present:
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _world(keyring: KeyRing, clock: FrozenClock) -> Member:
    """The lane-built minimal world of the plumbing cases (it computes nothing): a production
    tenant whose admin holds an ACTIVE membership, retention confirmed, one contract chain with
    one stream event."""
    someone = member(keyring, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        confirm_retention(session, someone.tenant_id, at=RETENTION_FROM)
        rows = insert_contract_rows(session, someone.tenant_id, head_stream_version=1)
        session.execute(
            insert(contract_event).values(
                **contract_event_values(
                    someone.tenant_id,
                    contract_id=rows.contract_id,
                    contracting_entity_id=rows.entity_id,
                    stream_version=1,
                )
            )
        )
    return someone


def _named_files(session: Session) -> list[UUID]:
    """The files the tenant's copied rows name through their file columns (the registry's
    reference map, ``snapshot_export.reference_columns``)."""
    named: set[UUID] = set()
    for name, spec in sx.reference_columns()[sx.FILE_REFERENCE].items():
        table = metadata.tables[f"erev.{name}"]
        for column in spec.split("|"):
            named.update(
                session.scalars(select(table.c[column]).where(table.c[column].is_not(None)))
            )
    return sorted(named, key=str)


def _counts(tenant_id: UUID) -> dict[str, int]:
    """Row counts of every COPIED table. ``file_object`` is the population the copy carries: the
    files a copied row names (``snapshot_dataset.RULES["file_object"]``: "only referenced rows" —
    a report output no copied row names never leaves the source), without the job's own files."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        counts: dict[str, int] = {}
        for dataset in sd.inventory().datasets:
            if dataset.snapshot_class is not sd.SnapshotClass.COPIED:
                continue
            table = metadata.tables[f"erev.{dataset.name}"]
            statement = select(func.count()).select_from(table)
            if dataset.name == "file_object":
                statement = statement.where(
                    table.c.purpose.not_in(_JOB_FILE_PURPOSES),
                    table.c.id.in_(_named_files(session)),
                )
            counts[dataset.name] = int(session.execute(statement).scalar_one())
        return counts


def _snapshot_row(tenant_id: UUID, snapshot_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return dict(
            session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )


def _stored_snapshot(someone: Member, runtime: JobRuntime, known_at: datetime) -> UUID:
    """A SUCCEEDED STORED_BACKUP export of the world, through the dispatched job path."""
    with tenant_session(_context(someone.tenant_id)) as session:
        row = tenant_snapshot_values(someone.tenant_id, known_at=known_at, purpose="STORED_BACKUP")
        session.execute(insert(tenant_snapshot).values(**row))
    params = {
        "tenant_snapshot_id": str(row["id"]),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    return UUID(str(row["id"]))


def _copy_params(
    someone: Member, snapshot_id: UUID, sandbox_id: UUID, name: str, known_at: datetime
) -> dict[str, Any]:
    return {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "SANDBOX_COPY",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name=name, requested_by=someone.user_id, restore=False
        ),
    }


def _load_report(sandbox_id: UUID, runtime: JobRuntime, keyring: KeyRing) -> dict[str, Any]:
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        detail = session.execute(
            select(audit_event.c.detail)
            .where(audit_event.c.action == sb.ACTION_LOADED)
            .order_by(audit_event.c.chain_seq)
        ).scalar_one()
        _, stream = open_file(
            session, UUID(str(detail["load_report_file_id"])), files=runtime.files, keyring=keyring
        )  # type: ignore[arg-type]
        return dict(json.loads(stream.read()))


def _revenue(tenant_id: UUID, group_id: UUID) -> Decimal:
    """Cumulative revenue of the group's latest ASC606 contract version in one tenant."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return Decimal(
            session.execute(
                select(contract_version.c.revenue_cum)
                .where(
                    contract_version.c.combination_group_id == group_id,
                    contract_version.c.book_code == "ASC606",
                )
                .order_by(contract_version.c.version_no.desc())
                .limit(1)
            ).scalar_one()
        )


def _estimate_events(tenant_id: UUID) -> dict[UUID, UUID]:
    """Each stream event that names an estimate version, with the version it names."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(event)): UUID(str(version))
            for event, version in session.execute(
                select(contract_event.c.id, contract_event.c.estimate_version_id).where(
                    contract_event.c.estimate_version_id.is_not(None)
                )
            )
        }


def _period_states(tenant_id: UUID) -> dict[UUID, str]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(state)): str(name)
            for state, name in session.execute(select(period_state.c.id, period_state.c.state))
        }


def test_sandbox_copy_k03(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """BUILD_SPEC SNP-2 ``test_sandbox_copy_k03`` (fragment 14 rev 1.5) on the world it names:
    ``worlds.k03_castellan`` — ``PRJ-CB-2026-01`` through the product's commands — taken through
    the J-06 change order and the J-10 September events to WLD-X-12: five ``ESTIMATE_CHANGED``
    events naming their estimate versions (05 SBX-04, the row-ordered component), one applied
    modification, and a group the source computed many times (05 SBX-05, the monetary state).
    Marcus (Controller) is the requester: a SANDBOX_COPY exports and loads in one job; the
    sandbox is of kind ``sandbox`` with the source lineage, its copied row counts equal the
    source's, the group is recomputed once and verifies (``derived_mismatches = 0``, not as a
    first computation), cumulative revenue is 797,294.12 as in production, every event names the
    estimate version it names in the source, the period states equal the source's (none closed
    here), and the source row names the sandbox as its target (DB-15, 04 1.56).

    Owed to SNP-2b (supervisor ruling R-10): the WLD-X-13 state of PRD J-25.2 — 829,852.94 after
    the J-14 correction in reopened September, Sep 2026 ``closed`` and Oct 2026 ``open``."""
    k03 = k03_castellan(app, keyring, clock, files)
    k03_change_order(k03, clock)  # J-06: WLD-X-10
    k03_september(k03, clock)  # J-10: WLD-X-11, WLD-X-12
    someone = k03.report.marcus.member
    with tenant_session(_context(someone.tenant_id)) as session:
        confirm_retention(session, someone.tenant_id, at=RETENTION_FROM)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        row = tenant_snapshot_values(someone.tenant_id, known_at=known_at, purpose="SANDBOX_COPY")
        session.execute(insert(tenant_snapshot).values(**row))
    sandbox_id = UUID(int=int(row["id"]) ^ 1)  # a distinct pre-allocated id
    before = _counts(someone.tenant_id)
    result = run_dispatched_snapshot(
        someone.tenant_id,
        _copy_params(someone, UUID(str(row["id"])), sandbox_id, "K03 Castellan", known_at),
        runtime=runtime,
        now=known_at,
    )
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    assert result["result"]["sandbox_tenant_id"] == str(sandbox_id)
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        created = session.execute(select(tenant).where(tenant.c.id == sandbox_id)).mappings().one()
    assert created["kind"] == "sandbox" and created["source_tenant_id"] == someone.tenant_id
    assert created["source_known_at"] == known_at and created["code"] == "sbx-k03-castellan"
    after_source = _counts(someone.tenant_id)
    assert after_source == before  # SBX-11: zero source rows changed
    sandbox_counts = _counts(sandbox_id)
    for name, count in before.items():
        if name in ("tenant_snapshot",):
            continue  # the source's own snapshot rows are not copied into the sandbox
        assert sandbox_counts[name] == count, name
    report = _load_report(sandbox_id, runtime, keyring)
    assert report["derived_mismatches"] == 0 and report["blocked_periods"] == []
    assert report["groups_recomputed"] == 1
    # one pair, verified by its monetary state: the source version is not a first computation
    assert (report["compared"], report["first_computations"]) == (1, 0)
    production = _revenue(someone.tenant_id, k03.group_id)
    assert production == Decimal("797294.12")  # WLD-X-12
    assert _revenue(sandbox_id, k03.group_id) == production  # "as in production" (PRD J-25.2)
    named = _estimate_events(someone.tenant_id)
    assert len(named) == 5 and _estimate_events(sandbox_id) == named
    states = _period_states(someone.tenant_id)
    assert set(states.values()) == {"open", "future"} and _period_states(sandbox_id) == states
    assert _snapshot_row(someone.tenant_id, UUID(str(row["id"])))["target_tenant_id"] == sandbox_id


def test_restore_into_new_sandbox(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """REQ-PLT-024: a stored SUCCEEDED snapshot restored into a NEW sandbox by a load-only
    TENANT_SNAPSHOT job (``params.load``; API-S-Job mode ``restore``); the export is not repeated,
    the sandbox is of kind ``sandbox`` and production row counts are unchanged."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    before = _counts(someone.tenant_id)
    manifest_before = _snapshot_row(someone.tenant_id, snapshot_id)["manifest_sha256"]
    sandbox_id = UUID(int=int(snapshot_id) ^ 2)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id,
            name="Restored Q3",
            requested_by=someone.user_id,
            restore=True,
        ),
    }
    assert sb.job_mode("TENANT_SNAPSHOT", params) == "restore"
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    assert result["result"]["counts"]["already_done"] == 1  # never re-exported
    row = _snapshot_row(someone.tenant_id, snapshot_id)
    assert row["manifest_sha256"] == manifest_before and row["target_tenant_id"] == sandbox_id
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        kind = session.execute(select(tenant.c.kind).where(tenant.c.id == sandbox_id)).scalar_one()
    assert kind == "sandbox"
    assert _counts(someone.tenant_id) == before


def test_snapshot_loaded_audit_event(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-06 rev 1.34 (STALE EXPECTATION; supervisor ruling R-7, 2026-09-30 — "the sandbox's
    first audit event" predates rev 1.20 and is withdrawn: ``derived_mismatches`` and
    ``blocked_periods`` exist only after the replay and the recompute, which audit through their
    governed paths as they run): ``tenant.snapshot_loaded`` is the load's SINGLE summary event in
    the sandbox; every earlier event of the sandbox's chain was written by this load's own period
    replay or recompute — an enumerated action under that step's request id of the load job,
    never anything else; and it carries the source tenant id, ``known_at``, the manifest SHA-256,
    the row counts, the source audit chain head at ``known_at``, the load report id and SHA-256,
    ``derived_mismatches`` and ``blocked_periods``; the source records
    ``tenant.sandbox_restored``."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    sandbox_id = UUID(int=int(snapshot_id) ^ 3)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name="Audited", requested_by=someone.user_id, restore=True
        ),
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    chain = load_chain(sandbox_id)  # (a) exactly one summary event, or it raises
    # (b) every earlier event is the load's own replay or recompute (enumerated, no wildcard)
    assert unexplained_load_events(chain, result["id"]) == []
    # ... and there ARE earlier events here, so the summary is provably not the first: this world's
    # one group is recomputed (and refused — it has no member) before the verification
    assert chain.before
    assert {load_step(event, result["id"]) for event in chain.before} == {"recompute"}
    assert {str(event["action"]) for event in chain.before} <= LOAD_RECOMPUTE_ACTIONS
    assert chain.after == ()  # no mismatch and no blocked period: no warning item beside it
    detail = dict(chain.summary["detail"])  # (c) the nine members
    assert set(detail) >= {
        "source_tenant_id",
        "known_at",
        "manifest_sha256",
        "row_counts",
        "source_audit_chain_head",
        "load_report_file_id",
        "load_report_sha256",
        "derived_mismatches",
        "blocked_periods",
    }
    assert detail["source_tenant_id"] == str(someone.tenant_id)
    assert (
        detail["manifest_sha256"]
        == _snapshot_row(someone.tenant_id, snapshot_id)["manifest_sha256"]
    )
    assert detail["audit_history_carried"] is False
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        report_row = (
            session.execute(
                select(file_object).where(file_object.c.id == UUID(detail["load_report_file_id"]))
            )
            .mappings()
            .one()
        )
    assert report_row["purpose"] == sb.LOAD_REPORT_PURPOSE  # AUDIT_DIGEST (E-68 rev 1.67)
    assert report_row["sha256"] == detail["load_report_sha256"]
    with tenant_session(_context(someone.tenant_id), read_only=True) as session:
        restored = session.execute(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action == sb.ACTION_RESTORED)
        ).scalar_one()
    assert restored == 1


def test_determinism_mismatch_warning(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SBX-05: a (group, book) pair whose recomputed output differs from the source raises ONE
    WARNING exception item ``SANDBOX_DETERMINISM_MISMATCH`` in the sandbox and notifies the
    requester. Boundary substitution, named: this minimal world computes nothing, so the case
    injects one mismatch at the CPU-tested ``snapshot_export.compare_determinism`` seam and
    proves the item, the report and the notification wiring. The genuine divergence — a sandbox
    output that really differs in one member, through the real comparison — is
    ``test_sandbox_replay.py::test_a_differing_sandbox_output_is_a_determinism_mismatch``."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    sandbox_id = UUID(int=int(snapshot_id) ^ 4)
    real = sx.compare_determinism

    def one_mismatch(source: Any, sandbox: Any, known_at: Any) -> sx.DeterminismReport:
        report = real(source, sandbox, known_at)
        group_id = next(iter(sandbox), (UUID(int=1), "ASC606"))[0]
        return sx.DeterminismReport(
            compared=report.compared + 1,
            mismatches=(*report.mismatches, sx.Mismatch(group_id, "ASC606", "a" * 64, "b" * 64)),
        )

    monkeypatch.setattr(sx, "compare_determinism", one_mismatch)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id,
            name="Mismatch",
            requested_by=someone.user_id,
            restore=True,
        ),
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    assert result["result"]["counts"]["derived_mismatches"] == 1
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        items = (
            session.execute(
                select(exception_item.c.code, exception_item.c.severity).where(
                    exception_item.c.code == sb.EXCEPTION_DETERMINISM
                )
            )
            .mappings()
            .all()
        )
    assert [(i["code"], i["severity"]) for i in items] == [(sb.EXCEPTION_DETERMINISM, "WARNING")]
    assert _load_report(sandbox_id, runtime, keyring)["derived_mismatches"] == 1
    with tenant_session(_context(someone.tenant_id), read_only=True) as session:
        notified = session.execute(
            select(func.count())
            .select_from(notification)
            .where(notification.c.recipient_membership_id == someone.membership_id)
        ).scalar_one()
    assert notified >= 1  # the requester is notified (05 SBX-05)


def test_memberships_copied_not_sessions(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-03: memberships and role assignments exist in the sandbox; sessions, API clients and
    support grants do not (never copied)."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    sandbox_id = UUID(int=int(snapshot_id) ^ 5)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name="Members", requested_by=someone.user_id, restore=True
        ),
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    with tenant_session(_context(sandbox_id), read_only=True) as session:

        def count(table: Any) -> int:
            return int(session.execute(select(func.count()).select_from(table)).scalar_one())

        assert count(tenant_membership) >= 1 and count(role_assignment) >= 1
        member_users = set(session.execute(select(tenant_membership.c.user_id)).scalars())
        assert (
            someone.user_id in member_users
        )  # the requester's membership makes the target visible
        # ``user_session`` is a global table (04 RLS-NONE-U: no ``tenant_id``, no policy), so a
        # bare count sees every tenant's sessions of the shared test database (DG-TST-13: tests
        # isolate by fresh tenant); "no session in the sandbox" is a session whose active tenant
        # is the sandbox. ``api_client`` and ``support_grant`` are tenant tables.
        sandbox_sessions = session.execute(
            select(func.count())
            .select_from(user_session)
            .where(user_session.c.active_tenant_id == sandbox_id)
        ).scalar_one()
        assert sandbox_sessions == 0 and count(api_client) == 0 and count(support_grant) == 0


def _restored(
    someone: Member, runtime: JobRuntime, known_at: datetime, name: str
) -> dict[str, Any]:
    """A stored snapshot of the world restored into a new sandbox; returns the load job's row with
    the pre-allocated sandbox id under ``sandbox_id``."""
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    sandbox_id = UUID(int=int(snapshot_id) ^ 6)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name=name, requested_by=someone.user_id, restore=True
        ),
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    return {**result, "sandbox_id": sandbox_id}


def _rows_without_tenant(tenant_id: UUID, table: Any) -> dict[UUID, dict[str, Any]]:
    """Every row of ``table`` by id, every column but the remapped tenant."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(row["id"])): {k: v for k, v in dict(row).items() if k != "tenant_id"}
            for row in session.execute(select(table)).mappings()
        }


def test_copy_phase_records_the_platform_scope_once_per_transaction(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-04 rev 1.30 / 04 §14.3 rev 1.85 at the real loader: the provision step and every
    transaction of the COPY PHASE — one per copied dataset with rows, one per approval graph — run
    under the provisioning platform scope, and each records ONE ``PLATFORM_SCOPE_USED`` event
    naming the sandbox tenant and the requester (compensating control 3). Nothing else of the load
    carries the scope: no event belongs to the period replay, the recompute, the verification,
    the load report or the audit steps."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    result = _restored(someone, runtime, known_at, "Scope events")
    sandbox_id, prefix = result["sandbox_id"], f"job-{result['id']}-"
    with identity_session(request_id="tests-copy-phase-scope") as session:
        events = [
            dict(row)
            for row in session.execute(
                select(
                    security_event.c.kind,
                    security_event.c.request_id,
                    security_event.c.user_id,
                    security_event.c.detail,
                ).where(security_event.c.tenant_id == sandbox_id)
            ).mappings()
        ]
    assert events and all(event["kind"] == "PLATFORM_SCOPE_USED" for event in events)
    assert all(event["user_id"] == someone.user_id for event in events)  # the requester
    assert all(event["detail"] == {"scope": "provisioning"} for event in events)
    request_ids = [str(event["request_id"]) for event in events]
    assert all(request_id.startswith(prefix) for request_id in request_ids)
    steps = [request_id.removeprefix(prefix) for request_id in request_ids]
    assert len(steps) == len(set(steps))  # one event per transaction, never two
    # the expected transactions, from what the load copied
    report = _load_report(sandbox_id, runtime, keyring)
    graph = sd.GRAPHS["approval_request"]
    in_graph = {graph.root, *(name for name, _ in graph.dependants)}
    component_of = {
        table: component for component in sd.COMPONENTS.values() for table in component.tables
    }
    loaded = {
        # a component's tables take ONE transaction, named for the component (05 rev 1.50)
        f"load-{component_of[name].name if name in component_of else name}"
        for name, count in report["row_counts"].items()
        if count and name in sb.COPY_PHASE_TABLES and name not in in_graph
    }
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        graphs = {
            f"graph-{request_id}" for request_id in session.scalars(select(approval_request.c.id))
        }
    assert len(graphs) == report["row_counts"]["approval_request"] >= 2  # bootstrap + retention
    assert {"load-sod_rule", "load-role_assignment", "load-registry_version"} <= loaded
    assert "load-stream" in loaded and "load-contract_event" not in loaded
    assert set(steps) == {"provision"} | loaded | graphs
    # named once more, by what must NOT be there: no later step of the load carries the scope
    later = ("periods", "replay", "groups", "recompute", "verify", "report")
    assert not [step for step in steps if step.startswith(later)]


def test_frozen_references_and_ledger_chain_heads_of_a_loaded_sandbox(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The references the database freezes at insert arrive with their rows (FIX-D1: a fixup
    UPDATE of them is refused — 42501 on ``role_assignment.approval_request_id``, DB-04 on a
    PUBLISHED version's ``supersedes_version_id``): every ``role_assignment`` and every
    ``registry_version`` of the sandbox equals its source row on every column but the remapped
    tenant, the AUTO-BOOTSTRAP grant naming its approval request and the retention version the
    DEFAULT version it supersedes. And the sandbox starts its own ledger chain: one
    ``ledger_chain_head`` per book at sequence 0 (04 §14.3), which no copied dataset brings."""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id = _restored(someone, runtime, known_at, "Frozen references")["sandbox_id"]
    for table in (role_assignment, registry_version):
        source, copied = (
            _rows_without_tenant(someone.tenant_id, table),
            _rows_without_tenant(sandbox_id, table),
        )
        assert copied == source, table.name
    grants = _rows_without_tenant(sandbox_id, role_assignment).values()
    requests = set(_rows_without_tenant(sandbox_id, approval_request))
    assert [g for g in grants if g["approval_request_id"] is not None]  # the bootstrap grant
    assert {g["approval_request_id"] for g in grants} - {None} <= requests
    versions = _rows_without_tenant(sandbox_id, registry_version)
    superseding = [v for v in versions.values() if v["supersedes_version_id"] is not None]
    assert len(superseding) == 1  # the retention confirmation supersedes the seeded DEFAULT
    assert superseding[0]["status"] == "PUBLISHED"
    assert versions[superseding[0]["supersedes_version_id"]]["status"] == "SUPERSEDED"
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        heads = {
            str(row["book_code"]): (row["last_chain_seq"], row["last_seal_sha256"])
            for row in session.execute(select(ledger_chain_head)).mappings()
        }
    assert heads == {"ASC606": (0, None), "IFRS15": (0, None), "LEGACY": (0, None)}


def _o1_revenue(app: FastAPI, actor: Actor, contract_id: str) -> dict[str, str]:
    """Revenue of obligation O1 by period key, September and October 2026, in the contract's
    latest version (``GET /schedule-lines``, as the workspace of ``actor``'s session reads it)."""
    listed = get(
        app,
        SCHEDULE_LINES,
        actor,
        {
            "contract": contract_id,
            "schedule_kind": "REVENUE",
            "obligation": "O1",
            "from_period": SEPTEMBER_2026,
            "to_period": OCTOBER_2026,
            "limit": "200",
        },
    )
    assert listed.status_code == 200, listed.text
    totals: dict[str, Decimal] = {}
    for item in listed.json()["items"]:
        key = item["period"]["period_key"]
        totals[key] = totals.get(key, Decimal(0)) + Decimal(item["amount"]["amount"])
    return {key: f"{value:.2f}" for key, value in sorted(totals.items())}


def _released_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[ReportWorld, dict[str, UUID]]:
    """WLD-K-01 (``worlds.k01_pellworth``: ``SF-ORD-10001`` booked, activated, billed and computed
    through September 2026) with a MANUAL ADJUSTMENT made through the product (BUILD_SPEC CLO-12;
    PRD J-13.2): Maya prepares a ``MANUAL_RELEASE`` of USD 2,400.00 on O1 effective 12 Sep 2026
    and submits it, Priya — Revenue Reviewer here — approves its one step. The approval appends
    ``MANUAL_ADJUSTMENT_APPLIED`` naming the adjustment, the adjustment is ``POSTED`` and names
    that event in turn (``applied_event_id``), and the group is recomputed with the release
    (ENGINE_SPEC_B S09-R-38).

    It replaces the directly inserted rows this witness stood on until CLO-12 landed (supervisor
    ruling R-43 (b))."""
    world = k01_pellworth(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # PRD §5.6: adjustment.approve
    booked = world.contracts[K01]
    (o1,) = [item for item in booked.obligations if item["obligation_key"] == "O1"]
    created = post(
        app,
        ADJUSTMENTS,
        world.maya,
        {
            "kind": "MANUAL_RELEASE",
            "contract_id": str(booked.contract["id"]),
            "effective_date": "2026-09-12",
            "reason_code": "ESTIMATE_CORRECTION",
            "memo": "Customer accepted phase 2 on 12 Sep 2026",
            "payload": {
                "obligation_id": str(o1["id"]),
                "amount": {"amount": "2400.00", "currency": "USD"},
            },
        },
    )
    assert created.status_code == 201, created.text
    adjustment_id = created.json()["id"]
    submitted = post(app, f"{ADJUSTMENTS}/{adjustment_id}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    decided = approve(app, request_id, world.priya)
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED", decided.text
    posted = get(app, f"{ADJUSTMENTS}/{adjustment_id}", world.maya)
    assert posted.status_code == 200 and posted.json()["status"] == "POSTED", posted.text
    return world, {
        "adjustment": UUID(adjustment_id),
        "applied": UUID(posted.json()["applied_event_id"]),
        "obligation": UUID(str(o1["id"])),
        "request": UUID(request_id),
    }


def test_an_event_naming_a_manual_adjustment_loads_with_it(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-04 rev 1.50 (supervisor ruling R-43 (b)) — the second frozen edge of the ``stream``
    component, ``contract_event.manual_adjustment_id``. The adjustment and the event that applied
    it name EACH OTHER, so one of the two references must wait: the event's is frozen (IM-A), the
    adjustment's ``applied_event_id`` is an updatable column of its DB-03 kernel. The component
    therefore inserts the obligation after its creating event, the adjustment after its
    obligation with ``applied_event_id`` NULL, then the event naming the adjustment; the fixup
    step restores ``applied_event_id``.

    On the product path (``_released_world``; the witness stood on directly inserted rows until
    CLO-12 landed). In the sandbox: every event equals its source row but for the DB-08 stamps
    and the stream keeps its order, the applied event naming the adjustment; the obligations
    equal their source rows; the adjustment equals its source row on every column — POSTED, its
    obligation, its approval request and its applied event. And the copy VERIFIES: the group is
    recomputed once with no mismatch, so the release is in the sandbox's figures as in
    production — O1 September 12,164.38 and October 7,689.86 (9,764.38 and 10,089.86 without
    it), read through the API: by Maya in production before the cutoff, by Marcus in the copy."""
    world, ids = _released_world(app, keyring, clock, files)
    booked = world.contracts[K01]
    contract_id = str(booked.contract["id"])
    group_id = UUID(str(booked.combination_group["id"]))
    released = {SEPTEMBER_2026: "12164.38", OCTOBER_2026: "7689.86"}
    assert _o1_revenue(app, world.maya, contract_id) == released
    someone = world.marcus.member
    with tenant_session(_context(someone.tenant_id)) as session:
        confirm_retention(session, someone.tenant_id, at=RETENTION_FROM)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        row = tenant_snapshot_values(someone.tenant_id, known_at=known_at, purpose="SANDBOX_COPY")
        session.execute(insert(tenant_snapshot).values(**row))
    sandbox_id = UUID(int=int(row["id"]) ^ 11)
    result = run_dispatched_snapshot(
        someone.tenant_id,
        _copy_params(someone, UUID(str(row["id"])), sandbox_id, "K01 released", known_at),
        runtime=runtime,
        now=known_at,
    )
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["derived_mismatches"] == 0, load_outcome(counts)

    source_events = _rows_without_tenant(someone.tenant_id, contract_event)
    events = _rows_without_tenant(sandbox_id, contract_event)
    assert set(events) == set(source_events) and ids["applied"] in events
    stamps = {"recorded_at", "record_seq"}  # DB-08: the sandbox's own
    for key, event in events.items():
        assert {c: v for c, v in event.items() if c not in stamps} == {
            c: v for c, v in source_events[key].items() if c not in stamps
        }, key
    assert events[ids["applied"]]["manual_adjustment_id"] == ids["adjustment"]
    assert events[ids["applied"]]["approval_request_id"] == ids["request"]

    def in_order(rows: dict[UUID, dict[str, Any]]) -> list[UUID]:
        return sorted(rows, key=lambda key: rows[key]["record_seq"])

    assert in_order(events) == in_order(source_events)
    assert _rows_without_tenant(sandbox_id, obligation) == _rows_without_tenant(
        someone.tenant_id, obligation
    )
    adjustments = _rows_without_tenant(sandbox_id, manual_adjustment)
    assert adjustments == _rows_without_tenant(someone.tenant_id, manual_adjustment)
    restored = adjustments[ids["adjustment"]]
    assert restored["status"] == "POSTED" and restored["obligation_id"] == ids["obligation"]
    assert restored["approval_request_id"] == ids["request"]
    assert restored["applied_event_id"] == ids["applied"]  # the deferred edge, by the fixup step

    report = _load_report(sandbox_id, runtime, keyring)
    assert report["derived_mismatches"] == 0 and report["groups_recomputed"] == 1
    assert _revenue(sandbox_id, group_id) == _revenue(someone.tenant_id, group_id)
    # Marcus signs in again (the cutoff moved the clock past his session) and opens the copy.
    marcus = enter_workspace(app, clock, world.marcus, sandbox_id)
    assert _o1_revenue(app, marcus, contract_id) == released


def test_the_load_provisions_the_sandbox_key_through_the_runtime_authority(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 KEY-05 / DG-KRN-KEY-06 rev 1.108 (supervisor rulings R-43 (d) and R-60 (d)): the load
    creates a tenant, so it asks the job runtime's provisioning authority for the tenant's audit
    key — once, for the sandbox, inside the transaction that inserts the ``tenant`` row. An
    authority the provider denies, as it denies the accessor-only identity of a hosted worker
    (``tests/unit/test_sandbox_key_provisioning.py``), fails the load BY NAME — 412
    ``precondition-failed`` ``SANDBOX_KEY_PROVISIONING_DENIED`` in the job's problem — and NO
    tenant row is committed, so there is nothing to archive and nothing to open. An authority that
    fails for another reason fails the load without that name and commits no tenant either. With
    the authority answering, the load succeeds and the row carries the key id it returned.
    (Before rev 1.108 the load derived the key locally whatever the runtime said, so a hosted
    authority was never asked.)"""
    someone = _world(keyring, clock)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    asked: list[UUID] = []

    class Refusing:
        """What ``GcpTenantKeyProvisioner`` raises for an identity without the provisioning
        role (the unit test gets it from the hosted fake)."""

        def provision_audit_key(self, tenant_id: UUID) -> str:
            asked.append(tenant_id)
            raise TenantKeyProvisioningError(
                "denied", f"erev-audit-hmac-{tenant_id}", "create_secret"
            )

    class Broken:
        def provision_audit_key(self, tenant_id: UUID) -> str:
            asked.append(tenant_id)
            raise RuntimeError("planted: the authority failed for a reason of its own")

    class Recording:
        def provision_audit_key(self, tenant_id: UUID) -> str:
            asked.append(tenant_id)
            return DerivedTenantKeyProvisioner(keyring).provision_audit_key(tenant_id)

    def restore(sandbox_id: UUID, authority: Any, name: str) -> dict[str, Any]:
        params = {
            "tenant_snapshot_id": str(snapshot_id),
            "known_at": known_at.isoformat(),
            "purpose": "STORED_BACKUP",
            **sb.load_params_of(
                sandbox_tenant_id=sandbox_id, name=name, requested_by=someone.user_id, restore=True
            ),
        }
        hosted = dataclasses.replace(runtime, key_provisioner=authority)
        return run_dispatched_snapshot(someone.tenant_id, params, runtime=hosted, now=known_at)

    def tenant_row(sandbox_id: UUID) -> dict[str, Any] | None:
        with tenant_session(_context(sandbox_id), read_only=True) as session:
            found = session.execute(select(tenant).where(tenant.c.id == sandbox_id)).mappings()
            row = found.one_or_none()
        return None if row is None else dict(row)

    denied_id = UUID(int=int(snapshot_id) ^ 8)
    refused = restore(denied_id, Refusing(), "Denied key")
    assert refused["state"] == "FAILED"
    assert asked == [denied_id]
    problem = refused["problem"]
    assert (problem["type"].rsplit("/", 1)[-1], problem["status"]) == ("precondition-failed", 412)
    assert [(e["field"], e["rule_id"], e["message"]) for e in problem["errors"]] == [
        (None, "SANDBOX_KEY_PROVISIONING_DENIED", sb.KEY_DENIED)
    ]
    assert tenant_row(denied_id) is None  # the row and its key commit together, or not at all
    broken_id = UUID(int=int(snapshot_id) ^ 10)
    failed = restore(broken_id, Broken(), "Broken key")
    assert failed["state"] == "FAILED" and failed["problem"]["errors"] == []
    assert failed["problem"]["detail"] == "The job stopped with an unexpected error."
    assert tenant_row(broken_id) is None
    granted_id = UUID(int=int(snapshot_id) ^ 9)
    loaded = restore(granted_id, Recording(), "Granted key")
    assert loaded["state"] == "SUCCEEDED", loaded["problem"]
    assert asked == [denied_id, broken_id, granted_id]  # asked once per load
    created = tenant_row(granted_id)
    assert created is not None and created["status"] == "ACTIVE"
    assert created["audit_hmac_key_id"] == keyring.new_tenant_audit_key_id(granted_id)


def test_a_copy_carries_no_connection_and_no_webhook_endpoint_of_its_source(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-03 / SBX-08 (BUILD_SPEC SNP-4; supervisor ruling R-48 (f) on the adapter-secret
    namespace): ``integration_connection`` and ``webhook_endpoint`` are EXCLUDED_SECRET tables, so
    an ACTIVE connection, the reference of its secret and an active endpoint stay in the source.
    The sandbox starts with no connection, no endpoint, no delivery and no outbox message, and
    the source's reference — a name of the SOURCE's namespace of the secret store — is outside
    the sandbox's: a key ring that serves the secret to the source refuses it for the sandbox
    before the store is asked.

    Oracle: the source's rows are written before ``known_at`` is taken, so the cutoff keeps them
    and their absence is the class; each count is read under the tenant's own scope."""
    someone = _world(keyring, clock)
    reference = tenant_ref(someone.tenant_id, "crm-webhook-secret")
    with tenant_session(_context(someone.tenant_id)) as session:
        session.execute(
            insert(integration_connection).values(
                **integration_connection_values(
                    someone.tenant_id, status="ACTIVE", secret_ref=reference
                )
            )
        )
        insert_sealed_webhook_endpoint(session, someone.tenant_id, keyring=keyring)
    known_at = cutoff_after(someone.tenant_id, clock)
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id = _restored(someone, runtime, known_at, "No traffic")["sandbox_id"]

    def counts(tenant_id: UUID) -> list[int]:
        tables = (integration_connection, webhook_endpoint, webhook_delivery, outbox_message)
        with tenant_session(_context(tenant_id), read_only=True) as session:
            return [
                int(session.execute(select(func.count()).select_from(table)).scalar_one())
                for table in tables
            ]

    classes = sd.inventory().classes
    assert classes["integration_connection"] is sd.SnapshotClass.EXCLUDED_SECRET
    assert classes["webhook_endpoint"] is sd.SnapshotClass.EXCLUDED_SECRET
    assert counts(someone.tenant_id)[:2] == [1, 1]  # the source keeps both
    assert counts(sandbox_id) == [0, 0, 0, 0]

    assert in_adapter_namespace(reference, someone.tenant_id)
    assert not in_adapter_namespace(reference, sandbox_id)
    serving = keyring_with(app_settings, {reference: "fixture-shared-secret"})
    assert serving.adapter_secret(reference, tenant_id=someone.tenant_id) == "fixture-shared-secret"
    with pytest.raises(KeyError):
        serving.adapter_secret(reference, tenant_id=sandbox_id)


def _reader(tenant_id: UUID, scope: frozenset[UUID] | str, clock: FrozenClock) -> Principal:
    """A member of ``tenant_id`` who holds ``contract.read`` for ``scope`` and uploaded nothing."""
    return Principal(
        kind=PrincipalKind.USER,
        id=new_id(),
        tenant_id=tenant_id,
        membership_id=None,
        display_name="Import reader",
        roles=("revenue_accountant",),
        permissions=frozenset({import_scope.READ_PERMISSION}),
        permission_scopes={import_scope.READ_PERMISSION: scope},
        entity_scope=scope,
        auth_method="password",
        mfa_verified_at=clock.now(),
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def test_a_named_set_that_loses_an_entity_to_the_cut_is_unresolved_in_the_copy(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    files: LocalFileStore,
) -> None:
    """Supervisor ruling R-98 (04 T-IMP-02 ``named_entity_ids``): an upload is read only by a
    holder of ``contract.read`` for EVERY entity its rows name. Here the upload is made before
    ``known_at``; a second legal entity is created after it, and the validation that follows names
    both — the set is written once, whenever validation ends. A copy as of ``known_at`` does not
    carry the second entity. Its upload is then NOT copied as naming the first entity alone
    (which a reader of that one entity would gain, with the upload's rows and file): the set is
    NULL, not resolved, read under an all-entities scope only; the cut entity is counted in the
    manifest and the copy is not refused.

    Oracle: ``imports.scope.visible``, the predicate the import routes read with, evaluated for a
    reader of the first entity and for an all-entities reader in both workspaces. Positive
    controls: in the source the reader of both entities reads the upload; in the copy the
    all-entities reader does."""
    someone = _world(keyring, clock)
    tenant_id = someone.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        first, calendar_id = session.execute(
            select(legal_entity.c.id, legal_entity.c.calendar_id)
        ).one()
        stored = file_object_values(tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
        session.execute(insert(file_object).values(**stored))
        upload_id = insert_import_upload(session, tenant_id=tenant_id, file_object_id=stored["id"])
    known_at = cutoff_after(tenant_id, clock)
    with tenant_session(_context(tenant_id)) as session:  # after the cutoff
        later = legal_entity_values(tenant_id, calendar_id=calendar_id)
        session.execute(insert(legal_entity).values(**later))
        second = UUID(str(later["id"]))
        tx.apply(
            session,
            "import_upload",
            upload_id,
            to_status=None,
            set_values={"named_entity_ids": [first, second]},
        )
    runtime = _runtime(app_settings, keyring, clock)
    snapshot_id = _stored_snapshot(someone, runtime, known_at)
    sandbox_id = UUID(int=int(snapshot_id) ^ 12)
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "STORED_BACKUP",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id,
            name="Named set",
            requested_by=someone.user_id,
            restore=True,
        ),
    }
    result = run_dispatched_snapshot(tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]

    def named(workspace: UUID) -> list[UUID] | None:
        with tenant_session(_context(workspace), read_only=True) as session:
            return session.execute(
                select(import_upload.c.named_entity_ids).where(import_upload.c.id == upload_id)
            ).scalar_one()

    def readable(workspace: UUID, scope: frozenset[UUID] | str) -> list[UUID]:
        reader = _reader(workspace, scope, clock)
        with tenant_session(_context(workspace), read_only=True) as session:
            return list(
                session.scalars(select(import_upload.c.id).where(import_scope.visible(reader)))
            )

    with tenant_session(_context(sandbox_id), read_only=True) as session:
        entities = set(session.scalars(select(legal_entity.c.id)))
    assert entities == {first}  # the copy does not hold the later entity
    assert named(tenant_id) == [first, second]
    assert named(sandbox_id) is None  # never [first]
    one_entity = frozenset({first})
    assert readable(tenant_id, one_entity) == []
    assert readable(sandbox_id, one_entity) == []  # the copy widens nobody's reading
    assert readable(tenant_id, frozenset({first, second})) == [upload_id]
    assert readable(sandbox_id, "*") == [upload_id]
    manifest_file_id = _snapshot_row(tenant_id, snapshot_id)["manifest_file_id"]
    with tenant_session(_context(tenant_id), read_only=True) as session:
        _, stream = open_file(session, UUID(str(manifest_file_id)), files=files, keyring=keyring)
    with stream:
        manifest = json.loads(stream.read())
    assert manifest["array_drops"] == {"import_upload.named_entity_ids": 1}


# --- item SBX-COPY-OPEN-INVITATION-1 (05 SBX-03 and SBX-04 rev 1.205; 04 T-PLT-07 rev 1.293; PRD
# SM-13 rev 1.201; the supervisor's rulings of 2026-10-02): a copy and an open invitation ---

USERS = "/api/v1/users"
LOOKUP = "/api/v1/session/invitations/lookup"
ACCEPT = "/api/v1/session/accept-invitation"
INVITATION_LINK = "/accept-invitation#token="


@dataclasses.dataclass(frozen=True, slots=True)
class Invitations:
    """A production workspace with two invitations at the snapshot's cut: Ines's, an hour old and
    open; Otto's, eight days old — past its seven days and never removed, so INVITED still. Each
    holds the Viewer role the setup rule approved."""

    someone: Member
    admin: Actor  # the Tenant Admin, as signed in before the cut
    known_at: datetime
    viewer: UUID
    ines: UUID
    ines_email: str
    ines_token: str
    otto: UUID


def _viewer_invitation(email: str, name: str, viewer: UUID) -> dict[str, Any]:
    return {
        "email": email,
        "display_name": name,
        "roles": [{"role_id": str(viewer), "is_all_entities": True, "entity_codes": []}],
    }


def _invitations(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Invitations:
    someone = _world(keyring, clock)
    assign(someone, "tenant_admin")
    # What the product writes is stamped by the application clock. It follows the database's
    # from here on (``cutoff_after``), so that an invitation's age at the cut is its age by the
    # clock that stamped it: eight days for Otto's, an hour for Ines's.
    now = cutoff_after(someone.tenant_id, clock)
    with tenant_session(_context(someone.tenant_id), read_only=True) as session:
        viewer = session.execute(select(role.c.id).where(role.c.code == "viewer")).scalar_one()

    def invited(admin: Actor, name: str) -> tuple[UUID, str]:
        email = f"{name.lower()}-{new_id().hex[-8:]}@members.test"
        answer = post(app, USERS, admin, _viewer_invitation(email, name, viewer))
        assert answer.status_code == 201, answer.text
        assert [item["status"] for item in answer.json()["roles"]] == ["ACTIVE"]  # the setup rule
        return UUID(answer.json()["id"]), email

    clock.set(now - timedelta(days=8))
    admin = enrolled(app, clock, someone)
    otto, _ = invited(admin, "Otto")
    clock.set(now - timedelta(hours=1))
    admin = enter_workspace(app, clock, admin, someone.tenant_id)
    ines, ines_email = invited(admin, "Ines")
    with tenant_session(_context(someone.tenant_id), read_only=True) as session:
        payload = session.execute(
            select(outbox_message.c.payload).where(outbox_message.c.aggregate_id == ines)
        ).scalar_one()
    return Invitations(
        someone=someone,
        admin=admin,
        known_at=cutoff_after(someone.tenant_id, clock),
        viewer=UUID(str(viewer)),
        ines=ines,
        ines_email=ines_email,
        ines_token=emailed_token(payload, keyring, prefix=INVITATION_LINK),
        otto=otto,
    )


def _copied(world: Invitations, runtime: JobRuntime, name: str) -> UUID:
    """A SANDBOX_COPY of the world as of its cut — export and load in one job; the sandbox."""
    someone = world.someone
    with tenant_session(_context(someone.tenant_id)) as session:
        row = tenant_snapshot_values(
            someone.tenant_id, known_at=world.known_at, purpose="SANDBOX_COPY"
        )
        session.execute(insert(tenant_snapshot).values(**row))
    snapshot_id = UUID(str(row["id"]))
    sandbox_id = UUID(int=int(snapshot_id) ^ 7)
    result = run_dispatched_snapshot(
        someone.tenant_id,
        _copy_params(someone, snapshot_id, sandbox_id, name, world.known_at),
        runtime=runtime,
        now=world.known_at,
    )
    assert result["state"] == "SUCCEEDED", result["problem"]
    return sandbox_id


def _invitation_rows(tenant_id: UUID, *membership_ids: UUID) -> list[tuple[Any, ...]]:
    """Per membership, in the order given: its status, whether it holds a token and an expiry,
    ``removed_at``, ``activated_at``, and how each of its role assignments was revoked."""
    found: list[tuple[Any, ...]] = []
    with tenant_session(_context(tenant_id), read_only=True) as session:
        for membership_id in membership_ids:
            row = session.execute(
                select(
                    tenant_membership.c.status,
                    tenant_membership.c.invitation_token_sha256,
                    tenant_membership.c.invitation_expires_at,
                    tenant_membership.c.removed_at,
                    tenant_membership.c.activated_at,
                ).where(
                    tenant_membership.c.tenant_id == tenant_id,
                    tenant_membership.c.id == membership_id,
                )
            ).one()
            grants = session.execute(
                select(
                    role_assignment.c.revoked_at,
                    role_assignment.c.revoked_by,
                    role_assignment.c.revoked_by_kind,
                )
                .where(
                    role_assignment.c.tenant_id == tenant_id,
                    role_assignment.c.membership_id == membership_id,
                )
                .order_by(role_assignment.c.valid_from, role_assignment.c.id)
            ).all()
            found.append(
                (
                    str(row.status),
                    row.invitation_token_sha256 is not None,
                    row.invitation_expires_at is not None,
                    row.removed_at,
                    row.activated_at,
                    [tuple(grant) for grant in grants],
                )
            )
    return found


def test_a_copy_and_a_restore_carry_an_open_invitation_as_one_withdrawn(
    committed_db: TestDatabase,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-03 rev 1.205: an INVITED membership cannot be carried as it is — its token is
    nulled on export, and the table's two checks tie the status, the token and the expiry — so a
    copy carries it as the product leaves an invitation withdrawn before acceptance: REMOVED,
    token and expiry null, ``removed_at`` the snapshot's ``known_at``, its role assignment
    revoked at ``known_at`` by SYSTEM. An invitation past its seven days that nobody removed is
    INVITED too. The rule is the export's, so the restore of a stored backup carries the same.
    Production is as it was, its open invitation still answers its token, and the administrator
    of the copy reads both people as removed.

    Fail-first (the lane's tip before this item): the copy FAILED, "The job stopped with an
    unexpected error." — the load refused the row, INVITED with a null token
    (``ck_tenant_membership__invitation_expiry``) — and left an ARCHIVED sandbox."""
    world = _invitations(app, keyring, clock)
    someone, known_at = world.someone, world.known_at
    runtime = _runtime(app_settings, keyring, clock)
    before = _invitation_rows(someone.tenant_id, world.ines, world.otto)
    assert [row[:3] for row in before] == [("INVITED", True, True)] * 2
    assert [row[5] for row in before] == [[(None, None, None)]] * 2

    copy_id = _copied(world, runtime, "Invitations copied")
    restored_id = _restored(someone, runtime, known_at, "Invitations restored")["sandbox_id"]
    carried = ("REMOVED", False, False, known_at, None, [(known_at, None, "SYSTEM")])
    assert _invitation_rows(copy_id, world.ines, world.otto) == [carried, carried]
    assert _invitation_rows(restored_id, world.ines, world.otto) == [carried, carried]

    assert _invitation_rows(someone.tenant_id, world.ines, world.otto) == before
    looked_up = call(app, "POST", LOOKUP, json={"token": world.ines_token})
    assert looked_up.status_code == 200, looked_up.text

    admin = enter_workspace(app, clock, world.admin, copy_id)
    listed = get(app, USERS, admin, {"limit": 200})
    assert listed.status_code == 200, listed.text
    shown = {item["id"]: item for item in listed.json()["items"]}
    for membership_id in (world.ines, world.otto):
        person = shown[str(membership_id)]
        # The grid lists the roles in force: none, for a person the copy carries as removed.
        assert (person["status"], person["invitation_expires_at"], person["roles"]) == (
            "REMOVED",
            None,
            [],
        )
        detail = get(app, f"{USERS}/{membership_id}", admin)
        assert detail.status_code == 200, detail.text
        assert [
            (item["role"]["code"], item["status"], item["revoked_by"]["kind"])
            for item in detail.json()["roles"]
        ] == [("viewer", "REVOKED", "SYSTEM")]


def test_a_person_whose_invitation_a_copy_carries_is_invited_again_in_the_copy(
    committed_db: TestDatabase,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """PRD SM-13 rev 1.201 with 05 SBX-03 rev 1.205: the membership a copy carries as REMOVED is
    invited again there like any removed member's — by an administrator of the copy, on that
    membership, with the copy's own link — and the person accepts in the copy. Nothing of it
    reaches production, whose invitation is open still under its own token.

    Fail-first (the copy's rule without the invitation's): ``POST /users`` in the copy answered
    422 "This person is already a member of this workspace." — the person could never work in
    the copy."""
    world = _invitations(app, keyring, clock)
    someone = world.someone
    copy_id = _copied(world, _runtime(app_settings, keyring, clock), "Invited again")
    admin = enter_workspace(app, clock, world.admin, copy_id)

    again = post(app, USERS, admin, _viewer_invitation(world.ines_email, "Ines", world.viewer))
    assert again.status_code == 201, again.text
    body = again.json()
    assert (body["id"], body["status"]) == (str(world.ines), "INVITED")
    # The role is requested as for any invitation. A loaded copy is past setup — the load stamps
    # ``setup_completed_at`` — so no rule approves it: it waits for an approver, as in production
    # after setup. The role the copy carried stays revoked.
    assert sorted(item["status"] for item in body["roles"]) == ["REQUESTED", "REVOKED"]
    with tenant_session(_context(copy_id), read_only=True) as session:
        payload = session.execute(
            select(outbox_message.c.payload).where(outbox_message.c.aggregate_id == world.ines)
        ).scalar_one()  # the outbox is not copied: the one message is the copy's
    token = emailed_token(payload, keyring, prefix=INVITATION_LINK)
    assert token != world.ines_token

    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    [in_copy] = _invitation_rows(copy_id, world.ines)
    assert in_copy[:5] == ("ACTIVE", False, False, None, clock.now())
    assert in_copy[5] == [(world.known_at, None, "SYSTEM")]

    [in_production] = _invitation_rows(someone.tenant_id, world.ines)
    assert in_production == ("INVITED", True, True, None, None, [(None, None, None)])
    looked_up = call(app, "POST", LOOKUP, json={"token": world.ines_token})
    assert looked_up.status_code == 200, looked_up.text
