"""Call-start evidence survives missing outcomes and cannot be rewritten or dropped."""

from __future__ import annotations

import pytest
from alembic import command
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_call_intent, ai_model_log
from sqlalchemy import delete, exc, insert, select, text, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, ai_call_intent_row, ai_model_log_row
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_intent_constraints_and_retained_unknown_outcome(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    fresh_head()
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    other = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(other, None, "*")) as session:
        foreign = ai_call_intent_row(RowContext(other, new_id()), session)
        session.execute(insert(ai_call_intent).values(**foreign))
    with tenant_session(DbContext(tenant, None, "*")) as session:
        ctx = RowContext(tenant, new_id())
        row = ai_call_intent_row(ctx, session)
        for change in (
            {"attempt_no": 0},
            {"attempt_no": 4},
            {"provider": "unknown"},
            {"input_sha256": "bad"},
            {"source_sha256": "bad"},
            {"created_by_kind": "SYSTEM"},
            {"created_by": None},
        ):
            assert _fails(session, insert(ai_call_intent).values(**(row | change)))[0] == "23514"
        assert (
            _fails(session, insert(ai_call_intent).values(**(row | {"job_id": foreign["job_id"]})))[
                0
            ]
            == "23503"
        )
        session.execute(insert(ai_call_intent).values(**row))
        assert (
            _fails(session, insert(ai_call_intent).values(**(row | {"id": new_id()})))[0] == "23505"
        )
    # A committed start without an outcome remains discoverable after a worker disappears.
    with tenant_session(DbContext(tenant, None, "*")) as session:
        unresolved = (
            select(ai_call_intent.c.id)
            .outerjoin(
                ai_model_log,
                (ai_model_log.c.tenant_id == ai_call_intent.c.tenant_id)
                & (ai_model_log.c.intent_id == ai_call_intent.c.id),
            )
            .where(ai_model_log.c.id.is_(None))
        )
        assert session.scalars(unresolved).all() == [row["id"]]
        log = ai_model_log_row(ctx, session) | {"intent_id": foreign["id"]}
        assert _fails(session, insert(ai_model_log).values(**log))[0] == "23503"
        log["intent_id"] = row["id"]
        session.execute(insert(ai_model_log).values(**log))
        assert (
            _fails(session, insert(ai_model_log).values(**(log | {"id": new_id()})))[0] == "23505"
        )
        assert session.scalars(unresolved).all() == []
        for statement in (update(ai_call_intent).values(attempt_no=2), delete(ai_call_intent)):
            assert _fails(session, statement)[0] == "42501"
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "ALTER TABLE erev.ai_call_intent NO FORCE ROW LEVEL SECURITY"
            )
            for owner_statement in (
                update(ai_call_intent).values(attempt_no=2),
                delete(ai_call_intent),
                text("TRUNCATE erev.ai_call_intent CASCADE"),
            ):
                assert "EREV-IMM-001" in _owner_failure(connection, owner_statement)
        finally:
            transaction.rollback()
    with pytest.raises(exc.DBAPIError) as error:
        command.downgrade(alembic_config(), "0149")
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    with committed_db.owner_engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT version_num FROM erev.alembic_version").scalar_one()
            == "0150"
        )
