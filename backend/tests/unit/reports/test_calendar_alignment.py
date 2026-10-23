from datetime import date
from uuid import UUID

from erev_api.domain.reports.calendar_alignment import Interval, ranges_match


def test_equal_range_edges_are_insufficient_when_interior_or_opening_differs():
    periods = [
        Interval("P01", date(2026, 1, 1), date(2026, 1, 31)),
        Interval("P02", date(2026, 2, 1), date(2026, 2, 28)),
        Interval("P03", date(2026, 3, 1), date(2026, 3, 31)),
    ]

    def check(other):
        return ranges_match({UUID(int=1): periods, UUID(int=2): other}, "P02", "P03")

    assert check(periods)
    assert not check(periods[1:])  # Same range but no original opening period.
    assert not check(
        [
            periods[0],
            Interval("P02", date(2026, 2, 1), date(2026, 3, 1)),
            Interval("P03", date(2026, 3, 2), date(2026, 3, 31)),
        ]
    )
    assert not check([periods[0], periods[2]])  # Missing endpoint.
    assert not ranges_match({UUID(int=1): periods}, "P03", "P02")
    assert not ranges_match({}, "P02", "P03")
