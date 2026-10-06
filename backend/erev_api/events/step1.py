"""Step 1 readers of a contract's event stream (04 T-CON-01, table 15.4-I ``STEP1_RECORD``, §16.1
``submit-activation``, §16.3, §16.10 ``CONTRACT_ACTIVATION``; PRD SM-02; 03 REQ-CON-004 to
REQ-CON-006, REQ-PLT-014; supervisor rulings R-20 and R-61 on security findings SN-13 / SN-12,
R-77 on the independent review of their fix, and R-102 on the booking a judgement is made on,
the reviewed record and the criteria-met path of a book under an ACTIVE header).

ENGINE_SPEC Table 2.2-A makes a book's status a function of the contract's events, so the control
is who may append the events that move it — and at which dates, because the table reads them in
ENG-06 order (effective date, then record order). These readers say what the stream holds for the
books the contracting entity keeps; they sit below the domain (DG-LAY-03) because every caller must
agree on them: the events route (an assessment names an enabled book; its date; the not-a-contract
gate), the activation checklist and command (``STEP1_RECORD``; the ``CONTRACT_CRITERIA_MET`` events
the approved activation appends), the approval kernel (the ``CONTRACT_ACTIVATION`` subject content
states those events, so a change voids the approval) and the hook that appends a stored event
submission.

- ``enabled_books``: the books enabled for the tenant and kept, enabled, by the entity;
  ``lock_books`` serialises a gate decision with the commands that change them (ruling R-77 (5)).
- ``read``: the non-voided ``COLLECTIBILITY_ASSESSED`` events of the stream; per book the latest
  one in stream order — the preparer's current conclusion, or None once a later
  ``SIGNIFICANT_CHANGE_FLAGGED`` asks for a new one (REQ-CON-004); the stream's activation gate,
  the earliest non-voided ``CONTRACT_ACTIVATED`` in ENG-06 order, where Table 2.2-A leaves DRAFT —
  its date and the time it was written; the date of every Step 1 event with the book it acts in;
  the time the latest standing ``CONTRACT_BOOKED`` was recorded (ruling R-102 (c): a judgement
  is made on the booking it judges); and, per book, the event that put the book out as not
  probable and still holds (``out``; ruling R-102 (a)) — the Step 1 part of Table 2.2-A replayed
  over the stream in ENG-06 order: the activation event that read a not-probable assessment of
  the book, or the not-probable re-assessment that followed a significant-change flag, until a
  ``CONTRACT_CRITERIA_MET`` of the book. The replay reads Step 1 events only; a book the engine
  holds NOT_A_CONTRACT for another reason (no commercial substance, 606-10-25-4) is not in it,
  and the domain confirms every move from the engine's own status trace.
- ``standing``: where that replay leaves one book (item STEP1-HOLD-RELEASE-1; 04 §16.3 (g) rev
  1.209): active — it left DRAFT at an activation event and is not out as not probable — and
  whether a significant-change flag stands that no assessment of the book has followed. Table
  2.2-A moves an active book out only on a not-probable assessment that FOLLOWS such a flag
  (606-10-25-5), so the events route refuses the one that follows none (table 15.4-I
  ``STEP1_CHANGE_NOT_FLAGGED``, PRD IMP-136): it would be recorded and do nothing.
- ``in_force`` / ``every_book_not_probable``: the assessment Table 2.2-A reads at a gate — the
  latest in ENG-06 order at or before it — and ruling R-20 (b) over the enabled books.
- ``latest_date``: the date of the latest Step 1 event that acts in a book; an assessment or a
  flag dated before it would be read BEFORE events already recorded and rewrite the book's history
  (ruling R-77 (1)).
- ``records`` / ``serves`` / ``reviewed``: the judgement record an assessment rests on, read with
  its facts — a record of the contract, of the assessment's book or of no book, of a topic that
  fits the outcome (ruling R-77 (7)): every reader asks the same question.
- ``unmet``: the criteria of 606-10-25-1 a record answers No to that stop an activation (rulings
  R-113 (f), R-115 (f); 04 T-CON-19): (a), (b) or (c) — and (d) for a criteria-met
  re-assessment, where Table 2.2-A does not test commercial substance again. A record without
  the answers (the legacy composer's) stops nothing.
- ``criteria_met``: the books an approved activation moves out of NOT_A_CONTRACT — for a stored
  NOT_A_CONTRACT contract and, since ruling R-102 (a), for a stored ACTIVE one: each enabled book
  that is out as not probable (``out``) and whose latest assessment is probable, dated on or after
  the event that put it out, resting on a COLLECTIBILITY record REVIEWED after that event was
  written (ruling R-77 (3): a new judgement, not the gate's own record); that assessment gives
  ``CONTRACT_CRITERIA_MET`` its effective date (the date the criteria were met, as the preparer
  recorded it) and its record.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db import transitions
from erev_api.db.tables import book, contract_event, entity_book, judgement_record
from erev_api.enums import ContractEventType, ContractStatus, JudgementStatus, JudgementTopic
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.events.stream import EventIn

__all__ = [
    "ACTIVATION_TYPES",
    "ASSESSMENT_TYPES",
    "RECORDED_TYPES",
    "STATUS_TYPES",
    "Assessment",
    "CriteriaMet",
    "PutOut",
    "Record",
    "Standing",
    "Step1Stream",
    "criteria_met",
    "current_at",
    "enabled_books",
    "every_book_not_probable",
    "in_force",
    "latest_date",
    "lock_books",
    "newer",
    "not_probable_books",
    "not_voidable",
    "overtaken",
    "read",
    "records",
    "refuse_stored",
    "reviewed",
    "serves",
    "standing",
    "unmet",
]

# The Step 1 events of E-03 by what a recorder may do with them (04 §16.3).
ASSESSMENT_TYPES: Final = frozenset({ContractEventType.COLLECTIBILITY_ASSESSED})
# Recorded on the events route; their DATE decides what Table 2.2-A reads (ruling R-77 (1)).
RECORDED_TYPES: Final = ASSESSMENT_TYPES | {ContractEventType.SIGNIFICANT_CHANGE_FLAGGED}
# Appended by the approved activation alone (ruling R-20 (c)).
ACTIVATION_TYPES: Final = frozenset(
    {ContractEventType.CONTRACT_CRITERIA_MET, ContractEventType.CONTRACT_ACTIVATED}
)
# Never voided as events: a void would replay Table 2.2-A under the MANUAL_EVENT approval.
STATUS_TYPES: Final = ACTIVATION_TYPES | ASSESSMENT_TYPES
ACTIVATION_ONLY: Final = (
    "{event_type} is recorded by the approved activation. Submit the contract for activation."
)
# Ruling R-77 (1): no later assessment undoes a 606-10-25-5 reassessment of an active contract —
# the approved void of the flag does — so the copy promises a new assessment only where one works.
ASSESSMENT_NOT_VOIDABLE: Final = (
    "A Step 1 assessment is not voided: record a later assessment. On an active contract, a "
    "reassessment that followed a significant-change flag is undone by voiding the flag."
)
ACTIVATION_NOT_VOIDABLE: Final = (
    "An activation event is not voided. A contract assessed as not a contract is activated when "
    "its criteria are met; an activation is reversed by voiding the contract."
)
OWN_REQUEST: Final = "Record the Step 1 assessment in a request of its own."
FLAG_OWN_REQUEST: Final = "Record the significant-change flag in a request of its own."
# The topics a Step 1 assessment may rest on (L4-1-Q-10): not probable needs the NOT_A_CONTRACT
# conclusion (PRD SM-02 guard), probable a COLLECTIBILITY record. Item STEP1-HOLD-RELEASE-1 (04
# §16.3 (b) rev 1.209; the supervisor's ruling of 2026-10-01 on the lane's question 1): before,
# a probable assessment could also rest on a NOT_A_CONTRACT record — a review that answers No to
# criterion (e). The entry said one thing and its evidence the other, and the preparer alone
# ended with it the hold of a reviewed "not a contract" record and cleared a significant-change
# flag. A contract that becomes one later is re-assessed on a NEW reviewed COLLECTIBILITY record
# (606-10-25-6).
NOT_PROBABLE_TOPICS: Final = frozenset({JudgementTopic.NOT_A_CONTRACT.value})
PROBABLE_TOPICS: Final = frozenset({JudgementTopic.COLLECTIBILITY.value})
CRITERIA_MET_TOPIC: Final = JudgementTopic.COLLECTIBILITY.value
# 04 T-CON-19 "Step 1 criteria" and table 15.4-I ``STEP1_CRITERION_NOT_MET`` (PRD IMP-135;
# supervisor rulings R-113 (f), R-115 (f)): the criterion is named by its label — the books may
# differ in framework, the label does not.
CRITERION_LABELS: Final[Mapping[str, str]] = {
    "a": "Approved and committed",
    "b": "Rights identified",
    "c": "Payment terms identified",
    "d": "Commercial substance",
    "e": "Collectibility probable",
}
CRITERION_NOT_MET: Final = (
    "The Step 1 review answers No for {criterion_label}: the contract is not activated until "
    "the criterion is met."
)
# 04 table 15.4-I ``STEP1_CHANGE_NOT_FLAGGED`` (PRD IMP-136; item STEP1-HOLD-RELEASE-1, the
# supervisor's ruling of 2026-10-01 on the lane's question Q-H2): the code is the 422's
# ``errors[].rule_id``.
CHANGE_NOT_FLAGGED: Final = "STEP1_CHANGE_NOT_FLAGGED"
CHANGE_NOT_FLAGGED_MESSAGE: Final = (
    "A not-probable assessment of an active contract takes effect only after a significant "
    "change is flagged. Record the flag first."
)
_NO: Final = "NO"


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def enabled_books(session: Session, entity_id: UUID) -> list[str]:
    """The books enabled for the tenant and the entity, in book-code order."""
    statement = (
        select(entity_book.c.book_code)
        .join(book, book.c.code == entity_book.c.book_code)
        .where(
            entity_book.c.entity_id == entity_id,
            entity_book.c.is_enabled.is_(True),
            book.c.is_enabled.is_(True),
        )
    )
    return sorted({_text(value) for value in session.execute(statement).scalars()})


def lock_books(session: Session) -> None:
    """Ruling R-77 (5): a decision that reads enabled books to decide a not-a-contract gate holds
    every ``book`` row of the tenant ``FOR SHARE`` until it commits. The commands that change what
    ``enabled_books`` answers — ``PUT /entities/{id}/books/{code}`` and ``PATCH /books/{code}`` —
    take the row of their code ``FOR UPDATE`` at their entry, so a book is not kept, re-enabled or
    disabled between the reading and the appended gate, and a book command that waited sees the
    gate. Lock order (DG-KRN-DB-08): after the combination group and contract rows, in code order;
    shared locks do not block each other or the foreign keys that reference a book."""
    session.execute(select(book.c.id).order_by(book.c.code).with_for_update(read=True)).all()


@dataclass(frozen=True, slots=True)
class Assessment:
    """One ``COLLECTIBILITY_ASSESSED`` as ENGINE_SPEC Table 2.2-A reads it: for its book, at its
    ENG-06 position — the effective date, then the record order (``order``: a stored event by
    ``record_seq``; an event of a request after every stored one, in request order)."""

    book: str
    is_probable: bool
    effective_date: date
    order: tuple[int, int]
    judgement_record_id: str | None = None
    # The stored event (T-CON-05 id); None for an event of a request that is not stored yet.
    event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PutOut:
    """The event that put a book out of recognition as NOT_PROBABLE and still holds (ruling R-102
    (a); ENGINE_SPEC Table 2.2-A): the activation event that read a not-probable assessment of the
    book, or the not-probable re-assessment that followed a significant-change flag (606-10-25-5).
    ``recorded_at`` is its T-CON-05 ``created_at`` — the clock a judgement review is stamped with —
    and ``stream_version`` names it in the engine's status trace (``status@<event key>``)."""

    effective_date: date
    recorded_at: datetime
    stream_version: int


@dataclass(frozen=True, slots=True)
class Step1Stream:
    """What a contract's stream holds for Step 1 (module docstring, ``read``)."""

    assessments: tuple[Assessment, ...]  # non-voided, stream order
    latest: Mapping[str, Assessment | None]  # per book; None: reassessment needed
    gate_date: date | None
    # The unit-of-work time the gate was written (T-CON-05 ``created_at``): the clock a judgement
    # review is stamped with (T-CON-19 ``reviewed_at``), so the two compare (ruling R-77 (3)).
    gate_at: datetime | None = None
    # Every non-voided Step 1 event as (the book it acts in, its effective date); None: a
    # ``SIGNIFICANT_CHANGE_FLAGGED`` or ``CONTRACT_ACTIVATED`` acts in every book.
    dated: tuple[tuple[str | None, date], ...] = ()
    # The unit-of-work time the latest standing (non-voided) ``CONTRACT_BOOKED`` was written: a
    # Step 1 judgement is made on the booking it judges (ruling R-102 (c)).
    booked_at: datetime | None = None
    # Per book put out as not probable, by the Step 1 replay of Table 2.2-A (ruling R-102 (a)).
    out: Mapping[str, PutOut] = MappingProxyType({})
    # The standing Step 1 events as the replay reads them (``standing``), in stream order.
    steps: tuple[_Step, ...] = ()


@dataclass(frozen=True, slots=True)
class Standing:
    """Where the Step 1 replay of Table 2.2-A leaves one book (``standing``; item
    STEP1-HOLD-RELEASE-1). ``active``: the book left DRAFT at an activation event and is not out
    as not probable — the replay reads Step 1 events only, so a book the engine holds
    NOT_A_CONTRACT for another reason counts as active here. ``flagged``: a significant-change
    flag stands that no assessment of the book has followed (606-10-25-5: the next not-probable
    assessment of an active book takes it out). ``flagged_at`` (item STEP1-CITE-LATEST-1): the
    time the latest such flag was recorded — its T-CON-05 ``created_at``, the clock a judgement
    review is stamped with; None without a flag, and for a flag of the request that is being
    validated, which is not recorded yet."""

    active: bool
    flagged: bool
    flagged_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CriteriaMet:
    """One book the approved activation of a NOT_A_CONTRACT contract moves (ruling R-20 (c)): the
    ``CONTRACT_CRITERIA_MET`` it appends for the book, from the book's criteria-met
    re-assessment."""

    book: str
    effective_date: date
    judgement_record_id: UUID

    def members(self) -> dict[str, str]:
        """The members the request's subject content and impact preview carry (04 §16.10)."""
        return {
            "book": self.book,
            "effective_date": self.effective_date.isoformat(),
            "judgement_record_id": str(self.judgement_record_id),
        }


@dataclass(frozen=True, slots=True)
class Record:
    """The facts of a judgement record a Step 1 reader decides on (04 T-CON-19)."""

    contract_id: UUID | None
    topic: str
    book: str | None  # None: a record of every book
    status: str
    reviewed_at: datetime | None
    # T-CON-19 ``questionnaire.criteria``: the keys a to e, YES or NO; None when the record
    # carries none (a record written below the route by the legacy composer).
    criteria: Mapping[str, str] | None = None
    # T-CON-19 ``judgement_no``: names the record in the reason of its REQ-POL-010 hold.
    judgement_no: str = ""
    # T-CON-19 ``id`` and the record's subject (``subject_type``, ``subject_id``): two Step 1
    # records are one judgement when they share the subject and the book (``overtaken``).
    id: UUID | None = None
    subject: tuple[str, UUID] | None = None


_STEP1_EVENT_TYPES = (
    ContractEventType.COLLECTIBILITY_ASSESSED.value,
    ContractEventType.SIGNIFICANT_CHANGE_FLAGGED.value,
    ContractEventType.CONTRACT_ACTIVATED.value,
    ContractEventType.CONTRACT_CRITERIA_MET.value,
)
_ASSESSED = ContractEventType.COLLECTIBILITY_ASSESSED.value
_FLAGGED = ContractEventType.SIGNIFICANT_CHANGE_FLAGGED.value
_ACTIVATED = ContractEventType.CONTRACT_ACTIVATED.value
_CRITERIA_MET = ContractEventType.CONTRACT_CRITERIA_MET.value
_BOOKED = ContractEventType.CONTRACT_BOOKED.value


@dataclass(frozen=True, slots=True)
class _Step:
    """One standing Step 1 event as Table 2.2-A reads it (``_put_out``)."""

    kind: str
    book: str | None
    is_probable: bool | None
    effective_date: date
    record_seq: int
    stream_version: int
    created_at: datetime


def _replay(steps: Sequence[_Step], book_code: str) -> tuple[str, _Step | None, _Step | None]:
    """The Step 1 part of ENGINE_SPEC Table 2.2-A for one book, over the standing Step 1 events in
    ENG-06 order (effective date, then record order), as the engine's status machine reads them
    (``erev_engine`` stage 02: the transition first, then the observation). At the first
    ``CONTRACT_ACTIVATED`` the book leaves DRAFT: OUT when the assessment in force is not probable
    (the engine's first test there, reason NOT_PROBABLE), otherwise IN — active, or held for a
    reason this replay cannot see (no commercial substance, 606-10-25-4), which the domain learns
    from the engine. IN, a not-probable assessment of the book behind a significant-change flag
    that no assessment of the book has cleared puts it OUT (606-10-25-5). OUT, the book's
    ``CONTRACT_CRITERIA_MET`` brings it back IN. Answers where the replay ends: the status
    (DRAFT, IN or OUT), the flag that stands — the latest recorded of those no assessment of the
    book has followed, or None — and the event that put the book out, while it is out."""
    status = "DRAFT"
    probable: bool | None = None
    flag: _Step | None = None
    out: _Step | None = None
    for step in sorted(steps, key=lambda item: (item.effective_date, item.record_seq)):
        if step.kind == _ACTIVATED:
            if status == "DRAFT":
                if probable is False:
                    status, out = "OUT", step
                else:
                    status = "IN"
        elif step.kind == _CRITERIA_MET:
            if status == "OUT" and step.book == book_code:
                status, out = "IN", None
        elif step.kind == _ASSESSED and step.book == book_code:
            if status == "IN" and step.is_probable is False and flag is not None:
                status, out = "OUT", step
            probable, flag = step.is_probable, None
        elif step.kind == _FLAGGED and (flag is None or step.created_at >= flag.created_at):
            flag = step
    return status, flag, out


def _put_out(steps: Sequence[_Step], book_code: str) -> PutOut | None:
    """The event that put the book out as not probable, while it is out (``_replay``)."""
    out = _replay(steps, book_code)[2]
    if out is None:
        return None
    return PutOut(
        effective_date=out.effective_date,
        recorded_at=out.created_at,
        stream_version=out.stream_version,
    )


def standing(stream: Step1Stream, book_code: str) -> Standing:
    """Where the replay leaves ``book_code`` over the stored stream (``Standing``): a book
    without an assessment is read too — it is active behind an activation event, and a flag
    stands for it until its first assessment."""
    status, flag, _ = _replay(stream.steps, book_code)
    return Standing(
        active=status == "IN",
        flagged=flag is not None,
        flagged_at=None if flag is None else flag.created_at,
    )


def read(
    session: Session, contract_id: UUID, *, recorded_by: datetime | None = None
) -> Step1Stream:
    """The Step 1 reading of the contract's stream; a voided event counts for nothing. With
    ``recorded_by`` (item RPT-BRIDGE-STEP1-CHAIN-1; the supervisor's ruling of 2026-10-02, the
    cutoff alone) the reading is of the stream as it stood at that time: the events whose
    T-CON-05 ``created_at`` is at or before it. A void is an event of the stream, so it counts
    only when the ``EVENT_VOIDED`` itself was recorded by then — an event voided later still
    stands at the cutoff. The stream is append-only, so the reading at a cutoff is a function of
    the cutoff and of the rows recorded by it. ONE thing can change it after a run has read it:
    a row stamped at or before the cutoff by a unit of work that committed later — the stamp is
    the unit's time, not the commit's. A report run that reads at its bound cutoff binds
    nothing more of the stream, as its ledger columns read ``recorded_at`` against the run's
    time."""
    conditions = [
        contract_event.c.contract_id == contract_id,
        contract_event.c.event_type.in_(
            [*_STEP1_EVENT_TYPES, _BOOKED, ContractEventType.EVENT_VOIDED.value]
        ),
    ]
    if recorded_by is not None:
        conditions.append(contract_event.c.created_at <= recorded_by)
    events = list(
        session.execute(
            select(
                contract_event.c.id,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.record_seq,
                contract_event.c.stream_version,
                contract_event.c.created_at,
                contract_event.c.payload,
                contract_event.c.supersedes_event_id,
            )
            .where(*conditions)
            .order_by(contract_event.c.stream_version)
        ).mappings()
    )
    voided = {row["supersedes_event_id"] for row in events if row["supersedes_event_id"]}
    assessments: list[Assessment] = []
    latest: dict[str, Assessment | None] = {}
    gates: list[tuple[date, int, datetime | None]] = []
    dated: list[tuple[str | None, date]] = []
    steps: list[_Step] = []
    booked_at: datetime | None = None
    for row in events:
        if row["id"] in voided:
            continue
        kind = _text(row["event_type"])
        payload: Mapping[str, Any] = row["payload"] or {}
        if kind == _BOOKED:
            booked_at = row["created_at"]  # stream order: the latest standing booking wins
            continue
        if kind in _STEP1_EVENT_TYPES:
            named = payload.get("book")
            steps.append(
                _Step(
                    kind=kind,
                    book=None if named is None else str(named),
                    is_probable=(bool(payload.get("is_probable")) if kind == _ASSESSED else None),
                    effective_date=row["effective_date"],
                    record_seq=int(row["record_seq"]),
                    stream_version=int(row["stream_version"]),
                    created_at=row["created_at"],
                )
            )
        if kind == ContractEventType.COLLECTIBILITY_ASSESSED.value:
            record_id = payload.get("judgement_record_id")
            found = Assessment(
                book=str(payload.get("book")),
                is_probable=bool(payload.get("is_probable")),
                effective_date=row["effective_date"],
                order=(0, int(row["record_seq"])),
                judgement_record_id=None if record_id is None else str(record_id),
                event_id=UUID(str(row["id"])),
            )
            assessments.append(found)
            latest[found.book] = found
            dated.append((found.book, found.effective_date))
        elif kind == ContractEventType.SIGNIFICANT_CHANGE_FLAGGED.value:
            latest = dict.fromkeys(latest)  # REQ-CON-004: reassessment needed
            dated.append((None, row["effective_date"]))
        elif kind == ContractEventType.CONTRACT_ACTIVATED.value:
            gates.append((row["effective_date"], int(row["record_seq"]), row["created_at"]))
            dated.append((None, row["effective_date"]))
        elif kind == ContractEventType.CONTRACT_CRITERIA_MET.value:
            dated.append((str(payload.get("book")), row["effective_date"]))
    gate = min(gates, key=lambda item: (item[0], item[1])) if gates else None
    out: dict[str, PutOut] = {}
    if gate is not None:
        for book_code in sorted({item.book for item in assessments}):
            found_out = _put_out(steps, book_code)
            if found_out is not None:
                out[book_code] = found_out
    return Step1Stream(
        assessments=tuple(assessments),
        latest=latest,
        gate_date=None if gate is None else gate[0],
        gate_at=None if gate is None else gate[2],
        dated=tuple(dated),
        booked_at=booked_at,
        out=MappingProxyType(out),
        steps=tuple(steps),
    )


def in_force(assessments: Sequence[Assessment], book_code: str, at: date) -> Assessment | None:
    """The assessment of ``book_code`` in force at a gate dated ``at`` and recorded after every one
    of ``assessments``: the latest in ENG-06 order among those effective on or before ``at`` (Table
    2.2-A: "latest ``COLLECTIBILITY_ASSESSED`` for this book at or before the event")."""
    found = [item for item in assessments if item.book == book_code and item.effective_date <= at]
    return max(found, key=lambda item: (item.effective_date, item.order)) if found else None


def every_book_not_probable(
    books: Sequence[str], assessments: Sequence[Assessment], at: date
) -> bool:
    """Ruling R-20 (b): the assessment in force of EVERY enabled book is not probable. A book
    without one, or with a probable one, would be activated by the gate."""
    if not books:
        return False
    for book_code in books:
        found = in_force(assessments, book_code, at)
        if found is None or found.is_probable:
            return False
    return True


def latest_date(dated: Iterable[tuple[str | None, date]], book_code: str | None) -> date | None:
    """Ruling R-77 (1): the effective date of the latest Step 1 event that acts in ``book_code`` —
    its assessments and criteria-met events and every flag and activation event; for ``None`` (an
    event that acts in every book, a ``SIGNIFICANT_CHANGE_FLAGGED``) of any book. Table 2.2-A reads
    the events in ENG-06 order, so an event dated before it would be read before events already
    recorded: a probable assessment slipped between a flag and the not-probable re-assessment
    clears the flag and the book never left ACTIVE; the mirror moves a book out retroactively."""
    found = [
        day
        for acts_in, day in dated
        if book_code is None or acts_in is None or acts_in == book_code
    ]
    return max(found) if found else None


def current_at(stream: Step1Stream, book_code: str, at: date) -> bool:
    """Ruling R-77 (2): the book's latest assessment is the one in force at ``at``. A DRAFT contract
    is activated at its inception date; an assessment dated after it sorts behind the activation
    event, so Table 2.2-A would activate the book on an EARLIER assessment (or on none) against
    the preparer's current, reviewed conclusion."""
    latest = stream.latest.get(book_code)
    return latest is not None and in_force(stream.assessments, book_code, at) == latest


def not_probable_books(stream: Step1Stream, books: Sequence[str]) -> list[str]:
    """The enabled books whose latest assessment is not probable (ruling R-77 (2): an activation
    that leaves such a book NOT_A_CONTRACT is not a standard item and is decided by a person)."""
    found = []
    for book_code in books:
        latest = stream.latest.get(book_code)
        if latest is not None and not latest.is_probable:
            found.append(book_code)
    return found


def records(session: Session, record_ids: Iterable[str | UUID | None]) -> dict[str, Record]:
    """The facts of the named judgement records, by id text; an unknown id is absent."""
    wanted = sorted({UUID(str(value)) for value in record_ids if value is not None})
    if not wanted:
        return {}
    rows = session.execute(
        select(
            judgement_record.c.id,
            judgement_record.c.judgement_no,
            judgement_record.c.contract_id,
            judgement_record.c.topic,
            judgement_record.c.book_code,
            judgement_record.c.status,
            judgement_record.c.reviewed_at,
            judgement_record.c.questionnaire,
            judgement_record.c.subject_type,
            judgement_record.c.subject_id,
        ).where(judgement_record.c.id.in_(wanted))
    ).mappings()
    return {str(row["id"]): _record(row) for row in rows}


def _record(row: Mapping[Any, Any]) -> Record:
    """A stored T-CON-19 row as the readers decide on it; ``questionnaire`` may be unread."""
    return Record(
        contract_id=None if row["contract_id"] is None else UUID(str(row["contract_id"])),
        topic=_text(row["topic"]),
        book=None if row["book_code"] is None else _text(row["book_code"]),
        status=_text(row["status"]),
        reviewed_at=row["reviewed_at"],
        criteria=_criteria(row.get("questionnaire")),
        judgement_no=str(row["judgement_no"]),
        id=UUID(str(row["id"])),
        subject=(str(row["subject_type"]), UUID(str(row["subject_id"]))),
    )


def newer(record: Record, than: Record) -> bool:
    """``record`` was reviewed after ``than`` (item STEP1-CITE-LATEST-1): the later
    ``reviewed_at``, and of two reviews stamped with one instant the higher judgement number.
    Each review is a unit of work of its own, so in a running system no two share an instant;
    the number makes "newest" total where a clock stands still."""
    if record.reviewed_at is None or than.reviewed_at is None:
        return False
    return (record.reviewed_at, record.judgement_no) > (than.reviewed_at, than.judgement_no)


def overtaken(session: Session, known: Iterable[Record]) -> dict[UUID, Record]:
    """By record id, the record that OVERTOOK each REVIEWED Step 1 record of ``known`` (item
    STEP1-CITE-LATEST-1; the supervisor's ruling of 2026-10-02): COLLECTIBILITY and
    NOT_A_CONTRACT are one judgement with two outcomes, so a later review of either overtakes
    an earlier one of the other — of the same subject and the same book, the book read as PRD
    SM-10 reads it for a supersession (an equal book, or none on both; 04 T-CON-20 (c')). The
    answer names the newest such review (``newer``). The overtaken record keeps its status;
    within one topic SM-10 leaves one REVIEWED record, so nothing is said here of a superseded
    one. A record that no later review of the other topic has followed is absent."""
    step1_topics = PROBABLE_TOPICS | NOT_PROBABLE_TOPICS
    wanted = [
        record
        for record in known
        if record.id is not None
        and record.subject is not None
        and record.topic in step1_topics
        and record.status == JudgementStatus.REVIEWED.value
        and record.reviewed_at is not None
    ]
    if not wanted:
        return {}
    subjects = {record.subject for record in wanted if record.subject is not None}
    rows = session.execute(
        select(
            judgement_record.c.id,
            judgement_record.c.judgement_no,
            judgement_record.c.contract_id,
            judgement_record.c.topic,
            judgement_record.c.book_code,
            judgement_record.c.status,
            judgement_record.c.reviewed_at,
            judgement_record.c.subject_type,
            judgement_record.c.subject_id,
        ).where(
            # The key of ``ix_judgement_record__subject``, as a supersession reads a subject.
            judgement_record.c.subject_type.in_(sorted({kind for kind, _ in subjects})),
            judgement_record.c.subject_id.in_(sorted({named for _, named in subjects})),
            judgement_record.c.topic.in_(sorted(step1_topics)),
            judgement_record.c.status == JudgementStatus.REVIEWED.value,
        )
    ).mappings()
    others = [_record(row) for row in rows]
    found: dict[UUID, Record] = {}
    for record in wanted:
        newest: Record | None = None
        for other in others:
            if (
                other.subject == record.subject
                and other.book == record.book
                and other.topic != record.topic
                and newer(other, record)
                and (newest is None or newer(other, newest))
            ):
                newest = other
        if newest is not None and record.id is not None:
            found[record.id] = newest
    return found


def _criteria(questionnaire: Any) -> Mapping[str, str] | None:
    found = questionnaire.get("criteria") if isinstance(questionnaire, Mapping) else None
    if not isinstance(found, Mapping):
        return None
    return {str(key): str(value) for key, value in found.items() if value is not None}


def unmet(
    record: Record | None, *, criteria_met: bool = False, probable: bool = True
) -> tuple[str, ...]:
    """Rulings R-113 (f) and R-115 (f) (04 T-CON-19 "Step 1 criteria"): the criteria the record
    answers No to that stop an activation, in order — (a), (b), (c): the engine models none of
    them, so a review that says the parties have not approved the contract, or that rights or
    payment terms are not identified, carries no probable assessment and no activation. With
    ``criteria_met`` — the re-assessment of a book that is out — also (d): Table 2.2-A tests
    commercial substance at the activation event and not again at ``CONTRACT_CRITERIA_MET``.
    With ``probable`` — the record is read for a PROBABLE assessment, which a criteria-met
    re-assessment always is — also (e) (item STEP1-HOLD-RELEASE-1, the supervisor's ruling of
    2026-10-01 on the lane's question 1): an assessment that says collection is probable does
    not rest on a review that says it is not. A not-probable assessment rests on exactly such a
    record, so (e) is not read for it. A record that carries no answers stops nothing."""
    if record is None or not record.criteria:
        return ()
    keys = ["a", "b", "c"]
    if criteria_met:
        keys.append("d")
    if probable or criteria_met:
        keys.append("e")
    return tuple(key for key in keys if record.criteria.get(key) == _NO)


def serves(record: Record | None, *, contract_id: UUID, book_code: str, probable: bool) -> bool:
    """Ruling R-77 (7): the record is one an assessment of ``book_code`` of this contract with this
    outcome rests on — a record of the contract; of that book or of no book (04 T-CON-19: a record
    without a book is of every book); of topic NOT_A_CONTRACT when not probable and COLLECTIBILITY
    otherwise (``PROBABLE_TOPICS``). The book of a REJECTED record is editable, so a record
    re-reviewed for another book serves nothing in the first."""
    if record is None or record.contract_id != contract_id:
        return False
    if record.book is not None and record.book != book_code:
        return False
    return record.topic in (PROBABLE_TOPICS if probable else NOT_PROBABLE_TOPICS)


def reviewed(record: Record | None, *, contract_id: UUID, book_code: str, probable: bool) -> bool:
    """The record serves the assessment (``serves``) and is REVIEWED."""
    return (
        serves(record, contract_id=contract_id, book_code=book_code, probable=probable)
        and record is not None
        and record.status == JudgementStatus.REVIEWED.value
    )


def criteria_met(
    session: Session, *, contract_id: UUID, status: Any, entity_id: UUID
) -> list[CriteriaMet]:
    """The books an approved activation moves out of NOT_A_CONTRACT, in book order; empty for a
    contract whose stored status is neither NOT_A_CONTRACT nor ACTIVE. A book moves when it is out
    as not probable (``Step1Stream.out``: every assessed book of a contract behind the gate; under
    an ACTIVE header a book the activation left out, or one a 606-10-25-5 reassessment took out —
    ruling R-102 (a)), its latest assessment is probable, dated on or after the event that put it
    out, and rests on a record that serves it, is of topic COLLECTIBILITY and was REVIEWED after
    that event was written (ruling R-77 (3): the criteria are met on a new judgement — not on the
    gate's own NOT_A_CONTRACT record, and not on a collectibility record reviewed before the book
    was found not to be a contract). For an ACTIVE contract this is the platform's reading of the
    Step 1 events; ``activation`` confirms each book from the engine before it submits or
    appends. Item STEP1-CITE-LATEST-1: no book moves on a record that a later NOT_A_CONTRACT
    review has overtaken since the re-assessment was recorded (``overtaken``)."""
    if _text(status) not in (ContractStatus.NOT_A_CONTRACT.value, ContractStatus.ACTIVE.value):
        return []
    stream = read(session, contract_id)
    if not stream.out:
        return []
    known = records(
        session, [item.judgement_record_id for item in stream.latest.values() if item is not None]
    )
    overtaking = overtaken(session, known.values())
    found: list[CriteriaMet] = []
    for code in enabled_books(session, entity_id):
        put_out = stream.out.get(code)
        item = stream.latest.get(code)
        if (
            put_out is None
            or item is None
            or not item.is_probable
            or item.effective_date < put_out.effective_date
        ):
            continue
        record = known.get(str(item.judgement_record_id))
        if (
            record is None
            or not reviewed(record, contract_id=contract_id, book_code=code, probable=True)
            or record.topic != CRITERIA_MET_TOPIC
            or record.reviewed_at is None
            or record.reviewed_at <= put_out.recorded_at
            or unmet(record, criteria_met=True)
            or record.id in overtaking
        ):
            continue
        found.append(
            CriteriaMet(
                book=code,
                effective_date=item.effective_date,
                judgement_record_id=UUID(str(item.judgement_record_id)),
            )
        )
    return found


def not_voidable(event_type: Any) -> str | None:
    """Why an event of ``event_type`` is not voided as an event; None for a type that is."""
    kind = ContractEventType(_text(event_type))
    if kind in ASSESSMENT_TYPES:
        return ASSESSMENT_NOT_VOIDABLE
    if kind in ACTIVATION_TYPES:
        return ACTIVATION_NOT_VOIDABLE
    return None


def refuse_stored(session: Session, events: Sequence[EventIn]) -> None:
    """Ruling R-77 (9): the refusals of rulings R-20 and R-61 (b), applied again by the approval
    hook that appends a stored event submission, under its locks and before its first write. A
    submission is stored at the request and appended at the approval; what it may hold is decided
    at both ends, so a submission stored before a refusal existed — or built below the routes — is
    never appended: no activation event, no Step 1 assessment or significant-change flag (they are
    validated where they are recorded: their record, their book, their date), and no void of an
    assessment or of an activation event. 409 ``invalid-transition``; the decision is not taken."""
    errors: list[ProblemError] = []
    targets = sorted(
        {event.supersedes_event_id for event in events if event.supersedes_event_id is not None}
    )
    voided = (
        {
            UUID(str(row.id)): row.event_type
            for row in session.execute(
                select(contract_event.c.id, contract_event.c.event_type).where(
                    contract_event.c.id.in_(targets)
                )
            )
        }
        if targets
        else {}
    )
    for index, event in enumerate(events):
        field = f"events.{index}.event_type"
        message: str | None = None
        if event.event_type in ACTIVATION_TYPES:
            message = ACTIVATION_ONLY.format(event_type=event.event_type.value)
        elif event.event_type in ASSESSMENT_TYPES:
            message = OWN_REQUEST
        elif event.event_type in RECORDED_TYPES:
            message = FLAG_OWN_REQUEST
        elif event.supersedes_event_id is not None:
            target = voided.get(event.supersedes_event_id)
            message = None if target is None else not_voidable(target)
        if message is not None:
            errors.append(ProblemError(field=field, rule_id=transitions.RULE_ID, message=message))
    if errors:
        raise Problem("invalid-transition", errors[0].message, errors=errors)
