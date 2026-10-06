"""Period states (04 T-REF-06, T-REF-07, E-04, DB-07; API-S-Period §16.8; API-R-18; SCREENS_B
OQ-B-19; BUILD_SPEC RFD-2).

A kept book has one ``period_state`` per period of the entity's calendar from the book's first
period on. Each state is created ``future`` with a transition from NULL (T-REF-07), and
``POST /periods/{id}/open`` moves it to ``open`` — in order: never while the previous period of
the entity and book is still ``future`` (PRD SM-07). The blocker counts and the close run of
API-S-Period come from CLO sources, so until CLO registers them the counts are 0 and the close run
and current lock are null. This module is pure: no database and no clock.
"""

from __future__ import annotations

from typing import Final

from erev_api.enums import PeriodState

RULE_TRANSITION: Final = "DB-07"
STATE_OBJECT: Final = "period_state"
TRANSITION_OBJECT: Final = "period_state_transition"
OPEN_ACTION: Final = "period.open"
CREATE_TRANSITIONS_ACTION: Final = "period_state_transition.create"
CLOSE_PERMISSION: Final = "period.close"
# PRD ACT-27, SM-07: the lock decisions and the request of the permanent lock (Controller).
LOCK_PERMISSION: Final = "period.lock"
REOPEN_REQUEST_PERMISSION: Final = "period.reopen_request"  # CLO-7; PRD §5.6 (RR, CO)
SETUP_PERMISSION: Final = "settings.manage"
# 04 T-REF-07 ``to_state``: the allowed pairs (DB-07).
ALLOWED_TRANSITIONS: Final[frozenset[tuple[PeriodState | None, PeriodState]]] = frozenset(
    {
        (None, PeriodState.FUTURE),
        (PeriodState.FUTURE, PeriodState.OPEN),
        (PeriodState.OPEN, PeriodState.CLOSING),
        (PeriodState.CLOSING, PeriodState.OPEN),
        # rev 1.170: the end of a soft close of a period that has been locked before
        (PeriodState.CLOSING, PeriodState.REOPENED),
        (PeriodState.CLOSING, PeriodState.CLOSED),
        (PeriodState.CLOSED, PeriodState.REOPENED),
        (PeriodState.REOPENED, PeriodState.CLOSING),
        (PeriodState.CLOSED, PeriodState.PERMANENTLY_LOCKED),
    }
)
# 04 §16.8 API-S-Period ``blockers``, in catalogue order (REQ-CLS-008).
BLOCKER_COUNTS: Final = (
    "exceptions_open",
    "holds_open",
    "unmapped_products",
    "judgements_unreviewed",
    "approvals_pending",
    "interface_failures",
    "jobs_failed",
    "groups_dirty",
    "batches_unexported",
    "batches_unacknowledged",
    "reconciliations_unsigned",
    "manual_adjustments_pending",
)
NOT_FUTURE: Final = "Only a future period opens. {period_key} is {state}."
# PRD SM-07 guard on ``future → open`` ("Previous period not ``future``"; supervisor ruling
# R-58 (d), item PERIOD-OPEN-GUARD-1): the periods of an entity and book open in order.
PREVIOUS_FUTURE: Final = (
    "The previous period of {entity} in book {book} is future, so {period_key} does not open yet."
)
BOOK_NOT_KEPT: Final = (
    "{entity} does not keep the {book} book. Enable the book for the entity first."
)


def open_permissions(*, setup_completed: bool) -> frozenset[str]:
    """API-R-18 ``open``: ``period.close``, or ``settings.manage`` while setup is incomplete
    (SCREENS_B OQ-B-19; PRD ACT-44). The caller answers ``setup_completed`` from
    ``setup.rule_ended`` — the stamp, or the conditions of PRD BR-PLT-02 where the stamp is due
    (04 T-PLT-01; item APR-SETUP-RULE-2)."""
    if setup_completed:
        return frozenset({CLOSE_PERMISSION})
    return frozenset({CLOSE_PERMISSION, SETUP_PERMISSION})


def blockers() -> dict[str, int]:
    """Every API-S-Period blocker count at 0, until CLO registers its sources."""
    return dict.fromkeys(BLOCKER_COUNTS, 0)
