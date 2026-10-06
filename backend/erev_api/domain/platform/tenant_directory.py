"""The tenant directory the SCH periodics iterate (05 §SCH; the SCH-15 pattern): ACTIVE tenants in
id order through a platform session, optionally only those whose BR-PLT-02 setup is complete and
optionally narrowed to named tenants (a runbook re-run; the database witnesses)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from erev_api.db.session import platform_session
from erev_api.db.tables import tenant
from erev_api.enums import TenantStatus
from erev_api.jobs.context import JobRuntime


def active_tenants(
    runtime: JobRuntime,
    *,
    request_id: str,
    setup_complete: bool = False,
    only: Sequence[UUID] | None = None,
) -> list[UUID]:
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=runtime.keyring
    ) as db:
        query = select(tenant.c.id).where(tenant.c.status == TenantStatus.ACTIVE.value)
        if setup_complete:
            query = query.where(tenant.c.setup_completed_at.is_not(None))
        if only is not None:
            query = query.where(tenant.c.id.in_(list(only)))
        return [UUID(str(value)) for value in db.scalars(query.order_by(tenant.c.id))]
