"""Signed layer attribution: two owners, changed targets and prior posted amounts."""

from datetime import date
from decimal import Decimal as D
from uuid import UUID

import pytest
from erev_api.domain.reports.liability_fx_trace import (
    InvalidLiabilityTrace,
    LayerDelta,
    posting_delta,
)
from erev_engine.trace import SourceRef, Trace, TraceNode


@pytest.mark.parametrize("closing", [False, True])
def test_prior_target_and_paid_amounts_keep_their_actual_owners(closing: bool) -> None:
    day = date(2026, 9, 30)
    nodes = []
    movements = []
    for index, (key, owner, amount) in enumerate(
        (("a-now", 1, "10"), ("b-now", 2, "5"), ("a-before", 1, "6"), ("b-before", 2, "3")), 1
    ):
        formula = "fx.remeasure.closing.v1" if closing else "fx.remeasure.relief.v1"
        nodes.append(
            TraceNode(key, "fx_layer_remeasured", amount, "GBP", formula, (), {}, "0", formula[:-3])
        )
        movements.append(
            {
                "id": UUID(int=index),
                "contract_id": UUID(int=owner),
                "layer_key": f"layer-{owner}",
                "effective_date": day,
                "balance_role": "CONTRACT_LIABILITY",
                "movement_kind": "LIABILITY_LAYER_REMEASURED",
                "functional_currency": "GBP",
                "amount_functional": D(amount),
                "trace_node_id": key,
            }
        )
    for key, inputs, amount in (
        ("now", ("a-now", "b-now"), "-15"),
        ("before", ("a-before", "b-before"), "-9"),
    ):
        nodes.append(
            TraceNode(
                key,
                "posting_target",
                amount,
                "GBP",
                "post.role_target.v1",
                inputs,
                {"signs": "-1|-1", "minor_unit": "2"},
                "0",
                "post.role_target",
            )
        )
    nodes.append(
        TraceNode(
            "delta",
            "posting_delta",
            "-4",
            "GBP",
            "post.delta.v1",
            ("now", "before", SourceRef("source_record", "posted/group/period", {"value": "-2"})),
            {
                "previous": "true",
                "class": "TIME" if closing else "EVENT",
                "time": "-1500" if closing else "0",
                "time_previous": "-900" if closing else "0",
            },
            "0",
            "post.delta",
        )
    )
    trace = Trace(1, "test", tuple(nodes), {})
    paid = tuple(
        LayerDelta(UUID(int=owner), f"layer-{owner}", day, closing, D("-1")) for owner in (1, 2)
    )
    result = posting_delta(trace, "delta", movements, currency="GBP", minor_unit=2, paid=paid)
    assert result.amount == D("-4")
    assert {item.contract_id: item.amount for item in result.movements} == {
        UUID(int=1): D("-3"),
        UUID(int=2): D("-1"),
    }
    # The previous aggregate cannot be dropped just because both new targets reconcile.
    with pytest.raises(InvalidLiabilityTrace, match="paid amount"):
        posting_delta(trace, "delta", movements, currency="GBP", minor_unit=2, paid=())
    # A corrupt source cannot hide behind the target's correct overall total.
    changed = [dict(item) for item in movements]
    changed[0]["amount_functional"] = D("11")
    with pytest.raises(InvalidLiabilityTrace, match="differs from its retained trace"):
        posting_delta(trace, "delta", changed, currency="GBP", minor_unit=2, paid=paid)
