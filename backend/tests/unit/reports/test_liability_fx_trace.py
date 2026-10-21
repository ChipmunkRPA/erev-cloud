"""Signed layer attribution: two owners, changed targets and prior posted amounts."""

from dataclasses import replace
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


@pytest.mark.parametrize("annotations", [False, True])
@pytest.mark.parametrize("closing", [False, True])
def test_prior_target_and_paid_amounts_keep_their_actual_owners(
    closing: bool, annotations: bool
) -> None:
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
                {
                    "signs": "-1|-1",
                    "minor_unit": "2",
                    **(
                        {
                            "time_functional": str(int(D(amount) * 100)) if closing else "0",
                            "input_classes": "TIME|TIME" if closing else "EVENT|EVENT",
                            "input_time_txn": "0|0",
                            "input_time_functional": "unresolved|unresolved",
                        }
                        if annotations
                        else {}
                    ),
                },
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
    # Informational annotations do not authorize genuinely split ownership.
    split_nodes = tuple(
        replace(node, params={**node.params, "split": "true"}) if node.id == "now" else node
        for node in nodes
    )
    with pytest.raises(InvalidLiabilityTrace, match="unsupported split attribution"):
        posting_delta(
            Trace(1, "test", split_nodes, {}),
            "delta",
            movements,
            currency="GBP",
            minor_unit=2,
            paid=paid,
        )
    # The previous aggregate cannot be dropped just because both new targets reconcile.
    with pytest.raises(InvalidLiabilityTrace, match="paid amount"):
        posting_delta(trace, "delta", movements, currency="GBP", minor_unit=2, paid=())
    # A corrupt source cannot hide behind the target's correct overall total.
    changed = [dict(item) for item in movements]
    changed[0]["amount_functional"] = D("11")
    with pytest.raises(InvalidLiabilityTrace, match="differs from its retained trace"):
        posting_delta(trace, "delta", changed, currency="GBP", minor_unit=2, paid=paid)


def test_mixed_control_target_keeps_asset_and_liability_sources_separate() -> None:
    from erev_api.domain.reports.liability_fx_trace import project

    day = date(2026, 9, 30)
    nodes = []
    movements = []
    for index, (role, kind, amount) in enumerate(
        (
            ("CONTRACT_LIABILITY", "LIABILITY_LAYER_REMEASURED", "10"),
            ("CONTRACT_ASSET", "ASSET_LAYER_REMEASURED", "4"),
        ),
        1,
    ):
        key = f"source-{index}"
        nodes.append(
            TraceNode(
                key,
                "fx_layer_remeasured",
                amount,
                "GBP",
                "fx.remeasure.closing.v1",
                (),
                {},
                "0",
                "fx.remeasure.closing",
            )
        )
        movements.append(
            {
                "id": UUID(int=index),
                "contract_id": UUID(int=index),
                "layer_key": key,
                "effective_date": day,
                "balance_role": role,
                "movement_kind": kind,
                "functional_currency": "GBP",
                "amount_functional": D(amount),
                "trace_node_id": key,
            }
        )
    nodes.append(
        TraceNode(
            "target",
            "posting_target",
            "-6",
            "GBP",
            "post.role_target.v1",
            ("source-1", "source-2"),
            {"signs": "-1|1"},
            "0",
            "post.role_target",
        )
    )
    nodes.append(
        TraceNode(
            "mixed-delta",
            "posting_delta",
            "-6",
            "GBP",
            "post.delta.v1",
            ("target", SourceRef("source_record", "posted/group/period", {"value": "0"})),
            {"previous": "false", "class": "TIME", "time": "-600", "time_previous": "0"},
            "0",
            "post.delta",
        )
    )
    trace = Trace(1, "test", tuple(nodes), {})
    attributed = posting_delta(
        trace, "mixed-delta", movements, currency="GBP", minor_unit=2, paid=()
    )
    assert {
        (item.contract_id, item.balance_role): item.amount for item in attributed.movements
    } == {
        (UUID(int=1), "CONTRACT_LIABILITY"): D("-10"),
        (UUID(int=2), "CONTRACT_ASSET"): D("4"),
    }
    result = project(trace, "target", movements, currency="GBP")
    assert result.amount == D("-6")
    assert {(item.contract_id, item.balance_role): item.amount for item in result.sources} == {
        (UUID(int=1), "CONTRACT_LIABILITY"): D("-10"),
        (UUID(int=2), "CONTRACT_ASSET"): D("4"),
    }


@pytest.mark.parametrize("rate", ["1.1", "1.2"])
def test_zero_settlement_without_movement_row_requires_formula_verification(rate: str) -> None:
    from erev_api.domain.reports.liability_fx_trace import project

    settlement = TraceNode(
        "settlement",
        "fx_layer_remeasured",
        "0.00",
        "USD",
        "fx.settlement.spot.v1",
        (SourceRef("fx_rate", "spot", {"value": rate, "quote": "USD"}),),
        {
            "output": "DIFFERENCE",
            "amount_txn": "400000",
            "open_before": "1000000",
            "carrying_before": "1100000",
            "minor_unit": "2",
            "txn_minor_unit": "2",
            "rate_input": "true",
            "rate": "11/10" if rate == "1.1" else "6/5",
        },
        "0",
        "fx.settlement.spot",
    )
    target = TraceNode(
        "target",
        "posting_target",
        "0.00",
        "USD",
        "post.role_target.v1",
        ("settlement",),
        {"signs": "1"},
        "0",
        "post.role_target",
    )
    trace = Trace(1, "test", (settlement, target), {})
    if rate == "1.1":
        result = project(trace, "target", (), currency="USD")
        assert result.amount == 0 and result.sources == ()
    else:
        with pytest.raises(InvalidLiabilityTrace, match="formula verification"):
            project(trace, "target", (), currency="USD")
