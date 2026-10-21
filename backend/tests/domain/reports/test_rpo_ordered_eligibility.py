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


@pytest.mark.parametrize("kind", ["usage", "estimate", "amendment"])
@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("reenter", [False, True])
def test_same_day_monetary_attribution(kind, after, reenter):
    admitted, exited = date(2026, 1, 1), date(2026, 2, 10)
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    bundle = bundle_at_exit(kind, after=after, reenter=reenter)
    book = compute(bundle).books[0]
    vid, cid, gid, eid, oid = (uuid4() for _ in range(5))
    initial = rpo._Version(
        vid,
        gid,
        1,
        reenter,
        exited,
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
    )
    assert timeline is not None
    if reenter or after:
        # A retained binding without the ordered-evidence feature keeps its old refusal.
        assert rpo.initial_eligibility_timeline(
            initial, cid, book.trace, event_map, mixed=True, usage=True
        ) is None
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
        "USAGE",
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
        for day in {before, end, admitted, exited}
    }
    store = rpo.Store(
        {gid: (initial,)},
        {vid: (ob,)},
        {cid: timeline},
        cuts,
        realised_dates={vid: rpo_realised_dates.history(book.trace)},
        positions={vid: rpo_positions.history(book.trace)},
    )
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
