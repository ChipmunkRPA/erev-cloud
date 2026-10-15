"""Validate extraction output before it becomes a proposal (AIA-09; BR-AI-01).

Citations address the retained document text supplied by the authorised gateway.
Bounds establish a valid reference, not semantic support for the proposed value.
Use validate_redacted_extraction when citations address redacted page text.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.domain.ai.ports import AIResponse
from erev_api.privacy.patterns import MappedRedaction

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
LOW_CONFIDENCE = Decimal("0.75")


class OutputRefused(ValueError):
    """Fixed failure code, without model text or parser diagnostics."""


@dataclass(frozen=True, slots=True)
class DocumentCitation:
    document_id: UUID
    page: int
    char_start: int
    char_end: int

    def as_json(self) -> dict[str, Any]:
        return {
            "ref_type": "document",
            "ref_id": str(self.document_id),
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass(frozen=True, slots=True)
class ExtractionField:
    path: str
    # Canonical immutable bytes avoid caller mutation of nested JSON proposal values.
    value_bytes: bytes
    confidence: Decimal
    citation: DocumentCitation

    @property
    def check(self) -> bool:
        return self.confidence < LOW_CONFIDENCE

    def as_content(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "value": json.loads(self.value_bytes),
            "confidence": str(self.confidence),
            "check": self.check,
            "citation": self.citation.as_json(),
        }


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OutputRefused("AI_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise OutputRefused("AI_NONFINITE_NUMBER")


def validate_extraction(
    response: AIResponse,
    *,
    document_id: UUID,
    pages: Mapping[int, str],
    allowed_paths: frozenset[str],
) -> tuple[ExtractionField, ...]:
    """Refuse the entire proposal if any field or citation fails validation.

    ``allowed_paths`` is supplied by the trusted template/command schema, never
    inferred from the model. Page numbers are one-based; offsets are zero-based,
    half-open Python Unicode character spans, matching retained page text.
    """
    if response.stop_reason == "refusal":
        raise OutputRefused("AI_REFUSAL")
    if response.stop_reason != "end_turn":
        raise OutputRefused("AI_INCOMPLETE_RESPONSE")
    try:
        encoded = response.text.encode("utf-8")
    except UnicodeEncodeError:
        raise OutputRefused("AI_INVALID_ENCODING") from None
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise OutputRefused("AI_RESPONSE_TOO_LARGE")
    if sha256(encoded).hexdigest() != response.response_sha256:
        raise OutputRefused("AI_RESPONSE_HASH_MISMATCH")
    # Bound expanded decimal text before canonical encoding can allocate it.
    # A tiny exponent token such as 1e999999999 must not become a huge string.
    numeric_bytes = 0

    def decimal_token(token: str) -> Decimal:
        nonlocal numeric_bytes
        try:
            value = Decimal(token)
        except InvalidOperation:
            raise OutputRefused("AI_INVALID_NUMBER") from None
        _, digits, exponent = value.as_tuple()
        if not isinstance(exponent, int):
            raise OutputRefused("AI_NONFINITE_NUMBER")
        numeric_bytes += len(digits) + abs(exponent) + 3
        if numeric_bytes > MAX_RESPONSE_BYTES:
            raise OutputRefused("AI_NUMBER_TOO_LARGE")
        return value

    try:
        fields = json.loads(
            encoded,
            parse_float=decimal_token,
            parse_constant=_constant,
            object_pairs_hook=_object,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, OutputRefused):
            raise
        raise OutputRefused("AI_INVALID_JSON") from None
    if not isinstance(fields, list) or not fields:
        raise OutputRefused("AI_INVALID_EXTRACTION")
    result: list[ExtractionField] = []
    seen: set[str] = set()
    for field in fields:
        if not isinstance(field, dict) or set(field) != {"path", "value", "confidence", "citation"}:
            raise OutputRefused("AI_INVALID_EXTRACTION_FIELD")
        path = field["path"]
        if not isinstance(path, str) or path not in allowed_paths or path in seen:
            raise OutputRefused("AI_INVALID_FIELD_PATH")
        seen.add(path)
        confidence = field["confidence"]
        if type(confidence) not in (int, Decimal):
            raise OutputRefused("AI_INVALID_CONFIDENCE")
        confidence = Decimal(confidence)
        if not confidence.is_finite() or not Decimal(0) <= confidence <= Decimal(1):
            raise OutputRefused("AI_INVALID_CONFIDENCE")
        citation = field["citation"]
        if not isinstance(citation, dict) or set(citation) != {
            "ref_type",
            "ref_id",
            "page",
            "char_start",
            "char_end",
        }:
            raise OutputRefused("AI_INVALID_CITATION")
        if citation["ref_type"] != "document" or citation["ref_id"] != str(document_id):
            raise OutputRefused("AI_INVALID_CITATION")
        page, start, end = citation["page"], citation["char_start"], citation["char_end"]
        if (
            any(type(value) is not int for value in (page, start, end))
            or page < 1
            or page not in pages
            or not 0 <= start < end <= len(pages[page])
        ):
            raise OutputRefused("AI_INVALID_CITATION_SPAN")
        try:
            value_bytes = canonical_bytes(field["value"])
        except (TypeError, ValueError, RecursionError, UnicodeEncodeError):
            raise OutputRefused("AI_INVALID_FIELD_VALUE") from None
        result.append(
            ExtractionField(
                path=path,
                value_bytes=value_bytes,
                confidence=confidence,
                citation=DocumentCitation(document_id, page, start, end),
            )
        )
    return tuple(result)


def validate_redacted_extraction(
    response: AIResponse,
    *,
    document_id: UUID,
    pages: Mapping[int, MappedRedaction],
    allowed_paths: frozenset[str],
) -> tuple[ExtractionField, ...]:
    """Validate against outgoing pages and restore citations to source coordinates.

    The gateway must retain these exact mappings when preparing the document and
    must use their redacted text for the provider's page inputs. Mappings never
    belong in a provider payload. A single ambiguous span refuses the proposal.
    """
    fields = validate_extraction(
        response,
        document_id=document_id,
        pages={page: mapped.redaction.text for page, mapped in pages.items()},
        allowed_paths=allowed_paths,
    )
    result: list[ExtractionField] = []
    for field in fields:
        citation = field.citation
        try:
            start, end = pages[citation.page].original_span(citation.char_start, citation.char_end)
        except ValueError:
            raise OutputRefused("AI_AMBIGUOUS_CITATION_SPAN") from None
        result.append(replace(field, citation=replace(citation, char_start=start, char_end=end)))
    return tuple(result)
