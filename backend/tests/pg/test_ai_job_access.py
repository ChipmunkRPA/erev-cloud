"""AI jobs reload human grants instead of inheriting SYSTEM's tenant-wide scope."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    app_user,
    fiscal_calendar,
    job,
    legal_entity,
    role_assignment,
    tenant,
    tenant_membership,
)
from erev_api.domain.ai.access import AIAccessRefused, authorize_job, job_requester
from erev_api.domain.ai.log_export import capture_access, require_access
from erev_api.enums import JobKind, PrincipalKind, TenantKind
from erev_api.jobs.context import JobAttempt, JobContext, JobLost, JobRuntime
from erev_api.problems import Problem
from sqlalchemy import insert, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.principals import member
from support.rows import (
    fiscal_calendar_values,
    insert_custom_role,
    insert_role_assignment,
    legal_entity_values,
)

pytestmark = pytest.mark.pg


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, request: pytest.FixtureRequest
) -> Iterator[tuple[Session, JobContext, UUID, UUID, UUID]]:
    kind = getattr(request, "param", JobKind.AI_TASK)
    actor = member(keyring, clock)
    with tenant_session(DbContext(actor.tenant_id, actor.user_id, "*")) as session:
        calendar = fiscal_calendar_values(actor.tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        entities = [
            legal_entity_values(actor.tenant_id, calendar_id=calendar["id"]) for _ in range(2)
        ]
        session.execute(insert(legal_entity), entities)
        first, second = (UUID(str(row["id"])) for row in entities)
        assignment = insert_role_assignment(
            session,
            tenant_id=actor.tenant_id,
            membership_id=actor.membership_id,
            role_code="viewer",
            entity_ids=[first],
        )
        insert_custom_role(
            session, tenant_id=actor.tenant_id, code="other_read", permissions=["contract.read"]
        )
        insert_role_assignment(
            session,
            tenant_id=actor.tenant_id,
            membership_id=actor.membership_id,
            role_code="other_read",
            entity_ids=[second],
        )
        job_id = new_id()
        session.execute(
            insert(job).values(
                tenant_id=actor.tenant_id,
                id=job_id,
                kind=kind.value,
                queue="ai",
                state="RUNNING",
                params={},
                created_by=actor.user_id,
                created_by_kind="USER",
                updated_by=actor.user_id,
                updated_by_kind="USER",
            )
        )
        runtime = JobRuntime(
            clock=clock, keyring=None, files=None, attempt=JobAttempt(job_id, actor.tenant_id, None)
        )
        context = JobContext(
            job_id=job_id,
            tenant_id=actor.tenant_id,
            kind=kind,
            principal=system_principal(actor.tenant_id, on_behalf_of_id=actor.user_id),
            runtime=runtime,
        )
        yield session, context, first, second, assignment


def test_ai_permission_scope_replaces_system_and_other_role_union(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, first, second, _ = world
    principal = authorize_job(context, session, entity_ids=[first])
    assert principal.kind is PrincipalKind.USER
    assert principal.id == context.principal.on_behalf_of_id
    assert principal.entity_scope == (first,)
    assert principal.permission_scopes["contract.read"] == frozenset({first, second})
    assert principal.session_id is None and principal.mfa_verified_at is None
    with pytest.raises(AIAccessRefused, match="AI_PERMISSION_DENIED"):
        authorize_job(context, session, entity_ids=[second])


def test_revoked_role_is_rechecked(world: tuple[Session, JobContext, UUID, UUID, UUID]) -> None:
    session, context, first, _, assignment = world
    authorize_job(context, session, entity_ids=[first])
    session.execute(
        update(role_assignment)
        .where(role_assignment.c.id == assignment)
        .values(revoked_at=context.clock.now(), revoked_by_kind="SYSTEM")
    )
    with pytest.raises(AIAccessRefused, match="AI_PERMISSION_DENIED"):
        authorize_job(context, session)


def test_inactive_membership_is_rechecked(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, _, _, _ = world
    principal = authorize_job(context, session)
    session.execute(
        update(tenant_membership)
        .where(tenant_membership.c.id == principal.membership_id)
        .values(status="SUSPENDED", updated_by_kind="SYSTEM")
    )
    with pytest.raises(AIAccessRefused, match="AI_INITIATOR_INACTIVE"):
        authorize_job(context, session)


def test_finished_attempt_cannot_authorize(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, _, _, _ = world
    session.execute(
        update(job)
        .where(job.c.id == context.job_id)
        .values(state="SUCCEEDED", updated_by_kind="SYSTEM")
    )
    with pytest.raises(JobLost):
        authorize_job(context, session)


def test_context_and_creator_identity_cannot_be_substituted(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, _, _, _ = world
    context.principal = replace(context.principal, on_behalf_of_id=new_id())
    with pytest.raises(AIAccessRefused, match="AI_HUMAN_INITIATOR_REQUIRED"):
        authorize_job(context, session)
    context.kind = JobKind.REPORT_RUN
    with pytest.raises(AIAccessRefused, match="AI_JOB_CONTEXT_REQUIRED"):
        authorize_job(context, session)


@pytest.mark.parametrize("target", ["user", "tenant"])
def test_disabled_identity_or_workspace_refuses(
    world: tuple[Session, JobContext, UUID, UUID, UUID], target: str
) -> None:
    session, context, _, _, _ = world
    if target == "user":
        session.execute(
            update(app_user)
            .where(app_user.c.id == context.principal.on_behalf_of_id)
            .values(status="DISABLED", updated_by_kind="SYSTEM")
        )
    else:
        session.execute(
            update(tenant)
            .where(tenant.c.id == context.tenant_id)
            .values(status="SUSPENDED", updated_by_kind="SYSTEM")
        )
    with pytest.raises(AIAccessRefused, match="AI_INITIATOR_INACTIVE"):
        authorize_job(context, session)


def test_inline_context_and_wrong_attempt_refuse(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, _, _, _ = world
    inline = JobContext(
        job_id=context.job_id,
        tenant_id=context.tenant_id,
        kind=JobKind.AI_TASK,
        principal=context.principal,
        runtime=replace(context.runtime, attempt=None),
        persisted=False,
    )
    with pytest.raises(AIAccessRefused, match="AI_JOB_CONTEXT_REQUIRED"):
        authorize_job(inline, session)
    wrong = JobContext(
        job_id=context.job_id,
        tenant_id=context.tenant_id,
        kind=JobKind.AI_TASK,
        principal=context.principal,
        runtime=replace(
            context.runtime, attempt=JobAttempt(context.job_id, context.tenant_id, 999999)
        ),
    )
    with pytest.raises(JobLost):
        authorize_job(wrong, session)


@pytest.mark.parametrize("world", [JobKind.REPORT_RUN], indirect=True)
def test_report_export_refreshes_requester_and_refuses_revoked_permissions(
    world: tuple[Session, JobContext, UUID, UUID, UUID],
) -> None:
    session, context, first, second, assignment = world
    principal = job_requester(context, session, kind=JobKind.REPORT_RUN)
    assert principal.kind is PrincipalKind.USER
    assert principal.id == context.principal.on_behalf_of_id
    assert principal.mfa_verified_at is None and principal.session_id is None
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="export-worker",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=context.clock.now(),
        format_locale="en-US",
    )
    access = capture_access(ctx)
    assert access.scope == "OWN"
    require_access(ctx, access)
    with pytest.raises(AIAccessRefused, match="AI_JOB_CONTEXT_REQUIRED"):
        authorize_job(context, session)
    session.execute(
        update(role_assignment)
        .where(role_assignment.c.id == assignment)
        .values(revoked_at=context.clock.now(), revoked_by_kind="SYSTEM")
    )
    refreshed = job_requester(context, session, kind=JobKind.REPORT_RUN)
    assert "ai.use" not in refreshed.permissions
    assert "report.export" not in refreshed.permissions
    with pytest.raises(Problem):
        require_access(replace(ctx, principal=refreshed), access)
    session.execute(
        update(job)
        .where(job.c.id == context.job_id)
        .values(state="SUCCEEDED", updated_by_kind="SYSTEM")
    )
    with pytest.raises(JobLost):
        job_requester(context, session, kind=JobKind.REPORT_RUN)
