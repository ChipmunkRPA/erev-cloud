"""Revision 0128 — the trigger a dirty mark carries (item FX-REPUBLISH-DIRTY-1; 04 T-CON-03
``dirty_trigger`` rev 1.297; dev-guide DG-MIG-04, DG-MIG-13): what the column admits, as the
application's role writes it, and the revision's descent over a POPULATED database.
PostgreSQL-bound; one round trip on the shared test database.

1. At head, in a tenant's session (role ``erev_app``): the stamp and its trigger are written
   together in any status of the group; a trigger without a stamp, a trigger that no mark
   carries and a stamp that ends while its trigger stands are each refused by
   ``ck_combination_group__dirty_trigger`` — a trigger is carried by a mark only, and every
   writer that ends a mark ends its trigger in the same statement.
2. The downgrade over a group that carries a mark and its trigger goes through and refuses no
   row: the column, its check and its grant are gone, the group is still dirty — the
   application of the earlier revision reads no trigger from a mark — and the transition
   function is 0126's again. The upgrade back adds the column empty: the group that was dirty
   keeps its stamp and carries no trigger.

The module starts from a data-free head and leaves one (``support.db.fresh_head``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import combination_group
from sqlalchemy import exc, func, insert, select, text, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import combination_group_values

pytestmark = pytest.mark.pg

CHECK = "ck_combination_group__dirty_trigger"
COLUMN = text(
    "SELECT udt_name, is_nullable FROM information_schema.columns WHERE table_schema = 'erev' "
    "AND table_name = 'combination_group' AND column_name = 'dirty_trigger'"
)
GRANTED = text(
    "SELECT count(*) FROM information_schema.column_privileges WHERE table_schema = 'erev' "
    "AND table_name = 'combination_group' AND column_name = 'dirty_trigger' "
    "AND grantee = 'erev_app' AND privilege_type = 'UPDATE'"
)
CHECKS = text("SELECT count(*) FROM pg_constraint WHERE conname = :name")
FUNCTION = text(
    "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'erev' AND p.proname = 'tg_combination_group__transition'"
)
VERSION = text("SELECT version_num FROM erev.alembic_version")
STAMP = text("SELECT dirty_since FROM erev.combination_group WHERE id = :id")


def _revision_before_0128() -> str:
    """The revision 0128 sits on — the head at its merge (supervisor ruling R-68 (e)), read from
    the script directory so that a re-point does not move this test."""
    revision = ScriptDirectory.from_config(alembic_config()).get_revision("0128")
    assert revision is not None and isinstance(revision.down_revision, str)
    return revision.down_revision


def _refused(session: Any, statement: Any) -> tuple[str | None, str | None]:
    """(SQLSTATE, constraint) of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    orig = refused.value.orig
    return getattr(orig, "sqlstate", None), orig.diag.constraint_name


def _row(session: Any, group_id: UUID) -> tuple[bool, str | None]:
    """(dirty, trigger) of the group."""
    stamp, trigger = session.execute(
        select(combination_group.c.dirty_since, combination_group.c.dirty_trigger).where(
            combination_group.c.id == group_id
        )
    ).one()
    return stamp is not None, None if trigger is None else str(getattr(trigger, "value", trigger))


def test_0128_a_trigger_is_carried_by_a_mark_only_and_the_descent_keeps_the_mark(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    before = _revision_before_0128()
    fresh_head()  # a data-free head: the walk below meets only this module's rows
    test_database.app_engine.dispose()
    owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        marked = combination_group_values(tenant_id)
        clean = combination_group_values(tenant_id)
        the_marked = combination_group.c.id == marked["id"]
        the_clean = combination_group.c.id == clean["id"]
        with owner.connect() as connection:
            assert connection.execute(COLUMN).one() == ("computation_trigger", "YES")
            assert connection.execute(GRANTED).scalar_one() == 1
            assert connection.execute(CHECKS, {"name": CHECK}).scalar_one() == 1
            assert "'dirty_trigger'" in connection.execute(FUNCTION).scalar_one()

        # 1. what the column admits, as the application writes it
        with tenant_session(context) as session:
            session.execute(insert(combination_group), [marked, clean])
            assert _row(session, marked["id"]) == (False, None)
            session.execute(
                update(combination_group)
                .where(the_marked)
                .values(dirty_since=func.now(), dirty_trigger="FX_REPUBLISH")
            )
            assert _row(session, marked["id"]) == (True, "FX_REPUBLISH")
            # a trigger without a stamp
            assert _refused(
                session,
                update(combination_group).where(the_clean).values(dirty_trigger="FX_REPUBLISH"),
            ) == ("23514", CHECK)
            # a trigger that no mark carries
            assert _refused(
                session,
                update(combination_group)
                .where(the_clean)
                .values(dirty_since=func.now(), dirty_trigger="POLICY_RERUN"),
            ) == ("23514", CHECK)
            # a stamp that ends while its trigger stands
            assert _refused(
                session, update(combination_group).where(the_marked).values(dirty_since=None)
            ) == ("23514", CHECK)
            # the two end together, and a mark without a trigger is every other mark
            session.execute(
                update(combination_group)
                .where(the_marked)
                .values(dirty_since=None, dirty_trigger=None)
            )
            session.execute(
                update(combination_group).where(the_clean).values(dirty_since=func.now())
            )
            assert _row(session, clean["id"]) == (True, None)
            session.execute(
                update(combination_group)
                .where(the_marked)
                .values(dirty_since=func.now(), dirty_trigger="FX_REPUBLISH")
            )
            session.commit()

        # 2. the descent over the marked group, and the way back
        command.downgrade(alembic_config(), before)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            assert connection.execute(COLUMN).first() is None
            assert connection.execute(GRANTED).scalar_one() == 0
            assert connection.execute(CHECKS, {"name": CHECK}).scalar_one() == 0
            assert "'dirty_trigger'" not in connection.execute(FUNCTION).scalar_one()
        test_database.app_engine.dispose()
        with tenant_session(context) as session:  # the row as the tenant reads it (RLS)
            assert session.execute(STAMP, {"id": marked["id"]}).scalar_one() is not None

        command.upgrade(alembic_config(), "head")
        test_database.app_engine.dispose()
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() != before
            assert connection.execute(COLUMN).one() == ("computation_trigger", "YES")
            assert connection.execute(GRANTED).scalar_one() == 1
            assert connection.execute(CHECKS, {"name": CHECK}).scalar_one() == 1
        with tenant_session(context) as session:
            assert _row(session, marked["id"]) == (True, None)  # dirty as before, no trigger
            assert _row(session, clean["id"]) == (True, None)
    finally:
        fresh_head()
        test_database.app_engine.dispose()
        owner.dispose()
