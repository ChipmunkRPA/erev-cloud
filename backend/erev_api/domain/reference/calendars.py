"""Fiscal calendar rules and period generation (04 T-REF-04, T-REF-05, E-50; 03 REQ-REF-002,
REQ-REF-003; PRD WLD-P-05; DESIGN_SYSTEM DS-FMT-19; BUILD_SPEC RFD-1, BS3-D-16).

A fiscal year is named by the calendar year of the month in which it ends (T-REF-05
``fiscal_year``): the month before ``fiscal_year_start_month``, or December for a January start.
``MONTHLY`` calendars hold the twelve Gregorian months from ``fiscal_year_start_month``, named
``Sep 2026``. Week-based calendars end each fiscal year on the ``week_end_day`` weekday (ISO, 1
Monday to 7 Sunday) that is last in that month (``LAST_WEEKDAY_OF_MONTH``) or nearest to its last
day (``NEAREST_WEEKDAY_TO_MONTH_END``), so a year holds 52 or 53 weeks (BS3-D-16). The weeks of each
period follow the pattern, a 53-week year adds the extra week to the last period, and periods are
named ``FY2026 P09`` (DS-FMT-19). This module is pure: no database and no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Final

from erev_api.enums import CalendarPattern
from erev_api.problems import ProblemError

LAST_WEEKDAY_OF_MONTH: Final = "LAST_WEEKDAY_OF_MONTH"
NEAREST_WEEKDAY_TO_MONTH_END: Final = "NEAREST_WEEKDAY_TO_MONTH_END"
YEAR_END_ANCHORS: Final = (LAST_WEEKDAY_OF_MONTH, NEAREST_WEEKDAY_TO_MONTH_END)
MONTHS: Final = 12
WEEK_DAYS: Final = 7
BASE_WEEKS: Final = 52
MONTH_ABBREVIATIONS: Final = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
# Weeks of the periods of one quarter, repeated for the four quarters (E-50). [J] W5253 names the
# 52/53-week year rule and no period layout, so it takes the 4-4-5 layout (L1-1-Q-2).
QUARTER_WEEKS: Final = MappingProxyType(
    {
        CalendarPattern.P445: (4, 4, 5),
        CalendarPattern.P454: (4, 5, 4),
        CalendarPattern.P544: (5, 4, 4),
        CalendarPattern.W5253: (4, 4, 5),
    }
)
P13_WEEKS: Final = (4,) * 13
RULE_CALENDAR: Final = "T-REF-04"
WEEK_END_DAY_REQUIRED: Final = (
    "A week-based calendar needs the weekday its weeks end on, from 1 (Monday) to 7 (Sunday)."
)
ANCHOR_REQUIRED: Final = "A week-based calendar needs a year-end anchor."
WEEK_END_DAY_MONTHLY: Final = "A monthly calendar has no week end day."
ANCHOR_MONTHLY: Final = "A monthly calendar has no year-end anchor."


@dataclass(frozen=True, slots=True)
class CalendarRule:
    """The T-REF-04 pattern fields of a calendar."""

    pattern: CalendarPattern
    fiscal_year_start_month: int = 1
    week_end_day: int | None = None
    year_end_anchor: str | None = None


@dataclass(frozen=True, slots=True)
class PeriodSpec:
    """One T-REF-05 row of a fiscal year, before it has an id."""

    fiscal_year: int
    period_no: int
    quarter_no: int
    period_key: str
    name: str
    start_date: date
    end_date: date

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


def is_week_based(pattern: CalendarPattern) -> bool:
    """Every E-50 pattern except ``MONTHLY`` counts weeks (T-REF-04 ``week_end_day``)."""
    return pattern is not CalendarPattern.MONTHLY


def rule_errors(rule: CalendarRule) -> list[ProblemError]:
    """T-REF-04 findings: a week-based pattern needs ``week_end_day`` and ``year_end_anchor``, and
    ``MONTHLY`` takes neither."""
    week_based = is_week_based(rule.pattern)
    findings = (
        ("week_end_day", rule.week_end_day, WEEK_END_DAY_REQUIRED, WEEK_END_DAY_MONTHLY),
        ("year_end_anchor", rule.year_end_anchor, ANCHOR_REQUIRED, ANCHOR_MONTHLY),
    )
    errors: list[ProblemError] = []
    for field, value, required, refused in findings:
        if week_based and value is None:
            errors.append(ProblemError(field=field, rule_id=RULE_CALENDAR, message=required))
        elif not week_based and value is not None:
            errors.append(ProblemError(field=field, rule_id=RULE_CALENDAR, message=refused))
    return errors


def period_key(fiscal_year: int, period_no: int) -> str:
    """T-REF-05 and API-C-11: ``FY<fiscal_year>-P<period_no two digits>``."""
    return f"FY{fiscal_year}-P{period_no:02d}"


def quarter_of(period_no: int) -> int:
    """Periods 1 to 3 are quarter 1, and so on; period 13 belongs to quarter 4 (T-REF-05)."""
    return min((period_no - 1) // 3 + 1, 4)


def _month_end(year: int, month: int) -> date:
    following = date(year + 1, 1, 1) if month == MONTHS else date(year, month + 1, 1)
    return following - timedelta(days=1)


def _end_month(rule: CalendarRule) -> int:
    """The month in which a fiscal year ends: the month before ``fiscal_year_start_month``."""
    return rule.fiscal_year_start_month - 1 or MONTHS


def week_year_end(rule: CalendarRule, fiscal_year: int) -> date:
    """BS3-D-16: the last day of ``fiscal_year`` under a week-based rule."""
    if rule.week_end_day is None or rule.year_end_anchor not in YEAR_END_ANCHORS:
        raise ValueError("a week-based calendar needs week_end_day and year_end_anchor")
    month_end = _month_end(fiscal_year, _end_month(rule))
    back = (month_end.isoweekday() - rule.week_end_day) % WEEK_DAYS
    last_weekday = month_end - timedelta(days=back)
    # The nearest weekday lies at most three days away, so the two candidates never tie.
    if rule.year_end_anchor == LAST_WEEKDAY_OF_MONTH or back <= WEEK_DAYS // 2:
        return last_weekday
    return last_weekday + timedelta(days=WEEK_DAYS)


def period_weeks(pattern: CalendarPattern) -> tuple[int, ...]:
    """The weeks of each period of a 52-week year of a week-based pattern."""
    if pattern is CalendarPattern.P13:
        return P13_WEEKS
    return QUARTER_WEEKS[pattern] * 4


def _spec(fiscal_year: int, period_no: int, name: str, start: date, end: date) -> PeriodSpec:
    return PeriodSpec(
        fiscal_year=fiscal_year,
        period_no=period_no,
        quarter_no=quarter_of(period_no),
        period_key=period_key(fiscal_year, period_no),
        name=name,
        start_date=start,
        end_date=end,
    )


def _monthly(rule: CalendarRule, fiscal_year: int) -> tuple[PeriodSpec, ...]:
    first = rule.fiscal_year_start_month
    specs: list[PeriodSpec] = []
    for index in range(MONTHS):
        month = (first - 1 + index) % MONTHS + 1
        year = fiscal_year - 1 if first > 1 and month >= first else fiscal_year
        name = f"{MONTH_ABBREVIATIONS[month - 1]} {year}"
        specs.append(
            _spec(fiscal_year, index + 1, name, date(year, month, 1), _month_end(year, month))
        )
    return tuple(specs)


def _week_based(rule: CalendarRule, fiscal_year: int) -> tuple[PeriodSpec, ...]:
    start = week_year_end(rule, fiscal_year - 1) + timedelta(days=1)
    end = week_year_end(rule, fiscal_year)
    weeks = list(period_weeks(rule.pattern))
    # Consecutive year ends fall on one weekday 52 or 53 weeks apart (BS3-D-16).
    weeks[-1] += ((end - start).days + 1) // WEEK_DAYS - BASE_WEEKS
    specs: list[PeriodSpec] = []
    for index, count in enumerate(weeks):
        period_end = start + timedelta(days=count * WEEK_DAYS - 1)
        specs.append(
            _spec(fiscal_year, index + 1, f"FY{fiscal_year} P{index + 1:02d}", start, period_end)
        )
        start = period_end + timedelta(days=1)
    if specs[-1].end_date != end:
        raise RuntimeError(f"FY{fiscal_year}: the periods do not end on the fiscal year end")
    return tuple(specs)


def generate_periods(rule: CalendarRule, fiscal_year: int) -> tuple[PeriodSpec, ...]:
    """The periods of ``fiscal_year`` in period order; ``ValueError`` for an invalid rule."""
    errors = rule_errors(rule)
    if errors:
        raise ValueError("; ".join(str(error.message) for error in errors))
    if is_week_based(rule.pattern):
        return _week_based(rule, fiscal_year)
    return _monthly(rule, fiscal_year)
