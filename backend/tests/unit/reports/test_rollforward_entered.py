"""The period a billing document enters the contract balance roll-forward in, where an end of the
range is a lock's (``contract_balance_rollforward.entered``; ENGINE_SPEC_B S15-R-20 rev 1.168;
item RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's ruling of 2026-10-02). No database.

A lock's balances do not hold a document recorded after its cutoff, so the billing that posts no
line cannot stay in the period it is dated in: measured on PRD J-04 — K-07's invoice of
31 August, recorded after August's lock — August showed the billing against the lock's closing,
89,285.71 under "Other". A document is a movement of the first period whose end holds it, as a
line posted with an earlier origin is. The database witness is
``tests/domain/reports/test_rollforward_locked_ends_db.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward


def _period(number: int, start: date, end: date) -> tie_outs.PeriodRef:
    return tie_outs.PeriodRef(
        id=UUID(int=number),
        key=f"FY2026-P{number:02d}",
        name=f"P{number:02d}",
        fiscal_year=2026,
        period_no=number,
        quarter_no=None,
        start=start,
        end=end,
    )


JULY = _period(7, date(2026, 7, 1), date(2026, 7, 31))
AUGUST = _period(8, date(2026, 8, 1), date(2026, 8, 31))
SEPTEMBER = _period(9, date(2026, 9, 1), date(2026, 9, 30))
JULY_LOCKED = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
AUGUST_LOCKED = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _document(number: int, dated: date, recorded: datetime | None) -> rollforward.Document:
    return rollforward.Document(
        effective_date=dated,
        record_seq=number,
        event_id=UUID(int=number),
        amount=Decimal("100.00"),
        recorded_at=recorded,
    )


ON_TIME = _document(1, date(2026, 8, 10), AUGUST_LOCKED - timedelta(days=20))
AT_THE_CUTOFF = _document(2, date(2026, 8, 31), AUGUST_LOCKED)
LATE = _document(3, date(2026, 8, 31), AUGUST_LOCKED + timedelta(minutes=5))
OF_SEPTEMBER = _document(4, date(2026, 9, 12), AUGUST_LOCKED + timedelta(days=8))
OF_JULY = _document(5, date(2026, 7, 20), JULY_LOCKED - timedelta(days=3))
LATE_FOR_JULY = _document(6, date(2026, 7, 20), JULY_LOCKED + timedelta(days=1))
LATE_FOR_BOTH = _document(7, date(2026, 7, 20), AUGUST_LOCKED + timedelta(days=1))
NOT_STATED = _document(8, date(2026, 8, 15), None)
ALL = (
    ON_TIME,
    AT_THE_CUTOFF,
    LATE,
    OF_SEPTEMBER,
    OF_JULY,
    LATE_FOR_JULY,
    LATE_FOR_BOTH,
    NOT_STATED,
)


def test_without_a_lock_a_document_enters_in_the_period_it_is_dated_in() -> None:
    ends = [(JULY, None), (AUGUST, None), (SEPTEMBER, None)]
    assert rollforward.entered(ALL, ends) == [
        [ON_TIME, AT_THE_CUTOFF, LATE, NOT_STATED],
        [OF_SEPTEMBER],
    ]
    # the range's first period with nothing before it: July's documents are July's
    assert rollforward.entered(ALL, [(None, None), (JULY, None)]) == [
        [OF_JULY, LATE_FOR_JULY, LATE_FOR_BOTH]
    ]


def test_a_document_recorded_after_the_lock_of_its_period_enters_where_an_end_holds_it() -> None:
    """PRD J-04: August locked, the invoice dated 31 August recorded afterwards. August shows no
    billing of it; September, whose end is not a lock's, shows it. A document recorded at the
    lock's cutoff or before it is the lock's."""
    locked = [(JULY, JULY_LOCKED), (AUGUST, AUGUST_LOCKED), (SEPTEMBER, None)]
    august, september = rollforward.entered(ALL, locked)
    assert august == [ON_TIME, AT_THE_CUTOFF, LATE_FOR_JULY, NOT_STATED]
    assert september == [LATE, OF_SEPTEMBER, LATE_FOR_BOTH]
    # August alone: what its lock does not hold enters in no period of the range
    assert rollforward.entered(ALL, locked[:2]) == [august]
    # September alone opens at August's lock: the late documents are September's
    assert rollforward.entered(ALL, locked[1:]) == [september]


def test_a_document_enters_once_and_never_in_a_period_before_its_date() -> None:
    locked = [(JULY, JULY_LOCKED), (AUGUST, AUGUST_LOCKED), (SEPTEMBER, None)]
    found = rollforward.entered(ALL, locked)
    listed = [document for period in found for document in period]
    assert len(listed) == len(set(d.event_id for d in listed))
    assert OF_JULY not in listed  # in the opening: July's lock holds it
    for (period, _), documents in zip(locked[1:], found, strict=True):
        assert period is not None
        assert all(document.effective_date <= period.end for document in documents)


def test_the_lock_that_stands_holds_what_was_recorded_before_it() -> None:
    """A document recorded after a first lock of August and before its reopening and second
    lock: the standing lock — the second — was frozen after the document, so it holds it, and
    the document is August's again."""
    second = AUGUST_LOCKED + timedelta(days=3)
    assert LATE.recorded_at is not None and LATE.recorded_at < second
    assert rollforward.entered(
        [LATE], [(JULY, JULY_LOCKED), (AUGUST, second), (SEPTEMBER, None)]
    ) == [
        [LATE],
        [],
    ]
