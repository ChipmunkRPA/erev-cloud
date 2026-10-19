"""Migration cutover and open-period defaults must not inherit ordinary report defaults."""

from datetime import date
from uuid import UUID

import pytest
from erev_api.domain.reports.parallel_periods import select_periods
from erev_api.domain.reports.tie_outs import Calendar, PeriodRef
from erev_api.problems import Problem

CALENDAR = Calendar(
    tuple(
        PeriodRef(
            UUID(int=month),
            f"P{month}",
            f"Period {month}",
            2023,
            month,
            1,
            date(2023, month, 1),
            date(2023, month, 28),
        )
        for month in (1, 2, 3)
    )
)


def test_default_range_starts_after_cutover_and_ends_at_latest_open() -> None:
    result = select_periods(
        CALENDAR,
        entity_code="US",
        currency="USD",
        cutover=date(2023, 1, 31),
        open_period_ids=frozenset({UUID(int=2)}),
        first_key=None,
        last_key=None,
    )
    assert [p.key for p in result] == ["P2"]
    assert result[0].currency == "USD"


def test_explicit_closed_range_and_no_open_default() -> None:
    args = dict(
        entity_code="US", currency="USD", cutover=date(2023, 1, 31), open_period_ids=frozenset()
    )
    assert select_periods(CALENDAR, **args, first_key=None, last_key=None) == ()
    result = select_periods(CALENDAR, **args, first_key="P2", last_key="P3")
    assert [p.key for p in result] == ["P2", "P3"]
    with pytest.raises(Problem, match="after the migration cutover"):
        select_periods(CALENDAR, **args, first_key="P1", last_key="P2")
    with pytest.raises(Problem, match="start period is after"):
        select_periods(CALENDAR, **args, first_key="P3", last_key="P2")
