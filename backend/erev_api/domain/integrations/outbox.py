"""``SYNC_REQUEST`` outbox handler (04 T-INT-03 E-70 ``SYNC_REQUEST``; 05 ADP-30 to ADP-32 relay
pattern; dev-guide DG-KRN-EVT-04, DG-ARC-08; BUILD_SPEC DIN-12).

A sync request is an outbox message ``{connection_id, kind}`` on topic ``SYNC_REQUEST`` — enqueued
by a scheduler or another command in its own transaction (``enqueue_sync_request``) and relayed by
``OUTBOX_RELAY``; ``dispatch_sync_request`` runs ``commands.request_sync`` in one unit of work of
the job's principal, so the queued T-INT-02 row and its ``SYNC_RUN`` job are committed together
(DG-KRN-JOB-02). The dedupe key ``sync:<connection id>:<kind>:<bucket>`` lets a periodic scheduler
(DIN-13 ``sweeps.py``, SCH-09) enqueue at most one request per connection, kind and time bucket.
A refused request (a DISABLED connection, a kind the connection cannot run) is a ``Problem`` the
relay records as the message's failure (ADP-31).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from erev_api.domain.integrations import commands
from erev_api.enums import OutboxTopic
from erev_api.events import outbox
from erev_api.jobs.context import JobContext
from erev_api.uow import UnitOfWork

__all__ = ["AGGREGATE_TYPE", "dispatch_sync_request", "enqueue_sync_request", "sync_request_key"]

AGGREGATE_TYPE: Final = "integration_connection"


def sync_request_key(connection_id: UUID, kind: str, bucket: str) -> str:
    """The T-INT-03 ``dedupe_key`` of one request: ``sync:<connection id>:<kind>:<bucket>``."""
    return f"sync:{connection_id}:{kind}:{bucket}"


def enqueue_sync_request(
    uow: UnitOfWork, *, connection_id: UUID, kind: str, bucket: str
) -> Mapping[str, Any]:
    """Queue a sync request in the caller's transaction (relayed after commit, DG-KRN-EVT-04)."""
    return outbox.enqueue(
        uow,
        topic=OutboxTopic.SYNC_REQUEST,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=connection_id,
        dedupe_key=sync_request_key(connection_id, kind, bucket),
        payload={"connection_id": str(connection_id), "kind": kind},
    )


def dispatch_sync_request(jc: JobContext, payload: Mapping[str, Any]) -> outbox.DispatchResult:
    """``SYNC_REQUEST``: the QUEUED run and its ``SYNC_RUN`` job; the reference is the job id."""
    connection_id = UUID(str(payload["connection_id"]))
    kind = str(payload.get("kind") or "INBOUND_POLL")
    with jc.unit_of_work() as uow:
        requested = commands.request_sync(uow, connection_id, kind=kind)
        uow.commit()
    return outbox.DispatchResult(reference=str(requested.job_id))


outbox.HANDLERS[OutboxTopic.SYNC_REQUEST] = dispatch_sync_request
