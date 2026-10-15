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
    role_assignment,
    tenant,
)
from erev_api.domain.ai.access import AIAccessRefused
from erev_api.domain.ai.attempts import AttemptEvidenceRefused, record_attempt, record_intent
from erev_api.domain.ai.document_retrieval import RetrievedExtraction, retrieve_document
from erev_api.domain.ai.extraction_proposals import (
    record_extraction,
    record_extraction_failure,
    store_document_text,
)
from erev_api.domain.ai.extraction_recovery import RecoveredExtraction, recover_extraction
from erev_api.domain.ai.ports import AIResponse, AIUsage
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import ProposalEvidenceRefused
from erev_api.domain.platform import file_evidence
from erev_api.enums import FilePurpose, RegistryCategory
from erev_api.files.store import open_file, store_file
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import func, select, update
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

    def recover(
        context: JobContext,
        *,
        paths: frozenset[str] = frozenset({"amount"}),
        fingerprint: str = digest,
        file_digest: str = str(source["sha256"]),
    ) -> RecoveredExtraction | None:
        return recover_extraction(
            context,
            document_id=source["id"],
            source_sha256=file_digest,
            job_source_sha256=fingerprint,
            allowed_paths=paths,
            max_tokens=1024,
            provider="fake",
        )

    def start() -> tuple[JobContext, RetrievedExtraction, UUID, UUID]:
        base = context_for(world.maya.member, clock)
        context = JobContext(
            job_id=base.job_id,
            tenant_id=base.tenant_id,
            kind=base.kind,
            principal=base.principal,
            runtime=replace(base.runtime, keyring=keyring, files=world.app.state.file_store),
        )
        assert recover(context) is None
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
            for source_id, derived_id in ((None, text_id), (source["id"], source["id"])):
                with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_DOCUMENT_BINDING"):
                    record_intent(
                        uow,
                        request=retrieved.prepared.request,
                        provider="fake",
                        job_id=context.job_id,
                        source_sha256=digest,
                        file_object_id=source_id,
                        document_text_file_id=derived_id,
                    )
            intent_id = record_intent(
                uow,
                request=retrieved.prepared.request,
                provider="fake",
                job_id=context.job_id,
                source_sha256=digest,
                file_object_id=source["id"],
                document_text_file_id=text_id,
            )
            uow.commit()
        # The committed intent protects provenance even before a proposal/outcome exists.
        for evidence_id, column in (
            (source["id"], "file_object_id"),
            (text_id, "document_text_file_id"),
        ):
            assert any(
                hold.held_by == f"ai_call_intent.{column}"
                and hold.row_id == intent_id
                and hold.reference.approval
                and hold.entity_ids is None
                for hold in file_evidence.holds(world.place.tenant_id, evidence_id)
            )
        with pytest.raises(AttemptEvidenceRefused, match="AI_OUTCOME_UNKNOWN"):
            recover(context)
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
    restored = recover(context)
    assert restored is not None and restored.proposal_id == proposed and restored.failure is None
    assert restored.prepared == retrieved.prepared and restored.text_id == text_id
    assert restored.principal.id == world.maya.member.user_id
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        recover(context, paths=frozenset({"other"}))
    with pytest.raises(PreparationRefused, match="AI_JOB_INPUT_CHANGED"):
        recover(context, fingerprint="0" * 64)
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_UNAVAILABLE"):
        recover(context, file_digest="0" * 64)
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
    for failure_code, usage in (("AI_TIMEOUT", None), ("AI_PERMISSION", AIUsage(12, 3))):
        failed_ctx, failed_item, failed_text, failed_intent = start()
        with system_unit_of_work(
            failed_ctx.runtime, failed_item.principal, request_id="provider-failure-log"
        ) as uow:
            failure_log = record_attempt(
                uow,
                request=failed_item.prepared.request,
                provider="fake",
                outcome="TIMEOUT" if failure_code == "AI_TIMEOUT" else "ERROR",
                failure="timeout" if failure_code == "AI_TIMEOUT" else "provider_error",
                intent_id=failed_intent,
                provider_failure_code=failure_code,
                provider_retryable=failure_code == "AI_TIMEOUT",
                usage=usage,
            )
            uow.commit()

        recovered = recover(failed_ctx)
        assert recovered is not None and recovered.proposal_id is None
        assert recovered.prepared == failed_item.prepared
        assert recovered.intent_id == failed_intent and recovered.log_id == failure_log
        assert recovered.attempt_no == 1 and recovered.failure is not None
        assert recovered.failure.code == failure_code and recovered.failure.usage == usage
        assert recovered.failure.retryable is (failure_code == "AI_TIMEOUT")
        with pytest.raises(AttemptEvidenceRefused, match="AI_JOB_INPUT_CHANGED"):
            with system_unit_of_work(
                failed_ctx.runtime, failed_item.principal, request_id="retry-drops-documents"
            ) as uow:
                record_intent(
                    uow,
                    request=failed_item.prepared.request,
                    provider="fake",
                    job_id=failed_ctx.job_id,
                    source_sha256=digest,
                )

        def finalize(
            *,
            failed_ctx: JobContext = failed_ctx,
            failed_item: RetrievedExtraction = failed_item,
            failed_text: UUID = failed_text,
            selected_log: UUID = failure_log,
            code: str = failure_code,
            rollback: bool = False,
        ) -> UUID:
            with system_unit_of_work(
                failed_ctx.runtime, failed_item.principal, request_id="provider-failure-proposal"
            ) as uow:
                proposal = record_extraction_failure(
                    uow,
                    prepared=failed_item.prepared,
                    document_text_file_id=failed_text,
                    source_sha256=failed_item.source_sha256,
                    log_id=selected_log,
                    provider="fake",
                    code=code,
                    job_id=failed_ctx.job_id,
                    job_source_sha256=digest,
                )
                if rollback:
                    raise RuntimeError("rollback failure proposal")
                uow.commit()
                return proposal

        with pytest.raises(ProposalEvidenceRefused, match="AI_INVALID_PROVIDER_FAILURE"):
            finalize(code="untrusted provider message")
        with pytest.raises(ProposalEvidenceRefused, match="AI_ATTEMPT_EVIDENCE_MISMATCH"):
            finalize(code="AI_BAD_REQUEST")
        with tenant_session(world.place.principal.db_context, read_only=True) as session:
            other_log = session.scalar(
                select(ai_proposal.c.ai_model_log_id).where(ai_proposal.c.id == proposed)
            )
            assert other_log is not None
            before = dict(
                session.execute(select(ai_model_log).where(ai_model_log.c.id == failure_log))
                .mappings()
                .one()
            )
        with pytest.raises(ProposalEvidenceRefused, match="AI_ATTEMPT_EVIDENCE_MISMATCH"):
            finalize(selected_log=other_log)
        with system_unit_of_work(
            failed_ctx.runtime, failed_item.principal, request_id="unbound-failure-log"
        ) as uow:
            unbound_log = record_attempt(
                uow,
                request=failed_item.prepared.request,
                provider="fake",
                outcome="TIMEOUT" if failure_code == "AI_TIMEOUT" else "ERROR",
                failure="timeout" if failure_code == "AI_TIMEOUT" else "provider_error",
                provider_failure_code=failure_code,
                usage=usage,
            )
            uow.commit()
        with pytest.raises(ProposalEvidenceRefused, match="AI_INVALID_INTENT_BINDING"):
            finalize(selected_log=unbound_log)
        with pytest.raises(RuntimeError, match="rollback failure proposal"):
            finalize(rollback=True)
        with tenant_session(world.place.principal.db_context, read_only=True) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ai_proposal)
                    .where(ai_proposal.c.job_id == failed_ctx.job_id)
                )
                == 0
            )
        failed_ids.append((finalize(), failure_code))
        with tenant_session(world.place.principal.db_context, read_only=True) as session:
            after = dict(
                session.execute(select(ai_model_log).where(ai_model_log.c.id == failure_log))
                .mappings()
                .one()
            )
            assert after == before
            assert after["parameters"]["usage_evidence"] == (
                "UNKNOWN" if usage is None else "REPORTED"
            )
            assert (after["input_tokens"], after["output_tokens"]) == (
                (0, 0) if usage is None else (12, 3)
            )
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
    with system_unit_of_work(ctx.runtime, item.principal, request_id="invalidated-response") as uow:
        record_attempt(
            uow,
            request=item.prepared.request,
            provider="fake",
            outcome="ERROR",
            failure="invalid_output",
            response=response(raw),
            intent_id=intent,
        )
        uow.commit()
    with pytest.raises(AttemptEvidenceRefused, match="AI_RECOVERY_REQUIRED"):
        recover(ctx)
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        rows = {row["id"]: row for row in session.execute(select(ai_proposal)).mappings()}
        success = rows[proposed]
        assert len(rows) == 5 and success["kind"] == "CONTRACT_EXTRACTION"
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
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 8
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 6
        assert session.scalar(select(func.count()).select_from(contract_version)) == 0
        events = list(
            session.execute(
                select(audit_event).where(
                    audit_event.c.action.in_(["ai_proposal.create", "ai_document_text.create"])
                )
            ).mappings()
        )
        assert len(events) == 11
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
            == 6
        )

    # Evidence reads remain available after disabling new AI calls, without new attempts/logs.
    with tenant_session(world.place.principal.db_context) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.place.tenant_id)
            .values(
                ai_disabled_at=clock.now(),
                ai_disabled_by=world.maya.member.user_id,
                ai_disabled_by_kind="USER",
            )
        )
    disabled_result = recover(context)
    assert disabled_result is not None and disabled_result.proposal_id == proposed
    with tenant_session(world.place.principal.db_context) as session:
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 6
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 8
        session.execute(
            update(role_assignment)
            .where(role_assignment.c.membership_id == world.maya.member.membership_id)
            .values(
                revoked_at=clock.now(), revoked_by=world.maya.member.user_id, revoked_by_kind="USER"
            )
        )
    with pytest.raises(AIAccessRefused, match="AI_PERMISSION_DENIED"):
        recover(context)
