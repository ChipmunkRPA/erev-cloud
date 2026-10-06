"""Revision 0126 at the catalogue (04 rev 1.289 E-95, T-CON-03; PRD rev 1.196 SM-10, ACT-04; item
COMBINATION-PROPOSAL-DISCARD-1, the supervisor's rulings of 2026-10-02): a PROPOSED combination
group is discarded. PostgreSQL-bound; the test writes the rows of a tenant of its own.

E-95 ``combination_status`` holds ``VOIDED``, and DB-03 admits the pair (PROPOSED, VOIDED) and no
other pair into or out of that status: a group that waits for its approval, an approved, an
applied and a rejected one are not voided, and a voided group goes nowhere.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import combination_group
from sqlalchemy import exc, insert, text, update
from support.db import TestDatabase
from support.principals import member
from support.rows import combination_group_values

pytestmark = pytest.mark.pg

_LABELS = text(
    "SELECT e.enumlabel::text FROM pg_enum e "
    "JOIN pg_type t ON t.oid = e.enumtypid "
    "JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'erev' "
    "WHERE t.typname = 'combination_status' ORDER BY e.enumsortorder"
)
REFUSED = "EREV-TRN-001: status of erev.combination_group cannot change from {old} to {new}"


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _moved(row: dict[str, Any], status: str) -> Any:
    return (
        update(combination_group).where(combination_group.c.id == row["id"]).values(status=status)
    )


def _refused(session: Any, statement: Any) -> str:
    """The database's message for ``statement``, run in a savepoint that is rolled back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    return str(refused.value.orig)


def test_0126_a_proposed_group_is_voided_and_nothing_else(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    with test_database.owner_engine.connect() as connection:
        labels = [str(label) for label in connection.execute(_LABELS).scalars()]
    assert labels == ["PROPOSED", "SUBMITTED", "APPROVED", "APPLIED", "REJECTED", "VOIDED"]

    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:

        def stored() -> dict[str, Any]:
            row = combination_group_values(
                tenant_id, is_singleton=False, status="PROPOSED", criterion="25_9_A"
            )
            session.execute(insert(combination_group).values(**row))
            return row

        def refused(row: dict[str, Any], old: str, new: str) -> None:
            assert REFUSED.format(old=old, new=new) in _refused(session, _moved(row, new))

        # a proposal is discarded; a discarded group goes nowhere
        proposed = stored()
        session.execute(_moved(proposed, "VOIDED"))
        for status in ("PROPOSED", "SUBMITTED", "APPROVED", "APPLIED", "REJECTED"):
            refused(proposed, "VOIDED", status)

        # a group that waits for its approval, an approved and an applied one
        waiting = stored()
        session.execute(_moved(waiting, "SUBMITTED"))
        refused(waiting, "SUBMITTED", "VOIDED")
        session.execute(_moved(waiting, "APPROVED"))
        refused(waiting, "APPROVED", "VOIDED")
        session.execute(_moved(waiting, "APPLIED"))
        refused(waiting, "APPLIED", "VOIDED")
        # ... and a rejected one
        rejected = stored()
        session.execute(_moved(rejected, "SUBMITTED"))
        session.execute(_moved(rejected, "REJECTED"))
        refused(rejected, "REJECTED", "VOIDED")
        session.rollback()
