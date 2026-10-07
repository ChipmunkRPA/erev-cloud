"""Activation checklist, approval routing and unmapped-product blocking (04 table 15.4-I, §16.1
contract commands, §16.14 API-S-ActivationChecklist, §15.2 ``activation-checklist-failed``; PRD
SM-02, BR-CON-01, §2.5 routing rows ``CONTRACT_ACTIVATION``, IMP-09, IMP-100 to IMP-105, ERR-31;
dev-guide DG-CMD-09; legacy 01 §7.3 TC-setup-20; 03 REQ-CON-005, REQ-CON-006, REQ-REF-014;
BUILD_SPEC CTR-9, BS3-D-12; controls CTL-003, CTL-004, CTL-005).

Worlds: ``support.factories.j03_world`` (PRD WLD-X-23, ``SF-ORD-20417``) for the checklist and the
distinct review; ``support.factories.seat_world`` (AVM-US, USD) for routing. Maya (Revenue
Accountant) books, records Step 1 and submits; Marcus (Controller; MFA) reviews judgement records
and holds the Controller step; Priya is given Revenue Reviewer for ``contract.approve``. The
computations run ``erev_engine.compute``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    exception_item,
    role,
    schedule_line,
    subledger_line,
)
from erev_api.domain.contracts.commands import book_contract
from erev_api.enums import ApprovalSubjectType, PrincipalKind, RuleSetKind, SourceSystem
from erev_api.events.payloads import ContractBookedV1
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.api_clients import access_approver, issued_client
from support.db import TestDatabase
from support.factories import (
    IMPLEMENTATION_PLUS,
    J03World,
    SeatWorld,
    booked_contract,
    customer_id,
    j03_world,
    k09_body,
    seat_body,
    seat_line,
    seat_world,
    sf_ord_20417_body,
    step1_criteria,
)
from support.http import call
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, fields, get, new_product, post, put, reject, slug
from support.rows import publish_rule_set
from support.worlds import estimate_version_ready

CONTRACTS = "/api/v1/contracts"
JUDGEMENTS = "/api/v1/judgements"
SUGGESTIONS = "/api/v1/combination-suggestions"
EVENTS = "/api/v1/contracts/{contract_id}/events"
API_CLIENTS = "/api/v1/api-clients"
OAUTH_PATH = "/api/v1/oauth/token"
APPROVAL_HEADER = "x-erev-approval-request"
HARDWARE_X = "Hardware X"
ZERO_SEAT = "AVM-SEAT-ZERO"
RATIONALE = "Separate purchasing entities; negotiated independently."
REVIEW_RATIONALE = "Customer can benefit with readily available resources (606-10-25-19)."
# ``event.record``: the integration records Step 1 itself, so every event of its contract's
# stream is its own (supervisor ruling R-38 (i)).
SALESFORCE_SCOPES = ("contract.create", "contract.read", "event.record")
CODES = (
    "MANDATORY_FIELDS",
    "SOURCE_REFERENCE",
    "PRODUCT_TEMPLATE_SSP",
    "DISTINCT_REVIEW",
    "COMBINATION_SUGGESTIONS",
    "JUDGEMENT_RECORDS",
    "STEP1_RECORD",
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files, unpriced=(HARDWARE_X,), zero_priced=(ZERO_SEAT,))


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    return j03_world(app, keyring, clock, files)


# --- helpers -------------------------------------------------------------------------------------


def _created(app: FastAPI, actor: Actor, body: dict[str, Any]) -> UUID:
    created = post(app, CONTRACTS, actor, body)
    assert created.status_code == 201, created.text
    return UUID(str(created.json()["id"]))


def _checklist(app: FastAPI, actor: Actor, contract_id: UUID) -> list[tuple[str, bool, str | None]]:
    shown = get(app, f"{CONTRACTS}/{contract_id}/activation-checklist", actor)
    assert shown.status_code == 200, shown.text
    return [(item["code"], item["passed"], item["detail"]) for item in shown.json()["items"]]


def _passed(app: FastAPI, actor: Actor, contract_id: UUID) -> dict[str, bool]:
    return {code: passed for code, passed, _ in _checklist(app, actor, contract_id)}


def _submit(app: FastAPI, actor: Actor, contract_id: UUID, head: int) -> Any:
    return post(
        app, f"{CONTRACTS}/{contract_id}/submit-activation", actor, {}, if_match=f'"s{head}"'
    )


def _reviewed_record(
    app: FastAPI,
    preparer: Actor,
    reviewer: Actor,
    contract_id: UUID,
    topic: str = "COLLECTIBILITY",
    questionnaire: dict[str, Any] | None = None,
    *,
    book: str = "ASC606",
) -> str:
    body: dict[str, Any] = {
        "topic": topic,
        "subject_type": "contract",
        "subject_id": str(contract_id),
        "book": book,
        "conclusion": "Collection of the consideration is probable.",
        "rationale": "Credit review of the customer and its payment history.",
        # The five criteria of a Step 1 review (supervisor rulings R-113 (f), R-115 (f)).
        "questionnaire": {"criteria": step1_criteria(topic), **(questionnaire or {})},
    }
    created = post(app, JUDGEMENTS, preparer, body)
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(app, f"{JUDGEMENTS}/{record_id}/submit", preparer, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], reviewer)
    assert approved.status_code == 200, approved.text
    return record_id


def _assessed(record_id: str) -> dict[str, Any]:
    """The body of a probable ``COLLECTIBILITY_ASSESSED`` citing the reviewed record."""
    return {
        "events": [
            {
                "event_type": "COLLECTIBILITY_ASSESSED",
                "effective_date": "2026-09-01",
                "payload": {
                    "book": "ASC606",
                    "is_probable": True,
                    "judgement_record_id": record_id,
                },
            }
        ]
    }


def _step1(app: FastAPI, preparer: Actor, reviewer: Actor, contract_id: UUID, head: int) -> int:
    """A reviewed COLLECTIBILITY record and a probable ``COLLECTIBILITY_ASSESSED``; the new head."""
    record_id = _reviewed_record(app, preparer, reviewer, contract_id)
    appended = post(
        app,
        EVENTS.format(contract_id=contract_id),
        preparer,
        _assessed(record_id),
        if_match=f'"s{head}"',
    )
    assert appended.status_code == 201, appended.text
    return head + 1


def _bearer(token: str, head: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"k-{uuid4()}",
        "If-Match": f'"s{head}"',
    }


def _step1_by_integration(world: SeatWorld, token: str, contract_id: UUID, head: int) -> int:
    """Step 1 of an integration's contract (supervisor ruling R-38 (i)): people write and review
    the COLLECTIBILITY judgement record — an approval of its own, outside the stream — and the
    integration records the probable ``COLLECTIBILITY_ASSESSED`` that cites it, so every event of
    the stream is the integration's. The new head."""
    record_id = _reviewed_record(world.app, world.place.author, world.marcus, contract_id)
    appended = call(
        world.app,
        "POST",
        EVENTS.format(contract_id=contract_id),
        json=_assessed(record_id),
        headers=_bearer(token, head),
    )
    assert appended.status_code == 201, appended.text
    return head + 1


def _header(world: SeatWorld | J03World, contract_id: UUID) -> tuple[str, int]:
    row = world.place.rows(
        select(contract.c.status, contract.c.head_stream_version).where(
            contract.c.id == contract_id
        )
    )[0]
    return str(row["status"]), int(row["head_stream_version"])


def _event_types(world: SeatWorld | J03World, contract_id: UUID) -> list[str]:
    rows = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [str(row["event_type"]) for row in rows]


def _requests(world: SeatWorld, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            approval_request.c.id,
            approval_request.c.status,
            approval_request.c.flags,
            approval_request.c.amount_functional,
            approval_request.c.amount_currency,
            approval_request.c.impact_preview_sha256,
        )
        .where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == contract_id,
        )
        .order_by(approval_request.c.request_no)
    )


def _steps(world: SeatWorld, request_id: str) -> list[tuple[int, str, UUID | None, str]]:
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


def _seat_contract(
    world: SeatWorld, external_id: str, *, seats: str, price: str, product: str | None = None
) -> dict[str, Any]:
    line = seat_line("O1", seats=seats, price=price, start="2026-09-01", end="2027-08-31")
    if product is not None:
        line["product_code"] = product
    return seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )


# --- checklist -----------------------------------------------------------------------------------


def test_checklist_items(j03: J03World, clock: FrozenClock) -> None:
    body = sf_ord_20417_body(j03.customer_id)
    del body["document_ref"]
    contract_id = _created(j03.app, j03.place.author, body)

    shown = get(j03.app, f"{CONTRACTS}/{contract_id}/activation-checklist", j03.place.author)
    assert shown.status_code == 200, shown.text
    assert datetime.fromisoformat(shown.json()["evaluated_at"]) == clock.now()
    assert _checklist(j03.app, j03.place.author, contract_id) == [
        ("MANDATORY_FIELDS", True, None),
        ("SOURCE_REFERENCE", False, "No contract reference is recorded."),
        ("PRODUCT_TEMPLATE_SSP", True, None),
        ("DISTINCT_REVIEW", False, "Distinct review not recorded for O2 (AVM-IMPL-PLUS)."),
        ("COMBINATION_SUGGESTIONS", True, None),
        ("JUDGEMENT_RECORDS", True, None),
        ("STEP1_RECORD", False, "Step 1 review not recorded."),
    ]

    refused = _submit(j03.app, j03.place.author, contract_id, 1)
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "activation-checklist-failed"
    assert fields(refused) == [
        (None, "SOURCE_REFERENCE"),
        (None, "DISTINCT_REVIEW"),
        (None, "STEP1_RECORD"),
    ]
    assert refused.json()["detail"] == (
        "3 checklist items have not passed: SOURCE_REFERENCE, DISTINCT_REVIEW, STEP1_RECORD."
    )
    assert _header(j03, contract_id) == ("DRAFT", 1)
    assert _event_types(j03, contract_id) == ["CONTRACT_BOOKED"]


def test_open_suggestion_blocks_activation(seats: SeatWorld) -> None:
    maya = seats.place.author
    k09 = _created(seats.app, maya, k09_body(seats.customers["C-09"]))
    assert _passed(seats.app, maya, k09)["COMBINATION_SUGGESTIONS"] is True
    other = _seat_contract(seats, "SF-ORD-10420", seats="10", price="24000.00")
    other["inception_date"] = "2026-09-10"
    _created(seats.app, maya, other)

    items = {code: (passed, detail) for code, passed, detail in _checklist(seats.app, maya, k09)}
    assert items["COMBINATION_SUGGESTIONS"] == (
        False,
        "Combination suggestion with SF-ORD-10420 is open.",
    )
    listed = get(seats.app, SUGGESTIONS, maya, {"contract": str(k09)})
    assert listed.status_code == 200, listed.text
    (suggestion,) = listed.json()["items"]
    dismissed = post(
        seats.app, f"{SUGGESTIONS}/{suggestion['id']}/dismiss", maya, {"rationale": RATIONALE}
    )
    assert dismissed.status_code == 200, dismissed.text
    assert _passed(seats.app, maya, k09)["COMBINATION_SUGGESTIONS"] is True


def test_distinct_review_creates_judgement(j03: J03World) -> None:
    maya = j03.place.author
    body = sf_ord_20417_body(j03.customer_id, external_id="SF-ORD-20418")
    platform, implementation = body["lines"]
    body["lines"] = [
        {**implementation, "obligation_key": "O1"},
        {**platform, "obligation_key": "O2"},
    ]
    contract_id = _created(j03.app, maya, body)
    items = {
        code: (passed, detail) for code, passed, detail in _checklist(j03.app, maya, contract_id)
    }
    assert items["DISTINCT_REVIEW"] == (
        False,
        f"Distinct review not recorded for O1 ({IMPLEMENTATION_PLUS}).",
    )

    path = f"{CONTRACTS}/{contract_id}/obligations/O1/distinct-review"
    unnamed = post(j03.app, path, maya, {"distinctness": "nondistinct", "rationale": "Integrated."})
    assert unnamed.status_code == 422, unnamed.text
    assert fields(unnamed) == [("integrates_into_obligation_key", "T-CON-19")]
    unknown = post(
        j03.app,
        f"{CONTRACTS}/{contract_id}/obligations/O9/distinct-review",
        maya,
        {"distinctness": "distinct", "rationale": REVIEW_RATIONALE},
    )
    assert unknown.status_code == 404, unknown.text

    recorded = post(
        j03.app, path, maya, {"distinctness": "distinct", "rationale": REVIEW_RATIONALE}
    )
    assert recorded.status_code == 201, recorded.text
    created = recorded.json()
    assert set(created) == {"judgement_record_id", "approval_request_id"}
    assert recorded.headers["Location"] == f"/api/v1/judgements/{created['judgement_record_id']}"
    record = get(j03.app, f"{JUDGEMENTS}/{created['judgement_record_id']}", maya).json()
    obligation_id = record["subject_id"]
    assert (
        record["topic"],
        record["subject_type"],
        record["contract_id"],
        record["status"],
        record["rationale"],
        record["codification_refs"],
        record["questionnaire"],
        record["approval_request_id"],
    ) == (
        "POB_DISTINCT_OVERRIDE",
        "obligation",
        str(contract_id),
        "SUBMITTED",
        REVIEW_RATIONALE,
        ["606-10-25-19", "606-10-25-21"],
        {"obligation_key": "O1", "distinctness": "distinct"},
        created["approval_request_id"],
    )
    request = j03.place.rows(
        select(approval_request.c.subject_type, approval_request.c.subject_id).where(
            approval_request.c.id == UUID(created["approval_request_id"])
        )
    )[0]
    assert (str(request["subject_type"]), str(request["subject_id"])) == (
        "JUDGEMENT_RECORD",
        created["judgement_record_id"],
    )
    pending = {
        code: (passed, detail) for code, passed, detail in _checklist(j03.app, maya, contract_id)
    }
    assert pending["DISTINCT_REVIEW"][0] is False
    assert pending["JUDGEMENT_RECORDS"] == (
        False,
        "Judgement record required: POB distinct override.",
    )

    approved = approve(j03.app, created["approval_request_id"], j03.marcus)
    assert approved.status_code == 200, approved.text
    reviewed = _passed(j03.app, maya, contract_id)
    assert (reviewed["DISTINCT_REVIEW"], reviewed["JUDGEMENT_RECORDS"]) == (True, True)
    assert obligation_id != str(contract_id)


# --- routing -------------------------------------------------------------------------------------


def test_manual_contract_routes_to_revenue_reviewer(seats: SeatWorld) -> None:
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    contract_id = _created(
        seats.app, maya, _seat_contract(seats, "SF-ORD-10430", seats="50", price="120000.00")
    )
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    assert _passed(seats.app, maya, contract_id) == dict.fromkeys(CODES, True)

    submitted = _submit(seats.app, maya, contract_id, head)
    assert submitted.status_code == 200, submitted.text
    assert (submitted.json()["status"], submitted.json()["head_stream_version"]) == (
        "PENDING_REVIEW",
        2,
    )
    assert submitted.headers["ETag"] == '"s2"'
    request_id = submitted.headers[APPROVAL_HEADER]
    (request,) = _requests(seats, contract_id)
    # Item ACT-FLAGS-1 (04 §16.10 rev 1.287; the supervisor's ruling of 2026-10-02, conditions 2
    # and 3): the contract Maya books states neither of the two terms — the booking form does not
    # state them yet — and it is the first of its product in this workspace.
    assert (
        str(request["id"]),
        str(request["status"]),
        list(request["flags"]),
        Decimal(request["amount_functional"]),
        str(request["amount_currency"]).strip(),
    ) == (
        request_id,
        "PENDING",
        ["ABOVE_THRESHOLD", "MANUAL_ENTRY", "NEW_SKU", "TERMS_NOT_STATED"],
        Decimal("120000.00"),
        "USD",
    )
    assert request["impact_preview_sha256"] is not None
    assert _steps(seats, request_id) == [(1, "contract.approve", None, "ACTIVE")]
    # 04 §16.10 rev 1.126: an ordinary activation moves no criteria-met book and states no catch-up.
    stated = get(seats.app, f"/api/v1/approvals/{request_id}", seats.priya).json()
    assert stated["impact_preview"]["summary"]["criteria_met"] is None
    assert stated["impact_preview"]["summary"]["catch_up_total"] is None
    shown = get(seats.app, f"{CONTRACTS}/{contract_id}", maya).json()
    assert (shown["status"], shown["steps"][0]["state"]) == ("PENDING_REVIEW", "IN_REVIEW")
    # [J] L4-1-Q-18: no event, so the stored header stays DRAFT while the request is pending.
    assert _header(seats, contract_id) == ("DRAFT", 2)
    audits = seats.place.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_id == contract_id,
            audit_event.c.action == "contract.pending_review",
        )
    )
    assert [(row["before"]["status"], row["after"]["status"]) for row in audits] == [
        ("DRAFT", "PENDING_REVIEW")
    ]
    repeated = _submit(seats.app, maya, contract_id, head)
    assert (repeated.status_code, slug(repeated)) == (409, "invalid-transition")

    approved = approve(seats.app, request_id, seats.priya)
    assert approved.status_code == 200, approved.text
    active = get(seats.app, f"{CONTRACTS}/{contract_id}", maya).json()
    assert (active["status"], active["head_stream_version"]) == ("ACTIVE", 3)
    assert active["activated_at"] is not None
    checklist = active["activation_checklist"]
    assert [(item["code"], item["passed"], item["detail"]) for item in checklist["items"]] == [
        (code, True, None) for code in CODES
    ]
    assert checklist["evaluated_at"] is not None
    events = seats.place.rows(
        select(
            contract_event.c.event_type,
            contract_event.c.origin,
            contract_event.c.approval_request_id,
        )
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    assert [(str(row["event_type"]), str(row["origin"])) for row in events] == [
        ("CONTRACT_BOOKED", "UI"),
        ("COLLECTIBILITY_ASSESSED", "UI"),
        ("CONTRACT_ACTIVATED", "SYSTEM"),
    ]
    assert str(events[-1]["approval_request_id"]) == request_id
    computed = seats.place.rows(
        select(contract_computation.c.status, contract_computation.c.stream_heads)
        .where(
            contract_computation.c.combination_group_id == UUID(active["combination_group"]["id"])
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )[0]
    assert (str(computed["status"]), computed["stream_heads"][str(contract_id)]) == ("SUCCEEDED", 3)
    decided = seats.place.rows(
        select(approval_decision.c.approver_id, approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert [(row["approver_id"], str(row["decision"])) for row in decided] == [
        (seats.priya.member.user_id, "APPROVE")
    ]


def test_one_million_needs_controller_second_step(seats: SeatWorld) -> None:
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    contract_id = _created(
        seats.app, maya, _seat_contract(seats, "SF-ORD-10431", seats="400", price="1000000.00")
    )
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    submitted = _submit(seats.app, maya, contract_id, head)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "PENDING_REVIEW"
    request_id = submitted.headers[APPROVAL_HEADER]
    (request,) = _requests(seats, contract_id)
    # ``NEW_SKU`` and ``TERMS_NOT_STATED``: item ACT-FLAGS-1, as in the test above.
    assert list(request["flags"]) == [
        "ABOVE_CONTROLLER_THRESHOLD",
        "ABOVE_THRESHOLD",
        "MANUAL_ENTRY",
        "NEW_SKU",
        "TERMS_NOT_STATED",
    ]
    controller = seats.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert _steps(seats, request_id) == [
        (1, "contract.approve", None, "ACTIVE"),
        (2, "contract.approve", controller, "WAITING"),
    ]

    first = approve(seats.app, request_id, seats.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    # The second step is held by a Controller: a Revenue Reviewer without the role cannot decide it.
    refused = approve(seats.app, request_id, seats.priya)
    assert (refused.status_code, slug(refused)) == (403, "forbidden")
    assert refused.json()["detail"] == "This approval step needs a holder of the Controller role."
    assert get(seats.app, f"{CONTRACTS}/{contract_id}", maya).json()["status"] == "PENDING_REVIEW"

    second = approve(seats.app, request_id, seats.marcus)
    assert second.status_code == 200, second.text
    assert _header(seats, contract_id) == ("ACTIVE", 3)


def _publish_auto_approval(world: SeatWorld) -> tuple[UUID, UUID]:
    """PRD §2.5 ``AUTO-CON-01`` in a PUBLISHED ``AUTO_APPROVAL`` rule set version."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        version_id, rule_ids = publish_rule_set(
            session,
            tenant_id=world.place.tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="AVM-AUTO-APPROVAL",
            rules=[
                {
                    "rule_key": "AUTO-CON-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "CONTRACT_ACTIVATION"},
                        {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    return version_id, rule_ids["AUTO-CON-01"]


def _salesforce_token(
    world: SeatWorld, scopes: tuple[str, ...] = SALESFORCE_SCOPES
) -> tuple[UUID, str]:
    """API client ``svc-salesforce`` and a token of it. The client's scopes are an access grant
    (supervisor ruling R-38 (iii)): Marcus requests it, Ada — a second Tenant Admin — approves
    the grant, and Marcus issues its secret."""
    ada = access_approver(world.app, world.place.clock, world.marcus.member, "ada")
    client = issued_client(
        world.app,
        world.marcus,
        {"name": "svc-salesforce", "scopes": list(scopes)},
        approver=ada,
    )
    issued = call(
        world.app,
        "POST",
        OAUTH_PATH,
        data={"grant_type": "client_credentials"},
        auth=(client["client_id"], client["client_secret"]),
    )
    assert issued.status_code == 200, issued.text
    return UUID(str(client["id"])), str(issued.json()["access_token"])


def _api_client(
    world: SeatWorld, client_id: UUID, held: tuple[str, ...] = SALESFORCE_SCOPES
) -> Principal:
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = dict.fromkeys(held, "*")
    return Principal(
        kind=PrincipalKind.API_CLIENT,
        id=client_id,
        tenant_id=world.place.tenant_id,
        membership_id=None,
        display_name="svc-salesforce",
        roles=(),
        permissions=frozenset(held),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


# Item ACT-FLAGS-1 (04 §16.3, §16.10 rev 1.287): an integration's standard item states that its
# contract holds no acceptance clause and no side letter, and stands on a product the workspace
# knows — a booking that states neither term, and a product's first activation, wait for a person.
TERMS_STATED = MappingProxyType({"acceptance_clause": False, "side_letter": False})
KNOWN_ORDER = "SF-ORD-10001"


def _seat_product_known(world: SeatWorld) -> None:
    """The seat product is known to the workspace: a fixture contract of it is ACTIVE (booked and
    activated without a request), under a customer of its own so that no combination is suggested
    with a contract of a test. Made once a world."""
    if world.place.rows(select(contract.c.id).where(contract.c.external_id == KNOWN_ORDER)):
        return
    buyer = customer_id(
        world.app, world.place.author, code="C-77", name="Known Products GmbH (Demo)"
    )
    line = seat_line("K1", seats="1", price="2400.00", start="2026-01-01", end="2026-12-31")
    booked_contract(
        world.place,
        seat_body(buyer, external_id=KNOWN_ORDER, inception="2026-01-01", lines=[line]),
        activate=True,
    )


def _booked_by_salesforce(world: SeatWorld, client_id: UUID, external_id: str) -> UUID:
    """A seat contract of USD 30,000.00 booked by ``svc-salesforce`` through the adapter path, with
    both terms stated false, on a product the workspace knows (``_seat_product_known``)."""
    _seat_product_known(world)
    body = {
        **_seat_contract(world, external_id, seats="12", price="30000.00"),
        **TERMS_STATED,
    }
    with world.place.uow(_api_client(world, client_id)) as uow:
        booked = book_contract(
            uow,
            body=ContractBookedV1.model_validate(body),
            origin="ADAPTER",
            source_system=SourceSystem.SALESFORCE,
        )
        uow.commit()
    return UUID(str(booked.contract["id"]))


def _authors(world: SeatWorld, contract_id: UUID) -> list[tuple[str, str]]:
    """(event type, author kind) of the contract's stream, in stream order."""
    rows = world.place.rows(
        select(contract_event.c.event_type, contract_event.c.created_by_kind)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [(str(row["event_type"]), str(row["created_by_kind"])) for row in rows]


def test_salesforce_originated_contract_auto_approves(seats: SeatWorld) -> None:
    """REQ-CON-006; PRD §2.5 ``AUTO-CON-01``. Supervisor ruling R-38 (i): the contract is
    system-originated by its CONTENT — the integration booked it and recorded Step 1, so no event
    of its stream is a person's. (Before the ruling a person recorded Step 1 here; that case is
    ``test_r38_integration_draft_a_person_changed_waits_for_a_person``.)"""
    version_id, rule_id = _publish_auto_approval(seats)
    client_id, token = _salesforce_token(seats)
    contract_id = _booked_by_salesforce(seats, client_id, "SF-ORD-10440")
    head = _step1_by_integration(seats, token, contract_id, 1)
    assert _authors(seats, contract_id) == [
        ("CONTRACT_BOOKED", "API_CLIENT"),
        ("COLLECTIBILITY_ASSESSED", "API_CLIENT"),
    ]

    submitted = call(
        seats.app,
        "POST",
        f"{CONTRACTS}/{contract_id}/submit-activation",
        json={},
        headers=_bearer(token, head),
    )
    assert submitted.status_code == 200, submitted.text
    assert (submitted.json()["status"], submitted.json()["source_system"]) == (
        "ACTIVE",
        "SALESFORCE",
    )
    request_id = submitted.headers[APPROVAL_HEADER]
    (request,) = _requests(seats, contract_id)
    assert (str(request["status"]), list(request["flags"])) == ("APPROVED", [])
    decisions = seats.place.rows(
        select(
            approval_decision.c.decision,
            approval_decision.c.approver_kind,
            approval_decision.c.auto_rule_set_version_id,
            approval_decision.c.auto_rule_id,
        ).where(approval_decision.c.approval_request_id == UUID(request_id))
    )
    assert [
        (
            str(row["decision"]),
            str(row["approver_kind"]),
            row["auto_rule_set_version_id"],
            row["auto_rule_id"],
        )
        for row in decisions
    ] == [("AUTO_APPROVE", "SYSTEM", version_id, rule_id)]
    created_by = seats.place.rows(
        select(contract.c.created_by_kind, contract.c.source_system).where(
            contract.c.id == contract_id
        )
    )[0]
    assert (str(created_by["created_by_kind"]), str(created_by["source_system"])) == (
        "API_CLIENT",
        "SALESFORCE",
    )
    assert _header(seats, contract_id) == ("ACTIVE", 3)
    assert _event_types(seats, contract_id)[-1] == "CONTRACT_ACTIVATED"


def test_r38_integration_draft_a_person_changed_waits_for_a_person(seats: SeatWorld) -> None:
    """Supervisor ruling R-38 (i) (REQ-CON-006 rev 1.19; 04 §16.10 rev 1.104): system-originated
    is a fact of the content, not of who submits. ``svc-salesforce`` books two drafts under the
    published rule ``AUTO-CON-01``, which approves an untouched one (the test above). On the
    first a person records an event; the second a person replaces — a person's terms under the
    integration's ``source_system``. The integration then submits both: each activation carries
    ``MANUAL_ENTRY`` and waits for a reviewer, and no rule decides it. Before the ruling the flag
    read ``contract.source_system`` alone, so the rule approved a person's content unseen."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    _publish_auto_approval(seats)
    client_id, token = _salesforce_token(seats)

    # (1) A person records Step 1 on the integration's draft.
    recorded = _booked_by_salesforce(seats, client_id, "SF-ORD-10441")
    recorded_head = _step1(seats.app, maya, seats.marcus, recorded, 1)
    assert _authors(seats, recorded) == [
        ("CONTRACT_BOOKED", "API_CLIENT"),
        ("COLLECTIBILITY_ASSESSED", "USER"),
    ]
    # (2) A person replaces the integration's draft; the integration records Step 1 afterwards.
    replaced = _booked_by_salesforce(seats, client_id, "SF-ORD-10442")
    swapped = post(
        seats.app,
        f"{CONTRACTS}/{replaced}/replace-draft",
        maya,
        _seat_contract(seats, "SF-ORD-10442", seats="12", price="90000.00"),
        if_match='"s1"',
    )
    assert swapped.status_code == 200, swapped.text
    replaced_head = _step1_by_integration(seats, token, replaced, 3)
    assert _authors(seats, replaced) == [
        ("CONTRACT_BOOKED", "API_CLIENT"),
        ("EVENT_VOIDED", "SYSTEM"),
        ("CONTRACT_BOOKED", "USER"),
        ("COLLECTIBILITY_ASSESSED", "API_CLIENT"),
    ]

    # Item ACT-FLAGS-1 (04 §16.10 rev 1.287): the integration's booking states both terms; the
    # person's replacement — the booking form's body — states neither, and a draft states the
    # terms of its latest booking.
    for contract_id, head, flags in (
        (recorded, recorded_head, ["MANUAL_ENTRY"]),
        (replaced, replaced_head, ["MANUAL_ENTRY", "TERMS_NOT_STATED"]),
    ):
        submitted = call(
            seats.app,
            "POST",
            f"{CONTRACTS}/{contract_id}/submit-activation",
            json={},
            headers=_bearer(token, head),
        )
        assert submitted.status_code == 200, submitted.text
        assert (submitted.json()["status"], submitted.json()["source_system"]) == (
            "PENDING_REVIEW",
            "SALESFORCE",
        )
        (request,) = _requests(seats, contract_id)
        assert (str(request["status"]), list(request["flags"])) == ("PENDING", flags)
        assert (
            seats.place.rows(
                select(approval_decision.c.decision).where(
                    approval_decision.c.approval_request_id == request["id"]
                )
            )
            == []
        )
        assert _header(seats, contract_id) == ("DRAFT", head)
        approved = approve(seats.app, str(request["id"]), seats.priya)
        assert approved.status_code == 200, approved.text
        assert _header(seats, contract_id) == ("ACTIVE", head + 1)


def test_r38_content_an_approval_put_in_force_waits_for_a_person(seats: SeatWorld) -> None:
    """Supervisor rulings R-38 (i) and R-41 (7), the path the second independent review found: a
    person's content also reaches an integration's draft through an approval of its own, and the
    SYSTEM principal appends it — no event of the stream is written by a person. Maya adds a
    variable-consideration estimate to the draft ``svc-salesforce`` booked and Priya approves it:
    ``ESTIMATE_CHANGED`` is a SYSTEM event that names the approval request a USER prepared. The
    integration then records Step 1 and submits. The activation carries ``MANUAL_ENTRY`` and waits
    for a reviewer; read by author kind alone, the stream looked system-originated and rule
    ``AUTO-CON-01`` approved a contract whose price a person had changed."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    _publish_auto_approval(seats)
    client_id, token = _salesforce_token(seats)
    contract_id = _booked_by_salesforce(seats, client_id, "SF-ORD-10443")

    element = post(
        seats.app,
        f"{CONTRACTS}/{contract_id}/estimates",
        maya,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": "BONUS-SF-01",
            "vc_element_type": "BONUS",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert element.status_code == 201, element.text
    version = post(
        seats.app,
        f"/api/v1/estimates/{element.json()['id']}/versions",
        maya,
        {
            "effective_date": "2026-09-01",
            "scenarios": [
                {"outcome": "Adoption bonus earned", "amount": "5000.00"},
                {"outcome": "Not earned", "amount": "0.00"},
            ],
            "unconstrained_amount": "5000.00",
            "most_conservative_amount": "0.00",
            "constrained_amount": "5000.00",
            "rationale": "The customer's adoption target is highly likely to be met.",
        },
    )
    assert version.status_code == 201, version.text
    # What the submission asks of a version (04 §16.14 rev 1.241): its evidence and the reviewed
    # CONSTRAINT record of the element — a record of the version, which appends nothing to the
    # stream: the authors below stay the three they were.
    estimate_version_ready(
        seats.app,
        maya,
        str(version.json()["id"]),
        constraint_of="BONUS-SF-01",
        reviewer=seats.priya,
    )
    sent = post(
        seats.app,
        f"/api/v1/estimate-versions/{version.json()['id']}/submit",
        maya,
        {"comment": "Review"},
    )
    assert sent.status_code == 200, sent.text
    decided = approve(seats.app, str(sent.json()["approval_request_id"]), seats.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    head = _step1_by_integration(seats, token, contract_id, 2)
    # No author of the stream is a person: the person's content came through the approval.
    assert _authors(seats, contract_id) == [
        ("CONTRACT_BOOKED", "API_CLIENT"),
        ("ESTIMATE_CHANGED", "SYSTEM"),
        ("COLLECTIBILITY_ASSESSED", "API_CLIENT"),
    ]

    submitted = call(
        seats.app,
        "POST",
        f"{CONTRACTS}/{contract_id}/submit-activation",
        json={},
        headers=_bearer(token, head),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "PENDING_REVIEW"
    (request,) = _requests(seats, contract_id)
    # ``VARIABLE_CONSIDERATION``: item ACT-FLAGS-1 (04 §16.10 rev 1.287) — the contract holds an
    # estimated element of variable consideration, which by itself waits for a person.
    assert (str(request["status"]), list(request["flags"])) == (
        "PENDING",
        ["MANUAL_ENTRY", "VARIABLE_CONSIDERATION"],
    )
    assert (
        seats.place.rows(
            select(approval_decision.c.decision).where(
                approval_decision.c.approval_request_id == request["id"]
            )
        )
        == []
    )
    approved = approve(seats.app, str(request["id"]), seats.priya)
    assert approved.status_code == 200, approved.text
    assert _header(seats, contract_id)[0] == "ACTIVE"


@dataclass(frozen=True, slots=True)
class _Integration:
    """An API client that writes a contract's stream itself: it books the contract (origin
    ADAPTER, source SALESFORCE), records the Step 1 assessments and submits for activation with
    its bearer token — no person's event on the stream, no routing flag."""

    world: SeatWorld
    client_id: UUID
    token: str
    held: tuple[str, ...]

    def booked(self, customer: str, external_id: str) -> UUID:
        """A seat contract of 30,000.00 USD from 2026-09-01 to 2027-08-31, with both terms stated
        false, on a product the workspace knows."""
        _seat_product_known(self.world)
        line = seat_line("O1", seats="12", price="30000.00", start="2026-09-01", end="2027-08-31")
        body = {
            **seat_body(
                self.world.customers[customer],
                external_id=external_id,
                inception="2026-09-01",
                lines=[line],
            ),
            **TERMS_STATED,
        }
        principal = _api_client(self.world, self.client_id, self.held)
        with self.world.place.uow(principal) as uow:
            found = book_contract(
                uow,
                body=ContractBookedV1.model_validate(body),
                origin="ADAPTER",
                source_system=SourceSystem.SALESFORCE,
            )
            uow.commit()
        return UUID(str(found.contract["id"]))

    def send(self, path: str, body: dict[str, Any], head: int) -> Any:
        return call(
            self.world.app,
            "POST",
            path,
            json=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Idempotency-Key": f"k-{uuid4()}",
                "If-Match": f'"s{head}"',
            },
        )

    def assessed(self, contract_id: UUID, head: int, *items: dict[str, Any]) -> Any:
        return self.send(EVENTS.format(contract_id=contract_id), {"events": list(items)}, head)

    def submitted(self, contract_id: UUID, head: int) -> Any:
        return self.send(f"{CONTRACTS}/{contract_id}/submit-activation", {}, head)


def _integration(world: SeatWorld) -> _Integration:
    held = (*SALESFORCE_SCOPES, "event.record")
    client_id, token = _salesforce_token(world, held)
    return _Integration(world=world, client_id=client_id, token=token, held=held)


def _assessment(
    record_id: str, *, probable: bool, on: str = "2026-09-01", book: str = "ASC606"
) -> dict[str, Any]:
    return {
        "event_type": "COLLECTIBILITY_ASSESSED",
        "effective_date": on,
        "payload": {"book": book, "is_probable": probable, "judgement_record_id": record_id},
    }


def _decisions(world: SeatWorld, request_id: str) -> list[tuple[str, str, Any, Any]]:
    rows = world.place.rows(
        select(
            approval_decision.c.decision,
            approval_decision.c.approver_kind,
            approval_decision.c.auto_rule_set_version_id,
            approval_decision.c.auto_rule_id,
        ).where(approval_decision.c.approval_request_id == UUID(request_id))
    )
    return [
        (
            str(row["decision"]),
            str(row["approver_kind"]),
            row["auto_rule_set_version_id"],
            row["auto_rule_id"],
        )
        for row in rows
    ]


def _written_by(world: SeatWorld, contract_id: UUID) -> list[str]:
    rows = world.place.rows(
        select(contract_event.c.created_by_kind)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [str(row["created_by_kind"]) for row in rows]


def _book_statuses(world: SeatWorld, contract_id: UUID) -> dict[str, str]:
    """Book → the status of the contract's latest version in that book (singleton groups)."""
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    rows = world.place.rows(
        select(contract_version.c.book_code, contract_version.c.status_in_book)
        .where(contract_version.c.combination_group_id == group_id)
        .order_by(contract_version.c.version_no)
    )
    return {str(row["book_code"]): str(row["status_in_book"]) for row in rows}


def _offered(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bool, Any]]:
    """What ``submit_activation`` hands to ``approvals.submit`` for each activation request:
    (``auto_approval``, the routing decision it passes). ``submit`` applies the rule of a routing
    decision it is given (independent review of e40bf7c7, finding 9; ruling R-66 (9)), so a
    caller that added one would re-open auto-approval where the flag withholds it."""
    offered: list[tuple[bool, Any]] = []
    submit = approvals_engine.submit

    def observed(uow: Any, **members: Any) -> Any:
        if ApprovalSubjectType(members["subject_type"]) is ApprovalSubjectType.CONTRACT_ACTIVATION:
            offered.append((members["auto_approval"], members.get("routing_decision")))
        return submit(uow, **members)

    monkeypatch.setattr(approvals_engine, "submit", observed)
    return offered


def test_criteria_met_activation_is_never_auto_approved(
    seats: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-61 (c) (04 §16.1, §16.10 rev 1.126; PRD §2.5, SM-02 rev 1.55;
    REQ-PLT-016): a criteria-met activation is not a standard item. ``submit-activation`` offered
    every request without routing flags to the ``AUTO_APPROVAL`` rules, so for a contract an
    integration wrote — booked, assessed not probable (the not-a-contract gate) and re-assessed
    probable by an API client; 30,000.00 USD, no flags — the published rule approved the
    criteria-met activation at submission: criteria met and recognition with no person's
    decision on the activation. The request now stays PENDING until a person decides. Positive
    control: the same client's ordinary activation of a DRAFT contract is approved by the same
    published rule. The witness also pins what the command hands to ``approvals.submit``
    (``_offered``): ``auto_approval = False`` and NO routing decision of its own."""
    maya = seats.place.author
    offered = _offered(monkeypatch)
    assign(seats.priya.member, "revenue_reviewer")
    version_id, rule_id = _publish_auto_approval(seats)
    client = _integration(seats)

    # Positive control: the published rule approves this client's ordinary activation.
    standard = client.booked("C-02", "SF-ORD-10442")
    probable = _reviewed_record(seats.app, maya, seats.marcus, standard)
    recorded = client.assessed(standard, 1, _assessment(probable, probable=True))
    assert recorded.status_code == 201, recorded.text
    activated = client.submitted(standard, 2)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    (auto,) = _requests(seats, standard)
    assert (str(auto["status"]), list(auto["flags"])) == ("APPROVED", [])
    assert _decisions(seats, activated.headers[APPROVAL_HEADER]) == [
        ("AUTO_APPROVE", "SYSTEM", version_id, rule_id)
    ]
    assert offered == [(True, None)]

    # The same client's contract behind the not-a-contract gate, re-assessed probable on a
    # collectibility record reviewed after the gate (ruling R-77 (3)): every event of the stream
    # is the API client's.
    contract_id = client.booked("C-09", "SF-ORD-10441")
    not_probable = _reviewed_record(
        seats.app,
        maya,
        seats.marcus,
        contract_id,
        "NOT_A_CONTRACT",
        {"consideration_nonrefundable": False},
    )
    gated = client.assessed(contract_id, 1, _assessment(not_probable, probable=False))
    assert gated.status_code == 201, gated.text
    assert gated.json()["contract"]["status"] == "NOT_A_CONTRACT"
    seats.place.clock.advance(timedelta(minutes=1))
    met = _reviewed_record(seats.app, maya, seats.marcus, contract_id)
    reassessed = client.assessed(contract_id, 3, _assessment(met, probable=True, on="2026-09-10"))
    assert reassessed.status_code == 201, reassessed.text
    assert _header(seats, contract_id) == ("NOT_A_CONTRACT", 4)
    assert _written_by(seats, contract_id) == ["API_CLIENT"] * 4

    submitted = client.submitted(contract_id, 4)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]
    # The rule that approved the ordinary activation is not offered this request.
    assert offered == [(True, None), (False, None)]
    (request,) = _requests(seats, contract_id)
    assert (str(request["status"]), list(request["flags"])) == ("PENDING", [])
    assert _decisions(seats, request_id) == []
    assert _steps(seats, request_id) == [(1, "contract.approve", None, "ACTIVE")]
    assert submitted.json()["status"] == "PENDING_REVIEW"
    assert _header(seats, contract_id) == ("NOT_A_CONTRACT", 4)
    assert "CONTRACT_CRITERIA_MET" not in _event_types(seats, contract_id)
    postings = seats.place.scalar(
        select(func.count())
        .select_from(subledger_line)
        .where(subledger_line.c.contract_id == contract_id)
    )
    assert postings == 0

    # A person decides: criteria met and the activation are appended with the request id.
    approved = approve(seats.app, request_id, seats.priya)
    assert approved.status_code == 200, approved.text
    assert _header(seats, contract_id) == ("ACTIVE", 6)
    assert _event_types(seats, contract_id)[-2:] == ["CONTRACT_CRITERIA_MET", "CONTRACT_ACTIVATED"]
    assert _written_by(seats, contract_id) == ["API_CLIENT"] * 4 + ["SYSTEM"] * 2
    assert _decisions(seats, request_id) == [("APPROVE", "USER", None, None)]


def test_activation_that_leaves_a_book_not_a_contract_is_not_auto_approved(
    seats: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-77 (2), second half (REQ-PLT-016). Two books; ASC 606 assessed probable
    and IFRS 15 not probable, both dated the inception date. No gate follows (one book is
    probable), the checklist passes, and the activation leaves IFRS 15 NOT_A_CONTRACT — the
    engine decides per book. For a stream an integration wrote, without routing flags, the
    published rule approved that activation at submission: a contract whose books differ,
    activated with no person's decision. An activation is not offered to the auto-approval rules
    while the latest assessment of any enabled book is not probable. Positive control: the same
    client's contract with both books probable is approved by the same rule."""
    maya = seats.place.author
    offered = _offered(monkeypatch)
    assign(seats.priya.member, "revenue_reviewer")
    version_id, rule_id = _publish_auto_approval(seats)
    kept = put(
        seats.app,
        f"/api/v1/entities/{seats.entity_id}/books/IFRS15",
        seats.marcus,
        {"is_enabled": True},
    )
    assert kept.status_code == 200, kept.text
    client = _integration(seats)

    # Positive control: both books probable — a standard item.
    standard = client.booked("C-02", "SF-ORD-10444")
    probable = [
        _assessment(
            _reviewed_record(seats.app, maya, seats.marcus, standard, book=book),
            probable=True,
            book=book,
        )
        for book in ("ASC606", "IFRS15")
    ]
    recorded = client.assessed(standard, 1, *probable)
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["step1_gate"] is None
    activated = client.submitted(standard, 3)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    assert _decisions(seats, activated.headers[APPROVAL_HEADER]) == [
        ("AUTO_APPROVE", "SYSTEM", version_id, rule_id)
    ]
    assert _book_statuses(seats, standard) == {"ASC606": "ACTIVE", "IFRS15": "ACTIVE"}

    # IFRS 15 not probable: the activation would leave that book NOT_A_CONTRACT.
    contract_id = client.booked("C-09", "SF-ORD-10443")
    asc606 = _reviewed_record(seats.app, maya, seats.marcus, contract_id)
    ifrs15 = _reviewed_record(
        seats.app,
        maya,
        seats.marcus,
        contract_id,
        "NOT_A_CONTRACT",
        {"consideration_nonrefundable": False},
        book="IFRS15",
    )
    differing = client.assessed(
        contract_id,
        1,
        _assessment(asc606, probable=True),
        _assessment(ifrs15, probable=False, book="IFRS15"),
    )
    assert differing.status_code == 201, differing.text
    assert differing.json()["contract"]["status"] == "DRAFT"
    assert differing.json()["step1_gate"]["reason"] == "BOOK_NOT_ASSESSED"
    assert _passed(seats.app, maya, contract_id) == dict.fromkeys(CODES, True)

    submitted = client.submitted(contract_id, 3)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]
    assert offered == [(True, None), (False, None)]
    (request,) = _requests(seats, contract_id)
    assert (str(request["status"]), list(request["flags"])) == ("PENDING", [])
    assert _decisions(seats, request_id) == []
    assert submitted.json()["status"] == "PENDING_REVIEW"
    assert _header(seats, contract_id) == ("DRAFT", 3)
    assert _book_statuses(seats, contract_id) == {"ASC606": "DRAFT", "IFRS15": "DRAFT"}

    # A person decides; the engine decides per book.
    approved = approve(seats.app, request_id, seats.priya)
    assert approved.status_code == 200, approved.text
    assert _header(seats, contract_id) == ("ACTIVE", 4)
    assert _book_statuses(seats, contract_id) == {"ASC606": "ACTIVE", "IFRS15": "NOT_A_CONTRACT"}
    assert _decisions(seats, request_id) == [("APPROVE", "USER", None, None)]

    # Supervisor ruling R-102 (a): the criteria-met path of the book that stayed out is the same
    # approved path under the ACTIVE header — and no standard item either. Every event of the
    # re-assessment is the API client's; the published rule is not offered the request.
    seats.place.clock.advance(timedelta(minutes=1))
    met = _reviewed_record(seats.app, maya, seats.marcus, contract_id, book="IFRS15")
    head = _header(seats, contract_id)[1]  # the judgement held and released the contract
    reassessed = client.assessed(
        contract_id, head, _assessment(met, probable=True, book="IFRS15", on="2026-09-10")
    )
    assert reassessed.status_code == 201, reassessed.text
    requested = client.submitted(contract_id, head + 1)
    assert requested.status_code == 200, requested.text
    assert requested.json()["status"] == "ACTIVE"  # the header does not move
    reentry_id = requested.headers[APPROVAL_HEADER]
    assert offered == [(True, None), (False, None), (False, None)]
    assert [(str(row["status"]), list(row["flags"])) for row in _requests(seats, contract_id)] == [
        ("APPROVED", []),
        ("PENDING", []),
    ]
    assert _decisions(seats, reentry_id) == []
    assert _book_statuses(seats, contract_id) == {"ASC606": "ACTIVE", "IFRS15": "NOT_A_CONTRACT"}
    decided = approve(seats.app, reentry_id, seats.priya)
    assert decided.status_code == 200, decided.text
    assert _decisions(seats, reentry_id) == [("APPROVE", "USER", None, None)]
    assert _header(seats, contract_id) == ("ACTIVE", head + 2)
    assert _event_types(seats, contract_id)[-1] == "CONTRACT_CRITERIA_MET"
    assert _book_statuses(seats, contract_id) == {"ASC606": "ACTIVE", "IFRS15": "ACTIVE"}


def test_replaced_draft_of_an_integration_is_not_activated_on_its_old_judgement(
    seats: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-102 (c), item STEP1-DRAFT-REPLACE-1 — the hole as it was measured: a
    draft an integration wrote (30,000.00 USD, no routing flag), its Step 1 reviewed and
    assessed; the integration then replaced the draft (another customer, 75,000.00 USD) and
    submitted it, and the published ``AUTO_APPROVAL`` rule activated it with no person deciding
    anything after the replacement. The replacement voids the assessment with the booking it
    judged: the checklist fails, no request is made, nothing is offered to the rule. Positive
    control: once Step 1 is reviewed and assessed on the new booking the same client's
    submission is a standard item again and the rule approves it."""
    maya = seats.place.author
    offered = _offered(monkeypatch)
    version_id, rule_id = _publish_auto_approval(seats)
    client = _integration(seats)
    contract_id = client.booked("C-09", "SF-ORD-10451")
    judged = _reviewed_record(seats.app, maya, seats.marcus, contract_id)
    recorded = client.assessed(contract_id, 1, _assessment(judged, probable=True))
    assert recorded.status_code == 201, recorded.text
    assert _passed(seats.app, maya, contract_id) == dict.fromkeys(CODES, True)
    seats.place.clock.advance(timedelta(minutes=1))

    line = seat_line("O1", seats="25", price="75000.00", start="2026-09-01", end="2027-08-31")
    replacement = {
        **seat_body(
            seats.customers["C-02"],
            external_id="SF-ORD-10451",
            inception="2026-09-01",
            lines=[line],
        ),
        **TERMS_STATED,
    }
    replaced = client.send(f"{CONTRACTS}/{contract_id}/replace-draft", replacement, 2)
    assert replaced.status_code == 200, replaced.text
    assert _event_types(seats, contract_id) == [
        "CONTRACT_BOOKED",
        "COLLECTIBILITY_ASSESSED",
        "EVENT_VOIDED",
        "EVENT_VOIDED",
        "CONTRACT_BOOKED",
    ]
    assert _written_by(seats, contract_id) == [
        "API_CLIENT",
        "API_CLIENT",
        "SYSTEM",
        "SYSTEM",
        "API_CLIENT",
    ]
    assert _passed(seats.app, maya, contract_id) == {
        **dict.fromkeys(CODES, True),
        "STEP1_RECORD": False,
    }
    refused = client.submitted(contract_id, 5)
    assert refused.status_code == 409, refused.text
    assert refused.json()["type"].endswith("/activation-checklist-failed")
    assert _requests(seats, contract_id) == []
    assert offered == []
    assert _header(seats, contract_id) == ("DRAFT", 5)

    # Positive control: Step 1 on the new booking; the rule approves the standard item.
    renewed = _reviewed_record(seats.app, maya, seats.marcus, contract_id)
    again = client.assessed(contract_id, 5, _assessment(renewed, probable=True))
    assert again.status_code == 201, again.text
    activated = client.submitted(contract_id, 6)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    assert offered == [(True, None)]
    assert _decisions(seats, activated.headers[APPROVAL_HEADER]) == [
        ("AUTO_APPROVE", "SYSTEM", version_id, rule_id)
    ]


def test_engine_error_rolls_back_activation(seats: SeatWorld) -> None:
    maya = seats.place.author
    contract_id = _created(
        seats.app,
        maya,
        _seat_contract(seats, "SF-ORD-10432", seats="10", price="30000.00", product=ZERO_SEAT),
    )
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    submitted = _submit(seats.app, maya, contract_id, head)
    assert submitted.status_code == 422, submitted.text
    assert slug(submitted) == "validation-failed"
    assert [error["rule_id"] for error in submitted.json()["errors"]] == ["TOTAL_SSP_ZERO"]
    assert _header(seats, contract_id) == ("DRAFT", 2)
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, contract_id)
    assert _requests(seats, contract_id) == []


def test_tc_setup_20_unmapped_product_blocks_activation(seats: SeatWorld) -> None:
    maya = seats.place.author
    body = _seat_contract(seats, "TC-SETUP-20", seats="5", price="2500.00", product=HARDWARE_X)
    body["lines"][0] |= {"stratification": "Hardware 1", "ssp_version_label": "2023-01-01"}
    contract_id = _created(seats.app, maya, body)
    latest = seats.place.rows(
        select(contract_computation.c.status)
        .join(
            contract, contract.c.combination_group_id == contract_computation.c.combination_group_id
        )
        .where(contract.c.id == contract_id)
    )
    assert [str(row["status"]) for row in latest] == ["QUARANTINED"]
    items = seats.place.rows(
        select(exception_item.c.code, exception_item.c.severity, exception_item.c.status).where(
            exception_item.c.contract_id == contract_id
        )
    )
    assert [(row["code"], str(row["severity"]), str(row["status"])) for row in items] == [
        ("SSP_KEY_NOT_FOUND", "BLOCKING", "OPEN")
    ]
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)

    checklist = {
        code: (passed, detail) for code, passed, detail in _checklist(seats.app, maya, contract_id)
    }
    passed, detail = checklist["PRODUCT_TEMPLATE_SSP"]
    assert passed is False
    assert detail == (
        "No product, template or SSP for O1 (Hardware X). "
        "No approved SSP for Hardware X / Hardware 1 / 2023-01-01."
    )
    refused = _submit(seats.app, maya, contract_id, head)
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "activation-checklist-failed"
    assert fields(refused) == [(None, "PRODUCT_TEMPLATE_SSP")]
    lines = seats.place.scalar(
        select(func.count())
        .select_from(schedule_line)
        .where(schedule_line.c.contract_id == contract_id)
    )
    assert lines == 0
    assert _header(seats, contract_id) == ("DRAFT", 2)


# --- controls ------------------------------------------------------------------------------------


@pytest.mark.control("CTL-003")
def test_ctl_003_line_without_template_blocks_activation_and_posting(seats: SeatWorld) -> None:
    maya = seats.place.author
    new_product(
        seats.app,
        maya,
        code="AVM-SEAT-NOTPL",
        name="Seat without template",
        revenue_category="SUBSCRIPTION",
    )
    contract_id = _created(
        seats.app,
        maya,
        _seat_contract(
            seats, "SF-ORD-10433", seats="10", price="24000.00", product="AVM-SEAT-NOTPL"
        ),
    )
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    checklist = {
        code: (passed, detail) for code, passed, detail in _checklist(seats.app, maya, contract_id)
    }
    passed, detail = checklist["PRODUCT_TEMPLATE_SSP"]
    assert passed is False
    assert detail is not None
    assert detail.startswith("No product, template or SSP for O1 (AVM-SEAT-NOTPL).")
    refused = _submit(seats.app, maya, contract_id, head)
    assert (refused.status_code, slug(refused)) == (409, "activation-checklist-failed")
    assert [rule for _, rule in fields(refused)] == ["PRODUCT_TEMPLATE_SSP"]
    postings = seats.place.scalar(
        select(func.count())
        .select_from(subledger_line)
        .where(subledger_line.c.contract_id == contract_id)
    )
    assert postings == 0
    assert _header(seats, contract_id) == ("DRAFT", 2)


@pytest.mark.control("CTL-004")
def test_ctl_004_activation_gate_blocks_missing_document(seats: SeatWorld) -> None:
    maya = seats.place.author
    body = k09_body(seats.customers["C-09"])
    del body["document_ref"]
    contract_id = _created(seats.app, maya, body)
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    refused = _submit(seats.app, maya, contract_id, head)
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "activation-checklist-failed"
    assert fields(refused) == [(None, "SOURCE_REFERENCE")]
    assert refused.json()["errors"][0]["message"] == "No contract reference is recorded."
    assert refused.json()["detail"] == "1 checklist item has not passed: SOURCE_REFERENCE."
    assert _header(seats, contract_id) == ("DRAFT", 2)
    assert _requests(seats, contract_id) == []


@pytest.mark.control("CTL-005")
def test_ctl_005_routed_contract_needs_other_reviewer(seats: SeatWorld, clock: FrozenClock) -> None:
    """CTL-005, the routing's part: an activation its preparer submits becomes an approval
    request, and the preparer — who holds the reviewer's role as well — cannot decide it (403
    ``self-approval``): the contract stays PENDING_REVIEW at the same head, the request PENDING,
    and no ``CONTRACT_ACTIVATED`` is appended. Not witnessed here: the approval of another
    reviewer, which activates (``test_activation_pair_1_…`` below), and the rule-based
    auto-approval (``tests/domain/policies/test_auto_approval.py`` and ``test_rule_floor.py``)."""
    someone = colleague(seats.place.tenant_id, "rhea")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(someone, code)
    rhea = enrolled(seats.app, clock, someone)
    contract_id = _created(seats.app, rhea, k09_body(seats.customers["C-09"]))
    head = _step1(seats.app, rhea, seats.marcus, contract_id, 1)
    submitted = _submit(seats.app, rhea, contract_id, head)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]

    decided = approve(seats.app, request_id, rhea)
    assert (decided.status_code, slug(decided)) == (403, "self-approval")
    shown = get(seats.app, f"{CONTRACTS}/{contract_id}", rhea).json()
    assert (shown["status"], shown["head_stream_version"]) == ("PENDING_REVIEW", 2)
    (request,) = _requests(seats, contract_id)
    assert str(request["status"]) == "PENDING"
    assert _event_types(seats, contract_id) == ["CONTRACT_BOOKED", "COLLECTIBILITY_ASSESSED"]


@pytest.mark.control("CTL-005")
def test_activation_pair_1_approved_path_moves_stored_draft_to_active_and_refusals_hold(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """D-98 candidate 143 AMENDMENT 1 (Codex production-20260922-0121 §2, 0147 §2): the DB-03 pair
    (DRAFT, ACTIVE) admits the column move, so the APPROVAL INVARIANT — a DRAFT becomes ACTIVE only
    through the approved SM-02 ``activate`` or the SYSTEM path — is the domain's. This witness
    covers the APPROVED path and the refusals (the SYSTEM / consumed-import path is witnessed by the
    legacy ``test_contract_setup`` COMMIT, whose approval ``activate`` checks through
    ``consumed.covers``; Codex 0213 §2 (b)), exercised in the APPROVAL CONTEXT the hook checks:
    (1) a preparer cannot record ``CONTRACT_ACTIVATED`` through the events endpoint (refused by
    name — 409 ``invalid-transition`` naming the activation command since supervisor ruling R-20
    (c), 04 §16.3 rev 1.105; 422 ``API-R-30`` before it); (2) the preparer's own
    approval is refused (``self-approval``) and the stored status stays DRAFT (read model
    PENDING_REVIEW) with no ``CONTRACT_ACTIVATED``; (5) the domain hook handed the contract's own
    PENDING request refuses
    (409 ``invalid-transition``: not APPROVED) and writes nothing; (4) the reviewer's approval — the
    ordinary SM-02 activation — moves the STORED DRAFT to ACTIVE; on a second contract, (6) a
    REJECTED activation request leaves it DRAFT with no event and, handed to the hook, refuses by
    name; (3) the first contract's APPROVED request handed to the hook for the second contract is
    refused as another subject's (``LookupError``, ``assert_own_fresh_basis`` — subject and
    freshness, not the authorization control). Fail-first for (4): on the 0069 function the approved
    activation raised ``EREV-TRN-001: status of erev.contract cannot change from DRAFT to ACTIVE``
    (main 0959b560); 0070 admits the stored pair. (5) and (6) have their meaning on 0070.

    Of CTL-005's row ("Contract approval routing and rule-based auto-approval") this
    witnesses the approval that activates — the decision of a reviewer who is not
    the preparer moves the stored DRAFT to ACTIVE and appends
    ``CONTRACT_ACTIVATED`` — beside what does not activate: the events endpoint,
    the preparer's own decision, a pending request, a rejected one and another
    contract's approved one. Not witnessed here: which approver a routing rule
    names, and the rule-based auto-approval
    (``tests/domain/policies/test_auto_approval.py`` and ``test_rule_floor.py``).
    """
    from erev_api.domain.contracts import activation as activation_domain
    from erev_api.domain.contracts import events as events_domain
    from erev_api.problems import Problem

    assign(seats.priya.member, "revenue_reviewer")  # the reviewer who decides in (4) and (6)
    someone = colleague(seats.place.tenant_id, "rhea")
    for code in ("revenue_accountant", "revenue_reviewer"):
        assign(someone, code)
    rhea = enrolled(seats.app, clock, someone)
    contract_id = _created(seats.app, rhea, k09_body(seats.customers["C-09"]))
    head = _step1(seats.app, rhea, seats.marcus, contract_id, 1)
    # (1) the events endpoint refuses the activation type by name
    recorded = post(
        seats.app,
        f"{CONTRACTS}/{contract_id}/events",
        rhea,
        {
            "events": [
                {
                    "event_type": "CONTRACT_ACTIVATED",
                    "effective_date": "2026-01-01",
                    "payload": {"checklist": []},
                }
            ]
        },
        if_match=f'"s{head}"',
    )
    assert (recorded.status_code, slug(recorded)) == (409, "invalid-transition"), recorded.text
    assert fields(recorded) == [("events.0.event_type", "DB-03")]
    assert recorded.json()["errors"][0]["message"] == events_domain.ACTIVATION_ONLY.format(
        event_type="CONTRACT_ACTIVATED"
    )
    assert _header(seats, contract_id) == ("DRAFT", head)
    # (2) the preparer's own approval is refused; the stored status stays DRAFT
    submitted = _submit(seats.app, rhea, contract_id, head)
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.headers[APPROVAL_HEADER]
    decided = approve(seats.app, request_id, rhea)
    assert (decided.status_code, slug(decided)) == (403, "self-approval")
    assert _header(seats, contract_id) == (
        "DRAFT",
        head,
    )  # stored; the read model says PENDING_REVIEW
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, contract_id)
    # (5) the hook handed the contract's own PENDING request refuses: not APPROVED; nothing written
    with seats.place.uow() as uow, pytest.raises(Problem) as pending:
        activation_domain.activate(
            uow, contract_id=contract_id, approval_request_id=UUID(request_id), on_behalf_of=None
        )
    assert pending.value.slug == "invalid-transition"
    assert "PENDING, not APPROVED" in str(pending.value.detail)
    assert _header(seats, contract_id) == ("DRAFT", head)
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, contract_id)
    # (4) the ordinary approved activation moves the STORED DRAFT to ACTIVE (0070; RED on 0069)
    clock.advance(timedelta(minutes=1))
    approved = approve(seats.app, request_id, seats.priya)
    assert approved.status_code == 200, approved.text
    assert _header(seats, contract_id) == ("ACTIVE", head + 1)
    assert _event_types(seats, contract_id)[-1] == "CONTRACT_ACTIVATED"
    # (6) a second contract: the reviewer REJECTS its activation — stored DRAFT, no event; the hook
    #     handed the REJECTED request refuses by name (another customer's contract, created after
    #     (4): a same-customer contract raises a COMBINATION_SUGGESTIONS checklist item — measured
    #     on 72944ccc — and would fail its own submit)
    other_body = k09_body(seats.customers["C-02"])  # another customer: no combination suggestion
    other_body["external_id"] = f"{other_body['external_id']}-PAIR-2"
    other_id = _created(seats.app, rhea, other_body)
    other_head = _step1(seats.app, rhea, seats.marcus, other_id, 1)
    other_submitted = _submit(seats.app, rhea, other_id, other_head)
    assert other_submitted.status_code == 200, other_submitted.text
    other_request = other_submitted.headers[APPROVAL_HEADER]
    rejected = reject(seats.app, other_request, seats.priya, "Not this contract.")
    assert rejected.status_code == 200, rejected.text
    assert _header(seats, other_id) == ("DRAFT", other_head)
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, other_id)
    with seats.place.uow() as uow, pytest.raises(Problem) as refused:
        activation_domain.activate(
            uow, contract_id=other_id, approval_request_id=UUID(other_request), on_behalf_of=None
        )
    assert refused.value.slug == "invalid-transition"
    assert "REJECTED, not APPROVED" in str(refused.value.detail)
    assert _header(seats, other_id) == ("DRAFT", other_head)
    # (3) another contract's (APPROVED) request handed to the hook for this one: another subject
    with seats.place.uow() as uow, pytest.raises(LookupError, match="a hook re-validates its own"):
        activation_domain.activate(
            uow, contract_id=other_id, approval_request_id=UUID(request_id), on_behalf_of=None
        )
    assert _header(seats, other_id) == ("DRAFT", other_head)
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, other_id)


@pytest.mark.control("CTL-028")
def test_mandatory_product_attributes_block_booking_and_recheck_activation(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    from erev_api.db.tables import product
    from erev_api.enums import RegistryCategory
    from support.reference import patch
    from support.rows import publish_registry_version

    app, maya = seats.app, seats.place.author
    body = _seat_contract(seats, "REQUIRED-ATTR-EXISTING", seats="10", price="24000.00")
    contract_id = _created(app, maya, body)
    head = _step1(app, maya, seats.marcus, contract_id, 1)
    sent = _submit(app, maya, contract_id, head)
    assert sent.status_code == 200, sent.text
    request_id = sent.headers[APPROVAL_HEADER]
    context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=seats.place.tenant_id,
            category=RegistryCategory.DISCLOSURE_ELECTION,
            values={"disclosure.mandatory_disaggregation_attributes": ["review_channel"]},
            at=clock.now(),
        )
        product_id = session.execute(
            select(product.c.id).where(product.c.code == body["lines"][0]["product_code"])
        ).scalar_one()
    message = (
        f"Product {body['lines'][0]['product_code']} is missing mandatory "
        "disaggregation attributes: review_channel."
    )
    new_body = {**body, "external_id": "REQUIRED-ATTR-NEW"}
    refused = post(app, CONTRACTS, maya, new_body)
    assert refused.status_code == 422, refused.text
    assert ("lines", "REQ-REF-012") in fields(refused)
    assert message in [error["message"] for error in refused.json()["errors"]]
    checklist = {
        code: (passed, detail) for code, passed, detail in _checklist(app, maya, contract_id)
    }
    assert checklist["PRODUCT_TEMPLATE_SSP"] == (False, message)
    blocked = approve(app, request_id, seats.marcus)
    assert blocked.status_code == 409, blocked.text
    assert "PRODUCT_TEMPLATE_SSP" in [rule for _, rule in fields(blocked)]
    assert "CONTRACT_ACTIVATED" not in _event_types(seats, contract_id)
    path = f"/api/v1/products/{product_id}"
    shown = get(app, path, maya)
    assert shown.status_code == 200, shown.text
    fixed = patch(
        app,
        path,
        maya,
        {
            "disaggregation": {
                **shown.json()["disaggregation"],
                "review_channel": "direct",
            }
        },
        if_match=shown.headers["ETag"],
    )
    assert fixed.status_code == 200, fixed.text
    approved = approve(app, request_id, seats.marcus)
    assert approved.status_code == 200, approved.text
    assert "CONTRACT_ACTIVATED" in _event_types(seats, contract_id)
    created = post(app, CONTRACTS, maya, new_body)
    assert created.status_code == 201, created.text
