"""Prepare bounded extraction input and retain its exact citation mapping locally.

The worker still owes authorized file reads, PDF extraction, durable text storage,
job-only execution, budget enforcement and audited attempt/proposal persistence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.domain.ai.extraction_validation import ExtractionField, validate_redacted_extraction
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.ai.preparation import PreparationRefused, prepare_request
from erev_api.domain.ai.templates import load_template
from erev_api.privacy.patterns import MappedRedaction, Redaction, redact_with_offsets

MAX_PAGES = 600
MAX_TEXT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PreparedExtraction:
    request: AIRequest
    document_id: UUID
    pages: Mapping[int, MappedRedaction]
    allowed_paths: frozenset[str]

    def validate(self, response: AIResponse) -> tuple[ExtractionField, ...]:
        return validate_redacted_extraction(
            response,
            document_id=self.document_id,
            pages=self.pages,
            allowed_paths=self.allowed_paths,
        )


def prepare_extraction(
    *,
    document_id: UUID,
    pages: Sequence[str],
    allowed_paths: frozenset[str],
    model: str,
    max_tokens: int,
    send_contract_text: bool,
    redact_contact_details: bool = True,
    template_version: int = 1,
) -> PreparedExtraction:
    """Freeze page text and mappings together before any provider invocation.

    Pages are in document order; empty pages retain their page number. The source
    and redacted text each obey the UTF-8 cap. Provider payloads contain redacted
    text only; removed values and source-offset mappings remain local.
    """
    if not send_contract_text:
        raise PreparationRefused("AI_TEXT_DISABLED")
    if isinstance(pages, str | bytes) or not pages or len(pages) > MAX_PAGES:
        raise PreparationRefused("AI_DOCUMENT_PAGE_LIMIT")
    if not allowed_paths or any(not isinstance(path, str) or not path for path in allowed_paths):
        raise PreparationRefused("AI_INVALID_FIELD_PATHS")
    source_size = 0
    redacted_size = 0
    mapped: dict[int, MappedRedaction] = {}
    for page, text in enumerate(pages, start=1):
        if not isinstance(text, str):
            raise PreparationRefused("AI_INVALID_DOCUMENT_TEXT")
        try:
            source_size += len(text.encode("utf-8"))
        except UnicodeEncodeError:
            raise PreparationRefused("AI_INVALID_DOCUMENT_TEXT") from None
        if source_size > MAX_TEXT_BYTES:
            raise PreparationRefused("AI_DOCUMENT_TEXT_LIMIT")
        value = (
            redact_with_offsets(text)
            if redact_contact_details
            else MappedRedaction(Redaction(text, 0, 0), ())
        )
        redacted_size += len(value.redaction.text.encode("utf-8"))
        if redacted_size > MAX_TEXT_BYTES:
            raise PreparationRefused("AI_DOCUMENT_TEXT_LIMIT")
        mapped[page] = value
    document = [{"page": page, "text": value.redaction.text} for page, value in mapped.items()]
    facts = {"document_id": str(document_id), "allowed_paths": sorted(allowed_paths)}
    request = prepare_request(
        template=load_template("contract-review", template_version),
        model=model,
        max_tokens=max_tokens,
        inputs=facts,
        contract_text=canonical_bytes(document).decode("utf-8"),
        send_contract_text=True,
        redact_contact_details=redact_contact_details,
    )
    # The generic preparer also redacts strings. Fail closed if encoding/context
    # changed that result: citations must address the exact page text sent out.
    outgoing = json.loads(request.messages[0]["content"])
    if json.loads(outgoing["contract_text"]) != document or outgoing["facts"] != facts:
        raise PreparationRefused("AI_DOCUMENT_PREPARATION_MISMATCH")
    return PreparedExtraction(
        request, document_id, MappingProxyType(mapped), frozenset(allowed_paths)
    )
