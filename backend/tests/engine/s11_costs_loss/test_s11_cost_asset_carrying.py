"""T-CON-09 ``cost_asset_carrying_txn`` per member contract and period (04 T-CON-09; ENGINE_SPEC_B
§11.1; lane L5-5, cluster "cost").

No row of ``_balances`` held the carrying amount of the contract cost assets, so the COST and
JE-CHK-13x keys read ``cost_asset_carrying`` as ``<absent>``. No database.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest
from erev_engine.bundle import BalanceOut
from erev_engine.errors import EngineError
from erev_engine.stages.s11_costs_loss.balances import cost_asset_carrying_columns
from support.recognition import usd

K1, K2 = "K-01@US01", "K-02@US01"


def _row(subject: str, period: str) -> BalanceOut:
    columns = {"entity": "US01", "contract_liability_txn": usd("5.00")}
    return BalanceOut(subject, period, MappingProxyType(columns), MappingProxyType({}))


def test_carrying_sums_the_member_assets_and_defaults_to_zero() -> None:
    # JE-CHK-130 January: obtain 9,880.95 and fulfil 138,333.33 give 148,214.28; K-02 holds none.
    rows = (_row(K1, "FY2026-P01"), _row(K1, "FY2026-P02"), _row(K2, "FY2026-P01"))
    carrying = {
        ("K-01/EV-000004", "FY2026-P01"): usd("9880.95"),
        ("K-01/EV-000005", "FY2026-P01"): usd("138333.33"),
        ("K-01/EV-000004", "FY2026-P02"): usd("9761.90"),
        ("K-01/EV-000005", "FY2026-P02"): usd("136666.66"),
    }
    member_of = {"K-01/EV-000004": K1, "K-01/EV-000005": K1}
    found = cost_asset_carrying_columns(rows, carrying=carrying, member_of=member_of)
    assert [
        (row.subject_key, row.period_key, row.columns["cost_asset_carrying_txn"]) for row in found
    ] == [
        (K1, "FY2026-P01", usd("148214.28")),
        (K1, "FY2026-P02", usd("146428.56")),
        (K2, "FY2026-P01", 0),
    ]
    assert found[0].columns["contract_liability_txn"] == usd("5.00")


def test_an_asset_without_its_member_fails_closed() -> None:
    with pytest.raises(EngineError, match="no member contract"):
        cost_asset_carrying_columns(
            (_row(K1, "FY2026-P01"),),
            carrying={("K-01/EV-000009", "FY2026-P01"): 1},
            member_of={},
        )
