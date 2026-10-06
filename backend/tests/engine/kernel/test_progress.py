"""Exact progress functions (POLICIES ALG-11 §2.12 CHK-140 to CHK-145; ENGINE_SPEC CV-61, CV-62)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine.dates import MonthPeriod, calendar_months
from erev_engine.errors import EngineError
from erev_engine.money import period_amounts
from erev_engine.progress import (
    TIME_CONVENTIONS,
    cost_fraction,
    hours_fraction,
    milestone_fraction,
    output_fraction,
    ssp_delivered_fraction,
    time_fraction,
    units_fraction,
)

CHK_140_START = date(2026, 2, 10)
CHK_140_END = date(2027, 2, 9)


def _schedule(convention: str, amount_minor: int, start: date, end: date) -> list[int]:
    # One POB on a monthly calendar, so X = A (POLICIES §2.12 numeric checks); f_t at period ends.
    progress = [
        time_fraction(convention, start, end, month.end_date)
        for month in calendar_months(start, end)
    ]
    return period_amounts(Fraction(amount_minor, 100), amount_minor, progress, 2)


def test_time_fraction_daily() -> None:
    f = time_fraction("DAILY", CHK_140_START, CHK_140_END, date(2026, 6, 15))
    assert f == Fraction(126, 365)
    # CHK-140 schedule
    assert _schedule("DAILY", 1200000, CHK_140_START, CHK_140_END) == [
        62466, 101918, 98630, 101918, 98630, 101917, 101918,
        98630, 101918, 98630, 101918, 101918, 29589,
    ]  # fmt: skip


def test_time_fraction_monthly_even() -> None:
    assert time_fraction("MONTHLY_EVEN", CHK_140_START, CHK_140_END, date(2026, 2, 20)) == Fraction(
        11, 336
    )
    assert time_fraction("MONTHLY_EVEN", CHK_140_START, CHK_140_END, date(2026, 6, 15)) == Fraction(
        103, 336
    )
    # CHK-141 schedule: W = 19/28 + 11 + 9/28 = 12
    assert _schedule("MONTHLY_EVEN", 1200000, CHK_140_START, CHK_140_END) == (
        [67857] + [100000] * 11 + [32143]
    )


def test_time_fraction_mid_month() -> None:
    assert time_fraction("MID_MONTH", CHK_140_START, CHK_140_END, date(2026, 6, 15)) == Fraction(
        1, 3
    )
    # CHK-142 schedule: February 2026 to January 2027 counted, m = 12
    assert _schedule("MID_MONTH", 1200000, CHK_140_START, CHK_140_END) == [100000] * 12 + [0]


def test_time_fraction_edges() -> None:
    for convention in TIME_CONVENTIONS:
        assert time_fraction(convention, CHK_140_START, CHK_140_END, date(2026, 2, 9)) == 0
    # On and after the end 1 under DAILY and MONTHLY_EVEN only; MID_MONTH follows ALG-11 (D-79).
    for convention in ("DAILY", "MONTHLY_EVEN"):
        assert time_fraction(convention, CHK_140_START, CHK_140_END, CHK_140_END) == 1
        assert time_fraction(convention, CHK_140_START, CHK_140_END, date(2027, 3, 1)) == 1

    # CHK-145 (a): the rule counts no period, so the fallback counts February 2026.
    start, end = date(2026, 1, 20), date(2026, 2, 10)
    assert time_fraction("MID_MONTH", start, end, date(2026, 1, 31)) == 0
    assert time_fraction("MID_MONTH", start, end, date(2026, 2, 28)) == 1

    # S09-INV-10 contract: 0 ≤ f ≤ 1 and non-decreasing over every day around the CHK-140 term.
    for convention in TIME_CONVENTIONS:
        previous = Fraction(0)
        d = CHK_140_START - timedelta(days=3)
        while d <= CHK_140_END + timedelta(days=3):
            f = time_fraction(convention, CHK_140_START, CHK_140_END, d)
            assert previous <= f <= 1
            previous = f
            d += timedelta(days=1)

    with pytest.raises(ValueError, match="convention"):
        time_fraction("MONTHLY_WHOLE_MONTHS", CHK_140_START, CHK_140_END, date(2026, 6, 15))
    with pytest.raises(ValueError):
        time_fraction("DAILY", CHK_140_END, CHK_140_START, date(2026, 6, 15))
    with pytest.raises(TypeError):
        time_fraction("DAILY", CHK_140_START, CHK_140_END, datetime(2026, 6, 15))

    # A one-day term completes on its only day.
    assert time_fraction("MONTHLY_EVEN", date(2026, 3, 5), date(2026, 3, 5), date(2026, 3, 5)) == 1


def test_chk_143_monthly_even_whole_and_partial_terms() -> None:
    # (a) whole months equal CHK-004
    whole = _schedule("MONTHLY_EVEN", 3500000, date(2026, 1, 1), date(2027, 12, 31))
    assert whole[:3] == [145833, 145834, 145833]
    assert sum(whole[:23]) == 3354167
    assert whole[23] == 145833
    assert sum(whole) == 3500000
    # (b) partial first and last months: W = 2,885/868
    start, end = date(2026, 2, 10), date(2026, 5, 20)
    assert time_fraction("MONTHLY_EVEN", start, end, date(2026, 2, 28)) == Fraction(
        19, 28
    ) / Fraction(2885, 868)
    assert _schedule("MONTHLY_EVEN", 300000, start, end) == [61248, 90260, 90260, 58232]
    assert _schedule("DAILY", 300000, start, end) == [57000, 93000, 90000, 60000]


def test_chk_144_mid_month_counted_periods() -> None:
    assert _schedule("MID_MONTH", 1000000, date(2026, 3, 20), date(2026, 10, 10)) == [
        0, 166667, 166666, 166667, 166667, 166666, 166667, 0,
    ]  # fmt: skip


def test_chk_145_mid_month_edge_cases() -> None:
    assert _schedule("MID_MONTH", 50000, date(2026, 1, 20), date(2026, 2, 10)) == [0, 50000]
    assert _schedule("MID_MONTH", 50000, date(2026, 1, 5), date(2026, 1, 10)) == [50000]
    assert _schedule("MID_MONTH", 130000, date(2026, 1, 15), date(2027, 1, 15)) == [10000] * 13


def test_alg_11_mid_month_after_term_end() -> None:
    # CHK-145 (a): the fallback counts February 2026, which ends after the term end.
    start, end = date(2026, 1, 20), date(2026, 2, 10)
    assert time_fraction("MID_MONTH", start, end, end) == 0
    assert time_fraction("MID_MONTH", start, end, date(2026, 2, 28)) == 1
    # CHK-145 (b): the fallback counts January 2026.
    start, end = date(2026, 1, 5), date(2026, 1, 10)
    assert time_fraction("MID_MONTH", start, end, end) == 0
    assert time_fraction("MID_MONTH", start, end, date(2026, 1, 31)) == 1
    # CHK-145 (c): m = 13, and January 2027 completes on its last day.
    start, end = date(2026, 1, 15), date(2027, 1, 15)
    assert time_fraction("MID_MONTH", start, end, end) == Fraction(12, 13)
    assert time_fraction("MID_MONTH", start, end, date(2027, 1, 20)) == Fraction(12, 13)
    assert time_fraction("MID_MONTH", start, end, date(2027, 1, 31)) == 1

    terms = (
        (CHK_140_START, CHK_140_END),
        (date(2026, 1, 20), date(2026, 2, 10)),
        (date(2026, 1, 5), date(2026, 1, 10)),
        (date(2026, 1, 15), date(2027, 1, 15)),
    )
    for convention in ("DAILY", "MONTHLY_EVEN"):
        for term_start, term_end in terms:
            assert time_fraction(convention, term_start, term_end, term_end) == 1


def test_time_fraction_calendar_periods() -> None:
    # Explicit calendar months give the default result.
    months = calendar_months(CHK_140_START, CHK_140_END)
    for convention in TIME_CONVENTIONS:
        assert time_fraction(
            convention, CHK_140_START, CHK_140_END, date(2026, 6, 15), calendar=months
        ) == time_fraction(convention, CHK_140_START, CHK_140_END, date(2026, 6, 15))

    # ALG-11 rule 3: day 15 is the day number within the accounting period (a 4-4-5 pattern).
    periods = (
        MonthPeriod(date(2026, 1, 4), date(2026, 1, 31)),
        MonthPeriod(date(2026, 2, 1), date(2026, 2, 28)),
        MonthPeriod(date(2026, 3, 1), date(2026, 4, 4)),
    )
    start, end = date(2026, 1, 18), date(2026, 3, 20)
    # Day number 15 counts January here; the calendar 18th would not.
    assert time_fraction("MID_MONTH", start, end, date(2026, 1, 31), calendar=periods) == Fraction(
        1, 3
    )
    assert time_fraction("MID_MONTH", start, end, date(2026, 1, 31)) == 0
    # MONTHLY_EVEN: n = 14 of D = 28, whole February, n = 20 of D = 35.
    assert time_fraction("MONTHLY_EVEN", start, end, date(2026, 2, 28), calendar=periods) == (
        Fraction(1, 2) + 1
    ) / (Fraction(1, 2) + 1 + Fraction(20, 35))

    with pytest.raises(EngineError) as raised:
        time_fraction("MONTHLY_EVEN", date(2026, 1, 2), end, date(2026, 2, 1), calendar=periods)
    assert raised.value.detail["rule"] == "CV-12"


def test_ratio_functions() -> None:
    assert units_fraction(2, 5) == Fraction(2, 5)
    assert cost_fraction(420000, 820000) == Fraction(21, 41)
    assert hours_fraction(Decimal("37.5"), 150) == Fraction(1, 4)
    assert ssp_delivered_fraction("300.00", "700.00") == Fraction(3, 10)
    assert output_fraction(Fraction(1, 2)) == Fraction(1, 2)
    assert output_fraction(Fraction(3, 4), Fraction(1, 2)) == Fraction(1, 2)
    assert milestone_fraction("0.4") == Fraction(2, 5)
    assert milestone_fraction(Fraction(7, 10), Fraction(2, 5)) == Fraction(1, 2)

    # CV-62: a zero remaining total with zero done gives 1.
    assert units_fraction(0, 0) == 1
    assert cost_fraction(0, 0) == 1
    assert hours_fraction(0, 0) == 1
    assert ssp_delivered_fraction(0, 0) == 1
    assert output_fraction(1, 1) == 1
    assert milestone_fraction(1, 1) == 1

    # A non-zero numerator over a zero divisor is undefined; stages raise NON_FINITE_AMOUNT (CV-32).
    for function in (units_fraction, cost_fraction, hours_fraction):
        with pytest.raises(ValueError, match="undefined"):
            function(3, 0)

    # Capped at 1 (§9.2.4 min(1, …); S09-R-17); negative quantities and ratios outside [0, 1] raise.
    assert units_fraction(6, 5) == 1
    assert cost_fraction(900000, 820000) == 1
    with pytest.raises(ValueError):
        units_fraction(-1, 5)
    with pytest.raises(ValueError):
        cost_fraction(1, -5)
    with pytest.raises(ValueError):
        output_fraction(Fraction(3, 2))
    with pytest.raises(ValueError):
        milestone_fraction(Fraction(1, 4), Fraction(1, 2))
    with pytest.raises(TypeError):
        units_fraction(0.5, 1)  # type: ignore[arg-type]
