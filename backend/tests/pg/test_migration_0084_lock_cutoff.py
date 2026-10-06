"""Revision 0084 over a POPULATED database, and over an unpopulated one (dev-guide DG-MIG-13, the
paragraph of rev 1.96; 01 D-99 (3); 04 T-CLS-04 rev 1.113; supervisor rulings R-40 (b) and (c) of
2026-09-30). PostgreSQL-bound; one round trip on the shared test database.

0084 replaces the two DB-07 guard bodies — a change every database must receive by upgrade — and
adds ``period_lock.cutoff_known_at`` with ``ck_period_lock__cutoff_known_at``. A ``LOCK`` row
written before it has no cutoff and none is synthesized, so the check is added ``NOT VALID`` and
validated in the same revision:

1. a database that holds an earlier ``LOCK`` row still upgrades — the guards read the state row
   ``FOR SHARE`` afterwards — the check stays ``NOT VALID`` and the earlier row keeps NULL; the
   check is enforced for every new row all the same (a ``LOCK`` without a cutoff and another kind
   with one are refused, a ``LOCK`` with its cutoff is accepted);
2. a database without such a row (every database created at head) ends with the check validated.

The module starts from a data-free head and leaves one (``support.db.fresh_head``): the earlier
row is append-only, and the DG-MIG-05 round trip and the catalogue pins expect the validated check.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import period_lock
from sqlalchemy import exc, insert, select, text
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import insert_close_parts, period_lock_values

pytestmark = pytest.mark.pg

CHECK = "ck_period_lock__cutoff_known_at"
VALIDATED = text("SELECT convalidated FROM pg_constraint WHERE conname = :name")
GUARD_SOURCES = text(
    "SELECT proname, prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'erev' "
    "AND proname IN ('tg_subledger_line__period_guard', 'tg_journal_line__period_guard')"
)
COLUMN = text(
    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'erev' "
    "AND table_name = 'period_lock' AND column_name = 'cutoff_known_at'"
)
VERSION = text("SELECT version_num FROM erev.alembic_version")
CUTOFF = datetime(2026, 9, 12, 12, 0, 3, tzinfo=UTC)


def _revision_before_0084() -> str:
    """The revision 0084 sits on — main's head at its merge (supervisor ruling R-68 (e): a
    revision keeps its number and is re-pointed to the head it finds), read from the script
    directory so that a re-point does not move this test."""
    revision = ScriptDirectory.from_config(alembic_config()).get_revision("0084")
    assert revision is not None and isinstance(revision.down_revision, str)
    return revision.down_revision


def _share_locked(connection: Any) -> dict[str, bool]:
    return {
        str(name): "FOR SHARE" in str(source) for name, source in connection.execute(GUARD_SOURCES)
    }


def _refused(session: Any, row: dict[str, Any]) -> tuple[str | None, str]:
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(insert(period_lock).values(**row))
    savepoint.rollback()
    orig = refused.value.orig
    return getattr(orig, "sqlstate", None), str(orig.diag.constraint_name)


def test_0084_applies_over_earlier_lock_rows_and_validates_its_check_without_them(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    fresh_head()  # a data-free head: the walk below meets only this module's rows
    test_database.app_engine.dispose()
    owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            parts = insert_close_parts(session, tenant_id, state="closing")
            session.commit()
        before = _revision_before_0084()
        command.downgrade(alembic_config(), before)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            assert connection.execute(COLUMN).scalar_one() == 0
            assert _share_locked(connection) == {
                "tg_subledger_line__period_guard": False,
                "tg_journal_line__period_guard": False,
            }
        # a LOCK row of the earlier schema: no cutoff column exists to write
        earlier = period_lock_values(tenant_id, parts=parts)
        del earlier["cutoff_known_at"]
        with tenant_session(context) as session:
            session.execute(insert(period_lock).values(**earlier))
            session.commit()

        command.upgrade(alembic_config(), "head")  # 1. the populated database still upgrades
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() != before
            assert _share_locked(connection) == {
                "tg_subledger_line__period_guard": True,
                "tg_journal_line__period_guard": True,
            }
            assert connection.execute(VALIDATED, {"name": CHECK}).scalar_one() is False
        with tenant_session(context) as session:
            kept = session.execute(
                select(period_lock.c.cutoff_known_at).where(period_lock.c.id == earlier["id"])
            ).scalar_one()
            assert kept is None  # nothing backfilled, no instant synthesized
            # the check is enforced for every new row although it is not validated
            without = period_lock_values(tenant_id, parts=parts, cutoff_known_at=None)
            assert _refused(session, without) == ("23514", CHECK)
            reopen = period_lock_values(
                tenant_id,
                parts=parts,
                kind="REOPEN",
                reason_code="ERROR_CORRECTION",
                cutoff_known_at=CUTOFF,
            )
            assert _refused(session, reopen) == ("23514", CHECK)
            accepted = period_lock_values(tenant_id, parts=parts, cutoff_known_at=CUTOFF)
            session.execute(insert(period_lock).values(**accepted))
            stored = session.execute(
                select(period_lock.c.cutoff_known_at).where(period_lock.c.id == accepted["id"])
            ).scalar_one()
            assert stored == CUTOFF
            assert UUID(str(accepted["id"])) != UUID(str(earlier["id"]))
            session.rollback()
    finally:
        fresh_head()  # 2. and a database without an earlier LOCK row: the check is validated
        test_database.app_engine.dispose()
        owner.dispose()
    with owner.connect() as connection:
        assert connection.execute(VALIDATED, {"name": CHECK}).scalar_one() is True
        assert connection.execute(COLUMN).scalar_one() == 1
        assert _share_locked(connection) == {
            "tg_subledger_line__period_guard": True,
            "tg_journal_line__period_guard": True,
        }
