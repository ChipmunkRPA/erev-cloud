"""Tie-out ``difference`` of API-S-ReportRun ``tie_out_results`` (04 §16.9; D-88 L7-3-Q-3).

The helper is pure, so these tests build the stored T-RPT-02 items with ``tie_outs.compared`` and
``tie_outs.not_applicable`` and need no database.
"""

from __future__ import annotations

from decimal import Decimal

from erev_api.domain.reports import tie_outs


def test_difference_is_actual_minus_expected_per_currency() -> None:
    failed = tie_outs.compared(
        tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO,
        {"USD": Decimal("105043.80"), "JPY": Decimal("5000")},
        {"USD": Decimal("104043.80"), "EUR": Decimal("1.005")},
    )
    assert failed["result"] == tie_outs.FAIL
    # Code order at minor units: EUR 1.01 (half up) − 0.00, JPY 0 − 5000, USD −1000.00.
    assert tie_outs.difference(failed) == [
        {"amount": "1.01", "currency": "EUR"},
        {"amount": "-5000", "currency": "JPY"},
        {"amount": "-1000.00", "currency": "USD"},
    ]
    # The stored item is not changed: stored results, datasets, manifests and files carry none.
    assert "difference" not in failed


def test_difference_of_passing_and_not_applicable_results() -> None:
    passed = tie_outs.compared(
        tie_outs.TO_WATERFALL_EQ_JE_REVENUE,
        {"USD": Decimal("9764.38")},
        {"USD": Decimal("9764.38")},
    )
    assert tie_outs.difference(passed) == [{"amount": "0.00", "currency": "USD"}]
    # No negative zero.
    signed = {
        "code": tie_outs.TO_WATERFALL_EQ_JE_REVENUE,
        "result": tie_outs.PASS,
        "expected": [{"amount": "0.00", "currency": "USD"}],
        "actual": [{"amount": "-0.00", "currency": "USD"}],
    }
    assert tie_outs.difference(signed) == [{"amount": "0.00", "currency": "USD"}]
    assert tie_outs.difference(tie_outs.not_applicable(tie_outs.TO_ROLLFORWARD_EQ_GL)) is None
