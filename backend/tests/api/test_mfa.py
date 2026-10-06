"""Multi-factor authentication (04 T-PLT-04, T-PLT-05, API-R-01, API-R-03; 05 SAR-07, SAR-09,
SAR-26; 03 REQ-PLT-005; BUILD_SPEC PLF-5, BS1-D-19, BS1-D-30; CTL-033).

The second factor is the user's rule, enforced by the server (security review 2026-09-29 S21 and
lead finding 6; supervisor ruling R-48 (b)): a session that owes enrolment or the challenge
reaches only the session read, sign-out and the routes that settle the step it owes.
"""

from __future__ import annotations

import re
import secrets
import threading
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Annotated, Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from cryptography.exceptions import InvalidTag
from erev_api.api.deps import PUBLIC_PATHS
from erev_api.auth import mfa, sessions, totp
from erev_api.auth.dependencies import SECOND_FACTOR_ACTION, require, require_step_up
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.auth.sessions import AuthenticatedSession
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_event,
    security_event,
    tenant_membership,
    user_mfa_factor,
    user_recovery_code,
)
from erev_api.main import create_app
from fastapi import Depends, FastAPI
from fastapi.routing import iter_route_contexts
from sqlalchemy import select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.operators import create_operator, operator_services
from support.plans import sent
from support.principals import (
    LOGIN,
    PASSWORD,
    Member,
    Signed,
    colleague,
    cookie_headers,
    cookie_of,
    member,
    select_tenant,
    sign_in,
)
from support.rows import insert_approval_delegation, insert_role_assignment

SESSION = "/api/v1/session"
SESSION_MFA = "/api/v1/session/mfa"
ENROLL = "/api/v1/me/mfa/enroll"
CONFIRM = "/api/v1/me/mfa/confirm"
RECOVERY_CODES = "/api/v1/me/recovery-codes"
LOGOUT = "/api/v1/session/logout"
TENANT = "/api/v1/session/tenant"
ME = "/api/v1/me"
PASSWORD_CHANGE = "/api/v1/me/password"
CONTRACTS = "/api/v1/contracts"
AUDIT_EVENTS = "/api/v1/audit-events"
APPROVALS = "/api/v1/approvals"
DELEGATIONS = "/api/v1/approval-delegations"
USERS = "/api/v1/users"
OPERATOR_TENANTS = "/api/v1/operator/tenants"
APPROVE_PROBE = "/api/v1/__probe__/contract-approve"
STEP_UP_PROBE = "/api/v1/__probe__/step-up"
MOCK_PREFIX = "/api/v1/__mocks__/"
# 04 §15.2, API-C-03: what a session that owes a second-factor step is answered (REQ-PLT-005);
# the ERR-27 copy and the audit event's ``detail.step`` say which step.
SECOND_FACTOR_SLUG = "mfa-required"
# DG-KRN-AUTH-03: the routes that answer a session while it owes the named step, besides the
# session read (``GET /session``, an API-C-01 route). Every other cookie route refuses it.
OPEN_WHILE_ENROLMENT_PENDING = frozenset({("POST", LOGOUT), ("POST", ENROLL), ("POST", CONFIRM)})
OPEN_WHILE_CHALLENGE_PENDING = frozenset({("POST", LOGOUT), ("POST", SESSION_MFA)})
PROBLEM_BASE = "https://erev.dev/problems/"
RECOVERY_CODE = re.compile(r"[23456789a-hjkmnp-z]{4}-[23456789a-hjkmnp-z]{4}")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)

    @application.get(APPROVE_PROBE)
    def approve_probe(
        ctx: Annotated[RequestContext, Depends(require("contract.approve"))],
    ) -> dict[str, Any]:
        return {"roles": list(ctx.principal.roles)}

    @application.get(STEP_UP_PROBE)
    def step_up_probe(
        auth: Annotated[AuthenticatedSession, Depends(require_step_up())],
    ) -> dict[str, Any]:
        return {"user_id": str(auth.user.id)}

    return application


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def refresh(app: FastAPI, token: str) -> Signed:
    """The session behind ``token`` with its CSRF token."""
    response = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"})
    body = response.json()
    assert body["authenticated"] is True, body
    return Signed(token=token, csrf_token=body["csrf_token"], body=body)


def post(app: FastAPI, path: str, signed: Signed, json: Mapping[str, Any] | None = None) -> Any:
    return call(
        app, "POST", path, json=json, headers=cookie_headers(signed.token, signed.csrf_token)
    )


def code_for(secret: str, clock: FrozenClock, offset: int = 0) -> str:
    return totp.code_at(secret, totp.time_step(clock.now()) + offset)


def enrol(app: FastAPI, clock: FrozenClock, signed: Signed) -> tuple[Signed, str, list[str]]:
    """Enrol and confirm; returns the rotated verified session, the seed and the recovery codes."""
    started = post(app, ENROLL, signed)
    assert started.status_code == 200, started.text
    secret = str(started.json()["secret_base32"])
    confirmed = post(app, CONFIRM, signed, json={"code": code_for(secret, clock)})
    assert confirmed.status_code == 200, confirmed.text
    return refresh(app, cookie_of(confirmed)), secret, list(confirmed.json()["recovery_codes"])


def assign(someone: Member, role_code: str) -> None:
    context = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
        )


def event_kinds(user_id: UUID) -> list[str]:
    with identity_session(request_id="tests-mfa-events") as db:
        rows = db.execute(
            select(security_event.c.kind)
            .where(security_event.c.user_id == user_id)
            .order_by(security_event.c.chain_seq)
        ).scalars()
        return [str(kind) for kind in rows]


def second_membership(keyring: KeyRing, clock: FrozenClock, email: str, *, activate: bool) -> UUID:
    """Another tenant whose admin is the existing user of ``email`` (SPEC-Q-118)."""
    result = tenant_factory(keyring=keyring, clock=clock, admin_email=email)
    tenant_id = tenant_id_of(result)
    if activate:
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as db:
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
    return tenant_id


def enrol_events(tenant_id: UUID) -> list[tuple[Any, ...]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as db:
        rows = db.execute(
            select(
                audit_event.c.action,
                audit_event.c.object_type,
                audit_event.c.actor_id,
                audit_event.c.mfa_verified,
                audit_event.c.after,
            ).where(audit_event.c.action == mfa.ENROL_ACTION)
        ).all()
    return [tuple(row) for row in rows]


def test_enrolment_returns_ten_codes_once(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    active_second = second_membership(keyring, clock, lena.email, activate=True)
    invited_third = second_membership(keyring, clock, lena.email, activate=False)
    signed = sign_in(app, lena.email)

    started = post(app, ENROLL, signed)
    assert started.status_code == 200, started.text
    body = started.json()
    assert set(body) == {"otpauth_uri", "secret_base32"}
    assert body["otpauth_uri"].startswith("otpauth://totp/eRev:")
    assert parse_qs(urlsplit(body["otpauth_uri"]).query)["secret"] == [body["secret_base32"]]

    confirmed = post(app, CONFIRM, signed, json={"code": code_for(body["secret_base32"], clock)})
    assert confirmed.status_code == 200, confirmed.text
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(RECOVERY_CODE.fullmatch(code) for code in codes)

    # SAR-09: the verified session rotates and the presented one ends.
    rotated = refresh(app, cookie_of(confirmed))
    assert datetime.fromisoformat(rotated.body["mfa_verified_at"]) == clock.now()
    ended = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={signed.token}"})
    assert ended.json()["authenticated"] is False

    again = post(app, CONFIRM, rotated, json={"code": code_for(body["secret_base32"], clock, 1)})
    assert (again.status_code, slug(again)) == (409, "invalid-transition")
    restarted = post(app, ENROLL, rotated)
    assert (restarted.status_code, slug(restarted)) == (409, "invalid-transition")

    with identity_session(request_id="tests-mfa-codes") as db:
        hashes = list(
            db.scalars(
                select(user_recovery_code.c.code_hash).where(
                    user_recovery_code.c.user_id == lena.user_id
                )
            )
        )
    assert len(hashes) == 10
    assert all(str(value).startswith("$argon2id$") for value in hashes)
    assert not any(code in str(value) for value in hashes for code in codes)
    # The refused restart wrote nothing; the enrolment that was started and confirmed did
    # (04 E-79 rev 1.108; ruling R-50 (b)).
    assert event_kinds(lena.user_id) == [
        "LOGIN_SUCCEEDED",
        "MFA_ENROLMENT_STARTED",
        "MFA_ENROLLED",
    ]

    # T-PLT-04 AUD-OPS: one event per ACTIVE membership's tenant; the INVITED one gets none.
    expected = [
        ("mfa_factor.enrol", "user_mfa_factor", lena.user_id, True, {"factor_kind": "TOTP"})
    ]
    assert enrol_events(lena.tenant_id) == expected
    assert enrol_events(active_second) == expected
    assert enrol_events(invited_third) == []


def test_totp_seed_encrypted_at_rest(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)
    secret = str(post(app, ENROLL, signed).json()["secret_base32"])

    def factor_rows() -> list[Mapping[str, Any]]:
        with identity_session(request_id="tests-mfa-seed") as db:
            return list(
                db.execute(
                    select(user_mfa_factor).where(user_mfa_factor.c.user_id == lena.user_id)
                ).mappings()
            )

    (row,) = factor_rows()
    ciphertext = bytes(row["secret_ciphertext"])
    assert ciphertext.startswith(b"erev1")
    assert secret.encode("ascii") not in ciphertext
    assert (row["factor_kind"], row["secret_key_id"], row["confirmed_at"]) == (
        "TOTP",
        "kek:1",
        None,
    )
    context = {"table": "user_mfa_factor", "column": "secret_ciphertext", "row_id": str(row["id"])}
    assert keyring.decrypt(ciphertext, context=context) == secret.encode("ascii")
    with pytest.raises(InvalidTag):
        keyring.decrypt(ciphertext, context={**context, "row_id": str(lena.user_id)})

    # Restarting enrolment before confirmation replaces the pending seed on the same row.
    replaced = str(post(app, ENROLL, signed).json()["secret_base32"])
    (again,) = factor_rows()
    assert replaced != secret
    assert again["id"] == row["id"]
    assert bytes(again["secret_ciphertext"]) != ciphertext


@pytest.mark.control("CTL-033")
def test_ctl_033_mfa_required_permission_blocks_until_verified(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    reviewer = member(keyring, clock)
    assign(reviewer, "revenue_reviewer")

    # D-83: the password step opens her only workspace. The session owes enrolment, and tenant
    # selection is not among the routes that answer it (REQ-PLT-005).
    first = sign_in(app, reviewer.email)
    assert first.body["active_tenant"]["id"] == str(reviewer.tenant_id)
    not_enrolled = call(app, "GET", APPROVE_PROBE, headers=cookie_headers(first.token, key=False))
    assert (not_enrolled.status_code, slug(not_enrolled)) == (403, SECOND_FACTOR_SLUG)
    assert not_enrolled.json()["detail"] == mfa.ENROLMENT_REQUIRED
    _, secret, _ = enrol(app, clock, first)

    # A new sign-in starts without MFA verification.
    second = sign_in(app, reviewer.email)
    assert (second.body["mfa_required"], second.body["mfa_enrolment_required"]) == (True, False)
    assert second.body["active_tenant"]["id"] == str(reviewer.tenant_id)
    unverified = refresh(app, second.token)
    assert unverified.body["mfa_required"] is True
    blocked = call(app, "GET", APPROVE_PROBE, headers=cookie_headers(unverified.token, key=False))
    assert (blocked.status_code, slug(blocked)) == (403, SECOND_FACTOR_SLUG)
    assert blocked.json()["detail"] == mfa.VERIFICATION_REQUIRED

    verified = post(app, SESSION_MFA, unverified, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    assert verified.json()["active_tenant"]["id"] == str(reviewer.tenant_id)
    assert verified.json()["recovery_codes_remaining"] is None
    allowed = call(
        app, "GET", APPROVE_PROBE, headers=cookie_headers(cookie_of(verified), key=False)
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"roles": ["revenue_reviewer"]}
    # The replayed code of the same step is refused.
    replay = post(
        app,
        SESSION_MFA,
        refresh(app, cookie_of(verified)),
        json={"code": code_for(secret, clock, 1)},
    )
    assert (replay.status_code, replay.json()["errors"][0]["field"]) == (422, "code")

    context = DbContext(tenant_id=reviewer.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as db:
        denials = db.execute(
            select(audit_event.c.action, audit_event.c.detail)
            .where(audit_event.c.outcome == "DENIED")
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert [(action, detail["reason"], detail["step"]) for action, detail in denials] == [
        ("contract.approve", "mfa-required", "enrolment"),
        ("contract.approve", "mfa-required", "challenge"),
    ]


def wrong_code(secret: str, clock: FrozenClock) -> str:
    """A six-digit code that no step of the verification window gives."""
    valid = {code_for(secret, clock, offset) for offset in (-1, 0, 1)}
    return next(code for code in (f"{number:06d}" for number in range(10)) if code not in valid)


def locked_until(user_id: UUID) -> datetime | None:
    with identity_session(request_id="tests-mfa-lock") as db:
        value = db.execute(select(app_user.c.locked_until).where(app_user.c.id == user_id))
        return value.scalar_one()  # type: ignore[no-any-return]


def statuses(app: FastAPI, signed: Signed, json: Mapping[str, Any], times: int) -> list[int]:
    return [post(app, SESSION_MFA, signed, json=json).status_code for _ in range(times)]


def test_sar_13_mfa_rate_limit(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))
    others = [colleague(lena.tenant_id, f"user{number}") for number in range(11)]
    seeds = [enrol(app, clock, sign_in(app, someone.email))[1] for someone in others]
    # Password-only sign-ins in an earlier minute: the sign-in and MFA routes share the buckets.
    unverified = sign_in(app, lena.email)
    challenged = [sign_in(app, someone.email) for someone in others]
    clock.advance(timedelta(minutes=1))

    wrong = {"code": wrong_code(secret, clock)}
    assert statuses(app, unverified, wrong, 10) == [422] * 4 + [423] * 6
    limited = post(app, SESSION_MFA, unverified, json=wrong)
    assert (limited.status_code, slug(limited)) == (429, "rate-limited"), limited.text
    assert int(limited.headers["Retry-After"]) >= 1
    kinds = event_kinds(lena.user_id)
    assert (kinds.count("MFA_CHALLENGE_FAILED"), kinds.count("ACCOUNT_LOCKED")) == (5, 1)

    # Fifty attempts of ten users from one address fill the per-address bucket.
    clock.advance(timedelta(minutes=1))
    for signed, seed in zip(challenged[:10], seeds[:10], strict=True):
        assert statuses(app, signed, {"code": wrong_code(seed, clock)}, 5) == [422] * 4 + [423]
    eleventh = post(app, SESSION_MFA, challenged[10], json={"code": wrong_code(seeds[10], clock)})
    assert (eleventh.status_code, slug(eleventh)) == (429, "rate-limited"), eleventh.text
    assert "MFA_CHALLENGE_FAILED" not in event_kinds(others[10].user_id)

    clock.advance(timedelta(minutes=16))
    verified = post(app, SESSION_MFA, unverified, json={"code": code_for(secret, clock)})
    assert verified.status_code == 200, verified.text
    assert datetime.fromisoformat(verified.json()["mfa_verified_at"]) == clock.now()


@pytest.mark.control("CTL-033")
def test_ctl_033_mfa_lockout_after_five_failures(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))
    clock.advance(timedelta(minutes=1))
    wrong = {"code": wrong_code(secret, clock)}

    first = sign_in(app, lena.email)
    assert statuses(app, first, wrong, 4) == [422] * 4
    # A password sign-in does not restart the count (D-80).
    again = sign_in(app, lena.email)
    locked = post(app, SESSION_MFA, again, json=wrong)
    assert (locked.status_code, slug(locked)) == (423, "account-locked"), locked.text
    assert locked_until(lena.user_id) == clock.now() + timedelta(minutes=15)

    correct = post(app, SESSION_MFA, again, json={"code": code_for(secret, clock)})
    assert (correct.status_code, slug(correct)) == (423, "account-locked"), correct.text
    assert refresh(app, again.token).body["mfa_verified_at"] is None

    # A wrong recovery code counts as one challenge.
    carla = colleague(lena.tenant_id, "carla")
    _, carla_secret, carla_codes = enrol(app, clock, sign_in(app, carla.email))
    carla_signed = sign_in(app, carla.email)
    assert statuses(app, carla_signed, {"code": wrong_code(carla_secret, clock)}, 4) == [422] * 4
    unknown = next(
        code for code in iter(mfa.new_recovery_code, None) if code not in set(carla_codes)
    )
    recovery = post(app, SESSION_MFA, carla_signed, json={"recovery_code": unknown})
    assert (recovery.status_code, slug(recovery)) == (423, "account-locked"), recovery.text
    assert locked_until(carla.user_id) == clock.now() + timedelta(minutes=15)

    clock.advance(timedelta(minutes=15))
    verified = post(app, SESSION_MFA, again, json={"code": code_for(secret, clock)})
    assert verified.status_code == 200, verified.text
    following = post(
        app,
        SESSION_MFA,
        refresh(app, cookie_of(verified)),
        json={"code": wrong_code(secret, clock)},
    )
    assert (following.status_code, slug(following)) == (422, "validation-failed"), following.text


def test_login_next_step_flags(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    admin = member(keyring, clock)
    assign(admin, "tenant_admin")
    first = sign_in(app, admin.email)
    assert first.body["mfa_enrolment_required"] is True
    assert first.body["mfa_required"] is False
    enrol(app, clock, first)

    second = sign_in(app, admin.email)
    assert (second.body["mfa_required"], second.body["mfa_enrolment_required"]) == (True, False)

    viewer = member(keyring, clock)
    assign(viewer, "viewer")
    third = sign_in(app, viewer.email)
    assert (third.body["mfa_required"], third.body["mfa_enrolment_required"]) == (False, False)


def denied_events(tenant_id: UUID) -> list[tuple[str, str, str]]:
    """(action, step owed, path) of the workspace's ``DENIED`` audit events, in chain order; each
    is a second-factor refusal (``detail.reason`` is the slug)."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as db:
        rows = db.execute(
            select(audit_event.c.action, audit_event.c.detail)
            .where(audit_event.c.outcome == "DENIED")
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert {str(detail["reason"]) for _, detail in rows} <= {SECOND_FACTOR_SLUG}
    return [(str(action), str(detail["step"]), str(detail["path"])) for action, detail in rows]


@pytest.mark.control("CTL-033")
def test_ctl_033_unenrolled_mandatory_user_reaches_only_enrolment(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review S21: the enrolment gate was the SPA's, and ``GET /session`` did not carry
    the step, so a reload lifted it and the un-enrolled session read and ran every route that
    needs no MFA-gated permission. The step now rides on ``GET /session`` and the server refuses
    the session everywhere but the session read, sign-out and enrolment."""
    admin = member(keyring, clock)
    reviewer = colleague(admin.tenant_id, "rhea")
    assign(reviewer, "revenue_reviewer")  # approval permissions: MFA is mandatory

    signed = sign_in(app, reviewer.email)
    assert (signed.body["mfa_required"], signed.body["mfa_enrolment_required"]) == (False, True)
    reread = refresh(app, signed.token)
    assert (reread.body["mfa_required"], reread.body["mfa_enrolment_required"]) == (False, True)
    assert reread.body["mfa_verified_at"] is None
    assert reread.body["active_tenant"]["id"] == str(reviewer.tenant_id)

    cookie = cookie_headers(signed.token, key=False)
    reads = (CONTRACTS, AUDIT_EVENTS, APPROVALS, ME)
    for path in reads:
        refused = call(app, "GET", path, headers=cookie)
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), path
        assert refused.json()["detail"] == mfa.ENROLMENT_REQUIRED
    commands: dict[str, dict[str, Any] | None] = {
        TENANT: {"tenant_id": str(reviewer.tenant_id)},
        PASSWORD_CHANGE: {"current_password": PASSWORD, "new_password": reviewer.email},
        SESSION_MFA: {"code": "000000"},
        RECOVERY_CODES: None,
    }
    for path, body in commands.items():
        refused = post(app, path, signed, json=body)
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), path
    # No command ran: the session is the one that signed in, and no other security event exists.
    assert refresh(app, signed.token).body["active_tenant"]["id"] == str(reviewer.tenant_id)
    assert event_kinds(reviewer.user_id) == ["LOGIN_SUCCEEDED", "TENANT_SELECTED"]  # the sign-in
    # DG-KRN-AUTH-05: each refusal in the open workspace is a DENIED audit event naming the
    # route's permission, or the second-factor action where the route declares none.
    assert denied_events(reviewer.tenant_id) == [
        ("contract.read", "enrolment", CONTRACTS),
        ("audit.read", "enrolment", AUDIT_EVENTS),
        *[(SECOND_FACTOR_ACTION, "enrolment", path) for path in (APPROVALS, ME, *commands)],
    ]

    # Positive control: enrolment answers this session and settles the step.
    verified, _, _ = enrol(app, clock, signed)
    assert (verified.body["mfa_required"], verified.body["mfa_enrolment_required"]) == (
        False,
        False,
    )
    allowed = call(app, "GET", CONTRACTS, headers=cookie_headers(verified.token, key=False))
    assert allowed.status_code == 200, allowed.text
    assert select_tenant(app, verified, reviewer.tenant_id).status_code == 200


@pytest.mark.control("CTL-033")
def test_ctl_033_password_only_session_of_an_enrolled_user_reaches_only_the_challenge(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review lead finding 6: MFA was enforced per permission, so the password-only
    session of an enrolled Tenant Admin was refused on ``GET /users`` and answered everywhere
    else — reads, the delegation of its approval authority (S3), tenant selection. Such a
    session now reaches nothing but the session read, sign-out and the challenge."""
    ben = member(keyring, clock)
    assign(ben, "tenant_admin")
    _, secret, codes = enrol(app, clock, sign_in(app, ben.email))

    password_only = sign_in(app, ben.email)
    assert (password_only.body["mfa_required"], password_only.body["mfa_enrolment_required"]) == (
        True,
        False,
    )
    reread = refresh(app, password_only.token)
    assert (reread.body["mfa_required"], reread.body["mfa_enrolment_required"]) == (True, False)

    cookie = cookie_headers(password_only.token, key=False)
    for path in (USERS, CONTRACTS, AUDIT_EVENTS, APPROVALS, DELEGATIONS, ME):
        refused = call(app, "GET", path, headers=cookie)
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), path
        assert refused.json()["detail"] == mfa.VERIFICATION_REQUIRED
    now = clock.now()
    commands: dict[str, dict[str, Any] | None] = {
        DELEGATIONS: {
            "delegate_membership_id": str(ben.membership_id),
            "permissions": ["access.approve"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=1)).isoformat(),
            "reason": "Cover while I am away",
        },
        TENANT: {"tenant_id": str(ben.tenant_id)},
        ENROLL: None,
        PASSWORD_CHANGE: {"current_password": PASSWORD, "new_password": ben.email},
    }
    for path, body in commands.items():
        refused = post(app, path, password_only, json=body)
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), path
    assert [step for _, step, _ in denied_events(ben.tenant_id)] == ["challenge"] * 10

    # Positive control: the challenge answers this session, with the TOTP ...
    verified = post(app, SESSION_MFA, password_only, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    assert (verified.json()["mfa_required"], verified.json()["mfa_enrolment_required"]) == (
        False,
        False,
    )
    after = cookie_headers(cookie_of(verified), key=False)
    assert call(app, "GET", USERS, headers=after).status_code == 200
    assert call(app, "GET", CONTRACTS, headers=after).status_code == 200
    # ... or with a recovery code.
    again = sign_in(app, ben.email)
    assert (
        call(app, "GET", CONTRACTS, headers=cookie_headers(again.token, key=False)).status_code
        == 403
    )
    recovered = post(app, SESSION_MFA, again, json={"recovery_code": codes[0]})
    assert recovered.status_code == 200, recovered.text
    assert (
        call(
            app, "GET", CONTRACTS, headers=cookie_headers(cookie_of(recovered), key=False)
        ).status_code
        == 200
    )


def test_req_plt_005_a_confirmed_factor_is_challenged_whatever_the_permissions(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """MFA is optional for a Viewer. One who enrolled is challenged at every sign-in, and the
    challenge is the server's too; one who did not works with the password (positive control)."""
    admin = member(keyring, clock)
    opted_in = colleague(admin.tenant_id, "vera")
    assign(opted_in, "viewer")
    _, secret, _ = enrol(app, clock, sign_in(app, opted_in.email))
    signed = sign_in(app, opted_in.email)
    assert (signed.body["mfa_required"], signed.body["mfa_enrolment_required"]) == (True, False)
    refused = call(app, "GET", CONTRACTS, headers=cookie_headers(signed.token, key=False))
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG)
    verified = post(app, SESSION_MFA, signed, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    allowed = call(app, "GET", CONTRACTS, headers=cookie_headers(cookie_of(verified), key=False))
    assert allowed.status_code == 200, allowed.text

    plain = colleague(admin.tenant_id, "hannah")
    assign(plain, "auditor")
    password_only = sign_in(app, plain.email)
    assert (password_only.body["mfa_required"], password_only.body["mfa_enrolment_required"]) == (
        False,
        False,
    )
    reread = refresh(app, password_only.token)
    assert (reread.body["mfa_required"], reread.body["mfa_enrolment_required"]) == (False, False)
    cookie = cookie_headers(password_only.token, key=False)
    assert call(app, "GET", CONTRACTS, headers=cookie).status_code == 200
    assert call(app, "GET", AUDIT_EVENTS, headers=cookie).status_code == 200
    assert denied_events(admin.tenant_id) == [("contract.read", "challenge", CONTRACTS)]


def test_req_plt_005_mandatory_in_any_active_membership(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The rule is the user's: a Viewer here who is a Tenant Admin of another workspace must
    enrol before working in either (SPEC-Q-144), and a session without a workspace is refused
    without an audit event (there is no tenant log to hold one): the refusal is a security
    event (05 SAR-26 rev 1.128; ruling R-111 (6))."""
    lena = member(keyring, clock)
    assign(lena, "viewer")
    other_tenant = second_membership(keyring, clock, lena.email, activate=True)  # tenant_admin

    signed = sign_in(app, lena.email)
    assert signed.body["active_tenant"] is None  # D-83: several ACTIVE memberships open none
    assert (signed.body["mfa_required"], signed.body["mfa_enrolment_required"]) == (False, True)
    for tenant_id in (lena.tenant_id, other_tenant):
        refused = select_tenant(app, signed, tenant_id)
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG)
    refused = call(app, "GET", ME, headers=cookie_headers(signed.token, key=False))
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG)
    assert denied_events(lena.tenant_id) == []
    assert denied_events(other_tenant) == []
    assert [event["detail"]["path"] for event in pending_denied(lena.user_id)] == [
        TENANT,
        TENANT,
        ME,
    ]

    verified, _, _ = enrol(app, clock, signed)
    selected = select_tenant(app, verified, lena.tenant_id)
    assert selected.status_code == 200, selected.text
    assert (selected.json()["mfa_required"], selected.json()["mfa_enrolment_required"]) == (
        False,
        False,
    )
    in_tenant = cookie_headers(cookie_of(selected), key=False)
    assert call(app, "GET", CONTRACTS, headers=in_tenant).status_code == 200


def test_r_111_9_a_step_that_becomes_due_inside_a_session(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The review's untested branches of rule 1 (ruling R-111 (9)). The step is computed at each
    request from the grants in force and the factors confirmed, not at sign-in: a role granted
    after sign-in makes an open password-only session owe enrolment, and a factor confirmed in
    another session makes it owe the challenge. Each is refused at its next request."""
    admin = member(keyring, clock)
    vera = colleague(admin.tenant_id, "vera")
    assign(vera, "viewer")
    signed = sign_in(app, vera.email)
    cookie = cookie_headers(signed.token, key=False)
    assert call(app, "GET", CONTRACTS, headers=cookie).status_code == 200

    # A role with a requires_mfa permission, granted while the session is open.
    assign(vera, "controller")
    refused = call(app, "GET", CONTRACTS, headers=cookie)
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    assert refused.json()["detail"] == mfa.ENROLMENT_REQUIRED
    owed = refresh(app, signed.token)
    assert (owed.body["mfa_required"], owed.body["mfa_enrolment_required"]) == (False, True)

    # A factor confirmed in another session: this one owes the challenge from then on.
    hana = colleague(admin.tenant_id, "hana")
    assign(hana, "viewer")
    first = sign_in(app, hana.email)
    second = sign_in(app, hana.email)
    first_cookie = cookie_headers(first.token, key=False)
    assert call(app, "GET", CONTRACTS, headers=first_cookie).status_code == 200
    _, secret, _ = enrol(app, clock, second)  # MFA is optional for a Viewer; Hana opts in
    challenged = call(app, "GET", CONTRACTS, headers=first_cookie)
    assert (challenged.status_code, slug(challenged)) == (403, SECOND_FACTOR_SLUG), challenged.text
    assert challenged.json()["detail"] == mfa.VERIFICATION_REQUIRED
    state = refresh(app, first.token)
    assert (state.body["mfa_required"], state.body["mfa_enrolment_required"]) == (True, False)
    passed = post(app, SESSION_MFA, state, json={"code": code_for(secret, clock, 1)})
    assert passed.status_code == 200, passed.text
    answered = call(app, "GET", CONTRACTS, headers=cookie_headers(cookie_of(passed), key=False))
    assert answered.status_code == 200, answered.text
    assert denied_events(admin.tenant_id) == [
        ("contract.read", "enrolment", CONTRACTS),
        ("contract.read", "challenge", CONTRACTS),
    ]


def test_r_111_2_a_delegate_owes_the_second_factor_like_the_holder(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 2 (HOLE; supervisor ruling
    R-111 (2)); 03 REQ-PLT-005 rev 1.104. The gate read role grants only: a member with no
    approval role and no factor, given a delegation of an approval permission, read requests,
    previews and attachments with a password-only session. A member who holds a delegation of a
    ``requires_mfa`` permission that stands is MFA-mandatory like its holder — for reads too,
    and from the first request after the delegation starts, inside a session opened before it.
    A delegation that does not stand asks nothing (positive controls)."""
    admin = member(keyring, clock)
    assign(admin, "revenue_reviewer")  # the delegator holds contract.approve
    now = clock.now()

    def delegated(
        delegate: Member, start: datetime, end: datetime, *, revoked_at: datetime | None = None
    ) -> None:
        context = DbContext(tenant_id=admin.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            insert_approval_delegation(
                session,
                tenant_id=admin.tenant_id,
                delegator_membership_id=admin.membership_id,
                delegate_membership_id=delegate.membership_id,
                valid_from=start,
                valid_to=end,
                revoked_at=revoked_at,
            )

    dana = colleague(admin.tenant_id, "dana")
    assign(dana, "viewer")  # MFA is optional for a Viewer
    signed = sign_in(app, dana.email)
    assert (signed.body["mfa_required"], signed.body["mfa_enrolment_required"]) == (False, False)
    cookie = cookie_headers(signed.token, key=False)
    assert call(app, "GET", CONTRACTS, headers=cookie).status_code == 200
    assert denied_events(admin.tenant_id) == []

    delegated(dana, now - timedelta(minutes=1), now + timedelta(days=30))
    # The same session, its next request: the step has become due.
    refused = call(app, "GET", CONTRACTS, headers=cookie)
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    assert refused.json()["detail"] == mfa.ENROLMENT_REQUIRED
    inbox = call(app, "GET", APPROVALS, headers=cookie)
    assert (inbox.status_code, slug(inbox)) == (403, SECOND_FACTOR_SLUG), inbox.text
    reread = refresh(app, signed.token)
    assert (reread.body["mfa_required"], reread.body["mfa_enrolment_required"]) == (False, True)
    again = sign_in(app, dana.email)
    assert (again.body["mfa_required"], again.body["mfa_enrolment_required"]) == (False, True)
    assert [(step, path) for _, step, path in denied_events(admin.tenant_id)] == [
        ("enrolment", CONTRACTS),
        ("enrolment", APPROVALS),
    ]
    # Enrolment settles the step, as for a holder.
    verified, _, _ = enrol(app, clock, again)
    allowed = call(app, "GET", CONTRACTS, headers=cookie_headers(verified.token, key=False))
    assert allowed.status_code == 200, allowed.text

    # A delegation that does not stand asks nothing: one that ended, one that has not started
    # and one that was revoked.
    for name, start, end, revoked_at in (
        ("erin", now - timedelta(days=20), now - timedelta(days=1), None),
        ("finn", now + timedelta(days=1), now + timedelta(days=20), None),
        ("gail", now - timedelta(days=5), now + timedelta(days=20), now - timedelta(hours=1)),
    ):
        someone = colleague(admin.tenant_id, name)
        assign(someone, "viewer")
        delegated(someone, start, end, revoked_at=revoked_at)
        plain = sign_in(app, someone.email)
        assert (plain.body["mfa_required"], plain.body["mfa_enrolment_required"]) == (
            False,
            False,
        ), name
        read = call(app, "GET", CONTRACTS, headers=cookie_headers(plain.token, key=False))
        assert read.status_code == 200, (name, read.text)


def test_req_plt_005_sign_out_answers_a_session_that_owes_a_step(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """ "Sign in as someone else" (SCREENS_B §12.1) and "Sign out" on the enrolment screen
    (§12.2): both pending sessions end server-side."""
    admin = member(keyring, clock)
    assign(admin, "tenant_admin")
    owes_enrolment = sign_in(app, admin.email)
    assert post(app, LOGOUT, owes_enrolment).status_code == 204
    ended = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={owes_enrolment.token}"})
    assert ended.json()["authenticated"] is False

    enrol(app, clock, sign_in(app, admin.email))
    owes_challenge = sign_in(app, admin.email)
    assert owes_challenge.body["mfa_required"] is True
    assert post(app, LOGOUT, owes_challenge).status_code == 204
    ended = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={owes_challenge.token}"})
    assert ended.json()["authenticated"] is False


def test_req_plt_005_an_operator_sign_in_states_the_step_it_owes(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """Ruling R-48 (b), "operators likewise". A new operator's sign-in answer named neither step
    while its first operator call answered 403 ``mfa-required``: the client could not know what
    to show. The answer and ``GET /session`` now state the step an operator owes — enrolment,
    then the challenge on every later sign-in — and the session reaches only what settles it."""
    services = operator_services(keyring, clock, app_settings.file_root)
    operator = create_operator(services)
    code = f"t-{secrets.token_hex(6)}"
    body = {
        "code": code,
        "display_name": "Harbour Test",
        "reporting_currency": "USD",
        "is_demo": False,
        "admin_email": f"tomas@{code}.test",
    }

    fresh = sign_in(app, operator["email"])
    assert (fresh.body["mfa_required"], fresh.body["mfa_enrolment_required"]) == (False, True)
    reread = refresh(app, fresh.token)
    assert (reread.body["mfa_required"], reread.body["mfa_enrolment_required"]) == (False, True)
    refused = post(app, OPERATOR_TENANTS, fresh, json=body)
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    assert refused.json()["detail"] == mfa.ENROLMENT_REQUIRED
    me = call(app, "GET", ME, headers=cookie_headers(fresh.token, key=False))
    assert (me.status_code, slug(me)) == (403, SECOND_FACTOR_SLUG), me.text

    verified, secret, _ = enrol(app, clock, fresh)
    assert (verified.body["mfa_required"], verified.body["mfa_enrolment_required"]) == (
        False,
        False,
    )

    # Every later sign-in owes the challenge, and says so.
    clock.advance(timedelta(seconds=60))
    later = sign_in(app, operator["email"])
    assert (later.body["mfa_required"], later.body["mfa_enrolment_required"]) == (True, False)
    assert refresh(app, later.token).body["mfa_required"] is True
    refused = post(app, OPERATOR_TENANTS, later, json=body)
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    assert refused.json()["detail"] == mfa.VERIFICATION_REQUIRED
    # Positive control: the challenge settles the step and the operator command runs.
    challenged = post(app, SESSION_MFA, later, json={"code": code_for(secret, clock)})
    assert challenged.status_code == 200, challenged.text
    passed = refresh(app, cookie_of(challenged))
    assert (passed.body["mfa_required"], passed.body["mfa_enrolment_required"]) == (False, False)
    created = post(app, OPERATOR_TENANTS, passed, json=body)
    assert created.status_code == 201, created.text


def guarded_routes(app: FastAPI) -> list[tuple[str, str]]:
    """(method, path) of every route a session must authenticate for: the application's routes
    other than the API-C-01 routes and the mocks."""
    found: list[tuple[str, str]] = []
    for route in iter_route_contexts(app.routes):
        path = route.path or ""
        if path in PUBLIC_PATHS or path.startswith(MOCK_PREFIX) or not path.startswith("/api/"):
            continue
        found.extend((method, path) for method in sorted(route.methods or ()) if method != "HEAD")
    return sorted(found)


def walk(
    app: FastAPI, signed: Signed, *, skip: frozenset[tuple[str, str]]
) -> dict[tuple[str, str], tuple[int, str, str]]:
    """Every guarded route but ``skip`` called with the session of ``signed``, path parameters
    filled with a placeholder id: (status, problem slug, detail) by route. The guard answers
    before the path, query and body are validated, so the placeholder never matters."""
    answers: dict[tuple[str, str], tuple[int, str, str]] = {}
    for method, path in guarded_routes(app):
        if (method, path) in skip:
            continue
        url = re.sub(r"\{[^}]+\}", str(UUID(int=0)), path)
        response = call(app, method, url, headers=cookie_headers(signed.token, signed.csrf_token))
        refused = response.status_code >= 400
        answers[(method, path)] = (
            response.status_code,
            slug(response) if refused else "",
            str(response.json().get("detail")) if refused else "",
        )
    return answers


@pytest.mark.control("CTL-033")
def test_ctl_033_every_route_refuses_a_session_that_owes_its_second_factor(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The family sweep of S21 and lead finding 6: not a route of the application answers a
    session that owes enrolment or the challenge, besides the documented ones
    (DG-KRN-AUTH-03). A route added later is walked too."""
    admin = member(keyring, clock)
    unenrolled = colleague(admin.tenant_id, "rhea")
    assign(unenrolled, "controller")
    enrolled_admin = colleague(admin.tenant_id, "ben")
    assign(enrolled_admin, "tenant_admin")
    enrol(app, clock, sign_in(app, enrolled_admin.email))
    routes = guarded_routes(app)
    assert len(routes) > 350 and ("GET", CONTRACTS) in routes and ("POST", TENANT) in routes
    assert OPEN_WHILE_ENROLMENT_PENDING | OPEN_WHILE_CHALLENGE_PENDING <= set(routes)

    owes_enrolment = sign_in(app, unenrolled.email)
    answers = walk(app, owes_enrolment, skip=OPEN_WHILE_ENROLMENT_PENDING)
    refusal = (403, SECOND_FACTOR_SLUG, mfa.ENROLMENT_REQUIRED)
    assert {route: answer for route, answer in answers.items() if answer != refusal} == {}
    assert len(answers) == len(routes) - len(OPEN_WHILE_ENROLMENT_PENDING)

    owes_challenge = sign_in(app, enrolled_admin.email)
    answers = walk(app, owes_challenge, skip=OPEN_WHILE_CHALLENGE_PENDING)
    refusal = (403, SECOND_FACTOR_SLUG, mfa.VERIFICATION_REQUIRED)
    assert {route: answer for route, answer in answers.items() if answer != refusal} == {}
    assert len(answers) == len(routes) - len(OPEN_WHILE_CHALLENGE_PENDING)


def test_d83_mfa_sign_in_keeps_the_opened_workspace(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))

    # The password step opens her only ACTIVE membership and asks for the challenge.
    signed = sign_in(app, lena.email)
    assert signed.body["mfa_required"] is True
    assert signed.body["active_tenant"]["id"] == str(lena.tenant_id)
    verified = post(app, SESSION_MFA, signed, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["active_tenant"]["id"] == str(lena.tenant_id)
    assert datetime.fromisoformat(body["mfa_verified_at"]) == clock.now()
    assert verified.headers["X-Erev-Tenant-Kind"] == "production"


def test_recovery_code_single_use(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    _, _, codes = enrol(app, clock, sign_in(app, lena.email))

    signed = sign_in(app, lena.email)
    used = post(app, SESSION_MFA, signed, json={"recovery_code": codes[0].upper()})
    assert used.status_code == 200, used.text
    assert used.json()["recovery_codes_remaining"] == 9
    assert datetime.fromisoformat(used.json()["mfa_verified_at"]) == clock.now()
    assert event_kinds(lena.user_id)[-1] == "RECOVERY_CODE_USED"

    retry = sign_in(app, lena.email)
    again = post(app, SESSION_MFA, retry, json={"recovery_code": codes[0]})
    assert (again.status_code, slug(again)) == (422, "validation-failed")
    assert again.json()["errors"][0]["field"] == "recovery_code"
    assert event_kinds(lena.user_id)[-1] == "MFA_CHALLENGE_FAILED"
    assert refresh(app, retry.token).body["mfa_verified_at"] is None

    malformed = post(app, SESSION_MFA, retry, json={"code": "12345"})
    assert (malformed.status_code, malformed.json()["errors"][0]["field"]) == (422, "code")
    neither = post(app, SESSION_MFA, retry, json={})
    assert (neither.status_code, slug(neither)) == (422, "validation-failed")


def test_bs1_d_19_step_up_window(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    # A member without a factor, for whom MFA is optional, never verified: the step-up is absent.
    carla = colleague(lena.tenant_id, "carla")
    plain = sign_in(app, carla.email)
    never = call(app, "GET", STEP_UP_PROBE, headers=cookie_headers(plain.token, key=False))
    assert (never.status_code, slug(never)) == (403, "mfa-step-up-required")
    assert never.json()["detail"] == mfa.STEP_UP_REQUIRED

    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))
    # With a factor, the password-only session owes the challenge before anything else
    # (REQ-PLT-005): it does not reach the step-up check.
    signed = sign_in(app, lena.email)
    pending = call(app, "GET", STEP_UP_PROBE, headers=cookie_headers(signed.token, key=False))
    assert (pending.status_code, slug(pending)) == (403, SECOND_FACTOR_SLUG)
    assert pending.json()["detail"] == mfa.VERIFICATION_REQUIRED

    verified = post(app, SESSION_MFA, signed, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    headers = cookie_headers(cookie_of(verified), key=False)
    clock.advance(timedelta(minutes=4))
    fresh = call(app, "GET", STEP_UP_PROBE, headers=headers)
    assert fresh.status_code == 200, fresh.text
    clock.advance(timedelta(minutes=2))
    stale = call(app, "GET", STEP_UP_PROBE, headers=headers)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required")


def test_sar_09_a_verification_takes_the_factor_then_the_identity_then_the_session(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; dev-guide DG-KRN-AUTH-08): the lock order
    of a verification, read from the statements the request sent. It takes the member's factor
    row, then - for its rotation - the identity's row, then ends the session it was given and
    opens the successor. An MFA reset takes the factor before the identity as well
    (``tests/api/test_users_api.py``), so the two wait for each other at the factor and never in
    a ring."""
    lena = member(keyring, clock)
    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))
    signed = sign_in(app, lena.email)
    with sent() as statements:
        verified = post(app, SESSION_MFA, signed, json={"code": code_for(secret, clock, 1)})
    assert verified.status_code == 200, verified.text
    texts = [statement for statement, _ in statements]

    def first(*parts: str) -> int:
        found = [n for n, text in enumerate(texts) if all(part in text for part in parts)]
        assert found, (parts, texts)
        return found[0]

    factor = first("FROM erev.user_mfa_factor", "FOR UPDATE")
    identity = first("FROM erev.app_user", "FOR NO KEY UPDATE")
    ended = first("UPDATE erev.user_session", "end_reason")
    opened = first("INSERT INTO erev.user_session")
    chain = first("pg_advisory_xact_lock")
    assert factor < identity < ended < opened < chain, texts

    # A code that is refused: the identity's row is held before the event of the refusal asks
    # for the security chain's lock, as a password step holds it.
    owing = sign_in(app, lena.email)
    with sent() as statements:
        refused = post(app, SESSION_MFA, owing, json={"code": wrong_code(secret, clock)})
    assert refused.status_code == 422, refused.text
    texts = [statement for statement, _ in statements]
    factor = first("FROM erev.user_mfa_factor", "FOR UPDATE")
    identity = first("FROM erev.app_user", "FOR NO KEY UPDATE")
    chain = first("pg_advisory_xact_lock")
    assert factor < identity < chain, texts


def test_sar_09_a_password_step_beside_the_same_members_code_step_loses_neither(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item AUTH-LOCK-ORDER-1; dev-guide DG-KRN-AUTH-08).
    Measured in an e2e run of 2026-10-01: two browsers signed one member in at the same moment,
    and one ``POST /session/login`` was answered 409 after 1.3 s beside a ``POST /session/mfa``
    of the same member answered 422 after 1.1 s - a deadlock. The password step held the
    identity's row with its key and then asked for the security chain's lock for its event; the
    code step, refusing a code, held that lock and its event's foreign key waited for the
    identity's row.

    The identity's row is now held without its key, and the code step takes it before it writes
    an event: both take the identity before the chain. Here the password step holds the
    identity's row when the same member's code step, with a code that is not hers, begins: the
    code step is observed waiting for that row, the password step completes, and the code step
    then answers its 422. Neither is lost."""
    lena = member(keyring, clock)
    _, secret, _ = enrol(app, clock, sign_in(app, lena.email))
    owing = sign_in(app, lena.email)  # the other browser, past its password step
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the identity's lock and the event

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the password step was never let go"
        return opened(db, **arguments)

    def signing_in() -> None:
        try:
            seen["signed_in"] = call(
                app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD}
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["signed_in"] = error

    def verifying() -> None:
        try:
            seen["verified"] = post(
                app, SESSION_MFA, owing, json={"code": wrong_code(secret, clock)}
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["verified"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    signer = threading.Thread(target=signing_in, name="password-step")
    verifier = threading.Thread(target=verifying, name="code-step")
    signer.start()
    try:
        assert holding.wait(timeout=30), seen
        with (
            identity_session(request_id="tests-mfa-watch") as watch,
            observing_checkouts() as backends,
        ):
            verifier.start()
            _, waited_in = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20
            )
            assert "verified" not in seen  # the code step has not answered: it waits
    finally:
        release.set()
        signer.join(timeout=60)
        if verifier.ident is not None:
            verifier.join(timeout=60)
    assert not signer.is_alive() and not verifier.is_alive()

    signed_in, verified = seen["signed_in"], seen["verified"]
    assert not isinstance(signed_in, BaseException), signed_in
    assert not isinstance(verified, BaseException), verified
    assert signed_in.status_code == 200, signed_in.text  # the password step is not lost
    assert verified.status_code == 422, verified.text  # and the code step answers for its code
    assert slug(verified) == "validation-failed"
    # What the code step waited for was the identity's row, before it wrote an event - not an
    # event's foreign key behind the chain's lock.
    assert "erev.app_user" in waited_in and "for no key update" in waited_in.lower()
    assert "INSERT INTO erev.security_event" not in waited_in


def security_events(user_id: UUID, kind: str) -> list[dict[str, Any]]:
    """The user's events of one kind, in chain order: request id, session and detail."""
    with identity_session(request_id="tests-mfa-events") as db:
        rows = db.execute(
            select(
                security_event.c.request_id,
                security_event.c.session_id,
                security_event.c.outcome,
                security_event.c.detail,
            )
            .where(security_event.c.user_id == user_id, security_event.c.kind == kind)
            .order_by(security_event.c.chain_seq)
        ).mappings()
        return [dict(row) for row in rows]


def test_r_50_b_issuing_a_seed_and_replacing_the_recovery_batch_are_security_events(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Ruling R-50 (b) on the CTL-038 walk: ``POST /me/mfa/enroll`` created or re-seeded the
    pending factor and returned the seed, and ``POST /me/recovery-codes`` replaced the batch,
    without a security event — the only MFA writes the log did not show. Each writes its E-79
    kind under the request's id, and neither event holds the seed or a code."""
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)

    first = post(app, ENROLL, signed)
    second = post(app, ENROLL, signed)  # before confirmation: a new seed on the pending factor
    assert (first.status_code, second.status_code) == (200, 200), second.text
    started = security_events(lena.user_id, "MFA_ENROLMENT_STARTED")
    assert [(event["outcome"], event["detail"]) for event in started] == [
        ("SUCCESS", {"factor_kind": "TOTP", "reseeded": False}),
        ("SUCCESS", {"factor_kind": "TOTP", "reseeded": True}),
    ]
    assert [event["request_id"] for event in started] == [
        first.headers["X-Request-Id"],
        second.headers["X-Request-Id"],
    ]
    seeds = {first.json()["secret_base32"], second.json()["secret_base32"]}
    assert len(seeds) == 2

    secret = str(second.json()["secret_base32"])
    confirmed = post(app, CONFIRM, signed, json={"code": code_for(secret, clock)})
    assert confirmed.status_code == 200, confirmed.text
    verified = refresh(app, cookie_of(confirmed))
    assert security_events(lena.user_id, "RECOVERY_CODES_REGENERATED") == []  # the first batch

    regenerated = post(app, RECOVERY_CODES, verified)
    assert regenerated.status_code == 200, regenerated.text
    codes = regenerated.json()["recovery_codes"]
    with identity_session(request_id="tests-mfa-batches") as db:
        newest = db.execute(
            select(user_recovery_code.c.batch_id)
            .where(user_recovery_code.c.user_id == lena.user_id)
            .order_by(user_recovery_code.c.created_at.desc())
            .limit(1)
        ).scalar_one()
    [event] = security_events(lena.user_id, "RECOVERY_CODES_REGENERATED")
    assert (event["outcome"], event["detail"]) == (
        "SUCCESS",
        {"batch_id": str(newest), "codes": 10},
    )
    assert event["request_id"] == regenerated.headers["X-Request-Id"]
    # Neither kind carries a secret: no seed and no code in any event of the user.
    with identity_session(request_id="tests-mfa-events") as db:
        details = db.scalars(
            select(security_event.c.detail).where(security_event.c.user_id == lena.user_id)
        ).all()
    written = repr(details)
    assert not any(value in written for value in (*seeds, *codes))

    # A refused command writes neither kind: a confirmed factor is not re-seeded (409), and the
    # batch is not replaced without a fresh step-up (403).
    assert post(app, ENROLL, verified).status_code == 409
    clock.advance(timedelta(minutes=6))
    assert post(app, RECOVERY_CODES, verified).status_code == 403
    assert len(security_events(lena.user_id, "MFA_ENROLMENT_STARTED")) == 2
    assert len(security_events(lena.user_id, "RECOVERY_CODES_REGENERATED")) == 1


def pending_denied(user_id: UUID) -> list[dict[str, Any]]:
    """The user's ``MFA_PENDING_DENIED`` events, in chain order."""
    return security_events(user_id, "MFA_PENDING_DENIED")


def second_factor_kinds(user_id: UUID) -> list[str]:
    """The user's security events of the second factor, in chain order."""
    return [
        kind
        for kind in event_kinds(user_id)
        if kind.startswith("MFA_") or kind == "RECOVERY_CODE_USED"
    ]


def test_r_111_6_a_passed_challenge_is_a_security_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 8 (ruling R-111 (6)); 04 E-79
    rev 1.189; 05 SAR-26 rev 1.128. ``LOGIN_SUCCEEDED`` is written at the password step, before
    the gate, and a passed challenge wrote nothing: the log could not say which sign-ins were
    completed. Each passed challenge writes ``MFA_CHALLENGE_PASSED`` under the request's id — by
    code and by recovery code, at sign-in and as a step-up — and a failed one writes none."""
    lena = member(keyring, clock)
    _, secret, codes = enrol(app, clock, sign_in(app, lena.email))
    # A confirmed enrolment is MFA_ENROLLED, not a challenge.
    assert security_events(lena.user_id, "MFA_CHALLENGE_PASSED") == []

    signed = sign_in(app, lena.email)
    wrong = post(app, SESSION_MFA, signed, json={"code": wrong_code(secret, clock)})
    assert wrong.status_code == 422, wrong.text
    assert security_events(lena.user_id, "MFA_CHALLENGE_PASSED") == []
    by_code = post(app, SESSION_MFA, signed, json={"code": code_for(secret, clock, 1)})
    assert by_code.status_code == 200, by_code.text
    verified = refresh(app, cookie_of(by_code))
    clock.advance(totp.STEP)  # a step is accepted once
    step_up = post(app, SESSION_MFA, verified, json={"code": code_for(secret, clock, 1)})
    assert step_up.status_code == 200, step_up.text
    again = sign_in(app, lena.email)
    recovered = post(app, SESSION_MFA, again, json={"recovery_code": codes[0]})
    assert recovered.status_code == 200, recovered.text

    passed = security_events(lena.user_id, "MFA_CHALLENGE_PASSED")
    assert [(event["outcome"], event["detail"]) for event in passed] == [
        ("SUCCESS", {"method": "code", "step_up": False}),
        ("SUCCESS", {"method": "code", "step_up": True}),
        ("SUCCESS", {"method": "recovery_code", "step_up": False}),
    ]
    assert [event["request_id"] for event in passed] == [
        by_code.headers["X-Request-Id"],
        step_up.headers["X-Request-Id"],
        recovered.headers["X-Request-Id"],
    ]
    # The event names the verified session the challenge issued, as RECOVERY_CODE_USED does.
    [used] = security_events(lena.user_id, "RECOVERY_CODE_USED")
    assert passed[2]["session_id"] == used["session_id"] is not None
    assert len({event["session_id"] for event in passed}) == 3
    assert second_factor_kinds(lena.user_id) == [
        "MFA_ENROLMENT_STARTED",
        "MFA_ENROLLED",
        "MFA_CHALLENGE_FAILED",
        "MFA_CHALLENGE_PASSED",
        "MFA_CHALLENGE_PASSED",
        "MFA_CHALLENGE_PASSED",
        "RECOVERY_CODE_USED",
    ]


def test_r_111_6_a_refusal_outside_a_workspace_is_a_security_event(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """Independent review of the platform security merge, finding 8 (ruling R-111 (6)); 05
    SAR-26 rev 1.128. A session that owes its second factor is refused on every route, and in
    an open workspace the refusal is that workspace's ``DENIED`` audit event. With no workspace
    open — a user of several workspaces before one is chosen, every operator session — it was in
    neither log. It writes ``MFA_PENDING_DENIED`` with the method, the route and the step owed;
    the routes that answer a pending session write none, and a refusal inside a workspace stays
    one audit event and no security event."""
    lena = member(keyring, clock)
    assign(lena, "viewer")
    other_tenant = second_membership(keyring, clock, lena.email, activate=True)  # tenant_admin

    signed = sign_in(app, lena.email)
    assert signed.body["active_tenant"] is None
    refresh(app, signed.token)  # the session read answers a pending session
    assert pending_denied(lena.user_id) == []
    chosen = select_tenant(app, signed, lena.tenant_id)
    asked = call(
        app, "GET", f"{USERS}/{lena.user_id}", headers=cookie_headers(signed.token, key=False)
    )
    for refused in (chosen, asked):
        assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    events = pending_denied(lena.user_id)
    assert [(event["outcome"], event["detail"], event["request_id"]) for event in events] == [
        (
            "DENIED",
            {"method": "POST", "path": TENANT, "step": "enrolment"},
            chosen.headers["X-Request-Id"],
        ),
        (
            "DENIED",
            # the route's template: no id of the request is copied into the log
            {"method": "GET", "path": f"{USERS}/{{membership_id}}", "step": "enrolment"},
            asked.headers["X-Request-Id"],
        ),
    ]
    assert denied_events(lena.tenant_id) == [] and denied_events(other_tenant) == []

    # Enrolment settles the step and writes no refusal; the next sign-in owes the challenge.
    _, secret, _ = enrol(app, clock, signed)
    assert len(pending_denied(lena.user_id)) == 2
    clock.advance(timedelta(seconds=60))
    later = sign_in(app, lena.email)
    refused = call(app, "GET", ME, headers=cookie_headers(later.token, key=False))
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    assert pending_denied(lena.user_id)[-1]["detail"] == {
        "method": "GET",
        "path": ME,
        "step": "challenge",
    }
    challenged = post(app, SESSION_MFA, later, json={"code": code_for(secret, clock)})
    assert challenged.status_code == 200, challenged.text
    # Positive control: the verified session opens the workspace it was refused, and no
    # refusal is written for it.
    opened = select_tenant(app, refresh(app, cookie_of(challenged)), lena.tenant_id)
    assert opened.status_code == 200, opened.text
    assert len(pending_denied(lena.user_id)) == 3

    # An operator session never has a workspace membership.
    operator = create_operator(operator_services(keyring, clock, app_settings.file_root))
    with identity_session(request_id="tests-mfa-operator") as db:
        operator_id = db.execute(
            select(app_user.c.id).where(app_user.c.email == operator["email"])
        ).scalar_one()
    fresh = sign_in(app, operator["email"])
    refused = call(app, "GET", ME, headers=cookie_headers(fresh.token, key=False))
    assert (refused.status_code, slug(refused)) == (403, SECOND_FACTOR_SLUG), refused.text
    [event] = pending_denied(operator_id)
    assert (event["outcome"], event["detail"], event["request_id"]) == (
        "DENIED",
        {"method": "GET", "path": ME, "step": "enrolment"},
        refused.headers["X-Request-Id"],
    )

    # Inside a workspace: the workspace's DENIED audit event, and no security event.
    rhea = colleague(lena.tenant_id, "rhea")
    assign(rhea, "controller")
    at_work = sign_in(app, rhea.email)
    assert at_work.body["active_tenant"] is not None
    inside = call(app, "GET", CONTRACTS, headers=cookie_headers(at_work.token, key=False))
    assert (inside.status_code, slug(inside)) == (403, SECOND_FACTOR_SLUG), inside.text
    assert denied_events(lena.tenant_id) == [("contract.read", "enrolment", CONTRACTS)]
    assert pending_denied(rhea.user_id) == []


def test_regenerate_recovery_codes_invalidates_previous_batch(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    enrolled, _, first_batch = enrol(app, clock, sign_in(app, lena.email))

    regenerated = post(app, RECOVERY_CODES, enrolled)
    assert regenerated.status_code == 200, regenerated.text
    second_batch = regenerated.json()["recovery_codes"]
    assert len(second_batch) == 10
    assert not set(first_batch) & set(second_batch)

    clock.advance(timedelta(minutes=6))
    stale = post(app, RECOVERY_CODES, enrolled)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required")

    signed = sign_in(app, lena.email)
    old = post(app, SESSION_MFA, signed, json={"recovery_code": first_batch[1]})
    assert (old.status_code, old.json()["errors"][0]["field"]) == (422, "recovery_code")
    new = post(app, SESSION_MFA, signed, json={"recovery_code": second_batch[1]})
    assert new.status_code == 200, new.text
    assert new.json()["recovery_codes_remaining"] == 9
