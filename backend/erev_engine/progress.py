"""Exact progress functions shared by stages 06, 08 and 09 (ENGINE_SPEC §0.2, CV-61, CV-62; ALG-11).

Every function returns a ``Fraction`` in [0, 1] (S09-INV-10). The ratio functions take quantities
already measured on the segment's basis: the caller subtracts the boundary quantities for a
``PROSPECTIVE`` segment (CV-62). A zero total with nothing done gives 1 (CV-62); a non-zero
numerator over a zero total raises ``ValueError``, which stages convert to ``NON_FINITE_AMOUNT``
(CV-32). Standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Final

from erev_engine import dates
from erev_engine.money import to_fraction

__all__ = [
    "cost_fraction",
    "hours_fraction",
    "milestone_fraction",
    "output_fraction",
    "right_to_invoice_fraction",
    "series_increments",
    "ssp_delivered_fraction",
    "TIME_CONVENTIONS",
    "time_fraction",
    "time_units",
    "units_fraction",
]

type Number = str | int | Decimal | Fraction

# E-21 ratable_convention (POL-090 as ruled by D-75).
TIME_CONVENTIONS: Final = ("DAILY", "MONTHLY_EVEN", "MID_MONTH")
_MID_MONTH_THRESHOLD: Final = 15  # ALG-11 rule 3


def _ratio(done: Number, total: Number) -> Fraction:
    numerator = to_fraction(done)
    denominator = to_fraction(total)
    if numerator < 0 or denominator < 0:
        raise ValueError("progress quantities must not be negative")
    if denominator == 0:
        if numerator == 0:
            return Fraction(1)
        raise ValueError("progress is undefined: a non-zero quantity over a zero total")
    return min(Fraction(1), numerator / denominator)


def units_fraction(delivered: Number, total_quantity: Number) -> Fraction:
    """Units delivered ÷ total quantity, capped at 1 (ENGINE_SPEC_B §9.2.4; CV-61)."""
    return _ratio(delivered, total_quantity)


def ssp_delivered_fraction(ssp_delivered: Number, remaining_ssp: Number) -> Fraction:
    """``SSP_DELIVERED``: delivered SSP ÷ (delivered SSP + remaining SSP) (CV-61)."""
    return _ratio(ssp_delivered, to_fraction(ssp_delivered) + to_fraction(remaining_ssp))


def cost_fraction(costs_incurred: Number, total_costs: Number) -> Fraction:
    """Cost to cost: costs incurred ÷ total expected costs, capped at 1 (S09-R-14, S09-R-17)."""
    return _ratio(costs_incurred, total_costs)


def hours_fraction(hours_to_date: Number, expected_hours: Number) -> Fraction:
    """``LABOUR_HOURS``: hours to date ÷ expected total hours, capped at 1 (S09-R-15)."""
    return _ratio(hours_to_date, expected_hours)


def output_fraction(progress_ratio: Number, base_ratio: Number = 0) -> Fraction:
    """``OUTPUT_PERCENT``: p(d), or (p(d) − p_k) ÷ (1 − p_k) since a boundary (§9.2.4)."""
    return _since_base(progress_ratio, base_ratio)


def milestone_fraction(cumulative_weight: Number, base_weight: Number = 0) -> Fraction:
    """``MILESTONE``: w(d), or (w(d) − w_k) ÷ (1 − w_k) since a boundary (§9.2.4)."""
    return _since_base(cumulative_weight, base_weight)


def right_to_invoice_fraction(
    realised: Number, stated: Number, base_realised: Number = 0
) -> Fraction:
    """``RIGHT_TO_INVOICE``: min(1, R ÷ P) on the inception basis, min(1, (R − R_k) ÷ (P − R_k))
    since a boundary (ENGINE_SPEC_B S09-R-18 rev 1.20, §9.2.4; D-98 candidate 28). A denominator
    that is not positive gives 1 (P = 0 is an X = 0 component); R below R_k gives 0."""
    current, total, base = to_fraction(realised), to_fraction(stated), to_fraction(base_realised)
    denominator = total - base
    if denominator <= 0:
        return Fraction(1)
    return min(Fraction(1), max(Fraction(0), current - base) / denominator)


def _since_base(value: Number, base: Number) -> Fraction:
    current = to_fraction(value)
    boundary = to_fraction(base)
    if not (0 <= current <= 1 and 0 <= boundary <= 1):
        raise ValueError("cumulative ratios must lie between 0 and 1")
    return _ratio(current - boundary, 1 - boundary)


def time_fraction(
    convention: str,
    start: date,
    end: date,
    d: date,
    *,
    calendar: Sequence[dates.DateRange] | None = None,
) -> Fraction:
    """ALG-11 exact cumulative progress f(d) over the inclusive term [start, end] (POLICIES §2.12).

    ``calendar`` holds the performing entity's accounting periods; ``None`` means calendar months
    (E-50 ``MONTHLY``). f(d) = 0 before ``start`` for every convention. ``DAILY`` and
    ``MONTHLY_EVEN`` give 1 on and after ``end``; ``MID_MONTH`` evaluates ALG-11 at every date, so
    it completes on the last day of its last counted period, which may precede or follow ``end``
    (D-79).
    """
    if convention not in TIME_CONVENTIONS:
        raise ValueError(f"unknown ratable convention {convention!r}")
    dates.require_date(start, "start")
    dates.require_date(end, "end")
    dates.require_date(d, "d")
    if end < start:
        raise ValueError("the term end must not precede its start")
    if d < start:
        return Fraction(0)
    if d >= end and convention != "MID_MONTH":
        return Fraction(1)
    if convention == "DAILY":
        return Fraction(dates.days_inclusive(start, d), dates.days_inclusive(start, end))
    periods = (
        dates.calendar_months(start, end)
        if calendar is None
        else dates.covering_periods(calendar, start, end)
    )
    if convention == "MONTHLY_EVEN":
        return _monthly_even(periods, start, end, d)
    return _mid_month(periods, start, end, d)


def time_units(
    convention: str,
    start: date,
    end: date,
    *,
    calendar: Sequence[dates.DateRange] | None = None,
) -> Fraction:
    """ALG-11's count of the term's periods under ``convention``: ``time_fraction``'s denominator.

    ``DAILY`` the days of [start, end]; ``MONTHLY_EVEN`` W = whole periods + Σ n(P) ÷ D(P) over
    partial periods; ``MID_MONTH`` the counted periods (ALG-11 rule 3). A series obligation's
    remaining increments at d are ``time_units`` × (1 − f(d − 1)) (ENGINE_SPEC S06-R-11 series
    row; Codex C1B-S1): the increment count and the remaining-service share share one denominator.
    """
    if convention not in TIME_CONVENTIONS:
        raise ValueError(f"unknown ratable convention {convention!r}")
    dates.require_date(start, "start")
    dates.require_date(end, "end")
    if end < start:
        raise ValueError("the term end must not precede its start")
    if convention == "DAILY":
        return Fraction(dates.days_inclusive(start, end))
    periods = (
        dates.calendar_months(start, end)
        if calendar is None
        else dates.covering_periods(calendar, start, end)
    )
    if convention == "MONTHLY_EVEN":
        weight, _ = _monthly_even_weights(periods, start, end, end)
        return weight
    return Fraction(len(_mid_month_counted(periods, start, end)))


def series_increments(
    convention: str,
    unit: str,
    start: date,
    end: date,
    *,
    calendar: Sequence[dates.DateRange] | None = None,
) -> Fraction:
    """The increments of [start, end] in the series ``unit`` as the pinned convention counts them
    (S06-R-11 series row): ``day`` the days; ``month`` the convention's periods (``MONTHLY_EVEN``
    whole plus day-prorated partial periods, ``MID_MONTH`` the counted periods) — a month increment
    under ``DAILY``, which counts days, takes the calendar-month weights of ``MONTHLY_EVEN`` so that
    increments × (1 − f(d − 1)) is the remaining service in months."""
    if unit == "day":
        return Fraction(dates.days_inclusive(start, end))
    if unit != "month":
        raise ValueError(f"series increment unit {unit!r} is not a time increment")
    monthly = "MONTHLY_EVEN" if convention == "DAILY" else convention
    return time_units(monthly, start, end, calendar=calendar)


def _monthly_even_weights(
    periods: Sequence[dates.DateRange], start: date, end: date, d: date
) -> tuple[Fraction, Fraction]:
    # W = whole periods + Σ n(P) ÷ D(P) over partial periods; Elapsed(d) likewise through d.
    weight = Fraction(0)
    elapsed = Fraction(0)
    for period in periods:
        term_start = max(start, period.start_date)
        term_end = min(end, period.end_date)
        length = dates.days_inclusive(period.start_date, period.end_date)
        in_term = dates.days_inclusive(term_start, term_end)
        if in_term == length:
            weight += 1
            elapsed += 1 if period.end_date <= d else 0
        else:
            weight += Fraction(in_term, length)
            elapsed += Fraction(dates.days_inclusive(term_start, min(term_end, d)), length)
    return weight, elapsed


def _monthly_even(periods: Sequence[dates.DateRange], start: date, end: date, d: date) -> Fraction:
    weight, elapsed = _monthly_even_weights(periods, start, end, d)
    return elapsed / weight


def _mid_month_counted(
    periods: Sequence[dates.DateRange], start: date, end: date
) -> Sequence[dates.DateRange]:
    last_index = len(periods) - 1
    first = 0 if _day_number(start, periods[0]) <= _MID_MONTH_THRESHOLD else 1
    last = (
        last_index
        if _day_number(end, periods[last_index]) >= _MID_MONTH_THRESHOLD
        else last_index - 1
    )
    return periods[first : last + 1] if first <= last else periods[last_index:]


def _mid_month(periods: Sequence[dates.DateRange], start: date, end: date, d: date) -> Fraction:
    counted = _mid_month_counted(periods, start, end)
    completed = sum(1 for period in counted if period.end_date <= d)
    return Fraction(completed, len(counted))


def _day_number(x: date, period: dates.DateRange) -> int:
    return (x - period.start_date).days + 1
