"""Draft review requires explicit business inputs and faithful, one-to-one line mappings."""

from copy import deepcopy
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.ai.draft_review import review_draft, review_draft_lines
from erev_api.domain.ai.field_review import FieldReviewRefused
from erev_api.schemas.ai import AIExtractionDraftIn
from pydantic import ValidationError


def payload() -> dict[str, Any]:
    return {
        "command": "contract.create_draft",
        "entity_code": "US",
        "field_decisions": [{"path": "lines.7", "decision": "ACCEPT"}],
        "line_bindings": {"lines.7": "subscription"},
        "draft": {
            "external_id": "ORDER-1",
            "customer_id": str(UUID(int=1)),
            "contracting_entity_code": "US",
            "transaction_currency": "USD",
            "inception_date": "2026-10-15",
            "lines": [
                {
                    "obligation_key": "subscription",
                    "product_code": "P",
                    "quantity": "2",
                    "total_price": {"amount": "120.00", "currency": "USD"},
                }
            ],
        },
    }


def proposed() -> list[dict[str, Any]]:
    return [{"path": "lines.7", "value": {"product_code": "P", "amount": "120.0000"}}]


def test_explicit_mapping_preserves_review_and_draft_inputs() -> None:
    request = AIExtractionDraftIn.model_validate(payload())
    before = request.model_dump()
    result = review_draft_lines(proposed(), request)
    assert result.values["lines.7"] == {"product_code": "P", "amount": "120.0000"}
    assert request.model_dump() == before
    assert request.draft.lines[0].quantity == "2"


@pytest.mark.parametrize(
    "field", ["external_id", "transaction_currency", "inception_date", "contracting_entity_code"]
)
def test_required_contract_inputs_not_inferred(field: str) -> None:
    body = payload()
    del body["draft"][field]
    with pytest.raises(ValidationError):
        AIExtractionDraftIn.model_validate(body)


@pytest.mark.parametrize("field", ["quantity", "obligation_key", "product_code", "total_price"])
def test_required_line_inputs_not_inferred(field: str) -> None:
    body = payload()
    del body["draft"]["lines"][0][field]
    with pytest.raises(ValidationError):
        AIExtractionDraftIn.model_validate(body)


@pytest.mark.parametrize(
    "mutator", ["entity", "activation", "command", "unknown_key", "duplicate_target", "extra"]
)
def test_unsafe_or_ambiguous_request_refused(mutator: str) -> None:
    body = payload()
    if mutator == "entity":
        body["entity_code"] = "OTHER"
    elif mutator == "activation":
        body["draft"]["submit_for_activation"] = True
    elif mutator == "command":
        body["command"] = "contract.activate"
    elif mutator == "unknown_key":
        body["line_bindings"] = {"lines.7": "unknown"}
    elif mutator == "duplicate_target":
        body["line_bindings"]["lines.8"] = "subscription"
    else:
        body["approve"] = True
    with pytest.raises(ValidationError):
        AIExtractionDraftIn.model_validate(body)


@pytest.mark.parametrize(
    "bindings", [{}, {"lines.8": "subscription"}, {"customer_name": "subscription"}]
)
def test_exact_retained_line_coverage(bindings: dict[str, str]) -> None:
    body = payload()
    body["line_bindings"] = bindings
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_LINE_BINDINGS"):
        review_draft_lines(proposed(), AIExtractionDraftIn.model_validate(body))


@pytest.mark.parametrize(
    "change",
    [
        {"product_code": "OTHER"},
        {"total_price": {"amount": "119.99", "currency": "USD"}},
        {"total_price": {"amount": "-120.00", "currency": "USD"}},
        {"total_price": {"amount": "120.00", "currency": "EUR"}},
    ],
)
def test_draft_cannot_silently_override_reviewed_line(change: dict[str, Any]) -> None:
    body = payload()
    body["draft"]["lines"][0].update(change)
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft_lines(proposed(), AIExtractionDraftIn.model_validate(body))


def test_edit_value_must_match_draft() -> None:
    body = payload()
    body["field_decisions"][0].update(
        decision="EDIT",
        value={"product_code": "P", "amount": "100.00"},
        reason="Correct signed order",
    )
    request = AIExtractionDraftIn.model_validate(body)
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft_lines(proposed(), request)
    body["draft"]["lines"][0]["total_price"]["amount"] = "100.00"
    assert (
        review_draft_lines(proposed(), AIExtractionDraftIn.model_validate(body)).values["lines.7"][
            "amount"
        ]
        == "100.00"
    )


def test_rejected_line_cannot_be_mapped_and_human_lines_need_no_proposal() -> None:
    body = payload()
    body["field_decisions"][0].update(decision="REJECT", reason="Not supported")
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_LINE_BINDINGS"):
        review_draft_lines(proposed(), AIExtractionDraftIn.model_validate(body))
    body["line_bindings"] = {}
    extra = deepcopy(body["draft"]["lines"][0])
    extra["obligation_key"] = "human-added"
    body["draft"]["lines"].append(extra)
    assert review_draft_lines(proposed(), AIExtractionDraftIn.model_validate(body)).values == {}


def header_request(
    path: str, value: Any, target: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = payload()
    fields = proposed() + [{"path": path, "value": value}]
    body["field_decisions"].append({"path": path, "decision": "ACCEPT"})
    body["header_bindings"] = {path: target}
    return fields, body


@pytest.mark.parametrize("target", ["inception_date", "signature_date"])
def test_date_meaning_is_explicit_and_matches_draft(target: str) -> None:
    fields, body = header_request("effective_date", "2026-10-15", target)
    body["draft"][target] = "2026-10-15"
    request = AIExtractionDraftIn.model_validate(body)
    assert review_draft(fields, request).values["effective_date"] == "2026-10-15"
    body["draft"][target] = "2026-10-16"
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


def test_missing_signature_date_is_not_filled_from_proposal() -> None:
    fields, body = header_request("effective_date", "2026-10-15", "signature_date")
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


def test_payment_terms_must_be_exactly_reviewed_text() -> None:
    fields, body = header_request("payment_terms", "Net 30", "payment_terms")
    body["draft"]["payment_terms"] = "Net 30"
    assert (
        review_draft(fields, AIExtractionDraftIn.model_validate(body)).values["payment_terms"]
        == "Net 30"
    )
    body["draft"]["payment_terms"] = "Net 60"
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


def test_existing_customer_requires_matching_id_and_exact_resolved_name() -> None:
    fields, body = header_request("customer_name", "Example Customer", "customer")
    request = AIExtractionDraftIn.model_validate(body)
    for customer in (None, (UUID(int=2), "Example Customer")):
        with pytest.raises(FieldReviewRefused, match="AI_REVIEW_CUSTOMER_UNRESOLVED"):
            review_draft(fields, request, resolved_customer=customer)
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft(fields, request, resolved_customer=(UUID(int=1), "Other Customer"))
    result = review_draft(fields, request, resolved_customer=(UUID(int=1), "Example Customer"))
    assert result.values["customer_name"] == "Example Customer"


def test_inline_customer_reference_uses_explicit_name() -> None:
    fields, body = header_request("customer_name", "Example Customer", "customer")
    del body["draft"]["customer_id"]
    body["draft"]["customer"] = {"code": "C-1", "name": "Example Customer"}
    assert (
        review_draft(fields, AIExtractionDraftIn.model_validate(body)).values["customer_name"]
        == "Example Customer"
    )
    body["draft"]["customer"]["name"] = "Other Customer"
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_DRAFT_MISMATCH"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


@pytest.mark.parametrize(
    "bindings", [{}, {"customer_name": "customer"}, {"payment_terms": "signature_date"}]
)
def test_missing_extra_or_wrong_header_mapping_refused(bindings: dict[str, str]) -> None:
    fields, body = header_request("payment_terms", "Net 30", "payment_terms")
    body["header_bindings"] = bindings
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_HEADER_BINDINGS"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


@pytest.mark.parametrize(
    "path,value",
    [
        ("term_months", 12),
        ("termination", "Either party may terminate"),
        ("variable_consideration_terms", "Volume discount"),
        ("material_right_indicator", "Discount renewal option"),
    ],
)
def test_unimplemented_structured_terms_are_never_silently_dropped(path: str, value: Any) -> None:
    fields, body = header_request(path, value, "payment_terms")
    body["header_bindings"] = {}
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_HEADER_BINDINGS"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))


def test_rejected_header_cannot_be_bound() -> None:
    fields, body = header_request("payment_terms", "Net 30", "payment_terms")
    body["field_decisions"][-1].update(decision="REJECT", reason="Incorrect terms")
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_HEADER_BINDINGS"):
        review_draft(fields, AIExtractionDraftIn.model_validate(body))
    body["header_bindings"] = {}
    assert (
        "payment_terms" not in review_draft(fields, AIExtractionDraftIn.model_validate(body)).values
    )


def test_request_round_trip_preserves_omitted_replacement_values() -> None:
    fields, body = header_request("effective_date", "2026-10-15", "inception_date")
    request = AIExtractionDraftIn.model_validate(body)
    restored = AIExtractionDraftIn.model_validate_json(request.model_dump_json(exclude_unset=True))
    assert review_draft(fields, request) == review_draft(fields, restored)
