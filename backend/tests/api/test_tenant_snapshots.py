"""API-R-04 snapshot routes (BUILD_SPEC SNP-1 ``test_permission_and_step_up``; 04 T-PLT-34; 05
SBX-02, SBX-06; PRD ACT-50; lane record §13.2.10).

WRITTEN IN SLICE I-4 AND NOT RUN: the lane databases ``erev_rv_l23_*`` are Ray-side. The tests
register the handler by hand for the worker run (``TENANT_SNAPSHOT`` stays in
``PENDING_JOB_HANDLERS`` until P2's ``HANDLER_MODULES`` line lands) and stamp the engine release as
the worker's startup does; an unstamped process refuses to export.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from datetime import timedelta
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job
from erev_api.domain.platform import snapshot_retention
from erev_api.enums import JobKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, text
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, enrolled, member, step_up
from support.rows import insert_role_assignment
from support.snapshots import confirm_retention, seeded_sandbox

SNAPSHOTS = "/api/v1/tenant/snapshots"
SANDBOXES = "/api/v1/tenant/sandboxes"
RESET = "/api/v1/tenant/reset"
JOBS = "/api/v1/jobs"
PROBLEM_BASE = "https://erev.dev/problems/"
SNAPSHOT_ROLE = "controller"  # the default role holding tenant.snapshot (auth.permissions)
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@pytest.fixture
def handler() -> Iterator[ModuleType]:
    """The handler, registered for the test and deregistered afterwards; the release stamped."""
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


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _grant(someone: Member, role_code: str) -> None:
    with tenant_session(_db(someone.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
        )


def _confirm_retention(tenant_id: UUID, clock: FrozenClock) -> None:
    """Slices I-5 / I-5.3 / I-5.5: the PUBLISHED TENANT version that confirms the retention
    families, with the named human approval built in the admitted order (Codex I53-S1)."""
    with tenant_session(_db(tenant_id)) as session:
        confirm_retention(session, tenant_id, at=clock.now() - timedelta(days=1))


def _post(app: FastAPI, actor: Actor, body: Mapping[str, Any]) -> HttpResponse:
    return call(
        app,
        "POST",
        SNAPSHOTS,
        json=dict(body),
        headers={
            **cookie_headers(actor.token, actor.csrf_token),
            "Idempotency-Key": str(uuid4()),
        },
    )


def _get(app: FastAPI, actor: Actor, path: str) -> HttpResponse:
    return call(app, "GET", path, headers=cookie_headers(actor.token, key=False))


def _slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def _work(tenant_id: UUID, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it (the jobs API test's pattern)."""
    with tenant_session(_db(tenant_id)) as session:
        row = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": row["procrastinate_job_id"]})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)


def test_permission_and_step_up(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, handler: ModuleType
) -> None:
    """Without ``tenant.snapshot`` 403 ``forbidden``; with it but without a fresh TOTP 403
    ``mfa-step-up-required``; with both, 202 with the job, Location and the snapshot id header."""
    lena = member(keyring, clock)
    omar = colleague(lena.tenant_id, "omar")  # no roles
    denied = _post(
        app,
        enrolled(app, clock, omar),
        {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"},
    )
    assert denied.status_code == 403 and _slug(denied) == "forbidden", denied.text
    ines = colleague(lena.tenant_id, "ines")
    _grant(ines, SNAPSHOT_ROLE)
    holder = enrolled(app, clock, ines)  # verified at enrolment
    clock.advance(timedelta(minutes=6))  # past the BR-PLT-06 step-up window
    stale = _post(app, holder, {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"})
    assert stale.status_code == 403 and _slug(stale) == "mfa-step-up-required", stale.text
    fresh = step_up(app, clock, holder)
    accepted = _post(app, fresh, {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"})
    assert accepted.status_code == 202, accepted.text
    shown = accepted.json()
    assert (shown["kind"], shown["state"]) == ("TENANT_SNAPSHOT", "QUEUED")
    assert accepted.headers["Location"] == f"/api/v1/jobs/{shown['id']}"
    assert UUID(accepted.headers["X-Erev-Tenant-Snapshot-Id"]) == UUID(shown["tenant_snapshot_id"])


def test_request_list_status_and_manifest(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    handler: ModuleType,
) -> None:
    """A future known_at is refused by name; the request lists QUEUED and has no manifest; after
    the worker runs, the status reads SUCCEEDED and the manifest bytes hash to manifest_sha256.
    The list and the row name who asked for the snapshot as API-S-Actor."""
    lena = member(keyring, clock)
    _confirm_retention(lena.tenant_id, clock)
    ines = colleague(lena.tenant_id, "ines")
    _grant(ines, SNAPSHOT_ROLE)
    actor = enrolled(app, clock, ines)
    future = _post(
        app,
        actor,
        {"known_at": (clock.now() + timedelta(minutes=1)).isoformat(), "purpose": "STORED_BACKUP"},
    )
    assert future.status_code == 422 and _slug(future) == "validation-failed", future.text
    accepted = _post(app, actor, {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"})
    assert accepted.status_code == 202, accepted.text
    snapshot_id = UUID(accepted.headers["X-Erev-Tenant-Snapshot-Id"])
    job_id = UUID(accepted.json()["id"])
    listed = _get(app, actor, SNAPSHOTS)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(snapshot_id)]
    assert listed.json()["items"][0]["status"] == "QUEUED"
    # 04 §16.14 API-S-TenantSnapshot: who asked for it, as API-S-Actor (DG-API-11) — the name the
    # Sandbox copies screen shows under "Created by"; no bare id and no separate kind member.
    asked_by = {"id": str(ines.user_id), "kind": "USER", "display_name": "Ines"}
    assert listed.json()["items"][0]["created_by"] == asked_by
    assert "created_by_kind" not in listed.json()["items"][0]
    assert _get(app, actor, f"{SNAPSHOTS}/{snapshot_id}/manifest").status_code == 404
    _work(lena.tenant_id, job_id, runtime)
    shown = _get(app, actor, f"{SNAPSHOTS}/{snapshot_id}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["status"] == "SUCCEEDED" and shown.json()["job_id"] == str(job_id)
    assert shown.json()["created_by"] == asked_by and "created_by_kind" not in shown.json()
    manifest = _get(app, actor, f"{SNAPSHOTS}/{snapshot_id}/manifest")
    assert manifest.status_code == 200, manifest.text
    assert manifest.headers["content-type"].startswith("application/json")
    digest = shown.json()["manifest_sha256"]
    assert hashlib.sha256(manifest.content).hexdigest() == digest
    assert manifest.headers["ETag"] == f'"{digest}"'
    assert _get(app, actor, f"{SNAPSHOTS}/{uuid4()}").status_code == 404
    filtered = _get(app, actor, f"{SNAPSHOTS}?status=FAILED")
    assert filtered.status_code == 200 and filtered.json()["items"] == []


def test_a_snapshot_asked_too_early_fails_with_the_time_it_becomes_possible(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    handler: ModuleType,
) -> None:
    """BUILD_SPEC SNP-5 (item CFG-PLATFORM-PIN-1): a request without a retention policy in force
    is accepted (202) and its job ends FAILED. The job's problem — what SF-15:sandbox shows under
    the failed copy — is 412 ``precondition-failed`` and its detail is the copy of PRD ERR-77:
    with nothing confirmed, who sets and who approves the policy; with a policy approved today
    and in force from 15 Sep 2026 12:00 UTC, that instant. Both rows read FAILED in the list."""
    lena = member(keyring, clock)  # nothing confirmed
    ines = colleague(lena.tenant_id, "ines")
    _grant(ines, SNAPSHOT_ROLE)
    actor = enrolled(app, clock, ines)
    now = clock.now()
    assert now.date().isoformat() == "2026-09-12"

    def failed() -> dict[str, Any]:
        accepted = _post(app, actor, {"known_at": now.isoformat(), "purpose": "STORED_BACKUP"})
        assert accepted.status_code == 202, accepted.text
        job_id = UUID(accepted.json()["id"])
        _work(lena.tenant_id, job_id, runtime)
        shown = _get(app, actor, f"{JOBS}/{job_id}")
        assert shown.status_code == 200 and shown.json()["state"] == "FAILED", shown.text
        problem: dict[str, Any] = shown.json()["problem"]
        assert (problem["status"], problem["type"]) == (412, f"{PROBLEM_BASE}precondition-failed")
        assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
            ("RETENTION_UNSET", problem["detail"])
        ]
        return problem

    assert failed()["detail"] == snapshot_retention.NONE
    with tenant_session(_db(lena.tenant_id)) as session:
        confirm_retention(session, lena.tenant_id, at=now, effective_from=now + timedelta(days=3))
    assert failed()["detail"] == snapshot_retention.NOT_YET.format(
        approved="12 Sep 2026", effective="15 Sep 2026 12:00 UTC"
    )
    listed = _get(app, actor, SNAPSHOTS)
    assert listed.status_code == 200, listed.text
    assert [item["status"] for item in listed.json()["items"]] == ["FAILED", "FAILED"]


def test_restore_job_answers_mode_restore(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    handler: ModuleType,
) -> None:
    """04 API-R-04 rev 1.67 (D-98 candidate 137 (1)): API-S-Job ``mode`` is ``export`` for the
    snapshot job and ``restore`` for the load-only job of ``POST /tenant/sandboxes`` — on the 202
    answer, on ``GET /jobs/{id}`` and in ``GET /jobs``. PRODUCT DEFECT found by lane F-SNP
    (2026-09-30): the job reads did not select ``job.params``, from which the mode derives, so
    every answer said ``export``."""
    lena = member(keyring, clock)
    _confirm_retention(lena.tenant_id, clock)
    ines = colleague(lena.tenant_id, "ines")
    _grant(ines, SNAPSHOT_ROLE)
    actor = enrolled(app, clock, ines)
    accepted = _post(app, actor, {"known_at": clock.now().isoformat(), "purpose": "STORED_BACKUP"})
    assert accepted.status_code == 202, accepted.text
    export_job = str(accepted.json()["id"])
    assert accepted.json()["mode"] == "export"
    _work(lena.tenant_id, UUID(export_job), runtime)
    restored = call(
        app,
        "POST",
        SANDBOXES,
        json={
            "tenant_snapshot_id": accepted.headers["X-Erev-Tenant-Snapshot-Id"],
            "name": "Restore mode",
        },
        headers={
            **cookie_headers(actor.token, actor.csrf_token),
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert restored.status_code == 202, restored.text
    answer = restored.json()
    assert (answer["kind"], answer["mode"]) == ("TENANT_SNAPSHOT", "restore")
    assert restored.headers["X-Erev-Sandbox-Tenant-Id"] == answer["sandbox_tenant_id"]
    shown = _get(app, actor, f"{JOBS}/{answer['id']}")
    assert shown.status_code == 200 and shown.json()["mode"] == "restore", shown.text
    listed = _get(app, actor, JOBS)
    assert listed.status_code == 200, listed.text
    modes = {item["id"]: item["mode"] for item in listed.json()["items"]}
    assert (modes[answer["id"]], modes[export_job]) == ("restore", "export")


def _reset(app: FastAPI, actor: Actor, body: Mapping[str, Any]) -> HttpResponse:
    return call(
        app,
        "POST",
        RESET,
        json=dict(body),
        headers={
            **cookie_headers(actor.token, actor.csrf_token),
            "Idempotency-Key": str(uuid4()),
        },
    )


def test_reset_permission_and_step_up(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """BUILD_SPEC SNP-3 (PRD ACT-51; 05 SBX-07 rev 1.64), in a sandbox: without ``sandbox.reset``
    403 ``forbidden``; with it but without a fresh TOTP 403 ``mfa-step-up-required``; with both,
    202 with the ``SANDBOX_RESET`` job, ``Location`` and the pre-allocated successor in the
    header and the body; and a second reset while the first is queued is 409
    ``invalid-transition``."""
    sandbox = seeded_sandbox(keyring, clock)
    body = {"mode": "EMPTY", "reason": "Rehearsal complete"}
    omar = colleague(sandbox, "omar")  # no roles
    denied = _reset(app, enrolled(app, clock, omar), body)
    assert denied.status_code == 403 and _slug(denied) == "forbidden", denied.text
    ines = colleague(sandbox, "ines")
    _grant(ines, SNAPSHOT_ROLE)  # the controller also holds sandbox.reset (auth.permissions)
    holder = enrolled(app, clock, ines)  # verified at enrolment
    clock.advance(timedelta(minutes=6))  # past the BR-PLT-06 step-up window
    stale = _reset(app, holder, body)
    assert stale.status_code == 403 and _slug(stale) == "mfa-step-up-required", stale.text
    fresh = step_up(app, clock, holder)
    short = _reset(app, fresh, {"mode": "EMPTY", "reason": "too short"})
    assert short.status_code == 422 and _slug(short) == "validation-failed", short.text
    assert [(e["field"], e["rule_id"]) for e in short.json()["errors"]] == [("reason", "BR-PLT-08")]
    seedless = _reset(
        app,
        fresh,
        {"mode": "SNAPSHOT", "tenant_snapshot_id": str(uuid4()), "reason": body["reason"]},
    )
    assert seedless.status_code == 422, seedless.text  # this sandbox was not loaded from a snapshot
    assert [(e["field"], e["rule_id"]) for e in seedless.json()["errors"]] == [
        ("tenant_snapshot_id", "SANDBOX_SEED_REQUIRED")
    ]
    accepted = _reset(app, fresh, body)
    assert accepted.status_code == 202, accepted.text
    shown = accepted.json()
    assert (shown["kind"], shown["state"], shown["mode"]) == ("SANDBOX_RESET", "QUEUED", None)
    assert accepted.headers["Location"] == f"/api/v1/jobs/{shown['id']}"
    assert UUID(accepted.headers["X-Erev-Sandbox-Tenant-Id"]) == UUID(shown["sandbox_tenant_id"])
    assert UUID(shown["sandbox_tenant_id"]) != sandbox
    again = _reset(app, fresh, body)
    assert again.status_code == 409 and _slug(again) == "invalid-transition", again.text
