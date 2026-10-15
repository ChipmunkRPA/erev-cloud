"""AI explanation reads use intersected human scopes and PostgreSQL read-only mode."""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import fiscal_calendar, job, legal_entity, role_assignment
from erev_api.domain.ai.access import AIAccessRefused, authorize_job
from erev_api.domain.ai.retrieval import retrieve_narrative
from erev_api.enums import JobKind
from erev_api.explain import service
from erev_api.jobs.context import JobAttempt, JobContext, JobRuntime
from sqlalchemy import insert, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.principals import member
from support.rows import (
    fiscal_calendar_values,
    insert_custom_role,
    insert_role_assignment,
    legal_entity_values,
)
from tests.unit.ai.test_narratives import TRACE, explanation

pytestmark = pytest.mark.pg


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> tuple[JobContext, UUID, UUID, UUID]:
    actor = member(keyring, clock)
    with tenant_session(DbContext(actor.tenant_id, actor.user_id, "*")) as session:
        calendar = fiscal_calendar_values(actor.tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        entities = [
            legal_entity_values(actor.tenant_id, calendar_id=calendar["id"]) for _ in range(2)
        ]
        session.execute(insert(legal_entity), entities)
        first, second = (UUID(str(row["id"])) for row in entities)
        insert_custom_role(
            session, tenant_id=actor.tenant_id, code="only_ai", permissions=["ai.use"]
        )
        insert_role_assignment(
            session,
            tenant_id=actor.tenant_id,
            membership_id=actor.membership_id,
            role_code="only_ai",
            entity_ids=[first],
        )
        insert_custom_role(
            session, tenant_id=actor.tenant_id, code="only_read", permissions=["contract.read"]
        )
        read_assignment = insert_role_assignment(
            session,
            tenant_id=actor.tenant_id,
            membership_id=actor.membership_id,
            role_code="only_read",
            entity_ids=[first, second],
        )
        job_id = new_id()
        session.execute(
            insert(job).values(
                tenant_id=actor.tenant_id,
                id=job_id,
                kind="AI_TASK",
                queue="ai",
                state="RUNNING",
                params={},
                created_by=actor.user_id,
                created_by_kind="USER",
                updated_by=actor.user_id,
                updated_by_kind="USER",
            )
        )
    context = JobContext(
        job_id=job_id,
        tenant_id=actor.tenant_id,
        kind=JobKind.AI_TASK,
        principal=system_principal(actor.tenant_id, on_behalf_of_id=actor.user_id),
        runtime=JobRuntime(
            clock=clock, keyring=None, files=None, attempt=JobAttempt(job_id, actor.tenant_id, None)
        ),
    )
    return context, first, second, read_assignment


def test_user_scope_and_read_only_database_enforced(
    world: tuple[JobContext, UUID, UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    context, first, second, _ = world

    def snapshot(session: Session, **kwargs: object) -> tuple[UUID, service.Explanation]:
        assert session.scalar(text("SELECT current_setting('transaction_read_only')")) == "on"
        scope = str(session.scalar(text("SELECT current_setting('app.entity_scope')")))
        assert str(first) in scope and str(second) not in scope
        assert session.scalar(text("SELECT current_setting('app.user_id')")) == str(
            context.principal.on_behalf_of_id
        )
        with pytest.raises(DBAPIError) as error, session.begin_nested():
            session.execute(
                update(job).where(job.c.id == context.job_id).values(params={"forbidden": True})
            )
        assert getattr(error.value.orig, "sqlstate", None) == "25006"
        return TRACE, explanation()

    monkeypatch.setattr(service, "explanation_snapshot", snapshot)
    result = retrieve_narrative(
        context,
        object_type="schedule_line",
        object_id=new_id(),
        measure="amount",
        model="fixture-model",
        max_tokens=1000,
    )
    assert result.principal.entity_scope == (first,)
    assert result.prepared.trace_id == TRACE
    assert result.prepared.minor_unit == 2


def test_revoked_read_permission_refused_before_trace(
    world: tuple[JobContext, UUID, UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _, _, assignment = world
    with tenant_session(context.principal.db_context) as session:
        session.execute(
            update(role_assignment)
            .where(role_assignment.c.id == assignment)
            .values(revoked_at=context.clock.now(), revoked_by_kind="SYSTEM")
        )

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Trace read without current contract.read permission")

    monkeypatch.setattr(service, "explanation_snapshot", forbidden)
    with pytest.raises(AIAccessRefused, match="AI_READ_PERMISSION_DENIED"):
        retrieve_narrative(
            context,
            object_type="schedule_line",
            object_id=new_id(),
            measure="amount",
            model="fixture-model",
            max_tokens=1000,
        )


def test_disjoint_ai_and_read_scopes_refuse(world: tuple[JobContext, UUID, UUID, UUID]) -> None:
    context, _, second, assignment = world
    with context.read_session() as session:
        principal = authorize_job(context, session)
    assert principal.membership_id is not None
    with tenant_session(context.principal.db_context) as session:
        session.execute(
            update(role_assignment)
            .where(role_assignment.c.id == assignment)
            .values(revoked_at=context.clock.now(), revoked_by_kind="SYSTEM")
        )
        insert_role_assignment(
            session,
            tenant_id=context.tenant_id,
            membership_id=principal.membership_id,
            role_code="only_read",
            entity_ids=[second],
        )
    with pytest.raises(AIAccessRefused, match="AI_READ_PERMISSION_DENIED"):
        retrieve_narrative(
            context,
            object_type="schedule_line",
            object_id=new_id(),
            measure="amount",
            model="fixture-model",
            max_tokens=1000,
        )
