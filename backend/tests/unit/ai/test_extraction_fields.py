"""Extraction values are typed before canonical JSON can coerce provider numbers."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.ai.document_preparation import prepare_extraction
from erev_api.domain.ai.extraction_fields import (
    CONTRACT_EXTRACTION_PATHS,
    MAX_EXTRACTION_FIELDS,
    require_contract_paths,
    validate_contract_value,
)
from erev_api.domain.ai.extraction_validation import OutputRefused
from erev_api.domain.ai.ports import AIResponse
from erev_api.domain.ai.preparation import PreparationRefused


@pytest.mark.parametrize(
    "path,value",
    [
        ("customer_name", "Kinsley Marrow Foods Inc."),
        ("effective_date", "2024-02-29"),
        ("term_months", 12),
        ("term_months", 2147483647),
        ("payment_terms", "Net 30"),
        ("termination", "May terminate on 60 days notice"),
        ("variable_consideration_terms", "Credits up to 5%"),
        ("material_right_indicator", "Renewal increase capped at 3%"),
        ("lines.0", {"product_code": "A", "amount": "120.00"}),
        ("lines.499", {"product_code": "B", "amount": "-20.1234"}),
    ],
)
def test_catalogue_preserves_document_facts(path: str, value: Any) -> None:
    before = json.dumps(value)
    validate_contract_value(path, value)
    assert json.dumps(value) == before


@pytest.mark.parametrize(
    "path,value",
    [
        ("customer_name", None),
        ("customer_name", " "),
        ("customer_name", "x" * 401),
        ("effective_date", "2026-02-29"),
        ("effective_date", "20261001"),
        ("effective_date", "2026-W01-1"),
        ("effective_date", "10/01/2026"),
        ("term_months", True),
        ("term_months", "12"),
        ("term_months", 12.0),
        ("term_months", 0),
        ("term_months", -1),
        ("term_months", 2147483648),
        ("termination", {"party": "CUSTOMER"}),
        ("termination", "x" * 4001),
        ("payment_terms", "Net\x0030"),
        ("material_right_indicator", True),
        ("variable_consideration_terms", ["5%"]),
        ("lines.0", {"product_code": "A", "amount": 120}),
        ("lines.0", {"product_code": "A", "amount": 120.0}),
        ("lines.0", {"product_code": "A", "amount": "1e2"}),
        ("lines.0", {"product_code": "A", "amount": "١٢"}),
        ("lines.0", {"product_code": "A", "amount": "1.00001"}),
        ("lines.0", {"product_code": "A", "amount": "1" * 21}),
        ("lines.0", {"product_code": "A", "amount": "1.00", "currency": "USD"}),
        ("lines.0", {"product_code": "A", "amount": "1.00", "scope_flag": "OUT_OF_SCOPE"}),
        ("lines.0", {"product_code": "A"}),
        ("lines.0", {"product_code": "x" * 256, "amount": "1.00"}),
    ],
)
def test_invalid_values_are_not_coerced_or_retained(path: str, value: Any) -> None:
    with pytest.raises(OutputRefused, match="^AI_INVALID_FIELD_VALUE$"):
        validate_contract_value(path, value)


@pytest.mark.parametrize(
    "path",
    [
        "amount",
        "lines.-1",
        "lines.01",
        "lines.500",
        "lines.0.amount",
        "customer_id",
        "currency",
        "submit_for_activation",
    ],
)
def test_unknown_or_noncanonical_paths_are_refused(path: str) -> None:
    with pytest.raises(PreparationRefused, match="^AI_INVALID_FIELD_PATHS$"):
        require_contract_paths(frozenset({path}))
    with pytest.raises(OutputRefused, match="^AI_INVALID_FIELD_PATH$"):
        validate_contract_value(path, "untrusted")


def test_catalogue_matches_contract_line_capacity() -> None:
    from erev_api.domain.ai.jobs import ExtractionTask

    assert MAX_EXTRACTION_FIELDS == 507
    assert require_contract_paths(CONTRACT_EXTRACTION_PATHS) == CONTRACT_EXTRACTION_PATHS
    request = ExtractionTask.model_validate(
        {
            "operation": "extraction",
            "file_id": str(UUID(int=1)),
            "file_sha256": "a" * 64,
            "allowed_paths": sorted(CONTRACT_EXTRACTION_PATHS),
            "max_tokens": 1024,
        }
    )
    assert request.allowed_paths == CONTRACT_EXTRACTION_PATHS
    with pytest.raises(PreparationRefused):
        require_contract_paths(frozenset())


@pytest.mark.parametrize("token", ["120.0", "1.2e2", "120", "true", "null"])
def test_raw_json_money_is_checked_before_canonicalization(token: str) -> None:
    document_id = UUID(int=1)
    prepared = prepare_extraction(
        document_id=document_id,
        pages=("Product A amount 120.00",),
        allowed_paths=frozenset({"lines.0"}),
        model="fixture-model",
        max_tokens=1024,
        send_contract_text=True,
    )
    field = {
        "path": "lines.0",
        "value": {"product_code": "A", "amount": "RAW_TOKEN"},
        "confidence": 0.9,
        "citation": {
            "ref_type": "document",
            "ref_id": str(document_id),
            "page": 1,
            "char_start": 0,
            "char_end": 21,
        },
    }
    raw = json.dumps([field]).replace('"RAW_TOKEN"', token)
    response = AIResponse(
        raw, sha256(raw.encode()).hexdigest(), 10, 10, 1, "fixture-model", "end_turn"
    )
    with pytest.raises(OutputRefused, match="^AI_INVALID_FIELD_VALUE$"):
        prepared.validate(response, validate_value=validate_contract_value)
