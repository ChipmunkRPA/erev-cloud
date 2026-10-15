"""Reauthorize an AI job as its human initiator before reading provider inputs."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.permissions import effective_grants
from erev_api.auth.principal import Principal
from erev_api.db.tables import app_user, job, tenant, tenant_membership
from erev_api.enums import JobKind, MembershipStatus, PrincipalKind, TenantStatus, UserStatus
from erev_api.jobs.context import JobContext


class AIAccessRefused(ValueError):
    """Safe failure code without membership, role or source-document details."""


def authorize_job(
    context: JobContext, session: Session, *, entity_ids: Sequence[UUID] = ()
) -> Principal:
    """Reload current grants; never use the enclosing SYSTEM principal for AI reads.

    The caller uses a job read session and must use the returned user's narrowed
    database context for subsequent retrieval. Individual file/report permissions
    must still be checked by those query services. No request or run_inline path is
    admitted. Recheck on every attempt, before selecting facts or calling a model.
    """
    attempt = context.runtime.attempt
    if (
        context.kind is not JobKind.AI_TASK
        or attempt is None
        or attempt.job_id != context.job_id
        or attempt.tenant_id != context.tenant_id
        or context.principal.tenant_id != context.tenant_id
        or context.principal.kind is not PrincipalKind.SYSTEM
    ):
        raise AIAccessRefused("AI_JOB_CONTEXT_REQUIRED")
    attempt.require(session)
    creator = (
        session.execute(
            select(job.c.created_by, job.c.created_by_kind, job.c.kind).where(
                job.c.tenant_id == context.tenant_id, job.c.id == context.job_id
            )
        )
        .mappings()
        .one()
    )
    user_id = creator["created_by"]
    if (
        creator["kind"] != JobKind.AI_TASK.value
        or creator["created_by_kind"] != PrincipalKind.USER.value
        or user_id is None
        or user_id != context.principal.on_behalf_of_id
    ):
        raise AIAccessRefused("AI_HUMAN_INITIATOR_REQUIRED")
    member = (
        session.execute(
            select(tenant_membership.c.id, app_user.c.display_name)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id).join(
                    tenant, tenant.c.id == tenant_membership.c.tenant_id
                )
            )
            .where(
                tenant_membership.c.tenant_id == context.tenant_id,
                tenant_membership.c.user_id == user_id,
                tenant_membership.c.status == MembershipStatus.ACTIVE.value,
                app_user.c.status == UserStatus.ACTIVE.value,
                tenant.c.status == TenantStatus.ACTIVE.value,
            )
        )
        .mappings()
        .one_or_none()
    )
    if member is None:
        raise AIAccessRefused("AI_INITIATOR_INACTIVE")
    grants = effective_grants(session, member["id"], at=context.clock.now())
    scope = grants.permission_scopes.get("ai.use", frozenset())
    if (
        "ai.use" not in grants.permissions
        or not scope
        or (scope != "*" and any(entity_id not in scope for entity_id in entity_ids))
    ):
        raise AIAccessRefused("AI_PERMISSION_DENIED")
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=context.tenant_id,
        membership_id=member["id"],
        display_name=member["display_name"],
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope="*" if scope == "*" else tuple(sorted(scope)),
        # This is delegated worker execution, not a recreated login/MFA session.
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )
