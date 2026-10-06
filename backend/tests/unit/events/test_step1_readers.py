"""Step 1 readers, the header projection of the not-a-contract gate and the refusal of the
activation events (supervisor ruling R-20 on security findings SN-13 / SN-12; 04 E-03, T-CON-01,
§16.1, §16.3 rev 1.105; PRD SM-02 rev 1.34; ENGINE_SPEC Table 2.2-A, ENG-06).

Pure functions only: ``erev_api.events.step1.in_force`` / ``every_book_not_probable`` (what Table
2.2-A reads at a gate, and ruling R-20 (b) over the enabled books), ``events.stream``'s header
projection (a not-probable assessment moves a DRAFT header only as the pair the events route
appends), ``domain.contracts.events.refuse_activation_events`` (R-20 (c)) and the date of the
``CONTRACT_ACTIVATED`` a criteria-met activation appends. The database witnesses are in
``tests/domain/contracts/test_step1.py``.
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.db import transitions
from erev_api.domain.contracts import activation, bundles, repo
from erev_api.domain.contracts import events as contract_events
from erev_api.enums import BookCode, ContractEventType
from erev_api.events import payloads, step1, stream
from erev_api.events.step1 import Assessment, CriteriaMet, Record, Step1Stream
from erev_api.events.stream import EventIn
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendItemIn

RECORD = UUID("01a0f000-0000-7000-8000-000000000001")
GATE_DAY = date(2026, 9, 1)
PASSED = payloads.ChecklistItemV1(code="STEP1_RECORD", passed=True, detail=None)


def _stored(book: str, probable: bool, on: date, seq: int) -> Assessment:
    return Assessment(book=book, is_probable=probable, effective_date=on, order=(0, seq))


def _pending(book: str, probable: bool, on: date, index: int) -> Assessment:
    return Assessment(book=book, is_probable=probable, effective_date=on, order=(1, index))


def _assessed(book: str, *, probable: bool, on: date = GATE_DAY) -> EventIn:
    return EventIn(
        event_type=ContractEventType.COLLECTIBILITY_ASSESSED,
        effective_date=on,
        payload=payloads.CollectibilityAssessedV1(
            book=BookCode(book), is_probable=probable, judgement_record_id=RECORD
        ),
    )


def _activated(on: date = GATE_DAY) -> EventIn:
    return EventIn(
        event_type=ContractEventType.CONTRACT_ACTIVATED,
        effective_date=on,
        payload=payloads.ContractActivatedV1(checklist=(PASSED,)),
    )


def _criteria(book: str, on: date) -> EventIn:
    return EventIn(
        event_type=ContractEventType.CONTRACT_CRITERIA_MET,
        effective_date=on,
        payload=payloads.ContractCriteriaMetV1(book=BookCode(book), judgement_record_id=RECORD),
    )


def _unit() -> Any:
    """``header_projection`` reads ``uow.now`` alone (the status stamps)."""
    return SimpleNamespace(now=datetime(2026, 9, 12, 12, tzinfo=UTC))


# --- Table 2.2-A at a gate: the assessment in force (ENG-06) --------------------------------------


def test_in_force_is_the_latest_assessment_of_the_book_at_or_before_the_gate() -> None:
    earlier = _stored("ASC606", True, date(2026, 8, 20), 5)
    later = _stored("ASC606", False, date(2026, 9, 1), 7)
    other_book = _stored("IFRS15", True, date(2026, 9, 1), 8)
    after_gate = _stored("ASC606", True, date(2026, 9, 2), 9)
    rows = [after_gate, other_book, later, earlier]
    # the effective date first, whatever the record order; a later-dated assessment is not read
    assert step1.in_force(rows, "ASC606", GATE_DAY) is later
    assert step1.in_force(rows, "ASC606", date(2026, 8, 31)) is earlier
    assert step1.in_force(rows, "ASC606", date(2026, 9, 2)) is after_gate
    assert step1.in_force(rows, "IFRS15", GATE_DAY) is other_book
    assert step1.in_force(rows, "IFRS15", date(2026, 8, 31)) is None
    assert step1.in_force(rows, "LEGACY", GATE_DAY) is None


def test_in_force_orders_one_date_by_record_order_and_a_request_after_the_stream() -> None:
    first = _stored("ASC606", True, GATE_DAY, 5)
    second = _stored("ASC606", False, GATE_DAY, 6)
    assert step1.in_force([second, first], "ASC606", GATE_DAY) is second
    # an event of the request sorts after every stored event of its date, in request order
    pending_one = _pending("ASC606", True, GATE_DAY, 0)
    pending_two = _pending("ASC606", False, GATE_DAY, 1)
    rows = [pending_two, second, pending_one, first]
    assert step1.in_force(rows, "ASC606", GATE_DAY) is pending_two
    # … but never before a stored event of a LATER date
    back_dated = _pending("ASC606", True, date(2026, 8, 31), 0)
    assert step1.in_force([second, back_dated], "ASC606", GATE_DAY) is second


def test_ruling_r20_b_every_enabled_book_is_not_probable() -> None:
    asc_not = _stored("ASC606", False, GATE_DAY, 5)
    ifrs_not = _stored("IFRS15", False, GATE_DAY, 6)
    ifrs_probable = _stored("IFRS15", True, GATE_DAY, 6)
    assert step1.every_book_not_probable(["ASC606"], [asc_not], GATE_DAY) is True
    assert step1.every_book_not_probable(["ASC606", "IFRS15"], [asc_not, ifrs_not], GATE_DAY)
    # a book without an assessment, or with a probable one, would be activated by the gate
    assert step1.every_book_not_probable(["ASC606", "IFRS15"], [asc_not], GATE_DAY) is False
    assert not step1.every_book_not_probable(
        ["ASC606", "IFRS15"], [asc_not, ifrs_probable], GATE_DAY
    )
    # SN-13: an assessment that names another book says nothing about the book the entity keeps
    assert step1.every_book_not_probable(["ASC606"], [ifrs_not], GATE_DAY) is False
    # an assessment dated after the gate is not the one the gate reads
    late = _stored("ASC606", False, date(2026, 9, 2), 9)
    assert step1.every_book_not_probable(["ASC606"], [late], GATE_DAY) is False
    # an entity that keeps no enabled book has no gate
    assert step1.every_book_not_probable([], [asc_not], GATE_DAY) is False


# --- T-CON-01 header projection -------------------------------------------------------------------


def test_a_not_probable_assessment_moves_a_draft_header_only_with_the_gate_behind_it() -> None:
    alone = [_assessed("ASC606", probable=False)]
    assert stream.header_projection(_unit(), alone, current_status="DRAFT") == ({}, [])
    # another event between the assessment and a CONTRACT_ACTIVATED is not the pair
    split = [_assessed("ASC606", probable=False), _assessed("IFRS15", probable=True), _activated()]
    values, changes = stream.header_projection(_unit(), split, current_status="DRAFT")
    assert changes == [("DRAFT", "ACTIVE")]  # the projection of an activation, not of the gate
    pair = [_assessed("ASC606", probable=False), _activated()]
    values, changes = stream.header_projection(_unit(), pair, current_status="DRAFT")
    assert changes == [("DRAFT", "NOT_A_CONTRACT")]
    assert values == {"status": "NOT_A_CONTRACT"}  # no activation stamp, no stored checklist
    # a probable assessment never moves the header
    probable = [_assessed("ASC606", probable=True), _activated()]
    _, changes = stream.header_projection(_unit(), probable, current_status="DRAFT")
    assert changes == [("DRAFT", "ACTIVE")]


def test_the_criteria_met_activation_walks_both_sm_02_steps() -> None:
    day = date(2026, 9, 10)
    met = [_criteria("ASC606", day), _criteria("IFRS15", day)]
    values, changes = stream.header_projection(_unit(), met, current_status="NOT_A_CONTRACT")
    assert (values, changes) == (
        {"status": "PENDING_REVIEW"},
        [("NOT_A_CONTRACT", "PENDING_REVIEW")],
    )
    values, changes = stream.header_projection(
        _unit(), [_activated(day)], current_status="PENDING_REVIEW"
    )
    assert changes == [("PENDING_REVIEW", "ACTIVE")]
    assert values["status"] == "ACTIVE" and values["activated_at"] == _unit().now
    # One append would store NOT_A_CONTRACT → ACTIVE, which DB-03 does not hold: two appends.
    pairs = transitions.TRANSITIONS["contract"].pairs
    assert ("NOT_A_CONTRACT", "ACTIVE") not in pairs
    assert {("NOT_A_CONTRACT", "PENDING_REVIEW"), ("PENDING_REVIEW", "ACTIVE")} <= pairs
    # Criteria met says nothing to a contract that is not NOT_A_CONTRACT.
    assert stream.header_projection(_unit(), met, current_status="DRAFT") == ({}, [])
    assert stream.header_projection(_unit(), met, current_status="ACTIVE") == ({}, [])
    # The activation event is inert on a NOT_A_CONTRACT header: only the pair above activates.
    assert stream.header_projection(
        _unit(), [_activated(day)], current_status="NOT_A_CONTRACT"
    ) == ({}, [])


# --- ruling R-20 (c): the events route refuses the activation events ------------------------------


def _item(event_type: ContractEventType) -> EventAppendItemIn:
    return EventAppendItemIn(
        event_type=event_type,
        effective_date="2026-09-10",  # type: ignore[arg-type]
        payload={},
    )


def test_activation_events_are_refused_by_name_for_every_caller() -> None:
    assert contract_events.ACTIVATION_TYPES == {
        ContractEventType.CONTRACT_CRITERIA_MET,
        ContractEventType.CONTRACT_ACTIVATED,
    }
    # neither is a type the route records; the Step 1 type it records is the assessment
    assert not contract_events.ACTIVATION_TYPES & contract_events.RECORDED_TYPES
    assert contract_events.STEP1_TYPES == {ContractEventType.COLLECTIBILITY_ASSESSED}
    assert contract_events.STEP1_TYPES <= contract_events.RECORDED_TYPES
    items = [
        _item(ContractEventType.PAYMENT_RECEIVED),
        _item(ContractEventType.CONTRACT_CRITERIA_MET),
        _item(ContractEventType.CONTRACT_ACTIVATED),
    ]
    with pytest.raises(Problem) as refused:
        contract_events.refuse_activation_events(items)
    problem = refused.value
    assert (problem.slug, problem.status) == ("invalid-transition", 409)
    assert [(error.field, error.rule_id, error.message) for error in problem.errors] == [
        (
            "events.1.event_type",
            "DB-03",
            "CONTRACT_CRITERIA_MET is recorded by the approved activation. "
            "Submit the contract for activation.",
        ),
        (
            "events.2.event_type",
            "DB-03",
            "CONTRACT_ACTIVATED is recorded by the approved activation. "
            "Submit the contract for activation.",
        ),
    ]
    assert problem.detail == problem.errors[0].message
    # the types the route records pass
    contract_events.refuse_activation_events(
        [
            _item(ContractEventType.PAYMENT_RECEIVED),
            _item(ContractEventType.COLLECTIBILITY_ASSESSED),
        ]
    )


def test_the_step1_status_events_are_the_ones_request_void_refuses() -> None:
    assert contract_events.STATUS_TYPES == {
        ContractEventType.COLLECTIBILITY_ASSESSED,
        ContractEventType.CONTRACT_CRITERIA_MET,
        ContractEventType.CONTRACT_ACTIVATED,
    }
    # Ruling R-77 (1): the copy promises a new assessment only where one works, and names the
    # approved void of the flag for a 25-5 reassessment of an active contract.
    assert step1.not_voidable("COLLECTIBILITY_ASSESSED") == step1.ASSESSMENT_NOT_VOIDABLE
    assert "undone by voiding the flag" in step1.ASSESSMENT_NOT_VOIDABLE
    for kind in (ContractEventType.CONTRACT_CRITERIA_MET, ContractEventType.CONTRACT_ACTIVATED):
        assert step1.not_voidable(kind) == step1.ACTIVATION_NOT_VOIDABLE
    # … so the flag itself, like every other recorded event, is voided by the approved request.
    assert step1.not_voidable(ContractEventType.SIGNIFICANT_CHANGE_FLAGGED) is None
    assert step1.not_voidable("PAYMENT_RECEIVED") is None


# --- ruling R-20 (c): the events the approved criteria-met activation appends ---------------------


def test_the_activation_behind_criteria_met_is_dated_the_latest_criteria_met_date() -> None:
    row = {"inception_date": date(2026, 9, 1)}
    checklist = activation.Checklist(
        items=(activation.ChecklistItem(code="STEP1_RECORD", passed=True, detail=None),),
        evaluated_at=_unit().now,
    )
    request_id = UUID("01a0f000-0000-7000-8000-0000000000aa")
    # an ordinary activation: the inception date
    ordinary = activation._activated(row, checklist, request_id)
    assert (ordinary.effective_date, ordinary.approval_request_id) == (date(2026, 9, 1), request_id)
    criteria = [
        CriteriaMet(book="ASC606", effective_date=date(2026, 9, 10), judgement_record_id=RECORD),
        CriteriaMet(book="IFRS15", effective_date=date(2026, 9, 20), judgement_record_id=RECORD),
    ]
    # dated at inception it would sort before the gate and activate from inception (ENG-06)
    behind = activation._activated(row, checklist, request_id, criteria=criteria)
    assert behind.effective_date == date(2026, 9, 20)
    appended = activation._criteria_events(criteria, request_id)
    assert [
        (
            event.event_type,
            event.effective_date,
            payloads.payload_json(event.payload),
            event.approval_request_id,
        )
        for event in appended
    ] == [
        (
            ContractEventType.CONTRACT_CRITERIA_MET,
            date(2026, 9, 10),
            {"book": "ASC606", "judgement_record_id": str(RECORD)},
            request_id,
        ),
        (
            ContractEventType.CONTRACT_CRITERIA_MET,
            date(2026, 9, 20),
            {"book": "IFRS15", "judgement_record_id": str(RECORD)},
            request_id,
        ),
    ]
    assert criteria[0].members() == {
        "book": "ASC606",
        "effective_date": "2026-09-10",
        "judgement_record_id": str(RECORD),
    }


# --- supervisor ruling R-77: dates, records and stored submissions --------------------------------


def test_latest_step1_date_is_per_book_and_flags_and_activations_act_in_every_book() -> None:
    dated = [
        ("ASC606", date(2026, 9, 1)),  # assessment
        (None, date(2026, 9, 1)),  # CONTRACT_ACTIVATED
        (None, date(2026, 9, 5)),  # SIGNIFICANT_CHANGE_FLAGGED
        ("ASC606", date(2026, 9, 8)),  # the 25-5 reassessment
        ("IFRS15", date(2026, 9, 9)),
    ]
    assert step1.latest_date(dated, "ASC606") == date(2026, 9, 8)
    assert step1.latest_date(dated, "IFRS15") == date(2026, 9, 9)
    # a book without an event of its own still has the flag and the activation
    assert step1.latest_date(dated, "LEGACY") == date(2026, 9, 5)
    # a flag acts in every book: it is not dated before the latest event of any of them
    assert step1.latest_date(dated, None) == date(2026, 9, 9)
    assert step1.latest_date([], "ASC606") is None
    assert step1.latest_date([], None) is None


def test_ruling_r77_2_the_latest_assessment_is_the_one_in_force_at_the_inception_date() -> None:
    at_inception = _stored("ASC606", True, GATE_DAY, 5)
    late = _stored("ASC606", False, date(2026, 9, 2), 6)

    def stream_of(*rows: Assessment, latest: Assessment | None) -> Step1Stream:
        return Step1Stream(assessments=rows, latest={"ASC606": latest}, gate_date=None)

    assert step1.current_at(stream_of(at_inception, latest=at_inception), "ASC606", GATE_DAY)
    # dated after inception the latest assessment sorts behind the activation event: the engine
    # would activate on the earlier, probable one …
    assert not step1.current_at(stream_of(at_inception, late, latest=late), "ASC606", GATE_DAY)
    # … or on none at all
    assert not step1.current_at(stream_of(late, latest=late), "ASC606", GATE_DAY)
    # re-dated the inception date, the later record order is in force (ENG-06)
    redone = _stored("ASC606", False, GATE_DAY, 7)
    assert step1.current_at(
        stream_of(at_inception, late, redone, latest=redone), "ASC606", GATE_DAY
    )
    # a flag after the latest assessment asks for a new one; a book without one has none
    assert not step1.current_at(stream_of(at_inception, latest=None), "ASC606", GATE_DAY)
    assert not step1.current_at(stream_of(at_inception, latest=at_inception), "IFRS15", GATE_DAY)


def test_ruling_r77_2_the_books_an_activation_leaves_not_a_contract() -> None:
    probable = _stored("ASC606", True, GATE_DAY, 5)
    not_probable = _stored("IFRS15", False, GATE_DAY, 6)
    stream_ = Step1Stream(
        assessments=(probable, not_probable),
        latest={"ASC606": probable, "IFRS15": not_probable, "LEGACY": None},
        gate_date=None,
    )
    assert step1.not_probable_books(stream_, ["ASC606", "IFRS15", "LEGACY"]) == ["IFRS15"]
    assert step1.not_probable_books(stream_, ["ASC606"]) == []


def test_ruling_r77_7_a_record_serves_its_contract_its_book_and_a_fitting_topic() -> None:
    contract_id = UUID("01a0f000-0000-7000-8000-0000000000c1")
    other = UUID("01a0f000-0000-7000-8000-0000000000c2")
    reviewed_at = datetime(2026, 9, 12, 12, tzinfo=UTC)

    def record(**changes: Any) -> Record:
        members: dict[str, Any] = {
            "contract_id": contract_id,
            "topic": "COLLECTIBILITY",
            "book": "ASC606",
            "status": "REVIEWED",
            "reviewed_at": reviewed_at,
        }
        return Record(**{**members, **changes})

    def serves(found: Record | None, *, book: str = "ASC606", probable: bool = True) -> bool:
        return step1.serves(found, contract_id=contract_id, book_code=book, probable=probable)

    assert serves(record())
    # PRD SM-02: "not probable" rests on the NOT_A_CONTRACT conclusion alone
    assert not serves(record(), probable=False)
    assert serves(record(topic="NOT_A_CONTRACT"), probable=False)
    # Item STEP1-HOLD-RELEASE-1 (04 §16.3 (b) rev 1.209; the supervisor's ruling of 2026-10-01
    # on the lane's question 1): "probable" rests on a COLLECTIBILITY record alone. Before, a
    # NOT_A_CONTRACT record — a review that answers No to criterion (e) — served it too.
    assert not serves(record(topic="NOT_A_CONTRACT"))
    assert not serves(record(topic="CONTRACT_TERM"))
    # 04 T-CON-19: a record without a book is of every book; a record of another book of none
    assert serves(record(book=None), book="IFRS15")
    assert not serves(record(book="IFRS15"))
    # a record of another contract, of no contract, or no record
    assert not serves(record(contract_id=other))
    assert not serves(record(contract_id=None))
    assert not serves(None)
    # reviewed = serves and REVIEWED
    for status, expected in (("REVIEWED", True), ("SUBMITTED", False), ("SUPERSEDED", False)):
        assert (
            step1.reviewed(
                record(status=status), contract_id=contract_id, book_code="ASC606", probable=True
            )
            is expected
        )
    assert not step1.reviewed(
        record(book="IFRS15"), contract_id=contract_id, book_code="ASC606", probable=True
    )


def test_ruling_r77_9_a_stored_submission_holds_no_step1_event() -> None:
    day = date(2026, 9, 10)
    no_session: Any = SimpleNamespace()  # no void among the events: nothing is read
    payment = EventIn(
        event_type=ContractEventType.PAYMENT_RECEIVED,
        effective_date=day,
        payload=payloads.PaymentReceivedV1.model_validate(
            {
                "receipt_reference": "RCPT-1",
                "amount": {"amount": "10.00", "currency": "USD"},
                "receipt_date": "2026-09-10",
            }
        ),
    )
    flag = EventIn(
        event_type=ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
        effective_date=day,
        payload=payloads.SignificantChangeFlaggedV1(description="Downgraded."),
    )
    step1.refuse_stored(no_session, [payment])
    stored = [
        payment,
        _assessed("ASC606", probable=True),
        flag,
        _criteria("ASC606", day),
        _activated(day),
    ]
    with pytest.raises(Problem) as refused:
        step1.refuse_stored(no_session, stored)
    problem = refused.value
    assert (problem.slug, problem.status) == ("invalid-transition", 409)
    assert [(error.field, error.rule_id, error.message) for error in problem.errors] == [
        ("events.1.event_type", "DB-03", "Record the Step 1 assessment in a request of its own."),
        (
            "events.2.event_type",
            "DB-03",
            "Record the significant-change flag in a request of its own.",
        ),
        (
            "events.3.event_type",
            "DB-03",
            "CONTRACT_CRITERIA_MET is recorded by the approved activation. "
            "Submit the contract for activation.",
        ),
        (
            "events.4.event_type",
            "DB-03",
            "CONTRACT_ACTIVATED is recorded by the approved activation. "
            "Submit the contract for activation.",
        ),
    ]
    # the routes no longer store them either
    assert contract_events.STEP1_DATED_TYPES == {
        ContractEventType.COLLECTIBILITY_ASSESSED,
        ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
    }
    # … and no path stores PENDING_REVIEW, so the activation admits only what the routes store.
    # Ruling R-102 (a) adds ACTIVE, for the criteria-met path of a book that is not a contract.
    assert activation.SUBMITTABLE == ("DRAFT", "NOT_A_CONTRACT", "ACTIVE")


def test_ruling_r82_g_the_checklist_copy_is_the_prd_row_imp_131() -> None:
    """The line the Step 1 item shows for an assessment that is not in force at the inception date
    IS PRD §5.5 IMP-131 (a placeholder ``<two words>`` is the template field ``{two_words}``)."""
    prd = (Path(__file__).resolve().parents[4] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-131 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-131", "`STEP1_ASSESSMENT_NOT_IN_FORCE`", "ERROR"]
    copy = cells[3].strip('"')
    assert copy == activation.STEP1_NOT_IN_FORCE_MESSAGE.format(
        book="<book>", inception_date="<inception date>"
    )
    assert activation.STEP1_MESSAGE == "Step 1 review not recorded."  # IMP-105 keeps its copy


# --- supervisor ruling R-102: the booking a judgement is made on, the reviewed record, re-entry ---

CONTRACT = UUID("01a0f000-0000-7000-8000-0000000000c1")
BOOKED_AT = datetime(2026, 9, 12, 12, tzinfo=UTC)


def _record(
    *, status: str = "REVIEWED", topic: str = "COLLECTIBILITY", reviewed_at: datetime | None
) -> Record:
    return Record(
        contract_id=CONTRACT, topic=topic, book="ASC606", status=status, reviewed_at=reviewed_at
    )


def _messages(record: Record, **facts: Any) -> list[str]:
    errors = contract_events._step1_errors(
        0, _assessed("ASC606", probable=True), record, CONTRACT, **facts
    )
    assert {(error.field, error.rule_id) for error in errors} <= {
        ("events.0.payload.judgement_record_id", "REQ-POL-008")
    }
    return [str(error.message) for error in errors]


def test_ruling_r102_b_an_assessment_cites_a_reviewed_record() -> None:
    """Ruling R-102 (b), item STEP1-JR-STALE-1: a record cited while its review was pending made
    that review stale (the ``JUDGEMENT_RECORD`` request pins the contract's head). Every status
    but REVIEWED is refused where the assessment is recorded."""
    for status in ("DRAFT", "SUBMITTED", "REJECTED", "SUPERSEDED"):
        refused = _messages(_record(status=status, reviewed_at=None), booked_at=BOOKED_AT)
        assert refused == ["Use a reviewed judgement record."], status
    assert _messages(_record(reviewed_at=BOOKED_AT), booked_at=BOOKED_AT) == []


def test_ruling_r102_c_the_record_was_reviewed_at_or_after_the_latest_booking() -> None:
    """Ruling R-102 (c), item STEP1-DRAFT-REPLACE-1: a judgement is made on the booking it judges.
    A record reviewed before the latest standing booking was written is not cited again; the
    comparison is not strict, because the legacy composer reviews in the transaction that books.
    Behind an event that put the book out, the review is strictly later (ruling R-77 (3))."""
    before = _record(reviewed_at=BOOKED_AT - timedelta(microseconds=1))
    assert _messages(before, booked_at=BOOKED_AT) == [
        "Use a judgement record reviewed after the draft was last replaced."
    ]
    same_instant = _record(reviewed_at=BOOKED_AT)
    assert _messages(same_instant, booked_at=BOOKED_AT) == []
    # … while "after the gate" stays strict, and is asked of a review that passed the first test
    assert _messages(same_instant, booked_at=BOOKED_AT, gate_at=BOOKED_AT) == [
        "Use a judgement record reviewed after the contract was assessed as not a contract."
    ]
    later = _record(reviewed_at=BOOKED_AT + timedelta(minutes=1))
    assert _messages(later, booked_at=BOOKED_AT, gate_at=BOOKED_AT) == []
    # a stream without a standing booking (none is read) asks nothing of the time
    assert _messages(before, booked_at=None) == []


# The Step 1 alphabet of one book: (kind, book, is_probable).
_SYMBOLS: dict[str, tuple[str, str | None, bool | None]] = {
    "probable": ("COLLECTIBILITY_ASSESSED", "ASC606", True),
    "not-probable": ("COLLECTIBILITY_ASSESSED", "ASC606", False),
    "other-book-not-probable": ("COLLECTIBILITY_ASSESSED", "IFRS15", False),
    "flag": ("SIGNIFICANT_CHANGE_FLAGGED", None, None),
    "activated": ("CONTRACT_ACTIVATED", None, None),
    "criteria-met": ("CONTRACT_CRITERIA_MET", "ASC606", None),
    "other-book-criteria-met": ("CONTRACT_CRITERIA_MET", "IFRS15", None),
}


def _steps(names: tuple[str, ...]) -> list[Any]:
    """The events one per day in the order given: ENG-06 order equals the order of the tuple."""
    found = []
    for index, name in enumerate(names, start=1):
        kind, book, probable = _SYMBOLS[name]
        found.append(
            step1._Step(
                kind=kind,
                book=book,
                is_probable=probable,
                effective_date=GATE_DAY + timedelta(days=index),
                record_seq=index,
                stream_version=index + 1,
                created_at=BOOKED_AT + timedelta(minutes=index),
            )
        )
    return found


def _engine_segment(names: tuple[str, ...]) -> Any:
    """The engine's own Table 2.2-A (stage 02 ``StatusMachine``) over the same events, for a
    contract that has commercial substance and no mutual termination right: its last segment."""
    from erev_engine.stages.s02_contract_identification.status import StatusMachine

    machine = StatusMachine(
        contract_key="K",
        book_code="ASC606",
        header=SimpleNamespace(  # type: ignore[arg-type]
            has_commercial_substance=True, termination_party="NONE", termination_notice_days=None
        ),
        booked_on=GATE_DAY,
        penalty_substantive=False,
        criteria_met_transition="CUMULATIVE_CATCH_UP",
        consideration_nonrefundable=False,
    )
    for index, name in enumerate(names, start=1):
        kind, book, probable = _SYMBOLS[name]
        payload: dict[str, Any] = {} if book is None else {"book": book}
        if probable is not None:
            payload["is_probable"] = probable
        machine.step(
            SimpleNamespace(  # type: ignore[arg-type]
                event_type=kind,
                effective_date=GATE_DAY + timedelta(days=index),
                event_key=f"K/EV-{index + 1:06d}",
                payload=payload,
            )
        )
    return machine.current


def test_ruling_r102_a_the_step1_replay_names_the_event_that_put_a_book_out() -> None:
    """Ruling R-102 (a): ``Step1Stream.out`` — per book, the event that put it out as not probable
    and still holds. The activation event that read a not-probable assessment; the not-probable
    re-assessment behind a flag no assessment of the book has cleared (606-10-25-5); until the
    book's ``CONTRACT_CRITERIA_MET``."""

    def out(*names: str) -> int | None:
        found = step1._put_out(_steps(names), "ASC606")
        return None if found is None else found.stream_version - 1  # the position in ``names``

    assert out("probable", "activated") is None
    assert out("activated") is None  # no assessment: the gate activates the book (R-20 (b))
    assert out("not-probable", "activated") == 2  # … at the activation event
    assert out("not-probable", "activated", "probable") == 2  # a later assessment moves nothing
    assert out("not-probable", "activated", "probable", "criteria-met") is None
    assert out("not-probable", "activated", "other-book-criteria-met") == 2
    # 606-10-25-5 on an active book: the flag, then the not-probable re-assessment
    assert out("probable", "activated", "flag", "not-probable") == 4
    assert out("probable", "activated", "not-probable") is None  # no flag, no move
    assert out("probable", "activated", "flag", "probable", "not-probable") is None  # cleared
    assert out("probable", "activated", "flag", "other-book-not-probable", "not-probable") == 5
    # out, back in by criteria met, and out again by a second reassessment
    again = ("not-probable", "activated", "probable", "criteria-met", "flag", "not-probable")
    assert out(*again) == 6
    # a draft is never out, whatever was assessed
    assert out("not-probable", "flag", "not-probable") is None
    # ENG-06 order decides, not the order of the stream: the same events, given shuffled
    shuffled = _steps(("probable", "activated", "flag", "not-probable"))
    found = step1._put_out(list(reversed(shuffled)), "ASC606")
    assert found is not None and found.stream_version == 5
    assert (found.effective_date, found.recorded_at) == (
        GATE_DAY + timedelta(days=4),
        BOOKED_AT + timedelta(minutes=4),
    )


def test_ruling_r102_a_the_step1_replay_agrees_with_the_engines_status_machine() -> None:
    """The replay is the platform's reading of Step 1 events; Table 2.2-A is the engine's. For a
    contract the engine can only put out as NOT_PROBABLE (commercial substance, no mutual
    termination right) the two agree on EVERY sequence of up to six Step 1 events: the book is out
    exactly when the engine's last segment is NOT_A_CONTRACT / NOT_PROBABLE, and the event the
    replay names is the event that segment began at."""
    checked = 0
    for length in range(1, 7):
        for names in itertools.product(_SYMBOLS, repeat=length):
            segment = _engine_segment(names)
            found = step1._put_out(_steps(names), "ASC606")
            engine_out = (segment.status, segment.reason) == ("NOT_A_CONTRACT", "NOT_PROBABLE")
            assert (found is not None) == engine_out, names
            if found is not None:
                assert segment.from_event_key == f"K/EV-{found.stream_version:06d}", names
            assert segment.status != "NOT_A_CONTRACT" or engine_out, names  # no other reason here
            checked += 1
    assert checked == sum(len(_SYMBOLS) ** length for length in range(1, 7))


def test_ruling_r102_a_the_refusal_copy_is_the_prd_row_imp_133() -> None:
    """The sentence that names a book out for another reason IS PRD §5.5 IMP-133."""
    prd = (Path(__file__).resolve().parents[4] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-133 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-133", "`STEP1_REENTRY_OTHER_REASON`", "ERROR"]
    assert cells[3].strip('"') == activation.STEP1_OTHER_REASON_MESSAGE.format(
        book="<book>", reason="<reason>"
    )
    assert set(activation.OTHER_REASONS) == {
        "NO_COMMERCIAL_SUBSTANCE",
        "MUTUAL_TERMINATION_UNPERFORMED",
    }


def test_ruling_r102_a_status_segments_are_read_from_the_engines_trace() -> None:
    """``activation._segments``: per book the contract's status segments in ENG-06 order, from the
    nodes stage 02 writes (formula ``step1.status.v1``, measure ``status@<event key>``, params
    ``status`` and ``reason``); a node of another member of the group, and any other node, is not
    read."""

    def event(key: str, contract: str, day: int, seq: int, version: int) -> Any:
        return SimpleNamespace(
            event_key=key,
            contract_key=contract,
            effective_date=GATE_DAY + timedelta(days=day),
            record_seq=seq,
            stream_version=version,
        )

    def node(key: str, status: str, reason: str, formula: str = "step1.status.v1") -> Any:
        return SimpleNamespace(
            formula_id=formula, measure=f"status@{key}", params={"status": status, "reason": reason}
        )

    bundle = SimpleNamespace(
        events=(
            event("K/EV-000002", "K", 0, 11, 2),
            event("K/EV-000004", "K", 5, 14, 4),
            event("K/EV-000003", "K", 5, 13, 3),
            event("M/EV-000002", "M", 1, 12, 2),
        )
    )
    trace = SimpleNamespace(
        nodes=(
            node("K/EV-000004", "ACTIVE", "CRITERIA_MET"),
            node("M/EV-000002", "ACTIVE", "ACTIVATED"),
            node("K/EV-000002", "NOT_A_CONTRACT", "NOT_PROBABLE"),
            node("K/EV-000003", "NOT_A_CONTRACT", "NOT_PROBABLE", formula="other.v1"),
        )
    )
    output = SimpleNamespace(books=(SimpleNamespace(book_code="ASC606", trace=trace),))
    found = activation._segments(bundle, output, "K")  # type: ignore[arg-type]
    assert [(row.stream_version, row.status, row.reason) for row in found["ASC606"]] == [
        (2, "NOT_A_CONTRACT", "NOT_PROBABLE"),
        (4, "ACTIVE", "CRITERIA_MET"),
    ]


# --- supervisor rulings R-113 (f), R-115 (f): the five criteria of a Step 1 review ----------------

NOT_MET = (
    "The Step 1 review answers No for {label}: the contract is not activated until the "
    "criterion is met."
)


def _answered(**answers: str) -> Record:
    criteria = {"a": "YES", "b": "YES", "c": "YES", "d": "YES", "e": "YES", **answers}
    return Record(
        contract_id=CONTRACT,
        topic="COLLECTIBILITY",
        book="ASC606",
        status="REVIEWED",
        reviewed_at=BOOKED_AT + timedelta(hours=1),
        criteria=criteria,
    )


def test_ruling_r113_f_a_no_on_a_b_or_c_stops_an_activation_and_d_stops_criteria_met() -> None:
    """``step1.unmet``: the criteria a record answers No to that stop an activation — (a), (b),
    (c), which the engine does not model; and (d) for the re-assessment of a book that is out,
    where Table 2.2-A does not test commercial substance again. Item STEP1-HOLD-RELEASE-1 (the
    supervisor's ruling of 2026-10-01 on the lane's question 1; 04 §16.3 (b) rev 1.209): (e) is
    among them for a PROBABLE assessment — one that says collection is probable does not rest
    on a review that says it is not — and is not read for a not-probable one, which rests on
    exactly such a review. Before that ruling (e) was never among them. A record without the
    answers — the legacy composer's — stops nothing."""
    assert step1.unmet(_answered()) == ()
    assert step1.unmet(_answered(b="NO")) == ("b",)
    assert step1.unmet(_answered(c="NO", a="NO")) == ("a", "c")
    assert step1.unmet(_answered(d="NO")) == ()
    assert step1.unmet(_answered(d="NO"), criteria_met=True) == ("d",)
    assert step1.unmet(_answered(a="NO", d="NO", e="NO"), criteria_met=True) == ("a", "d", "e")
    assert step1.unmet(_answered(e="NO")) == ("e",)
    assert step1.unmet(_answered(e="NO"), probable=False) == ()
    assert step1.unmet(_answered(b="NO", e="NO"), probable=False) == ("b",)
    assert step1.unmet(None) == ()
    assert step1.unmet(_record(reviewed_at=BOOKED_AT)) == ()  # no ``criteria`` at all
    # The copy is PRD IMP-135 and names the criterion by its label.
    prd = (Path(__file__).resolve().parents[4] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-135 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-135", "`STEP1_CRITERION_NOT_MET`", "ERROR"]
    assert cells[3].strip('"') == step1.CRITERION_NOT_MET.format(
        criterion_label="<criterion label>"
    )
    assert [step1.CRITERION_LABELS[key] for key in "abc"] == [
        "Approved and committed",
        "Rights identified",
        "Payment terms identified",
    ]


def test_ruling_r113_f_a_probable_assessment_is_refused_on_a_review_that_answers_no() -> None:
    """``_step1_errors``: a probable assessment names the criterion its record answers No to; a
    not-probable assessment may cite the same record (it serves the gate)."""
    assert _messages(_answered(a="NO", c="NO"), booked_at=BOOKED_AT) == [
        NOT_MET.format(label="Approved and committed"),
        NOT_MET.format(label="Payment terms identified"),
    ]
    # (d) stops the criteria-met re-assessment only
    assert _messages(_answered(d="NO"), booked_at=BOOKED_AT) == []
    assert _messages(_answered(d="NO"), booked_at=BOOKED_AT, gate_at=BOOKED_AT) == [
        NOT_MET.format(label="Commercial substance")
    ]
    not_probable = dataclasses.replace(_answered(a="NO", e="NO"), topic="NOT_A_CONTRACT")
    assert (
        contract_events._step1_errors(
            0, _assessed("ASC606", probable=False), not_probable, CONTRACT, booked_at=BOOKED_AT
        )
        == []
    )


def test_ruling_r113_f_the_answers_are_whole_at_submission_and_e_follows_the_topic() -> None:
    """``policies.judgements.step1_criteria_errors`` without a contract (no (d) to compare): none
    or some answers while a draft, all five at submission; (e) agrees with the topic at every
    write; another topic is not read."""
    from erev_api.domain.policies import judgements
    from erev_api.enums import JudgementTopic

    def found(topic: str, criteria: dict[str, str] | None, *, whole: bool) -> list[tuple[Any, str]]:
        questionnaire = None if criteria is None else {"criteria": criteria}
        errors = judgements.step1_criteria_errors(
            None,  # type: ignore[arg-type]
            JudgementTopic(topic),
            questionnaire,
            None,
            whole=whole,
        )
        assert {error.rule_id for error in errors} <= {"T-CON-19"}
        return [(error.field, str(error.message)) for error in errors]

    all_met = {"a": "YES", "b": "YES", "c": "YES", "d": "YES", "e": "YES"}
    assert found("COLLECTIBILITY", None, whole=False) == []
    assert found("COLLECTIBILITY", {"a": "YES"}, whole=False) == []
    assert found("COLLECTIBILITY", all_met, whole=True) == []
    assert [field for field, _ in found("COLLECTIBILITY", None, whole=True)] == [
        "questionnaire.criteria"
    ]
    assert [field for field, _ in found("COLLECTIBILITY", {"a": "YES"}, whole=True)] == [
        f"questionnaire.criteria.{key}" for key in "bcde"
    ]
    assert [field for field, _ in found("COLLECTIBILITY", {"e": "NO"}, whole=False)] == [
        "questionnaire.criteria.e"
    ]
    assert found("NOT_A_CONTRACT", {**all_met, "e": "NO"}, whole=True) == []
    assert [field for field, _ in found("NOT_A_CONTRACT", all_met, whole=True)] == [
        "questionnaire.criteria.e"
    ]
    assert found("CONTRACT_TERM", None, whole=True) == []


def test_ruling_r102_a_the_engine_confirms_or_refuses_each_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``activation._confirm_reentry`` — the decision table of the criteria-met path under an
    ACTIVE header, on the status segments of the dry run (the Step 1 replay and the enabled books
    are given). A book moves when the pending ``CONTRACT_CRITERIA_MET`` began a CRITERIA_MET
    segment right behind the NOT_PROBABLE segment the replay's event began. Refused by name (PRD
    IMP-133) when a book — moving or not — is out for another reason; refused as unconfirmed when
    the pending event moves nothing or the engine's segment began at another event; and a
    contract of which nothing moves is not submittable."""
    current = {
        "id": CONTRACT,
        "external_id": "K",
        "head_stream_version": 8,
        "contracting_entity_id": CONTRACT,
    }
    moving = [CriteriaMet(book="ASC606", effective_date=GATE_DAY, judgement_record_id=RECORD)]
    put_out = step1.PutOut(effective_date=GATE_DAY, recorded_at=BOOKED_AT, stream_version=5)
    stream = Step1Stream(assessments=(), latest={}, gate_date=GATE_DAY, out={"ASC606": put_out})
    monkeypatch.setattr(step1, "read", lambda session, contract_id: stream)
    monkeypatch.setattr(step1, "enabled_books", lambda session, entity_id: ["ASC606", "IFRS15"])

    def confirm(criteria: list[CriteriaMet], **books: list[tuple[int, str, str]]) -> None:
        segments = {
            code: [activation._Segment(version, status, reason) for version, status, reason in rows]
            for code, rows in books.items()
        }
        monkeypatch.setattr(activation, "_segments", lambda bundle, output, external_id: segments)
        activation._confirm_reentry(
            None,  # type: ignore[arg-type]
            current,
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            criteria,
            now=BOOKED_AT,
        )

    out = (5, "NOT_A_CONTRACT", "NOT_PROBABLE")
    met = (9, "ACTIVE", "CRITERIA_MET")
    active = (3, "ACTIVE", "ACTIVATED")
    confirm(moving, ASC606=[active, out, met], IFRS15=[active])  # the book moves

    def refused(criteria: list[CriteriaMet], **books: list[tuple[int, str, str]]) -> Problem:
        with pytest.raises(Problem) as found:
            confirm(criteria, **books)
        return found.value

    # another reason, for the book that would move: the segment behind the pending event
    substance = (3, "NOT_A_CONTRACT", "NO_COMMERCIAL_SUBSTANCE")
    named = refused(moving, ASC606=[substance, met], IFRS15=[active])
    assert (named.slug, named.status) == ("activation-checklist-failed", 409)
    assert [(error.rule_id, error.message) for error in named.errors] == [
        (
            "STEP1_RECORD",
            "ASC606 is not a contract for a reason other than collectibility (no commercial "
            "substance). Recording criteria met does not activate it.",
        )
    ]
    # … and for a book that would stay: the contract is not served while it stands so
    unperformed = (3, "NOT_A_CONTRACT", "MUTUAL_TERMINATION_UNPERFORMED")
    other = refused(moving, ASC606=[active, out, met], IFRS15=[unperformed])
    assert [error.message for error in other.errors] == [
        "IFRS15 is not a contract for a reason other than collectibility (both parties can end "
        "it without penalty and nothing is performed). Recording criteria met does not activate "
        "it."
    ]
    # the pending event moved nothing
    for rows in ([active, out], [active], [met]):
        unconfirmed = refused(moving, ASC606=rows, IFRS15=[active])
        assert (unconfirmed.slug, unconfirmed.status) == ("invalid-transition", 409)
        assert unconfirmed.detail == activation.NOT_CONFIRMED.format(books="ASC606")
    # the engine's NOT_PROBABLE segment began at another event than the replay's
    elsewhere = refused(moving, ASC606=[active, (6, "NOT_A_CONTRACT", "NOT_PROBABLE"), met])
    assert elsewhere.detail == activation.NOT_CONFIRMED.format(books="ASC606")
    # nothing moves and nothing is out for another reason
    nothing = refused([], ASC606=[active], IFRS15=[active])
    assert (nothing.slug, nothing.detail) == ("invalid-transition", activation.NOT_SUBMITTABLE)
    # nothing moves and a book is out for another reason: by name
    assert refused([], ASC606=[substance]).slug == "activation-checklist-failed"


def test_a_refused_reentry_is_answered_from_what_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``activation._nothing_out`` — the cheap pre-check of ``submit-activation`` under an ACTIVE
    header (ruling R-102 (a), the supervisor's word on the slice: a refusal does not cost a
    computation of the group). What is stored answers that no enabled book is out only when the
    group's versions are the head's (a head computation, not dirty), the Step 1 replay holds no
    enabled book out, and the latest stored version of every enabled book reads another status
    than NOT_A_CONTRACT; the LEGACY book has no contract version and is not asked for one. Every
    other state leaves the answer to the dry run."""
    current = {"id": CONTRACT, "contracting_entity_id": CONTRACT}
    clean: dict[str, Any] = {"head_computation_id": RECORD, "dirty_since": None}
    put_out = step1.PutOut(effective_date=GATE_DAY, recorded_at=BOOKED_AT, stream_version=5)
    asked: list[str] = []

    def answer(
        group: dict[str, Any] = clean,
        books: tuple[str, ...] = ("ASC606", "IFRS15"),
        out: dict[str, step1.PutOut] | None = None,
        **stored: str | None,
    ) -> bool:
        stream = Step1Stream(assessments=(), latest={}, gate_date=GATE_DAY, out=out or {})
        statuses = {"ASC606": "ACTIVE", "IFRS15": "ACTIVE", **stored}

        def previous(session: Any, group_id: UUID, code: str) -> dict[str, Any] | None:
            asked.append(code)
            status = statuses.get(code)
            return None if status is None else {"status_in_book": status}

        asked.clear()
        monkeypatch.setattr(repo, "get_group", lambda session, group_id: group)
        monkeypatch.setattr(step1, "enabled_books", lambda session, entity_id: list(books))
        monkeypatch.setattr(step1, "read", lambda session, contract_id: stream)
        monkeypatch.setattr(bundles, "previous_version", previous)
        return activation._nothing_out(None, CONTRACT, current)  # type: ignore[arg-type]

    assert answer() is True
    assert asked == ["ASC606", "IFRS15"]
    assert answer(ASC606="TERMINATED", IFRS15="DRAFT") is True
    # the stored versions are not the head's: nothing is read from them
    assert answer({**clean, "dirty_since": BOOKED_AT}) is False
    assert answer({**clean, "head_computation_id": None}) is False
    assert asked == []
    # a book out by the Step 1 replay — an enabled one only
    assert answer(out={"IFRS15": put_out}) is False
    assert asked == []
    assert answer(books=("ASC606",), out={"IFRS15": put_out}) is True
    # a book the engine holds out, whatever the reason: the dry run names it
    assert answer(IFRS15="NOT_A_CONTRACT") is False
    assert answer(ASC606="NOT_A_CONTRACT") is False
    # an enabled book without a stored version is not answered by what is stored …
    assert answer(IFRS15=None) is False
    # … except the LEGACY book, which has none by design
    assert answer(books=("ASC606", "IFRS15", "LEGACY")) is True
    assert asked == ["ASC606", "IFRS15"]


# --- item STEP1-HOLD-RELEASE-1 (the supervisor's ruling of 2026-10-01; 04 §16.3 (g) rev 1.209) ----


def _standing(*names: str, book: str = "ASC606") -> tuple[bool, bool]:
    """(active, flagged) of ``book`` behind the events of ``names`` (``step1.standing``)."""
    stream = Step1Stream(assessments=(), latest={}, gate_date=None, steps=tuple(_steps(names)))
    found = step1.standing(stream, book)
    return found.active, found.flagged


def test_step1_hold_release_1_the_replay_says_where_a_book_stands() -> None:
    """``step1.standing``: a book is active once it left DRAFT at an activation event and is not
    out as not probable, and a significant-change flag stands for it until an assessment OF THE
    BOOK follows. The events route asks it before it takes a not-probable assessment of an
    active book (table 15.4-I ``STEP1_CHANGE_NOT_FLAGGED``)."""
    assert _standing() == (False, False)
    assert _standing("probable", "activated") == (True, False)
    assert _standing("activated") == (True, False)  # no assessment: the gate activates the book
    assert _standing("probable", "activated", "flag") == (True, True)
    assert _standing("probable", "activated", "flag", "probable") == (True, False)
    assert _standing("probable", "activated", "flag", "not-probable") == (False, False)
    # another book's assessment answers nothing for this one; a book never assessed is read too
    assert _standing("probable", "activated", "flag", "other-book-not-probable") == (True, True)
    assert _standing("probable", "activated", "flag", book="IFRS15") == (True, True)
    assert _standing("flag", "activated") == (True, True)  # a flag from before the activation
    # out at the activation event, back by criteria met, and a draft is never active
    assert _standing("not-probable", "activated") == (False, False)
    assert _standing("not-probable", "activated", "flag") == (False, True)
    assert _standing("not-probable", "activated", "probable", "criteria-met") == (True, False)
    assert _standing("probable", "flag") == (False, True)


def test_step1_hold_release_1_the_refused_assessment_is_the_one_the_engine_ignores() -> None:
    """The premise of PRD IMP-136 against the engine's own Table 2.2-A (stage 02
    ``StatusMachine``), on EVERY sequence of up to five Step 1 events: where the replay says
    active and not flagged — the case the route refuses — a not-probable assessment appended
    behind the sequence leaves the engine's segment exactly as it was; where it says active and
    flagged, the same assessment takes the book out as NOT_PROBABLE at that very event. So the
    refusal stops an entry that would do nothing, and an admitted one always moves the book."""
    checked = refused = moved = 0
    for length in range(1, 6):
        for names in itertools.product(_SYMBOLS, repeat=length):
            active, flagged = _standing(*names)
            checked += 1
            if not active:
                continue
            before = _engine_segment(names)
            after = _engine_segment((*names, "not-probable"))
            assert before.status == "ACTIVE", names
            if flagged:
                moved += 1
                assert (after.status, after.reason, after.from_event_key) == (
                    "NOT_A_CONTRACT",
                    "NOT_PROBABLE",
                    f"K/EV-{length + 2:06d}",
                ), names
            else:
                refused += 1
                assert (after.status, after.reason, after.from_event_key) == (
                    before.status,
                    before.reason,
                    before.from_event_key,
                ), names
    assert checked == sum(len(_SYMBOLS) ** length for length in range(1, 6))
    assert refused > 0 and moved > 0


def test_step1_hold_release_1_the_refusal_copy_is_the_prd_row_imp_136() -> None:
    """The sentence the events route refuses an unflagged not-probable assessment of an active
    book with IS PRD §5.5 IMP-136, under the code of 04 table 15.4-I."""
    prd = (Path(__file__).resolve().parents[4] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-136 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-136", f"`{step1.CHANGE_NOT_FLAGGED}`", "ERROR"]
    assert cells[3].strip('"') == step1.CHANGE_NOT_FLAGGED_MESSAGE


# --- item STEP1-CITE-LATEST-1 (the supervisor's ruling of 2026-10-02; 04 §16.3 (b)) ---------------

CITED_OVERTAKEN = (
    "This judgement record was overtaken by the review of judgement record {judgement_no}. Use "
    "the latest reviewed Step 1 record."
)
REVIEWED_BEFORE_FLAG = "Use a judgement record reviewed after the significant change was flagged."


def test_step1_cite_latest_1_newer_is_the_later_review_and_on_a_tie_the_higher_number() -> None:
    """``step1.newer``: the order in which two reviews of one judgement are read. Each review is
    a unit of work of its own, so two never share an instant in a running system; where a clock
    stands still the higher judgement number is the newer, so that "newest" is always one
    record."""
    first = dataclasses.replace(_record(reviewed_at=BOOKED_AT), judgement_no="JDG-000001")
    second = dataclasses.replace(_record(reviewed_at=BOOKED_AT), judgement_no="JDG-000002")
    later = dataclasses.replace(first, reviewed_at=BOOKED_AT + timedelta(microseconds=1))
    assert step1.newer(second, first) and not step1.newer(first, second)
    assert step1.newer(later, second) and not step1.newer(
        second, later
    )  # the time, then the number
    assert not step1.newer(first, first)
    unreviewed = dataclasses.replace(first, reviewed_at=None)
    assert not step1.newer(unreviewed, first) and not step1.newer(first, unreviewed)


def test_step1_cite_latest_1_one_finding_about_the_review_of_the_cited_record() -> None:
    """``events._step1_errors`` behind the three findings that were there (not reviewed; before
    the booking; before the gate): a record that serves and was OVERTAKEN is refused by the name
    of the record that overtook it, and a probable assessment that answers a flag is refused on
    a record reviewed before the flag was recorded — not strict, a tie passes — and on any
    record when the flag is of the same request. One finding a record; a record of the wrong
    topic is told its topic and nothing of this; a not-probable assessment is bound by "newest"
    alone."""
    minute = timedelta(minutes=1)
    by = dataclasses.replace(
        _record(topic="NOT_A_CONTRACT", reviewed_at=BOOKED_AT + minute), judgement_no="JDG-000007"
    )
    overtaken = [CITED_OVERTAKEN.format(judgement_no="JDG-000007")]
    cited = _record(reviewed_at=BOOKED_AT)
    assert _messages(cited, overtaken_by=by) == overtaken

    flag_at = BOOKED_AT + 5 * minute
    assert _messages(cited, flag_at=flag_at) == [REVIEWED_BEFORE_FLAG]
    assert _messages(_record(reviewed_at=flag_at), flag_at=flag_at) == []
    assert _messages(_record(reviewed_at=flag_at + minute), flag_at=flag_at) == []
    assert _messages(_record(reviewed_at=flag_at + minute), flag_here=True) == [
        REVIEWED_BEFORE_FLAG
    ]

    # one finding, and the earlier ones of the chain speak first
    waiting = _record(status="SUBMITTED", reviewed_at=None)
    assert _messages(waiting, overtaken_by=by, flag_here=True) == [
        "Use a reviewed judgement record."
    ]
    early = _record(reviewed_at=BOOKED_AT - minute)
    assert _messages(early, booked_at=BOOKED_AT, overtaken_by=by, flag_here=True) == [
        "Use a judgement record reviewed after the draft was last replaced."
    ]
    assert _messages(cited, booked_at=BOOKED_AT, gate_at=BOOKED_AT, overtaken_by=by) == [
        "Use a judgement record reviewed after the contract was assessed as not a contract."
    ]
    assert _messages(cited, overtaken_by=by, flag_at=flag_at) == overtaken

    # a record that does not serve the assessment — the other topic — is told that alone
    wrong = _record(topic="NOT_A_CONTRACT", reviewed_at=BOOKED_AT)
    assert _messages(wrong, overtaken_by=by, flag_here=True) == [
        "Use a judgement record of topic COLLECTIBILITY."
    ]

    def not_probable(**facts: Any) -> list[str]:
        errors = contract_events._step1_errors(
            0,
            _assessed("ASC606", probable=False),
            _record(topic="NOT_A_CONTRACT", reviewed_at=BOOKED_AT),
            CONTRACT,
            **facts,
        )
        return [str(error.message) for error in errors]

    # the flag clause is the probable assessment's: a not-probable one acts on the change
    assert not_probable(flag_at=flag_at) == []
    assert not_probable(flag_here=True) == []
    collectibility = dataclasses.replace(by, topic="COLLECTIBILITY")
    assert not_probable(overtaken_by=collectibility) == overtaken


def test_step1_cite_latest_1_the_standing_names_the_time_of_its_latest_flag() -> None:
    """``Standing.flagged_at``: the time the standing flag was recorded — of several that no
    assessment of the book has followed, the latest; None once an assessment of the book
    answered it, and for a book that was never flagged."""

    def flagged_at(*names: str) -> datetime | None:
        stream = Step1Stream(assessments=(), latest={}, gate_date=None, steps=tuple(_steps(names)))
        found = step1.standing(stream, "ASC606")
        assert found.flagged is (found.flagged_at is not None)
        return found.flagged_at

    def recorded(position: int) -> datetime:
        return BOOKED_AT + timedelta(minutes=position)  # ``_steps``: one minute a step

    assert flagged_at("probable", "activated") is None
    assert flagged_at("probable", "activated", "flag") == recorded(3)
    assert flagged_at("probable", "activated", "flag", "flag") == recorded(4)
    assert flagged_at("probable", "activated", "flag", "probable") is None
    assert flagged_at("probable", "activated", "flag", "other-book-not-probable") == recorded(3)
    assert flagged_at("probable", "activated", "flag", "probable", "flag") == recorded(5)


def test_step1_cite_latest_1_the_checklist_copy_is_the_prd_row_imp_143() -> None:
    """The line the Step 1 item shows for a book whose assessment rests on an overtaken record IS
    PRD §5.5 IMP-143, under the code of 04 table 15.4-I (a placeholder ``<two words>`` is the
    template field ``{two_words}``)."""
    prd = (Path(__file__).resolve().parents[4] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-143 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-143", "`STEP1_RECORD_OVERTAKEN`", "ERROR"]
    assert cells[3].strip('"') == activation.STEP1_OVERTAKEN_MESSAGE.format(
        book="<book>",
        judgement_no="<judgement no>",
        later_judgement_no="<later judgement no>",
    )


def test_step1_cite_latest_1_criteria_met_moves_no_book_on_an_overtaken_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``step1.criteria_met``: a book that is out moves on its probable re-assessment when its
    record was reviewed after the event that put the book out — and not once a later review of
    the other Step 1 topic has overtaken that record (``step1.overtaken``)."""
    put_out = step1.PutOut(effective_date=GATE_DAY, recorded_at=BOOKED_AT, stream_version=3)
    record_id = UUID("01a0f000-0000-7000-8000-0000000000d1")
    item = Assessment(
        book="ASC606",
        is_probable=True,
        effective_date=GATE_DAY + timedelta(days=9),
        order=(0, 4),
        judgement_record_id=str(record_id),
    )
    stream = Step1Stream(
        assessments=(item,), latest={"ASC606": item}, gate_date=GATE_DAY, out={"ASC606": put_out}
    )
    record = dataclasses.replace(_record(reviewed_at=BOOKED_AT + timedelta(hours=1)), id=record_id)
    later = dataclasses.replace(
        _record(topic="NOT_A_CONTRACT", reviewed_at=BOOKED_AT + timedelta(hours=2)),
        judgement_no="JDG-000009",
    )
    overtaking: dict[UUID, Record] = {}
    monkeypatch.setattr(step1, "read", lambda session, contract_id: stream)
    monkeypatch.setattr(step1, "enabled_books", lambda session, entity_id: ["ASC606"])
    monkeypatch.setattr(step1, "records", lambda session, ids: {str(record_id): record})
    monkeypatch.setattr(step1, "overtaken", lambda session, known: overtaking)

    def moved() -> list[str]:
        found = step1.criteria_met(
            None,  # type: ignore[arg-type]
            contract_id=CONTRACT,
            status="NOT_A_CONTRACT",
            entity_id=CONTRACT,
        )
        return [found_item.book for found_item in found]

    assert moved() == ["ASC606"]
    overtaking[record_id] = later
    assert moved() == []
