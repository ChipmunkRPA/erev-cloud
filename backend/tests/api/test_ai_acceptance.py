"""Human draft acceptance is atomic, permissioned, replay-safe and never posts revenue."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.documents.pdf import extract_pdf_pages
from erev_api.approvals import subjects
from erev_api.approvals.ai_provenance import accepted_draft_proposals
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    ai_model_log,
    ai_proposal,
    audit_event,
    contract,
    customer,
    file_attachment,
    file_object,
    job,
    subledger_line,
)
from erev_api.domain.ai import acceptance
from erev_api.domain.ai import jobs as ai_jobs
from erev_api.domain.ai.extraction_gateway import ExtractionGateway
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.contracts import activation
from erev_api.enums import FilePurpose
from erev_api.files.store import put_file
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.problems import Problem
from erev_api.schemas.ai import AIExtractionDraftIn
from sqlalchemy import func, insert, select, update
from support.http import call
from support.principals import colleague, cookie_headers
from support.reference import holding
from support.rows import RowContext, ai_proposal_row
from tests.api.test_ai_extractions import enable, source_file
from tests.api.test_explain_api import PLATFORM, World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401


def test_acceptance_is_atomic_and_replay_rechecks_source(
    world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = world.maya
    source = source_file(world)
    with world.place.uow() as uow:
        name = uow.session.scalar(select(customer.c.name).where(customer.c.id == world.customer_id))
        text_file = put_file(
            uow,
            purpose=FilePurpose.AI_DOCUMENT_TEXT,
            stream=io.BytesIO(json.dumps({"pages": ["Synthetic retained evidence"]}).encode()),
            original_filename=None,
            media_type="application/json",
        )
        row = ai_proposal_row(RowContext(world.place.tenant_id, actor.member.user_id), uow.session)
        row.update(
            kind="CONTRACT_EXTRACTION",
            file_object_id=source,
            document_text_file_id=text_file.row["id"],
            content=[
                {"path": "customer_name", "value": name},
                {"path": "lines.0", "value": {"product_code": PLATFORM, "amount": "120.00"}},
            ],
            created_at=clock.now(),
            expires_at=clock.now() + timedelta(days=30),
        )
        uow.session.execute(insert(ai_proposal).values(**row))
        uow.commit()
    proposal_id = row["id"]
    path = f"/api/v1/ai/proposals/{proposal_id}/accept"
    body: dict[str, Any] = {
        "command": "contract.create_draft",
        "entity_code": "AVM-US",
        "field_decisions": [
            {"path": "customer_name", "decision": "ACCEPT"},
            {"path": "lines.0", "decision": "ACCEPT"},
        ],
        "header_bindings": {"customer_name": "customer"},
        "line_bindings": {"lines.0": "O1"},
        "draft": {
            "external_id": "AI-DRAFT-001",
            "customer_id": str(world.customer_id),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM,
                    "quantity": "1",
                    "total_price": {"amount": "120.00", "currency": "USD"},
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
    }
    headers = cookie_headers(actor.token, actor.csrf_token)
    detail = call(world.app, "GET", path.removesuffix("/accept"), headers=headers)
    assert detail.status_code == 200, detail.text
    etag = detail.headers["ETag"]
    missing_etag = call(world.app, "POST", path, json=body, headers=headers)
    assert missing_etag.status_code == 428, missing_etag.text
    viewer = holding(world.app, colleague(world.place.tenant_id, "no_create"), "viewer")
    denied_headers = cookie_headers(viewer.token, viewer.csrf_token) | {"If-Match": etag}
    denied = call(world.app, "POST", path, json=body, headers=denied_headers)
    assert denied.status_code == 403, denied.text
    mismatched = deepcopy(body)
    mismatched["draft"]["lines"][0]["total_price"]["amount"] = "121.00"
    refused = call(
        world.app,
        "POST",
        path,
        json=mismatched,
        headers=cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag},
    )
    assert refused.status_code == 422, refused.text
    rejected = deepcopy(body)
    rejected["field_decisions"] = [
        {"path": path, "decision": "REJECT", "reason": "Reviewer excludes this field"}
        for path in ("customer_name", "lines.0")
    ]
    rejected["header_bindings"] = {}
    rejected["line_bindings"] = {}
    empty = call(
        world.app,
        "POST",
        path,
        json=rejected,
        headers=cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag},
    )
    assert empty.status_code == 422, empty.text
    assert "AI_REVIEW_EMPTY_ACCEPTANCE" in empty.text
    parsed = AIExtractionDraftIn.model_validate(body)
    with pytest.raises(Problem) as expired:
        with replace(world.place, clock=FrozenClock(row["expires_at"])).uow() as uow:
            acceptance.accept_draft(uow, proposal_id, parsed, check_version=lambda _: None)
    assert expired.value.slug == "invalid-transition"

    def fail_transition(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected transition failure")

    with monkeypatch.context() as patch:
        patch.setattr(acceptance, "apply", fail_transition)
        with pytest.raises(RuntimeError, match="injected transition failure"):
            with world.place.uow() as uow:
                acceptance.accept_draft(uow, proposal_id, parsed, check_version=lambda _: None)
                uow.commit()
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(file_attachment)
                .where(file_attachment.c.file_object_id == source)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(contract)
                .where(contract.c.external_id == "AI-DRAFT-001")
            )
            == 0
        )
        assert (
            session.scalar(select(ai_proposal.c.status).where(ai_proposal.c.id == proposal_id))
            == "proposed"
        )
    request_headers = [
        cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag} for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(call, world.app, "POST", path, json=body, headers=h)
            for h in request_headers
        ]
        responses = [future.result(timeout=30) for future in futures]
    assert sorted(response.status_code for response in responses) == [201, 412], [
        r.text for r in responses
    ]
    accepted = next(response for response in responses if response.status_code == 201)
    winning_headers = request_headers[responses.index(accepted)]
    contract_id = UUID(accepted.json()["contract_id"])
    assert accepted.headers["Location"] == f"/api/v1/contracts/{contract_id}"
    replay = call(world.app, "POST", path, json=body, headers=winning_headers)
    assert replay.status_code == 201 and replay.json() == accepted.json(), replay.text
    with tenant_session(world.place.principal.db_context) as session:
        saved = (
            session.execute(select(ai_proposal).where(ai_proposal.c.id == proposal_id))
            .mappings()
            .one()
        )
        assert saved["status"] == "accepted" and saved["accepted_object_id"] == contract_id
        assert saved["accepted_by"] == actor.member.user_id and saved["row_version"] == 2
        assert len(saved["field_decisions"]) == 2
        created = (
            session.execute(select(contract).where(contract.c.id == contract_id)).mappings().one()
        )
        assert created["status"] == "DRAFT" and created["created_by"] == actor.member.user_id
        assert (
            session.scalar(
                select(func.count())
                .select_from(subledger_line)
                .where(subledger_line.c.contract_id == contract_id)
            )
            == 0
        )
        attached = (
            session.execute(
                select(file_attachment).where(file_attachment.c.file_object_id == source)
            )
            .mappings()
            .one()
        )
        assert attached["subject_type"] == "contract" and attached["subject_id"] == contract_id
        assert len(accepted_draft_proposals(session, contract_id)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.action == "ai_proposal.accept",
                    audit_event.c.object_id == proposal_id,
                )
            )
            == 1
        )
        session.execute(
            update(file_object)
            .where(file_object.c.id == source)
            .values(
                shredded_at=clock.now(),
                shredded_by=actor.member.user_id,
                shredded_by_kind="USER",
                shred_reason="fixture unavailable source",
            )
        )
    unavailable = call(world.app, "POST", path, json=body, headers=winning_headers)
    assert unavailable.status_code == 404, unavailable.text


def test_worker_proposal_acceptance_preserves_evidence_and_shares_source(
    world: World, clock: FrozenClock, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real fixture PDF parsing and queued worker; deterministic provider, no live model."""
    source = source_file(world)
    enable(world, clock, send_text=True)
    actor = world.maya
    provider_calls: list[AIRequest] = []

    class Provider:
        def complete(self, request: AIRequest) -> AIResponse:
            provider_calls.append(request)
            outgoing = json.loads(request.messages[0]["content"])
            page = json.loads(outgoing["contract_text"])[0]
            suggested = "Kinsley Marrow Foods Inc."
            start = page["text"].index(suggested)
            raw = json.dumps(
                [
                    {
                        "path": "customer_name",
                        "value": suggested,
                        "confidence": 0.97,
                        "citation": {
                            "ref_type": "document",
                            "ref_id": str(source),
                            "page": 1,
                            "char_start": start,
                            "char_end": start + len(suggested),
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
            extract_pages=extract_pdf_pages,
        ),
    )
    monkeypatch.setattr(ai_jobs, "_wait", lambda _delay: pytest.fail("unexpected retry"))
    headers = cookie_headers(actor.token, actor.csrf_token)
    queued = call(
        world.app,
        "POST",
        "/api/v1/ai/contract-extractions",
        json={"file_id": str(source)},
        headers=headers,
    )
    assert queued.status_code == 202, queued.text
    run_job(
        UUID(queued.json()["id"]),
        world.place.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=world.app.state.file_store),
    )
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        finished = (
            session.execute(select(job).where(job.c.id == UUID(queued.json()["id"])))
            .mappings()
            .one()
        )
        assert finished["state"] == "SUCCEEDED", finished["problem"]
        proposal = session.execute(select(ai_proposal)).mappings().one()
        assert proposal["status"] == "proposed"
        name = session.scalar(select(customer.c.name).where(customer.c.id == world.customer_id))
    path = f"/api/v1/ai/proposals/{proposal['id']}"
    detail = call(world.app, "GET", path, headers=headers)
    assert detail.status_code == 200, detail.text
    pages = call(world.app, "GET", path + "/document-text", headers=headers)
    assert pages.status_code == 200, pages.text
    assert len(pages.json()["pages"]) == 4
    assert "Kinsley Marrow Foods Inc." in pages.json()["pages"][0]["text"]
    reviewer = holding(world.app, colleague(world.place.tenant_id, "evidence_reader"), "viewer")
    review_headers = cookie_headers(reviewer.token, reviewer.csrf_token)
    before = call(world.app, "GET", path, headers=review_headers)
    assert before.status_code == 404, before.text
    body = {
        "command": "contract.create_draft",
        "entity_code": "AVM-US",
        "field_decisions": [
            {
                "path": "customer_name",
                "decision": "EDIT",
                "value": name,
                "reason": "Human selects the existing demo customer.",
            }
        ],
        "header_bindings": {"customer_name": "customer"},
        "draft": {
            "external_id": "AI-WORKER-DRAFT-01",
            "customer_id": str(world.customer_id),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM,
                    "quantity": "1",
                    "total_price": {"amount": "120.00", "currency": "USD"},
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
    }
    accepted = call(
        world.app,
        "POST",
        path + "/accept",
        json=body,
        headers=cookie_headers(actor.token, actor.csrf_token)
        | {"If-Match": detail.headers["ETag"]},
    )
    assert accepted.status_code == 201, accepted.text
    contract_id = UUID(accepted.json()["contract_id"])
    shared = call(world.app, "GET", path, headers=review_headers)
    assert shared.status_code == 200, shared.text
    assert shared.json()["status"] == "accepted"
    assert shared.json()["content"] == detail.json()["content"]
    assert shared.json()["citations"] == detail.json()["citations"]
    shared_text = call(world.app, "GET", path + "/document-text", headers=review_headers)
    assert shared_text.status_code == 200 and shared_text.json() == pages.json(), shared_text.text
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        saved = session.execute(select(ai_proposal)).mappings().one()
        assert saved["field_decisions"][0]["value"] == name
        assert saved["field_decisions"][0]["decision"] == "EDIT"
        assert saved["ai_model_log_id"] == proposal["ai_model_log_id"]
        assert "AI_ASSISTED" in activation.activation_flags(session, contract_id)
        provenance = subjects.contract_activation_content(session, contract_id)["ai_assisted"]
        assert provenance[0]["proposal_id"] == str(proposal["id"])
        assert provenance[0]["accepted_by"] == str(actor.member.user_id)
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(subledger_line)
                .where(subledger_line.c.contract_id == contract_id)
            )
            == 0
        )
    assert len(provider_calls) == 1
