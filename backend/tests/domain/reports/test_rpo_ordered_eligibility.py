"""Reporting uses original event positions for same-day eligibility and monetary causes."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import rpo_positions, rpo_realised_dates
from erev_api.domain.reports.builders import rpo
from erev_engine import compute
from support import step1_worlds as worlds
from support.ordered_step1 import bundle_at_exit


def report_store(bundle, before, end, *, performance=False):
    admitted = date(2026, 1, 1)
    book = compute(bundle).books[0]
    vid, cid, gid, eid, oid = (uuid4() for _ in range(5))
    initial = rpo._Version(
        vid,
        gid,
        1,
        book.contract_version.columns["status_in_book"] == "ACTIVE",
        max(event.effective_date for event in bundle.events),
        frozenset(event.event_type for event in bundle.events),
        entries=((cid, admitted),),
        cause_events=frozenset(event.event_key for event in bundle.events),
    )
    event_map = {
        event.event_key: (cid, event.event_type, event.effective_date, event.record_seq)
        for event in bundle.events
    }
    timeline = rpo.initial_eligibility_timeline(
        initial,
        cid,
        book.trace,
        event_map,
        mixed=True,
        usage=True,
        ordered=True,
        performance=performance,
    )
    assert timeline is not None
    if performance:
        assert (
            rpo.initial_eligibility_timeline(
                initial, cid, book.trace, event_map, mixed=True, usage=True, ordered=True
            )
            is None
        )
    output = book.obligation_versions[0]
    columns = output.columns
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        worlds.CONTRACT,
        worlds.SERVICE,
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        bundle.pob_template_versions[0].recognition_method,
        date(2026, 12, 31),
        admitted,
        Decimal(str(columns["allocated_amount"])) / 100,
        False,
    )
    periods = {p.period_key: p for entity in bundle.entities for p in entity.periods}
    for schedule in book.schedules:
        if schedule.subject_key == output.subject_key and schedule.schedule_kind == "REVENUE":
            line = uuid4()
            ob.lines.append(
                (line, periods[schedule.period_key].end_date, Decimal(schedule.amount) / 100)
            )
            ob.line_nodes[line] = schedule.trace_node_id
    row = {**columns, "id": oid, "contract_id": cid, "trace_nodes": output.trace_nodes}
    for name in ("revenue_cum", "billed_cum", "scheduled_amount", "awaiting_trigger_amount"):
        row[name] = Decimal(str(columns[name])) / 100
    ratio = columns["progress_ratio"]
    row["progress_ratio"] = Decimal(ratio.numerator) / Decimal(ratio.denominator)
    nodes = to_date.nodes_of(
        book.trace.nodes,
        starts={(p.period_key, p.end_date): (p.start_date,) for p in periods.values()},
    )
    cuts = {
        (vid, day): to_date.version_at(
            {"version_no": 1},
            [row],
            nodes=nodes,
            external_ids={cid: worlds.CONTRACT},
            as_of=day,
        ).obligations
        for day in {before, end, *(event.effective_date for event in bundle.events)}
    }
    store = rpo.Store(
        {gid: (initial,)},
        {vid: (ob,)},
        {cid: timeline},
        cuts,
        realised_dates={vid: rpo_realised_dates.history(book.trace)},
        positions={vid: rpo_positions.history(book.trace)},
    )
    return store, eid, vid, oid, book, cuts


@pytest.mark.parametrize("kind", ["usage", "estimate", "amendment"])
@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("reenter", [False, True])
def test_same_day_monetary_attribution(kind, after, reenter):
    exited = date(2026, 2, 10)
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    bundle = bundle_at_exit(kind, after=after, reenter=reenter)
    store, eid, vid, oid, book, cuts = report_store(bundle, before, end)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    points = next(iter(store.positions[vid].values()))
    exit_point = next(
        p
        for (event, side), p in points.items()
        if side == "after" and p.event_type == "COLLECTIBILITY_ASSESSED" and p.day == exited
    )
    entry_point = next(
        (
            p
            for (event, side), p in points.items()
            if side == "after" and p.event_type == "CONTRACT_CRITERIA_MET" and p.day == exited
        ),
        None,
    )
    money = Decimal(120 if kind == "amendment" else 60)
    assert result.lines["OPENING"] == 1100
    assert result.lines["MODIFICATIONS"] == (money if kind == "amendment" and not after else 0)
    assert result.lines["VC_ESTIMATE_CHANGES"] == (
        money if kind != "amendment" and not after else 0
    )
    eligibility = -(exit_point.fixed + exit_point.realised - exit_point.revenue)
    if entry_point is not None:
        eligibility += entry_point.fixed + entry_point.realised - entry_point.revenue
    assert result.lines["ELIGIBILITY_CHANGES"] == eligibility
    assert result.lines["CLOSING"] == (1200 + money - cuts[vid, end][oid].revenue if reenter else 0)
    assert result.lines["NEW_CONTRACTS"] == result.lines["CANCELLATIONS"] == 0
    assert result.lines["UNEXPLAINED"] == 0, result.lines
    with pytest.raises(to_date.Unreadable):
        rpo.rollforward_lines(replace(store, positions={}), ranges={eid: (before, end)}, applied={})


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize(
    "exited,end",
    [
        (date(2026, 2, 10), date(2026, 2, 28)),
        (date(2026, 2, 10), date(2026, 3, 31)),
        (date(2026, 3, 20), date(2026, 3, 31)),
    ],
)
@pytest.mark.parametrize("returned", ["0.2", "0.05"])
def test_returns_and_delivery_follow_original_eligibility_order(after, exited, end, returned):
    from support import cpc_worlds
    from support.recognition import estimate_version

    jan = date(2026, 1, 1)
    before = date(2026, 1, 31)
    bundle = worlds.time_world(
        paid=None,
        steps=[("C", jan, "")],
        template_changes={"recognition_method": "UNITS_DELIVERED"},
        policies={
            "returns.model": "EXPECTED_RETURNS",
            "returns.returned_units_scope": "REDUCE_CONTRACT_QUANTITY",
        },
    )
    estimate = replace(
        estimate_version(f"{worlds.CONTRACT}/RET", "RETURN_RATE", 1, jan),
        obligation_key=worlds.SERVICE,
        expected_quantity=Decimal("0.1"),
        parameters={
            "window_end_date": "2026-03-15",
            "carrying_cost_per_unit": "0",
            "recovery_cost_per_unit": "0",
        },
    )
    events = cpc_worlds.pinned(list(bundle.events), estimate)
    events = worlds.delivered(events, date(2026, 1, 15), worlds.SERVICE, "0.5")
    events = worlds.significant_change(events, exited, "Distress")
    if after:
        events = worlds.not_probable(events, exited)
    events = cpc_worlds.then(
        events,
        "RETURN_RECORDED",
        exited,
        {
            "obligation_key": worlds.SERVICE,
            "quantity": Decimal(returned),
            "refund_amount": Decimal(returned) * 1200,
        },
    )
    events = worlds.delivered(events, exited, worlds.SERVICE, "0.1")
    if not after:
        events = worlds.not_probable(events, exited)
    events = worlds.criteria_met(events, exited)
    bundle = replace(
        bundle,
        events=tuple(events),
        estimate_versions=(estimate,),
        known_at=max(bundle.known_at, *(event.recorded_at for event in events)),
    )
    store, eid, vid, oid, book, cuts = report_store(bundle, before, end, performance=True)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    # January: net allocation 1,080, recognized 480, RPO 600.
    # Delivery adds 0.1 units. Excess actual returns lower net allocation; otherwise
    # remaining expected returns expire in March, increasing allocation and revenue equally.
    excess = Decimal(120) if returned == "0.2" else Decimal(0)
    release = Decimal(60) if returned == "0.05" and end.month == 3 else Decimal(0)
    assert result.lines["OPENING"] == 600
    expected_vc = (-excess if not after else 0) + release
    expected_revenue = (-120 + excess if not after else 0) - release
    if after and exited.month == 3:
        expected_vc, expected_revenue = Decimal(120), Decimal(-120)
    assert result.lines["VC_ESTIMATE_CHANGES"] == expected_vc
    assert result.lines["ELIGIBILITY_CHANGES"] == (0 if not after else -120)
    assert result.lines["CLOSING"] == 480
    assert result.lines["REVENUE"] == expected_revenue
    assert result.lines["UNEXPLAINED"] == 0, result.lines


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("delivered_early", [False, True])
def test_royalty_guarantee_correction_and_satisfaction_across_eligibility(after, delivered_early):
    from support import cpc_worlds

    jan, exited = date(2026, 1, 1), date(2026, 2, 10)
    bundle = worlds.time_world(
        paid=None,
        steps=[("C", jan, "")],
        template_changes={
            "obligation_kind": "LICENCE",
            "licence_nature": "FUNCTIONAL",
            "recognition_method": "ROYALTY",
        },
        policies={"royalty.minimum_guarantee": "FIXED_ON_LICENCE_PATTERN"},
    )
    events = list(bundle.events)
    if delivered_early:
        events = worlds.delivered(events, date(2026, 1, 15), worlds.SERVICE)

    def statement(events, day, start, end, amount):
        return cpc_worlds.then(
            events,
            "USAGE_REPORTED",
            day,
            {
                "obligation_key": worlds.SERVICE,
                "usage_period_start": start,
                "usage_period_end": end,
                "metric": "LICENSEE_SALES",
                "quantity": Decimal(amount),
                "rated_amount": Decimal(amount),
                "is_royalty_statement": True,
            },
        )

    events = statement(events, date(2026, 1, 31), jan, date(2026, 1, 31), 600)
    events = worlds.significant_change(events, exited, "Licensee distress")
    if after:
        events = worlds.not_probable(events, exited)
    events = statement(events, exited, date(2026, 2, 1), exited, 1000)
    if not after:
        events = worlds.not_probable(events, exited)
    events = worlds.criteria_met(events, exited)
    if not delivered_early:
        events = worlds.delivered(events, date(2026, 3, 15), worlds.SERVICE)
    events = statement(events, date(2026, 3, 20), date(2026, 2, 1), exited, 800)
    bundle = replace(
        bundle,
        events=tuple(events),
        known_at=max(bundle.known_at, *(event.recorded_at for event in events)),
    )
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    store, eid, vid, oid, book, cuts = report_store(bundle, before, end, performance=True)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    # 600 January + corrected 800 February less the 1,200 guarantee = 200 excess royalty.
    assert result.lines["OPENING"] == (0 if delivered_early else 1200)
    assert result.lines["VC_ESTIMATE_CHANGES"] == (-200 if after else 200)
    assert result.lines["ELIGIBILITY_CHANGES"] == (400 if after and not delivered_early else 0)
    assert result.lines["REVENUE"] == ((200 if after else -200) if delivered_early else -1400)
    assert result.lines["CLOSING"] == 0
    assert result.lines["UNEXPLAINED"] == 0, result.lines
