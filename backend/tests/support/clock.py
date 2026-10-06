"""Frozen test clock (docs/dev-guide.md DG-TST-14, DG-KRN-TIME-06)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from erev_api.clock import FrozenClock

FROZEN_AT: Final[datetime] = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)


def frozen_clock(at: datetime = FROZEN_AT) -> FrozenClock:
    return FrozenClock(at)
