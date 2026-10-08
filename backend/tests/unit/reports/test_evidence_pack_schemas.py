"""RPS-16 request boundary; these tests do not establish pack generation or CTL-041."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from erev_api.schemas.evidence_packs import EvidencePackCreateIn
from pydantic import TypeAdapter, ValidationError

ADAPTER = TypeAdapter(EvidencePackCreateIn)
REQUESTS: dict[str, dict[str, Any]] = {
    "CLOSE": {
        "kind": "CLOSE",
        "entity_code": "AVM-US",
        "book": "ASC606",
        "period_key": "2026-09",
        "period_lock_id": "00000000-0000-0000-0000-000000000001",
    },
    "CONTRACT_SAMPLE": {
        "kind": "CONTRACT_SAMPLE",
        "contract_external_ids": ["PRJ-CB-2026-01"],
        "as_of": "2026-09-30",
    },
    "CHANGE": {"kind": "CHANGE", "from_date": "2026-09-01", "to_date": "2026-09-30"},
    "ACCESS": {"kind": "ACCESS", "as_of": "2026-09-30"},
}
SELECTORS = {key for request in REQUESTS.values() for key in request if key != "kind"}


@pytest.mark.parametrize("kind", REQUESTS)
def test_documented_request_round_trips_without_adding_unused_fields(kind: str) -> None:
    parsed = ADAPTER.validate_python(REQUESTS[kind])
    assert parsed.model_dump(mode="json") == REQUESTS[kind]
    assert ADAPTER.validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    ("kind", "field"),
    [(kind, field) for kind, body in REQUESTS.items() for field in body if field != "kind"],
)
@pytest.mark.parametrize("null", [False, True], ids=["absent", "null"])
def test_every_required_selector_is_required_and_nonnull(kind: str, field: str, null: bool) -> None:
    body = deepcopy(REQUESTS[kind])
    if null:
        body[field] = None
    else:
        del body[field]
    with pytest.raises(ValidationError) as error:
        ADAPTER.validate_python(body)
    assert error.value.errors()[0]["loc"] == (kind, field)


@pytest.mark.parametrize(
    ("kind", "field"),
    [(kind, field) for kind, body in REQUESTS.items() for field in sorted(SELECTORS - body.keys())],
)
@pytest.mark.parametrize("null", [False, True], ids=["value", "null"])
def test_every_unused_selector_is_refused_even_when_null(kind: str, field: str, null: bool) -> None:
    value = next(body[field] for body in REQUESTS.values() if field in body)
    with pytest.raises(ValidationError) as error:
        ADAPTER.validate_python({**REQUESTS[kind], field: None if null else value})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == (kind, field)


@pytest.mark.parametrize("kind", REQUESTS)
def test_unknown_fields_cannot_be_silently_ignored(kind: str) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**REQUESTS[kind], "known_at": "2026-09-30"})


@pytest.mark.parametrize("body", [{}, {"kind": None}, {"kind": "close"}, {"kind": "OTHER"}])
def test_kind_is_explicit_and_known(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(body)


@pytest.mark.parametrize("value", ["", " ", "\t\n", "\u2003"])
@pytest.mark.parametrize("field", ["entity_code", "period_key", "contract_external_ids"])
def test_blank_identifiers_are_refused(field: str, value: str) -> None:
    kind = "CONTRACT_SAMPLE" if field == "contract_external_ids" else "CLOSE"
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(
            {**REQUESTS[kind], field: [value] if field == "contract_external_ids" else value}
        )


@pytest.mark.parametrize("count", [0, 51])
def test_sample_size_limits(count: int) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(
            {
                **REQUESTS["CONTRACT_SAMPLE"],
                "contract_external_ids": [f"C-{n}" for n in range(count)],
            }
        )


def test_fifty_exact_business_keys_preserve_order_and_spelling() -> None:
    keys = [" Contract 1 ", "Contract 1", "contract 1", *[f"C-{n}" for n in range(47)]]
    body = {**REQUESTS["CONTRACT_SAMPLE"], "contract_external_ids": keys}
    assert ADAPTER.validate_python(body).model_dump(mode="json") == body


def test_duplicate_contracts_are_not_silently_deduplicated() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        ADAPTER.validate_python(
            {**REQUESTS["CONTRACT_SAMPLE"], "contract_external_ids": ["K03", "K03"]}
        )


def test_change_date_range_is_ordered_and_allows_a_single_day() -> None:
    ADAPTER.validate_python({**REQUESTS["CHANGE"], "from_date": "2026-09-30"})
    with pytest.raises(ValidationError, match="on or after"):
        ADAPTER.validate_python({**REQUESTS["CHANGE"], "from_date": "2026-10-01"})


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        ("CLOSE", "entity_code", "x" * 65),
        ("CLOSE", "period_key", "x" * 17),
        ("CLOSE", "period_lock_id", "not-a-lock"),
        ("CLOSE", "book", "OTHER"),
        ("ACCESS", "as_of", "2026-02-30"),
        ("ACCESS", "as_of", "2026-09-30T12:00:00Z"),
        ("CONTRACT_SAMPLE", "contract_external_ids", [123]),
        ("CONTRACT_SAMPLE", "contract_external_ids", "K03"),
    ],
)
def test_invalid_selector_types_and_values(kind: str, field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**REQUESTS[kind], field: value})


def test_api_schema_exposes_kind_specific_requirements() -> None:
    schema = ADAPTER.json_schema()
    assert schema["discriminator"]["propertyName"] == "kind"
    assert set(schema["discriminator"]["mapping"]) == set(REQUESTS)
    for kind, ref in schema["discriminator"]["mapping"].items():
        variant = schema["$defs"][ref.rsplit("/", 1)[1]]
        assert set(variant["required"]) == set(REQUESTS[kind])
        assert set(variant["properties"]) == set(REQUESTS[kind])
        assert variant["additionalProperties"] is False
