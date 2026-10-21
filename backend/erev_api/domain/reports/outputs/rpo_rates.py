"""Presentation of retained RPO currency rates without fresh reads or recalculation."""

from collections.abc import Mapping
from typing import Any

REPORTS = frozenset({"rpo", "rpo_rollforward"})
TITLE = "Retained RPO exchange rates"
BASIS = (
    "Original rates used by this report. Average rates translate movements; closing rates "
    "translate endpoints. Each conversion leg is listed separately at its retained precision."
)
COLUMNS = (
    ("entity_id", "Entity ID"),
    ("period_key", "Period"),
    ("period_end", "Period end"),
    ("rate_type", "Rate basis"),
    ("base_currency", "Source currency"),
    ("quote_currency", "Target currency"),
    ("rate", "Retained rate (exact)"),
    ("rate_id", "Original rate ID"),
    ("version_id", "Rate-set version ID"),
    ("rate_cutoff", "Rate knowledge cutoff"),
)
OPTIONAL = frozenset({"rate_id", "version_id"})


def records(value: Any) -> tuple[Mapping[str, Any], ...] | None:
    """Unknown legacy shapes retain the generic raw control presentation."""
    if not isinstance(value, (list, tuple)):
        return None
    for row in value:
        if not isinstance(row, Mapping):
            return None
        for key, _ in COLUMNS:
            if not isinstance(row.get(key), str) and not (key in OPTIONAL and row.get(key) is None):
                return None
    return tuple(value)
