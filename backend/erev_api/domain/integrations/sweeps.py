"""SCH-09 ``integration_sweeps`` (05 §5.7 SCH-09, §5.1 ADP-16, ADP-17; 04 T-INT-02 ``kind``,
T-INT-03 ``SYNC_REQUEST``; 03 REQ-INT-007; BUILD_SPEC DIN-13).

Every six hours the worker asks for one ``SYNC_RUN`` of kind ``RECONCILIATION_SWEEP`` per ACTIVE
inbound connection of every ACTIVE tenant. The request is an outbox message on topic
``SYNC_REQUEST`` (``outbox.enqueue_sync_request``) whose dedupe key names the connection, the kind
and the six-hour bucket of the run, so a periodic that fires twice for one bucket — a worker
restart, two workers, a retried task — asks once. ``OUTBOX_RELAY`` turns the message into the QUEUED
T-INT-02 row and its job in one unit of work (``commands.request_sync``); the job compares the
source's object versions with ``source_record`` and, once the connection's baseline sweep is
complete, raises ``SOURCE_VERSION_GAP`` for the versions the feed never delivered
(``sync.apply_object``).

One SYSTEM unit of work per tenant. A sandbox tenant has no inbound integration (05 SBX-08: the
request would be refused 403 ``sandbox-restricted`` at the relay), so its connections — rows a
snapshot may have copied — are counted and skipped. A connection disabled between this read and
the relay is refused there by name (409 ``invalid-transition``, recorded on the message, ADP-31).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.principal import system_principal
from erev_api.db.tables import integration_connection, outbox_message
from erev_api.domain.integrations import commands
from erev_api.domain.integrations.outbox import enqueue_sync_request, sync_request_key
from erev_api.domain.platform.tenant_directory import active_tenants
from erev_api.enums import OutboxTopic, TenantKind
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.logging import get_logger, register_logger_fields

__all__ = [
    "BUCKET_HOURS",
    "KIND",
    "REQUEST_ID",
    "SweepReport",
    "bucket_of",
    "run",
    "sweepable_connections",
]

REQUEST_ID: Final = "sch09-integration-sweeps"
KIND: Final = "RECONCILIATION_SWEEP"
BUCKET_HOURS: Final = 6  # the period of the SCH-09 cron ``0 */6 * * *``

_LOGGER: Final = "erev_api.domain.integrations.sweeps"
register_logger_fields(
    _LOGGER,
    ("tenants", "connections", "requested", "repeated", "sandbox_skipped", "tenant_id", "bucket"),
)


@dataclass(frozen=True, slots=True)
class SweepReport:
    tenants: int = 0
    connections: int = 0
    requested: int = 0  # messages enqueued by this run
    repeated: int = 0  # connections already asked for in this bucket
    sandbox_skipped: int = 0  # connections of sandbox tenants (05 SBX-08)


def bucket_of(now: datetime) -> str:
    """The six-hour UTC bucket of ``now``: ``2026-09-12T12`` from 12:00 to 17:59:59."""
    at = now.astimezone(UTC)
    return f"{at:%Y-%m-%d}T{at.hour - at.hour % BUCKET_HOURS:02d}"


def sweepable_connections(session: Session) -> list[UUID]:
    """The ACTIVE connections of the session's tenant that ``/sync`` admits a
    ``RECONCILIATION_SWEEP`` for (``commands.INBOUND_ADAPTERS``), in code order."""
    rows = session.execute(
        select(integration_connection.c.id)
        .where(
            integration_connection.c.status == "ACTIVE",
            integration_connection.c.adapter.in_(sorted(commands.INBOUND_ADAPTERS)),
        )
        .order_by(integration_connection.c.code)
    ).scalars()
    return [UUID(str(value)) for value in rows]


def _asked(session: Session, connection_id: UUID, bucket: str) -> bool:
    return (
        session.execute(
            select(outbox_message.c.id).where(
                outbox_message.c.topic == OutboxTopic.SYNC_REQUEST.value,
                outbox_message.c.dedupe_key == sync_request_key(connection_id, KIND, bucket),
            )
        ).first()
        is not None
    )


def run(
    runtime: JobRuntime,
    *,
    request_id: str = REQUEST_ID,
    only_tenants: Sequence[UUID] | None = None,
) -> SweepReport:
    """SCH-09 over every ACTIVE tenant; returns the counts it also logs."""
    logger = get_logger(_LOGGER)
    tenant_ids = active_tenants(runtime, request_id=request_id, only=only_tenants)
    connections = requested = repeated = sandbox_skipped = 0
    for tenant_id in tenant_ids:
        with system_unit_of_work(
            runtime, system_principal(tenant_id), request_id=request_id
        ) as uow:
            found = sweepable_connections(uow.session)
            connections += len(found)
            if not found:
                continue
            if uow.ctx.tenant_kind is TenantKind.SANDBOX:
                sandbox_skipped += len(found)
                continue
            bucket = bucket_of(uow.now)
            asked = 0
            for connection_id in found:
                if _asked(uow.session, connection_id, bucket):
                    repeated += 1
                    continue
                enqueue_sync_request(uow, connection_id=connection_id, kind=KIND, bucket=bucket)
                asked += 1
            uow.commit()
            requested += asked
            logger.info(
                "integration_sweeps.requested",
                tenant_id=str(tenant_id),
                bucket=bucket,
                connections=len(found),
                requested=asked,
            )
    report = SweepReport(
        tenants=len(tenant_ids),
        connections=connections,
        requested=requested,
        repeated=repeated,
        sandbox_skipped=sandbox_skipped,
    )
    logger.info(
        "integration_sweeps.completed",
        tenants=report.tenants,
        connections=report.connections,
        requested=report.requested,
        repeated=report.repeated,
        sandbox_skipped=report.sandbox_skipped,
    )
    return report
