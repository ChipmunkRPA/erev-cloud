"""Original usage fees across an initial eligibility timeline."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import rpo_realised_dates
from erev_api.domain.reports.builders import rpo
from erev_engine import compute
from support import cpc_worlds
from support import step1_worlds as worlds


@pytest.mark.parametrize("usage_day", [date(2026, 2, 5), date(2026, 2, 15)])
def test_initial_usage_is_attributed_to_its_eligibility_segment(usage_day):
    admitted, exited, entered = date(2026, 1, 1), date(2026, 2, 10), date(2026, 3, 1)
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    bundle = worlds.time_world(
        paid=None,
        steps=[
            ("C", admitted, ""),
            ("S", exited, "Distress"),
            ("N", exited, ""),
            ("C", entered, ""),
        ],
        template_changes={"recognition_method": "USAGE"},
    )
    events = cpc_worlds.then(
        list(bundle.events),
        "USAGE_REPORTED",
        usage_day,
        {
            "obligation_key": worlds.SERVICE,
            "usage_period_start": date(2026, 2, 1),
            "usage_period_end": usage_day,
            "metric": "CALLS",
            "quantity": Decimal(10),
            "rated_amount": Decimal(60),
        },
    )
    bundle = replace(
        bundle,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
    )
    book = compute(bundle).books[0]
    vid, cid, gid, eid, oid = (uuid4() for _ in range(5))
    initial = rpo._Version(
        vid,
        gid,
        1,
        True,
        entered,
        frozenset(event.event_type for event in bundle.events),
        entries=((cid, admitted),),
        cause_events=frozenset(event.event_key for event in bundle.events),
    )
    event_map = {
        event.event_key: (cid, event.event_type, event.effective_date, event.record_seq)
        for event in bundle.events
    }
    assert rpo.initial_eligibility_timeline(initial, cid, book.trace, event_map, mixed=True) is None
    timeline = rpo.initial_eligibility_timeline(
        initial,
        cid,
        book.trace,
        event_map,
        mixed=True,
        usage=True,
    )
    assert timeline is not None
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
        for day in {before, end, admitted, exited, entered, usage_day}
    }
    store = rpo.Store(
        {gid: (initial,)},
        {vid: (ob,)},
        {cid: timeline},
        cuts,
        realised_dates={vid: rpo_realised_dates.history(book.trace)},
    )
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})

    def revenue_at(day):
        return cuts[vid, day][oid].revenue

    exit_fee = Decimal(60 if usage_day < exited else 0)
    expected_eligibility = revenue_at(exited) - 1200 - exit_fee + 1260 - revenue_at(entered)
    assert result.lines["OPENING"] == 1200 - revenue_at(before)
    assert result.lines["VC_ESTIMATE_CHANGES"] == exit_fee
    assert result.lines["ELIGIBILITY_CHANGES"] == expected_eligibility
    assert result.lines["CLOSING"] == 1260 - revenue_at(end)
    assert result.lines["NEW_CONTRACTS"] == result.lines["CANCELLATIONS"] == 0
    assert result.lines["UNEXPLAINED"] == 0, result.lines
    with pytest.raises(to_date.Unreadable) as caught:
        rpo.rollforward_lines(
            replace(store, realised_dates={}), ranges={eid: (before, end)}, applied={}
        )
    assert caught.value.errors[0].field.endswith(".realised_allocation")
