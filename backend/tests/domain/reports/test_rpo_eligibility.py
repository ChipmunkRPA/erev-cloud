"""RPO eligibility exits and re-entry from original Step 1 computations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import rpo_boundary_changes, rpo_estimate_changes
from erev_api.domain.reports.builders import rpo
from erev_engine import compute
from support import allocation_worlds, cpc_worlds, step1_worlds


@pytest.mark.parametrize("modified", [False, True])
@pytest.mark.parametrize("estimated", [False, True])
def test_original_collectibility_exit_and_reentry(modified: bool, estimated: bool) -> None:
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    admitted, exited, returned = date(2026, 1, 1), date(2026, 2, 10), date(2026, 3, 1)
    steps = [
        ("C", admitted, ""),
        ("S", exited, "Customer deterioration"),
        ("N", exited, ""),
        ("C", returned, ""),
    ]
    cid, eid, gid, oid = (uuid4() for _ in range(4))
    versions, obligations, cuts, boundaries = [], {}, {}, {}
    estimates_by_version = {}
    schedules_by_version = {}
    previous_events: set[str] = set()
    for index, (count, effective) in enumerate(((1, admitted), (3, exited), (4, returned))):
        bundle = step1_worlds.time_world(paid=None, steps=steps[:count])
        if modified or estimated:
            bundle = step1_worlds.time_world(paid=None, steps=steps[:1], known_at=bundle.known_at)
            events = list(bundle.events)
            estimates = []
            if estimated:
                initial = replace(
                    allocation_worlds.untargeted_element(),
                    estimate_key="C-STEP1/BASE",
                    version_key="C-STEP1/BASE@v1",
                )
                estimates.append(initial)
                events = cpc_worlds.pinned(events, initial)
            amendments = []
            if index:
                if modified:
                    amendment = cpc_worlds.concession("120", exited, key=step1_worlds.SERVICE)
                    amendment = replace(
                        amendment,
                        price_change_amount=None,
                        lines=tuple(
                            {**line, "product_code": "SERVICE"} for line in amendment.lines
                        ),
                    )
                    amendments.append(amendment)
                    events = cpc_worlds.amended(events, amendment)
                if estimated:
                    updated = allocation_worlds.later_version(estimates[0], 2, exited, "60")
                    estimates.append(updated)
                    events = cpc_worlds.pinned(events, updated)
                events = step1_worlds.significant_change(events, exited, "Customer deterioration")
                events = step1_worlds.not_probable(events, exited)
                if index == 2:
                    events = step1_worlds.criteria_met(events, returned)
            bundle = replace(
                bundle,
                events=tuple(events),
                estimate_versions=tuple(estimates),
                contracts=(replace(bundle.contracts[0], modifications=tuple(amendments)),),
            )
        book = compute(bundle).books[0]
        vid = uuid4()
        causes = [event for event in bundle.events if event.event_key not in previous_events]
        previous_events = {event.event_key for event in bundle.events}
        included = book.contract_version.columns["status_in_book"] in {"ACTIVE", "TERMINATED"}
        version = rpo._Version(
            vid,
            gid,
            index + 1,
            included,
            effective,
            frozenset(event.event_type for event in causes),
            entries=((cid, effective),) if included else (),
            eligibility_exits=((cid, effective),) if not included else (),
            estimate_events=frozenset(
                event.event_key for event in causes if event.event_type == "ESTIMATE_CHANGED"
            ),
            estimate_dates=tuple(
                (event.event_key, event.effective_date)
                for event in causes
                if event.event_type == "ESTIMATE_CHANGED"
            ),
            modification_events=frozenset(
                event.event_key for event in causes if event.event_type == "CONTRACT_AMENDED"
            ),
        )
        versions.append(version)
        boundaries[vid] = rpo_boundary_changes.history(book.trace)
        shares = rpo_estimate_changes.allocations(book.trace, version.estimate_events)
        if shares is not None:
            estimates_by_version[vid] = shares
        output = book.obligation_versions[0]
        columns = output.columns
        ob = rpo._Ob(
            oid,
            vid,
            oid,
            cid,
            step1_worlds.CONTRACT,
            step1_worlds.SERVICE,
            "Service",
            None,
            None,
            None,
            eid,
            "E",
            "USD",
            "TIME_ELAPSED",
            date(2026, 12, 31),
            admitted,
            Decimal(str(columns["allocated_amount"])) / 100,
            False,
        )
        period_ends = {
            p.period_key: p.end_date for entity in bundle.entities for p in entity.periods
        }
        for schedule in book.schedules:
            if schedule.subject_key == output.subject_key and schedule.schedule_kind == "REVENUE":
                line_id = uuid4()
                ob.lines.append(
                    (line_id, period_ends[schedule.period_key], Decimal(schedule.amount) / 100)
                )
                ob.line_nodes[line_id] = schedule.trace_node_id
        obligations[vid] = (ob,)
        schedules_by_version[vid] = sum((a for _, d, a in ob.lines if d <= end), Decimal(0))
        row = {**columns, "id": oid, "contract_id": cid, "trace_nodes": output.trace_nodes}
        for name in ("revenue_cum", "billed_cum", "scheduled_amount", "awaiting_trigger_amount"):
            row[name] = Decimal(str(columns[name])) / 100
        ratio = columns["progress_ratio"]
        row["progress_ratio"] = Decimal(ratio.numerator) / Decimal(ratio.denominator)
        nodes = to_date.nodes_of(
            book.trace.nodes,
            starts={
                (p.period_key, p.end_date): (p.start_date,)
                for entity in bundle.entities
                for p in entity.periods
            },
        )
        for day in (before, end, admitted, exited, returned):
            cuts[vid, day] = to_date.version_at(
                {"version_no": index + 1},
                [row],
                nodes=nodes,
                external_ids={cid: step1_worlds.CONTRACT},
                as_of=day,
            ).obligations
    chain = tuple(versions)
    store = rpo.Store(
        {gid: chain},
        obligations,
        {cid: chain},
        cuts,
        boundaries=boundaries,
        estimate_allocations=estimates_by_version,
    )
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["OPENING"] == 1100, result.lines
    assert result.lines["NEW_CONTRACTS"] == 0, result.lines
    assert result.lines["CANCELLATIONS"] == 0, result.lines
    assert result.lines["UNEXPLAINED"] == 0, result.lines
    # Reconcile disclosure to original engine schedules, independent of RPO movement logic.
    total_price = Decimal(1200 + (120 if modified else 0) + (60 if estimated else 0))
    assert result.lines["CLOSING"] == total_price - schedules_by_version[versions[2].id]
    exit_revenue = schedules_by_version[versions[1].id]
    entry_revenue = schedules_by_version[versions[2].id]
    assert result.lines["ELIGIBILITY_CHANGES"] == exit_revenue - entry_revenue
    assert result.lines["VC_ESTIMATE_CHANGES"] == (60 if estimated else 0)
    assert result.lines["MODIFICATIONS"] == (120 if modified else 0), result.lines
    assert result.lines["REVENUE"] == 100 - exit_revenue, result.lines

    # Without the new binding, preserve the old calculation rather than rewrite history.
    (legacy,) = rpo.rollforward_lines(
        replace(store, classify_eligibility_changes=False), ranges={eid: (before, end)}, applied={}
    )
    assert legacy.lines["ELIGIBILITY_CHANGES"] == 0
    assert legacy.lines != result.lines
    if modified and not estimated:
        # Original engine schedules: Jan 100; the exit retains Feb 4.08;
        # re-entry retains March 187.69, admitting RPO 1,028.23.
        # The 120 price increase must stay separate from that eligibility balance.
        assert result.lines["CLOSING"] == Decimal("1028.23")
    if modified or estimated:
        missing_evidence = replace(
            store,
            boundaries={} if modified else boundaries,
            estimate_allocations={} if estimated else estimates_by_version,
        )
        (incomplete,) = rpo.rollforward_lines(
            missing_evidence,
            ranges={eid: (before, end)},
            applied={},
        )
        assert incomplete.lines != result.lines
        (old,) = rpo.rollforward_lines(
            replace(store, classify_mixed_eligibility=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert old.lines != result.lines
        return
    # A competing price change must not be hidden inside the eligibility movement.
    mixed = replace(versions[1], causes=versions[1].causes | {"CONTRACT_AMENDED"})
    mixed_chain = (versions[0], mixed, versions[2])
    (unsupported,) = rpo.rollforward_lines(
        replace(store, versions={gid: mixed_chain}, chains={cid: mixed_chain}),
        ranges={eid: (before, end)},
        applied={},
    )
    assert unsupported.lines["ELIGIBILITY_CHANGES"] == 0
