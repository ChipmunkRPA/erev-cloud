"""Reauthorize an AI job as its human initiator before reading provider inputs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from erev_api.auth.permissions import effective_grants
from erev_api.auth.principal import Principal
from erev_api.db.tables import (
    app_user,
    calc_trace,
    combination_group_member,
    contract,
    job,
    tenant,
    tenant_membership,
)
from erev_api.enums import JobKind, MembershipStatus, PrincipalKind, TenantStatus, UserStatus
from erev_api.jobs.context import JobContext


class AIAccessRefused(ValueError):
    """Safe failure code without membership, role or source-document details."""


def authorize_job(
    context: JobContext, session: Session, *, entity_ids: Sequence[UUID] = ()
) -> Principal:
    """Reload current human grants and narrow them to the AI permission before source reads."""
    principal = job_requester(context, session, kind=JobKind.AI_TASK)
    scope = principal.permission_scopes.get("ai.use", frozenset())
    if (
        "ai.use" not in principal.permissions
        or not scope
        or (scope != "*" and any(entity_id not in scope for entity_id in entity_ids))
    ):
        raise AIAccessRefused("AI_PERMISSION_DENIED")
    return replace(principal, entity_scope="*" if scope == "*" else tuple(sorted(scope)))


def job_requester(
    context: JobContext,
    session: Session,
    *,
    kind: Literal[JobKind.AI_TASK, JobKind.REPORT_RUN, JobKind.EVIDENCE_PACK],
) -> Principal:
    """Refresh a persisted attempt's active human initiator; callers must check source grants.

    This returns no logged-in/MFA session and grants no SYSTEM access. A report export must
    apply its retained ExportAccess and report.export checks before reading or rendering rows.
    """
    attempt = context.runtime.attempt
    if (
        context.kind is not kind
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
        creator["kind"] != kind.value
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
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=context.tenant_id,
        membership_id=member["id"],
        display_name=member["display_name"],
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        # This is delegated worker execution, not a recreated login/MFA session.
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )


def narrative_reader(principal: Principal) -> Principal:
    """Narrow narrative evidence reads to overlapping current AI/source grants."""
    if "ai.use" not in principal.permissions:
        raise AIAccessRefused("AI_PERMISSION_DENIED")
    read_scope = principal.permission_scopes.get("contract.read", frozenset())
    ai_scope = principal.permission_scopes.get("ai.use", frozenset())
    if "contract.read" not in principal.permissions or not read_scope:
        raise AIAccessRefused("AI_READ_PERMISSION_DENIED")
    if ai_scope == "*":
        scope = read_scope
    elif read_scope == "*":
        scope = ai_scope
    else:
        scope = ai_scope & read_scope
    if not scope:
        raise AIAccessRefused("AI_READ_PERMISSION_DENIED")
    return replace(principal, entity_scope="*" if scope == "*" else tuple(sorted(scope)))


def visible_narrative_trace(
    scope: Literal["*"] | tuple[UUID, ...] = "*",
) -> ColumnElement[bool]:
    """Match Explain's current/past member access; calc_trace itself is tenant-only RLS."""
    members = (
        select(combination_group_member.c.contract_id)
        .where(
            combination_group_member.c.tenant_id == calc_trace.c.tenant_id,
            combination_group_member.c.combination_group_id == calc_trace.c.combination_group_id,
        )
        .correlate(calc_trace)
    )
    return (
        select(contract.c.id)
        .where(
            contract.c.tenant_id == calc_trace.c.tenant_id,
            true() if scope == "*" else contract.c.contracting_entity_id.in_(scope),
            or_(
                contract.c.combination_group_id == calc_trace.c.combination_group_id,
                contract.c.id.in_(members),
            ),
        )
        .correlate(calc_trace)
        .exists()
    )


class AICancelled(Exception):
    """Cooperative stop before further AI processing; retained evidence stays intact."""


def require_not_cancelled(context: JobContext) -> None:
    if context.cancel_requested():
        raise AICancelled("AI_CANCELLED")
