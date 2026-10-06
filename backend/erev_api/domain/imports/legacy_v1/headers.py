"""Legacy v1 row reading and row findings (04 T-IMP-01, T-IMP-03 ``normalized``, §17.3, §17.4,
table 15.4-A; BUILD_SPEC DIN-4 to DIN-6).

A validated legacy row is stored as the JSON of its per-row model: the exact legacy column names as
members, text as given, numbers as decimal strings and dates as ``YYYY-MM-DD``. ``text``,
``number`` and ``day`` read those members back. ``RowFinding`` is the shape a template rule answers
(a table 15.4-A code, its severity, the PRD IMP copy and the column), which the validation job turns
into its findings; it keeps the emitters free of the validation module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from erev_api.domain.imports import legacy_templates as columns

__all__ = ["RowFinding", "day", "memos", "number", "text"]

type Severity = Literal["ERROR", "WARNING", "INFO"]


@dataclass(frozen=True, slots=True)
class RowFinding:
    """One template rule finding of a row (04 table 15.4-A)."""

    code: str
    severity: Severity
    message: str
    column: str | None = None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def text(row: Mapping[str, Any], name: str) -> str | None:
    """The exact text of a cell (LM-CL-01: keys are exact text); None when blank."""
    value = row.get(name)
    return None if _blank(value) else str(value)


def number(row: Mapping[str, Any], name: str) -> Decimal | None:
    """A numeric cell as ``Decimal``; None when blank."""
    value = row.get(name)
    if _blank(value):
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def day(row: Mapping[str, Any], name: str) -> date | None:
    """A date cell; None when blank."""
    value = row.get(name)
    if _blank(value):
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def memos(row: Mapping[str, Any]) -> dict[str, str]:
    """``memo_1`` to ``memo_3`` of the non-blank memo cells."""
    found: dict[str, str] = {}
    for column, member in columns.MEMOS:
        value = text(row, column)
        if value is not None:
            found[member] = value
    return found
