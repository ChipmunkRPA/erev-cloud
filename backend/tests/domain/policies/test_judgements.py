"""API-R-33 judgement records (04 T-CON-19 questionnaire schemas, §15.3 API-R-33, E-57; PRD SM-10,
§2.5 routing row ``JUDGEMENT_RECORD``; 03 REQ-POL-008; BUILD_SPEC CTR-7).

World: ``support.factories.seat_world`` (PRD §2.6 for K-09 on AVM-US). Maya (Revenue Accountant)
prepares records with ``judgement.create``; Marcus (Controller; MFA) reviews them with
``judgement.review``. Contracts are booked through ``book_contract`` and stay DRAFT.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import routing
from erev_api.approvals.subjects import JUDGEMENT_AUTHOR_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_event,
    contract_hold,
    judgement_record,
)
from erev_api.domain.policies.judgements import NOT_THE_CREATOR
from erev_api.enums import ApprovalSubjectType, RuleSetKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, k09_body, seat_world, step1_criteria
from support.principals import Actor, colleague, enrolled, member
from support.reference import APPROVALS, approve, assign, fields, get, patch, post, reject, slug
from support.rows import insert_contract_rows, insert_role_assignment, publish_rule_set

JUDGEMENTS = "/api/v1/judgements"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _contract(world: SeatWorld) -> UUID:
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    return UUID(str(booked.contract["id"]))


def _body(contract_id: UUID, topic: str, questionnaire: dict[str, Any] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "topic": topic,
        "subject_type": "contract",
        "subject_id": str(contract_id),
        "book": "ASC606",
        "conclusion": "The customer can terminate for convenience at the end of each quarter.",
        "rationale": "No substantive penalty applies; the term ends at the earliest termination.",
        "codification_refs": ["606-10-25-3"],
    }
    if questionnaire is not None:
        body["questionnaire"] = questionnaire
    return body


def test_questionnaire_validated_per_topic(world: SeatWorld) -> None:
    contract_id = _contract(world)
    author = world.place.author
    refused = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(contract_id, "NOT_A_CONTRACT", {"event_c_met_on": "2026-10-01"}),
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("questionnaire.consideration_nonrefundable", "T-CON-19")]

    term = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(contract_id, "CONTRACT_TERM", {"termination_penalty_substantive": False}),
    )
    assert term.status_code == 422, term.text
    assert slug(term) == "validation-failed"
    assert fields(term) == [("questionnaire.enforceable_end_date", "T-CON-19")]
    # A boolean member is a JSON boolean, not a string.
    stringly = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": "false"},
        ),
    )
    assert stringly.status_code == 422, stringly.text
    assert fields(stringly) == [("questionnaire.termination_penalty_substantive", "T-CON-19")]

    created = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {
                "enforceable_end_date": "2026-12-31",
                "termination_penalty_substantive": False,
                "notice_letter": "Clause 14.2",
            },
        ),
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert created.headers["Location"] == f"{JUDGEMENTS}/{record['id']}"
    assert (
        record["judgement_no"],
        record["status"],
        record["contract_id"],
        record["book"],
        record["questionnaire"],
        record["reviewer"],
    ) == (
        "JDG-000001",
        "DRAFT",
        str(contract_id),
        "ASC606",
        # Members the schema does not list are kept as evidence (T-CON-19).
        {
            "enforceable_end_date": "2026-12-31",
            "termination_penalty_substantive": False,
            "notice_letter": "Clause 14.2",
        },
        None,
    )
    # Updates are validated too.
    edited = patch(
        world.app,
        f"{JUDGEMENTS}/{record['id']}",
        author,
        {"questionnaire": {"enforceable_end_date": "2026-12-31"}},
        if_match=None,
    )
    assert edited.status_code == 422, edited.text
    assert fields(edited) == [("questionnaire.termination_penalty_substantive", "T-CON-19")]


def test_licence_nature_55_62_criteria_answered_together_for_functional_ip(
    world: SeatWorld,
) -> None:
    """04 T-CON-19 ``LICENCE_NATURE`` rev 1.11 (D-91 gaps (viii); ENA-4b): the two ASC606
    606-10-55-62 members are answered together (one alone is 422 ``validation-failed`` with a
    T-CON-19 field error), permitted only when ``nature`` is FUNCTIONAL, and stored as JSON
    booleans."""
    contract_id = _contract(world)
    author = world.place.author
    base = {"obligation_key": "L-1", "nature": "FUNCTIONAL"}
    alone = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "LICENCE_NATURE",
            {**base, "functionality_expected_to_change_substantively": True},
        ),
    )
    assert alone.status_code == 422, alone.text
    assert slug(alone) == "validation-failed"
    assert fields(alone) == [("questionnaire", "T-CON-19")]
    symbolic = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "LICENCE_NATURE",
            {
                "obligation_key": "L-1",
                "nature": "SYMBOLIC",
                "functionality_expected_to_change_substantively": True,
                "customer_required_to_use_updated_ip": True,
            },
        ),
    )
    assert (symbolic.status_code, fields(symbolic)) == (422, [("questionnaire", "T-CON-19")])
    stringly = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "LICENCE_NATURE",
            {
                **base,
                "functionality_expected_to_change_substantively": "true",
                "customer_required_to_use_updated_ip": True,
            },
        ),
    )
    assert stringly.status_code == 422, stringly.text
    assert fields(stringly) == [
        ("questionnaire.functionality_expected_to_change_substantively", "T-CON-19")
    ]
    created = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "LICENCE_NATURE",
            {
                **base,
                "functionality_expected_to_change_substantively": True,
                "customer_required_to_use_updated_ip": True,
            },
        ),
    )
    assert created.status_code == 201, created.text
    assert created.json()["questionnaire"] == {
        "obligation_key": "L-1",
        "nature": "FUNCTIONAL",
        "functionality_expected_to_change_substantively": True,
        "customer_required_to_use_updated_ip": True,
    }
    plain = post(world.app, JUDGEMENTS, author, _body(contract_id, "LICENCE_NATURE", base))
    assert plain.status_code == 201, plain.text  # neither member: the right to use


def test_submit_routes_judgement_review(world: SeatWorld) -> None:
    contract_id = _contract(world)
    author = world.place.author
    created = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
        ),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    submitted = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", author, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    shown = submitted.json()
    assert shown["status"] == "SUBMITTED"
    assert shown["content_sha256"] is not None
    request_id = shown["approval_request_id"]
    request = get(world.app, f"{APPROVALS}/{request_id}", world.marcus)
    assert request.status_code == 200, request.text
    detail = request.json()
    assert (detail["subject"]["type"], detail["subject"]["id"], detail["status"]) == (
        "JUDGEMENT_RECORD",
        record_id,
        "PENDING",
    )
    assert [step["required_permission"] for step in detail["steps"]] == ["judgement.review"]
    # A DRAFT-only edit is refused once submitted.
    late = patch(
        world.app, f"{JUDGEMENTS}/{record_id}", author, {"rationale": "Changed"}, if_match=None
    )
    assert late.status_code == 409, late.text
    assert slug(late) == "invalid-transition"

    approved = approve(world.app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    reviewed = get(world.app, f"{JUDGEMENTS}/{record_id}", author)
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert (body["status"], body["reviewer"]["id"], body["reviewed_at"]) == (
        "REVIEWED",
        str(world.marcus.member.user_id),
        world.place.clock.now().isoformat().replace("+00:00", "Z"),
    )
    actions = world.place.rows(
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_id == UUID(record_id),
            audit_event.c.action.like("judgement_record.%"),
        )
    )
    assert sorted((row["action"], row["before"]["status"]) for row in actions if row["before"]) == [
        ("judgement_record.reviewed", "SUBMITTED"),
        ("judgement_record.submitted", "DRAFT"),
    ]


def test_unreviewed_judgements_listed(world: SeatWorld) -> None:
    contract_id = _contract(world)
    author = world.place.author
    records = []
    for topic, questionnaire in (
        ("COLLECTIBILITY", None),
        # sent for review below, so with the five criteria (supervisor rulings R-113 (f), R-115 (f))
        (
            "NOT_A_CONTRACT",
            {
                "consideration_nonrefundable": True,
                "criteria": step1_criteria("NOT_A_CONTRACT"),
            },
        ),
    ):
        created = post(world.app, JUDGEMENTS, author, _body(contract_id, topic, questionnaire))
        assert created.status_code == 201, created.text
        records.append(created.json()["id"])
    submitted = post(world.app, f"{JUDGEMENTS}/{records[1]}/submit", author, {})
    assert submitted.status_code == 200, submitted.text

    listed = get(world.app, JUDGEMENTS, author, {"status": "SUBMITTED", "subject_type": "contract"})
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [(item["id"], item["topic"], item["status"]) for item in items] == [
        (records[1], "NOT_A_CONTRACT", "SUBMITTED")
    ]
    everything = get(world.app, JUDGEMENTS, author, {"subject_id": str(contract_id)})
    assert everything.status_code == 200, everything.text
    assert sorted(item["id"] for item in everything.json()["items"]) == sorted(records)
    unknown = get(world.app, JUDGEMENTS, author, {"stage": "x"})
    assert unknown.status_code == 422, unknown.text


EVENTS = "/api/v1/contracts/{contract_id}/events"
# D-98 candidate 101c (c): an event the judged contract receives between the request and the review.
BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4201",
        "line_external_id": "INV-US-4201-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}


def test_review_is_stale_after_a_contract_event(world: SeatWorld) -> None:
    """04 §16.10 rev 1.49 (D-98 candidate 101c): the JUDGEMENT_RECORD subject content carries the
    judged contract's current group id and stream head, so an event appended to the contract
    between the request and the decision voids the request STALE_SUBJECT (409 ``stale-approval``);
    the record returns to REJECTED through on_voided and no recompute ran on rows the reviewer did
    not see. DB-bound, NOT RUN on l12."""
    contract_id = _contract(world)
    author = world.place.author
    created = post(
        world.app,
        JUDGEMENTS,
        author,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
        ),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    submitted = post(world.app, f"{JUDGEMENTS}/{record_id}/submit", author, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    head = int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    appended = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        author,
        {"events": [BILLING]},
        if_match=f'"s{head}"',
    )
    # 201 appended, 202 API-S-Job when the compute is deferred (04 §16.3 API-S-EventAppend).
    assert appended.status_code in (201, 202), appended.text
    stale = approve(world.app, request_id, world.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    request = get(world.app, f"{APPROVALS}/{request_id}", world.marcus).json()
    assert (request["status"], request["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", author).json()
    assert (shown["status"], shown["reviewer"]) == ("REJECTED", None)


# --- D-98 candidate 101d (P5-LOCK-R3d): the approved basis of an ACTIVE contract's judgement ------


def _active_contract(world: SeatWorld) -> UUID:
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=True)
    return UUID(str(booked.contract["id"]))


def _submitted(world: SeatWorld, contract_id: UUID) -> tuple[str, str]:
    """A CONTRACT_TERM judgement of the contract, submitted: ``(record id, request id)``."""
    created = post(
        world.app,
        JUDGEMENTS,
        world.place.author,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
        ),
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(
        world.app, f"{JUDGEMENTS}/{record_id}/submit", world.place.author, {"comment": "Review"}
    )
    assert submitted.status_code == 200, submitted.text
    return record_id, str(submitted.json()["approval_request_id"])


def _head(world: SeatWorld, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _last_event_type(world: SeatWorld, contract_id: UUID) -> str:
    rows = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version.desc())
        .limit(1)
    )
    return str(getattr(rows[0]["event_type"], "value", rows[0]["event_type"]))


def test_active_pending_judgement_holds_first_then_approves_unchanged(world: SeatWorld) -> None:
    """DG-KRN-APR-05 rev 1.40 (Codex SELF-STALE-R1): the REQ-POL-010 hold of an ACTIVE contract is
    applied BEFORE the basis is hashed, so an immediate unchanged approval SUCCEEDS; before this
    slice the hold's HOLD_APPLIED advanced the head after the hash and the first approval voided
    STALE_SUBJECT with no external edit. DB-bound, NOT RUN on l12."""
    contract_id = _active_contract(world)
    record_id, request_id = _submitted(world, contract_id)
    assert _last_event_type(world, contract_id) == "HOLD_APPLIED"
    approved = approve(world.app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author).json()
    assert shown["status"] == "REVIEWED"
    assert _last_event_type(world, contract_id) == "HOLD_RELEASED"


def test_active_pending_judgement_is_stale_after_a_later_event(world: SeatWorld) -> None:
    """The head-based protection stays: an event appended to the ACTIVE contract after the hold
    and the hash makes the decision stale (409 ``stale-approval``, VOIDED STALE_SUBJECT). DB-bound,
    NOT RUN on l12."""
    contract_id = _active_contract(world)
    record_id, request_id = _submitted(world, contract_id)
    appended = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match=f'"s{_head(world, contract_id)}"',
    )
    # 201 appended, 202 API-S-Job when the compute is deferred (04 §16.3 API-S-EventAppend).
    assert appended.status_code in (201, 202), appended.text
    stale = approve(world.app, request_id, world.marcus)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    request = get(world.app, f"{APPROVALS}/{request_id}", world.marcus).json()
    assert (request["status"], request["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author).json()
    assert shown["status"] == "REJECTED"


def test_resubmitted_judgement_reuses_its_open_hold(world: SeatWorld) -> None:
    """The existing-same-reason-hold control: a rejected record edited back to DRAFT and
    resubmitted finds its SYSTEM hold still open — ``apply_system_hold`` answers it without a new
    event, the head is unchanged, the basis is hashed after it and the approval succeeds.
    DB-bound, NOT RUN on l12."""
    contract_id = _active_contract(world)
    record_id, request_id = _submitted(world, contract_id)
    rejected = reject(world.app, request_id, world.marcus, "Explain the penalty.")
    assert rejected.status_code == 200, rejected.text
    edited = patch(
        world.app,
        f"{JUDGEMENTS}/{record_id}",
        world.place.author,
        {"rationale": "The penalty is a reimbursement of costs, not a deterrent."},
        if_match=None,
    )
    assert edited.status_code == 200, edited.text
    head_before = _head(world, contract_id)
    resubmitted = post(
        world.app, f"{JUDGEMENTS}/{record_id}/submit", world.place.author, {"comment": "Again"}
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert _head(world, contract_id) == head_before  # the open hold answered; no HOLD_APPLIED
    approved = approve(world.app, resubmitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author).json()
    assert shown["status"] == "REVIEWED"


def test_hold_and_outcome_bind_to_one_routing_decision_across_a_publication(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Codex ROUTING-R1 (packet 1337; DG-KRN-APR-01 rev 1.40), the admissible direction. Batch #4
    on main c9110467 measured the first form of this case (a custom AUTO_APPROVAL v1 for
    JUDGEMENT_RECORD, superseded between the former two reads): its premise is inadmissible in
    this domain — an auto-approved judgement record is reviewed by its preparer, and DB-10
    ``tg_judgement_record__review`` refuses that (EREV-APR-001, 403 ``self-approval``); the CPU
    case (``test_submit_judgement_binds_the_hold_and_the_outcome_to_one_routing_decision``,
    stubbed routing) carries the split between the two readings. One reading decides the hold and
    the request: PENDING, the contract held, 200 — consistent — and the published state was read
    once. DB-bound, NOT RUN on l12.

    Supervisor rulings R-26 (b) and Q2 reading (A) (04 §16.10 rev 1.104): no AUTO_APPROVAL rule is
    read for a judgement record a user prepares, so the second form of this case — a concurrent
    publication of an AUTO_APPROVAL rule for JUDGEMENT_RECORD between the former two reads — has
    no reading left to count. The case counts the reading that still happens, the routed steps: no
    routing rule names JUDGEMENT_RECORD at the first reading; a concurrent, committed publication
    of an APPROVAL_ROUTING rule with two review steps lands right after it. A second reading
    inside ``approvals.submit`` would give the request those two steps, under a hold decided on
    the first. The request carries the first reading's single step and names no routing rule."""
    tenant_id = world.place.tenant_id
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    contract_id = _active_contract(world)
    real = routing.resolve_steps
    readings: list[Any] = []

    def publishing(session: Any, facts: Any, *, fallback: Any, at: Any) -> Any:
        found = real(session, facts, fallback=fallback, at=at)
        readings.append(found)
        if len(readings) == 1:
            # The concurrent publication, committed between the two former reads.
            with tenant_session(ctx) as other:
                publish_rule_set(
                    other,
                    tenant_id=tenant_id,
                    kind=RuleSetKind.APPROVAL_ROUTING,
                    code="P5-ROUTE-JR",
                    rules=[
                        {
                            "rule_key": "ROUTE-JR-01",
                            "conditions": [
                                {"field": "subject.type", "op": "eq", "value": "JUDGEMENT_RECORD"}
                            ],
                            "outputs": {
                                "steps": [
                                    {
                                        "name": "Review",
                                        "permission": "judgement.review",
                                        "min_approvers": 1,
                                    },
                                    {
                                        "name": "Second review",
                                        "permission": "judgement.review",
                                        "min_approvers": 1,
                                    },
                                ]
                            },
                        }
                    ],
                )
        return found

    monkeypatch.setattr(routing, "resolve_steps", publishing)
    record_id, request_id = _submitted(world, contract_id)  # 200: one reading, no rule yet
    request = get(world.app, f"{APPROVALS}/{request_id}", world.marcus).json()
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author).json()
    held = _last_event_type(world, contract_id) == "HOLD_APPLIED"
    # Consistent: held with a pending review, or auto-approved and unheld — never split.
    assert held == (request["status"] == "PENDING"), (held, request["status"])
    assert (request["status"], shown["status"], held, len(readings)) == (
        "PENDING",
        "SUBMITTED",
        True,
        1,
    )
    # The request is the first reading's: the subject's own step, chosen by no rule.
    assert readings[0].rule is None
    assert [
        (step["step_no"], step["required_permission"], step["min_approvers"])
        for step in request["steps"]
    ] == [(1, "judgement.review", 1)]
    assert request["routing"] == {"rule_set_version_id": None, "rule_key": None}
    # The publication is real: a reading taken now finds the rule and its two steps.
    with tenant_session(ctx, read_only=True) as session:
        later = real(
            session,
            routing.routing_facts(
                subject_type=ApprovalSubjectType.JUDGEMENT_RECORD,
                entity_codes=(),
                amount_functional=None,
                flags=[],
            ),
            fallback=readings[0].steps,
            at=clock.now(),
        )
    assert later.rule is not None
    assert [(step.name, step.permission) for step in later.steps] == [
        ("Review", "judgement.review"),
        ("Second review", "judgement.review"),
    ]


def test_author_cannot_review_through_a_delegate(world: SeatWorld, clock: FrozenClock) -> None:
    """T-CON-19 "``reviewer_id`` must differ from ``created_by``" through delegation (supervisor
    ruling R-25; REQ-PLT-011 "across UI, API, delegation and role switching"; the BR-JE-01 family).
    Ana authors a judgement record and Tomas submits it, so Ana is not the request's preparer. Ana
    also holds ``judgement.review`` and delegates it to Dora, who holds no approval permission of
    her own: Dora's decision would be the author's review taken on her behalf — 403
    ``self-approval``, as for Ana in person — and the record stays SUBMITTED. The Controller, who
    did not write it, reviews it."""
    app, tenant_id = world.app, world.place.tenant_id
    contract_id = _contract(world)
    ana_member = colleague(tenant_id, "ana")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(ana_member, code)
    ana = enrolled(app, clock, ana_member)
    tomas_member = colleague(tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    tomas = enrolled(app, clock, tomas_member)
    dora_member = colleague(tenant_id, "dora")
    assign(dora_member, "viewer")
    dora = enrolled(app, clock, dora_member)

    created = post(
        app,
        JUDGEMENTS,
        ana,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
        ),
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(app, f"{JUDGEMENTS}/{record_id}/submit", tomas, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])

    now = clock.now()
    delegated = post(
        app,
        "/api/v1/approval-delegations",
        ana,
        {
            "delegate_membership_id": str(dora.member.membership_id),
            "permissions": ["judgement.review"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "reason": "Out of office",
        },
    )
    assert delegated.status_code == 201, delegated.text
    detail = get(app, f"{APPROVALS}/{request_id}", dora)
    assert detail.status_code == 200 and detail.json()["can_decide"] is False, detail.text
    for approver in (dora, ana):
        refused = approve(app, request_id, approver)
        assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
        assert refused.json()["detail"] == JUDGEMENT_AUTHOR_DETAIL
    shown = get(app, f"{JUDGEMENTS}/{record_id}", ana).json()
    assert (shown["status"], shown["reviewed_at"]) == ("SUBMITTED", None)
    pending = get(app, f"{APPROVALS}/{request_id}", tomas).json()
    assert [step["decisions"] for step in pending["steps"]] == [[]]

    approved = approve(app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    assert get(app, f"{JUDGEMENTS}/{record_id}", ana).json()["status"] == "REVIEWED"


def test_r64_a_draft_judgement_is_changed_only_by_its_creator(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (7) (a); 04 T-CON-19 rev 1.104 part 6. The author rule reads
    ``created_by``: the author of a record is the one person who may not review it. Ana creates
    a draft. Tomas, who may prepare judgement records and also reviews them, rewrites its
    conclusion by PATCH: before the ruling that succeeded, Ana submitted "her" record, and Tomas
    — neither its creator nor the request's preparer — reviewed the content he had written. Now
    the draft is changed only by its creator (403 by name for anyone else, nothing written);
    Ana's own edit and submission stand, and Tomas, who wrote none of it, reviews it."""
    app, tenant_id = world.app, world.place.tenant_id
    contract_id = _contract(world)
    ana_member = colleague(tenant_id, "ana")
    assign(ana_member, "revenue_accountant")
    ana = enrolled(app, clock, ana_member)
    tomas_member = colleague(tenant_id, "tomas")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(tomas_member, code)
    tomas = enrolled(app, clock, tomas_member)

    created = post(
        app,
        JUDGEMENTS,
        ana,
        _body(
            contract_id,
            "CONTRACT_TERM",
            {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
        ),
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    written = created.json()["conclusion"]

    rewritten = patch(
        app,
        f"{JUDGEMENTS}/{record_id}",
        tomas,
        {"conclusion": "The term runs to the end of the contract; no termination right exists."},
        if_match=None,
    )
    assert (rewritten.status_code, slug(rewritten)) == (403, "forbidden"), rewritten.text
    # Item JDG-REJECTED-EXIT-1: a draft can be discarded, and the refusal says so.
    assert rewritten.json()["detail"] == NOT_THE_CREATOR_DISCARD
    shown = get(app, f"{JUDGEMENTS}/{record_id}", ana).json()
    assert (shown["status"], shown["conclusion"]) == ("DRAFT", written)

    # Positive controls: the creator edits and submits; a reviewer who wrote none of it reviews.
    edited = patch(
        app,
        f"{JUDGEMENTS}/{record_id}",
        ana,
        {"rationale": "The customer may terminate at each quarter end without a penalty."},
        if_match=None,
    )
    assert edited.status_code == 200, edited.text
    submitted = post(app, f"{JUDGEMENTS}/{record_id}/submit", ana, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, str(submitted.json()["approval_request_id"]), tomas)
    assert approved.status_code == 200, approved.text
    reviewed = get(app, f"{JUDGEMENTS}/{record_id}", ana).json()
    assert (reviewed["status"], reviewed["conclusion"]) == ("REVIEWED", written)
    assert reviewed["reviewer"]["id"] == str(tomas.member.user_id)


def test_a_step1_record_answers_the_five_criteria_when_it_is_sent_for_review(
    world: SeatWorld,
) -> None:
    """04 T-CON-19 "Step 1 criteria" (rev 1.150; supervisor rulings R-113 (f), R-115 (f); item
    STEP1-CRITERIA-1; 03 REQ-CON-003). The five answers of a Step 1 review were a convention of
    the review form inside a free-form questionnaire: the API took a record without them, and the
    not-a-contract gate honoured it. A record of topic COLLECTIBILITY or NOT_A_CONTRACT carries
    ``questionnaire.criteria`` — the keys a to e, each YES or NO: optional and partial while the
    record is a draft, whole when it is sent for review; wherever (e) is answered it agrees with
    the topic, and (d) with the contract's commercial substance. Each refusal names its key.
    Control: a record of another topic is not asked for them."""
    contract_id = _contract(world)  # K-09: has commercial substance
    author = world.place.author

    def created(topic: str, questionnaire: dict[str, Any] | None) -> Any:
        return post(world.app, JUDGEMENTS, author, _body(contract_id, topic, questionnaire))

    def refused_at(response: Any) -> list[str | None]:
        assert response.status_code == 422, response.text
        assert slug(response) == "validation-failed"
        assert {rule for _, rule in fields(response)} == {"T-CON-19"}
        return [field for field, _ in fields(response)]

    # The shape: the keys a to e, each YES or NO, and no other key.
    assert refused_at(created("COLLECTIBILITY", {"criteria": {"f": "YES"}})) == [
        "questionnaire.criteria.f"
    ]
    assert refused_at(created("COLLECTIBILITY", {"criteria": {"a": "MAYBE"}})) == [
        "questionnaire.criteria.a"
    ]
    # (e) agrees with the topic, wherever the answer is written.
    probable_no = created("COLLECTIBILITY", {"criteria": step1_criteria(e="NO")})
    assert refused_at(probable_no) == ["questionnaire.criteria.e"]
    assert probable_no.json()["errors"][0]["message"] == (
        "A collectibility record answers Yes to criterion (e). Use topic NOT_A_CONTRACT for a "
        "review that finds collection not probable."
    )
    not_a_contract_yes = created(
        "NOT_A_CONTRACT",
        {
            "consideration_nonrefundable": True,
            "criteria": step1_criteria("NOT_A_CONTRACT", e="YES"),
        },
    )
    assert refused_at(not_a_contract_yes) == ["questionnaire.criteria.e"]
    # (d) agrees with the contract.
    substance = created("COLLECTIBILITY", {"criteria": step1_criteria(d="NO")})
    assert refused_at(substance) == ["questionnaire.criteria.d"]
    assert substance.json()["errors"][0]["message"] == (
        "The contract is recorded with commercial substance; criterion (d) answers No. Correct "
        "the contract or the answer."
    )

    # A draft may hold none of the answers, or some; a submission holds all five.
    draft = created("COLLECTIBILITY", None)
    assert draft.status_code == 201, draft.text
    path = f"{JUDGEMENTS}/{draft.json()['id']}"
    unanswered = post(world.app, f"{path}/submit", author, {})
    assert refused_at(unanswered) == ["questionnaire.criteria"]
    assert unanswered.json()["errors"][0]["message"] == (
        "Answer criteria (a) to (e) of the Step 1 review before it is submitted."
    )
    partial = patch(
        world.app,
        path,
        author,
        {"questionnaire": {"criteria": {"a": "YES", "e": "YES"}}},
        if_match=None,
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["questionnaire"] == {"criteria": {"a": "YES", "e": "YES"}}
    incomplete = post(world.app, f"{path}/submit", author, {})
    assert refused_at(incomplete) == [
        "questionnaire.criteria.b",
        "questionnaire.criteria.c",
        "questionnaire.criteria.d",
    ]
    # An edit is held to the topic as well.
    flipped = patch(
        world.app, path, author, {"questionnaire": {"criteria": {"e": "NO"}}}, if_match=None
    )
    assert refused_at(flipped) == ["questionnaire.criteria.e"]
    whole = patch(
        world.app,
        path,
        author,
        {"questionnaire": {"criteria": step1_criteria(), "credit_grade": "BB"}},
        if_match=None,
    )
    assert whole.status_code == 200, whole.text
    sent = post(world.app, f"{path}/submit", author, {})
    assert sent.status_code == 200, sent.text
    shown = get(world.app, path, author).json()
    assert (shown["status"], shown["questionnaire"]) == (
        "SUBMITTED",
        {"criteria": step1_criteria(), "credit_grade": "BB"},
    )

    # Control: a record of another topic is sent for review without them.
    term = created(
        "CONTRACT_TERM",
        {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False},
    )
    assert term.status_code == 201, term.text
    reviewed = post(world.app, f"{JUDGEMENTS}/{term.json()['id']}/submit", author, {})
    assert reviewed.status_code == 200, reviewed.text


NOT_DISCARDABLE = "Only a draft or rejected judgement record can be discarded."
# Item JDG-REJECTED-EXIT-1: the second preparer's 403 where the record can be discarded, and
# the checklist's line for a rejected record (04 table 15.4-I ``JUDGEMENT_RECORD_REJECTED``).
NOT_THE_CREATOR_DISCARD = (
    "Only the person who created this judgement record can change it. Create a new record "
    "instead and discard this one."
)
REJECTED_LINE = (
    "Judgement record {judgement_no} ({topic}) was rejected. Discard it, or have its author "
    "revise it and send it for review again."
)


def test_jdg_discard_1_a_draft_judgement_record_is_discarded(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """The discard of a judgement record (the supervisor's ruling of 2026-10-01 on the lane's
    question J1 (a); PRD SM-10; 04 T-CON-19, E-57 ``VOIDED``, API-R-33 rev 1.242). SM-10 gave a
    DRAFT record one exit, its submission: a record made by mistake waited for a reviewer's
    rejection. ``POST /judgements/{id}/discard`` moves ANY draft to VOIDED — one that was never
    submitted, discarded by another holder of ``judgement.create``, and one that was submitted,
    rejected and edited again, with its request's history. A record in another status is
    refused; a discarded record takes no command and keeps its number. And it leaves the
    activation checklist (04 table 15.4-I JUDGEMENT_RECORDS), which a draft and a rejected
    record of the contract fail: before, such a record was reviewed after all or the contract
    was never activated."""
    app = world.app
    author = world.place.author
    contract_id = _contract(world)
    term = {"enforceable_end_date": "2026-12-31", "termination_penalty_substantive": False}

    def drafted() -> dict[str, Any]:
        created = post(app, JUDGEMENTS, author, _body(contract_id, "CONTRACT_TERM", term))
        assert created.status_code == 201, created.text
        return dict(created.json())

    def discard(record_id: str, actor: Any = None) -> Any:
        return post(app, f"{JUDGEMENTS}/{record_id}/discard", actor or author, {})

    def checklist() -> tuple[bool, str | None]:
        shown = get(app, f"/api/v1/contracts/{contract_id}/activation-checklist", author)
        assert shown.status_code == 200, shown.text
        [item] = [item for item in shown.json()["items"] if item["code"] == "JUDGEMENT_RECORDS"]
        return item["passed"], item["detail"]

    required = (False, "Judgement record required: Contract term.")

    def refused(response: Any) -> None:
        assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
        assert [
            (error["field"], error["rule_id"], error["message"])
            for error in response.json()["errors"]
        ] == [("status", "DB-03", NOT_DISCARDABLE)]

    # --- a draft that was never submitted, discarded by another holder ---
    assert checklist() == (True, None)
    first = drafted()
    assert checklist() == required
    someone = colleague(world.place.tenant_id, "nadia")
    assign(someone, "revenue_accountant")
    gone = discard(first["id"], enrolled(app, clock, someone))
    assert gone.status_code == 200, gone.text
    assert (
        gone.json()["status"],
        gone.json()["judgement_no"],
        gone.json()["approval_request_id"],
    ) == ("VOIDED", first["judgement_no"], None)
    assert world.place.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_type == "judgement_record",
            audit_event.c.object_id == UUID(first["id"]),
            audit_event.c.action == "judgement_record.voided",
        )
    ) == [{"before": {"status": "DRAFT"}, "after": {"status": "VOIDED"}}]
    voided = get(app, JUDGEMENTS, author, {"status": "VOIDED", "subject_id": str(contract_id)})
    assert [item["id"] for item in voided.json()["items"]] == [first["id"]]
    assert checklist() == (True, None)

    # --- a discarded record takes no command ---
    refused(discard(first["id"]))
    edited = patch(
        app, f"{JUDGEMENTS}/{first['id']}", author, {"rationale": "Too late."}, if_match=None
    )
    assert (edited.status_code, slug(edited)) == (409, "invalid-transition"), edited.text
    sent = post(app, f"{JUDGEMENTS}/{first['id']}/submit", author, {"comment": "Review"})
    assert (sent.status_code, slug(sent)) == (409, "invalid-transition"), sent.text

    # --- submitted, rejected, a draft again by an edit: discarded with its request's history ---
    second = drafted()
    assert second["judgement_no"] > first["judgement_no"]  # the number is not given out again
    submitted = post(app, f"{JUDGEMENTS}/{second['id']}/submit", author, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    refused(discard(second["id"]))  # SUBMITTED
    rejected = reject(app, request_id, world.marcus, "Not this term.")
    assert rejected.status_code == 200, rejected.text
    # a rejected record holds the activation, and the line names it (JDG-REJECTED-EXIT-1)
    assert checklist() == (
        False,
        REJECTED_LINE.format(judgement_no=second["judgement_no"], topic="Contract term"),
    )
    revised = patch(
        app,
        f"{JUDGEMENTS}/{second['id']}",
        author,
        {"rationale": "Revised after the rejection."},
        if_match=None,
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    dropped = discard(second["id"])
    assert dropped.status_code == 200, dropped.text
    assert (dropped.json()["status"], dropped.json()["approval_request_id"]) == (
        "VOIDED",
        request_id,
    )
    assert checklist() == (True, None)


def test_jdg_discard_1_the_hold_of_a_discarded_record_is_released_by_hand(world: SeatWorld) -> None:
    """A record of an ACTIVE contract holds the contract from its submission (REQ-POL-010), and
    the hold stays after a rejection, to be released by hand. The discard is the record's alone:
    it appends nothing to the contract — the head stands and the hold stays open — and the hold
    is released by hand, as after the rejection (04 §16.14 rev 1.242)."""
    app = world.app
    author = world.place.author
    contract_id = _active_contract(world)
    record_id, request_id = _submitted(world, contract_id)
    assert _last_event_type(world, contract_id) == "HOLD_APPLIED"
    rejected = reject(app, request_id, world.marcus, "Not this term.")
    assert rejected.status_code == 200, rejected.text
    revised = patch(
        app, f"{JUDGEMENTS}/{record_id}", author, {"rationale": "Given up."}, if_match=None
    )
    assert (revised.status_code, revised.json()["status"]) == (200, "DRAFT"), revised.text
    head = _head(world, contract_id)

    dropped = post(app, f"{JUDGEMENTS}/{record_id}/discard", author, {})
    assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
    assert _head(world, contract_id) == head
    (hold,) = world.place.rows(
        select(contract_hold.c.id, contract_hold.c.released_at).where(
            contract_hold.c.contract_id == contract_id
        )
    )
    assert hold["released_at"] is None
    shown = get(app, f"/api/v1/contracts/{contract_id}", author)
    assert (shown.status_code, shown.json()["on_hold"]) == (200, True), shown.text

    released = post(
        app,
        f"/api/v1/contracts/{contract_id}/release-hold",
        author,
        {"hold_id": str(hold["id"]), "comment": "The record was discarded."},
        if_match=f'"s{head}"',
    )
    assert released.status_code == 200, released.text
    assert (released.json()["on_hold"], _last_event_type(world, contract_id)) == (
        False,
        "HOLD_RELEASED",
    )


def _judgement_item(world: SeatWorld, contract_id: UUID) -> tuple[bool, str | None]:
    """The checklist item ``JUDGEMENT_RECORDS`` of the contract: passed, and its sentence."""
    shown = get(
        world.app, f"/api/v1/contracts/{contract_id}/activation-checklist", world.place.author
    )
    assert shown.status_code == 200, shown.text
    [item] = [item for item in shown.json()["items"] if item["code"] == "JUDGEMENT_RECORDS"]
    return item["passed"], item["detail"]


def _number(world: SeatWorld, record_id: str) -> str:
    shown = get(world.app, f"{JUDGEMENTS}/{record_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return str(shown.json()["judgement_no"])


def test_jdg_rejected_exit_1_a_rejected_record_is_discarded_as_it_stands(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """Item JDG-REJECTED-EXIT-1 (the supervisor's rulings of 2026-10-02; PRD SM-10; 04 T-CON-19,
    table 15.4-I ``JUDGEMENT_RECORD_REJECTED``). A REJECTED record fails the activation
    checklist and had one exit, its creator's edit, which makes it a draft again. Measured
    before: the discard of a rejected record answered 409, by its creator too, and another
    Revenue Accountant's edit 403 "... Create a new record instead." — which left the rejected
    one where it was. The discard takes a rejected record as it takes a draft: for any holder
    of ``judgement.create`` for the record's entity, with the request's history on the row, one
    audit event that states it from REJECTED, and the record leaves the checklist — whose line
    names the rejected record by its number, and the discard, where it said "Judgement record
    required". A record in review, and a reviewed one, are refused as before."""
    app = world.app
    author = world.place.author
    contract_id = _contract(world)
    record_id, request_id = _submitted(world, contract_id)
    number = _number(world, record_id)

    def discard(actor: Actor) -> Any:
        return post(app, f"{JUDGEMENTS}/{record_id}/discard", actor, {})

    def refused(response: Any) -> None:
        assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
        assert [
            (error["field"], error["rule_id"], error["message"])
            for error in response.json()["errors"]
        ] == [("status", "DB-03", NOT_DISCARDABLE)]

    someone = colleague(world.place.tenant_id, "nadia")
    assign(someone, "revenue_accountant")
    nadia = enrolled(app, clock, someone)

    def taken_over() -> tuple[int, str]:
        """A second preparer's edit: who may act is answered before the record's state."""
        foreign = patch(
            app, f"{JUDGEMENTS}/{record_id}", nadia, {"rationale": "Taken over."}, if_match=None
        )
        return foreign.status_code, str(foreign.json()["detail"])

    # in review: the record waits, the line names its topic (PRD IMP-104), and the second
    # preparer is not sent to a discard that would be refused
    assert _judgement_item(world, contract_id) == (
        False,
        "Judgement record required: Contract term.",
    )
    refused(discard(author))
    assert taken_over() == (403, NOT_THE_CREATOR)
    rejected = reject(app, request_id, world.marcus, "Not this term.")
    assert rejected.status_code == 200, rejected.text
    assert _judgement_item(world, contract_id) == (
        False,
        REJECTED_LINE.format(judgement_no=number, topic="Contract term"),
    )

    # The edit is the creator's alone, and its refusal now names the road ...
    assert taken_over() == (403, NOT_THE_CREATOR_DISCARD)
    # ... the discard writes no content, and is not.
    dropped = discard(nadia)
    assert dropped.status_code == 200, dropped.text
    assert (dropped.json()["status"], dropped.json()["approval_request_id"]) == (
        "VOIDED",
        request_id,
    )
    assert world.place.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_type == "judgement_record",
            audit_event.c.object_id == UUID(record_id),
            audit_event.c.action == "judgement_record.voided",
        )
    ) == [{"before": {"status": "REJECTED"}, "after": {"status": "VOIDED"}}]
    assert _judgement_item(world, contract_id) == (True, None)

    # --- a discarded record takes no command; a reviewed record is not discarded ---
    refused(discard(author))
    edited = patch(
        app, f"{JUDGEMENTS}/{record_id}", author, {"rationale": "Too late."}, if_match=None
    )
    assert (edited.status_code, slug(edited)) == (409, "invalid-transition"), edited.text
    record_id, request_id = _submitted(world, contract_id)
    assert approve(app, request_id, world.marcus).status_code == 200
    refused(discard(author))  # REVIEWED
    assert taken_over() == (403, NOT_THE_CREATOR)


def test_jdg_rejected_exit_1_the_record_passes_the_draft_state_inside_one_transaction(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervisor's two conditions on way (i). PRD SM-10 has no pair REJECTED → VOIDED, and
    the database says so itself: a direct UPDATE of the rejected row to VOIDED is refused by the
    transition trigger (``EREV-TRN-001``). The command sends TWO updates of the row, REJECTED →
    DRAFT and DRAFT → VOIDED, in that order, each a pair DB-03 holds — and they are one unit of
    work: a refusal after the first step leaves the record REJECTED, with nothing audited."""
    from erev_api.db import transitions
    from sqlalchemy import exc, update
    from support.plans import sent

    app = world.app
    author = world.place.author
    contract_id = _contract(world)
    record_id, request_id = _submitted(world, contract_id)
    rejected = reject(app, request_id, world.marcus, "Not this term.")
    assert rejected.status_code == 200, rejected.text
    pairs = transitions.TRANSITIONS["judgement_record"].pairs
    assert ("REJECTED", "VOIDED") not in pairs
    assert {("REJECTED", "DRAFT"), ("DRAFT", "VOIDED")} <= pairs

    def stored() -> tuple[str, int]:
        (row,) = world.place.rows(
            select(judgement_record.c.status, judgement_record.c.row_version).where(
                judgement_record.c.id == UUID(record_id)
            )
        )
        return str(getattr(row["status"], "value", row["status"])), int(row["row_version"])

    def audited() -> int:
        return len(
            world.place.rows(
                select(audit_event.c.id).where(
                    audit_event.c.object_type == "judgement_record",
                    audit_event.c.object_id == UUID(record_id),
                    audit_event.c.action == "judgement_record.voided",
                )
            )
        )

    before = stored()
    assert before[0] == "REJECTED"

    # --- the trigger's own view: one update from REJECTED to VOIDED is no pair ---
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        with pytest.raises(exc.DBAPIError) as direct:
            session.execute(
                update(judgement_record)
                .where(judgement_record.c.id == UUID(record_id))
                .values(status="VOIDED")
            )
        session.rollback()
    message = str(getattr(getattr(direct.value.orig, "diag", None), "message_primary", ""))
    assert "EREV-TRN-001" in message and "cannot change from REJECTED to" in message, message
    assert stored() == before

    # --- a refusal after the first step: nothing is half-done ---
    applied = transitions.apply
    steps: list[tuple[str | None, str | None]] = []

    def failing(session: Any, object_type: str, row_id: Any, **kwargs: Any) -> Any:
        if object_type == "judgement_record":
            steps.append((kwargs.get("expected_status"), kwargs.get("to_status")))
            if kwargs.get("to_status") == "VOIDED":
                raise Problem("invalid-transition", "The second step was refused.")
        return applied(session, object_type, row_id, **kwargs)

    monkeypatch.setattr(transitions, "apply", failing)
    halted = post(app, f"{JUDGEMENTS}/{record_id}/discard", author, {})
    monkeypatch.setattr(transitions, "apply", applied)
    assert (halted.status_code, slug(halted)) == (409, "invalid-transition"), halted.text
    assert steps == [("REJECTED", "DRAFT"), ("DRAFT", "VOIDED")]
    assert (stored(), audited()) == (before, 0)  # the first update went with the transaction

    # --- the command: two updates of the row, both admitted pairs, in that order ---
    with sent() as seen:
        dropped = post(app, f"{JUDGEMENTS}/{record_id}/discard", author, {})
    assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
    moves = [
        (str(parameters["status_1"]), str(parameters["status"]))
        for statement, parameters in seen
        if statement.lstrip().startswith("UPDATE erev.judgement_record")
    ]
    assert moves == [("REJECTED", "DRAFT"), ("DRAFT", "VOIDED")]
    assert all(move in pairs for move in moves)
    assert (stored()[0], audited()) == ("VOIDED", 1)


def test_jdg_rejected_exit_1_a_contract_whose_step1_review_was_rejected_is_activated(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """The journey that was closed (measured on main with index 174). A Step 1 review of a DRAFT
    contract is rejected; the preparer writes a NEW record — what the screens do after a
    rejection — it is reviewed and the probable assessment cites it. ``submit-activation``
    answered 409 for ``JUDGEMENT_RECORDS`` for good, with "Judgement record required:
    Collectibility." beside a reviewed collectibility record: the rejected record could not be
    discarded, and only its creator's edit made it a draft. The item now names the rejected
    record; another Revenue Accountant discards it, and the contract is submitted, approved and
    ACTIVE."""
    app = world.app
    author = world.place.author
    assign(world.priya.member, "revenue_reviewer")
    contract_id = _contract(world)
    events = f"/api/v1/contracts/{contract_id}/events"
    activation = f"/api/v1/contracts/{contract_id}/submit-activation"

    def step1_record() -> tuple[str, str]:
        created = post(
            app,
            JUDGEMENTS,
            author,
            _body(contract_id, "COLLECTIBILITY", {"criteria": step1_criteria()}),
        )
        assert created.status_code == 201, created.text
        sent = post(app, f"{JUDGEMENTS}/{created.json()['id']}/submit", author, {})
        assert sent.status_code == 200, sent.text
        return str(created.json()["id"]), str(sent.json()["approval_request_id"])

    def submit() -> Any:
        return post(
            app,
            activation,
            author,
            {"comment": "Collection is probable."},
            if_match=f'"s{_head(world, contract_id)}"',
        )

    first, first_request = step1_record()
    rejected = reject(app, first_request, world.marcus, "The credit review is missing.")
    assert rejected.status_code == 200, rejected.text
    second, second_request = step1_record()
    assert approve(app, second_request, world.marcus).status_code == 200
    assessed = post(
        app,
        events,
        author,
        {
            "events": [
                {
                    "event_type": "COLLECTIBILITY_ASSESSED",
                    "effective_date": "2026-09-01",
                    "payload": {
                        "book": "ASC606",
                        "is_probable": True,
                        "judgement_record_id": second,
                    },
                }
            ]
        },
        if_match=f'"s{_head(world, contract_id)}"',
    )
    assert assessed.status_code == 201, assessed.text

    held = submit()
    assert (held.status_code, slug(held)) == (409, "activation-checklist-failed"), held.text
    assert [(error["rule_id"], error["message"]) for error in held.json()["errors"]] == [
        (
            "JUDGEMENT_RECORDS",
            REJECTED_LINE.format(judgement_no=_number(world, first), topic="Collectibility"),
        )
    ]

    someone = colleague(world.place.tenant_id, "rosa")
    assign(someone, "revenue_accountant")
    dropped = post(app, f"{JUDGEMENTS}/{first}/discard", enrolled(app, clock, someone), {})
    assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
    assert _judgement_item(world, contract_id) == (True, None)

    submitted = submit()
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.headers["x-erev-approval-request"], world.priya)
    assert decided.status_code == 200, decided.text
    shown = get(app, f"/api/v1/contracts/{contract_id}", author)
    assert (shown.status_code, shown.json()["status"]) == (200, "ACTIVE"), shown.text


def test_jdg_rejected_exit_1_the_hold_of_a_rejected_record_stays_after_its_discard(
    world: SeatWorld,
) -> None:
    """A record of an ACTIVE contract holds the contract from its submission, and the hold stays
    after the rejection (REQ-POL-010). The discard of the rejected record is the record's alone,
    as the discard of a draft is: nothing is appended to the contract, the hold stays open and
    is released by hand."""
    app = world.app
    author = world.place.author
    contract_id = _active_contract(world)
    record_id, request_id = _submitted(world, contract_id)
    assert _last_event_type(world, contract_id) == "HOLD_APPLIED"
    rejected = reject(app, request_id, world.marcus, "Not this term.")
    assert rejected.status_code == 200, rejected.text
    head = _head(world, contract_id)

    dropped = post(app, f"{JUDGEMENTS}/{record_id}/discard", author, {})
    assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
    assert _head(world, contract_id) == head
    (hold,) = world.place.rows(
        select(contract_hold.c.id, contract_hold.c.released_at).where(
            contract_hold.c.contract_id == contract_id
        )
    )
    assert hold["released_at"] is None
    released = post(
        app,
        f"/api/v1/contracts/{contract_id}/release-hold",
        author,
        {"hold_id": str(hold["id"]), "comment": "The record was discarded."},
        if_match=f'"s{head}"',
    )
    assert released.status_code == 200, released.text
    assert (released.json()["on_hold"], _last_event_type(world, contract_id)) == (
        False,
        "HOLD_RELEASED",
    )


def test_jdg_discard_1_the_discard_asks_judgement_create_for_the_records_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """``POST /judgements/{id}/discard`` asks ``judgement.create`` for the entity of the record's
    contract (04 §16.14 rev 1.242), as the edit and the submission of a record do. One tenant,
    entities E_in and E_out with one contract each; Tomas (Revenue Accountant, all entities)
    drafts a record on the E_out contract. Rob holds the role for E_in alone. Rita holds it
    for E_in and reads E_out as a viewer: she reads the record, and the route's own guard is
    passed by her role for E_in. Both discards answer 404, the answer of a permission that is
    not held for the entity (REQ-PLT-012), and the record stays a draft. Olga holds the role
    for E_out and discards the record she did not write."""
    owner = member(keyring, clock, name="tomas")
    tenant_id = owner.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=owner.membership_id,
            role_code="revenue_accountant",
        )
        inside = insert_contract_rows(session, tenant_id)
        outside = insert_contract_rows(session, tenant_id)

    e_in, e_out = inside.entity_id, outside.entity_id

    def scoped(name: str, *grants: tuple[str, UUID]) -> Actor:
        someone = colleague(tenant_id, name)
        for role_code, entity_id in grants:
            assign(someone, role_code, entity_ids=[entity_id])
        return enrolled(app, clock, someone)

    tomas = enrolled(app, clock, owner)
    rob = scoped("rob", ("revenue_accountant", e_in))
    rita = scoped("rita", ("revenue_accountant", e_in), ("viewer", e_out))
    olga = scoped("olga", ("revenue_accountant", e_out))
    created = post(
        app,
        JUDGEMENTS,
        tomas,
        {
            "topic": "OTHER",
            "subject_type": "contract",
            "subject_id": str(outside.contract_id),
            "conclusion": "The side letter changes no right of the customer.",
            "rationale": "Read with legal on 2026-09-01.",
        },
    )
    assert created.status_code == 201, created.text
    record = f"{JUDGEMENTS}/{created.json()['id']}"

    assert get(app, record, rita).status_code == 200
    for outsider in (rob, rita):
        refused = post(app, f"{record}/discard", outsider, {})
        assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert get(app, record, tomas).json()["status"] == "DRAFT"
    dropped = post(app, f"{record}/discard", olga, {})
    assert (dropped.status_code, dropped.json()["status"]) == (200, "VOIDED"), dropped.text
