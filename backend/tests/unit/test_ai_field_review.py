"""Human decisions must cover retained fields exactly without coercing proposed money."""

from decimal import Decimal
from typing import Any

import pytest
from erev_api.domain.ai.field_review import FieldReviewRefused, review_fields
from erev_api.schemas.ai import AIFieldDecisionIn
from pydantic import ValidationError


def decision(path: str, action: str = "ACCEPT", **kwargs: Any) -> AIFieldDecisionIn:
    return AIFieldDecisionIn.model_validate({"path": path, "decision": action, **kwargs})


def test_complete_review_preserves_order_values_and_detaches_mutable_inputs() -> None:
    line = {"product_code": "PLATFORM", "amount": "-120.0000"}
    edited = {"product_code": "SERVICE", "amount": "50.00"}
    proposed: list[dict[str, Any]] = [
        {"path": "customer_name", "value": "Example Customer"},
        {"path": "lines.0", "value": line},
        {"path": "lines.1", "value": line},
        {"path": "termination", "value": "Source termination wording"},
    ]
    result = review_fields(
        proposed,
        [
            decision("termination", "REJECT", reason="  Unsupported clause  "),
            decision("lines.1", "EDIT", value=edited, reason="Corrected from signed order"),
            decision("lines.0"),
            decision("customer_name"),
        ],
    )
    assert list(result.values) == ["customer_name", "lines.0", "lines.1"]
    assert [item["path"] for item in result.decisions] == [item["path"] for item in proposed]
    assert result.values["lines.0"] == line
    assert result.values["lines.1"] == edited
    assert result.decisions[-1] == {
        "path": "termination",
        "decision": "REJECT",
        "reason": "Unsupported clause",
    }
    line["amount"] = "999.00"
    edited["amount"] = "777.00"
    assert result.values["lines.0"]["amount"] == "-120.0000"
    assert result.values["lines.1"]["amount"] == "50.00"
    result.values["lines.0"]["amount"] = "100.00"
    assert result.decisions[1]["value"]["amount"] == "-120.0000"


@pytest.mark.parametrize(
    "choices",
    [
        [],
        [decision("customer_name"), decision("customer_name")],
        [decision("effective_date")],
        [decision("submit_for_activation")],
        [decision("customer_name"), decision("effective_date")],
    ],
)
def test_missing_duplicate_extra_or_unknown_decisions_refused(
    choices: list[AIFieldDecisionIn],
) -> None:
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_FIELD_COVERAGE"):
        review_fields([{"path": "customer_name", "value": "Example"}], choices)


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "EDIT", "reason": "Correction"},
        {"decision": "EDIT", "value": "Replacement"},
        {"decision": "REJECT"},
        {"decision": "REJECT", "reason": "   "},
        {"decision": "REJECT", "reason": "x" * 4001},
        {"decision": "REJECT", "reason": "a\x00b"},
        {"decision": "ACCEPT", "value": None},
        {"decision": "ACCEPT", "value": "Override"},
        {"decision": "REJECT", "reason": "Rejected", "value": "Override"},
        {"decision": "accept"},
        {"decision": "ACCEPT", "submit_for_activation": True},
    ],
)
def test_explicit_decision_shape(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AIFieldDecisionIn.model_validate({"path": "customer_name"} | payload)


@pytest.mark.parametrize(
    "path,original,value",
    [
        ("customer_name", "Example", None),
        ("customer_name", "Example", ""),
        ("effective_date", "2026-10-15", "2026-02-30"),
        ("term_months", 12, "12"),
        ("term_months", 12, True),
        ("term_months", 12, 0),
        ("lines.0", {"product_code": "P", "amount": "1.00"}, {"product_code": "P", "amount": 1}),
        (
            "lines.0",
            {"product_code": "P", "amount": "1.00"},
            {"product_code": "P", "amount": Decimal("1.00")},
        ),
        (
            "lines.0",
            {"product_code": "P", "amount": "1.00"},
            {"product_code": "P", "amount": "1e2"},
        ),
        (
            "lines.0",
            {"product_code": "P", "amount": "1.00"},
            {"product_code": "P", "amount": "1.00", "currency": "USD"},
        ),
    ],
)
def test_typed_edits_fail_without_coercion(path: str, original: Any, value: Any) -> None:
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_INVALID_VALUE"):
        review_fields(
            [{"path": path, "value": original}],
            [decision(path, "EDIT", value=value, reason="Checked signed source")],
        )


@pytest.mark.parametrize(
    "proposed",
    [
        [{"path": "unknown", "value": "value"}],
        [{"path": "customer_name"}],
        [{"path": "term_months", "value": True}],
        [{"path": "customer_name", "value": "Example"}] * 2,
    ],
)
def test_invalid_retained_fields_cannot_be_laundered_by_rejection(
    proposed: list[dict[str, Any]],
) -> None:
    choices = [decision(item["path"], "REJECT", reason="Not supported") for item in proposed]
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_INVALID_PROPOSAL"):
        review_fields(proposed, choices)


def test_all_rejected_stays_empty_without_defaults() -> None:
    result = review_fields(
        [{"path": "customer_name", "value": "Example"}],
        [decision("customer_name", "REJECT", reason="Wrong counterparty")],
    )
    assert result.values == {}
    assert "value" not in result.decisions[0]


def test_empty_review_cannot_create_default_contract() -> None:
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_FIELD_COVERAGE"):
        review_fields([], [])


def test_full_catalogue_can_be_reviewed() -> None:
    from erev_api.domain.ai.extraction_fields import CONTRACT_EXTRACTION_PATHS

    fields: list[dict[str, Any]] = []
    for path in sorted(CONTRACT_EXTRACTION_PATHS):
        value: Any = "Reviewed source text"
        if path.startswith("lines."):
            value = {"product_code": "P", "amount": "1.00"}
        elif path == "term_months":
            value = 12
        elif path == "effective_date":
            value = "2026-10-15"
        fields.append({"path": path, "value": value})
    result = review_fields(fields, [decision(field["path"]) for field in reversed(fields)])
    assert len(result.values) == len(result.decisions) == 507


def test_oversized_review_refused() -> None:
    fields = [{"path": "customer_name", "value": "Example"}] * 508
    with pytest.raises(FieldReviewRefused, match="AI_REVIEW_FIELD_COVERAGE"):
        review_fields(fields, [decision("customer_name")] * 508)
