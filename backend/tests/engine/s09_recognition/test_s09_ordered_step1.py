"""Revenue freezes at the original status event, including later events on the same day."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_engine import compute
from support import allocation_worlds, cpc_worlds
from support import step1_worlds as worlds

JAN = date(2026, 1, 1)
EXIT = date(2026, 2, 10)


def bundle_at_exit(kind, *, after, reenter=False):
    bundle = worlds.time_world(
        paid=None,
        steps=[("C", JAN, "")],
        template_changes={"recognition_method": "USAGE"} if kind == "usage" else {},
    )
    events = list(bundle.events)
    estimates = []
    if kind == "estimate":
        initial = replace(
            allocation_worlds.untargeted_element(),
            estimate_key="C-STEP1/BASE",
            version_key="C-STEP1/BASE@v1",
        )
        estimates = [initial, allocation_worlds.later_version(initial, 2, EXIT, "60")]
        events = cpc_worlds.pinned(events, initial)
    amendments = []
    events = worlds.significant_change(events, EXIT, "Customer deterioration")
    if after:
        events = worlds.not_probable(events, EXIT)
    if kind == "usage":
        events = cpc_worlds.then(
            events,
            "USAGE_REPORTED",
            EXIT,
            {
                "obligation_key": worlds.SERVICE,
                "usage_period_start": date(2026, 2, 1),
                "usage_period_end": EXIT,
                "metric": "CALLS",
                "quantity": Decimal(10),
                "rated_amount": Decimal(60),
            },
        )
    elif kind == "estimate":
        events = cpc_worlds.pinned(events, estimates[1])
    elif kind == "amendment":
        amendment = cpc_worlds.concession("120", EXIT, key=worlds.SERVICE)
        amendment = replace(
            amendment,
            price_change_amount=None,
            lines=tuple({**line, "product_code": "SERVICE"} for line in amendment.lines),
        )
        amendments.append(amendment)
        events = cpc_worlds.amended(events, amendment)
    if not after:
        events = worlds.not_probable(events, EXIT)
    if reenter:
        events = worlds.criteria_met(events, EXIT)
    return replace(
        bundle,
        events=tuple(events),
        estimate_versions=tuple(estimates),
        contracts=(replace(bundle.contracts[0], modifications=tuple(amendments)),),
        known_at=max(bundle.known_at, *(event.recorded_at for event in events)),
    )


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
