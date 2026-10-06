"""T-CON-09 ``loss_provision_txn`` per member contract and period (04 T-CON-09; ENGINE_SPEC_B §11.1,
S11-R-14; D-92 (3); lane ENG-C7).

No row of ``_balances`` held the required provision of the member's loss units, so the four LOSS
keys (LOSS-S7-LOSS-OWN, JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE, LOSS-GE-03-LOSS-CONTRACT-
PROVISION, IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY) read ``loss_provision`` as ``<absent>``.
The EX-11-B / CHK-132 figures: provision 0.00 / 30,000.00 / 0.00 at the three year ends. No
database.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest
from erev_engine.bundle import BalanceOut
from erev_engine.errors import EngineError
from erev_engine.stages.s11_costs_loss.balances import loss_provision_columns
from support.recognition import usd

K1, K2 = "K-01@US01", "K-02@US01"
YEARS = ("FY2026-P12", "FY2027-P12", "FY2028-P12")


def _row(subject: str, period: str) -> BalanceOut:
    columns = {"entity": "US01", "contract_asset_txn": usd("5.00")}
    return BalanceOut(subject, period, MappingProxyType(columns), MappingProxyType({}))


def test_ex_11_b_provision_per_member_and_period_defaults_to_zero() -> None:
    # CHK-132: required 0.00 / 30,000.00 / 0.00 (S11-R-14); K-02 has no loss unit in the book.
    rows = (*(_row(K1, period) for period in YEARS), _row(K2, YEARS[0]))
    provisions = {("K-01", YEARS[0]): 0, ("K-01", YEARS[1]): usd("30000.00"), ("K-01", YEARS[2]): 0}
    found = loss_provision_columns(rows, provisions=provisions, member_of={"K-01": K1})
    assert [
        (row.subject_key, row.period_key, row.columns["loss_provision_txn"]) for row in found
    ] == [
        (K1, YEARS[0], 0),
        (K1, YEARS[1], usd("30000.00")),
        (K1, YEARS[2], 0),
        (K2, YEARS[0], 0),
    ]
    assert found[0].columns["contract_asset_txn"] == usd("5.00")


def test_pob_units_sum_into_their_member() -> None:
    # POL-150 POB: two units of one contract at one period end sum into the member's column.
    rows = (_row(K1, YEARS[1]),)
    provisions = {("K-01/P1", YEARS[1]): usd("10000.00"), ("K-01/P2", YEARS[1]): usd("2500.00")}
    member_of = {"K-01/P1": K1, "K-01/P2": K1}
    (found,) = loss_provision_columns(rows, provisions=provisions, member_of=member_of)
    assert found.columns["loss_provision_txn"] == usd("12500.00")


def test_a_unit_without_its_member_fails_closed() -> None:
    with pytest.raises(EngineError, match="no member contract"):
        loss_provision_columns(
            (_row(K1, YEARS[0]),), provisions={("K-09", YEARS[0]): 1}, member_of={}
        )
