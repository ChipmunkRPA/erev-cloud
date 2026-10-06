"""Stage 08 posting-period assignment (ENGINE_SPEC §8.1, §8.2, §8.4 S08-R-08, §8.6 S08-INV-03).

``assign_posting_period`` fixes where an amount dated ``effective_date`` posts in one book (RCP-04;
POL-180 ``FIRST_OPEN_PERIOD_WITH_ORIGIN``; D-19):

- the period of the date in the owning entity's calendar (CV-12) when its state is ``open``,
  ``closing`` or ``reopened``;
- when that period is ``closed`` or ``permanently_locked``, the first later period in one of those
  states, with ``origin_period_key`` = the effective period and ``reason_code = LATE_EVENT``, or
  None when the bundle holds no later postable period (bundle assembly supplies the horizon;
  RCP-15);
- nothing when the period is ``future``: the group is re-marked dirty when the period opens
  (SCH-06).

The result never names a ``closed``, ``permanently_locked`` or ``future`` period (S08-INV-03;
PROP:P11). Stage 14 calls it for every closed-period carry (ENGINE_SPEC_B S14-R-06), and
``late.py`` for the late-event findings and register. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.stages.state import BookContext

__all__ = ["CLOSED_STATES", "FUTURE", "LATE_EVENT", "Assignment", "assign_posting_period"]

LATE_EVENT: Final = "LATE_EVENT"  # reason code and finding code (S08-R-08, S08-R-10)
CLOSED_STATES: Final = frozenset({"closed", "permanently_locked"})  # E-04
FUTURE: Final = "future"  # E-04


@dataclass(frozen=True, slots=True)
class Assignment:
    """Where an amount posts (ENGINE_SPEC §8.1)."""

    posting_period_key: str | None  # None: nothing posts (future period, or no later open period)
    origin_period_key: str | None  # set only when the effective period is closed or locked
    reason_code: str | None  # "LATE_EVENT" with an origin


def assign_posting_period(ctx: BookContext, entity: str, effective_date: date) -> Assignment:
    """The posting period of an amount of ``entity`` dated ``effective_date`` (S08-R-08)."""
    calendar = ctx.entities.get(entity)
    if calendar is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the owning entity has no calendar in the book context",
            subject_key=entity,
            detail={"rule": "CV-12", "entity": entity},
        )
    book_code = str(ctx.book_code)
    period = dates.period_of(calendar, effective_date)
    state = dates.period_state(period, book_code)
    if state in dates.POSTABLE_STATES:
        return Assignment(period.period_key, None, None)
    if state == FUTURE:
        return Assignment(None, None, None)
    if state not in CLOSED_STATES:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the period carries an unknown E-04 state",
            subject_key=entity,
            detail={"rule": "CV-45", "period_key": period.period_key, "state": state},
        )
    later = dates.first_open_period_on_or_after(
        calendar, book_code, period.end_date + timedelta(days=1)
    )
    posting = None if later is None else later.period_key
    return Assignment(posting, period.period_key, LATE_EVENT)
