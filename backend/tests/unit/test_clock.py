"""KRN-TIME clock contract (docs/dev-guide.md §5.10; BUILD_SPEC FND-2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from erev_api.clock import FrozenClock, SystemClock, entity_today, local_noon_utc, to_entity_date


def test_krn_time_entity_dates() -> None:
    at = datetime(2026, 9, 1, 6, 30, tzinfo=UTC)
    assert to_entity_date(at, "America/Los_Angeles") == date(2026, 8, 31)
    assert to_entity_date(at, "Pacific/Auckland") == date(2026, 9, 1)
    noon = local_noon_utc(date(2026, 9, 12), "Asia/Tokyo")
    assert noon == datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
    assert noon.utcoffset() == timedelta(0)
    clock = FrozenClock(datetime(2026, 9, 12, 12, 0, tzinfo=UTC))
    clock.advance(timedelta(hours=1))
    assert clock.now() == datetime(2026, 9, 12, 13, 0, tzinfo=UTC)
    assert clock.now().isoformat() == "2026-09-12T13:00:00+00:00"


def test_krn_time_frozen_clock_set_and_rejects_naive() -> None:
    clock = FrozenClock(datetime(2026, 9, 12, 14, 0, tzinfo=UTC))
    clock.set(datetime.fromisoformat("2026-09-13T09:00:00+09:00"))
    assert clock.now() == datetime(2026, 9, 13, 0, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC
    assert entity_today(clock, "America/Los_Angeles") == date(2026, 9, 12)
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 9, 12, 12, 0))
    with pytest.raises(ValueError):
        to_entity_date(datetime(2026, 9, 12, 12, 0), "UTC")


def test_krn_time_system_clock_is_aware_utc() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


def test_dg_tst_14_clock_fixture(clock: FrozenClock) -> None:
    assert clock.now() == datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
