"""Readable export presentation of retained RPO exemption facts; no recalculation."""

from collections.abc import Mapping
from typing import Any

TITLE = "RPO exemption changes"
BASIS = (
    "Original transaction-currency endpoint amounts. Movement is opening excluded RPO less "
    "closing excluded RPO; translated report movements may differ."
)
COLUMNS = (
    ("contract", "Contract"),
    ("obligation", "Obligation"),
    ("entity", "Entity"),
    ("currency", "Transaction currency"),
    ("opening_date", "Opening date"),
    ("opening_rule", "Opening exemption"),
    ("opening_excluded", "Opening excluded RPO"),
    ("closing_date", "Closing date"),
    ("closing_rule", "Closing exemption"),
    ("closing_excluded", "Closing excluded RPO"),
    ("movement", "Exemption movement"),
)
MONEY = frozenset({"opening_excluded", "closing_excluded", "movement"})
RULES = {
    "POL-197": "Short-term contract",
    "POL-198": "Right to invoice",
    "POL-200": "Unsatisfied variable consideration",
}


def records(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Reject malformed retained facts rather than silently omit them from an export."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("RPO exemption details must be a list.")
    for row in value:
        if not isinstance(row, Mapping) or any(key not in row for key, _ in COLUMNS):
            raise ValueError("RPO exemption details are incomplete.")
    return tuple(value)


def cell(row: Mapping[str, Any], key: str) -> str:
    value = row[key]
    if key in {"opening_rule", "closing_rule"}:
        return "Not excluded" if value is None else RULES.get(str(value), str(value))
    return str(value)
