"""Revenue sources keep asset creation and negative credits, even at net zero."""

from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest
from erev_api.domain.reports.revenue_trace import InvalidRevenueTrace, project
from erev_engine.trace import Trace, TraceNode


def sources() -> tuple[Trace, list[dict]]:
    nodes = []
    movements = []
    for index, (key, role, kind, formula, amount) in enumerate(
        (
            (
                "relief",
                "CONTRACT_LIABILITY",
                "LIABILITY_LAYER_CONSUMED",
                "fx.layer.consume.fifo.v1",
                "80",
            ),
            ("asset", "CONTRACT_ASSET", "ASSET_LAYER_CREATED", "fx.asset_layer.create.v1", "20"),
            ("settled", "CONTRACT_ASSET", "ASSET_LAYER_SETTLED", "fx.settlement.spot.v1", "20"),
            ("credit", "CONTRACT_LIABILITY", "LIABILITY_LAYER_CREATED", "fx.layer.create.v1", "80"),
        ),
        1,
    ):
        nodes.append(TraceNode(key, key, amount, "GBP", formula, (), {}, "0", formula[:-3]))
        movements.append(
            {
                "id": UUID(int=index),
                "contract_id": UUID(int=index),
                "layer_key": key,
                "balance_role": role,
                "movement_kind": kind,
                "functional_currency": "GBP",
                "amount_functional": Decimal(amount),
                "trace_node_id": key,
            }
        )
    for key, amount, children, signs in (
        ("prior", "100", ("relief", "asset"), "1|1"),
        ("current", "0", ("prior", "settled", "credit"), "1|-1|-1"),
    ):
        nodes.append(
            TraceNode(
                key,
                "revenue_functional",
                amount,
                "GBP",
                "fx.revenue_functional.v1",
                children,
                {"signs": signs, "minor_unit": "2"},
                "0",
                "fx.revenue_functional",
            )
        )
    return Trace(1, "test", tuple(nodes), {}), movements


def test_signed_sources_preserve_owner_and_control_role_at_net_zero() -> None:
    trace, movements = sources()
    result = project(trace, "current", movements, currency="GBP")
    assert sum((part.amount for part in result), Fraction()) == 0
    assert {part.contract_id: part.amount for part in result} == {
        UUID(int=1): 80,
        UUID(int=2): 20,
        UUID(int=3): -20,
        UUID(int=4): -80,
    }
    assert {part.movement_kind for part in result} == {
        "LIABILITY_LAYER_CONSUMED",
        "ASSET_LAYER_CREATED",
        "ASSET_LAYER_SETTLED",
        "LIABILITY_LAYER_CREATED",
    }


@pytest.mark.parametrize("corruption", ["amount", "missing", "duplicate", "currency", "cycle"])
def test_corrupt_source_cannot_hide_in_zero_target(corruption: str) -> None:
    from dataclasses import replace

    trace, movements = sources()
    if corruption == "amount":
        movements[0]["amount_functional"] = Decimal(81)
    elif corruption == "missing":
        movements.pop(0)
    elif corruption == "duplicate":
        movements.append(movements[0])
    elif corruption == "currency":
        movements[0]["functional_currency"] = "USD"
    else:
        nodes = list(trace.nodes)
        nodes[-2] = replace(nodes[-2], inputs=("current",), params={"signs": "1"})
        trace = replace(trace, nodes=tuple(nodes))
    with pytest.raises(InvalidRevenueTrace):
        project(trace, "current", movements, currency="GBP")
