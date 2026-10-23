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


@pytest.mark.parametrize("view", ["transaction", "functional"])
@pytest.mark.parametrize("sign", [1, -1])
def test_mixed_period_sources_preserve_distinct_owners(view: str, sign: int) -> None:
    import json
    from dataclasses import replace

    from erev_api.domain.reports.revenue_trace import RevenueSource, split_mixed_sources

    sources = (
        RevenueSource(
            UUID(int=1),
            UUID(int=11),
            "a",
            "LIABILITY_LAYER_CONSUMED",
            Fraction(80),
            source_key="ob@P1",
        ),
        RevenueSource(
            UUID(int=2),
            UUID(int=22),
            "b",
            "LIABILITY_LAYER_CONSUMED",
            Fraction(40),
            source_key="ob@P1",
        ),
        RevenueSource(
            UUID(int=3),
            UUID(int=33),
            "c",
            "ASSET_LAYER_SETTLED",
            Fraction(-24),
            source_key="ob@P2",
            coefficient=-1,
        ),
    )
    amounts = {UUID(int=1): Fraction(100), UUID(int=2): Fraction(50), UUID(int=3): Fraction(30)}
    params = {"input_period_classes": json.dumps([{"P1": "TIME", "P2": "EVENT"}])}

    def split(held=sources, config=params, time_functional=Fraction(120 * sign)):
        return split_mixed_sources(
            held,
            params=config,
            count=1,
            index=0,
            subject="ob",
            sign=sign,
            transaction_amounts=amounts,
            time_txn=Fraction(150 * sign),
            time_functional=time_functional,
            view=view,
        )

    result = split()
    assert [item.contract_id for item in result] == [UUID(int=x) for x in (11, 22, 33)]
    assert [item.layer_key for item in result] == ["a", "b", "c"]
    assert [item.time for item in result] == [True, True, False]
    assert [item.amount for item in result] == [
        sign * Fraction(x) for x in ((100, 50, -30) if view == "transaction" else (80, 40, -24))
    ]
    assert [item.contract_id.int for item in split(held=(sources[0], sources[2], sources[1]))] == [
        11,
        33,
        22,
    ]
    with pytest.raises(InvalidRevenueTrace, match="either currency"):
        split(time_functional=Fraction(119 * sign))
    with pytest.raises(InvalidRevenueTrace, match="finer source"):
        split(config={"input_period_classes": '[{"P1":"MIXED","P2":"EVENT"}]'})
    with pytest.raises(InvalidRevenueTrace, match="recognition period"):
        split(held=(replace(sources[0], source_key="another@P1"), *sources[1:]))
    with pytest.raises(InvalidRevenueTrace, match="retained period"):
        split(config={})


@pytest.mark.parametrize("view", ["transaction", "functional"])
@pytest.mark.parametrize("classification", ["TIME", "EVENT", "MIXED"])
def test_split_role_replays_original_rounding_and_preserves_source(
    view: str, classification: str
) -> None:
    from dataclasses import replace

    from erev_api.domain.reports.revenue_trace import split_role_target

    original = {
        "id": UUID(int=1),
        "contract_id": UUID(int=9),
        "layer_key": "original-layer",
        "balance_role": "CONTRACT_LIABILITY",
        "movement_kind": "LIABILITY_LAYER_CONSUMED",
        "trace_node_id": "relief",
        "functional_currency": "GBP",
        "amount_txn": Decimal("100.01"),
        "amount_functional": Decimal("80.00"),
        "source_key": "ob@P1",
    }
    time_txn, time_fn = {"TIME": (-3334, -2667), "EVENT": (0, 0), "MIXED": (-1000, -800)}[
        classification
    ]
    params = {
        "signs": "1",
        "minor_unit": "2",
        "weights": "1/3|2/3",
        "keys": "REVENUE|SUPPLIER",
        "index": "0",
        "side": "-1",
        "amount_functional": "-2667",
        "time": str(time_txn),
        "time_functional": str(time_fn),
        "input_classes": classification,
        "input_time_txn": str(time_txn),
        "input_time_functional": str(time_fn),
    }
    nodes = (
        TraceNode(
            "revenue_cum:ob:P1",
            "revenue_cum",
            "100.01",
            "USD",
            "input.echo.v1",
            (),
            {},
            "0",
            "input.echo",
        ),
        TraceNode(
            "relief",
            "fx_layer_consumed",
            "80.00",
            "GBP",
            "fx.layer.consume.fifo.v1",
            (),
            {},
            "0",
            "fx.layer.consume.fifo",
        ),
        TraceNode(
            "revenue_functional:ob:P1",
            "revenue_functional",
            "80.00",
            "GBP",
            "fx.revenue_functional.v1",
            ("relief",),
            {"signs": "1"},
            "0",
            "fx.revenue_functional",
        ),
        TraceNode(
            "split",
            "posting_target",
            "-33.34",
            "USD",
            "post.role_target.v1",
            ("revenue_cum:ob:P1",),
            params,
            "0",
            "post.role_target",
        ),
    )

    def read(held=nodes, rows=(original,), *, attribute=True, period_ends=None):
        return split_role_target(
            Trace(1, "test", tuple(held), {}),
            "split",
            rows,
            currency="GBP",
            txn_scale=2,
            functional_scale=2,
            view=view,
            attribute=attribute,
            period_ends=period_ends,
        )

    result = read()
    assert result.amount == Fraction("-33.34" if view == "transaction" else "-26.67")
    assert result.time_amount == Fraction(time_txn if view == "transaction" else time_fn, 100)
    assert sum(item.amount for item in result.movements) == result.amount
    assert {item.contract_id for item in result.movements} == {UUID(int=9)}
    assert {item.layer_key for item in result.movements} == {"original-layer"}
    assert result.source_ids == (UUID(int=1),)
    split_sources = (
        nodes[0],
        replace(nodes[1], value="40.00"),
        replace(nodes[1], id="relief-two", value="40.00"),
        replace(nodes[2], inputs=("relief", "relief-two"), params={"signs": "1|1"}),
        nodes[3],
    )
    split_rows = (
        {**original, "amount_txn": "50.00", "amount_functional": "40.00"},
        {
            **original,
            "id": UUID(int=2),
            "layer_key": "other-layer",
            "trace_node_id": "relief-two",
            "amount_txn": "50.01",
            "amount_functional": "40.00",
        },
    )
    with pytest.raises(InvalidRevenueTrace, match="unique original source"):
        read(split_sources, split_rows)
    # A role explicitly switched to zero weight must reverse its earlier share,
    # even after additional original layers enter the gross population.
    zero_params = {
        **params,
        "weights": "0|1",
        "amount_functional": "0",
        "time": "0",
        "time_functional": "0",
        "input_time_txn": "0",
        "input_time_functional": "0",
    }
    zero_nodes = (*split_sources[:-1], replace(nodes[-1], value="0", params=zero_params))
    zero = read(zero_nodes, split_rows)
    assert zero.amount == zero.time_amount == 0
    assert zero.movements == ()
    assert zero.source_ids == (UUID(int=1), UUID(int=2))
    from erev_api.domain.reports.revenue_trace import posting_delta

    reversal = posting_delta(
        zero,
        result,
        basis="ALL",
        paid=(),
        expected_paid=Fraction(0),
        expected_delta=-result.amount,
    )
    assert reversal.amount == -result.amount
    assert {item.layer_key for item in reversal.movements} == {"original-layer"}
    # A small nonzero weight rounded to zero does not erase source ambiguity.
    with pytest.raises(InvalidRevenueTrace, match="unique original source"):
        read(
            (
                *zero_nodes[:-1],
                replace(
                    zero_nodes[-1],
                    params={
                        **zero_params,
                        "weights": "1/1000000|1",
                    },
                ),
            ),
            split_rows,
        )
    with pytest.raises(InvalidRevenueTrace, match="transaction sources"):
        read(zero_nodes, ({**split_rows[0], "amount_txn": "49.99"}, split_rows[1]))
    with pytest.raises(InvalidRevenueTrace, match="formula or TIME"):
        read(
            (
                *zero_nodes[:-1],
                replace(
                    zero_nodes[-1],
                    params={
                        **zero_params,
                        "amount_functional": "1",
                    },
                ),
            ),
            split_rows,
        )
    scalar = read(split_sources, split_rows, attribute=False)
    assert scalar.amount == result.amount and scalar.time_amount == result.time_amount
    assert not scalar.movements
    from erev_api.domain.reports.revenue_trace import posting_delta

    with pytest.raises(InvalidRevenueTrace, match="sources do not reproduce"):
        posting_delta(
            scalar,
            None,
            basis="ALL",
            paid=(),
            expected_paid=Fraction(0),
            expected_delta=scalar.amount,
        )
    with pytest.raises(InvalidRevenueTrace, match="formula or TIME"):
        read(
            (
                *split_sources[:-1],
                replace(split_sources[-1], params={**params, "amount_functional": "-2666"}),
            ),
            split_rows,
            attribute=False,
        )
    with pytest.raises(InvalidRevenueTrace, match="formula or TIME"):
        read((*nodes[:-1], replace(nodes[-1], params={**params, "amount_functional": "-2666"})))
    with pytest.raises(InvalidRevenueTrace, match="transaction sources"):
        read(rows=({**original, "amount_txn": "100.00"},))

    if classification == "EVENT":
        from datetime import date

        empty = (
            replace(nodes[0], value="0.00"),
            replace(nodes[-1], value="0.00", params={**params, "amount_functional": "0"}),
        )
        dates = {"P0": date(2026, 1, 31), "P1": date(2026, 2, 28)}
        baseline = read(empty, (), period_ends=dates)
        assert baseline.amount == baseline.time_amount == 0
        assert not baseline.movements and not baseline.source_ids
        with pytest.raises(InvalidRevenueTrace, match="source history"):
            read(empty, ())
        with pytest.raises(InvalidRevenueTrace, match="source history"):
            read((*empty, replace(nodes[2], id="revenue_functional:ob:P0")), (), period_ends=dates)


@pytest.mark.parametrize("view", ["transaction", "functional"])
@pytest.mark.parametrize("sign", [1, -1])
def test_mixed_period_retains_exact_time_for_one_period_origin(view: str, sign: int) -> None:
    import json
    from dataclasses import replace

    from erev_api.domain.reports.revenue_trace import RevenueSource, split_mixed_sources

    sources = (
        RevenueSource(
            UUID(int=1),
            UUID(int=11),
            "a",
            "LIABILITY_LAYER_CONSUMED",
            Fraction(80),
            source_key="ob@P1",
        ),
        RevenueSource(
            UUID(int=2),
            UUID(int=22),
            "b",
            "LIABILITY_LAYER_CONSUMED",
            Fraction(42),
            source_key="ob@P2",
        ),
    )
    amounts = {UUID(int=1): Fraction(100), UUID(int=2): Fraction(50)}
    params = {
        "input_period_classes": '[{"P1":"TIME","P2":"MIXED"}]',
        "input_period_time": json.dumps(
            [{"P1": [str(100 * sign), str(80 * sign)], "P2": [str(20 * sign), str(17 * sign)]}]
        ),
    }

    def project(held=sources, config=params):
        return split_mixed_sources(
            held,
            params=config,
            count=1,
            index=0,
            subject="ob",
            sign=sign,
            transaction_amounts=amounts,
            time_txn=Fraction(120 * sign),
            time_functional=Fraction(97 * sign),
            view=view,
        )

    result = project()
    assert [(item.contract_id.int, item.time, item.amount) for item in result] == [
        (11, True, sign * Fraction(100 if view == "transaction" else 80)),
        (22, True, sign * Fraction(20 if view == "transaction" else 17)),
        (22, False, sign * Fraction(30 if view == "transaction" else 25)),
    ]
    changed = {
        **params,
        "input_period_time": json.dumps([{"P2": [str(20 * sign), str(18 * sign)]}]),
    }
    with pytest.raises(InvalidRevenueTrace, match="either currency"):
        project(config=changed)
    with pytest.raises(InvalidRevenueTrace, match="unique original"):
        project(held=(*sources, replace(sources[1], contract_id=UUID(int=33))))
    with pytest.raises(InvalidRevenueTrace, match="finer source"):
        project(config={"input_period_classes": params["input_period_classes"]})


@pytest.mark.parametrize("corruption", [None, "amount", "currency", "scale", "missing", "row"])
def test_cumulative_transaction_evidence_is_verified(corruption: str | None) -> None:
    from dataclasses import replace

    trace, rows = sources()
    rows = [dict(row, amount_txn=row["amount_functional"], txn_currency="GBP") for row in rows]
    nodes = []
    for node in trace.nodes:
        if node.formula_id == "fx.revenue_functional.v1":
            params = {
                **node.params,
                "amount_txn": str(int(Fraction(node.value) * 100)),
                "txn_currency": "GBP",
                "txn_minor_unit": "2",
            }
            if node.id == "prior":
                if corruption == "amount":
                    params["amount_txn"] = "9999"
                elif corruption == "currency":
                    params["txn_currency"] = "USD"
                elif corruption == "scale":
                    params["txn_minor_unit"] = "3"
                elif corruption == "missing":
                    del params["amount_txn"]
            node = replace(node, params=params)
        nodes.append(node)
    if corruption == "row":
        rows[0]["amount_txn"] = Decimal("79.99")
    updated = replace(trace, nodes=tuple(nodes))
    if corruption:
        with pytest.raises(InvalidRevenueTrace, match="transaction evidence"):
            project(updated, "current", rows, currency="GBP")
    else:
        result = project(updated, "current", rows, currency="GBP")
        assert sum(item.amount for item in result) == 0
        assert len(result) == 4  # opposing signed sources survive a net-zero target
