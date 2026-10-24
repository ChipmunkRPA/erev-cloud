"""Displayed maturity reconciles after currency translation and its rounding."""

from decimal import Decimal
from uuid import UUID

from erev_api.domain.reports.builders.contract_balances import _values
from erev_api.domain.reports.reporting_currency import Translation
from erev_api.domain.reports.tie_outs import BalanceRow


def test_asset_maturity_uses_rounded_presented_total_and_current():
    entity = UUID(int=1)
    row = BalanceRow(
        UUID(int=2),
        "ROUNDING",
        None,
        entity,
        "US",
        "USD",
        UUID(int=3),
        {"contract_asset": Decimal("0.02"), "contract_asset_current": Decimal("0.01")},
    )
    translation = Translation("EUR", {entity: {"base_currency": "USD", "rate": "0.5"}})
    (translated,) = translation.balances((row,))
    values = _values(translated.value, asset_noncurrent=True)
    assert values["contract_asset"] == values["contract_asset_current"] == Decimal("0.01")
    assert values["contract_asset_noncurrent"] == Decimal("0.00")
    # Independently translating the raw remainder would overstate the displayed sum.
    assert translation.amount(entity, Decimal("0.01")) == Decimal("0.01")
    assert "contract_asset_noncurrent" not in _values(translated.value, asset_noncurrent=False)
