"""A rounded memo spanning owners preserves exact source amounts and rejects missing relief."""

from dataclasses import replace

import pytest
from erev_api.domain.reports.credit_memo_fx import parts
from erev_engine.trace import SourceRef, Trace, TraceNode


def test_credit_memo_cumulative_rounding_keeps_offsetting_sources() -> None:
    # Two one-cent reliefs at 1.5: round(total)=3 cents, not 2+2 cents.
    # Historical carrying 1+2 also totals 3: the net-zero FX still has +1/-1 owners.
    reliefs = tuple(
        TraceNode(
            str(i),
            "fx_layer_consumed",
            value,
            "USD",
            "fx.layer.consume.fifo.v1",
            (),
            {},
            "0",
            "fx.layer.consume.fifo",
        )
        for i, value in ((1, "0.01"), (2, "0.02"))
    )
    memo = TraceNode(
        "memo",
        "fx_credit_memo_difference",
        "0.00",
        "USD",
        "fx.credit_memo_difference.v1",
        (SourceRef("fx_rate", "rate", {"quote": "USD", "value": "1.5"}), "1", "2"),
        {
            "rate": "3/2",
            "rate_input": "true",
            "minor_unit": "2",
            "txn_minor_unit": "2",
            "amount_txn": "2",
            "reliefs": "2",
            "effective_date": "2026-08-20",
        },
        "0",
        "fx.credit_memo_difference",
    )
    trace = Trace(1, "test", (*reliefs, memo), {})
    movements = [
        {
            "trace_node_id": str(i),
            "movement_kind": "LIABILITY_LAYER_CONSUMED",
            "balance_role": "CONTRACT_LIABILITY",
            "functional_currency": "USD",
            "effective_date": "2026-08-20",
            "amount_functional": i,
            "amount_txn": 1,
            "source_key": "event",
            "contract_key": f"owner-{i}",
            "layer_key": f"layer-{i}",
        }
        for i in (1, 2)
    ]
    found = parts(trace, movements)
    assert [
        (part.movement["contract_key"], part.spot_minor, part.difference_minor) for part in found
    ] == [("owner-1", 2, 1), ("owner-2", 1, -1)]
    with pytest.raises(ValueError, match="retained movement"):
        parts(trace, movements[:1])
    with pytest.raises(ValueError, match="formula verification"):
        parts(replace(trace, nodes=(*reliefs, replace(memo, value="0.01"))), movements)
    with pytest.raises(ValueError, match="source quantities"):
        parts(trace, [{**movements[0], "amount_txn": 2}, movements[1]])
