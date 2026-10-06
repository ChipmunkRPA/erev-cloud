"""Manual event maker-checker (BUILD_SPEC CTR-6; 03 REQ-DAT-014; PRD BR-REC-01, ACT-09, ACT-10; 04
§16.3 "Manual events" and T-CON-24 "Checked again where it is appended", rev 1.194; dev-guide
DG-KRN-EVT-02 rev 1.177; control CTL-009; supervisor ruling R-120 (a)).

A delivery, progress, milestone, cost or return event that a signed-in person records is not
appended: the request waits whole as an event submission until another user holding
``event.approve`` approves it; the approval checks the stored batch again against the stream as
it stands, appends it as SYSTEM for the preparer and computes the group. An API client's events
are appended directly. A usage report is the sixth such type (04 rev 1.238; PRD BR-REC-01 rev
1.166; item EVT-USAGE-MANUAL-1).

Worlds. ``k01``: WLD-K-01 ``SF-ORD-10001`` through 30 Jan 2026 — INV-US-1001 is recorded, O2
(AVM-IMPL-STD, 16,200.00 allocated, WLD-X-01) has no progress yet; Maya (Revenue Accountant)
records, Priya is given Revenue Reviewer for ``event.approve``. ``k11``: WLD-K-11
``NS-SO-DE-5004`` with 120 of the 200 O1 units delivered (80 remaining). ``k08``: WLD-K-08
``SF-ORD-10003``, the usage contract, active since 1 January 2026.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    combination_group,
    contract,
    contract_computation,
    contract_event,
    event_submission,
    exception_item,
    file_attachment,
    subledger_line,
)
from erev_api.domain.contracts import events as contract_events
from erev_api.enums import ContractEventType
from erev_api.events.payloads import (
    CostIncurredV1,
    DeliveryRecordedV1,
    MilestoneAchievedV1,
    ProgressRecordedV1,
    ReturnRecordedV1,
    UsageReportedV1,
)
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.api_clients import access_approver, issued_client
from support.db import TestDatabase
from support.factories import K11World, Workspace, delivered_k11, k11_world
from support.http import HttpResponse, call
from support.principals import Actor, sign_in
from support.principals import workspace as signed_workspace
from support.reference import approve, assign, fields, get, post, reject, slug
from support.worlds import (
    K01,
    K08,
    ReportWorld,
    approved_manual_events,
    evidence_file,
    k01_pellworth,
    k08_ulvane,
    submitted_manual_events,
)

EVENTS = "/api/v1/contracts/{contract_id}/events"
SUBMISSIONS = "/api/v1/event-submissions"
APPROVALS = "/api/v1/approvals"
JANUARY_2026 = "FY2026-P01"
# PRD WLD-X-01: O2 of K-01 is allocated 16,200.00; 40 % of it is January's revenue of O2.
O2_FORTY_PERCENT = Decimal("6480.00")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k01(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 30))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: `event.approve`
    return world


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


@pytest.fixture
def k08(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    world = k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


def _progress(ratio: str = "0.40", day: str = "2026-01-31") -> dict[str, Any]:
    return {
        "event_type": "PROGRESS_RECORDED",
        "effective_date": day,
        "payload": {
            "obligation_key": "O2",
            "cumulative_progress_ratio": ratio,
            "measure": "OUTPUT_PERCENT",
        },
    }


def _delivery(
    quantity: str, *, trigger: str = "DELIVERY", day: str = "2026-09-14"
) -> dict[str, Any]:
    return {
        "event_type": "DELIVERY_RECORDED",
        "effective_date": day,
        "payload": {"obligation_key": "O1", "quantity": quantity, "trigger": trigger},
    }


def _billing(invoice: str, amount: str, currency: str, day: str, key: str) -> dict[str, Any]:
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": day,
        "payload": {
            "invoice_number": invoice,
            "line_external_id": f"{invoice}-1",
            "obligation_key": key,
            "amount": {"amount": amount, "currency": currency},
            "issue_date": day,
        },
    }


def _head(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def _sent(
    place: Workspace,
    actor: Actor,
    contract_id: UUID,
    *items: dict[str, Any],
    evidence: list[str] | None = None,
) -> HttpResponse:
    body: dict[str, Any] = {"events": list(items)}
    if evidence is not None:
        body["evidence_file_ids"] = evidence
    return post(
        place.app,
        EVENTS.format(contract_id=contract_id),
        actor,
        body,
        if_match=f'"s{_head(place, contract_id)}"',
    )


def _stream(place: Workspace, contract_id: UUID) -> list[dict[str, Any]]:
    return place.rows(
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def _request(place: Workspace, request_id: str) -> dict[str, Any]:
    return place.rows(select(approval_request).where(approval_request.c.id == UUID(request_id)))[0]


def _submission(place: Workspace, submission_id: str) -> dict[str, Any]:
    return place.rows(select(event_submission).where(event_submission.c.id == UUID(submission_id)))[
        0
    ]


def _submissions(place: Workspace) -> list[dict[str, Any]]:
    return place.rows(select(event_submission).order_by(event_submission.c.id))


def _dirty(place: Workspace, contract_id: UUID) -> bool:
    group_id = place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    return (
        place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )


def _computations(place: Workspace, contract_id: UUID) -> list[tuple[str, int]]:
    """(status, the contract's head it computed) of the group's computations, oldest first."""
    group_id = place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    rows = place.rows(
        select(contract_computation.c.status, contract_computation.c.stream_heads)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.id)
    )
    return [(str(row["status"]), int(row["stream_heads"][str(contract_id)])) for row in rows]


def _delivered(place: Workspace, contract_id: UUID) -> Decimal:
    """Units delivered by the events the stream holds, voided ones left out."""
    stream = _stream(place, contract_id)
    voided = {row["supersedes_event_id"] for row in stream if row["supersedes_event_id"]}
    return sum(
        (
            Decimal(str(row["payload"]["quantity"]))
            for row in stream
            if str(row["event_type"]) == "DELIVERY_RECORDED" and row["id"] not in voided
        ),
        Decimal(0),
    )


def _revenue(place: Workspace, contract_id: UUID) -> Decimal:
    """Revenue posted for the contract, as a positive figure (credits are stored negative)."""
    total = place.scalar(
        select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0)).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
        )
    )
    return -Decimal(total)


def _k01_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[K01].contract["id"]))


# --- BUILD_SPEC CTR-6: the five tests and CTL-009's ---------------------------------------------


def test_manual_progress_creates_submission(k01: ReportWorld) -> None:
    """A manual progress event creates an event submission and appends nothing (04 §16.3;
    REQ-DAT-014): 201 ``{event_submission_id, approval_request_id}``, the head unmoved, one
    ``MANUAL_EVENT`` request waiting for ``event.approve``, the evidence on the request."""
    place, contract_id = k01.place, _k01_id(k01)
    head, revenue = _head(place, contract_id), _revenue(place, contract_id)
    evidence = evidence_file(k01.app, k01.maya, "progress-report-2026-01.pdf")

    sent = _sent(place, k01.maya, contract_id, _progress(), evidence=[evidence])

    assert sent.status_code == 201, sent.text
    created = sent.json()
    assert set(created) == {"event_submission_id", "approval_request_id"}
    assert sent.headers["Location"] == f"{SUBMISSIONS}/{created['event_submission_id']}"
    # nothing is appended and nothing is posted
    assert _head(place, contract_id) == head
    assert [str(row["event_type"]) for row in _stream(place, contract_id)].count(
        "PROGRESS_RECORDED"
    ) == 0
    assert _revenue(place, contract_id) == revenue
    # the stored batch, as the route validated it
    submission = _submission(place, created["event_submission_id"])
    assert (str(submission["status"]), submission["created_by"]) == (
        "SUBMITTED",
        k01.maya.member.user_id,
    )
    assert [
        (item["event_type"], item["effective_date"], item["obligation_key"])
        for item in submission["events"]
    ] == [("PROGRESS_RECORDED", "2026-01-31", "O2")]
    assert str(submission["approval_request_id"]) == created["approval_request_id"]
    # the request: MANUAL_EVENT, one step for `event.approve` (PRD §2.5), decided by nobody
    request = _request(place, created["approval_request_id"])
    assert (
        str(request["subject_type"]),
        str(request["subject_id"]),
        str(request["status"]),
        request["preparer_id"],
        str(request["summary"]),
    ) == (
        "MANUAL_EVENT",
        created["event_submission_id"],
        "PENDING",
        k01.maya.member.user_id,
        f"Record progress of {K01}",
    )
    steps = place.rows(
        select(approval_step.c.required_permission, approval_step.c.min_approvers).where(
            approval_step.c.approval_request_id == UUID(created["approval_request_id"])
        )
    )
    assert [(str(row["required_permission"]), row["min_approvers"]) for row in steps] == [
        ("event.approve", 1)
    ]
    assert not place.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(created["approval_request_id"])
        )
    )
    # the evidence is the request's attachment: the approver reads it where she decides
    shown = get(k01.app, f"{APPROVALS}/{created['approval_request_id']}", k01.priya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["attachments"] == [
        {"file_id": evidence, "original_filename": "progress-report-2026-01.pdf"}
    ]
    assert shown.json()["can_decide"] is True
    # the command's own audit event names the contract, the types and the request
    (audited,) = place.rows(
        select(
            audit_event.c.actor_id, audit_event.c.after, audit_event.c.approval_request_id
        ).where(audit_event.c.action == "event_submission.submit_manual_events")
    )
    assert audited["actor_id"] == k01.maya.member.user_id
    assert audited["after"] == {
        "contract_id": str(contract_id),
        "event_types": ["PROGRESS_RECORDED"],
        "approval_request_id": created["approval_request_id"],
        "evidence_file_ids": [evidence],
    }
    # the read of the submission (API-R-30)
    read = get(k01.app, f"{SUBMISSIONS}/{created['event_submission_id']}", k01.maya)
    assert (read.status_code, read.json()["status"], read.json()["applied_event_ids"]) == (
        200,
        "SUBMITTED",
        [],
    )


def test_evidence_required_for_manual_events(k01: ReportWorld) -> None:
    """The same request without ``evidence_file_ids`` is refused, 422 ``validation-failed`` with
    ``rule_id`` ``REQ-DAT-014``; so is an evidence id that names no file the preparer may read
    (04 §16.3 ``evidence_file_ids`` rev 1.194). Nothing is stored either way."""
    place, contract_id = k01.place, _k01_id(k01)
    head = _head(place, contract_id)

    for body_evidence in (None, []):
        refused = _sent(place, k01.maya, contract_id, _progress(), evidence=body_evidence)
        assert refused.status_code == 422, refused.text
        assert slug(refused) == "validation-failed"
        assert fields(refused) == [("evidence_file_ids", "REQ-DAT-014")]
        assert refused.json()["errors"][0]["message"] == "Attach at least one evidence file."

    # an id that names no stored file, and a file another member uploaded and the preparer
    # cannot read: both answered alike, at the index of the id
    theirs = evidence_file(k01.app, k01.marcus, "marcus-only.pdf")
    for unreadable in (str(uuid4()), theirs):
        refused = _sent(place, k01.maya, contract_id, _progress(), evidence=[unreadable])
        assert refused.status_code == 422, refused.text
        assert fields(refused) == [("evidence_file_ids[0]", "T-PLT-29")]

    assert _head(place, contract_id) == head
    assert _submissions(place) == []
    assert not place.rows(
        select(approval_request.c.id).where(approval_request.c.subject_type == "MANUAL_EVENT")
    )
    assert not place.rows(
        select(file_attachment.c.id).where(file_attachment.c.subject_type == "approval_request")
    )


def test_approval_appends_as_system_for_preparer(k01: ReportWorld) -> None:
    """Priya approves: the SYSTEM principal appends the event for the preparer — ``is_manual``
    true, its request named, origin SYSTEM, kind SYSTEM with no ``created_by`` (04 SC-C), the
    preparer on the audit event's ``on_behalf_of``, on the request and on the submission — the
    submission becomes APPLIED with ``applied_event_ids`` (T-CON-24), and the approval computes
    the group: O2's revenue of 6,480.00 (40 % of 16,200.00, WLD-X-01) is posted with it."""
    place, contract_id = k01.place, _k01_id(k01)
    head, revenue = _head(place, contract_id), _revenue(place, contract_id)
    lines_before = [
        row["id"]
        for row in place.rows(
            select(subledger_line.c.id).where(subledger_line.c.contract_id == contract_id)
        )
    ]
    created = submitted_manual_events(place, contract_id, _progress())
    assert _head(place, contract_id) == head

    approved = approve(k01.app, created["approval_request_id"], k01.priya)

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    stream = _stream(place, contract_id)
    event = stream[-1]
    assert (
        str(event["event_type"]),
        event["stream_version"],
        str(event["effective_date"]),
        str(event["origin"]),
        event["is_manual"],
        str(event["approval_request_id"]),
        event["created_by"],
        str(event["created_by_kind"]),
    ) == (
        "PROGRESS_RECORDED",
        head + 1,
        "2026-01-31",
        "SYSTEM",
        True,
        created["approval_request_id"],
        None,
        "SYSTEM",
    )
    assert event["payload"]["cumulative_progress_ratio"] == "0.40"
    assert _head(place, contract_id) == head + 1
    # the append's audit fact (AUD-FACT: the ids in the detail): SYSTEM, on behalf of the preparer
    facts = [
        row
        for row in place.rows(
            select(
                audit_event.c.actor_kind, audit_event.c.on_behalf_of_id, audit_event.c.detail
            ).where(audit_event.c.action == "contract_event.append")
        )
        if str(event["id"]) in row["detail"]["ids"]
    ]
    assert [(str(row["actor_kind"]), row["on_behalf_of_id"]) for row in facts] == [
        ("SYSTEM", k01.maya.member.user_id)
    ]
    # the submission: APPLIED with the event's id; the preparer is its creator
    submission = _submission(place, created["event_submission_id"])
    assert (
        str(submission["status"]),
        list(submission["applied_event_ids"]),
        submission["created_by"],
    ) == ("APPLIED", [event["id"]], k01.maya.member.user_id)
    # the request: prepared by Maya, decided by Priya
    request = _request(place, created["approval_request_id"])
    assert (str(request["status"]), request["preparer_id"]) == (
        "APPROVED",
        k01.maya.member.user_id,
    )
    decisions = place.rows(
        select(approval_decision.c.decision, approval_decision.c.approver_id).where(
            approval_decision.c.approval_request_id == UUID(created["approval_request_id"])
        )
    )
    assert [(str(row["decision"]), row["approver_id"]) for row in decisions] == [
        ("APPROVE", k01.priya.member.user_id)
    ]
    # the approval computed the group: the event is in a computation and its revenue is posted
    assert _computations(place, contract_id)[-1] == ("SUCCEEDED", head + 1)
    assert _dirty(place, contract_id) is False
    assert _revenue(place, contract_id) - revenue == O2_FORTY_PERCENT
    posted = place.rows(
        select(subledger_line.c.amount_txn, subledger_line.c.effective_date)
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
            subledger_line.c.id.not_in(lines_before),
        )
        .order_by(subledger_line.c.id)
    )
    assert [(Decimal(row["amount_txn"]), str(row["effective_date"])) for row in posted] == [
        (-O2_FORTY_PERCENT, "2026-01-31")
    ]
    # the event read names the computation that included it, and — in one place — who recorded
    # the event and who approved it, read from its request (API-S-Event ``prepared_by``,
    # ``approved_by``; PRD J-08-AC-3)
    shown = get(k01.app, f"/api/v1/events/{event['id']}", k01.maya)
    assert shown.status_code == 200, shown.text
    read = shown.json()
    assert (read["is_manual"], read["computation"]["status"]) == (True, "SUCCEEDED")
    assert (read["created_by"]["kind"], read["created_by"]["id"]) == ("SYSTEM", None)
    assert (read["prepared_by"]["kind"], read["prepared_by"]["id"]) == (
        "USER",
        str(k01.maya.member.user_id),
    )
    assert (read["approved_by"]["kind"], read["approved_by"]["id"]) == (
        "USER",
        str(k01.priya.member.user_id),
    )
    assert read["prepared_by"]["display_name"] != read["approved_by"]["display_name"]
    # an event no request put in force names neither
    listed = get(k01.app, EVENTS.format(contract_id=contract_id), k01.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    others = [item for item in listed.json()["items"] if item["approval_request_id"] is None]
    assert others and {(item["prepared_by"], item["approved_by"]) for item in others} == {
        (None, None)
    }


def test_withdraw_submission(k01: ReportWorld) -> None:
    """``POST /event-submissions/{id}/withdraw`` by the preparer sets the submission VOIDED and
    withdraws the request; nothing is appended, and the request can no longer be approved."""
    place, contract_id = k01.place, _k01_id(k01)
    head = _head(place, contract_id)
    created = submitted_manual_events(place, contract_id, _progress())
    path = f"{SUBMISSIONS}/{created['event_submission_id']}/withdraw"

    # another holder of `event.record` is not the preparer
    assign(k01.priya.member, "revenue_accountant")
    other = post(k01.app, path, k01.priya, {"comment": "Not mine to withdraw."})
    assert (other.status_code, slug(other)) == (403, "forbidden"), other.text

    withdrawn = post(k01.app, path, k01.maya, {"comment": "Recorded against the wrong date."})

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "VOIDED"
    request = _request(place, created["approval_request_id"])
    assert (str(request["status"]), str(request["void_reason"])) == (
        "WITHDRAWN",
        "WITHDRAWN_BY_PREPARER",
    )
    late = approve(k01.app, created["approval_request_id"], k01.priya)
    assert late.status_code == 409, late.text
    assert _head(place, contract_id) == head
    assert str(_submission(place, created["event_submission_id"])["status"]) == "VOIDED"


def _metering_token(world: K11World | ReportWorld) -> tuple[UUID, str]:
    """API client ``svc-metering`` (PRD §2.5 integrations) with ``event.record`` and its token.
    The client's scopes are an access grant (supervisor ruling R-38 (iii)): Marcus requests
    it, Ada — a second Tenant Admin — approves the grant, and Marcus issues its secret."""
    ada = access_approver(world.app, world.place.clock, world.marcus.member, "ada")
    client = issued_client(
        world.app,
        world.marcus,
        {"name": "svc-metering", "scopes": ["event.record", "contract.read"]},
        approver=ada,
    )
    issued = call(
        world.app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(client["client_id"], client["client_secret"]),
    )
    assert issued.status_code == 200, issued.text
    return UUID(str(client["id"])), str(issued.json()["access_token"])


def test_integrated_source_events_not_manual(k11: K11World) -> None:
    """``DELIVERY_RECORDED`` sent by API client ``svc-metering`` is appended directly with
    ``is_manual`` false (PRD ACT-10): no submission, no approval request, computed at once —
    beside a person's delivery of the same contract, which waits."""
    contract_id = UUID(str(delivered_k11(k11).contract["id"]))
    place = k11.place
    head = _head(place, contract_id)
    client_id, token = _metering_token(k11)

    sent = call(
        k11.app,
        "POST",
        EVENTS.format(contract_id=contract_id),
        json={"events": [_delivery("30")]},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"k-{uuid4()}",
            "If-Match": f'"s{head}"',
        },
    )

    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert set(body) >= {"contract", "events", "computation"}
    (appended,) = body["events"]
    assert (appended["event_type"], appended["is_manual"], appended["origin"]) == (
        "DELIVERY_RECORDED",
        False,
        "API",
    )
    assert body["computation"]["status"] == "SUCCEEDED"
    stored = _stream(place, contract_id)[-1]
    assert (
        stored["created_by"],
        str(stored["created_by_kind"]),
        stored["approval_request_id"],
    ) == (
        client_id,
        "API_CLIENT",
        None,
    )
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 1, Decimal(150))
    assert _submissions(place) == []
    assert not place.rows(
        select(approval_request.c.id).where(approval_request.c.subject_type == "MANUAL_EVENT")
    )
    # the positive control of the rule: the same event from a signed-in person waits
    waiting = _sent(place, place.author, contract_id, _delivery("30"))
    assert waiting.status_code == 201, waiting.text
    assert set(waiting.json()) == {"event_submission_id", "approval_request_id"}
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 1, Decimal(150))


def _usage(calls: str, rated: str, start: str, end: str) -> dict[str, Any]:
    return {
        "event_type": "USAGE_REPORTED",
        "effective_date": end,
        "payload": {
            "obligation_key": "O1",
            "usage_period_start": start,
            "usage_period_end": end,
            "metric": "API_CALL",
            "quantity": calls,
            "rated_amount": {"amount": rated, "currency": "USD"},
        },
    }


def test_evt_usage_manual_1_usage_reported_by_a_person_waits_for_approval(k08: ReportWorld) -> None:
    """04 §16.3 "Manual events", rev 1.238 (item EVT-USAGE-MANUAL-1; PRD BR-REC-01 rev 1.166): a
    usage report entered by a signed-in person is a manual event. It waits whole for another
    user's approval, without evidence, and posts its revenue when it is approved; the metering
    client's report is appended at once, as before (PRD J-11, ACT-10).

    Measured before the rule: Maya alone reported 50,000 calls rated 5,000.00 on K-08 and two
    lines posted the 5,000.00 with the append — no request, no second person."""
    place, maya = k08.place, k08.maya
    contract_id = UUID(str(k08.contracts[K08].contract["id"]))
    head, revenue = _head(place, contract_id), _revenue(place, contract_id)

    sent = _sent(place, maya, contract_id, _usage("50000", "5000.00", "2026-09-01", "2026-09-10"))

    assert sent.status_code == 201, sent.text
    created = sent.json()
    # the keys first: without the rule the answer is an append's (contract, events, computation)
    assert set(created) == {"event_submission_id", "approval_request_id"}
    assert (_head(place, contract_id), _revenue(place, contract_id)) == (head, revenue)
    submission = _submission(place, created["event_submission_id"])
    assert [
        (item["event_type"], item["effective_date"], item["obligation_key"])
        for item in submission["events"]
    ] == [("USAGE_REPORTED", "2026-09-10", "O1")]
    request = _request(place, created["approval_request_id"])
    assert (str(request["subject_type"]), str(request["status"]), str(request["summary"])) == (
        "MANUAL_EVENT",
        "PENDING",
        f"Record usage of {K08}",
    )
    # evidence is offered, not required: the request carries none
    assert not place.rows(
        select(file_attachment.c.id).where(
            file_attachment.c.subject_id == UUID(created["approval_request_id"])
        )
    )

    approved = approve(k08.app, created["approval_request_id"], k08.priya)

    assert approved.status_code == 200, approved.text
    stored = _stream(place, contract_id)[-1]
    assert (
        str(stored["event_type"]),
        stored["is_manual"],
        str(stored["origin"]),
        str(stored["approval_request_id"]),
    ) == ("USAGE_REPORTED", True, "SYSTEM", created["approval_request_id"])
    assert _head(place, contract_id) == head + 1
    assert _revenue(place, contract_id) == revenue + Decimal("5000.00")
    assert _computations(place, contract_id)[-1] == ("SUCCEEDED", head + 1)

    # the metering client's report is appended and computed at once (PRD J-11; ACT-10)
    client_id, token = _metering_token(k08)
    direct = call(
        k08.app,
        "POST",
        EVENTS.format(contract_id=contract_id),
        json={"events": [_usage("20000", "2000.00", "2026-09-11", "2026-09-12")]},
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"k-{uuid4()}",
            "If-Match": f'"s{head + 1}"',
        },
    )
    assert direct.status_code == 201, direct.text
    (appended,) = direct.json()["events"]
    assert (appended["event_type"], appended["is_manual"], appended["origin"]) == (
        "USAGE_REPORTED",
        False,
        "API",
    )
    assert direct.json()["computation"]["status"] == "SUCCEEDED"
    assert _stream(place, contract_id)[-1]["created_by"] == client_id
    assert _head(place, contract_id) == head + 2
    assert _revenue(place, contract_id) == revenue + Decimal("7000.00")
    assert len(_submissions(place)) == 1


@pytest.mark.control("CTL-009")
def test_ctl_009_preparer_cannot_approve_manual_event(k01: ReportWorld) -> None:
    """CTL-009: Maya deciding her own submission is refused, 403 ``self-approval``, and no event
    is appended. She holds ``event.approve`` herself here and is MFA-verified, so that no other
    refusal precedes the one under test; Priya then approves the same request."""
    place, contract_id = k01.place, _k01_id(k01)
    assign(k01.maya.member, "revenue_reviewer")
    maya = signed_workspace(k01.app, k01.maya.member, sign_in(k01.app, k01.maya.member.email))
    head = _head(place, contract_id)
    evidence = evidence_file(k01.app, maya)
    sent = _sent(place, maya, contract_id, _progress(), evidence=[evidence])
    assert sent.status_code == 201, sent.text
    request_id = sent.json()["approval_request_id"]

    own = approve(k01.app, request_id, maya)

    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert _head(place, contract_id) == head
    assert str(_request(place, request_id)["status"]) == "PENDING"
    assert str(_submission(place, sent.json()["event_submission_id"])["status"]) == "SUBMITTED"
    shown = get(k01.app, f"{APPROVALS}/{request_id}", maya)
    assert shown.json()["can_decide"] is False
    # the positive control: another holder of `event.approve` decides it
    other = approve(k01.app, request_id, k01.priya)
    assert other.status_code == 200, other.text
    assert _head(place, contract_id) == head + 1


# --- which requests wait, and what they need ------------------------------------------------------


def test_ctr_6_evidence_is_asked_of_progress_milestone_cost_and_acceptance() -> None:
    """04 §16.3 ``evidence_file_ids`` (rev 1.194; SCREENS §4.9.3): evidence is required for a
    progress, a milestone and a cost event and for a delivery whose trigger is acceptance; a
    delivery on another trigger, a return and — since rev 1.238 — a usage report take the
    approval without it. The six types are the ones E-03 gives the ``MANUAL_EVENT`` approval
    "when manual"."""
    day = date(2026, 9, 14)

    def event(event_type: ContractEventType, payload: Any) -> EventIn:
        return EventIn(event_type=event_type, effective_date=day, payload=payload)

    delivery = ContractEventType.DELIVERY_RECORDED
    needs = {
        "progress": event(
            ContractEventType.PROGRESS_RECORDED,
            ProgressRecordedV1(
                obligation_key="O2", cumulative_progress_ratio="0.4", measure="OUTPUT_PERCENT"
            ),
        ),
        "milestone": event(
            ContractEventType.MILESTONE_ACHIEVED,
            MilestoneAchievedV1(
                obligation_key="O1", milestone_code="DESIGN-SIGNOFF", cumulative_weight="1"
            ),
        ),
        "cost": event(
            ContractEventType.COST_INCURRED,
            CostIncurredV1(
                purpose="COST_TO_OBTAIN",
                amount={"amount": "6480.00", "currency": "USD"},
                payee="Sales rep 12",
                plan_code="SALES-2026",
                is_incremental=True,
            ),
        ),
        "acceptance": event(
            delivery, DeliveryRecordedV1(obligation_key="O1", quantity="1", trigger="ACCEPTANCE")
        ),
    }
    spared = {
        "delivery": event(
            delivery, DeliveryRecordedV1(obligation_key="O1", quantity="1", trigger="DELIVERY")
        ),
        "return": event(
            ContractEventType.RETURN_RECORDED,
            ReturnRecordedV1(obligation_key="O1", quantity="1", reason="RMA-1 Resaleable"),
        ),
        "usage": event(
            ContractEventType.USAGE_REPORTED,
            UsageReportedV1(
                obligation_key="O1",
                usage_period_start=date(2026, 9, 1),
                usage_period_end=date(2026, 9, 10),
                metric="API_CALL",
                quantity="50000",
                rated_amount={"amount": "5000.00", "currency": "USD"},
            ),
        ),
    }
    assert {
        name: contract_events._needs_evidence(item) for name, item in needs.items()
    } == dict.fromkeys(needs, True)
    assert {
        name: contract_events._needs_evidence(item) for name, item in spared.items()
    } == dict.fromkeys(spared, False)
    assert {item.event_type for item in (*needs.values(), *spared.values())} == set(
        contract_events.MANUAL_TYPES
    )


def test_ctr_6_a_delivery_waits_whole_with_what_was_sent_beside_it(k11: K11World) -> None:
    """A person's request is stored whole (04 §16.3 "Manual events" (1)): a billing sent beside
    a delivery waits with it, and the approval appends both in the order sent and computes. A
    delivery on trigger DELIVERY needs no evidence, one on ACCEPTANCE does; a Step 1 event in
    such a request is refused by name. A person's request without a manual event — a billing
    alone — is appended directly, as before."""
    contract_id = UUID(str(delivered_k11(k11).contract["id"]))
    place, maya = k11.place, k11.place.author
    head = _head(place, contract_id)

    # the positive control: a billing alone is appended and computed at once, as a person's event
    billed = _sent(
        place, maya, contract_id, _billing("INV-DE-5004", "100.00", "EUR", "2026-09-13", "O1")
    )
    assert billed.status_code == 201, billed.text
    assert [
        (item["event_type"], item["is_manual"], item["origin"]) for item in billed.json()["events"]
    ] == [("BILLING_RECORDED", True, "UI")]
    assert _head(place, contract_id) == head + 1

    # acceptance asks for evidence; nothing is stored
    refused = _sent(place, maya, contract_id, _delivery("10", trigger="ACCEPTANCE"))
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("evidence_file_ids", "REQ-DAT-014")]
    # a Step 1 event does not ride in a submission (ruling R-77 (9))
    riding = _sent(
        place,
        maya,
        contract_id,
        _delivery("10"),
        {
            "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
            "effective_date": "2026-09-14",
            "payload": {"description": "The customer's credit standing changed."},
        },
    )
    assert riding.status_code == 422, riding.text
    assert fields(riding) == [("events.1.event_type", "API-R-30")]
    assert _submissions(place) == []

    # a delivery on trigger DELIVERY and the billing beside it: one submission, no evidence asked
    sent = _sent(
        place,
        maya,
        contract_id,
        _delivery("50"),
        _billing("INV-DE-5005", "22500.00", "EUR", "2026-09-14", "O1"),
    )
    assert sent.status_code == 201, sent.text
    created = sent.json()
    assert set(created) == {"event_submission_id", "approval_request_id"}
    assert _head(place, contract_id) == head + 1
    request = _request(place, created["approval_request_id"])
    assert (str(request["subject_type"]), str(request["summary"])) == (
        "MANUAL_EVENT",
        "Record delivery of NS-SO-DE-5004 (2 events)",
    )
    assert [
        item["event_type"] for item in _submission(place, created["event_submission_id"])["events"]
    ] == ["DELIVERY_RECORDED", "BILLING_RECORDED"]

    approved = approve(k11.app, created["approval_request_id"], k11.priya)

    assert approved.status_code == 200, approved.text
    last = _stream(place, contract_id)[-2:]
    assert [
        (str(row["event_type"]), row["stream_version"], row["is_manual"], str(row["origin"]))
        for row in last
    ] == [
        ("DELIVERY_RECORDED", head + 2, True, "SYSTEM"),
        ("BILLING_RECORDED", head + 3, True, "SYSTEM"),
    ]
    assert {str(row["approval_request_id"]) for row in last} == {created["approval_request_id"]}
    assert _delivered(place, contract_id) == Decimal(170)
    assert _computations(place, contract_id)[-1] == ("SUCCEEDED", head + 3)
    assert _dirty(place, contract_id) is False


def test_ctr_6_a_rejected_submission_appends_nothing(k01: ReportWorld) -> None:
    """A rejection closes the submission ``REJECTED`` (T-CON-24) and appends nothing."""
    place, contract_id = k01.place, _k01_id(k01)
    head = _head(place, contract_id)
    created = submitted_manual_events(place, contract_id, _progress())

    rejected = reject(k01.app, created["approval_request_id"], k01.priya, "The report is unsigned.")

    assert rejected.status_code == 200, rejected.text
    assert str(_submission(place, created["event_submission_id"])["status"]) == "REJECTED"
    assert str(_request(place, created["approval_request_id"])["status"]) == "REJECTED"
    assert _head(place, contract_id) == head


# --- checked again where it is appended (04 T-CON-24 rev 1.194) -----------------------------------


def test_ctr_6_a_stored_batch_is_checked_again_where_it_is_appended(k11: K11World) -> None:
    """04 T-CON-24 "Checked again where it is appended": two requests of 60 units are stored
    while 80 remain — each within the bound alone. The first approval appends and computes; the
    second finds the bound broken on the stream as it stands and voids its request as stale
    (409 ``stale-approval``, ``STALE_SUBJECT``); 180 of 200 are delivered, the computations
    succeed and no exception item is raised.

    Before the check both were approved: 240 of 200 delivered, the computation QUARANTINED with
    ``PROGRESS_OVER_DELIVERY`` and a BLOCKING item — control CTL-008 by-passed through the
    approval (measured on main 965ed2bd through the attribute-change request)."""
    contract_id = UUID(str(delivered_k11(k11).contract["id"]))
    place = k11.place
    head = _head(place, contract_id)
    first = submitted_manual_events(place, contract_id, _delivery("60"), evidence_file_ids=[])
    second = submitted_manual_events(place, contract_id, _delivery("60"), evidence_file_ids=[])
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head, Decimal(120))

    approved = approve(k11.app, first["approval_request_id"], k11.priya)
    assert approved.status_code == 200, approved.text
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 1, Decimal(180))

    stale = approve(k11.app, second["approval_request_id"], k11.priya)

    # the status first: without the check this approval answers 200 and 240 of 200 are delivered
    assert stale.status_code == 409, stale.text
    assert slug(stale) == "stale-approval"
    request = _request(place, second["approval_request_id"])
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert str(_submission(place, second["event_submission_id"])["status"]) == "VOIDED"
    assert not place.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(second["approval_request_id"])
        )
    )
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 1, Decimal(180))
    assert {status for status, _ in _computations(place, contract_id)} == {"SUCCEEDED"}
    assert _dirty(place, contract_id) is False
    assert place.rows(select(exception_item.c.code)) == []
    # the preparer records it again and meets the finding by name (PRD IMP-22)
    again = _sent(place, place.author, contract_id, _delivery("60"))
    assert again.status_code == 422, again.text
    assert fields(again) == [("events.0.payload.quantity", "PROGRESS_OVER_DELIVERY")]
    # the positive control: what still fits is stored and approved
    fits = approved_manual_events(
        place, k11.priya, contract_id, _delivery("20"), evidence_file_ids=[]
    )
    assert fits["computation"]["status"] == "SUCCEEDED"
    assert _delivered(place, contract_id) == Decimal(200)


def test_ctr_6_a_second_void_of_one_event_is_stale_and_a_void_is_posted_at_its_approval(
    k11: K11World,
) -> None:
    """The void request is an event submission too: two requests to void one delivery are both
    stored; the first approval appends ``EVENT_VOIDED`` and computes — the group is not left
    marked for the next command — and the second is stale, so the stream never holds two voids
    of one event."""
    contract_id = UUID(str(delivered_k11(k11).contract["id"]))
    place, maya = k11.place, k11.place.author
    recorded = approved_manual_events(
        place, k11.priya, contract_id, _delivery("30"), evidence_file_ids=[]
    )
    target = recorded["events"][0]["id"]
    assert _delivered(place, contract_id) == Decimal(150)
    head = _head(place, contract_id)
    body = {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded against the wrong order."}
    requests = [
        post(k11.app, f"/api/v1/events/{target}/request-void", maya, body) for _ in range(2)
    ]
    assert [response.status_code for response in requests] == [201, 201]

    approved = approve(k11.app, requests[0].json()["approval_request_id"], k11.priya)

    assert approved.status_code == 200, approved.text
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 1, Decimal(120))
    assert _computations(place, contract_id)[-1] == ("SUCCEEDED", head + 1)
    assert _dirty(place, contract_id) is False
    stale = approve(k11.app, requests[1].json()["approval_request_id"], k11.priya)
    assert stale.status_code == 409, stale.text  # without the check: a second void of the event
    assert slug(stale) == "stale-approval"
    assert _head(place, contract_id) == head + 1
    assert [
        str(row["event_type"]) for row in _stream(place, contract_id) if row["supersedes_event_id"]
    ] == ["EVENT_VOIDED"]


def test_ctr_6_the_attribute_change_request_takes_the_same_rules(k11: K11World) -> None:
    """``ATTRIBUTE_CHANGE`` and ``MANUAL_EVENT`` share one lifecycle (dev-guide DG-KRN-EVT-02 rev
    1.177). The road on which the defect was measured: two attribute-change requests that each
    carry a delivery of 60 units, 80 remaining — the first is applied and computed, the second is
    stale. And the evidence rule holds for the manual events such a request carries."""
    contract_id = UUID(str(delivered_k11(k11).contract["id"]))
    place, maya = k11.place, k11.place.author
    head = _head(place, contract_id)
    change = {
        "event_type": "LINE_ATTRIBUTES_CHANGED",
        "effective_date": "2026-09-14",
        "obligation_key": "O1",
        "payload": {
            "obligation_key": "O1",
            "changes": {"account_overrides": {"REVENUE": "4000"}},
            "diff": {"account_overrides": {"before": {}, "after": {"REVENUE": "4000"}}},
        },
    }

    refused = _sent(place, maya, contract_id, change, _delivery("10", trigger="ACCEPTANCE"))
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("evidence_file_ids", "REQ-DAT-014")]
    assert _submissions(place) == []

    requests = [_sent(place, maya, contract_id, change, _delivery("60")) for _ in range(2)]
    assert [response.status_code for response in requests] == [201, 201]
    first, second = (response.json() for response in requests)
    assert str(_request(place, first["approval_request_id"])["subject_type"]) == "ATTRIBUTE_CHANGE"

    approved = approve(k11.app, first["approval_request_id"], k11.priya)
    assert approved.status_code == 200, approved.text
    stale = approve(k11.app, second["approval_request_id"], k11.priya)

    assert stale.status_code == 409, stale.text  # the measured defect: 200, and 240 of 200
    assert slug(stale) == "stale-approval"
    assert (_head(place, contract_id), _delivered(place, contract_id)) == (head + 2, Decimal(180))
    assert {status for status, _ in _computations(place, contract_id)} == {"SUCCEEDED"}
    assert place.rows(select(exception_item.c.code)) == []
    assert str(_submission(place, second["event_submission_id"])["status"]) == "VOIDED"
