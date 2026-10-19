"""Reload the persisted report job's initiator before accessing frozen source evidence."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from sqlalchemy import select

from erev_api.auth.permissions import api_client_grants
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.tables import api_client, job, tenant
from erev_api.domain.ai.access import AIAccessRefused, job_requester
from erev_api.enums import JobKind, PrincipalKind
from erev_api.jobs.context import JobContext
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def validation_requester(jc: JobContext, uow: UnitOfWork, run: Mapping[str, Any]) -> RequestContext:
    attempt = jc.runtime.attempt
    if (
        jc.kind != JobKind.REPORT_RUN
        or attempt is None
        or attempt.job_id != jc.job_id
        or attempt.tenant_id != uow.principal.tenant_id
        or jc.tenant_id != uow.principal.tenant_id
        or jc.principal.kind != PrincipalKind.SYSTEM
        or run["job_id"] != jc.job_id
    ):
        raise Problem("forbidden")
    attempt.require(uow.session)
    creator = uow.session.execute(
        select(job.c.created_by, job.c.created_by_kind, job.c.kind).where(
            job.c.tenant_id == jc.tenant_id, job.c.id == jc.job_id
        )
    ).one()
    if (
        creator.kind != "REPORT_RUN"
        or creator.created_by is None
        or creator.created_by != jc.principal.on_behalf_of_id
        or (creator.created_by, creator.created_by_kind)
        != (run["created_by"], run["created_by_kind"])
    ):
        raise Problem("forbidden")
    if creator.created_by_kind == "USER":
        try:
            principal = job_requester(jc, uow.session, kind=JobKind.REPORT_RUN)
        except AIAccessRefused as error:
            raise Problem("forbidden") from error
    elif creator.created_by_kind == "API_CLIENT":
        client = uow.session.execute(
            select(api_client.c.name)
            .join(tenant, tenant.c.id == api_client.c.tenant_id)
            .where(
                api_client.c.tenant_id == jc.tenant_id,
                api_client.c.id == creator.created_by,
                tenant.c.status == "ACTIVE",
            )
        ).one_or_none()
        if client is None:
            raise Problem("forbidden")
        # Creation checked the token grant; immutable format/entity selection prevents this
        # worker from expanding that authorization. Recheck the client's current grants.
        grants = api_client_grants(
            uow.session,
            creator.created_by,
            token_scopes=["report.run", "report.export"],
            at=uow.now,
        )
        principal = Principal(
            kind=PrincipalKind.API_CLIENT,
            id=creator.created_by,
            tenant_id=jc.tenant_id,
            membership_id=None,
            display_name=client.name,
            roles=grants.roles,
            permissions=grants.permissions,
            permission_scopes=grants.permission_scopes,
            entity_scope=grants.entity_scope,
            auth_method="system",
            mfa_verified_at=None,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        )
    else:
        raise Problem("forbidden")
    require_export(principal, run["output_format"], run["entity_ids"])
    return replace(uow.ctx, principal=principal, now=uow.now)


def require_export(principal: Principal, output_format: str, entity_ids: Any) -> None:
    if output_format == "JSON":
        return
    scope = principal.permission_scopes.get("report.export")
    if (
        "report.export" not in principal.permissions
        or not scope
        or (scope != "*" and not set(entity_ids) <= scope)
    ):
        raise Problem("forbidden")
