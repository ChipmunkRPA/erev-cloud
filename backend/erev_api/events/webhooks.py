"""Outbound webhooks KRN-EVT (dev-guide §5.11 DG-KRN-EVT-07; 04 T-PLT-35, T-PLT-36; 05 NTR-10 to
NTR-13, SCH-12, KEY-08; REQ-PLT-034; BUILD_SPEC PLF-24, BS1-D-08).

``emit_webhook`` inserts one ``webhook_delivery`` per active endpoint subscribed to the event kind,
holding the NTR-10 envelope ``{id, kind, tenant_code, occurred_at, data}``, and enqueues one
``WEBHOOK`` outbox message per delivery in the caller's transaction. ``deliver`` makes one attempt
for each due delivery, claiming one delivery at a time (D-80): the claim stamps ``next_attempt_at``
two minutes ahead and commits; a second transaction locks the row while the stamp still holds,
posts the canonical JSON body signed with ``X-Erev-Signature: t=<unix seconds>,v1=<hex>`` through
the runtime's ``WebhookSender``, and records ``SUCCEEDED``; or ``FAILED``, due again
30 s × 2^(n − 1) after the n-th failed attempt, at most one hour later and never after
``abandon_at``; or ``ABANDONED`` once ``abandon_at`` (created + 24 hours) is reached or the endpoint
is inactive. A delivery whose stamp changed was taken by another deliverer and is left alone. The
job heartbeats after each delivery. The ``WEBHOOK`` outbox handler makes the first attempt; the
minute task ``webhook_delivery_due`` (SCH-12) defers ``WEBHOOK_DELIVERY`` for every tenant holding
due deliveries, which makes the retries.

A sandbox sends no webhook (05 SBX-08 rev 1.64; REQ-PLT-022; CTL-043), and this module holds the
second of the rule's three layers, independent of the command guard and of the DB-15 trigger:
``emit_webhook`` creates no delivery and no outbox message when the unit of work's tenant is a
sandbox, whatever the endpoint rows say, and ``deliver`` ends a delivery it finds queued in a
sandbox ``ABANDONED`` before the signing secret is opened or the sender is called.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import ColumnElement, Select, and_, insert, select
from sqlalchemy.orm import Session

from erev_api.audit.verify import rfc3339
from erev_api.auth.keyring import KeyRing
from erev_api.clock import Clock
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import tenant, webhook_delivery, webhook_endpoint
from erev_api.db.transitions import apply
from erev_api.enums import JobKind, OutboxTopic, TenantKind, WebhookDeliveryStatus
from erev_api.events import outbox
from erev_api.events.outbox import DispatchResult
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.logging import get_logger, register_logger_fields

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# 04 T-PLT-35 ``event_kinds`` (REQ-PLT-034).
EVENT_KINDS: Final[tuple[str, ...]] = (
    "run.completed",
    "import.committed",
    "period.locked",
    "journal_batch.exported",
    "journal_batch.acknowledged",
    "exception.raised",
)
SIGNATURE_HEADER: Final = "X-Erev-Signature"  # BS1-D-08
ABANDON_AFTER: Final = timedelta(hours=24)  # T-PLT-36 ``abandon_at``
LEASE: Final = timedelta(seconds=120)  # the claim stamp: the 05 §5.6 WEBHOOK_DELIVERY timeout
# 05 §5.6: 5 attempts with an exponential wait from 30 s.
DELIVERY_RETRY: Final = RetryPolicy(max_attempts=5, backoff_seconds=(30, 60, 120, 240))
BATCH_SIZE: Final = 100  # deliveries per run (D-80)
HREF_PREFIX: Final = "/api/v1/"
DELIVERY_OBJECT: Final = "webhook_delivery"
ENDPOINT_INACTIVE: Final = "The endpoint is inactive."
# 05 SBX-08: the ``last_error`` of a delivery found queued in a sandbox tenant.
SANDBOX_TENANT: Final = "The workspace is a sandbox; a sandbox sends no webhooks."
_PENDING: Final = WebhookDeliveryStatus.PENDING
_FAILED: Final = WebhookDeliveryStatus.FAILED
_SUCCEEDED: Final = WebhookDeliveryStatus.SUCCEEDED
_ABANDONED: Final = WebhookDeliveryStatus.ABANDONED
_LOGGER: Final = "erev_api.events.webhooks"

register_logger_fields(_LOGGER, ("webhook_delivery_id", "attempt", "status", "error_class"))


class WebhookDeliveryError(Exception):
    """A refused or failed delivery whose message is safe to store in ``last_error``."""


class WebhookSender(Protocol):
    """05 NTR-12: the adapter a delivery hands its signed body to."""

    def post(self, url: str, *, body: bytes, headers: Mapping[str, str]) -> int:
        """POST ``body`` to ``url`` without following redirects and return the response status;
        a refused destination raises ``WebhookDeliveryError``, a transport failure any error."""
        ...


@dataclass(frozen=True, slots=True)
class DeliveryStats:
    claimed: int
    succeeded: int
    failed: int
    abandoned: int


def signature_header(secret: bytes, timestamp: int, body: bytes) -> str:
    """NTR-11: ``t=<unix seconds>,v1=<hex HMAC-SHA256 over "<t>." + body>``."""
    signed = f"{timestamp}.".encode("ascii") + body
    return f"t={timestamp},v1={hmac.new(secret, signed, hashlib.sha256).hexdigest()}"


def secret_context(tenant_id: UUID, endpoint_id: UUID) -> dict[str, str]:
    """SAR-07 associated data of an endpoint's sealed signing secret (KEY-08)."""
    return {
        "table": "webhook_endpoint",
        "column": "secret_ciphertext",
        "tenant_id": str(tenant_id),
        "row_id": str(endpoint_id),
    }


def delivery_wait(failures: int) -> timedelta:
    """The wait after the ``failures``-th failed attempt: 30 s × 2^(failures − 1), at most one
    hour (T-PLT-36)."""
    return outbox.backoff(failures - 1)


def _data_value(key: str, value: Any) -> str:
    """NTR-10: a member of ``data`` is an id (``id`` or ``*_id``) or an href (``href`` or
    ``*_href``) under ``/api/v1/``."""
    if key == "href" or key.endswith("_href"):
        if isinstance(value, str) and value.startswith(HREF_PREFIX):
            return value
    elif key == "id" or key.endswith("_id"):
        if isinstance(value, UUID | str):
            return str(UUID(str(value)))
    raise ValueError(f"webhook data member {key!r} must be an id or an href (05 NTR-10)")


def emit_webhook(uow: UnitOfWork, *, event_kind: str, payload: Mapping[str, Any]) -> int:
    """Insert one delivery per active endpoint subscribed to ``event_kind`` and enqueue its
    ``WEBHOOK`` message (DG-KRN-EVT-07); returns the number of deliveries.

    ``payload`` becomes the envelope's ``data`` and holds resource ids and hrefs only (NTR-10);
    any other member, or an unknown event kind, raises ``ValueError``.

    In a sandbox tenant nothing is emitted and 0 is returned, whatever the endpoint rows say
    (05 SBX-08): the event kind and the payload are still checked, so a caller's mistake reads
    the same in both kinds of workspace.
    """
    if event_kind not in EVENT_KINDS:
        raise ValueError(f"unknown webhook event kind {event_kind!r} (04 T-PLT-35)")
    data = {key: _data_value(key, value) for key, value in sorted(payload.items())}
    if uow.ctx.tenant_kind is TenantKind.SANDBOX:
        return 0
    session = uow.session
    endpoint_ids = [
        UUID(str(value))
        for value in session.scalars(
            select(webhook_endpoint.c.id)
            .where(
                webhook_endpoint.c.is_active.is_(True),
                webhook_endpoint.c.event_kinds.contains([event_kind]),
            )
            .order_by(webhook_endpoint.c.id)
        )
    ]
    if not endpoint_ids:
        return 0
    principal = uow.principal
    code = session.execute(
        select(tenant.c.code).where(tenant.c.id == principal.tenant_id)
    ).scalar_one()
    envelope = {
        "id": str(new_id()),
        "kind": event_kind,
        "tenant_code": str(code),
        "occurred_at": rfc3339(uow.now),
        "data": data,
    }
    digest = sha256_hex(envelope)
    for endpoint_id in endpoint_ids:
        delivery_id = new_id()
        session.execute(
            insert(webhook_delivery).values(
                tenant_id=principal.tenant_id,
                id=delivery_id,
                webhook_endpoint_id=endpoint_id,
                event_kind=event_kind,
                payload=envelope,
                payload_sha256=digest,
                status=_PENDING.value,
                attempt_count=0,
                next_attempt_at=uow.now,
                abandon_at=uow.now + ABANDON_AFTER,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
            )
        )
        outbox.enqueue(
            uow,
            topic=OutboxTopic.WEBHOOK,
            aggregate_type=DELIVERY_OBJECT,
            aggregate_id=delivery_id,
            dedupe_key=f"webhook:{delivery_id}",
            payload={"webhook_delivery_id": str(delivery_id)},
        )
    return len(endpoint_ids)


def _due(now: datetime) -> ColumnElement[bool]:
    return and_(
        webhook_delivery.c.status.in_([_PENDING.value, _FAILED.value]),
        webhook_delivery.c.next_attempt_at <= now,
    )


def due_deliveries(now: datetime) -> Select[Any]:
    """The deliveries due at ``now``: PENDING or FAILED with ``next_attempt_at`` reached."""
    return select(webhook_delivery.c.id).where(_due(now))


@dataclass(frozen=True, slots=True)
class _Claimed:
    id: UUID
    status: WebhookDeliveryStatus
    attempt_count: int
    abandon_at: datetime
    payload: Mapping[str, Any]
    endpoint_id: UUID
    url: str
    secret_ciphertext: bytes
    is_active: bool
    sandbox: bool  # the delivery's tenant is a sandbox (05 SBX-08): never posted
    stamp: datetime  # the ``next_attempt_at`` the claim wrote


def _claim(jc: JobContext, *, delivery_id: UUID | None) -> _Claimed | None:
    """Claim the next due delivery: stamp ``next_attempt_at`` two minutes ahead and commit
    (D-80)."""
    now = jc.clock.now()
    statement = (
        select(
            webhook_delivery.c.id,
            webhook_delivery.c.status,
            webhook_delivery.c.attempt_count,
            webhook_delivery.c.abandon_at,
            webhook_delivery.c.payload,
            webhook_endpoint.c.id.label("endpoint_id"),
            webhook_endpoint.c.url,
            webhook_endpoint.c.secret_ciphertext,
            webhook_endpoint.c.is_active,
            tenant.c.kind.label("tenant_kind"),
        )
        .join(
            webhook_endpoint,
            and_(
                webhook_endpoint.c.tenant_id == webhook_delivery.c.tenant_id,
                webhook_endpoint.c.id == webhook_delivery.c.webhook_endpoint_id,
            ),
        )
        .join(tenant, tenant.c.id == webhook_delivery.c.tenant_id)
        .where(_due(now))
        .order_by(webhook_delivery.c.next_attempt_at, webhook_delivery.c.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=webhook_delivery)
    )
    if delivery_id is not None:
        statement = statement.where(webhook_delivery.c.id == delivery_id)
    stamp = now + LEASE
    with tenant_session(jc.principal.db_context) as session:
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        apply(
            session,
            "webhook_delivery",
            row["id"],
            to_status=None,
            set_values={"next_attempt_at": stamp},
        )
    return _Claimed(
        id=UUID(str(row["id"])),
        status=WebhookDeliveryStatus(row["status"]),
        attempt_count=int(row["attempt_count"]),
        abandon_at=row["abandon_at"],
        payload=dict(row["payload"]),
        endpoint_id=UUID(str(row["endpoint_id"])),
        url=str(row["url"]),
        secret_ciphertext=bytes(row["secret_ciphertext"]),
        is_active=bool(row["is_active"]),
        sandbox=TenantKind(row["tenant_kind"]) is TenantKind.SANDBOX,
        stamp=stamp,
    )


def _held(session: Session, item: _Claimed) -> bool:
    """Lock the claimed delivery while ``next_attempt_at`` still equals the claim stamp; False when
    another deliverer took it after the lease lapsed."""
    locked = session.execute(
        select(webhook_delivery.c.id)
        .where(
            webhook_delivery.c.id == item.id,
            webhook_delivery.c.status == item.status.value,
            webhook_delivery.c.next_attempt_at == item.stamp,
        )
        .with_for_update()
    ).scalar_one_or_none()
    return locked is not None


def _record(
    session: Session, item: _Claimed, target: WebhookDeliveryStatus, values: Mapping[str, Any]
) -> WebhookDeliveryStatus:
    apply(
        session,
        "webhook_delivery",
        item.id,
        to_status=None if target is item.status else target.value,
        expected_status=item.status.value,
        set_values=values,
    )
    return target


def _attempt(
    jc: JobContext, sender: WebhookSender, keyring: KeyRing, item: _Claimed
) -> WebhookDeliveryStatus | None:
    """One NTR-12 POST of a claimed delivery, recorded only where the claim stamp still holds.

    The recording transaction locks the row before the POST and keeps it until the outcome is
    written, so a deliverer whose clock passed the lease during the POST cannot take the delivery
    and post the same attempt again (SPEC-Q-216). None means another deliverer took the delivery.
    """
    with tenant_session(jc.principal.db_context) as session:
        if not _held(session, item):
            return None
        if item.sandbox:
            # 05 SBX-08: ended before the secret is opened or the sender is called.
            values = {"next_attempt_at": None, "last_error": SANDBOX_TENANT}
            return _record(session, item, _ABANDONED, values)
        if not item.is_active:
            values = {"next_attempt_at": None, "last_error": ENDPOINT_INACTIVE}
            return _record(session, item, _ABANDONED, values)
        attempt = item.attempt_count + 1
        body = canonical_bytes(item.payload)
        secret = keyring.decrypt(
            item.secret_ciphertext, context=secret_context(jc.tenant_id, item.endpoint_id)
        )
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: signature_header(secret, int(jc.clock.now().timestamp()), body),
        }
        response_status: int | None = None
        try:
            response_status = sender.post(item.url, body=body, headers=headers)
        except WebhookDeliveryError as refused:
            error = str(refused)
        except Exception as failure:
            # Only the class is kept: transport messages can carry addresses (DG-LOG-03).
            error = type(failure).__name__
        else:
            if 200 <= response_status < 300:
                succeeded = {
                    "attempt_count": attempt,
                    "next_attempt_at": None,
                    "last_response_status": response_status,
                    "last_error": None,
                    "succeeded_at": jc.clock.now(),
                }
                return _record(session, item, _SUCCEEDED, succeeded)
            error = f"HTTP {response_status}"
        finished = jc.clock.now()
        if finished >= item.abandon_at:
            target, next_attempt = _ABANDONED, None
        else:
            target, next_attempt = _FAILED, min(finished + delivery_wait(attempt), item.abandon_at)
        status = _record(
            session,
            item,
            target,
            {
                "attempt_count": attempt,
                "next_attempt_at": next_attempt,
                "last_response_status": response_status,
                "last_error": error,
            },
        )
    get_logger(_LOGGER).warning(
        "webhook.delivery_failed",
        webhook_delivery_id=str(item.id),
        attempt=attempt,
        status=status.value,
        error_class=error if response_status is not None else error.split(":", 1)[0],
    )
    return status


def deliver(
    jc: JobContext, *, delivery_id: UUID | None = None, batch_size: int = BATCH_SIZE
) -> DeliveryStats:
    """Attempt the tenant's due deliveries one claim at a time, at most ``batch_size``, or only
    ``delivery_id`` when it is due; the job heartbeats after each delivery (D-80)."""
    sender, keyring = jc.runtime.webhooks, jc.runtime.keyring
    if sender is None or keyring is None:
        raise RuntimeError("this job runtime has no webhook sender or key ring")
    claimed = 0
    outcomes: list[WebhookDeliveryStatus] = []
    while claimed < batch_size:
        item = _claim(jc, delivery_id=delivery_id)
        if item is None:
            break
        claimed += 1
        status = _attempt(jc, sender, keyring, item)
        if status is not None:
            outcomes.append(status)
        jc.heartbeat()
        if delivery_id is not None:
            break
    return DeliveryStats(
        claimed=claimed,
        succeeded=outcomes.count(_SUCCEEDED),
        failed=outcomes.count(_FAILED),
        abandoned=outcomes.count(_ABANDONED),
    )


def dispatch_webhook(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
    """``WEBHOOK``: the first attempt of delivery ``payload["webhook_delivery_id"]``. A delivery
    that is no longer due (attempted by the sweep, or leased) is left alone."""
    delivery_id = UUID(str(payload["webhook_delivery_id"]))
    stats = deliver(jc, delivery_id=delivery_id, batch_size=1)
    return DispatchResult(reference=str(delivery_id) if stats.claimed else None)


outbox.HANDLERS[OutboxTopic.WEBHOOK] = dispatch_webhook


@task(JobKind.WEBHOOK_DELIVERY, retry=DELIVERY_RETRY)
def delivery_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``WEBHOOK_DELIVERY``: one batch of the tenant's due deliveries, or the delivery
    ``params["webhook_delivery_id"]``."""
    named = params.get("webhook_delivery_id")
    stats = deliver(jc, delivery_id=None if named is None else UUID(str(named)))
    counts = {
        "claimed": stats.claimed,
        "succeeded": stats.succeeded,
        "failed": stats.failed,
        "abandoned": stats.abandoned,
    }
    return JobOutcome(state="SUCCEEDED", result={"counts": counts})


def sweep(clock: Clock, *, request_id: str = "webhook-sweeper") -> int:
    """SCH-12: defer ``WEBHOOK_DELIVERY`` for each tenant with due deliveries and no delivery job
    QUEUED or RUNNING; returns the number deferred."""
    return registry.defer_for_due_tenants(
        JobKind.WEBHOOK_DELIVERY, {}, due=due_deliveries, clock=clock, request_id=request_id
    )
