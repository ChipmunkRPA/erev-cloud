"""SCH-11: expire overdue proposals without deleting retained AI evidence."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.principal import system_principal
from erev_api.db.session import platform_session
from erev_api.db.tables import ai_proposal, tenant
from erev_api.db.transitions import apply
from erev_api.jobs.context import JobRuntime, system_unit_of_work

BATCH_SIZE: Final = 100
REQUEST_ID: Final = "ai-proposal-expiry"


def expire_due(runtime: JobRuntime) -> int:
    """Visit each tenant; commit bounded batches and skip proposals being reviewed."""
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=REQUEST_ID, keyring=runtime.keyring
    ) as session:
        tenant_ids = tuple(session.scalars(select(tenant.c.id).order_by(tenant.c.id)))
    return sum(expire_tenant(runtime, tenant_id) for tenant_id in tenant_ids)


def expire_tenant(runtime: JobRuntime, tenant_id: UUID) -> int:
    """Lock before deciding the transition; reruns cannot duplicate expiry or audit events."""
    expired = 0
    while True:
        with system_unit_of_work(
            runtime, system_principal(tenant_id), request_id=REQUEST_ID
        ) as uow:
            rows = tuple(
                uow.session.execute(
                    select(ai_proposal.c.id, ai_proposal.c.row_version)
                    .where(
                        ai_proposal.c.tenant_id == tenant_id,
                        ai_proposal.c.status == "proposed",
                        ai_proposal.c.expires_at <= uow.now,
                    )
                    .order_by(ai_proposal.c.expires_at, ai_proposal.c.id)
                    .limit(BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                ).mappings()
            )
            for row in rows:
                apply(
                    uow.session,
                    "ai_proposal",
                    row["id"],
                    to_status="expired",
                    expected_status="proposed",
                    expected_row_version=row["row_version"],
                    set_values={
                        "row_version": row["row_version"] + 1,
                        "updated_at": uow.now,
                        "updated_by": None,
                        "updated_by_kind": "SYSTEM",
                    },
                )
                uow.audit(
                    action="ai_proposal.expire",
                    object_type="ai_proposal",
                    object_id=row["id"],
                    before={"status": "proposed"},
                    after={"status": "expired"},
                )
            uow.commit()
        expired += len(rows)
        if len(rows) < BATCH_SIZE:
            return expired
