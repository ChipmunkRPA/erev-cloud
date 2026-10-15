"""Worker-only document retrieval and extraction with current human source access."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.tables import tenant
from erev_api.domain.ai.access import authorize_job, require_not_cancelled
from erev_api.domain.ai.document_preparation import (
    MAX_PDF_BYTES,
    PreparedExtraction,
    prepare_extraction,
)
from erev_api.domain.ai.ports import DocumentExtractor
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.settings import AISettings, load_settings
from erev_api.domain.platform import attachments
from erev_api.enums import FilePurpose, TenantKind
from erev_api.jobs.context import JobContext
from erev_api.problems import Problem


@dataclass(frozen=True, slots=True)
class RetrievedExtraction:
    principal: Principal
    prepared: PreparedExtraction
    pages: tuple[str, ...]
    source_sha256: str


def _admit(
    context: JobContext, platform_kill_switch: Callable[[], bool]
) -> tuple[RequestContext, AISettings]:
    require_not_cancelled(context)
    with context.read_session() as session:
        principal = authorize_job(context, session)
        settings = load_settings(
            session,
            tenant_id=context.tenant_id,
            now=context.clock.now(),
            platform_kill_switch=platform_kill_switch(),
        )
        kind = session.execute(
            select(tenant.c.kind).where(tenant.c.id == context.tenant_id)
        ).scalar_one()
    settings.require_available()
    if not settings.send_contract_text:
        raise PreparationRefused("AI_TEXT_DISABLED")
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind(kind),
        request_id=f"ai-document-{context.job_id}",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=context.clock.now(),
        format_locale="en-US",
    ), settings


def _source(ctx: RequestContext, file_id: UUID) -> Mapping[str, Any]:
    row = attachments.get_file(ctx, file_id)
    if row["purpose"] != FilePurpose.ATTACHMENT.value or row["shredded_at"] is not None:
        raise Problem("not-found")
    if row["media_type"] != "application/pdf":
        raise PreparationRefused("AI_INVALID_PDF")
    if row["size_bytes"] > MAX_PDF_BYTES:
        raise PreparationRefused("AI_DOCUMENT_FILE_LIMIT")
    return row


def retrieve_document(
    context: JobContext,
    *,
    file_id: UUID,
    allowed_paths: frozenset[str],
    max_tokens: int,
    extract_pages: DocumentExtractor,
    platform_kill_switch: Callable[[], bool],
    expected_file_sha256: str | None = None,
) -> RetrievedExtraction:
    """Read no bytes before consent/access checks; never hold SQL transactions while parsing.

    The composition root supplies the isolated parser. This prepares input only: the gateway
    still owns token admission, committed call intent, durable text/proposal evidence and retries.
    """
    ctx, settings = _admit(context, platform_kill_switch)
    row = _source(ctx, file_id)
    digest = str(row["sha256"]).strip()
    if expected_file_sha256 is not None and digest != expected_file_sha256:
        raise PreparationRefused("AI_INPUT_CHANGED")
    files, keyring = context.runtime.files, context.runtime.keyring
    if files is None or keyring is None:
        raise RuntimeError("AI_DOCUMENT_RUNTIME_REQUIRED")
    _, data = attachments.file_content(ctx, file_id, files=files, keyring=keyring)
    if len(data) > MAX_PDF_BYTES:
        raise PreparationRefused("AI_DOCUMENT_FILE_LIMIT")
    if len(data) != row["size_bytes"] or sha256(data).hexdigest() != digest:
        raise PreparationRefused("AI_INPUT_CHANGED")
    context.heartbeat()
    require_not_cancelled(context)
    pages = extract_pages(data, send_contract_text=True)
    context.heartbeat()
    fresh_ctx, fresh_settings = _admit(context, platform_kill_switch)
    fresh_row = _source(fresh_ctx, file_id)
    if fresh_settings != settings or str(fresh_row["sha256"]).strip() != digest:
        raise PreparationRefused("AI_INPUT_CHANGED")
    prepared = prepare_extraction(
        document_id=file_id,
        pages=pages,
        allowed_paths=allowed_paths,
        model=settings.model,
        max_tokens=max_tokens,
        send_contract_text=True,
        redact_contact_details=settings.redact_contact_details,
    )
    return RetrievedExtraction(fresh_ctx.principal, prepared, tuple(pages), digest)
