"""Document limits, opt-in and citation binding across the extraction boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.ai.provider import FakeProvider
from erev_api.domain.ai.document_preparation import PreparedExtraction, prepare_extraction
from erev_api.domain.ai.preparation import PreparationRefused

DOC = UUID("00000000-0000-0000-0000-000000000029")


def prepare(**changes: Any) -> PreparedExtraction:
    arguments: dict[str, Any] = {
        "document_id": DOC,
        "pages": ["Contact alice@example.com. Fee: 120.00."],
        "allowed_paths": frozenset({"amount"}),
        "model": "configured-test-model",
        "max_tokens": 1000,
        "send_contract_text": True,
    }
    return prepare_extraction(**(arguments | changes))


def test_preparation_fake_provider_validation_preserves_source_citation(tmp_path: Path) -> None:
    prepared = prepare()
    outgoing = json.loads(prepared.request.messages[0]["content"])
    pages = json.loads(outgoing["contract_text"])
    assert pages == [{"page": 1, "text": "Contact [email]. Fee: 120.00."}]
    assert outgoing["facts"] == {"document_id": str(DOC), "allowed_paths": ["amount"]}
    assert "alice@example.com" not in repr(prepared)
    start = pages[0]["text"].index("120.00")
    fixture = {
        "text": json.dumps(
            [
                {
                    "path": "amount",
                    "value": "120.00",
                    "confidence": 0.72,
                    "citation": {
                        "ref_type": "document",
                        "ref_id": str(DOC),
                        "page": 1,
                        "char_start": start,
                        "char_end": start + 6,
                    },
                }
            ]
        ),
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": 1,
        "stop_reason": "end_turn",
    }
    target = tmp_path / "contract-review/v1" / f"{prepared.request.input_sha256}.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(fixture))
    (field,) = prepared.validate(FakeProvider(tmp_path).complete(prepared.request))
    assert field.as_content()["value"] == "120.00"
    assert field.check
    original = "Contact alice@example.com. Fee: 120.00."
    assert original[field.citation.char_start : field.citation.char_end] == "120.00"
    assert field.citation.char_start == original.index("120.00")


def test_disabled_refuses_before_inspecting_any_pages() -> None:
    with pytest.raises(PreparationRefused, match="AI_TEXT_DISABLED"):
        prepare(send_contract_text=False, pages=None)


@pytest.mark.parametrize("pages", [[], [""] * 601, "a document string"])
def test_page_limits(pages: Any) -> None:
    with pytest.raises(PreparationRefused, match="AI_DOCUMENT_PAGE_LIMIT"):
        prepare(pages=pages)


def test_blank_pages_keep_their_numbers() -> None:
    prepared = prepare(pages=["", "Amount: 120.00", ""])
    pages = json.loads(json.loads(prepared.request.messages[0]["content"])["contract_text"])
    assert pages == [
        {"page": 1, "text": ""},
        {"page": 2, "text": "Amount: 120.00"},
        {"page": 3, "text": ""},
    ]
    assert len(prepare(pages=[""] * 600).pages) == 600


def test_utf8_limit_counts_all_pages_before_redaction() -> None:
    with pytest.raises(PreparationRefused, match="AI_DOCUMENT_TEXT_LIMIT"):
        prepare(pages=["😀" * (256 * 1024), "😀" * (256 * 1024) + "a"])
    prepared = prepare(pages=["a" * (2 * 1024 * 1024)])
    assert len(prepared.pages[1].redaction.text) == 2 * 1024 * 1024


def test_redaction_expansion_also_obeys_text_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from erev_api.domain.ai import document_preparation

    monkeypatch.setattr(document_preparation, "MAX_TEXT_BYTES", 6)
    with pytest.raises(PreparationRefused, match="AI_DOCUMENT_TEXT_LIMIT"):
        prepare(pages=["a@b.co"])


@pytest.mark.parametrize("pages", [[None], ["\ud800"]])
def test_invalid_document_text_refused(pages: Any) -> None:
    with pytest.raises(PreparationRefused, match="AI_INVALID_DOCUMENT_TEXT"):
        prepare(pages=pages)


def test_text_and_maps_do_not_change_when_caller_edits_pages() -> None:
    source = ["Fee: 120.00"]
    prepared = prepare(pages=source)
    source[0] = "Fee: 999.00"
    assert prepared.pages[1].redaction.text == "Fee: 120.00"
    with pytest.raises(TypeError):
        prepared.pages[1] = prepared.pages[1]  # type: ignore[index]


def test_explicit_redaction_disable_retains_identity_mapping_and_binds_configuration() -> None:
    prepared = prepare(redact_contact_details=False)
    assert "alice@example.com" in prepared.request.messages[0]["content"]
    assert prepared.pages[1].original_span(0, 7) == (0, 7)
    assert prepared.request.input_sha256 != prepare().request.input_sha256


def test_contact_bearing_allowed_path_cannot_silently_change() -> None:
    with pytest.raises(PreparationRefused, match="AI_DOCUMENT_PREPARATION_MISMATCH"):
        prepare(allowed_paths=frozenset({"alice@example.com"}))
