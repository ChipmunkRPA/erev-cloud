"""Revision 0111's downgrade over a POPULATED database, and over an unpopulated one (dev-guide
DG-MIG-04 and DG-MIG-13; 04 T-CLS-02 rev 1.172; the revision corrected in place — PRODUCT DEFECT,
the supervisor's message of 2026-10-01 13:32). PostgreSQL-bound; one round trip on the shared test
database.

0111 added ``CLOSE_RUN_COMPLETED`` to ``ck_close_checklist_template__gate_check_code``.
Provisioning seeds that gate's template row for every tenant, so every populated database holds a
row the gate list of revision 0047 does not admit. The downgrade restores that list ``NOT VALID``
and validates it in the same transaction:

1. over a provisioned tenant the downgrade goes through — the check stays ``NOT VALID``, the
   tenant's template row is kept, and the check is enforced for every new row all the same (a new
   template that carries the literal is refused, a tenant task is accepted); the upgrade back
   re-adds the fourteen-literal check, validated, over the row that was kept;
2. a database without such a row (the DG-MIG-05 round trip) ends the downgrade with the check
   validated.

Fail-first (measured on the revision before the correction): the downgrade re-added the list
validated and failed on the tenant's row with a bare ``check_violation`` — "check constraint
"ck_close_checklist_template__gate_check_code" of relation "close_checklist_template" is violated
by some row" — neither removing what the upgrade made possible nor refusing by name, and every
walk down through 0111 over a populated database stopped there
(``test_migration_0067_downgrade_guard.py``, ``test_migration_0084_lock_cutoff.py``).

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
from erev_api.db.tables import close_checklist_template
from sqlalchemy import exc, func, insert, select, text
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import close_checklist_template_values

pytestmark = pytest.mark.pg

CHECK = "ck_close_checklist_template__gate_check_code"
GATE = "CLOSE_RUN_COMPLETED"
VALIDATED = text("SELECT convalidated FROM pg_constraint WHERE conname = :name")
DEFINITION = text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name")
MARK_COLUMN = text(
    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'erev' "
    "AND table_name = 'combination_group' AND column_name = 'period_ends_open'"
)
VERSION = text("SELECT version_num FROM erev.alembic_version")


def _revision_before_0111() -> str:
    """The revision 0111 sits on — main's head at its merge (supervisor ruling R-68 (e)), read
    from the script directory so that a re-point does not move this test."""
    revision = ScriptDirectory.from_config(alembic_config()).get_revision("0111")
    assert revision is not None and isinstance(revision.down_revision, str)
    return revision.down_revision


def _check(connection: Any) -> tuple[bool, str]:
    """(validated, definition) of the gate list's check."""
    validated = connection.execute(VALIDATED, {"name": CHECK}).scalar_one()
    return bool(validated), str(connection.execute(DEFINITION, {"name": CHECK}).scalar_one())


def _gate_rows(session: Any) -> int:
    """The template rows of the gate the revision added, as the tenant sees them."""
    table = close_checklist_template
    return int(
        session.execute(
            select(func.count()).select_from(table).where(table.c.gate_check_code == GATE)
        ).scalar_one()
    )


def _refused(session: Any, row: dict[str, Any]) -> tuple[str | None, str]:
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(insert(close_checklist_template).values(**row))
    savepoint.rollback()
    orig = refused.value.orig
    return getattr(orig, "sqlstate", None), str(orig.diag.constraint_name)


def test_0111_downgrade_keeps_a_tenants_gate_row_and_validates_its_check_without_one(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    before = _revision_before_0111()
    fresh_head()  # a data-free head: the walk below meets only this module's rows
    test_database.app_engine.dispose()
    owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            assert _gate_rows(session) == 1  # provisioning seeded the fourteenth gate
        with owner.connect() as connection:
            validated, definition = _check(connection)
            assert validated is True and f"'{GATE}'" in definition

        command.downgrade(alembic_config(), before)  # 1. over the provisioned tenant
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            assert connection.execute(MARK_COLUMN).scalar_one() == 0
            validated, definition = _check(connection)
            assert validated is False and definition.endswith("NOT VALID")
            assert f"'{GATE}'" not in definition and "'CONTROLLER_CERTIFIED'" in definition
        with tenant_session(context) as session:
            assert _gate_rows(session) == 1  # nothing deleted, nothing rewritten
            # the list of 0047 is enforced for every new row although it is not validated
            late = close_checklist_template_values(
                tenant_id, code="LATE-GATE", gate_kind="AUTOMATIC", gate_check_code=GATE
            )
            assert _refused(session, late) == ("23514", CHECK)
            task = close_checklist_template_values(tenant_id, code="CUTOFF-MEMO")
            session.execute(insert(close_checklist_template).values(**task))
            stored = session.execute(
                select(close_checklist_template.c.id).where(
                    close_checklist_template.c.code == "CUTOFF-MEMO"
                )
            ).scalar_one()
            assert UUID(str(stored)) == UUID(str(task["id"]))
            session.rollback()

        # the re-upgrade through 0111 over the NOT VALID check: the fourteen-literal list is
        # added validated, over the row that was kept
        command.upgrade(alembic_config(), "head")
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() != before
            assert connection.execute(MARK_COLUMN).scalar_one() == 1
            validated, definition = _check(connection)
            assert validated is True and f"'{GATE}'" in definition
        with tenant_session(context) as session:
            assert _gate_rows(session) == 1
    finally:
        fresh_head()  # 2. and a database without such a row
        test_database.app_engine.dispose()
        owner.dispose()
    try:
        command.downgrade(alembic_config(), before)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            validated, definition = _check(connection)
            assert validated is True and "NOT VALID" not in definition
            assert f"'{GATE}'" not in definition
    finally:
        command.upgrade(alembic_config(), "head")
    with owner.connect() as connection:
        validated, definition = _check(connection)
        assert validated is True and f"'{GATE}'" in definition
