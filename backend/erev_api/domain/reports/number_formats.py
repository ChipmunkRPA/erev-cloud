"""XLSX number formats of the tenant negative style (docs/design/DESIGN_SYSTEM.md DS-FMT-26).

Numeric cells carry the format of `ui.negative_number_style` (04 T-PLT-31): parentheses
`#,##0.00_);(#,##0.00)` or minus `#,##0.00;-#,##0.00`, with the decimals of the currency's ISO 4217
minor unit.
"""

from __future__ import annotations

NEGATIVE_NUMBER_STYLES = frozenset({"PARENTHESES", "MINUS"})


def xlsx_number_format(minor_unit: int, style: str) -> str:
    """Return the Excel number format for amounts with ``minor_unit`` decimals under ``style``."""
    if isinstance(minor_unit, bool) or not 0 <= minor_unit <= 4:
        raise ValueError(f"minor unit must be an integer from 0 to 4, got {minor_unit!r}")
    figures = "#,##0" + ("." + "0" * minor_unit if minor_unit else "")
    if style == "PARENTHESES":
        return f"{figures}_);({figures})"
    if style == "MINUS":
        return f"{figures};-{figures}"
    raise ValueError(f"unknown negative number style {style!r}")
