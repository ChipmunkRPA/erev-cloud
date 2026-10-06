"""ALG-11 time-elapsed conventions and re-baselined ratable schedules at stage level (ENC-2).

POLICIES §2.12 CHK-140 to CHK-145 (POL-090) and §2.1.5 CHK-006, run through stage 09 over
``AllocatedState`` built against the documented contract (support.recognition).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, PeriodInput, ResolvedPolicyInput
from erev_engine.money import round_half_up
from erev_engine.stages.s09_recognition import components, run
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState, PolicyResolver
from erev_engine.trace import TraceBuilder, reevaluate
from support.bundles import entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

O1 = f"{CONTRACT_KEY}/POB-01"
CHK_140_TERM = (date(2026, 2, 10), date(2027, 2, 9))


def _ratable(
    x_exact: Fraction,
    start: date,
    end: date,
    convention: str | None,
    *,
    a_posted: int | None = None,
) -> ObligationState:
    posted = round_half_up(x_exact, 2) if a_posted is None else a_posted
    return obligation(
        "POB-01", [segment(x_exact, posted, start=start, end=end)], convention=convention
    )


def _schedule(
    ob: ObligationState,
    *,
    calendar: EntityInput | None = None,
    inception: date | None = None,
    ctx: BookContext | None = None,
) -> tuple[dict[str, int], BookContext, AllocatedState]:
    """Period amounts of one obligation; the trace re-evaluates node for node (DG-ENG-04)."""
    assert ob.start_date is not None and ob.end_date is not None
    first = inception or ob.start_date
    if calendar is None:
        months = 12 * (ob.end_date.year - first.year) + ob.end_date.month - first.month + 1
        calendar = entity(start=first.replace(day=1), months=months)
    ctx = book_context(calendar) if ctx is None else ctx
    st = allocated_state([ob], inception=first, statuses=((first, "ACTIVE"),))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return period_amounts(targets_by_period(state, O1)), ctx, st


def _progress(ctx: BookContext, st: AllocatedState, d: date) -> Fraction:
    at = components.target_at(ctx, st, st.obligations[0], d)
    assert at.fixed is not None
    return at.fixed.progress.value


def _usd(values: list[str]) -> list[int]:
    return [usd(value) for value in values]


def test_chk_140_daily_365_day_term() -> None:
    amounts, ctx, st = _schedule(_ratable(Fraction(12000), *CHK_140_TERM, "DAILY"))
    assert list(amounts.values()) == _usd(
        [
            "624.66",
            "1019.18",
            "986.30",
            "1019.18",
            "986.30",
            "1019.17",
            "1019.18",
            "986.30",
            "1019.18",
            "986.30",
            "1019.18",
            "1019.18",
            "295.89",
        ]
    )
    assert list(amounts)[0] == "FY2026-P02" and list(amounts)[-1] == "FY2027-P02"
    assert sum(amounts.values()) == usd("12000.00")
    assert _progress(ctx, st, date(2026, 6, 15)) == Fraction(126, 365)


def test_chk_141_monthly_even_partial_months() -> None:
    amounts, ctx, st = _schedule(_ratable(Fraction(12000), *CHK_140_TERM, "MONTHLY_EVEN"))
    assert list(amounts.values()) == _usd(["678.57"] + ["1000.00"] * 11 + ["321.43"])
    assert sum(amounts.values()) == usd("12000.00")
    # W = 19/28 + 11 + 9/28 = 12
    assert _progress(ctx, st, date(2026, 2, 20)) == Fraction(11, 336)
    assert _progress(ctx, st, date(2026, 6, 15)) == Fraction(103, 336)


def test_chk_142_mid_month_day_15_rule() -> None:
    amounts, ctx, st = _schedule(_ratable(Fraction(12000), *CHK_140_TERM, "MID_MONTH"))
    assert list(amounts.values()) == _usd(["1000.00"] * 12 + ["0.00"])
    assert _progress(ctx, st, date(2026, 6, 15)) == Fraction(1, 3)


def test_chk_143_monthly_even_whole_and_partial_terms() -> None:
    # (a) CHK-004 on a whole-month term.
    amounts, _, _ = _schedule(
        _ratable(Fraction(35000), date(2026, 1, 1), date(2027, 12, 31), "MONTHLY_EVEN")
    )
    values = list(amounts.values())
    assert values[:3] == _usd(["1458.33", "1458.34", "1458.33"])
    assert sum(values[:23]) == usd("33541.67")
    assert values[23] == usd("1458.33")
    assert len(values) == 24 and sum(values) == usd("35000.00")

    # (b) W = 19/28 + 2 + 20/31 = 2,885/868, and DAILY on the same term.
    term = (date(2026, 2, 10), date(2026, 5, 20))
    monthly_even, _, _ = _schedule(_ratable(Fraction(3000), *term, "MONTHLY_EVEN"))
    assert list(monthly_even.values()) == _usd(["612.48", "902.60", "902.60", "582.32"])
    daily, _, _ = _schedule(_ratable(Fraction(3000), *term, "DAILY"))
    assert list(daily.values()) == _usd(["570.00", "930.00", "900.00", "600.00"])


def test_chk_144_mid_month_late_start_early_end() -> None:
    amounts, _, _ = _schedule(
        _ratable(Fraction(10000), date(2026, 3, 20), date(2026, 10, 10), "MID_MONTH")
    )
    assert list(amounts) == [f"FY2026-P{month:02d}" for month in range(3, 11)]
    assert list(amounts.values()) == _usd(
        ["0.00", "1666.67", "1666.66", "1666.67", "1666.67", "1666.66", "1666.67", "0.00"]
    )


def test_chk_145_mid_month_edge_cases() -> None:
    # (a) the rule counts no period; the fallback counts February 2026.
    amounts, _, _ = _schedule(
        _ratable(Fraction(500), date(2026, 1, 20), date(2026, 2, 10), "MID_MONTH")
    )
    assert amounts == {"FY2026-P01": 0, "FY2026-P02": usd("500.00")}
    # (b) the fallback counts January 2026.
    amounts, _, _ = _schedule(
        _ratable(Fraction(500), date(2026, 1, 5), date(2026, 1, 10), "MID_MONTH"),
        calendar=entity(months=3),
    )
    assert amounts == {"FY2026-P01": usd("500.00"), "FY2026-P02": 0, "FY2026-P03": 0}
    # (c) both thresholds are inclusive: m = 13.
    amounts, _, _ = _schedule(
        _ratable(Fraction(1300), date(2026, 1, 15), date(2027, 1, 15), "MID_MONTH")
    )
    assert list(amounts.values()) == _usd(["100.00"] * 13)


def test_chk_006_warranty_and_franchisor_schedules_at_stage_level() -> None:
    # S2-WARRANTY-OWN: X = 10,500 × 1,000 ÷ 11,000 over months 13 to 24 of a contract.
    warranty = Fraction(10500 * 1000, 11000)
    assert round_half_up(warranty, 2) == usd("954.55")
    amounts, _, _ = _schedule(
        _ratable(warranty, date(2027, 1, 1), date(2027, 12, 31), "MONTHLY_EVEN"),
        calendar=entity(months=24),
        inception=date(2026, 1, 1),
    )
    months = list(amounts.values())
    assert months[:12] == [0] * 12
    high = {13, 15, 17, 19, 21, 23, 24}
    assert months[12:] == [usd("79.55") if m in high else usd("79.54") for m in range(13, 25)]
    assert months[23] == usd("79.55")  # revenue_month_24

    # S12-FRANCHISOR-OWN: X = 50,000 × 40,000 ÷ 55,000 over ten years; years from December targets.
    licence = Fraction(50000 * 40000, 55000)
    assert round_half_up(licence, 2) == usd("36363.64")
    amounts, _, _ = _schedule(
        _ratable(licence, date(2026, 1, 1), date(2035, 12, 31), "MONTHLY_EVEN"),
        calendar=entity(months=120),
    )
    years = [
        sum(value for key, value in amounts.items() if key.startswith(f"FY{year}-"))
        for year in range(2026, 2036)
    ]
    cumulative = sum(years)
    assert years == [usd("3636.37") if y in {2, 5, 7, 10} else usd("3636.36") for y in range(1, 11)]
    assert years[9] == usd("3636.37")  # licence_year10
    assert cumulative == usd("36363.64")


def test_upfront_fee_option_b_pattern() -> None:
    # POL-029 option B: a 3,000.00 fee over the expected relationship of 36 months.
    amounts, _, _ = _schedule(
        _ratable(Fraction(3000), date(2026, 1, 1), date(2028, 12, 31), "MONTHLY_EVEN")
    )
    months = list(amounts.values())
    assert len(months) == 36
    assert months == [usd("83.34") if m % 3 == 2 else usd("83.33") for m in range(1, 37)]
    assert sum(months) == usd("3000.00")


def test_alg11_rule3_accounting_period_threshold() -> None:
    # A P445 calendar: day 20 of P01 starts in P02; day 34 of P03 counts P03 (ALG-11 rule 3).
    bounds = (
        (date(2026, 1, 1), date(2026, 1, 28)),
        (date(2026, 1, 29), date(2026, 2, 25)),
        (date(2026, 2, 26), date(2026, 4, 1)),
        (date(2026, 4, 2), date(2026, 4, 29)),
    )
    periods = tuple(
        PeriodInput(f"FY2026-P{no:02d}", 2026, no, start, end, (("ASC606", "open"),))
        for no, (start, end) in enumerate(bounds, start=1)
    )
    calendar = EntityInput("US01", "USD", "America/New_York", "P445", periods)
    ob = _ratable(Fraction(1000), date(2026, 1, 20), date(2026, 3, 31), "MID_MONTH")
    amounts, ctx, st = _schedule(ob, calendar=calendar, inception=date(2026, 1, 1))
    assert amounts == {
        "FY2026-P01": 0,
        "FY2026-P02": usd("500.00"),
        "FY2026-P03": usd("500.00"),
        "FY2026-P04": 0,
    }
    at = components.target_at(ctx, st, st.obligations[0], date(2026, 2, 25))
    assert at.fixed is not None and at.fixed.progress.value == Fraction(1, 2)
    assert at.fixed.progress.params["periods"] == (
        "2026-01-01/2026-01-28;2026-01-29/2026-02-25;2026-02-26/2026-04-01"
    )


def test_s09_r08_convention_pinned_or_pol_090() -> None:
    calendar = entity(start=date(2026, 2, 1), months=13)
    base = book_context(calendar)
    override = ResolvedPolicyInput(
        "recognition.time_convention", "OBLIGATION", O1, "MONTHLY_EVEN", "O", "OVR-1", "K"
    )
    policies = sorted(
        (*base.policies.all(), override), key=lambda p: (p.code, p.scope, p.subject_key)
    )
    ctx = dataclasses.replace(base, policies=PolicyResolver(tuple(policies)))
    # No pinned convention: the obligation-level POL-090 value applies (CHK-141 figures).
    unpinned, _, _ = _schedule(_ratable(Fraction(12000), *CHK_140_TERM, None), ctx=ctx)
    assert unpinned["FY2026-P02"] == usd("678.57")
    # A pinned convention wins over the policy value (CHK-142 figures).
    pinned, _, _ = _schedule(_ratable(Fraction(12000), *CHK_140_TERM, "MID_MONTH"), ctx=ctx)
    assert pinned["FY2026-P02"] == usd("1000.00")
