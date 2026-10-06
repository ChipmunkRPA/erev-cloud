"""PROP:P4 schedule bounds (dev-guide §9.7; POLICIES ALG-01 §2.1.3; D-11a; D-79; REQ-REC-019).

The helper part checks ``cumulative_posted`` over generated progress paths (EKC-7). The schedule
part runs stage 09 over generated time-elapsed and units obligations and checks its revenue targets
and ``REVENUE`` schedule lines (ENGINE_SPEC_B §9.2.14, S09-INV-01, S09-INV-02; BUILD_SPEC ENC-10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import accumulate

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.money import cumulative_posted, largest_remainder, period_amounts
from erev_engine.stages.s09_recognition import RecognitionState, run
from erev_engine.stages.state import EventView, ObligationState
from erev_engine.trace import TraceBuilder, reevaluate
from hypothesis import given
from hypothesis import strategies as st
from support.bundles import entity
from support.recognition import CONTRACT_KEY, allocated_state, book_context, event_view, obligation
from support.recognition import segment as allocation_segment
from support.strategies import (
    MINOR_UNITS,
    AllocationCase,
    allocation_cases,
    currencies,
    progress_paths,
)

pytestmark = pytest.mark.property

CALENDAR = entity(start=date(2026, 1, 1), months=24)
FIRST_DAY = date(2026, 1, 1)
O1 = f"{CONTRACT_KEY}/POB-01"


def p04_bound_violations(
    exact: Fraction,
    allocation: int,
    path: Sequence[Fraction],
    minor_unit: int,
    cumulative: Sequence[int],
) -> list[Fraction]:
    """Every f_t < 1 at which |C_t − X × f_t × 10^μ| > 1/2 while no bound binds (D-79 on P4).

    For A ≥ 0 a bound binds when C_t = 0 with X × f_t × 10^μ < 0, or C_t = A with
    X × f_t × 10^μ > A. For A < 0 it binds when C_t = 0 with X × f_t × 10^μ > 0, or C_t = A with
    X × f_t × 10^μ < A.
    """
    scale = 10**minor_unit
    violations: list[Fraction] = []
    for progress, value in zip(path, cumulative, strict=True):
        if progress == 1:
            continue
        target = exact * progress * scale
        if allocation >= 0:
            binds = (value == 0 and target < 0) or (value == allocation and target > allocation)
        else:
            binds = (value == 0 and target > 0) or (value == allocation and target < allocation)
        if not binds and abs(value - target) > Fraction(1, 2):
            violations.append(progress)
    return violations


@given(case=allocation_cases(max_size=12), path=progress_paths(), data=st.data())
def test_p04_helper_bounds(
    case: AllocationCase, path: tuple[Fraction, ...], data: st.DataObject
) -> None:
    posted = largest_remainder(case.total_minor, case.weights, case.keys)
    index = data.draw(st.integers(0, len(case.keys) - 1))
    scale = 10**case.minor_unit
    # X in currency units and A, its largest-remainder posted allocation in minor units.
    exact = Fraction(case.total_minor) * case.weights[index] / sum(case.weights) / scale
    allocation = posted[index]

    amounts = period_amounts(exact, allocation, path, case.minor_unit)
    assert sum(amounts) == allocation
    cumulative = [cumulative_posted(exact, allocation, f, case.minor_unit) for f in path]
    assert list(accumulate(amounts)) == cumulative
    for progress, value in zip(path, cumulative, strict=True):
        if allocation >= 0:
            assert 0 <= value <= allocation
        else:
            assert allocation <= value <= 0
        if progress == 1:
            assert value == allocation
    assert p04_bound_violations(exact, allocation, path, case.minor_unit, cumulative) == []


def test_p04_exemption_rejects_unbound_values() -> None:
    # CHK-004: USD 35,000.00 over 24 equal months; A = 3,500,000 minor units.
    exact, allocation, minor_unit = Fraction(35000), 3_500_000, 2
    path = [Fraction(t, 24) for t in range(1, 25)]

    posted = [cumulative_posted(exact, allocation, f, minor_unit) for f in path]
    assert posted[:3] == [145833, 291667, 437500]
    assert p04_bound_violations(exact, allocation, path, minor_unit, posted) == []

    front_loaded = [allocation] * 24
    violations = p04_bound_violations(exact, allocation, path, minor_unit, front_loaded)
    assert violations[0] == Fraction(1, 24)
    assert violations == path[:23]

    back_loaded = [0] * 23 + [allocation]
    violations = p04_bound_violations(exact, allocation, path, minor_unit, back_loaded)
    assert violations[0] == Fraction(1, 24)
    assert violations == path[:23]


@dataclass(frozen=True, slots=True)
class Stage09Case:
    """One obligation for stage 09: X, A within one minor unit of X, and its measure."""

    currency: str
    method: str  # TIME_ELAPSED | UNITS_DELIVERED
    convention: str | None
    exact: Fraction
    allocation: int
    start: date
    end: date
    quantity: int
    deliveries: tuple[tuple[date, int], ...]


@st.composite
def stage09_cases(draw: st.DrawFn) -> Stage09Case:
    currency = draw(currencies())
    scale = 10 ** MINOR_UNITS[currency]
    exact = Fraction(draw(st.integers(-(10**9), 10**9)), draw(st.integers(1, 10**4)))
    scaled = exact * scale
    floor = scaled.numerator // scaled.denominator
    # A largest-remainder share lies strictly within one minor unit of X × 10^μ (ALG-01 §2.1.2).
    allocation = draw(st.sampled_from(sorted({floor, -(-scaled.numerator // scaled.denominator)})))
    start = FIRST_DAY + timedelta(days=draw(st.integers(0, 364)))
    end = start + timedelta(days=draw(st.integers(0, 364)))
    if draw(st.booleans()):
        convention = draw(st.sampled_from(("DAILY", "MONTHLY_EVEN", "MID_MONTH")))
        return Stage09Case(
            currency, "TIME_ELAPSED", convention, exact, allocation, start, end, 1, ()
        )
    quantity = draw(st.integers(1, 50))
    cuts = (
        draw(st.lists(st.integers(1, quantity - 1), unique=True, max_size=5))
        if quantity > 1
        else []
    )
    bounds = [0, *sorted(cuts), quantity]
    parts = [high - low for low, high in zip(bounds, bounds[1:], strict=False)]
    days = sorted(draw(st.lists(st.integers(0, 729), min_size=len(parts), max_size=len(parts))))
    deliveries = tuple(
        (FIRST_DAY + timedelta(days=day), part) for day, part in zip(days, parts, strict=True)
    )
    return Stage09Case(
        currency, "UNITS_DELIVERED", None, exact, allocation, start, end, quantity, deliveries
    )


def _stage09(case: Stage09Case) -> RecognitionState:
    ob: ObligationState
    events: list[EventView] = []
    if case.method == "TIME_ELAPSED":
        seg = allocation_segment(case.exact, case.allocation, start=case.start, end=case.end)
        ob = obligation("POB-01", [seg], convention=case.convention)
    else:
        seg = allocation_segment(
            case.exact,
            case.allocation,
            start=case.start,
            end=case.end,
            quantity=Fraction(case.quantity),
            measure="UNITS_DELIVERED",
        )
        ob = obligation(
            "POB-01",
            [seg],
            method="UNITS_DELIVERED",
            convention=None,
            quantity=Fraction(case.quantity),
        )
        for version, (when, units) in enumerate(case.deliveries, start=2):
            payload = {
                "obligation_key": "POB-01",
                "quantity": Decimal(units),
                "trigger": "DELIVERY",
            }
            events.append(
                event_view(
                    CONTRACT_KEY,
                    version,
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


@given(case=stage09_cases())
def test_p04_stage09_schedules(case: Stage09Case) -> None:
    state = _stage09(case)
    minor_unit = MINOR_UNITS[case.currency]
    targets = [target for target in state.revenue_targets if target.subject_key == O1]
    cumulative = [target.value for target in targets]
    allocation = case.allocation

    # The schedule lines sum to the allocation at completion.
    assert cumulative[-1] == allocation
    assert sum(line.amount for line in state.schedule_lines) == allocation
    for value in cumulative:
        if allocation >= 0:
            assert 0 <= value <= allocation
        else:
            assert allocation <= value <= 0
    running = dict(
        zip(
            [line.period_key for line in state.schedule_lines],
            accumulate(line.amount for line in state.schedule_lines),
            strict=True,
        )
    )
    by_period = {target.period_key: target.value for target in targets}
    assert all(by_period[period_key] == value for period_key, value in running.items())
    if case.exact != 0:
        path = []
        for target in targets:
            assert target.exact is not None
            path.append(target.exact / case.exact)  # E = X × f_t
        assert p04_bound_violations(case.exact, allocation, path, minor_unit, cumulative) == []
