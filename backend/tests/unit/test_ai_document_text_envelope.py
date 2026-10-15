"""Retained text may only be served under its original source and job binding."""

from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.ai.extraction_proposals import decode_retained_pages
from erev_api.domain.ai.proposals import ProposalEvidenceRefused
from erev_engine.canonical import canonical_bytes

DOCUMENT = UUID(int=1)
JOB = UUID(int=2)


def decode(payload: bytes) -> tuple[str, ...]:
    return decode_retained_pages(
        payload,
        document_id=DOCUMENT,
        job_id=JOB,
        job_source_sha256="a" * 64,
        source_sha256="b" * 64,
    )


def envelope() -> dict[str, Any]:
    return {
        "version": 1,
        "source_file_id": str(DOCUMENT),
        "job_id": str(JOB),
        "job_source_sha256": "a" * 64,
        "source_sha256": "b" * 64,
        "pages": ["First page", "", "Third page"],
    }


def test_exact_original_pages_and_order() -> None:
    assert decode(canonical_bytes(envelope())) == ("First page", "", "Third page")


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"source_file_id": str(UUID(int=3))},
        {"job_id": str(UUID(int=4))},
        {"job_source_sha256": "c" * 64},
        {"source_sha256": "d" * 64},
        {"extra": "not allowed"},
        {"pages": []},
        {"pages": [1]},
        {"pages": "text"},
        {"pages": [""] * 601},
        {"pages": ["x" * (2 * 1024 * 1024 + 1)]},
    ],
)
def test_mismatched_or_invalid_envelope_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        decode(canonical_bytes(envelope() | change))


@pytest.mark.parametrize("payload", [b"not-json", b"[]", b"{}", b"null"])
def test_malformed_payload_refused(payload: bytes) -> None:
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        decode(payload)


def test_noncanonical_payload_refused() -> None:
    with pytest.raises(ProposalEvidenceRefused, match="AI_DOCUMENT_EVIDENCE_MISMATCH"):
        decode(b" " + canonical_bytes(envelope()))
