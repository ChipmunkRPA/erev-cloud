"""Shared unit costs replay frozen exact amounts rather than new FX publications."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from erev_api.domain.contracts import bundles, portfolio_cost_fx
from erev_api.problems import Problem
from erev_engine.bundle import FxRateInput


def draft():
    return dict(
        currency="GBP",
        effective_date=date(2026, 10, 1),
        parameters={"carrying_cost_per_unit": "12.50", "recovery_cost_per_unit": "0.01"},
    )


def capture(monkeypatch, rates):
    session = Mock()
    session.scalars.return_value = ["USD"]
    monkeypatch.setattr(bundles, "fx_rate_inputs", lambda *_: rates)
    return portfolio_cost_fx.capture(session, draft(), [])


def rate(**changes):
    return FxRateInput(
        **{
            **dict(
                rate_key="SPOT@v1/GBP/USD/2026-10-01",
                version_key="SPOT@v1",
                rate_type="spot",
                base_currency="GBP",
                quote_currency="USD",
                effective_date=date(2026, 10, 1),
                period_key=None,
                rate=Decimal("1.25"),
            ),
            **changes,
        }
    )


def test_exact_costs_and_original_source_survive_replay(monkeypatch):
    frozen = capture(monkeypatch, [rate()])[0].model_dump(mode="json")
    assert Decimal(frozen["converted_costs"]["carrying_cost_per_unit"]) == Decimal("15.625")
    assert Decimal(frozen["converted_costs"]["recovery_cost_per_unit"]) == Decimal("0.0125")
    original = {**draft(), "portfolio_application_basis": {"cost_conversions": [frozen]}}
    saved = deepcopy(original)
    monkeypatch.setattr(
        bundles, "fx_rate_inputs", lambda *_: pytest.fail("Replay must not resolve FX")
    )
    result = portfolio_cost_fx.apply(original, {"USD"})
    assert result["currency"] == "USD"
    assert result["parameters"]["shared_unit_cost_fx"] == frozen
    assert original == saved
    assert portfolio_cost_fx.apply(original, {"GBP"}) == original
    broken = deepcopy(original)
    broken["portfolio_application_basis"]["cost_conversions"][0]["converted_costs"][
        "recovery_cost_per_unit"
    ] = "0.01"
    with pytest.raises(Problem, match="does not reconcile"):
        portfolio_cost_fx.apply(broken, {"USD"})


@pytest.mark.parametrize(
    "rates",
    [
        [],
        [rate(base_currency="USD", quote_currency="GBP")],
        [rate(effective_date=date(2026, 10, 2))],
    ],
)
def test_missing_inverse_or_future_rate_cannot_substitute(monkeypatch, rates):
    with pytest.raises(Problem, match="Publish a direct"):
        capture(monkeypatch, rates)
