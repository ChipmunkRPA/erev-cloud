"""T-CON-09 functional columns of foreign-currency entities (04 T-CON-09; ENGINE_SPEC_B S12-R-09,
S12-INV-03, S10-R-23; lane L5-5, cluster "functional balances").

``_balances`` published ``<column>_functional`` only when the entity's functional currency was the
transaction currency, so every foreign-currency key that asserts ``functional.contract_liability``,
``functional.contract_asset`` or ``functional.unbilled_receivable`` read ``<absent>`` (FX-BHD,
FX-CHK-080 to -082, FX-JPY, FX-POL-160, FX-POL-161, LATE-POL-181). The columns now come from the
stage 12 layer carrying and the S12-R-09 reclass shares. No database.
"""

from __future__ import annotations

from types import MappingProxyType

from erev_engine.bundle import BalanceOut
from erev_engine.enums import BookCode
from erev_engine.stages.s12_fx_entities import FxState, FxTarget, LayerBalance
from erev_engine.stages.s12_fx_entities.balances import functional_balance_columns
from support.recognition import allocated_state, usd

ENTITY = "US01"
PERIODS = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
K1, K2 = "K-01@US01", "K-02@US01"
MEMBER_OF = {"K-01/L": K1, "K-01/S": K1, "K-02/L": K2}


def _layer(period: str, key: str, role: str, txn: str, functional: str) -> LayerBalance:
    return LayerBalance(BookCode.ASC606, ENTITY, period, key, role, None, usd(txn), usd(functional))


def _reclass(obligation: str, role: str, period: str, txn: str, functional: str) -> FxTarget:
    return FxTarget(
        book_code=BookCode.ASC606,
        entity=ENTITY,
        subject_key=f"{obligation}#{role}",
        measure="netting_reclass_amount",
        part=None,
        balance_role=role,
        period_key=period,
        txn_currency="EUR",
        amount_txn=usd(txn),
        functional_currency="USD",
        amount_functional=usd(functional),
        rates=(),
        node_id=f"fx_reclass_functional:{obligation}#{role}:{period}",
    )


def _state(layers: tuple[LayerBalance, ...], targets: tuple[FxTarget, ...]) -> FxState:
    return FxState(
        allocated=allocated_state([]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=layers,
        functional_targets=targets,
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _row(subject: str, period: str, currency: str = "EUR", **txn: str) -> BalanceOut:
    columns: dict[str, object] = {"entity": ENTITY, "functional_currency": "USD"}
    columns["txn_currency"] = currency
    columns.update({f"{name}_txn": usd(amount) for name, amount in txn.items()})
    return BalanceOut(subject, period, MappingProxyType(columns), MappingProxyType({}))


def _functional(rows: tuple[BalanceOut, ...]) -> dict[tuple[str, str], tuple[object, ...]]:
    names = ("contract_liability", "contract_asset", "unbilled_receivable")
    return {
        (row.subject_key, row.period_key): tuple(row.columns.get(f"{n}_functional") for n in names)
        for row in rows
    }


def _run(
    rows: tuple[BalanceOut, ...], fx: FxState, currency: str = "EUR"
) -> tuple[BalanceOut, ...]:
    return functional_balance_columns(
        rows,
        fx,
        txn_currency=currency,
        functional={ENTITY: "USD"},
        periods={ENTITY: PERIODS},
        member_of=MEMBER_OF,
    )


def test_liability_from_the_layers_and_presented_assets_from_the_reclass_shares() -> None:
    # January: EUR 5,000.00 licence CA and 1,000.00 services UR remeasured at 1.1200 (CHK-081
    # figures of the S12-R-09 test); February: EUR 4,000.00 billed ahead in two layers at 1.1100
    # and 1.1300, and the reclass targets carry forward without a February attribution.
    layers = (
        _layer("FY2026-P01", "A1", "CONTRACT_ASSET", "6000.00", "6720.00"),
        _layer("FY2026-P02", "L1", "CONTRACT_LIABILITY", "3000.00", "3330.00"),
        _layer("FY2026-P02", "L2", "CONTRACT_LIABILITY", "1000.00", "1130.00"),
    )
    targets = (
        _reclass("K-01/L", "CONTRACT_ASSET", "FY2026-P01", "5000.00", "5600.00"),
        _reclass("K-01/S", "UNBILLED_RECEIVABLE", "FY2026-P01", "1000.00", "1120.00"),
        _reclass("K-01/L", "CONTRACT_ASSET", "FY2026-P02", "5000.00", "5600.00"),
        _reclass("K-01/S", "UNBILLED_RECEIVABLE", "FY2026-P02", "1000.00", "1120.00"),
    )
    rows = (
        _row(K1, "FY2026-P01", contract_liability="0.00", contract_asset="5000.00"),
        _row(K1, "FY2026-P02", contract_liability="4000.00", contract_asset="0.00"),
    )
    found = _run(rows, _state(layers, targets))
    assert _functional(found) == {
        (K1, "FY2026-P01"): (0, usd("5600.00"), usd("1120.00")),
        (K1, "FY2026-P02"): (usd("4460.00"), 0, 0),
    }
    assert found[0].columns["contract_asset_txn"] == usd("5000.00")


def test_several_members_share_the_liability_by_their_transaction_liabilities() -> None:
    layers = (_layer("FY2026-P02", "L1", "CONTRACT_LIABILITY", "4000.00", "4460.00"),)
    rows = (
        _row(K1, "FY2026-P02", contract_liability="3000.00"),
        _row(K2, "FY2026-P02", contract_liability="1000.00"),
    )
    found = _functional(_run(rows, _state(layers, ())))
    assert found == {
        (K1, "FY2026-P02"): (usd("3345.00"), 0, 0),
        (K2, "FY2026-P02"): (usd("1115.00"), 0, 0),
    }


def test_a_same_currency_row_is_unchanged() -> None:
    row = _row(K1, "FY2026-P01", currency="USD", contract_liability="10.00")
    found = functional_balance_columns(
        (row,),
        _state((_layer("FY2026-P01", "L1", "CONTRACT_LIABILITY", "10.00", "10.00"),), ()),
        txn_currency="USD",
        functional={ENTITY: "USD"},
        periods={ENTITY: PERIODS},
        member_of=MEMBER_OF,
    )
    assert found == (row,)
