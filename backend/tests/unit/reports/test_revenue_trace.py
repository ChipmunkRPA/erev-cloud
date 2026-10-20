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


@pytest.mark.parametrize("basis, expected", [("ALL", 40), ("TIME", 20), ("EVENT", 20)])
def test_target_prior_and_paid_preserve_reversal_owners(basis: str, expected: int) -> None:
    from datetime import date

    from erev_api.domain.reports.revenue_trace import (
        RevenueMovement,
        RevenueTarget,
        posting_delta,
    )

    def movement(owner: int, amount: int, time: bool = False) -> RevenueMovement:
        return RevenueMovement(
            UUID(int=owner),
            f"layer-{owner}",
            "ASSET_LAYER_SETTLED" if owner == 3 else "LIABILITY_LAYER_CREATED",
            date(2026, 8, 31),
            f"event-{owner}",
            time,
            Fraction(amount),
        )

    # The same historical revenue in both targets cancels, even when its
    # retained movement row belongs to a different computation version.
    prior = RevenueTarget(Fraction(-100), Fraction(0), (movement(1, -100),), (UUID(int=10),))
    current = RevenueTarget(
        Fraction(0),
        Fraction(20),
        (movement(1, -100), movement(3, 20, True), movement(4, 80)),
        (UUID(int=11), UUID(int=12), UUID(int=13)),
    )
    paid = () if basis == "TIME" else (movement(4, 60),)
    result = posting_delta(
        current,
        prior,
        basis=basis,
        paid=paid,
        expected_paid=Fraction(0 if basis == "TIME" else 60),
        expected_delta=Fraction(expected),
    )
    assert result.amount == expected
    assert {item.contract_id: item.amount for item in result.movements} == (
        {UUID(int=3): 20, UUID(int=4): 20}
        if basis == "ALL"
        else {UUID(int=3 if basis == "TIME" else 4): 20}
    )
    assert result.source_ids == tuple(UUID(int=i) for i in (10, 11, 12, 13))


@pytest.mark.parametrize("corruption", ["target", "time", "paid", "basis", "delta"])
def test_posted_delta_refuses_unreconciled_components(corruption: str) -> None:
    from dataclasses import replace
    from datetime import date

    from erev_api.domain.reports.revenue_trace import (
        RevenueMovement,
        RevenueTarget,
        posting_delta,
    )

    item = RevenueMovement(
        UUID(int=1),
        "layer",
        "LIABILITY_LAYER_CONSUMED",
        date(2026, 8, 31),
        "event",
        False,
        Fraction(-80),
    )
    target = RevenueTarget(Fraction(-80), Fraction(0), (item,), (UUID(int=2),))
    paid = (replace(item, amount=Fraction(-20)),)
    expected_paid, expected_delta = Fraction(-20), Fraction(-60)
    if corruption == "target":
        target = replace(target, amount=Fraction(-81))
    elif corruption == "time":
        target = replace(target, time_amount=Fraction(-80))
    elif corruption == "paid":
        expected_paid = Fraction(-19)
    elif corruption == "basis":
        paid = (replace(paid[0], time=True),)
    else:
        expected_delta = Fraction(-59)
    with pytest.raises(InvalidRevenueTrace):
        posting_delta(
            target,
            None,
            basis="EVENT",
            paid=paid,
            expected_paid=expected_paid,
            expected_delta=expected_delta,
        )


def test_zero_functional_rounding_keeps_the_transaction_source_sign() -> None:
    from dataclasses import replace

    trace, movements = sources()
    leaf = replace(trace.nodes[0], value="0")
    root = replace(trace.nodes[-1], value="0", inputs=(leaf.id,), params={"signs": "-1"})
    movements = [{**movements[0], "amount_functional": Decimal(0), "amount_txn": Decimal("0.01")}]
    result = project(replace(trace, nodes=(leaf, root)), root.id, movements, currency="GBP")
    assert len(result) == 1
    assert result[0].amount == 0
    assert result[0].coefficient == -1
    assert result[0].movement_id == movements[0]["id"]


def test_input_classes_require_original_unmixed_sources() -> None:
    from erev_api.domain.reports.revenue_trace import input_classes

    assert input_classes({}, 2, Fraction(100), Fraction(0)) == (False, False)
    assert input_classes({}, 2, Fraction(100), Fraction(100)) == (True, True)
    with pytest.raises(InvalidRevenueTrace, match="retained component"):
        input_classes({}, 2, Fraction(100), Fraction(40))
    for classes, count in (("MIXED", 1), ("TIME|EVENT", 1), ("TIME", 0)):
        with pytest.raises(InvalidRevenueTrace, match="unambiguous"):
            input_classes(
                {"input_classes": classes, "time_functional": "10"}, count, Fraction(0), Fraction(0)
            )
    # Zero transaction revenue can retain a functional TIME residual.
    assert input_classes(
        {"input_classes": "TIME", "time_functional": "10"}, 1, Fraction(0), Fraction(0)
    ) == (True,)


@pytest.mark.parametrize("total,time", [(60, 100), (-80, -31), (0, 5)])
def test_mixed_input_uses_exact_amounts_only_for_one_original_source(total, time) -> None:
    from dataclasses import replace

    from erev_api.domain.reports.revenue_trace import RevenueSource, split_single_origin

    source = RevenueSource(
        UUID(int=1), UUID(int=2), "layer", "LIABILITY_LAYER_CONSUMED", Fraction(total)
    )
    result = split_single_origin([source], total=Fraction(total), time=Fraction(time))
    assert sum(item.amount for item in result) == total
    assert sum(item.amount for item in result if item.time) == time
    assert all(
        item.contract_id == source.contract_id and item.layer_key == "layer" for item in result
    )
    for other in (
        replace(source, contract_id=UUID(int=3)),
        replace(source, layer_key="other"),
        replace(source, source_key="other-origin"),
    ):
        with pytest.raises(InvalidRevenueTrace, match="unique original"):
            split_single_origin([source, other], total=Fraction(total), time=Fraction(time))
    with pytest.raises(InvalidRevenueTrace, match="unique original"):
        split_single_origin([], total=Fraction(total), time=Fraction(time))
