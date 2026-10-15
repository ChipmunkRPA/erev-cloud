"""Model output is evidence to validate, not instructions or accepted contract fields."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.ai.extraction_validation import OutputRefused, validate_extraction
from erev_api.domain.ai.ports import AIResponse

DOC = UUID("00000000-0000-0000-0000-000000000001")
PAGES = {1: "Café costs 120.00."}
PATHS = frozenset({"customer_name", "amount", "payment_terms"})


def field(**changes: Any) -> dict[str, Any]:
    return {
        "path": "customer_name",
        "value": "Café",
        "confidence": 0.97,
        "citation": {
            "ref_type": "document",
            "ref_id": str(DOC),
            "page": 1,
            "char_start": 0,
            "char_end": 4,
        },
        **changes,
    }


def response(raw: str) -> AIResponse:
    return AIResponse(raw, sha256(raw.encode()).hexdigest(), 100, 50, 1, "test-model", "end_turn")


def validate(value: Any) -> Any:
    return validate_extraction(
        response(json.dumps(value)), document_id=DOC, pages=PAGES, allowed_paths=PATHS
    )


def test_valid_fields_preserve_values_and_citations() -> None:
    (item,) = validate([field(value={"amount": "120.00", "currency": "USD"})])
    content = item.as_content()
    assert content["value"] == {"amount": "120.00", "currency": "USD"}
    assert content["confidence"] == "0.97"
    assert not item.check
    assert PAGES[item.citation.page][item.citation.char_start : item.citation.char_end] == "Café"
    content["value"]["amount"] = "changed"
    assert item.as_content()["value"]["amount"] == "120.00"


@pytest.mark.parametrize(
    ("confidence", "check"), [(0, True), (0.7499, True), (0.75, False), (1, False)]
)
def test_low_confidence_flagged(confidence: float, check: bool) -> None:
    assert validate([field(confidence=confidence)])[0].check is check


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "0.97", None])
def test_invalid_confidence_refused(confidence: Any) -> None:
    with pytest.raises(OutputRefused, match="AI_INVALID_CONFIDENCE"):
        validate([field(confidence=confidence)])


def test_uncited_field_rejected() -> None:
    item = field()
    del item["citation"]
    with pytest.raises(OutputRefused, match="AI_INVALID_EXTRACTION_FIELD"):
        validate([item])


@pytest.mark.parametrize(
    "changes",
    [
        {"ref_id": str(UUID(int=2))},
        {"ref_type": "record"},
        {"page": 2},
        {"page": 0},
        {"page": True},
        {"char_start": -1},
        {"char_end": 100},
        {"char_end": 0},
        {"char_start": 4, "char_end": 3},
        {"char_end": 1.5},
    ],
)
def test_invalid_citations_refused(changes: dict[str, Any]) -> None:
    item = field()
    item["citation"].update(changes)
    with pytest.raises(OutputRefused, match="AI_INVALID_CITATION"):
        validate([item])


def test_paths_come_from_trusted_schema_and_are_unique() -> None:
    for values in ([field(path="contract.activate")], [field(), field()]):
        with pytest.raises(OutputRefused, match="AI_INVALID_FIELD_PATH"):
            validate(values)


@pytest.mark.parametrize(
    "raw", ["[]", "{}", "```json\n[]\n```", "[", "[NaN]", "[Infinity]", '[{"path":"a","path":"b"}]']
)
def test_malformed_output_never_becomes_a_partial_proposal(raw: str) -> None:
    with pytest.raises(OutputRefused):
        validate_extraction(response(raw), document_id=DOC, pages=PAGES, allowed_paths=PATHS)


def test_refusal_incomplete_and_hash_mismatch() -> None:
    original = response(json.dumps([field()]))
    for invalid, code in (
        (replace(original, stop_reason="refusal"), "AI_REFUSAL"),
        (replace(original, stop_reason="max_tokens"), "AI_INCOMPLETE_RESPONSE"),
        (replace(original, response_sha256="0" * 64), "AI_RESPONSE_HASH_MISMATCH"),
    ):
        with pytest.raises(OutputRefused, match=code):
            validate_extraction(invalid, document_id=DOC, pages=PAGES, allowed_paths=PATHS)


def test_errors_do_not_contain_model_text() -> None:
    with pytest.raises(OutputRefused) as caught:
        validate_extraction(
            response("Sensitive invalid document"),
            document_id=DOC,
            pages=PAGES,
            allowed_paths=PATHS,
        )
    assert str(caught.value) == "AI_INVALID_JSON"
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("token", ["1e999999999", "1e-999999999", "0e999999999"])
def test_decimal_expansion_is_bounded_before_canonical_encoding(token: str) -> None:
    raw = json.dumps([field(value="NUMBER")]).replace('"NUMBER"', token)
    with pytest.raises(OutputRefused, match="AI_NUMBER_TOO_LARGE"):
        validate_extraction(response(raw), document_id=DOC, pages=PAGES, allowed_paths=PATHS)


def test_numeric_expansion_budget_is_shared_across_fields() -> None:
    raw = json.dumps([field(value=["NUMBER"] * 3)]).replace('"NUMBER"', "1e1000000")
    with pytest.raises(OutputRefused, match="AI_NUMBER_TOO_LARGE"):
        validate_extraction(response(raw), document_id=DOC, pages=PAGES, allowed_paths=PATHS)


def test_a_valid_field_does_not_allow_a_later_uncited_field() -> None:
    with pytest.raises(OutputRefused, match="AI_INVALID_CITATION"):
        validate([field(), field(path="amount", citation=None)])


def test_large_and_deep_responses_are_refused() -> None:
    for raw, code in (
        (" " * (2 * 1024 * 1024 + 1), "AI_RESPONSE_TOO_LARGE"),
        ("[" * 10000 + "0" + "]" * 10000, "AI_INVALID_JSON"),
    ):
        with pytest.raises(OutputRefused, match=code):
            validate_extraction(response(raw), document_id=DOC, pages=PAGES, allowed_paths=PATHS)


def test_escaped_unpaired_surrogate_value_is_refused() -> None:
    with pytest.raises(OutputRefused, match="AI_INVALID_FIELD_VALUE"):
        validate([field(value="\ud800")])


def test_decimal_values_use_exact_canonical_strings() -> None:
    raw = json.dumps([field(value="NUMBER")]).replace('"NUMBER"', "120.001")
    (item,) = validate_extraction(response(raw), document_id=DOC, pages=PAGES, allowed_paths=PATHS)
    assert item.as_content()["value"] == "120.001"
