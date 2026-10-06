"""DB-07 on the partitions (04 §14.1 DB-07 and DB-14 rev 1.182; supervisor rulings R-97 (7) and
R-116 (h); gap G1 of the independent review of revision 0084; REQ-CLS-002; CTL-015).
PostgreSQL-bound.

``tg_subledger_line__period_guard`` is created on the partitioned parent (revision 0040). It
reaches the 180 monthly partitions and the default partition only because PostgreSQL clones a row
trigger of a partitioned table to each partition; until rev 1.182 nothing asserted that — the
grants test named the parent alone and the DB-14 lint read the DB-01 triggers only. A partition
whose copy is missing or disabled admits a line into a closed period. ``journal_line`` is not
partitioned (04 §1.6): its guard is on the one table.

The catalogue is read as ``erev_app``; the two probes insert through the parent, as the product
does, into a period that ends after the last monthly partition.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.lint import catalogue_connection
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import legal_entity, period, period_state, subledger_line, subledger_posting
from sqlalchemy import exc, insert, literal_column, select, text
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    LedgerParts,
    insert_ledger_parts,
    period_state_values,
    period_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

SUBLEDGER_GUARD: Final = "tg_subledger_line__period_guard"
JOURNAL_GUARD: Final = "tg_journal_line__period_guard"
# 04 §1.6 / DG-MIG-10: monthly partitions 2018-01 to 2032-12 and the default partition.
MONTHLY: Final = tuple(
    f"subledger_line_p{year:04d}{month:02d}" for year in range(2018, 2033) for month in range(1, 13)
)
DEFAULT_PARTITION: Final = "subledger_line_pdefault"
# pg_trigger.tgtype: ROW (1), BEFORE (2), INSERT (4).
ROW_BEFORE_INSERT: Final = 7
# A period that follows the probe's January 2026 without a gap (DB-05) and ends after the last
# monthly partition (2032-12): its lines are routed to the default partition.
BEYOND: Final = (date(2026, 2, 1), date(2033, 1, 31))

_GUARDS: Final = text(
    """
    SELECT member.relname, t.tgname, t.tgenabled, t.tgtype, t.tgisinternal,
           t.tgfoid::regprocedure::text AS guard,
           t.tgparentid = parent_guard.oid AS cloned_from_parent
      FROM pg_class root
      JOIN pg_namespace n ON n.oid = root.relnamespace
      JOIN pg_trigger parent_guard ON parent_guard.tgrelid = root.oid
       AND parent_guard.tgname = :guard
      CROSS JOIN LATERAL pg_partition_tree(root.oid::regclass) tree
      JOIN pg_class member ON member.oid = tree.relid
      LEFT JOIN pg_trigger t ON t.tgrelid = member.oid AND t.tgname = :guard
     WHERE n.nspname = 'erev' AND root.relname = :table
     ORDER BY member.relname
    """
)
_TABLE_GUARD: Final = text(
    """
    SELECT c.relkind, c.relispartition, t.tgenabled, t.tgtype, t.tgfoid::regprocedure::text
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      LEFT JOIN pg_trigger t ON t.tgrelid = c.oid AND t.tgname = :guard
     WHERE n.nspname = 'erev' AND c.relname = :table
    """
)


@pytest.mark.control("CTL-015")
def test_db_07_the_subledger_guard_is_on_every_partition_and_the_default(
    test_database: TestDatabase,
) -> None:
    """Every relation of ``subledger_line``'s partition tree — the parent, the 180 monthly
    partitions and the default partition — carries the guard: enabled, a row trigger before
    insert, bound to the guard function, and on a partition the copy PostgreSQL made of the
    parent's trigger."""
    with catalogue_connection(request_id="tests-db-07-partitions") as connection:
        rows = connection.execute(
            _GUARDS, {"table": "subledger_line", "guard": SUBLEDGER_GUARD}
        ).all()
    found = {str(row.relname): row for row in rows}
    assert set(found) == {"subledger_line", DEFAULT_PARTITION, *MONTHLY}
    assert len(MONTHLY) == 180 and len(rows) == 182  # one trigger per relation, none twice
    for name, row in found.items():
        assert row.tgname == SUBLEDGER_GUARD, name
        assert row.tgenabled == "O", name  # fires for the application's sessions
        assert int(row.tgtype) & ROW_BEFORE_INSERT == ROW_BEFORE_INSERT, name
        assert row.guard == f"{SUBLEDGER_GUARD}()", name
        assert row.tgisinternal is False, name
        assert bool(row.cloned_from_parent) is (name != "subledger_line"), name


@pytest.mark.control("CTL-015")
def test_db_07_the_journal_guard_is_on_its_one_table(test_database: TestDatabase) -> None:
    """``journal_line`` is an ordinary table — not a partitioned parent and not a partition — and
    carries its guard enabled."""
    with catalogue_connection(request_id="tests-db-07-journal") as connection:
        (row,) = connection.execute(
            _TABLE_GUARD, {"table": "journal_line", "guard": JOURNAL_GUARD}
        ).all()
    relkind, is_partition, enabled, tgtype, guard = row
    assert (str(relkind), bool(is_partition)) == ("r", False)
    assert (str(enabled), str(guard)) == ("O", f"{JOURNAL_GUARD}()")
    assert int(tgtype) & ROW_BEFORE_INSERT == ROW_BEFORE_INSERT


def _beyond(session: Session, tenant_id: UUID, parts: LedgerParts, *, state: str) -> UUID:
    """The period ``BEYOND`` in ``state`` for the probe's entity; returns the period id."""
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == parts.chain.entity_id)
    ).scalar_one()
    later = period_values(
        tenant_id,
        calendar_id=calendar_id,
        fiscal_year=2026,
        period_no=2,
        start_date=BEYOND[0],
        end_date=BEYOND[1],
    )
    session.execute(insert(period).values(**later))
    session.execute(
        insert(period_state).values(
            **period_state_values(
                tenant_id,
                entity_id=parts.chain.entity_id,
                period_id=later["id"],
                period_end_date=BEYOND[1],
                state=state,
            )
        )
    )
    return UUID(str(later["id"]))


def _line_beyond(session: Session, tenant_id: UUID, parts: LedgerParts, period_id: UUID) -> str:
    """Insert one line of the period ``BEYOND`` through the parent; returns the partition that
    holds it."""
    posting = subledger_posting_values(tenant_id, parts=parts, idempotency_key=f"probe:{new_id()}")
    session.execute(insert(subledger_posting).values(**posting))
    line = subledger_line_values(
        tenant_id,
        posting=posting,
        parts=parts,
        period_id=period_id,
        period_end_date=BEYOND[1],
        effective_date=date(2033, 1, 15),
    )
    return str(
        session.execute(
            insert(subledger_line)
            .values(**line)
            .returning(literal_column("tableoid::regclass::text"))
        ).scalar_one()
    )


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("state", ["closed", "permanently_locked", "future"])
def test_db_07_the_guard_refuses_a_line_routed_to_the_default_partition(
    committed_db: TestDatabase, keyring: KeyRing, state: str
) -> None:
    """A line whose period ends after the last monthly partition is routed to the default partition,
    and the guard decides there as on any partition: a period that is not postable refuses it
    (``EREV-LED-003``)."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        period_id = _beyond(session, tenant_id, parts, state=state)
        session.commit()
    with tenant_session(context) as poster:
        with pytest.raises(exc.DBAPIError) as refused:
            _line_beyond(poster, tenant_id, parts, period_id)
        diag = getattr(refused.value.orig, "diag", None)
        message = str(getattr(diag, "message_primary", "") or "")
        assert getattr(refused.value.orig, "sqlstate", None) == "P0001", message
        assert message.startswith("EREV-LED-003: ") and f"is {state} in book ASC606" in message
        poster.rollback()


@pytest.mark.control("CTL-015")
def test_db_07_a_line_of_an_open_period_lands_in_the_default_partition(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """The control of the refusal above: the same line into an ``open`` period is admitted, and
    the relation that holds it is the default partition — the refusals were the default
    partition's guard, not a routing error."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        period_id = _beyond(session, tenant_id, parts, state="open")
        session.commit()
    with tenant_session(context) as poster:
        held_by = _line_beyond(poster, tenant_id, parts, period_id)
        assert held_by in (DEFAULT_PARTITION, f"erev.{DEFAULT_PARTITION}"), held_by
        poster.rollback()
