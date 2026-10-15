"""AI call evidence is tenant scoped, append-only and has validated counters."""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_model_log
from sqlalchemy import delete, insert, select, text, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, ai_model_log_row
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_ai_model_log_constraints(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant, user_id=None, entity_scope="*")) as session:
        row = ai_model_log_row(RowContext(tenant, new_id()), session)
        for changes in (
            {"provider": "other"},
            {"outcome": "UNKNOWN"},
            {"input_tokens": -1},
            {"output_tokens": -1},
            {"latency_ms": -1},
            {"input_sha256": "not-a-digest"},
            {"response_sha256": "not-a-digest"},
        ):
            assert _fails(session, insert(ai_model_log).values(**(row | changes)))[0] == "23514"
        for outcome in ("SUCCESS", "ERROR", "TIMEOUT", "BUDGET_EXCEEDED", "DISABLED"):
            values = row | {"id": new_id(), "outcome": outcome}
            if outcome != "SUCCESS":
                values |= {"response_sha256": None, "input_tokens": 0, "output_tokens": 0}
            session.execute(insert(ai_model_log).values(**values))
        rows = session.execute(select(ai_model_log)).mappings().all()
        assert len(rows) == 5
        assert {entry["outcome"] for entry in rows} == {
            "SUCCESS",
            "ERROR",
            "TIMEOUT",
            "BUDGET_EXCEEDED",
            "DISABLED",
        }
        assert _fails(session, update(ai_model_log).values(input_tokens=999))[0] == "42501"
        assert _fails(session, delete(ai_model_log))[0] == "42501"

    # Even the owner cannot rewrite retained evidence without a governed data fix.
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.ai_model_log NO FORCE ROW LEVEL SECURITY")
            for statement in (
                update(ai_model_log).values(input_tokens=999),
                delete(ai_model_log),
                text("TRUNCATE erev.ai_model_log"),
            ):
                assert "EREV-IMM-001" in _owner_failure(connection, statement)
        finally:
            transaction.rollback()
