"""Number explanations enter the persisted worker path without HTTP provider calls."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, audit_event, job, role_assignment, tenant
from erev_api.domain.ai import commands as ai_commands
from erev_api.domain.ai import gateway as gateway_module
from erev_api.domain.ai import jobs as ai_jobs
from erev_api.domain.ai.gateway import AiGateway
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.ai.retrieval import RetrievedNarrative, retrieve_narrative
from erev_api.enums import RegistryCategory
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.problems import Problem
from sqlalchemy import func, select, text, update
from support.http import HttpResponse, call
from support.principals import colleague, cookie_headers, member
from support.reference import assign, entity, holding
from support.rows import publish_registry_version
from tests.api.test_explain_api import World, k01_computed, september_line
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401

PATH = "/api/v1/ai/explanations"


def test_submission_is_authorized_idempotent_and_processed_by_worker(
    world: World, clock: FrozenClock, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    k01_computed(world)
    line = september_line(world)
    body = {"object_type": "schedule_line", "id": str(line["id"]), "measure": "amount"}
    actor = world.maya
    db = DbContext(world.place.tenant_id, actor.member.user_id, "*")
    observed: list[AIRequest] = []

    class Provider:
        def complete(self, request: AIRequest) -> AIResponse:
            observed.append(request)
            root = json.loads(request.messages[0]["content"])["facts"]["root_node_id"]
            answer = json.dumps({"narrative": f"Revenue USD {line['amount']}.", "node_ids": [root]})
            return AIResponse(
                answer, sha256(answer.encode()).hexdigest(), 20, 10, 0, request.model, "end_turn"
            )

    gateway = AiGateway(
        provider="fake", provider_factory=Provider, platform_kill_switch=lambda: False
    )
    monkeypatch.setattr(ai_jobs, "_gateway", gateway)
    monkeypatch.setattr(ai_jobs, "_wait", lambda _delay: pytest.fail("unexpected retry"))
    reader = holding(world.app, colleague(world.place.tenant_id, "auditor"), "auditor")
    refused = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(reader.token, reader.csrf_token)
    )
    assert refused.status_code == 403, refused.text
    assign(actor.member, "viewer")
    disabled = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(actor.token, actor.csrf_token)
    )
    assert disabled.status_code == 409 and disabled.json()["type"].endswith("ai-disabled"), (
        disabled.text
    )
    with tenant_session(db) as session:
        assert (
            session.scalar(select(func.count()).select_from(job).where(job.c.kind == "AI_TASK"))
            == 0
        )
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.model": "fixture-model",
                "ai.monthly_token_budget": 10000,
                "ai.send_contract_text": False,
                "ai.redact_contact_details": True,
            },
            at=clock.now(),
        )
    headers = cookie_headers(actor.token, actor.csrf_token)
    accepted = call(world.app, "POST", PATH, json=body, headers=headers)
    assert accepted.status_code == 202, accepted.text
    job_id = UUID(accepted.json()["id"])
    assert accepted.headers["Location"] == f"/api/v1/jobs/{job_id}"
    replay = call(world.app, "POST", PATH, json=body, headers=headers)
    assert replay.status_code == 202 and replay.json() == accepted.json(), replay.text
    assert observed == []
    with tenant_session(db) as session:
        rows = session.execute(select(job).where(job.c.kind == "AI_TASK")).mappings().all()
        assert len(rows) == 1
        queued = rows[0]
        assert queued["state"] == "QUEUED" and queued["created_by"] == actor.member.user_id
        assert queued["params"]["operation"] == "narrative"
        assert "messages" not in queued["params"] and "model" not in queued["params"]
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 0
        assert session.scalar(select(func.count()).select_from(ai_proposal)) == 0
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
            {"id": queued["procrastinate_job_id"]},
        )
    run_job(
        job_id,
        world.place.tenant_id,
        attempt=1,
        runtime=JobRuntime(
            clock=clock,
            keyring=keyring,
            files=world.app.state.file_store,
        ),
    )
    assert len(observed) == 1
    with tenant_session(db, read_only=True) as session:
        result = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        assert result["state"] == "SUCCEEDED", result["problem"]
        proposal = session.execute(select(ai_proposal)).mappings().one()
        assert proposal["id"] == UUID(result["result"]["proposal_id"])
        assert proposal["job_id"] == job_id and proposal["status"] == "proposed"
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "job.start", audit_event.c.object_id == job_id)
            )
            == 1
        )

    proposal_path = f"/api/v1/ai/proposals/{proposal['id']}"

    def read_as(who: Any) -> HttpResponse:
        return call(
            world.app, "GET", proposal_path, headers=cookie_headers(who.token, who.csrf_token)
        )

    saved = read_as(actor)
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"] == proposal["content"]
    assert saved.json()["citations"] == proposal["citations"]
    assert saved.json()["created_by"]["id"] == str(actor.member.user_id)
    assert saved.headers["ETag"]
    assert "job_source_sha256" not in saved.json()
    assert read_as(reader).status_code == 403
    foreign = holding(world.app, member(keyring, clock, name="foreign"), "viewer")
    assert read_as(foreign).status_code == 404

    germany = entity(
        world.app,
        actor,
        code="AVM-DE",
        calendar_id=world.calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    outsider = colleague(world.place.tenant_id, "dieter")
    scoped = holding(world.app, outsider, "viewer", entity_ids=[UUID(germany["id"])])
    hidden = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(scoped.token, scoped.csrf_token)
    )
    assert hidden.status_code == 404, hidden.text
    assert read_as(scoped).status_code == 404
    with monkeypatch.context() as patch:
        patch.setattr(
            world.app.state,
            "settings",
            world.app.state.settings.model_copy(update={"ai_kill_switch": True}),
        )
        assert read_as(actor).json() == saved.json()
        stopped = call(
            world.app,
            "POST",
            PATH,
            json=body,
            headers=cookie_headers(actor.token, actor.csrf_token),
        )
        assert stopped.status_code == 409 and stopped.json()["type"].endswith("ai-disabled"), (
            stopped.text
        )
    with tenant_session(db, read_only=True) as session:
        assert (
            session.scalar(select(func.count()).select_from(job).where(job.c.kind == "AI_TASK"))
            == 1
        )

    # A different authorized member may read, but revocation takes effect immediately.
    peer = holding(world.app, colleague(world.place.tenant_id, "peer"), "viewer")
    assert read_as(peer).status_code == 200
    with tenant_session(db) as session:
        session.execute(
            update(role_assignment)
            .where(role_assignment.c.membership_id == peer.member.membership_id)
            .values(valid_to=clock.now())
        )
    assert read_as(peer).status_code == 403
    with tenant_session(db) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.place.tenant_id)
            .values(
                ai_disabled_at=clock.now(),
                ai_disabled_by=actor.member.user_id,
                ai_disabled_by_kind="USER",
            )
        )
    assert read_as(actor).json() == saved.json()
    with tenant_session(db) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.place.tenant_id)
            .values(
                ai_disabled_at=None,
                ai_disabled_by=None,
                ai_disabled_by_kind=None,
            )
        )
    assert len(observed) == 1

    # A source re-resolved to another trace must not reach the provider. The
    # retrieval double models that concurrent source change after HTTP admission.
    queued_again = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(actor.token, actor.csrf_token)
    )
    assert queued_again.status_code == 202, queued_again.text
    changed_job = UUID(queued_again.json()["id"])
    real_retrieve = retrieve_narrative

    def changed_trace(*args: Any, **kwargs: Any) -> RetrievedNarrative:
        fresh = real_retrieve(*args, **kwargs)
        return replace(fresh, prepared=replace(fresh.prepared, trace_id=uuid4()))

    with tenant_session(db) as session:
        task_id = session.scalar(select(job.c.procrastinate_job_id).where(job.c.id == changed_job))
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"), {"id": task_id}
        )
    with monkeypatch.context() as patch:
        patch.setattr(gateway_module, "retrieve_narrative", changed_trace)
        run_job(
            changed_job,
            world.place.tenant_id,
            attempt=1,
            runtime=JobRuntime(
                clock=clock,
                keyring=keyring,
                files=world.app.state.file_store,
            ),
        )
    assert len(observed) == 1
    with tenant_session(db, read_only=True) as session:
        assert session.scalar(select(job.c.state).where(job.c.id == changed_job)) == "FAILED"
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 1

    reject_path = proposal_path + "/reject"
    reject_body = {"reason": "  Superseded by the reviewed explanation.  "}

    def reject_as(who: Any, etag: str | None = None, payload: Any = reject_body) -> HttpResponse:
        request_headers = cookie_headers(who.token, who.csrf_token)
        if etag is not None:
            request_headers["If-Match"] = etag
        return call(world.app, "POST", reject_path, json=payload, headers=request_headers)

    assert reject_as(actor).status_code == 428
    assert reject_as(reader, saved.headers["ETag"]).status_code == 403
    assert reject_as(scoped, saved.headers["ETag"]).status_code == 404
    assert reject_as(foreign, saved.headers["ETag"]).status_code == 404
    assert reject_as(actor, saved.headers["ETag"], {"reason": "   "}).status_code == 422
    assert read_as(actor).json()["status"] == "proposed"
    # A broad ai.use session must still obey a narrower contract.read grant.
    restricted_reader = replace(
        world.place.principal,
        permission_scopes={
            **world.place.principal.permission_scopes,
            "ai.use": "*",
            "contract.read": frozenset({UUID(germany["id"])}),
        },
    )
    with pytest.raises(Problem) as outside_source:
        with world.place.uow(restricted_reader) as uow:
            ai_commands.reject_proposal(
                uow, proposal["id"], reason="Out of scope", check_version=lambda _version: None
            )
    assert outside_source.value.slug == "not-found"
    # At the exact expiry boundary a still-proposed row cannot be acted on.
    with pytest.raises(Problem) as expired:
        with replace(world.place, clock=FrozenClock(proposal["expires_at"])).uow() as uow:
            ai_commands.reject_proposal(
                uow, proposal["id"], reason="Too late", check_version=lambda _version: None
            )
    assert expired.value.slug == "invalid-transition"
    assert read_as(actor).json()["status"] == "proposed"
    # Competing reviewers holding the same ETag cannot both win the transition.
    with monkeypatch.context() as patch:
        patch.setattr(
            world.app.state,
            "settings",
            world.app.state.settings.model_copy(update={"ai_kill_switch": True}),
        )
        review_headers = [cookie_headers(actor.token, actor.csrf_token) for _ in range(2)]
        for request_headers in review_headers:
            request_headers["If-Match"] = saved.headers["ETag"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    call, world.app, "POST", reject_path, json=reject_body, headers=request_headers
                )
                for request_headers in review_headers
            ]
            outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in outcomes) == [200, 412], [
        response.text for response in outcomes
    ]
    rejected = next(response for response in outcomes if response.status_code == 200)
    winning_headers = review_headers[outcomes.index(rejected)]
    replayed_rejection = call(
        world.app, "POST", reject_path, json=reject_body, headers=winning_headers
    )
    assert replayed_rejection.status_code == 200
    assert replayed_rejection.json() == rejected.json()
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == reject_body["reason"].strip()
    assert rejected.json()["rejected_by"]["id"] == str(actor.member.user_id)
    assert rejected.json()["content"] == saved.json()["content"]
    assert rejected.json()["row_version"] == saved.json()["row_version"] + 1
    assert reject_as(actor, rejected.headers["ETag"]).status_code == 409
    assert read_as(actor).json() == rejected.json()
    with tenant_session(db, read_only=True) as session:
        events = (
            session.execute(
                select(audit_event).where(
                    audit_event.c.action == "ai_proposal.reject",
                    audit_event.c.object_id == proposal["id"],
                )
            )
            .mappings()
            .all()
        )
        assert len(events) == 1
        assert events[0]["actor_id"] == actor.member.user_id
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 1
    assert len(observed) == 1

    # A cached successful response must not bypass subsequently narrowed source access.
    with tenant_session(db) as session:
        session.execute(
            update(role_assignment)
            .where(role_assignment.c.membership_id == actor.member.membership_id)
            .values(
                valid_to=clock.now(),
                revoked_at=clock.now(),
                revoked_by=actor.member.user_id,
                revoked_by_kind="USER",
            )
        )
    assign(actor.member, "viewer", entity_ids=[UUID(germany["id"])])
    revoked_replay = call(world.app, "POST", reject_path, json=reject_body, headers=winning_headers)
    assert revoked_replay.status_code == 404, revoked_replay.text
    assert read_as(actor).status_code == 404


def test_disable_serializes_with_explanation_admission(world: World, clock: FrozenClock) -> None:
    k01_computed(world)
    line = september_line(world)
    actor = world.maya
    db = DbContext(world.place.tenant_id, actor.member.user_id, "*")
    body = {"object_type": "schedule_line", "id": str(line["id"]), "measure": "amount"}
    with tenant_session(db) as session:
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.AI,
            values={"ai.enabled": True},
            at=clock.now(),
        )
    started = Event()

    def submit() -> HttpResponse:
        started.set()
        return call(
            world.app,
            "POST",
            PATH,
            json=body,
            headers=cookie_headers(actor.token, actor.csrf_token),
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with tenant_session(db) as session:
            holder = session.scalar(select(func.pg_backend_pid()))
            session.execute(
                update(tenant)
                .where(tenant.c.id == world.place.tenant_id)
                .values(
                    ai_disabled_at=clock.now(),
                    ai_disabled_by=actor.member.user_id,
                    ai_disabled_by_kind="USER",
                )
            )
            pending = pool.submit(submit)
            assert started.wait(timeout=5)
            blocked = False
            for _ in range(100):
                blocked = bool(
                    session.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE :holder = ANY(pg_blocking_pids(pid)))"
                        ),
                        {"holder": holder},
                    )
                )
                if blocked:
                    break
                Event().wait(0.02)
            assert blocked, "submission did not serialize behind the tenant switch"
            assert not pending.done()
        response = pending.result(timeout=10)
    assert response.status_code == 409 and response.json()["type"].endswith("ai-disabled"), (
        response.text
    )
    with tenant_session(db, read_only=True) as session:
        assert (
            session.scalar(select(func.count()).select_from(job).where(job.c.kind == "AI_TASK"))
            == 0
        )
