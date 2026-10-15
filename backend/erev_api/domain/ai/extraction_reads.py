"""Authorized, audited original text for human extraction review; no model calls."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_proposal, file_object
from erev_api.domain.ai.extraction_proposals import MAX_RECORD_BYTES, decode_retained_pages
from erev_api.domain.ai.proposals import ProposalEvidenceRefused
from erev_api.domain.ai.queries import proposal_detail
from erev_api.domain.platform.attachments import file_content
from erev_api.files.store import FileStore
from erev_api.problems import Problem
from erev_api.schemas.ai import AIDocumentPageOut, AIDocumentTextOut, AIExtractionProposalOut


def document_text(
    ctx: RequestContext, proposal_id: UUID, *, files: FileStore, keyring: KeyRing
) -> AIDocumentTextOut:
    proposal = proposal_detail(ctx, proposal_id)
    if not isinstance(proposal, AIExtractionProposalOut):
        raise Problem("not-found")
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        binding = (
            session.execute(
                select(ai_proposal.c.job_id, ai_proposal.c.job_source_sha256, file_object.c.sha256)
                .join(
                    file_object,
                    (file_object.c.id == ai_proposal.c.file_object_id)
                    & (file_object.c.tenant_id == ai_proposal.c.tenant_id),
                )
                .where(
                    ai_proposal.c.id == proposal_id,
                    ai_proposal.c.tenant_id == ctx.principal.tenant_id,
                )
            )
            .mappings()
            .one()
        )
        size = session.scalar(
            select(file_object.c.size_bytes).where(
                file_object.c.id == proposal.document_text_file_id,
                file_object.c.purpose == "AI_DOCUMENT_TEXT",
            )
        )
        if size is None or size > MAX_RECORD_BYTES:
            raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    # The normal file reader rechecks current original-source access through the text owner,
    # handles shredded keys, and commits file.download evidence before returning plaintext.
    row, payload = file_content(ctx, proposal.document_text_file_id, files=files, keyring=keyring)
    if len(payload) != size or sha256(payload).hexdigest() != str(row["sha256"]).strip():
        raise ProposalEvidenceRefused("AI_DOCUMENT_EVIDENCE_MISMATCH")
    pages = decode_retained_pages(
        payload,
        document_id=proposal.file_object_id,
        job_id=binding["job_id"],
        job_source_sha256=binding["job_source_sha256"],
        source_sha256=str(binding["sha256"]).strip(),
    )
    return AIDocumentTextOut(
        proposal_id=proposal.id,
        file_object_id=proposal.file_object_id,
        pages=[AIDocumentPageOut(page_no=index, text=page) for index, page in enumerate(pages, 1)],
    )
