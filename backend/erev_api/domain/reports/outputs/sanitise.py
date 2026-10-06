"""Spreadsheet formula-injection guard (03 REQ-SEC-011; SCREENS_B RV-07; BUILD_SPEC RPS-2).

CSV and XLSX outputs write a text cell that starts with ``=``, ``+``, ``-``, ``@``, a tab or a
carriage return with a leading apostrophe, so a spreadsheet shows the text instead of evaluating
it. The writers pass only text cells here: money, integers, dates and timestamps are numeric or
machine-readable values and stay unchanged (DS-FMT-25, DS-FMT-26).
"""

from __future__ import annotations

from typing import Final

FORMULA_TRIGGERS: Final = ("=", "+", "-", "@", "\t", "\r")
PREFIX: Final = "'"


def guard(text: str) -> str:
    """``text`` with a leading apostrophe when a spreadsheet would read it as a formula."""
    return PREFIX + text if text.startswith(FORMULA_TRIGGERS) else text
