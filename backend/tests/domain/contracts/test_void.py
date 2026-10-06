"""Contract void (04 §16.1 ``request-void``, §16.3 ``CONTRACT_VOIDED``, table 3.4-R, T-SL-01
``void:<contract_event_id>``; PRD §2.5 routing rows ``CONTRACT_VOID``, §5.2 SM-02, J-26;
03 REQ-CON-015; BUILD_SPEC CTR-11; control CTL-046; readiness row APR-SUBJECTS-CTR).

Worlds: ``support.factories.seat_world`` (AVM-US, USD; a draft seat contract without postings) and
``support.factories.k11_world`` (AVM-DE, EUR; K-11 delivered and computed, so revenue lines are
posted in FY2026-P09). Maya (Revenue Accountant, ``contract.void``) requests; Priya is given
Revenue Reviewer (``contract.approve``); Marcus (Controller) holds the second step.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    contract,
    contract_event,
    role,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.contracts import void as void_module
from erev_api.domain.demo.avenmoor.policies import (
    ROUTING_RULES,
    routing_conditions,
    routing_outputs,
)
from erev_api.enums import RuleSetKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    K11World,
    SeatWorld,
    activated_contract,
    booked_contract,
    computed,
    delivered_k11,
    k11_world,
    seat_body,
    seat_line,
    seat_world,
)
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled
from support.reference import APPROVALS, approve, assign, fields, get, post, reject, slug
from support.rows import publish_rule_set

CONTRACTS = "/api/v1/contracts"
GROUPS = "/api/v1/combination-groups"
COMMENT = "Duplicate of NS-SO-DE-5003 created by a repeated CRM sync."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    world = seat_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


def _request_void(
    app: FastAPI, actor: Actor, contract_id: UUID, head: int, reason: str, comment: str = COMMENT
) -> HttpResponse:
    return post(
        app,
        f"{CONTRACTS}/{contract_id}/request-void",
        actor,
        {"reason_code": reason, "comment": comment},
        if_match=f'"s{head}"',
    )


def _draft_seat_contract(world: SeatWorld, external_id: str) -> UUID:
    """A C-09 seat contract booked through ``POST /contracts`` and left DRAFT (head 1)."""
    line = seat_line("O1", seats="30", price="108000.00", start="2026-09-01", end="2029-08-31")
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    created = post(world.app, CONTRACTS, world.place.author, body)
    assert created.status_code == 201, created.text
    return UUID(str(created.json()["id"]))


def _header(world: SeatWorld | K11World, contract_id: UUID) -> tuple[str, int]:
    row = world.place.rows(
        select(contract.c.status, contract.c.head_stream_version).where(
            contract.c.id == contract_id
        )
    )[0]
    return str(row["status"]), int(row["head_stream_version"])


def _requests(world: SeatWorld | K11World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            approval_request.c.id,
            approval_request.c.status,
            approval_request.c.flags,
            approval_request.c.entity_id,
            approval_request.c.amount_functional,
            approval_request.c.amount_currency,
            approval_request.c.impact_preview_sha256,
            approval_request.c.reason_code,
            approval_request.c.comment,
            approval_request.c.preparer_id,
            approval_request.c.void_reason,
            approval_request.c.routing_rule_id,
        )
        .where(
            approval_request.c.subject_type == "CONTRACT_VOID",
            approval_request.c.subject_id == contract_id,
        )
        .order_by(approval_request.c.request_no)
    )


def _steps(world: SeatWorld | K11World, request_id: str) -> list[tuple[int, str, UUID | None, str]]:
    rows = world.place.rows(
        select(
            approval_step.c.step_no,
            approval_step.c.required_permission,
            approval_step.c.required_role_id,
            approval_step.c.status,
        )
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return [
        (
            int(row["step_no"]),
            str(row["required_permission"]),
            row["required_role_id"],
            str(row["status"]),
        )
        for row in rows
    ]


def _events(world: SeatWorld | K11World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract_event.c.origin,
            contract_event.c.approval_request_id,
            contract_event.c.payload,
        )
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def _lines(world: SeatWorld | K11World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            subledger_line.c.id,
            subledger_line.c.subledger_posting_id,
            subledger_line.c.account_role,
            subledger_line.c.entity_id,
            subledger_line.c.period_id,
            subledger_line.c.origin_period_id,
            subledger_line.c.amount_txn,
            subledger_line.c.reason_code,
            subledger_line.c.book_code,
            subledger_line.c.recorded_at,
        ).where(subledger_line.c.contract_id == contract_id)
    )


def _sums(lines: list[dict[str, Any]]) -> dict[tuple[str, UUID, UUID], Decimal]:
    totals: dict[tuple[str, UUID, UUID], Decimal] = defaultdict(Decimal)
    for line in lines:
        totals[(str(line["account_role"]), line["entity_id"], line["period_id"])] += Decimal(
            line["amount_txn"]
        )
    return dict(totals)


def test_void_without_posted_lines_one_step(seats: SeatWorld) -> None:
    """PRD §2.5 ``CONTRACT_VOID`` (no posted line): one ``contract.approve`` step; nothing changes
    while the request is pending; approval appends ``CONTRACT_VOIDED`` as SYSTEM with the request
    id and the request's reason, sets ``VOIDED`` and ``voided_at`` (SM-02) and posts nothing."""
    maya = seats.place.author
    contract_id = _draft_seat_contract(seats, "SF-ORD-10440")
    requested = _request_void(seats.app, maya, contract_id, 1, "CREATED_IN_ERROR")
    assert requested.status_code == 200, requested.text
    assert set(requested.json()) == {"approval_request_id"}
    request_id = requested.json()["approval_request_id"]
    (request,) = _requests(seats, contract_id)
    assert (
        str(request["id"]),
        str(request["status"]),
        list(request["flags"]),
        request["entity_id"],
        Decimal(request["amount_functional"]),
        str(request["amount_currency"]).strip(),
        str(request["reason_code"]),
        request["comment"],
        request["preparer_id"],
    ) == (
        request_id,
        "PENDING",
        [],
        seats.entity_id,
        Decimal("108000.00"),
        "USD",
        "CREATED_IN_ERROR",
        COMMENT,
        maya.member.user_id,
    )
    assert request["impact_preview_sha256"] is not None
    assert _steps(seats, request_id) == [(1, "contract.approve", None, "ACTIVE")]
    shown = get(seats.app, f"{APPROVALS}/{request_id}", seats.priya).json()
    assert shown["subject"]["type"] == "CONTRACT_VOID"
    assert str(shown["subject"]["href"]).endswith(f"/contracts/{contract_id}")
    assert shown["impact_preview"] is not None
    # The request is the pending state: the contract itself is unchanged (SMAP-01 rule).
    assert _header(seats, contract_id) == ("DRAFT", 1)
    again = _request_void(seats.app, maya, contract_id, 1, "DUPLICATE")
    assert (again.status_code, slug(again)) == (409, "invalid-transition")

    approved = approve(seats.app, request_id, seats.priya)
    assert approved.status_code == 200, approved.text
    assert _header(seats, contract_id) == ("VOIDED", 2)
    voided = get(seats.app, f"{CONTRACTS}/{contract_id}", maya).json()
    assert (voided["status"], voided["voided_at"] is not None) == ("VOIDED", True)
    events = _events(seats, contract_id)
    assert [(str(row["event_type"]), str(row["origin"])) for row in events] == [
        ("CONTRACT_BOOKED", "UI"),
        ("CONTRACT_VOIDED", "SYSTEM"),
    ]
    assert str(events[-1]["approval_request_id"]) == request_id
    # D-98 99a: the SYSTEM append carries the approved cutoff (no posted line on a draft contract).
    assert events[-1]["payload"] == {
        "reason_code": "CREATED_IN_ERROR",
        "comment": COMMENT,
        "approval_request_id": request_id,
        "posted_line_count": 0,
        "posted_through": None,
        "posted_through_seq": {},
    }
    assert _lines(seats, contract_id) == []
    decided = seats.place.rows(
        select(approval_decision.c.approver_id, approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert [(row["approver_id"], str(row["decision"])) for row in decided] == [
        (seats.priya.member.user_id, "APPROVE")
    ]
    audits = seats.place.rows(
        select(audit_event.c.action, audit_event.c.after).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.action.in_(("contract.void_requested", "contract.voided")),
        )
    )
    assert sorted(str(row["action"]) for row in audits) == [
        "contract.void_requested",
        "contract.voided",
    ]
    # A voided contract takes no second void (SM-02).
    closed = _request_void(seats.app, maya, contract_id, 2, "DUPLICATE")
    assert (closed.status_code, slug(closed)) == (409, "invalid-transition")


def test_void_request_rejected_leaves_contract_and_reopens(seats: SeatWorld) -> None:
    """Maker-checker: the reviewer's rejection closes the request with an audit trail only; the
    contract is unchanged and a new request can be opened (SM-01; REQ-PLT-013)."""
    maya = seats.place.author
    contract_id = _draft_seat_contract(seats, "SF-ORD-10441")
    requested = _request_void(seats.app, maya, contract_id, 1, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    rejected = reject(
        seats.app, request_id, seats.priya, "Not a duplicate: the second order stands."
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert _header(seats, contract_id) == ("DRAFT", 1)
    assert [str(row["event_type"]) for row in _events(seats, contract_id)] == ["CONTRACT_BOOKED"]
    closed = seats.place.rows(
        select(audit_event.c.approval_request_id).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.action == "contract.void_request_closed",
        )
    )
    assert [str(row["approval_request_id"]) for row in closed] == [request_id]
    reopened = _request_void(seats.app, maya, contract_id, 1, "DUPLICATE")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["approval_request_id"] != request_id


def test_void_reason_subset(seats: SeatWorld) -> None:
    """04 table 3.4-R: ``DATA_CORRECTION`` is a void reason; ``AUDIT_ADJUSTMENT`` is an E-110
    literal outside the subset and answers 422 ``REASON_CODE_NOT_ALLOWED``; the header stays."""
    maya = seats.place.author
    contract_id = _draft_seat_contract(seats, "SF-ORD-10442")
    refused = _request_void(seats.app, maya, contract_id, 1, "AUDIT_ADJUSTMENT")
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("reason_code", "REASON_CODE_NOT_ALLOWED")]
    assert refused.json()["errors"][0]["message"] == (
        "The reason Audit adjustment cannot be used to void a contract."
    )
    assert _requests(seats, contract_id) == []
    accepted = _request_void(seats.app, maya, contract_id, 1, "DATA_CORRECTION")
    assert accepted.status_code == 200, accepted.text
    assert _header(seats, contract_id) == ("DRAFT", 1)


def test_void_needs_the_void_permission_and_a_fresh_head(seats: SeatWorld) -> None:
    """``contract.void`` guards the command (04 API-R-28; PRD ACT-05): a Revenue Reviewer without it
    is 403; a stale ``If-Match`` is 412 and opens nothing."""
    maya = seats.place.author
    contract_id = _draft_seat_contract(seats, "SF-ORD-10443")
    forbidden = _request_void(seats.app, seats.priya, contract_id, 1, "DUPLICATE")
    assert (forbidden.status_code, slug(forbidden)) == (403, "forbidden")
    stale = _request_void(seats.app, maya, contract_id, 7, "DUPLICATE")
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed")
    assert _requests(seats, contract_id) == []


def _footprint(world: SeatWorld, contract_id: UUID) -> tuple[tuple[str, int], int, int, int]:
    """Header, event count, CONTRACT_VOID request count and subledger line count of a contract."""
    return (
        _header(world, contract_id),
        len(_events(world, contract_id)),
        len(_requests(world, contract_id)),
        len(_lines(world, contract_id)),
    )


def test_void_refusals_have_no_side_effects(seats: SeatWorld) -> None:
    """Every refused request-void (422 reason, 403 permission, 412 stale head, 409 pending) leaves
    the contract, its stream, the request table and the subledger exactly as they were; only the
    one accepted request opens exactly one PENDING request (DG-CMD-09; REQ-PLT-013)."""
    maya = seats.place.author
    contract_id = _draft_seat_contract(seats, "SF-ORD-10444")
    before = _footprint(seats, contract_id)
    assert before == (("DRAFT", 1), 1, 0, 0)
    refused = _request_void(seats.app, maya, contract_id, 1, "AUDIT_ADJUSTMENT")
    assert refused.status_code == 422, refused.text
    forbidden = _request_void(seats.app, seats.priya, contract_id, 1, "DUPLICATE")
    assert forbidden.status_code == 403, forbidden.text
    stale = _request_void(seats.app, maya, contract_id, 3, "DUPLICATE")
    assert stale.status_code == 412, stale.text
    assert _footprint(seats, contract_id) == before
    opened = _request_void(seats.app, maya, contract_id, 1, "DUPLICATE")
    assert opened.status_code == 200, opened.text
    pending = _footprint(seats, contract_id)
    assert pending == (("DRAFT", 1), 1, 1, 0)
    again = _request_void(seats.app, maya, contract_id, 1, "CREATED_IN_ERROR")
    assert (again.status_code, slug(again)) == (409, "invalid-transition")
    assert _footprint(seats, contract_id) == pending
    (request,) = _requests(seats, contract_id)
    assert (str(request["status"]), str(request["reason_code"])) == ("PENDING", "DUPLICATE")


def _active(world: SeatWorld, external_id: str, seats: str, price: str, end: str) -> UUID:
    line = seat_line("O1", seats=seats, price=price, start="2026-09-01", end=end)
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return UUID(str(booked.contract["id"]))


def test_combined_member_cannot_be_voided(seats: SeatWorld) -> None:
    """SM-02 / SMAP-01: a contract with a current membership of a non-singleton applied group
    answers 409 ``invalid-transition``; the void is a group decision (leave first)."""
    first = _active(seats, "SF-ORD-10417", "30", "108000.00", "2029-08-31")
    second = _active(seats, "SF-ORD-10418", "10", "48000.00", "2027-08-31")
    proposed = post(
        seats.app,
        GROUPS,
        seats.place.author,
        {
            "contract_ids": [str(first), str(second)],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = proposed.json()["id"]
    submitted = post(seats.app, f"{GROUPS}/{group_id}/submit", seats.place.author, {})
    assert submitted.status_code == 200, submitted.text
    applied = approve(seats.app, submitted.json()["approval_request_id"], seats.marcus)
    assert applied.status_code == 200, applied.text
    _, head = _header(seats, first)
    refused = _request_void(seats.app, seats.place.author, first, head, "DUPLICATE")
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition")
    assert refused.json()["detail"] == (
        "A contract combined into an applied group cannot be voided; take it out of the group "
        "first."
    )
    assert _requests(seats, first) == []


@pytest.mark.control("CTL-046")
def test_ctl_046_void_with_posted_lines_two_steps_and_reversals(
    k11: K11World, clock: FrozenClock
) -> None:
    """CTL-046 (REQ-CON-015; PRD §2.5 ``CONTRACT_VOID`` with posted lines; J-26): K-11 delivered
    and computed has revenue posted; its void routes two steps (Revenue Reviewer, then a
    Controller); before approval nothing reverses; the preparer's approval is 403 ``self-approval``
    although she holds ``contract.approve`` and is MFA-verified (the authority and BR-PLT-06
    step-up checks before it pass; CTL-014 maker-checker); after both
    approvals a ``VOID_REVERSAL`` posting with key ``void:<contract_event_id>`` (04 T-SL-01) nets
    every posted role, entity and period of the contract to zero with reason ``VOID`` (ENGINE_SPEC_B
    S14-R-08; D-98 80), every earlier line is still stored and the events stay readable."""
    someone = colleague(k11.place.tenant_id, "rhea")
    for code in ("revenue_accountant", "revenue_reviewer"):  # contract.void and contract.approve
        assign(someone, code)
    rhea = enrolled(k11.app, clock, someone)  # MFA-verified preparer (BR-PLT-06)
    booked = delivered_k11(k11)
    group_id = UUID(str(booked.combination_group["id"]))
    computed(k11.place, group_id)
    contract_id = UUID(str(booked.contract["id"]))
    status, head = _header(k11, contract_id)
    assert status == "ACTIVE"
    before = _lines(k11, contract_id)
    assert before, "K-11 delivered and computed posts lines"
    assert all(str(line["reason_code"] or "") != "VOID" for line in before)

    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    (request,) = _requests(k11, contract_id)
    assert (
        list(request["flags"]),
        request["entity_id"],
        str(request["amount_currency"]).strip(),
        str(request["reason_code"]),
    ) == (["POSTED_LINES"], k11.entity_id, "EUR", "DUPLICATE")
    assert Decimal(request["amount_functional"]) > 0
    controller = k11.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert _steps(k11, request_id) == [
        (1, "contract.approve", None, "ACTIVE"),
        (2, "contract.approve", controller, "WAITING"),
    ]
    # Before approval nothing reverses and nothing changes.
    assert _lines(k11, contract_id) == before
    assert _header(k11, contract_id) == ("ACTIVE", head)

    denied = approve(k11.app, request_id, rhea)
    assert (denied.status_code, slug(denied)) == (403, "self-approval")
    first = approve(k11.app, request_id, k11.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    assert _lines(k11, contract_id) == before
    refused = approve(k11.app, request_id, k11.priya)
    assert (refused.status_code, slug(refused)) == (403, "forbidden")
    second = approve(k11.app, request_id, k11.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"

    assert _header(k11, contract_id) == ("VOIDED", head + 1)
    events = _events(k11, contract_id)
    assert (str(events[-1]["event_type"]), str(events[-1]["origin"])) == (
        "CONTRACT_VOIDED",
        "SYSTEM",
    )
    assert str(events[-1]["approval_request_id"]) == request_id
    void_event_id = events[-1]["id"]
    postings = k11.place.rows(
        select(
            subledger_posting.c.id,
            subledger_posting.c.book_code,
            subledger_posting.c.posting_kind,
            subledger_posting.c.idempotency_key,
        ).where(subledger_posting.c.combination_group_id == group_id)
    )
    reversals = [row for row in postings if str(row["posting_kind"]) == "VOID_REVERSAL"]
    assert reversals, [str(row["posting_kind"]) for row in postings]
    assert {str(row["idempotency_key"]) for row in reversals} == {f"void:{void_event_id}"}
    after = _lines(k11, contract_id)
    # Nothing is deleted: every earlier line is still stored, and the reversal lines are new.
    assert {line["id"] for line in before} <= {line["id"] for line in after}
    reversal_ids = {row["id"] for row in reversals}
    reversed_lines = [line for line in after if line["subledger_posting_id"] in reversal_ids]
    # D-98 80: the book loop binds the voided members into stage 14, so every reversal intent and
    # line carries reason VOID (ENGINE_SPEC_B S14-R-08).
    assert reversed_lines and all(str(line["reason_code"]) == "VOID" for line in reversed_lines)
    # Every posted role, entity and period of the contract nets to zero after the reversal.
    assert all(total == 0 for total in _sums(after).values()), _sums(after)
    assert _sums(reversed_lines) == {key: -total for key, total in _sums(before).items()}
    listed = get(k11.app, f"{CONTRACTS}/{contract_id}/events", rhea)
    assert listed.status_code == 200, listed.text
    assert [item["event_type"] for item in listed.json()["items"]][-1] == "CONTRACT_VOIDED"


def _step_names(world: SeatWorld | K11World, request_id: str) -> list[str]:
    rows = world.place.rows(
        select(approval_step.c.name)
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return [str(row["name"]) for row in rows]


def _reviewer(world: K11World, clock: FrozenClock, name: str, *roles: str) -> Actor:
    """An MFA-verified colleague holding ``roles`` (BR-PLT-06 step-up passes on a decision)."""
    someone = colleague(world.place.tenant_id, name)
    for code in roles:
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def _void_reversal_ids(world: K11World, group_id: UUID) -> set[UUID]:
    rows = world.place.rows(
        select(subledger_posting.c.id).where(
            subledger_posting.c.combination_group_id == group_id,
            subledger_posting.c.posting_kind == "VOID_REVERSAL",
        )
    )
    return {row["id"] for row in rows}


def test_void_request_voided_as_stale_when_a_computation_posts_before_the_decision(
    k11: K11World, clock: FrozenClock
) -> None:
    """D-98 92 (F-CTR-VOID-FRESH-R1): a void requested while the delivered contract has no posted
    line routes one step; the queued computation then posts lines at the same event head, so the
    request's subject content (posted-state basis) changes and the reviewer's approval voids it as
    ``STALE_SUBJECT`` with 409 ``stale-approval`` — nothing is appended, nothing reverses; the void
    resubmitted afterwards routes two steps (``POSTED_LINES``) and executes under them."""
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    booked = delivered_k11(k11)  # delivered, not yet computed: no posted line
    group_id = UUID(str(booked.combination_group["id"]))
    contract_id = UUID(str(booked.contract["id"]))
    status, head = _header(k11, contract_id)
    assert _lines(k11, contract_id) == []

    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    (request,) = _requests(k11, contract_id)
    assert list(request["flags"]) == []
    assert _steps(k11, request_id) == [(1, "contract.approve", None, "ACTIVE")]

    # The deferred CONTRACT_COMPUTE persists postings; the stream head does not move.
    computed(k11.place, group_id)
    posted = _lines(k11, contract_id)
    assert posted and _header(k11, contract_id) == (status, head)

    stale = approve(k11.app, request_id, k11.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    (voided,) = _requests(k11, contract_id)
    assert (str(voided["status"]), str(voided["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert _header(k11, contract_id) == (status, head)
    assert [str(row["event_type"]) for row in _events(k11, contract_id)][-1] != "CONTRACT_VOIDED"
    assert _lines(k11, contract_id) == posted
    assert _void_reversal_ids(k11, group_id) == set()

    # Resubmitted under the posted state it now has: two steps, the second held by a Controller.
    again = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert again.status_code == 200, again.text
    second_id = again.json()["approval_request_id"]
    requests = _requests(k11, contract_id)
    assert [str(row["status"]) for row in requests] == ["VOIDED", "PENDING"]
    assert list(requests[-1]["flags"]) == ["POSTED_LINES"]
    controller = k11.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert _steps(k11, second_id) == [
        (1, "contract.approve", None, "ACTIVE"),
        (2, "contract.approve", controller, "WAITING"),
    ]
    first = approve(k11.app, second_id, k11.priya)
    assert first.status_code == 200, first.text
    second = approve(k11.app, second_id, k11.marcus)
    assert second.status_code == 200, second.text
    assert _header(k11, contract_id) == ("VOIDED", head + 1)
    assert _void_reversal_ids(k11, group_id)
    assert all(total == 0 for total in _sums(_lines(k11, contract_id)).values())


@pytest.mark.control("CTL-046")
def test_ctl_046_published_route_void_02_second_step_is_held_by_a_controller(
    k11: K11World, clock: FrozenClock
) -> None:
    """D-98 93 (F-CTR-VOID-ROUTE-R2): the shipped Avenmoor ``ROUTE-VOID-01`` / ``ROUTE-VOID-02``
    published in the tenant; a void with posted lines matches ``ROUTE-VOID-02``, whose second step
    carries the ``controller`` role (04 T-REF-26 ``role`` → T-PLT-18 ``required_role_id``), so a
    second Revenue Reviewer holding ``contract.approve`` is refused on step 2 and only a Controller
    completes it — the matched rule enforces what the SubjectSpec fallback enforces
    (maker-checker and distinct approvers kept)."""
    void_rules = [rule for rule in ROUTING_RULES if rule.rule_key.startswith("ROUTE-VOID-")]
    assert [rule.rule_key for rule in void_rules] == ["ROUTE-VOID-01", "ROUTE-VOID-02"]
    assert routing_outputs(void_rules[1])["steps"][1] == {
        "name": "Controller approval",
        "permission": "contract.approve",
        "min_approvers": 1,
        "role": "controller",
    }
    context = DbContext(tenant_id=k11.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        _, rule_ids = publish_rule_set(
            session,
            tenant_id=k11.place.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            code="APPROVAL_ROUTING",
            rules=[
                {
                    "rule_key": rule.rule_key,
                    "conditions": routing_conditions(rule),
                    "outputs": routing_outputs(rule),
                }
                for rule in void_rules
            ],
        )
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    sven = _reviewer(k11, clock, "sven", "revenue_reviewer")
    booked = delivered_k11(k11)
    group_id = UUID(str(booked.combination_group["id"]))
    computed(k11.place, group_id)
    contract_id = UUID(str(booked.contract["id"]))
    _, head = _header(k11, contract_id)
    assert _lines(k11, contract_id)

    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    (request,) = _requests(k11, contract_id)
    assert (list(request["flags"]), request["routing_rule_id"]) == (
        ["POSTED_LINES"],
        rule_ids["ROUTE-VOID-02"],
    )
    controller = k11.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert _steps(k11, request_id) == [
        (1, "contract.approve", None, "ACTIVE"),
        (2, "contract.approve", controller, "WAITING"),
    ]
    assert _step_names(k11, request_id) == ["Revenue review", "Controller approval"]

    denied = approve(k11.app, request_id, rhea)
    assert (denied.status_code, slug(denied)) == (403, "self-approval")
    first = approve(k11.app, request_id, k11.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    refused = approve(k11.app, request_id, sven)
    assert (refused.status_code, slug(refused)) == (403, "forbidden")
    assert refused.json()["detail"] == "This approval step needs a holder of the Controller role."
    repeated = approve(k11.app, request_id, k11.priya)
    assert repeated.status_code == 403, repeated.text  # a second decision by the same reviewer
    assert _header(k11, contract_id)[0] == "ACTIVE"
    second = approve(k11.app, request_id, k11.marcus)
    assert second.status_code == 200, second.text
    assert _header(k11, contract_id) == ("VOIDED", head + 1)
    assert _void_reversal_ids(k11, group_id)


def test_d98_101_compute_committed_between_pre_lock_read_and_locks_is_refused(
    k11: K11World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-98 101 (Codex F-CTR-VOID-FRESH-R3): a one-step void request of an unposted contract is
    being approved; a deferred computation (another session) commits postings AFTER the approval's
    pre-lock basis read and BEFORE its first financial lock. The forced interleaving runs the
    computation inside the first ``void_flags`` call of the approval path (an existing module
    boundary; no production seam). The approval must not proceed over the new posted state: the
    final validation under the group / contract locks refuses it as 409 ``stale-approval``, the
    decision rolls back and ``decide`` voids the request ``STALE_SUBJECT`` at once (D-98 101d(2):
    the engine's ``assert_fresh_basis`` under the hook's locks; the contract ACTIVE, nothing
    appended, no reversal), and the resubmitted void
    routes two steps."""
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    booked = delivered_k11(k11)  # delivered, not computed: no posted line
    group_id = UUID(str(booked.combination_group["id"]))
    contract_id = UUID(str(booked.contract["id"]))
    status, head = _header(k11, contract_id)
    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    (request,) = _requests(k11, contract_id)
    assert list(request["flags"]) == []

    original = void_module.void_flags
    calls: list[int] = []

    def interleaved(session: Any, subject_id: UUID) -> frozenset[str]:
        flags = original(session, subject_id)
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            # Session B: the queued CONTRACT_COMPUTE locks the group, persists the postings and
            # commits — after A's pre-lock read, before A's first financial lock.
            computed(k11.place, group_id)
        return flags

    monkeypatch.setattr(void_module, "void_flags", interleaved)
    decided = approve(k11.app, request_id, k11.priya)
    monkeypatch.setattr(void_module, "void_flags", original)
    assert calls, "the approval path read the basis before locking"
    assert decided.status_code == 409, (
        decided.text
    )  # today: 200, the void executes over new postings
    assert slug(decided) == "stale-approval"
    assert _lines(k11, contract_id), "session B's postings are committed"
    (voided,) = _requests(k11, contract_id)
    # D-98 101d(2): the engine's assert_fresh_basis under the hook's locks raised StaleBasis;
    # decide undid the decision and the hook's partial work and voided the request by name at once.
    assert (str(voided["status"]), str(voided["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert _header(k11, contract_id) == (status, head)
    assert [str(row["event_type"]) for row in _events(k11, contract_id)][-1] != "CONTRACT_VOIDED"
    assert _void_reversal_ids(k11, group_id) == set()
    resubmitted = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert resubmitted.status_code == 200, resubmitted.text
    controller = k11.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert _steps(k11, resubmitted.json()["approval_request_id"]) == [
        (1, "contract.approve", None, "ACTIVE"),
        (2, "contract.approve", controller, "WAITING"),
    ]


def _seals(world: K11World, contract_id: UUID) -> dict[UUID, tuple[str, int]]:
    """Posting id → (book, T-SL-02 chain position) of every posting with a line of the contract."""
    seal = subledger_posting_seal
    rows = world.place.rows(
        select(seal.c.subledger_posting_id, seal.c.book_code, seal.c.chain_seq)
        .join(subledger_line, subledger_line.c.subledger_posting_id == seal.c.subledger_posting_id)
        .where(subledger_line.c.contract_id == contract_id)
        .distinct()
    )
    return {
        row["subledger_posting_id"]: (str(row["book_code"]).strip(), int(row["chain_seq"]))
        for row in rows
    }


def _by_position(seals: dict[UUID, tuple[str, int]], positions: dict[str, int]) -> set[UUID]:
    """The reversed set 04 T-SL-01 derives from a stored cutoff position (D-98 99b)."""
    return {
        posting_id
        for posting_id, (book, seq) in seals.items()
        if book in positions and seq <= positions[book]
    }


def _conserved(lines: list[dict[str, Any]], postings: set[UUID]) -> dict[tuple[str, str], Decimal]:
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for line in lines:
        if line["subledger_posting_id"] in postings:
            totals[(str(line["account_role"]), str(line["book_code"]).strip())] += Decimal(
                line["amount_txn"]
            )
    return dict(totals)


def _void_and_approve_two_steps(
    k11: K11World, clock: FrozenClock, *, advance: bool = True
) -> tuple[UUID, UUID, str]:
    """The CTL-046 world voided: K-11 delivered and computed, the void routed two steps and approved
    by Priya then Marcus — after the frozen clock advanced one minute (inside the MFA step-up
    window), so the reversal is recorded strictly after the reversed postings, or with ``advance``
    false in the very instant of the reversed postings (the original CTL-046 population; D-98
    99b); returns (contract id, group id, request id)."""
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    booked = delivered_k11(k11)
    group_id = UUID(str(booked.combination_group["id"]))
    computed(k11.place, group_id)
    contract_id = UUID(str(booked.contract["id"]))
    _, head = _header(k11, contract_id)
    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    if advance:
        clock.advance(timedelta(minutes=1))
    assert approve(k11.app, request_id, k11.priya).status_code == 200
    assert approve(k11.app, request_id, k11.marcus).status_code == 200
    assert _header(k11, contract_id) == ("VOIDED", head + 1)
    return contract_id, group_id, request_id


def test_d98_99_void_reversal_conserves_the_derived_reversed_set(
    k11: K11World, clock: FrozenClock
) -> None:
    """D-98 99 / 99a / 99b: ``reverses_posting_id`` stays NULL; the approved cutoff is stored on
    the ``CONTRACT_VOIDED`` payload (``approval_request_id``, ``posted_line_count``,
    ``posted_through`` and the per-book chain position ``posted_through_seq``), in the execution
    audit event and in the ``VOID_REVERSAL`` posting's description; the reversed set is DERIVED
    from the STORED position — every posting of the contract in the book whose seal ``chain_seq``
    is at or below it — and Σ(reversed set) + reversal = 0 per account role and book (04 T-SL-01;
    CTL-046). With the clock advanced, the timestamps agree with the positions."""
    contract_id, group_id, request_id = _void_and_approve_two_steps(k11, clock)
    lines = _lines(k11, contract_id)
    reversal_ids = _void_reversal_ids(k11, group_id)
    assert reversal_ids
    void_event = _events(k11, contract_id)[-1]
    assert str(void_event["event_type"]) == "CONTRACT_VOIDED"
    payload = void_event["payload"]
    assert payload["approval_request_id"] == request_id
    posted_through = datetime.fromisoformat(payload["posted_through"])
    earlier = [line for line in lines if line["subledger_posting_id"] not in reversal_ids]
    reversal = [line for line in lines if line["subledger_posting_id"] in reversal_ids]
    assert payload["posted_line_count"] == len(earlier) > 0
    assert posted_through == max(line["recorded_at"] for line in earlier)
    assert min(line["recorded_at"] for line in reversal) > posted_through
    seals = _seals(k11, contract_id)
    positions = payload["posted_through_seq"]
    assert positions == {
        book: max(seq for pid, (b, seq) in seals.items() if b == book and pid not in reversal_ids)
        for book in {b for pid, (b, _) in seals.items() if pid not in reversal_ids}
    }
    assert all(seals[pid][1] > positions[seals[pid][0]] for pid in reversal_ids)
    reversed_set = _by_position(seals, positions)
    assert reversed_set == {line["subledger_posting_id"] for line in earlier}
    assert reversed_set and reversed_set.isdisjoint(reversal_ids)
    # With the clock advanced the timestamp view names the same set (D-98 99a wording).
    books = {str(line["book_code"]).strip() for line in reversal}
    assert reversed_set == {
        line["subledger_posting_id"]
        for line in lines
        if line["recorded_at"] <= posted_through and str(line["book_code"]).strip() in books
    }
    postings = k11.place.rows(
        select(
            subledger_posting.c.id,
            subledger_posting.c.reverses_posting_id,
            subledger_posting.c.description,
        ).where(subledger_posting.c.id.in_(sorted(reversal_ids)))
    )
    assert all(
        row["reverses_posting_id"] is None for row in postings
    )  # D-98 99: derived, not stored
    assert all(
        f"approval request {request_id}" in str(row["description"])
        and payload["posted_through"] in str(row["description"])
        and f"chain positions {positions}" in str(row["description"])
        for row in postings
    )
    executed = k11.place.rows(
        select(audit_event.c.detail).where(
            audit_event.c.object_id == contract_id, audit_event.c.action == "contract.void_executed"
        )
    )
    # The audit detail and the payload serialise the same instant (offset vs "Z" spelling).
    assert [datetime.fromisoformat(row["detail"]["posted_through"]) for row in executed] == [
        posted_through
    ]
    assert [row["detail"]["posted_through_seq"] for row in executed] == [positions]
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for line in lines:
        if (
            line["subledger_posting_id"] in reversed_set
            or line["subledger_posting_id"] in reversal_ids
        ):
            totals[(str(line["account_role"]), str(line["book_code"]).strip())] += Decimal(
                line["amount_txn"]
            )
    assert totals and all(total == 0 for total in totals.values()), dict(totals)


def test_d98_99b_no_clock_advance_population_is_derived_by_position(
    k11: K11World, clock: FrozenClock
) -> None:
    """D-98 99b (Codex VOID-CUTOFF-R4): the original CTL-046 population — K-11 computed and the void
    approved WITHOUT advancing the shared frozen clock, so the reversed postings P and the reversal
    R carry one ``recorded_at`` T. A time cutoff ``<= T`` selects R itself (the set would exceed
    the stored population and count R twice); the stored cutoff is the per-book chain POSITION
    (T-SL-02 ``chain_seq``) of the last original posting, R's seal is later by construction, the
    derived set equals the approved population exactly (line count = ``posted_line_count``) and
    Σ(reversed set) + R = 0 per account role and book. The clock is not advanced to make this
    pass."""
    contract_id, group_id, request_id = _void_and_approve_two_steps(k11, clock, advance=False)
    lines = _lines(k11, contract_id)
    reversal_ids = _void_reversal_ids(k11, group_id)
    assert reversal_ids
    payload = _events(k11, contract_id)[-1]["payload"]
    assert payload["approval_request_id"] == request_id
    posted_through = datetime.fromisoformat(payload["posted_through"])
    earlier = [line for line in lines if line["subledger_posting_id"] not in reversal_ids]
    reversal = [line for line in lines if line["subledger_posting_id"] in reversal_ids]
    assert earlier and reversal
    # The defect population: every line, reversed and reversing, was recorded in the instant T.
    assert {line["recorded_at"] for line in lines} == {posted_through}
    books = {str(line["book_code"]).strip() for line in reversal}
    by_time = {
        line["subledger_posting_id"]
        for line in lines
        if line["recorded_at"] <= posted_through and str(line["book_code"]).strip() in books
    }
    assert reversal_ids <= by_time  # the timestamp rule selects the reversal itself
    assert len([line for line in lines if line["subledger_posting_id"] in by_time]) > len(earlier)
    # The position rule: R's seal is later than the stored position of every book it posts to.
    seals = _seals(k11, contract_id)
    positions = payload["posted_through_seq"]
    assert set(positions) == {seals[pid][0] for pid in reversal_ids} == books
    assert all(seals[pid][1] > positions[seals[pid][0]] for pid in reversal_ids)
    reversed_set = _by_position(seals, positions)
    assert reversed_set == {line["subledger_posting_id"] for line in earlier}
    assert reversed_set.isdisjoint(reversal_ids)
    derived = [line for line in lines if line["subledger_posting_id"] in reversed_set]
    assert len(derived) == payload["posted_line_count"] == len(earlier)
    conserved = _conserved(lines, reversed_set | reversal_ids)
    assert conserved and all(total == 0 for total in conserved.values()), conserved
    assert any(total != 0 for total in _conserved(lines, reversed_set).values())
    postings = k11.place.rows(
        select(subledger_posting.c.reverses_posting_id, subledger_posting.c.description).where(
            subledger_posting.c.id.in_(sorted(reversal_ids))
        )
    )
    assert all(
        row["reverses_posting_id"] is None
        and f"chain positions {positions}" in str(row["description"])
        for row in postings
    )
    executed = k11.place.rows(
        select(audit_event.c.detail).where(
            audit_event.c.object_id == contract_id, audit_event.c.action == "contract.void_executed"
        )
    )
    assert [
        (row["detail"]["posted_line_count"], row["detail"]["posted_through_seq"])
        for row in executed
    ] == [(len(earlier), positions)]
    (request,) = _requests(k11, contract_id)
    assert request["status"] == "APPROVED"


def test_d98_99b_population_mismatch_refuses_the_execution_by_name(
    k11: K11World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-98 99b: under the execution's locks the approval derives the reversed population from the
    stored position and refuses ``CUTOFF_POPULATION_MISMATCH`` (409 ``stale-approval``) when its
    line count departs from the approved count — nothing appended, nothing posted, the request
    still pending. The departure is forced at the module boundary (``reversed_population``); no
    production seam."""
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    booked = delivered_k11(k11)
    group_id = UUID(str(booked.combination_group["id"]))
    computed(k11.place, group_id)
    contract_id = UUID(str(booked.contract["id"]))
    _, head = _header(k11, contract_id)
    before = _lines(k11, contract_id)
    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    real = void_module.reversed_population

    def short_by_one(session: Any, cid: UUID, positions: Any) -> tuple[Any, int]:
        found, count = real(session, cid, positions)
        return found, count - 1

    monkeypatch.setattr(void_module, "reversed_population", short_by_one)
    assert approve(k11.app, request_id, k11.priya).status_code == 200
    refused = approve(k11.app, request_id, k11.marcus)
    assert (refused.status_code, slug(refused)) == (409, "stale-approval"), refused.text
    assert refused.json()["code"] == "CUTOFF_POPULATION_MISMATCH"
    assert "was approved over" in refused.json()["detail"]
    assert _header(k11, contract_id) == ("ACTIVE", head)
    assert _lines(k11, contract_id) == before
    assert _void_reversal_ids(k11, group_id) == set()
    (request,) = _requests(k11, contract_id)
    assert request["status"] == "PENDING"


def test_d98_101c_101d_void_approval_locks_then_revalidates_before_its_first_write(
    k11: K11World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-98 101c / 101d(2) at the re-merge on main d3166d0a: the request and the approval take the
    kernel helper ``lock_group_then_contract`` (the combination group, then the contract row; the
    ruled order, membership re-verified), and the approval hook calls the engine's
    ``assert_fresh_basis`` after those locks and before its first write (the SYSTEM append) —
    recorded through the module boundaries, no production seam."""
    rhea = _reviewer(k11, clock, "rhea", "revenue_accountant", "revenue_reviewer")
    booked = delivered_k11(k11)
    group_id = UUID(str(booked.combination_group["id"]))
    computed(k11.place, group_id)
    contract_id = UUID(str(booked.contract["id"]))
    _, head = _header(k11, contract_id)
    requested = _request_void(k11.app, rhea, contract_id, head, "DUPLICATE")
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    order: list[str] = []
    real_lock = void_module.lock_group_then_contract
    real_fresh = void_module.approvals.assert_fresh_basis
    real_append = void_module.append_events

    def lock(session: Any, cid: UUID, **kwargs: Any) -> Any:
        order.append("locks")
        return real_lock(session, cid, **kwargs)

    def fresh(uow: Any, rid: UUID) -> None:
        order.append("fresh")
        real_fresh(uow, rid)

    def append(*args: Any, **kwargs: Any) -> Any:
        order.append("append")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(void_module, "lock_group_then_contract", lock)
    monkeypatch.setattr(void_module.approvals, "assert_fresh_basis", fresh)
    monkeypatch.setattr(void_module, "append_events", append)
    clock.advance(timedelta(minutes=1))
    assert approve(k11.app, request_id, k11.priya).status_code == 200
    assert order == []  # the first step applies nothing
    assert approve(k11.app, request_id, k11.marcus).status_code == 200
    assert order == ["locks", "fresh", "append"]
    assert _header(k11, contract_id) == ("VOIDED", head + 1)
    assert _void_reversal_ids(k11, group_id)
