"""Revision 0119's downgrade: refused by name over a tenant's ``NOT_STATED`` item, a round trip
without one (dev-guide DG-MIG-04, DG-MIG-13; 04 T-CLS-07 rev 1.253; the supervisor's ruling of
2026-10-01 21:23, form (2)). PostgreSQL-bound; one walk on the shared test database.

0119 added ``NOT_STATED`` to ``ck_reconciliation_item__item_kind``. Such an item exists only where a
tenant attached a trial balance to a reconciliation one of whose contract balance roles could not
be stated; no provisioning writes one. The kind list of revision 0047 does not admit it, and the
application of the earlier revision cannot read it (the revision's docstring states the 500 that
was measured), so the downgrade does not keep the row behind a ``NOT VALID`` check as 0111's does:

1. over a tenant's ``NOT_STATED`` item the downgrade is refused BY NAME — ``EREV-MIG-0119`` —
   and nothing is changed: the version, both columns, the three checks and the foreign key stand
   as the upgrade made them, the kind check validated, and the item is as it was. An ``EXISTS``
   over the table on the owner connection sees no row of the tenant (FORCE ROW LEVEL SECURITY);
   the refusal comes from the constraint validation, which scans every physical row;
2. a database without such an item — a provisioned tenant, a reconciliation with an item of an
   earlier kind — goes down through the revision: the columns, their check and key and the
   ``NOT_STATED`` check are gone, the seven-literal list is back and validated, and the item is
   kept; the upgrade restores what the revision makes.

Fail-first (the downgrade as written on 2026-09-30, revision 0097 of the lane's branch): it
re-added the seven-literal list validated outside any block and failed with a bare
``check_violation`` — the defect revision 0111 was corrected for.

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
from erev_api.db.tables import reconciliation, reconciliation_item
from sqlalchemy import exc, insert, select, text
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import insert_close_parts, reconciliation_item_values, reconciliation_values

pytestmark = pytest.mark.pg

REVISION = "0119"
KIND_CHECK = "ck_reconciliation_item__item_kind"
MADE = (
    "ck_reconciliation_item__account_role",
    "ck_reconciliation_item__not_stated",
    "fk_reconciliation_item__origin_period",
)
VERSION = text("SELECT version_num FROM erev.alembic_version")
CONSTRAINTS = text(
    "SELECT conname, convalidated, pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conrelid = 'erev.reconciliation_item'::regclass AND conname = ANY(:names) "
    "ORDER BY conname"
)
COLUMNS = text(
    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'erev' "
    "AND table_name = 'reconciliation_item' AND column_name = ANY(:names) ORDER BY column_name"
)
# What a guard written as a query would ask — and cannot see on the owner connection.
BLIND_PREDICATE = text(
    "SELECT EXISTS (SELECT 1 FROM erev.reconciliation_item WHERE item_kind = 'NOT_STATED')"
)


def _revision_before() -> str:
    """The revision 0119 sits on — main's head when it was built or merged (supervisor ruling
    R-68 (e)), read from the script directory so that a re-point does not move this test."""
    revision = ScriptDirectory.from_config(alembic_config()).get_revision(REVISION)
    assert revision is not None and isinstance(revision.down_revision, str)
    return revision.down_revision


def _catalogue(connection: Any) -> tuple[list[str], dict[str, tuple[bool, str]]]:
    """The revision's two columns that exist, and its constraints as (validated, definition)."""
    columns = [
        str(name)
        for (name,) in connection.execute(COLUMNS, {"names": ["account_role", "origin_period_id"]})
    ]
    constraints = {
        str(name): (bool(validated), str(definition))
        for name, validated, definition in connection.execute(
            CONSTRAINTS, {"names": [KIND_CHECK, *MADE]}
        )
    }
    return columns, constraints


def _items(session: Any) -> list[tuple[str, str | None]]:
    """(kind, account) of the tenant's reconciliation items, in kind order."""
    table = reconciliation_item
    return [
        (str(kind), None if code is None else str(code))
        for kind, code in session.execute(
            select(table.c.item_kind, table.c.account_code).order_by(table.c.item_kind)
        )
    ]


def _a_reconciliation(session: Any, tenant_id: UUID) -> UUID:
    parts = insert_close_parts(session, tenant_id)
    row = reconciliation_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
    session.execute(insert(reconciliation).values(**row))
    return UUID(str(row["id"]))


def test_0119_downgrade_is_refused_by_name_over_a_not_stated_item_and_goes_through_without_one(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    before = _revision_before()
    fresh_head()  # a data-free head: the walk below meets only this module's rows
    test_database.app_engine.dispose()
    owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            reconciliation_id = _a_reconciliation(session, tenant_id)
            session.execute(
                insert(reconciliation_item).values(
                    **reconciliation_item_values(
                        tenant_id,
                        reconciliation_id=reconciliation_id,
                        item_kind="NOT_STATED",
                        account_code=None,
                        account_role="UNBILLED_RECEIVABLE",
                        subledger_amount=None,
                    )
                )
            )
            session.commit()
        with owner.connect() as connection:
            made = _catalogue(connection)
            assert made[0] == ["account_role", "origin_period_id"]
            assert sorted(made[1]) == sorted([KIND_CHECK, *MADE])
            assert made[1][KIND_CHECK][0] is True and "'NOT_STATED'" in made[1][KIND_CHECK][1]
            # the owner connection sees no row of the tenant: a guard written as a query is blind
            assert connection.execute(BLIND_PREDICATE).scalar_one() is False

        # 1. refused by name, and the whole revision rolls back
        with pytest.raises(exc.DBAPIError) as refused:
            command.downgrade(alembic_config(), before)
        assert "EREV-MIG-0119" in str(refused.value.orig)
        assert getattr(refused.value.orig, "sqlstate", None) == "P0001"
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == REVISION
            assert _catalogue(connection) == made  # nothing changed in the catalogue
        with tenant_session(context) as session:
            assert _items(session) == [("NOT_STATED", None)]  # and nothing in the rows
    finally:
        fresh_head()  # 2. and a database without such an item
        test_database.app_engine.dispose()
        owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            reconciliation_id = _a_reconciliation(session, tenant_id)
            session.execute(
                insert(reconciliation_item).values(
                    **reconciliation_item_values(tenant_id, reconciliation_id=reconciliation_id)
                )
            )
            session.commit()
        test_database.app_engine.dispose()
        command.downgrade(alembic_config(), before)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            columns, constraints = _catalogue(connection)
            assert columns == [] and sorted(constraints) == [KIND_CHECK]
            validated, definition = constraints[KIND_CHECK]
            assert validated is True and "NOT VALID" not in definition
            assert "'NOT_STATED'" not in definition and "'OTHER'" in definition
        with tenant_session(context) as session:
            assert _items(session) == [("AMOUNT_VARIANCE", "4000")]  # kept through the downgrade
    finally:
        command.upgrade(alembic_config(), "head")
        test_database.app_engine.dispose()
        owner.dispose()
    with owner.connect() as connection:
        assert connection.execute(VERSION).scalar_one() != before
        columns, constraints = _catalogue(connection)
        assert columns == ["account_role", "origin_period_id"]
        assert sorted(constraints) == sorted([KIND_CHECK, *MADE])
        assert constraints[KIND_CHECK][0] is True and "'NOT_STATED'" in constraints[KIND_CHECK][1]
    with tenant_session(context) as session:
        assert _items(session) == [("AMOUNT_VARIANCE", "4000")]  # the item went down and came back
