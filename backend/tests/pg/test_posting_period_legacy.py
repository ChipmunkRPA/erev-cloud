"""``periods.posting_period`` for the LEGACY book (item PER-LEGACY-POSTING-PERIOD-1; supervisor
ruling R-118 (h); dev-guide DG-KRN-TIME-04 rev 1.197; 05 RCP-04 rev 1.153 and RCP-15 rev 1.94; 04
§14.1 DB-07 rev 1.155; REQ-CLS-002). PostgreSQL-bound: ``erev_app`` sessions, probe rows through
``support.rows``.

The LEGACY book has no close of its own and follows the primary book's: the DB-07 guard refuses a
LEGACY line while the primary book's period is not postable, and the bundle hands the engine the
primary's state. The posting-period helper judged the LEGACY row's own state alone, so for a date
in a period the primary book had closed it answered that period — where the guard refuses the
line. Each case here asks the helper and then inserts LEGACY lines in the same rows: where the
helper answers a period the guard admits the line there, and refuses it in every period before.

Three periods of one calendar, January to March 2026; a case names the state of each period for
the primary book and for the LEGACY book (None: the book keeps no row for the period).

The mirror of DB-07 on a command, ``periods.refuse_closed_postings``, puts that question to the
books the entity keeps (``periods.kept_books``; DG-KRN-TIME-04 rev 1.197): a book it has stopped
keeping takes no posting and opens no period, so with the rule above it would refuse every late
event from the next lock of the primary book on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api import periods
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    book,
    entity_book,
    legal_entity,
    period,
    period_state,
    subledger_line,
    subledger_posting,
)
from erev_api.enums import BookCode
from erev_api.problems import Problem
from sqlalchemy import exc, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    LedgerParts,
    entity_book_values,
    insert_ledger_parts,
    period_state_values,
    period_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

PRIMARY: Final = BookCode.ASC606  # the primary book of a provisioned tenant (04 §14.3)
LEGACY: Final = BookCode.LEGACY
DATED: Final = date(2026, 1, 15)  # a business date of January, the first period
MONTHS: Final = (
    (1, date(2026, 1, 1), date(2026, 1, 31)),
    (2, date(2026, 2, 1), date(2026, 2, 28)),
    (3, date(2026, 3, 1), date(2026, 3, 31)),
)
States = tuple[str | None, str | None]  # (primary book, LEGACY book) of one period


@dataclass(frozen=True)
class Probe:
    context: DbContext
    tenant_id: UUID
    parts: LedgerParts
    period_ids: tuple[UUID, ...]  # January, February, March
    period_keys: tuple[str, ...]


def _probe(keyring: KeyRing, states: tuple[States, States, States]) -> Probe:
    """The committed rows of a case: the three periods and, per period, the state rows the case
    names. January's primary row is the one ``insert_ledger_parts`` writes."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    january_primary = states[0][0]
    assert january_primary is not None, "the probe's first period keeps a primary row"
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id, state=january_primary)
        entity_id = parts.chain.entity_id
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity_id)
        ).scalar_one()
        period_ids = [parts.period_id]
        keys = ["FY2026-P01"]
        for number, start, end in MONTHS[1:]:
            values = period_values(
                tenant_id, calendar_id=calendar_id, period_no=number, start_date=start, end_date=end
            )
            session.execute(insert(period).values(**values))
            period_ids.append(UUID(str(values["id"])))
            keys.append(str(values["period_key"]))
        for index, (primary, legacy) in enumerate(states):
            for book, state in ((PRIMARY, primary), (LEGACY, legacy)):
                if state is None or (index == 0 and book is PRIMARY):
                    continue
                session.execute(
                    insert(period_state).values(
                        **period_state_values(
                            tenant_id,
                            entity_id=entity_id,
                            period_id=period_ids[index],
                            period_end_date=MONTHS[index][2],
                            book_code=book,
                            state=state,
                        )
                    )
                )
        session.commit()
    return Probe(context, tenant_id, parts, tuple(period_ids), tuple(keys))


def _legacy_line(session: Session, probe: Probe, index: int) -> None:
    """One LEGACY line dated ``DATED`` posted into the period ``index`` — with January as its
    origin when it posts later — inside a savepoint, so a refusal leaves the session usable."""
    posting = subledger_posting_values(
        probe.tenant_id,
        parts=probe.parts,
        book_code=LEGACY.value,
        idempotency_key=f"probe:{new_id()}",
    )
    columns: dict[str, Any] = {
        "period_id": probe.period_ids[index],
        "period_end_date": MONTHS[index][2],
        "effective_date": DATED,
    }
    if index > 0:
        # 05 RCP-04: a line of a later period carries its origin and the reason (T-SL-04)
        columns["origin_period_id"] = probe.period_ids[0]
        columns["reason_code"] = "LATE_EVENT"
    with session.begin_nested():
        session.execute(insert(subledger_posting).values(**posting))
        line = subledger_line_values(probe.tenant_id, posting=posting, parts=probe.parts, **columns)
        session.execute(insert(subledger_line).values(**line))


def _admitted(session: Session, probe: Probe, index: int) -> bool:
    """Whether the DB-07 guard admits a LEGACY line into the period ``index``."""
    try:
        _legacy_line(session, probe, index)
    except exc.DBAPIError as error:
        diag = getattr(error.orig, "diag", None)
        message = str(getattr(diag, "message_primary", "") or "")
        assert getattr(error.orig, "sqlstate", None) == "P0001", message
        assert message.startswith("EREV-LED-003: "), message
        return False
    return True


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    ("states", "posting", "origin"),
    [
        # both books postable: the period of the date, no origin
        ((("open", "open"), ("open", "open"), ("open", "open")), 0, None),
        ((("closing", "open"), ("open", "open"), ("open", "open")), 0, None),
        ((("reopened", "open"), ("open", "open"), ("open", "open")), 0, None),
        # the primary book's period is not postable: the first later period postable in both
        ((("closed", "open"), ("open", "open"), ("open", "open")), 1, 0),
        ((("permanently_locked", "open"), ("open", "open"), ("open", "open")), 1, 0),
        ((("future", "open"), ("open", "open"), ("open", "open")), 1, 0),
        # a later period postable in one book only is skipped
        ((("closed", "open"), ("closed", "open"), ("open", "open")), 2, 0),
        ((("closed", "open"), ("open", None), ("open", "open")), 2, 0),
        ((("closed", "open"), (None, "open"), ("open", "open")), 2, 0),
        # the LEGACY row's own state refuses as it always did
        ((("open", "closed"), ("open", "open"), ("open", "open")), 1, 0),
        ((("open", None), ("open", "open"), ("open", "open")), 1, 0),
    ],
)
def test_time_04_a_legacy_date_posts_where_the_guard_admits_a_legacy_line(
    committed_db: TestDatabase,
    keyring: KeyRing,
    states: tuple[States, States, States],
    posting: int,
    origin: int | None,
) -> None:
    """The helper's answer for a LEGACY amount dated in January, and the guard on the same rows:
    a LEGACY line is admitted in the period the helper names and refused (``EREV-LED-003``) in
    every period before it.

    Fail-first (the helper read the LEGACY row alone): with the primary book's January closed,
    permanently locked or ``future`` and the LEGACY row ``open`` it answered January without an
    origin — the period in which the guard refuses the line."""
    probe = _probe(keyring, states)
    with tenant_session(probe.context) as session:
        found, came_from = periods.posting_period(
            session,
            entity_id=probe.parts.chain.entity_id,
            book_code=LEGACY,
            effective_date=DATED,
        )
        assert (found.period_key, None if came_from is None else came_from.period_key) == (
            probe.period_keys[posting],
            None if origin is None else probe.period_keys[origin],
        )
        for index in range(posting):
            assert not _admitted(session, probe, index), probe.period_keys[index]
        assert _admitted(session, probe, posting), probe.period_keys[posting]
        session.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    ("states", "closed_book"),
    [
        # no later period is postable in both books, and the state that refuses is a closed one:
        # PRD ERR-15 with EREV-LED-003, naming the book whose period is closed
        ((("closed", "open"), ("closed", "open"), ("permanently_locked", "open")), PRIMARY),
        ((("closed", "closed"), ("open", "closed"), ("open", "closed")), LEGACY),
        # the state a lock of the primary book leaves when it opens the primary's next period
        # alone (BR-CLS-03) and the LEGACY row of that period is still ``future``
        ((("closed", "open"), ("open", "future"), ("future", "future")), PRIMARY),
        # the state that refuses is not a closed one: 409 without the code
        ((("future", "open"), ("future", "open"), ("future", "open")), None),
        ((("open", None), ("open", None), ("open", None)), None),
    ],
)
def test_time_04_a_legacy_date_without_a_period_postable_in_both_books_is_refused(
    committed_db: TestDatabase,
    keyring: KeyRing,
    states: tuple[States, States, States],
    closed_book: BookCode | None,
) -> None:
    """Neither January nor a later period is postable in both books: 409 ``period-closed`` — PRD
    ERR-15 with ``EREV-LED-003`` when the state that refuses January is ``closed`` or
    ``permanently_locked``, naming the book whose period is closed (the primary where the LEGACY
    row itself is postable) — and the guard admits a LEGACY line in none of the three periods.

    Fail-first (the first case): the helper answered January, postable in the LEGACY book."""
    probe = _probe(keyring, states)
    with tenant_session(probe.context) as session:
        with pytest.raises(Problem) as refused:
            periods.posting_period(
                session,
                entity_id=probe.parts.chain.entity_id,
                book_code=LEGACY,
                effective_date=DATED,
            )
        problem = refused.value
        assert problem.slug == "period-closed"
        if closed_book is None:
            assert problem.code is None
            assert problem.detail == periods.NO_POSTABLE_PERIOD.format(
                date=DATED.isoformat(), book=LEGACY.value
            )
        else:
            assert problem.code == "EREV-LED-003"
            assert f"in book {closed_book.value}." in str(problem.detail), problem.detail
        for index in range(len(MONTHS)):
            assert not _admitted(session, probe, index), probe.period_keys[index]
        session.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    ("states", "posting", "origin"),
    [
        ((("open", "closed"), ("open", "open"), ("open", "open")), 0, None),
        ((("closed", "open"), ("open", "closed"), ("open", "open")), 1, 0),
        ((("closed", None), ("closed", None), ("open", None)), 2, 0),
    ],
)
def test_time_04_the_primary_book_is_judged_by_its_own_rows_alone(
    committed_db: TestDatabase,
    keyring: KeyRing,
    states: tuple[States, States, States],
    posting: int,
    origin: int | None,
) -> None:
    """The control: for the primary book — as for every book but LEGACY — the helper reads that
    book's rows and no other; what the LEGACY rows read does not move its answer."""
    probe = _probe(keyring, states)
    with tenant_session(probe.context) as session:
        found, came_from = periods.posting_period(
            session,
            entity_id=probe.parts.chain.entity_id,
            book_code=PRIMARY,
            effective_date=DATED,
        )
        assert (found.period_key, None if came_from is None else came_from.period_key) == (
            probe.period_keys[posting],
            None if origin is None else probe.period_keys[origin],
        )
        session.rollback()


# the state a lock of the primary book's January leaves while the LEGACY book's February is
# ``future``: the primary posts a January date in February, the LEGACY book has no period
AFTER_A_LOCK: Final[tuple[States, States, States]] = (
    ("closed", "open"),
    ("open", "future"),
    ("future", "future"),
)


def _legacy_kept(session: Session, probe: Probe, *, workspace: bool, entity: bool | None) -> None:
    """The LEGACY book as the workspace enables it (T-REF-02; provisioning leaves it disabled)
    and as the probe's entity keeps it (T-REF-03; None: no row, the probe's own shape)."""
    session.execute(
        update(book)
        .where(book.c.tenant_id == probe.tenant_id, book.c.code == LEGACY.value)
        .values(is_enabled=workspace)
    )
    if entity is not None:
        kept = entity_book_values(
            probe.tenant_id,
            entity_id=probe.parts.chain.entity_id,
            first_period_id=probe.period_ids[0],
            book_code=LEGACY,
        )
        session.execute(insert(entity_book).values(**kept, is_enabled=entity))


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    ("workspace", "entity", "asked"),
    [
        (True, True, True),  # kept: the mirror asks the book, and no period is postable in both
        (True, None, True),  # states without a T-REF-03 row are still what the question is about
        (True, False, False),  # the entity keeps the book no longer
        (False, True, False),  # the workspace has disabled the book: no computation posts in it
    ],
)
def test_time_04_the_mirror_asks_the_books_the_entity_keeps(
    committed_db: TestDatabase,
    keyring: KeyRing,
    workspace: bool,
    entity: bool | None,
    asked: bool,
) -> None:
    """``periods.refuse_closed_postings`` for a date in a January the primary book has closed,
    February open in the primary book and ``future`` in the LEGACY book. A kept LEGACY book is
    asked and refuses — PRD ERR-15 with ``EREV-LED-003``, naming the primary book. A LEGACY book
    the entity has stopped keeping, or the workspace has disabled, is not asked: the primary
    book's answer stands — a late event, posted in February — and nothing is refused.

    Fail-first (the mirror asked every book with period states): the two cases that are not
    asked were refused as the kept one is, with no way out — a book that is not kept opens no
    period."""
    probe = _probe(keyring, AFTER_A_LOCK)
    entity_id = probe.parts.chain.entity_id
    with tenant_session(probe.context) as session:
        _legacy_kept(session, probe, workspace=workspace, entity=entity)
        assert periods.kept_books(session, entity_id) == ([PRIMARY, LEGACY] if asked else [PRIMARY])
        if asked:
            with pytest.raises(Problem) as refused:
                periods.refuse_closed_postings(
                    session, entity_id=entity_id, effective_dates=[DATED]
                )
            problem = refused.value
            assert (problem.slug, problem.code) == ("period-closed", "EREV-LED-003")
            assert f"in book {PRIMARY.value}." in str(problem.detail), problem.detail
        else:
            periods.refuse_closed_postings(session, entity_id=entity_id, effective_dates=[DATED])
        found, came_from = periods.posting_period(
            session, entity_id=entity_id, book_code=PRIMARY, effective_date=DATED
        )
        assert (found.period_key, None if came_from is None else came_from.period_key) == (
            probe.period_keys[1],
            probe.period_keys[0],
        )
        session.rollback()
