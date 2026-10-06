"""The reports' reader at a date (``erev_api.domain.reports.cuts``; item RPT-ASOF-FIGURES-1;
ENGINE_SPEC_B S15-R-01 and S15-R-08 rev 1.127; 04 API-C-10; supervisor ruling R-116 (c)). No
database.

``scheduled_after`` is the one rule the reports add to the reader of the contract reads: the
schedule lines of the periods after the cut state the scheduled part of an obligation's remainder
when it has one, they must add up to it, and an obligation without a scheduled part states none.
The versions of a run are loaded for the dates it states, and a read at another date is a mistake
of the caller, not a figure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.contracts.to_date import Measured, ObligationAt
from erev_api.domain.reports import cuts

JANUARY, FEBRUARY, MARCH, APRIL = (
    date(2026, 1, 31),
    date(2026, 2, 28),
    date(2026, 3, 31),
    date(2026, 4, 30),
)
# O1: 400.00 over four months, 100.00 a month
LINES: tuple[cuts.Line, ...] = tuple(
    (UUID(int=index), end, Decimal("100.00"))
    for index, end in enumerate((JANUARY, FEBRUARY, MARCH, APRIL), start=1)
)


def at(
    *, revenue: str, scheduled: str, awaiting: str = "0.00", measured: Measured | None
) -> ObligationAt:
    return ObligationAt(
        revenue=Decimal(revenue),
        billed=Decimal(0),
        progress_ratio=Decimal(0),
        delta=Decimal(0),
        billed_delta=Decimal(0),
        shift=Decimal(0),
        scheduled=Decimal(scheduled),
        awaiting=Decimal(awaiting),
        satisfaction_status="PARTIALLY_SATISFIED",
        measured=measured,
        billed_measured=None,
    )


def later(found: ObligationAt, day: date) -> list[date]:
    lines = cuts.scheduled_after(LINES, found, day, contract="C-1", obligation="O1")
    return [end for _, end, _ in lines]


def test_the_lines_after_the_period_read_state_the_scheduled_part() -> None:
    february = at(revenue="200.00", scheduled="200.00", measured=Measured("P02", FEBRUARY))
    assert later(february, FEBRUARY) == [MARCH, APRIL]
    # a date inside February is read at the end of February: the month's line is no later line
    assert later(february, date(2026, 2, 10)) == [MARCH, APRIL]


def test_a_date_beyond_the_horizon_is_read_at_the_horizon() -> None:
    """A version measured to February and asked for June answers at February (04 API-C-10): the
    lines of March and April lie before June and are still its scheduled part."""
    february = at(revenue="200.00", scheduled="200.00", measured=Measured("P02", FEBRUARY))
    assert later(february, date(2026, 6, 30)) == [MARCH, APRIL]


def test_before_the_first_period_every_line_is_later() -> None:
    nothing_yet = at(revenue="0.00", scheduled="400.00", measured=None)
    assert later(nothing_yet, date(2025, 12, 31)) == [JANUARY, FEBRUARY, MARCH, APRIL]


def test_an_obligation_without_a_scheduled_part_states_no_scheduled_line() -> None:
    """Its later lines — a transfer still to come, amounts a computation recognises past the
    version's date — are inside its awaiting-trigger amount."""
    waiting = at(
        revenue="200.00", scheduled="0.00", awaiting="200.00", measured=Measured("P02", FEBRUARY)
    )
    assert later(waiting, FEBRUARY) == []


def test_lines_that_do_not_add_up_to_the_scheduled_part_are_refused_by_name() -> None:
    short = at(revenue="200.00", scheduled="150.00", measured=Measured("P02", FEBRUARY))
    with pytest.raises(cuts.ScheduleUnreadable) as refused:
        later(short, FEBRUARY)
    (error,) = refused.value.errors
    assert (error.field, error.rule_id, error.message) == (
        "obligations[O1].scheduled_amount",
        "S15-R-01",
        "Contract C-1, obligation O1: at 2026-02-28 the scheduled amount read from the "
        "calculation trace of the contract version is 150.00, and the version's revenue schedule "
        "places 200.00 in later periods. Nothing is reported in place of either.",
    )


def test_a_read_at_a_date_the_versions_were_not_loaded_for_is_a_mistake() -> None:
    """``Versions`` keeps of each trace the nodes its dates reach and no other, so a read at a
    date outside them is refused before any node is read — never answered from too few."""
    found = cuts.Versions({}, {}, {}, {}, frozenset({FEBRUARY}))
    with pytest.raises(ValueError, match="were loaded for 2026-02-28, not for 2026-03-31"):
        found.at(UUID(int=7), MARCH)
    with pytest.raises(ValueError, match="were loaded for 2026-02-28, not for 2026-03-31"):
        found.balance({"contract_version_id": UUID(int=7)}, MARCH)
