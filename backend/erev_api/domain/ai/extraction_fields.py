"""Contract-review field catalogue; proposed facts never become accounting commands here."""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from erev_api.domain.ai.extraction_validation import OutputRefused
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.money import validate_money_string

# ContractCreateIn accepts at most 500 lines. Terms remain quoted review text; the model
# cannot select accounting classifications, identifiers, currencies, approvals or schedules.
MAX_EXTRACTION_LINES: Final = 500
HEADER_PATHS: Final = frozenset(
    {
        "customer_name",
        "effective_date",
        "term_months",
        "payment_terms",
        "termination",
        "variable_consideration_terms",
        "material_right_indicator",
    }
)
CONTRACT_EXTRACTION_PATHS: Final = HEADER_PATHS | frozenset(
    f"lines.{index}" for index in range(MAX_EXTRACTION_LINES)
)
MAX_EXTRACTION_FIELDS: Final = len(CONTRACT_EXTRACTION_PATHS)


def require_contract_paths(paths: frozenset[str]) -> frozenset[str]:
    if not paths or not paths.issubset(CONTRACT_EXTRACTION_PATHS):
        raise PreparationRefused("AI_INVALID_FIELD_PATHS")
    return paths


def _text(value: Any, limit: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and bool(value.strip())
        and "\x00" not in value
    )


def validate_contract_value(path: str, value: Any) -> None:
    """Validate original parsed JSON before canonicalization can stringify decimal numbers.

    Nothing is coerced, rounded, trimmed, resolved to an ID or interpreted as an accounting
    conclusion. Dates must already be unambiguous ISO dates and amounts exact decimal strings.
    """
    if path not in CONTRACT_EXTRACTION_PATHS:
        raise OutputRefused("AI_INVALID_FIELD_PATH")
    valid = False
    if path == "customer_name":
        valid = _text(value, 400)  # customer reference label, TY-07
    elif path == "effective_date":
        if isinstance(value, str) and len(value) == 10:
            try:
                valid = date.fromisoformat(value).isoformat() == value
            except ValueError:
                pass
    elif path == "term_months":
        valid = type(value) is int and 1 <= value <= 2_147_483_647
    elif path in HEADER_PATHS:
        valid = _text(value, 4000)
    elif isinstance(value, dict) and set(value) == {"product_code", "amount"}:
        amount = value["amount"]
        if _text(value["product_code"], 255) and isinstance(amount, str):
            try:
                validate_money_string(amount)
                valid = True
            except ValueError:
                pass
    if not valid:
        raise OutputRefused("AI_INVALID_FIELD_VALUE")
