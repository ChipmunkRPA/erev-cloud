"""Proposal evidence and SM-11 states are guarded even below the command boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, file_object
from sqlalchemy import delete, insert, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    RowContext,
    ai_model_log_row,
    ai_proposal_row,
    file_object_values,
    insert_app_user,
)
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_proposal_evidence_and_states(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with identity_session(request_id="tests-ai-reviewer") as session:
        user = insert_app_user(session)
    now = datetime.now(UTC)
    with tenant_session(DbContext(tenant_id=tenant, user_id=user, entity_scope="*")) as session:
        row = ai_proposal_row(RowContext(tenant, user), session)
        session.execute(insert(ai_proposal).values(**row))
        target = ai_proposal.c.id == row["id"]
        stored = session.execute(select(ai_proposal).where(target)).mappings().one()
        assert (stored["expires_at"] - stored["created_at"]).days == 30
        assert stored["status"] == "proposed"
        changes: dict[str, Any]
        for changes in ({"content": {}}, {"citations": []}, {"ai_model_log_id": new_id()}):
            assert (
                _fails(session, update(ai_proposal).where(target).values(**changes))[0] == "42501"
            )
        assert _fails(session, delete(ai_proposal).where(target))[0] == "42501"
        assert (
            _fails(session, update(ai_proposal).where(target).values(status="accepted"))[0]
            == "23514"
        )
        assert (
            _fails(
                session,
                update(ai_proposal)
                .where(target)
                .values(status="failed", problem={"code": "ERROR"}),
            )[0]
            == "P0001"
        )
        session.execute(
            update(ai_proposal)
            .where(target)
            .values(
                status="accepted",
                accepted_command="contract.create_draft",
                field_decisions=[{"path": "external_id", "decision": "ACCEPT", "value": "EXAMPLE"}],
                accepted_object_type="contract",
                accepted_object_id=new_id(),
                accepted_by=user,
                accepted_at=now,
            )
        )
        accepted = dict(session.execute(select(ai_proposal).where(target)).mappings().one())
        invalid_decisions: list[Any] | dict[str, Any]
        for invalid_decisions in ([], {}):
            assert (
                _fails(
                    session,
                    insert(ai_proposal).values(
                        **(accepted | {"id": new_id(), "field_decisions": invalid_decisions})
                    ),
                )[0]
                == "23514"
            )
        for changes in (
            {"status": "proposed"},
            {"accepted_command": "changed"},
            {"field_decisions": []},
            {"accepted_by": new_id()},
        ):
            assert (
                _fails(session, update(ai_proposal).where(target).values(**changes))[0] == "P0001"
            )
        for status, values in (
            (
                "rejected",
                {"rejected_by": user, "rejected_at": now, "rejection_reason": "Not applicable."},
            ),
            ("expired", {}),
        ):
            candidate = row | {"id": new_id()}
            session.execute(insert(ai_proposal).values(**candidate))
            predicate = ai_proposal.c.id == candidate["id"]
            session.execute(update(ai_proposal).where(predicate).values(status=status, **values))
            assert (
                _fails(session, update(ai_proposal).where(predicate).values(status="proposed"))[0]
                == "P0001"
            )
        session.execute(
            insert(ai_proposal).values(
                **(
                    row
                    | {
                        "id": new_id(),
                        "status": "failed",
                        "problem": {"code": "AI_REFUSAL"},
                    }
                )
            )
        )
        session.execute(insert(ai_proposal).values(**(row | {"id": new_id()})))
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.ai_proposal NO FORCE ROW LEVEL SECURITY")
            assert "EREV-TRN-001" in _owner_failure(
                connection,
                update(ai_proposal).where(ai_proposal.c.status == "proposed").values(content={}),
            )
            assert "EREV-TRN-001" in _owner_failure(
                connection,
                update(ai_proposal)
                .where(ai_proposal.c.status == "proposed")
                .values(citations=[{"ref_type": "record"}]),
            )
        finally:
            transaction.rollback()


def test_proposal_cannot_reference_other_tenant_evidence(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    a = tenant_id_of(tenant_factory(keyring=keyring))
    b = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=b, user_id=None, entity_scope="*")) as session:
        log = ai_model_log_row(RowContext(b, new_id()), session)
        session.execute(insert(ai_model_log).values(**log))
        document = file_object_values(b)
        session.execute(insert(file_object).values(**document))
    with tenant_session(DbContext(tenant_id=a, user_id=None, entity_scope="*")) as session:
        row = ai_proposal_row(RowContext(a, new_id()), session)
        assert (
            _fails(session, insert(ai_proposal).values(**(row | {"ai_model_log_id": log["id"]})))[0]
            == "23503"
        )

        for column in ("file_object_id", "document_text_file_id"):
            assert (
                _fails(session, insert(ai_proposal).values(**(row | {column: document["id"]})))[0]
                == "23503"
            )
