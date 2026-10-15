"""Completed proposal job bindings are tenant-bound, unique and immutable."""

from __future__ import annotations

import pytest
from alembic import command
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_proposal, job
from sqlalchemy import exc, insert, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, ai_proposal_row, job_row
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_job_binding_constraints_and_downgrade_guard(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    fresh_head()
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    other = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(other, None, "*")) as session:
        foreign_job = job_row(RowContext(other, new_id()), session)
        session.execute(insert(job).values(**foreign_job))
    with tenant_session(DbContext(tenant, None, "*")) as session:
        ctx = RowContext(tenant, new_id())
        own_job = job_row(ctx, session)
        session.execute(insert(job).values(**own_job))
        row = ai_proposal_row(ctx, session) | {
            "job_id": own_job["id"],
            "job_source_sha256": "a" * 64,
        }
        session.execute(insert(ai_proposal).values(**row))
        assert _fails(session, insert(ai_proposal).values(**(row | {"id": new_id()})))[0] == "23505"
        for change in ({"job_id": None}, {"job_source_sha256": None}, {"job_source_sha256": "bad"}):
            assert (
                _fails(session, insert(ai_proposal).values(**(row | change | {"id": new_id()})))[0]
                == "23514"
            )
        assert (
            _fails(
                session,
                insert(ai_proposal).values(**(row | {"id": new_id(), "job_id": foreign_job["id"]})),
            )[0]
            == "23503"
        )
        assert (
            _fails(
                session,
                update(ai_proposal)
                .where(ai_proposal.c.id == row["id"])
                .values(job_id=None, job_source_sha256=None),
            )[0]
            == "42501"
        )
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.ai_proposal NO FORCE ROW LEVEL SECURITY")
            assert "EREV-TRN-001" in _owner_failure(
                connection,
                update(ai_proposal)
                .where(ai_proposal.c.id == row["id"])
                .values(job_id=None, job_source_sha256=None),
            )
        finally:
            transaction.rollback()
    with pytest.raises(exc.DBAPIError) as error:
        command.downgrade(alembic_config(), "0148")
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    with committed_db.owner_engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT version_num FROM erev.alembic_version").scalar_one()
            == "0149"
        )
    command.upgrade(alembic_config(), "head")
