"""Day counts, month arithmetic and period lookup (ENGINE_SPEC §0.2, CV-12, CV-13; S04-R-12).

Dates are plain ``date`` values in the owning entity's time zone (D-19); a ``datetime`` is rejected.
Period lookup reads the bundle calendar through read-only protocols, so any frozen dataclass with
the ``EntityInput`` and ``PeriodInput`` fields of ENGINE_SPEC §0.4 satisfies them. Standard library
only; no clock (DG-ENG-01).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Protocol

from erev_engine.errors import EngineError

__all__ = [
    "POSTABLE_STATES",
    "DateRange",
    "EntityCalendar",
    "MonthPeriod",
    "PeriodLike",
    "add_months",
    "calendar_months",
    "covering_periods",
    "days_in_month",
    "days_inclusive",
    "first_open_period_on_or_after",
    "month_end",
    "month_ends_between",
    "month_start",
    "period_of",
    "period_state",
    "require_date",
]

# States an amount may post into (ENGINE_SPEC S08-R-08, CV-13; 05 RCP-04; D-79).
POSTABLE_STATES: Final = frozenset({"open", "closing", "reopened"})


class DateRange(Protocol):
    """An inclusive date range: an accounting period or a calendar month."""

    @property
    def start_date(self) -> date: ...

    @property
    def end_date(self) -> date: ...


class PeriodLike(DateRange, Protocol):
    """The ``PeriodInput`` fields period lookup reads (ENGINE_SPEC §0.4; 04 T-REF-05)."""

    @property
    def period_key(self) -> str: ...

    @property
    def states(self) -> tuple[tuple[str, str], ...]: ...


class EntityCalendar(Protocol):
    """The ``EntityInput`` fields period lookup reads (ENGINE_SPEC §0.4)."""

    @property
    def periods(self) -> Sequence[PeriodLike]: ...


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    """A calendar month as an inclusive date range (the MONTHLY calendar pattern of E-50)."""

    start_date: date
    end_date: date


def require_date(value: object, name: str) -> date:
    """``value`` as a plain ``date``; ``datetime`` and other types raise ``TypeError``."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{name} must be a date, not {type(value).__qualname__}")
    return value


def days_inclusive(start: date, end: date) -> int:
    """Days in [start, end], both dates counted; 0 when ``end`` precedes ``start``."""
    require_date(start, "start")
    require_date(end, "end")
    return max((end - start).days + 1, 0)


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def month_start(d: date) -> date:
    require_date(d, "d")
    return d.replace(day=1)


def month_end(d: date) -> date:
    require_date(d, "d")
    return d.replace(day=days_in_month(d.year, d.month))


def add_months(d: date, months: int) -> date:
    """``d`` moved by ``months`` calendar months, clamped to the last day of the target month."""
    require_date(d, "d")
    if isinstance(months, bool) or not isinstance(months, int):
        raise TypeError("months must be int")
    index = d.year * 12 + d.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(d.day, days_in_month(year, month)))


def month_ends_between(a: date, b: date) -> int:
    """m(a, b): the number of calendar month ends e with a < e ≤ b (S04-R-12 rev 1.3)."""
    return max(_month_ends_through(b) - _month_ends_through(a), 0)


def _month_ends_through(d: date) -> int:
    # Month ends on or before d, counted from a fixed origin.
    require_date(d, "d")
    return d.year * 12 + d.month - 1 + (1 if d == month_end(d) else 0)


def calendar_months(start: date, end: date) -> tuple[MonthPeriod, ...]:
    """The calendar months from the month of ``start`` through the month of ``end``."""
    if require_date(end, "end") < require_date(start, "start"):
        raise ValueError("end must not precede start")
    months: list[MonthPeriod] = []
    first = month_start(start)
    while first <= end:
        months.append(MonthPeriod(first, month_end(first)))
        first = month_end(first) + timedelta(days=1)
    return tuple(months)


def covering_periods[P: DateRange](periods: Sequence[P], start: date, end: date) -> tuple[P, ...]:
    """The contiguous periods from the one containing ``start`` through the one containing ``end``.

    A date outside every period, or a gap between consecutive periods, raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` with ``detail["rule"] == "CV-12"``.
    """
    if require_date(end, "end") < require_date(start, "start"):
        raise ValueError("end must not precede start")
    ordered = sorted(periods, key=lambda p: (p.start_date, p.end_date))
    first = _index_containing(ordered, start)
    last = _index_containing(ordered, end)
    selected = ordered[first : last + 1]
    for previous, current in zip(selected, selected[1:], strict=False):
        if current.start_date != previous.end_date + timedelta(days=1):
            raise _no_period(current.start_date - timedelta(days=1))
    return tuple(selected)


def _index_containing[P: DateRange](ordered: Sequence[P], d: date) -> int:
    for index, period in enumerate(ordered):
        if period.start_date <= d <= period.end_date:
            return index
    raise _no_period(d)


def _no_period(d: date) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        "no accounting period of the entity contains the date",
        detail={"rule": "CV-12", "date": d.isoformat()},
    )


def period_of(entity: EntityCalendar, d: date) -> PeriodLike:
    """The period of ``entity.periods`` whose [start_date, end_date] contains ``d`` (CV-12)."""
    require_date(d, "d")
    ordered = sorted(entity.periods, key=lambda p: (p.start_date, p.end_date))
    return ordered[_index_containing(ordered, d)]


def period_state(period: PeriodLike, book_code: str) -> str:
    """The E-04 state of ``period`` for ``book_code`` at ``known_at`` (ENGINE_SPEC §0.4).

    Bundle assembly supplies a state for every book the entity keeps; a missing book raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` with ``detail["rule"] == "CV-13"``.
    """
    for code, state in period.states:
        if code == book_code:
            return state
    raise EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        "the period carries no state for the book",
        detail={"rule": "CV-13", "period_key": period.period_key, "book_code": book_code},
    )


def first_open_period_on_or_after(
    entity: EntityCalendar, book_code: str, d: date
) -> PeriodLike | None:
    """The earliest period ending on or after ``d`` whose state is in ``POSTABLE_STATES``.

    ``open``, ``closing`` and ``reopened`` periods qualify; ``None`` when no such period exists
    (ENGINE_SPEC S08-R-08; 05 RCP-04; DG-KRN-TIME-04 as amended by D-79). A period without a state
    for the book raises ``ENGINE_INVARIANT_VIOLATED`` (CV-13).
    """
    require_date(d, "d")
    for period in sorted(entity.periods, key=lambda p: (p.start_date, p.end_date)):
        if period.end_date >= d and period_state(period, book_code) in POSTABLE_STATES:
            return period
    return None
