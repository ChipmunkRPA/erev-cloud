"""Prove identical complete fiscal ranges before admitting cross-calendar totals."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID


@dataclass(frozen=True)
class Interval:
    key: str
    start: date
    end: date


def ranges_match(
    calendars: Mapping[UUID, Sequence[Interval]], start_key: str, end_key: str
) -> bool:
    signatures = []
    for periods in calendars.values():
        ordered = sorted(periods, key=lambda period: (period.start, period.end, period.key))
        starts = [i for i, period in enumerate(ordered) if period.key == start_key]
        ends = [i for i, period in enumerate(ordered) if period.key == end_key]
        if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
            return False
        first, last = starts[0], ends[0]
        selected = tuple(ordered[first : last + 1])
        before = ordered[first - 1] if first else None
        chain = selected if before is None else (before, *selected)
        if any(p.start > p.end for p in chain) or any(
            left.end + timedelta(days=1) != right.start
            for left, right in zip(chain[:-1], chain[1:], strict=True)
        ):
            return False
        signatures.append((before, selected))
    return bool(signatures) and all(value == signatures[0] for value in signatures[1:])
