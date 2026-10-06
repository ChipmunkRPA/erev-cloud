"""Journal run commands (04 §16.7 API-S-JournalRunCreate, "Journal commands", T-SL-06, T-SL-07,
§14.1 DB-16; PRD SM-08, §2.5 routing row ``JOURNAL_RUN``, BR-JE-01; POLICIES POL-005, POL-006;
dev-guide DG-CMD-01 to DG-CMD-08, DG-KRN-APR-01, DG-KRN-JOB-02; BUILD_SPEC CLO-8, CLO-11).

``create_run`` validates the request and defers ``JOURNAL_RUN_CALCULATE``; the job inserts the run
in ``draft`` with its batches, entries and lines (``summarise.calculate_run``). The run id is chosen
here, so the job is idempotent and the command can answer the run id beside the job.

A journal run is neither calculated nor cancelled in a period that is ``closed`` or
``permanently_locked`` (item JR-CLOSED-PERIOD-GUARD-1, ruling R-97 (7); 04 §14.1 DB-07 and §16.7
rev 1.205; PRD ERR-86): the lock certified the period's journal population, and a period needs a
run that is not cancelled to lock. ``create_run`` refuses on a plain read and the job reads the
period again under its state row; ``cancel_run`` reads that row ``FOR SHARE`` after the run row,
the batch rows and the coverage lock (``summarise.refuse_closed_period``), so a lock decision in
flight is waited for and the cancel is then refused. ``create_run`` also refuses a ``future``
period, 422 on ``period_key`` — the guard of PRD SM-08 "Run journals" — and nothing refuses the
cancel of a run that stands in one.

No further run is made without a line (item JRN-EMPTY-RUN-1; 04 §16.7 rev 1.248; PRD ERR-96):
``create_run`` answers 409 by the run's number when a run of the entity, book and period that is
not cancelled stands and the run asked for would hold no line (``summarise.nothing_pending``,
over the lines the calculation itself would read for that mode and cutoff), and the job asks
again under the coverage lock. Those lines include the ones the run would take over — left out
by a run of the key under a journal-export hold that is released since (item
JRN-HELD-AFTER-EXPORT-1; 04 T-SL-06 rev 1.267) — so after a release the command is accepted.
The first run of a period without activity is made — the lock gates need a run — and is the
period's run as it stands: ``submit_run`` refuses a run without lines, so it is never approved
or exported.

``submit_run`` opens a ``JOURNAL_RUN`` request routed to ``journal.approve``. The run stays
``draft`` (label "Submitted", SMAP-06) and records the request. The approval callback moves every
batch and the run to ``approved`` in the deciding transaction, where the DB-16 triggers check that
each batch balances and that the entry numbers have no gap. An approver who ran the calculation is
refused with 403 ``self-approval`` (BR-JE-01), as the engine refuses the submitter. A rejected or
voided request leaves the run ``draft``, so it can be submitted again. ``cancel_run`` cancels a
``draft`` or ``approved`` run with its batches, and voids a pending request with
``SUBJECT_VOIDED``. Three refusals protect what a cancellation cannot take back (BUILD_SPEC
CLO-14): only the latest non-cancelled run of its entity, book and period can be cancelled —
coverage is the highest sealed position of the key, so the seals of an earlier run cancelled under
a later one could never be journalised again (ruling R-52 (b)) — a run is not cancelled while a
relay has claimed the export message of one of its batches (security finding SC-N1, rulings R-32,
R-71 (a) and R-75: the adapter is being called, or was when a relay stopped, and
``export.dispatch_batch`` re-reads the batch under the same row locks; whatever the age of the
claim, the relay that takes the message again completes the export, so the refusal lasts until
the batch is ``exported`` or ``failed``) — and it is not cancelled while such a message is
``FAILED`` and due again (item JRN-CANCEL-APPROVED-PENDING-1, ruling R-119 (c); 04 §16.7 (c)):
the claim is gone and the batch still reads ``approved``, but an attempt was made, a timeout can
follow an acceptance, and only the ledger knows; the next attempt asks it first. A message no
relay has claimed refuses nothing. A run with a ``failed`` batch is ``failed_exits``'s. Each
change raises the row's ``row_version``, because IM-S tables have no touch trigger (DB-02).
Approval also writes one export message per batch (``export.enqueue_run``; ADP-30; BUILD_SPEC
CLO-13).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    JOURNAL_RUNNER_DETAIL,
    SubjectLifecycle,
    register_lifecycle,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id, transitions
from erev_api.db.tables import job, journal_batch, journal_run, legal_entity
from erev_api.domain.contracts.queries import primary_book
from erev_api.domain.journals import export, queries, summarise
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    JobKind,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    OutboxStatus,
    PeriodState,
)
from erev_api.periods import CLOSED_STATES, period_by_key, period_state
from erev_api.problems import Problem, ProblemError
from erev_api.registry.resolve import resolve
from erev_api.schemas.common import JobOut
from erev_api.schemas.journals import (
    JournalRunCancelIn,
    JournalRunCreateIn,
    JournalRunOut,
    JournalRunSubmitIn,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

RUN_PERMISSION: Final = "journal.run"
CREATE_ACTION: Final = "journal_run.request_calculation"
SUBMIT_ACTION: Final = "journal_run.submit"
APPROVE_ACTION: Final = "journal_run.approve"
CANCEL_ACTION: Final = "journal_run.cancel"
OBJECT_TYPE: Final = "journal_run"
BATCH_OBJECT: Final = "journal_batch"
RULE_RUN: Final = "T-SL-06"
RULE_STATES: Final = "E-34"
POSTING_MODE: Final = "je.posting_mode"  # POL-005
SUMMARIZATION: Final = "je.summarization"  # POL-006
UNKNOWN_ENTITY: Final = "No entity has this code."
LEGACY_BOOK: Final = "Journal runs summarise a posting book. Choose ASC606 or IFRS15, not LEGACY."
UNKNOWN_PERIOD: Final = "The entity's calendar has no period with this key."
BOOK_NOT_KEPT: Final = "{entity} keeps no {book} state for {period_key}."
FUTURE_PERIOD: Final = (
    "{period_key} is not open yet for {entity} in book {book}. Open the period before running "
    "journals."
)
NOT_SUBMITTABLE: Final = "Only a calculated journal run can be submitted for approval."
NO_LINES: Final = "Journal run {run_no} has no journal lines: there is nothing to approve."
NOT_APPROVABLE: Final = "Only a calculated journal run can be approved."
NOT_CANCELLABLE: Final = "A journal run can be cancelled only before it is exported."
EXPORT_IN_PROGRESS: Final = (
    "An export of this journal run is in progress: batch {external_id} is being sent. It cannot "
    "be cancelled while a batch is being sent. An interrupted export resumes about 15 minutes "
    "after it stopped."
)
EXPORT_ATTEMPTED: Final = (
    "An export of this journal run is in progress: an attempt to send batch {external_id} failed "
    "and it will be sent again. It cannot be cancelled until the batch has been sent or has "
    "failed."
)
LATER_RUN: Final = (
    "Journal run {run_no} was calculated after this run for the same entity, book and period. "
    "Cancel {run_no} first."
)
RUNNER_DETAIL: Final = JOURNAL_RUNNER_DETAIL  # PRD BR-JE-01 copy, owned by the subject spec
CANCELLABLE: Final = frozenset({JournalState.DRAFT.value, JournalState.APPROVED.value})


def _invalid(field: str, message: str) -> Problem:
    error = ProblemError(field=field, rule_id=RULE_RUN, message=message)
    return Problem("validation-failed", "1 field needs attention.", errors=[error])


def _state_problem(message: str) -> Problem:
    error = ProblemError(field="state", rule_id=RULE_STATES, message=message)
    return Problem("invalid-transition", message, errors=[error])


def _text(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _locked_run(session: Session, run_id: UUID) -> dict[str, Any]:
    """The visible run under ``FOR UPDATE``, else 404 ``not-found``."""
    row = (
        session.execute(select(journal_run).where(journal_run.c.id == run_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _locked_batches(session: Session, run_id: UUID) -> list[Mapping[str, Any]]:
    """The run's batches in batch and chunk order, locked in that order (DG-CMD-02)."""
    return [
        dict(item)
        for item in session.execute(
            select(journal_batch.c.id, journal_batch.c.state, journal_batch.c.row_version)
            .where(journal_batch.c.journal_run_id == run_id)
            .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
            .with_for_update()
        ).mappings()
    ]


def create_run(uow: UnitOfWork, body: JournalRunCreateIn) -> tuple[UUID, JobOut]:
    """``POST /journal-runs``: (run id, API-S-Job of the deferred calculation)."""
    session = uow.session
    found = session.execute(
        select(legal_entity.c.id, legal_entity.c.calendar_id).where(
            legal_entity.c.code == body.entity_code
        )
    ).one_or_none()
    if found is None:
        raise _invalid("entity_code", UNKNOWN_ENTITY)
    entity_id, calendar_id = UUID(str(found[0])), UUID(str(found[1]))
    require_for_entity(uow.ctx, RUN_PERMISSION, entity_id)
    book = body.book if body.book is not None else BookCode(primary_book(session))
    if book is BookCode.LEGACY:
        raise _invalid("book", LEGACY_BOOK)
    try:
        at = period_by_key(session, calendar_id=calendar_id, period_key=body.period_key)
    except LookupError:
        raise _invalid("period_key", UNKNOWN_PERIOD) from None
    try:
        state = period_state(session, entity_id=entity_id, book_code=book, period_id=at.id)
    except LookupError:
        message = BOOK_NOT_KEPT.format(
            entity=body.entity_code, book=book.value, period_key=body.period_key
        )
        raise _invalid("book", message) from None
    if state in CLOSED_STATES:
        # PRD ERR-86, on a plain read: the job reads the period again under its state row
        # (``summarise.calculate``), so a lock decided between the two is not missed.
        raise summarise.period_closed(
            session,
            entity_id=entity_id,
            book_code=book.value,
            period_id=at.id,
            consequence=summarise.NOT_CALCULATED,
            field="period_key",
        )
    if state is PeriodState.FUTURE:
        # PRD SM-08, the guard of "Run journals" (enforced since PRD rev 1.134): no posting can
        # stand in a period that is not open yet, so a run there would have no line.
        message = FUTURE_PERIOD.format(
            period_key=body.period_key, entity=body.entity_code, book=book.value
        )
        raise _invalid("period_key", message)
    mode = body.mode or JournalRunMode(
        str(
            resolve(
                session, POSTING_MODE, book_code=book, entity_id=entity_id, known_at=uow.now
            ).value
        )
    )
    grain = body.grain or JournalRunGrain(
        str(
            resolve(
                session, SUMMARIZATION, book_code=book, entity_id=entity_id, known_at=uow.now
            ).value
        )
    )
    cutoff = body.cutoff_known_at or uow.now
    # PRD ERR-96 (04 §16.7 rev 1.248; item JRN-EMPTY-RUN-1), on a plain read: where a run of the
    # key stands and this one — of its mode, through its cutoff — would hold no line, there is
    # nothing to summarize, and a run without lines would stand after the run it follows. The
    # job asks again under the coverage lock.
    covered = summarise.nothing_pending(
        session,
        entity_id=entity_id,
        book_code=book.value,
        period_id=at.id,
        mode=mode,
        cutoff=cutoff,
        files=uow.files,
        keyring=uow.keyring,
    )
    if covered is not None:
        raise covered
    run_id = new_id()
    params = {
        "journal_run_id": str(run_id),
        "entity_id": str(entity_id),
        "book_code": book.value,
        "period_id": str(at.id),
        "mode": mode.value,
        "grain": grain.value,
        "cutoff_known_at": cutoff.isoformat(),
        "close_run_id": None if body.close_run_id is None else str(body.close_run_id),
    }
    job_row = uow.defer(
        JobKind.JOURNAL_RUN_CALCULATE, params, subject_type=OBJECT_TYPE, subject_id=run_id
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        after={**params, "job_id": str(job_row["id"]), "period_key": body.period_key},
    )
    return run_id, job_out_of(session, UUID(str(job_row["id"])))


# --- approval (SM-08; CLO-11) --------------------------------------------------------------------


def submit_run(uow: UnitOfWork, run_id: UUID, body: JournalRunSubmitIn) -> JournalRunOut:
    """``POST /journal-runs/{id}/submit``: open the ``JOURNAL_RUN`` request of a ``draft`` run."""
    session = uow.session
    row = _locked_run(session, run_id)
    require_for_entity(uow.ctx, RUN_PERMISSION, UUID(str(row["entity_id"])))
    if _text(row["state"]) != JournalState.DRAFT.value:
        raise _state_problem(NOT_SUBMITTABLE)
    if int(row["line_count"]) == 0:
        # 04 §16.7 ``submit`` rev 1.248 (item JRN-EMPTY-RUN-1): the first run of a period without
        # activity is the period's run as it stands; there is nothing a second person could
        # approve, and nothing would leave eRev.
        raise _state_problem(NO_LINES.format(run_no=row["run_no"]))
    shown = queries.run_row(session, run_id)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.JOURNAL_RUN,
        subject_id=run_id,
        summary=(
            f"Approve journal run {row['run_no']} of {shown['entity_code']} "
            f"for {shown['period_name']}"
        ),
        comment=body.comment,
    )
    request_id = UUID(str(request["id"]))
    status = _text(request["status"])
    if status == ApprovalRequestStatus.PENDING.value:
        transitions.apply(
            session,
            OBJECT_TYPE,
            run_id,
            to_status=None,
            expected_status=JournalState.DRAFT.value,
            set_values={
                "approval_request_id": request_id,
                "row_version": int(row["row_version"]) + 1,
                **_stamps(uow),
            },
        )
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        before={"approval_request_id": _text(row["approval_request_id"])},
        after={"approval_request_id": str(request_id), "request_status": status},
        comment=body.comment,
        approval_request_id=request_id,
    )
    return queries.get_run(session, run_id)


def _approved(uow: UnitOfWork, run_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved``: every batch and the run move ``draft`` → ``approved`` in the deciding
    transaction (DB-16). The runner of the calculation cannot approve it, in person or through a
    delegate (BR-JE-01; REQ-PLT-011)."""
    session = uow.session
    row = _locked_run(session, run_id)
    if _text(row["state"]) != JournalState.DRAFT.value:
        raise _state_problem(NOT_APPROVABLE)
    if row["job_id"] is not None:
        # BR-JE-01 under the run lock: no APPROVE decision of this request was taken by the runner
        # or on the runner's behalf (``approvals.approvers_of`` holds approvers and delegators).
        # ``decide`` already refused such a decision (``SubjectSpec.excluded_deciders``); this is
        # the hook's own check of the decisions it is about to apply.
        runner = session.execute(
            select(job.c.created_by).where(job.c.id == row["job_id"])
        ).scalar_one_or_none()
        if runner is not None and UUID(str(runner)) in approvals.approvers_of(
            session, approval_request_id
        ):
            raise Problem("self-approval", RUNNER_DETAIL)
    batches = _locked_batches(session, run_id)
    for batch in batches:
        transitions.apply(
            session,
            BATCH_OBJECT,
            UUID(str(batch["id"])),
            to_status=JournalState.APPROVED.value,
            expected_status=JournalState.DRAFT.value,
            set_values={"row_version": int(batch["row_version"]) + 1, **_stamps(uow)},
        )
    transitions.apply(
        session,
        OBJECT_TYPE,
        run_id,
        to_status=JournalState.APPROVED.value,
        expected_status=JournalState.DRAFT.value,
        set_values={
            "approval_request_id": approval_request_id,
            "approved_at": uow.now,
            "row_version": int(row["row_version"]) + 1,
            **_stamps(uow),
        },
    )
    written = export.enqueue_run(uow, run_id)
    uow.audit(
        action=APPROVE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        before={"state": JournalState.DRAFT.value, "approved_at": None},
        after={
            "state": JournalState.APPROVED.value,
            "approved_at": uow.now,
            "journal_batch_ids": [str(batch["id"]) for batch in batches],
            "export_messages_written": written,
        },
        approval_request_id=approval_request_id,
    )


def _unchanged(_uow: UnitOfWork, _run_id: UUID, _approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided``: the run stays ``draft`` and can be submitted again."""


register_lifecycle(
    ApprovalSubjectType.JOURNAL_RUN,
    SubjectLifecycle(on_approved=_approved, on_rejected=_unchanged, on_voided=_unchanged),
)


def _later_run(session: Session, row: Mapping[str, Any]) -> str | None:
    """The number of the latest non-cancelled run of the same entity, book and period that
    stands after ``row`` — its range starts at or after the end of this run's (DB-16: a run starts
    where the runs it continues end) and it was created later — or None (ruling R-52 (b)). The
    mode is not read: a run of another mode that starts at the key's first seal continues no
    earlier run, and once coverage no longer depends on the mode (ruling R-52 (a)) every later
    run of the key is a continuation."""
    found = session.execute(
        select(journal_run.c.run_no)
        .where(
            journal_run.c.entity_id == row["entity_id"],
            journal_run.c.book_code == row["book_code"],
            journal_run.c.period_id == row["period_id"],
            journal_run.c.id != row["id"],
            journal_run.c.state != JournalState.CANCELLED.value,
            journal_run.c.from_chain_seq >= row["to_chain_seq"],
            # created later; runs of one instant in the order of their numbers (T-PLT-26 pads to
            # six digits, so a longer number is a later one)
            tuple_(
                journal_run.c.created_at, func.length(journal_run.c.run_no), journal_run.c.run_no
            )
            > tuple_(
                literal(row["created_at"], journal_run.c.created_at.type),
                literal(len(str(row["run_no"]))),
                literal(str(row["run_no"])),
            ),
        )
        .order_by(
            journal_run.c.created_at.desc(),
            func.length(journal_run.c.run_no).desc(),
            journal_run.c.run_no.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    return None if found is None else str(found)


def cancel_run(uow: UnitOfWork, run_id: UUID, body: JournalRunCancelIn) -> JournalRunOut:
    """``POST /journal-runs/{id}/cancel``: a ``draft`` or ``approved`` run and its batches become
    ``cancelled``; a pending request is voided with ``SUBJECT_VOIDED`` (PRD SM-08). Refused for a
    run with a later non-cancelled run of its key, while one of its batches is being sent and
    while one waits to be sent again after a failed attempt (module docstring)."""
    session = uow.session
    row = _locked_run(session, run_id)
    require_for_entity(uow.ctx, RUN_PERMISSION, UUID(str(row["entity_id"])))
    state = _text(row["state"])
    batches = _locked_batches(session, run_id)
    if state not in CANCELLABLE or any(_text(item["state"]) not in CANCELLABLE for item in batches):
        raise _state_problem(NOT_CANCELLABLE)
    # The calculation of a run of this key holds the same lock while it reads where the key's
    # runs end: a run it is adding is committed, and seen below, before this cancel decides.
    summarise.lock_coverage(
        session,
        tenant_id=uow.principal.tenant_id,
        entity_id=UUID(str(row["entity_id"])),
        book_code=str(_text(row["book_code"])),
        period_id=UUID(str(row["period_id"])),
    )
    # The period's state row, held from here on (after the run row, the batch rows and the
    # coverage lock; DG-KRN-DB-08 rev 1.188): a lock decision in flight is waited for, and a run
    # of a closed period is not cancelled (PRD ERR-86).
    closed = summarise.refuse_closed_period(
        session,
        entity_id=UUID(str(row["entity_id"])),
        book_code=str(_text(row["book_code"])),
        period_id=UUID(str(row["period_id"])),
        consequence=summarise.NOT_CANCELLED,
    )
    if closed is not None:
        raise closed
    later = _later_run(session, row)
    if later is not None:
        raise _state_problem(LATER_RUN.format(run_no=later))
    # One read of the run's export messages decides both refusals (``export.unsettled``). A
    # message no relay has claimed refuses nothing: nothing was sent for it, and the dispatch
    # re-reads the batch under these locks.
    held = export.unsettled(session, run_id)
    sending = export.first_with(held, OutboxStatus.DISPATCHING)
    if sending is not None:
        raise _state_problem(EXPORT_IN_PROGRESS.format(external_id=sending))
    attempted = export.first_with(held, OutboxStatus.FAILED)
    if attempted is not None:
        raise _state_problem(EXPORT_ATTEMPTED.format(external_id=attempted))
    voided = approvals.void_subject(
        uow, subject_type=ApprovalSubjectType.JOURNAL_RUN, subject_id=run_id, comment=body.reason
    )
    for batch in batches:
        transitions.apply(
            session,
            BATCH_OBJECT,
            UUID(str(batch["id"])),
            to_status=JournalState.CANCELLED.value,
            expected_status=_text(batch["state"]),
            set_values={"row_version": int(batch["row_version"]) + 1, **_stamps(uow)},
        )
    transitions.apply(
        session,
        OBJECT_TYPE,
        run_id,
        to_status=JournalState.CANCELLED.value,
        expected_status=state,
        set_values={
            "cancelled_at": uow.now,
            "row_version": int(row["row_version"]) + 1,
            **_stamps(uow),
        },
    )
    uow.audit(
        action=CANCEL_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        before={"state": state, "cancelled_at": None},
        after={
            "state": JournalState.CANCELLED.value,
            "cancelled_at": uow.now,
            "voided_approval_request_id": None if voided is None else str(voided["id"]),
        },
        comment=body.reason,
    )
    return queries.get_run(session, run_id)
