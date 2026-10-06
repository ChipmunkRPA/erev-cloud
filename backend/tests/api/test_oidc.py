"""API-R-01 OIDC sign-in against the in-process mock IdP (04 T-PLT-02, T-PLT-03, E-79
``OIDC_LINKED``, §16.12; 05 SAR-27, THR-05, ADP-24; 03 REQ-PLT-006; BUILD_SPEC PLF-27, BS1-D-25).

Maya already has an account as a provisioned workspace's admin. The IdP also knows Omar, whose email
it has not verified, and Ines of another organisation. The provider is bound to ``acme.test``, and
an identity signs in through it only once the operator has invited it for the provider
(REQ-PLT-006; supervisor ruling R-48 (d)).
"""

from __future__ import annotations

import json
import secrets
import threading
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

import pytest
from erev_api.adapters.mocks.oidc import CODE as MOCK_CODE
from erev_api.adapters.mocks.oidc import MockUser, OidcMock, issuer_for
from erev_api.auth import oidc, sessions, totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.sessions import sha256_hex
from erev_api.cli import CliServices
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, owner_engine, tenant_session
from erev_api.db.tables.platform import (
    app_user,
    identity_provider,
    role_assignment,
    security_event,
    tenant_membership,
    user_session,
)
from fastapi import FastAPI
from sqlalchemy import func, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.oidc import (
    CLIENT_ID,
    EMAIL_DOMAINS,
    PROVIDER_CODE,
    change_domains,
    create_mock_oidc,
    disable,
    enable,
    end_sessions,
    idp_create_args,
    invite,
    oidc_app,
    remove_provider,
)
from support.operators import invoke, operator_services
from support.plans import sent
from support.principals import member, sign_in

START = f"/api/v1/session/oidc/{PROVIDER_CODE}/start"
SESSION = "/api/v1/session"
LOGOUT = "/api/v1/session/logout"
ME = "/api/v1/me"
SESSION_MFA = "/api/v1/session/mfa"
TENANT = "/api/v1/session/tenant"
ENROLL = "/api/v1/me/mfa/enroll"
CONFIRM = "/api/v1/me/mfa/confirm"
USERS = "/api/v1/users"
SECOND_PROVIDER = "mock-oidc-b"
PROBLEM_BASE = "https://erev.dev/problems/"
MAYA = "maya@acme.test"
OMAR = "omar@acme.test"
INES = "ines@contoso.test"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return oidc_app(app_settings, clock)


@pytest.fixture
def services(keyring: KeyRing, clock: FrozenClock, tmp_path: Path) -> CliServices:
    """The operator's command line: provider creation and invitations."""
    return operator_services(keyring, clock, tmp_path)


@pytest.fixture
def provider_id(
    request: pytest.FixtureRequest,
    committed_db: TestDatabase,
    app_settings: Settings,
    services: CliServices,
) -> Iterator[UUID]:
    """Provider ``mock-oidc`` bound to ``acme.test``, or to the domains a test names through an
    indirect parameter."""
    domains: tuple[str, ...] = getattr(request, "param", EMAIL_DOMAINS)
    yield create_mock_oidc(services, issuer_for(app_settings), email_domains=domains)
    remove_provider()


def invited(services: CliServices, email: str) -> None:
    """The operator invites the identity for the provider (``erev idp invite``)."""
    result = invite(services, email)
    assert result.exit_code == 0, result.output


def link_of(user_id: UUID) -> tuple[UUID | None, str | None]:
    """(provider, provider subject) of the identity."""
    with identity_session(request_id="tests-oidc-link") as db:
        row = db.execute(
            select(app_user.c.identity_provider_id, app_user.c.identity_provider_subject).where(
                app_user.c.id == user_id
            )
        ).one()
    return row.identity_provider_id, row.identity_provider_subject


def sessions_of(user_id: UUID) -> int:
    with identity_session(request_id="tests-oidc-sessions") as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(user_session)
                .where(user_session.c.user_id == user_id)
            ).scalar_one()
        )


@dataclass(frozen=True, slots=True)
class Started:
    authorize_path: str
    params: dict[str, str]
    flow_cookie: str


def set_cookies(response: HttpResponse) -> dict[str, str]:
    pairs = [
        header.split(";", 1)[0].split("=", 1) for header in response.headers.get_list("set-cookie")
    ]
    return {name: value for name, value in pairs}


def start(app: FastAPI, code: str = PROVIDER_CODE) -> Started:
    response = call(app, "GET", f"/api/v1/session/oidc/{code}/start")
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    return Started(
        authorize_path=location.path,
        params=dict(parse_qsl(location.query)),
        flow_cookie=set_cookies(response)["erev_oidc"],
    )


def authorize(
    app: FastAPI, started: Started, email: str, **overrides: str
) -> tuple[str, dict[str, str]]:
    """The mock IdP signs ``email`` in and redirects to the callback."""
    params = {**started.params, "login_hint": email, **overrides}
    response = call(app, "GET", started.authorize_path, params=params)
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    return location.path, dict(parse_qsl(location.query))


def callback(
    app: FastAPI, started: Started, path: str, query: dict[str, str], **overrides: str
) -> HttpResponse:
    headers = {"Cookie": f"erev_oidc={started.flow_cookie}"}
    return call(app, "GET", path, params={**query, **overrides}, headers=headers)


def sign_in_with_idp(app: FastAPI, email: str, code: str = PROVIDER_CODE) -> HttpResponse:
    started = start(app, code)
    path, query = authorize(app, started, email)
    return callback(app, started, path, query)


def assert_unauthenticated(response: HttpResponse) -> None:
    assert response.status_code == 401, response.text
    assert response.json()["type"] == PROBLEM_BASE + "unauthenticated"


def user_id_of(email: str) -> UUID | None:
    with identity_session(request_id="tests-oidc-user") as db:
        found = db.execute(
            select(app_user.c.id).where(app_user.c.email == email)
        ).scalar_one_or_none()
    return found


def account(keyring: KeyRing, clock: FrozenClock, email: str) -> UUID:
    """The provisioned workspace admin with ``email``; an earlier test's account is reused."""
    if user_id_of(email) is None:
        tenant_factory(keyring=keyring, clock=clock, admin_email=email)
    found = user_id_of(email)
    assert found is not None
    return found


def role_rows(user_id: UUID) -> list[tuple[Any, ...]]:
    with identity_session(request_id="tests-oidc-roles", user_id=user_id) as db:
        memberships = db.execute(
            select(tenant_membership.c.tenant_id, tenant_membership.c.id).where(
                tenant_membership.c.user_id == user_id
            )
        ).all()
    rows: list[tuple[Any, ...]] = []
    for tenant_id, membership_id in memberships:
        with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
            rows += [
                tuple(row)
                for row in db.execute(
                    select(role_assignment)
                    .where(role_assignment.c.membership_id == membership_id)
                    .order_by(role_assignment.c.id)
                )
            ]
    return rows


def chain_mark() -> int:
    with identity_session(request_id="tests-oidc-mark") as db:
        return int(
            db.execute(select(func.coalesce(func.max(security_event.c.chain_seq), 0))).scalar_one()
        )


def events_since(mark: int) -> list[tuple[str, UUID | None, dict[str, Any]]]:
    with identity_session(request_id="tests-oidc-events") as db:
        rows = db.execute(
            select(security_event.c.kind, security_event.c.user_id, security_event.c.detail)
            .where(security_event.c.chain_seq > mark)
            .order_by(security_event.c.chain_seq)
        ).all()
    return [(row.kind, row.user_id, row.detail) for row in rows]


def test_links_existing_user_by_verified_email(
    app: FastAPI,
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """The first sign-in of an identity the operator invited for the provider links it, under the
    provider's subject (REQ-PLT-006 rev 1.23: the verified email finds the identity, the
    invitation admits it — email alone links nobody, see the test of that name below)."""
    maya = account(keyring, clock, MAYA)
    roles_before = role_rows(maya)
    assert roles_before != []
    invited(services, MAYA)
    mark = chain_mark()

    started = start(app)
    assert started.authorize_path == "/api/v1/__mocks__/oidc/authorize"
    assert {
        name: started.params[name]
        for name in ("response_type", "client_id", "redirect_uri", "code_challenge_method")
    } == {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": f"{app_settings.public_origin}/api/v1/session/oidc/mock-oidc/callback",
        "code_challenge_method": "S256",
    }
    assert all(len(started.params[name]) >= 43 for name in ("state", "nonce", "code_challenge"))
    path, query = authorize(app, started, MAYA)
    signed_in = callback(app, started, path, query)
    assert signed_in.status_code == 302, signed_in.text
    assert signed_in.headers["location"] == f"{app_settings.public_origin}/sign-in"
    cookies = set_cookies(signed_in)
    assert cookies["erev_oidc"] == ""
    token = cookies["erev_session"]

    with identity_session(request_id="tests-oidc-session") as db:
        opened = db.execute(
            select(user_session.c.user_id, user_session.c.auth_method).where(
                user_session.c.token_sha256 == sha256_hex(token)
            )
        ).one()
        linked = db.execute(
            select(app_user.c.identity_provider_id).where(app_user.c.id == maya)
        ).scalar_one()
    assert (opened.user_id, opened.auth_method) == (maya, "oidc")
    assert linked == provider_id
    assert link_of(maya) == (provider_id, "mock-maya")
    session = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"})
    assert (session.json()["authenticated"], session.json()["user"]["email"]) == (True, MAYA)

    # A second sign-in reuses the link.
    assert sign_in_with_idp(app, MAYA).status_code == 302
    provider = {"auth_method": "oidc", "provider": PROVIDER_CODE}
    assert events_since(mark) == [
        ("OIDC_LINKED", maya, {"provider": PROVIDER_CODE}),
        ("LOGIN_SUCCEEDED", maya, provider),
        ("LOGIN_SUCCEEDED", maya, provider),
    ]
    assert role_rows(maya) == roles_before


def test_sar_15_callback_refuses_private_endpoints(
    provider_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-A-04 (D-80): the review probe saw the token form posted to 10.0.0.5."""
    requested: list[str] = []
    probe = oidc_app(app_settings, clock, requested=requested)
    discovery = OidcMock.discovery

    def private_endpoints(self: OidcMock) -> dict[str, Any]:
        return {
            **discovery(self),
            "token_endpoint": "http://10.0.0.5/internal-admin",
            "jwks_uri": "http://169.254.169.254/latest/meta-data/",
        }

    monkeypatch.setattr(OidcMock, "discovery", private_endpoints)
    account(keyring, clock, MAYA)
    mark = chain_mark()

    started = start(probe)
    path, query = authorize(probe, started, MAYA)
    assert_unauthenticated(callback(probe, started, path, query))
    assert events_since(mark) == [
        (
            "LOGIN_FAILED",
            None,
            {"auth_method": "oidc", "provider": PROVIDER_CODE, "reason": "provider_request_failed"},
        )
    ]
    # Only the two discovery requests, of start and of the callback, reached the transport.
    assert [urlsplit(url).path for url in requested] == [
        "/api/v1/__mocks__/oidc/.well-known/openid-configuration"
    ] * 2
    assert all(urlsplit(url).hostname == "127.0.0.1" for url in requested)


@pytest.mark.parametrize("provider_id", [("acme.test", "contoso.test")], indirect=True)
def test_unknown_or_unverified_email_refused(
    app: FastAPI, provider_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Ines has no account and Omar's email is not verified. The provider is bound to both
    organisations' domains here, so that Ines is refused as an unknown user and not for her
    domain (REQ-PLT-006 rev 1.23)."""
    omar = account(keyring, clock, OMAR)
    with identity_session(request_id="tests-oidc-count") as db:
        users_before = db.execute(select(func.count()).select_from(app_user)).scalar_one()
    mark = chain_mark()

    assert_unauthenticated(sign_in_with_idp(app, INES))
    assert_unauthenticated(sign_in_with_idp(app, OMAR))

    assert user_id_of(INES) is None
    with identity_session(request_id="tests-oidc-refused") as db:
        assert db.execute(select(func.count()).select_from(app_user)).scalar_one() == users_before
        assert (
            db.execute(
                select(app_user.c.identity_provider_id).where(app_user.c.id == omar)
            ).scalar_one()
            is None
        )
        sessions = db.execute(
            select(func.count()).select_from(user_session).where(user_session.c.user_id == omar)
        ).scalar_one()
    assert sessions == 0
    failures = [
        (kind, user_id, detail.get("reason")) for kind, user_id, detail in events_since(mark)
    ]
    assert failures == [
        ("LOGIN_FAILED", None, "unknown_user"),
        ("LOGIN_FAILED", None, "email_not_verified"),
    ]


def test_state_or_nonce_mismatch_refused(
    app: FastAPI, provider_id: UUID, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = account(keyring, clock, MAYA)
    mark = chain_mark()

    started = start(app)
    path, query = authorize(app, started, MAYA)
    assert_unauthenticated(callback(app, started, path, query, state="changed-" + query["state"]))

    started = start(app)
    path, query = authorize(app, started, MAYA, nonce="another-nonce")
    assert_unauthenticated(callback(app, started, path, query))

    # Without the flow cookie the state cannot be checked.
    started = start(app)
    path, query = authorize(app, started, MAYA)
    assert_unauthenticated(call(app, "GET", path, params=query))

    reasons = [(kind, user_id, detail["reason"]) for kind, user_id, detail in events_since(mark)]
    assert reasons == [
        ("LOGIN_FAILED", None, "state_mismatch"),
        ("LOGIN_FAILED", None, "id_token_invalid"),
        ("LOGIN_FAILED", None, "state_mismatch"),
    ]
    with identity_session(request_id="tests-oidc-unlinked") as db:
        linked = db.execute(
            select(app_user.c.identity_provider_id).where(app_user.c.id == maya)
        ).scalar_one()
    assert linked is None


def test_get_session_lists_enabled_providers(app: FastAPI, provider_id: UUID) -> None:
    response = call(app, "GET", SESSION)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "authenticated": False,
        "capabilities": {"identity_providers": [{"code": "mock-oidc", "name": "Mock OIDC"}]},
    }
    unknown = call(app, "GET", "/api/v1/session/oidc/unknown-idp/start")
    assert unknown.status_code == 404, unknown.text


def asserting(app: FastAPI, *users: MockUser) -> None:
    """The mock IdP signs in these users and no other: what its administrator set it to say."""
    mock = app.state.mocks.adapters[MOCK_CODE]
    assert isinstance(mock, OidcMock)
    mock._users = users  # noqa: SLF001 - the test stands in for the provider's administrator


def failures_since(mark: int) -> list[tuple[UUID | None, str]]:
    """(user, reason) of each ``LOGIN_FAILED`` since the mark."""
    return [
        (user_id, str(detail["reason"]))
        for kind, user_id, detail in events_since(mark)
        if kind == "LOGIN_FAILED"
    ]


def test_ops_idp_domains_1_a_change_of_domains_holds_from_the_next_sign_in(
    app: FastAPI, provider_id: UUID, services: CliServices, keyring: KeyRing, clock: FrozenClock
) -> None:
    """OPS-IDP-DOMAINS-1 (04 T-PLT-03 rev 1.217; REQ-PLT-006 rev 1.132): the callback reads
    the provider's domains at every sign-in, so ``erev idp domains`` holds from the next one. A
    domain that is added lets an identity of it be invited and signed in; a domain that is taken
    away refuses the same identity before any identity is read - it stays invited and linked,
    and no session is made."""
    ines = account(keyring, clock, INES)  # contoso.test: the provider is bound to acme.test
    had = sessions_of(ines)
    assert invite(services, INES).exit_code == 1  # her domain is not the provider's
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, INES))
    assert failures_since(mark) == [(None, "email_domain_not_bound")]

    assert change_domains(services, add=("contoso.test",)).exit_code == 0
    invited(services, INES)
    assert sign_in_with_idp(app, INES).status_code == 302
    linked_provider, subject = link_of(ines)
    assert linked_provider == provider_id and subject
    assert sessions_of(ines) == had + 1

    taken = change_domains(services, remove=("contoso.test",))
    assert taken.exit_code == 0, taken.output
    assert json.loads(taken.stdout.splitlines()[-1])["identities_outside"] == 1
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, INES))
    assert failures_since(mark) == [(None, "email_domain_not_bound")]
    assert link_of(ines) == (provider_id, subject)
    assert sessions_of(ines) == had + 1


def test_req_plt_006_a_provider_signs_in_only_its_domains_and_the_identities_invited_for_it(
    app: FastAPI, provider_id: UUID, services: CliServices, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review P3-13 (ruling R-48 (d)). The first login linked ANY existing user by the
    verified email the provider asserted: whoever controlled a registered provider signed in as
    a user of another organisation, or as a password user who had never used the provider. A
    provider now vouches only for the domains it was bound to, and only for identities the
    operator invited for it, each under one subject."""
    maya = account(keyring, clock, MAYA)
    ines = account(keyring, clock, INES)  # another organisation's admin, a password user
    assert link_of(maya) == (None, None) and link_of(ines) == (None, None)
    # The accounts are the module's: sessions of its earlier tests stay, so each count is a gain.
    had = {user: sessions_of(user) for user in (maya, ines)}

    # 1. An email of a domain the provider is not bound to: refused before any identity is read.
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, INES))
    # 2. An identity of the provider's own domain that was never linked to or invited for it.
    assert_unauthenticated(sign_in_with_idp(app, MAYA))
    assert failures_since(mark) == [
        (None, "email_domain_not_bound"),
        (maya, "not_invited_for_provider"),
    ]
    with identity_session(request_id="tests-oidc-domain") as db:
        refused_email = db.execute(
            select(security_event.c.email_sha256)
            .where(security_event.c.chain_seq > mark)
            .order_by(security_event.c.chain_seq)
            .limit(1)
        ).scalar_one()
    assert refused_email == sha256_hex(INES)
    assert link_of(maya) == (None, None) and link_of(ines) == (None, None)
    assert (sessions_of(maya), sessions_of(ines)) == (had[maya], had[ines])

    # Positive control: invited for the provider, Maya signs in and is linked to her subject.
    invited(services, MAYA)
    assert sign_in_with_idp(app, MAYA).status_code == 302
    assert link_of(maya) == (provider_id, "mock-maya")
    assert sessions_of(maya) == had[maya] + 1

    # 3. The provider now names another subject under Maya's email (an account re-created at
    #    the provider): the identity stays bound to the subject it was linked with.
    [maya_user] = [
        user
        for user in app.state.mocks.adapters[MOCK_CODE]._users
        if user.email == MAYA  # noqa: SLF001
    ]
    mark = chain_mark()
    asserting(app, replace(maya_user, sub="mock-maya-recreated"))
    assert_unauthenticated(sign_in_with_idp(app, MAYA))
    # 4. ... and no second identity takes a subject that is linked: Omar, invited and verified,
    #    presented under Maya's subject.
    omar = account(keyring, clock, OMAR)
    had[omar] = sessions_of(omar)
    invited(services, OMAR)
    asserting(app, MockUser(sub="mock-maya", email=OMAR, email_verified=True, name="Omar Haddad"))
    assert_unauthenticated(sign_in_with_idp(app, OMAR))
    assert failures_since(mark) == [
        (maya, "subject_mismatch"),
        (omar, "subject_linked_to_another_identity"),
    ]
    assert link_of(maya) == (provider_id, "mock-maya")
    assert link_of(omar) == (provider_id, None)
    assert (sessions_of(maya), sessions_of(omar)) == (had[maya] + 1, had[omar])

    # Positive control: under her own subject Maya still signs in.
    asserting(app, maya_user)
    assert sign_in_with_idp(app, MAYA).status_code == 302
    assert sessions_of(maya) == had[maya] + 2


# --- the review's untested branches (supervisor ruling R-111 (9)) ---------------------------------


@dataclass(frozen=True, slots=True)
class Identity:
    """A fresh identity of the provider's domain: the admin of a workspace of its own."""

    email: str
    user_id: UUID
    tenant_id: UUID
    sub: str

    @property
    def mock(self) -> MockUser:
        return MockUser(sub=self.sub, email=self.email, email_verified=True, name="Zoe Marten")


def identity(keyring: KeyRing, clock: FrozenClock, *, active: bool = False) -> Identity:
    """A new workspace admin ``zoe-…@acme.test``; ``active`` accepts the membership, so that the
    identity holds the administrator's ``requires_mfa`` permissions (the accounts ``account``
    gives are invited only and shared by the module's tests)."""
    name = f"zoe-{secrets.token_hex(4)}"
    email = f"{name}@acme.test"
    result = tenant_factory(keyring=keyring, clock=clock, admin_email=email)
    tenant_id = tenant_id_of(result)
    if active:
        with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
            db.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == result.admin_membership_id)
                .values(
                    status="ACTIVE",
                    invitation_token_sha256=None,
                    invitation_expires_at=None,
                    activated_at=clock.now(),
                    updated_by_kind="SYSTEM",
                )
            )
    found = user_id_of(email)
    assert found is not None
    return Identity(email=email, user_id=found, tenant_id=tenant_id, sub=f"mock-{name}")


def as_owner(user_id: UUID, **values: Any) -> None:
    """Write ``app_user`` columns no command of 1.0 writes this way: a row state, set as the
    owner."""
    with owner_engine().begin() as connection:
        connection.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(updated_by_kind="SYSTEM", **values)
        )


def session_of(app: FastAPI, response: HttpResponse) -> tuple[dict[str, str], dict[str, Any]]:
    """The session cookie a sign-in set, and what ``GET /session`` says of it."""
    assert response.status_code == 302, response.text
    cookie = {"Cookie": f"erev_session={set_cookies(response)['erev_session']}"}
    return cookie, call(app, "GET", SESSION, headers=cookie).json()


def commanding(cookie: dict[str, str], state: dict[str, Any]) -> dict[str, str]:
    return {
        **cookie,
        "X-CSRF-Token": str(state["csrf_token"]),
        "Idempotency-Key": f"k-{secrets.token_hex(8)}",
    }


def pending_denied(user_id: UUID) -> list[dict[str, Any]]:
    with identity_session(request_id="tests-oidc-pending") as db:
        rows = db.execute(
            select(security_event.c.detail)
            .where(
                security_event.c.user_id == user_id,
                security_event.c.kind == "MFA_PENDING_DENIED",
            )
            .order_by(security_event.c.chain_seq)
        ).scalars()
        return [dict(detail) for detail in rows]


def test_r_111_9_an_oidc_session_owes_the_second_factor(
    app: FastAPI, provider_id: UUID, services: CliServices, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The review's untested branches of rule 1 (ruling R-111 (9); REQ-PLT-005; 05 SAR-26). A
    provider's assertion is not a second factor: the session of an OIDC sign-in starts
    unverified. For an administrator it owes enrolment — refused on every route, the refusal on
    record (no workspace is open after an OIDC sign-in, so as a security event) — and, once a
    factor is confirmed, every later OIDC sign-in owes the challenge."""
    zoe = identity(keyring, clock, active=True)
    asserting(app, zoe.mock)
    invited(services, zoe.email)

    cookie, state = session_of(app, sign_in_with_idp(app, zoe.email))
    assert (state["authenticated"], state["active_tenant"]) == (True, None)
    assert (state["mfa_required"], state["mfa_enrolment_required"]) == (False, True)
    refused = call(
        app,
        "POST",
        TENANT,
        json={"tenant_id": str(zoe.tenant_id)},
        headers=commanding(cookie, state),
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["type"] == PROBLEM_BASE + "mfa-required"
    assert pending_denied(zoe.user_id) == [{"method": "POST", "path": TENANT, "step": "enrolment"}]

    started = call(app, "POST", ENROLL, headers=commanding(cookie, state))
    assert started.status_code == 200, started.text
    secret = str(started.json()["secret_base32"])
    confirmed = call(
        app,
        "POST",
        CONFIRM,
        json={"code": totp.code_at(secret, totp.time_step(clock.now()))},
        headers=commanding(cookie, state),
    )
    assert confirmed.status_code == 200, confirmed.text

    # A later sign-in through the provider: the factor is confirmed, the challenge is owed.
    clock.advance(timedelta(seconds=60))
    cookie, state = session_of(app, sign_in_with_idp(app, zoe.email))
    assert (state["mfa_required"], state["mfa_enrolment_required"]) == (True, False)
    again = call(
        app,
        "POST",
        TENANT,
        json={"tenant_id": str(zoe.tenant_id)},
        headers=commanding(cookie, state),
    )
    assert again.status_code == 403, again.text
    assert pending_denied(zoe.user_id)[-1] == {
        "method": "POST",
        "path": TENANT,
        "step": "challenge",
    }
    passed = call(
        app,
        "POST",
        SESSION_MFA,
        json={"code": totp.code_at(secret, totp.time_step(clock.now()))},
        headers=commanding(cookie, state),
    )
    assert passed.status_code == 200, passed.text
    verified = {"Cookie": f"erev_session={set_cookies(passed)['erev_session']}"}
    state = call(app, "GET", SESSION, headers=verified).json()
    opened = call(
        app,
        "POST",
        TENANT,
        json={"tenant_id": str(zoe.tenant_id)},
        headers=commanding(verified, state),
    )
    assert opened.status_code == 200, opened.text
    at_work = {"Cookie": f"erev_session={set_cookies(opened)['erev_session']}"}
    assert call(app, "GET", USERS, headers=at_work).status_code == 200


def test_r_111_9_an_oidc_sign_in_is_refused_by_the_state_of_the_identity(
    app: FastAPI, provider_id: UUID, services: CliServices, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The review's untested branches of rule 4 (ruling R-111 (9); REQ-PLT-006). The address the
    provider asserts is matched to a bound domain exactly — a sub-domain is another domain — and
    whatever its letter case finds the one identity. An identity that is not ACTIVE is refused
    with its reason, a locked account answers 423, and a provider whose domain list is empty
    vouches for nobody, linked or not."""
    zoe = identity(keyring, clock)
    invited(services, zoe.email)
    local, _, domain = zoe.email.partition("@")

    # A sub-domain of a bound domain.
    elsewhere = replace(zoe.mock, email=f"{local}@mail.{domain}")
    asserting(app, elsewhere)
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, elsewhere.email))
    assert failures_since(mark) == [(None, "email_domain_not_bound")]
    assert link_of(zoe.user_id) == (provider_id, None)

    # An upper-case address in the claim: the same identity, linked under the subject.
    shouted = replace(zoe.mock, email=zoe.email.upper())
    asserting(app, shouted)
    with identity_session(request_id="tests-oidc-count") as db:
        users_before = db.execute(select(func.count()).select_from(app_user)).scalar_one()
    _, state = session_of(app, sign_in_with_idp(app, shouted.email))
    assert state["user"]["email"] == zoe.email
    assert link_of(zoe.user_id) == (provider_id, zoe.sub)
    with identity_session(request_id="tests-oidc-count") as db:
        assert db.execute(select(func.count()).select_from(app_user)).scalar_one() == users_before
    asserting(app, zoe.mock)
    held = sessions_of(zoe.user_id)

    # An identity that is not ACTIVE.
    as_owner(zoe.user_id, status="LOCKED")
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, zoe.email))
    assert failures_since(mark) == [(zoe.user_id, "user_not_active")]
    as_owner(zoe.user_id, status="ACTIVE")

    # A locked account: 423, and no session; when the lock has passed she signs in again.
    as_owner(zoe.user_id, locked_until=clock.now() + timedelta(minutes=15))
    locked = sign_in_with_idp(app, zoe.email)
    assert locked.status_code == 423, locked.text
    assert locked.json()["type"] == PROBLEM_BASE + "account-locked"
    assert sessions_of(zoe.user_id) == held
    clock.advance(timedelta(minutes=16))
    assert sign_in_with_idp(app, zoe.email).status_code == 302
    assert sessions_of(zoe.user_id) == held + 1

    # A provider without a domain (a row of before the binding): it vouches for nobody.
    with owner_engine().begin() as connection:
        connection.execute(
            update(identity_provider)
            .where(identity_provider.c.id == provider_id)
            .values(email_domains=[])
        )
    mark = chain_mark()
    assert_unauthenticated(sign_in_with_idp(app, zoe.email))
    assert failures_since(mark) == [(None, "email_domain_not_bound")]
    assert sessions_of(zoe.user_id) == held + 1


def test_r_111_9_an_oidc_flow_belongs_to_one_provider_and_ten_minutes(
    app: FastAPI,
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """The review's untested branches of rule 4 (ruling R-111 (9); REQ-PLT-006; 05 SAR-27). An
    identity invited for one provider does not sign in through another that is bound to the same
    domain; the flow cookie is sealed for the provider that started the flow and for ten
    minutes."""
    created = invoke(
        services,
        idp_create_args(code=SECOND_PROVIDER, issuer_url=issuer_for(app_settings)),
    )
    assert created.exit_code == 0, created.output
    try:
        zoe = identity(keyring, clock)
        asserting(app, zoe.mock)
        result = invite(services, zoe.email, code=SECOND_PROVIDER)
        assert result.exit_code == 0, result.output
        held = sessions_of(zoe.user_id)

        # Invited for the second provider, presented by the first.
        mark = chain_mark()
        assert_unauthenticated(sign_in_with_idp(app, zoe.email))
        assert failures_since(mark) == [(zoe.user_id, "linked_to_another_provider")]

        # The first provider's flow cookie at the second provider's callback.
        mark = chain_mark()
        started = start(app)
        path, query = authorize(app, started, zoe.email)
        foreign = path.replace(f"/{PROVIDER_CODE}/", f"/{SECOND_PROVIDER}/")
        assert foreign != path
        assert_unauthenticated(callback(app, started, foreign, query))
        # A flow that is older than ten minutes.
        started = start(app, SECOND_PROVIDER)
        path, query = authorize(app, started, zoe.email)
        clock.advance(oidc.FLOW_LIFETIME + timedelta(seconds=1))
        assert_unauthenticated(callback(app, started, path, query))
        assert [
            (detail["provider"], detail["reason"])
            for kind, _, detail in events_since(mark)
            if kind == "LOGIN_FAILED"
        ] == [(SECOND_PROVIDER, "state_mismatch"), (SECOND_PROVIDER, "state_mismatch")]
        assert sessions_of(zoe.user_id) == held

        # Positive control: through her own provider, within the ten minutes, she signs in.
        assert sign_in_with_idp(app, zoe.email, SECOND_PROVIDER).status_code == 302
        assert sessions_of(zoe.user_id) == held + 1
        assert link_of(zoe.user_id)[1] == zoe.sub
    finally:
        remove_provider(SECOND_PROVIDER)


def test_ops_idp_domains_1_a_disabled_provider_signs_nobody_in(
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """OPS-IDP-DOMAINS-1 with the supervisor's ruling of 2026-10-01 (05 SAR-27 rev 1.156; 04
    T-PLT-03 rev 1.217): ``erev idp disable`` takes a provider out of sign-in from the next
    request on. The sign-in page no longer offers it and its start route answers 404, as for an
    unknown code. Its callback refuses - a sign-in that was started before the provider was
    disabled ends with 401 and ``LOGIN_FAILED``, reason ``provider_disabled``, and nothing is
    sent to the provider. Nothing else changes: the identity stays invited and linked, signs in
    with its password, and the session it had opened through the provider stays open.
    ``erev idp enable`` puts the provider back."""
    requested: list[str] = []
    app = oidc_app(app_settings, clock, requested=requested)
    lena = member(keyring, clock)  # an identity with a password, of a domain of her own
    domain = lena.email.rpartition("@")[2]
    assert change_domains(services, add=(domain,)).exit_code == 0
    invited(services, lena.email)
    asserting(app, MockUser(sub="mock-lena", email=lena.email, email_verified=True, name="Lena"))
    listed = {"identity_providers": [{"code": PROVIDER_CODE, "name": "Mock OIDC"}]}

    # Enabled: she signs in through the provider, and a second sign-in is on its way.
    signed_in = sign_in_with_idp(app, lena.email)
    assert signed_in.status_code == 302, signed_in.text
    session = {"Cookie": f"erev_session={set_cookies(signed_in)['erev_session']}"}
    assert link_of(lena.user_id) == (provider_id, "mock-lena")
    in_flight = start(app)
    path, query = authorize(app, in_flight, lena.email)
    assert call(app, "GET", SESSION).json()["capabilities"] == listed

    disabled = disable(services)
    assert disabled.exit_code == 0, disabled.output
    assert json.loads(disabled.stdout.splitlines()[-1]) == {
        "provider": PROVIDER_CODE,
        "is_enabled": False,
        "changed": True,
    }
    mark, sent, had = chain_mark(), len(requested), sessions_of(lena.user_id)

    # Not offered, and not started: the answer of an unknown code.
    assert call(app, "GET", SESSION).json()["capabilities"] == {"identity_providers": []}
    refused_start = call(app, "GET", START)
    assert refused_start.status_code == 404, refused_start.text
    assert refused_start.json()["type"] == PROBLEM_BASE + "not-found"
    # The sign-in that was on its way, and a callback without a flow: refused by name.
    assert_unauthenticated(callback(app, in_flight, path, query))
    assert_unauthenticated(call(app, "GET", path, params=query))
    refusal = (
        "LOGIN_FAILED",
        None,
        {"auth_method": "oidc", "provider": PROVIDER_CODE, "reason": "provider_disabled"},
    )
    assert events_since(mark) == [refusal, refusal]
    assert requested[sent:] == []  # nothing went to the provider: no discovery, no token request
    assert sessions_of(lena.user_id) == had

    # Nothing else changed: her link, her open session and her password.
    assert link_of(lena.user_id) == (provider_id, "mock-lena")
    assert call(app, "GET", SESSION, headers=session).json()["authenticated"] is True
    assert sign_in(app, lena.email).token
    # The operator still prepares the provider while it is disabled: an invitation is taken.
    assert invite(services, lena.email).exit_code == 0

    enabled = enable(services)
    assert enabled.exit_code == 0, enabled.output
    assert json.loads(enabled.stdout.splitlines()[-1]) == {
        "provider": PROVIDER_CODE,
        "is_enabled": True,
        "changed": True,
    }
    assert call(app, "GET", SESSION).json()["capabilities"] == listed
    assert sign_in_with_idp(app, lena.email).status_code == 302


def ends_of(user_id: UUID) -> Counter[tuple[str, str | None]]:
    """(method, end reason) of every session of the identity; None while a session is open."""
    with identity_session(request_id="tests-oidc-ends") as db:
        rows = db.execute(
            select(user_session.c.auth_method, user_session.c.end_reason).where(
                user_session.c.user_id == user_id
            )
        ).all()
    return Counter((str(row.auth_method), row.end_reason) for row in rows)


def ended_first(user_id: UUID, reason: str) -> list[tuple[UUID, Any]]:
    """(id, ended_at) of the identity's sessions that ended with ``reason``."""
    with identity_session(request_id="tests-oidc-ended") as db:
        rows = db.execute(
            select(user_session.c.id, user_session.c.ended_at)
            .where(user_session.c.user_id == user_id, user_session.c.end_reason == reason)
            .order_by(user_session.c.id)
        ).all()
    return [(row.id, row.ended_at) for row in rows]


def lena_at_the_provider(email: str) -> MockUser:
    return MockUser(sub="mock-lena", email=email, email_verified=True, name="Lena")


def lena_of(app: FastAPI, services: CliServices, keyring: KeyRing, clock: FrozenClock) -> Any:
    """An identity with a password, of a domain of her own, invited for the provider and known
    to the mock IdP."""
    lena = member(keyring, clock)
    domain = lena.email.rpartition("@")[2]
    assert change_domains(services, add=(domain,)).exit_code == 0
    invited(services, lena.email)
    asserting(app, lena_at_the_provider(lena.email))
    return lena


def test_ops_idp_sessions_1_a_sign_in_in_flight_reads_the_provider_again(
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """Item OPS-IDP-SESSIONS-1 (05 SAR-27 rev 1.178; 04 T-PLT-03 rev 1.249). The callback read
    its provider once, before it went to the provider; a sign-in that was past that read when
    the operator disabled the provider went on and opened its session, good for twelve hours.
    The provider is read again in the transaction that opens the session: the operator disables
    it here while the callback redeems its code, and the sign-in is refused with
    ``LOGIN_FAILED``, reason ``provider_disabled``, on the identity - no session is opened."""
    app = oidc_app(app_settings, clock)
    lena = lena_of(app, services, keyring, clock)
    assert sign_in_with_idp(app, lena.email).status_code == 302
    had = sessions_of(lena.user_id)
    client = app.state.oidc_http

    class Disabling:
        """The provider's token endpoint answers, and the operator disables the provider."""

        def get_json(self, url: str) -> dict[str, Any]:
            answer: dict[str, Any] = client.get_json(url)
            return answer

        def post_form(self, url: str, form: Any) -> dict[str, Any]:
            answer: dict[str, Any] = client.post_form(url, form)
            # ``erev idp disable``, by its function: the request's own thread runs this.
            oidc.set_enabled(
                code=PROVIDER_CODE,
                enabled=False,
                request_id="tests-oidc-disable",
                keyring=keyring,
            )
            return answer

    app.state.oidc_http = Disabling()
    mark = chain_mark()
    started = start(app)
    path, query = authorize(app, started, lena.email)
    with sent() as statements:
        assert_unauthenticated(callback(app, started, path, query))
    # The second read stands behind the identity's row lock: the callback reads the provider
    # before it goes to it, and again once the sign-in holds the identity (DG-KRN-AUTH-08).
    texts = [statement for statement, _ in statements]
    provider_reads = [n for n, text in enumerate(texts) if "FROM erev.identity_provider" in text]
    identity_locks = [
        n
        for n, text in enumerate(texts)
        if "FROM erev.app_user" in text and "FOR NO KEY UPDATE" in text
    ]
    assert len(provider_reads) == 2 and len(identity_locks) == 1, texts
    assert provider_reads[0] < identity_locks[0] < provider_reads[1]
    assert events_since(mark) == [
        (
            "PLATFORM_SCOPE_USED",
            None,
            {"command": "idp.disable", "provider": PROVIDER_CODE, "changed": True},
        ),
        (
            "LOGIN_FAILED",
            lena.user_id,
            {"auth_method": "oidc", "provider": PROVIDER_CODE, "reason": "provider_disabled"},
        ),
    ]
    assert sessions_of(lena.user_id) == had
    # Enabled again, the same flow signs her in: the refusal was the provider's state alone.
    app.state.oidc_http = client
    assert enable(services).exit_code == 0
    assert sign_in_with_idp(app, lena.email).status_code == 302


def test_ops_idp_sessions_1_the_command_ends_what_was_opened_through_the_provider(
    app: FastAPI,
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """Item OPS-IDP-SESSIONS-1 (05 SAR-27 rev 1.178; 04 T-PLT-08 rev 1.249). Disabling a
    provider ended no session and no command did. ``erev idp end-sessions`` ends the sessions
    that are open and were opened through a disabled provider - the open ``oidc`` rows of the
    identities bound to it - with ``REVOKED`` and one platform security event that counts the
    identities and the sessions. A session one of them opened with a password, a session of
    another provider's identity and a session that had ended before are left as they are; an
    enabled provider is refused, and a second run ends nothing."""
    lena = lena_of(app, services, keyring, clock)
    created = invoke(
        services, idp_create_args(code=SECOND_PROVIDER, issuer_url=issuer_for(app_settings))
    )
    assert created.exit_code == 0, created.output
    try:
        zoe = identity(keyring, clock)
        asserting(app, lena_at_the_provider(lena.email), zoe.mock)
        assert invite(services, zoe.email, code=SECOND_PROVIDER).exit_code == 0

        # Lena: a session through the provider that she signed out of, two that are open and
        # one she opened with her password. Zoe: a session through the other provider.
        left, left_state = session_of(app, sign_in_with_idp(app, lena.email))
        signed_out = call(app, "POST", LOGOUT, headers=commanding(left, left_state))
        assert signed_out.status_code == 204, signed_out.text
        through = [session_of(app, sign_in_with_idp(app, lena.email))[0] for _ in range(2)]
        by_password = {"Cookie": f"erev_session={sign_in(app, lena.email).token}"}
        other = session_of(app, sign_in_with_idp(app, zoe.email, SECOND_PROVIDER))[0]
        before = ends_of(lena.user_id)
        assert before[("oidc", "LOGOUT")] == 1 and before[("oidc", None)] == 2
        assert before[("password", None)] >= 1
        first_end = ended_first(lena.user_id, "LOGOUT")
        zoe_before = ends_of(zoe.user_id)

        # While the provider is in sign-in the command refuses and nothing ends.
        mark = chain_mark()
        refused = end_sessions(services)
        assert refused.exit_code == 1, refused.output
        problem = json.loads(refused.stderr)
        assert problem["type"] == PROBLEM_BASE + "validation-failed"
        assert [(e["field"], e["rule_id"], e["message"]) for e in problem["errors"]] == [
            ("code", "T-PLT-03", oidc.PROVIDER_ENABLED)
        ]
        assert (ends_of(lena.user_id), chain_mark()) == (before, mark)

        assert disable(services).exit_code == 0
        mark = chain_mark()
        ended = end_sessions(services)
        assert ended.exit_code == 0, ended.output
        counted = {"provider": PROVIDER_CODE, "identities": 1, "sessions_ended": 2}
        assert json.loads(ended.stdout.splitlines()[-1]) == counted
        assert events_since(mark) == [
            (
                "PLATFORM_SCOPE_USED",
                None,
                {"command": "idp.end-sessions", **counted},
            )
        ]
        after = ends_of(lena.user_id)
        assert after[("oidc", "REVOKED")] == 2 and after[("oidc", None)] == 0
        assert (
            after[("oidc", "LOGOUT")] == 1
            and after[("password", None)] == before[("password", None)]
        )
        assert ended_first(lena.user_id, "LOGOUT") == first_end  # an ended row keeps its end
        with identity_session(request_id="tests-oidc-revoked") as db:
            revoked = db.execute(
                select(user_session.c.ended_at, user_session.c.expires_at).where(
                    user_session.c.user_id == lena.user_id,
                    user_session.c.end_reason == "REVOKED",
                )
            ).all()
        # Ended at the command's instant, and kept as long as any ended session (T-PLT-08).
        assert [(row.ended_at, row.expires_at - row.ended_at) for row in revoked] == [
            (clock.now(), sessions.RETENTION)
        ] * 2
        assert ends_of(zoe.user_id) == zoe_before
        for cookie in through:
            assert call(app, "GET", SESSION, headers=cookie).json()["authenticated"] is False
            assert_unauthenticated(call(app, "GET", ME, headers=cookie))
        for cookie in (by_password, other):
            assert call(app, "GET", SESSION, headers=cookie).json()["authenticated"] is True

        # A second run finds nothing to end and says so, with its event.
        mark = chain_mark()
        again = end_sessions(services)
        assert again.exit_code == 0, again.output
        nothing = {"provider": PROVIDER_CODE, "identities": 0, "sessions_ended": 0}
        assert json.loads(again.stdout.splitlines()[-1]) == nothing
        assert events_since(mark) == [
            ("PLATFORM_SCOPE_USED", None, {"command": "idp.end-sessions", **nothing})
        ]
    finally:
        remove_provider(SECOND_PROVIDER)


def test_ops_idp_sessions_1_a_sign_in_that_holds_the_identity_is_ended_by_the_command(
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item OPS-IDP-SESSIONS-1 (05 SAR-27 rev 1.178; dev-guide DG-KRN-AUTH-08): the command is
    exact against a sign-in under way. A sign-in has read the provider enabled and holds the
    identity's row; the operator disables the provider and starts the command. The command is
    observed waiting for that row - one of its own backends, blocked by the sign-in's - and
    only then is the sign-in let go: it commits its session, and the command ends it with the
    one that was open before."""
    app = oidc_app(app_settings, clock)
    lena = lena_of(app, services, keyring, clock)
    assert sign_in_with_idp(app, lena.email).status_code == 302  # linked, and one session open
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the identity's lock and the row

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the sign-in was never let go"
        return opened(db, **arguments)

    def signing_in() -> None:
        try:
            seen["signed_in"] = sign_in_with_idp(app, lena.email)
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["signed_in"] = error

    def ending() -> None:
        try:
            seen["ended"] = oidc.end_sessions(
                code=PROVIDER_CODE,
                request_id="tests-oidc-end-sessions",
                keyring=keyring,
                now=clock.now(),
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["ended"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    signer = threading.Thread(target=signing_in, name="sign-in")
    commander = threading.Thread(target=ending, name="end-sessions")
    signer.start()
    try:
        assert holding.wait(timeout=30), seen
        assert disable(services).exit_code == 0
        with (
            identity_session(request_id="tests-oidc-watch") as watch,
            observing_checkouts() as backends,
        ):
            commander.start()
            _, statement = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20, expect="app_user"
            )
            assert "for no key update" in statement.lower()
            assert "ended" not in seen  # the command has not answered: it waits
    finally:
        release.set()
        signer.join(timeout=60)
        if commander.ident is not None:
            commander.join(timeout=60)
    assert not signer.is_alive() and not commander.is_alive()

    signed_in = seen["signed_in"]
    assert not isinstance(signed_in, BaseException), signed_in
    assert signed_in.status_code == 302, signed_in.text  # the sign-in itself completed
    cookie = {"Cookie": f"erev_session={set_cookies(signed_in)['erev_session']}"}
    assert seen["ended"] == {"provider": PROVIDER_CODE, "identities": 1, "sessions_ended": 2}
    assert ends_of(lena.user_id)[("oidc", None)] == 0
    assert call(app, "GET", SESSION, headers=cookie).json()["authenticated"] is False


def test_ops_idp_sessions_1_a_rotation_past_its_authentication_opens_nothing_after_the_command(
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item SESSION-ROTATION-END-1 (05 SAR-09 and SAR-27 rev 1.178; dev-guide DG-KRN-AUTH-08). A
    rotation opened the successor of the session its request had presented without asking
    whether that session was still open: a request that was past its authentication when the
    operator ended the provider's sessions went on and left an open ``oidc`` session behind the
    command. A rotation opens a successor only when it ended the presented session itself: the
    provider is disabled and its sessions are ended here while the request selects a workspace,
    and the request is answered 401 - no session of hers is open afterwards."""
    app = oidc_app(app_settings, clock)
    lena = lena_of(app, services, keyring, clock)
    cookie, state = session_of(app, sign_in_with_idp(app, lena.email))
    assert ends_of(lena.user_id) == Counter({("oidc", None): 1})
    marked = sessions._mark_opened  # noqa: SLF001 - between the authentication and the rotation
    ended: list[dict[str, Any]] = []

    def ending(facts: Any, **arguments: Any) -> None:
        marked(facts, **arguments)
        # ``erev idp disable`` and ``erev idp end-sessions``, by their functions: the request's
        # own thread runs them, after it was authenticated and before it rotates its session.
        oidc.set_enabled(
            code=PROVIDER_CODE, enabled=False, request_id="tests-oidc-disable", keyring=keyring
        )
        ended.append(
            oidc.end_sessions(
                code=PROVIDER_CODE,
                request_id="tests-oidc-end-sessions",
                keyring=keyring,
                now=clock.now(),
            )
        )

    monkeypatch.setattr(sessions, "_mark_opened", ending)
    selected = call(
        app,
        "POST",
        TENANT,
        json={"tenant_id": str(lena.tenant_id)},
        headers=commanding(cookie, state),
    )
    assert ended == [{"provider": PROVIDER_CODE, "identities": 1, "sessions_ended": 1}]
    assert_unauthenticated(selected)
    assert "erev_session" not in set_cookies(selected)
    assert ends_of(lena.user_id) == Counter({("oidc", "REVOKED"): 1})


def test_ops_idp_sessions_1_a_rotation_that_holds_the_identity_is_ended_by_the_command(
    provider_id: UUID,
    services: CliServices,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item SESSION-ROTATION-END-1 (05 SAR-09 and SAR-27 rev 1.178; dev-guide DG-KRN-AUTH-08): the
    command is exact against a rotation under way. A rotation has ended the session it presented
    and has not yet committed its successor; the operator disables the provider and starts the
    command. Without the identity's row the command waited for the ended session's row, passed
    it over as ended and never saw the successor. A rotation holds the identity's row from its
    first statement: the command is observed waiting for that row, and once the rotation has
    committed, the command's statement ends the successor."""
    app = oidc_app(app_settings, clock)
    lena = lena_of(app, services, keyring, clock)
    cookie, state = session_of(app, sign_in_with_idp(app, lena.email))
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the presented session's end and the row

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the rotation was never let go"
        return opened(db, **arguments)

    def rotating() -> None:
        try:
            seen["rotated"] = call(
                app,
                "POST",
                TENANT,
                json={"tenant_id": str(lena.tenant_id)},
                headers=commanding(cookie, state),
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["rotated"] = error

    def ending() -> None:
        try:
            seen["ended"] = oidc.end_sessions(
                code=PROVIDER_CODE,
                request_id="tests-oidc-end-sessions",
                keyring=keyring,
                now=clock.now(),
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["ended"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    rotator = threading.Thread(target=rotating, name="rotation")
    commander = threading.Thread(target=ending, name="end-sessions")
    rotator.start()
    try:
        assert holding.wait(timeout=30), seen
        assert disable(services).exit_code == 0
        with (
            identity_session(request_id="tests-oidc-watch") as watch,
            observing_checkouts() as backends,
        ):
            commander.start()
            _, waited_in = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20, expect="app_user"
            )
            assert "ended" not in seen  # the command has not answered: it waits
    finally:
        release.set()
        rotator.join(timeout=60)
        if commander.ident is not None:
            commander.join(timeout=60)
    assert not rotator.is_alive() and not commander.is_alive()

    rotated = seen["rotated"]
    assert not isinstance(rotated, BaseException), rotated
    assert rotated.status_code == 200, rotated.text  # the rotation itself completed
    successor = {"Cookie": f"erev_session={set_cookies(rotated)['erev_session']}"}
    assert seen["ended"] == {"provider": PROVIDER_CODE, "identities": 1, "sessions_ended": 1}
    # The presented session by the rotation, its successor by the command.
    assert ends_of(lena.user_id) == Counter({("oidc", "REVOKED"): 2})
    assert call(app, "GET", SESSION, headers=successor).json()["authenticated"] is False
    # What the command waited for was the identity's row, not the session's (its UPDATE names
    # both tables).
    assert "for no key update" in waited_in.lower()
