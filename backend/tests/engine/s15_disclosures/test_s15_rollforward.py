"""Stage 15 contract balances rollforward with FX movement (EDS-3).

ENGINE_SPEC_B §15.2.2 (S15-R-03 to S15-R-07), §15.3 S15-INV-01 and S15-INV-05, §15.7 EX-15-B and
§12.7 EX-12-A; POLICIES POL-126, ALG-08 §2.9.3 (CHK-081) and §5.11 PT-11 (CHK-121); 03 REQ-FX-007.
The rollforward reads its records through ``BalanceInputs`` (L4-3-Q-3). EX-15-B needs revenue dated
10 and 25 April, while the book loop dates relief at period ends (``s13_books.costs_view``). So the
worlds pass dated control-role flows and stage 10 presented balances as fakes, as the stage 12
tests do (L2-5-Q-10). The functional views run the real stage 12 over the CHK-081 and EX-12-A flows,
and CHK-121 runs the real stage 07 handler. The book loop does not yet carry a business-combination
baseline into stage 10 and stage 14 (L4-3-Q-8). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, FxRateInput
from erev_engine.dates import month_end
from erev_engine.enums import BookCode, ScheduleKind, ScheduleLineType
from erev_engine.stages import s07_onboarding, s12_fx_entities, s15_disclosures
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows, FxState
from erev_engine.stages.s15_disclosures import (
    BALANCE_LINES,
    BalanceInputs,
    BalanceRollforward,
    rollforward_balances,
)
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    PolicyResolver,
    RateIndex,
    ScheduleLineOut,
    SegmentCause,
    Target,
)
from erev_engine.trace import TraceBuilder, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    event_view,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
UK = "UK01"
UNIT = f"CG-1@{ENTITY}"
CL, CA, UR = "CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE"
DELIVERY = f"{CONTRACT_KEY}/D"
SERVICES = f"{CONTRACT_KEY}/S"
LICENCE = f"{CONTRACT_KEY}/L"
RATE_SET = "FX-PUBLISHED@v1"
MARCH, APRIL = "FY2026-P03", "FY2026-P04"
MARCH_END = date(2026, 3, 31)
MONTHS_2026 = tuple(f"FY2026-P{month:02d}" for month in range(1, 5))


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stage 12 reads it (L2-5-Q-10)."""

    allocated: AllocatedState
    fx_flows: FxFlows


# --- Records -------------------------------------------------------------------------------------


def event_key(stream: int) -> str:
    return f"{CONTRACT_KEY}/EV-{stream:06d}"


def invoice(stream: int, issued: date, amount: str) -> ControlFlow:
    """A noncancellable invoice of the contracting entity (S10-R-06, S12-R-04)."""
    return ControlFlow(
        "BILLING",
        ENTITY,
        f"{CONTRACT_KEY}@{ENTITY}",
        event_key(stream),
        issued,
        stream,
        usd(amount),
        unconditional_date=issued,
    )


def on_event(stream: int, on: date, amount: str, subject: str) -> ControlFlow:
    """Event-driven revenue relief of an obligation."""
    return ControlFlow("REVENUE", ENTITY, subject, event_key(stream), on, stream, usd(amount))


def release(subject: str, on: date, amount: str) -> ControlFlow:
    """A time-driven revenue release at a period end (``record_seq`` None)."""
    source = f"{subject}@FY{on.year}-P{on.month:02d}"
    return ControlFlow("REVENUE", ENTITY, subject, source, on, None, usd(amount))


def presented(values: Mapping[str, tuple[str, str, str]]) -> tuple[Target, ...]:
    """Stage 10 presented contract liability, contract asset and unbilled receivable per period."""
    measures = ("contract_liability", "contract_asset", "unbilled_receivable")
    return tuple(
        Target(
            BookCode.ASC606,
            ENTITY,
            UNIT,
            measure,
            period_key,
            None,
            usd(amount),
            None,
            f"{measure}:{UNIT}:{period_key}",
        )
        for period_key, amounts in sorted(values.items())
        for measure, amount in zip(measures, amounts, strict=True)
    )


def conditional(subjects: Iterable[str], periods: Iterable[str]) -> dict[tuple[str, str], str]:
    """Stage 10 right classes (S10-R-21)."""
    keys = tuple(periods)
    return {(subject, key): "CONDITIONAL" for subject in subjects for key in keys}


def schedule(subject: str, period_key: str, line_type: str, amount: str) -> ScheduleLineOut:
    return ScheduleLineOut(
        ScheduleKind.REVENUE,
        "obligation",
        subject,
        ENTITY,
        period_key,
        ScheduleLineType(line_type),
        usd(amount),
        0,
        Fraction(0),
        None,
        False,
        f"schedule_line:{subject}:{period_key}",
    )


def lines(found: BalanceRollforward, balance: str) -> dict[str, int]:
    """The non-zero lines of one balance."""
    return {code: amount for code, amount in found.lines[balance].items() if amount}


def assert_ties(found: BalanceRollforward) -> None:
    """S15-INV-01: opening + lines = closing per balance, and nothing is unexplained."""
    for balance, values in found.lines.items():
        assert tuple(values) == BALANCE_LINES[balance]
        moved = sum(amount for code, amount in values.items() if code not in ("OPENING", "CLOSING"))
        assert values["OPENING"] + moved == values["CLOSING"], (found.period_key, balance)
        assert values["OTHER"] == 0, (found.period_key, found.view, balance)


# --- EX-15-B --------------------------------------------------------------------------------------


def ex_15_b_context(consumption: str | None = None) -> BookContext:
    ctx = book_context(bundles.entity(start=date(2026, 1, 1), months=4))
    if consumption is None:
        return ctx
    resolved = tuple(
        dataclasses.replace(policy, value=consumption, level="T", source_ref="OVR-TEST")
        if policy.code == "rollforward.opening_liability_consumption"
        else policy
        for policy in ctx.policies.all()
    )
    return dataclasses.replace(ctx, policies=PolicyResolver(resolved))


def ex_15_b_state() -> AllocatedState:
    delivery = obligation(
        "D",
        [
            segment(
                Fraction(8000),
                usd("8000.00"),
                start=date(2026, 4, 10),
                end=date(2026, 4, 10),
                measure="POINT_IN_TIME",
            )
        ],
        method="POINT_IN_TIME",
        convention=None,
    )
    services = obligation(
        "S",
        [segment(Fraction(20800), usd("20800.00"), start=date(2026, 1, 1), end=date(2026, 12, 31))],
        convention="MONTHLY_EVEN",
    )
    return allocated_state([delivery, services])


def ex_15_b() -> BalanceInputs:
    """EX-15-B: at 31 Mar billed 20,000.00, revenue 15,000.00 and contract liability 5,000.00. In
    April: delivery revenue 8,000.00 on 10 Apr (a conditional obligation), an invoice of 4,000.00
    on 20 Apr, a TP estimate catch-up of +200.00 on 25 Apr and time-elapsed revenue of 600.00 on
    30 Apr. Stage 10 attributes the January invoice to the services, the April invoice to the
    delivery."""
    flows = (
        invoice(2, date(2026, 1, 1), "20000.00"),
        release(SERVICES, date(2026, 1, 31), "5000.00"),
        release(SERVICES, date(2026, 2, 28), "5000.00"),
        release(SERVICES, date(2026, 3, 31), "5000.00"),
        on_event(5, date(2026, 4, 10), "8000.00", DELIVERY),
        invoice(6, date(2026, 4, 20), "4000.00"),
        on_event(7, date(2026, 4, 25), "200.00", SERVICES),
        release(SERVICES, date(2026, 4, 30), "600.00"),
    )
    return BalanceInputs(
        flows=flows,
        presented=presented(
            {
                "FY2026-P01": ("15000.00", "0.00", "0.00"),
                "FY2026-P02": ("10000.00", "0.00", "0.00"),
                MARCH: ("5000.00", "0.00", "0.00"),
                APRIL: ("200.00", "0.00", "0.00"),
            }
        ),
        right_classes=conditional((DELIVERY, SERVICES), MONTHS_2026),
        schedule_lines=(
            schedule(SERVICES, MARCH, "NORMAL", "5000.00"),
            schedule(DELIVERY, APRIL, "NORMAL", "8000.00"),
            schedule(SERVICES, APRIL, "TP_CHANGE", "200.00"),
            schedule(SERVICES, APRIL, "NORMAL", "600.00"),
        ),
        attribution={
            event_key(2): {SERVICES: usd("20000.00")},
            event_key(6): {DELIVERY: usd("4000.00")},
        },
    )


def test_ex_15_b_flip_to_asset_and_back() -> None:
    found = rollforward_balances(ex_15_b_context(), ex_15_b_state(), ex_15_b(), ENTITY, APRIL)
    assert (found.unit, found.view, found.currency, found.period_key) == (
        UNIT,
        "TRANSACTION",
        "USD",
        APRIL,
    )
    assert (found.opening_date, found.closing_date) == (date(2026, 3, 31), date(2026, 4, 30))
    assert lines(found, CL) == {
        "OPENING": usd("5000.00"),
        "INCREASES_BILLING": usd("1000.00"),
        "REVENUE_FROM_OPENING_BALANCE": -usd("5000.00"),
        "REVENUE_FROM_OTHER_INCREASES": -usd("800.00"),
        "CLOSING": usd("200.00"),
    }
    assert lines(found, CA) == {
        "REVENUE_IN_EXCESS_OF_BILLING": usd("3000.00"),
        "TRANSFERRED_TO_RECEIVABLES_OR_SETTLED": -usd("3000.00"),
    }
    assert (found.lines[CA]["OPENING"], found.lines[CA]["CLOSING"], lines(found, UR)) == (0, 0, {})
    # Revenue 8,800.00 = 5,000.00 + 3,000.00 + 800.00; billing 4,000.00 = 3,000.00 + 1,000.00.
    liability, asset = found.lines[CL], found.lines[CA]
    revenue = (
        -liability["REVENUE_FROM_OPENING_BALANCE"]
        - liability["REVENUE_FROM_OTHER_INCREASES"]
        + asset["REVENUE_IN_EXCESS_OF_BILLING"]
    )
    assert revenue == found.revenue_relief == usd("8800.00")
    billing = -asset["TRANSFERRED_TO_RECEIVABLES_OR_SETTLED"] + liability["INCREASES_BILLING"]
    assert billing == usd("4000.00")
    # Memo lines by cause (S15-R-04) sum to the revenue lines and do not enter the tie.
    assert tuple(found.memo) == s15_disclosures.MEMO_CAUSES
    assert {cause: amount for cause, amount in found.memo.items() if amount} == {
        "NORMAL": usd("8600.00"),
        "TP_CHANGE": usd("200.00"),
    }
    assert sum(found.memo.values()) == found.revenue_relief
    assert found.balanced
    # The month before: opening 10,000.00 and March revenue from the opening balance.
    march = rollforward_balances(ex_15_b_context(), ex_15_b_state(), ex_15_b(), ENTITY, MARCH)
    assert lines(march, CL) == {
        "OPENING": usd("10000.00"),
        "REVENUE_FROM_OPENING_BALANCE": -usd("5000.00"),
        "CLOSING": usd("5000.00"),
    }
    assert march.memo["NORMAL"] == usd("5000.00")


def test_s15_r05_revenue_from_opening_liability() -> None:
    ctx, st, records = ex_15_b_context(), ex_15_b_state(), ex_15_b()
    code = "rollforward.opening_liability_consumption"
    assert ctx.policies.value(code, entity=ENTITY, period=APRIL) == "FIFO_WITHIN_CONTRACT"
    found = rollforward_balances(ctx, st, records, ENTITY, APRIL)
    # POL-126 FIFO_WITHIN_CONTRACT: min(5,000.00, 8,800.00) = 5,000.00 (S15-INV-05).
    opening = found.lines[CL]["OPENING"]
    assert found.revenue_from_opening_liability == min(opening, found.revenue_relief)
    assert found.revenue_from_opening_liability == usd("5000.00")
    # Relief below the opening liability: April recognises only the 600.00 release.
    quiet = dataclasses.replace(
        records,
        flows=tuple(
            flow for flow in records.flows if flow.record_seq is None or flow.record_seq < 5
        ),
        presented=presented(
            {MARCH: ("5000.00", "0.00", "0.00"), APRIL: ("4400.00", "0.00", "0.00")}
        ),
    )
    less = rollforward_balances(ctx, st, quiet, ENTITY, APRIL)
    assert (less.revenue_from_opening_liability, less.revenue_relief) == (
        usd("600.00"),
        usd("600.00"),
    )
    assert (less.lines[CL]["CLOSING"], less.balanced) == (usd("4400.00"), True)
    # FIFO_WITHIN_POB, with stage 10 obligation-attributed billing: the services hold the opening
    # liability (20,000.00 billed − 15,000.00 recognised), the delivery none. So
    # min(5,000.00, 800.00) + min(0.00, 8,000.00) = 800.00, and no other line moves.
    pob = rollforward_balances(ex_15_b_context("FIFO_WITHIN_POB"), st, records, ENTITY, APRIL)
    assert pob.revenue_from_opening_liability == usd("800.00")
    assert pob.lines[CL]["REVENUE_FROM_OTHER_INCREASES"] == -usd("5000.00")
    assert pob.revenue_from_opening_liability <= min(pob.lines[CL]["OPENING"], pob.revenue_relief)
    for balance, values in pob.lines.items():
        for line_code, amount in values.items():
            if not line_code.startswith("REVENUE_FROM_"):
                assert amount == found.lines[balance][line_code], (balance, line_code)
    assert pob.balanced


# --- CHK-081 and EX-12-A (functional views) ------------------------------------------------------


def fx_context(calendars: Sequence[EntityInput]) -> BookContext:
    """One EUR book over ``calendars``: every calendar, horizon and PERIOD policy value (CV-17)."""
    ctx = book_context(calendars[0], currency="EUR")
    resolved = {(p.code, p.scope, p.subject_key): p for p in ctx.policies.all()}
    for calendar in calendars[1:]:
        for policy in bundles.policy_set("DEFAULT", entity=calendar):
            resolved.setdefault((policy.code, policy.scope, policy.subject_key), policy)
    codes = {calendar.functional_currency for calendar in calendars} | {"EUR"}
    return dataclasses.replace(
        ctx,
        currencies=bundles.currencies(*codes),
        entities={calendar.code: calendar for calendar in calendars},
        horizon={calendar.code: calendar.periods[-1].period_key for calendar in calendars},
        policies=PolicyResolver(tuple(resolved[key] for key in sorted(resolved))),
    )


def spot(quote: str, on: date, value: str) -> FxRateInput:
    key = f"EUR{quote}-SPOT-{on.isoformat()}"
    return FxRateInput(key, RATE_SET, "spot", "EUR", quote, on, None, Decimal(value))


def period_rate(kind: str, quote: str, month: int, value: str) -> FxRateInput:
    period_key = f"FY2026-P{month:02d}"
    key = f"EUR{quote}-{kind.upper()}-{period_key}"
    end = month_end(date(2026, month, 1))
    return FxRateInput(key, RATE_SET, kind, "EUR", quote, end, period_key, Decimal(value))


def stage_12(
    ctx: BookContext,
    allocated: AllocatedState,
    flows: Sequence[ControlFlow],
    rates: Sequence[FxRateInput],
) -> FxState:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    costs = _Costs(allocated, FxFlows(tuple(flows)))
    state = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(tuple(rates)))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert state.findings == ()
    return state


def chk_081() -> tuple[BookContext, AllocatedState, BalanceInputs]:
    """CHK-081: arrears billing in EUR for a USD entity; average rates 1.1100, 1.1300 and 1.1500,
    closing rates 1.1200 and 1.1400, and EUR 3,000.00 invoiced on 31 March at 1.1600."""
    ctx = fx_context([bundles.entity(start=date(2026, 1, 1), months=3)])
    services = obligation(
        "S",
        [segment(Fraction(3000), usd("3000.00"), start=date(2026, 1, 1), end=MARCH_END)],
        convention="MONTHLY_EVEN",
    )
    allocated = allocated_state([services])
    flows = (
        release(SERVICES, date(2026, 1, 31), "1000.00"),
        release(SERVICES, date(2026, 2, 28), "1000.00"),
        release(SERVICES, MARCH_END, "1000.00"),
        invoice(4, MARCH_END, "3000.00"),
    )
    rates = (
        period_rate("average", "USD", 1, "1.1100"),
        period_rate("average", "USD", 2, "1.1300"),
        period_rate("average", "USD", 3, "1.1500"),
        period_rate("closing", "USD", 1, "1.1200"),
        period_rate("closing", "USD", 2, "1.1400"),
        spot("USD", MARCH_END, "1.1600"),
    )
    records = BalanceInputs(
        flows=flows,
        presented=presented(
            {
                "FY2026-P01": ("0.00", "1000.00", "0.00"),
                "FY2026-P02": ("0.00", "2000.00", "0.00"),
                MARCH: ("0.00", "0.00", "0.00"),
            }
        ),
        right_classes=conditional([SERVICES], MONTHS_2026[:3]),
        fx=stage_12(ctx, allocated, flows, rates),
    )
    return ctx, allocated, records


def ex_12_a() -> tuple[BookContext, AllocatedState, BalanceInputs]:
    """EX-12-A: a EUR contract of US01 (USD); services S of EUR 3,000.00 over January to March
    performed by UK01 (GBP) and a licence L of EUR 1,500.00 on 15 March performed by US01, both
    conditional; invoices of EUR 3,000.00 on 1 January and EUR 1,500.00 on 20 April."""
    us = bundles.entity(start=date(2026, 1, 1), months=4)
    uk = bundles.entity(UK, functional_currency="GBP", start=date(2026, 1, 1), months=4)
    ctx = fx_context([us, uk])
    services = obligation(
        "S",
        [segment(Fraction(3000), usd("3000.00"), start=date(2026, 1, 1), end=MARCH_END)],
        convention="MONTHLY_EVEN",
    )
    licence = obligation(
        "L",
        [segment(Fraction(1500), usd("1500.00"), start=date(2026, 3, 15), end=date(2026, 3, 15))],
        convention="MONTHLY_EVEN",
    )
    allocated = allocated_state([dataclasses.replace(services, performing_entity=UK), licence])
    flows = (
        invoice(1, date(2026, 1, 1), "3000.00"),
        release(SERVICES, date(2026, 1, 31), "1000.00"),
        release(SERVICES, date(2026, 2, 28), "1000.00"),
        on_event(5, date(2026, 3, 15), "1500.00", LICENCE),
        release(SERVICES, MARCH_END, "1000.00"),
        invoice(6, date(2026, 4, 20), "1500.00"),
    )
    rates = (
        spot("USD", date(2026, 1, 1), "1.123456"),
        spot("USD", date(2026, 4, 20), "1.1450"),
        period_rate("average", "USD", 3, "1.1350"),
        period_rate("closing", "USD", 3, "1.1400"),
        period_rate("average", "GBP", 1, "0.8612"),
        period_rate("average", "GBP", 2, "0.8655"),
        period_rate("average", "GBP", 3, "0.8700"),
    )
    records = BalanceInputs(
        flows=flows,
        presented=presented(
            {
                "FY2026-P01": ("2000.00", "0.00", "0.00"),
                "FY2026-P02": ("1000.00", "0.00", "0.00"),
                MARCH: ("0.00", "1500.00", "0.00"),
                APRIL: ("0.00", "0.00", "0.00"),
            }
        ),
        right_classes=conditional([SERVICES, LICENCE], MONTHS_2026),
        fx=stage_12(ctx, allocated, flows, rates),
    )
    return ctx, allocated, records


def test_fx_line_shown_separately() -> None:
    ctx, allocated, records = chk_081()
    january = rollforward_balances(ctx, allocated, records, ENTITY, "FY2026-P01", view="FUNCTIONAL")
    assert (january.view, january.currency) == ("FUNCTIONAL", "USD")
    # REQ-FX-007; CHK-081: revenue in excess of billing 1,110.00 at the January average rate, and
    # the remeasurement to the closing rate on its own line, 10.00; closing 1,120.00.
    assert lines(january, CA) == {
        "REVENUE_IN_EXCESS_OF_BILLING": usd("1110.00"),
        "FX": usd("10.00"),
        "CLOSING": usd("1120.00"),
    }
    assert (lines(january, CL), lines(january, UR)) == ({}, {})
    assert (january.revenue_relief, january.balanced) == (usd("1110.00"), True)
    # The transaction view has no FX line.
    txn = rollforward_balances(ctx, allocated, records, ENTITY, "FY2026-P01")
    assert (txn.view, txn.currency) == ("TRANSACTION", "EUR")
    assert lines(txn, CA) == {
        "REVENUE_IN_EXCESS_OF_BILLING": usd("1000.00"),
        "CLOSING": usd("1000.00"),
    }
    # February: FX 30.00, closing 2,280.00. March: the invoice at spot settles the three layers
    # after a settlement remeasurement of 50.00, and 3,480.00 transfers to receivables.
    february = rollforward_balances(
        ctx, allocated, records, ENTITY, "FY2026-P02", view="FUNCTIONAL"
    )
    assert lines(february, CA) == {
        "OPENING": usd("1120.00"),
        "REVENUE_IN_EXCESS_OF_BILLING": usd("1130.00"),
        "FX": usd("30.00"),
        "CLOSING": usd("2280.00"),
    }
    march = rollforward_balances(ctx, allocated, records, ENTITY, MARCH, view="FUNCTIONAL")
    assert lines(march, CA) == {
        "OPENING": usd("2280.00"),
        "REVENUE_IN_EXCESS_OF_BILLING": usd("1150.00"),
        "TRANSFERRED_TO_RECEIVABLES_OR_SETTLED": -usd("3480.00"),
        "FX": usd("50.00"),
    }
    assert february.balanced and march.balanced


# --- CHK-121 -------------------------------------------------------------------------------------


def test_s15_r06_business_combination_line() -> None:
    """CHK-121: a 24-month subscription of 240,000.00 billed upfront on 1 Jan 2025 and acquired on
    1 Jan 2026, established at the cutover of 31 Dec 2025 (reason BUSINESS_COMBINATION)."""
    inception, cutover = date(2025, 1, 1), date(2025, 12, 31)
    calendar = bundles.entity(start=inception, months=24)
    overrides = [("onboarding.method", "CONTRACT", CONTRACT_KEY, "OPENING_BALANCES_AT_CUTOVER")]
    ctx = book_context(calendar, overrides=overrides)
    subscription = obligation(
        "SUB-01",
        [segment(Fraction(240000), usd("240000.00"), start=inception, end=date(2026, 12, 31))],
        convention="MONTHLY_EVEN",
    )
    row = {
        "obligation_key": "SUB-01",
        "billed_cum": Decimal("240000.00"),
        "catch_up_cum": Decimal("0"),
        "delivered_quantity_cum": Decimal("0"),
        "netting_reclass_amount": Decimal("0"),
        "position_obligation": Decimal("120000.00"),
        "pre_standard_revenue_cum": Decimal("0"),
        "remaining_allocation": Decimal("120000.00"),
        "remaining_billing": Decimal("0"),
        "remaining_quantity": Decimal("1"),
        "remaining_ssp": Decimal("240000"),
        "revenue_cum": Decimal("120000.00"),
        "ssp_delivered_cum": Decimal("0"),
    }
    payload = {
        "reason": "BUSINESS_COMBINATION",
        "cutover_date": cutover,
        "migration_batch_id": "MIG-000001",
        "fair_value_contract_liability": Decimal("90000.00"),
        "obligations": [row],
    }
    ev = event_view(CONTRACT_KEY, 3, "OPENING_BALANCE_ESTABLISHED", cutover, payload)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(
        ctx, allocated_state([subscription], events=[ev], inception=inception), ev, tb
    )
    assert after.findings == ()
    (acquired,) = after.obligations
    assert acquired.segments[-1].cause == SegmentCause.OPENING_BALANCE
    baseline = s07_onboarding.baseline_of(acquired)
    assert baseline is not None
    assert baseline.billed_cum - baseline.revenue_cum == usd("120000.00")
    # Stage 07 records no onboarding difference, the only cutover amount stage 14 posts (S07-R-07).
    assert s07_onboarding.differences_of(acquired) == ()
    # Stage 12 input records as if originated: the upfront invoice and 10,000.00 a month.
    flows = [invoice(2, inception, "240000.00")]
    for year, months in ((2025, range(1, 13)), (2026, range(1, 2))):
        for month in months:
            flows.append(
                release(f"{CONTRACT_KEY}/SUB-01", month_end(date(year, month, 1)), "10000.00")
            )
    records = BalanceInputs(
        flows=tuple(flows),
        presented=presented(
            {
                "FY2025-P11": ("130000.00", "0.00", "0.00"),
                "FY2025-P12": ("120000.00", "0.00", "0.00"),
                "FY2026-P01": ("110000.00", "0.00", "0.00"),
            }
        ),
        right_classes=conditional([f"{CONTRACT_KEY}/SUB-01"], ("FY2025-P12", "FY2026-P01")),
    )
    # The acquisition period: the ASC606 opening balances enter as the business-combinations line,
    # contract liability 120,000.00. No flow of the period enters: the 31 Dec release and the
    # invoice are pre-acquisition, so the line creates no journal line.
    december = rollforward_balances(ctx, after, records, ENTITY, "FY2025-P12")
    assert lines(december, CL) == {
        "BUSINESS_COMBINATIONS": usd("120000.00"),
        "CLOSING": usd("120000.00"),
    }
    assert (lines(december, CA), lines(december, UR), december.revenue_relief) == ({}, {}, 0)
    assert december.balanced
    # January 2026: revenue of 10,000.00 from the opening balance, closing 110,000.00.
    january = rollforward_balances(ctx, after, records, ENTITY, "FY2026-P01")
    assert lines(january, CL) == {
        "OPENING": usd("120000.00"),
        "REVENUE_FROM_OPENING_BALANCE": -usd("10000.00"),
        "CLOSING": usd("110000.00"),
    }
    assert january.balanced
    # Before the acquisition the entity presents nothing, whatever the as-if-originated balances.
    november = rollforward_balances(ctx, after, records, ENTITY, "FY2025-P11")
    assert all(amount == 0 for values in november.lines.values() for amount in values.values())


# --- S15-INV-01 ----------------------------------------------------------------------------------


def test_s15_inv_01_opening_plus_lines_equals_closing() -> None:
    worlds = [
        (ex_15_b_context(), ex_15_b_state(), ex_15_b(), (MARCH, APRIL)),
        (*chk_081(), MONTHS_2026[:3]),
        (*ex_12_a(), MONTHS_2026),
    ]
    for ctx, allocated, records, periods in worlds:
        for period_key in periods:
            for view in ("TRANSACTION", "FUNCTIONAL"):
                found = rollforward_balances(ctx, allocated, records, ENTITY, period_key, view=view)
                assert found.currency == (
                    ctx.entities[ENTITY].functional_currency
                    if view == "FUNCTIONAL"
                    else ctx.txn_currency
                )
                assert_ties(found)
    # EX-12-A in USD: the 1 Jan invoice at spot 1.123456 (3,370.37) and the historical reliefs;
    # 15 Mar the licence relieves the last 1,123.46 and creates 567.50 at the March average; 31 Mar
    # the services create 1,135.00 and remeasure 7.50 (closing 1,710.00); 20 Apr the invoice at
    # spot settles 1,717.50 after 7.50 of settlement remeasurement.
    ctx, allocated, records = ex_12_a()
    usd_view = {
        key: rollforward_balances(ctx, allocated, records, ENTITY, key, view="FUNCTIONAL")
        for key in MONTHS_2026
    }
    assert lines(usd_view["FY2026-P01"], CL) == {
        "INCREASES_BILLING": usd("3370.37"),
        "REVENUE_FROM_OTHER_INCREASES": -usd("1123.46"),
        "CLOSING": usd("2246.91"),
    }
    assert lines(usd_view["FY2026-P02"], CL) == {
        "OPENING": usd("2246.91"),
        "REVENUE_FROM_OPENING_BALANCE": -usd("1123.45"),
        "CLOSING": usd("1123.46"),
    }
    assert lines(usd_view[MARCH], CL) == {
        "OPENING": usd("1123.46"),
        "REVENUE_FROM_OPENING_BALANCE": -usd("1123.46"),
    }
    assert lines(usd_view[MARCH], CA) == {
        "REVENUE_IN_EXCESS_OF_BILLING": usd("1702.50"),
        "FX": usd("7.50"),
        "CLOSING": usd("1710.00"),
    }
    assert lines(usd_view[APRIL], CA) == {
        "OPENING": usd("1710.00"),
        "TRANSFERRED_TO_RECEIVABLES_OR_SETTLED": -usd("1717.50"),
        "FX": usd("7.50"),
    }
    # The performing entity presents no contract balance (S12-R-14).
    uk = rollforward_balances(ctx, allocated, records, UK, MARCH, view="FUNCTIONAL")
    assert uk.currency == "GBP"
    assert all(amount == 0 for values in uk.lines.values() for amount in values.values())
    # An unexplained difference is shown as OTHER and fails the tie-out (S15-R-07).
    ctx, allocated, records = ex_15_b_context(), ex_15_b_state(), ex_15_b()
    wrong = dataclasses.replace(
        records,
        presented=presented(
            {MARCH: ("5000.00", "0.00", "0.00"), APRIL: ("250.00", "0.00", "0.00")}
        ),
    )
    found = rollforward_balances(ctx, allocated, wrong, ENTITY, APRIL)
    assert (found.lines[CL]["OTHER"], found.lines[CL]["CLOSING"], found.balanced) == (
        usd("50.00"),
        usd("250.00"),
        False,
    )
    liability = found.lines[CL]
    moved = sum(amount for code, amount in liability.items() if code not in ("OPENING", "CLOSING"))
    assert liability["OPENING"] + moved == liability["CLOSING"]
