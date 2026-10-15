"""Extraction output is bound to encrypted original pages and committed call intent."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    ai_call_intent,
    ai_model_log,
    ai_proposal,
    audit_event,
    contract_version,
    file_object,
)
from erev_api.domain.ai.attempts import record_intent
from erev_api.domain.ai.document_retrieval import RetrievedExtraction, retrieve_document
from erev_api.domain.ai.extraction_proposals import record_extraction, store_document_text
from erev_api.domain.ai.ports import AIResponse
from erev_api.domain.ai.proposals import ProposalEvidenceRefused
from erev_api.enums import FilePurpose, RegistryCategory
from erev_api.files.store import open_file, store_file
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import func, select
from support.rows import publish_registry_version
from tests.api.test_explain_api import World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401
from tests.domain.ai.test_narrative_retrieval import context_for


def test_retained_extraction_evidence_success_failure_and_rollback(
    world: World, clock: FrozenClock, keyring: KeyRing
) -> None:
    pdf = (
        Path(__file__).parents[2] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"
    ).read_bytes()
    original = "Contact buyer@example.com; amount USD 120.00 due."
    with world.place.uow() as uow:
        source = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(pdf),
            original_filename="contract.pdf",
            media_type="application/pdf",
        )
        publish_registry_version(
            uow.session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.AI,
            values={"ai.enabled": True, "ai.send_contract_text": True},
            at=clock.now(),
        )
        uow.commit()
    digest = sha256_hex(
        {"file_id": str(source["id"]), "sha256": source["sha256"], "max_tokens": 1024}
    )

    def parser(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
        assert data == pdf and send_contract_text
        return (original,)

    def start() -> tuple[JobContext, RetrievedExtraction, UUID, UUID]:
        base = context_for(world.maya.member, clock)
        context = JobContext(
            job_id=base.job_id,
            tenant_id=base.tenant_id,
            kind=base.kind,
            principal=base.principal,
            runtime=replace(base.runtime, keyring=keyring, files=world.app.state.file_store),
        )
        retrieved = retrieve_document(
            context,
            file_id=source["id"],
            max_tokens=1024,
            allowed_paths=frozenset({"amount"}),
            extract_pages=parser,
            platform_kill_switch=lambda: False,
        )
        with system_unit_of_work(
            context.runtime, retrieved.principal, request_id="retain-text"
        ) as uow:
            text_id = store_document_text(
                uow, retrieved, job_id=context.job_id, job_source_sha256=digest
            )
            assert (
                store_document_text(uow, retrieved, job_id=context.job_id, job_source_sha256=digest)
                == text_id
            )
            intent_id = record_intent(
                uow,
                request=retrieved.prepared.request,
                provider="fake",
                job_id=context.job_id,
                source_sha256=digest,
            )
            uow.commit()
        return context, retrieved, text_id, intent_id

    context, retrieved, text_id, intent_id = start()
    outgoing = retrieved.prepared.pages[1].redaction.text
    offset = outgoing.index("120.00")
    raw = json.dumps(
        [
            {
                "path": "amount",
                "value": "120.00",
                "confidence": 0.72,
                "citation": {
                    "ref_type": "document",
                    "ref_id": str(source["id"]),
                    "page": 1,
                    "char_start": offset,
                    "char_end": offset + 6,
                },
            }
        ]
    )

    def response(text: str, stop: str = "end_turn") -> AIResponse:
        return AIResponse(
            text,
            sha256(text.encode()).hexdigest(),
            40,
            20,
            1,
            retrieved.prepared.request.model,
            stop,
        )

    with system_unit_of_work(
        context.runtime, retrieved.principal, request_id="extraction-success"
    ) as uow:
        # Caller-side offset maps cannot replace the maps rebuilt from immutable retained pages.
        proposed = record_extraction(
            uow,
            prepared=replace(retrieved.prepared, pages={}),
            document_text_file_id=text_id,
            source_sha256=retrieved.source_sha256,
            response=response(raw),
            provider="fake",
            job_id=context.job_id,
            job_source_sha256=digest,
            intent_id=intent_id,
        )
        uow.commit()
    failed_ids = []
    for body, stop, code in (
        ('[{"path":"amount"}]', "end_turn", "AI_INVALID_EXTRACTION_FIELD"),
        ("", "refusal", "AI_REFUSAL"),
    ):
        ctx, item, text_file, intent = start()
        with system_unit_of_work(
            ctx.runtime, item.principal, request_id="extraction-invalid"
        ) as uow:
            failed_id = record_extraction(
                uow,
                prepared=item.prepared,
                document_text_file_id=text_file,
                source_sha256=item.source_sha256,
                response=response(body, stop),
                provider="fake",
                job_id=ctx.job_id,
                job_source_sha256=digest,
                intent_id=intent,
            )
            uow.commit()
        failed_ids.append((failed_id, code))
    ctx, item, text_file, intent = start()

    def write(
        *,
        wrong_text: UUID | None = None,
        wrong_intent: UUID | None = None,
        wrong_request: bool = False,
    ) -> UUID:
        with system_unit_of_work(
            ctx.runtime, item.principal, request_id="extraction-rollback"
        ) as uow:
            record_extraction(
                uow,
                prepared=replace(item.prepared, allowed_paths=frozenset({"unapproved"}))
                if wrong_request
                else item.prepared,
                document_text_file_id=text_file if wrong_text is None else wrong_text,
                source_sha256=item.source_sha256,
                response=response(raw),
                provider="fake",
                job_id=ctx.job_id,
                job_source_sha256=digest,
                intent_id=intent if wrong_intent is None else wrong_intent,
            )
            raise RuntimeError("rollback extraction")

    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        write(wrong_text=text_id)
    with pytest.raises(ProposalEvidenceRefused, match="AI_INVALID_INTENT_BINDING"):
        write(wrong_intent=intent_id)
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        write(wrong_request=True)
    with pytest.raises(ProposalEvidenceRefused, match="AI_PROPOSAL_SCOPE_REQUIRED"):
        with system_unit_of_work(
            ctx.runtime,
            replace(item.principal, permissions=frozenset()),
            request_id="extraction-denied",
        ) as uow:
            record_extraction(
                uow,
                prepared=item.prepared,
                document_text_file_id=text_file,
                source_sha256=item.source_sha256,
                response=response(raw),
                provider="fake",
                job_id=ctx.job_id,
                job_source_sha256=digest,
                intent_id=intent,
            )
    with pytest.raises(RuntimeError, match="rollback extraction"):
        write()
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        rows = {row["id"]: row for row in session.execute(select(ai_proposal)).mappings()}
        success = rows[proposed]
        assert len(rows) == 3 and success["kind"] == "CONTRACT_EXTRACTION"
        assert (
            success["file_object_id"] == source["id"]
            and success["document_text_file_id"] == text_id
        )
        (field,) = success["content"]
        assert field["check"] is True and field["confidence"] == "0.72"
        assert field["value"] == "120.00"
        assert field["citation"]["char_start"] == original.index("120.00")
        assert success["citations"] == [field["citation"]]
        assert (success["expires_at"] - success["created_at"]).days == 30
        for failed_id, code in failed_ids:
            assert rows[failed_id]["status"] == "failed"
            assert rows[failed_id]["content"] == rows[failed_id]["citations"] == []
            assert rows[failed_id]["problem"] == {"code": code}
        text_row, stream = open_file(
            session, text_id, files=world.app.state.file_store, keyring=keyring
        )
        with stream:
            kept = json.loads(stream.read())
        assert kept["pages"] == [original] and kept["source_sha256"] == source["sha256"]
        with world.app.state.file_store.open(text_row["storage_key"]) as encrypted:
            assert original.encode() not in encrypted.read()
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 3
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 4
        assert session.scalar(select(func.count()).select_from(contract_version)) == 0
        events = list(
            session.execute(
                select(audit_event).where(
                    audit_event.c.action.in_(["ai_proposal.create", "ai_document_text.create"])
                )
            ).mappings()
        )
        assert len(events) == 7
        assert all(
            event["actor_id"] == world.maya.member.user_id and event["actor_kind"] == "USER"
            for event in events
        )
        assert "buyer@example.com" not in json.dumps([dict(event) for event in events], default=str)
        assert (
            session.scalar(
                select(func.count())
                .select_from(file_object)
                .where(file_object.c.purpose == "AI_DOCUMENT_TEXT")
            )
            == 4
        )
