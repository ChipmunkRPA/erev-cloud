"""Extraction submission binds readable files and leaves parsing/provider execution to jobs."""

from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, audit_event, file_object, job, tenant
from erev_api.domain.ai import jobs as ai_jobs
from erev_api.domain.ai.commands import EXTRACTION_MAX_TOKENS
from erev_api.domain.ai.extraction_fields import CONTRACT_EXTRACTION_PATHS
from erev_api.domain.ai.extraction_gateway import ExtractionGateway
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.enums import FilePurpose, RegistryCategory
from erev_api.files.store import store_file
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from sqlalchemy import func, insert, select, text, update
from support.http import HttpResponse, call
from support.principals import colleague, cookie_headers
from support.reference import holding
from support.rows import RowContext, file_object_row, publish_registry_version
from tests.api.test_explain_api import World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401

PATH = "/api/v1/ai/contract-extractions"


def source_file(world: World) -> UUID:
    data = (
        Path(__file__).parents[1] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"
    ).read_bytes()
    with world.place.uow() as uow:
        row = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(data),
            original_filename="contract.pdf",
            media_type="application/pdf",
        )
        uow.commit()
    return UUID(str(row["id"]))


def enable(world: World, clock: FrozenClock, *, send_text: bool) -> None:
    clock.advance(timedelta(seconds=1))
    with tenant_session(world.place.principal.db_context) as session:
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.send_contract_text": send_text,
                "ai.monthly_token_budget": 10000,
            },
            at=clock.now(),
        )


def test_extraction_submission_and_worker(
    world: World, clock: FrozenClock, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_id = source_file(world)
    body = {"file_id": str(file_id)}
    actor = world.maya
    observed: list[AIRequest] = []
    parsed: list[bytes] = []

    def parser(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
        assert send_contract_text
        parsed.append(data)
        return ("Customer Kinsley Marrow Foods Inc.",)

    class Provider:
        def complete(self, request: AIRequest) -> AIResponse:
            observed.append(request)
            assert request.max_tokens == EXTRACTION_MAX_TOKENS
            facts = json.loads(request.messages[0]["content"])["facts"]
            assert frozenset(facts["allowed_paths"]) == CONTRACT_EXTRACTION_PATHS
            raw = json.dumps(
                [
                    {
                        "path": "customer_name",
                        "value": "Kinsley Marrow Foods Inc.",
                        "confidence": 0.97,
                        "citation": {
                            "ref_type": "document",
                            "ref_id": str(file_id),
                            "page": 1,
                            "char_start": 9,
                            "char_end": 33,
                        },
                    }
                ]
            )
            return AIResponse(
                raw, sha256(raw.encode()).hexdigest(), 40, 20, 1, request.model, "end_turn"
            )

    monkeypatch.setattr(
        ai_jobs,
        "_gateway",
        ExtractionGateway(
            provider="fake",
            provider_factory=Provider,
            platform_kill_switch=lambda: False,
            extract_pages=parser,
        ),
    )
    monkeypatch.setattr(ai_jobs, "_wait", lambda _delay: pytest.fail("unexpected retry"))
    reader = holding(world.app, colleague(world.place.tenant_id, "auditor"), "auditor")
    denied = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(reader.token, reader.csrf_token)
    )
    assert denied.status_code == 403, denied.text
    disabled = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(actor.token, actor.csrf_token)
    )
    assert disabled.status_code == 409 and disabled.json()["type"].endswith("ai-disabled"), (
        disabled.text
    )
    enable(world, clock, send_text=False)
    text_off = call(
        world.app, "POST", PATH, json=body, headers=cookie_headers(actor.token, actor.csrf_token)
    )
    assert (
        text_off.status_code == 422
        and text_off.json()["errors"][0]["rule_id"] == "AI_TEXT_DISABLED"
    ), text_off.text
    enable(world, clock, send_text=True)
    with world.place.uow() as uow:
        hidden = file_object_row(RowContext(world.place.tenant_id, uuid4()), uow.session)
        uow.session.execute(insert(file_object).values(**hidden))
        invalid = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(b"name,amount\nExample,120.00\n"),
            original_filename="contract.csv",
            media_type="text/csv",
        )
        uow.commit()
    for inaccessible in (hidden["id"], uuid4()):
        response = call(
            world.app,
            "POST",
            PATH,
            json={"file_id": str(inaccessible)},
            headers=cookie_headers(actor.token, actor.csrf_token),
        )
        assert response.status_code == 404, response.text
    invalid_response = call(
        world.app,
        "POST",
        PATH,
        json={"file_id": str(invalid["id"])},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert invalid_response.status_code == 422, invalid_response.text
    for extra in (
        {"model": "unapproved"},
        {"allowed_paths": ["submit_for_activation"]},
        {"max_tokens": 1},
    ):
        response = call(
            world.app,
            "POST",
            PATH,
            json=body | extra,
            headers=cookie_headers(actor.token, actor.csrf_token),
        )
        assert response.status_code == 422, response.text
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert (
            session.scalar(select(func.count()).select_from(job).where(job.c.kind == "AI_TASK"))
            == 0
        )
    headers = cookie_headers(actor.token, actor.csrf_token)
    accepted = call(world.app, "POST", PATH, json=body, headers=headers)
    assert accepted.status_code == 202, accepted.text
    job_id = UUID(accepted.json()["id"])
    assert accepted.headers["Location"] == f"/api/v1/jobs/{job_id}"
    replay = call(world.app, "POST", PATH, json=body, headers=headers)
    assert replay.status_code == 202 and replay.json() == accepted.json(), replay.text
    assert observed == []
    assert parsed == []
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        queued = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        source = (
            session.execute(select(file_object).where(file_object.c.id == file_id)).mappings().one()
        )
        assert UUID(queued["params"]["engine_release_id"])
        assert {k: v for k, v in queued["params"].items() if k != "engine_release_id"} == {
            "operation": "extraction",
            "file_id": str(file_id),
            "file_sha256": source["sha256"],
            "allowed_paths": sorted(CONTRACT_EXTRACTION_PATHS),
            "max_tokens": EXTRACTION_MAX_TOKENS,
        }
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 0
    run_job(
        job_id,
        world.place.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=world.app.state.file_store),
    )
    assert len(observed) == len(parsed) == 1
    with tenant_session(world.place.principal.db_context) as session:
        finished = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        assert finished["state"] == "SUCCEEDED", finished["problem"]
        proposal = session.execute(select(ai_proposal)).mappings().one()
        assert proposal["status"] == "proposed" and proposal["file_object_id"] == file_id
        assert proposal["created_by"] == actor.member.user_id
        proposal_id = proposal["id"]
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.place.tenant_id)
            .values(
                ai_disabled_at=clock.now(),
                ai_disabled_by=actor.member.user_id,
                ai_disabled_by_kind="USER",
            )
        )
    detail_path = f"/api/v1/ai/proposals/{proposal_id}"
    detail = call(world.app, "GET", detail_path, headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["kind"] == "CONTRACT_EXTRACTION"
    assert detail.json()["file_object_id"] == str(file_id)
    assert detail.json()["document_text_file_id"] == str(proposal["document_text_file_id"])
    assert detail.json()["content"] == proposal["content"]
    assert detail.json()["citations"] == proposal["citations"]
    assert detail.headers["ETag"]
    text_path = f"{detail_path}/document-text"
    text_response = call(world.app, "GET", text_path, headers=headers)
    assert text_response.status_code == 200, text_response.text
    assert text_response.json() == {
        "proposal_id": str(proposal_id),
        "file_object_id": str(file_id),
        "pages": [{"page_no": 1, "text": "Customer Kinsley Marrow Foods Inc."}],
    }
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        downloads = (
            session.execute(
                select(audit_event).where(
                    audit_event.c.action == "file.download",
                    audit_event.c.object_id == proposal["document_text_file_id"],
                )
            )
            .mappings()
            .all()
        )
        assert len(downloads) == 1
        assert downloads[0]["actor_id"] == actor.member.user_id
    assert len(observed) == len(parsed) == 1
    forbidden = call(
        world.app, "GET", detail_path, headers=cookie_headers(reader.token, reader.csrf_token)
    )
    assert forbidden.status_code == 403, forbidden.text
    other = holding(world.app, colleague(world.place.tenant_id, "other_viewer"), "viewer")
    hidden_detail = call(
        world.app, "GET", detail_path, headers=cookie_headers(other.token, other.csrf_token)
    )
    assert hidden_detail.status_code == 404, hidden_detail.text
    for denied_actor, expected_status in ((reader, 403), (other, 404)):
        denied_text = call(
            world.app,
            "GET",
            text_path,
            headers=cookie_headers(denied_actor.token, denied_actor.csrf_token),
        )
        assert denied_text.status_code == expected_status, denied_text.text
    missing = call(world.app, "GET", f"/api/v1/ai/proposals/{uuid4()}", headers=headers)
    assert missing.status_code == 404, missing.text
    with tenant_session(world.place.principal.db_context) as session:
        session.execute(
            update(file_object)
            .where(file_object.c.id == proposal["document_text_file_id"])
            .values(
                shredded_at=clock.now(),
                shredded_by=actor.member.user_id,
                shredded_by_kind="USER",
                shred_reason="fixture unavailable text",
            )
        )
    shredded_text = call(world.app, "GET", text_path, headers=headers)
    assert shredded_text.status_code == 404, shredded_text.text
    with tenant_session(world.place.principal.db_context) as session:
        # Model a subsequently unavailable source in the fixture; replay must recheck it.
        session.execute(
            update(file_object)
            .where(file_object.c.id == file_id)
            .values(
                shredded_at=clock.now(),
                shredded_by=actor.member.user_id,
                shredded_by_kind="USER",
                shred_reason="fixture unavailable source",
            )
        )
    replay_denied = call(world.app, "POST", PATH, json=body, headers=headers)
    assert replay_denied.status_code == 404, replay_denied.text
    unavailable = call(world.app, "GET", detail_path, headers=headers)
    assert unavailable.status_code == 404, unavailable.text
    unavailable_text = call(world.app, "GET", text_path, headers=headers)
    assert unavailable_text.status_code == 404, unavailable_text.text
    assert len(observed) == 1


def test_disable_serializes_with_extraction_admission(world: World, clock: FrozenClock) -> None:
    file_id = source_file(world)
    enable(world, clock, send_text=True)
    actor = world.maya
    started = Event()

    def submit() -> HttpResponse:
        started.set()
        return call(
            world.app,
            "POST",
            PATH,
            json={"file_id": str(file_id)},
            headers=cookie_headers(actor.token, actor.csrf_token),
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with tenant_session(world.place.principal.db_context) as session:
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
            assert blocked and not pending.done()
        response = pending.result(timeout=10)
    assert response.status_code == 409 and response.json()["type"].endswith("ai-disabled"), (
        response.text
    )
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert (
            session.scalar(select(func.count()).select_from(job).where(job.c.kind == "AI_TASK"))
            == 0
        )
