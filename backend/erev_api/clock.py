"""Clock and entity-date helpers KRN-TIME (docs/dev-guide.md §5.10).

The only module, besides ``logging.py``, allowed to read the system clock (DG-KRN-TIME-05).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from time import monotonic as _monotonic_seconds
from typing import Protocol
from zoneinfo import ZoneInfo

from fastapi import Request


class Clock(Protocol):
    def now(self) -> datetime: ...


def _as_utc(at: datetime) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("clock instants must be timezone-aware")
    return at.astimezone(UTC)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic clock for tests and runners; moves only when told to (DG-KRN-TIME-06)."""

    def __init__(self, at: datetime) -> None:
        self._at = _as_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = _as_utc(at)

    def advance(self, delta: timedelta) -> None:
        self._at = self._at + delta


def get_clock(request: Request) -> Clock:
    """The application clock ``app.state.clock`` set by ``create_app``; tests pass their own."""
    clock: Clock = request.app.state.clock
    return clock


def monotonic() -> float:
    """Seconds from a monotonic source, for measuring durations only; never a timestamp."""
    return _monotonic_seconds()


def to_entity_date(at: datetime, tz_name: str) -> date:
    """The calendar date of ``at`` in the legal entity's IANA time zone (DG-KRN-TIME-02)."""
    return _as_utc(at).astimezone(ZoneInfo(tz_name)).date()


def entity_today(clock: Clock, tz_name: str) -> date:
    return to_entity_date(clock.now(), tz_name)


def local_noon_utc(d: date, tz_name: str) -> datetime:
    """Noon of ``d`` in the entity's time zone, expressed in UTC."""
    return datetime.combine(d, time(12), tzinfo=ZoneInfo(tz_name)).astimezone(UTC)
