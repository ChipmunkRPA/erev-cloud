"""The preparer of an event submission is held to her contract's own entity (item
MANUAL-EVENT-PREPARER-SCOPE-1; the supervisor's rulings of 2026-10-01 and 2026-10-02; 04 §16.10
rev 1.269; dev-guide DG-KRN-APR-07 and DG-KRN-EVT-02 rev 1.254; BUILD_SPEC CTR-6).

Since BUILD_SPEC CTR-6 a signed-in person's manual event is a request, and a request of a contract
subject names the contracting entities of the contract's whole combination group (R-25): its
approval computes the group. The kernel held the preparer to every entity her request names (R-64
(6)), so in a group of two contracting entities a Revenue Accountant of one entity could no longer
record her own contract's progress — measured: 403, "This item belongs to legal entities outside
your roles, so you cannot submit it for approval." The seam R-106 (b) gave imports
(``SubjectSpec.preparer_entities``) is stated for ``MANUAL_EVENT`` and ``ATTRIBUTE_CHANGE``: the
preparer is held to the contracting entity of the contract the events are recorded on, while the
request stays bound to the group's contracting entities for its readers and its deciders.

World (``test_reader_independence._two_entities``): SF-ORD-UK-2004 of AVM-UK and SF-ORD-NI-3001 of
AVM-NI in one combination group. Una is a Revenue Accountant of AVM-UK alone, Ulrich a Revenue
Reviewer of AVM-UK alone, Nora a Revenue Accountant of AVM-NI alone, Rosa a Revenue Reviewer of
every entity. DB-bound.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import test_reader_independence as readers
from erev_api.approvals import engine
from erev_api.clock import FrozenClock
from erev_api.db.tables import approval_request, contract, event_submission, legal_entity
from fastapi import FastAPI
from sqlalchemy import select
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, get, gl_account, holding, post, reject
from support.worlds import K04World, evidence_file

app = readers.app
files = readers.files
k04 = readers.k04

APPROVALS = "/api/v1/approvals"
SUBMISSIONS = "/api/v1/event-submissions"
CREATED = {"event_submission_id", "approval_request_id"}


def _progress(ratio: str, day: str) -> dict[str, Any]:
    return {
        "event_type": "PROGRESS_RECORDED",
        "effective_date": day,
        "payload": {
            "obligation_key": "O2",
            "cumulative_progress_ratio": ratio,
            "measure": "OUTPUT_PERCENT",
        },
    }


def _sent(
    app: FastAPI, actor: Actor, contract_id: UUID, event: dict[str, Any], *, evidence: bool = True
) -> Any:
    """``POST /contracts/{id}/events`` with one event, as ``actor``, at the head ``actor`` reads."""
    shown = get(app, f"{readers.CONTRACTS}/{contract_id}", actor)
    if shown.status_code != 200:
        return shown
    body: dict[str, Any] = {"events": [event]}
    if evidence:
        body["evidence_file_ids"] = [evidence_file(app, actor)]
    head = shown.json()["head_stream_version"]
    return post(
        app, f"{readers.CONTRACTS}/{contract_id}/events", actor, body, if_match=f'"s{head}"'
    )


def _people(k04: K04World, clock: FrozenClock) -> tuple[Actor, Actor, Actor, Actor, UUID]:
    """Una, Ulrich, Nora and Rosa, and the id of AVM-NI."""
    app, tenant_id, uk = k04.app, k04.report.tenant_id, k04.uk_entity_id
    (northern,) = k04.report.place.rows(
        select(legal_entity.c.id).where(legal_entity.c.code == readers.NORTHERN)
    )
    ni = UUID(str(northern["id"]))
    una = holding(app, colleague(tenant_id, "una"), "revenue_accountant", entity_ids=[uk])
    local = colleague(tenant_id, "ulrich")
    assign(local, "revenue_reviewer", entity_ids=[uk])
    ulrich = enrolled(app, clock, local)
    nora = holding(app, colleague(tenant_id, "nora"), "revenue_accountant", entity_ids=[ni])
    everywhere = colleague(tenant_id, "rosa")
    assign(everywhere, "revenue_reviewer")
    rosa = enrolled(app, clock, everywhere)
    return una, ulrich, nora, rosa, ni


def _request(k04: K04World, request_id: str) -> dict[str, Any]:
    (row,) = k04.report.place.rows(
        select(approval_request).where(approval_request.c.id == UUID(request_id))
    )
    return dict(row)


def test_manual_event_preparer_scope_1_an_accountant_of_one_entity_records_her_contracts_event(
    k04: K04World, clock: FrozenClock
) -> None:
    """Una records O2's progress on the AVM-UK contract of a group of two contracting entities.
    Her request is stored — until this item it was refused, 403 — and it names BOTH entities: the
    reviewer of AVM-UK alone is refused the decision, the reviewer of every entity approves, and
    the approval appends the event and computes the group. Una is answered the header of her own
    request, not its content; she reads her submission through the contract's routes."""
    place, app = k04.report.place, k04.app
    british, other, group_id = readers._two_entities(k04, readers.NORTHERN)
    una, ulrich, _nora, rosa, ni = _people(k04, clock)

    sent = _sent(app, una, british, _progress("0.50", "2026-06-30"))

    # the status first: without the rule the kernel answers 403 and stores nothing
    assert sent.status_code == 201, sent.text
    assert set(sent.json()) == CREATED
    request_id = str(sent.json()["approval_request_id"])
    submission_id = str(sent.json()["event_submission_id"])
    request = _request(k04, request_id)
    assert (str(request["subject_type"]), str(request["status"])) == ("MANUAL_EVENT", "PENDING")
    # the request is the group's: both contracting entities, for its readers and its deciders
    assert {UUID(str(value)) for value in request["entity_ids"]} == {k04.uk_entity_id, ni}
    assert request["preparer_id"] == una.member.user_id

    # what the preparer reads of it: the header (04 §16.10 "Content of a request") — no summary
    # of the events, no evidence, the entities of her own scope and the count of all — and her
    # submission, through the contract's routes
    own = get(app, f"{APPROVALS}/{request_id}", una)
    assert own.status_code == 200, own.text
    header = own.json()
    assert (header["content_withheld"], header["can_decide"]) == (True, False)
    assert header["summary"] == f"Manual event {request['request_no']}"
    assert (header["subject"]["href"], header["attachments"]) == (None, [])
    assert ([item["code"] for item in header["entities"]], header["entity_count"]) == (
        ["AVM-UK"],
        2,
    )
    read = get(app, f"{SUBMISSIONS}/{submission_id}", una)
    assert (read.status_code, read.json()["status"]) == (200, "SUBMITTED"), read.text

    # the deciders answer for every entity the request names (R-41 (1))
    whole = get(app, f"{APPROVALS}/{request_id}", rosa)
    assert whole.status_code == 200 and whole.json()["content_withheld"] is False, whole.text
    body = {"subject_content_sha256": whole.json()["subject"]["content_sha256"], "comment": "OK"}
    local = post(app, f"{APPROVALS}/{request_id}/approve", ulrich, body)
    assert local.status_code == 403, local.text
    assert local.json()["detail"] == engine.EVERY_ENTITY_DETAIL
    assert str(_request(k04, request_id)["status"]) == "PENDING"

    decided = approve(app, request_id, rosa)
    assert decided.status_code == 200, decided.text
    applied = get(app, f"{SUBMISSIONS}/{submission_id}", una).json()
    assert (applied["status"], len(applied["applied_event_ids"])) == ("APPLIED", 1)
    latest = readers._latest(place, group_id)
    assert str(latest["status"]) == "SUCCEEDED"
    members = place.rows(
        select(contract.c.latest_computation_id).where(contract.c.id.in_([british, other]))
    )
    assert {row["latest_computation_id"] for row in members} == {latest["id"]}


def test_manual_event_preparer_scope_1_the_reason_of_a_rejection_reaches_the_preparer(
    k04: K04World, clock: FrozenClock
) -> None:
    """The preparer of such a request reads its header only, and with it the comment of a
    REJECTION of her own request (item APR-REJECTION-REASON-PREPARER-1, on which this item
    stands: a preparer who is told "rejected" and not why cannot record the event again)."""
    app = k04.app
    british, _other, _group_id = readers._two_entities(k04, readers.NORTHERN)
    una, _ulrich, _nora, rosa, _ni = _people(k04, clock)
    sent = _sent(app, una, british, _progress("0.80", "2026-07-31"))
    assert sent.status_code == 201, sent.text
    request_id = str(sent.json()["approval_request_id"])

    refused = reject(app, request_id, rosa, "The July report is not signed.")

    assert refused.status_code == 200, refused.text
    own = get(app, f"{APPROVALS}/{request_id}", una)
    assert own.status_code == 200, own.text
    shown = own.json()
    assert (shown["status"], shown["content_withheld"]) == ("REJECTED", True)
    comments = [decision["comment"] for step in shown["steps"] for decision in step["decisions"]]
    assert comments == ["The July report is not signed."]
    read = get(app, f"{SUBMISSIONS}/{sent.json()['event_submission_id']}", una)
    assert (read.status_code, read.json()["status"]) == (200, "REJECTED"), read.text


def test_manual_event_preparer_scope_1_an_attribute_change_takes_the_same_rule(
    k04: K04World, clock: FrozenClock
) -> None:
    """``ATTRIBUTE_CHANGE`` stores the same submission and states the same seam: Una's change of
    a revenue account on her contract's line is stored, names both entities and is applied by the
    approval of the reviewer of every entity."""
    place, app = k04.report.place, k04.app
    british, _other, _group_id = readers._two_entities(k04, readers.NORTHERN)
    una, _ulrich, _nora, rosa, ni = _people(k04, clock)
    gl_account(
        app,
        k04.report.maya,
        code="4025",
        name="Revenue - implementation, reclassified",
        account_type="REVENUE",
        normal_balance="C",
    )
    change = {
        "event_type": "LINE_ATTRIBUTES_CHANGED",
        "effective_date": "2026-06-30",
        "obligation_key": "O2",
        "payload": {
            "obligation_key": "O2",
            "changes": {"account_overrides": {"REVENUE": "4025"}},
            "diff": {"account_overrides": {"before": {}, "after": {"REVENUE": "4025"}}},
        },
    }

    sent = _sent(app, una, british, change, evidence=False)

    assert sent.status_code == 201, sent.text
    assert set(sent.json()) == CREATED
    request_id = str(sent.json()["approval_request_id"])
    request = _request(k04, request_id)
    assert (str(request["subject_type"]), str(request["status"])) == ("ATTRIBUTE_CHANGE", "PENDING")
    assert {UUID(str(value)) for value in request["entity_ids"]} == {k04.uk_entity_id, ni}
    decided = approve(app, request_id, rosa)
    assert decided.status_code == 200, decided.text
    (stored,) = place.rows(
        select(event_submission.c.status).where(
            event_submission.c.id == UUID(str(sent.json()["event_submission_id"]))
        )
    )
    assert str(stored["status"]) == "APPLIED"


def test_manual_event_preparer_scope_1_the_contracts_own_entity_is_still_asked(
    k04: K04World, clock: FrozenClock
) -> None:
    """The narrowing is to the contract's OWN entity and no further. Nora, a Revenue Accountant
    of AVM-NI alone, records nothing on the AVM-UK contract of her group — the route asks
    ``event.record`` for the contract's contracting entity, and she does not see that contract —
    and her event on her own entity's contract is stored as Una's is."""
    place, app = k04.report.place, k04.app
    british, other, _group_id = readers._two_entities(k04, readers.NORTHERN)
    _una, _ulrich, nora, _rosa, ni = _people(k04, clock)
    before = len(place.rows(select(event_submission.c.id)))

    refused = _sent(app, nora, british, _progress("0.50", "2026-06-30"))

    assert refused.status_code == 404, refused.text
    assert len(place.rows(select(event_submission.c.id))) == before
    # the control: her own contract, SF-ORD-NI-3001, whose one obligation is O1
    own_event = _progress("0.50", "2026-06-30")
    own_event["payload"]["obligation_key"] = "O1"
    sent = _sent(app, nora, other, own_event)
    assert sent.status_code == 201, sent.text
    request = _request(k04, str(sent.json()["approval_request_id"]))
    assert {UUID(str(value)) for value in request["entity_ids"]} == {k04.uk_entity_id, ni}
    assert request["preparer_id"] == nora.member.user_id
