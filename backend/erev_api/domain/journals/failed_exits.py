"""The ways out of a failed journal run (04 T-SL-07 "The ways out of ``failed``", §16.7 "Journal
commands" rev 1.159, E-34; 05 ADP-12, ADP-33, §5.6, SBX-08; PRD SM-08, BR-JE-03, ERR-73, ERR-74;
dev-guide DG-KRN-JOB-05; CTL-021; item JRN-FAILED-CANCEL-1, supervisor ruling R-112 (c)).

A batch its ledger can never accept as generated held the acknowledgement gate of its period for
good: a ``failed`` batch had no way out but a retry. Two more exist here, and both ask the ledger
first — a ``REJECTED`` receipt does not say whether the ledger answered or eight attempts timed
out, and a timeout can follow an acceptance.

``cancel_run`` is ``POST /journal-runs/{id}/cancel``. A run without a failed batch is cancelled as
before (``commands.cancel_run``: ``draft`` or ``approved``, 200). A run with a failed batch is
refused while another of its batches is ``exported`` or ``acknowledged`` (PRD ERR-74: the
recalculation would send those lines again under new external ids), while a later run of its
entity, book and period stands, while one of its batches is being sent or still waits to be sent,
and while a cancellation of it is already under way. Otherwise the command changes nothing and
defers ``JOURNAL_EXPORT`` in mode ``CANCEL`` (202). The job asks the ledger for every failed batch
of an ERP adapter by its external id, with no transaction open (ADP-12 ``get_posting``). A batch
the ledger holds gets its ``DUPLICATE`` receipt and is acknowledged, and the run is not cancelled
(PRD ERR-73). When the ledger holds none, ONE transaction under the run, batch and coverage locks
reads everything again — the command's refusals, and that no batch was sent since the ledger was
asked — and cancels the run and its batches (E-34 ``failed`` → ``cancelled``), resolves the
batches' ``JOURNAL_EXPORT_FAILED`` items with the reason and records a CTL-021 execution for each
failed batch. The next run of the key starts where its non-cancelled runs end (DB-16).

``hand_over_batch`` is ``POST /journal-batches/{id}/hand-over``: the exit of a failed batch of an
ERP adapter whose run is partly in a ledger. After the same question, one transaction counts and
totals the batch's lines again (``export.recount``), stores the REQ-JE-011 file and moves the
batch ``failed`` → ``exported`` without a message or a receipt; the batch then waits for
``acknowledge`` as a CSV batch does (ADP-33; PRD BR-JE-03).

What the two jobs decide is returned, not raised (``export.Refused``; DG-KRN-JOB-05): only a
ledger that could not be reached fails the attempt, which the ADP-12 schedule repeats. A refusal
is also an audit event of the command's own action with outcome ``DENIED``, written by the job.

Neither exit asks before the ledger has had its time (04 §16.7 rev 1.247; 05 ADP-12 rev 1.175;
item JRN-EXIT-SETTLE-1, review finding F9). "Not found" means "holds nothing" only when no
request can still land: a request the ledger did not answer can be applied after the attempt
ended, and a ledger that accepted a chunk may not show it yet. So for ``SETTLE_AFTER`` from the
end of a failed batch's last attempt, unless the ledger refused the chunk, and at any age for a
batch whose message died of ``ports.Accepted``, both exits are refused by name — at the command
and again in the job's deciding transaction (``may_still_land``). The retry is held back by
neither: it asks the ledger first and sends under the same external id.

A decision is made once (04 §16.7 rev 1.246; dev-guide DG-KRN-JOB-05 rev 1.233; item
JRN-EXIT-JOB-IDEMPOTENT-1, review finding F10). The kernel records a job's end in a transaction
after the handler's own, so a worker that stops between the two has the handler run again over
what it already did; decided anew, a run it had cancelled read "cannot be cancelled" and a
second, ``DENIED`` event contradicted the first. Each decision event therefore names its job and
carries the job's counts, and an attempt begins by looking for the event of its own job
(``_decided``): finding one, it returns that ending, asks no ledger and writes nothing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.dependencies import require_for_entity
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import transitions
from erev_api.db.tables import (
    audit_event,
    integration_connection,
    job,
    journal_batch,
    journal_run,
    tenant,
)
from erev_api.domain.journals import commands, export, ports, summarise
from erev_api.domain.platform import guards
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import (
    AuditOutcome,
    ControlResult,
    GlAdapter,
    JobKind,
    JobState,
    JournalState,
    OutboxStatus,
)
from erev_api.jobs.registry import JobOutcome
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut
from erev_api.schemas.journals import JournalRunCancelIn, JournalRunOut

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

# ``params.mode`` of the two ``JOURNAL_EXPORT`` modes, and ``result.outcome`` of their jobs.
CANCEL: Final = "CANCEL"
HAND_OVER: Final = "HAND_OVER"
CANCELLED: Final = "CANCELLED"
NOT_CANCELLED: Final = "NOT_CANCELLED"
HANDED_OVER: Final = "HANDED_OVER"
NOT_HANDED_OVER: Final = "NOT_HANDED_OVER"
BATCH_PARAM: Final = export.BATCH_PARAM  # the batch a hand-over names, as a retry names its own
REASON_PARAM: Final = "reason"
# The request is the command's event; the decision is the job's (SUCCESS or DENIED).
CANCEL_REQUEST_ACTION: Final = "journal_run.request_cancel"
HAND_OVER_REQUEST_ACTION: Final = "journal_batch.request_hand_over"
HAND_OVER_ACTION: Final = "journal_batch.hand_over"
FAILED: Final = JournalState.FAILED.value
APPROVED: Final = JournalState.APPROVED.value
CANCELLED_STATE: Final = JournalState.CANCELLED.value
# A batch in one of these states is outside eRev: a ledger holds it, or its file was handed out.
OUTSIDE: Final = frozenset({JournalState.EXPORTED.value, JournalState.ACKNOWLEDGED.value})
PENDING_JOB: Final = (JobState.QUEUED.value, JobState.RUNNING.value)
# An export message the relay will still send: beside a failed batch it is a retry, or a batch
# the relay has not reached (ruling R-112 (c): "no message of the run is claimed or pending").
STILL_TO_BE_SENT: Final = (OutboxStatus.PENDING, OutboxStatus.FAILED)
# PRD ERR-73: the ledger holds a failed batch — the two endings of the sentence.
HELD_NOT_CANCELLED: Final = (
    "{ledger} holds batch {external_id} as {document}. The batch is acknowledged and journal "
    "run {run_no} is not cancelled."
)
HELD_NOT_HANDED_OVER: Final = (
    "{ledger} holds batch {external_id} as {document}. The batch is acknowledged and is not "
    "handed over."
)
# PRD ERR-74.
PARTLY_IN_LEDGER: Final = (
    "Journal run {run_no} has a batch that a ledger holds or that was handed out "
    "({external_id}). Retry its failed batch, or hand it over for manual posting."
)
# 04 §16.7 rev 1.159, sentences without a PRD row.
UNREACHABLE: Final = (
    "The ledger could not be reached, so nothing was changed: {message}. Ask again when the "
    "ledger answers."
)
NOT_ASKED: Final = "The ledger could not be asked, so nothing was changed: {reason}"
CONNECTION_GONE: Final = (
    "batch {external_id} names a general ledger connection that no longer exists."
)
CONNECTION_DISABLED: Final = "general ledger connection {code} is disabled."
EXPORT_WAITING: Final = (
    "An export of this journal run is in progress: batch {external_id} is waiting to be sent. "
    "It cannot be cancelled until the batch has been sent or has failed."
)
CANCEL_UNDER_WAY: Final = "A cancellation of this journal run is already under way."
SENT_MEANWHILE: Final = (
    "Batch {external_id} was sent again while the ledger was asked, so nothing was changed. "
    "Ask again."
)
NOT_FAILED: Final = "Only a failed batch can be handed over."
CSV_BATCH: Final = (
    "A CSV batch is not handed over. Correct what its export named and retry it, or cancel the "
    "journal run."
)
BATCH_BEING_SENT: Final = (
    "Batch {external_id} is being sent. It cannot be handed over while it is being sent."
)
BATCH_WAITING: Final = (
    "Batch {external_id} is waiting to be sent again. It cannot be handed over until that "
    "retry has ended."
)
HAND_OVER_UNDER_WAY: Final = "A hand-over of this batch is already under way."
LINES_NOT_HANDED_OVER: Final = "It cannot be handed over."  # ends ``export.LINES_DIFFER``
# 04 §16.7 rev 1.247 (item JRN-EXIT-SETTLE-1; review finding F9): a failed batch the ledger may
# still take. Both exits ask the ledger and read "not found" as "holds nothing", which is true
# only when no request can still land there. ``SETTLE_AFTER`` is how long after the end of a
# batch's last attempt they wait before they ask, unless the ledger refused the chunk: the
# longest wait of the ADP-12 schedule, and the age at which a stranded claim is taken again
# (ADP-32). The wait shortens the time in which a late acceptance is missed and does not end it
# (05 ADP-12, the stated limit). A batch the ledger ACCEPTED is refused at any age.
SETTLE_AFTER: Final = export.RETRY_CAP
REFUSED_BY_LEDGER: Final = ports.Permanent.__name__  # ``outbox_message.last_error``
ACCEPTED_BY_LEDGER: Final = ports.Accepted.__name__
SETTLING: Final = (
    "The last attempt to send batch {external_id} ended less than 15 minutes ago without the "
    "ledger's refusal, so the ledger may still take it."
)
LEDGER_ACCEPTED: Final = "The ledger accepted batch {external_id} and does not show it yet."
RETRY_INSTEAD: Final = "Retry the batch: a retry asks the ledger first."
ASK_AGAIN: Final = "Ask again in about {wait}, or retry the batch."
CANCEL_SETTLING: Final = f"{SETTLING} This journal run cannot be cancelled yet. {ASK_AGAIN}"
CANCEL_ACCEPTED: Final = f"{LEDGER_ACCEPTED} This journal run cannot be cancelled. {RETRY_INSTEAD}"
HAND_OVER_SETTLING: Final = f"{SETTLING} It cannot be handed over yet. {ASK_AGAIN}"
HAND_OVER_ACCEPTED: Final = f"{LEDGER_ACCEPTED} It cannot be handed over. {RETRY_INSTEAD}"
# The resolutions of the batches' ``JOURNAL_EXPORT_FAILED`` items.
CANCELLED_RESOLUTION: Final = "The journal run was cancelled: {reason}"
HELD_RESOLUTION: Final = "The ledger holds the batch as {document}."
HANDED_OVER_RESOLUTION: Final = "The batch was handed over for manual posting."
HANDED_OVER_MESSAGE: Final = "{count} lines written to the export file for manual posting."

_text = export._text
_state_problem = export._state_problem


@dataclass(frozen=True, slots=True)
class _Asked:
    """A failed batch as it stood when the ledger was asked: ``attempts`` is what the last
    transaction compares, so a batch that was sent meanwhile is never decided on a stale answer.
    ``context`` holds the ``GLContext`` members of its connection; None for a ``CSV`` batch, which
    has no ledger, and with ``unusable`` — why — for a ledger that cannot be asked."""

    id: UUID
    external_id: str
    adapter: GlAdapter
    attempts: int
    ledger: str
    context: Mapping[str, Any] | None = None
    unusable: str | None = None


class _NotAsked(Exception):
    """A ledger that cannot be asked at all — its connection is gone or disabled, or it refused
    the question: a decision, not a failure of the attempt."""


def _batches(session: Session, run_id: UUID) -> list[dict[str, Any]]:
    """The run's batches in batch and chunk order, locked in that order (DG-CMD-02)."""
    return [
        dict(item)
        for item in session.execute(
            select(journal_batch)
            .where(journal_batch.c.journal_run_id == run_id)
            .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
            .with_for_update()
        ).mappings()
    ]


def _under_way(session: Session, run_id: UUID, mode: str, batch_id: UUID | None = None) -> bool:
    """Whether a job of ``mode`` for the run — and the batch — has still to finish."""
    statement = select(job.c.id).where(
        job.c.kind == JobKind.JOURNAL_EXPORT.value,
        job.c.subject_id == run_id,
        job.c.state.in_(PENDING_JOB),
        job.c.params[export.MODE_PARAM].astext == mode,
    )
    if batch_id is not None:
        statement = statement.where(job.c.params[BATCH_PARAM].astext == str(batch_id))
    return session.execute(statement.limit(1)).first() is not None


# --- what stored facts refuse ---------------------------------------------------------------------


def deaths(named: Sequence[export.NamedMessage]) -> list[tuple[str, str | None, datetime]]:
    """Of the one read of a run's named messages (``export.named_messages``), the failed batches
    of an ERP adapter whose export message is ``DEAD``, in their order: (the external id, the
    message's ``last_error``, the instant its last attempt ended). A ``CSV`` batch has no
    ledger; a batch whose message is not settled is ``export.unsettled_of``'s."""
    return [
        (item.external_id, item.last_error, item.updated_at)
        for item in named
        if item.batch_state == FAILED
        and item.adapter != GlAdapter.CSV.value
        and item.status is OutboxStatus.DEAD
    ]


def may_still_land(
    deaths: Sequence[tuple[str, str | None, datetime]], now: datetime
) -> tuple[str, str | None] | None:
    """Which failed batch the ledger may still take (04 §16.7 rev 1.247), of ``deaths``: the
    first whose message died of an acceptance — (its external id, None): the ledger said yes,
    at any age — else the first whose message died of anything but the ledger's refusal less
    than ``SETTLE_AFTER`` ago — (its external id, the wait that is left, in whole minutes
    rounded up). None when the ledger can be asked about every batch."""
    for external_id, error, _ in deaths:
        if error == ACCEPTED_BY_LEDGER:
            return external_id, None
    for external_id, error, died_at in deaths:
        left = died_at + SETTLE_AFTER - now
        if error != REFUSED_BY_LEDGER and left > timedelta(0):
            minutes = math.ceil(left / timedelta(minutes=1))
            return external_id, f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return None


def _not_yet(landing: tuple[str, str | None], *, accepted: str, settling: str) -> Problem:
    """The refusal of an exit for the batch ``may_still_land`` names, in the exit's words."""
    external_id, wait = landing
    if wait is None:
        return _state_problem(accepted.format(external_id=external_id))
    return _state_problem(settling.format(external_id=external_id, wait=wait))


def _standing(
    uow: UnitOfWork, row: Mapping[str, Any], batches: Sequence[Mapping[str, Any]]
) -> Problem | None:
    """The refusal of the cancel of a run with a failed batch that stored facts decide, read
    under the run and batch locks — by the command and, again, by the job's last transaction.
    The coverage lock is taken here, after the row locks, as ``commands.cancel_run`` takes it,
    and after it the period's state row: a run of a closed period is not cancelled (item
    JR-CLOSED-PERIOD-GUARD-1; 04 §16.7 ``cancel`` (d) rev 1.205)."""
    session = uow.session
    run_id = UUID(str(row["id"]))
    outside = next((item for item in batches if _text(item["state"]) in OUTSIDE), None)
    if outside is not None:
        return _state_problem(
            PARTLY_IN_LEDGER.format(run_no=row["run_no"], external_id=outside["external_id"])
        )
    states = {_text(item["state"]) for item in batches}
    if _text(row["state"]) != FAILED or not states <= {FAILED, APPROVED}:
        return _state_problem(commands.NOT_CANCELLABLE)
    summarise.lock_coverage(
        session,
        tenant_id=uow.principal.tenant_id,
        entity_id=UUID(str(row["entity_id"])),
        book_code=str(_text(row["book_code"])),
        period_id=UUID(str(row["period_id"])),
    )
    # the period's state row, held from here on, as ``commands.cancel_run`` takes it (PRD ERR-86)
    closed = summarise.refuse_closed_period(
        session,
        entity_id=UUID(str(row["entity_id"])),
        book_code=str(_text(row["book_code"])),
        period_id=UUID(str(row["period_id"])),
        consequence=summarise.NOT_CANCELLED,
    )
    if closed is not None:
        return closed
    later = commands._later_run(session, row)
    if later is not None:
        return _state_problem(commands.LATER_RUN.format(run_no=later))
    # one read for every refusal: a message claimed between two reads would be missed by both
    named = export.named_messages(session, run_id)
    held = export.unsettled_of(named)
    sending = export.first_with(held, OutboxStatus.DISPATCHING)
    if sending is not None:
        return _state_problem(commands.EXPORT_IN_PROGRESS.format(external_id=sending))
    pending = export.first_with(held, *STILL_TO_BE_SENT)
    if pending is not None:
        return _state_problem(EXPORT_WAITING.format(external_id=pending))
    # every message is settled: is one of them a death after which the ledger may still post?
    landing = may_still_land(deaths(named), uow.now)
    if landing is not None:
        return _not_yet(landing, accepted=CANCEL_ACCEPTED, settling=CANCEL_SETTLING)
    return None


def _batch_standing(session: Session, batch: Mapping[str, Any], now: datetime) -> Problem | None:
    """The refusal of a hand-over that stored facts decide, under the run and batch locks, at
    the instant ``now`` of the deciding transaction."""
    if _text(batch["state"]) != FAILED:
        return _state_problem(NOT_FAILED)
    if GlAdapter(str(_text(batch["adapter"]))) is GlAdapter.CSV:
        return _state_problem(CSV_BATCH)
    run_id, batch_id = UUID(str(batch["journal_run_id"])), UUID(str(batch["id"]))
    external_id = str(batch["external_id"])
    named = export.named_messages(session, run_id, batch_id)  # one read, as in ``_standing``
    held = export.unsettled_of(named)
    if export.first_with(held, OutboxStatus.DISPATCHING) is not None:
        return _state_problem(BATCH_BEING_SENT.format(external_id=external_id))
    if export.first_with(held, *STILL_TO_BE_SENT) is not None:
        return _state_problem(BATCH_WAITING.format(external_id=external_id))
    landing = may_still_land(deaths(named), now)
    if landing is not None:
        return _not_yet(landing, accepted=HAND_OVER_ACCEPTED, settling=HAND_OVER_SETTLING)
    return None


def _sent_meanwhile(
    batches: Sequence[Mapping[str, Any]], asked: Sequence[_Asked]
) -> Problem | None:
    """The refusal for a failed batch the ledger was not asked about as it stands now: it failed,
    or was sent again, after the question. Its attempt count moves with every recorded dispatch
    and a dispatch still in flight is ``_standing``'s, so an equal count is the same batch."""
    seen = {item.id: item.attempts for item in asked}
    for batch in batches:
        if _text(batch["state"]) != FAILED:
            continue
        if seen.get(UUID(str(batch["id"]))) != int(batch["attempt_count"]):
            return _state_problem(SENT_MEANWHILE.format(external_id=batch["external_id"]))
    return None


# --- the commands (04 §16.7) ----------------------------------------------------------------------


def cancel_run(uow: UnitOfWork, run_id: UUID, body: JournalRunCancelIn) -> JournalRunOut | JobOut:
    """``POST /journal-runs/{id}/cancel``: 200 API-S-JournalRun for a run none of whose batches
    failed (``commands.cancel_run``); 202 API-S-Job ``JOURNAL_EXPORT`` for a failed run, which the
    job cancels once its ledger holds none of it (module docstring)."""
    session = uow.session
    row = commands._locked_run(session, run_id)
    require_for_entity(uow.ctx, commands.RUN_PERMISSION, UUID(str(row["entity_id"])))
    batches = _batches(session, run_id)
    if not any(_text(item["state"]) == FAILED for item in batches):
        return commands.cancel_run(uow, run_id, body)
    refused = _standing(uow, row, batches)
    if refused is not None:
        raise refused
    if _under_way(session, run_id, CANCEL):
        raise _state_problem(CANCEL_UNDER_WAY)
    job_row = uow.defer(
        JobKind.JOURNAL_EXPORT,
        {"journal_run_id": str(run_id), export.MODE_PARAM: CANCEL, REASON_PARAM: body.reason},
        subject_type=export.OBJECT_TYPE,
        subject_id=run_id,
    )
    uow.audit(
        action=CANCEL_REQUEST_ACTION,
        object_type=export.OBJECT_TYPE,
        object_id=run_id,
        object_version=str(row["row_version"]),
        after={
            "state": FAILED,
            "job_id": str(job_row["id"]),
            "failed_batch_ids": [
                str(item["id"]) for item in batches if _text(item["state"]) == FAILED
            ],
        },
        comment=body.reason,
    )
    return job_out_of(session, UUID(str(job_row["id"])))


def hand_over_batch(uow: UnitOfWork, batch_id: UUID) -> JobOut:
    """``POST /journal-batches/{id}/hand-over``: 202 API-S-Job ``JOURNAL_EXPORT`` (module
    docstring). A sandbox exports nothing, so it is refused through the one guard (05 SBX-08)."""
    session = uow.session
    batch = export._command_batch(uow, batch_id)
    run_id = UUID(str(batch["journal_run_id"]))
    guards.ensure_production(
        uow,
        action=HAND_OVER_REQUEST_ACTION,
        object_type=export.BATCH_OBJECT,
        object_id=batch_id,
        message=export.SANDBOX_DETAIL,
    )
    refused = _batch_standing(session, batch, uow.now)
    if refused is not None:
        raise refused
    if _under_way(session, run_id, HAND_OVER, batch_id):
        raise _state_problem(HAND_OVER_UNDER_WAY)
    job_row = uow.defer(
        JobKind.JOURNAL_EXPORT,
        {"journal_run_id": str(run_id), export.MODE_PARAM: HAND_OVER, BATCH_PARAM: str(batch_id)},
        subject_type=export.OBJECT_TYPE,
        subject_id=run_id,
    )
    uow.audit(
        action=HAND_OVER_REQUEST_ACTION,
        object_type=export.BATCH_OBJECT,
        object_id=batch_id,
        object_version=str(batch["row_version"]),
        after={
            "state": FAILED,
            "external_id": str(batch["external_id"]),
            "last_error": batch["last_error"],
            "job_id": str(job_row["id"]),
        },
    )
    return job_out_of(session, UUID(str(job_row["id"])))


# --- the question to the ledger (05 ADP-12) -------------------------------------------------------


def _failed(session: Session, run_id: UUID, batch_id: UUID | None = None) -> list[_Asked]:
    """The run's failed batches — or ``batch_id`` alone, when it is one — as they stand, each
    with what is needed to ask its ledger."""
    statement = (
        select(
            journal_batch.c.id,
            journal_batch.c.external_id,
            journal_batch.c.adapter,
            journal_batch.c.attempt_count,
            journal_batch.c.integration_connection_id,
        )
        .where(journal_batch.c.journal_run_id == run_id, journal_batch.c.state == FAILED)
        .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
    )
    if batch_id is not None:
        statement = statement.where(journal_batch.c.id == batch_id)
    found: list[_Asked] = []
    for row in session.execute(statement).mappings():
        adapter = GlAdapter(str(_text(row["adapter"])))
        external_id = str(row["external_id"])
        asked = _Asked(
            id=UUID(str(row["id"])),
            external_id=external_id,
            adapter=adapter,
            attempts=int(row["attempt_count"]),
            ledger=adapter.value,
        )
        if adapter is not GlAdapter.CSV:
            connection = session.execute(
                select(
                    integration_connection.c.code,
                    integration_connection.c.name,
                    integration_connection.c.status,
                    integration_connection.c.base_url,
                    integration_connection.c.config,
                ).where(integration_connection.c.id == row["integration_connection_id"])
            ).one_or_none()
            if connection is None:
                asked = dataclasses.replace(
                    asked, unusable=CONNECTION_GONE.format(external_id=external_id)
                )
            elif str(connection.status) != export.ACTIVE_CONNECTION:
                asked = dataclasses.replace(
                    asked,
                    ledger=str(connection.name),
                    unusable=CONNECTION_DISABLED.format(code=connection.code),
                )
            else:
                asked = dataclasses.replace(
                    asked,
                    ledger=str(connection.name),
                    context={
                        "base_url": connection.base_url,
                        "config": dict(connection.config or {}),
                    },
                )
        found.append(asked)
    return found


def _held(
    jc: JobContext, failed: Sequence[_Asked], tenant_code: str
) -> list[tuple[_Asked, ports.PostingResult]]:
    """Ask the ledger for every failed batch of an ERP adapter, with no transaction open; the
    batches it holds, each with the posting. ``_NotAsked`` when a ledger cannot be asked — before
    any is, so nothing is decided on half an answer; ``Problem`` when it could not be reached,
    which fails the attempt and leaves everything as it is."""
    for batch in failed:
        if batch.unusable is not None:
            raise _NotAsked(batch.unusable)
    held: list[tuple[_Asked, ports.PostingResult]] = []
    for batch in failed:
        if batch.context is None:
            continue  # a CSV batch fails before a file exists: there is no ledger to ask
        try:
            adapter = ports.gl_adapter_for(
                batch.adapter,
                ports.GLContext(tenant_code=tenant_code, accounts=(), **batch.context),
            )
            posting = adapter.get_posting(batch.external_id)
        except ports.Transient as error:
            message = UNREACHABLE.format(message=str(error).rstrip("."))
            raise _state_problem(message) from error
        except ports.Permanent as error:
            raise _NotAsked(str(error)) from error
        jc.heartbeat()
        if posting is not None:
            held.append((batch, posting))
    return held


def _acknowledge(jc: JobContext, batch: _Asked, posting: ports.PostingResult) -> str:
    """The ledger holds the batch: its ``DUPLICATE`` receipt, the batch ``acknowledged`` and the
    run rolled up, in one transaction (``export.record_posting``). The ledger's document."""
    document = str(posting.gl_document_id)
    export.record_posting(
        jc,
        batch.id,
        dataclasses.replace(posting, status="DUPLICATE"),
        resolution=HELD_RESOLUTION.format(document=document),
    )
    return document


def _refusal_detail(jc: JobContext, refusal: Problem, counts: Mapping[str, int]) -> dict[str, Any]:
    """The ``detail`` of the ``DENIED`` event a job writes for the refusal it decided: what an
    attempt of the job that is run again rebuilds the refusal from (``_again``), with the job's
    ``counts`` (04 §16.7 rev 1.246)."""
    [error] = refusal.errors
    return {
        "problem": refusal.slug,
        "field": error.field,
        "rule_id": error.rule_id,
        "message": refusal.detail,
        "job_id": str(jc.job_id),
        "counts": dict(counts),
    }


def _cancel_denied(
    jc: JobContext, run_id: UUID, refusal: Problem, reason: str, counts: Mapping[str, int]
) -> None:
    """The refused cancel, as the ``DENIED`` ``journal_run.cancel`` event of the run."""
    with jc.unit_of_work() as uow:
        uow.audit(
            action=commands.CANCEL_ACTION,
            object_type=export.OBJECT_TYPE,
            object_id=run_id,
            outcome=AuditOutcome.DENIED,
            detail=_refusal_detail(jc, refusal, counts),
            comment=reason,
        )
        uow.commit()


def _hand_over_denied(
    jc: JobContext, batch_id: UUID, refusal: Problem, counts: Mapping[str, int]
) -> None:
    """The refused hand-over, as the ``DENIED`` ``journal_batch.hand_over`` event of the batch."""
    with jc.unit_of_work() as uow:
        uow.audit(
            action=HAND_OVER_ACTION,
            object_type=export.BATCH_OBJECT,
            object_id=batch_id,
            outcome=AuditOutcome.DENIED,
            detail=_refusal_detail(jc, refusal, counts),
        )
        uow.commit()


# --- a job that is run again (04 §16.7 rev 1.246; dev-guide DG-KRN-JOB-05 rev 1.233) --------------


def _decided(
    jc: JobContext, object_type: str, object_id: UUID, action: str
) -> tuple[bool, Mapping[str, Any]] | None:
    """The decision this job already made, when an earlier attempt of it made one (item
    JRN-EXIT-JOB-IDEMPOTENT-1). A handler's return and the record of the job's end are two
    transactions (``registry._execute``): a worker that stops between them leaves the job
    ``RUNNING``, the sweeper queues it again, and the handler runs a second time over a run it
    has cancelled or a batch it has handed over. The decision is the audit event of ``action``
    on the object whose ``job_id`` is this job's — in ``after`` for ``SUCCESS``, in ``detail``
    for ``DENIED``: (whether it succeeded, those facts). None while the job has decided nothing,
    which is also what a worker leaves that stopped between a decision and its ``DENIED`` event;
    that decision is then made again. An event without ``counts`` was written before the
    revision and is not read as a decision."""
    job_id = str(jc.job_id)
    with jc.read_session() as session:
        events = session.execute(
            select(audit_event.c.outcome, audit_event.c.after, audit_event.c.detail)
            .where(
                audit_event.c.object_type == object_type,
                audit_event.c.object_id == object_id,
                audit_event.c.action == action,
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    for outcome, after, detail in events:
        succeeded = _text(outcome) == AuditOutcome.SUCCESS.value
        facts = (after if succeeded else detail) or {}
        if facts.get("job_id") == job_id and "counts" in facts:
            return succeeded, facts
    return None


def _done(run_id: UUID, counts: Mapping[str, int], outcome: str) -> JobOutcome:
    """The ending of a mode that did what was asked."""
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": export.RUN_HREF.format(run_id=run_id),
            "counts": dict(counts),
            "outcome": outcome,
        },
    )


def _again(
    jc: JobContext,
    run_id: UUID,
    decided: tuple[bool, Mapping[str, Any]],
    *,
    done: str,
    not_done: str,
) -> JobOutcome:
    """What an attempt that is run again returns: the ending its job's decision event records,
    with that event's counts. No ledger is asked and nothing is written."""
    succeeded, facts = decided
    counts = {str(name): int(value) for name, value in dict(facts["counts"]).items()}
    if succeeded:
        return _done(run_id, counts, done)
    message = str(facts["message"])
    error = ProblemError(field=facts.get("field"), rule_id=facts.get("rule_id"), message=message)
    refusal = Problem(str(facts["problem"]), message, errors=[error])
    return export.Refused(not_done, refusal).job_outcome(jc, run_id, counts)


def _tenant_code(session: Session, tenant_id: UUID) -> str:
    return str(session.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one())


# --- mode CANCEL ----------------------------------------------------------------------------------


def _cancel(
    jc: JobContext,
    run_id: UUID,
    reason: str,
    asked: Sequence[_Asked],
    counts: Mapping[str, int],
) -> Problem | None:
    """The cancel itself, in one transaction under the run, batch and coverage locks; the
    refusal, and nothing written, when the run is no longer what the ledger was asked about.
    ``counts`` is what the job ends with when it cancels: the event carries it (``_decided``)."""
    asked_ids = {item.id for item in asked if item.context is not None}
    with jc.unit_of_work() as uow:
        session = uow.session
        row = commands._locked_run(session, run_id)
        batches = _batches(session, run_id)
        refused = _standing(uow, row, batches) or _sent_meanwhile(batches, asked)
        if refused is not None:
            return refused
        for batch in batches:
            batch_id, state = UUID(str(batch["id"])), str(_text(batch["state"]))
            transitions.apply(
                session,
                export.BATCH_OBJECT,
                batch_id,
                to_status=CANCELLED_STATE,
                expected_status=state,
                set_values={"row_version": int(batch["row_version"]) + 1, **export._stamps(uow)},
            )
            if state != FAILED:
                continue
            export._settle_failure(
                uow, batch_id, resolution=CANCELLED_RESOLUTION.format(reason=reason)
            )
            # CTL-021: the batch no longer waits for a receipt — the ledger does not hold it.
            record_execution(
                uow,
                control_id=export.CONTROL_ID,
                run_ref_type=RunRefType.JOURNAL_BATCH,
                run_ref_id=batch_id,
                population_count=1,
                exception_count=0,
                result=ControlResult.PASS,
                entity_id=UUID(str(batch["entity_id"])),
                book_code=str(_text(batch["book_code"])),
                period_id=UUID(str(batch["period_id"])),
                detail={
                    "status": CANCELLED_STATE,
                    "ack_kind": None,
                    "gl_document_id": None,
                    "ledger_asked": batch_id in asked_ids,
                },
            )
        transitions.apply(
            session,
            export.OBJECT_TYPE,
            run_id,
            to_status=CANCELLED_STATE,
            expected_status=FAILED,
            set_values={
                "cancelled_at": uow.now,
                "row_version": int(row["row_version"]) + 1,
                **export._stamps(uow),
            },
        )
        uow.audit(
            action=commands.CANCEL_ACTION,
            object_type=export.OBJECT_TYPE,
            object_id=run_id,
            before={"state": FAILED, "cancelled_at": None},
            after={
                "state": CANCELLED_STATE,
                "cancelled_at": uow.now,
                "journal_batch_ids": [str(batch["id"]) for batch in batches],
                "ledger_asked": sorted(
                    item.external_id for item in asked if item.context is not None
                ),
                "job_id": str(jc.job_id),
                "counts": dict(counts),
            },
            comment=reason,
        )
        uow.commit()
    return None


def cancel_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``JOURNAL_EXPORT`` in mode ``CANCEL`` (module docstring): ``result.outcome`` is
    ``CANCELLED``, or ``NOT_CANCELLED`` with the problem as ``result.refusal``. An attempt that
    is run again returns what its job decided (``_decided``)."""
    run_id = UUID(str(params["journal_run_id"]))
    reason = str(params[REASON_PARAM])
    decided = _decided(jc, export.OBJECT_TYPE, run_id, commands.CANCEL_ACTION)
    if decided is not None:
        return _again(jc, run_id, decided, done=CANCELLED, not_done=NOT_CANCELLED)
    with jc.read_session() as session:
        run_no = str(
            session.execute(
                select(journal_run.c.run_no).where(journal_run.c.id == run_id)
            ).scalar_one()
        )
        tenant_code = _tenant_code(session, jc.tenant_id)
        failed = _failed(session, run_id)
    counts = {"asked": 0, "held": 0, "cancelled": 0}
    refused: Problem | None
    try:
        held = _held(jc, failed, tenant_code)
    except _NotAsked as error:
        refused = _state_problem(NOT_ASKED.format(reason=error))
    else:
        counts["asked"] = sum(1 for item in failed if item.context is not None)
        counts["held"] = len(held)
        documents = [_acknowledge(jc, batch, posting) for batch, posting in held]
        if held:
            first = held[0][0]
            refused = _state_problem(
                HELD_NOT_CANCELLED.format(
                    ledger=first.ledger,
                    external_id=first.external_id,
                    document=documents[0],
                    run_no=run_no,
                )
            )
        else:
            cancelled = {**counts, "cancelled": 1}
            refused = _cancel(jc, run_id, reason, failed, cancelled)
            if refused is None:
                return _done(run_id, cancelled, CANCELLED)
    _cancel_denied(jc, run_id, refused, reason, counts)
    return export.Refused(NOT_CANCELLED, refused).job_outcome(jc, run_id, counts)


# --- mode HAND_OVER -------------------------------------------------------------------------------


def _hand_over(jc: JobContext, asked: _Asked, counts: Mapping[str, int]) -> Problem | None:
    """The hand-over itself, in one transaction under the run and batch locks: the recount, the
    file, ``failed`` → ``exported``. The refusal, and nothing written, when the batch is no
    longer what the ledger was asked about or its lines are not the ones it was approved with.
    ``counts`` is what the job ends with when it hands over: the event carries it, with the
    job's id (``_decided``)."""
    with jc.unit_of_work() as uow:
        session = uow.session
        batch = export._locked_batch(session, asked.id)
        if batch is None:
            return _state_problem(NOT_FAILED)
        refused = _batch_standing(session, batch, uow.now) or _sent_meanwhile([batch], [asked])
        if refused is not None:
            return refused
        chunk = export.chunk_of(session, asked.id)
        changed = export.recount(batch, chunk, consequence=LINES_NOT_HANDED_OVER)
        if changed is not None:
            error = ProblemError(field="lines", rule_id=export.RULE_RECOUNT, message=changed)
            return Problem("invalid-transition", changed, errors=[error])
        artifact = export.render_export(chunk)
        export.apply_posting(
            uow,
            batch,
            ports.PostingResult(
                external_id=chunk.external_id,
                status="EXPORTED",
                response_sha256=hashlib.sha256(artifact).hexdigest(),
                message=HANDED_OVER_MESSAGE.format(count=len(chunk.lines)),
                artifact=artifact,
                artifact_name=f"{export.export_name(chunk)}.zip",
            ),
            action=HAND_OVER_ACTION,
            resolution=HANDED_OVER_RESOLUTION,
            decided={"job_id": str(jc.job_id), "counts": dict(counts)},
        )
        uow.commit()
    return None


def hand_over_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``JOURNAL_EXPORT`` in mode ``HAND_OVER`` (module docstring): ``result.outcome`` is
    ``HANDED_OVER``, or ``NOT_HANDED_OVER`` with the problem as ``result.refusal``. An attempt
    that is run again returns what its job decided (``_decided``)."""
    run_id = UUID(str(params["journal_run_id"]))
    batch_id = UUID(str(params[BATCH_PARAM]))
    decided = _decided(jc, export.BATCH_OBJECT, batch_id, HAND_OVER_ACTION)
    if decided is not None:
        return _again(jc, run_id, decided, done=HANDED_OVER, not_done=NOT_HANDED_OVER)
    with jc.read_session() as session:
        tenant_code = _tenant_code(session, jc.tenant_id)
        failed = _failed(session, run_id, batch_id)
    counts = {"asked": 0, "held": 0, "handed_over": 0}
    refused: Problem | None
    if not failed:
        refused = _state_problem(NOT_FAILED)
    elif failed[0].adapter is GlAdapter.CSV:
        refused = _state_problem(CSV_BATCH)
    else:
        [asked] = failed
        try:
            held = _held(jc, failed, tenant_code)
        except _NotAsked as error:
            refused = _state_problem(NOT_ASKED.format(reason=error))
        else:
            counts["asked"], counts["held"] = 1, len(held)
            if held:
                document = _acknowledge(jc, asked, held[0][1])
                refused = _state_problem(
                    HELD_NOT_HANDED_OVER.format(
                        ledger=asked.ledger, external_id=asked.external_id, document=document
                    )
                )
            else:
                handed = {**counts, "handed_over": 1}
                refused = _hand_over(jc, asked, handed)
                if refused is None:
                    return _done(run_id, handed, HANDED_OVER)
    _hand_over_denied(jc, batch_id, refused, counts)
    return export.Refused(NOT_HANDED_OVER, refused).job_outcome(jc, run_id, counts)


export.MODE_HANDLERS[CANCEL] = cancel_job
export.MODE_HANDLERS[HAND_OVER] = hand_over_job
