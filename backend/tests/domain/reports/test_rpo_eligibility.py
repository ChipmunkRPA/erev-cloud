"""RPO eligibility exits and re-entry from original Step 1 computations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

from erev_api.domain.contracts import to_date
from erev_api.domain.reports.builders import rpo
from erev_engine import compute
from support import step1_worlds


def test_original_collectibility_exit_and_reentry() -> None:
    before, end = date(2026, 1, 31), date(2026, 3, 31)
    admitted, exited, returned = date(2026, 1, 1), date(2026, 2, 10), date(2026, 3, 1)
    steps = [
        ("C", admitted, ""),
        ("S", exited, "Customer deterioration"),
        ("N", exited, ""),
        ("C", returned, ""),
    ]
    cid, eid, gid, oid = (uuid4() for _ in range(4))
    versions, obligations, cuts = [], {}, {}
    previous_events: set[str] = set()
    for index, (count, effective) in enumerate(((1, admitted), (3, exited), (4, returned))):
        bundle = step1_worlds.time_world(paid=None, steps=steps[:count])
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
        )
        versions.append(version)
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
    store = rpo.Store({gid: chain}, obligations, {cid: chain}, cuts)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["OPENING"] == 1100, result.lines
    assert result.lines["NEW_CONTRACTS"] == 0, result.lines
    assert result.lines["CANCELLATIONS"] == 0, result.lines
    assert result.lines["UNEXPLAINED"] == 0, result.lines
    assert result.lines["CLOSING"] == 900, result.lines
    assert result.lines["ELIGIBILITY_CHANGES"] == -200, result.lines
    assert result.lines["REVENUE"] == 0, result.lines

    # Without the new binding, preserve the old calculation rather than rewrite history.
    (legacy,) = rpo.rollforward_lines(
        replace(store, classify_eligibility_changes=False), ranges={eid: (before, end)}, applied={}
    )
    assert legacy.lines["ELIGIBILITY_CHANGES"] == 0
    assert legacy.lines != result.lines
    # A competing price change must not be hidden inside the eligibility movement.
    mixed = replace(versions[1], causes=versions[1].causes | {"CONTRACT_AMENDED"})
    mixed_chain = (versions[0], mixed, versions[2])
    (unsupported,) = rpo.rollforward_lines(
        replace(store, versions={gid: mixed_chain}, chains={cid: mixed_chain}),
        ranges={eid: (before, end)},
        applied={},
    )
    assert unsupported.lines["ELIGIBILITY_CHANGES"] == 0
