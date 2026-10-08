"""Independent RPO closing and movement checks for realized usage consideration (B4-2)."""

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.stages.s09_recognition import run
from erev_engine.stages.s15_disclosures.rpo import rollforward
from erev_engine.stages.state import AllocatedState, BookContext
from erev_engine.trace import TraceBuilder, reevaluate
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
)


def _world(fee: int, held: bool = False) -> tuple[BookContext, AllocatedState]:
    ctx = book_context(
        horizon="FY2026-P06",
        overrides=[("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")],
    )
    segments = [
        segment(
            Fraction(fee),
            fee * 100,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            measure="USAGE",
        ),
        segment(
            Fraction(0),
            0,
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            component="PERIOD_VC",
            measure="USAGE",
        ),
    ]
    usage = event_view(
        CONTRACT_KEY,
        2,
        "USAGE_REPORTED",
        date(2026, 3, 31),
        {
            "obligation_key": "POB-01",
            "usage_period_start": date(2026, 3, 1),
            "usage_period_end": date(2026, 3, 31),
            "metric": "API_CALLS",
            "quantity": Decimal("3000"),
            "rated_amount": Decimal("150.00"),
        },
        obligation_keys=["POB-01"],
    )
    events = [usage]
    if held:
        events.append(
            event_view(
                CONTRACT_KEY,
                3,
                "HOLD_APPLIED",
                date(2026, 3, 1),
                {
                    "hold_type": "recognition",
                    "hold_source": "MANUAL",
                    "reason": "Customer acceptance dispute",
                    "obligation_key": "POB-01",
                },
                obligation_keys=["POB-01"],
            )
        )
    st = allocated_state(
        [obligation("POB-01", segments, method="USAGE", convention=None)], events=events
    )
    return ctx, st


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("fee", [0, 12000])
def test_realized_usage_is_added_and_does_not_reduce_fixed_remaining(fee: int, held: bool) -> None:
    ctx, st = _world(fee, held)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    realised = {
        node.id.rpartition(":")[2]: node.value
        for node in trace.nodes
        if node.measure == "realised_allocation"
    }
    assert realised["FY2026-P01"] == "0.00"
    assert realised["FY2026-P02"] == "0.00"
    assert realised["FY2026-P03"] == "150.00"
    assert realised["-"] == "150.00"
    fixed = {
        node.params["source_node"]: Decimal(node.value)
        for node in trace.nodes
        if node.measure == "scheduled_fixed_amount"
    }
    march_parts = [value for source, value in fixed.items() if source.endswith(":FY2026-P03")]
    assert march_parts == ([] if held else [Decimal(fee) / 12])
    measures = recognition.obligation_measures[f"{CONTRACT_KEY}/POB-01"]
    # Without a hold, nine fixed-fee portions remain; with a hold, ten plus the unrecognized fee.
    expected_closing = fee * 100 * 10 // 12 + 15000 if held else fee * 75
    assert measures.scheduled_amount + measures.awaiting_trigger_amount == expected_closing
    march = rollforward(ctx, st, recognition, "US01", "FY2026-P03")
    assert march.lines["OPENING"] == fee * 100 * 10 // 12
    assert march.lines["CLOSING"] == expected_closing
    assert march.lines["VC_ESTIMATE_CHANGES"] == 15000
    assert march.lines["REVENUE"] == (0 if held else -(fee * 100 // 12 + 15000))
    assert march.lines["UNEXPLAINED"] == 0
    april = rollforward(ctx, st, recognition, "US01", "FY2026-P04")
    assert april.lines["OPENING"] == expected_closing
    assert april.lines["CLOSING"] == (expected_closing if held else fee * 100 * 8 // 12)
    assert april.lines["VC_ESTIMATE_CHANGES"] == 0
    assert april.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize("entered", [False, True])
def test_realized_usage_respects_step_one_entry(entered: bool) -> None:
    ctx, st = _world(12000)
    history = [(date(2026, 1, 1), "NOT_A_CONTRACT")]
    if entered:
        history.append((date(2026, 3, 1), "ACTIVE"))
    contract = dataclasses.replace(st.contracts[0], status_in_book={"ASC606": tuple(history)})
    st = dataclasses.replace(st, contracts=(contract,))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = run(ctx, st, tb)
    march = rollforward(ctx, st, recognition, "US01", "FY2026-P03")
    if not entered:
        assert set(march.lines.values()) == {0}
    else:
        assert march.lines["OPENING"] == 0
        assert march.lines["NEW_CONTRACTS"] == 1200000
        assert march.lines["VC_ESTIMATE_CHANGES"] == 15000
        assert march.lines["UNEXPLAINED"] == 0
        measures = recognition.obligation_measures[f"{CONTRACT_KEY}/POB-01"]
        assert (
            march.lines["CLOSING"] == measures.scheduled_amount + measures.awaiting_trigger_amount
        )
