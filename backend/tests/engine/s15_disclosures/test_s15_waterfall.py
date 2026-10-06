"""Stage 15 revenue waterfall measures and the RPO rollforward (EDS-2).

ENGINE_SPEC_B §15.2.1 (S15-R-01, S15-R-02), §15.2.3 S15-R-12, §14.4 S14-INV-06, §9.7 EX-09-A and
EX-09-B, §15.7 EX-15-A; 03 REQ-RPT-004, REQ-RPT-010 (V9); SCREENS_B RPT-07. The worlds run through
the real engine with stage 15 registered, and the stage 15 state is read from
``s13_books.run_books`` over the same bundle (as ``test_s15_rpo``). K-03 (EX-09-B; PRD WLD-K-03) is
cost to cost, which is ENC-5 and deferred post-rc, so K-03 is measured with ``UNITS_DELIVERED``:
costs as units and the EAC as the contracted quantity (L2-5-Q-5). A measure-only EAC version adds no
segment, so EAC version 3 of 30 Sep 2026 is not built (L3-2-Q-34). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import EventInput, InputBundle, ModificationInput, OutputBundle
from erev_engine.stages import STAGES, s01_canonicalize, s13_books, s15_disclosures
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s13_books import BookResult
from erev_engine.stages.s15_disclosures import ROLLFORWARD_LINES, DisclosureState
from erev_engine.stages.state import BookContext
from erev_engine.trace import TraceBuilder
from support import bundles
from support.intent_totals import posted
from test_s15_rpo import (
    K02,
    booked,
    dated_rpo,
    k02,
    one_year,
    point,
    product,
    ssp_version,
    template,
    usd,
    world,
)

ENTITY = bundles.ENTITY_CODE


def run(value: InputBundle) -> tuple[OutputBundle, BookContext, BookResult, DisclosureState]:
    """``compute`` over ``value``, then the book context, the book result and the stage 15 state of
    the book loop over the same bundle."""
    output = compute(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    return output, s13_books.book_context(cb, cb.books[str(result.book)]), result, result.state


def nonzero(values: Mapping[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    return {cell: amount for cell, amount in sorted(values.items()) if amount != 0}


def journal(output: OutputBundle) -> dict[tuple[str, str], int]:
    """Σ ``REVENUE`` posting-intent lines per (entity, posting period), credit positive."""
    found: dict[tuple[str, str], int] = {}
    for book in output.books:
        for intent in book.posting_intents:
            for line in intent.lines:
                if line.account_role == "REVENUE":
                    cell = (intent.entity, intent.posting_period_key)
                    signed = line.amount_txn if line.side == "C" else -line.amount_txn
                    found[cell] = found.get(cell, 0) + signed
    return nonzero(found)


def stage_09_revenue(ctx: BookContext, result: BookResult) -> dict[tuple[str, str], int]:
    """The period movement of the stage 09 ``revenue_cum`` targets, Σ obligations."""
    recognition = result.states["09"]
    assert isinstance(recognition, RecognitionState)
    starts = {
        (code, period.period_key): period.start_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    ordered = sorted(
        (target for target in recognition.revenue_targets if target.measure == "revenue_cum"),
        key=lambda target: (target.subject_key, starts[(target.entity, target.period_key)]),
    )
    found: dict[tuple[str, str], int] = {}
    previous: dict[str, int] = {}
    for target in ordered:
        cell = (target.entity, target.period_key)
        found[cell] = found.get(cell, 0) + target.value - previous.get(target.subject_key, 0)
        previous[target.subject_key] = target.value
    return nonzero(found)


# --- K-03 (EX-09-B), units standing in for costs --------------------------------------------------

K03 = "K-03"
K03_INCEPTION, K03_END, K03_MOD = date(2026, 2, 1), date(2027, 12, 31), date(2026, 9, 10)
K03_COSTS = (  # WLD-K-03: costs incurred through 31 Aug 2026, 420,000.00
    (date(2026, 2, 28), "30000"),
    (date(2026, 3, 31), "50000"),
    (date(2026, 4, 30), "60000"),
    (date(2026, 5, 31), "70000"),
    (date(2026, 6, 30), "70000"),
    (date(2026, 7, 31), "70000"),
    (date(2026, 8, 31), "70000"),
)
UNITS = template("TPL-UNITS", method="UNITS_DELIVERED", pattern="OVER_TIME")


def cost(stream: int, on: date, units: str) -> EventInput:
    payload = {"obligation_key": "O1", "quantity": Decimal(units), "trigger": "DELIVERY"}
    return bundles.event(K03, stream, "DELIVERY_RECORDED", on, payload, obligation_keys=["O1"])


def k03(*, through_august: bool = False) -> InputBundle:
    """K-03: O1 1,000,000.00 with EAC 700,000.00 (700,000 units) and costs of 420,000.00 to 31 Aug
    2026; change order ``CR-CASTELLAN-2026-09`` on 10 Sep 2026 under 25-13(b), +350,000.00 and EAC
    820,000.00 (+120,000 units); costs of 82,000.00 on 25 Sep 2026."""
    line = bundles.booking_line(
        "O1", product_code="SKU-BUILD", quantity="700000", total_price="1000000.00", end=K03_END
    )
    events = [booked(K03, K03_INCEPTION, line)]
    events.extend(cost(stream, on, units) for stream, (on, units) in enumerate(K03_COSTS, start=3))
    modifications: list[ModificationInput] = []
    if not through_august:
        change = {
            "obligation_key": "O1",
            "action": "CHANGE",
            "product_code": "SKU-BUILD",
            "quantity_delta": Decimal("120000"),
            "consideration_delta": Decimal("350000.00"),
        }
        modification = ModificationInput(
            modification_key="CR-CASTELLAN-2026-09",
            effective_date=K03_MOD,
            kind="QUANTITY_CHANGE",
            template_mode=None,
            status="APPLIED",
            reference=None,
            questionnaire={},
            lines=(change,),
            price_change_amount=None,
            noncash_consideration=None,
            consideration_payable=None,
            scope_605_35=None,
            currency="USD",
            proposed_treatments={},
            chosen_treatments={},
            treatment_summary=None,
            ssp_basis={},
            judgement_key=None,
            content_sha256=None,
        )
        payload = {
            "modification_id": modification.modification_key,
            "treatments": {"O1": "CUMULATIVE_CATCH_UP"},
            "lines": [change],
            "ssp_basis": {},
        }
        events.append(
            bundles.event(K03, 10, "CONTRACT_AMENDED", K03_MOD, payload, obligation_keys=["O1"])
        )
        events.append(cost(11, date(2026, 9, 25), "82000"))
        modifications.append(modification)
    value = world(
        K03,
        events,
        products=[product("SKU-BUILD", "TPL-UNITS")],
        ssp=[ssp_version(1, [point("SSP-US@v1", "SKU-BUILD", "1000000.00")], date(2020, 1, 1))],
        inception=K03_INCEPTION,
        months=24,
        modifications=modifications,
    )
    templates = sorted((*value.pob_template_versions, UNITS), key=lambda item: item.template_code)
    return dataclasses.replace(value, pob_template_versions=tuple(templates))


# --- S15-R-01 and S15-R-02 ------------------------------------------------------------------------


def test_s15_r01_waterfall_measures() -> None:
    value = k02()
    output, _, _, state = run(value)
    (book,) = output.books
    waterfall = state.waterfall
    assert waterfall.as_of == date(2026, 9, 30)
    rows = {row.subject_key: row for row in waterfall.rows}
    o1, o2 = rows[f"{K02}/POB-01"], rows[f"{K02}/POB-02"]
    # EX-09-A: September 2026 recognised O1 9,490.37 + O2 2,279.43 = 11,769.80.
    september, october = (ENTITY, "FY2026-P09"), (ENTITY, "FY2026-P10")
    assert (o1.recognised[september], o2.recognised[september]) == (
        usd("9490.37"),
        usd("2279.43"),
    )
    assert waterfall.recognised[september] == usd("11769.80")
    assert (o1.as_of_period_key, o1.recognised_to_date, o2.recognised_to_date) == (
        "FY2026-P09",
        usd("89380.78"),
        usd("2279.43"),
    )
    # Scheduled per future period equals the schedule lines of the version, from October 2026
    # (EX-09-A 14,132.46) to December 2027.
    ends = {period.period_key: period.end_date for period in value.entities[0].periods}
    expected: dict[str, dict[tuple[str, str], int]] = {}
    for line in book.schedules:
        if str(line.schedule_kind) == "REVENUE" and ends[line.period_key] > date(2026, 9, 30):
            cells = expected.setdefault(line.subject_key, {})
            cell = (line.entity, line.period_key)
            cells[cell] = cells.get(cell, 0) + line.amount
    assert {row.subject_key: dict(row.scheduled) for row in waterfall.rows} == expected
    assert (next(iter(o1.scheduled)), list(o1.scheduled)[-1]) == (october, (ENTITY, "FY2027-P12"))
    assert o1.scheduled[october] + o2.scheduled[october] == usd("14132.46")
    assert waterfall.scheduled[october] == usd("14132.46")
    assert (sum(o1.scheduled.values()), sum(o2.scheduled.values())) == (
        usd("138893.19"),
        usd("69446.60"),
    )
    # Awaiting trigger per obligation equals awaiting_trigger_amount of the obligation version.
    columns = {version.subject_key: version.columns for version in book.obligation_versions}
    for row in waterfall.rows:
        assert row.awaiting == columns[row.subject_key]["awaiting_trigger_amount"] == 0
    # S15-R-02: recognised to date + scheduled + awaiting = allocated of every included obligation.
    assert (o1.included, o1.allocated, o2.allocated) == (True, usd("228273.97"), usd("71726.03"))
    assert (o1.unexplained, o2.unexplained, waterfall.balanced) == (0, 0, True)
    # Each cell names its contributors: intent lines, schedule lines and the stage 09 node.
    revenue_lines = {
        line.trace_node_id
        for intent in book.posting_intents
        if intent.subject_key == o1.subject_key and intent.posting_period_key == "FY2026-P09"
        for line in intent.lines
        if line.account_role == "REVENUE"
    }
    assert revenue_lines and set(o1.contributors[("recognised", *september)]) == revenue_lines
    schedule_nodes = sorted(
        {
            line.trace_node_id
            for line in book.schedules
            if line.subject_key == o1.subject_key and line.period_key == "FY2026-P10"
        }
    )
    assert o1.contributors[("scheduled", *october)] == tuple(schedule_nodes)
    assert o1.contributors[("awaiting", "-", "-")] == (f"awaiting_trigger_amount:{K02}/POB-01:-",)
    # An awaiting-trigger amount: the hardware of the one-year world, undelivered at 30 June 2026.
    output, _, _, state = run(one_year(date(2026, 12, 31), "DO_NOT_APPLY"))
    (book,) = output.books
    columns = {version.subject_key: version.columns for version in book.obligation_versions}
    rows = {row.subject_key: row for row in state.waterfall.rows}
    hardware, subscription = rows["K-1Y/POB-02"], rows["K-1Y/POB-01"]
    assert (hardware.included, hardware.awaiting, hardware.recognised_to_date) == (
        True,
        usd("3000.00"),
        0,
    )
    assert dict(hardware.scheduled) == {}
    assert hardware.awaiting == columns["K-1Y/POB-02"]["awaiting_trigger_amount"]
    assert state.waterfall.awaiting == usd("3000.00")
    assert subscription.recognised_to_date + sum(subscription.scheduled.values()) == usd("12000.00")
    assert state.waterfall.balanced


def test_s15_r02_recognised_ties_to_revenue_intents() -> None:
    for value in (k02(), k03()):
        output, ctx, result, state = run(value)
        revenue = journal(output)
        # S14-INV-06: recognised per period = Σ REVENUE posting intents of that period.
        assert revenue and nonzero(state.waterfall.recognised) == revenue
        # Without late carries, each period's revenue is also the movement of the stage 09 targets.
        assert stage_09_revenue(ctx, result) == revenue
        assert state.waterfall.balanced
    # K-03 (WLD-X-09 to WLD-X-11): 600,000.00 to 31 Aug 2026; September 91,463.41 catch-up and
    # 135,000.00 of progress.
    _, _, _, state = run(k03())
    recognised = state.waterfall.recognised
    assert [recognised[(ENTITY, f"FY2026-P{month:02d}")] for month in range(2, 10)] == [
        usd("42857.14"),
        usd("71428.57"),
        usd("85714.29"),
        usd("100000.00"),
        usd("100000.00"),
        usd("100000.00"),
        usd("100000.00"),
        usd("226463.41"),
    ]
    (row,) = state.waterfall.rows
    assert (row.allocated, row.recognised_to_date, row.awaiting) == (
        usd("1350000.00"),
        usd("826463.41"),
        usd("523536.59"),
    )
    assert dict(row.scheduled) == {}
    # The subledger after sealing the August computation: posted amounts for February to August,
    # and a recompute that posts only the September delta. Recognised adds both.
    first = compute(k03(through_august=True))
    output, _, _, state = run(dataclasses.replace(k03(), posted=posted(first)))
    september = (ENTITY, "FY2026-P09")
    assert journal(output) == {september: usd("226463.41")}
    subledger = {**journal(first), september: usd("226463.41")}
    assert nonzero(state.waterfall.recognised) == subledger
    assert state.waterfall.recognised[(ENTITY, "FY2026-P08")] == usd("100000.00")
    assert state.waterfall.balanced


# --- S15-R-12 -------------------------------------------------------------------------------------


def test_s15_r12_rpo_rollforward() -> None:
    _, ctx, result, state = run(k02())
    (september,) = state.rpo_rollforwards
    assert (september.entity, september.period_key) == (ENTITY, "FY2026-P09")
    assert (september.opening_date, september.closing_date) == (
        date(2026, 8, 31),
        date(2026, 9, 30),
    )
    # EX-15-A; V9: opening 160,109.59 + modification 60,000.00 − September revenue 11,769.80 =
    # closing 208,339.79.
    assert tuple(september.lines) == ROLLFORWARD_LINES
    assert dict(september.lines) == {
        "OPENING": usd("160109.59"),
        "NEW_CONTRACTS": 0,
        "MODIFICATIONS": usd("60000.00"),
        "VC_ESTIMATE_CHANGES": 0,
        "LATE_EVENTS": 0,
        "REVENUE": -usd("11769.80"),
        "CANCELLATIONS": 0,
        "EXEMPTIONS": 0,
        "FX": 0,
        "UNEXPLAINED": 0,
        "CLOSING": usd("208339.79"),
    }
    assert september.unexplained == 0
    assert september.lines["CLOSING"] == state.rpo_amount
    assert -september.lines["REVENUE"] == state.waterfall.recognised[(ENTITY, "FY2026-P09")]
    # S15-INV-08 (D-91): per contracting entity, Σ CLOSING of the obligations whose performing-
    # entity period end coincides with the period end = the RPO after exemptions of the stage 09
    # obligation measures dated at that end; K-02 has no returns, so ρ = 0 and the lines are the
    # gross ones above (opening 160,109.59, modification 60,000.00, revenue −11,769.80, closing
    # 208,339.79).
    recognition_09 = result.states["09"]
    assert isinstance(recognition_09, RecognitionState)
    for entity_rows in (september,):
        subjects = [row.subject_key for row in entity_rows.rows]
        assert sum(row.lines["CLOSING"] for row in entity_rows.rows) == dated_rpo(
            ctx, recognition_09, entity_rows.closing_date, subjects
        )
    rows = {row.subject_key: row.lines for row in september.rows}
    o1, o2 = rows[f"{K02}/POB-01"], rows[f"{K02}/POB-02"]
    # O1: 240,000.00 − 79,890.41 at 31 Aug; A′ 228,273.97 − 240,000.00; C(30 Sep) − C(31 Aug).
    assert (o1["OPENING"], o1["MODIFICATIONS"], o1["REVENUE"], o1["CLOSING"]) == (
        usd("160109.59"),
        -usd("11726.03"),
        -usd("9490.37"),
        usd("138893.19"),
    )
    # O2 enters with its share of the pool.
    assert (o2["OPENING"], o2["MODIFICATIONS"], o2["REVENUE"], o2["CLOSING"]) == (
        0,
        usd("71726.03"),
        -usd("2279.43"),
        usd("69446.60"),
    )
    # Every closing is the next opening; January brings the new contract.
    recognition = result.states["09"]
    assert isinstance(recognition, RecognitionState)
    previous = None
    for month in range(1, 13):
        found = s15_disclosures.rollforward(
            ctx, state.allocated, recognition, ENTITY, f"FY2026-P{month:02d}"
        )
        assert found.unexplained == 0, found.period_key
        if previous is not None:
            assert found.lines["OPENING"] == previous.lines["CLOSING"], found.period_key
        previous = found
    january = s15_disclosures.rollforward(ctx, state.allocated, recognition, ENTITY, "FY2026-P01")
    assert (
        january.lines["OPENING"],
        january.lines["NEW_CONTRACTS"],
        january.lines["REVENUE"],
        january.lines["CLOSING"],
    ) == (0, usd("240000.00"), -usd("10191.78"), usd("229808.22"))
    again = s15_disclosures.rollforward(ctx, state.allocated, recognition, ENTITY, "FY2026-P09")
    assert dict(again.lines) == dict(september.lines)
    # An opening from a previous lock snapshot that differs from the restated opening: the
    # difference is the late-events line, and the closing does not move.
    late = s15_disclosures.rollforward(
        ctx,
        state.allocated,
        recognition,
        ENTITY,
        "FY2026-P09",
        opening={f"{K02}/POB-01": usd("160000.00")},
    )
    assert (
        late.lines["OPENING"],
        late.lines["LATE_EVENTS"],
        late.lines["CLOSING"],
        late.unexplained,
    ) == (usd("160000.00"), usd("109.59"), usd("208339.79"), 0)
    # Exemption movements under POL-197 APPLY: June's subscription revenue comes out of exempt RPO,
    # so the opening and closing are 0.
    _, _, _, exempt = run(one_year(date(2026, 12, 31), "APPLY"))
    (june,) = exempt.rpo_rollforwards
    assert (june.period_key, june.lines["OPENING"], june.lines["CLOSING"], june.unexplained) == (
        "FY2026-P06",
        0,
        0,
        0,
    )
    assert june.lines["EXEMPTIONS"] == -june.lines["REVENUE"] == usd("986.30")
    assert june.lines["CLOSING"] == exempt.rpo_after_exemptions  # net; rpo_amount is gross
