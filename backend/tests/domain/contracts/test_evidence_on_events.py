"""The evidence of recorded events (item EVT-EVIDENCE-1; the supervisor's rulings of 2026-10-02;
04 §16.3 "Manual events", T-CON-24, T-PLT-29 and T-PLT-30, rev 1.268; dev-guide DG-KRN-EVT-02 rev
1.253; 03 REQ-DAT-014; BUILD_SPEC CTR-6; controls CTL-009, CTL-046).

A person's manual event is a request (BUILD_SPEC CTR-6), and the evidence REQ-DAT-014 asks for is
attached to the request, where its approver reads it. Measured before this item, in WLD-K-01:
after the approval the Controller, the Auditor and a second Revenue Accountant read the appended
event and were answered 404 for the file that supported it — only the preparer, the decider and a
holder of ``event.approve`` opened it; ``file.shred`` took the evidence of a pending and of an
applied request from one administrator; the approval counted an attachment whose file had been
destroyed; and the evidence sent with a direct append was attached to nothing.

Three rules and one consequence:

1. the evidence of a submission that is submitted, approved or applied is HELD — shredded only
   through an approved request (``platform.file_evidence``);
2. the approval counts evidence that can still be read, under the files' locks: a shredded file
   makes the pending request stale, and an event that needs evidence with none left is refused
   while the request stays pending;
3. after the approval every appended event carries every readable file of the request (T-PLT-30
   subject ``contract_event``), written by the SYSTEM principal for the preparer, so the readers
   of the event on its contract open it;
4. a direct append attaches the files its caller sent to the events it appends, as the caller,
   and a live attachment of a contract event holds its file, whichever road wrote it.

World: WLD-K-01 through 30 January 2026 (``test_manual_events.k01``). Maya (Revenue Accountant)
prepares; Priya (Revenue Reviewer) decides; Marcus is the Controller; Ava an Auditor; Lena a second
Revenue Accountant; Tess a Tenant Admin, who shreds. DB-bound.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import test_manual_events as manual
from erev_api.clock import FrozenClock
from erev_api.db.tables import approval_request, audit_event, event_submission, file_attachment
from erev_api.domain.platform import file_evidence
from fastapi import FastAPI
from sqlalchemy import select
from support import upload_fixtures
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, sign_in, workspace
from support.reference import approve, assign, fields, get, post, reject, slug
from support.shred_in_flight import beside_a_shred
from support.worlds import ReportWorld

app = manual.app
files = manual.files
k01 = manual.k01

ATTACHMENTS = "/api/v1/attachments"
FILES = "/api/v1/files"
SHRED_REASON = "DSR-2026-0917: erase the person's data in this document"
CONTRACT = "SF-ORD-10001"
EVENT_RECORD = f"the evidence of an event recorded on contract {CONTRACT}"
GONE = (
    "This request no longer has an evidence file attached. Reject it, or ask the preparer to "
    "attach a file to it or withdraw it."
)


def _request_record(request_no: str) -> str:
    return (
        f"the evidence of approval request {request_no}, whose events wait for approval or are "
        "recorded"
    )


def _file(app: FastAPI, actor: Actor, name: str, *, purpose: str = "ATTACHMENT") -> str:
    """A stored file of its own bytes (identical bytes are ONE stored file); its id."""
    content = upload_fixtures.PDF + f"% {name}\n".encode()
    stored = call(
        app,
        "POST",
        FILES,
        data={"purpose": purpose},
        files={"file": (name, content, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stored.status_code == 201, stored.text
    return str(stored.json()["id"])


def _member(world: ReportWorld, key: str, role: str) -> Actor:
    someone = colleague(world.tenant_id, key)
    assign(someone, role)
    return workspace(world.app, someone, sign_in(world.app, someone.email))


def _others(world: ReportWorld) -> dict[str, Actor]:
    """The readers of the contract who neither prepared nor decide the request."""
    return {
        "the Controller": world.marcus,
        "the Auditor": _member(world, "ava", "auditor"),
        "a second Revenue Accountant": _member(world, "lena", "revenue_accountant"),
    }


def _admin(world: ReportWorld, clock: FrozenClock) -> Actor:
    someone = colleague(world.tenant_id, "tess")
    assign(someone, "tenant_admin")
    return enrolled(world.app, clock, someone)


def _listed(app: FastAPI, actor: Actor, subject_type: str, subject_id: Any) -> list[str]:
    """The files of the subject's attachments as ``actor`` lists them."""
    shown = get(app, ATTACHMENTS, actor, {"subject_type": subject_type, "subject_id": subject_id})
    assert shown.status_code == 200, shown.text
    return [str(item["file_object_id"]) for item in shown.json()["items"]]


def _opens(app: FastAPI, actor: Actor, file_id: str) -> tuple[int, int]:
    """(the file's metadata, its content) as ``actor`` is answered."""
    return (
        get(app, f"{FILES}/{file_id}", actor).status_code,
        get(app, f"{FILES}/{file_id}/content", actor).status_code,
    )


def _waiting(k01: ReportWorld, *events: dict[str, Any], evidence: list[str]) -> dict[str, str]:
    """Maya's request with its evidence: ``{event_submission_id, approval_request_id}``."""
    sent = manual._sent(k01.place, k01.maya, manual._k01_id(k01), *events, evidence=evidence)
    assert sent.status_code == 201, sent.text
    assert set(sent.json()) == {"event_submission_id", "approval_request_id"}
    return {key: str(value) for key, value in sent.json().items()}


def _applied(k01: ReportWorld, created: dict[str, str]) -> list[str]:
    shown = get(k01.app, f"{manual.SUBMISSIONS}/{created['event_submission_id']}", k01.maya)
    assert shown.status_code == 200, shown.text
    return [str(value) for value in shown.json()["applied_event_ids"] or ()]


def _status(k01: ReportWorld, created: dict[str, str]) -> tuple[str, str]:
    """(the request's status, the submission's)."""
    place = k01.place
    (request,) = place.rows(
        select(approval_request.c.status).where(
            approval_request.c.id == UUID(created["approval_request_id"])
        )
    )
    (stored,) = place.rows(
        select(event_submission.c.status).where(
            event_submission.c.id == UUID(created["event_submission_id"])
        )
    )
    return str(request["status"]), str(stored["status"])


def _request_no(k01: ReportWorld, created: dict[str, str]) -> str:
    (row,) = k01.place.rows(
        select(approval_request.c.request_no).where(
            approval_request.c.id == UUID(created["approval_request_id"])
        )
    )
    return str(row["request_no"])


def _holds(k01: ReportWorld, file_id: str) -> list[str]:
    return [hold.record for hold in file_evidence.holds(k01.tenant_id, UUID(file_id))]


def _shred(app: FastAPI, admin: Actor, file_id: str) -> HttpResponse:
    return post(app, f"{FILES}/{file_id}/shred", admin, {"reason": SHRED_REASON})


def _approval_required(refused: HttpResponse, record: str) -> None:
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    (error,) = refused.json()["errors"]
    assert (error["rule_id"], error["message"]) == (
        "FILE_SHRED_APPROVAL_REQUIRED",
        file_evidence.APPROVAL_MESSAGE.format(record=record),
    )


def test_evt_evidence_1_the_readers_of_an_event_open_its_evidence_after_the_approval(
    k01: ReportWorld,
) -> None:
    """While the request waits its evidence is the request's: the Controller, the Auditor and a
    second accountant read neither the request nor the file. The approval attaches the file to
    the appended event, and whoever reads the event on its contract lists it there and opens it.
    The attachment is the SYSTEM principal's, written for the preparer: no person voids it."""
    app, place = k01.app, k01.place
    others = _others(k01)
    evidence = _file(app, k01.maya, "progress-report-2026-01.pdf")
    created = _waiting(k01, manual._progress(), evidence=[evidence])
    request_id = created["approval_request_id"]

    # pending: the request's readers alone
    assert _listed(app, k01.priya, "approval_request", request_id) == [evidence]
    assert _opens(app, k01.priya, evidence) == (200, 200)
    for name, actor in others.items():
        assert get(app, f"{manual.APPROVALS}/{request_id}", actor).status_code == 404, name
        assert _opens(app, actor, evidence) == (404, 404), name

    decided = approve(app, request_id, k01.priya)
    assert decided.status_code == 200, decided.text
    (event_id,) = _applied(k01, created)

    # the status first: before the rule the event carried nothing and the three were answered 404
    readers = {"the preparer": k01.maya, "the decider": k01.priya, **others}
    for name, actor in readers.items():
        assert get(app, f"/api/v1/events/{event_id}", actor).status_code == 200, name
        assert _listed(app, actor, "contract_event", event_id) == [evidence], name
        assert _opens(app, actor, evidence) == (200, 200), name
    # the request keeps its own attachment, for its readers
    assert _listed(app, k01.priya, "approval_request", request_id) == [evidence]

    (attached,) = place.rows(
        select(file_attachment).where(
            file_attachment.c.subject_type == "contract_event",
            file_attachment.c.subject_id == UUID(event_id),
        )
    )
    assert (attached["created_by"], str(attached["created_by_kind"])) == (None, "SYSTEM")
    assert attached["voided_at"] is None
    (written,) = [
        row
        for row in place.rows(
            select(audit_event).where(audit_event.c.action == "file_attachment.create")
        )
        if str(row["actor_kind"]) == "SYSTEM"
    ]
    assert written["on_behalf_of_id"] == k01.maya.member.user_id  # it names the preparer
    assert written["detail"] == {
        "file_object_id": evidence,
        "subject_type": "contract_event",
        "approval_request_id": request_id,
        "contract_id": str(manual._k01_id(k01)),
        "ids": [str(attached["id"])],
    }
    # an attachment is voided by its uploader alone: this one has none
    for actor in (k01.maya, k01.priya, k01.marcus):
        voided = post(
            app, f"{ATTACHMENTS}/{attached['id']}/void", actor, {"reason": "Attached in error."}
        )
        assert voided.status_code == 404, voided.text


def test_evt_evidence_1_every_event_of_the_batch_carries_every_file(k01: ReportWorld) -> None:
    """The evidence was sent with the request, so every event the request appends carries every
    file — the invoice recorded beside the progress as the progress itself; files times events."""
    app = k01.app
    report = _file(app, k01.maya, "progress-report-2026-01.pdf")
    invoice = _file(app, k01.maya, "invoice-copy-INV-US-9001.pdf")
    created = _waiting(
        k01,
        manual._progress(),
        manual._billing("INV-US-9001", "100.00", "USD", "2026-01-30", "O1"),
        evidence=[report, invoice, report],  # a file named twice is attached once
    )

    assert approve(app, created["approval_request_id"], k01.priya).status_code == 200

    applied = _applied(k01, created)
    assert len(applied) == 2
    for event_id in applied:
        assert sorted(_listed(app, k01.marcus, "contract_event", event_id)) == sorted(
            [report, invoice]
        )
    rows = k01.place.rows(
        select(file_attachment.c.id).where(file_attachment.c.subject_type == "contract_event")
    )
    assert len(rows) == 4


def test_evt_evidence_1_a_rejected_and_a_withdrawn_submission_keep_their_evidence_to_the_request(
    k01: ReportWorld, clock: FrozenClock
) -> None:
    """A rejected or withdrawn submission appends no event: its evidence stays the request's
    alone, is read by the request's readers as before, and is no longer held — one administrator
    shreds it, as the document of a rejected adjustment."""
    app, place = k01.app, k01.place
    tess = _admin(k01, clock)
    outsider = _member(k01, "ava", "auditor")
    rejected_file = _file(app, k01.maya, "progress-report-rejected.pdf")
    rejected = _waiting(k01, manual._progress("0.60", "2026-01-31"), evidence=[rejected_file])
    assert _holds(k01, rejected_file) == [_request_record(_request_no(k01, rejected))]
    refused = reject(app, rejected["approval_request_id"], k01.priya, "Not supported.")
    assert refused.status_code == 200, refused.text

    withdrawn_file = _file(app, k01.maya, "progress-report-withdrawn.pdf")
    withdrawn = _waiting(k01, manual._progress("0.70", "2026-01-31"), evidence=[withdrawn_file])
    gone = post(
        app,
        f"{manual.SUBMISSIONS}/{withdrawn['event_submission_id']}/withdraw",
        k01.maya,
        {"comment": "Sent in error."},
    )
    assert gone.status_code == 200, gone.text

    assert _status(k01, rejected) == ("REJECTED", "REJECTED")
    assert _status(k01, withdrawn)[1] != "SUBMITTED"
    assert (
        place.rows(
            select(file_attachment.c.id).where(file_attachment.c.subject_type == "contract_event")
        )
        == []
    )
    for file_id in (rejected_file, withdrawn_file):
        assert _opens(app, k01.maya, file_id) == (200, 200)
        assert _opens(app, outsider, file_id) == (404, 404)
        assert _holds(k01, file_id) == []
        erased = _shred(app, tess, file_id)
        assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text


def test_evt_evidence_1_the_evidence_of_a_pending_and_of_an_applied_submission_is_held(
    k01: ReportWorld, clock: FrozenClock
) -> None:
    """One administrator does not shred the evidence of a request that waits, nor of one that was
    applied: ``file.shred`` names the record and the approved path. Once applied, the request and
    the event both rest on the file."""
    app = k01.app
    tess = _admin(k01, clock)
    evidence = _file(app, k01.maya, "progress-report-2026-01.pdf")
    created = _waiting(k01, manual._progress(), evidence=[evidence])
    of_request = _request_record(_request_no(k01, created))

    # the status first: before the rule the shred answered 200 and the file was gone
    _approval_required(_shred(app, tess, evidence), of_request)
    assert _holds(k01, evidence) == [of_request]

    assert approve(app, created["approval_request_id"], k01.priya).status_code == 200
    _approval_required(_shred(app, tess, evidence), of_request)
    assert _holds(k01, evidence) == [of_request, EVENT_RECORD]
    assert _opens(app, k01.marcus, evidence) == (200, 200)


def test_evt_evidence_1_an_approved_shred_makes_the_pending_request_stale(
    k01: ReportWorld, clock: FrozenClock
) -> None:
    """Only an approved ``EVIDENCE_SHRED`` request erases the evidence of a request that waits.
    Its proposal names that pending request, so the Controller sees what the shred stops; and
    once the file is shredded the decision of the pending request is refused as stale — the
    request is voided, nothing is appended, and the preparer records the event again with
    evidence that can be read."""
    app, place = k01.app, k01.place
    contract_id = manual._k01_id(k01)
    tess = _admin(k01, clock)
    evidence = _file(app, k01.maya, "progress-report-2026-01.pdf")
    created = _waiting(k01, manual._progress(), evidence=[evidence])
    request_no = _request_no(k01, created)
    head = manual._head(place, contract_id)

    asked = post(app, f"{FILES}/{evidence}/request-shred", tess, {"reason": SHRED_REASON})
    assert asked.status_code == 200, asked.text
    shred_request = get(
        app, f"{manual.APPROVALS}/{asked.json()['approval_request_id']}", k01.marcus
    )
    assert shred_request.status_code == 200, shred_request.text
    preview = get(
        app, f"{FILES}/{shred_request.json()['impact_preview']['file_id']}/content", k01.marcus
    )
    assert preview.status_code == 200, preview.text
    named = preview.json()["after"].get("pending_requests")
    shredded = approve(app, asked.json()["approval_request_id"], k01.marcus)
    assert shredded.status_code == 200, shredded.text

    decided = approve(app, created["approval_request_id"], k01.priya)

    assert {
        "the proposal names": named,
        "the pending request's decision": (decided.status_code, slug(decided)),
    } == {
        "the proposal names": [
            {
                "request_no": request_no,
                "subject_type": "MANUAL_EVENT",
                "record": _request_record(request_no),
            }
        ],
        "the pending request's decision": (409, "stale-approval"),
    }
    (voided,) = place.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(created["approval_request_id"])
        )
    )
    assert (str(voided["status"]), str(voided["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert _status(k01, created)[1] == "VOIDED"
    assert manual._head(place, contract_id) == head  # nothing appended
    # the way on: the same event, with evidence that can be read
    again = _waiting(
        k01, manual._progress(), evidence=[_file(app, k01.maya, "progress-report-signed.pdf")]
    )
    assert approve(app, again["approval_request_id"], k01.priya).status_code == 200


def test_evt_evidence_1_the_approval_waits_for_a_shred_in_flight(
    k01: ReportWorld, clock: FrozenClock
) -> None:
    """The approval locks the files of the request's evidence before it reads its basis again, as
    a shred locks the file it destroys. A shred in flight — the row locked and marked, not
    committed — holds the decision back; when it commits, the decision is refused as stale: no
    event is appended on a document destroyed beside it."""
    app, place = k01.app, k01.place
    contract_id = manual._k01_id(k01)
    evidence = _file(app, k01.maya, "progress-report-2026-01.pdf")
    created = _waiting(k01, manual._progress(), evidence=[evidence])
    head = manual._head(place, contract_id)

    decided = beside_a_shred(
        k01.tenant_id,
        UUID(evidence),
        lambda: approve(app, created["approval_request_id"], k01.priya),
        at=clock.now(),
    )

    assert (decided.waited, decided.response.status_code, slug(decided.response)) == (
        True,
        409,
        "stale-approval",
    )
    assert _status(k01, created) == ("VOIDED", "VOIDED")
    assert manual._head(place, contract_id) == head


def test_evt_evidence_1_an_event_that_needs_evidence_is_not_approved_without_a_readable_file(
    k01: ReportWorld,
) -> None:
    """REQ-DAT-014 at the approval. The requester may void her attachment while her request waits
    (T-PLT-30); a progress event is then approved on nothing. The approval is refused, the
    request stays pending, and once she has attached a document again it is approved and the
    event carries that document.

    The refusal's sentence names two roads of the preparer, and the first is walked here: as the
    requester of a pending request she attaches to it with ``POST /attachments`` whatever she
    holds (T-PLT-30, ruling R-100 (b)), and the approver reads the new file on the request at
    once — no new submission. The second, the withdrawal, is the third witness of this module."""
    app, place = k01.app, k01.place
    contract_id = manual._k01_id(k01)
    first = _file(app, k01.maya, "progress-report-2026-01.pdf")
    created = _waiting(k01, manual._progress(), evidence=[first])
    request_id = created["approval_request_id"]
    head = manual._head(place, contract_id)
    (attachment,) = place.rows(
        select(file_attachment.c.id).where(file_attachment.c.subject_id == UUID(request_id))
    )
    voided = post(
        app, f"{ATTACHMENTS}/{attachment['id']}/void", k01.maya, {"reason": "The wrong report."}
    )
    assert voided.status_code == 200, voided.text

    refused = approve(app, request_id, k01.priya)

    # the status first: before the rule the approval answered 200 and appended the event
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("evidence_file_ids", "REQ-DAT-014")]
    # The sentence is the approver's: she cannot attach to another person's request, and the
    # approval pane shows the detail of a refused decision.
    assert refused.json()["detail"] == refused.json()["errors"][0]["message"] == GONE
    assert _status(k01, created) == ("PENDING", "SUBMITTED")
    assert manual._head(place, contract_id) == head

    def on_the_request() -> list[str]:
        """The files of the request as its approver reads them (API-S-Approval ``attachments``)."""
        shown = get(app, f"{manual.APPROVALS}/{request_id}", k01.priya)
        assert shown.status_code == 200, shown.text
        return [str(item["file_id"]) for item in shown.json()["attachments"]]

    assert on_the_request() == []
    second = _file(app, k01.maya, "progress-report-2026-01-signed.pdf")
    attached = post(
        app,
        ATTACHMENTS,
        k01.maya,
        {"file_object_id": second, "subject_type": "approval_request", "subject_id": request_id},
    )
    assert attached.status_code == 201, attached.text
    assert on_the_request() == [second]  # the same request, read again: nothing was submitted anew
    assert _status(k01, created) == ("PENDING", "SUBMITTED")
    decided = approve(app, request_id, k01.priya)
    assert decided.status_code == 200, decided.text
    (event_id,) = _applied(k01, created)
    assert _listed(app, k01.marcus, "contract_event", event_id) == [second]
    assert _holds(k01, first) == []  # a voided attachment holds nothing


def test_evt_evidence_1_a_direct_append_attaches_its_evidence_to_the_events_it_appends(
    k01: ReportWorld, clock: FrozenClock
) -> None:
    """An invoice needs no approval (04 E-03), and the files its caller sends with it are attached
    to the appended event, as the caller: the readers of the event list them there and open them,
    and the file is held like the evidence of an approved request. Measured before: the file's
    id stood in the audit event of the record and nowhere a reader of the event could follow it —
    only its uploader opened it."""
    app, place = k01.app, k01.place
    contract_id = manual._k01_id(k01)
    tess = _admin(k01, clock)
    others = _others(k01)
    evidence = _file(app, k01.maya, "invoice-copy-INV-US-9001.pdf")

    billed = manual._sent(
        place,
        k01.maya,
        contract_id,
        manual._billing("INV-US-9001", "100.00", "USD", "2026-01-30", "O1"),
        evidence=[evidence],
    )

    assert billed.status_code == 201, billed.text
    (event,) = billed.json()["events"]
    event_id = str(event["id"])
    for name, actor in {"the caller": k01.maya, "a reviewer": k01.priya, **others}.items():
        assert _listed(app, actor, "contract_event", event_id) == [evidence], name
        assert _opens(app, actor, evidence) == (200, 200), name
    (attached,) = place.rows(
        select(file_attachment).where(file_attachment.c.subject_id == UUID(event_id))
    )
    assert (attached["created_by"], str(attached["created_by_kind"])) == (
        k01.maya.member.user_id,
        "USER",
    )
    _approval_required(_shred(app, tess, evidence), EVENT_RECORD)
    assert _holds(k01, evidence) == [EVENT_RECORD]


def test_evt_evidence_1_a_direct_append_refuses_a_file_that_cannot_be_attached(
    k01: ReportWorld,
) -> None:
    """What a record names as its evidence is attached, so it must be a file that can be: one of
    another purpose is refused on the member the caller sent, and nothing is appended."""
    app, place = k01.app, k01.place
    contract_id = manual._k01_id(k01)
    head = manual._head(place, contract_id)
    study = _file(app, k01.maya, "list-prices.pdf", purpose="SSP_STUDY")
    source = call(
        app,
        "POST",
        FILES,
        data={"purpose": "IMPORT_SOURCE"},
        files={"file": ("invoices.csv", b"contract,invoice\\n", "text/csv")},
        headers=cookie_headers(k01.maya.token, k01.maya.csrf_token),
    )
    assert source.status_code == 201, source.text

    refused = manual._sent(
        place,
        k01.maya,
        contract_id,
        manual._billing("INV-US-9002", "100.00", "USD", "2026-01-30", "O1"),
        evidence=[study, str(source.json()["id"])],
    )

    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("evidence_file_ids[1]", "T-PLT-29")]
    assert manual._head(place, contract_id) == head
    assert (
        place.rows(
            select(file_attachment.c.id).where(file_attachment.c.subject_type == "contract_event")
        )
        == []
    )
