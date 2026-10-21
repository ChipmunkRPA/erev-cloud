"""Revenue freezes at the original status event, including later events on the same day."""

from dataclasses import replace
from decimal import Decimal

import pytest
from erev_engine import compute
from support.ordered_step1 import EXIT, bundle_at_exit


def revenue_through_february(book):
    return sum(
        schedule.amount
        for schedule in book.schedules
        if schedule.schedule_kind == "REVENUE" and schedule.period_key <= "FY2026-P02"
    )


@pytest.mark.parametrize("kind", ["usage", "estimate", "amendment"])
def test_post_exit_same_day_changes_do_not_rewrite_frozen_revenue(kind):
    baseline = compute(bundle_at_exit("none", after=True)).books[0]
    assert revenue_through_february(baseline) == 10000  # January: 1,200 / 12, in cents.
    earlier = compute(bundle_at_exit(kind, after=False)).books[0]
    later = compute(bundle_at_exit(kind, after=True)).books[0]
    assert revenue_through_february(later) == revenue_through_february(baseline)
    assert revenue_through_february(earlier) > revenue_through_february(baseline)
    assert (
        later.obligation_versions[0].columns["allocated_amount"]
        > (baseline.obligation_versions[0].columns["allocated_amount"])
    )
    if kind == "estimate":
        node = next(
            n
            for n in later.trace.nodes
            if n.params.get("v_new") == "C-STEP1/BASE@v2" and n.measure.startswith("catch_up@")
        )
        assert Decimal(node.value) == 0
        assert node.params["guard"] == "S02-R-05:FROZEN"


def test_later_same_day_reentry_does_not_change_the_prior_estimate_position():
    book = compute(bundle_at_exit("estimate", after=True, reenter=True)).books[0]
    node = next(
        n
        for n in book.trace.nodes
        if n.params.get("v_new") == "C-STEP1/BASE@v2" and n.measure.startswith("catch_up@")
    )
    assert Decimal(node.value) == 0
    assert node.params["guard"] == "S02-R-05:FROZEN"
    assert book.contract_version.columns["status_in_book"] == "ACTIVE"
    baseline = compute(bundle_at_exit("none", after=True)).books[0]
    assert revenue_through_february(book) > revenue_through_february(baseline)


@pytest.mark.parametrize("kind", ["usage", "estimate", "amendment"])
def test_original_positions_keep_same_day_money_separate_from_eligibility(kind):
    from erev_api.domain.reports.rpo_positions import history
    from erev_engine.trace import reevaluate

    book = compute(bundle_at_exit(kind, after=True, reenter=True)).books[0]
    points = next(iter(history(book.trace).values()))
    by_kind = {
        point.event_type: (event, point)
        for (event, side), point in points.items()
        if side == "after" and point.day == EXIT
    }
    money_kind = {
        "usage": "USAGE_REPORTED",
        "estimate": "ESTIMATE_CHANGED",
        "amendment": "CONTRACT_AMENDED",
    }[kind]
    exit_event, exited = by_kind["COLLECTIBILITY_ASSESSED"]
    money_event, money = by_kind[money_kind]
    entry_event, entered = by_kind["CONTRACT_CRITERIA_MET"]
    assert exited.record_seq < money.record_seq < entered.record_seq
    assert exited.revenue == money.revenue == Decimal(100)
    assert entered.revenue > money.revenue
    assert points[money_event, "before"].fixed == exited.fixed == Decimal(1200)
    if kind == "usage":
        assert exited.realised == 0
        assert money.realised == entered.realised == Decimal(60)
        assert money.fixed == Decimal(1200)
    else:
        assert money.fixed == Decimal(1260 if kind == "estimate" else 1320)
    assert points[entry_event, "before"].revenue == money.revenue
    assert points[exit_event, "before"].revenue == exited.revenue
    evaluated = reevaluate(book.trace)
    assert all(evaluated[node.id] == node.value for node in book.trace.nodes)


def test_event_position_reader_refuses_partial_or_changed_original_evidence():
    from erev_api.domain.reports.rpo_positions import history
    from erev_api.problems import Problem

    trace = compute(bundle_at_exit("usage", after=True)).books[0].trace
    node = next(n for n in trace.nodes if n.measure.startswith("rpo_position_fixed@"))
    with pytest.raises(Problem, match="Invalid original RPO"):
        history(replace(trace, nodes=tuple(n for n in trace.nodes if n.id != node.id)))
    with pytest.raises(Problem, match="Invalid original RPO"):
        history(
            replace(
                trace,
                nodes=tuple(replace(n, value="999") if n.id == node.id else n for n in trace.nodes),
            )
        )
