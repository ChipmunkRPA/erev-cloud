"""Native sequential counterfactuals retain offsetting effects and period reconciliation."""

from dataclasses import replace
from datetime import date
from fractions import Fraction

import pytest
from erev_api.domain.reports.modification_causal import calculate
from erev_api.domain.reports.variance_measures import MeasureKey
from erev_api.domain.reports.variance_reporting import Basis
from erev_api.problems import Problem
from erev_engine import compute
from tests.unit.reports.test_modification_event_amounts import _trace


@pytest.mark.parametrize("view", ["transaction", "functional", "reporting"])
@pytest.mark.parametrize("net_zero", [False, True])
def test_original_order_signed_changes_and_period_total(view, net_zero):
    source, keys = _trace(
        foreign=True,
        same_period=True,
        return_input=True,
        second_delta="-20000.00" if net_zero else "-10000.00",
    )
    # Selection order does not override the original ENG-06 event order.
    original = compute(source)
    reporting = Basis(
        "GBP", "USD", "FY2026-P04", date(2026, 4, 30), Fraction("1.25"), Fraction("1.25"), "a" * 64
    )
    executed = []

    def engine(bundle):
        executed.append(bundle)
        return compute(bundle)

    result = calculate(
        source,
        source_output_sha256=original.sha256(),
        selected_event_keys=tuple(reversed(keys)),
        entity_code="US01",
        book_code="ASC606",
        period_key="FY2026-P04",
        currency_view=view,
        reporting_basis=reporting if view == "reporting" else None,
        engine=engine,
    )
    currency = "GBP" if view == "functional" else "USD"
    metric = result.replay.measures[MeasureKey("K-01", currency, "REVENUE")]
    positive = Fraction(8000 if view == "functional" else 10000)
    assert [e.event_keys for e in metric.effects] == [(keys[0],), (keys[1],)]
    assert [e.amount for e in metric.effects] == [
        positive,
        -positive if net_zero else -positive / 2,
    ]
    assert metric.metric_before + sum(e.amount for e in metric.effects) == metric.metric_after
    assert metric.sums_exactly
    assert result.selected_event_keys == tuple(keys)
    assert result.source_output_sha256 == original.sha256()
    assert len(result.replay.executions) == 3
    for bundle in executed[1:]:
        assert bundle.trigger == "DRY_RUN"
        assert replace(bundle, trigger=source.trigger, events=source.events) == source


def test_unselected_modification_remains_a_separate_reconciling_effect():
    source, keys = _trace(foreign=True, same_period=True, return_input=True)
    result = calculate(
        source,
        source_output_sha256=compute(source).sha256(),
        selected_event_keys=(keys[0],),
        entity_code="US01",
        book_code="ASC606",
        period_key="FY2026-P04",
    )
    metric = result.replay.measures[MeasureKey("K-01", "GBP", "REVENUE")]
    assert result.selected_event_keys == (keys[0],)
    assert [(e.event_keys, e.amount) for e in metric.effects] == [
        ((keys[0],), Fraction(8000)),
        ((keys[1],), Fraction(-4000)),
    ]
    assert metric.sums_exactly


def test_retained_output_mismatch_refuses_before_causal_execution():
    source, keys = _trace(same_period=True, return_input=True)
    calls = []

    def engine(bundle):
        calls.append(bundle)
        return compute(bundle)

    with pytest.raises(Problem, match="does not reproduce"):
        calculate(
            source,
            source_output_sha256="0" * 64,
            selected_event_keys=keys,
            entity_code="US01",
            book_code="ASC606",
            period_key="FY2026-P04",
            engine=engine,
        )
    assert len(calls) == 1


def test_delivery_between_modifications_is_not_charged_to_a_modification():
    from tests.engine.s06_modifications.test_s06_prospective import delivered

    source, keys = _trace(foreign=True, same_period=True, return_input=True)
    delivery = delivered(6, "O1", "1", date(2026, 4, 1))
    source = replace(
        source,
        events=tuple(
            sorted(
                (*source.events, delivery),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    result = calculate(
        source,
        source_output_sha256=compute(source).sha256(),
        selected_event_keys=keys,
        entity_code="US01",
        book_code="ASC606",
        period_key="FY2026-P04",
    )
    metric = result.replay.measures[MeasureKey("K-01", "GBP", "REVENUE")]
    assert [(e.event_keys, e.amount) for e in metric.effects] == [
        ((keys[0],), Fraction(8000)),
        ((delivery.event_key,), Fraction(9600)),
        ((keys[1],), Fraction(-4800)),
    ]
    assert metric.sums_exactly
