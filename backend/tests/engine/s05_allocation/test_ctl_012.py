"""CTL-012 allocation invariant fails closed (03 §4.1 CTL-012; ENGINE_SPEC §5.5 S05-INV-01; 04 DB-17
V1; dev-guide DG-ENG-05; BUILD_SPEC ENA-13).

Golden Contract 2 at its setup step replays under the parity preset; stages 01 to 05 run for real.
No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, money
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, Quota
from erev_engine.trace import TraceBuilder
from support import golden_streams
from support.fold import book_context


def priced_contract_2() -> tuple[BookContext, PricedState, TraceBuilder]:
    value = golden_streams.stream("Contract 2", "02").input_bundle(preset="LEGACY_PARITY")
    ctx = book_context(value, "ASC606")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(ctx, cb, tb)
    return ctx, s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb), tb


@pytest.mark.control("CTL-012")
def test_ctl_012_allocation_sum_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, priced, tb = priced_contract_2()
    real = money.largest_remainder

    def dropping(total_minor: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
        amounts = real(total_minor, weights, keys)
        return [amounts[0] - 1, *amounts[1:]]

    monkeypatch.setattr(money, "largest_remainder", dropping)
    returned: list[AllocatedState] = []
    with pytest.raises(EngineError) as raised:
        returned.append(s05_allocation.run(ctx, priced, tb))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "S05-INV-01"
    assert returned == []


@pytest.mark.control("CTL-012")
def test_ctl_012_contract_version_identity_fails_closed() -> None:
    ctx, priced, tb = priced_contract_2()
    allocated = s05_allocation.run(ctx, priced, tb)
    s05_allocation.assert_contract_version_identity(allocated)
    first = allocated.obligations[0]
    quota = first.original_allocation
    segment = first.segments[0]
    short = dataclasses.replace(
        first,
        original_allocation=Quota(quota.x_exact, quota.a_posted - 1),
        segments=(dataclasses.replace(segment, a_posted=segment.a_posted - 1), *first.segments[1:]),
    )
    state = dataclasses.replace(allocated, obligations=(short, *allocated.obligations[1:]))
    with pytest.raises(EngineError) as raised:
        s05_allocation.assert_contract_version_identity(state)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "DB-17 V1"
    assert "DB-17 V1" in raised.value.message
    assert (raised.value.detail["allocated"], raised.value.detail["expected"]) == ("89999", "90000")
