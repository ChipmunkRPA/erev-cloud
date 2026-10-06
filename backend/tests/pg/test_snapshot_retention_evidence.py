"""SNP-1 retention evidence over a lane database (D-98 candidates 25 / 86; lane record §13.3).

WRITTEN, NOT RUN by lane F-SNP: the lane databases ``erev_rv_l23_*`` are Ray-side and these tests
run only under an admitted gate slot (producer CPU checks are not database proof). Two owed cases:

(a) ``record_auto_approval`` — a published ``AUTO_APPROVAL`` rule that matches ``REGISTRY_VERSION``
    submissions never approves a version carrying ``platform.snapshot_retention_families`` (the
    lifecycle withholds auto-approval, D-98 86); and a version that nevertheless carries only the
    SYSTEM ``AUTO_APPROVE`` decision such a rule writes is refused by the snapshot job
    (``RETENTION_UNCONFIRMED`` naming ``AUTO_APPROVE``), even when a user published it.
(b) the human retention choices — a named human ``APPROVE`` confirms (the manifest states approver
    and instant); a version without that evidence refuses before any count, read or write.

Added with the whole value set (04 T-PLT-32 rev 1.183; supervisor ruling R-117 (b)):

(c) a later PLATFORM version that states another value stands on the confirmed retention version,
    so its stored set carries the families; its request waits for a person, as every registry
    version's does (ruling R-26 (b)). The confirmation stays the approval of the version that
    stated the families: the carrying version's approver confirmed no retention period.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import ModuleType
from uuid import UUID

import pytest
from erev_api.approvals import engine, routing
from erev_api.approvals.subjects import spec_for
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    file_object,
    registry_version,
    tenant_snapshot,
)
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.policies import lifecycle, registry_versions
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    JobKind,
    RegistryCategory,
    RegistryScope,
    RuleSetKind,
    TenantKind,
)
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from sqlalchemy import func, select, update
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import member
from support.rows import publish_rule_set, tenant_snapshot_values
from support.snapshots import active_member, confirm_retention, run_dispatched_snapshot

pytestmark = pytest.mark.pg

KNOWN_AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
def job() -> Iterator[ModuleType]:
    """The handler, registered by hand while TENANT_SNAPSHOT is in PENDING_JOB_HANDLERS; the
    release stamped as the worker's startup stamps it."""
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


def _runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _snapshot_params(tenant_id: UUID) -> dict[str, object]:
    with tenant_session(_context(tenant_id)) as session:
        snapshot = tenant_snapshot_values(tenant_id, known_at=KNOWN_AT)
        session.execute(tenant_snapshot.insert().values(**snapshot))
    return {
        "tenant_snapshot_id": str(snapshot["id"]),
        "known_at": KNOWN_AT.isoformat(),
        "purpose": "STORED_BACKUP",
    }


def _row(tenant_id: UUID, params: dict[str, object]) -> dict[str, object]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return dict(
            session.execute(
                select(tenant_snapshot).where(
                    tenant_snapshot.c.id == UUID(str(params["tenant_snapshot_id"]))
                )
            )
            .mappings()
            .one()
        )


def _run_inline(
    tenant_id: UUID, params: dict[str, object], clock: FrozenClock, runtime: JobRuntime
) -> str:
    """The inline boundary (Codex PREP-S1): run_inline calls the handler directly and lets a
    refusal escape as a Problem — the callers assert that refusal with pytest.raises."""
    return registry.run_inline(
        JobKind.TENANT_SNAPSHOT,
        params,
        tenant_id=tenant_id,
        principal=system_principal(tenant_id),
        clock=clock,
        runtime=runtime,
    ).state


def _nothing_stored(tenant_id: UUID, job: ModuleType) -> None:
    """Observed narrowly: no SNAPSHOT_DATASET file, no tenant.snapshot_created event — the guard
    precedes dataset access, not every earlier SQL statement."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        files = session.execute(
            select(func.count())
            .select_from(file_object)
            .where(file_object.c.purpose == "SNAPSHOT_DATASET")
        ).scalar_one()
        created = session.execute(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action == job.ACTION_CREATED)
        ).scalar_one()
    assert (files, created) == (0, 0)


def _publish_auto_approval_rule(tenant_id: UUID, at: datetime) -> tuple[UUID, UUID]:
    """A PUBLISHED AUTO_APPROVAL rule set whose one rule approves every REGISTRY_VERSION
    submission; returns (rule_set_version_id, rule_id)."""
    with tenant_session(_context(tenant_id)) as session:
        version_id, rule_ids = publish_rule_set(
            session,
            tenant_id=tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            rules=[
                {
                    "rule_key": "AUTO-REG-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "REGISTRY_VERSION"}
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
            at=at,
        )
    return version_id, rule_ids["AUTO-REG-01"]


def _submit_retention_version(
    tenant_id: UUID,
    clock: FrozenClock,
    keyring: KeyRing,
    app_settings: Settings,
    *,
    values: dict[str, object] | None = None,
    effective_from: datetime | None = KNOWN_AT - timedelta(days=1),
) -> UUID:
    """Create, test and submit a TENANT PLATFORM registry version through the real policy
    commands (a SYSTEM principal prepares; approval evidence comes later): by default the one
    that states the retention families."""
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-snapshot-retention",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        version_id = registry_versions.create_policy(
            uow,
            category=RegistryCategory.PLATFORM,
            scope=RegistryScope.TENANT,
            entity_code=None,
            book_code=None,
            values=(
                {sd.RETENTION_PARAMETER: dict(sd.RETENTION_FAMILIES)} if values is None else values
            ),
            # The default: a future instant at submission and in force at the snapshot's
            # KNOWN_AT — the caller holds the clock two days before KNOWN_AT while submitting
            # (PRD ERR-75: a superseding version never takes effect in the past; Codex 0139).
            # Since 04 rev 1.183 a PLATFORM version may also name no date and take effect at its
            # publication (supervisor ruling R-115 (e)); case (c) submits one.
            effective_from=effective_from,
        )
        version = lifecycle.lock(uow.session, registry_versions.KIND, version_id)
        lifecycle.mark_tested(
            uow,
            registry_versions.KIND,
            version,
            content_sha256=lifecycle.current_sha256(
                uow.session, registry_versions.KIND, version_id
            ),
            detail={"cases": 0, "note": "tests-snapshot-retention"},
        )
        registry_versions.submit_policy(uow, version_id, comment=None)
        uow.commit()
    return version_id


def test_auto_approval_rule_is_withheld_and_an_auto_approved_version_refuses(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Owed case (a). (1) With a matching AUTO_APPROVAL rule in force, submitting a version that
    carries platform.snapshot_retention_families leaves its request PENDING with no decision —
    the lifecycle withheld auto-approval (D-98 86). (2) Writing the SYSTEM AUTO_APPROVE decision
    such a rule leaves (record_auto_approval), approving and publishing through the subject
    callback, and even stamping a user as publisher, still refuses the snapshot: the only decision
    is AUTO_APPROVE, which never confirms retention.

    Controlled time (Codex 0139; PRD ERR-75, supervisor ruling R-113 (b)): the tenant, the rule,
    the submission and the decision happen two days before KNOWN_AT, so that effective_from =
    KNOWN_AT - 1 day is a future instant at submission (§16.5; the fixture tenant has no legal
    entity, so no period start exists) and has not passed at the decision — the version
    supersedes the provisioned PLATFORM version, and a superseding version never takes effect in
    the past — and the version is in force at the snapshot's KNOWN_AT; the clock stands at
    KNOWN_AT for the snapshot."""
    clock.set(KNOWN_AT - timedelta(days=2))
    tenant_id = member(keyring, clock).tenant_id
    rule_set_version_id, rule_id = _publish_auto_approval_rule(
        tenant_id, KNOWN_AT - timedelta(days=3)
    )
    version_id = _submit_retention_version(tenant_id, clock, keyring, app_settings)
    with tenant_session(_context(tenant_id), read_only=True) as session:
        version = dict(
            session.execute(select(registry_version).where(registry_version.c.id == version_id))
            .mappings()
            .one()
        )
        request = dict(
            session.execute(
                select(approval_request).where(
                    approval_request.c.id == version["approval_request_id"]
                )
            )
            .mappings()
            .one()
        )
        decisions = session.execute(
            select(approval_decision).where(
                approval_decision.c.approval_request_id == request["id"]
            )
        ).all()
    assert request["status"] == ApprovalRequestStatus.PENDING.value  # (1) withheld
    assert decisions == []
    # (2) the pre-ruling auto path, reproduced exactly as record_auto_approval writes it
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-snapshot-retention-auto",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(
        ctx, clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root)
    ) as uow:
        engine.record_auto_approval(
            uow.session,
            tenant_id=tenant_id,
            approval_request_id=UUID(str(request["id"])),
            subject_content_sha256=str(request["subject_content_sha256"]),
            rule=routing.RuleRef(
                rule_set_version_id=rule_set_version_id,
                rule_id=rule_id,
                rule_set_code="AUTO-REG",
                rule_key="AUTO-REG-01",
            ),
            now=uow.now,
        )
        spec_for(ApprovalSubjectType.REGISTRY_VERSION).on_approved(
            uow, version_id, UUID(str(request["id"]))
        )
        uow.commit()
    with tenant_session(_context(tenant_id)) as session:
        decisions = (
            session.execute(
                select(approval_decision.c.decision).where(
                    approval_decision.c.approval_request_id == request["id"]
                )
            )
            .scalars()
            .all()
        )
        assert decisions == [ApprovalDecisionKind.AUTO_APPROVE.value]
        status = session.execute(
            select(registry_version.c.status).where(registry_version.c.id == version_id)
        ).scalar_one()
        assert status == "PUBLISHED"  # decided before its effective instant
        # a user publisher stamped after the fact does not turn an AUTO_APPROVE into evidence
        session.execute(
            update(registry_version)
            .where(registry_version.c.id == version_id)
            .values(published_by=active_member(session, tenant_id))
        )
    clock.set(KNOWN_AT)
    params = _snapshot_params(tenant_id)
    with pytest.raises(Problem) as info:
        _run_inline(tenant_id, params, clock, _runtime(app_settings, keyring, clock))
    assert info.value.slug == "precondition-failed"
    assert "RETENTION_UNCONFIRMED" in str(info.value) and "AUTO_APPROVE" in str(info.value)
    _nothing_stored(tenant_id, job)
    assert _row(tenant_id, params)["manifest_file_id"] is None


def test_human_retention_choices_confirm_or_refuse(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Owed case (b). A named human APPROVE confirms: the job SUCCEEDS and the manifest states
    "CONFIRMED: registry version <id> approved by <approver> at <instant>"; a version with no
    decision and no publisher refuses RETENTION_UNCONFIRMED before any count, read or write."""
    confirmed = member(keyring, clock).tenant_id
    with tenant_session(_context(confirmed)) as session:
        version_id = confirm_retention(session, confirmed, at=KNOWN_AT - timedelta(days=1))
        approver = active_member(session, confirmed)
    runtime = _runtime(app_settings, keyring, clock)
    params = _snapshot_params(confirmed)
    assert _run_inline(confirmed, params, clock, runtime) == "SUCCEEDED"
    row = _row(confirmed, params)
    assert row["status"] == "SUCCEEDED"
    with tenant_session(_context(confirmed), read_only=True) as session:
        _, stream = open_file(
            session, UUID(str(row["manifest_file_id"])), files=runtime.files, keyring=keyring
        )
        manifest_bytes = stream.read()
    assert hashlib.sha256(manifest_bytes).hexdigest() == row["manifest_sha256"]
    status = json.loads(manifest_bytes)["retention"]["families_status"]
    assert status.startswith(f"CONFIRMED: registry version {version_id} approved by {approver} at ")

    unconfirmed = member(keyring, clock).tenant_id
    with tenant_session(_context(unconfirmed)) as session:
        confirm_retention(session, unconfirmed, at=KNOWN_AT - timedelta(days=1), human=False)
    params = _snapshot_params(unconfirmed)
    with pytest.raises(Problem) as info:
        _run_inline(unconfirmed, params, clock, runtime)
    assert info.value.slug == "precondition-failed" and "RETENTION_UNCONFIRMED" in str(info.value)
    _nothing_stored(unconfirmed, job)
    assert _row(unconfirmed, params)["manifest_file_id"] is None


def test_unconfirmed_retention_ends_failed_through_the_dispatch_path(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The FAILED lifecycle, through the real dispatch path (Codex PREP-S1): insert_job →
    dispatch → the task fetched → run_job catches the refusal, ends the job FAILED with the
    problem and runs on_failure, which ends the T-PLT-34 row FAILED."""
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:
        confirm_retention(session, tenant_id, at=KNOWN_AT - timedelta(days=1), human=False)
    params = _snapshot_params(tenant_id)
    job_row = run_dispatched_snapshot(
        tenant_id, params, runtime=_runtime(app_settings, keyring, clock), now=clock.now()
    )
    assert job_row["state"] == "FAILED"
    assert "RETENTION_UNCONFIRMED" in str((job_row["problem"] or {}).get("detail"))
    row = _row(tenant_id, params)
    assert row["status"] == "FAILED" and row["manifest_file_id"] is None
    _nothing_stored(tenant_id, job)


def test_a_later_platform_version_carries_the_families_and_waits_for_a_human(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """Case (c). The retention is confirmed by a named human; a matching AUTO_APPROVAL rule is in
    force. A PLATFORM version that states only the negative-number style — and names no date
    (supervisor ruling R-115 (e)) — is stored at its submit as the whole set, the families with
    it (04 T-PLT-32 rev 1.183). Its request is PENDING without a decision: no tenant rule
    approves a registry version (R-26 (b)), although the version changes nothing of the families
    and the lifecycle's own check (D-98 86) therefore asks for no named approver
    (``test_registry_whole_set::test_a_version_that_changes_the_retention_families_is_withheld_from_auto_approval``).
    The confirmed version stays the one in force, and its approval stays the confirmation."""
    clock.set(KNOWN_AT - timedelta(days=2))
    tenant_id = member(keyring, clock).tenant_id
    _publish_auto_approval_rule(tenant_id, KNOWN_AT - timedelta(days=3))
    with tenant_session(_context(tenant_id)) as session:
        confirmed_id = confirm_retention(session, tenant_id, at=KNOWN_AT - timedelta(days=3))
    version_id = _submit_retention_version(
        tenant_id,
        clock,
        keyring,
        app_settings,
        values={"ui.negative_number_style": "MINUS"},
        effective_from=None,
    )
    with tenant_session(_context(tenant_id), read_only=True) as session:
        version = dict(
            session.execute(select(registry_version).where(registry_version.c.id == version_id))
            .mappings()
            .one()
        )
        request = dict(
            session.execute(
                select(approval_request).where(
                    approval_request.c.id == version["approval_request_id"]
                )
            )
            .mappings()
            .one()
        )
        decisions = session.execute(
            select(func.count())
            .select_from(approval_decision)
            .where(approval_decision.c.approval_request_id == request["id"])
        ).scalar_one()
        confirmed = session.execute(
            select(registry_version.c.status).where(registry_version.c.id == confirmed_id)
        ).scalar_one()
    assert (version["status"], version["supersedes_version_id"]) == ("SUBMITTED", confirmed_id)
    assert version["values"] == {
        "ui.negative_number_style": "MINUS",
        sd.RETENTION_PARAMETER: dict(sd.RETENTION_FAMILIES),
    }
    assert (request["status"], decisions, confirmed) == ("PENDING", 0, "PUBLISHED")
