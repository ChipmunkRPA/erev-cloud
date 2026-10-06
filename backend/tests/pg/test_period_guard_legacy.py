"""DB-07 for the LEGACY book: a LEGACY subledger line follows the state of the PRIMARY book's
period (04 §14.1 DB-07 rev 1.155; revision 0105; supervisor rulings R-97 (2), R-112 (e) and
R-114 (d) of 2026-09-30; finding F1 of the independent review of revision 0084; REQ-CLS-002,
REQ-CLS-011; CTL-015). PostgreSQL-bound: ``erev_app`` sessions, probe rows through
``support.rows``.

The LEGACY book has no close of its own, so its state rows stay postable. Until revision 0105 the
guard read the LEGACY row alone: a LEGACY line was admitted into a period the primary book had
locked, and held no row a lock decision of the primary book waits for. The planner's half — the
bundle hands the engine the primary's state — and the lock decision's wait are witnessed in
``tests/domain/close/test_lock_legacy_db.py``.

Since revision 0113 (lane SECFIX-CLO, item REOPEN-CLOSING-FLAG-1; supervisor ruling R-117 (c); 04
DB-07 rev 1.184) the stored ``is_post_reopen`` follows the ``REOPEN`` record of the line's own
state row or of the primary book's, not a state literal: a probe that needs a reopened period
names the books it puts under such a record.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
    legal_entity,
    period,
    period_state,
    subledger_line,
    subledger_posting,
)
from erev_api.enums import BookCode
from sqlalchemy import exc, insert, select
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    insert_ledger_parts,
    insert_reopen_record,
    period_state_values,
    period_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

LOCK_NOT_AVAILABLE: Final = "55P03"
PRIMARY: Final = BookCode.ASC606.value  # the primary book of a provisioned tenant (04 §14.3)
LEGACY: Final = BookCode.LEGACY.value
FOLLOWS: Final = "whose close the LEGACY book follows"


@dataclass(frozen=True, slots=True)
class Probe:
    """One tenant with FY2026-P01 of one entity: the primary book's state row and, unless the
    probe leaves it out, the LEGACY book's."""

    context: DbContext
    tenant_id: UUID
    parts: Any
    primary_state_id: UUID
    legacy_state_id: UUID | None


def _state_id(session: Session, entity_id: UUID, period_id: UUID, book: str) -> UUID | None:
    found = session.execute(
        select(period_state.c.id).where(
            period_state.c.entity_id == entity_id,
            period_state.c.period_id == period_id,
            period_state.c.book_code == book,
        )
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def _probe(
    keyring: KeyRing, *, primary: str, legacy: str | None, reopened: tuple[str, ...] = ()
) -> Probe:
    """The committed rows of a probe: FY2026-P01 in ``primary`` for the primary book and in
    ``legacy`` for the LEGACY book; ``None`` leaves the LEGACY book without a state row. The
    books named in ``reopened`` are put under a ``REOPEN`` record, as the reopen decision
    leaves a period (``support.rows.insert_reopen_record``; 04 T-REF-06 rev 1.184)."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id, state=primary)
        entity_id = parts.chain.entity_id
        if legacy is not None:
            session.execute(
                insert(period_state).values(
                    **period_state_values(
                        tenant_id,
                        entity_id=entity_id,
                        period_id=parts.period_id,
                        period_end_date=parts.period_end_date,
                        book_code=BookCode.LEGACY,
                        state=legacy,
                    )
                )
            )
        for code in reopened:
            insert_reopen_record(
                session,
                tenant_id,
                entity_id=entity_id,
                period_id=parts.period_id,
                book_code=BookCode(code),
            )
        primary_id = _state_id(session, entity_id, parts.period_id, PRIMARY)
        legacy_id = _state_id(session, entity_id, parts.period_id, LEGACY)
        session.commit()
    assert primary_id is not None
    return Probe(context, tenant_id, parts, primary_id, legacy_id)


def _insert_line(
    poster: Session, probe: Probe, *, book: str = LEGACY, **columns: Any
) -> tuple[UUID, bool]:
    """One line of ``book`` in the poster's transaction (DB-06 (1): with a posting of its own);
    returns its id and the ``is_post_reopen`` the guard stored."""
    posting = subledger_posting_values(
        probe.tenant_id, parts=probe.parts, book_code=book, idempotency_key=f"probe:{new_id()}"
    )
    poster.execute(insert(subledger_posting).values(**posting))
    line = subledger_line_values(probe.tenant_id, posting=posting, parts=probe.parts, **columns)
    flag = poster.execute(
        insert(subledger_line).values(**line).returning(subledger_line.c.is_post_reopen)
    ).scalar_one()
    return UUID(str(line["id"])), bool(flag)


def _sqlstate(error: exc.DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _message(error: exc.DBAPIError) -> str:
    diag = getattr(error.orig, "diag", None)
    return str(getattr(diag, "message_primary", "") or "")


def _row_lock(state_id: UUID | None, *, share: bool) -> Any:
    """A state row ``FOR UPDATE`` (a change of the state) or ``FOR SHARE``, NOWAIT."""
    assert state_id is not None
    return (
        select(period_state.c.state)
        .where(period_state.c.id == state_id)
        .with_for_update(read=share, nowait=True)
    )


@contextmanager
def _other(probe: Probe) -> Iterator[Session]:
    """A second ``erev_app`` transaction of the tenant, rolled back at the end."""
    with tenant_session(probe.context) as session:
        try:
            yield session
        finally:
            session.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    ("primary", "legacy", "reopened", "post_reopen"),
    [
        ("open", "open", (), False),
        ("closing", "open", (), False),
        ("open", "closing", (), False),
        # the flag follows the REOPEN record of either row (REQ-CLS-011; 04 DB-07 rev 1.184)
        ("reopened", "open", (PRIMARY,), True),
        ("open", "reopened", (LEGACY,), True),
        ("reopened", "reopened", (PRIMARY, LEGACY), True),
        # the primary book in soft close again after its reopen: still under the REOPEN record
        ("closing", "open", (PRIMARY,), True),
    ],
)
def test_db_07_a_legacy_line_posts_while_both_books_are_postable(
    committed_db: TestDatabase,
    keyring: KeyRing,
    primary: str,
    legacy: str,
    reopened: tuple[str, ...],
    post_reopen: bool,
) -> None:
    """A LEGACY line is admitted while the primary book's period AND its own are ``open``,
    ``closing`` or ``reopened``; ``is_post_reopen`` is true when either row is under a ``REOPEN``
    record — locked once and not locked now (revision 0113, lane SECFIX-CLO; supervisor ruling
    R-117 (c): revision 0105 stored "either state is ``reopened``", so a LEGACY line beside a
    primary period in soft close again after its reopen was stored false). A line of the primary
    book beside it carries the primary's flag alone. ``periods.under_reopen`` answers for the
    LEGACY book as the guard stores. Fail-first (the 0084 body): a LEGACY line beside a reopened
    primary period stored ``false``."""
    probe = _probe(keyring, primary=primary, legacy=legacy, reopened=reopened)
    with tenant_session(probe.context) as poster:
        _, flag = _insert_line(poster, probe)
        assert flag is post_reopen
        _, primary_flag = _insert_line(poster, probe, book=PRIMARY)
        assert primary_flag is (PRIMARY in reopened)
        scope = {"entity_id": probe.parts.chain.entity_id, "period_id": probe.parts.period_id}
        read = {
            code: periods.under_reopen(poster, book_code=BookCode(code), **scope)
            for code in (PRIMARY, LEGACY)
        }
        assert read == {PRIMARY: primary_flag, LEGACY: flag}
        # PRD BR-CLS-04 / BR-CLS-06 for a LEGACY posting: the primary's soft close counts too
        assert periods.auto_approval_barred(poster, book_code=BookCode.LEGACY, **scope) is (
            flag or "closing" in (primary, legacy)
        )
        poster.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("primary", ["closed", "permanently_locked", "future"])
@pytest.mark.parametrize("legacy", ["open", "closing", "reopened"])
def test_db_07_a_legacy_line_is_refused_while_the_primary_book_is_not_postable(
    committed_db: TestDatabase, keyring: KeyRing, primary: str, legacy: str
) -> None:
    """The LEGACY row is postable and the primary book's period is not: the line is refused
    ``EREV-LED-003`` naming the primary book, and once its statement is rolled back it holds
    neither state row — a change of either takes its row at once. Fail-first (the 0084 body, the
    lane's measurement): the line was admitted into the period the primary book had locked."""
    probe = _probe(keyring, primary=primary, legacy=legacy)
    with tenant_session(probe.context) as poster:
        attempt = poster.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            _insert_line(poster, probe)
        attempt.rollback()
        message = _message(refused.value)
        assert _sqlstate(refused.value) == "P0001", message
        assert message.startswith("EREV-LED-003: "), message
        assert f"is {primary} in book {PRIMARY}, {FOLLOWS}" in message, message
        with _other(probe) as changer:
            assert changer.execute(_row_lock(probe.primary_state_id, share=False)).scalar_one() == (
                primary
            )
            assert changer.execute(_row_lock(probe.legacy_state_id, share=False)).scalar_one() == (
                legacy
            )
        poster.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("legacy", ["closed", "permanently_locked", "future", None])
def test_db_07_a_legacy_line_still_needs_its_own_postable_state(
    committed_db: TestDatabase, keyring: KeyRing, legacy: str | None
) -> None:
    """The rule of the LEGACY row itself is unchanged: with the primary book's period open, a
    LEGACY line is refused when the LEGACY row is not postable or does not exist — by the message
    of every book, naming LEGACY."""
    probe = _probe(keyring, primary="open", legacy=legacy)
    with tenant_session(probe.context) as poster:
        attempt = poster.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            _insert_line(poster, probe)
        attempt.rollback()
        message = _message(refused.value)
        assert _sqlstate(refused.value) == "P0001", message
        assert f"is {legacy or 'without a state'} in book {LEGACY}, so line" in message, message
        assert FOLLOWS not in message
        poster.rollback()


@pytest.mark.control("CTL-015")
def test_db_07_a_legacy_line_is_refused_where_the_entity_keeps_no_primary_period(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """A period for which the entity has a LEGACY state row and none of the primary book — a
    LEGACY book kept from an earlier first period (04 T-REF-03) — is not postable for the LEGACY
    book either: the line is refused, naming the primary book ``without a state``."""
    probe = _probe(keyring, primary="open", legacy="open")
    entity_id = probe.parts.chain.entity_id
    with tenant_session(probe.context) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity_id)
        ).scalar_one()
        february = period_values(
            probe.tenant_id,
            calendar_id=calendar_id,
            period_no=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        session.execute(insert(period).values(**february))
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    probe.tenant_id,
                    entity_id=entity_id,
                    period_id=february["id"],
                    period_end_date=february["end_date"],
                    book_code=BookCode.LEGACY,
                    state="open",
                )
            )
        )
        session.commit()
    with tenant_session(probe.context) as poster:
        attempt = poster.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            _insert_line(
                poster,
                probe,
                period_id=february["id"],
                period_end_date=february["end_date"],
                effective_date=date(2026, 2, 15),
            )
        attempt.rollback()
        message = _message(refused.value)
        assert _sqlstate(refused.value) == "P0001", message
        assert f"is without a state in book {PRIMARY}, {FOLLOWS}" in message, message
        poster.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("primary", ["open", "closing", "reopened"])
def test_db_07_a_legacy_line_in_flight_holds_the_primary_books_state_row(
    committed_db: TestDatabase, keyring: KeyRing, primary: str
) -> None:
    """A LEGACY line inserted and not committed holds the PRIMARY book's state row ``FOR SHARE``
    — the row the lock decision of the primary book takes ``FOR UPDATE`` — and its own: a change
    of either state cannot take its row (``FOR UPDATE NOWAIT`` answers 55P03), another poster
    shares both, and once the transaction ends both are free. Fail-first (the 0084 body): the
    primary's row was granted ``FOR UPDATE`` while the LEGACY line was uncommitted — the lock
    decision did not wait for it."""
    probe = _probe(keyring, primary=primary, legacy="open")
    with tenant_session(probe.context) as poster:
        _insert_line(poster, probe)  # in flight: inserted, not committed
        for state_id in (probe.primary_state_id, probe.legacy_state_id):
            with _other(probe) as closer, pytest.raises(exc.DBAPIError) as refused:
                closer.execute(_row_lock(state_id, share=False))
            assert _sqlstate(refused.value) == LOCK_NOT_AVAILABLE, _message(refused.value)
            assert "period_state" in _message(refused.value)
        with _other(probe) as second:
            assert second.execute(_row_lock(probe.primary_state_id, share=True)).scalar_one() == (
                primary
            )
            assert second.execute(_row_lock(probe.legacy_state_id, share=True)).scalar_one() == (
                "open"
            )
        poster.rollback()
    with _other(probe) as closer:  # the posting ended: both states can change again
        assert closer.execute(_row_lock(probe.primary_state_id, share=False)).scalar_one() == (
            primary
        )
        assert closer.execute(_row_lock(probe.legacy_state_id, share=False)).scalar_one() == "open"


@pytest.mark.control("CTL-015")
def test_db_07_a_primary_book_line_takes_no_legacy_state_row(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """The other direction does not exist: a line of the primary book holds its own state row and
    leaves the LEGACY row free, so the LEGACY row adds no wait to a posting of a posting book."""
    probe = _probe(keyring, primary="open", legacy="open")
    with tenant_session(probe.context) as poster:
        _insert_line(poster, probe, book=PRIMARY)
        with _other(probe) as changer:
            assert changer.execute(_row_lock(probe.legacy_state_id, share=False)).scalar_one() == (
                "open"
            )
        with _other(probe) as closer, pytest.raises(exc.DBAPIError) as refused:
            closer.execute(_row_lock(probe.primary_state_id, share=False))
        assert _sqlstate(refused.value) == LOCK_NOT_AVAILABLE, _message(refused.value)
        poster.rollback()
