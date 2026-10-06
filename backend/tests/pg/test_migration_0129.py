"""Revision 0129 over stored computations, both ways (dev-guide DG-MIG-04, DG-MIG-13; 04 rev 1.302
T-CON-07 ``cutoff_at``; item COMPUTE-BEHIND-CUTOFF-1, register index 285). PostgreSQL-bound; one
round trip on the shared test database.

0129 adds ``contract_computation.cutoff_at`` — the cutoff a computation's bundle admitted by —
and nothing else: no default, no check, no index, no grant, no function.

1. At head the column is the table's last, ``timestamp with time zone``, nullable, without a
   default; the app role stores a computation with it and without it, and reads both.
2. The descent drops the column over stored computations and keeps the rows; a computation of
   the earlier schema is stored beside them.
3. The ascent adds the column over those rows and writes nothing into it: every computation
   stored before it reads NULL — the cutoff of a computation that has been stored is kept
   nowhere else, so none is backfilled and none comes back after a descent.
4. T-CON-07 is IM-A: a stored cutoff is not changed afterwards, as no column of the row is.

The module starts from a data-free head and leaves one (``support.db.fresh_head``): the rows are
append-only.
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
from erev_api.db.tables import contract_computation, engine_release
from sqlalchemy import exc, func, insert, select, text, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import contract_computation_values, engine_release_values, insert_contract_rows

pytestmark = pytest.mark.pg

REVISION = "0129"
COLUMNS = text(
    "SELECT column_name::text, data_type::text, is_nullable::text, column_default "
    "FROM information_schema.columns "
    "WHERE table_schema = 'erev' AND table_name = 'contract_computation' "
    "ORDER BY ordinal_position"
)
VERSION = text("SELECT version_num FROM erev.alembic_version")
CUTOFF = datetime(2026, 10, 3, 3, 4, 50, 897830, tzinfo=UTC)


def _revision_before() -> str:
    """The revision 0129 sits on — the head it found at its merge (supervisor ruling R-68 (e)),
    read from the script directory so that a re-point does not move this test."""
    revision = ScriptDirectory.from_config(alembic_config()).get_revision(REVISION)
    assert revision is not None and isinstance(revision.down_revision, str)
    return revision.down_revision


def _head() -> str:
    """The chain's head: 0129 itself at its merge and a later revision since (the chain is in
    merge order, supervisor ruling R-68 (e)) — read from the script directory, as the revision
    before is, so that the walk stays about 0129's column wherever the head stands."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert isinstance(head, str)
    return head


def _columns(connection: Any) -> list[tuple[str, str, str, str | None]]:
    return [tuple(row) for row in connection.execute(COLUMNS)]


def _cutoffs(session: Any) -> dict[UUID, datetime | None]:
    return {
        UUID(str(row.id)): row.cutoff_at
        for row in session.execute(
            select(contract_computation.c.id, contract_computation.c.cutoff_at)
        )
    }


def test_0129_adds_the_cutoff_over_stored_computations_and_its_descent_keeps_them(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    fresh_head()  # a data-free head: the walk below meets only this module's rows
    test_database.app_engine.dispose()
    owner.dispose()
    try:
        tenant_id = member(keyring, clock).tenant_id
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")

        # 1. at head
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == _head()
            assert _columns(connection)[-1] == (
                "cutoff_at",
                "timestamp with time zone",
                "YES",
                None,
            )
        with tenant_session(context) as session:
            chain = insert_contract_rows(session, tenant_id)
            release = engine_release_values()
            session.execute(insert(engine_release).values(**release))

            def computation(**extra: Any) -> dict[str, Any]:
                return contract_computation_values(
                    tenant_id,
                    combination_group_id=chain.group_id,
                    engine_release_id=release["id"],
                    **extra,
                )

            with_cutoff = computation(cutoff_at=CUTOFF)
            without = computation()
            session.execute(insert(contract_computation).values(**with_cutoff))
            session.execute(insert(contract_computation).values(**without))
            assert _cutoffs(session) == {with_cutoff["id"]: CUTOFF, without["id"]: None}
            session.commit()

        # 2. the descent over the two stored computations
        before = _revision_before()
        command.downgrade(alembic_config(), before)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == before
            assert "cutoff_at" not in [name for name, *_ in _columns(connection)]
        earlier = computation()  # a computation of the earlier schema: no cutoff to write
        with tenant_session(context) as session:
            stored = select(func.count()).select_from(contract_computation)
            assert session.execute(stored).scalar_one() == 2
            session.execute(insert(contract_computation).values(**earlier))
            session.commit()

        # 3. the ascent over the three
        command.upgrade(alembic_config(), "head")
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == _head()
            assert _columns(connection)[-1][0] == "cutoff_at"
        with tenant_session(context) as session:
            assert _cutoffs(session) == {
                with_cutoff["id"]: None,  # dropped with the column; kept nowhere else
                without["id"]: None,
                earlier["id"]: None,
            }
            later = computation(cutoff_at=CUTOFF)
            session.execute(insert(contract_computation).values(**later))
            assert _cutoffs(session)[later["id"]] == CUTOFF

            # 4. append-only: a stored row keeps the cutoff it was stored with, or none
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError):
                session.execute(
                    update(contract_computation)
                    .where(contract_computation.c.id == earlier["id"])
                    .values(cutoff_at=CUTOFF)
                )
            savepoint.rollback()
            assert _cutoffs(session)[earlier["id"]] is None
            session.rollback()
    finally:
        fresh_head()
        test_database.app_engine.dispose()
        owner.dispose()
    with owner.connect() as connection:
        assert _columns(connection)[-1][0] == "cutoff_at"
