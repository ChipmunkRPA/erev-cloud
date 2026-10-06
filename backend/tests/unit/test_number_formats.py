"""DS-FMT-26 XLSX number formats per tenant negative style (DESIGN_SYSTEM §6.2, DS-VER-03)."""

from __future__ import annotations

import pytest
from erev_api.domain.reports.number_formats import xlsx_number_format


def test_ds_fmt_26_xlsx_number_formats() -> None:
    assert xlsx_number_format(2, "PARENTHESES") == "#,##0.00_);(#,##0.00)"
    assert xlsx_number_format(2, "MINUS") == "#,##0.00;-#,##0.00"
    assert xlsx_number_format(0, "PARENTHESES") == "#,##0_);(#,##0)"
    assert xlsx_number_format(0, "MINUS") == "#,##0;-#,##0"
    assert xlsx_number_format(3, "PARENTHESES") == "#,##0.000_);(#,##0.000)"
    assert xlsx_number_format(4, "MINUS") == "#,##0.0000;-#,##0.0000"


@pytest.mark.parametrize(
    ("minor_unit", "style", "message"),
    [
        (2, "RED", "unknown negative number style 'RED'"),
        (-1, "MINUS", "minor unit must be an integer from 0 to 4, got -1"),
        (True, "MINUS", "minor unit must be an integer from 0 to 4, got True"),
    ],
)
def test_ds_fmt_26_xlsx_number_format_refuses_unknown_input(
    minor_unit: int, style: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        xlsx_number_format(minor_unit, style)
