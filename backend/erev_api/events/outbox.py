"""Transactional outbox KRN-EVT (dev-guide §5.11 DG-KRN-EVT-04 to DG-KRN-EVT-06; 04 T-INT-03;
05 ADP-30 to ADP-32, SCH-03, NTR-04, NTR-05; REQ-JE-013, REQ-PLT-021).

``enqueue`` inserts one ``outbox_message`` in the caller's transaction, deduplicated on (topic,
``dedupe_key``), and the first message of a unit of work defers one ``OUTBOX_RELAY`` job, so a
message is relayed only when the business transaction commits. ``relay`` claims one due message at a
time under ``FOR UPDATE SKIP LOCKED`` and commits the claim, with ``updated_at`` as the claim stamp,
dispatches the message through its topic handler outside the row transaction, then records
``DISPATCHED``, or ``FAILED`` with a backoff of 30 s × 2^attempt capped at one hour, or ``DEAD``
after the tenth failure, only while the stamp still holds; the job heartbeats after each message
(D-80). ``sweep`` is the minute task SCH-03: it defers a relay for every tenant holding due messages
or messages stranded in ``DISPATCHING`` for more than 15 minutes (ADP-32).
A topic may register its own ``DispatchSchedule`` in ``SCHEDULES`` (``JOURNAL_EXPORT``: the ADP-12
schedule), and a handler that raises ``Undeliverable`` ends the message ``DEAD`` at once (ADP-12
``Permanent``). ``relay_messages`` dispatches named messages of one topic (the ``JOURNAL_EXPORT``
job of a run; BUILD_SPEC CLO-13). A topic may also register what happens when one of its messages
dies (``DEAD_HOOKS``; item JRN-DISPATCH-DEAD-1): the relay calls the hook before it records
``DEAD``, and a hook that cannot do its work leaves the message claimed for the next relay, so a
message is never ``DEAD`` beside a record that still expects its delivery. ``last_error`` keeps
the slug of a catalogue problem or else the class of the error, never its message (DG-LOG-03).
``PENDING_OUTBOX_HANDLERS`` names the E-70 topics whose handlers later phases build, each with its
PHASES §5.3 phase code (BS-D-07).
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.clock import Clock
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import notification, outbox_message, tenant
from erev_api.db.transitions import apply
from erev_api.enums import JobKind, OutboxStatus, OutboxTopic, PrincipalKind
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class EmailMessage:
    tenant_code: str
    reference: UUID  # the notification id, or the aggregate id of a message without one
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    """05 NTR-05: the adapter the relay hands ``EMAIL`` messages to."""

    def send(self, message: EmailMessage) -> str:
        """Deliver ``message`` and return a delivery reference; a failure raises."""
        ...


@dataclass(frozen=True, slots=True)
class DispatchResult:
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class RelayStats:
    claimed: int
    dispatched: int
    failed: int
    dead: int


Handler = Callable[[JobContext, Mapping[str, Any]], DispatchResult]


class Undeliverable(Exception):
    """A handler failure that no retry can cure: the message is ``DEAD`` at once (05 ADP-12
    ``Permanent``)."""


@dataclass(frozen=True, slots=True)
class DispatchSchedule:
    """A topic's retry schedule: the number of attempts, and the wait after failed attempt n."""

    max_attempts: int
    delay: Callable[[int], timedelta]


MAX_ATTEMPTS: Final = 10
BACKOFF_BASE: Final = timedelta(seconds=30)
BACKOFF_CAP: Final = timedelta(hours=1)
STRANDED_AFTER: Final = timedelta(minutes=15)  # ADP-32
BATCH_SIZE: Final = 100  # messages per relay run
# 05 §5.6 execution profiles: the relay follows the ADP-12 schedule (30 s × 2^n, at most 15 minutes,
# 8 attempts); an email delivery has 5 attempts with an exponential wait from 30 s (SPEC-Q-219).
RELAY_RETRY: Final = RetryPolicy(max_attempts=8, backoff_seconds=(30, 60, 120, 240, 480, 900))
EMAIL_RETRY: Final = RetryPolicy(max_attempts=5, backoff_seconds=(30, 60, 120, 240))
_LOGGER: Final = "erev_api.events.outbox"

register_logger_fields(_LOGGER, ("outbox_message_id", "topic", "attempt", "error_class", "outcome"))
# What ``outbox.dispatch_failed`` says this relay recorded for the message, beside the two
# statuses ``FAILED`` and ``DEAD``: nothing - its dead hook raised (the message stays
# ``DISPATCHING``), a later relay had taken the message, or the recording itself raised
# (dev-guide DG-KRN-EVT-05 rev 1.206; 05 DPL-37 rev 1.162: the hosted SLO-05 alert matches
# ``outcome`` ``DEAD``).
UNSETTLED: Final = "UNSETTLED"

# One relay job per unit of work, however many messages it enqueues.
_RELAY_DEFERRED: Final[weakref.WeakSet[UnitOfWork]] = weakref.WeakSet()


def backoff(attempt: int) -> timedelta:
    """The wait after failed attempt ``attempt``: 30 s × 2^attempt, at most one hour."""
    delay: timedelta = BACKOFF_BASE * 2**attempt
    return delay if delay < BACKOFF_CAP else BACKOFF_CAP


DEFAULT_SCHEDULE: Final = DispatchSchedule(max_attempts=MAX_ATTEMPTS, delay=backoff)
# Topics whose messages follow another schedule register it from their module (JOURNAL_EXPORT).
SCHEDULES: Final[dict[OutboxTopic, DispatchSchedule]] = {}
# What a topic does when one of its messages dies — its last attempt failed, or its error says no
# retry can cure it — given the job context, the message's payload and the error (05 ADP-31 rev
# 1.98; item JRN-DISPATCH-DEAD-1). The relay calls it before it records the message ``DEAD``; a
# hook that raises leaves the message unsettled (``_dispatch``). JOURNAL_EXPORT registers the one
# that records the batch ``failed``.
DeadHook = Callable[[JobContext, Mapping[str, Any], Exception], None]
DEAD_HOOKS: Final[dict[OutboxTopic, DeadHook]] = {}


def error_name(error: Exception) -> str:
    """What the relay keeps and logs of a failed dispatch: the slug of a catalogue problem, else
    the class of the error. A database error the unit of work mapped at its commit is a
    ``Problem`` — ``lock-conflict``, ``statement-timeout`` — and its class would name nothing
    (item JRN-DISPATCH-DEAD-1). Never the message, which can hold addresses (DG-LOG-03)."""
    return error.slug if isinstance(error, Problem) else type(error).__name__


# 04 T-INT-03 ``payload`` rev 1.151: an ``EMAIL`` message never holds the token of a link. A link
# that carries one keeps this place in ``link_path`` and names the token in ``link_token``.
TOKEN_PLACE: Final = "{token}"
LINK_TOKEN: Final = "link_token"
TOKEN_NOT_NAMED: Final = "an email link with a token place names its token in link_token"
TOKEN_IN_PAYLOAD: Final = "an email payload never holds the token of a link"


def link_token_reference(purpose: str, reference: UUID, key_id: str) -> dict[str, str]:
    """The ``link_token`` member of an ``EMAIL`` payload: what the dispatcher derives the token
    of the link from (``KeyRing.link_token``)."""
    return {"purpose": purpose, "reference": str(reference), "key_id": key_id}


def _checked_email_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The payload of an ``EMAIL`` message, refused when its link would store a token: a link
    that assigns a token (``token=…``) holds the place for it, and the place and the ``link_token``
    that names the token come together (rulings R-48 (g), R-53 (h))."""
    path = str(payload.get("link_path") or "")
    if "token=" in path and TOKEN_PLACE not in path:
        raise ValueError(TOKEN_IN_PAYLOAD)
    if (TOKEN_PLACE in path) != (payload.get(LINK_TOKEN) is not None):
        raise ValueError(TOKEN_NOT_NAMED)
    return dict(payload)


def email_link_path(payload: Mapping[str, Any], keyring: KeyRing | None) -> str | None:
    """The link of an ``EMAIL`` payload as the email carries it (05 NTR-04): its ``link_path``,
    the place for a token filled with the token that ``link_token`` names — derived here, when
    the email goes out, because no payload holds one."""
    link_path = payload.get("link_path")
    if link_path is None:
        return None
    path = str(link_path)
    named = payload.get(LINK_TOKEN)
    if named is None:
        if TOKEN_PLACE in path:
            raise ValueError(TOKEN_NOT_NAMED)
        return path
    if keyring is None:
        raise RuntimeError("this job runtime has no key ring to derive a link token with")
    issued = keyring.link_token(
        str(named["purpose"]), UUID(str(named["reference"])), key_id=str(named["key_id"])
    )
    return path.replace(TOKEN_PLACE, issued.token)


def message_values(
    *,
    tenant_id: UUID,
    topic: OutboxTopic,
    aggregate_type: str,
    aggregate_id: UUID,
    dedupe_key: str,
    payload: Mapping[str, Any],
    now: datetime,
    created_by: UUID | None,
    created_by_kind: PrincipalKind,
) -> dict[str, Any]:
    """The T-INT-03 row of a new PENDING message, due at ``now``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "topic": OutboxTopic(topic).value,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "dedupe_key": dedupe_key,
        "payload": (
            _checked_email_payload(payload)
            if OutboxTopic(topic) is OutboxTopic.EMAIL
            else dict(payload)
        ),
        "status": OutboxStatus.PENDING.value,
        "attempt_count": 0,
        "next_attempt_at": now,
        "created_at": now,
        "created_by": created_by,
        "created_by_kind": created_by_kind.value,
        "updated_at": now,
        "updated_by": created_by,
        "updated_by_kind": created_by_kind.value,
    }


def insert_message(session: Session, values: Mapping[str, Any]) -> bool:
    """Insert unless (tenant, topic, ``dedupe_key``) exists; True when a row was inserted."""
    statement = (
        insert(outbox_message)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "topic", "dedupe_key"])
        .returning(outbox_message.c.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


def enqueue(
    uow: UnitOfWork,
    *,
    topic: OutboxTopic,
    aggregate_type: str,
    aggregate_id: UUID,
    dedupe_key: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Insert a message in the unit of work and relay it after commit (DG-KRN-EVT-04).

    A repeated (topic, ``dedupe_key``) inserts nothing and returns the stored message.
    """
    principal = uow.principal
    values = message_values(
        tenant_id=principal.tenant_id,
        topic=topic,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        dedupe_key=dedupe_key,
        payload=payload,
        now=uow.now,
        created_by=principal.id,
        created_by_kind=principal.kind,
    )
    if not insert_message(uow.session, values):
        stored = (
            uow.session.execute(
                select(outbox_message).where(
                    outbox_message.c.topic == values["topic"],
                    outbox_message.c.dedupe_key == dedupe_key,
                )
            )
            .mappings()
            .one()
        )
        return MappingProxyType(dict(stored))
    if uow not in _RELAY_DEFERRED:
        _RELAY_DEFERRED.add(uow)
        uow.defer(JobKind.OUTBOX_RELAY, {})
    return MappingProxyType(values)


def _stamp(now: datetime) -> dict[str, Any]:
    return {"updated_at": now, "updated_by": None, "updated_by_kind": PrincipalKind.SYSTEM.value}


def _due(now: datetime) -> ColumnElement[bool]:
    """Due messages, and messages whose own claim stamp is more than 15 minutes old (ADP-32)."""
    return or_(
        and_(
            outbox_message.c.status.in_([OutboxStatus.PENDING.value, OutboxStatus.FAILED.value]),
            outbox_message.c.next_attempt_at <= now,
        ),
        and_(
            outbox_message.c.status == OutboxStatus.DISPATCHING.value,
            outbox_message.c.updated_at < now - STRANDED_AFTER,
        ),
    )


@dataclass(frozen=True, slots=True)
class _Claimed:
    id: UUID
    topic: OutboxTopic
    payload: Mapping[str, Any]
    attempt_count: int
    stamp: datetime  # the ``updated_at`` the claim wrote


def _claim(
    jc: JobContext, *, message_id: UUID | None = None, topic: OutboxTopic | None = None
) -> _Claimed | None:
    """Mark the next due message ``DISPATCHING``, stamp ``updated_at`` and commit (D-80)."""
    now = jc.clock.now()
    statement = (
        select(
            outbox_message.c.id,
            outbox_message.c.topic,
            outbox_message.c.payload,
            outbox_message.c.attempt_count,
            outbox_message.c.status,
        )
        .where(_due(now))
        .order_by(outbox_message.c.next_attempt_at, outbox_message.c.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if message_id is not None:
        statement = statement.where(outbox_message.c.id == message_id)
    if topic is not None:
        statement = statement.where(outbox_message.c.topic == topic.value)
    with tenant_session(jc.principal.db_context) as session:
        row = session.execute(statement).one_or_none()
        if row is None:
            return None
        if row.status == OutboxStatus.DISPATCHING.value:
            apply(session, "outbox_message", row.id, to_status=None, set_values=_stamp(now))
        else:
            apply(
                session,
                "outbox_message",
                row.id,
                to_status=OutboxStatus.DISPATCHING.value,
                expected_status=str(row.status),
                set_values=_stamp(now),
            )
    return _Claimed(
        id=UUID(str(row.id)),
        topic=OutboxTopic(row.topic),
        payload=MappingProxyType(dict(row.payload)),
        attempt_count=int(row.attempt_count),
        stamp=now,
    )


def _record(
    jc: JobContext, message: _Claimed, target: OutboxStatus, values: Mapping[str, Any]
) -> OutboxStatus | None:
    """Record the outcome while ``updated_at`` still equals the claim stamp; None when a later relay
    re-claimed the message (ADP-32), which then settles it."""
    with tenant_session(jc.principal.db_context) as session:
        held = session.execute(
            select(outbox_message.c.id)
            .where(
                outbox_message.c.id == message.id,
                outbox_message.c.status == OutboxStatus.DISPATCHING.value,
                outbox_message.c.updated_at == message.stamp,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if held is None:
            return None
        apply(
            session,
            "outbox_message",
            message.id,
            to_status=target.value,
            expected_status=OutboxStatus.DISPATCHING.value,
            set_values=values,
        )
    return target


def _died(jc: JobContext, message: _Claimed, error: Exception) -> bool:
    """Run the topic's ``DEAD_HOOKS`` entry for a message that is about to be recorded ``DEAD``;
    False when the hook itself failed. The message is then not settled: it stays ``DISPATCHING``
    under this claim, its failed attempt uncounted, and the relay that takes it again after 15
    minutes (ADP-32) dispatches it as the last attempt once more — so what the hook writes and the
    ``DEAD`` status are either both recorded or neither (item JRN-DISPATCH-DEAD-1)."""
    hook = DEAD_HOOKS.get(message.topic)
    if hook is None:
        return True
    try:
        hook(jc, message.payload, error)
    except Exception as failure:
        get_logger(_LOGGER).error(
            "outbox.dead_hook_failed",
            outbox_message_id=str(message.id),
            topic=message.topic.value,
            attempt=message.attempt_count + 1,
            error_class=error_name(failure),
        )
        return False
    return True


def _dispatch(jc: JobContext, message: _Claimed) -> OutboxStatus | None:
    """Run the topic handler outside any row transaction and record the outcome; None when the
    outcome was not recorded — a later relay re-claimed the message, or its dead hook failed."""
    handler = HANDLERS.get(message.topic)
    try:
        if handler is None:
            raise LookupError(f"no outbox handler is registered for topic {message.topic.value}")
        handler(jc, message.payload)
    except Exception as error:
        attempt = message.attempt_count + 1
        now = jc.clock.now()
        schedule = SCHEDULES.get(message.topic, DEFAULT_SCHEDULE)
        dead = isinstance(error, Undeliverable) or attempt >= schedule.max_attempts
        target = OutboxStatus.DEAD if dead else OutboxStatus.FAILED
        # Only the error's name is kept: messages can hold addresses (DG-LOG-03).
        name = error_name(error)
        values: dict[str, Any] = {"attempt_count": attempt, "last_error": name, **_stamp(now)}
        if target is OutboxStatus.FAILED:
            delay = schedule.delay(attempt)
            # 05 ADP-12: a failure that states when the other side takes the next request (the
            # ``Retry-After`` of a 429) is not retried earlier than that.
            asked = getattr(error, "retry_after", None)
            if isinstance(asked, int | float) and asked > 0:
                delay = max(delay, timedelta(seconds=float(asked)))
            values["next_attempt_at"] = now + delay
        recorded: OutboxStatus | None = None
        try:
            if not dead or _died(jc, message, error):
                recorded = _record(jc, message, target, values)
        finally:
            # Written once the outcome is known, so that the line calls a message dead only
            # when it is recorded so (item DEPLOY-ALERT-NAMES-1).
            get_logger(_LOGGER).warning(
                "outbox.dispatch_failed",
                outbox_message_id=str(message.id),
                topic=message.topic.value,
                attempt=attempt,
                error_class=name,
                outcome=UNSETTLED if recorded is None else recorded.value,
            )
        return recorded
    now = jc.clock.now()
    # DG-KRN-EVT-05 rev 1.127 (ruling R-108 (b) (5)): a delivered message keeps no `last_error` -
    # the class of an earlier failed attempt is not the row's state; `attempt_count` keeps the
    # history.
    return _record(
        jc,
        message,
        OutboxStatus.DISPATCHED,
        {"dispatched_at": now, "last_error": None, **_stamp(now)},
    )


def _relay(
    jc: JobContext,
    *,
    batch_size: int,
    message_id: UUID | None = None,
    topic: OutboxTopic | None = None,
) -> RelayStats:
    """Claim, dispatch and record one message at a time, at most ``batch_size``; the job heartbeats
    after each message (D-80)."""
    claimed = 0
    outcomes: list[OutboxStatus] = []
    while claimed < batch_size:
        message = _claim(jc, message_id=message_id, topic=topic)
        if message is None:
            break
        claimed += 1
        status = _dispatch(jc, message)
        if status is not None:
            outcomes.append(status)
        jc.heartbeat()
        if message_id is not None:
            break
    return RelayStats(
        claimed=claimed,
        dispatched=outcomes.count(OutboxStatus.DISPATCHED),
        failed=outcomes.count(OutboxStatus.FAILED),
        dead=outcomes.count(OutboxStatus.DEAD),
    )


def relay(jc: JobContext, *, batch_size: int = BATCH_SIZE) -> RelayStats:
    """Dispatch up to ``batch_size`` of the tenant's due messages (DG-KRN-EVT-05; ADP-31)."""
    return _relay(jc, batch_size=batch_size)


def relay_messages(
    jc: JobContext, message_ids: Sequence[UUID], *, topic: OutboxTopic
) -> RelayStats:
    """Dispatch each named message of ``topic`` that is due, one at a time (BUILD_SPEC CLO-13)."""
    totals = [
        _relay(jc, batch_size=1, message_id=message_id, topic=topic) for message_id in message_ids
    ]
    return RelayStats(
        claimed=sum(item.claimed for item in totals),
        dispatched=sum(item.dispatched for item in totals),
        failed=sum(item.failed for item in totals),
        dead=sum(item.dead for item in totals),
    )


def _dispatch_email(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
    """``EMAIL``: one message to the payload's recipient. The link joins ``EREV_PUBLIC_ORIGIN``
    and the payload's ``link_path`` (NTR-04), completed here with the token of a link that carries
    one (``email_link_path``); a notification's ``email_sent_at`` is set once."""
    runtime = jc.runtime
    if runtime.email is None or runtime.public_origin is None:
        raise RuntimeError("this job runtime has no email sender")
    with jc.read_session() as session:
        code = session.execute(
            select(tenant.c.code).where(tenant.c.id == jc.tenant_id)
        ).scalar_one()
    text = str(payload["text"])
    link_path = email_link_path(payload, runtime.keyring)
    if link_path is not None:
        text = f"{text}\n{runtime.public_origin}{link_path}\n"
    reference = runtime.email.send(
        EmailMessage(
            tenant_code=str(code),
            reference=UUID(str(payload["reference"])),
            to=str(payload["to"]),
            subject=str(payload["subject"]),
            text=text,
        )
    )
    notification_id = payload.get("notification_id")
    if notification_id is not None:
        with tenant_session(jc.principal.db_context) as session:
            session.execute(
                update(notification)
                .where(
                    notification.c.id == UUID(str(notification_id)),
                    notification.c.email_sent_at.is_(None),
                )
                .values(email_sent_at=jc.clock.now())
            )
    return DispatchResult(reference=reference)


# One handler per built E-70 topic (DG-ARC-08). Topics whose handlers live in other modules register
# from those modules when the worker imports them (``WEBHOOK``: ``erev_api.events.webhooks``;
# ``JOURNAL_EXPORT``: ``erev_api.domain.journals.export``; ``SYNC_REQUEST``:
# ``erev_api.domain.integrations.outbox``).
HANDLERS: Final[dict[OutboxTopic, Handler]] = {OutboxTopic.EMAIL: _dispatch_email}

PENDING_OUTBOX_HANDLERS: Final[tuple[tuple[str, str], ...]] = ()


def _outcome(stats: RelayStats) -> JobOutcome:
    counts = {
        "claimed": stats.claimed,
        "dispatched": stats.dispatched,
        "failed": stats.failed,
        "dead": stats.dead,
    }
    return JobOutcome(state="SUCCEEDED", result={"counts": counts})


@task(JobKind.OUTBOX_RELAY, retry=RELAY_RETRY)
def relay_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``OUTBOX_RELAY``: one relay batch of the tenant (ADP-31)."""
    return _outcome(relay(jc))


@task(JobKind.EMAIL_DELIVERY, retry=EMAIL_RETRY)
def email_delivery_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``EMAIL_DELIVERY``: dispatch the ``EMAIL`` message ``params["outbox_message_id"]`` when it
    is due, with the outbox retry schedule (SPEC-Q-179)."""
    stats = _relay(
        jc,
        batch_size=1,
        message_id=UUID(str(params["outbox_message_id"])),
        topic=OutboxTopic.EMAIL,
    )
    return _outcome(stats)


def sweep(clock: Clock, *, request_id: str = "outbox-sweeper") -> int:
    """SCH-03: defer ``OUTBOX_RELAY`` for each tenant with due or stranded messages and no relay
    already QUEUED or RUNNING (ADP-32); returns the number of relays deferred."""
    return registry.defer_for_due_tenants(
        JobKind.OUTBOX_RELAY,
        {},
        due=lambda now: select(outbox_message.c.id).where(_due(now)),
        clock=clock,
        request_id=request_id,
    )
