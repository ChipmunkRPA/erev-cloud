"""0067's downgrade guard over a POPULATED database (D-98 128 AMENDMENT 1; dev-guide 1.60
DG-MIG-13; integrated batch #6 ci return; Codex 1631 §2 qualifications) — WRITTEN, NOT RUN on the
lane (no lane database); the next integrated batch measures it.

The walk starts from a data-free head (``fresh_head``; FLMG-WALK-RESET-1) and the database is
then populated with what the guard must see. A descent from head meets every later revision's
downgrade first, and a row that carries an enum label a later revision added makes that revision
refuse — DG-MIG-06, by design — before the walk reaches 0067: since revision 0092 an MFA enrolment
writes a ``security_event`` of a kind that revision added (``MFA_ENROLMENT_STARTED``), and the rows
earlier tests of the session committed hold such events (the whole-suite run on main 91056811
stopped there with ``invalid input value for enum security_event_kind``).

Both branches, in one round trip:

1. fail-first of the mechanism: with an OPENING_BALANCES batch WITHOUT a cutover present, the
   ORIGINAL predicate (``SELECT EXISTS (… WHERE mode = 'OPENING_BALANCES' AND cutover_date IS
   NULL)``) run on the OWNER connection without a tenant context is BLIND (False) while the tenant
   session counts the row — the reason the designed refusal surfaced as a raw CheckViolation;
2. the corrected downgrade to 0066 is REFUSED BY NAME (``EREV-MIG-0067``) and the whole revision
   transaction rolls back: the capture tables still exist, the 1.60 CHECK is still in force, the
   version table still says 0067 — no date synthesized, no row deleted, RLS untouched;
3. compatible data (the row given its cutover through the app role, as ``/import`` does) downgrades
   to 0066 with the ORIGINAL effect (the 0056 CHECK in force, the capture tables gone) and upgrades
   back to head.

The DG-MIG-05 round trip (``test_migrations.py::test_upgrade_downgrade_upgrade``) passes only on an
UNPOPULATED database for the same reason; this module leaves the database at head with the row
compatible.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from alembic import command
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import file_object, migration_batch
from erev_api.enums import FilePurpose
from sqlalchemy import exc, insert, select, text, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.principals import member
from support.rows import file_object_values, migration_batch_values

pytestmark = pytest.mark.pg

BLIND_PREDICATE_0067_ORIGINAL = (
    "SELECT EXISTS (SELECT 1 FROM erev.migration_batch "
    "WHERE mode = 'OPENING_BALANCES' AND cutover_date IS NULL)"
)
CHECK_DEFINITION = text(
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conname = 'ck_migration_batch__cutover'"
)
CAPTURE_TABLE = text("SELECT to_regclass('erev.migration_population_version') IS NOT NULL")
VERSION = text("SELECT version_num FROM erev.alembic_version")


def test_0067_downgrade_refuses_by_name_over_a_populated_database_and_downgrades_compatible_data(
    test_database: TestDatabase, keyring, clock
) -> None:
    # The descent must not meet rows earlier tests committed (DG-MIG-06): a data-free head
    # first, then the rows the guard must see. The pooled connections belong to the schema that
    # was dropped (their statements name its type ids), so they go too.
    fresh_head()
    test_database.app_engine.dispose()
    test_database.owner_engine.dispose()
    someone = member(keyring, clock)
    tenant_id = someone.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**file_row))
        batch = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], status="UPLOADED", cutover_date=None
        )
        session.execute(insert(migration_batch).values(**batch))
        session.commit()
    owner = test_database.owner_engine
    try:
        # 1. the original predicate is blind on the owner connection; the tenant session sees
        #    the row
        with owner.connect() as connection:
            assert connection.execute(text(BLIND_PREDICATE_0067_ORIGINAL)).scalar_one() is False
        with tenant_session(context) as session:
            found = (
                session.execute(
                    select(migration_batch.c.id).where(
                        migration_batch.c.mode == "OPENING_BALANCES",
                        migration_batch.c.cutover_date.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            assert UUID(str(batch["id"])) in {UUID(str(value)) for value in found}
        # 2. the corrected downgrade refuses BY NAME and the whole revision rolls back
        with pytest.raises(exc.DBAPIError) as refused:
            command.downgrade(alembic_config(), "0066")
        assert "EREV-MIG-0067" in str(refused.value.orig)
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == "0067"
            assert connection.execute(CAPTURE_TABLE).scalar_one() is True
            assert "mode = 'REPLAY'" in str(connection.execute(CHECK_DEFINITION).scalar_one())
        with tenant_session(context) as session:  # the row is untouched: no synthesized date
            assert (
                session.execute(
                    select(migration_batch.c.cutover_date).where(
                        migration_batch.c.id == batch["id"]
                    )
                ).scalar_one()
                is None
            )
        # 3. compatible data downgrades with the original effect and upgrades back to head
        with tenant_session(context) as session:
            session.execute(
                update(migration_batch)
                .where(migration_batch.c.id == batch["id"])
                .values(
                    cutover_date=date(2023, 1, 31),
                    row_version=migration_batch.c.row_version + 1,
                )
            )
            session.commit()
        command.downgrade(alembic_config(), "0066")
        with owner.connect() as connection:
            assert connection.execute(VERSION).scalar_one() == "0066"
            assert connection.execute(CAPTURE_TABLE).scalar_one() is False
            assert "cutover_date IS NOT NULL" in str(
                connection.execute(CHECK_DEFINITION).scalar_one()
            )
    finally:
        command.upgrade(alembic_config(), "head")
    with owner.connect() as connection:
        assert connection.execute(VERSION).scalar_one() != "0066"
        assert connection.execute(CAPTURE_TABLE).scalar_one() is True
