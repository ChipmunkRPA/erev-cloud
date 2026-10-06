"""API-R-14 Support grants (04 §15.3 API-R-14, T-PLT-33; SCREENS_B §9.14 SF-14:support-access,
SB-R-05; REQ-PLT-036; BUILD_SPEC PLF-26, BS1-D-27).

Tomas and Grace are Tenant Admins enrolled in MFA. Tomas records a request on an operator's behalf,
Grace approves it, and Tomas revokes the grant while the operator has the workspace open.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.cli import CliServices
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import audit_event, user_session
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.operators import approve, create_operator, operator_services, operator_signed_in
from support.principals import (
    Actor,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    select_tenant,
    sign_in,
    workspace,
)
from support.rows import insert_contract_rows, insert_role_assignment

GRANTS = "/api/v1/support-grants"
AUDIT = "/api/v1/audit-events"
FILES = "/api/v1/files"
ATTACHMENTS = "/api/v1/attachments"
PROBLEM_BASE = "https://erev.dev/problems/"
REASON = "Investigation finished early"


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def services(keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> CliServices:
    # The CLI stores files the api reads, so both share one file store.
    return operator_services(keyring, clock, app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    context = DbContext(tenant_id=tomas.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for someone in (tomas, grace):
            insert_role_assignment(
                session,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code="tenant_admin",
            )
    return World(tomas=enrolled(app, clock, tomas), grace=enrolled(app, clock, grace))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def test_revoke_grant(
    app: FastAPI, clock: FrozenClock, services: CliServices, world: World
) -> None:
    operator = create_operator(services)
    now = clock.now()
    created = post(
        app,
        GRANTS,
        world.tomas,
        {
            "operator_email": operator["email"],
            "reason": "Investigate export failure",
            "ticket_ref": "SUP-2291",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_to": (now + timedelta(hours=7)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    assert "location" not in created.headers
    body = created.json()
    assert (body["status"], body["created_by"]["kind"], body["operator"]["id"]) == (
        "REQUESTED",
        "USER",
        operator["id"],
    )
    grant_id = body["id"]
    approved = approve(app, body["approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text

    signed = operator_signed_in(app, clock, operator["email"])
    selected = select_tenant(app, signed, world.tenant_id)
    assert selected.status_code == 200, selected.text
    operator_token = cookie_of(selected)

    listed = call(
        app,
        "GET",
        GRANTS,
        params={"status": "APPROVED"},
        headers=cookie_headers(world.tomas.token, key=False),
    )
    assert listed.status_code == 200, listed.text
    assert [(item["id"], item["status"]) for item in listed.json()["items"]] == [
        (grant_id, "APPROVED")
    ]

    short = post(app, f"{GRANTS}/{grant_id}/revoke", world.tomas, {"reason": "done"})
    assert (short.status_code, slug(short)) == (422, "validation-failed")
    assert [(error["field"], error["rule_id"]) for error in short.json()["errors"]] == [
        ("reason", "BR-PLT-08")
    ]

    revoked = post(app, f"{GRANTS}/{grant_id}/revoke", world.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    out = revoked.json()
    assert out["status"] == "REVOKED"
    assert out["revoked_at"] is not None
    assert out["revoked_by"]["id"] == str(world.tomas.member.user_id)
    assert out["revoked_by"]["kind"] == "USER"
    with identity_session(request_id="tests-support-grant-revoke") as db:
        reasons = db.scalars(
            select(user_session.c.end_reason).where(
                user_session.c.operator_support_grant_id == UUID(grant_id)
            )
        ).all()
    assert reasons == ["REVOKED"]
    after = call(app, "GET", AUDIT, headers=cookie_headers(operator_token, key=False))
    assert (after.status_code, slug(after)) == (401, "unauthenticated")

    again = post(app, f"{GRANTS}/{grant_id}/revoke", world.tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition")
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        audited = session.execute(
            select(audit_event.c.actor_kind, audit_event.c.comment).where(
                audit_event.c.action == "support_grant.revoke",
                audit_event.c.object_id == UUID(grant_id),
            )
        ).all()
    assert [(row.actor_kind, row.comment) for row in audited] == [("USER", REASON)]


def test_req_plt_036_a_support_grant_reads_records_and_no_stored_file(
    app: FastAPI, clock: FrozenClock, services: CliServices, world: World
) -> None:
    """Security review ST-1 (rulings R-33, R-48 (c)). The read-only scope of a support grant
    carries ``audit.read``, which opened every stored file: an operator under a grant downloaded
    the workspace's contract documents. The scope names no file purpose, so the operator reads
    the records the grant opens — and no file, content or metadata."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    nora_member = colleague(world.tenant_id, "nora")
    with tenant_session(context) as session:
        chain = insert_contract_rows(session, world.tenant_id)
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=nora_member.membership_id,
            role_code="revenue_accountant",
        )
    nora = workspace(app, nora_member, sign_in(app, nora_member.email))
    document = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n% signed order form\n%%EOF\n"
    uploaded = call(
        app,
        "POST",
        FILES,
        data={"purpose": "ATTACHMENT"},
        files={"file": ("order-form.pdf", document, "application/pdf")},
        headers=cookie_headers(nora.token, nora.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    subject = {"subject_type": "contract", "subject_id": str(chain.contract_id)}
    linked = post(app, ATTACHMENTS, nora, {"file_object_id": file_id, **subject})
    assert linked.status_code == 201, linked.text

    operator = create_operator(services)
    now = clock.now()
    created = post(
        app,
        GRANTS,
        world.tomas,
        {
            "operator_email": operator["email"],
            "reason": "Investigate export failure",
            "ticket_ref": "SUP-2291",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_to": (now + timedelta(hours=7)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    assert approve(app, created.json()["approval_request_id"], world.grace).status_code == 200
    selected = select_tenant(
        app, operator_signed_in(app, clock, operator["email"]), world.tenant_id
    )
    assert selected.status_code == 200, selected.text
    support = cookie_headers(cookie_of(selected), key=False)

    # Positive control: the grant reads the workspace's records, the contract's attachment list
    # among them.
    assert call(app, "GET", AUDIT, headers=support).status_code == 200
    listed = call(app, "GET", ATTACHMENTS, params=subject, headers=support)
    assert listed.status_code == 200, listed.text
    assert [item["file_object_id"] for item in listed.json()["items"]] == [file_id]
    # ... and no stored file: metadata and content answer as for an id that names nothing.
    unknown = call(app, "GET", f"{FILES}/{uuid4()}/content", headers=support)
    for path in (f"{FILES}/{file_id}", f"{FILES}/{file_id}/content"):
        hidden = call(app, "GET", path, headers=support)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), (path, hidden.text)
        assert {**hidden.json(), "instance": None} == {**unknown.json(), "instance": None}
    # The members who read the contract still read its document.
    for reader in (nora, world.tomas):
        shown = call(
            app,
            "GET",
            f"{FILES}/{file_id}/content",
            headers=cookie_headers(reader.token, key=False),
        )
        assert (shown.status_code, shown.content) == (200, document), shown.text
