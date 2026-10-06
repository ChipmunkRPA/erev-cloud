"""Part targets past the evaluation horizon need no stage 12 functional amount (ENGINE_SPEC_B C-05,
S12-R-13, S14-R-01, S14-R-04; lane L5-5, cluster "FX horizon").

Stage 09 publishes ``revenue_relief_cum`` through the term end of a deterministic component, while
stage 12 evaluates layers and publishes its functional targets only through the horizon (C-05;
S12-R-13), and stage 14 derives role targets only through the horizon (S14-R-04). Stage 14 still
converted every producer target, so the first foreign-currency relief target after the horizon
raised "stage 12 publishes no functional amount for a foreign-currency part target" in
FX-CHK-081, -082, -083, POL-160 and POL-161. No database.
"""

from __future__ import annotations

from datetime import date

import pytest
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s12_fx_entities.layers import FxTarget
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import RELIEF_MEASURE, part_targets
from erev_engine.stages.state import Target
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
OBLIGATION = f"{CONTRACT_KEY}/L1-PLATFORM"


def _relief(period: str, amount: str) -> Target:
    node = f"revenue_relief_cum:{OBLIGATION}:{period}"
    return Target(
        BookCode.ASC606, ENTITY, OBLIGATION, RELIEF_MEASURE, period, None, usd(amount), None, node
    )


def _functional(period: str, txn: str, functional: str) -> FxTarget:
    return FxTarget(
        book_code=BookCode.ASC606,
        entity=ENTITY,
        subject_key=OBLIGATION,
        measure="revenue_cum",
        part=None,
        balance_role=None,
        period_key=period,
        txn_currency="EUR",
        amount_txn=usd(txn),
        functional_currency="USD",
        amount_functional=usd(functional),
        rates=(),
        node_id=f"revenue_functional:{OBLIGATION}:{period}",
    )


def _state(functional: tuple[FxTarget, ...]) -> FxState:
    ob = obligation(
        "L1-PLATFORM",
        [segment(12, usd("1200.00"), start=date(2026, 1, 1), end=date(2026, 12, 31))],
    )
    return FxState(
        allocated=allocated_state([ob]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=functional,
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _ctx(horizon: str):  # type: ignore[no-untyped-def]
    calendar = bundles.entity(functional_currency="USD", months=6)
    return book_context(calendar, book_code="ASC606", currency="EUR", horizon=horizon)


def test_relief_after_the_horizon_needs_no_stage_12_amount() -> None:
    # EUR 100.00 a month; horizon FY2026-P02; stage 12 converts P01 and P02 at 1.12.
    relief = tuple(
        _relief(period, amount)
        for period, amount in (
            ("FY2026-P01", "100.00"),
            ("FY2026-P02", "200.00"),
            ("FY2026-P03", "300.00"),
            ("FY2026-P04", "400.00"),
        )
    )
    functional = (
        _functional("FY2026-P01", "100.00", "112.00"),
        _functional("FY2026-P02", "200.00", "224.00"),
    )
    found = part_targets(_ctx("FY2026-P02"), _state(functional), PartInputs(relief=relief))
    assert [(p.part, p.period_key, p.amount_txn, p.amount_functional) for p in found] == [
        ("JET-02 principal", "FY2026-P01", usd("100.00"), usd("112.00")),
        ("JET-02 principal", "FY2026-P02", usd("200.00"), usd("224.00")),
    ]
    assert found[1].node_ids[-1] == f"revenue_functional:{OBLIGATION}:FY2026-P02"


def test_a_missing_stage_12_amount_inside_the_horizon_still_fails_closed() -> None:
    relief = (_relief("FY2026-P01", "100.00"), _relief("FY2026-P02", "200.00"))
    functional = (_functional("FY2026-P01", "100.00", "112.00"),)
    with pytest.raises(EngineError) as raised:
        part_targets(_ctx("FY2026-P02"), _state(functional), PartInputs(relief=relief))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["period_key"] == "FY2026-P02"
