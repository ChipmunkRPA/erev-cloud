"""Day counts, month arithmetic and period lookup (ENGINE_SPEC CV-12, CV-13, S04-R-12; EKC-4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pytest
from erev_engine.dates import (
    POSTABLE_STATES,
    MonthPeriod,
    add_months,
    calendar_months,
    covering_periods,
    days_inclusive,
    first_open_period_on_or_after,
    month_end,
    month_ends_between,
    period_of,
    period_state,
)
from erev_engine.errors import EngineError


@dataclass(frozen=True, slots=True)
class _Period:
    period_key: str
    start_date: date
    end_date: date
    states: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Entity:
    periods: tuple[_Period, ...]


def _fy2023(states: dict[int, str]) -> _Entity:
    return _Entity(
        tuple(
            _Period(
                f"FY2023-P{n:02d}",
                date(2023, n, 1),
                month_end(date(2023, n, 1)),
                (("ASC606", states.get(n, "future")),),
            )
            for n in range(1, 13)
        )
    )


def test_period_lookup() -> None:
    entity = _fy2023({1: "closed", 2: "open"})
    assert period_of(entity, date(2023, 1, 31)).period_key == "FY2023-P01"
    assert period_of(entity, date(2023, 2, 1)).period_key == "FY2023-P02"
    assert period_of(entity, date(2023, 12, 31)).period_key == "FY2023-P12"
    for outside in (date(2022, 12, 31), date(2024, 1, 1)):
        with pytest.raises(EngineError) as raised:
            period_of(entity, outside)
        assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
        assert raised.value.detail["rule"] == "CV-12"

    open_period = first_open_period_on_or_after(entity, "ASC606", date(2023, 1, 31))
    assert open_period is not None
    assert open_period.period_key == "FY2023-P02"
    assert period_state(period_of(entity, date(2023, 1, 31)), "ASC606") == "closed"

    # D-79: open, closing and reopened periods receive amounts (S08-R-08; DG-KRN-TIME-04 amended).
    later = _fy2023({1: "closed", 2: "closing", 3: "closed", 4: "reopened"})
    closing = first_open_period_on_or_after(later, "ASC606", date(2023, 1, 15))
    assert closing is not None
    assert closing.period_key == "FY2023-P02"
    reopened = first_open_period_on_or_after(later, "ASC606", date(2023, 3, 1))
    assert reopened is not None
    assert reopened.period_key == "FY2023-P04"
    assert first_open_period_on_or_after(later, "ASC606", date(2023, 4, 30)) is reopened
    assert first_open_period_on_or_after(later, "ASC606", date(2023, 5, 1)) is None

    # A book without a state is a malformed bundle (CV-13 horizon needs every book's state).
    with pytest.raises(EngineError) as raised:
        period_state(entity.periods[0], "IFRS15")
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail == {
        "book_code": "IFRS15",
        "period_key": "FY2023-P01",
        "rule": "CV-13",
    }

    # Lookup does not depend on the order of the periods tuple.
    shuffled = _Entity(tuple(reversed(entity.periods)))
    assert period_of(shuffled, date(2023, 6, 30)).period_key == "FY2023-P06"
    with pytest.raises(TypeError):
        period_of(entity, datetime(2023, 1, 31))


def test_s08_r08_first_postable_period_includes_closing() -> None:
    assert frozenset({"open", "closing", "reopened"}) == POSTABLE_STATES

    def first(states: dict[int, str], d: date) -> str | None:
        period = first_open_period_on_or_after(_fy2023(states), "ASC606", d)
        return None if period is None else period.period_key

    assert first({1: "closed", 2: "closing", 3: "open"}, date(2023, 2, 1)) == "FY2023-P02"
    # P03 to P12 are future: the closing period is still the posting period, not None.
    assert first({1: "closed", 2: "closing"}, date(2023, 2, 1)) == "FY2023-P02"

    later = {1: "closed", 2: "closed", 3: "closing", 4: "reopened"}
    assert first(later, date(2023, 1, 15)) == "FY2023-P03"
    # Every period ending on or after the date is closed or future.
    assert first(later, date(2023, 5, 1)) is None
    assert first({n: "closed" for n in range(1, 13)}, date(2023, 1, 15)) is None

    # A period without a state for the book still raises (CV-13).
    with pytest.raises(EngineError) as raised:
        first_open_period_on_or_after(_fy2023(later), "IFRS15", date(2023, 1, 15))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["rule"] == "CV-13"


def test_month_ends_between() -> None:
    assert month_ends_between(date(2026, 1, 1), date(2026, 1, 31)) == 1
    assert month_ends_between(date(2026, 1, 31), date(2026, 1, 31)) == 0
    assert month_ends_between(date(2026, 1, 15), date(2026, 2, 27)) == 1
    assert month_ends_between(date(2026, 1, 1), date(2027, 12, 31)) == 24
    assert month_ends_between(date(2026, 1, 1), date(2028, 1, 1)) == 24
    # No month end e satisfies a < e ≤ b when b precedes a.
    assert month_ends_between(date(2026, 3, 1), date(2026, 1, 1)) == 0
    assert month_ends_between(date(2024, 1, 31), date(2024, 2, 29)) == 1


def test_day_counts_and_month_arithmetic() -> None:
    assert days_inclusive(date(2026, 2, 10), date(2027, 2, 9)) == 365
    assert days_inclusive(date(2026, 2, 10), date(2026, 2, 10)) == 1
    assert days_inclusive(date(2026, 2, 10), date(2026, 2, 9)) == 0
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)
    assert add_months(date(2026, 12, 31), 2) == date(2027, 2, 28)
    assert calendar_months(date(2026, 2, 10), date(2026, 5, 20)) == (
        MonthPeriod(date(2026, 2, 1), date(2026, 2, 28)),
        MonthPeriod(date(2026, 3, 1), date(2026, 3, 31)),
        MonthPeriod(date(2026, 4, 1), date(2026, 4, 30)),
        MonthPeriod(date(2026, 5, 1), date(2026, 5, 31)),
    )
    with pytest.raises(ValueError):
        calendar_months(date(2026, 5, 20), date(2026, 2, 10))
    with pytest.raises(TypeError):
        add_months(date(2026, 1, 1), True)

    # A gap between consecutive periods is a malformed calendar (CV-12).
    gapped = (
        MonthPeriod(date(2026, 1, 1), date(2026, 1, 31)),
        MonthPeriod(date(2026, 2, 2), date(2026, 2, 28)),
    )
    with pytest.raises(EngineError) as raised:
        covering_periods(gapped, date(2026, 1, 10), date(2026, 2, 10))
    assert raised.value.detail == {"date": "2026-02-01", "rule": "CV-12"}
    assert covering_periods(gapped, date(2026, 2, 3), date(2026, 2, 10)) == gapped[1:]
