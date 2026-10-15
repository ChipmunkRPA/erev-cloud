"""Encrypted extraction text and atomic proposal/call evidence; no accounting writes."""

from __future__ import annotations

import io
import json
from datetime import timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import insert, null, select

from erev_api.audit.writer import record, record_facts
from erev_api.db import new_id
from erev_api.db.tables import ai_proposal, file_object
from erev_api.domain.ai.attempts import record_attempt
from erev_api.domain.ai.document_preparation import (
    MAX_PAGES,
    MAX_TEXT_BYTES,
    PreparedExtraction,
    prepare_extraction,
)
from erev_api.domain.ai.document_retrieval import RetrievedExtraction
from erev_api.domain.ai.extraction_fields import validate_contract_value
from erev_api.domain.ai.extraction_validation import OutputRefused
from erev_api.domain.ai.ports import AIResponse
from erev_api.domain.ai.proposals import (
    ProposalEvidenceRefused,
    require_failure_binding,
    require_intent_binding,
    require_job_binding,
)
from erev_api.domain.platform import file_access
from erev_api.enums import FilePurpose, PrincipalKind
from erev_api.files.store import open_file, put_file
from erev_api.uow import UnitOfWork

# JSON escaping can expand each text character to six bytes; pages and metadata are bounded.
MAX_RECORD_BYTES = 6 * MAX_TEXT_BYTES + 65536


def _source(uow: UnitOfWork, file_id: UUID, digest: str) -> None:
    principal = uow.principal
    held = principal.permission_scopes.get("ai.use", frozenset())
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
        or not held
        or (
            held != "*"
            and (principal.entity_scope == "*" or not set(principal.entity_scope).issubset(held))
        )
    ):
        raise ProposalEvidenceRefused("AI_PROPOSAL_SCOPE_REQUIRED")
    row = file_access.bound(uow.session, uow.ctx, file_id)
    if (
        row is None
        or row["purpose"] != FilePurpose.ATTACHMENT.value
        or row["media_type"] != "application/pdf"
        or row["shredded_at"] is not None
        or str(row["sha256"]).strip() != digest
    ):
        raise ProposalEvidenceRefused("AI_DOCUMENT_UNAVAILABLE")


def _rebuild(prepared: PreparedExtraction, pages: tuple[str, ...]) -> PreparedExtraction:
    rebuilt = prepare_extraction(
        document_id=prepared.document_id,
        pages=pages,
        allowed_paths=prepared.allowed_paths,
        model=prepared.request.model,
        max_tokens=prepared.request.max_tokens,
        send_contract_text=True,
        redact_contact_details=prepared.request.parameters["redact_contact_details"],
        template_version=prepared.request.template_version,
    )
    if rebuilt.request != prepared.request:
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    return rebuilt


def store_document_text(
    uow: UnitOfWork, retrieved: RetrievedExtraction, *, job_id: UUID, job_source_sha256: str
) -> UUID:
    """Retain original pages before a call; caller supplies freshly authorized extraction."""
    require_job_binding(uow, job_id, job_source_sha256)
    if (
        retrieved.principal.id != uow.principal.id
        or retrieved.principal.tenant_id != uow.principal.tenant_id
    ):
        raise ProposalEvidenceRefused("AI_PROPOSAL_USER_REQUIRED")
    _source(uow, retrieved.prepared.document_id, retrieved.source_sha256)
    _rebuild(retrieved.prepared, retrieved.pages)
    payload = canonical_bytes(
        {
            "version": 1,
            "job_id": str(job_id),
            "job_source_sha256": job_source_sha256,
            "source_file_id": str(retrieved.prepared.document_id),
            "source_sha256": retrieved.source_sha256,
            "pages": list(retrieved.pages),
        }
    )
    stored = put_file(
        uow,
        purpose=FilePurpose.AI_DOCUMENT_TEXT,
        stream=io.BytesIO(payload),
        original_filename=None,
        media_type="application/json",
    )
    if stored.created:
        record_facts(
            uow,
            action="ai_document_text.create",
            object_type="file_object",
            ids=[stored.row["id"]],
            detail={
                "job_id": str(job_id),
                "source_file_id": str(retrieved.prepared.document_id),
                "sha256": str(stored.row["sha256"]),
            },
        )
    return UUID(str(stored.row["id"]))


def _retained_pages(
    uow: UnitOfWork,
    document_id: UUID,
    text_id: UUID,
    *,
    job_id: UUID,
    job_source_sha256: str,
    source_sha256: str,
) -> tuple[str, ...]:
    _source(uow, document_id, source_sha256)
    row = (
        uow.session.execute(
            select(file_object).where(
                file_object.c.tenant_id == uow.principal.tenant_id,
                file_object.c.id == text_id,
                file_object.c.purpose == FilePurpose.AI_DOCUMENT_TEXT.value,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["size_bytes"] > MAX_RECORD_BYTES:
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    _, stream = open_file(uow.session, text_id, files=uow.files, keyring=uow.keyring)
    with stream:
        payload = stream.read(MAX_RECORD_BYTES + 1)
    if (
        len(payload) != row["size_bytes"]
        or sha256(payload).hexdigest() != str(row["sha256"]).strip()
    ):
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    return decode_retained_pages(
        payload,
        document_id=document_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        source_sha256=source_sha256,
    )


def decode_retained_pages(
    payload: bytes,
    *,
    document_id: UUID,
    job_id: UUID,
    job_source_sha256: str,
    source_sha256: str,
) -> tuple[str, ...]:
    """Validate the canonical text envelope against its immutable source/job bindings."""
    if len(payload) > MAX_RECORD_BYTES:
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    try:
        document = json.loads(payload)
        expected = {
            "version": 1,
            "job_id": str(job_id),
            "job_source_sha256": job_source_sha256,
            "source_file_id": str(document_id),
            "source_sha256": source_sha256,
            "pages": document["pages"],
        }
        if (
            document != expected
            or type(document["version"]) is not int
            or canonical_bytes(document) != payload
            or not isinstance(document["pages"], list)
            or any(not isinstance(page, str) for page in document["pages"])
        ):
            raise ValueError("invalid retained text")
    except (ValueError, KeyError, TypeError, RecursionError):
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH") from None
    pages = document["pages"]
    if (
        not pages
        or len(pages) > MAX_PAGES
        or sum(len(page.encode("utf-8")) for page in pages) > MAX_TEXT_BYTES
    ):
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    return tuple(pages)


def _retained(
    uow: UnitOfWork,
    prepared: PreparedExtraction,
    text_id: UUID,
    *,
    job_id: UUID,
    job_source_sha256: str,
    source_sha256: str,
) -> PreparedExtraction:
    return _rebuild(
        prepared,
        _retained_pages(
            uow,
            prepared.document_id,
            text_id,
            job_id=job_id,
            job_source_sha256=job_source_sha256,
            source_sha256=source_sha256,
        ),
    )


def restore_extraction(
    uow: UnitOfWork,
    *,
    document_id: UUID,
    text_id: UUID,
    source_sha256: str,
    job_id: UUID,
    job_source_sha256: str,
    intent_id: UUID,
    input_sha256: str,
    allowed_paths: frozenset[str],
    model: str,
    max_tokens: int,
    redact_contact_details: bool,
    template_version: int,
) -> PreparedExtraction:
    """Rebuild the exact prior request from retained original pages, without parsing a PDF."""
    require_job_binding(uow, job_id, job_source_sha256)
    pages = _retained_pages(
        uow,
        document_id,
        text_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        source_sha256=source_sha256,
    )
    prepared = prepare_extraction(
        document_id=document_id,
        pages=pages,
        allowed_paths=allowed_paths,
        model=model,
        max_tokens=max_tokens,
        send_contract_text=True,
        redact_contact_details=redact_contact_details,
        template_version=template_version,
    )
    if prepared.request.input_sha256 != input_sha256:
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    require_intent_binding(
        uow,
        intent_id,
        job_id,
        job_source_sha256,
        input_sha256,
        file_object_id=document_id,
        document_text_file_id=text_id,
    )
    return prepared


def record_extraction(
    uow: UnitOfWork,
    *,
    prepared: PreparedExtraction,
    document_text_file_id: UUID,
    source_sha256: str,
    response: AIResponse,
    provider: Literal["fake", "anthropic"],
    job_id: UUID,
    job_source_sha256: str,
    intent_id: UUID,
) -> UUID:
    """Rebuild from retained text and bind the committed call intent before persisting output.

    Caller owns fresh settings/source authorization, budget admission and commit. Invalid or
    uncited output becomes a failed proposal with no provider text retained in content/audit.
    """
    require_job_binding(uow, job_id, job_source_sha256)
    rebuilt = _retained(
        uow,
        prepared,
        document_text_file_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        source_sha256=source_sha256,
    )
    require_intent_binding(
        uow,
        intent_id,
        job_id,
        job_source_sha256,
        rebuilt.request.input_sha256,
        file_object_id=prepared.document_id,
        document_text_file_id=document_text_file_id,
    )
    problem: str | None = None
    content: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    try:
        fields = rebuilt.validate(response, validate_value=validate_contract_value)
        content = [field.as_content() for field in fields]
        citations = [field.citation.as_json() for field in fields]
    except OutputRefused as error:
        problem = str(error)
    log_id = record_attempt(
        uow,
        request=rebuilt.request,
        intent_id=intent_id,
        response=response,
        provider=provider,
        outcome="SUCCESS" if problem is None else "ERROR",
        failure=None
        if problem is None
        else "refusal"
        if problem == "AI_REFUSAL"
        else "invalid_output",
    )
    return _insert_extraction(
        uow,
        prepared=rebuilt,
        document_text_file_id=document_text_file_id,
        log_id=log_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        content=content,
        citations=citations,
        problem=problem,
    )


def record_extraction_failure(
    uow: UnitOfWork,
    *,
    prepared: PreparedExtraction,
    document_text_file_id: UUID,
    source_sha256: str,
    log_id: UUID,
    provider: Literal["fake", "anthropic"],
    code: str,
    job_id: UUID,
    job_source_sha256: str,
) -> UUID:
    """Finalize a failed extraction from existing attempt evidence without charging again.

    The gateway owns retry exhaustion and fresh admission. This only persists the terminal
    proposal, with retained source provenance and no invented response or token counters.
    """
    require_job_binding(uow, job_id, job_source_sha256)
    rebuilt = _retained(
        uow,
        prepared,
        document_text_file_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        source_sha256=source_sha256,
    )
    intent_id = require_failure_binding(
        uow,
        request=rebuilt.request,
        log_id=log_id,
        provider=provider,
        code=code,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        file_object_id=prepared.document_id,
        document_text_file_id=document_text_file_id,
    )
    if intent_id is None:
        raise ProposalEvidenceRefused("AI_INVALID_INTENT_BINDING")
    return _insert_extraction(
        uow,
        prepared=rebuilt,
        document_text_file_id=document_text_file_id,
        log_id=log_id,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
        content=[],
        citations=[],
        problem=code,
    )


def _insert_extraction(
    uow: UnitOfWork,
    *,
    prepared: PreparedExtraction,
    document_text_file_id: UUID,
    log_id: UUID,
    job_id: UUID,
    job_source_sha256: str,
    content: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    problem: str | None,
) -> UUID:
    proposal_id = new_id()
    status = "proposed" if problem is None else "failed"
    uow.session.execute(
        insert(ai_proposal).values(
            tenant_id=uow.principal.tenant_id,
            id=proposal_id,
            kind="CONTRACT_EXTRACTION",
            job_id=job_id,
            job_source_sha256=job_source_sha256,
            status=status,
            file_object_id=prepared.document_id,
            document_text_file_id=document_text_file_id,
            content=content,
            citations=citations,
            ai_model_log_id=log_id,
            expires_at=uow.now + timedelta(days=30),
            problem=null() if problem is None else {"code": problem},
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind="USER",
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind="USER",
        )
    )
    record(
        uow,
        action="ai_proposal.create",
        object_type="ai_proposal",
        object_id=proposal_id,
        after={"kind": "CONTRACT_EXTRACTION", "status": status},
        detail={
            "source_file_id": str(prepared.document_id),
            "document_text_file_id": str(document_text_file_id),
            "ai_model_log_id": str(log_id),
            "content_sha256": sha256_hex(content),
            "citations_sha256": sha256_hex(citations),
        },
    )
    return proposal_id
