"""Financial freshness is about original economic inputs, not rate-version labels."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from erev_api.domain.contracts.fx_input_freshness import changed, rates_view
from erev_engine.bundle import FxRateInput


def test_original_fx_inputs_detect_changes_but_ignore_equal_republication_and_future_rates():
    rate = FxRateInput(
        "R@v1/average/EUR/USD/2026-09-30",
        "R@v1",
        "average",
        "EUR",
        "USD",
        date(2026, 9, 30),
        "FY2026-P09",
        Decimal("1.110000"),
    )
    through = date(2026, 9, 30)
    original = {"version": 1, "currencies": ["EUR", "USD"], "rates": rates_view([rate])}
    same = replace(rate, version_key="R@v2", rate=Decimal("1.11"))
    future = replace(rate, effective_date=date(2026, 10, 31), period_key="FY2026-P10")
    assert not changed(original, [same, future], through)
    assert changed(original, [replace(same, rate=Decimal("1.12"))], through)
    assert changed(original, [], through)
    assert changed({"version": 1, "rates": []}, [rate], through)
    assert changed(None, [rate], through)
