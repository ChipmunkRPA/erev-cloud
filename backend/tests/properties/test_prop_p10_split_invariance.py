"""PROP:P10 split invariance (dev-guide §9.7; ENGINE_SPEC_B §9.2.4, S09-INV-12; BUILD_SPEC ENC-10).

One delivery of q on a date gives the same stage 09 targets, causes, schedule lines and obligation
measures as deliveries q1 + q2 = q on that date, under the units and point-in-time measures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.stages.s09_recognition import RecognitionState, run
from erev_engine.stages.state import EventView
from erev_engine.trace import TraceBuilder, reevaluate
from hypothesis import given
from hypothesis import strategies as st
from support.bundles import entity
from support.recognition import CONTRACT_KEY, allocated_state, book_context, event_view, obligation
from support.recognition import segment as allocation_segment
from support.strategies import MINOR_UNITS, currencies

pytestmark = pytest.mark.property

CALENDAR = entity(start=date(2026, 1, 1), months=12)
FIRST_DAY = date(2026, 1, 1)
O1 = f"{CONTRACT_KEY}/POB-01"


@dataclass(frozen=True, slots=True)
class SplitCase:
    currency: str
    method: str  # UNITS_DELIVERED | POINT_IN_TIME
    exact: Fraction
    allocation: int
    quantity: int
    deliveries: tuple[tuple[date, int], ...]  # (date, units in hundredths)
    split: int  # index of the delivery recorded as two events
    first: int  # q1 in hundredths, 0 < q1 < q


@st.composite
def split_cases(draw: st.DrawFn) -> SplitCase:
    currency = draw(currencies())
    scale = 10 ** MINOR_UNITS[currency]
    exact = Fraction(draw(st.integers(-(10**8), 10**8)), draw(st.integers(1, 1000)))
    scaled = exact * scale
    allocation = draw(
        st.sampled_from(
            sorted(
                {scaled.numerator // scaled.denominator, -(-scaled.numerator // scaled.denominator)}
            )
        )
    )
    count = draw(st.integers(1, 4))
    days = sorted(draw(st.lists(st.integers(0, 364), min_size=count, max_size=count)))
    units = draw(st.lists(st.integers(2, 20_000), min_size=count, max_size=count))
    split = draw(st.integers(0, count - 1))
    return SplitCase(
        currency=currency,
        method=draw(st.sampled_from(("UNITS_DELIVERED", "POINT_IN_TIME"))),
        exact=exact,
        allocation=allocation,
        quantity=draw(st.integers(1, 500)),
        deliveries=tuple(
            (FIRST_DAY + timedelta(days=day), hundredths)
            for day, hundredths in zip(days, units, strict=True)
        ),
        split=split,
        first=draw(st.integers(1, units[split] - 1)),
    )


def _run(case: SplitCase, *, split: bool) -> RecognitionState:
    goods = allocation_segment(
        case.exact,
        case.allocation,
        start=FIRST_DAY,
        end=date(2026, 12, 31),
        quantity=Fraction(case.quantity),
        measure=case.method,
    )
    ob = obligation(
        "POB-01", [goods], method=case.method, convention=None, quantity=Fraction(case.quantity)
    )
    events: list[EventView] = []
    for index, (when, hundredths) in enumerate(case.deliveries):
        parts = [hundredths]
        if split and index == case.split:
            parts = [case.first, hundredths - case.first]
        for part in parts:
            payload = {
                "obligation_key": "POB-01",
                "quantity": Decimal(part).scaleb(-2),
                "trigger": "DELIVERY",
            }
            events.append(
                event_view(
                    CONTRACT_KEY,
                    len(events) + 2,
                    "DELIVERY_RECORDED",
                    when,
                    payload,
                    obligation_keys=["POB-01"],
                )
            )
    ctx = book_context(CALENDAR, currency=case.currency)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = run(ctx, allocated_state([ob], events=events), tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state


@given(case=split_cases())
def test_p10_split_invariance(case: SplitCase) -> None:
    whole = _run(case, split=False)
    parts = _run(case, split=True)
    assert [(t.period_key, t.value, t.exact) for t in whole.revenue_targets] == [
        (t.period_key, t.value, t.exact) for t in parts.revenue_targets
    ]
    assert [(t.period_key, t.cause, t.value) for t in whole.revenue_by_cause] == [
        (t.period_key, t.cause, t.value) for t in parts.revenue_by_cause
    ]
    assert [
        (line.period_key, line.line_type, line.amount, line.cumulative_exact, line.quantity)
        for line in whole.schedule_lines
    ] == [
        (line.period_key, line.line_type, line.amount, line.cumulative_exact, line.quantity)
        for line in parts.schedule_lines
    ]
    one, two = whole.obligation_measures[O1], parts.obligation_measures[O1]
    for name in (
        "as_of",
        "allocated_amount",
        "progress_ratio",
        "revenue_cum",
        "remaining_allocation",
        "remaining_quantity",
        "scheduled_amount",
        "awaiting_trigger_amount",
        "satisfaction_status",
        "satisfied_date",
        "delivered_quantity",
        "revenue_amount",
        "ssp_delivered_cum",
    ):
        assert getattr(one, name) == getattr(two, name), name
