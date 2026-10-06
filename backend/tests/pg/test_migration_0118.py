"""Revision 0118 at the catalogue (04 rev 1.242 E-57, T-CON-19; PRD rev 1.169 SM-10; the
supervisor's ruling of 2026-10-01 on the lane's question J1 (a)): a DRAFT judgement record is
discarded. PostgreSQL-bound; the test writes the rows of a tenant of its own.

E-57 ``judgement_status`` holds ``VOIDED``, and DB-03 admits the pair (DRAFT, VOIDED) and no
other pair into or out of that status: a record that waits for its review, a reviewed one and a
rejected one are not voided, and a voided record goes nowhere.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import judgement_record
from sqlalchemy import exc, insert, text, update
from support.db import TestDatabase
from support.principals import member
from support.rows import judgement_record_values

pytestmark = pytest.mark.pg

_LABELS = text(
    "SELECT e.enumlabel::text FROM pg_enum e "
    "JOIN pg_type t ON t.oid = e.enumtypid "
    "JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'erev' "
    "WHERE t.typname = 'judgement_status' ORDER BY e.enumsortorder"
)
REFUSED = "EREV-TRN-001: status of erev.judgement_record cannot change from {old} to {new}"


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _moved(row: dict[str, Any], status: str) -> Any:
    return update(judgement_record).where(judgement_record.c.id == row["id"]).values(status=status)


def _refused(session: Any, statement: Any) -> str:
    """The database's message for ``statement``, run in a savepoint that is rolled back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    return str(refused.value.orig)


def test_0118_a_draft_judgement_record_is_voided_and_nothing_else(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    with test_database.owner_engine.connect() as connection:
        labels = [str(label) for label in connection.execute(_LABELS).scalars()]
    assert labels == ["DRAFT", "SUBMITTED", "REVIEWED", "REJECTED", "SUPERSEDED", "VOIDED"]

    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:

        def stored() -> dict[str, Any]:
            row = judgement_record_values(tenant_id)
            session.execute(insert(judgement_record).values(**row))
            return row

        def refused(row: dict[str, Any], old: str, new: str) -> None:
            assert REFUSED.format(old=old, new=new) in _refused(session, _moved(row, new))

        # a draft is discarded; a discarded record goes nowhere
        draft = stored()
        session.execute(_moved(draft, "VOIDED"))
        for status in ("DRAFT", "SUBMITTED", "REVIEWED", "REJECTED", "SUPERSEDED"):
            refused(draft, "VOIDED", status)

        # a record that waits for its review, a reviewed, a superseded and a rejected one
        waiting = stored()
        session.execute(_moved(waiting, "SUBMITTED"))
        refused(waiting, "SUBMITTED", "VOIDED")
        session.execute(_moved(waiting, "REVIEWED"))
        refused(waiting, "REVIEWED", "VOIDED")
        session.execute(_moved(waiting, "SUPERSEDED"))
        refused(waiting, "SUPERSEDED", "VOIDED")
        rejected = stored()
        session.execute(_moved(rejected, "SUBMITTED"))
        session.execute(_moved(rejected, "REJECTED"))
        refused(rejected, "REJECTED", "VOIDED")
        # ... which is a draft again by its revision, and is then discarded
        session.execute(_moved(rejected, "DRAFT"))
        session.execute(_moved(rejected, "VOIDED"))
        session.rollback()
