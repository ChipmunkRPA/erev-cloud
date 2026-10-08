"""API-R-09 approvals and delegations (04 §15.3 API-R-09, §16.10, T-PLT-21; SCREENS §15.3 to
§15.7 bindings; PRD BR-PLT-06, BR-PLT-07; dev-guide DG-KRN-APR-03, DG-LST-06; BUILD_SPEC PLF-16).

Lena prepares items through the approval engine; Ben, a Tenant Admin enrolled in MFA, holds
``access.approve``; Mia holds no role. The probe subjects give ``ROLE_CHANGE`` an
``access.approve`` step and ``SSP_BOOK_VERSION`` an ``ssp.approve`` step, with the amount taken
from the subject content.

Delegating approval authority and taking it back are access administration (PRD BR-PLT-06,
BR-PLT-07; security review 2026-09-29 S3, supervisor ruling R-48 (a)): both commands need the
delegator's MFA-verified session with a fresh step-up.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects as approval_subjects
from erev_api.approvals.engine import (
    EVERY_ENTITY_DETAIL,
    NO_SPECIFICATION,
    WITHDRAW_DETAIL,
    ImpactPreview,
    submit,
)
from erev_api.approvals.subjects import SubjectEntities
from erev_api.auth import mfa, totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import effective_grants
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_delegation,
    approval_request,
    approval_step,
    audit_event,
    file_object,
    fiscal_calendar,
    legal_entity,
)
from erev_api.domain.platform import approval_delegations
from erev_api.enums import ApprovalSubjectType, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support import upload_fixtures as fx
from support.api_clients import access_approver, issued_client
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    SESSION_MFA,
    Actor,
    authenticator,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    refreshed,
    sign_in,
    step_up,
    workspace,
)
from support.rows import (
    approval_request_values,
    approval_step_values,
    fiscal_calendar_values,
    insert_role_assignment,
    legal_entity_values,
)
from support.subjects import ProbeSubjects, install

APPROVALS = "/api/v1/approvals"
BULK_APPROVE = f"{APPROVALS}/bulk-approve"
DELEGATIONS = "/api/v1/approval-delegations"
FILES = "/api/v1/files"
PROBLEM_BASE = "https://erev.dev/problems/"
ROLE_CHANGE = ApprovalSubjectType.ROLE_CHANGE
SSP_BOOK = ApprovalSubjectType.SSP_BOOK_VERSION
SUMMARY = "Change the access approver role"
# 04 §16.10 API-S-Approval.
API_S_APPROVAL = {
    "id",
    "request_no",
    "subject",
    "summary",
    "status",
    "entity",
    "entities",
    "entity_count",
    "all_entities",
    "amount",
    "flags",
    "routing",
    "preparer",
    "submitted_at",
    "reason_code",
    "comment",
    "decided_at",
    "voided_at",
    "void_reason",
    "current_step_no",
    "steps",
    "impact_preview",
    "reopen_judgement",
    "attachments",
    "can_decide",
    "content_withheld",
}


@dataclass(frozen=True, slots=True)
class World:
    lena: Actor
    ben: Actor
    mia: Actor


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _amount(subjects: ProbeSubjects, subject_id: UUID) -> tuple[Decimal, str] | None:
    value = subjects.contents[subject_id].get("amount")
    return None if value is None else (Decimal(value), "USD")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ProbeSubjects:
    subjects = ProbeSubjects()
    for subject_type, permission in ((ROLE_CHANGE, "access.approve"), (SSP_BOOK, "ssp.approve")):
        spec = subjects.spec(subject_type, required_permission=permission)
        install(
            monkeypatch,
            replace(
                spec,
                amount_functional=lambda _session, subject_id: _amount(subjects, subject_id),
            ),
        )
    return subjects


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    lena = member(keyring, clock)
    ben = colleague(lena.tenant_id, "ben")
    mia = colleague(lena.tenant_id, "mia")
    with tenant_session(_all_entities(lena.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=lena.tenant_id,
            membership_id=ben.membership_id,
            role_code="tenant_admin",
        )
    return World(
        lena=workspace(app, lena, sign_in(app, lena.email), None),
        ben=enrolled(app, clock, ben),
        mia=workspace(app, mia, sign_in(app, mia.email), None),
    )


@dataclass(frozen=True, slots=True)
class Submitter:
    probe: ProbeSubjects
    clock: FrozenClock
    keyring: KeyRing
    settings: Settings

    def __call__(
        self,
        preparer: Actor,
        *,
        amount: str | None = None,
        subject_type: ApprovalSubjectType = ROLE_CHANGE,
        preview: ImpactPreview | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> Mapping[str, Any]:
        """Submit a new probe subject one minute after the previous submission, with its impact
        preview, its reason code and its comment when they are given."""
        self.clock.advance(timedelta(minutes=1))
        content: dict[str, Any] = {"role": "access_approver"}
        if amount is not None:
            content["amount"] = amount
        someone = preparer.member
        # The preparer as a request builds her: what her role assignments grant now. Until 04
        # rev 1.319 this helper gave every preparer the entity scope of all entities and no
        # permission, a principal no request builds — the kernel then asked a preparer's entity
        # scope, and it now asks what she reads (``engine.own_scope_covers``; item
        # READ-SCOPE-BY-PERMISSION-1). STALE TEST WORLD by the supervisor's ruling of 2026-10-03.
        everything = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(everything, read_only=True) as session:
            grants = effective_grants(session, someone.membership_id, at=self.clock.now())
        principal = Principal(
            kind=PrincipalKind.USER,
            id=someone.user_id,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            display_name="Preparer",
            roles=grants.roles,
            permissions=grants.permissions,
            permission_scopes=grants.permission_scopes,
            entity_scope=grants.entity_scope,
            auth_method="password",
            mfa_verified_at=None,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
            role_scopes=grants.role_scopes,
        )
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-approvals-api",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=self.clock.now(),
            format_locale="en-US",
        )
        files = LocalFileStore(self.settings.file_root)
        with unit_of_work(ctx, clock=self.clock, keyring=self.keyring, files=files) as uow:
            request = submit(
                uow,
                subject_type=subject_type,
                subject_id=self.probe.new_subject(**content),
                summary=SUMMARY,
                impact_preview=preview,
                reason_code=reason_code,
                comment=comment,
            )
            uow.commit()
        return request


@pytest.fixture
def submitted(
    probe: ProbeSubjects, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> Submitter:
    return Submitter(probe=probe, clock=clock, keyring=keyring, settings=app_settings)


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def ids(response: HttpResponse) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def fields(response: HttpResponse) -> list[tuple[str, str | None, str]]:
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def test_list_filters_and_sort(app: FastAPI, world: World, submitted: Submitter) -> None:
    first = str(submitted(world.lena, amount="100.00")["id"])
    second = str(submitted(world.lena, amount="250.00")["id"])
    third = str(submitted(world.lena)["id"])
    own = str(submitted(world.ben, amount="900.00")["id"])
    ssp = str(submitted(world.lena, amount="500.00", subject_type=SSP_BOOK)["id"])

    waiting = get(
        app,
        APPROVALS,
        world.ben,
        assigned_to_me="true",
        status="PENDING",
        sort="submitted_at",
        count="true",
    )
    assert ids(waiting) == [first, second, third]
    assert waiting.headers["X-Erev-Total-Count"] == "3"
    assert [item["can_decide"] for item in waiting.json()["items"]] == [True, True, True]

    page = get(
        app,
        APPROVALS,
        world.ben,
        assigned_to_me="true",
        status="PENDING",
        sort="submitted_at",
        limit="2",
    )
    assert ids(page) == [first, second]
    rest = get(
        app,
        APPROVALS,
        world.ben,
        assigned_to_me="true",
        status="PENDING",
        sort="submitted_at",
        limit="2",
        cursor=page.json()["next_cursor"],
    )
    assert (ids(rest), rest.json()["next_cursor"]) == ([third], None)

    assert ids(get(app, APPROVALS, world.lena, preparer="me")) == [ssp, third, second, first]
    by_membership = get(
        app, APPROVALS, world.ben, preparer=str(world.lena.member.membership_id), status="PENDING"
    )
    assert ids(by_membership) == [third, second, first]

    largest = get(app, APPROVALS, world.ben, status="PENDING", sort="amount")
    assert ids(largest) == [own, second, first, third]
    assert [item["amount"] for item in largest.json()["items"]] == [
        {"amount": "900.00", "currency": "USD"},
        {"amount": "250.00", "currency": "USD"},
        {"amount": "100.00", "currency": "USD"},
        None,
    ]
    fixed = get(app, APPROVALS, world.ben, sort="-amount")
    assert (fixed.status_code, slug(fixed)) == (422, "validation-failed"), fixed.text
    assert [(field, rule) for field, rule, _ in fields(fixed)] == [("sort", "API-C-09")]


def test_approval_detail_and_can_decide(app: FastAPI, world: World, submitted: Submitter) -> None:
    request = submitted(world.lena, amount="250.00")
    path = f"{APPROVALS}/{request['id']}"

    as_preparer = get(app, path, world.lena)
    assert as_preparer.status_code == 200, as_preparer.text
    body = as_preparer.json()
    assert set(body) == API_S_APPROVAL
    assert as_preparer.headers["ETag"].startswith('"h')
    assert body["can_decide"] is False
    assert body["subject"] == {
        "type": "ROLE_CHANGE",
        "id": str(request["subject_id"]),
        "display": SUMMARY,
        "href": None,
        "content_sha256": request["subject_content_sha256"],
        "row_version": None,
    }
    assert (
        body["request_no"],
        body["summary"],
        body["status"],
        body["amount"],
        body["flags"],
        body["current_step_no"],
    ) == (request["request_no"], SUMMARY, "PENDING", {"amount": "250.00", "currency": "USD"}, [], 1)
    assert body["routing"] == {"rule_set_version_id": None, "rule_key": None}
    assert (body["preparer"]["id"], body["preparer"]["kind"]) == (
        str(world.lena.member.user_id),
        "USER",
    )
    assert [
        (step["step_no"], step["required_permission"], step["min_approvers"], step["status"])
        for step in body["steps"]
    ] == [(1, "access.approve", 1, "ACTIVE")]
    assert body["steps"][0]["decisions"] == []
    assert (
        body["entity"],
        body["impact_preview"],
        body["attachments"],
        body["decided_at"],
        body["voided_at"],
        body["void_reason"],
    ) == (None, None, [], None, None, None)
    # R-41 (8); 04 §16.10 rev 1.104: the entities the request is bound to. A ROLE_CHANGE names none.
    assert (body["entities"], body["entity_count"], body["all_entities"]) == ([], 0, False)

    as_approver = get(app, path, world.ben)
    assert as_approver.status_code == 200, as_approver.text
    assert as_approver.json()["can_decide"] is True
    assert as_approver.headers["ETag"] == as_preparer.headers["ETag"]

    hidden = get(app, path, world.mia)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found")


def test_approve_needs_hash_and_step_up(
    app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock
) -> None:
    request = submitted(world.lena)
    path = f"{APPROVALS}/{request['id']}/approve"

    missing = post(app, path, world.ben, {"comment": "Reviewed the role change"})
    assert (missing.status_code, slug(missing)) == (422, "validation-failed"), missing.text
    assert [field for field, _, _ in fields(missing)] == ["subject_content_sha256"]

    clock.advance(timedelta(minutes=6))
    decision = {
        "subject_content_sha256": request["subject_content_sha256"],
        "comment": "Reviewed the role change",
    }
    stale = post(app, path, world.ben, decision)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text

    assert world.ben.secret is not None
    verified = call(
        app,
        "POST",
        SESSION_MFA,
        json={"code": totp.code_at(world.ben.secret, totp.time_step(clock.now()))},
        headers=cookie_headers(world.ben.token, world.ben.csrf_token),
    )
    assert verified.status_code == 200, verified.text
    fresh = refreshed(app, cookie_of(verified))
    ben = replace(world.ben, token=fresh.token, csrf_token=fresh.csrf_token)

    approved = post(app, path, ben, decision)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert (body["status"], body["can_decide"], body["steps"][0]["status"]) == (
        "APPROVED",
        False,
        "APPROVED",
    )
    [recorded] = body["steps"][0]["decisions"]
    assert (
        recorded["decision"],
        recorded["approver"]["id"],
        recorded["on_behalf_of"],
        recorded["comment"],
    ) == ("APPROVE", str(ben.member.user_id), None, "Reviewed the role change")
    assert approved.headers["ETag"].startswith('"h')


def test_apr_denied_audit_a_stale_step_up_is_on_record_with_the_id_as_sent(
    app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock
) -> None:
    """Item APR-DENIED-AUDIT-1 (the supervisor's ruling of 2026-10-02; DG-KRN-AUTH-05): an
    approval with a step-up older than five minutes is refused before the request is read, and
    the attempt is recorded — ``approval_request.approve``, ``DENIED``, reason
    ``mfa-step-up-required`` — with the id as sent and nothing of a request, so the event is the
    same for an id that exists and one that does not. A bulk call refused as a whole is ONE
    event that names the ids it sent.

    Fail-first: the three refusals left no trace."""
    request = submitted(world.lena)
    known, unknown = str(request["id"]), str(new_id())
    hashes = {"subject_content_sha256": request["subject_content_sha256"]}
    clock.advance(timedelta(minutes=6))
    for request_id in (known, unknown):
        stale = post(app, f"{APPROVALS}/{request_id}/approve", world.ben, hashes)
        assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    whole = post(
        app,
        BULK_APPROVE,
        world.ben,
        {"items": [{"approval_request_id": item, **hashes} for item in (known, unknown)]},
    )
    assert (whole.status_code, slug(whole)) == (403, "mfa-step-up-required"), whole.text

    with tenant_session(_all_entities(world.ben.member.tenant_id), read_only=True) as session:
        denied = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.object_id,
                audit_event.c.actor_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.outcome == "DENIED")
            .order_by(audit_event.c.chain_seq)
        ).all()
    stale_step_up = {"permission": "", "reason": "mfa-step-up-required"}
    ben = world.ben.member.user_id
    assert [(row.action, row.object_id, row.actor_id, dict(row.detail)) for row in denied] == [
        ("approval_request.approve", UUID(known), ben, stale_step_up),
        ("approval_request.approve", UUID(unknown), ben, stale_step_up),
        (
            "approval_request.approve",
            None,
            ben,
            {**stale_step_up, "approval_request_ids": [known, unknown], "items": 2},
        ),
    ]
    # Positive control: nothing was decided, and the request still waits.
    assert get(app, f"{APPROVALS}/{known}", world.ben).json()["status"] == "PENDING"


def test_reject_requires_comment(app: FastAPI, world: World, submitted: Submitter) -> None:
    request = submitted(world.lena)
    path = f"{APPROVALS}/{request['id']}/reject"

    refused = post(app, path, world.ben, {})
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [field for field, _, _ in fields(refused)] == ["comment"]

    rejected = post(app, path, world.ben, {"comment": "The access approver role needs an owner."})
    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["status"], rejected.json()["steps"][0]["status"]) == (
        "REJECTED",
        "REJECTED",
    )


def test_withdraw_by_preparer_only(app: FastAPI, world: World, submitted: Submitter) -> None:
    request = submitted(world.lena)
    path = f"{APPROVALS}/{request['id']}/withdraw"

    refused = post(app, path, world.ben, {})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    withdrawn = post(app, path, world.lena, {"comment": "Wrong role"})
    assert withdrawn.status_code == 200, withdrawn.text
    assert (withdrawn.json()["status"], withdrawn.json()["void_reason"]) == (
        "WITHDRAWN",
        "WITHDRAWN_BY_PREPARER",
    )


def test_a_caller_that_is_no_person_learns_nothing_from_a_decision_route(
    app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock
) -> None:
    """R-41 (8) (REQ-PLT-012; the second independent review): an API client never decides, and
    the refusal is the same for an id that exists and one that does not. ``POST .../reject`` read
    the request before the person check, so a bearer token got 404 for an unknown id and 403 for
    a request it could not read: the difference confirmed the id. Approve, reject and bulk approve
    now answer the same problem for both, and the request is untouched; the approver decides."""
    request = submitted(world.lena, amount="250.00")
    # The client's scopes are an access grant (supervisor ruling R-38 (iii)): Ben requests it,
    # Ada — a second Tenant Admin — approves the grant, and Ben issues its secret.
    ada = access_approver(app, clock, world.ben.member, "ada")
    client = issued_client(
        app, world.ben, {"name": "svc-probe", "scopes": ["contract.read"]}, approver=ada
    )
    issued = call(
        app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(client["client_id"], client["client_secret"]),
    )
    assert issued.status_code == 200, issued.text

    def as_client(path: str, json: Mapping[str, Any]) -> tuple[int, str, str | None]:
        response = call(
            app,
            "POST",
            path,
            json=dict(json),
            headers={
                "Authorization": f"Bearer {issued.json()['access_token']}",
                "Idempotency-Key": f"k-{new_id()}",
            },
        )
        return response.status_code, slug(response), response.json().get("detail")

    known, unknown = str(request["id"]), str(new_id())
    hashes = {"subject_content_sha256": request["subject_content_sha256"]}
    rejected = [
        as_client(f"{APPROVALS}/{request_id}/reject", {"comment": "Not mine."})
        for request_id in (known, unknown)
    ]
    assert rejected[0] == rejected[1]
    assert rejected[0][:2] == (403, "forbidden")
    approved = [
        as_client(f"{APPROVALS}/{request_id}/approve", hashes) for request_id in (known, unknown)
    ]
    assert approved[0] == approved[1] and approved[0][0] == 403
    detail = get(app, f"{APPROVALS}/{known}", world.ben)
    assert detail.status_code == 200, detail.text
    assert (detail.json()["status"], detail.json()["steps"][0]["decisions"]) == ("PENDING", [])

    # Item APR-DENIED-AUDIT-1: each attempt is on record under the client's own id, with the id
    # as sent and nothing of a request — the trail says the same of an id that names a request
    # and of one that names none.
    with tenant_session(_all_entities(world.ben.member.tenant_id), read_only=True) as session:
        client_id = session.execute(
            select(api_client.c.id).where(api_client.c.name == "svc-probe")
        ).scalar_one()
        denied = session.execute(
            select(audit_event).where(audit_event.c.outcome == "DENIED").order_by("chain_seq")
        ).all()
    no_person = {"permission": "", "reason": "NOT_A_PERSON"}
    assert [(row.action, row.object_id, dict(row.detail)) for row in denied] == [
        ("approval_request.reject", UUID(known), no_person),
        ("approval_request.reject", UUID(unknown), no_person),
        ("approval_request.approve", UUID(known), no_person),
        ("approval_request.approve", UUID(unknown), no_person),
    ]
    assert {(str(row.actor_kind), row.actor_id, row.api_client_id) for row in denied} == {
        ("API_CLIENT", client_id, client_id)
    }

    # Positive control: the person who holds the step permission rejects it.
    decided = post(app, f"{APPROVALS}/{known}/reject", world.ben, {"comment": "Wrong role."})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "REJECTED"


def test_bulk_approve_bounds(app: FastAPI, world: World, submitted: Submitter) -> None:
    first = submitted(world.lena)
    second = submitted(world.lena)

    too_many = post(
        app,
        BULK_APPROVE,
        world.ben,
        {
            "items": [
                {"approval_request_id": str(new_id()), "subject_content_sha256": "0" * 64}
                for _ in range(201)
            ]
        },
    )
    assert (too_many.status_code, slug(too_many)) == (422, "validation-failed"), too_many.text
    assert [field for field, _, _ in fields(too_many)] == ["items"]

    approved = post(
        app,
        BULK_APPROVE,
        world.ben,
        {
            "items": [
                {
                    "approval_request_id": str(request["id"]),
                    "subject_content_sha256": request["subject_content_sha256"],
                }
                for request in (first, second)
            ],
            "comment": "Quarterly access review",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json() == {
        "results": [
            {"approval_request_id": str(request["id"]), "status": "APPROVED", "problem": None}
            for request in (first, second)
        ]
    }


def rate_preview(rate: str) -> ImpactPreview:
    """The snapshot an SSP rate change is approved on: the unit rate before and after."""
    return ImpactPreview(
        before={"ssp_unit_rate": {"amount": "100.00", "currency": "USD"}},
        after={"ssp_unit_rate": {"amount": rate, "currency": "USD"}},
    )


def joined(app: FastAPI, tenant_id: UUID, name: str, role_code: str) -> Actor:
    """A colleague with one role at work in the tenant, the second factor passed where the role
    makes it mandatory."""
    someone = colleague(tenant_id, name)
    with tenant_session(_all_entities(tenant_id)) as session:
        insert_role_assignment(
            session, tenant_id=tenant_id, membership_id=someone.membership_id, role_code=role_code
        )
    return workspace(app, someone, sign_in(app, someone.email))


def approval_body(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "subject_content_sha256": request["subject_content_sha256"],
        "impact_preview_sha256": request["impact_preview_sha256"],
    }


def decided(tenant_id: UUID, request_id: Any) -> tuple[str, int]:
    """(status, number of decisions) of the request as stored."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one()
        decisions = session.execute(
            select(func.count())
            .select_from(approval_decision)
            .where(approval_decision.c.approval_request_id == request_id)
        ).scalar_one()
    return str(status), int(decisions)


def test_req_plt_015_the_readers_of_a_request_read_its_impact_preview(
    app: FastAPI, world: World, submitted: Submitter
) -> None:
    """Security review P3-4 with S2 (ruling R-48 (c)). The stored preview was read by its creator
    and by any holder of ``audit.read``: the SSP Approver asked to decide got 404 on it and
    approved without it, while an Auditor who is no party to the request read it. The preview is
    read by whoever reads the request — its preparer and the holders of the step's permission."""
    tenant_id = world.lena.member.tenant_id
    sam = joined(app, tenant_id, "sam", "ssp_approver")  # ssp.approve; no audit.read
    ada = joined(app, tenant_id, "ada", "auditor")  # audit.read; no approval permission
    request = submitted(world.lena, subject_type=SSP_BOOK, preview=rate_preview("1.00"))

    detail = get(app, f"{APPROVALS}/{request['id']}", sam)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    shown = detail.json()["impact_preview"]
    assert shown["sha256"] == request["impact_preview_sha256"]
    metadata, content = f"{FILES}/{shown['file_id']}", f"{FILES}/{shown['file_id']}/content"

    for reader in (sam, world.lena):  # the step's approver; the preparer
        document = get(app, content, reader)
        assert document.status_code == 200, document.text
        assert document.json()["after"]["ssp_unit_rate"]["amount"] == "1.00"
        described = get(app, metadata, reader)
        assert described.status_code == 200, described.text
        assert described.json()["sha256"] == request["impact_preview_sha256"]
    # No party to the request: the Auditor (``audit.read`` opens audit artefacts only), a Tenant
    # Admin without the step's permission, a member without a role. 404, as for an unknown id.
    for outsider in (ada, world.ben, world.mia):
        unseen = get(app, f"{APPROVALS}/{request['id']}", outsider)
        assert (unseen.status_code, slug(unseen)) == (404, "not-found")
        for path in (metadata, content):
            hidden = get(app, path, outsider)
            assert (hidden.status_code, slug(hidden)) == (404, "not-found"), path
    hidden, unknown = get(app, content, ada), get(app, f"{FILES}/{new_id()}/content", ada)
    assert {**hidden.json(), "instance": None} == {**unknown.json(), "instance": None}

    approved = post(
        app,
        f"{APPROVALS}/{request['id']}/approve",
        sam,
        {**approval_body(request), "comment": "Rate change reviewed against the preview"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert get(app, content, sam).status_code == 200  # the decider keeps reading what was decided


def test_req_plt_015_a_request_whose_preview_cannot_be_read_is_not_approved(
    app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock
) -> None:
    """Ruling R-48 (c): the approve action is refused while the preview cannot be read. A request
    whose stored preview was destroyed answered 404 on ``approve`` only after the decision had
    run, and ``bulk-approve`` — which returns no preview — approved it. Both now refuse it with
    409 ``invalid-transition`` naming REQ-PLT-015, before any decision is written."""
    tenant_id = world.lena.member.tenant_id
    sam = joined(app, tenant_id, "sam", "ssp_approver")
    lost, kept, other = (
        submitted(world.lena, subject_type=SSP_BOOK, preview=rate_preview(rate))
        for rate in ("1.00", "2.00", "3.00")
    )
    for request in (lost, kept):
        assert get(app, f"{APPROVALS}/{request['id']}", sam).json()["can_decide"] is True
    # The stored preview of two requests is destroyed, as ``file.shred`` marks a row (T-PLT-29).
    with tenant_session(_all_entities(tenant_id)) as session:
        session.execute(
            update(file_object)
            .where(
                file_object.c.id.in_(
                    select(approval_request.c.impact_preview_file_id).where(
                        approval_request.c.id.in_([lost["id"], other["id"]])
                    )
                )
            )
            .values(
                shredded_at=clock.now(),
                shredded_by_kind=PrincipalKind.SYSTEM.value,
                shred_reason="Preview destroyed",
            )
        )

    refused = post(
        app,
        f"{APPROVALS}/{lost['id']}/approve",
        sam,
        {**approval_body(lost), "comment": "Approve without the preview"},
    )
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    [error] = refused.json()["errors"]
    assert error["rule_id"] == "REQ-PLT-015"
    assert decided(tenant_id, lost["id"]) == ("PENDING", 0)

    bulk = post(
        app,
        BULK_APPROVE,
        sam,
        {
            "items": [
                {"approval_request_id": str(request["id"]), **approval_body(request)}
                for request in (other, kept, lost)
            ],
            "comment": "Quarterly SSP review",
        },
    )
    assert bulk.status_code == 200, bulk.text
    results = bulk.json()["results"]
    assert [(item["approval_request_id"], item["status"]) for item in results] == [
        (str(other["id"]), "PENDING"),
        (str(kept["id"]), "APPROVED"),
        (str(lost["id"]), "PENDING"),
    ]
    for item in (results[0], results[2]):
        assert item["problem"]["type"] == f"{PROBLEM_BASE}invalid-transition"
        assert [error["rule_id"] for error in item["problem"]["errors"]] == ["REQ-PLT-015"]
    assert results[1]["problem"] is None
    # Positive control and no decision on the refused ones: only the readable request is decided.
    assert decided(tenant_id, kept["id"]) == ("APPROVED", 1)
    assert decided(tenant_id, other["id"]) == ("PENDING", 0)
    assert decided(tenant_id, lost["id"]) == ("PENDING", 0)

    # A list made only of unreadable previews decides nothing and still answers per item.
    alone = post(
        app,
        BULK_APPROVE,
        sam,
        {"items": [{"approval_request_id": str(lost["id"]), **approval_body(lost)}]},
    )
    assert alone.status_code == 200, alone.text
    [only] = alone.json()["results"]
    assert (only["status"], only["problem"]["status"]) == ("PENDING", 409)


def delegation_body(world: World, clock: FrozenClock, *, days: int = 30) -> dict[str, Any]:
    now = clock.now()
    return {
        "delegate_membership_id": str(world.mia.member.membership_id),
        "permissions": ["access.approve", "support_grant.approve"],
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=days)).isoformat(),
        "reason": "Cover while I am away",
    }


def with_factor(app: FastAPI, someone: Actor) -> Actor:
    """The world gives the delegate an authenticator app (supervisor ruling R-111 (2)): a
    delegation goes only to a member with a confirmed second factor, and a delegate is held to
    it — her session has answered the challenge."""
    authenticator(app, someone.member)
    return workspace(app, someone.member, sign_in(app, someone.member.email))


def delegation_rows(tenant_id: UUID) -> int:
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        return int(
            session.execute(select(func.count()).select_from(approval_delegation)).scalar_one()
        )


def delegation_audit(tenant_id: UUID) -> list[tuple[str, str, UUID | None, bool]]:
    """(action, outcome, actor, MFA-verified) of the delegation audit events, in chain order."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.outcome,
                audit_event.c.actor_id,
                audit_event.c.mfa_verified,
            )
            .where(audit_event.c.object_type == approval_delegations.OBJECT_TYPE)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(a), str(getattr(o, "value", o)), actor, bool(verified))
        for a, o, actor, verified in rows
    ]


def test_br_plt_07_a_password_only_session_cannot_delegate(
    app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock
) -> None:
    """Security review S3: with Ben's password alone — a session that owes the MFA challenge —
    an attacker handed Ben's ``access.approve`` and ``support_grant.approve`` to Mia, who holds no
    role, for 90 days, and Mia approved on Ben's behalf. The session is refused, nothing is
    delegated and Mia has no authority over Lena's request."""
    ben = world.ben.member
    signed = sign_in(app, ben.email)
    assert signed.body["mfa_required"] is True and signed.body["mfa_verified_at"] is None
    password_only = Actor(member=ben, token=signed.token, csrf_token=signed.csrf_token, secret=None)

    refused = post(app, DELEGATIONS, password_only, delegation_body(world, clock, days=90))
    assert (refused.status_code, slug(refused)) == (403, "mfa-required"), refused.text
    assert refused.json()["detail"] == mfa.VERIFICATION_REQUIRED
    assert delegation_rows(ben.tenant_id) == 0
    assert [action for action, *_ in delegation_audit(ben.tenant_id)] == []

    request = submitted(world.lena)
    path = f"{APPROVALS}/{request['id']}"
    hidden = get(app, path, world.mia)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    approved = post(
        app,
        f"{path}/approve",
        world.mia,
        {"subject_content_sha256": request["subject_content_sha256"], "comment": "ok"},
    )
    assert (approved.status_code, slug(approved)) == (403, "mfa-step-up-required"), approved.text
    shown = get(app, path, world.ben)
    assert shown.status_code == 200 and shown.json()["status"] == "PENDING", shown.text


def test_br_plt_07_delegation_commands_need_the_delegators_step_up(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Ruling R-48 (a): creating and ending a delegation need a TOTP verification at most five
    minutes old, as approving does (BR-PLT-06). A verified session whose verification is older is
    refused before anything is validated or written; after a step-up the same request succeeds
    (positive control), and both acts are audited with the delegator as the MFA-verified actor —
    and so is each refusal for want of the step-up (ruling R-111 (6))."""
    tenant_id = world.ben.member.tenant_id
    mia = with_factor(app, world.mia)
    clock.advance(timedelta(minutes=6))  # Ben verified when he enrolled
    body = delegation_body(world, clock)

    stale = post(app, DELEGATIONS, world.ben, body)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    assert stale.json()["detail"] == mfa.STEP_UP_REQUIRED
    # The refusal comes before validation: a body that names the delegator is refused the same way.
    invalid = post(
        app,
        DELEGATIONS,
        world.ben,
        {**body, "delegate_membership_id": str(world.ben.member.membership_id)},
    )
    assert (invalid.status_code, slug(invalid)) == (403, "mfa-step-up-required"), invalid.text
    assert delegation_rows(tenant_id) == 0

    ben = step_up(app, clock, world.ben)
    created = post(app, DELEGATIONS, ben, body)
    assert created.status_code == 201, created.text
    delegation = created.json()
    assert delegation["permissions"] == ["access.approve", "support_grant.approve"]
    assert delegation["delegator"]["id"] == str(ben.member.user_id)
    assert ids(get(app, DELEGATIONS, mia)) == [delegation["id"]]

    # Ending the delegation is the same act: not the delegate, and only with a step-up.
    revoke = f"{DELEGATIONS}/{delegation['id']}/revoke"
    clock.advance(timedelta(minutes=6))
    by_delegate = post(app, revoke, mia, {})
    assert (by_delegate.status_code, slug(by_delegate)) == (403, "forbidden"), by_delegate.text
    stale = post(app, revoke, ben, {"reason": "Back from leave"})
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    (listed,) = get(app, DELEGATIONS, ben).json()["items"]
    assert listed["revoked_at"] is None
    ben = step_up(app, clock, ben)
    revoked = post(app, revoke, ben, {"reason": "Back from leave"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_by"]["id"] == str(ben.member.user_id)

    assert delegation_audit(tenant_id) == [
        ("approval_delegation.create", "DENIED", ben.member.user_id, True),
        ("approval_delegation.create", "DENIED", ben.member.user_id, True),
        ("approval_delegation.create", "SUCCESS", ben.member.user_id, True),
        ("approval_delegation.revoke", "DENIED", ben.member.user_id, True),
        ("approval_delegation.revoke", "SUCCESS", ben.member.user_id, True),
    ]


def test_br_plt_07_the_delegation_commands_refuse_an_unverified_principal(
    app: FastAPI, world: World, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    """The commands enforce the session themselves (DG-CMD-01), whoever calls them: a principal
    that holds the permission but whose session never passed MFA is refused ``mfa-required``, one
    verified more than five minutes ago ``mfa-step-up-required``, and neither writes a row."""
    ben = world.ben.member
    files = LocalFileStore(app_settings.file_root)

    def attempt(verified_at: datetime | None) -> Problem:
        principal = Principal(
            kind=PrincipalKind.USER,
            id=ben.user_id,
            tenant_id=ben.tenant_id,
            membership_id=ben.membership_id,
            display_name="Ben",
            roles=("tenant_admin",),
            permissions=frozenset({"access.approve", "support_grant.approve"}),
            permission_scopes=MappingProxyType(
                {"access.approve": "*", "support_grant.approve": "*"}
            ),
            entity_scope="*",
            auth_method="password",
            mfa_verified_at=verified_at,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        )
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-delegation-command",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=clock.now(),
            format_locale="en-US",
        )
        body = delegation_body(world, clock)
        with (
            pytest.raises(Problem) as refused,
            unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow,
        ):
            approval_delegations.create_delegation(
                uow,
                delegate_membership_id=world.mia.member.membership_id,
                permissions=body["permissions"],
                valid_from=clock.now(),
                valid_to=clock.now() + timedelta(days=30),
                reason=body["reason"],
            )
        return refused.value

    never = attempt(None)
    assert (never.slug, never.status) == ("mfa-required", 403)
    old = attempt(clock.now() - timedelta(minutes=5, seconds=1))
    assert (old.slug, old.status) == ("mfa-step-up-required", 403)
    assert delegation_rows(ben.tenant_id) == 0


def test_delegations(app: FastAPI, world: World, submitted: Submitter, clock: FrozenClock) -> None:
    mia = with_factor(app, world.mia)
    now = clock.now()
    base = {
        "delegate_membership_id": str(world.mia.member.membership_id),
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=30)).isoformat(),
        "reason": "Annual leave in October",
    }
    not_held = post(app, DELEGATIONS, world.ben, {**base, "permissions": ["contract.approve"]})
    assert (not_held.status_code, slug(not_held)) == (422, "validation-failed"), not_held.text
    assert fields(not_held) == [
        ("permissions[0]", "T-PLT-21", "You can delegate only approval permissions you hold.")
    ]
    too_long = post(
        app,
        DELEGATIONS,
        world.ben,
        {
            **base,
            "permissions": ["access.approve"],
            "valid_to": (now + timedelta(days=91)).isoformat(),
        },
    )
    assert (too_long.status_code, slug(too_long)) == (422, "validation-failed"), too_long.text
    assert fields(too_long) == [("valid_to", "BR-PLT-07", "A delegation lasts at most 90 days.")]

    created = post(app, DELEGATIONS, world.ben, {**base, "permissions": ["access.approve"]})
    assert created.status_code == 201, created.text
    delegation = created.json()
    assert (
        delegation["permissions"],
        delegation["revoked_at"],
        delegation["delegator"]["id"],
        delegation["delegate"]["id"],
    ) == (["access.approve"], None, str(world.ben.member.user_id), str(world.mia.member.user_id))
    assert ids(get(app, DELEGATIONS, mia)) == [delegation["id"]]

    request = submitted(world.lena)
    path = f"{APPROVALS}/{request['id']}"
    as_delegate = get(app, path, mia)
    assert as_delegate.status_code == 200, as_delegate.text
    assert as_delegate.json()["can_decide"] is True

    revoke = f"{DELEGATIONS}/{delegation['id']}/revoke"
    by_delegate = post(app, revoke, mia, {})
    assert (by_delegate.status_code, slug(by_delegate)) == (403, "forbidden"), by_delegate.text
    revoked = post(app, revoke, world.ben, {"reason": "Back from leave"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["revoked_by"]["id"] == str(world.ben.member.user_id)
    again = post(app, revoke, world.ben, {})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    gone = get(app, path, mia)
    assert (gone.status_code, slug(gone)) == (404, "not-found")


# --- an entity-bound request over HTTP (R-41 (8); R-64) ------------------------------------------

BOUND = ApprovalSubjectType.POLICY_OVERRIDE  # the probe of a subject bound to legal entities
BOUND_PERMISSION = "contract.approve"  # held by the Revenue Reviewer role


@dataclass(frozen=True, slots=True)
class Bound:
    """Three legal entities, Revenue Reviewers scoped to them, and a probe subject bound to the
    entities a test names: ``new("A", "B")`` submits one as Lena."""

    rhea: Actor  # approves for entity A
    ravi: Actor  # approves for entities A and B
    rosa: Actor  # approves for entity C
    new: Callable[..., Mapping[str, Any]]
    entities: Mapping[str, UUID]  # "A", "B", "C"


@pytest.fixture
def bound(
    app: FastAPI,
    world: World,
    submitted: Submitter,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> Bound:
    tenant_id = world.lena.member.tenant_id
    stated: dict[UUID, SubjectEntities] = {}
    install(
        monkeypatch,
        replace(
            submitted.probe.spec(BOUND, required_permission=BOUND_PERMISSION),
            entity_id=approval_subjects._resolved_by_entities,
            entities=lambda _session, subject_id: stated[subject_id],
            amount_functional=lambda _session, subject_id: _amount(submitted.probe, subject_id),
            flags=lambda _session, subject_id: frozenset(
                submitted.probe.contents[subject_id].get("flags", ())
            ),
        ),
    )
    people = {name: colleague(tenant_id, name) for name in ("rhea", "ravi", "rosa")}
    with tenant_session(_all_entities(tenant_id)) as session:
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        entities: dict[str, UUID] = {}
        for key in "ABC":
            row = legal_entity_values(tenant_id, calendar_id=calendar["id"], code=f"ENT-{key}")
            session.execute(insert(legal_entity).values(**row))
            entities[key] = UUID(str(row["id"]))
        for name, keys in (("rhea", "A"), ("ravi", "AB"), ("rosa", "C")):
            insert_role_assignment(
                session,
                tenant_id=tenant_id,
                membership_id=people[name].membership_id,
                role_code="revenue_reviewer",
                entity_ids=[entities[key] for key in keys],
            )
        # Lena prepares for every entity: a preparer reads what she submits (R-64 (6)).
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=world.lena.member.membership_id,
            role_code="revenue_accountant",
        )

    def new(
        *keys: str,
        amount: str | None = None,
        flags: tuple[str, ...] = (),
        preview: ImpactPreview | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> Mapping[str, Any]:
        original = submitted.probe.new_subject

        def bound_subject(**content: Any) -> UUID:
            subject_id = original(**content, **({"flags": list(flags)} if flags else {}))
            stated[subject_id] = SubjectEntities(frozenset(entities[key] for key in keys))
            return subject_id

        monkeypatch.setattr(submitted.probe, "new_subject", bound_subject)
        try:
            return submitted(
                world.lena,
                subject_type=BOUND,
                amount=amount,
                preview=preview,
                reason_code=reason_code,
                comment=comment,
            )
        finally:
            monkeypatch.setattr(submitted.probe, "new_subject", original)

    return Bound(
        rhea=enrolled(app, clock, people["rhea"]),
        ravi=enrolled(app, clock, people["ravi"]),
        rosa=enrolled(app, clock, people["rosa"]),
        new=new,
        entities=MappingProxyType(entities),
    )


def _commands(app: FastAPI, actor: Actor, request: Mapping[str, Any]) -> dict[str, Any]:
    """What the read and each command on ``request`` answer ``actor``: (status, problem slug),
    and for the bulk item (its ``status``, its problem slug). Nothing here can succeed for an
    actor who may not decide and did not prepare the request."""
    request_id = str(request["id"])
    hashes = {"subject_content_sha256": request["subject_content_sha256"]}

    def answer(response: HttpResponse) -> tuple[int, str | None]:
        return response.status_code, None if response.status_code == 200 else slug(response)

    bulk = post(
        app, BULK_APPROVE, actor, {"items": [{"approval_request_id": request_id, **hashes}]}
    )
    assert bulk.status_code == 200, bulk.text
    (item,) = bulk.json()["results"]
    problem = item["problem"]
    return {
        "read": answer(get(app, f"{APPROVALS}/{request_id}", actor)),
        "approve": answer(post(app, f"{APPROVALS}/{request_id}/approve", actor, hashes)),
        "reject": answer(
            post(app, f"{APPROVALS}/{request_id}/reject", actor, {"comment": "Not mine to decide."})
        ),
        "withdraw": answer(post(app, f"{APPROVALS}/{request_id}/withdraw", actor, {})),
        "bulk": (item["status"], None if problem is None else problem["type"].rsplit("/", 1)[-1]),
    }


def test_commands_on_an_entity_bound_request_answer_as_the_read_does(
    app: FastAPI, world: World, bound: Bound
) -> None:
    """Supervisor rulings R-41 (8) and R-64 (REQ-PLT-012; 04 §16.10 rev 1.104): the HTTP parity of
    approve, reject, withdraw and bulk approval on a request bound to legal entities — the API
    tests before this one used tenant-level requests only. A request outside the caller's entity
    scope answers 404 on the read and on every command, and its bulk item carries that problem
    and no status: no command confirms an id the read denies. A caller who reads the request and
    holds the step's permission for one of its entities only is refused by name on approve and
    reject, 403 on withdraw, and the bulk item keeps the request's status. The approver who covers
    every entity decides it — by reject, and in bulk — and the preparer withdraws."""
    hidden: dict[str, Any] = {
        "read": (404, "not-found"),
        "approve": (404, "not-found"),
        "reject": (404, "not-found"),
        "withdraw": (404, "not-found"),
        "bulk": (None, "not-found"),
    }
    partial: dict[str, Any] = {
        "read": (200, None),
        "approve": (403, "forbidden"),
        "reject": (403, "forbidden"),
        "withdraw": (403, "forbidden"),
        "bulk": ("PENDING", "forbidden"),
    }
    both, only_b, third = bound.new("A", "B"), bound.new("B"), bound.new("A", "B")

    # Rosa approves for entity C: neither request names it.
    assert _commands(app, bound.rosa, both) == hidden
    assert _commands(app, bound.rosa, only_b) == hidden
    # Rhea approves for entity A: she reads the request of A and B and may not decide it; the
    # request of B alone is outside her scope (row-level security hides a request of one entity).
    assert _commands(app, bound.rhea, both) == partial
    assert _commands(app, bound.rhea, only_b) == hidden
    refused = post(
        app,
        f"{APPROVALS}/{both['id']}/approve",
        bound.rhea,
        {"subject_content_sha256": both["subject_content_sha256"]},
    )
    assert refused.json()["detail"] == EVERY_ENTITY_DETAIL
    withdrawn = post(app, f"{APPROVALS}/{both['id']}/withdraw", bound.rhea, {})
    assert withdrawn.json()["detail"] == WITHDRAW_DETAIL

    # The queue says the same: Rhea lists the request she reads and nothing waits for her.
    listed = get(app, APPROVALS, bound.rhea, status="PENDING")
    assert set(ids(listed)) == {str(both["id"]), str(third["id"])}
    waiting = get(app, APPROVALS, bound.rhea, assigned_to_me="true", count="true")
    assert (ids(waiting), waiting.headers["X-Erev-Total-Count"]) == ([], "0")
    assert ids(get(app, APPROVALS, bound.rosa, status="PENDING")) == []
    for request in (both, only_b, third):
        shown = get(app, f"{APPROVALS}/{request['id']}", world.lena)
        assert (shown.json()["status"], shown.json()["steps"][0]["decisions"]) == ("PENDING", [])

    # Positive controls: Ravi approves for A and B.
    waiting = get(app, APPROVALS, bound.ravi, assigned_to_me="true", count="true")
    assert set(ids(waiting)) == {str(request["id"]) for request in (both, only_b, third)}
    assert waiting.headers["X-Erev-Total-Count"] == "3"

    # API-S-Approval states the entities (R-41 (8); supervisor ruling R-104, findings Q-43 and
    # Q-48). A request bound to ONE entity carries ``entity``; a request of several carries
    # none, lists the entities the reader may read and counts all it names. The ``entity``
    # filter matches a request that names the entity, alone or among several — so "waiting for
    # me" for an entity, which the Home tile counts, is the inbox filtered by that entity.
    def stated(actor: Actor, request: Mapping[str, Any]) -> tuple[Any, ...]:
        body = get(app, f"{APPROVALS}/{request['id']}", actor).json()
        entity = body["entity"]
        return (
            None if entity is None else entity["code"],
            [ref["code"] for ref in body["entities"]],
            body["entity_count"],
            body["all_entities"],
        )

    assert stated(bound.ravi, only_b) == ("ENT-B", ["ENT-B"], 1, False)
    assert stated(bound.ravi, both) == (None, ["ENT-A", "ENT-B"], 2, False)
    # Rhea reads it through entity A alone: the entity outside her scope is counted, not named.
    assert stated(bound.rhea, both) == (None, ["ENT-A"], 2, False)
    for code, expected in (("ENT-A", (both, third)), ("ENT-B", (both, only_b, third))):
        of_entity = get(
            app, APPROVALS, bound.ravi, assigned_to_me="true", entity=code, count="true"
        )
        assert set(ids(of_entity)) == {str(request["id"]) for request in expected}, code
        assert of_entity.headers["X-Erev-Total-Count"] == str(len(expected)), code
    # An entity outside the reader's scope answers as an unknown one (REQ-PLT-012).
    outside = get(app, APPROVALS, bound.ravi, assigned_to_me="true", entity="ENT-C")
    assert (outside.status_code, slug(outside)) == (422, "validation-failed"), outside.text
    rejected = post(
        app, f"{APPROVALS}/{both['id']}/reject", bound.ravi, {"comment": "Wrong contract."}
    )
    assert (rejected.status_code, rejected.json()["status"]) == (200, "REJECTED"), rejected.text
    approved = post(
        app,
        BULK_APPROVE,
        bound.ravi,
        {
            "items": [
                {
                    "approval_request_id": str(only_b["id"]),
                    "subject_content_sha256": only_b["subject_content_sha256"],
                }
            ]
        },
    )
    assert approved.json()["results"] == [
        {"approval_request_id": str(only_b["id"]), "status": "APPROVED", "problem": None}
    ]
    gone = post(app, f"{APPROVALS}/{third['id']}/withdraw", world.lena, {"comment": "Not needed."})
    assert (gone.status_code, gone.json()["status"]) == (200, "WITHDRAWN"), gone.text


# --- content of a request over HTTP (item APR-CONTENT-SCOPE-1; 04 §16.10 rev 1.208) --------------

ATTACHMENTS = "/api/v1/attachments"
FLAG = "TP_CHANGE_GE_250K"


def upload(app: FastAPI, actor: Actor, name: str, content: bytes) -> HttpResponse:
    return call(
        app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": (name, content, "application/octet-stream")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )


def attach(app: FastAPI, actor: Actor, file_id: str, request_id: str) -> HttpResponse:
    return post(
        app,
        ATTACHMENTS,
        actor,
        {"file_object_id": file_id, "subject_type": "approval_request", "subject_id": request_id},
    )


def attached(app: FastAPI, actor: Actor, request_id: str) -> list[str]:
    """The file ids of the attachments the actor lists on the request."""
    listed = get(app, ATTACHMENTS, actor, subject_type="approval_request", subject_id=request_id)
    assert listed.status_code == 200, listed.text
    return [item["file_object_id"] for item in listed.json()["items"]]


def scoped(
    app: FastAPI,
    clock: FrozenClock,
    tenant_id: UUID,
    name: str,
    *,
    approves: list[UUID],
    prepares: list[UUID],
) -> Actor:
    """A colleague who approves contracts for ``approves`` (a Revenue Reviewer there) and
    prepares them for ``prepares`` (a Revenue Accountant there), at work with the second factor
    passed."""
    someone = colleague(tenant_id, name)
    with tenant_session(_all_entities(tenant_id)) as session:
        for role_code, entity_ids in (
            ("revenue_reviewer", approves),
            ("revenue_accountant", prepares),
        ):
            insert_role_assignment(
                session,
                tenant_id=tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
                entity_ids=entity_ids,
            )
    return enrolled(app, clock, someone)


def test_apr_content_scope_a_reader_of_one_entity_is_answered_the_header_of_a_request(
    app: FastAPI, world: World, bound: Bound, clock: FrozenClock
) -> None:
    """Item APR-CONTENT-SCOPE-1 (release blocker; the supervisor's ruling of 2026-10-01; 04
    §16.10 rev 1.208). Rhea approves for entity A and the request names A and B: before the
    ruling she read its summary, its amount, its preview — the file and its bytes — and its
    attachments, all of which state the record of entity B. She is answered the header and
    ``content_withheld``: the number, the status, the steps, her own entity and the count of
    all; the summary reads the subject type's name and the request's number; the amount and the
    preview are null, the flags and the attachments empty, a decision carries no comment. Her
    answer names nothing of entity B. The preview file and an attached file answer her 404 on
    both file routes, exactly as an unknown id; the attachment list is empty; attaching answers
    404 as for a subject she does not see. Her approval keeps the engine's refusal by name, 403,
    alone and in bulk — not the preview check's 409.

    The list cannot be made to tell what the row withholds: ordered by ``amount`` her withheld
    row comes last, as a request without an amount, also across a page boundary, and the count
    is the same; the list has no search and no filter on a content member, for anyone.

    Positive controls beside each: Ravi, who approves for A and B, and Lena, who prepared it
    for every entity."""
    tenant_id = world.lena.member.tenant_id
    both = bound.new("A", "B", amount="900.00", flags=(FLAG,), preview=rate_preview("1.00"))
    of_a = bound.new("A", amount="250.00")
    small = bound.new("A", amount="100.00")
    request_id = str(both["id"])
    path = f"{APPROVALS}/{request_id}"

    # Lena attaches her evidence while the request is pending (R-100 (b)).
    evidence = fx.PDF + b"% the master agreement of ENT-B\n"
    uploaded = upload(app, world.lena, "ent-b-master-agreement.pdf", evidence)
    assert uploaded.status_code == 201, uploaded.text
    file_id = str(uploaded.json()["id"])
    assert attach(app, world.lena, file_id, request_id).status_code == 201

    # Ravi covers both entities: the whole request.
    whole = get(app, path, bound.ravi)
    assert whole.status_code == 200, whole.text
    shown = whole.json()
    preview = shown["impact_preview"]
    assert (shown["content_withheld"], shown["summary"], shown["subject"]["display"]) == (
        False,
        SUMMARY,
        SUMMARY,
    )
    assert (shown["amount"], shown["flags"]) == ({"amount": "900.00", "currency": "USD"}, [FLAG])
    assert preview["sha256"] == both["impact_preview_sha256"]
    assert shown["attachments"] == [
        {"file_id": file_id, "original_filename": "ent-b-master-agreement.pdf"}
    ]
    assert shown["can_decide"] is True
    preview_id = str(preview["file_id"])

    # Rhea covers entity A: the header.
    answered = get(app, path, bound.rhea)
    assert answered.status_code == 200, answered.text
    body = answered.json()
    withheld = f"Policy override {both['request_no']}"
    assert set(body) == API_S_APPROVAL
    assert body["content_withheld"] is True
    assert body["subject"] == {**shown["subject"], "display": withheld}
    assert (body["subject"]["type"], body["subject"]["id"], body["subject"]["content_sha256"]) == (
        BOUND.value,
        str(both["subject_id"]),
        both["subject_content_sha256"],
    )
    assert (body["summary"], body["amount"], body["flags"]) == (withheld, None, [])
    assert (body["impact_preview"], body["attachments"], body["reopen_judgement"]) == (
        None,
        [],
        None,
    )
    assert (body["id"], body["request_no"], body["status"], body["can_decide"]) == (
        request_id,
        both["request_no"],
        "PENDING",
        False,
    )
    assert (
        body["entity"],
        [ref["code"] for ref in body["entities"]],
        body["entity_count"],
        body["all_entities"],
    ) == (None, ["ENT-A"], 2, False)
    assert [
        (step["step_no"], step["required_permission"], step["status"], step["decisions"])
        for step in body["steps"]
    ] == [(1, BOUND_PERMISSION, "ACTIVE", [])]
    assert (body["preparer"], body["routing"], body["submitted_at"]) == (
        shown["preparer"],
        shown["routing"],
        shown["submitted_at"],
    )
    for word in (
        "ENT-B",
        str(bound.entities["B"]),
        SUMMARY,
        "900.00",
        FLAG,
        file_id,
        preview_id,
        "ent-b-master-agreement",
        str(both["impact_preview_sha256"]),
    ):
        assert word not in answered.text, word
    # The list answers her the same row, and a request of her own entity whole.
    rows = {
        item["id"]: item
        for item in get(app, APPROVALS, bound.rhea, status="PENDING").json()["items"]
    }
    assert rows[request_id] == body
    own = rows[str(of_a["id"])]
    assert (own["content_withheld"], own["summary"], own["amount"]) == (
        False,
        SUMMARY,
        {"amount": "250.00", "currency": "USD"},
    )

    # The files of the request are content: 404 for her on both routes, as an unknown id.
    unknown = get(app, f"{FILES}/{new_id()}/content", bound.rhea)
    for file in (preview_id, file_id):
        for route in (f"{FILES}/{file}", f"{FILES}/{file}/content"):
            assert get(app, route, bound.ravi).status_code == 200, route
            assert get(app, route, world.lena).status_code == 200, route
            hidden = get(app, route, bound.rhea)
            assert hidden.status_code == 404, route
            assert slug(hidden) == "not-found", route
            assert {**hidden.json(), "instance": None} == {**unknown.json(), "instance": None}
    assert attached(app, bound.ravi, request_id) == [file_id]
    assert attached(app, bound.rhea, request_id) == []

    # Attaching asks the same rule. Pat and Quinn both prepare contracts for A and B, so each
    # holds a permission that attaches for every entity of the request (item ATT-MULTI-ENTITY-1
    # asks no more of them). Pat approves for A alone: the request is listed for her, her own
    # entity scope covers it, and its content is withheld — the stricter half of the rule — so
    # she attaches nothing. Quinn approves for A and B.
    a_and_b = [bound.entities[key] for key in "AB"]
    pat = scoped(app, clock, tenant_id, "pat", approves=[bound.entities["A"]], prepares=a_and_b)
    quinn = scoped(app, clock, tenant_id, "quinn", approves=a_and_b, prepares=a_and_b)
    seen = get(app, path, pat).json()
    assert (seen["content_withheld"], [ref["code"] for ref in seen["entities"]]) == (
        True,
        ["ENT-A", "ENT-B"],
    )
    memo = upload(app, pat, "pat-memo.pdf", fx.PDF + b"% pat\n")
    assert memo.status_code == 201, memo.text
    refused = attach(app, pat, str(memo.json()["id"]), request_id)
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    unseen = attach(app, pat, str(memo.json()["id"]), str(new_id()))
    assert {**refused.json(), "instance": None} == {**unseen.json(), "instance": None}
    note = upload(app, quinn, "quinn-note.pdf", fx.PDF + b"% quinn\n")
    assert note.status_code == 201, note.text
    assert attach(app, quinn, str(note.json()["id"]), request_id).status_code == 201
    assert set(attached(app, bound.ravi, request_id)) == {file_id, str(note.json()["id"])}
    assert attached(app, pat, request_id) == []

    # Her approval is refused by the engine, by name — the request has a preview she cannot
    # read, and the preview check leaves a request she cannot decide to the decision.
    alone = post(app, f"{path}/approve", bound.rhea, approval_body(both))
    assert (alone.status_code, slug(alone)) == (403, "forbidden"), alone.text
    assert alone.json()["detail"] == EVERY_ENTITY_DETAIL
    bulk = post(
        app,
        BULK_APPROVE,
        bound.rhea,
        {"items": [{"approval_request_id": request_id, **approval_body(both)}]},
    )
    assert bulk.status_code == 200, bulk.text
    (item,) = bulk.json()["results"]
    assert (item["status"], item["problem"]["type"]) == ("PENDING", f"{PROBLEM_BASE}forbidden")
    assert decided(tenant_id, both["id"]) == ("PENDING", 0)

    # The list ordered by amount: Ravi's largest first; Rhea's withheld row as one without an
    # amount, last — on one page, across a page boundary, and with the same count.
    def by_amount(actor: Actor, **params: str) -> HttpResponse:
        return get(
            app,
            APPROVALS,
            actor,
            status="PENDING",
            subject_type=BOUND.value,
            sort="amount",
            **params,
        )

    largest, middle, least = request_id, str(of_a["id"]), str(small["id"])
    assert ids(by_amount(bound.ravi)) == [largest, middle, least]
    hers = by_amount(bound.rhea, count="true")
    assert ids(hers) == [middle, least, largest]
    assert [row["amount"] for row in hers.json()["items"]] == [
        {"amount": "250.00", "currency": "USD"},
        {"amount": "100.00", "currency": "USD"},
        None,
    ]
    assert hers.headers["X-Erev-Total-Count"] == "3"
    first = by_amount(bound.rhea, limit="2")
    assert ids(first) == [middle, least]
    rest = by_amount(bound.rhea, limit="2", cursor=first.json()["next_cursor"])
    assert (ids(rest), rest.json()["next_cursor"]) == ([largest], None)
    one = by_amount(bound.rhea, limit="1")
    two = by_amount(bound.rhea, limit="1", cursor=one.json()["next_cursor"])
    three = by_amount(bound.rhea, limit="1", cursor=two.json()["next_cursor"])
    assert [ids(page) for page in (one, two, three)] == [[middle], [least], [largest]]
    assert three.json()["next_cursor"] is None
    # No search and no filter reads a content member — for her and for him alike.
    for actor in (bound.rhea, bound.ravi):
        searched = get(app, APPROVALS, actor, q="access approver")
        assert (searched.status_code, slug(searched)) == (422, "validation-failed")
        assert fields(searched) == [("q", "API-C-09", "approvals has no search.")]
        ranged = get(app, APPROVALS, actor, amount_min="500.00")
        assert (ranged.status_code, slug(ranged)) == (422, "validation-failed")
        assert fields(ranged) == [
            ("amount_min", "API-C-09", "amount_min is not a filter of approvals.")
        ]

    # What the decider writes is content: the rejection reaches her without its comment.
    comment = "ENT-B's master agreement is not signed."
    rejected = post(app, f"{path}/reject", bound.ravi, {"comment": comment})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["steps"][0]["decisions"][0]["comment"] == comment
    after = get(app, path, bound.rhea).json()
    (decision,) = after["steps"][0]["decisions"]
    assert (after["status"], decision["decision"], decision["comment"]) == (
        "REJECTED",
        "REJECT",
        None,
    )
    assert decision["approver"]["id"] == str(bound.ravi.member.user_id)
    assert comment not in get(app, path, bound.rhea).text
    assert get(app, path, world.lena).json()["steps"][0]["decisions"][0]["comment"] == comment


# --- a subject type without a specification (item APR-SETUP-RULE-2) ------------------------------


def test_apr_request_reason_a_request_answers_what_it_was_submitted_with(
    app: FastAPI, world: World, bound: Bound
) -> None:
    """Item APR-REQUEST-REASON-1 (supervisor rulings R-83 (d) and R-104 (a); the ruling of
    2026-10-01; 04 §16.10 rev 1.252): API-S-Approval answers the reason code and the comment a
    request was submitted with — the justification an approver reads before deciding (SCREENS
    §15.4 region 3) and the reason the banner of a pending reopen names (SCREENS_B §1.1).

    Both are content. Ravi approves for A and B and reads them on a request of A and B, and so
    does Lena, who prepared it for every entity. Rhea approves for A: her answer is the header,
    without them, and names neither. ``GET /approvals`` answers each reader the same row as
    the single read — the reopen banner takes its request from the list.

    Fail-first: the answer had neither member."""
    reason, comment = "DATA_CORRECTION", "ENT-B's order was booked twice."
    both = bound.new("A", "B", amount="900.00", reason_code=reason, comment=comment)
    plain = bound.new("A", amount="250.00")

    def submitted_with(
        actor: Actor, request: Mapping[str, Any]
    ) -> tuple[bool, str | None, str | None]:
        answered = get(app, f"{APPROVALS}/{request['id']}", actor)
        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert set(body) == API_S_APPROVAL
        rows = {
            item["id"]: item
            for item in get(app, APPROVALS, actor, status="PENDING").json()["items"]
        }
        assert rows[body["id"]] == body
        return body["content_withheld"], body["reason_code"], body["comment"]

    assert submitted_with(bound.ravi, both) == (False, reason, comment)
    assert submitted_with(world.lena, both) == (False, reason, comment)
    assert submitted_with(bound.rhea, both) == (True, None, None)
    header = get(app, f"{APPROVALS}/{both['id']}", bound.rhea).text
    for word in (reason, comment):
        assert word not in header, word

    # Positive control: a request submitted with neither answers null, also to who reads it whole.
    assert submitted_with(bound.rhea, plain) == (False, None, None)
    assert submitted_with(world.lena, plain) == (False, None, None)


def test_apr_decision_code_content_a_decisions_reason_code_is_withheld_with_its_comment(
    app: FastAPI, world: World, bound: Bound
) -> None:
    """Item APR-DECISION-CODE-CONTENT-1 (the supervisor's ruling of 2026-10-01 on the lane's own
    finding; 04 §16.10 rev 1.252) — a residue of item APR-CONTENT-SCOPE-1. ``POST
    /approvals/{id}/approve`` and ``/reject`` take ``reason_code``: free text of up to 100
    characters, bound to no code table. It was answered with the header, so an approver for A
    and B could write a hundred characters that a reader of A read — the comment's channel under
    another name.

    Ravi approves for A and B: he rejects one request of A and B and approves another, each
    with a comment and a code. Rhea approves for A: she reads who decided, which decision it
    was and when, and neither the comment nor the code. Ravi reads both, and so does Lena, who
    prepared the requests for every entity. ``GET /approvals`` answers each of them the same
    row.

    Fail-first: Rhea read both codes."""
    why, kept = "ENT-B's contract is not signed.", "The override stands."
    rejected_code = "ENT-B order 4471: no countersignature"
    approved_code = "ENT-B's order is one contract with ENT-A's"
    first = bound.new("A", "B", amount="900.00")
    second = bound.new("A", "B", amount="700.00")
    rejection = post(
        app,
        f"{APPROVALS}/{first['id']}/reject",
        bound.ravi,
        {"comment": why, "reason_code": rejected_code},
    )
    assert rejection.status_code == 200, rejection.text
    approval = post(
        app,
        f"{APPROVALS}/{second['id']}/approve",
        bound.ravi,
        {
            "subject_content_sha256": second["subject_content_sha256"],
            "comment": kept,
            "reason_code": approved_code,
        },
    )
    assert approval.status_code == 200, approval.text

    def decided(
        actor: Actor, request: Mapping[str, Any]
    ) -> list[tuple[str, str | None, str | None]]:
        answered = get(app, f"{APPROVALS}/{request['id']}", actor)
        assert answered.status_code == 200, answered.text
        body = answered.json()
        rows = {item["id"]: item for item in get(app, APPROVALS, actor).json()["items"]}
        assert rows[body["id"]] == body
        return [
            (decision["decision"], decision["comment"], decision["reason_code"])
            for step in body["steps"]
            for decision in step["decisions"]
        ]

    # Positive controls: the readers of the whole request read the decider's words.
    for reader in (bound.ravi, world.lena):
        assert decided(reader, first) == [("REJECT", why, rejected_code)]
        assert decided(reader, second) == [("APPROVE", kept, approved_code)]
    # Rhea reads the header: the decisions, and nothing the decider wrote.
    assert decided(bound.rhea, first) == [("REJECT", None, None)]
    assert decided(bound.rhea, second) == [("APPROVE", None, None)]
    for request in (first, second):
        header = get(app, f"{APPROVALS}/{request['id']}", bound.rhea).text
        for word in (why, kept, rejected_code, approved_code):
            assert word not in header, word


def test_a_request_of_a_subject_type_without_a_specification_is_refused_by_name(
    app: FastAPI, world: World, submitted: Submitter
) -> None:
    """Item APR-SETUP-RULE-2 (the supervisor's ruling of 2026-10-01 on the independent review of
    the setup rule; 04 §16.10 rev 1.224; rulings R-64 (7) (c) and R-87 (3)). A pending request
    whose subject type has no specification yet (``subjects.PENDING_SUBJECTS``) comes from a seed:
    no command submits one. It waits for nobody and ``can_decide`` is false for everyone — and
    the commands say the same. Approve, reject, the bulk approval's item and the preparer's
    withdraw answer 409 ``invalid-transition`` by name; nothing is decided, voided or audited,
    and the request beside it, of a specified subject, is approved as ever.

    Fail-first: each of the four raised ``LookupError`` from ``spec_for`` — an error no route
    answers."""
    tenant_id = world.lena.member.tenant_id
    with tenant_session(_all_entities(tenant_id)) as session:
        seeded = approval_request_values(
            tenant_id,
            current_step_no=1,
            subject_type=ApprovalSubjectType.AI_PROPOSAL_ACCEPTANCE.value,
            preparer_id=world.lena.member.user_id,
            summary="Accept the proposed allocation",
        )
        session.execute(insert(approval_request).values(**seeded))
        session.execute(
            insert(approval_step).values(
                **approval_step_values(tenant_id, approval_request_id=seeded["id"])
            )
        )
    request_id = str(seeded["id"])
    path = f"{APPROVALS}/{request_id}"
    refusal = [("subject.type", "SM-01", NO_SPECIFICATION)]
    hashes = {"subject_content_sha256": str(seeded["subject_content_sha256"])}

    # Ben holds the step's permission for every entity; the read says that nobody decides it.
    shown = get(app, path, world.ben)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["status"], shown.json()["can_decide"]) == ("PENDING", False)

    for command, body in (
        ("approve", {**hashes, "comment": "Looks right"}),
        ("reject", {"comment": "Not this quarter."}),
    ):
        refused = post(app, f"{path}/{command}", world.ben, body)
        assert refused.status_code == 409, (command, refused.text)
        assert slug(refused) == "invalid-transition", (command, refused.text)
        assert fields(refused) == refusal, command

    # The bulk approval refuses that item alone; the specified request beside it is approved.
    specified = submitted(world.lena)
    bulk = post(
        app,
        BULK_APPROVE,
        world.ben,
        {
            "items": [
                {"approval_request_id": request_id, **hashes},
                {
                    "approval_request_id": str(specified["id"]),
                    "subject_content_sha256": specified["subject_content_sha256"],
                },
            ]
        },
    )
    assert bulk.status_code == 200, bulk.text
    stopped, approved = bulk.json()["results"]
    assert (stopped["status"], stopped["problem"]["type"]) == (
        "PENDING",
        f"{PROBLEM_BASE}invalid-transition",
    )
    assert [
        (error["field"], error["rule_id"], error["message"])
        for error in stopped["problem"]["errors"]
    ] == refusal
    assert approved == {
        "approval_request_id": str(specified["id"]),
        "status": "APPROVED",
        "problem": None,
    }

    # The preparer's withdraw is refused by the same name; anyone else as for any request.
    other = post(app, f"{path}/withdraw", world.ben, {})
    assert (other.status_code, slug(other)) == (403, "forbidden"), other.text
    withdrawn = post(app, f"{path}/withdraw", world.lena, {"comment": "Seeded by mistake"})
    assert withdrawn.status_code == 409, withdrawn.text
    assert slug(withdrawn) == "invalid-transition", withdrawn.text
    assert fields(withdrawn) == refusal

    # Nothing moved: the request is pending, undecided, and no command of it is on the trail.
    after = get(app, path, world.lena)
    assert after.status_code == 200, after.text
    assert (after.json()["status"], after.json()["void_reason"]) == ("PENDING", None)
    assert [step["decisions"] for step in after.json()["steps"]] == [[]]
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        events = session.execute(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.approval_request_id == seeded["id"])
        ).scalar_one()
    assert events == 0
