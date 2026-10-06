"""Period lookup and posting assignment KRN-TIME (dev-guide §5.10 DG-KRN-TIME-04; 04 T-REF-05,
T-REF-06, DB-07; 05 RCP-04, TZ-04; BUILD_SPEC RFD-2).

The helpers read the real ``period`` and ``period_state`` tables in the caller's session, so
row-level security applies: an entity outside the principal's scope has no visible calendar or
state. ``posting_period`` implements JET R2 and ALG-09 steps 2 and 3 as amended by D-79: the period
containing the business date when its state is postable, otherwise the earliest later postable
period with the containing period as origin, otherwise 409 ``period-closed``. For the ``LEGACY``
book "postable" means postable in the LEGACY book and in the primary book it follows
(``followed_book``; DG-KRN-TIME-04 rev 1.197).

``under_reopen`` is the one reading of "the period was locked once and is not locked now"
(supervisor ruling R-117 (c); DG-KRN-TIME-04 rev 1.167; 04 T-REF-06, T-SL-04 rev 1.184): the
period's current lock record is a ``REOPEN``. ``auto_approval_barred`` is the rule of PRD
BR-CLS-04, BR-DAT-07 and BR-CLS-06 for one period. The DB-07 guard reads the same record for
``is_post_reopen``; no module tests the state literal ``reopened`` for that fact.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from erev_api.db.tables import book as book_rows
from erev_api.db.tables import entity_book, legal_entity, period
from erev_api.db.tables import period_lock as lock_rows
from erev_api.db.tables import period_state as state_rows
from erev_api.enums import BookCode, LockKind, PeriodState
from erev_api.problems import Problem, ProblemError

# DB-07; ENGINE_SPEC S08-R-08; 05 RCP-04; D-79.
POSTABLE_STATES: Final[frozenset[PeriodState]] = frozenset(
    {PeriodState.OPEN, PeriodState.CLOSING, PeriodState.REOPENED}
)
RULE_PERIOD: Final = "T-REF-05"
NO_PERIOD: Final = (
    "No period of the entity's calendar contains {date}. Generate that fiscal year first."
)
NO_POSTABLE_PERIOD: Final = (
    "The period of {date} is not open for {book}, and no later period is open."
)
# PRD §5.5 ERR-15 (BUILD_SPEC CLO-3).
CLOSED_STATES: Final[frozenset[PeriodState]] = frozenset(
    {PeriodState.CLOSED, PeriodState.PERMANENTLY_LOCKED}
)
PERIOD_CLOSED: Final = (
    "{period} is closed for {entity} in book {book}. Postings to a closed period are not allowed."
)


@dataclass(frozen=True, slots=True)
class PeriodRef:
    id: UUID
    calendar_id: UUID
    period_key: str
    fiscal_year: int
    period_no: int
    start_date: date
    end_date: date


_COLUMNS: Final = (
    period.c.id,
    period.c.calendar_id,
    period.c.period_key,
    period.c.fiscal_year,
    period.c.period_no,
    period.c.start_date,
    period.c.end_date,
)


def _ref(row: Mapping[Any, Any]) -> PeriodRef:
    return PeriodRef(
        id=UUID(str(row["id"])),
        calendar_id=UUID(str(row["calendar_id"])),
        period_key=str(row["period_key"]),
        fiscal_year=int(row["fiscal_year"]),
        period_no=int(row["period_no"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
    )


def period_containing(session: Session, *, calendar_id: UUID, d: date) -> PeriodRef:
    """The period of ``calendar_id`` whose dates contain ``d``; ``LookupError`` when none does."""
    statement = select(*_COLUMNS).where(
        period.c.calendar_id == calendar_id, period.c.start_date <= d, period.c.end_date >= d
    )
    row = session.execute(statement).mappings().first()
    if row is None:
        raise LookupError(f"no period of calendar {calendar_id} contains {d.isoformat()}")
    return _ref(row)


def period_by_key(session: Session, *, calendar_id: UUID, period_key: str) -> PeriodRef:
    """The period ``period_key`` of ``calendar_id``; ``LookupError`` for an unknown key."""
    statement = select(*_COLUMNS).where(
        period.c.calendar_id == calendar_id, period.c.period_key == period_key
    )
    row = session.execute(statement).mappings().first()
    if row is None:
        raise LookupError(f"calendar {calendar_id} has no period {period_key!r}")
    return _ref(row)


def period_state(
    session: Session, *, entity_id: UUID, book_code: BookCode, period_id: UUID
) -> PeriodState:
    """The E-04 state of the period for the entity and book; ``LookupError`` when the entity keeps
    no state of that book for the period, or the caller cannot see the entity."""
    statement = select(state_rows.c.state).where(
        state_rows.c.entity_id == entity_id,
        state_rows.c.book_code == book_code.value,
        state_rows.c.period_id == period_id,
    )
    found = session.execute(statement).scalar_one_or_none()
    if found is None:
        raise LookupError(
            f"entity {entity_id} has no {book_code.value} state for period {period_id}"
        )
    return PeriodState(found)


def lock_kind(session: Session, lock_id: UUID | None) -> LockKind | None:
    """The kind of the T-CLS-04 record ``lock_id`` names; None without an id, and for a record the
    caller cannot see."""
    if lock_id is None:
        return None
    found = session.execute(
        select(lock_rows.c.kind).where(lock_rows.c.id == lock_id)
    ).scalar_one_or_none()
    return None if found is None else LockKind(str(getattr(found, "value", found)))


def followed_book(session: Session, book_code: BookCode) -> BookCode | None:
    """The book whose close ``book_code`` follows: the tenant's primary book for the ``LEGACY``
    book, which has no close of its own (04 T-REF-06 and DB-07 rev 1.155); None for every other
    book, and for ``LEGACY`` where the tenant names no other primary book."""
    if book_code is not BookCode.LEGACY:
        return None
    primary = session.execute(
        select(book_rows.c.code).where(book_rows.c.is_primary.is_(True))
    ).scalar()
    if primary is None or str(primary) == book_code.value:
        return None
    return BookCode(str(primary))


def _followed_rows(
    session: Session, *, entity_id: UUID, book_code: BookCode, period_id: UUID
) -> list[tuple[PeriodState, UUID | None]]:
    """(state, current lock id) of the period's state row for the book and, for the ``LEGACY``
    book, of the tenant's primary book's row as well: the LEGACY book has no close of its own and
    follows the primary book's (04 T-REF-06 and DB-07 rev 1.155). Rows the caller cannot see are
    absent."""
    books = [book_code.value]
    followed = followed_book(session, book_code)
    if followed is not None:
        books.append(followed.value)
    found = session.execute(
        select(state_rows.c.state, state_rows.c.current_lock_id).where(
            state_rows.c.entity_id == entity_id,
            state_rows.c.book_code.in_(books),
            state_rows.c.period_id == period_id,
        )
    ).all()
    return [
        (
            PeriodState(row.state),
            None if row.current_lock_id is None else UUID(str(row.current_lock_id)),
        )
        for row in found
    ]


def under_reopen(
    session: Session, *, entity_id: UUID, book_code: BookCode, period_id: UUID
) -> bool:
    """Whether the period of the entity and book was locked once and is not locked now: the
    current lock record of its state row (T-REF-06 ``current_lock_id``) is a ``REOPEN``
    (supervisor ruling R-117 (c)). True while the period is ``reopened`` and through the soft
    close that follows a reopen, whatever the state literal reads; False for a period never
    locked and for one the caller cannot see. For the ``LEGACY`` book the primary book's row
    counts as well, as the DB-07 guard reads it for a LEGACY line (04 rev 1.155, rev 1.184)."""
    rows = _followed_rows(session, entity_id=entity_id, book_code=book_code, period_id=period_id)
    return any(lock_kind(session, lock_id) is LockKind.REOPEN for _, lock_id in rows)


def auto_approval_barred(
    session: Session, *, entity_id: UUID, book_code: BookCode, period_id: UUID
) -> bool:
    """PRD BR-CLS-04, BR-DAT-07 and BR-CLS-06: a posting into the period needs a human approval by
    someone other than the submitter — no ``AUTO_APPROVAL`` rule applies — while the period is in
    soft close (``closing``) or under reopen (``under_reopen``); a posting of the ``LEGACY`` book
    also while the primary book's period is. False for any other period and for one without a
    visible state."""
    rows = _followed_rows(session, entity_id=entity_id, book_code=book_code, period_id=period_id)
    return any(
        state is PeriodState.CLOSING or lock_kind(session, lock_id) is LockKind.REOPEN
        for state, lock_id in rows
    )


def posting_period(
    session: Session, *, entity_id: UUID, book_code: BookCode, effective_date: date
) -> tuple[PeriodRef, PeriodRef | None]:
    """(posting period, origin period) of an amount dated ``effective_date`` (DG-KRN-TIME-04).

    The business date maps to the posting entity's calendar (05 TZ-04). A period without a state
    for the book is not postable. 404 ``not-found`` for an entity the caller cannot see; 422
    ``validation-failed`` on ``effective_date`` when no generated period contains the date; 409
    ``period-closed`` when neither that period nor any later one is postable.

    The ``LEGACY`` book (DG-KRN-TIME-04 rev 1.197; 05 RCP-04 rev 1.153; item
    PER-LEGACY-POSTING-PERIOD-1; supervisor ruling R-118 (h)). A LEGACY amount posts where the
    DB-07 guard admits a LEGACY line and where the bundle's periods send it (04 DB-07 rev 1.155;
    05 RCP-15 rev 1.94): a period is postable for LEGACY only when its own state row AND the
    primary book's row for the same entity and period are — a missing primary row is not
    postable — and the later period is the earliest one postable in both.
    When none exists and the state that refuses is ``closed`` or ``permanently_locked``, the 409
    names the book whose period is closed: the primary where the LEGACY row itself is postable.
    """
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity_id)
    ).scalar_one_or_none()
    if calendar_id is None:
        raise Problem("not-found")
    try:
        containing = period_containing(session, calendar_id=calendar_id, d=effective_date)
    except LookupError:
        message = NO_PERIOD.format(date=effective_date.isoformat())
        error = ProblemError(field="effective_date", rule_id=RULE_PERIOD, message=message)
        raise Problem("validation-failed", errors=[error]) from None
    followed = followed_book(session, book_code)
    refusing = _refusing(
        session, entity_id=entity_id, book_code=book_code, followed=followed, at=containing
    )
    if refusing is None:
        return containing, None
    state, refusing_book = refusing
    postable = [member.value for member in POSTABLE_STATES]
    both: list[Any] = []
    if followed is not None:
        followed_state = state_rows.alias("followed_state")
        both.append(
            exists().where(
                followed_state.c.entity_id == entity_id,
                followed_state.c.book_code == followed.value,
                followed_state.c.period_id == period.c.id,
                followed_state.c.state.in_(postable),
            )
        )
    later = (
        select(*_COLUMNS)
        .select_from(
            period.join(
                state_rows,
                and_(
                    state_rows.c.tenant_id == period.c.tenant_id,
                    state_rows.c.period_id == period.c.id,
                ),
            )
        )
        .where(
            period.c.calendar_id == calendar_id,
            period.c.start_date > containing.end_date,
            state_rows.c.entity_id == entity_id,
            state_rows.c.book_code == book_code.value,
            state_rows.c.state.in_(postable),
            *both,
        )
        .order_by(period.c.start_date)
        .limit(1)
    )
    row = session.execute(later).mappings().first()
    if row is None:
        if state in CLOSED_STATES:
            raise _closed_problem(
                session, entity_id=entity_id, book_code=refusing_book, at=containing
            )
        detail = NO_POSTABLE_PERIOD.format(date=effective_date.isoformat(), book=book_code.value)
        raise Problem("period-closed", detail)
    return _ref(row), containing


def _state_or_none(
    session: Session, *, entity_id: UUID, book_code: BookCode, period_id: UUID
) -> PeriodState | None:
    try:
        return period_state(session, entity_id=entity_id, book_code=book_code, period_id=period_id)
    except LookupError:
        return None


def _refusing(
    session: Session,
    *,
    entity_id: UUID,
    book_code: BookCode,
    followed: BookCode | None,
    at: PeriodRef,
) -> tuple[PeriodState | None, BookCode] | None:
    """None when a posting of ``book_code`` is admitted in the period ``at``; else the state that
    refuses it and the book that state is of: the book's own row first, then the row of the book
    it follows (``followed``; the LEGACY book's primary). A missing row is the state None."""
    for book in (book_code, followed):
        if book is None:
            continue
        state = _state_or_none(session, entity_id=entity_id, book_code=book, period_id=at.id)
        if state not in POSTABLE_STATES:
            return state, book
    return None


def _closed_problem(
    session: Session, *, entity_id: UUID, book_code: BookCode, at: PeriodRef
) -> Problem:
    """409 ``period-closed`` with the ERR-15 detail for the closed period ``at``."""
    names = session.execute(
        select(period.c.name, legal_entity.c.code)
        .select_from(period.join(legal_entity, legal_entity.c.tenant_id == period.c.tenant_id))
        .where(period.c.id == at.id, legal_entity.c.id == entity_id)
    ).one()
    detail = PERIOD_CLOSED.format(period=names[0], entity=names[1], book=book_code.value)
    return Problem("period-closed", detail, code="EREV-LED-003")


def kept_books(session: Session, entity_id: UUID) -> list[BookCode]:
    """The books with period states of ``entity_id`` that the entity keeps, in code order: every
    book it has a state row for, less a book whose ``entity_book`` row is not enabled (04
    T-REF-03) and a book the workspace has disabled (T-REF-02) — the books a computation of the
    entity posts in (05 RCP-15). A book without an ``entity_book`` row visible to the caller
    counts as kept: the states are what the question is about."""
    stated = session.execute(
        select(state_rows.c.book_code).where(state_rows.c.entity_id == entity_id).distinct()
    ).scalars()
    dropped = session.execute(
        select(entity_book.c.book_code)
        .where(entity_book.c.entity_id == entity_id, entity_book.c.is_enabled.is_(False))
        .union(select(book_rows.c.code).where(book_rows.c.is_enabled.is_(False)))
    ).scalars()
    not_kept = {str(code) for code in dropped}
    return sorted(
        {BookCode(str(code)) for code in stated if str(code) not in not_kept},
        key=lambda member: member.value,
    )


def refuse_closed_postings(
    session: Session, *, entity_id: UUID, effective_dates: Iterable[date]
) -> None:
    """DG-CMD-03 mirror of DB-07 (BUILD_SPEC CLO-3; PRD ERR-15): 409 ``period-closed`` when an
    amount dated in a ``closed`` or ``permanently_locked`` period of a kept book would find no later
    postable period. A closed period with a later postable one is a late event (DG-KRN-TIME-04),
    and a future period posts nothing, so neither refuses.

    The books asked are the ones the entity keeps (``kept_books``; DG-KRN-TIME-04 rev 1.197): a
    book it has stopped keeping takes no posting and its periods are no longer opened, so a
    question put to it would refuse every late event with no way out — for the ``LEGACY`` book
    as soon as the primary book's period is locked, since its own next period stays ``future``."""
    books = kept_books(session, entity_id)
    for effective_date in sorted(set(effective_dates)):
        for book_code in books:
            try:
                posting_period(
                    session, entity_id=entity_id, book_code=book_code, effective_date=effective_date
                )
            except Problem as problem:
                if problem.slug == "period-closed" and problem.code == "EREV-LED-003":
                    raise
