"""Step 1: contract status machine, collectibility, criteria met and the enforceable term (PRD
SM-02; 04 E-03, T-CON-01, T-CON-19, §16.1 ``submit-activation``, §16.3 ``COLLECTIBILITY_ASSESSED``,
``CONTRACT_CRITERIA_MET``, ``SIGNIFICANT_CHANGE_FLAGGED``, §16.10 ``CONTRACT_ACTIVATION``, table
15.4-I ``STEP1_RECORD``; dev-guide DG-SM-01, DG-SM-03; ENGINE_SPEC Table 2.2-A, S02-R-01 to
S02-R-08; 03 REQ-CON-002 to REQ-CON-006, REQ-CON-013, REQ-PLT-014; BUILD_SPEC CTR-7, CTR-9).

Supervisor ruling R-20 on security findings SN-13 and SN-12 (04 rev 1.105; PRD rev 1.34): no
contract reaches recognition without the activation approval. The engine is a function of the
events (Table 2.2-A), so the witnesses here are about who may append the events that move a book:
an assessment names an enabled book of the contracting entity; the not-a-contract gate follows a
not-probable assessment only when every book the contract is computed in is not probable;
``CONTRACT_CRITERIA_MET`` and ``CONTRACT_ACTIVATED`` are appended by the approved activation alone;
and (d) a book status in {ACTIVE, COMPLETED, TERMINATED} implies an APPROVED
``CONTRACT_ACTIVATION`` request of the contract, the SYSTEM activation path (BS3-D-19) or a
MIGRATION-origin activation — ``_unapproved_recognition`` after every step of the witnesses.

World: ``support.factories.seat_world`` (AVM-US, K-09 ``SF-ORD-10417``: 30 seats × 36 months,
108,000.00 USD from 2026-09-01), with ``STEP1_CHART`` where receipts post to the deposit liability.
Maya (Revenue Accountant) prepares judgement records and records events; Marcus (Controller; MFA)
reviews the records; Priya is given Revenue Reviewer for ``contract.approve``. The computations run
``erev_engine.compute``. The clock stands at 2026-09-12, so September 2026 (FY2026-P09) is open.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.preview import read_preview
from erev_api.approvals.subjects import contract_activation_content
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id, transitions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    contract,
    contract_computation,
    contract_event,
    contract_hold,
    contract_version,
    event_submission,
    job,
    period_lock,
    period_state,
    period_state_transition,
    role,
    role_assignment,
    subledger_line,
)
from erev_api.db.tables import book as book_table
from erev_api.domain.contracts.activation import step1_record
from erev_api.enums import BookCode, ContractEventType, TenantKind
from erev_api.events.payloads import ContractCriteriaMetV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import and_, func, insert, or_, select, text, update
from support.db import TestDatabase
from support.factories import (
    STEP1_CHART,
    J03World,
    SeatWorld,
    activated_contract,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    j03_world,
    k02_body,
    k09_body,
    range_entry,
    seat_world,
    sf_ord_20417_body,
    step1_criteria,
)
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import enrolled, sign_in
from support.principals import workspace as signed_workspace
from support.reference import approve, assign, fields, get, patch, periods, post, put, reject, slug
from support.rows import (
    CloseParts,
    insert_approval_request,
    period_lock_values,
    period_state_transition_values,
)

CONTRACTS = "/api/v1/contracts"
JUDGEMENTS = "/api/v1/judgements"
EVENTS = "/api/v1/contracts/{contract_id}/events"
APPROVAL_HEADER = "x-erev-approval-request"
# E-17 statuses in which a book recognises revenue (REQ-CON-002, V4).
RECOGNISING = frozenset({"ACTIVE", "COMPLETED", "TERMINATED"})
ACTIVATION_ONLY = (
    "{event_type} is recorded by the approved activation. Submit the contract for activation."
)
# PRD IMP-131 ``STEP1_ASSESSMENT_NOT_IN_FORCE`` (rulings R-77 (2), R-82 (g)): the line the Step 1
# item of the checklist shows when a draft's latest assessment is not in force at inception.
NOT_IN_FORCE = (
    "The Step 1 assessment of {book} is not the one in force at the inception date "
    "({inception_date}). Record it again, dated on or before that date."
)
CHECKLIST_CODES = (
    "MANDATORY_FIELDS",
    "SOURCE_REFERENCE",
    "PRODUCT_TEMPLATE_SSP",
    "DISTINCT_REVIEW",
    "COMBINATION_SUGGESTIONS",
    "JUDGEMENT_RECORDS",
    "STEP1_RECORD",
)
RECEIPT = {
    "event_type": "PAYMENT_RECEIVED",
    "effective_date": "2026-09-05",
    "payload": {
        "receipt_reference": "RCPT-US-4410",
        "amount": {"amount": "36000.00", "currency": "USD"},
        "receipt_date": "2026-09-05",
    },
}
# PRD SM-02 as STORED — 04 T-CON-01 ``status`` (rev 1.79; D-98 candidate 143 AMENDMENT 1;
# dev-guide DG-KRN-DB-09 rev 1.70): "DRAFT → PENDING_REVIEW, DRAFT → ACTIVE, PENDING_REVIEW →
# ACTIVE, PENDING_REVIEW → DRAFT, DRAFT → NOT_A_CONTRACT, NOT_A_CONTRACT → PENDING_REVIEW, ACTIVE ↔
# COMPLETED, ACTIVE → TERMINATED, any but VOIDED → VOIDED." (DRAFT, ACTIVE) is the stored form of
# the approved SM-02 activation and of the SYSTEM activation: ``/submit-activation`` appends no
# event (L4-1-Q-18), so the row is DRAFT when ``activate`` writes ACTIVE.
SM_02_PAIRS = frozenset(
    {
        ("DRAFT", "PENDING_REVIEW"),
        ("DRAFT", "ACTIVE"),
        ("PENDING_REVIEW", "ACTIVE"),
        ("PENDING_REVIEW", "DRAFT"),
        ("DRAFT", "NOT_A_CONTRACT"),
        ("NOT_A_CONTRACT", "PENDING_REVIEW"),
        ("ACTIVE", "COMPLETED"),
        ("COMPLETED", "ACTIVE"),
        ("ACTIVE", "TERMINATED"),
        *(
            (status, "VOIDED")
            for status in (
                "DRAFT",
                "PENDING_REVIEW",
                "NOT_A_CONTRACT",
                "ACTIVE",
                "COMPLETED",
                "TERMINATED",
            )
        ),
    }
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(
        app, keyring, clock, LocalFileStore(app_settings.file_root), chart=STEP1_CHART
    )


def _k09(world: SeatWorld, **extra: Any) -> UUID:
    body = {**k09_body(world.customers["C-09"]), **extra}
    booked = booked_contract(world.place, body, activate=False)
    return UUID(str(booked.contract["id"]))


def _record(
    world: SeatWorld,
    contract_id: UUID,
    topic: str,
    questionnaire: dict[str, Any] | None = None,
    *,
    book: str | None = "ASC606",
    submit: bool = True,
) -> tuple[str, str | None]:
    """A judgement record Maya prepares and, with ``submit``, sends for review; returns its id
    and the id of its ``JUDGEMENT_RECORD`` request. A Step 1 record carries the five criteria
    (supervisor rulings R-113 (f), R-115 (f)): met but for (e), which follows the topic, unless
    ``questionnaire`` states its own ``criteria``."""
    body: dict[str, Any] = {
        "topic": topic,
        "subject_type": "contract",
        "subject_id": str(contract_id),
        "conclusion": f"{topic} assessed for SF-ORD-10417.",
        "rationale": "Credit review of Orrin Vale Architects LLP and the contract terms.",
    }
    if book is not None:
        body["book"] = book
    if topic in ("COLLECTIBILITY", "NOT_A_CONTRACT"):
        questionnaire = {"criteria": step1_criteria(topic), **(questionnaire or {})}
    if questionnaire is not None:
        body["questionnaire"] = questionnaire
    created = post(world.app, JUDGEMENTS, world.place.author, body)
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    if not submit:
        return record_id, None
    submitted = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    return record_id, str(submitted.json()["approval_request_id"])


def _reviewed(
    world: SeatWorld,
    contract_id: UUID,
    topic: str,
    questionnaire: dict[str, Any] | None = None,
    *,
    book: str | None = "ASC606",
) -> str:
    """A judgement record Maya prepares and Marcus reviews; returns its id. The review precedes
    any event that cites the record: the ``JUDGEMENT_RECORD`` request pins the contract's head (04
    §16.10), so an event appended while the review is pending makes it stale."""
    record_id, request_id = _record(world, contract_id, topic, questionnaire, book=book)
    assert request_id is not None
    approved = approve(world.app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    return record_id


def _append(world: SeatWorld, contract_id: UUID, head: int, *items: dict[str, Any]) -> Any:
    return post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": list(items)},
        if_match=f'"s{head}"',
    )


def _assessment(
    record_id: str, *, probable: bool, on: str = "2026-09-01", book: str = "ASC606"
) -> dict[str, Any]:
    return {
        "event_type": "COLLECTIBILITY_ASSESSED",
        "effective_date": on,
        "payload": {"book": book, "is_probable": probable, "judgement_record_id": record_id},
    }


def _criteria_met(record_id: str, *, on: str = "2026-09-10") -> dict[str, Any]:
    return {
        "event_type": "CONTRACT_CRITERIA_MET",
        "effective_date": on,
        "payload": {"book": "ASC606", "judgement_record_id": record_id},
    }


def _created(world: SeatWorld, customer: str = "C-09", external_id: str | None = None) -> UUID:
    """K-09 booked by Maya through the API (a manual contract: routing flag ``MANUAL_ENTRY``)."""
    body = k09_body(world.customers[customer])
    if external_id is not None:
        body["external_id"] = external_id
        body["document_ref"] = external_id
    drafted = post(world.app, CONTRACTS, world.place.author, body)
    assert drafted.status_code == 201, drafted.text
    return UUID(str(drafted.json()["id"]))


def _head(world: SeatWorld, contract_id: UUID) -> int:
    return _header(world, contract_id)[1]


def _record_events(world: SeatWorld, contract_id: UUID, *items: dict[str, Any]) -> Any:
    return _append(world, contract_id, _head(world, contract_id), *items)


def _gated(world: SeatWorld, contract_id: UUID, *, on: str = "2026-09-01") -> str:
    """The contract brought to NOT_A_CONTRACT: a reviewed NOT_A_CONTRACT record and the
    not-probable assessment behind which the route appends the gate; returns the record id."""
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", {"consideration_nonrefundable": False})
    assessed = _record_events(world, contract_id, _assessment(record, probable=False, on=on))
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert assessed.json()["step1_gate"] == {"appended": True, "reason": None}
    _later(world)
    return record


def _later(world: SeatWorld) -> None:
    """Time passes. The criteria-met record is REVIEWED AFTER the gate was written (ruling R-77
    (3)); the clock of these witnesses stands still unless moved."""
    world.place.clock.advance(timedelta(minutes=1))


def _submit(world: SeatWorld, contract_id: UUID) -> Any:
    return post(
        world.app,
        f"{CONTRACTS}/{contract_id}/submit-activation",
        world.place.author,
        {"comment": "Collection is now probable."},
        if_match=f'"s{_head(world, contract_id)}"',
    )


def _checklist(world: SeatWorld, contract_id: UUID) -> dict[str, bool]:
    shown = get(world.app, f"{CONTRACTS}/{contract_id}/activation-checklist", world.place.author)
    assert shown.status_code == 200, shown.text
    return {item["code"]: item["passed"] for item in shown.json()["items"]}


def _read_status(world: SeatWorld, contract_id: UUID) -> str:
    shown = get(world.app, f"{CONTRACTS}/{contract_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return str(shown.json()["status"])


# Item ACT-FLAGS-1 (04 §16.10 rev 1.287; the supervisor's ruling of 2026-10-02, conditions 2 and
# 3): the flags of K-09's activation as Maya books it — 108,000.00 USD by a person, a booking
# that states neither of the two terms (the booking form does not state them yet), and a product
# of which no other activated contract of this workspace holds a line.
K09_FLAGS = ["ABOVE_THRESHOLD", "MANUAL_ENTRY", "NEW_SKU", "TERMS_NOT_STATED"]


def _activation_requests(world: SeatWorld, contract_id: UUID) -> list[tuple[str, list[str]]]:
    rows = world.place.rows(
        select(approval_request.c.status, approval_request.c.flags)
        .where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == contract_id,
        )
        .order_by(approval_request.c.request_no)
    )
    return [(str(row["status"]), list(row["flags"])) for row in rows]


def _stream(world: SeatWorld, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.origin,
            contract_event.c.created_by_kind,
            contract_event.c.approval_request_id,
            contract_event.c.payload,
            contract_event.c.supersedes_event_id,
        )
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def _books(world: SeatWorld, contract_id: UUID) -> dict[str, tuple[str, Decimal]]:
    """Book → (status, cumulative revenue) of the contract's latest version in that book. The
    contracts of these witnesses are singleton groups, so the group's version is the contract's."""
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    rows = world.place.rows(
        select(
            contract_version.c.book_code,
            contract_version.c.status_in_book,
            contract_version.c.revenue_cum,
        )
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no)
    )
    return {
        str(row["book_code"]): (str(row["status_in_book"]), Decimal(row["revenue_cum"]))
        for row in rows
    }


def _posted(world: SeatWorld, contract_id: UUID) -> dict[tuple[str, str, str], Decimal]:
    """(book, account role, D or C) → the posted transaction amount, unsigned."""
    rows = world.place.rows(
        select(
            subledger_line.c.book_code,
            subledger_line.c.account_role,
            subledger_line.c.dr_cr,
            func.sum(subledger_line.c.amount_txn).label("total"),
        )
        .where(subledger_line.c.contract_id == contract_id)
        .group_by(subledger_line.c.book_code, subledger_line.c.account_role, subledger_line.c.dr_cr)
    )
    return {
        (str(row["book_code"]), str(row["account_role"]), str(row["dr_cr"])): abs(
            Decimal(row["total"])
        )
        for row in rows
    }


def _recognition(world: SeatWorld) -> list[tuple[str, str, str]]:
    """(external id, book, status) of every contract of the world a book recognises in."""
    found: list[tuple[str, str, str]] = []
    rows = world.place.rows(
        select(contract.c.id, contract.c.external_id).order_by(contract.c.external_id)
    )
    for row in rows:
        for book, (status, _) in sorted(_books(world, row["id"]).items()):
            if status in RECOGNISING:
                found.append((str(row["external_id"]), book, status))
    return found


def _unapproved_recognition(world: SeatWorld) -> list[tuple[str, str, str]]:
    """Ruling R-20 (d): the recognising (contract, book) pairs WITHOUT an APPROVED
    ``CONTRACT_ACTIVATION`` request of the contract, a ``CONTRACT_ACTIVATED`` appended by the
    SYSTEM principal (the approved activation; the BS3-D-19 path of ``activated_contract``) or a
    MIGRATION-origin activation. The invariant says this list is empty; the gate the events route
    appends for the recording principal is no such evidence."""
    found: list[tuple[str, str, str]] = []
    ids = {
        str(row["external_id"]): row["id"]
        for row in world.place.rows(select(contract.c.id, contract.c.external_id))
    }
    for external_id, book, status in _recognition(world):
        contract_id = ids[external_id]
        approved = world.place.scalar(
            select(func.count())
            .select_from(approval_request)
            .where(
                approval_request.c.subject_type == "CONTRACT_ACTIVATION",
                approval_request.c.subject_id == contract_id,
                approval_request.c.status == "APPROVED",
            )
        )
        system = world.place.scalar(
            select(func.count())
            .select_from(contract_event)
            .where(
                contract_event.c.contract_id == contract_id,
                contract_event.c.event_type == "CONTRACT_ACTIVATED",
                or_(
                    and_(
                        contract_event.c.created_by_kind == "SYSTEM",
                        contract_event.c.origin == "SYSTEM",
                    ),
                    contract_event.c.origin == "MIGRATION",
                ),
            )
        )
        if not approved and not system:
            found.append((external_id, book, status))
    return found


def _preview_document(world: SeatWorld, request_id: str) -> dict[str, Any]:
    """The stored ``IMPACT_PREVIEW`` document the request hashes (04 §16.10)."""
    with world.place.uow() as uow:
        file_id = uow.session.execute(
            select(approval_request.c.impact_preview_file_id).where(
                approval_request.c.id == UUID(request_id)
            )
        ).scalar_one()
        return read_preview(uow.session, file_id, files=uow.files, keyring=uow.keyring)


def _keep_ifrs15(world: SeatWorld) -> None:
    """AVM-US keeps a second book (``PUT /entities/{id}/books/IFRS15``)."""
    kept = put(
        world.app,
        f"/api/v1/entities/{world.entity_id}/books/IFRS15",
        world.marcus,
        {"is_enabled": True},
    )
    assert kept.status_code == 200, kept.text


def _header(world: SeatWorld, contract_id: UUID) -> tuple[str, int]:
    row = world.place.rows(
        select(contract.c.status, contract.c.head_stream_version).where(
            contract.c.id == contract_id
        )
    )[0]
    return str(row["status"]), int(row["head_stream_version"])


def _event_types(world: SeatWorld, contract_id: UUID) -> list[str]:
    rows = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [str(row["event_type"]) for row in rows]


def _status_audits(world: SeatWorld, contract_id: UUID) -> list[tuple[str, str, str]]:
    rows = world.place.rows(
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.object_type == "contract",
            audit_event.c.before.is_not(None),
        )
    )
    return sorted(
        (str(row["action"]), row["before"]["status"], row["after"]["status"])
        for row in rows
        if "status" in (row["before"] or {})
    )


def _audited_gates(world: SeatWorld, contract_id: UUID) -> list[Any]:
    """Ruling R-84 (b): ``step1_gate`` in the audit detail of each ``contract.record_events`` of
    the contract, in stream order — the two members the answer carries; None for a request that
    decided no gate."""
    rows = world.place.rows(
        select(audit_event.c.object_version, audit_event.c.detail).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.object_type == "contract",
            audit_event.c.action == "contract.record_events",
        )
    )
    ordered = sorted(rows, key=lambda row: int(row["object_version"]))
    return [(row["detail"] or {}).get("step1_gate") for row in ordered]


def _step1(world: SeatWorld, contract_id: UUID) -> tuple[bool, str | None]:
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        row = session.execute(select(contract).where(contract.c.id == contract_id)).mappings().one()
        item = step1_record(session, row)
    assert item.code == "STEP1_RECORD"
    return item.passed, item.detail


def test_contract_transitions_equal_sm_02(world: SeatWorld) -> None:
    spec = transitions.TRANSITIONS["contract"]
    assert (spec.status_column, spec.pairs, spec.editable_while) == (
        "status",
        SM_02_PAIRS,
        frozenset({"DRAFT"}),
    )
    assert len(spec.pairs) == 15  # the nine named moves and the six "any but VOIDED → VOIDED"
    # DG-SM-02: a pair outside SM-02 is refused in Python before any SQL.
    refused = transitions.violations(
        spec, to_status="ACTIVE", set_values={}, expected_status="NOT_A_CONTRACT"
    )
    assert [(error.field, error.rule_id) for error in refused] == [("status", "DB-03")]

    # DG-SM-03: every status change writes contract.<status lowercase>. SM-02 NOT_A_CONTRACT →
    # PENDING_REVIEW is the submission of the criteria-met activation (ruling R-20 (c); PRD rev
    # 1.34): the events route no longer records ``CONTRACT_CRITERIA_MET``.
    not_probable = _k09(world)
    record = _reviewed(
        world, not_probable, "NOT_A_CONTRACT", {"consideration_nonrefundable": False}
    )
    assessed = _append(world, not_probable, 1, _assessment(record, probable=False))
    assert assessed.status_code == 201, assessed.text
    _later(world)  # ruling R-77 (3): the criteria-met record is reviewed after the gate
    met = _reviewed(world, not_probable, "COLLECTIBILITY")
    reassessed = _append(world, not_probable, 3, _assessment(met, probable=True, on="2026-09-10"))
    assert reassessed.status_code == 201, reassessed.text
    submitted = _submit(world, not_probable)
    assert submitted.status_code == 200, submitted.text
    assert _status_audits(world, not_probable) == [
        ("contract.not_a_contract", "DRAFT", "NOT_A_CONTRACT"),
        ("contract.pending_review", "NOT_A_CONTRACT", "PENDING_REVIEW"),
    ]

    booked = booked_contract(world.place, k02_body(world.customers["C-02"]), activate=False)
    activated_contract(world.place, booked)
    assert _status_audits(world, UUID(str(booked.contract["id"]))) == [
        ("contract.active", "DRAFT", "ACTIVE")
    ]


def test_not_probable_sets_not_a_contract_and_deposits(world: SeatWorld) -> None:
    contract_id = _k09(world)
    # A COLLECTIBILITY record cannot carry "not probable" (PRD SM-02 guard). It is reviewed
    # first: the later review of either Step 1 topic overtakes the other (item
    # STEP1-CITE-LATEST-1), and the assessment below cites the newest.
    evidence = _reviewed(world, contract_id, "COLLECTIBILITY")
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", {"consideration_nonrefundable": False})
    wrong = _append(world, contract_id, 1, _assessment(evidence, probable=False))
    assert wrong.status_code == 422, wrong.text
    assert fields(wrong) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]

    assessed = _append(world, contract_id, 1, _assessment(record, probable=False))
    assert assessed.status_code == 201, assessed.text
    body = assessed.json()
    assert body["contract"]["status"] == "NOT_A_CONTRACT"
    assert body["computation"]["status"] == "SUCCEEDED", body["computation"]
    # [J] L4-1-Q-10: the activation gate follows the assessment.
    assert _event_types(world, contract_id) == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
    ]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)

    receipt = {
        "event_type": "PAYMENT_RECEIVED",
        "effective_date": "2026-09-05",
        "payload": {
            "receipt_reference": "RCPT-US-4410",
            "amount": {"amount": "36000.00", "currency": "USD"},
            "receipt_date": "2026-09-05",
        },
    }
    paid = _append(world, contract_id, 3, receipt)
    assert paid.status_code == 201, paid.text
    assert paid.json()["computation"]["status"] == "SUCCEEDED", paid.json()["computation"]
    stored = world.place.rows(
        select(contract_version.c.version_no, contract_version.c.status_in_book)
        .join(
            contract_computation,
            contract_computation.c.id == contract_version.c.contract_computation_id,
        )
        .where(contract_computation.c.id == UUID(paid.json()["computation"]["id"]))
    )
    assert [row["status_in_book"] for row in stored] == ["NOT_A_CONTRACT"]
    lines = world.place.rows(
        select(subledger_line.c.account_role, func.sum(subledger_line.c.amount_txn).label("total"))
        .where(subledger_line.c.contract_id == contract_id)
        .group_by(subledger_line.c.account_role)
    )
    totals = {str(row["account_role"]): Decimal(row["total"]) for row in lines}
    assert "REVENUE" not in totals
    # L4-1-Q-15: the receipt's DEPOSIT_LIABILITY lines (Dr BILLING_CLEARING UNAPPLIED_CASH 36,000.00
    # / Cr DEPOSIT_LIABILITY 36,000.00, JET-01b) need the engine to publish the stage 02 deposit
    # targets as posting intents; the rc engine publishes none, as STP1-S1-EX1-CASEA shows.


def test_criteria_met_moves_to_pending_review(world: SeatWorld) -> None:
    """PRD SM-02 NOT_A_CONTRACT → PENDING_REVIEW (rev 1.34; ruling R-20 (c)): criteria met is the
    book's re-assessment with a reviewed record, submitted for activation. The stored status stays
    NOT_A_CONTRACT while the request is pending and the read model answers PENDING_REVIEW (04
    T-CON-01 rev 1.105; the L4-1-Q-18 pattern); a rejection returns the contract to
    NOT_A_CONTRACT, and an event recorded while a request is pending makes it stale
    (REQ-PLT-014)."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _k09(world)
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    # Criteria are met only through the approved activation: the events route refuses the event
    # while the contract is a draft as in every other status (SM-02).
    early = _append(world, contract_id, 1, _criteria_met(met, on="2026-10-01"))
    assert early.status_code == 409, early.text
    assert slug(early) == "invalid-transition"

    _gated(world, contract_id)
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)
    # An unreviewed record does not meet the criteria: a draft record is not assessed with, and
    # while it is unreviewed the activation checklist fails on the record and on Step 1.
    draft_id, _ = _record(world, contract_id, "COLLECTIBILITY", book=None, submit=False)
    unsubmitted = _append(
        world, contract_id, 3, _assessment(draft_id, probable=True, on="2026-09-10")
    )
    assert unsubmitted.status_code == 422, unsubmitted.text
    assert fields(unsubmitted) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert fields(refused) == [(None, "JUDGEMENT_RECORDS"), (None, "STEP1_RECORD")]
    assert _activation_requests(world, contract_id) == []
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)

    # The record is reviewed; the re-assessment that cites it is recorded and moves nothing.
    sent = post(world.app, f"{JUDGEMENTS}/{draft_id}/submit", world.place.author, {})
    assert sent.status_code == 200, sent.text
    reviewed = approve(world.app, sent.json()["approval_request_id"], world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    recorded = _append(world, contract_id, 3, _assessment(draft_id, probable=True, on="2026-09-10"))
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)

    moved = _submit(world, contract_id)
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "PENDING_REVIEW"
    first_request = moved.headers[APPROVAL_HEADER]
    # The stored row never leaves NOT_A_CONTRACT while the request is pending, and no event is
    # appended: the head stays 4.
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _read_status(world, contract_id) == "PENDING_REVIEW"
    again = _submit(world, contract_id)
    assert (again.status_code, slug(again)) == (409, "invalid-transition")

    # A rejection returns the contract to NOT_A_CONTRACT (audited) and appends nothing.
    rejected = reject(world.app, first_request, world.priya, "Collection is not yet probable.")
    assert rejected.status_code == 200, rejected.text
    assert _read_status(world, contract_id) == "NOT_A_CONTRACT"
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert ("contract.not_a_contract", "PENDING_REVIEW", "NOT_A_CONTRACT") in _status_audits(
        world, contract_id
    )
    assert "CONTRACT_CRITERIA_MET" not in _event_types(world, contract_id)

    # A second submission goes stale when the stream changes before the decision: nothing the
    # approver did not see is activated.
    second = _submit(world, contract_id)
    assert second.status_code == 200, second.text
    second_request = second.headers[APPROVAL_HEADER]
    paid = _append(world, contract_id, 4, RECEIPT)
    assert paid.status_code == 201, paid.text
    stale = approve(world.app, second_request, world.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    assert [status for status, _ in _activation_requests(world, contract_id)] == [
        "REJECTED",
        "VOIDED",
    ]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 5)
    assert _event_types(world, contract_id) == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
        "COLLECTIBILITY_ASSESSED",
        "PAYMENT_RECEIVED",
    ]
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _unapproved_recognition(world) == _recognition(world) == []


def test_significant_change_forces_reassessment(world: SeatWorld) -> None:
    contract_id = _k09(world)
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")
    first = _reviewed(world, contract_id, "COLLECTIBILITY")
    assessed = _append(world, contract_id, 1, _assessment(first, probable=True))
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["contract"]["status"] == "DRAFT"
    assert _step1(world, contract_id) == (True, None)

    flagged = _append(
        world,
        contract_id,
        2,
        {
            "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
            "effective_date": "2026-09-05",
            "payload": {"description": "Customer credit rating downgraded to CCC."},
        },
    )
    assert flagged.status_code == 201, flagged.text
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")

    # A record that is only submitted is not assessed with (ruling R-102 (b): before it the
    # assessment was recorded and failed the item — and made the record's review stale).
    submitted = post(
        world.app,
        JUDGEMENTS,
        world.place.author,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "conclusion": "Collection remains probable after the downgrade.",
            "rationale": "Letter of credit in place.",
            "questionnaire": {"criteria": step1_criteria()},
        },
    )
    assert submitted.status_code == 201, submitted.text
    pending_id = submitted.json()["id"]
    sent = post(world.app, f"{JUDGEMENTS}/{pending_id}/submit", world.place.author, {})
    assert sent.status_code == 200, sent.text
    pending = _append(
        world, contract_id, 3, _assessment(pending_id, probable=True, on="2026-09-06")
    )
    assert pending.status_code == 422, pending.text
    assert fields(pending) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert pending.json()["errors"][0]["message"] == NOT_REVIEWED
    assert _header(world, contract_id) == ("DRAFT", 3)
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")

    second = _reviewed(world, contract_id, "COLLECTIBILITY")
    late = _append(world, contract_id, 3, _assessment(second, probable=True, on="2026-09-07"))
    assert late.status_code == 201, late.text
    # Ruling R-77 (2): a draft is activated at its inception date (2026-09-01), where Table 2.2-A
    # reads the assessment in force; one dated after it sorts behind the activation event, so it
    # does not pass the item, which says so (IMP-131). The re-assessment dated the inception
    # date does.
    assert _step1(world, contract_id) == (
        False,
        NOT_IN_FORCE.format(book="ASC606", inception_date="01 Sep 2026"),
    )
    reassessed = _append(world, contract_id, 4, _assessment(second, probable=True, on="2026-09-01"))
    assert reassessed.status_code == 201, reassessed.text
    assert _step1(world, contract_id) == (True, None)


def test_reviewed_contract_term_judgement_sets_enforceable_term(world: SeatWorld) -> None:
    contract_id = _k09(world, termination={"party": "CUSTOMER", "has_penalty": False})
    record = _reviewed(
        world,
        contract_id,
        "CONTRACT_TERM",
        {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
    )
    shown = get(world.app, f"/api/v1/contracts/{contract_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    steps = shown.json()["steps"]
    assert steps[0]["step"] == "CONTRACT"
    assert steps[0]["detail"]["enforceable_term"] == {
        "end_date": "2026-12-31",
        "basis": "JUDGEMENT",
    }
    reviewed = get(world.app, f"{JUDGEMENTS}/{record}", world.place.author)
    assert reviewed.json()["status"] == "REVIEWED"
    assert date.fromisoformat(steps[0]["detail"]["enforceable_term"]["end_date"]) == date(
        2026, 12, 31
    )


# --- supervisor ruling R-20 (security findings SN-13 and SN-12) ----------------------------------

NOT_A_CONTRACT = {"consideration_nonrefundable": False}
# Ruling R-77 (1): no later assessment undoes a 25-5 reassessment of an active contract — the
# approved void of the flag does — so the refusal promises a new assessment only where one works.
ASSESSMENT_NOT_VOIDABLE = (
    "A Step 1 assessment is not voided: record a later assessment. On an active contract, a "
    "reassessment that followed a significant-change flag is undone by voiding the flag."
)
ACTIVATION_NOT_VOIDABLE = (
    "An activation event is not voided. A contract assessed as not a contract is activated when "
    "its criteria are met; an activation is reversed by voiding the contract."
)
FLAG = {
    "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
    "effective_date": "2026-09-05",
    "payload": {"description": "Customer credit rating downgraded to CCC."},
}


def _usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _decisions(world: SeatWorld, *subject_ids: UUID) -> int:
    """The approval decisions anyone took on the named subjects."""
    return int(
        world.place.scalar(
            select(func.count())
            .select_from(
                approval_decision.join(
                    approval_request,
                    approval_request.c.id == approval_decision.c.approval_request_id,
                )
            )
            .where(approval_request.c.subject_id.in_(list(subject_ids)))
        )
    )


def test_f13_assessment_names_an_enabled_book_of_the_contracting_entity(world: SeatWorld) -> None:
    """SN-13 (ruling R-20 (a)). The preparer ALONE recorded a not-probable assessment naming a
    book the entity does not keep (IFRS15) with a merely submitted record; the route appended the
    gate, the engine — which reads an assessment only in the book it names — activated ASC606, and
    revenue posted with no approval of anything. The assessment is refused: it names an enabled
    book of the contracting entity, its record is of that book and — since ruling R-102 (b) — is
    REVIEWED. Positive control: on a reviewed record of the book the entity keeps, the same
    preparer's assessment STOPS recognition (NOT_A_CONTRACT) with no approval of an activation."""
    contract_id = _created(world)
    # The finding's own shape: a merely submitted record of the book the entity does not keep.
    submitted_only, _ = _record(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    alone = _record_events(
        world, contract_id, _assessment(submitted_only, probable=False, book="IFRS15")
    )
    assert alone.status_code == 422, alone.text
    assert slug(alone) == "validation-failed"
    assert fields(alone) == [
        ("events.0.payload.judgement_record_id", "REQ-POL-008"),
        ("events.0.payload.book", "REQ-POL-008"),
    ]
    assert [error["message"] for error in alone.json()["errors"]] == [
        NOT_REVIEWED,
        "Book IFRS15 is not enabled for AVM-US.",
    ]
    # The book rule alone: a reviewed record of that book.
    other_book = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    refused = _record_events(
        world, contract_id, _assessment(other_book, probable=False, book="IFRS15")
    )
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("events.0.payload.book", "REQ-POL-008")]
    assert refused.json()["errors"][0]["message"] == "Book IFRS15 is not enabled for AVM-US."
    # … and the record of another book does not serve the book the entity keeps.
    wrong = _record_events(world, contract_id, _assessment(other_book, probable=False))
    assert wrong.status_code == 422, wrong.text
    assert fields(wrong) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert wrong.json()["errors"][0]["message"] == "The judgement record applies to another book."
    # Nothing was written: no gate, no status, no computation beyond the booking's, no posting.
    assert _header(world, contract_id) == ("DRAFT", 1)
    assert _event_types(world, contract_id) == ["CONTRACT_BOOKED"]
    assert _books(world, contract_id) == {"ASC606": ("DRAFT", Decimal("0"))}
    assert _posted(world, contract_id) == {}
    assert _recognition(world) == []

    # Positive control: the book the entity keeps, on a reviewed record of it.
    own_book = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    assessed = _record_events(world, contract_id, _assessment(own_book, probable=False))
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert _event_types(world, contract_id) == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
    ]
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _posted(world, contract_id) == {}
    assert _recognition(world) == []
    # No approval of an activation was asked or given: the judgement reviews are the only decisions.
    assert _decisions(world, contract_id) == 0
    assert _activation_requests(world, contract_id) == []


def test_f12_criteria_met_is_appended_only_by_the_approved_activation(world: SeatWorld) -> None:
    """SN-12 (ruling R-20 (c)). After the not-a-contract gate, a ``CONTRACT_CRITERIA_MET`` sent to
    the events route with ONE reviewed judgement made the engine ACTIVE and posted revenue with no
    ``CONTRACT_ACTIVATION`` request — no checklist, no routing, no second step. The events route
    and its preview refuse the event, and ``CONTRACT_ACTIVATED``, by name. Positive control and
    witness of R-20 (c): the re-assessment is recorded, the contract is submitted for activation,
    a reviewer other than the preparer approves, and SYSTEM appends ``CONTRACT_CRITERIA_MET`` and
    ``CONTRACT_ACTIVATED`` with the request id; only then does a book recognise. The preview
    states the POL-013 catch-up the approver decides on: 985.40 = 108,000.00 × 10 / 1,096 days,
    the engine's ``revenue_cum`` at the criteria-met date (ENGINE_SPEC S02-R-04; 04
    API-S-ImpactSummary rev 1.105)."""
    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _gated(world, contract_id)
    paid = _record_events(world, contract_id, RECEIPT)
    assert paid.status_code == 201, paid.text
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)

    # --- the refusals ---
    activated = {
        "event_type": "CONTRACT_ACTIVATED",
        "effective_date": "2026-09-10",
        "payload": {"checklist": [{"code": "STEP1_RECORD", "passed": True}]},
    }
    for path in (EVENTS, f"{EVENTS}/preview"):
        for item in (_criteria_met(met), activated):
            refused = post(
                world.app,
                path.format(contract_id=contract_id),
                maya,
                {"events": [item]},
                if_match='"s4"',
            )
            assert refused.status_code == 409, (path, refused.text)
            assert slug(refused) == "invalid-transition"
            assert fields(refused) == [("events.0.event_type", "DB-03")]
            assert refused.json()["detail"] == ACTIVATION_ONLY.format(event_type=item["event_type"])
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _activation_requests(world, contract_id) == []
    assert _unapproved_recognition(world) == _recognition(world) == []
    # The activation command before the criteria are recorded as met: the checklist fails.
    early = _submit(world, contract_id)
    assert (early.status_code, slug(early)) == (409, "activation-checklist-failed")
    assert fields(early) == [(None, "STEP1_RECORD")]

    # --- positive control: the re-assessment, then the approved activation ---
    reassessed = _record_events(
        world, contract_id, _assessment(met, probable=True, on="2026-09-10")
    )
    assert reassessed.status_code == 201, reassessed.text
    assert reassessed.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert [event["event_type"] for event in reassessed.json()["events"]] == [
        "COLLECTIBILITY_ASSESSED"
    ]
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    assert (submitted.json()["status"], submitted.json()["head_stream_version"]) == (
        "PENDING_REVIEW",
        5,
    )
    request_id = submitted.headers[APPROVAL_HEADER]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 5)
    # The same routing as any activation: a manual contract of 108,000.00 USD.
    assert _activation_requests(world, contract_id) == [("PENDING", K09_FLAGS)]
    assert _recognition(world) == []

    # What the approver decides on: the books that move and the POL-013 catch-up.
    document = _preview_document(world, request_id)
    assert document["before"]["status"] == "NOT_A_CONTRACT"
    after = document["after"]
    assert after["status"] == "ACTIVE"
    assert after["criteria_met"] == [
        {
            "book": "ASC606",
            "effective_date": "2026-09-10",
            "judgement_record_id": met,
            "catch_up_total": _usd("985.40"),
        }
    ]
    assert after["catch_up_total"] == _usd("985.40")
    assert after["catch_up_by_obligation"] == [
        {"obligation_key": "O1", "treatment": None, "amount": _usd("985.40")}
    ]
    # … which the approval request itself names for the approver (04 §16.10 rev 1.126; ruling
    # R-61 (f), item ACT-STEP1-UI-1): the books that move, their dates and records, the catch-up.
    shown = get(world.app, f"/api/v1/approvals/{request_id}", world.priya)
    assert shown.status_code == 200, shown.text
    stated = shown.json()["impact_preview"]["summary"]
    assert stated["criteria_met"] == [
        {
            "book": "ASC606",
            "effective_date": "2026-09-10",
            "judgement_record_id": met,
            "catch_up_total": _usd("985.40"),
        }
    ]
    assert stated["catch_up_total"] == _usd("985.40")
    # … and what the request's content hash binds (REQ-PLT-014).
    with world.place.uow() as uow:
        content = contract_activation_content(uow.session, contract_id)
    assert content["head_stream_version"] == 5
    assert content["criteria_met"] == [
        {"book": "ASC606", "effective_date": "2026-09-10", "judgement_record_id": met}
    ]

    approved = approve(world.app, request_id, world.priya)
    assert approved.status_code == 200, approved.text
    assert _header(world, contract_id) == ("ACTIVE", 7)
    assert _read_status(world, contract_id) == "ACTIVE"
    events = _stream(world, contract_id)
    assert [
        (
            str(event["event_type"]),
            event["effective_date"].isoformat(),
            str(event["origin"]),
            str(event["created_by_kind"]),
        )
        for event in events
    ] == [
        ("CONTRACT_BOOKED", "2026-09-01", "UI", "USER"),
        ("COLLECTIBILITY_ASSESSED", "2026-09-01", "UI", "USER"),
        ("CONTRACT_ACTIVATED", "2026-09-01", "UI", "USER"),  # the not-a-contract gate
        ("PAYMENT_RECEIVED", "2026-09-05", "UI", "USER"),
        ("COLLECTIBILITY_ASSESSED", "2026-09-10", "UI", "USER"),
        ("CONTRACT_CRITERIA_MET", "2026-09-10", "SYSTEM", "SYSTEM"),
        ("CONTRACT_ACTIVATED", "2026-09-10", "SYSTEM", "SYSTEM"),
    ]
    assert [str(event["approval_request_id"]) for event in events[5:]] == [request_id, request_id]
    assert events[5]["payload"] == {"book": "ASC606", "judgement_record_id": met}
    # The engine's figure is the previewed one: cumulative revenue at the criteria-met date.
    assert _books(world, contract_id) == {"ASC606": ("ACTIVE", Decimal("985.40"))}
    # Postings: the receipt while not a contract (JET-01b), its transfer at the transition
    # (S02-R-04, S02-R-08) and the revenue of the transition period FY2026-P09, 2,956.20 =
    # 108,000.00 × 30 / 1,096, which holds the catch-up of 985.40 (JET-02).
    assert _posted(world, contract_id) == {
        ("ASC606", "BILLING_CLEARING", "D"): Decimal("36000.00"),
        ("ASC606", "DEPOSIT_LIABILITY", "C"): Decimal("36000.00"),
        ("ASC606", "DEPOSIT_LIABILITY", "D"): Decimal("36000.00"),
        ("ASC606", "CONTRACT_LIABILITY", "C"): Decimal("36000.00"),
        ("ASC606", "CONTRACT_LIABILITY", "D"): Decimal("2956.20"),
        ("ASC606", "REVENUE", "C"): Decimal("2956.20"),
    }
    # DG-SM-03: the read-model move at the submission, then both stored SM-02 steps at approval.
    assert _status_audits(world, contract_id) == [
        ("contract.active", "PENDING_REVIEW", "ACTIVE"),
        ("contract.not_a_contract", "DRAFT", "NOT_A_CONTRACT"),
        ("contract.pending_review", "NOT_A_CONTRACT", "PENDING_REVIEW"),
        ("contract.pending_review", "NOT_A_CONTRACT", "PENDING_REVIEW"),
    ]
    assert _activation_requests(world, contract_id) == [("APPROVED", K09_FLAGS)]
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_gate_needs_every_enabled_book_not_probable(world: SeatWorld) -> None:
    """Ruling R-20 (b): with the request's events applied, the not-a-contract gate is appended
    only when the assessment of EVERY enabled book of the contracting entity is not probable.
    Until then the assessment is recorded and the contract stays DRAFT in the header and in every
    book. A contract whose books differ takes the approved activation, where the engine decides
    per book (S02-R-01)."""
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    draft = {"ASC606": ("DRAFT", Decimal("0")), "IFRS15": ("DRAFT", Decimal("0"))}
    assert _books(world, contract_id) == draft
    asc606 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    one = _record_events(world, contract_id, _assessment(asc606, probable=False))
    assert one.status_code == 201, one.text
    assert one.json()["contract"]["status"] == "DRAFT"
    assert [event["event_type"] for event in one.json()["events"]] == ["COLLECTIBILITY_ASSESSED"]
    assert _header(world, contract_id) == ("DRAFT", 2)
    assert _books(world, contract_id) == draft
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")

    ifrs15 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    both = _record_events(world, contract_id, _assessment(ifrs15, probable=False, book="IFRS15"))
    assert both.status_code == 201, both.text
    assert both.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert [event["event_type"] for event in both.json()["events"]] == [
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
    ]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _books(world, contract_id) == {
        "ASC606": ("NOT_A_CONTRACT", Decimal("0")),
        "IFRS15": ("NOT_A_CONTRACT", Decimal("0")),
    }
    assert _posted(world, contract_id) == {}
    assert _recognition(world) == []

    # Books that differ: not probable under ASC 606, probable under IFRS 15 — no gate.
    mixed = _created(world, "C-02", "SF-ORD-10517")
    not_probable = _reviewed(world, mixed, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    probable = _reviewed(world, mixed, "COLLECTIBILITY", book="IFRS15")
    recorded = _record_events(
        world,
        mixed,
        _assessment(not_probable, probable=False),
        _assessment(probable, probable=True, book="IFRS15"),
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["contract"]["status"] == "DRAFT"
    assert _event_types(world, mixed) == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "COLLECTIBILITY_ASSESSED",
    ]
    assert _books(world, mixed) == draft
    assert _recognition(world) == []
    # The approved activation is its only way to a status; the engine then decides per book.
    submitted = _submit(world, mixed)
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    books = _books(world, mixed)
    assert books["ASC606"] == ("NOT_A_CONTRACT", Decimal("0"))
    assert books["IFRS15"][0] == "ACTIVE" and books["IFRS15"][1] > 0
    assert _recognition(world) == [("SF-ORD-10517", "IFRS15", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_gate_needs_the_engine_confirmation(world: SeatWorld) -> None:
    """Ruling R-20 (b), confirmed by the engine (04 §16.3 rev 1.105). The enabled-book rule reads
    the contracting entity's books; the engine computes the group in every book any entity of the
    group keeps, where a book without an assessment would be ACTIVATED by the gate. So the gate is
    kept only when the dry run of the batch gives the contract NOT_A_CONTRACT in every book it is
    computed in, each an enabled book of the contracting entity; a dry run the engine refuses
    confirms nothing. The dry run's answer is shaped here through the command's ``engine``."""
    import dataclasses

    import erev_engine
    from erev_api.domain.contracts import events as events_domain
    from erev_api.schemas.events import EventAppendIn, EventAppendItemIn
    from erev_engine.bundle import InputBundle, OutputBundle
    from erev_engine.errors import EngineError

    contract_id = _created(world)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)

    def dry_run(shape: Any) -> Any:
        def run(bundle: InputBundle) -> OutputBundle:
            output = erev_engine.compute(bundle)
            return shape(output) if bundle.trigger == "DRY_RUN" else output

        return run

    def recognising(output: OutputBundle) -> OutputBundle:
        """Another book of the group activates the contract at the gate."""
        books = tuple(
            dataclasses.replace(
                book, status_in_book=tuple((key, "ACTIVE") for key, _ in book.status_in_book)
            )
            for book in output.books
        )
        return dataclasses.replace(output, books=books)

    def other_entity_book(output: OutputBundle) -> OutputBundle:
        """A book the contracting entity does not keep holds the contract NOT_A_CONTRACT — for
        want of performance (606-10-25-4), which the first receipt would end."""
        extra = dataclasses.replace(output.books[0], book_code="IFRS15")
        return dataclasses.replace(output, books=(*output.books, extra))

    def refused(output: OutputBundle) -> OutputBundle:
        raise EngineError("SSP_KEY_NOT_FOUND", "No approved SSP for the key.")

    def assess(on: str, engine: Any) -> tuple[list[str], Any]:
        """Record a not-probable assessment through the command: the appended event types and
        what the answer says of the gate (ruling R-77 (6))."""
        body = EventAppendIn(
            events=[EventAppendItemIn.model_validate(_assessment(record, probable=False, on=on))]
        )
        before = _head(world, contract_id)
        with world.place.uow() as uow:
            recorded = events_domain.record_events(
                uow,
                contract_id=contract_id,
                expected_stream_version=before,
                body=body,
                engine=engine,
            )
            uow.commit()
        assert recorded.appended is not None
        gate = recorded.appended.step1_gate
        assert gate is not None
        return _event_types(world, contract_id)[before:], (gate.appended, gate.reason)

    # Ruling R-77 (6): a withheld gate is never silent — the answer names the reason.
    for day, shape, reason in (
        ("2026-09-01", recognising, "BOOK_NOT_CONFIRMED"),
        ("2026-09-02", other_entity_book, "BOOK_NOT_CONFIRMED"),
        ("2026-09-03", refused, "ENGINE_REFUSED"),
    ):
        assert assess(day, dry_run(shape)) == (["COLLECTIBILITY_ASSESSED"], (False, reason))
        assert _header(world, contract_id)[0] == "DRAFT"
        assert _books(world, contract_id) == {"ASC606": ("DRAFT", Decimal("0"))}
    # Positive control: the engine confirms, and the gate follows the assessment.
    assert assess("2026-09-04", dry_run(lambda output: output)) == (
        ["COLLECTIBILITY_ASSESSED", "CONTRACT_ACTIVATED"],
        (True, None),
    )
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 6)
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _recognition(world) == []


def test_step1_status_is_not_moved_by_back_dating_voiding_or_riding(world: SeatWorld) -> None:
    """The family of R-20: every other way a recorder could change what ENGINE_SPEC Table 2.2-A
    reads at the activation event, each refused with a positive control beside it. (1) An
    assessment dated BEFORE the contract's ``CONTRACT_ACTIVATED`` would be the one the gate reads
    (ENG-06 orders by effective date first) and activate the book retroactively. (2) A void of the
    not-probable assessment or of the gate replays the table under the ``MANUAL_EVENT`` approval.
    (3) An assessment riding in an attribute-change submission would be appended at that approval
    with none of the Step 1 checks."""
    maya = world.place.author
    contract_id = _created(world)
    _gated(world, contract_id, on="2026-09-05")
    paid = _record_events(world, contract_id, RECEIPT)
    assert paid.status_code == 201, paid.text
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    not_a_contract = {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}

    # (1) back-dating
    back_dated = _record_events(
        world, contract_id, _assessment(met, probable=True, on="2026-09-04")
    )
    assert back_dated.status_code == 422, back_dated.text
    assert fields(back_dated) == [("events.0.effective_date", "REQ-POL-008")]
    # Ruling R-118 (e): one sentence serves a date before the activation event too — the gate is
    # the book's latest Step 1 entry here.
    assert back_dated.json()["errors"][0]["message"] == ASSESSMENT_BEFORE_STEP1.format(
        book_label="ASC 606", date="05 Sep 2026"
    )
    # (2) voiding the assessment the gate read, and the gate
    events = _stream(world, contract_id)
    assert [str(event["event_type"]) for event in events[1:3]] == [
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
    ]
    for event, copy in zip(
        events[1:3], (ASSESSMENT_NOT_VOIDABLE, ACTIVATION_NOT_VOIDABLE), strict=True
    ):
        voided = post(
            world.app,
            f"/api/v1/events/{event['id']}/request-void",
            maya,
            {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded in error."},
        )
        assert voided.status_code == 409, voided.text
        assert slug(voided) == "invalid-transition"
        assert voided.json()["detail"] == copy
    # (3) riding in an attribute-change submission
    attribute = {
        "event_type": "LINE_ATTRIBUTES_CHANGED",
        "effective_date": "2026-09-10",
        "obligation_key": "O1",
        "payload": {
            "obligation_key": "O1",
            "changes": {"account_overrides": {"REVENUE": "4010"}},
            "diff": {"account_overrides": {"before": {}, "after": {"REVENUE": "4010"}}},
        },
    }
    riding = _record_events(
        world, contract_id, attribute, _assessment(met, probable=True, on="2026-09-10")
    )
    assert riding.status_code == 422, riding.text
    assert fields(riding) == [("events.1.event_type", "API-R-30")]
    assert riding.json()["errors"][0]["message"] == (
        "Record the Step 1 assessment in a request of its own."
    )
    # … and neither does the significant-change flag: its date is checked against the Step 1
    # events recorded when it is appended, not when it was stored (ruling R-77 (1), (9)).
    flagged = _record_events(
        world, contract_id, attribute, {**FLAG, "effective_date": "2026-09-10"}
    )
    assert flagged.status_code == 422, flagged.text
    assert fields(flagged) == [("events.1.event_type", "API-R-30")]
    assert flagged.json()["errors"][0]["message"] == (
        "Record the significant-change flag in a request of its own."
    )
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _books(world, contract_id) == not_a_contract

    # Positive controls: an assessment dated on the activation date is recorded (it sorts after
    # the gate, ENG-06), in a request of its own; another event is voided as before.
    same_day = _record_events(world, contract_id, _assessment(met, probable=True, on="2026-09-05"))
    assert same_day.status_code == 201, same_day.text
    assert same_day.json()["contract"]["status"] == "NOT_A_CONTRACT"
    receipt = post(
        world.app,
        f"/api/v1/events/{events[3]['id']}/request-void",
        maya,
        {"reason_code": "DUPLICATE", "comment": "The receipt was recorded twice."},
    )
    assert receipt.status_code == 201, receipt.text
    assert set(receipt.json()) == {"event_submission_id", "approval_request_id"}
    assert _books(world, contract_id) == not_a_contract
    assert _unapproved_recognition(world) == _recognition(world) == []


def test_r20_d_a_recognising_book_implies_an_approved_activation(world: SeatWorld) -> None:
    """Ruling R-20 (d): a book status in {ACTIVE, COMPLETED, TERMINATED} implies an APPROVED
    ``CONTRACT_ACTIVATION`` request of the contract, the SYSTEM activation path (BS3-D-19) or a
    MIGRATION-origin activation. The Step 1 witnesses of this module assert it after their steps
    (``_unapproved_recognition``); here the SYSTEM path, and the proof that the witness can fail:
    a ``CONTRACT_CRITERIA_MET`` appended for the recorder — what the events route did before the
    ruling, done here below the route — makes a book recognise with no activation approval."""
    booked = booked_contract(world.place, k02_body(world.customers["C-02"]), activate=False)
    activated_contract(world.place, booked)
    assert _recognition(world) == [("SF-ORD-10002", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []

    contract_id = _created(world)
    _gated(world, contract_id)
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert _unapproved_recognition(world) == []
    appended(
        world.place,
        contract_id,
        3,
        [
            EventIn(
                event_type=ContractEventType.CONTRACT_CRITERIA_MET,
                effective_date=date(2026, 9, 10),
                payload=ContractCriteriaMetV1(book=BookCode.ASC606, judgement_record_id=UUID(met)),
            )
        ],
    )
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    computed(world.place, group_id)
    assert _books(world, contract_id)["ASC606"][0] == "ACTIVE"
    assert _unapproved_recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]


# --- supervisor ruling R-77 (independent review of the fix of SN-13 / SN-12) ----------------------

# Supervisor ruling R-118 (e) (the copy point): "entry", the book by its label, dates as
# DD MMM YYYY (DS-FMT-16); the sentence about "the contract's activation event" is gone.
ASSESSMENT_BEFORE_STEP1 = (
    "This assessment is dated before the contract's latest Step 1 entry in {book_label} "
    "({date}). Date it on or after that date."
)
FLAG_BEFORE_STEP1 = (
    "This significant-change flag is dated before the contract's latest Step 1 entry ({date}). "
    "Date it on or after that date."
)
REVIEWED_BEFORE_GATE = (
    "Use a judgement record reviewed after the contract was assessed as not a contract."
)
APPENDED = {"appended": True, "reason": None}
# Supervisor ruling R-102 (b) and (c): the record an assessment cites.
NOT_REVIEWED = "Use a reviewed judgement record."
REVIEWED_BEFORE_BOOKING = "Use a judgement record reviewed after the draft was last replaced."
# Supervisor rulings R-113 (f) and R-115 (f): PRD IMP-135, the criterion named by its label.
CRITERION_NOT_MET = (
    "The Step 1 review answers No for {criterion_label}: the contract is not activated until the "
    "criterion is met."
)
# Rulings R-82 (c) and R-84 (a): nothing of Step 1 is dated ahead of the later of today and the
# contract's inception date.
STEP1_AHEAD = (
    "This {what} is dated after {date}, the later of today and the contract's inception date. "
    "Date it on or before that date."
)


def _activated(world: SeatWorld, contract_id: UUID) -> str:
    """The DRAFT contract activated on a reviewed probable assessment dated its inception date, by
    a reviewer other than the preparer; returns the collectibility record."""
    record = _reviewed(world, contract_id, "COLLECTIBILITY")
    assessed = _record_events(world, contract_id, _assessment(record, probable=True))
    assert assessed.status_code == 201, assessed.text
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    assert _header(world, contract_id)[0] == "ACTIVE"
    return record


def _group_id(world: SeatWorld, contract_id: UUID) -> UUID:
    return UUID(
        str(
            world.place.scalar(
                select(contract.c.combination_group_id).where(contract.c.id == contract_id)
            )
        )
    )


def test_back_dated_step1_event_does_not_rewrite_a_25_5_transition(world: SeatWorld) -> None:
    """Ruling R-77 (1), the hole the review found beside the fix. An ACTIVE contract is reassessed
    under 606-10-25-5: a significant-change flag, then a not-probable assessment — the book is
    NOT_A_CONTRACT from that date (Table 2.2-A). A holder of ``event.record`` then recorded a
    PROBABLE assessment dated BETWEEN the two, citing the old collectibility record: in ENG-06
    order it is read before the not-probable one and clears the flag, so on replay the book never
    left ACTIVE and the revenue since posted as catch-up — no request, no review. Once the stream
    holds a ``CONTRACT_ACTIVATED``, an assessment or a flag dated before the latest Step 1 event
    it acts on is refused, in either direction. Since ruling R-102 (a) a probable assessment of
    a book that is out is the book's criteria-met re-assessment, so the old record is refused as
    well (reviewed before the book was put out); the date rule is shown alone on a record
    reviewed after it. Positive controls: a later-dated assessment on that record is recorded
    (and, by itself, moves nothing — the approved criteria-met request does); the APPROVED void
    of the flag undoes the transition. The R-20 (d) invariant holds after every step."""
    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    probable = _activated(world, contract_id)
    assert _books(world, contract_id)["ASC606"][0] == "ACTIVE"

    flagged = _record_events(world, contract_id, FLAG)
    assert flagged.status_code == 201, flagged.text
    not_probable = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    moved = _record_events(
        world, contract_id, _assessment(not_probable, probable=False, on="2026-09-08")
    )
    assert moved.status_code == 201, moved.text
    assert moved.json()["computation"]["status"] == "SUCCEEDED", moved.json()["computation"]
    # No gate is decided on an active contract, and the header is the projection of the events
    # (04 T-CON-01): it stays ACTIVE while the book is not a contract.
    assert moved.json()["step1_gate"] is None
    assert moved.json()["contract"]["status"] == "ACTIVE"
    status, recognised = _books(world, contract_id)["ASC606"]
    assert status == "NOT_A_CONTRACT"
    assert _recognition(world) == _unapproved_recognition(world) == []
    before = (_header(world, contract_id), _books(world, contract_id), _posted(world, contract_id))

    # --- the refusals ---
    # The hole's own shape: the OLD record, dated between the flag and the reassessment. Two
    # findings now — the record was reviewed before the book was put out, and the date.
    slipped = _assessment(probable, probable=True, on="2026-09-06")
    before_step1 = ASSESSMENT_BEFORE_STEP1.format(book_label="ASC 606", date="08 Sep 2026")
    for path in (EVENTS, f"{EVENTS}/preview"):
        refused = post(
            world.app,
            path.format(contract_id=contract_id),
            maya,
            {"events": [slipped]},
            if_match=f'"s{_head(world, contract_id)}"',
        )
        assert refused.status_code == 422, (path, refused.text)
        assert fields(refused) == [
            ("events.0.payload.judgement_record_id", "REQ-POL-008"),
            ("events.0.effective_date", "REQ-POL-008"),
        ]
        assert [error["message"] for error in refused.json()["errors"]] == [
            REVIEWED_BEFORE_GATE,
            before_step1,
        ]
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    ) == before
    # The mirror, in the other direction: a not-probable assessment dated before the latest
    # Step 1 event. It is shown here, on the record the book was put out with, before the
    # collectibility review below overtakes that record (item STEP1-CITE-LATEST-1).
    earlier = _record_events(
        world, contract_id, _assessment(not_probable, probable=False, on="2026-09-04")
    )
    assert earlier.status_code == 422, earlier.text
    assert fields(earlier) == [("events.0.effective_date", "REQ-POL-008")]
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    ) == before
    # A collectibility judgement made after the book was put out: the record a criteria-met
    # re-assessment of the book rests on (rulings R-77 (3), R-102 (a)). Its review supersedes the
    # old record (PRD SM-10), which is then no reviewed record at all (ruling R-102 (b)); and
    # while it waited for its review the contract was on a SYSTEM recognition hold (REQ-POL-010).
    _later(world)
    fresh = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert _event_types(world, contract_id)[-2:] == ["HOLD_APPLIED", "HOLD_RELEASED"]
    superseded = _record_events(
        world, contract_id, _assessment(probable, probable=True, on="2026-09-08")
    )
    assert superseded.status_code == 422, superseded.text
    assert [error["message"] for error in superseded.json()["errors"]] == [NOT_REVIEWED]
    before = (_header(world, contract_id), _books(world, contract_id), _posted(world, contract_id))
    # The date rule alone: the same date on the record reviewed after the book was put out.
    dated = _record_events(world, contract_id, _assessment(fresh, probable=True, on="2026-09-06"))
    assert dated.status_code == 422, dated.text
    assert fields(dated) == [("events.0.effective_date", "REQ-POL-008")]
    assert dated.json()["errors"][0]["message"] == before_step1
    # The mirror: a flag dated before the latest Step 1 event (the not-probable assessment dated
    # before it is shown above).
    back_flag = _record_events(world, contract_id, {**FLAG, "effective_date": "2026-09-07"})
    assert back_flag.status_code == 422, back_flag.text
    assert fields(back_flag) == [("events.0.effective_date", "REQ-POL-008")]
    assert back_flag.json()["errors"][0]["message"] == FLAG_BEFORE_STEP1.format(date="08 Sep 2026")
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    ) == before

    # --- positive controls ---
    # Dated on the latest Step 1 event (it sorts after it, ENG-06) or later, an assessment on
    # the new judgement is recorded; the book stays not a contract: Table 2.2-A leaves
    # NOT_A_CONTRACT only by CONTRACT_CRITERIA_MET, which the approved criteria-met request
    # appends (ruling R-102 (a); ``test_criteria_met_path_after_a_25_5_reassessment``).
    later = _record_events(world, contract_id, _assessment(fresh, probable=True, on="2026-09-08"))
    assert later.status_code == 201, later.text
    assert _books(world, contract_id)["ASC606"] == (status, recognised)
    # A wrong 25-5 move is undone by the APPROVED void of the flag (subject MANUAL_EVENT).
    flag_event = next(
        event
        for event in _stream(world, contract_id)
        if str(event["event_type"]) == "SIGNIFICANT_CHANGE_FLAGGED"
    )
    requested = post(
        world.app,
        f"/api/v1/events/{flag_event['id']}/request-void",
        maya,
        {"reason_code": "CREATED_IN_ERROR", "comment": "The downgrade was another customer's."},
    )
    assert requested.status_code == 201, requested.text
    assert _books(world, contract_id)["ASC606"][0] == "NOT_A_CONTRACT"  # nothing until approved
    own = approve(world.app, requested.json()["approval_request_id"], maya)
    assert own.status_code == 403, own.text
    voided = approve(world.app, requested.json()["approval_request_id"], world.priya)
    assert voided.status_code == 200, voided.text
    computed(world.place, _group_id(world, contract_id))
    restored, again = _books(world, contract_id)["ASC606"]
    assert restored == "ACTIVE" and again > recognised
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_draft_activation_reads_the_assessment_in_force_at_inception(world: SeatWorld) -> None:
    """Ruling R-77 (2). ``CONTRACT_ACTIVATED`` of a DRAFT contract is dated its inception date, so
    an assessment dated after inception sorts BEHIND it (ENG-06) and Table 2.2-A activates the
    book on whatever was in force before — against the preparer's reviewed conclusion: two books,
    ASC 606 probable and IFRS 15 not probable dated inception + 1 day, passed the checklist and
    the approved activation made IFRS 15 ACTIVE. ``STEP1_RECORD`` now requires, per enabled book
    of a DRAFT contract, that the assessment in force at the inception date is the book's latest.
    Positive control: the same conclusion dated the inception date is the one the activation
    reads — IFRS 15 is NOT_A_CONTRACT and ASC 606 ACTIVE after the approval."""
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    asc606 = _reviewed(world, contract_id, "COLLECTIBILITY")
    ifrs15 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    recorded = _record_events(
        world,
        contract_id,
        _assessment(asc606, probable=True),
        _assessment(ifrs15, probable=False, book="IFRS15", on="2026-09-02"),
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["contract"]["status"] == "DRAFT"
    # Rulings R-77 (6) and R-84 (b): the answer says why no gate followed the not-probable
    # assessment — the reason code (04 E-132); the copy is the screen's.
    assert recorded.json()["step1_gate"] == {"appended": False, "reason": "BOOK_NOT_ASSESSED"}
    draft = {"ASC606": ("DRAFT", Decimal("0")), "IFRS15": ("DRAFT", Decimal("0"))}
    assert _books(world, contract_id) == draft

    # The refusal: both assessments are reviewed, yet the one of IFRS 15 is not in force at the
    # inception date (2026-09-01), where the activation event would stand.
    assert _checklist(world, contract_id) == {
        **dict.fromkeys(CHECKLIST_CODES, True),
        "STEP1_RECORD": False,
    }
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert fields(refused) == [(None, "STEP1_RECORD")]
    # The item says which book and why (PRD IMP-131; ruling R-82 (g)).
    assert refused.json()["errors"][0]["message"] == NOT_IN_FORCE.format(
        book="IFRS15", inception_date="01 Sep 2026"
    )
    assert _activation_requests(world, contract_id) == []
    assert _books(world, contract_id) == draft
    assert _recognition(world) == []

    # Positive control: dated the inception date, the conclusion is read by the activation.
    redated = _record_events(world, contract_id, _assessment(ifrs15, probable=False, book="IFRS15"))
    assert redated.status_code == 201, redated.text
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    books = _books(world, contract_id)
    assert books["IFRS15"] == ("NOT_A_CONTRACT", Decimal("0"))
    assert books["ASC606"][0] == "ACTIVE" and books["ASC606"][1] > 0
    assert _header(world, contract_id)[0] == "ACTIVE"
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_criteria_met_needs_a_new_collectibility_judgement(world: SeatWorld) -> None:
    """Ruling R-77 (3). After the not-a-contract gate the preparer recorded ``is_probable: true``
    citing the GATE'S OWN reviewed NOT_A_CONTRACT record, or a collectibility record reviewed
    BEFORE the gate, and submitted: ``STEP1_RECORD`` passed on a record id that was REVIEWED and
    nothing else — criteria met with no new judgement. The criteria-met re-assessment rests on a
    COLLECTIBILITY record reviewed AFTER the gate was written: the route refuses the two by name,
    and the reader the activation uses (``step1.criteria_met``) decides the same for an
    assessment appended below the route, and for a record that is merely SUBMITTED — which the
    route itself no longer takes (ruling R-102 (b)). Positive control: a collectibility record
    reviewed after the gate meets the criteria."""
    from erev_api.events import step1
    from erev_api.events.payloads import CollectibilityAssessedV1

    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    early = _reviewed(world, contract_id, "COLLECTIBILITY")  # reviewed before the gate
    gate_record = _gated(world, contract_id)
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)

    # --- the refusals at the route ---
    own = _record_events(
        world, contract_id, _assessment(gate_record, probable=True, on="2026-09-10")
    )
    assert own.status_code == 422, own.text
    # Three findings on the one record: it is of another topic, it was reviewed before the gate
    # and — item STEP1-HOLD-RELEASE-1, ruling R-113 (f) (3) extended to criterion (e) — it answers
    # No to "Collectibility probable" (two findings before that ruling).
    assert fields(own) == [("events.0.payload.judgement_record_id", "REQ-POL-008")] * 3
    assert [error["message"] for error in own.json()["errors"]] == [
        "Use a judgement record of topic COLLECTIBILITY.",
        REVIEWED_BEFORE_GATE,
        NOT_PROBABLE_REVIEW,
    ]
    before_gate = _record_events(
        world, contract_id, _assessment(early, probable=True, on="2026-09-10")
    )
    assert before_gate.status_code == 422, before_gate.text
    assert fields(before_gate) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert before_gate.json()["errors"][0]["message"] == REVIEWED_BEFORE_GATE
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)

    def criteria() -> list[str]:
        with world.place.uow() as uow:
            return [
                item.book
                for item in step1.criteria_met(
                    uow.session,
                    contract_id=contract_id,
                    status="NOT_A_CONTRACT",
                    entity_id=world.entity_id,
                )
            ]

    def below_the_route(record_id: str, head: int) -> None:
        appended(
            world.place,
            contract_id,
            head,
            [
                EventIn(
                    event_type=ContractEventType.COLLECTIBILITY_ASSESSED,
                    effective_date=date(2026, 9, 10),
                    payload=CollectibilityAssessedV1(
                        book=BookCode.ASC606, is_probable=True, judgement_record_id=UUID(record_id)
                    ),
                )
            ],
        )

    # --- the reader decides the same for what reaches the stream another way ---
    for head, record_id in ((3, early), (4, gate_record)):
        below_the_route(record_id, head)
        assert criteria() == []
        assert _checklist(world, contract_id)["STEP1_RECORD"] is False
        refused = _submit(world, contract_id)
        assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
        assert fields(refused) == [(None, "STEP1_RECORD")]
    # A SUBMITTED collectibility record is not cited at the route (ruling R-102 (b), item
    # STEP1-JR-STALE-1) …
    pending, pending_request = _record(world, contract_id, "COLLECTIBILITY")
    assert pending_request is not None
    cited = _record_events(world, contract_id, _assessment(pending, probable=True, on="2026-09-10"))
    assert cited.status_code == 422, cited.text
    assert fields(cited) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert cited.json()["errors"][0]["message"] == NOT_REVIEWED
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 5)
    # … and, cited below the route, it meets nothing until it is reviewed; that append moved the
    # head, so the pending review is stale and ends REJECTED (04 §16.10).
    below_the_route(pending, 5)
    assert criteria() == []
    assert _checklist(world, contract_id) == {
        **dict.fromkeys(CHECKLIST_CODES, True),
        "JUDGEMENT_RECORDS": False,
        "STEP1_RECORD": False,
    }
    stale = approve(world.app, pending_request, world.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    assert get(world.app, f"{JUDGEMENTS}/{pending}", world.place.author).json()["status"] == (
        "REJECTED"
    )
    assert criteria() == []
    assert _activation_requests(world, contract_id) == []
    assert _recognition(world) == []

    # --- positive control: the record resubmitted and reviewed after the gate ---
    # PRD SM-10: a rejected record returns to draft by an edit, is submitted again and reviewed.
    edited = patch(
        world.app,
        f"{JUDGEMENTS}/{pending}",
        world.place.author,
        {"rationale": "Letter of credit received on 10 September 2026."},
        if_match=None,
    )
    assert edited.status_code == 200, edited.text
    resubmitted = post(world.app, f"{JUDGEMENTS}/{pending}/submit", world.place.author, {})
    assert resubmitted.status_code == 200, resubmitted.text
    reviewed = approve(world.app, resubmitted.json()["approval_request_id"], world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    assert criteria() == ["ASC606"]
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    with world.place.uow() as uow:
        content = contract_activation_content(uow.session, contract_id)
    assert content["criteria_met"] == [
        {"book": "ASC606", "effective_date": "2026-09-10", "judgement_record_id": pending}
    ]
    assert _recognition(world) == []


def test_a_record_reviewed_for_another_book_serves_nothing(world: SeatWorld) -> None:
    """Ruling R-77 (7). "A record of that book" was checked where an assessment is recorded and
    nowhere else. The book of a REJECTED record is editable (PRD SM-10), and an assessment that
    cites a SUBMITTED record makes its review stale, hence REJECTED: re-reviewed for ANOTHER book
    it still passed ``STEP1_RECORD`` for the first. Every reader now asks the record for its
    contract, topic and book (``step1.serves``). Since ruling R-102 (b) the route takes a
    REVIEWED record only, so the sequence is reached below the route (an import, a migration)
    and the readers still answer. Positive control: a reviewed record of the assessed book
    passes."""
    from erev_api.events.payloads import CollectibilityAssessedV1

    maya = world.place.author
    contract_id = _created(world)
    record_id, request_id = _record(world, contract_id, "COLLECTIBILITY")  # book ASC606
    assert request_id is not None
    at_the_route = _record_events(world, contract_id, _assessment(record_id, probable=True))
    assert at_the_route.status_code == 422, at_the_route.text
    assert at_the_route.json()["errors"][0]["message"] == NOT_REVIEWED
    appended(
        world.place,
        contract_id,
        1,
        [
            EventIn(
                event_type=ContractEventType.COLLECTIBILITY_ASSESSED,
                effective_date=date(2026, 9, 1),
                payload=CollectibilityAssessedV1(
                    book=BookCode.ASC606, is_probable=True, judgement_record_id=UUID(record_id)
                ),
            )
        ],
    )
    stale = approve(world.app, request_id, world.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    # The preparer moves the rejected record to another book and has it reviewed there.
    moved = patch(world.app, f"{JUDGEMENTS}/{record_id}", maya, {"book": "IFRS15"}, if_match=None)
    assert moved.status_code == 200, moved.text
    assert (moved.json()["status"], moved.json()["book"]) == ("DRAFT", "IFRS15")
    sent = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", maya, {})
    assert sent.status_code == 200, sent.text
    reviewed = approve(world.app, sent.json()["approval_request_id"], world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    assert get(world.app, f"{JUDGEMENTS}/{record_id}", maya).json()["status"] == "REVIEWED"

    # The ASC 606 assessment still cites the record, which is REVIEWED — for IFRS 15.
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert fields(refused) == [(None, "STEP1_RECORD")]
    assert _activation_requests(world, contract_id) == []

    # Positive control: a reviewed record of the assessed book.
    own_book = _reviewed(world, contract_id, "COLLECTIBILITY")
    again = _record_events(world, contract_id, _assessment(own_book, probable=True))
    assert again.status_code == 201, again.text
    assert _step1(world, contract_id) == (True, None)


def test_criteria_met_moves_only_the_reassessed_book(world: SeatWorld) -> None:
    """Rulings R-20 (c) and R-77, two books with one moving (the review's untested case). Both
    books of AVM-US are assessed not probable behind the gate; ASC 606 alone is re-assessed
    probable on a new reviewed judgement. The approved activation appends
    ``CONTRACT_CRITERIA_MET`` for ASC 606 only: that book recognises, IFRS 15 stays
    NOT_A_CONTRACT under the ACTIVE header (04 T-CON-01 rev 1.126: the status per book governs
    the accounting), and the R-20 (d) invariant holds — the recognising book has the approved
    activation."""
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    asc606 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    ifrs15 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    gated = _record_events(
        world,
        contract_id,
        _assessment(asc606, probable=False),
        _assessment(ifrs15, probable=False, book="IFRS15"),
    )
    assert gated.status_code == 201, gated.text
    assert gated.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert gated.json()["step1_gate"] == APPENDED
    not_a_contract = {
        "ASC606": ("NOT_A_CONTRACT", Decimal("0")),
        "IFRS15": ("NOT_A_CONTRACT", Decimal("0")),
    }
    assert _books(world, contract_id) == not_a_contract
    _later(world)
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    reassessed = _record_events(
        world, contract_id, _assessment(met, probable=True, on="2026-09-10")
    )
    assert reassessed.status_code == 201, reassessed.text
    assert _books(world, contract_id) == not_a_contract
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)

    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]
    # What the approver decides on: one book moves; 985.40 = 108,000.00 × 10 / 1,096 days.
    moving = [
        {
            "book": "ASC606",
            "effective_date": "2026-09-10",
            "judgement_record_id": met,
            "catch_up_total": _usd("985.40"),
        }
    ]
    assert _preview_document(world, request_id)["after"]["criteria_met"] == moving
    shown = get(world.app, f"/api/v1/approvals/{request_id}", world.priya).json()
    assert shown["impact_preview"]["summary"]["criteria_met"] == moving
    head = _head(world, contract_id)
    approved = approve(world.app, request_id, world.priya)
    assert approved.status_code == 200, approved.text

    assert _header(world, contract_id) == ("ACTIVE", head + 2)
    appended_events = _stream(world, contract_id)[head:]
    assert [
        (str(event["event_type"]), event["payload"].get("book")) for event in appended_events
    ] == [("CONTRACT_CRITERIA_MET", "ASC606"), ("CONTRACT_ACTIVATED", None)]
    assert _books(world, contract_id) == {
        "ASC606": ("ACTIVE", Decimal("985.40")),
        "IFRS15": ("NOT_A_CONTRACT", Decimal("0")),
    }
    assert {key[0] for key in _posted(world, contract_id)} == {"ASC606"}
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_criteria_met_request_withdrawn_stale_and_its_events_not_voided(world: SeatWorld) -> None:
    """The review's untested ends of a criteria-met activation (rulings R-20 (c), R-61, R-77).
    Withdrawal returns the contract to NOT_A_CONTRACT and appends nothing. The request's content
    states the books that move, so what changes them without an event makes the decision stale
    (REQ-PLT-014): the record of a moving book SUPERSEDED by a newer review (PRD SM-10), and a
    moving book the entity no longer keeps. After the approved activation neither
    ``CONTRACT_CRITERIA_MET`` nor ``CONTRACT_ACTIVATED`` is voided as an event."""
    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    gate_asc = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    gate_ifrs = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    gated = _record_events(
        world,
        contract_id,
        _assessment(gate_asc, probable=False),
        _assessment(gate_ifrs, probable=False, book="IFRS15"),
    )
    assert gated.status_code == 201, gated.text
    assert gated.json()["step1_gate"] == APPENDED
    _later(world)
    met_asc = _reviewed(world, contract_id, "COLLECTIBILITY")
    met_ifrs = _reviewed(world, contract_id, "COLLECTIBILITY", book="IFRS15")
    reassessed = _record_events(
        world,
        contract_id,
        _assessment(met_asc, probable=True, on="2026-09-10"),
        _assessment(met_ifrs, probable=True, book="IFRS15", on="2026-09-10"),
    )
    assert reassessed.status_code == 201, reassessed.text
    head = _head(world, contract_id)

    def moving() -> list[tuple[str, str]]:
        with world.place.uow() as uow:
            content = contract_activation_content(uow.session, contract_id)
        return [(item["book"], item["judgement_record_id"]) for item in content["criteria_met"]]

    assert moving() == [("ASC606", met_asc), ("IFRS15", met_ifrs)]

    # --- withdrawal ---
    first = _submit(world, contract_id)
    assert first.status_code == 200, first.text
    assert _read_status(world, contract_id) == "PENDING_REVIEW"
    withdrawn = post(
        world.app, f"/api/v1/approvals/{first.headers[APPROVAL_HEADER]}/withdraw", maya, {}
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "WITHDRAWN"
    assert _read_status(world, contract_id) == "NOT_A_CONTRACT"
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", head)
    assert ("contract.not_a_contract", "PENDING_REVIEW", "NOT_A_CONTRACT") in _status_audits(
        world, contract_id
    )

    # --- stale by supersession: a newer reviewed record of the same topic, subject and book ---
    second = _submit(world, contract_id)
    assert second.status_code == 200, second.text
    newer = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert get(world.app, f"{JUDGEMENTS}/{met_asc}", maya).json()["status"] == "SUPERSEDED"
    assert moving() == [("IFRS15", met_ifrs)]
    superseded = approve(world.app, second.headers[APPROVAL_HEADER], world.priya)
    assert (superseded.status_code, slug(superseded)) == (409, "stale-approval")
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", head)
    again = _record_events(world, contract_id, _assessment(newer, probable=True, on="2026-09-10"))
    assert again.status_code == 201, again.text
    head += 1
    assert moving() == [("ASC606", newer), ("IFRS15", met_ifrs)]

    # --- stale by a book change: the entity no longer keeps a moving book ---
    third = _submit(world, contract_id)
    assert third.status_code == 200, third.text
    dropped = put(
        world.app,
        f"/api/v1/entities/{world.entity_id}/books/IFRS15",
        world.marcus,
        {"is_enabled": False},
    )
    assert dropped.status_code == 200, dropped.text
    assert moving() == [("ASC606", newer)]
    changed = approve(world.app, third.headers[APPROVAL_HEADER], world.priya)
    assert (changed.status_code, slug(changed)) == (409, "stale-approval")
    assert [status for status, _ in _activation_requests(world, contract_id)] == [
        "WITHDRAWN",
        "VOIDED",
        "VOIDED",
    ]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", head)
    assert _recognition(world) == []

    # --- the approved activation; its events are not voided ---
    fourth = _submit(world, contract_id)
    assert fourth.status_code == 200, fourth.text
    approved = approve(world.app, fourth.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    assert _header(world, contract_id) == ("ACTIVE", head + 2)
    for event in _stream(world, contract_id)[head:]:
        refused = post(
            world.app,
            f"/api/v1/events/{event['id']}/request-void",
            maya,
            {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded in error."},
        )
        assert refused.status_code == 409, (event["event_type"], refused.text)
        assert slug(refused) == "invalid-transition"
        assert refused.json()["detail"] == ACTIVATION_NOT_VOIDABLE
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_gate_is_withheld_for_a_group_over_the_obligation_budget(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rulings R-20 (b) and R-77 (6), the oversize branch. A group over the obligation budget
    (RCP-18: more than 200 obligations) is not computed in the request, so the engine cannot
    confirm the gate there: the assessment is recorded, the contract stays DRAFT, and because
    the computation is deferred the answer is the job — whose parameters, and so its result,
    state what became of the gate. The budget is lowered to the contract's single obligation."""
    from erev_api.domain.contracts import events as events_domain

    contract_id = _created(world)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    monkeypatch.setattr(events_domain, "OBLIGATION_BUDGET", 0)
    deferred = _record_events(world, contract_id, _assessment(record, probable=False))
    assert deferred.status_code == 202, deferred.text
    monkeypatch.undo()
    assert _event_types(world, contract_id) == ["CONTRACT_BOOKED", "COLLECTIBILITY_ASSESSED"]
    assert _header(world, contract_id) == ("DRAFT", 2)
    finished = _worked(world, str(deferred.json()["id"]))
    assert finished["state"] == "SUCCEEDED", finished
    assert finished["result"]["step1_gate"] == {"appended": False, "reason": "GROUP_TOO_LARGE"}
    # … and the audit detail of the recording states the same two members (ruling R-84 (b)).
    assert _audited_gates(world, contract_id) == [{"appended": False, "reason": "GROUP_TOO_LARGE"}]
    assert _books(world, contract_id) == {"ASC606": ("DRAFT", Decimal("0"))}
    assert _recognition(world) == []


def _behind_a_book_command(
    world: SeatWorld,
    name: str,
    run: Callable[[], Any],
    *,
    while_waiting: Callable[[], None] | None = None,
) -> Any:
    """Send the request ``run`` while another unit of work stands where ``PUT
    /entities/{id}/books/{code}`` and ``PATCH /books/{code}`` stand after their first statement —
    the ``book`` row of their code ``FOR UPDATE``, uncommitted (ruling R-80, exclusive side). The
    request is observed waiting ``FOR SHARE`` on ``book``, participant-bound (its backend blocked
    by the holder's backend); ``while_waiting`` runs then; the holder commits and the request's
    answer is returned."""
    place = world.place
    ctx = RequestContext(
        principal=system_principal(place.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=f"r-step1-{name}",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=place.clock.now(),
        format_locale="en-US",
    )
    outcome: dict[str, Any] = {}

    def call() -> None:
        try:
            outcome["result"] = run()
        except Exception as exc:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = exc

    with observing_checkouts() as backends:
        with unit_of_work(ctx, clock=place.clock, keyring=place.keyring, files=place.files) as t1:
            holder_pid = backend_pid(t1.session)
            t1.session.execute(
                select(book_table.c.id).where(book_table.c.code == "IFRS15").with_for_update()
            ).one()
            request = threading.Thread(target=call, name=name)
            request.start()
            blocked_pid, blocked_in = await_lock_wait(
                t1.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=20.0,
                expect="for share",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            assert "book" in blocked_in.lower(), blocked_in
            if while_waiting is not None:
                while_waiting()
            t1.commit()
        request.join(timeout=30)
    assert not request.is_alive() and "error" not in outcome, outcome
    return outcome["result"]


def test_gate_decisions_wait_for_a_book_command(world: SeatWorld) -> None:
    """Rulings R-77 (5) and R-80: a decision that reads the enabled books to decide a gate takes
    every ``book`` row of the tenant ``FOR SHARE`` before it reads ``entity_book``, and the book
    commands hold the row of their code ``FOR UPDATE`` from their first statement — so a book is
    not kept or disabled between the reading and the commit that appends the gate. Both shared
    sides are witnessed waiting for a book command that has not committed: the not-probable
    assessment of a DRAFT contract (nothing is appended while it waits; afterwards it decides the
    gate on the books as they then are), and the proposal of a combination group with a member
    behind the gate (``combination._gated_member_errors``). With the lock taken out the first
    request runs beside the uncommitted command and no wait is ever observed (null control run
    for the slice report)."""
    contract_id = _created(world)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    head = _head(world, contract_id)

    def nothing_appended() -> None:
        assert _event_types(world, contract_id) == ["CONTRACT_BOOKED"]

    assessed = _behind_a_book_command(
        world,
        "gate-decision",
        lambda: _append(world, contract_id, head, _assessment(record, probable=False)),
        while_waiting=nothing_appended,
    )
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["step1_gate"] == APPENDED
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)

    other = _created(world, external_id="SF-ORD-10418")
    proposed = _behind_a_book_command(
        world,
        "gated-join",
        lambda: post(
            world.app,
            GROUPS,
            world.place.author,
            {
                "contract_ids": [str(contract_id), str(other)],
                "criterion": "606-10-25-9(a)",
                "rationale": "Negotiated together.",
            },
        ),
    )
    # Both contracts are AVM-US's and computed in ASC 606 alone: the guard refuses nothing.
    assert proposed.status_code == 201, proposed.text


def test_a_stored_submission_meets_the_step1_refusals_again_at_its_approval(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling R-77 (9). The approval hook of an event submission appended whatever the submission
    stored, so a void of a Step 1 status event REQUESTED BEFORE the route refused it (ruling R-20)
    was still applied at its approval — replaying Table 2.2-A under the ``MANUAL_EVENT`` approval.
    The hook applies the refusals again under its locks, before its first write: the decision is
    not taken and nothing is appended. The stored submissions are made here as the route made them
    before the ruling (its refusal switched off for the two requests). Positive control: the void
    of a receipt is approved and appended as before.

    04 §16.3 rev 1.231 (item EVT-VOID-OWN-COMMANDS-1): the route refuses the two types a second
    way, by the allow-list of the fact-capture types, so the set-up switches that off as well."""
    from erev_api.domain.contracts import events as contract_events
    from erev_api.events import step1

    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _gated(world, contract_id)
    paid = _record_events(world, contract_id, RECEIPT)
    assert paid.status_code == 201, paid.text
    assessment, gate, receipt = _stream(world, contract_id)[1:4]
    void = {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded in error."}
    stored: list[str] = []
    with monkeypatch.context() as before_the_ruling:
        before_the_ruling.setattr(step1, "not_voidable", lambda event_type: None)
        before_the_ruling.setattr(contract_events, "VOIDABLE_TYPES", frozenset(ContractEventType))
        for event in (assessment, gate):
            requested = post(world.app, f"/api/v1/events/{event['id']}/request-void", maya, void)
            assert requested.status_code == 201, requested.text
            stored.append(str(requested.json()["approval_request_id"]))
    appended_before = _event_types(world, contract_id)

    for request_id, copy in zip(
        stored, (ASSESSMENT_NOT_VOIDABLE, ACTIVATION_NOT_VOIDABLE), strict=True
    ):
        refused = approve(world.app, request_id, world.priya)
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
        assert refused.json()["detail"] == copy
        assert fields(refused) == [("events.0.event_type", "DB-03")]
    assert _event_types(world, contract_id) == appended_before
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    statuses = world.place.rows(
        select(approval_request.c.status).where(
            approval_request.c.id.in_([UUID(value) for value in stored])
        )
    )
    assert [str(row["status"]) for row in statuses] == ["PENDING", "PENDING"]
    assert _recognition(world) == []

    # Positive control: the void of the receipt.
    requested = post(world.app, f"/api/v1/events/{receipt['id']}/request-void", maya, void)
    assert requested.status_code == 201, requested.text
    approved = approve(world.app, requested.json()["approval_request_id"], world.priya)
    assert approved.status_code == 200, approved.text
    assert _event_types(world, contract_id) == [*appended_before, "EVENT_VOIDED"]


def test_step1_event_is_not_dated_ahead_of_today_or_of_the_inception(world: SeatWorld) -> None:
    """Rulings R-82 (c) and R-84 (a). With no back-dating (R-77 (1)) and no void of an assessment,
    a Step 1 event recorded with a FUTURE date could be neither preceded nor removed. A
    ``COLLECTIBILITY_ASSESSED`` or ``SIGNIFICANT_CHANGE_FLAGGED`` is not dated after the later of
    the contracting entity's current date (the clock stands at 2026-09-12 in AVM-US's zone) and
    the contract's inception date. Inception past: today is accepted, tomorrow refused. Inception
    ahead (2026-09-20): the inception date is accepted — the contract is assessed at its
    inception, as the legacy import and the seeds do — and the day after it refused. The CSV v2
    import's shared service answers the same two refusals (no CSV v2 template carries a Step 1
    event today; the service is what any template would call)."""
    from uuid import uuid4

    from erev_api.domain.imports.csv_v2 import recorded as csv_recorded
    from erev_api.domain.imports.csv_v2.framework import ApplyContext, CsvRow, Plan
    from erev_api.problems import Problem
    from erev_api.schemas.events import EventAppendItemIn

    # --- inception 2026-09-01, past ---
    past = _created(world)
    record = _reviewed(world, past, "COLLECTIBILITY")
    for item, what in (
        (_assessment(record, probable=True, on="2026-09-13"), "assessment"),
        ({**FLAG, "effective_date": "2026-09-13"}, "significant-change flag"),
    ):
        refused = _record_events(world, past, item)
        assert refused.status_code == 422, refused.text
        assert fields(refused) == [("events.0.effective_date", "REQ-POL-008")]
        assert refused.json()["errors"][0]["message"] == STEP1_AHEAD.format(
            what=what, date="12 Sep 2026"
        )
    assert _event_types(world, past) == ["CONTRACT_BOOKED"]
    today = _record_events(
        world,
        past,
        _assessment(record, probable=True, on="2026-09-12"),
        {**FLAG, "effective_date": "2026-09-12"},
    )
    assert today.status_code == 201, today.text

    # --- inception 2026-09-20, ahead of the clock ---
    body = k09_body(world.customers["C-02"])
    body |= {"external_id": "SF-ORD-10517", "document_ref": "SF-ORD-10517"}
    body["inception_date"] = "2026-09-20"
    body["lines"][0]["start_date"] = "2026-09-20"
    drafted = post(world.app, CONTRACTS, world.place.author, body)
    assert drafted.status_code == 201, drafted.text
    ahead = UUID(str(drafted.json()["id"]))
    at_inception = _reviewed(world, ahead, "COLLECTIBILITY")
    day_after = _record_events(
        world, ahead, _assessment(at_inception, probable=True, on="2026-09-21")
    )
    assert day_after.status_code == 422, day_after.text
    assert fields(day_after) == [("events.0.effective_date", "REQ-POL-008")]
    assert day_after.json()["errors"][0]["message"] == STEP1_AHEAD.format(
        what="assessment", date="20 Sep 2026"
    )
    assessed = _record_events(
        world, ahead, _assessment(at_inception, probable=True, on="2026-09-20")
    )
    assert assessed.status_code == 201, assessed.text
    assert _step1(world, ahead) == (True, None)  # … and it is the one in force at inception

    # --- the same refusals where the CSV v2 event templates append (csv_v2.recorded.append) ---
    row = CsvRow(
        id=uuid4(), sheet_name="events", row_number=2, raw={}, normalized={}, business_key=None
    )
    context = ApplyContext(
        import_upload_id=uuid4(),
        file_sha256="0" * 64,
        template_code="progress_events",
        template_version=1,
        dry_run=True,
    )
    for external_id, record_id, on, bound in (
        ("SF-ORD-10417", record, "2026-09-13", "12 Sep 2026"),
        ("SF-ORD-10517", at_inception, "2026-09-21", "20 Sep 2026"),
    ):
        item = EventAppendItemIn.model_validate(_assessment(record_id, probable=True, on=on))
        plan = Plan(key=external_id, rows=(row,), body={})
        with world.place.uow() as uow, pytest.raises(Problem) as imported:
            csv_recorded.append(uow, plan, context=context, items=[item])
        assert (imported.value.slug, imported.value.status) == ("validation-failed", 422)
        assert [(error.field, error.rule_id, error.message) for error in imported.value.errors] == [
            (
                "events.0.effective_date",
                "REQ-POL-008",
                STEP1_AHEAD.format(what="assessment", date=bound),
            )
        ]


_TASK_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def _worked(world: SeatWorld | J03World, job_id: str) -> dict[str, Any]:
    """The worker fetches the job's task and runs it; API-S-Job afterwards."""
    place = world.place
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == UUID(job_id))
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    runtime = JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files)
    run_job(UUID(job_id), place.tenant_id, attempt=1, runtime=runtime)
    shown = get(world.app, f"/api/v1/jobs/{job_id}", place.author)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _previewed(world: SeatWorld | J03World, contract_id: UUID, *items: dict[str, Any]) -> Any:
    """``POST /contracts/{id}/events/preview`` and its job, run: the job's ``result``."""
    queued = post(
        world.app,
        f"{EVENTS}/preview".format(contract_id=contract_id),
        world.place.author,
        {"events": list(items)},
        if_match=f'"s{_head(world, contract_id)}"',
    )
    assert queued.status_code == 202, queued.text
    finished = _worked(world, str(queued.json()["id"]))
    assert finished["state"] == "SUCCEEDED", finished
    return finished["result"]


def test_preview_of_a_not_probable_assessment_shows_the_gate(world: SeatWorld) -> None:
    """Ruling R-77 (8). The preview job skipped Step 1: it computed the assessment alone, while
    recording appends the not-a-contract gate behind it. The preview now decides the gate as the
    append does, computes the batch WITH it and says what became of it (``result.step1_gate``; the
    events it counts include the gate). It appends nothing. Control: the preview of a probable
    assessment decides no gate; recording then does what the preview said."""
    contract_id = _created(world)
    probable = _reviewed(world, contract_id, "COLLECTIBILITY")
    # The control first: once the NOT_A_CONTRACT record below is reviewed it overtakes this one
    # (item STEP1-CITE-LATEST-1), and a probable assessment no longer cites it.
    plain = _previewed(world, contract_id, _assessment(probable, probable=True))
    assert plain["counts"] == {"events": 1}
    assert "step1_gate" not in plain

    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    shown = _previewed(world, contract_id, _assessment(record, probable=False))
    assert shown["step1_gate"] == APPENDED
    assert shown["counts"] == {"events": 2}  # the assessment and the gate behind it
    assert _header(world, contract_id) == ("DRAFT", 1)
    assert _event_types(world, contract_id) == ["CONTRACT_BOOKED"]

    recorded = _record_events(world, contract_id, _assessment(record, probable=False))
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["step1_gate"] == APPENDED
    assert [event["event_type"] for event in recorded.json()["events"]] == [
        "COLLECTIBILITY_ASSESSED",
        "CONTRACT_ACTIVATED",
    ]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)
    # The audit detail of the recording carries the same two members (ruling R-84 (b)); the two
    # previews recorded nothing and so audited no recording.
    assert _audited_gates(world, contract_id) == [APPENDED]


# --- a group of two entities (rulings R-20 (b), R-77 (5) and (6)) ---------------------------------

GROUPS = "/api/v1/combination-groups"
GATED_MEMBER = (
    "{contract} is assessed as not a contract. In this group it would also be computed in book "
    "{books}, which {entity} does not keep and where it has no assessment. Combine it after it "
    "is activated."
)


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> J03World:
    """PRD WLD-X-23: AVM-US and AVM-UK; ``SF-ORD-20417`` is contracted by AVM-US and its
    implementation line is performed by AVM-UK, so its group is computed in every book either
    entity keeps (``bundles.build``)."""
    return j03_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _uk_keeps_ifrs15(world: J03World) -> None:
    kept = put(
        world.app,
        f"/api/v1/entities/{world.uk_entity_id}/books/IFRS15",
        world.marcus,
        {"is_enabled": True},
    )
    assert kept.status_code == 200, kept.text


def _j03_contract(world: J03World, external_id: str, *, with_uk_line: bool) -> UUID:
    body = sf_ord_20417_body(world.customer_id, external_id=external_id)
    if not with_uk_line:
        body["lines"] = body["lines"][:1]  # the platform line alone: AVM-US contracts and performs
    created = post(world.app, CONTRACTS, world.place.author, body)
    assert created.status_code == 201, created.text
    return UUID(str(created.json()["id"]))


def test_gate_is_withheld_when_the_group_is_computed_in_a_book_of_another_entity(
    j03: J03World,
) -> None:
    """Rulings R-20 (b) and R-77 (6) on a real group of two entities (the review's untested
    case). AVM-UK, which performs a line of the contract, keeps IFRS 15; AVM-US, which contracts
    it, does not, so the group is computed in a book where the contract has no assessment.
    Measured here, not inferred: the engine refuses that computation (``ENGINE_INVARIANT_VIOLATED``
    — CV-13, AVM-US has no period state for the book), at the booking already, so the dry run of
    the gate confirms nothing. The assessment is recorded, the contract stays DRAFT and is
    activated in no book, and the answer names the reason — it is never silent. Positive control:
    a contract AVM-US contracts and performs alone takes the gate."""
    _uk_keeps_ifrs15(j03)
    contract_id = _j03_contract(j03, "SF-ORD-20417", with_uk_line=True)
    assert _books(j03, contract_id) == {}  # the booking's computation is quarantined (CV-13)
    record = _reviewed(j03, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    assessed = _record_events(j03, contract_id, _assessment(record, probable=False))
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["contract"]["status"] == "DRAFT"
    assert [event["event_type"] for event in assessed.json()["events"]] == [
        "COLLECTIBILITY_ASSESSED"
    ]
    assert assessed.json()["step1_gate"] == {"appended": False, "reason": "ENGINE_REFUSED"}
    assert assessed.json()["computation"]["status"] == "QUARANTINED"  # CV-13, as at the booking
    assert _header(j03, contract_id) == ("DRAFT", 2)
    assert _books(j03, contract_id) == {}
    # Positive control: AVM-US contracts and performs alone; its only book is assessed.
    alone = _j03_contract(j03, "SF-ORD-20419", with_uk_line=False)
    own = _reviewed(j03, alone, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    taken = _record_events(j03, alone, _assessment(own, probable=False))
    assert taken.status_code == 201, taken.text
    assert taken.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert taken.json()["step1_gate"] == APPENDED
    assert _books(j03, alone) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _recognition(j03) == []


def test_gated_contract_does_not_join_a_group_computed_in_another_book(j03: J03World) -> None:
    """Ruling R-77 (5), item STEP1-BOOK-ADOPTION-1 in ``combination``. A contract behind the
    not-a-contract gate is assessed in the books its own entity keeps. Combined with a contract
    whose group is computed in a book that entity does not keep, the gate would be replayed there
    with no assessment and the engine would activate it — through a ``COMBINATION_GROUP``
    approval that says nothing of Step 1. The guard stands at the three places a join is decided:
    the proposal, its submission, and the approval under its locks (a book kept after the request
    moves no stream head, so the approval's staleness check cannot see it). Positive control: while
    both groups are computed in ASC 606 alone, the same pair is proposed and submitted."""
    maya = j03.place.author
    gated = _j03_contract(j03, "SF-ORD-20419", with_uk_line=False)
    record = _reviewed(j03, gated, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    taken = _record_events(j03, gated, _assessment(record, probable=False))
    assert taken.status_code == 201, taken.text
    assert taken.json()["contract"]["status"] == "NOT_A_CONTRACT"
    other = _j03_contract(j03, "SF-ORD-20417", with_uk_line=True)
    proposal = {
        "contract_ids": [str(gated), str(other)],
        "criterion": "606-10-25-9(a)",
        "rationale": "Negotiated together.",
    }

    # Positive control: both groups are computed in ASC 606 only.
    first = post(j03.app, GROUPS, maya, proposal)
    assert first.status_code == 201, first.text
    sent = post(j03.app, f"{GROUPS}/{first.json()['id']}/submit", maya, {})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED"
    second = post(j03.app, GROUPS, maya, proposal)
    assert second.status_code == 201, second.text

    # AVM-UK keeps IFRS 15: the other contract's group, and so the combined one, is computed there.
    _uk_keeps_ifrs15(j03)
    message = GATED_MEMBER.format(contract="SF-ORD-20419", books="IFRS15", entity="AVM-US")
    # … at the approval, under its locks: nothing is applied.
    refused = approve(j03.app, sent.json()["approval_request_id"], j03.marcus)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == message
    assert "COMBINATION_CHANGED" not in _event_types(j03, gated)
    assert "COMBINATION_CHANGED" not in _event_types(j03, other)
    assert get(j03.app, f"{GROUPS}/{first.json()['id']}", maya).json()["status"] == "SUBMITTED"
    # … at the submission of a proposal made before the book was kept.
    late = post(j03.app, f"{GROUPS}/{second.json()['id']}/submit", maya, {})
    assert late.status_code == 422, late.text
    assert [rule for _, rule in fields(late)] == ["REQ-POL-008"]
    assert late.json()["errors"][0]["message"] == message
    # … and at a new proposal.
    third = post(j03.app, GROUPS, maya, proposal)
    assert third.status_code == 422, third.text
    assert [rule for _, rule in fields(third)] == ["REQ-POL-008"]
    assert third.json()["errors"][0]["message"] == message
    assert _books(j03, gated) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _recognition(j03) == []


# --- supervisor ruling R-102: the booking a judgement is made on (c), the reviewed record (b), ---
# --- and the criteria-met path of a book under an ACTIVE header (a) -------------------------------

OTHER_REASON = (
    "{book} is not a contract for a reason other than collectibility ({reason}). Recording "
    "criteria met does not activate it."
)
NOT_SUBMITTABLE = (
    "Only a draft contract, a contract that is not a contract, or an active contract with a book "
    "that is not a contract can be submitted for activation."
)


def _replaced(
    world: SeatWorld, contract_id: UUID, *, customer: str = "C-02", price: str = "90000.00"
) -> Any:
    """``POST /contracts/{id}/replace-draft`` by Maya: K-09, another customer, another price."""
    body = k09_body(world.customers[customer])
    body["lines"][0]["quantity"] = "25"
    body["lines"][0]["total_price"] = {"amount": price, "currency": "USD"}
    return post(
        world.app,
        f"{CONTRACTS}/{contract_id}/replace-draft",
        world.place.author,
        body,
        if_match=f'"s{_head(world, contract_id)}"',
    )


def _status_of(world: SeatWorld, record_id: str) -> str:
    return str(get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author).json()["status"])


def test_replace_draft_voids_the_step1_assessments_of_the_booking_it_replaces(
    world: SeatWorld,
) -> None:
    """Ruling R-102 (c), item STEP1-DRAFT-REPLACE-1 (measured through the routes before the fix).
    A draft with a reviewed Step 1 record and its probable assessment was replaced — another
    customer, another price — and the checklist still passed on the judgement made for the terms
    the replacement removed. A Step 1 judgement is made on the booking it judges: the SYSTEM
    append that voids the earlier booking voids the draft's standing assessments with it, so the
    item fails until Step 1 is done again; and the old record, still REVIEWED, is not cited again.
    Positive control: a judgement reviewed after the replacement carries the activation."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    judged = _reviewed(world, contract_id, "COLLECTIBILITY")
    assessed = _record_events(world, contract_id, _assessment(judged, probable=True))
    assert assessed.status_code == 201, assessed.text
    assert _step1(world, contract_id) == (True, None)
    _later(world)  # the replacement is recorded after the review

    replaced = _replaced(world, contract_id)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["customer"]["code"] == "C-02"
    assert replaced.json()["head_stream_version"] == 5
    booking, assessment, void_booking, void_assessment, rebooked = _stream(world, contract_id)
    assert [
        str(event["event_type"])
        for event in (booking, assessment, void_booking, void_assessment, rebooked)
    ] == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "EVENT_VOIDED",
        "EVENT_VOIDED",
        "CONTRACT_BOOKED",
    ]
    assert (void_booking["supersedes_event_id"], void_assessment["supersedes_event_id"]) == (
        booking["id"],
        assessment["id"],
    )
    for void in (void_booking, void_assessment):
        assert (str(void["origin"]), str(void["created_by_kind"])) == ("SYSTEM", "SYSTEM")
        assert void["payload"]["reason_code"] == "DATA_CORRECTION"
    assert void_assessment["effective_date"] == assessment["effective_date"]
    audited = world.place.rows(
        select(audit_event.c.object_version, audit_event.c.detail).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.action == "contract.replace_draft",
        )
    )
    assert [(row["object_version"], row["detail"]) for row in audited] == [
        (
            "5",
            {
                # The contract key every event of a contract-scoped object carries in its detail
                # (04 T-PLT-19 "Contract key" rev 1.154; supervisor ruling R-108) — the writer's
                # ``contract_id`` met this slice's detail at the integration ff106547.
                "contract_id": str(contract_id),
                "voided_event_id": str(void_booking["id"]),
                "booking_event_id": str(rebooked["id"]),
                "voided_assessment_event_ids": [str(assessment["id"])],
            },
        )
    ]
    assert _header(world, contract_id) == ("DRAFT", 5)
    assert _books(world, contract_id) == {"ASC606": ("DRAFT", Decimal("0"))}

    # The record is as it was; the replaced draft has no assessment.
    assert _status_of(world, judged) == "REVIEWED"
    assert _step1(world, contract_id) == (False, "Step 1 review not recorded.")
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert fields(refused) == [(None, "STEP1_RECORD")]
    assert _activation_requests(world, contract_id) == []
    # … and the judgement made on the replaced booking is not cited again, on the route or its
    # preview.
    for path in (EVENTS, f"{EVENTS}/preview"):
        again = post(
            world.app,
            path.format(contract_id=contract_id),
            world.place.author,
            {"events": [_assessment(judged, probable=True)]},
            if_match='"s5"',
        )
        assert again.status_code == 422, (path, again.text)
        assert fields(again) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
        assert again.json()["errors"][0]["message"] == REVIEWED_BEFORE_BOOKING
    assert _header(world, contract_id) == ("DRAFT", 5)

    # Positive control: a judgement made on the new booking.
    renewed = _reviewed(world, contract_id, "COLLECTIBILITY")
    recorded = _record_events(world, contract_id, _assessment(renewed, probable=True))
    assert recorded.status_code == 201, recorded.text
    assert _step1(world, contract_id) == (True, None)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    assert _header(world, contract_id)[0] == "ACTIVE"
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_a_not_probable_assessment_does_not_outlive_the_booking_it_judged(world: SeatWorld) -> None:
    """Ruling R-102 (c), the gate side (measured before the fix). Two books; ASC 606 assessed not
    probable, the gate withheld because IFRS 15 had no assessment; the draft replaced; then IFRS 15
    assessed not probable — and the gate followed, its ASC 606 half resting on the judgement made
    before the replacement. The voided assessment no longer counts: the gate is withheld until
    ASC 606 is judged again on the new booking. Behind the gate nothing is replaced."""
    _keep_ifrs15(world)
    contract_id = _created(world)
    first = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    withheld = _record_events(world, contract_id, _assessment(first, probable=False))
    assert withheld.status_code == 201, withheld.text
    assert withheld.json()["step1_gate"] == {"appended": False, "reason": "BOOK_NOT_ASSESSED"}
    _later(world)
    assert _replaced(world, contract_id).status_code == 200

    second = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    alone = _record_events(world, contract_id, _assessment(second, probable=False, book="IFRS15"))
    assert alone.status_code == 201, alone.text
    assert alone.json()["contract"]["status"] == "DRAFT"
    assert alone.json()["step1_gate"] == {"appended": False, "reason": "BOOK_NOT_ASSESSED"}
    assert "CONTRACT_ACTIVATED" not in _event_types(world, contract_id)

    # ASC 606 judged again on the new booking: every book is not probable and the gate follows.
    renewed = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    gated = _record_events(world, contract_id, _assessment(renewed, probable=False))
    assert gated.status_code == 201, gated.text
    assert gated.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert gated.json()["step1_gate"] == APPENDED
    assert _books(world, contract_id) == {
        "ASC606": ("NOT_A_CONTRACT", Decimal("0")),
        "IFRS15": ("NOT_A_CONTRACT", Decimal("0")),
    }
    behind = _replaced(world, contract_id)
    assert (behind.status_code, slug(behind)) == (409, "invalid-transition")
    assert _recognition(world) == []


def test_an_assessment_cites_a_reviewed_record_on_every_channel(world: SeatWorld) -> None:
    """Ruling R-102 (b), item STEP1-JR-STALE-1. An assessment that cited a SUBMITTED record moved
    the contract's head, which the record's ``JUDGEMENT_RECORD`` request pins: every such review
    went stale and the record ended REJECTED while its assessment stood. The record is REVIEWED
    before it is cited — on the events route, on its preview and where the CSV v2 event templates
    append. Positive control: nothing was appended, so the pending review is decided, and the
    reviewed record is then cited."""
    from uuid import uuid4

    from erev_api.domain.imports.csv_v2 import recorded as csv_recorded
    from erev_api.domain.imports.csv_v2.framework import ApplyContext, CsvRow, Plan
    from erev_api.problems import Problem
    from erev_api.schemas.events import EventAppendItemIn

    contract_id = _created(world)
    draft, _ = _record(world, contract_id, "COLLECTIBILITY", book=None, submit=False)
    pending, pending_request = _record(world, contract_id, "COLLECTIBILITY")
    assert pending_request is not None
    row = CsvRow(
        id=uuid4(), sheet_name="events", row_number=2, raw={}, normalized={}, business_key=None
    )
    context = ApplyContext(
        import_upload_id=uuid4(),
        file_sha256="0" * 64,
        template_code="progress_events",
        template_version=1,
        dry_run=True,
    )
    for record_id in (draft, pending):
        for path in (EVENTS, f"{EVENTS}/preview"):
            refused = post(
                world.app,
                path.format(contract_id=contract_id),
                world.place.author,
                {"events": [_assessment(record_id, probable=True)]},
                if_match='"s1"',
            )
            assert refused.status_code == 422, (path, refused.text)
            assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
            assert refused.json()["errors"][0]["message"] == NOT_REVIEWED
        item = EventAppendItemIn.model_validate(_assessment(record_id, probable=True))
        with world.place.uow() as uow, pytest.raises(Problem) as imported:
            csv_recorded.append(
                uow, Plan(key="SF-ORD-10417", rows=(row,), body={}), context=context, items=[item]
            )
        assert (imported.value.slug, imported.value.status) == ("validation-failed", 422)
        assert [(error.field, error.rule_id, error.message) for error in imported.value.errors] == [
            ("events.0.payload.judgement_record_id", "REQ-POL-008", NOT_REVIEWED)
        ]
    assert _header(world, contract_id) == ("DRAFT", 1)

    # Positive control: the head did not move, so the review is not stale; reviewed, it is cited.
    reviewed = approve(world.app, pending_request, world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    assert _status_of(world, pending) == "REVIEWED"
    recorded = _record_events(world, contract_id, _assessment(pending, probable=True))
    assert recorded.status_code == 201, recorded.text
    assert _step1(world, contract_id) == (True, None)


def _confirmations(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The books each call of ``activation._confirm_reentry`` was asked to confirm."""
    from erev_api.domain.contracts import activation

    seen: list[list[str]] = []
    confirm = activation._confirm_reentry

    def observed(
        session: Any, current: Any, bundle: Any, output: Any, criteria: Any, **kw: Any
    ) -> None:
        seen.append([item.book for item in criteria])
        confirm(session, current, bundle, output, criteria, **kw)

    monkeypatch.setattr(activation, "_confirm_reentry", observed)
    return seen


def _engine_runs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The trigger of every bundle the default engine computes from here on."""
    from erev_api.domain.contracts import computation

    seen: list[str] = []
    default = computation.default_engine

    def observed() -> Any:
        run = default()

        def counted(bundle: Any) -> Any:
            seen.append(str(bundle.trigger))
            return run(bundle)

        return counted

    monkeypatch.setattr(computation, "default_engine", observed)
    return seen


def test_criteria_met_path_of_a_book_under_an_active_header(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling R-102 (a), item CTR-STEP1-REENTRY-1: books that differed at the activation. ASC 606
    probable, IFRS 15 not probable: the approved activation leaves IFRS 15 NOT_A_CONTRACT under
    an ACTIVE header, and before this slice the book had no way back — ``submit-activation``
    refused an ACTIVE contract and the events route refuses ``CONTRACT_CRITERIA_MET``. The same
    approved path now serves the book: its criteria-met re-assessment rests on a COLLECTIBILITY
    record reviewed after the event that put the book out (here the activation event); the
    request is a ``CONTRACT_ACTIVATION`` a person decides; the engine confirms the book at the
    submission and again at the approval; the approval appends ``CONTRACT_CRITERIA_MET`` for the
    book and NO ``CONTRACT_ACTIVATED``; the header does not move. The R-20 (d) witness holds per
    book after every step."""
    confirmations = _confirmations(monkeypatch)
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    asc606 = _reviewed(world, contract_id, "COLLECTIBILITY")
    early = _reviewed(world, contract_id, "COLLECTIBILITY", book="IFRS15")  # before the book is out
    ifrs15 = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    differing = _record_events(
        world,
        contract_id,
        _assessment(asc606, probable=True),
        _assessment(ifrs15, probable=False, book="IFRS15"),
    )
    assert differing.status_code == 201, differing.text
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    activated = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert activated.status_code == 200, activated.text
    head = _head(world, contract_id)
    assert _header(world, contract_id) == ("ACTIVE", head)
    out = _books(world, contract_id)
    assert out["IFRS15"] == ("NOT_A_CONTRACT", Decimal("0")) and out["ASC606"][0] == "ACTIVE"
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert confirmations == []  # a DRAFT activation is no criteria-met path

    # --- before the re-assessment: the item says what is missing, and nothing is submitted ---
    assert _checklist(world, contract_id) == {
        **dict.fromkeys(CHECKLIST_CODES, True),
        "STEP1_RECORD": False,
    }
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert fields(refused) == [(None, "STEP1_RECORD")]
    # The re-assessment of the book that is out rests on a COLLECTIBILITY record reviewed after
    # the event that put it out: neither the record that put it out nor an earlier judgement.
    own = _record_events(
        world, contract_id, _assessment(ifrs15, probable=True, book="IFRS15", on="2026-09-10")
    )
    assert own.status_code == 422, own.text
    assert [error["message"] for error in own.json()["errors"]] == [
        "Use a judgement record of topic COLLECTIBILITY.",
        REVIEWED_BEFORE_GATE,
        NOT_PROBABLE_REVIEW,  # item STEP1-HOLD-RELEASE-1: the record answers No to criterion (e)
    ]
    before_out = _record_events(
        world, contract_id, _assessment(early, probable=True, book="IFRS15", on="2026-09-10")
    )
    assert before_out.status_code == 422, before_out.text
    assert fields(before_out) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert before_out.json()["errors"][0]["message"] == REVIEWED_BEFORE_GATE
    assert _header(world, contract_id) == ("ACTIVE", head)

    # --- the criteria-met re-assessment of IFRS 15, on a new judgement ---
    _later(world)
    met = _reviewed(world, contract_id, "COLLECTIBILITY", book="IFRS15")
    head = _head(world, contract_id)  # the judgement held and released the active contract
    reassessed = _record_events(
        world, contract_id, _assessment(met, probable=True, book="IFRS15", on="2026-09-10")
    )
    assert reassessed.status_code == 201, reassessed.text
    assert reassessed.json()["step1_gate"] is None
    assert _books(world, contract_id)["IFRS15"] == ("NOT_A_CONTRACT", Decimal("0"))  # nothing yet
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)

    requested = _submit(world, contract_id)
    assert requested.status_code == 200, requested.text
    request_id = requested.headers[APPROVAL_HEADER]
    # The header does not move and neither does the read model; a person decides.
    assert requested.json()["status"] == "ACTIVE"
    assert _read_status(world, contract_id) == "ACTIVE"
    assert _header(world, contract_id) == ("ACTIVE", head + 1)
    # The criteria-met request of the ACTIVE contract states the flags from its record again:
    # ``NEW_SKU`` still, since no OTHER activated contract holds a line of its product (item
    # ACT-FLAGS-1, the rule as the supervisor ruled it).
    assert _activation_requests(world, contract_id)[-1] == ("PENDING", K09_FLAGS)
    assert confirmations == [["IFRS15"]]
    again = _submit(world, contract_id)
    assert (again.status_code, slug(again)) == (409, "invalid-transition")
    # What the approver decides on. 1,182.48 = 108,000.00 × 12 / 1,096 days: the version's date
    # is 2026-09-12, the date of the hold the judgement's review applied and released on the
    # active contract (REQ-POL-010), so the figure includes the days since the criteria-met date
    # (04 §16.10; supervisor ruling R-61 (e)).
    moving = [
        {
            "book": "IFRS15",
            "effective_date": "2026-09-10",
            "judgement_record_id": met,
            "catch_up_total": _usd("1182.48"),
        }
    ]
    document = _preview_document(world, request_id)
    assert (document["before"]["status"], document["after"]["status"]) == ("ACTIVE", "ACTIVE")
    assert document["after"]["criteria_met"] == moving
    shown = get(world.app, f"/api/v1/approvals/{request_id}", world.priya).json()
    assert shown["impact_preview"]["summary"]["criteria_met"] == moving
    with world.place.uow() as uow:
        content = contract_activation_content(uow.session, contract_id)
    assert content["criteria_met"] == [
        {"book": "IFRS15", "effective_date": "2026-09-10", "judgement_record_id": met}
    ]
    audits_before = _status_audits(world, contract_id)

    # --- the approval: CONTRACT_CRITERIA_MET for the book, no CONTRACT_ACTIVATED ---
    approved = approve(world.app, request_id, world.priya)
    assert approved.status_code == 200, approved.text
    assert confirmations == [["IFRS15"], ["IFRS15"]]  # … confirmed again under the locks
    assert _header(world, contract_id) == ("ACTIVE", head + 2)
    (appended_event,) = _stream(world, contract_id)[head + 1 :]
    assert (
        str(appended_event["event_type"]),
        appended_event["payload"]["book"],
        appended_event["payload"]["judgement_record_id"],
        appended_event["effective_date"],
        str(appended_event["origin"]),
        str(appended_event["approval_request_id"]),
    ) == ("CONTRACT_CRITERIA_MET", "IFRS15", met, date(2026, 9, 10), "SYSTEM", request_id)
    assert _event_types(world, contract_id).count("CONTRACT_ACTIVATED") == 1
    assert _status_audits(world, contract_id) == audits_before  # no status moved
    # The catch-up brings the book to where ASC 606 stands: twelve days of 108,000.00 / 1,096.
    assert _books(world, contract_id) == {
        "ASC606": ("ACTIVE", Decimal("1182.48")),
        "IFRS15": ("ACTIVE", Decimal("1182.48")),
    }
    assert _recognition(world) == [
        ("SF-ORD-10417", "ASC606", "ACTIVE"),
        ("SF-ORD-10417", "IFRS15", "ACTIVE"),
    ]
    assert _unapproved_recognition(world) == []
    # Per book: the book that returned to recognition has its CONTRACT_CRITERIA_MET, carrying an
    # APPROVED CONTRACT_ACTIVATION request.
    assert _activation_requests(world, contract_id)[-1][0] == "APPROVED"

    # Nothing is out any more: there is nothing to submit — and the refusal costs no computation
    # of the group (the cheap pre-check): the stored versions already say that no book is out.
    runs = _engine_runs(monkeypatch)
    nothing = _submit(world, contract_id)
    assert (nothing.status_code, slug(nothing)) == (409, "invalid-transition")
    assert nothing.json()["detail"] == NOT_SUBMITTABLE
    assert runs == []
    assert confirmations == [["IFRS15"], ["IFRS15"]]


def test_criteria_met_path_after_a_25_5_reassessment(world: SeatWorld) -> None:
    """Ruling R-102 (a): a 606-10-25-5 reassessment later cured. An ACTIVE contract; a
    significant-change flag; a not-probable assessment — the book is NOT_A_CONTRACT from that
    date, under an ACTIVE header. The cure is the same approved path: a probable re-assessment on
    a collectibility record reviewed after the reassessment was recorded, submitted for
    activation. A rejected request changes nothing; a request made stale by a later event is
    voided, not applied; the approved one appends ``CONTRACT_CRITERIA_MET`` and the book
    recognises again, with the catch-up."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _activated(world, contract_id)
    assert _record_events(world, contract_id, FLAG).status_code == 201
    not_probable = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    moved = _record_events(
        world, contract_id, _assessment(not_probable, probable=False, on="2026-09-08")
    )
    assert moved.status_code == 201, moved.text
    # Out at 2026-09-08: the eight days to that date stay recognised, 788.32 = 108,000.00 × 8 /
    # 1,096 (the engine's figure; the same day count gives 985.40 at a criteria-met date ten
    # days in).
    status, recognised = _books(world, contract_id)["ASC606"]
    assert (status, recognised) == ("NOT_A_CONTRACT", Decimal("788.32"))
    assert _checklist(world, contract_id)["STEP1_RECORD"] is False  # the book is out, no cure yet
    _later(world)
    cure = _reviewed(world, contract_id, "COLLECTIBILITY")
    reassessed = _record_events(
        world, contract_id, _assessment(cure, probable=True, on="2026-09-10")
    )
    assert reassessed.status_code == 201, reassessed.text
    assert _books(world, contract_id)["ASC606"] == (status, recognised)
    assert _checklist(world, contract_id) == dict.fromkeys(CHECKLIST_CODES, True)
    still_out = (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    )

    # A rejected request changes nothing.
    first = _submit(world, contract_id)
    assert first.status_code == 200, first.text
    assert _read_status(world, contract_id) == "ACTIVE"
    rejected = reject(world.app, first.headers[APPROVAL_HEADER], world.priya, "Not yet.")
    assert rejected.status_code == 200, rejected.text
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    ) == still_out
    # A request made stale by a later event is voided, not applied.
    second = _submit(world, contract_id)
    assert second.status_code == 200, second.text
    paid = _record_events(world, contract_id, RECEIPT)
    assert paid.status_code == 201, paid.text
    stale = approve(world.app, second.headers[APPROVAL_HEADER], world.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval")
    assert "CONTRACT_CRITERIA_MET" not in _event_types(world, contract_id)
    assert _books(world, contract_id)["ASC606"][0] == "NOT_A_CONTRACT"
    assert _recognition(world) == _unapproved_recognition(world) == []

    # The approved request: criteria met for the book, and no activation event.
    third = _submit(world, contract_id)
    assert third.status_code == 200, third.text
    request_id = third.headers[APPROVAL_HEADER]
    assert [state for state, _ in _activation_requests(world, contract_id)] == [
        "APPROVED",
        "REJECTED",
        "VOIDED",
        "PENDING",
    ]
    head = _head(world, contract_id)
    approved = approve(world.app, request_id, world.priya)
    assert approved.status_code == 200, approved.text
    assert _header(world, contract_id) == ("ACTIVE", head + 1)
    last = _stream(world, contract_id)[-1]
    assert (str(last["event_type"]), last["payload"]["book"], last["effective_date"]) == (
        "CONTRACT_CRITERIA_MET",
        "ASC606",
        date(2026, 9, 10),
    )
    assert _event_types(world, contract_id).count("CONTRACT_ACTIVATED") == 1
    # The catch-up (POL-013): twelve days to the version's date, 1,182.48 = 108,000.00 × 12 / 1,096.
    assert _books(world, contract_id)["ASC606"] == ("ACTIVE", Decimal("1182.48"))
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_a_book_out_for_another_reason_is_refused_by_name(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling R-102 (a), Q1 (candidate AD-56): the criteria-met path serves a book the engine put
    out as NOT_PROBABLE only. A contract without commercial substance, activated on a probable
    assessment, is NOT_A_CONTRACT in the engine for 606-10-25-1(d) under an ACTIVE header; Table
    2.2-A would leave that status on ``CONTRACT_CRITERIA_MET`` whatever the reason and does not
    test commercial substance again, so the platform does not append it: ``submit-activation`` is
    refused by name (PRD IMP-133), a known limitation. With the five criteria (rulings R-113 (f),
    R-115 (f)) every review of this contract answers No to (d) — the answer agrees with the
    contract — and such a review serves the draft's probable assessment, where the engine tests
    (d), but no criteria-met re-assessment, where it does not: the route refuses the cure by name
    (PRD IMP-135) before any request could be made."""
    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    body = k09_body(world.customers["C-09"])
    body["has_commercial_substance"] = False
    drafted = post(world.app, CONTRACTS, maya, body)
    assert drafted.status_code == 201, drafted.text
    contract_id = UUID(str(drafted.json()["id"]))
    # (d) agrees with the contract wherever the record is written: a Yes is refused by name.
    disagreeing = post(
        world.app,
        JUDGEMENTS,
        maya,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "conclusion": "Collection is probable.",
            "rationale": "Credit review.",
            "questionnaire": {"criteria": step1_criteria()},
        },
    )
    assert disagreeing.status_code == 422, disagreeing.text
    assert fields(disagreeing) == [("questionnaire.criteria.d", "T-CON-19")]
    lacking = {"criteria": step1_criteria(d="NO")}
    probable = _reviewed(world, contract_id, "COLLECTIBILITY", lacking)
    assert (
        _record_events(world, contract_id, _assessment(probable, probable=True))
    ).status_code == 201
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    assert approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya).status_code == 200
    # The engine's own reading: the header is ACTIVE, the book is not a contract (25-1(d)).
    assert _header(world, contract_id)[0] == "ACTIVE"
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}

    # Nothing re-assessed: the Step 1 events show no book out as not probable; the engine does.
    # The stored version says NOT_A_CONTRACT without a reason, so this refusal is the one that
    # still reads a dry run — only the engine names the reason.
    runs = _engine_runs(monkeypatch)
    plain = _submit(world, contract_id)
    assert runs == ["DRY_RUN"]
    assert (plain.status_code, slug(plain)) == (409, "activation-checklist-failed")
    assert fields(plain) == [(None, "STEP1_RECORD")]
    assert plain.json()["errors"][0]["message"] == OTHER_REASON.format(
        book="ASC606", reason="no commercial substance"
    )

    # A flag and a not-probable assessment: by the Step 1 events alone the book is now out as
    # not probable (606-10-25-5); the engine never left its first reason. The cure — a probable
    # re-assessment — is refused where it is recorded: the review answers No to (d).
    assert _record_events(world, contract_id, FLAG).status_code == 201
    not_probable = _reviewed(
        world,
        contract_id,
        "NOT_A_CONTRACT",
        {**NOT_A_CONTRACT, "criteria": step1_criteria("NOT_A_CONTRACT", d="NO")},
    )
    assert (
        _record_events(
            world, contract_id, _assessment(not_probable, probable=False, on="2026-09-08")
        )
    ).status_code == 201
    _later(world)
    cure = _reviewed(world, contract_id, "COLLECTIBILITY", lacking)
    head = _head(world, contract_id)
    refused = _record_events(world, contract_id, _assessment(cure, probable=True, on="2026-09-10"))
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert refused.json()["errors"][0]["message"] == CRITERION_NOT_MET.format(
        criterion_label="Commercial substance"
    )
    nothing = _submit(world, contract_id)
    assert (nothing.status_code, slug(nothing)) == (409, "activation-checklist-failed")
    # Item STEP1-CITE-LATEST-1: the book's latest assessment — the not-probable one — rests on
    # a record that the cure's review has overtaken, and the item says so (PRD IMP-143) where
    # it said "Step 1 review not recorded."
    assert nothing.json()["errors"][0]["message"] == STEP1_OVERTAKEN.format(
        book="ASC606",
        judgement_no=_judgement_no(world, not_probable),
        later_judgement_no=_judgement_no(world, cure),
    )
    assert [state for state, _ in _activation_requests(world, contract_id)] == ["APPROVED"]
    assert _header(world, contract_id) == ("ACTIVE", head)
    assert "CONTRACT_CRITERIA_MET" not in _event_types(world, contract_id)
    assert _books(world, contract_id) == {"ASC606": ("NOT_A_CONTRACT", Decimal("0"))}
    assert _recognition(world) == []


# --- supervisor rulings R-113 (f), R-115 (f): five criteria are recorded and each can stop --------


def test_a_review_that_answers_no_to_a_b_or_c_carries_no_activation(world: SeatWorld) -> None:
    """Rulings R-113 (f) and R-115 (f), item STEP1-CRITERIA-1 (browser findings Q-52, Q-53). The
    five answers of a Step 1 review were a convention of the form: a No on "Approved and
    committed" was stored and changed nothing, so a contract activated on a review that said its
    parties had not approved it. A review that answers No to (a), (b) or (c) serves no probable
    assessment — refused by name where it is recorded — and no activation: the checklist fails
    by name for ANY enabled book whose latest assessment rests on such a review, a not-probable
    one too. The review still serves the not-probable assessment and its gate. Positive control:
    the same conclusion on a review whose first three criteria are met lets the activation go to
    its approver."""
    maya = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    _keep_ifrs15(world)
    contract_id = _created(world)
    rights = CRITERION_NOT_MET.format(criterion_label="Rights identified")
    approved = CRITERION_NOT_MET.format(criterion_label="Approved and committed")

    # A probable assessment on a review that answers No to (b): refused by name, route and preview.
    not_identified = _reviewed(
        world, contract_id, "COLLECTIBILITY", {"criteria": step1_criteria(b="NO")}
    )
    for path in (EVENTS, f"{EVENTS}/preview"):
        refused = post(
            world.app,
            path.format(contract_id=contract_id),
            maya,
            {"events": [_assessment(not_identified, probable=True)]},
            if_match='"s1"',
        )
        assert refused.status_code == 422, (path, refused.text)
        assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
        assert refused.json()["errors"][0]["message"] == rights
    assert _header(world, contract_id) == ("DRAFT", 1)

    # Books that differ: ASC 606 probable on a sound review; IFRS 15 not probable on a review
    # that also answers No to (a). The not-probable assessment is recorded — the review serves it
    # — and the activation, which would make ASC 606 ACTIVE, is refused by name.
    sound = _reviewed(world, contract_id, "COLLECTIBILITY")
    unapproved = _reviewed(
        world,
        contract_id,
        "NOT_A_CONTRACT",
        {**NOT_A_CONTRACT, "criteria": step1_criteria("NOT_A_CONTRACT", a="NO")},
        book="IFRS15",
    )
    differing = _record_events(
        world,
        contract_id,
        _assessment(sound, probable=True),
        _assessment(unapproved, probable=False, book="IFRS15"),
    )
    assert differing.status_code == 201, differing.text
    assert differing.json()["step1_gate"] == {"appended": False, "reason": "BOOK_NOT_ASSESSED"}
    assert _step1(world, contract_id) == (False, approved)
    stopped = _submit(world, contract_id)
    assert (stopped.status_code, slug(stopped)) == (409, "activation-checklist-failed")
    assert fields(stopped) == [(None, "STEP1_RECORD")]
    assert stopped.json()["errors"][0]["message"] == approved
    assert _activation_requests(world, contract_id) == []
    assert _header(world, contract_id) == ("DRAFT", 3)
    assert _recognition(world) == []

    # Positive control: IFRS 15 judged not probable on a review whose first three criteria are
    # met. The item passes and the activation goes to a person (a book stays not a contract).
    met = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book="IFRS15")
    again = _record_events(world, contract_id, _assessment(met, probable=False, book="IFRS15"))
    assert again.status_code == 201, again.text
    assert _step1(world, contract_id) == (True, None)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    assert [state for state, _ in _activation_requests(world, contract_id)] == ["PENDING"]


def test_the_gate_and_criteria_met_read_the_five_criteria(world: SeatWorld) -> None:
    """Rulings R-113 (f) and R-115 (f) behind the not-a-contract gate. A review that answers No to
    (a) with (e) serves the not-probable assessment and its gate — the contract is not one, and
    deposit accounting starts. Criteria met is then a new review: one that still answers No to
    (c) carries no criteria-met re-assessment (refused by name), and while a book's latest
    assessment rests on a No the activation is refused by name too. Positive control: a review
    that answers Yes to all five moves the book through the approved activation."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    gate_record = _reviewed(
        world,
        contract_id,
        "NOT_A_CONTRACT",
        {**NOT_A_CONTRACT, "criteria": step1_criteria("NOT_A_CONTRACT", a="NO")},
    )
    gated = _record_events(world, contract_id, _assessment(gate_record, probable=False))
    assert gated.status_code == 201, gated.text
    assert gated.json()["contract"]["status"] == "NOT_A_CONTRACT"
    assert gated.json()["step1_gate"] == APPENDED
    _later(world)
    # Behind the gate the item names the criterion the standing review answers No to.
    assert _step1(world, contract_id) == (
        False,
        CRITERION_NOT_MET.format(criterion_label="Approved and committed"),
    )

    terms_open = _reviewed(
        world, contract_id, "COLLECTIBILITY", {"criteria": step1_criteria(c="NO")}
    )
    refused = _record_events(
        world, contract_id, _assessment(terms_open, probable=True, on="2026-09-10")
    )
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert refused.json()["errors"][0]["message"] == CRITERION_NOT_MET.format(
        criterion_label="Payment terms identified"
    )
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)
    stopped = _submit(world, contract_id)
    assert (stopped.status_code, slug(stopped)) == (409, "activation-checklist-failed")
    assert _activation_requests(world, contract_id) == []

    # Positive control: every criterion met, on a review made after the gate.
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    recorded = _record_events(world, contract_id, _assessment(met, probable=True, on="2026-09-10"))
    assert recorded.status_code == 201, recorded.text
    assert _step1(world, contract_id) == (True, None)
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
    assert approved.status_code == 200, approved.text
    assert _books(world, contract_id)["ASC606"] == ("ACTIVE", Decimal("985.40"))
    assert _unapproved_recognition(world) == []


# --- item STEP1-HOLD-RELEASE-1 (the supervisor's ruling of 2026-10-01; 04 T-CON-20, §16.3 (g)) ----

# 04 T-CON-20 "Judgement holds" (rev 1.209): the reason of a NOT_A_CONTRACT record's hold, the
# two refusals of a release by hand and the comments of the SYSTEM releases.
HOLD_STEP1 = (
    "Judgement record {judgement_no} (NOT_A_CONTRACT) is not reviewed, or the Step 1 assessment "
    "that cites it is not recorded."
)
RELEASED_BY_REVIEW = "This hold is released by the review of judgement record {judgement_no}."
RELEASED_BY_ASSESSMENT = (
    "This hold is released when the Step 1 assessment that cites judgement record "
    "{judgement_no} is recorded."
)
ASSESSMENT_RECORDED = (
    "The Step 1 assessment that cites judgement record {judgement_no} was recorded."
)
RECORD_SUPERSEDED = (
    "Judgement record {judgement_no} was superseded by judgement record {superseded_by}."
)
RECORD_OVERTAKEN = (
    "Judgement record {judgement_no} was overtaken by the review of judgement record "
    "{overtaken_by}."
)
RECORD_REVIEWED = "Judgement record {judgement_no} was reviewed."
HOLD_COLLECTIBILITY = "Judgement record {judgement_no} (COLLECTIBILITY) is not reviewed."
# 04 §16.3 (b) rev 1.209 (the supervisor's ruling on the lane's question 1): what a probable
# assessment meets when it cites a record that answers No to criterion (e).
USE_COLLECTIBILITY = "Use a judgement record of topic COLLECTIBILITY."
NOT_PROBABLE_REVIEW = (
    "The Step 1 review answers No for Collectibility probable: the contract is not activated "
    "until the criterion is met."
)
# PRD IMP-136 (04 table 15.4-I ``STEP1_CHANGE_NOT_FLAGGED``).
CHANGE_NOT_FLAGGED = (
    "A not-probable assessment of an active contract takes effect only after a significant "
    "change is flagged. Record the flag first."
)
# K-09 at the clock of these witnesses (2026-09-12): 108,000.00 over 1,096 days. ``_books`` reads
# the cumulative revenue of the book's latest version, which is as of the latest event's date:
# five days behind the flag of 2026-09-05; twelve once an event of the clock's day leaves the
# book active; a recognition hold placed that day freezes the book at the day before
# (ENGINE_SPEC_B S09-R-43), eleven days; out at 2026-09-08, eight days stay.
AT_THE_FLAG = ("ACTIVE", Decimal("492.70"))
ACTIVE_TO_DATE = ("ACTIVE", Decimal("1182.48"))
HELD = ("ACTIVE", Decimal("1083.94"))
OUT_AT_THE_EIGHTH = ("NOT_A_CONTRACT", Decimal("788.32"))


def _judgement_no(world: SeatWorld, record_id: str) -> str:
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return str(shown.json()["judgement_no"])


def _holds(world: SeatWorld, contract_id: UUID) -> list[tuple[str, str, str | None]]:
    """(source, reason, the comment of its release — None while it is open) of the contract's
    holds in the order they were applied, read from the stream; the T-CON-20 projection agrees
    with it (a row is open exactly where no release names it)."""
    stream = _stream(world, contract_id)
    released = {
        str(event["payload"]["hold_id"]): str(event["payload"]["comment"])
        for event in stream
        if str(event["event_type"]) == "HOLD_RELEASED"
    }
    applied = [
        (str(event["id"]), str(event["payload"]["hold_source"]), str(event["payload"]["reason"]))
        for event in stream
        if str(event["event_type"]) == "HOLD_APPLIED"
    ]
    assert set(_open_holds(world, contract_id)) == {
        hold_id for hold_id, _, _ in applied if hold_id not in released
    }
    return [(source, reason, released.get(hold_id)) for hold_id, source, reason in applied]


def _open_holds(world: SeatWorld, contract_id: UUID) -> list[str]:
    rows = world.place.rows(
        select(contract_hold.c.id).where(
            contract_hold.c.contract_id == contract_id, contract_hold.c.released_at.is_(None)
        )
    )
    return [str(row["id"]) for row in rows]


def _release_by_hand(world: SeatWorld, contract_id: UUID, hold_id: str) -> Any:
    return post(
        world.app,
        f"{CONTRACTS}/{contract_id}/release-hold",
        world.place.author,
        {"hold_id": hold_id, "comment": "Released by hand by the preparer."},
        if_match=f'"s{_head(world, contract_id)}"',
    )


def _on_hold(world: SeatWorld, contract_id: UUID) -> bool:
    shown = get(world.app, f"{CONTRACTS}/{contract_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return bool(shown.json()["on_hold"])


def _released_in_audit(world: SeatWorld, contract_id: UUID) -> list[Any]:
    """``released_hold_event_ids`` in the audit detail of each ``contract.record_events`` of the
    contract, in stream order; None for a request that released no hold."""
    rows = world.place.rows(
        select(audit_event.c.object_version, audit_event.c.detail).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.object_type == "contract",
            audit_event.c.action == "contract.record_events",
        )
    )
    ordered = sorted(rows, key=lambda row: int(row["object_version"]))
    return [(row["detail"] or {}).get("released_hold_event_ids") for row in ordered]


def _flagged_and_held(world: SeatWorld) -> tuple[UUID, str, str, str]:
    """K-09 ACTIVE with a significant-change flag and a NOT_A_CONTRACT record that waits for its
    review: the contract, the record, its review request and the reason of its hold."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _activated(world, contract_id)
    assert _record_events(world, contract_id, FLAG).status_code == 201
    assert _books(world, contract_id)["ASC606"] == AT_THE_FLAG
    record, request = _record(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    assert request is not None
    reason = HOLD_STEP1.format(judgement_no=_judgement_no(world, record))
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]
    return contract_id, record, request, reason


def test_step1_hold_release_1_a_not_a_contract_hold_ends_at_the_assessment_that_cites_it(
    world: SeatWorld,
) -> None:
    """Item STEP1-HOLD-RELEASE-1 (the supervisor's ruling of 2026-10-01). An ACTIVE contract is
    reassessed under 606-10-25-5: the flag, a NOT_A_CONTRACT record, its review, the not-probable
    assessment that cites it. The record's REQ-POL-010 hold was released by the REVIEW, so from
    the review to the assessment the book recognised revenue under a reviewed "not a contract";
    and while the review was pending the preparer released the hold alone. Now: the preparer's
    release by hand is refused by name while the record waits for its review; the review
    releases nothing and the release by hand stays refused, by the assessment's name; the
    assessment is appended with the SYSTEM release behind it in one unit of work and one
    computation, and the preview computes the same two events. The figures: 1,182.48 active,
    1,083.94 held from the submission to the assessment (the review posts nothing), 788.32 once
    the book is out at 2026-09-08."""
    contract_id, record, request, reason = _flagged_and_held(world)
    number = _judgement_no(world, record)
    (hold_id,) = _open_holds(world, contract_id)
    assert _books(world, contract_id)["ASC606"] == HELD

    early = _release_by_hand(world, contract_id, hold_id)
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert early.json()["detail"] == RELEASED_BY_REVIEW.format(judgement_no=number)

    reviewed = approve(world.app, request, world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    assert _status_of(world, record) == "REVIEWED"
    # (a) the review releases nothing: no event behind the hold, the book as it was held
    assert _event_types(world, contract_id)[-1] == "HOLD_APPLIED"
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]
    assert _on_hold(world, contract_id) is True
    assert _books(world, contract_id)["ASC606"] == HELD
    late = _release_by_hand(world, contract_id, hold_id)
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text
    assert late.json()["detail"] == RELEASED_BY_ASSESSMENT.format(judgement_no=number)
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]

    # (b) the assessment that cites the record, and the release behind it
    assessment = _assessment(record, probable=False, on="2026-09-08")
    shown = _previewed(world, contract_id, assessment)
    assert shown["counts"] == {"events": 2}  # the assessment and the release behind it
    assert "step1_gate" not in shown
    september = next(
        item for item in shown["summary"]["revenue_by_period"] if item["period_key"] == "FY2026-P09"
    )
    assert (september["before"]["amount"], september["after"]["amount"]) == ("1083.94", "788.32")
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]  # a preview appends nothing
    head = _head(world, contract_id)
    assessed = _record_events(world, contract_id, assessment)
    assert assessed.status_code == 201, assessed.text
    body = assessed.json()
    assert [(event["event_type"], event["origin"]) for event in body["events"]] == [
        ("COLLECTIBILITY_ASSESSED", "UI"),
        ("HOLD_RELEASED", "SYSTEM"),
    ]
    assert body["computation"]["status"] == "SUCCEEDED", body["computation"]
    assert body["step1_gate"] is None
    assert (body["contract"]["status"], body["contract"]["on_hold"]) == ("ACTIVE", False)
    assert _header(world, contract_id) == ("ACTIVE", head + 2)
    assert _holds(world, contract_id) == [
        ("SYSTEM", reason, ASSESSMENT_RECORDED.format(judgement_no=number))
    ]
    assert _released_in_audit(world, contract_id)[-1] == [body["events"][1]["id"]]
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    assert _recognition(world) == _unapproved_recognition(world) == []


def _reopened_assessment_period(world: SeatWorld, state_id: str) -> None:
    """Seed DB-valid close/reopen history; this fixture does not certify a real close run."""
    for previous, state, kind in [("closing", "closed", "LOCK"), ("closed", "reopened", "REOPEN")]:
        with world.place.uow() as uow:
            row = (
                uow.session.execute(select(period_state).where(period_state.c.id == UUID(state_id)))
                .mappings()
                .one()
            )
            transition_id = new_id()
            parts = CloseParts(
                calendar_id=UUID(int=0),
                entity_id=world.entity_id,
                period_id=row["period_id"],
                period_state_transition_id=transition_id,
                approval_request_id=insert_approval_request(
                    uow.session,
                    tenant_id=uow.principal.tenant_id,
                    entity_id=world.entity_id,
                ),
                file_id=UUID(int=0),
            )
            reason = "ERROR_CORRECTION" if kind == "REOPEN" else None
            lock = period_lock_values(
                uow.principal.tenant_id,
                parts=parts,
                kind=kind,
                reason_code=reason,
                created_at=uow.now,
            )
            uow.session.execute(insert(period_lock).values(**lock))
            uow.session.execute(
                insert(period_state_transition).values(
                    **period_state_transition_values(
                        uow.principal.tenant_id,
                        period_state_id=row["id"],
                        entity_id=world.entity_id,
                        period_id=row["period_id"],
                        from_state=previous,
                        to_state=state,
                        id=transition_id,
                        reason_code=reason,
                        approval_request_id=parts.approval_request_id,
                        period_lock_id=lock["id"],
                    )
                )
            )
            uow.session.execute(
                update(period_state)
                .where(period_state.c.id == row["id"])
                .values(
                    state=state,
                    current_lock_id=lock["id"],
                    updated_by_kind="SYSTEM",
                )
            )
            uow.commit()


@pytest.mark.parametrize(
    ("soft_close", "basis_change"),
    [
        (False, None),
        (False, "unrelated-period"),
        (True, None),
        (True, "period"),
        (True, "judgement"),
        (True, "ssp"),
        (True, "reopened"),
        (True, "reopened-closing"),
        (True, "elapsed"),
        (True, "day"),
        (True, "busy-submission"),
        (True, "busy-approval"),
        (True, "second-book"),
        (True, "deferred"),
        (True, "compute-fails"),
        (True, "late-input-change"),
        (True, "ssp-between-checks"),
        (True, "ssp-after-read"),
        (True, "api-client"),
        (True, "book-added"),
        (True, "later-assessment"),
        (True, "decider-revoked"),
        (True, "evidence-snapshot"),
    ],
    ids=[
        "open",
        "unrelated-close",
        "soft-close",
        "period-changed",
        "judgement-superseded",
        "ssp-changed",
        "reopened",
        "reopened-closing",
        "same-day-delay",
        "next-day",
        "busy-submission",
        "busy-approval",
        "two-books",
        "deferred-computation",
        "calculation-failure",
        "late-input-change",
        "ssp-between-checks",
        "ssp-after-read",
        "api-client",
        "book-added",
        "later-assessment",
        "decider-revoked",
        "evidence-snapshot",
    ],
)
def test_step1_assessment_date_requires_independent_review_in_soft_close(
    world: SeatWorld,
    soft_close: bool,
    basis_change: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B1-13: reviewing a conclusion must not authorize an unreviewed posting date.

    Prepare and review the judgement while September is open. Then start close through
    the public command before requesting the dated assessment. The pending request must
    leave the stream, accounting balances, book status and judgement hold unchanged.
    The open-period control retains immediate application of the reviewed assessment.
    """
    assign(world.priya.member, "revenue_reviewer")
    if basis_change == "second-book":
        _keep_ifrs15(world)
    contract_id = _created(world)
    if basis_change == "second-book":
        first = _reviewed(world, contract_id, "COLLECTIBILITY")
        second = _reviewed(world, contract_id, "COLLECTIBILITY", book="IFRS15")
        assessed = _record_events(
            world,
            contract_id,
            _assessment(first, probable=True),
            _assessment(second, probable=True, book="IFRS15"),
        )
        assert assessed.status_code == 201, assessed.text
        submitted = _submit(world, contract_id)
        assert submitted.status_code == 200, submitted.text
        activated = approve(world.app, submitted.headers[APPROVAL_HEADER], world.priya)
        assert activated.status_code == 200, activated.text
    else:
        _activated(world, contract_id)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    if soft_close or basis_change == "unrelated-period":
        closing_key = "FY2026-P01" if basis_change == "unrelated-period" else "FY2026-P09"
        september = next(
            row
            for row in periods(world.app, world.place.author, entity="AVM-US", book="ASC606")
            if row["period"]["period_key"] == closing_key
        )
        started = post(
            world.app,
            f"/api/v1/periods/{september['id']}/start-close",
            world.place.author,
            {"comment": "Review assessment date during September close"},
            if_match=f'"r{september["row_version"]}"',
        )
        assert started.status_code == 200, started.text
        assert started.json()["state"] == "closing"
        if basis_change in {"reopened", "reopened-closing"}:
            _reopened_assessment_period(world, september["id"])
            current = next(
                row
                for row in periods(world.app, world.place.author, entity="AVM-US", book="ASC606")
                if row["id"] == september["id"]
            )
            assert current["state"] == "reopened"
            if basis_change == "reopened-closing":
                reclosing = post(
                    world.app,
                    f"/api/v1/periods/{september['id']}/start-close",
                    world.place.author,
                    {},
                    if_match=f'"r{current["row_version"]}"',
                )
                assert reclosing.status_code == 200, reclosing.text
                assert reclosing.json()["state"] == "closing"
    before = (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    )
    if basis_change == "busy-submission":
        with world.place.uow() as blocker:
            blocker.session.execute(
                select(period_state.c.id)
                .where(period_state.c.id == UUID(september["id"]))
                .with_for_update()
            ).one()
            refused = _record_events(
                world,
                contract_id,
                {**FLAG, "effective_date": "2026-09-08"},
                _assessment(record, probable=False, on="2026-09-08"),
            )
            assert refused.status_code == 409, refused.text
            assert slug(refused) == "lock-conflict"
        assert _header(world, contract_id) == before[0]
        assert (
            world.place.scalar(
                select(func.count())
                .select_from(event_submission)
                .where(event_submission.c.contract_id == contract_id)
            )
            == 0
        )
    batch = [
        {**FLAG, "effective_date": "2026-09-08"},
        _assessment(record, probable=False, on="2026-09-08"),
    ]
    evidence_id = None
    if basis_change == "evidence-snapshot":
        from support import upload_fixtures as upload
        from support.http import call
        from support.principals import cookie_headers

        stored = call(
            world.app,
            "POST",
            "/api/v1/files",
            data={"purpose": "ATTACHMENT"},
            files={"file": ("assessment-date.pdf", upload.PDF, "application/pdf")},
            headers=cookie_headers(world.place.author.token, world.place.author.csrf_token),
        )
        assert stored.status_code == 201, stored.text
        evidence_id = stored.json()["id"]
        assessed = post(
            world.app,
            EVENTS.format(contract_id=contract_id),
            world.place.author,
            {"events": batch, "evidence_file_ids": [evidence_id]},
            if_match=f'"s{before[0][1]}"',
        )
    elif basis_change == "api-client":
        from support.api_clients import access_approver, issued_client
        from support.http import call

        ada = access_approver(world.app, world.place.clock, world.marcus.member, "ada")
        client = issued_client(
            world.app,
            world.marcus,
            {"name": "svc-step1", "scopes": ["event.record", "contract.read"]},
            approver=ada,
        )
        token = call(
            world.app,
            "POST",
            "/api/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            auth=(client["client_id"], client["client_secret"]),
        )
        assert token.status_code == 200, token.text
        assessed = call(
            world.app,
            "POST",
            EVENTS.format(contract_id=contract_id),
            json={"events": batch},
            headers={
                "Authorization": f"Bearer {token.json()['access_token']}",
                "Idempotency-Key": f"step1-{new_id()}",
                "If-Match": f'"s{before[0][1]}"',
            },
        )
    else:
        assessed = _record_events(world, contract_id, *batch)
    if not soft_close:
        assert assessed.status_code == 201, assessed.text
        assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
        assert _header(world, contract_id)[1] == before[0][1] + 3
        return
    after = (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    )
    assert after == before, "A pending assessment must not append, post, or release its hold"
    assert assessed.status_code == 201, assessed.text
    request_id = assessed.json()["approval_request_id"]
    assert assessed.json()["event_submission_id"]
    preview = _preview_document(world, request_id)
    assert preview["after"]["primary_book"] == "ASC606"
    expected_books = {"ASC606", "IFRS15"} if basis_change == "second-book" else {"ASC606"}
    assert {row["book"] for row in preview["after"]["revenue_by_book"]} == expected_books
    assert preview["after"]["posting_lines"], "The hold release must show its posting effects"
    for line in preview["after"]["posting_lines"]:
        assert line["book"] in expected_books
        assert line["entity"] == "AVM-US"
        assert line["transaction_amount"]["currency"] == "USD"
        assert line["functional_amount"]["currency"] == "USD"
        assert line["side"] in {"Debit", "Credit"}
    if basis_change == "elapsed":
        world.place.clock.advance(timedelta(minutes=1))
    final_decider = world.priya
    if basis_change == "decider-revoked":
        shown = get(world.app, f"/api/v1/approvals/{request_id}", world.priya)
        assert shown.status_code == 200, shown.text
        reviewed = shown.json()
        assignment_id = world.place.scalar(
            select(role_assignment.c.id)
            .join(role, role.c.id == role_assignment.c.role_id)
            .where(
                role_assignment.c.membership_id == world.priya.member.membership_id,
                role_assignment.c.revoked_at.is_(None),
                role.c.code == "revenue_reviewer",
            )
        )
        revoked = post(
            world.app,
            f"/api/v1/role-assignments/{assignment_id}/revoke",
            world.marcus,
            {"reason": "Reviewer no longer has approval responsibility."},
        )
        assert revoked.status_code == 200, revoked.text
        refused = post(
            world.app,
            f"/api/v1/approvals/{request_id}/approve",
            world.priya,
            {
                "subject_content_sha256": reviewed["subject"]["content_sha256"],
                "impact_preview_sha256": reviewed["impact_preview"]["sha256"],
                "comment": "Decision from a page loaded before role revocation.",
            },
        )
        assert refused.status_code in (403, 404), refused.text
        assert (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
        ) == before
        assign(world.marcus.member, "revenue_reviewer")
        pending = get(world.app, f"/api/v1/approvals/{request_id}", world.marcus)
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == "PENDING"
        final_decider = world.marcus
    if basis_change in {"period", "judgement", "ssp", "day", "book-added", "later-assessment"}:
        decider = world.priya
        if basis_change == "period":
            cancelled = post(
                world.app,
                f"/api/v1/periods/{september['id']}/cancel-close",
                world.place.author,
                {"reason_code": "CLOSE_RESTARTED", "comment": "Reconsider September close"},
                if_match=f'"r{started.json()["row_version"]}"',
            )
            assert cancelled.status_code == 200, cancelled.text
        elif basis_change == "day":
            world.place.clock.advance(timedelta(days=1))
            decider = signed_workspace(
                world.app,
                world.priya.member,
                sign_in(world.app, world.priya.member.email),
                world.priya.secret,
            )
        elif basis_change == "ssp":
            approved_ssp_version(
                world.app,
                world.place.author,
                [world.priya],
                world.book_id,
                label="Updated study",
                effective_from="2026-09-01",
                copy_from_version_id=world.version_id,
                entries=[
                    range_entry(
                        "AVM-SEAT-MO", "2300.00", "2500.00", "2700.00", value_basis="AMOUNT"
                    )
                ],
            )
        elif basis_change == "book-added":
            _keep_ifrs15(world)
        elif basis_change == "later-assessment":
            later = _record_events(
                world,
                contract_id,
                {**FLAG, "effective_date": "2026-09-09"},
                _assessment(record, probable=False, on="2026-09-09"),
            )
            assert later.status_code == 201, later.text
            applied = approve(world.app, later.json()["approval_request_id"], world.priya)
            assert applied.status_code == 200, applied.text
            assert _header(world, contract_id)[1] == before[0][1] + 3
        else:
            _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
        changed = (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
        )
        stale = approve(world.app, request_id, decider)
        assert stale.status_code == 409, stale.text
        assert slug(stale) == "stale-approval", stale.text
        assert (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
        ) == changed
        assert (
            world.place.scalar(
                select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
            )
            == "VOIDED"
        )
        assert (
            world.place.scalar(
                select(event_submission.c.applied_event_ids).where(
                    event_submission.c.id == UUID(assessed.json()["event_submission_id"])
                )
            )
            == []
        )
        return
    if basis_change == "busy-approval":
        with world.place.uow() as blocker:
            blocker.session.execute(
                select(period_state.c.id)
                .where(period_state.c.id == UUID(september["id"]))
                .with_for_update()
            ).one()
            refused = approve(world.app, request_id, world.priya)
            assert refused.status_code == 409, refused.text
            assert slug(refused) == "lock-conflict"
        assert _header(world, contract_id) == before[0]
        pending = get(world.app, f"/api/v1/approvals/{request_id}", world.priya)
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == "PENDING"
    if basis_change != "api-client":
        assign(world.place.author.member, "revenue_reviewer")
        preparer = enrolled(world.app, world.place.clock, world.place.author.member)
        own = approve(world.app, request_id, preparer)
        assert own.status_code == 403, own.text
        assert slug(own) == "self-approval", own.text
    assert _header(world, contract_id) == before[0]
    if basis_change == "deferred":
        from erev_api.domain.contracts import holds as holds_domain

        monkeypatch.setattr(holds_domain, "OBLIGATION_BUDGET", 0)
    computations_before = world.place.scalar(select(func.count()).select_from(contract_computation))
    publishers: list[threading.Thread] = []
    if basis_change in {"ssp-between-checks", "ssp-after-read"}:
        from erev_api.domain.contracts import computation as computation_domain
        from erev_api.domain.contracts import step1_approval

        published: dict[str, Any] = {}

        def publish() -> None:
            try:
                published["version"] = approved_ssp_version(
                    world.app,
                    preparer,
                    [world.priya],
                    world.book_id,
                    label="Concurrent study",
                    effective_from="2026-09-01",
                    copy_from_version_id=world.version_id,
                    entries=[
                        range_entry(
                            "AVM-SEAT-MO", "2300.00", "2500.00", "2700.00", value_basis="AMOUNT"
                        )
                    ],
                )
            except Exception as error:  # noqa: BLE001 - surfaced in the deciding test thread
                published["error"] = error

        def publish_before_continuing() -> None:
            publisher = threading.Thread(target=publish, name="step1-concurrent-ssp")
            publishers.append(publisher)
            publisher.start()
            publisher.join(timeout=20)
            assert not publisher.is_alive(), "SSP publication did not finish during the decision"
            assert "error" not in published, published
            assert published["version"]

        if basis_change == "ssp-between-checks":
            original_check = step1_approval.assert_calculation

            def checked_then_published(*args: Any, **kwargs: Any) -> None:
                original_check(*args, **kwargs)
                publish_before_continuing()

            monkeypatch.setattr(step1_approval, "assert_calculation", checked_then_published)
        else:
            run = computation_domain.default_engine()

            def publish_after_read(bundle: Any) -> Any:
                publish_before_continuing()
                return run(bundle)

            monkeypatch.setattr(computation_domain, "default_engine", lambda: publish_after_read)
    if basis_change == "compute-fails":
        from erev_api.domain.contracts import computation as computation_domain

        def failed_calculation(bundle: Any) -> Any:
            raise RuntimeError("Injected engine failure after assessment validation")

        monkeypatch.setattr(computation_domain, "default_engine", lambda: failed_calculation)
    elif basis_change == "late-input-change":
        from dataclasses import replace

        from erev_api.domain.contracts import bundles as bundles_domain

        original_build = bundles_domain.build

        def changed_inputs(*args: Any, **kwargs: Any) -> Any:
            bundle = original_build(*args, **kwargs)
            if bundle.trigger == "COMMAND":
                # Simulate a publication entering the actual computation's fresh read,
                # after the earlier pending-event bundle was checked. This is a boundary
                # test, not evidence of a real two-connection publication interleaving.
                bundle = replace(bundle, engine_version=bundle.engine_version + "-changed")
            return bundle

        monkeypatch.setattr(bundles_domain, "build", changed_inputs)
    try:
        decided = approve(world.app, request_id, final_decider)
    finally:
        for publisher in publishers:
            publisher.join(timeout=30)
            assert not publisher.is_alive(), "Publication did not exit after decision rollback"
    if basis_change in {"compute-fails", "late-input-change", "ssp-between-checks"}:
        assert decided.status_code == 409, decided.text
        expected_problem = (
            "invalid-transition" if basis_change == "compute-fails" else "stale-approval"
        )
        assert slug(decided) == expected_problem
        assert (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
        ) == before
        assert (
            world.place.scalar(select(func.count()).select_from(contract_computation))
            == computations_before
        )
        assert (
            world.place.scalar(
                select(event_submission.c.applied_event_ids).where(
                    event_submission.c.id == UUID(assessed.json()["event_submission_id"])
                )
            )
            == []
        )
        pending = get(world.app, f"/api/v1/approvals/{request_id}", world.priya)
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == (
            "PENDING" if basis_change == "compute-fails" else "VOIDED"
        )
        if basis_change in {"late-input-change", "ssp-between-checks"}:
            return
        monkeypatch.undo()
        decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    assert _header(world, contract_id)[1] == before[0][1] + 3
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    expected_posted = dict(before[2])
    for line in preview["after"]["posting_lines"]:
        key = (line["book"], line["account_role"], "D" if line["side"] == "Debit" else "C")
        expected_posted[key] = expected_posted.get(key, Decimal(0)) + Decimal(
            line["transaction_amount"]["amount"]
        )
    assert _posted(world, contract_id) == expected_posted
    assert all(released is not None for _, _, released in _holds(world, contract_id))
    approved_events = world.place.rows(
        select(
            contract_event.c.id,
            contract_event.c.approval_request_id,
            contract_event.c.origin,
            contract_event.c.is_manual,
        )
        .where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.stream_version > before[0][1],
        )
        .order_by(contract_event.c.stream_version)
    )
    if basis_change == "api-client":
        assert all(not row["is_manual"] for row in approved_events)
    assert len(approved_events) == 3
    assert all(
        row["approval_request_id"] == UUID(request_id) and row["origin"] == "SYSTEM"
        for row in approved_events
    )
    assert world.place.scalar(
        select(event_submission.c.applied_event_ids).where(
            event_submission.c.id == UUID(assessed.json()["event_submission_id"])
        )
    ) == [row["id"] for row in approved_events]
    if evidence_id is not None:
        _step1_evidence_snapshot(
            world,
            UUID(request_id),
            [row["id"] for row in approved_events],
            UUID(evidence_id),
            monkeypatch,
        )


def _step1_evidence_snapshot(
    world: SeatWorld,
    request_id: UUID,
    event_ids: list[UUID],
    evidence_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real snapshot carries the Step 1 request, derived-event evidence and file bytes."""
    from erev_api.db.tables import file_attachment, tenant_snapshot
    from erev_api.domain.platform import sandboxes, snapshot_job
    from erev_api.enums import JobKind
    from erev_api.files.store import open_file
    from erev_api.jobs import registry
    from support import upload_fixtures as upload
    from support.factories import stamp_test_release
    from support.rows import tenant_snapshot_values
    from support.snapshots import confirm_retention, cutoff_after, run_dispatched_snapshot

    stamp_test_release()
    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.TENANT_SNAPSHOT,
        registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        ),
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        confirm_retention(
            session, world.place.tenant_id, at=world.place.clock.now() - timedelta(days=1)
        )
    known_at = cutoff_after(world.place.tenant_id, world.place.clock)
    row = tenant_snapshot_values(world.place.tenant_id, known_at=known_at, purpose="SANDBOX_COPY")
    with tenant_session(context) as session:
        session.execute(insert(tenant_snapshot).values(**row))
    sandbox_id = new_id()
    runtime = JobRuntime(
        clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
    )
    result = run_dispatched_snapshot(
        world.place.tenant_id,
        {
            "tenant_snapshot_id": str(row["id"]),
            "known_at": known_at.isoformat(),
            "purpose": "SANDBOX_COPY",
            **sandboxes.load_params_of(
                sandbox_tenant_id=sandbox_id,
                name="Step one assessment evidence",
                requested_by=world.marcus.member.user_id,
                restore=False,
            ),
        },
        runtime=runtime,
        now=known_at,
    )
    assert result["state"] == "SUCCEEDED", str(result["problem"])
    assert result["result"]["counts"]["derived_mismatches"] == 0
    attachments = []
    previews = []
    for tenant_id in (world.place.tenant_id, sandbox_id):
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"), read_only=True
        ) as session:
            request = (
                session.execute(select(approval_request).where(approval_request.c.id == request_id))
                .mappings()
                .one()
            )
            assert (request["subject_type"], request["status"]) == ("STEP1_EVENT", "APPROVED")
            previews.append(
                read_preview(
                    session,
                    request["impact_preview_file_id"],
                    files=world.place.files,
                    keyring=world.place.keyring,
                )
            )
            attachments.append(
                set(
                    session.execute(
                        select(file_attachment.c.subject_type, file_attachment.c.subject_id).where(
                            file_attachment.c.file_object_id == evidence_id,
                            file_attachment.c.voided_at.is_(None),
                        )
                    ).all()
                )
            )
            _, stream = open_file(
                session, evidence_id, files=world.place.files, keyring=world.place.keyring
            )
            assert stream.read() == upload.PDF
    expected = {("approval_request", request_id)} | {
        ("contract_event", event_id) for event_id in event_ids
    }
    assert attachments == [expected, expected]
    assert previews[0] == previews[1]


@pytest.mark.parametrize(
    ("performer_closing", "period_changed", "fx_mode"),
    [
        (False, False, "none"),
        (True, False, "none"),
        (True, True, "none"),
        (True, False, "unchanged"),
        (True, False, "changed"),
        (True, False, "concurrent"),
    ],
    ids=[
        "performer-open",
        "performer-closing",
        "performer-period-changed",
        "performer-gbp",
        "performer-fx-changed",
        "performer-fx-concurrent",
    ],
)
def test_step1_date_review_follows_performing_entity_postings(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    performer_closing: bool,
    period_changed: bool,
    fx_mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from erev_api.db.tables import legal_entity
    from support.factories import open_periods
    from support.reference import entity

    world = seat_world(
        app,
        keyring,
        clock,
        LocalFileStore(app_settings.file_root),
        chart=(
            *STEP1_CHART,
            ("1300", "Intercompany due from", "ASSET", "D", "INTERCOMPANY_DUE_FROM"),
            ("2300", "Intercompany due to", "LIABILITY", "C", "INTERCOMPANY_DUE_TO"),
            ("7200", "Foreign exchange gain or loss", "EXPENSE", "D", "FX_GAIN_LOSS"),
            ("7299", "Rounding", "EXPENSE", "D", "ROUNDING"),
        ),
    )
    assign(world.priya.member, "revenue_reviewer")
    calendar_id = world.place.scalar(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
    )
    fx_sets: dict[str, str] = {}

    def publish_rates(kind: str, rate: str) -> None:
        pair = {"base_currency": "USD", "quote_currency": "GBP", "rate": rate}
        rates = (
            [{**pair, "effective_date": f"2026-09-{day:02d}"} for day in range(1, 31)]
            if kind == "spot"
            else [{**pair, "period_key": "FY2026-P09"}]
        )
        draft = post(
            app,
            f"/api/v1/fx-rate-sets/{fx_sets[kind]}/versions",
            world.place.author,
            {"coverage_from": "2026-09-01", "coverage_to": "2026-09-30", "rates": rates},
        )
        assert draft.status_code == 201, draft.text
        submitted = post(
            app,
            f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
            world.place.author,
            {},
            if_match=f'"r{draft.json()["row_version"]}"',
        )
        assert submitted.status_code == 200, submitted.text
        published = approve(app, submitted.json()["pending_approval_request_id"], world.marcus)
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "APPROVED"

    if fx_mode != "none":
        enabled = put(
            app, "/api/v1/tenant-currencies", world.marcus, {"currency_codes": ["USD", "GBP"]}
        )
        assert enabled.status_code == 200, enabled.text
        for kind in ("spot", "average", "closing"):
            made = post(
                app,
                "/api/v1/fx-rate-sets",
                world.place.author,
                {"code": f"STEP1-{kind.upper()}", "name": f"Step 1 {kind}", "rate_type": kind},
            )
            assert made.status_code == 201, made.text
            fx_sets[kind] = made.json()["id"]
            publish_rates(kind, "0.800000")
    entity(
        app,
        world.place.author,
        code="AVM-OPS",
        calendar_id=str(calendar_id),
        functional_currency="USD" if fx_mode == "none" else "GBP",
    )
    open_periods(
        app,
        world.place.author,
        entity_code="AVM-OPS",
        keys=[f"FY2026-P{month:02d}" for month in range(1, 10)],
    )
    body = k09_body(world.customers["C-09"])
    body["lines"][0]["performing_entity_code"] = "AVM-OPS"
    created = post(app, CONTRACTS, world.place.author, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(created.json()["id"])
    _activated(world, contract_id)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    performing_period = next(
        row
        for row in periods(app, world.place.author, entity="AVM-OPS", book="ASC606")
        if row["period"]["period_key"] == "FY2026-P09"
    )
    if performer_closing:
        started = post(
            app,
            f"/api/v1/periods/{performing_period['id']}/start-close",
            world.place.author,
            {},
            if_match=f'"r{performing_period["row_version"]}"',
        )
        assert started.status_code == 200, started.text
    owner_period = next(
        row
        for row in periods(app, world.place.author, entity="AVM-US", book="ASC606")
        if row["period"]["period_key"] == "FY2026-P09"
    )
    assert owner_period["state"] == "open"

    def ledger(*, functional: bool = False) -> dict[tuple[str, str, str, str], Decimal]:
        amount = subledger_line.c.amount_functional if functional else subledger_line.c.amount_txn
        rows = world.place.rows(
            select(
                legal_entity.c.code,
                subledger_line.c.book_code,
                subledger_line.c.account_role,
                subledger_line.c.dr_cr,
                func.sum(amount).label("total"),
            )
            .join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
            .where(subledger_line.c.contract_id == contract_id)
            .group_by(
                legal_entity.c.code,
                subledger_line.c.book_code,
                subledger_line.c.account_role,
                subledger_line.c.dr_cr,
            )
        )
        return {
            (
                str(row["code"]),
                str(row["book_code"]),
                str(row["account_role"]),
                str(row["dr_cr"]),
            ): abs(Decimal(row["total"]))
            for row in rows
        }

    before = (_header(world, contract_id), ledger(), _holds(world, contract_id))
    functional_before = ledger(functional=True)
    assessed = _record_events(
        world,
        contract_id,
        {**FLAG, "effective_date": "2026-09-08"},
        _assessment(record, probable=False, on="2026-09-08"),
    )
    assert assessed.status_code == 201, assessed.text
    if not performer_closing:
        assert "approval_request_id" not in assessed.json()
        assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
        return
    request_id = assessed.json()["approval_request_id"]
    assert (_header(world, contract_id), ledger(), _holds(world, contract_id)) == before
    preview = _preview_document(world, request_id)
    lines = preview["after"]["posting_lines"]
    assert "AVM-OPS" in {line["entity"] for line in lines}
    for line in lines:
        if line["entity"] == "AVM-OPS":
            assert line["transaction_amount"]["currency"] == "USD"
            assert line["functional_amount"]["currency"] == ("USD" if fx_mode == "none" else "GBP")
    with world.place.uow() as blocker:
        blocker.session.execute(
            select(period_state.c.id)
            .where(period_state.c.id == UUID(performing_period["id"]))
            .with_for_update()
        ).one()
        refused = approve(app, request_id, world.priya)
        assert refused.status_code == 409, refused.text
        assert slug(refused) == "lock-conflict"
    assert (_header(world, contract_id), ledger(), _holds(world, contract_id)) == before
    if period_changed:
        cancelled = post(
            app,
            f"/api/v1/periods/{performing_period['id']}/cancel-close",
            world.place.author,
            {"reason_code": "CLOSE_RESTARTED", "comment": "Reconsider performing entity close"},
            if_match=f'"r{started.json()["row_version"]}"',
        )
        assert cancelled.status_code == 200, cancelled.text
    if fx_mode == "changed":
        publish_rates("average", "0.900000")
    publisher: threading.Thread | None = None
    concurrent: dict[str, Any] = {}
    if fx_mode == "concurrent":
        from erev_api.domain.contracts import step1_approval

        original_check = step1_approval.assert_calculation

        def publish_average() -> None:
            try:
                publish_rates("average", "0.900000")
                concurrent["published"] = True
            except Exception as error:  # noqa: BLE001 - surfaced in the test thread
                concurrent["error"] = error

        publisher = threading.Thread(target=publish_average, name="step1-concurrent-fx")

        def checked_then_observe(uow: Any, *args: Any) -> None:
            original_check(uow, *args)
            assert publisher is not None
            with observing_checkouts() as backends:
                holder = backend_pid(uow.session)
                publisher.start()
                # The group's FOR UPDATE is at the end of a long reach CTE; the
                # pg_stat_activity query is truncated before its table name. Still
                # require this publisher to be blocked by this decision's backend.
                _, concurrent["waiting_statement"] = await_lock_wait(
                    uow.session,
                    holder_pid=holder,
                    backends=backends,
                    timeout=10,
                    expect="with reach as",
                    while_running=publisher.is_alive,
                )
            assert publisher.is_alive() and "published" not in concurrent

        monkeypatch.setattr(step1_approval, "assert_calculation", checked_then_observe)
    try:
        decided = approve(app, request_id, world.priya)
    finally:
        if publisher is not None and publisher.ident is not None:
            publisher.join(timeout=30)
            assert not publisher.is_alive(), concurrent
    if fx_mode == "concurrent":
        assert "error" not in concurrent, concurrent
        assert concurrent["published"]
        assert concurrent["waiting_statement"].startswith("WITH reach AS")
    if period_changed or fx_mode == "changed":
        assert decided.status_code == 409, decided.text
        assert slug(decided) == "stale-approval"
        assert (_header(world, contract_id), ledger(), _holds(world, contract_id)) == before
        return
    assert decided.status_code == 200, decided.text
    expected = dict(before[1])
    expected_functional = dict(functional_before)
    for line in lines:
        key = (
            line["entity"],
            line["book"],
            line["account_role"],
            "D" if line["side"] == "Debit" else "C",
        )
        expected[key] = expected.get(key, Decimal(0)) + Decimal(
            line["transaction_amount"]["amount"]
        )
        expected_functional[key] = expected_functional.get(key, Decimal(0)) + Decimal(
            line["functional_amount"]["amount"]
        )
    assert ledger() == expected
    assert ledger(functional=True) == expected_functional
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    assert _header(world, contract_id)[1] == before[0][1] + 3


@pytest.mark.parametrize(
    ("over_budget", "physical_large"),
    [(False, False), (True, False), (True, True)],
    ids=["draft-gate", "large-group-boundary", "201-obligations"],
)
def test_draft_step1_date_approval_applies_only_the_reviewed_gate(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch, over_budget: bool, physical_large: bool
) -> None:
    """A restricted-window draft assessment reviews and atomically applies its derived gate."""
    from erev_api.domain.contracts import events as events_domain
    from erev_api.domain.contracts import holds as holds_domain

    assign(world.priya.member, "revenue_reviewer")
    if physical_large:
        from erev_api.domain.contracts.compute_job import obligation_count

        body = k09_body(world.customers["C-09"])
        template = body["lines"][0]
        body["lines"] = [{**template, "obligation_key": f"O{index}"} for index in range(1, 202)]
        created = post(world.app, CONTRACTS, world.place.author, body)
        assert created.status_code == 201, created.text
        contract_id = UUID(created.json()["id"])
        with world.place.uow() as uow:
            assert obligation_count(uow.session, _group_id(world, contract_id)) == 201
    else:
        contract_id = _created(world)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    september = next(
        row
        for row in periods(world.app, world.place.author, entity="AVM-US", book="ASC606")
        if row["period"]["period_key"] == "FY2026-P09"
    )
    started = post(
        world.app,
        f"/api/v1/periods/{september['id']}/start-close",
        world.place.author,
        {},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    if over_budget and not physical_large:
        # Exercise the existing withholding boundary with one real obligation. This does
        # not stand in for a volume/performance test of a physically large contract.
        monkeypatch.setattr(events_domain, "OBLIGATION_BUDGET", 0)
        monkeypatch.setattr(holds_domain, "OBLIGATION_BUDGET", 0)
    before = (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    )
    jobs_before = world.place.scalar(
        select(func.count()).select_from(job).where(job.c.kind == "CONTRACT_COMPUTE")
    )
    sent = _record_events(world, contract_id, _assessment(record, probable=False, on="2026-09-08"))
    assert sent.status_code == 201, sent.text
    request_id = sent.json()["approval_request_id"]
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    ) == before
    preview = _preview_document(world, request_id)
    expected_status = "DRAFT" if over_budget else "NOT_A_CONTRACT"
    assert preview["before"]["status"] == "DRAFT"
    assert preview["after"]["status"] == expected_status
    decided = approve(world.app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    assert _header(world, contract_id) == (
        expected_status,
        before[0][1] + (1 if over_budget else 2),
    )
    effects = world.place.rows(
        select(
            contract_event.c.id, contract_event.c.event_type, contract_event.c.approval_request_id
        )
        .where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.stream_version > before[0][1],
        )
        .order_by(contract_event.c.stream_version)
    )
    expected_types = ["COLLECTIBILITY_ASSESSED"]
    if not over_budget:
        expected_types.insert(1, "CONTRACT_ACTIVATED")
    assert [str(row["event_type"]) for row in effects] == expected_types
    assert all(row["approval_request_id"] == UUID(request_id) for row in effects)
    assert world.place.scalar(
        select(event_submission.c.applied_event_ids).where(
            event_submission.c.id == UUID(sent.json()["event_submission_id"])
        )
    ) == [row["id"] for row in effects]
    assert before[3] == _holds(world, contract_id) == []
    assert _books(world, contract_id)["ASC606"][0] == expected_status
    assert (
        world.place.scalar(
            select(func.count()).select_from(job).where(job.c.kind == "CONTRACT_COMPUTE")
        )
        == jobs_before
    )


def test_step1_date_review_terminal_decisions_do_not_apply_twice(world: SeatWorld) -> None:
    """Rejected/withdrawn dates do nothing; resubmission can apply exactly once."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _activated(world, contract_id)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    september = next(
        row
        for row in periods(world.app, world.place.author, entity="AVM-US", book="ASC606")
        if row["period"]["period_key"] == "FY2026-P09"
    )
    started = post(
        world.app,
        f"/api/v1/periods/{september['id']}/start-close",
        world.place.author,
        {},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text

    def state() -> tuple[Any, ...]:
        return (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
            world.place.scalar(select(func.count()).select_from(contract_computation)),
        )

    before = state()
    mixed = _record_events(
        world,
        contract_id,
        {**FLAG, "effective_date": "2026-09-08"},
        _assessment(record, probable=False, on="2026-09-08"),
        RECEIPT,
    )
    assert mixed.status_code == 422, mixed.text
    assert "Record the Step 1 assessment in a request of its own." in mixed.text
    assert state() == before
    assert (
        world.place.scalar(
            select(func.count())
            .select_from(event_submission)
            .where(event_submission.c.contract_id == contract_id)
        )
        == 0
    )
    for action, request_status, submission_status in (
        ("reject", "REJECTED", "REJECTED"),
        ("withdraw", "WITHDRAWN", "VOIDED"),
        ("approve", "APPROVED", "APPLIED"),
    ):
        assessed = _record_events(
            world,
            contract_id,
            {**FLAG, "effective_date": "2026-09-08"},
            _assessment(record, probable=False, on="2026-09-08"),
        )
        assert assessed.status_code == 201, assessed.text
        assert state() == before
        request_id = assessed.json()["approval_request_id"]
        submission_id = UUID(assessed.json()["event_submission_id"])
        if action == "reject":
            decided = reject(world.app, request_id, world.priya, "Revise the assessment date.")
        elif action == "withdraw":
            decided = post(
                world.app, f"/api/v1/approvals/{request_id}/withdraw", world.place.author, {}
            )
        else:
            decided = approve(world.app, request_id, world.priya)
        assert decided.status_code == 200, decided.text
        detail = get(world.app, f"/api/v1/approvals/{request_id}", world.priya)
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == request_status
        submission = world.place.rows(
            select(event_submission.c.status, event_submission.c.applied_event_ids).where(
                event_submission.c.id == submission_id
            )
        )[0]
        assert submission["status"] == submission_status
        if action != "approve":
            assert state() == before
            assert submission["applied_event_ids"] == []
        else:
            assert _header(world, contract_id)[1] == before[0][1] + 3
            assert len(submission["applied_event_ids"]) == 3
            assert all(released is not None for _, _, released in _holds(world, contract_id))
        terminal = state()
        repeated = approve(world.app, request_id, world.priya)
        assert (repeated.status_code, slug(repeated)) == (409, "invalid-transition")
        assert state() == terminal


def test_step1_hold_release_1_a_not_probable_assessment_of_an_active_book_follows_a_flag(
    world: SeatWorld,
) -> None:
    """The supervisor's ruling on Q-H2 (PRD IMP-136; 04 table 15.4-I
    ``STEP1_CHANGE_NOT_FLAGGED``). Measured before the fix: on an ACTIVE contract WITHOUT a
    significant-change flag a reviewed NOT_A_CONTRACT record and the not-probable assessment
    citing it were both taken (201) — and the book stayed ACTIVE and went on recognising, because
    Table 2.2-A moves an active book only on a not-probable assessment that FOLLOWS a flag
    (606-10-25-5). The route and its preview refuse the assessment by name and nothing changes;
    with the flag — here in the same request, read first — the assessment takes the book out and
    releases the record's hold. Control: a not-probable assessment of a book that is already out
    is not one of an active book and is taken as before."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _activated(world, contract_id)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    number = _judgement_no(world, record)
    reason = HOLD_STEP1.format(judgement_no=number)
    before = (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    )
    assert before[1]["ASC606"] == HELD and before[3] == [("SYSTEM", reason, None)]

    assessment = _assessment(record, probable=False, on="2026-09-08")
    for path in (EVENTS, f"{EVENTS}/preview"):
        refused = post(
            world.app,
            path.format(contract_id=contract_id),
            world.place.author,
            {"events": [assessment]},
            if_match=f'"s{_head(world, contract_id)}"',
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), (path, refused)
        assert fields(refused) == [("events.0.payload.is_probable", "STEP1_CHANGE_NOT_FLAGGED")]
        assert refused.json()["errors"][0]["message"] == CHANGE_NOT_FLAGGED
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
        _holds(world, contract_id),
    ) == before

    both = _record_events(world, contract_id, {**FLAG, "effective_date": "2026-09-08"}, assessment)
    assert both.status_code == 201, both.text
    assert [event["event_type"] for event in both.json()["events"]] == [
        "SIGNIFICANT_CHANGE_FLAGGED",
        "COLLECTIBILITY_ASSESSED",
        "HOLD_RELEASED",
    ]
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    assert _holds(world, contract_id) == [
        ("SYSTEM", reason, ASSESSMENT_RECORDED.format(judgement_no=number))
    ]
    again = _record_events(world, contract_id, _assessment(record, probable=False, on="2026-09-09"))
    assert again.status_code == 201, again.text
    assert [event["event_type"] for event in again.json()["events"]] == ["COLLECTIBILITY_ASSESSED"]
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    assert _recognition(world) == _unapproved_recognition(world) == []


def test_step1_hold_release_1_a_probable_assessment_does_not_cite_a_not_probable_review(
    world: SeatWorld,
) -> None:
    """The supervisor's ruling on the lane's question 1 (04 §16.3 (b) rev 1.209; ruling R-113
    (f) (3) extended to criterion (e)). 04 §16.3 (b) let a probable assessment cite a
    NOT_A_CONTRACT record, although such a record answers No to (e): the entry said one thing and
    its evidence the other — and with it the preparer alone would have ended the hold of a
    reviewed "not a contract" record and answered a significant-change flag. The route and its
    preview refuse it by name, with the topic to use; nothing moves: the flag stands, the hold
    stays, and its release by hand stays refused. The not-probable assessment the record stands
    for is then taken, takes the book out and releases the hold."""
    contract_id, record, request, reason = _flagged_and_held(world)
    number = _judgement_no(world, record)
    assert approve(world.app, request, world.marcus).status_code == 200
    (hold_id,) = _open_holds(world, contract_id)

    def state() -> tuple[Any, ...]:
        return (
            _header(world, contract_id),
            _books(world, contract_id),
            _posted(world, contract_id),
            _holds(world, contract_id),
        )

    before = state()
    assert before[1]["ASC606"] == HELD and before[3] == [("SYSTEM", reason, None)]
    for path in (EVENTS, f"{EVENTS}/preview"):
        refused = post(
            world.app,
            path.format(contract_id=contract_id),
            world.place.author,
            {"events": [_assessment(record, probable=True, on="2026-09-08")]},
            if_match=f'"s{_head(world, contract_id)}"',
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), (path, refused)
        assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")] * 2
        assert [item["message"] for item in refused.json()["errors"]] == [
            USE_COLLECTIBILITY,
            NOT_PROBABLE_REVIEW,
        ]
    assert state() == before
    by_hand = _release_by_hand(world, contract_id, hold_id)
    assert (by_hand.status_code, slug(by_hand)) == (409, "invalid-transition"), by_hand.text
    assert by_hand.json()["detail"] == RELEASED_BY_ASSESSMENT.format(judgement_no=number)

    # The flag still stands: the assessment the record stands for takes the book out.
    out = _record_events(world, contract_id, _assessment(record, probable=False, on="2026-09-08"))
    assert out.status_code == 201, out.text
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH
    assert _holds(world, contract_id) == [
        ("SYSTEM", reason, ASSESSMENT_RECORDED.format(judgement_no=number))
    ]


def test_step1_hold_release_1_a_superseded_record_gives_up_its_hold(world: SeatWorld) -> None:
    """(c): a reviewed NOT_A_CONTRACT record that no assessment cites is superseded by a later
    record of the same topic, subject and book (PRD SM-10). Its hold is released with it, by
    name; the record that supersedes it carries a hold of its own until ITS assessment is
    recorded, so the contract is held throughout."""
    contract_id, first, request, first_reason = _flagged_and_held(world)
    assert approve(world.app, request, world.marcus).status_code == 200
    first_no = _judgement_no(world, first)

    second, second_request = _record(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    assert second_request is not None
    second_no = _judgement_no(world, second)
    second_reason = HOLD_STEP1.format(judgement_no=second_no)
    assert _holds(world, contract_id) == [
        ("SYSTEM", first_reason, None),
        ("SYSTEM", second_reason, None),
    ]
    assert approve(world.app, second_request, world.marcus).status_code == 200
    assert (_status_of(world, first), _status_of(world, second)) == ("SUPERSEDED", "REVIEWED")
    assert _holds(world, contract_id) == [
        (
            "SYSTEM",
            first_reason,
            RECORD_SUPERSEDED.format(judgement_no=first_no, superseded_by=second_no),
        ),
        ("SYSTEM", second_reason, None),
    ]
    assert _on_hold(world, contract_id) is True
    assert _books(world, contract_id)["ASC606"] == HELD

    assessed = _record_events(
        world, contract_id, _assessment(second, probable=False, on="2026-09-08")
    )
    assert assessed.status_code == 201, assessed.text
    assert _holds(world, contract_id)[1] == (
        "SYSTEM",
        second_reason,
        ASSESSMENT_RECORDED.format(judgement_no=second_no),
    )
    assert _on_hold(world, contract_id) is False
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH


def _release_audits(world: SeatWorld, contract_id: UUID) -> list[tuple[str, str | None]]:
    """(actor, comment) of the ``contract_hold.release`` audit event of each released hold of
    the contract, in the order the holds were applied. The event of a release is written in the
    unit of work that causes it: its actor is the person who acted, while the ``HOLD_RELEASED``
    it belongs to is appended by SYSTEM."""
    rows = world.place.rows(
        select(audit_event.c.actor_id, audit_event.c.comment)
        .select_from(
            contract_hold.join(
                audit_event,
                and_(
                    audit_event.c.tenant_id == contract_hold.c.tenant_id,
                    audit_event.c.object_id == contract_hold.c.id,
                ),
            )
        )
        .where(
            contract_hold.c.contract_id == contract_id,
            audit_event.c.action == "contract_hold.release",
        )
        .order_by(contract_hold.c.applied_at, contract_hold.c.id)
    )
    return [(str(row["actor_id"]), row["comment"]) for row in rows]


def test_step1_hold_release_1_a_voided_flag_leaves_the_hold_to_the_next_review(
    world: SeatWorld,
) -> None:
    """(c'), the first way in (the supervisor's ruling on the lane's question 2; 04 T-CON-20
    "Judgement holds" rev 1.209). The flag a reviewed NOT_A_CONTRACT record answered is voided by
    an approved request. The not-probable assessment that would release the record's hold is
    then refused — no flag stands (IMP-136) — and so is the release by hand: without (c') the
    contract is held for good. The review of a COLLECTIBILITY record of the same subject and
    book, a second person concluding the opposite, releases that hold by name, with the audit
    event a release writes; the overtaken record stays REVIEWED and the book recognises again."""
    contract_id, record, request, reason = _flagged_and_held(world)
    number = _judgement_no(world, record)
    assert approve(world.app, request, world.marcus).status_code == 200
    (hold_id,) = _open_holds(world, contract_id)
    flag_event = next(
        event
        for event in _stream(world, contract_id)
        if str(event["event_type"]) == "SIGNIFICANT_CHANGE_FLAGGED"
    )
    requested = post(
        world.app,
        f"/api/v1/events/{flag_event['id']}/request-void",
        world.place.author,
        {"reason_code": "CREATED_IN_ERROR", "comment": "The downgrade was another customer's."},
    )
    assert requested.status_code == 201, requested.text
    voided = approve(world.app, requested.json()["approval_request_id"], world.priya)
    assert voided.status_code == 200, voided.text
    computed(world.place, _group_id(world, contract_id))

    # No way out by the preparer alone, and none by the assessment the record stands for.
    unflagged = _record_events(
        world, contract_id, _assessment(record, probable=False, on="2026-09-08")
    )
    assert unflagged.status_code == 422, unflagged.text
    assert fields(unflagged) == [("events.0.payload.is_probable", "STEP1_CHANGE_NOT_FLAGGED")]
    by_hand = _release_by_hand(world, contract_id, hold_id)
    assert (by_hand.status_code, slug(by_hand)) == (409, "invalid-transition"), by_hand.text
    assert by_hand.json()["detail"] == RELEASED_BY_ASSESSMENT.format(judgement_no=number)
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]
    assert _books(world, contract_id)["ASC606"] == HELD

    # The next review: collection is probable. Its own hold while it waits, both released by it.
    fresh, fresh_request = _record(world, contract_id, "COLLECTIBILITY")
    assert fresh_request is not None
    fresh_no = _judgement_no(world, fresh)
    own = HOLD_COLLECTIBILITY.format(judgement_no=fresh_no)
    assert _holds(world, contract_id) == [("SYSTEM", reason, None), ("SYSTEM", own, None)]
    assert approve(world.app, fresh_request, world.marcus).status_code == 200
    overtaken = RECORD_OVERTAKEN.format(judgement_no=number, overtaken_by=fresh_no)
    reviewed = RECORD_REVIEWED.format(judgement_no=fresh_no)
    assert _holds(world, contract_id) == [
        ("SYSTEM", reason, overtaken),
        ("SYSTEM", own, reviewed),
    ]
    reviewer = str(world.marcus.member.user_id)
    assert _release_audits(world, contract_id) == [(reviewer, overtaken), (reviewer, reviewed)]
    assert (_status_of(world, record), _status_of(world, fresh)) == ("REVIEWED", "REVIEWED")
    assert _on_hold(world, contract_id) is False
    assert _books(world, contract_id)["ASC606"] == ACTIVE_TO_DATE
    assert _unapproved_recognition(world) == []


def test_step1_hold_release_1_a_collectibility_review_overtakes_a_reviewed_not_a_contract_record(
    world: SeatWorld,
) -> None:
    """(c'), the second way in: the facts change between the review of the NOT_A_CONTRACT record
    and its assessment, and the next review finds collection probable. A COLLECTIBILITY record
    supersedes nothing (PRD SM-10 reads the same topic), so the first record's hold had no end.
    Its review releases the open hold of every REVIEWED NOT_A_CONTRACT record of the same
    subject and book. A NOT_A_CONTRACT record that is still SUBMITTED beside it keeps its hold:
    that one follows its own review — here a stale one, because the two submissions behind it
    moved the head its request pins (04 §16.10), after which a person releases it."""
    contract_id, first, request, first_reason = _flagged_and_held(world)
    first_no = _judgement_no(world, first)
    assert approve(world.app, request, world.marcus).status_code == 200

    waiting, waiting_request = _record(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    assert waiting_request is not None
    waiting_reason = HOLD_STEP1.format(judgement_no=_judgement_no(world, waiting))
    fresh, fresh_request = _record(world, contract_id, "COLLECTIBILITY")
    assert fresh_request is not None
    fresh_no = _judgement_no(world, fresh)
    own = HOLD_COLLECTIBILITY.format(judgement_no=fresh_no)
    assert _holds(world, contract_id) == [
        ("SYSTEM", first_reason, None),
        ("SYSTEM", waiting_reason, None),
        ("SYSTEM", own, None),
    ]

    assert approve(world.app, fresh_request, world.marcus).status_code == 200
    assert _holds(world, contract_id) == [
        (
            "SYSTEM",
            first_reason,
            RECORD_OVERTAKEN.format(judgement_no=first_no, overtaken_by=fresh_no),
        ),
        ("SYSTEM", waiting_reason, None),
        ("SYSTEM", own, RECORD_REVIEWED.format(judgement_no=fresh_no)),
    ]
    assert (_status_of(world, first), _status_of(world, waiting), _status_of(world, fresh)) == (
        "REVIEWED",
        "SUBMITTED",
        "REVIEWED",
    )
    assert _on_hold(world, contract_id) is True
    assert _books(world, contract_id)["ASC606"] == HELD

    # The record that waited: its request is stale; the hold stays under a reason that is still
    # true, and is released by hand now that nothing waits for a review.
    (waiting_hold,) = _open_holds(world, contract_id)
    early = _release_by_hand(world, contract_id, waiting_hold)
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    late = approve(world.app, waiting_request, world.marcus)
    assert (late.status_code, slug(late)) == (409, "stale-approval"), late.text
    assert _status_of(world, waiting) == "REJECTED"
    assert _holds(world, contract_id)[1] == ("SYSTEM", waiting_reason, None)
    by_hand = _release_by_hand(world, contract_id, waiting_hold)
    assert by_hand.status_code == 200, by_hand.text
    assert _on_hold(world, contract_id) is False
    assert _books(world, contract_id)["ASC606"] == ACTIVE_TO_DATE


def test_step1_hold_release_1_a_record_of_another_book_is_not_overtaken(world: SeatWorld) -> None:
    """(c') reads "the same book" as PRD SM-10 reads it for a supersession: an equal book, or
    none on both. A NOT_A_CONTRACT record without a book — of every book (04 T-CON-19) — is not
    overtaken by the review of a COLLECTIBILITY record of one book: the first still stands for
    the others. Its hold ends as (b) says, at the not-probable assessment that cites it."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    _activated(world, contract_id)
    assert _record_events(world, contract_id, FLAG).status_code == 201
    every_book = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT, book=None)
    number = _judgement_no(world, every_book)
    reason = HOLD_STEP1.format(judgement_no=number)
    assert _holds(world, contract_id) == [("SYSTEM", reason, None)]

    one_book = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert _holds(world, contract_id) == [
        ("SYSTEM", reason, None),
        (
            "SYSTEM",
            HOLD_COLLECTIBILITY.format(judgement_no=_judgement_no(world, one_book)),
            RECORD_REVIEWED.format(judgement_no=_judgement_no(world, one_book)),
        ),
    ]
    assert _on_hold(world, contract_id) is True

    out = _record_events(
        world, contract_id, _assessment(every_book, probable=False, on="2026-09-08")
    )
    assert out.status_code == 201, out.text
    assert _holds(world, contract_id)[0] == (
        "SYSTEM",
        reason,
        ASSESSMENT_RECORDED.format(judgement_no=number),
    )
    assert _on_hold(world, contract_id) is False
    assert _books(world, contract_id)["ASC606"] == OUT_AT_THE_EIGHTH


# --- the record an assessment cites (item STEP1-CITE-LATEST-1) ------------------------------------

# 04 §16.3 (b): the two sentences an assessment meets when its record is not the newest review
# of the judgement, or was made before the flag it answers.
CITED_OVERTAKEN = (
    "This judgement record was overtaken by the review of judgement record {judgement_no}. Use "
    "the latest reviewed Step 1 record."
)
REVIEWED_BEFORE_FLAG = "Use a judgement record reviewed after the significant change was flagged."


def _cite_refused(
    world: SeatWorld, contract_id: UUID, message: str, *items: dict[str, Any]
) -> None:
    """The route and its preview refuse ``items`` on the record of the last one, with one
    sentence, and nothing moves."""
    before = (_header(world, contract_id), _books(world, contract_id), _posted(world, contract_id))
    for path in (EVENTS, f"{EVENTS}/preview"):
        answer = post(
            world.app,
            path.format(contract_id=contract_id),
            world.place.author,
            {"events": list(items)},
            if_match=f'"s{_head(world, contract_id)}"',
        )
        assert (answer.status_code, slug(answer)) == (422, "validation-failed"), (path, answer.text)
        assert fields(answer) == [
            (f"events.{len(items) - 1}.payload.judgement_record_id", "REQ-POL-008")
        ]
        assert answer.json()["errors"][0]["message"] == message
    assert (
        _header(world, contract_id),
        _books(world, contract_id),
        _posted(world, contract_id),
    ) == before


def test_step1_cite_latest_1_a_probable_reassessment_rests_on_a_review_made_after_the_flag(
    world: SeatWorld,
) -> None:
    """Item STEP1-CITE-LATEST-1 (the supervisor's ruling of 2026-10-02), case (i). Measured
    before: on an ACTIVE contract a significant-change flag was answered by a PROBABLE
    assessment that cited the collectibility record of the activation, reviewed before the flag
    — 201: the flag was cleared and the book went on recognising, and no reviewer had looked at
    the change. An assessment that answers a flag rests on a record reviewed at or after the
    time the flag was recorded. The route and its preview refuse the old record by name and
    nothing moves; a flag sent in the request of the assessment is refused the same way — no
    record can have been reviewed after a flag that is recorded with the assessment. The record
    reviewed after the flag is taken and answers it."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    old = _activated(world, contract_id)
    _later(world)

    _cite_refused(
        world,
        contract_id,
        REVIEWED_BEFORE_FLAG,
        FLAG,
        _assessment(old, probable=True, on="2026-09-08"),
    )
    assert _event_types(world, contract_id)[-1] == "CONTRACT_ACTIVATED"  # no flag was stored

    assert _record_events(world, contract_id, FLAG).status_code == 201
    assert _books(world, contract_id)["ASC606"] == AT_THE_FLAG
    _cite_refused(
        world, contract_id, REVIEWED_BEFORE_FLAG, _assessment(old, probable=True, on="2026-09-08")
    )

    fresh = _reviewed(world, contract_id, "COLLECTIBILITY")
    taken = _record_events(world, contract_id, _assessment(fresh, probable=True, on="2026-09-08"))
    assert taken.status_code == 201, taken.text
    assert _books(world, contract_id)["ASC606"][0] == "ACTIVE"
    # The flag is answered: a later probable assessment on the same record is no reassessment.
    again = _record_events(world, contract_id, _assessment(fresh, probable=True, on="2026-09-09"))
    assert again.status_code == 201, again.text
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_step1_cite_latest_1_a_not_probable_assessment_does_not_cite_an_overtaken_review(
    world: SeatWorld,
) -> None:
    """Case (ii). COLLECTIBILITY and NOT_A_CONTRACT are one judgement with two outcomes: a later
    review of either overtakes an earlier one of the other (the hold head's (c') released the
    overtaken record's hold and left the record REVIEWED). Measured before: after a flag, a
    NOT_A_CONTRACT record was reviewed, then a COLLECTIBILITY record — the reviewer's later
    conclusion — and a not-probable assessment that cited the FIRST was taken: 201, the book out
    against its newest review. The route and its preview refuse the overtaken record and name
    the one that overtook it; the judgement's answer names it too (``overtaken_by``), and the
    record stays REVIEWED. The assessment the newest review supports is taken. Two records
    are one judgement only when they share the subject: a record of another contract,
    reviewed before this contract's NOT_A_CONTRACT record, is overtaken by nothing."""
    contract_id, first, request, _reason = _flagged_and_held(world)
    elsewhere = _reviewed(world, _created(world, external_id="SF-ORD-10418"), "COLLECTIBILITY")
    _later(world)
    assert approve(world.app, request, world.marcus).status_code == 200
    _later(world)
    fresh = _reviewed(world, contract_id, "COLLECTIBILITY")
    first_no, fresh_no = _judgement_no(world, first), _judgement_no(world, fresh)

    author = world.place.author
    shown = get(world.app, f"{JUDGEMENTS}/{first}", author).json()
    assert (shown["status"], shown["overtaken_by"]) == (
        "REVIEWED",
        {"id": fresh, "judgement_no": fresh_no},
    )
    assert get(world.app, f"{JUDGEMENTS}/{fresh}", author).json()["overtaken_by"] is None
    listed = get(world.app, JUDGEMENTS, author)  # one page, the records of both contracts
    assert listed.status_code == 200, listed.text
    assert {
        item["judgement_no"]: (item["status"], item["overtaken_by"])
        for item in listed.json()["items"]
    } == {
        "JDG-000001": ("SUPERSEDED", None),  # the activation's record, superseded by the fresh one
        first_no: ("REVIEWED", {"id": fresh, "judgement_no": fresh_no}),
        _judgement_no(world, elsewhere): ("REVIEWED", None),  # the other contract's
        fresh_no: ("REVIEWED", None),
    }

    _cite_refused(
        world,
        contract_id,
        CITED_OVERTAKEN.format(judgement_no=fresh_no),
        _assessment(first, probable=False, on="2026-09-08"),
    )
    assert _status_of(world, first) == "REVIEWED"

    taken = _record_events(world, contract_id, _assessment(fresh, probable=True, on="2026-09-08"))
    assert taken.status_code == 201, taken.text
    assert _books(world, contract_id)["ASC606"][0] == "ACTIVE"
    assert _recognition(world) == [("SF-ORD-10417", "ASC606", "ACTIVE")]
    assert _unapproved_recognition(world) == []


def test_step1_cite_latest_1_the_later_review_of_either_topic_overtakes_the_other(
    world: SeatWorld,
) -> None:
    """The mirror, on a DRAFT contract: a COLLECTIBILITY record is reviewed, then a
    NOT_A_CONTRACT record — the probable assessment that cites the first is refused by the
    second's name, and the not-probable assessment on the second is taken with its gate. The
    clock of this witness stands still between the two reviews: of two reviews stamped with one
    instant the higher judgement number is the newer."""
    contract_id = _k09(world)
    probable = _reviewed(world, contract_id, "COLLECTIBILITY")
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    author = world.place.author
    stamps = {
        get(world.app, f"{JUDGEMENTS}/{item}", author).json()["reviewed_at"]
        for item in (probable, record)
    }
    assert len(stamps) == 1  # one instant: the number decides
    assert _judgement_no(world, record) > _judgement_no(world, probable)

    refused = _append(world, contract_id, 1, _assessment(probable, probable=True))
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("events.0.payload.judgement_record_id", "REQ-POL-008")]
    assert refused.json()["errors"][0]["message"] == CITED_OVERTAKEN.format(
        judgement_no=_judgement_no(world, record)
    )
    assert _header(world, contract_id) == ("DRAFT", 1)

    assessed = _append(world, contract_id, 1, _assessment(record, probable=False))
    assert assessed.status_code == 201, assessed.text
    assert assessed.json()["step1_gate"] == APPENDED
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 3)


def test_rpt_bridge_step1_chain_1_the_step1_reading_at_a_record_cutoff(world: SeatWorld) -> None:
    """Item RPT-BRIDGE-STEP1-CHAIN-1 (the supervisor's ruling of 2026-10-01, way (b)): the
    contract's own Step 1 per book from its events as they stood at a record cutoff —
    ``step1.read(..., recorded_by=...)`` reads the events recorded at or before it, and a void
    counts only when the EVENT_VOIDED itself was recorded by then. K-09 is activated, flagged,
    taken out by a not-probable assessment, and the flag is then voided, each a minute apart:
    the reading at each of the four times is what the stream held then, and without a cutoff it
    is today's."""
    from erev_api.events import step1

    assign(world.priya.member, "revenue_reviewer")
    clock = world.place.clock
    contract_id = _created(world)
    _activated(world, contract_id)
    activated_at = clock.now()
    _later(world)
    assert _record_events(world, contract_id, FLAG).status_code == 201
    flagged_at = clock.now()
    _later(world)
    record = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)
    out = _record_events(world, contract_id, _assessment(record, probable=False, on="2026-09-08"))
    assert out.status_code == 201, out.text
    out_at = clock.now()
    _later(world)
    flag_event = next(
        event
        for event in _stream(world, contract_id)
        if str(event["event_type"]) == "SIGNIFICANT_CHANGE_FLAGGED"
    )
    requested = post(
        world.app,
        f"/api/v1/events/{flag_event['id']}/request-void",
        world.place.author,
        {"reason_code": "CREATED_IN_ERROR", "comment": "The downgrade was another customer's."},
    )
    assert requested.status_code == 201, requested.text
    voided = approve(world.app, requested.json()["approval_request_id"], world.priya)
    assert voided.status_code == 200, voided.text

    def reading(at: Any) -> tuple[int, list[str], bool, bool]:
        context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            stream = step1.read(session, contract_id, recorded_by=at)
        stands = step1.standing(stream, "ASC606")
        return len(stream.assessments), sorted(stream.out), stands.active, stands.flagged

    assert reading(activated_at) == (1, [], True, False)
    assert reading(flagged_at) == (1, [], True, True)
    assert reading(out_at) == (2, ["ASC606"], False, False)
    # The void of the flag was recorded after ``out_at``: at that cutoff the flag stands and the
    # book is out; today the flag counts for nothing and the book never left.
    assert reading(clock.now()) == reading(None) == (2, [], True, False)


# --- the activation's half of item STEP1-CITE-LATEST-1 --------------------------------------------

# 04 table 15.4-I ``STEP1_RECORD_OVERTAKEN``: the sentence of the checklist item ``STEP1_RECORD``.
STEP1_OVERTAKEN = (
    "The Step 1 assessment of {book} rests on judgement record {judgement_no}, which the review "
    "of judgement record {later_judgement_no} has overtaken. Record the assessment on the latest "
    "review."
)


def test_step1_cite_latest_1_a_draft_is_not_activated_on_an_overtaken_record(
    world: SeatWorld,
) -> None:
    """The route asks for the newest review when an assessment is recorded; a record can be
    overtaken afterwards, and it stays REVIEWED. Measured before: a DRAFT contract whose
    probable assessment cited a reviewed COLLECTIBILITY record, and for which a NOT_A_CONTRACT
    record was reviewed a minute later, failed no checklist item — ``submit-activation`` 200,
    the approval 200, the contract ACTIVE and recognising against its newest review. The item
    ``STEP1_RECORD`` now fails for the book and says which record overtook which; the
    submission answers 409; and the assessment the newest review supports is then recorded."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    first = _reviewed(world, contract_id, "COLLECTIBILITY")
    assessed = _record_events(world, contract_id, _assessment(first, probable=True))
    assert assessed.status_code == 201, assessed.text
    assert _step1(world, contract_id) == (True, None)
    _later(world)
    second = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)

    assert _step1(world, contract_id) == (
        False,
        STEP1_OVERTAKEN.format(
            book="ASC606",
            judgement_no=_judgement_no(world, first),
            later_judgement_no=_judgement_no(world, second),
        ),
    )
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed"), refused
    assert fields(refused) == [(None, "STEP1_RECORD")]
    assert _activation_requests(world, contract_id) == []
    assert _header(world, contract_id) == ("DRAFT", 2)

    gated = _record_events(world, contract_id, _assessment(second, probable=False))
    assert gated.status_code == 201, gated.text
    assert gated.json()["step1_gate"] == APPENDED
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _recognition(world) == _unapproved_recognition(world) == []


def test_step1_cite_latest_1_a_record_overtaken_while_the_activation_waits_stops_its_approval(
    world: SeatWorld,
) -> None:
    """The gate is evaluated again where the approval executes: a record that is overtaken while
    the activation request waits stops the approval with the same item, the request stays
    pending and nothing is appended."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _created(world)
    first = _reviewed(world, contract_id, "COLLECTIBILITY")
    assert _record_events(world, contract_id, _assessment(first, probable=True)).status_code == 201
    submitted = _submit(world, contract_id)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]
    _later(world)
    _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)

    stopped = approve(world.app, request_id, world.priya)
    assert (stopped.status_code, slug(stopped)) == (409, "activation-checklist-failed"), stopped
    assert fields(stopped) == [(None, "STEP1_RECORD")]
    assert [state for state, _ in _activation_requests(world, contract_id)] == ["PENDING"]
    assert _header(world, contract_id) == ("DRAFT", 2)
    assert _event_types(world, contract_id) == ["CONTRACT_BOOKED", "COLLECTIBILITY_ASSESSED"]
    assert _recognition(world) == _unapproved_recognition(world) == []


def test_step1_cite_latest_1_criteria_met_moves_no_book_on_an_overtaken_record(
    world: SeatWorld,
) -> None:
    """Behind the gate. Measured before: the criteria-met re-assessment cited a COLLECTIBILITY
    record reviewed after the gate, a NOT_A_CONTRACT record was reviewed a minute later, and the
    activation was submitted and approved all the same — ``CONTRACT_CRITERIA_MET`` appended, the
    book recognising. ``step1.criteria_met`` moves no book on an overtaken record. A request
    that waits states the books that move, so its approval is stale (REQ-PLT-014), as it is for
    a superseded record; the next submission is refused by the item, which says so."""
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _k09(world)
    _gated(world, contract_id)
    met = _reviewed(world, contract_id, "COLLECTIBILITY")
    assessed = _record_events(world, contract_id, _assessment(met, probable=True, on="2026-09-10"))
    assert assessed.status_code == 201, assessed.text
    assert _step1(world, contract_id) == (True, None)
    waiting = _submit(world, contract_id)
    assert waiting.status_code == 200, waiting.text
    _later(world)
    again = _reviewed(world, contract_id, "NOT_A_CONTRACT", NOT_A_CONTRACT)

    stale = approve(world.app, waiting.headers[APPROVAL_HEADER], world.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    assert _step1(world, contract_id) == (
        False,
        STEP1_OVERTAKEN.format(
            book="ASC606",
            judgement_no=_judgement_no(world, met),
            later_judgement_no=_judgement_no(world, again),
        ),
    )
    refused = _submit(world, contract_id)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed"), refused
    assert fields(refused) == [(None, "STEP1_RECORD")]
    assert [state for state, _ in _activation_requests(world, contract_id)] == ["VOIDED"]
    assert _header(world, contract_id) == ("NOT_A_CONTRACT", 4)
    assert "CONTRACT_CRITERIA_MET" not in _event_types(world, contract_id)
    assert _recognition(world) == _unapproved_recognition(world) == []


def test_rpt_bridge_step1_chain_1_a_booking_replaced_after_the_cutoff_stands_at_it(
    world: SeatWorld,
) -> None:
    """The latest standing booking is read at the cutoff too (``Step1Stream.booked_at``; ruling
    R-102 (c)): a draft that was replaced after the cutoff is, at the cutoff, the draft as it
    was booked first — the replacement and its void of the first booking were recorded later."""
    from erev_api.events import step1

    clock = world.place.clock
    contract_id = _created(world)
    first_at = clock.now()
    _later(world)
    assert _replaced(world, contract_id).status_code == 200

    def booked_at(at: Any) -> Any:
        context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            return step1.read(session, contract_id, recorded_by=at).booked_at

    assert clock.now() > first_at
    assert booked_at(first_at) == first_at
    assert booked_at(clock.now()) == booked_at(None) == clock.now()
