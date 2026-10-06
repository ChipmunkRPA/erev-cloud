"""Time zones and period assignment (05 §9 TZ-03, TZ-04, TZ-11; 04 API-C-07; dev-guide
DG-KRN-TIME-02, DG-KRN-TIME-04; 03 REQ-CLS-005; BUILD_SPEC RFD-2).

``to_entity_date`` turns an instant into the entity's business date, and ``periods.posting_period``
maps that date to the posting entity's calendar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from functools import cache
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from erev_api import periods as kernel_periods
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock, to_entity_date
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.enums import BookCode
from erev_api.main import create_app
from erev_api.problems import Problem
from hypothesis import given
from hypothesis import strategies as st
from support.db import TestDatabase
from support.principals import member
from support.reference import PERIODS, calendar, entity, holding, periods, post

# 05 TZ-11: 2026-03-31T23:30:00-04:00 = 2026-04-01T03:30:00Z.
INSTANT = datetime(2026, 3, 31, 23, 30, tzinfo=timezone(timedelta(hours=-4)))
ZONES = ("America/New_York", "Europe/London", "Asia/Tokyo", "Australia/Lord_Howe")
FIRST_YEAR, LAST_YEAR = 2020, 2030
WINDOW_SECONDS = 2 * 60 * 60


def test_tz_11_entity_local_date_assignment(
    committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock, keyring: KeyRing
) -> None:
    assert INSTANT.astimezone(UTC) == datetime(2026, 4, 1, 3, 30, tzinfo=UTC)
    assert to_entity_date(INSTANT, "America/New_York") == date(2026, 3, 31)
    assert to_entity_date(INSTANT, "Europe/London") == date(2026, 4, 1)

    app = create_app(app_settings, clock=clock)
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    # Periods open in order (PRD SM-07 guard "Previous period not future"; supervisor ruling
    # R-58 (d)), so each entity keeps its book from the first period this test opens: March for
    # AVM-US and AVM-UK, April for AVM-DE. Until that ruling the test opened March and April above
    # the future January and February, and AVM-DE's April above its future March.
    us = entity(app, maya, code="AVM-US", calendar_id=calendar_id, first_period_key="FY2026-P03")
    uk = entity(
        app,
        maya,
        code="AVM-UK",
        calendar_id=calendar_id,
        functional_currency="GBP",
        time_zone="Europe/London",
        first_period_key="FY2026-P03",
    )
    de = entity(
        app,
        maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
        first_period_key="FY2026-P04",
    )
    opened = {"AVM-US": ("FY2026-P03", "FY2026-P04"), "AVM-UK": ("FY2026-P03", "FY2026-P04")}
    opened["AVM-DE"] = ("FY2026-P04",)
    for code, keys in opened.items():
        for item in periods(app, maya, entity=code):
            if item["period"]["period_key"] in keys:
                response = post(app, f"{PERIODS}/{item['id']}/open", maya, {}, if_match='"r1"')
                assert response.status_code == 200, response.text

    context = DbContext(tenant_id=maya_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:

        def posting(found: dict[str, str], effective_date: date) -> tuple[str, str | None]:
            posting_period, origin = kernel_periods.posting_period(
                session,
                entity_id=UUID(found["id"]),
                book_code=BookCode.ASC606,
                effective_date=effective_date,
            )
            return posting_period.period_key, None if origin is None else origin.period_key

        # TZ-03 then TZ-04: one instant, two business dates, two posting periods.
        assert posting(us, to_entity_date(INSTANT, us["time_zone"])) == ("FY2026-P03", None)
        assert posting(uk, to_entity_date(INSTANT, uk["time_zone"])) == ("FY2026-P04", None)
        # DG-KRN-TIME-04: March of AVM-DE is not postable — the book is kept from April, so March
        # has no state — and the amount posts in the next open period.
        assert posting(de, date(2026, 3, 31)) == ("FY2026-P04", "FY2026-P03")
        with pytest.raises(Problem) as closed:
            posting(de, date(2026, 12, 15))
        assert closed.value.slug == "period-closed"
        with pytest.raises(Problem) as outside:
            posting(us, date(2027, 1, 1))
        assert (outside.value.slug, outside.value.errors[0].field) == (
            "validation-failed",
            "effective_date",
        )
        march = kernel_periods.period_by_key(
            session, calendar_id=UUID(calendar_id), period_key="FY2026-P03"
        )
        assert (
            kernel_periods.period_containing(
                session, calendar_id=UUID(calendar_id), d=date(2026, 3, 31)
            )
            == march
        )
        assert (march.start_date, march.end_date) == (date(2026, 3, 1), date(2026, 3, 31))
        with pytest.raises(LookupError):
            kernel_periods.period_state(
                session, entity_id=UUID(de["id"]), book_code=BookCode.ASC606, period_id=march.id
            )


@cache
def transitions(tz_name: str) -> tuple[datetime, ...]:
    """The instants from 2020 to 2030 at which the zone's UTC offset changes, to the second."""
    zone = ZoneInfo(tz_name)
    found: list[datetime] = []
    day = datetime(FIRST_YEAR, 1, 1, tzinfo=UTC)
    end = datetime(LAST_YEAR + 1, 1, 1, tzinfo=UTC)
    while day < end:
        after = day + timedelta(days=1)
        if day.astimezone(zone).utcoffset() != after.astimezone(zone).utcoffset():
            low, high = day, after
            while high - low > timedelta(seconds=1):
                middle = low + (high - low) / 2
                if middle.astimezone(zone).utcoffset() == low.astimezone(zone).utcoffset():
                    low = middle
                else:
                    high = middle
            found.append(high)
        day = after
    return tuple(found)


def local_midnight(tz_name: str, day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=ZoneInfo(tz_name)).astimezone(UTC)


@st.composite
def instants_near_midnight_or_transition(draw: st.DrawFn) -> tuple[str, datetime]:
    """An instant within ±2 hours of a local midnight or of a DST transition of one zone."""
    tz_name = draw(st.sampled_from(ZONES))
    anchors = transitions(tz_name)
    if anchors and draw(st.booleans()):
        anchor = draw(st.sampled_from(anchors))
    else:
        day = draw(st.dates(min_value=date(FIRST_YEAR, 1, 1), max_value=date(LAST_YEAR, 12, 31)))
        anchor = local_midnight(tz_name, day)
    offset = draw(st.integers(min_value=-WINDOW_SECONDS, max_value=WINDOW_SECONDS))
    return tz_name, anchor + timedelta(seconds=offset)


def test_tz_11_transition_anchors() -> None:
    # Three zones change their offset twice a year; Tokyo keeps one offset; Lord Howe moves 30 min.
    assert {zone: len(transitions(zone)) for zone in ZONES} == {
        "America/New_York": 22,
        "Europe/London": 22,
        "Asia/Tokyo": 0,
        "Australia/Lord_Howe": 22,
    }
    first = transitions("Australia/Lord_Howe")[0]
    zone = ZoneInfo("Australia/Lord_Howe")
    before = (first - timedelta(seconds=1)).astimezone(zone).utcoffset()
    after = first.astimezone(zone).utcoffset()
    assert before is not None and after is not None
    assert abs(after - before) == timedelta(minutes=30)


@given(instants_near_midnight_or_transition())
def test_tz_11_instants_near_midnight_property(case: tuple[str, datetime]) -> None:
    tz_name, at = case
    expected = at.astimezone(ZoneInfo(tz_name)).date()
    assert to_entity_date(at, tz_name) == expected
    # The business date depends on the instant only, not on the offset it is written with.
    assert to_entity_date(at.astimezone(timezone(timedelta(hours=-11))), tz_name) == expected
