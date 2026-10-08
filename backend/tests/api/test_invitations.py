"""API-R-01 invitation lookup and acceptance (04 T-PLT-07, §16.12; PRD BR-PLT-01, ERR-21; SCREENS_B
§12.3; BUILD_SPEC PLF-15).

Each test provisions its own "Acme Test" workspace with a unique code and admin email: users are
global, and the platform domain tests keep ``acme-test`` with ``admin@acme.test`` uninvited for the
whole session (SPEC-Q-180).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    audit_event,
    notification_preference,
    outbox_message,
    security_event,
    tenant_membership,
)
from erev_api.domain.platform.provisioning import (
    OperatorActor,
    TenantProvisionRequest,
    TenantProvisionResult,
    provision_tenant,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import tenant_id_of
from support.http import HttpResponse, call
from support.links import emailed_token
from support.principals import LOGIN, PASSWORD, cookie_of

LOOKUP = "/api/v1/session/invitations/lookup"
ENROLL = "/api/v1/me/mfa/enroll"
CONFIRM = "/api/v1/me/mfa/confirm"
USERS = "/api/v1/users"
ACCEPT = "/api/v1/session/accept-invitation"
SESSION = "/api/v1/session"
WEAK_PASSWORD = "password1234"


@dataclass(frozen=True, slots=True)
class Invited:
    result: TenantProvisionResult
    tenant_id: UUID
    email: str
    token: str


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).rsplit("/", 1)[1]


def invited(keyring: KeyRing, clock: FrozenClock) -> Invited:
    """A provisioned "Acme Test" workspace and the token of its provisioning email."""
    code = f"acme-{secrets.token_hex(6)}"
    email = f"admin@{code}.test"
    result = provision_tenant(
        TenantProvisionRequest(
            code=code,
            display_name="Acme Test",
            reporting_currency="USD",
            is_demo=False,
            admin_email=email,
        ),
        actor=OperatorActor(
            channel="CLI", operator_user_id=None, os_user="tests", request_id=f"r-{code}"
        ),
        clock=clock,
        keyring=keyring,
    )
    tenant_id = tenant_id_of(result)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        payload = db.execute(
            select(outbox_message.c.payload).where(
                outbox_message.c.aggregate_id == result.admin_membership_id
            )
        ).scalar_one()
    # The message names the token; the link is composed as the email carries it (T-INT-03).
    token = emailed_token(payload, keyring, prefix="/accept-invitation#token=")
    return Invited(result=result, tenant_id=tenant_id, email=email, token=token)


def membership_of(invitation: Invited) -> Mapping[str, Any]:
    context = DbContext(tenant_id=invitation.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as db:
        return (
            db.execute(
                select(tenant_membership).where(
                    tenant_membership.c.id == invitation.result.admin_membership_id
                )
            )
            .mappings()
            .one()
        )


def test_lookup_and_accept(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    invitation = invited(keyring, clock)
    lookup = call(app, "POST", LOOKUP, json={"token": invitation.token})
    assert lookup.status_code == 200, lookup.text
    body = lookup.json()
    assert set(body) == {
        "workspace_display_name",
        "inviter_display_name",
        "email",
        "expires_at",
        "has_password",
    }
    assert (body["workspace_display_name"], body["inviter_display_name"], body["email"]) == (
        "Acme Test",
        None,
        invitation.email,
    )
    # 04 §16.12 rev 1.38: the provisioned administrator has no password yet (D-98 candidate 24).
    assert body["has_password"] is False
    assert datetime.fromisoformat(body["expires_at"]) == invitation.result.invitation_expires_at

    weak = call(app, "POST", ACCEPT, json={"token": invitation.token, "password": WEAK_PASSWORD})
    assert (weak.status_code, slug(weak)) == (422, "password-policy"), weak.text
    assert weak.json()["detail"] == "Choose a less common password."
    assert weak.json()["errors"][0]["field"] == "password"
    assert membership_of(invitation)["status"] == "INVITED"

    accepted = call(app, "POST", ACCEPT, json={"token": invitation.token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    session = accepted.json()
    assert session["authenticated"] is True
    assert session["user"]["email"] == invitation.email
    assert session["active_tenant"]["id"] == str(invitation.tenant_id)
    assert session["active_tenant"]["display_name"] == "Acme Test"
    assert accepted.headers["X-Erev-Tenant-Kind"] == "production"
    token = cookie_of(accepted)
    again = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"})
    assert again.json()["active_tenant"]["id"] == str(invitation.tenant_id)

    membership = membership_of(invitation)
    assert membership["status"] == "ACTIVE"
    assert membership["activated_at"] == clock.now()
    assert (membership["invitation_token_sha256"], membership["invitation_expires_at"]) == (
        None,
        None,
    )
    user_id = membership["user_id"]
    with identity_session(request_id="tests-invitation-events") as db:
        events = db.execute(
            select(security_event.c.kind, security_event.c.tenant_id, security_event.c.session_id)
            .where(security_event.c.user_id == user_id)
            .order_by(security_event.c.chain_seq)
        ).all()
    assert [event.kind for event in events] == ["TENANT_SELECTED"]
    assert events[0].tenant_id == invitation.tenant_id
    assert events[0].session_id is not None

    context = DbContext(tenant_id=invitation.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as db:
        accept_events = (
            db.execute(select(audit_event).where(audit_event.c.action == "membership.accept"))
            .mappings()
            .all()
        )
        preferences = db.execute(
            select(notification_preference.c.kind).where(
                notification_preference.c.membership_id == invitation.result.admin_membership_id
            )
        ).all()
    [accept_event] = accept_events
    assert (accept_event["actor_kind"], accept_event["actor_id"], accept_event["object_id"]) == (
        "USER",
        user_id,
        invitation.result.admin_membership_id,
    )
    assert (accept_event["before"], accept_event["after"]["status"]) == (
        {"status": "INVITED"},
        "ACTIVE",
    )
    assert {str(row.kind) for row in preferences} == {
        "APPROVAL_ASSIGNED",
        "ITEM_REJECTED",
        "APPROVAL_VOIDED",
        "JOB_FAILED",
        "CLOSE_BLOCKER_RAISED",
        "CHAIN_VERIFICATION_FAILED",
        "EXPORT_FAILED",
        "EXCEPTION_ASSIGNED",
        "SUPPORT_GRANT_REQUESTED",
        "ITEM_APPROVED",
        "PERIOD_LOCKED",
        "PERIOD_REOPENED",
        "APPROVAL_UNASSIGNED",
    }

    signed_in = call(app, "POST", LOGIN, json={"email": invitation.email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    replayed = call(app, "POST", ACCEPT, json={"token": invitation.token, "password": PASSWORD})
    assert (replayed.status_code, slug(replayed)) == (404, "not-found")


def test_r_111_9_the_session_of_an_accepted_invitation_owes_the_second_factor(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The review's untested branches of rule 1 (ruling R-111 (9); REQ-PLT-005). Accepting an
    invitation opens a session with the password alone. The provisioned administrator holds
    ``requires_mfa`` permissions, so that session owes enrolment like a session of a sign-in: the
    answer says so, every route but the enrolment routes refuses it, and enrolling settles it."""
    invitation = invited(keyring, clock)
    accepted = call(app, "POST", ACCEPT, json={"token": invitation.token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    session = accepted.json()
    assert (session["mfa_required"], session["mfa_enrolment_required"]) == (False, True)
    token = cookie_of(accepted)
    cookie = {"Cookie": f"erev_session={token}"}

    refused = call(app, "GET", USERS, headers=cookie)
    assert (refused.status_code, slug(refused)) == (403, "mfa-required"), refused.text
    reread = call(app, "GET", SESSION, headers=cookie).json()
    assert (reread["authenticated"], reread["mfa_enrolment_required"]) == (True, True)

    def headers() -> dict[str, str]:
        return {
            **cookie,
            "X-CSRF-Token": reread["csrf_token"],
            "Idempotency-Key": f"k-{secrets.token_hex(8)}",
        }

    started = call(app, "POST", ENROLL, headers=headers())
    assert started.status_code == 200, started.text
    code = totp.code_at(started.json()["secret_base32"], totp.time_step(clock.now()))
    confirmed = call(app, "POST", CONFIRM, json={"code": code}, headers=headers())
    assert confirmed.status_code == 200, confirmed.text
    verified = {"Cookie": f"erev_session={cookie_of(confirmed)}"}
    assert call(app, "GET", USERS, headers=verified).status_code == 200


def lookup_failures(request_ids: Sequence[str]) -> list[tuple[str, str, Any]]:
    """(kind, outcome, detail) of the ``INVITATION_LOOKUP_FAILED`` events of the given requests."""
    with identity_session(request_id="tests-invitation-lookup-failures") as db:
        rows = db.execute(
            select(security_event.c.kind, security_event.c.outcome, security_event.c.detail)
            .where(
                security_event.c.kind == "INVITATION_LOOKUP_FAILED",
                security_event.c.request_id.in_(list(request_ids)),
            )
            .order_by(security_event.c.chain_seq)
        ).all()
    return [(row.kind, row.outcome, row.detail) for row in rows]


def test_expired_or_unknown_token_not_found(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    invitation = invited(keyring, clock)
    clock.advance(timedelta(days=7, seconds=1))
    expired = call(app, "POST", LOOKUP, json={"token": invitation.token})
    assert (expired.status_code, slug(expired)) == (404, "not-found"), expired.text
    refused = call(app, "POST", ACCEPT, json={"token": invitation.token, "password": PASSWORD})
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert membership_of(invitation)["status"] == "INVITED"
    # 04 T-PLT-07 rev 1.38 (D-98 candidate 20): each refusal writes one anonymous security event
    # naming its reason and route; the token hash is never stored.
    request_ids = [expired.headers["X-Request-Id"], refused.headers["X-Request-Id"]]
    events = lookup_failures(request_ids)
    assert [(kind, outcome) for kind, outcome, _ in events] == [
        ("INVITATION_LOOKUP_FAILED", "FAILED"),
        ("INVITATION_LOOKUP_FAILED", "FAILED"),
    ]
    assert [detail for _, _, detail in events] == [
        {"reason": "expired", "route": "lookup"},
        {"reason": "expired", "route": "accept"},
    ]
    with identity_session(request_id="tests-invitation-lookup-failures") as db:
        anonymous = db.execute(
            select(security_event.c.user_id, security_event.c.email_sha256).where(
                security_event.c.request_id.in_(request_ids),
                security_event.c.kind == "INVITATION_LOOKUP_FAILED",
            )
        ).all()
    assert anonymous == [(None, None), (None, None)]


def test_unknown_and_malformed_tokens_write_the_failure_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    unknown_token = secrets.token_urlsafe(32)
    unknown = call(app, "POST", LOOKUP, json={"token": unknown_token})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    malformed = call(app, "POST", LOOKUP, json={"token": "not-a-token"})
    assert (malformed.status_code, slug(malformed)) == (404, "not-found"), malformed.text
    events = lookup_failures([unknown.headers["X-Request-Id"], malformed.headers["X-Request-Id"]])
    assert [detail for _, _, detail in events] == [
        {"reason": "unknown", "route": "lookup"},
        {"reason": "malformed", "route": "lookup"},
    ]


def test_successful_lookup_writes_no_failure_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    invitation = invited(keyring, clock)
    lookup = call(app, "POST", LOOKUP, json={"token": invitation.token})
    assert lookup.status_code == 200, lookup.text
    assert lookup_failures([lookup.headers["X-Request-Id"]]) == []

    unknown = call(app, "POST", LOOKUP, json={"token": secrets.token_urlsafe(32)})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found")
