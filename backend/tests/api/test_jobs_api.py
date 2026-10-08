"""API-R-11 jobs (04 §15.3 API-R-11, §16.0 API-S-Job, T-PLT-27; 05 JOB-05; BUILD_SPEC PLF-22).

Maya starts the jobs. Omar is another member of the workspace, first without roles and then as an
auditor holding ``audit.read``. The tests play the worker as ``tests/domain/platform/test_jobs.py``
does: they mark the Procrastinate task fetched and call ``run_job``. The last test is the witness
of ``job.cancel`` (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a)).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit.redact import json_value
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, evidence_pack, job
from erev_api.db.transitions import apply
from erev_api.domain.platform import retention  # noqa: F401  (registers RETENTION_SWEEP)
from erev_api.domain.reports import evidence
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import HandlerSpec, JobOutcome, RetryPolicy, run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, text
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import evidence_pack_values, insert_role_assignment

JOBS = "/api/v1/jobs"
PROBLEM_BASE = "https://erev.dev/problems/"
REQUEST_ID = "X-Request-Id"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _start(someone: Member, kind: JobKind, clock: FrozenClock) -> UUID:
    with tenant_session(_db(someone.tenant_id)) as session:
        row = registry.insert_job(
            session,
            kind,
            {},
            tenant_id=someone.tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            session,
            job_id=row["id"],
            tenant_id=someone.tenant_id,
            queue=str(row["queue"]),
            now=clock.now(),
        )
    return UUID(str(row["id"]))


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _run(tenant_id: UUID, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    procrastinate_job_id = _job(tenant_id, job_id)["procrastinate_job_id"]
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def cancel(app: FastAPI, job_id: UUID, actor: Actor) -> HttpResponse:
    return call(
        app,
        "POST",
        f"{JOBS}/{job_id}/cancel",
        headers=cookie_headers(actor.token, actor.csrf_token),
    )


def ids(response: HttpResponse) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_api_s_job_shape_and_access(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya_member = member(keyring, clock)
    omar_member = colleague(maya_member.tenant_id, "omar")
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    omar = workspace(app, omar_member, sign_in(app, omar_member.email))

    swept = _start(maya_member, JobKind.RETENTION_SWEEP, clock)
    _run(maya_member.tenant_id, swept, runtime)
    waiting = _start(maya_member, JobKind.RETENTION_SWEEP, clock)

    shown = get(app, f"{JOBS}/{swept}", maya)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert set(body) == {
        "id",
        "kind",
        "state",
        "progress",
        "result",
        "problem",
        "created_by",
        "created_at",
        "started_at",
        "finished_at",
        # 04 API-S-Job rev 1.67 (SNP-2) and rev 1.281 (item JRN-JOB-MODE-1): derived from the
        # params of a TENANT_SNAPSHOT job and of a JOURNAL_EXPORT job
        "mode",
    }
    assert body["mode"] is None  # "null for every other kind": this one is a RETENTION_SWEEP
    assert (body["id"], body["kind"], body["state"], body["progress"], body["problem"]) == (
        str(swept),
        "RETENTION_SWEEP",
        "SUCCEEDED",
        {"done": 0, "total": None},
        None,
    )
    assert body["result"]["href"] == f"{JOBS}/{swept}"
    assert set(body["result"]["counts"]) == {
        "api_token",
        "idempotency_record",
        "user_session",
        "password_reset_token",
    }
    assert (body["created_by"]["id"], body["created_by"]["kind"]) == (
        str(maya_member.user_id),
        "USER",
    )
    assert body["created_by"]["display_name"]
    assert body["created_at"] and body["started_at"] and body["finished_at"]

    # Another member without audit.read sees neither the job nor the list entry.
    hidden = get(app, f"{JOBS}/{swept}", omar)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    assert ids(get(app, JOBS, omar)) == []

    with tenant_session(_db(maya_member.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=maya_member.tenant_id,
            membership_id=omar_member.membership_id,
            role_code="auditor",
        )
    assert get(app, f"{JOBS}/{swept}", omar).status_code == 200
    assert sorted(ids(get(app, JOBS, omar, kind="RETENTION_SWEEP"))) == sorted(
        [str(swept), str(waiting)]
    )
    # Seeing a job is not enough to cancel it.
    refused = cancel(app, waiting, omar)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    assert ids(get(app, JOBS, maya, kind="RETENTION_SWEEP", state="SUCCEEDED")) == [str(swept)]
    assert ids(get(app, JOBS, maya, state="QUEUED")) == [str(waiting)]
    unknown = get(app, JOBS, maya, state="STALLED")
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text


def test_cancel_between_chunks(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maya_member = member(keyring, clock)
    omar_member = colleague(maya_member.tenant_id, "omar")
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    omar = workspace(app, omar_member, sign_in(app, omar_member.email))
    chunks: list[int] = []
    requests: list[HttpResponse] = []

    def chunked(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        for chunk in range(3):
            chunks.append(chunk)
            context.progress(chunk + 1, 3)
            if chunk == 0:
                # Maya cancels while the first chunk runs.
                requests.append(cancel(app, context.job_id, maya))
            if context.cancel_requested():
                break
        return JobOutcome(state="SUCCEEDED", result={"counts": {"chunks": len(chunks)}})

    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(chunked, RetryPolicy()))
    running = _start(maya_member, JobKind.REPORT_RUN, clock)
    _run(maya_member.tenant_id, running, runtime)

    assert chunks == [0]
    (requested,) = requests
    assert requested.status_code == 200, requested.text
    assert requested.json()["state"] == "RUNNING"
    stored = _job(maya_member.tenant_id, running)
    assert (stored["state"], stored["cancel_requested_at"], stored["finished_at"]) == (
        "CANCELLED",
        clock.now(),
        clock.now(),
    )
    assert (stored["progress_done"], stored["result"]) == (1, {"counts": {"chunks": 1}})
    shown = get(app, f"{JOBS}/{running}", maya).json()
    assert (shown["state"], shown["result"]) == (
        "CANCELLED",
        {"href": None, "counts": {"chunks": 1}},
    )

    finished = cancel(app, running, maya)
    assert (finished.status_code, slug(finished)) == (409, "invalid-transition"), finished.text

    # A queued job is cancelled at once, and its later delivery does nothing.
    queued = _start(maya_member, JobKind.REPORT_RUN, clock)
    denied = cancel(app, queued, omar)
    assert (denied.status_code, slug(denied)) == (404, "not-found"), denied.text
    cancelled = cancel(app, queued, maya)
    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["state"], cancelled.json()["finished_at"] is not None) == (
        "CANCELLED",
        True,
    )
    _run(maya_member.tenant_id, queued, runtime)
    assert chunks == [0]
    assert _job(maya_member.tenant_id, queued)["state"] == "CANCELLED"


def _job_events(tenant_id: UUID, job_id: UUID) -> list[tuple[Any, ...]]:
    """``(action, actor kind, actor id, request id, before, after)`` of a job's audit events, in
    chain order."""
    with tenant_session(_db(tenant_id)) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.actor_kind,
                audit_event.c.actor_id,
                audit_event.c.request_id,
                audit_event.c.before,
                audit_event.c.after,
            )
            .where(audit_event.c.object_type == "job", audit_event.c.object_id == job_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), str(kind), actor, str(request), before, after)
        for action, kind, actor, request, before, after in rows
    ]


def test_r_50_a_cancel_writes_job_cancel_as_the_caller(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 T-PLT-27 rev 1.106 (supervisor ruling R-50 (a)). ``POST /jobs/{id}/cancel`` is a user
    command and wrote no audit event (``domain/platform/jobs.py`` said "cancelling writes no audit
    event"). It writes ``job.cancel`` as the caller under the response's request id when it
    changes the job: for a RUNNING job the request, followed by the registry's ``job.finish`` with
    state CANCELLED when the handler stops; for a QUEUED job the terminal event itself. A repeated
    request on a job already asked to stop and a refused request write nothing."""
    maya_member = member(keyring, clock)
    omar_member = colleague(maya_member.tenant_id, "omar")
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    omar = workspace(app, omar_member, sign_in(app, omar_member.email))
    tenant_id = maya_member.tenant_id
    requests: list[HttpResponse] = []

    def chunked(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        # Maya asks twice while the first chunk runs: the second request changes nothing.
        requests.append(cancel(app, context.job_id, maya))
        requests.append(cancel(app, context.job_id, maya))
        assert context.cancel_requested()
        return JobOutcome(state="SUCCEEDED", result={"counts": {"chunks": 1}})

    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(chunked, RetryPolicy()))
    running = _start(maya_member, JobKind.REPORT_RUN, clock)
    _run(tenant_id, running, runtime)
    first, second = requests
    assert (first.status_code, second.status_code) == (200, 200), (first.text, second.text)
    assert (first.json()["state"], second.json()["state"]) == ("RUNNING", "RUNNING")
    assert _job(tenant_id, running)["state"] == "CANCELLED"
    now = json_value(clock.now())
    assert _job_events(tenant_id, running) == [
        (
            "job.cancel",
            "USER",
            maya_member.user_id,
            first.headers[REQUEST_ID],
            {"state": "RUNNING", "cancel_requested_at": None},
            {"kind": "REPORT_RUN", "state": "RUNNING", "cancel_requested_at": now},
        ),
        (
            "job.finish",
            "SYSTEM",
            None,
            f"job-{running}",
            None,
            {"kind": "REPORT_RUN", "state": "CANCELLED", "problem": None},
        ),
    ]
    assert first.headers[REQUEST_ID] != second.headers[REQUEST_ID]

    # A finished job refuses the request, and someone else's job is not found: no event.
    finished = cancel(app, running, maya)
    assert (finished.status_code, slug(finished)) == (409, "invalid-transition"), finished.text
    queued = _start(maya_member, JobKind.REPORT_RUN, clock)
    denied = cancel(app, queued, omar)
    assert (denied.status_code, slug(denied)) == (404, "not-found"), denied.text
    assert len(_job_events(tenant_id, running)) == 2
    assert _job_events(tenant_id, queued) == []

    # A queued job ends CANCELLED in the command's transaction: job.cancel is its terminal event,
    # and its later delivery writes no job.finish.
    cancelled = cancel(app, queued, maya)
    assert cancelled.status_code == 200, cancelled.text
    _run(tenant_id, queued, runtime)
    assert _job(tenant_id, queued)["state"] == "CANCELLED"
    assert _job_events(tenant_id, queued) == [
        (
            "job.cancel",
            "USER",
            maya_member.user_id,
            cancelled.headers[REQUEST_ID],
            {"state": "QUEUED", "cancel_requested_at": None},
            {"kind": "REPORT_RUN", "state": "CANCELLED", "cancel_requested_at": now},
        )
    ]


def _start_pack(
    someone: Member, clock: FrozenClock, *, pack_status: str = "QUEUED"
) -> tuple[UUID, UUID]:
    # Seed a pack lifecycle record; this fixture does not claim ACCESS pack generation.
    assert registry.HANDLERS[JobKind.EVIDENCE_PACK].handler is evidence.build_pack
    pack = evidence_pack_values(someone.tenant_id, status=pack_status)
    with tenant_session(_db(someone.tenant_id)) as session:
        parent = registry.insert_job(
            session,
            JobKind.EVIDENCE_PACK,
            {"evidence_pack_id": str(pack["id"])},
            tenant_id=someone.tenant_id,
            now=clock.now(),
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
            subject_type="evidence_pack",
            subject_id=pack["id"],
        )
        session.execute(insert(evidence_pack).values(**{**pack, "job_id": parent["id"]}))
        registry.dispatch(
            session,
            job_id=parent["id"],
            tenant_id=someone.tenant_id,
            queue=str(parent["queue"]),
            now=clock.now(),
        )
    return pack["id"], parent["id"]


def test_queued_pack_cancellation_settles_both_records(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    owner = member(keyring, clock)
    actor = workspace(app, owner, sign_in(app, owner.email))
    pack_id, job_id = _start_pack(owner, clock)
    response = cancel(app, job_id, actor)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "CANCELLED"
    with tenant_session(_db(owner.tenant_id), read_only=True) as session:
        pack = (
            session.execute(select(evidence_pack).where(evidence_pack.c.id == pack_id))
            .mappings()
            .one()
        )
        assert (pack["status"], pack["file_id"]) == ("FAILED", None)
        stops = (
            session.execute(
                select(audit_event.c.detail).where(
                    audit_event.c.action == "evidence.stop", audit_event.c.object_id == pack_id
                )
            )
            .scalars()
            .all()
        )
        assert len(stops) == 1 and stops[0]["reason"] == "cancelled"


def test_completed_pack_refuses_late_running_job_cancellation(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    owner = member(keyring, clock)
    actor = workspace(app, owner, sign_in(app, owner.email))
    pack_id, job_id = _start_pack(owner, clock, pack_status="SUCCEEDED")
    with tenant_session(_db(owner.tenant_id)) as session:
        apply(session, "job", job_id, to_status="RUNNING", expected_status="QUEUED", set_values={})
    response = cancel(app, job_id, actor)
    assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
    assert response.json()["detail"] == "The evidence pack has already completed."
    assert _job(owner.tenant_id, job_id)["cancel_requested_at"] is None
    with tenant_session(_db(owner.tenant_id), read_only=True) as session:
        assert (
            session.scalar(select(evidence_pack.c.status).where(evidence_pack.c.id == pack_id))
            == "SUCCEEDED"
        )


def test_unsupported_pack_failure_cleans_its_subject_and_cannot_stop_another_pack(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
) -> None:
    owner = member(keyring, clock)
    pack_id, job_id = _start_pack(owner, clock)
    # A foreign malformed job points at this pack but is not its owning job.
    with tenant_session(_db(owner.tenant_id)) as session:
        foreign = registry.insert_job(
            session,
            JobKind.EVIDENCE_PACK,
            {"evidence_pack_id": str(pack_id)},
            tenant_id=owner.tenant_id,
            now=clock.now(),
            created_by=owner.user_id,
            created_by_kind=PrincipalKind.USER,
            subject_type="evidence_pack",
            subject_id=pack_id,
        )
        registry.dispatch(
            session,
            job_id=foreign["id"],
            tenant_id=owner.tenant_id,
            queue=str(foreign["queue"]),
            now=clock.now(),
        )
    _run(owner.tenant_id, foreign["id"], runtime)
    assert _job(owner.tenant_id, foreign["id"])["state"] == "FAILED"
    with tenant_session(_db(owner.tenant_id), read_only=True) as session:
        assert (
            session.scalar(select(evidence_pack.c.status).where(evidence_pack.c.id == pack_id))
            == "QUEUED"
        )
    _run(owner.tenant_id, job_id, runtime)
    assert _job(owner.tenant_id, job_id)["state"] == "FAILED"
    with tenant_session(_db(owner.tenant_id), read_only=True) as session:
        assert (
            session.scalar(select(evidence_pack.c.status).where(evidence_pack.c.id == pack_id))
            == "FAILED"
        )
