"""The groups a changed rate reaches, without a database (item FX-REPUBLISH-DIRTY-1; supervisor
ruling R-116 (b) and the rulings of 2026-10-02 on the lane's pre-build line; 04 T-REF-11 "The
groups a changed rate reaches" rev 1.297; 05 RCP-17 rev 1.206): the two pure rules of
``close.rate_reach`` — the reach of a changed key in one entity's calendar, and whether a group is
at work in a reach. The statements say the same in SQL; the database witnesses are
``tests/domain/contracts/test_fx_republish_mark.py`` (the mark, its trigger, the reach) and
``tests/domain/close/test_rate_reach_db.py`` (the close runs around a corrected rate).

The calendar is the twelve months of 2026. A key of an ``average`` or ``closing`` rate is dated
the last day of its period (T-REF-11); a ``spot`` rate is dated the day it is of.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

import pytest
from erev_api.domain.close.rate_reach import at_work, reach_of

MONTHS = tuple(
    (date(2026, month, 1), date(2026, month, monthrange(2026, month)[1])) for month in range(1, 13)
)
JULY = (date(2026, 7, 1), date(2026, 7, 31))
SEPTEMBER_END = date(2026, 9, 30)


# --- the reach of a changed key -------------------------------------------------------------------


@pytest.mark.parametrize("rate_type", ["average", "closing"])
def test_an_average_or_closing_key_reaches_its_own_period(rate_type: str) -> None:
    reach = reach_of(
        rate_type, date(2026, 7, 31), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=None
    )
    assert reach == JULY


@pytest.mark.parametrize("rate_type", ["average", "closing"])
def test_a_period_rate_dated_inside_a_period_is_read_by_nobody(rate_type: str) -> None:
    """Stage 12 reads the average and the closing of a period by its last day: a row of one of
    those types dated another day is no period's rate."""
    reach = reach_of(
        rate_type, date(2026, 7, 15), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=None
    )
    assert reach is None


def test_a_period_rate_ignores_the_next_spot_date() -> None:
    reach = reach_of(
        "closing",
        date(2026, 7, 31),
        periods=MONTHS,
        horizon=SEPTEMBER_END,
        next_spot=date(2026, 8, 20),
    )
    assert reach == JULY


def test_a_spot_key_reaches_to_the_day_before_the_next_spot_date() -> None:
    """The spot rate of a flow is the latest on or before its date: a rate dated 1 July answers
    for every flow until the day before the pair's next spot date — 19 August, in August."""
    reach = reach_of(
        "spot",
        date(2026, 7, 1),
        periods=MONTHS,
        horizon=SEPTEMBER_END,
        next_spot=date(2026, 8, 20),
    )
    assert reach == (date(2026, 7, 1), date(2026, 8, 31))


def test_a_spot_key_whose_successor_opens_a_period_ends_in_the_period_before() -> None:
    reach = reach_of(
        "spot", date(2026, 7, 10), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=date(2026, 9, 1)
    )
    assert reach == (date(2026, 7, 1), date(2026, 8, 31))


def test_a_spot_key_followed_in_its_own_period_reaches_that_period() -> None:
    reach = reach_of(
        "spot", date(2026, 7, 1), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=date(2026, 7, 2)
    )
    assert reach == JULY


def test_a_spot_key_without_a_later_one_has_no_end() -> None:
    reach = reach_of(
        "spot", date(2026, 8, 20), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=None
    )
    assert reach == (date(2026, 8, 1), None)


@pytest.mark.parametrize("rate_type", ["average", "closing", "spot"])
def test_a_key_after_the_last_postable_period_has_no_reach(rate_type: str) -> None:
    """CV-13: the replay ends on the last day of the entity's last postable period, so a later
    key is read by nobody — SCH-06 marks when its period opens. A key ON that day is read."""
    beyond = reach_of(
        rate_type, date(2026, 10, 31), periods=MONTHS, horizon=SEPTEMBER_END, next_spot=None
    )
    assert beyond is None
    on_the_day = reach_of(
        rate_type, SEPTEMBER_END, periods=MONTHS, horizon=SEPTEMBER_END, next_spot=None
    )
    assert on_the_day is not None and on_the_day[0] == date(2026, 9, 1)


def test_an_entity_without_a_postable_period_bounds_no_key() -> None:
    """CV-13's fallback: without a postable period there is no last day to end the replay."""
    reach = reach_of("closing", date(2026, 12, 31), periods=MONTHS, horizon=None, next_spot=None)
    assert reach == (date(2026, 12, 1), date(2026, 12, 31))


def test_a_key_outside_the_calendar_has_no_reach() -> None:
    reach = reach_of("spot", date(2027, 1, 5), periods=MONTHS, horizon=None, next_spot=None)
    assert reach is None


# --- a group at work in a reach -------------------------------------------------------------------

FIRST, LAST = JULY


def _at_work(
    *,
    inception: date = date(2026, 1, 1),
    events: tuple[date, ...] = (),
    scheduled: tuple[date, ...] = (),
    sealed: tuple[date, ...] = (),
    position: bool = False,
    last: date | None = LAST,
) -> bool:
    return at_work(
        FIRST,
        last,
        inception=inception,
        events=events,
        scheduled=scheduled,
        sealed=sealed,
        position=position,
    )


def test_a_group_at_rest_before_the_reach_is_left_out() -> None:
    """Finished and settled in June: no event, schedule line or sealed line from July on, and no
    position left. No sealed amount of it is made of July's rate."""
    assert not _at_work(
        events=(date(2026, 3, 1), date(2026, 6, 30)),
        scheduled=(date(2026, 6, 30),),
        sealed=(date(2026, 6, 30),),
    )


def test_a_position_alone_keeps_a_group() -> None:
    """Nothing dated in the reach, but a balance still open: a closing rate remeasures it."""
    assert _at_work(events=(date(2026, 3, 1),), position=True)


@pytest.mark.parametrize("kind", ["events", "scheduled", "sealed"])
def test_an_event_a_schedule_line_or_a_sealed_line_from_the_first_day_on_keeps_a_group(
    kind: str,
) -> None:
    assert _at_work(**{kind: (FIRST,)})
    assert _at_work(**{kind: (date(2026, 11, 30),)})  # a later period's line carries the rate too
    assert not _at_work(**{kind: (date(2026, 6, 30),)})  # the day before the reach: at rest


def test_a_group_that_begins_after_the_reach_is_left_out() -> None:
    """Its replay starts on a later day: nothing of it is dated in the reach."""
    assert not _at_work(inception=date(2026, 8, 1), events=(date(2026, 8, 1),), position=True)


def test_a_group_whose_first_event_lies_in_the_reach_has_begun() -> None:
    """A contract with a later inception date in its header and an event dated inside the reach
    (an opening balance, a backdated delivery) has begun by the reach's last day."""
    assert _at_work(inception=date(2026, 8, 1), events=(date(2026, 7, 20),))


def test_a_reach_without_an_end_leaves_out_no_later_group() -> None:
    assert _at_work(inception=date(2026, 11, 1), events=(date(2026, 11, 1),), last=None)
    assert not _at_work(inception=date(2026, 11, 1), last=None)  # begun, and nothing at work
