"""Signed-in members for api and domain tests (dev-guide §9.1; BUILD_SPEC PLF-2, PLF-4).

``member`` provisions a tenant through ``tenant_factory`` and makes its admin a user who can sign
in: a password and an ``ACTIVE`` membership, until invitation acceptance exists as a command. The
provisioned ``tenant_admin`` grant is revoked, so tests assign the roles they need. ``colleague``
adds another such member to the tenant.
``sign_in`` and ``select_tenant`` drive the API-R-01 session routes over ASGI; ``workspace`` and
``enrolled`` return an ``Actor`` in the tenant, the second verified through TOTP enrolment, and
``step_up`` refreshes an actor's MFA verification (BR-PLT-06).

The second factor is the user's rule (03 REQ-PLT-005; supervisor ruling R-48 (b)): a member who
holds a ``requires_mfa`` permission, or who has a confirmed factor, works only in a session that
passed it. ``sign_in`` stays the bare password step, so a test can look at the session that still
owes a step; ``workspace`` settles the step as the member would: a member who must enrol has an
authenticator (``authenticator``, world setup like the password of ``member``), and the session
answers the sign-in challenge through ``POST /session/mfa`` (``challenge``).

A test that enrols a persona, or gives it a role with a ``requires_mfa`` permission, in mid-test
goes on with the verified session: the one of before owes the second factor from then on and is
refused everywhere else with 403 ``mfa-required``. ``carrying`` puts the verified session into a
world that was built with the earlier one.
"""

from __future__ import annotations

import dataclasses
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_api.auth import passwords, totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import app_user, tenant_membership, user_mfa_factor
from fastapi import FastAPI
from sqlalchemy import select, update
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.rows import (
    insert_active_membership,
    insert_app_user,
    insert_sealed_mfa_factor,
    revoke_role_assignments,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

PASSWORD = "Lena!Revenue2026"
LOGIN = "/api/v1/session/login"
TENANT = "/api/v1/session/tenant"
SESSION = "/api/v1/session"
SESSION_MFA = "/api/v1/session/mfa"


@dataclass(frozen=True, slots=True)
class Member:
    user_id: UUID
    email: str
    tenant_id: UUID
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class Signed:
    token: str
    csrf_token: str
    body: Mapping[str, Any]


@lru_cache(maxsize=1)
def password_hash() -> str:
    return passwords.hash_password(PASSWORD)


def member(
    keyring: KeyRing,
    clock: FrozenClock,
    *,
    code: str | None = None,
    name: str = "lena",
    is_demo: bool = False,
) -> Member:
    """A provisioned tenant (a random code unless ``code`` is given) whose admin
    ``<name>@<code>.test`` has a password and an ACTIVE membership; ``is_demo`` gives the tenant
    the demo marker."""
    code = code or f"t-{secrets.token_hex(6)}"
    email = f"{name}@{code}.test"
    result = tenant_factory(
        keyring=keyring, clock=clock, code=code, admin_email=email, is_demo=is_demo
    )
    tenant_id = tenant_id_of(result)
    with identity_session(request_id="tests-session-member") as db:
        user_id = db.execute(select(app_user.c.id).where(app_user.c.email == email)).scalar_one()
        db.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(password_hash=password_hash(), updated_by_kind="SYSTEM")
        )
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
        revoke_role_assignments(
            db, tenant_id=tenant_id, membership_id=result.admin_membership_id, at=clock.now()
        )
    return Member(
        user_id=user_id, email=email, tenant_id=tenant_id, membership_id=result.admin_membership_id
    )


def cookie_of(response: HttpResponse) -> str:
    return response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]


def sign_in(app: FastAPI, email: str, password: str = PASSWORD) -> Signed:
    response = call(app, "POST", LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return Signed(token=cookie_of(response), csrf_token=body["csrf_token"], body=body)


def cookie_headers(
    token: str, csrf_token: str | None = None, *, key: bool = True, **extra: str
) -> dict[str, str]:
    headers = {"Cookie": f"erev_session={token}", **extra}
    if csrf_token is not None:
        headers["X-CSRF-Token"] = csrf_token
    if key:
        headers["Idempotency-Key"] = f"k-{uuid.uuid4()}"
    return headers


def select_tenant(app: FastAPI, signed: Signed, tenant_id: UUID) -> HttpResponse:
    return call(
        app,
        "POST",
        TENANT,
        json={"tenant_id": str(tenant_id)},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )


@dataclass(frozen=True, slots=True)
class Actor:
    """A member signed in with the tenant active; ``secret`` is the TOTP seed once enrolled."""

    member: Member
    token: str
    csrf_token: str
    secret: str | None


def colleague(tenant_id: UUID, name: str) -> Member:
    """Another user of the tenant who can sign in, with an ACTIVE membership and no role."""
    email = f"{name}-{secrets.token_hex(4)}@members.test"
    with identity_session(request_id="tests-colleague") as session:
        user_id = insert_app_user(session, email=email)
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(
                password_hash=password_hash(), display_name=name.title(), updated_by_kind="SYSTEM"
            )
        )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        membership_id = insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
    return Member(user_id=user_id, email=email, tenant_id=tenant_id, membership_id=membership_id)


# The TOTP seeds of the members these helpers enrolled, by user id: a later sign-in of the same
# member answers the challenge with it.
_SEEDS: dict[UUID, str] = {}


def authenticator(app: FastAPI, someone: Member) -> str:
    """World setup: ``someone`` has an authenticator app — a confirmed TOTP factor with a fresh
    seed, sealed as ``mfa.enroll`` seals it. Returns the seed. The member's sessions then pass the
    challenge through the product's own route (``challenge``)."""
    seed = totp.new_secret()
    with identity_session(request_id="tests-authenticator") as db:
        insert_sealed_mfa_factor(
            db, someone.user_id, keyring=app.state.keyring, seed=seed, at=app.state.clock.now()
        )
    _SEEDS[someone.user_id] = seed
    return seed


def next_code(app: FastAPI, user_id: UUID, seed: str) -> str:
    """The code of the earliest step of the verification window the factor has not used yet
    (``totp.matching_step`` accepts t-1 to t+1 and refuses a step at or before the last one)."""
    current = totp.time_step(app.state.clock.now())
    with identity_session(request_id="tests-next-code") as db:
        last = db.execute(
            select(user_mfa_factor.c.last_used_step).where(
                user_mfa_factor.c.user_id == user_id, user_mfa_factor.c.disabled_at.is_(None)
            )
        ).scalar_one()
    step = current - totp.WINDOW if last is None else max(current - totp.WINDOW, int(last) + 1)
    assert step <= current + totp.WINDOW, (
        "every TOTP step of this instant is spent for this member: advance the clock 30 seconds"
    )
    return totp.code_at(seed, step)


def challenge(app: FastAPI, someone: Member, signed: Signed, seed: str) -> Signed:
    """Answer the sign-in challenge of ``signed`` with the member's TOTP; the rotated, verified
    session (``POST /session/mfa``)."""
    verified = call(
        app,
        "POST",
        SESSION_MFA,
        json={"code": next_code(app, someone.user_id, seed)},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert verified.status_code == 200, verified.text
    return refreshed(app, cookie_of(verified))


def second_factor(
    app: FastAPI, someone: Member, signed: Signed, secret: str | None = None
) -> tuple[Signed, str | None]:
    """The session of ``signed`` once it owes no second-factor step, with the member's seed
    (REQ-PLT-005). A session that owes nothing comes back as it is."""
    seed = secret or _SEEDS.get(someone.user_id)
    if signed.body.get("mfa_enrolment_required"):
        seed = authenticator(app, someone)
    elif not signed.body.get("mfa_required"):
        return signed, seed
    assert seed is not None, f"{someone.email} has a factor whose seed the test must pass"
    return challenge(app, someone, signed, seed), seed


def workspace(app: FastAPI, someone: Member, signed: Signed, secret: str | None = None) -> Actor:
    """``someone`` at work in the tenant: the second factor settled where the session owes one
    (``second_factor``), then the workspace selected."""
    signed, secret = second_factor(app, someone, signed, secret)
    selected = select_tenant(app, signed, someone.tenant_id)
    assert selected.status_code == 200, selected.text
    return Actor(
        member=someone,
        token=cookie_of(selected),
        csrf_token=selected.json()["csrf_token"],
        secret=secret,
    )


def refreshed(app: FastAPI, token: str) -> Signed:
    """The session of a rotated cookie with its CSRF token."""
    body = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"}).json()
    return Signed(token=token, csrf_token=body["csrf_token"], body=body)


def enrolled(app: FastAPI, clock: FrozenClock, someone: Member) -> Actor:
    """Sign in, confirm TOTP enrolment (the rotated session is verified) and choose the tenant."""
    signed = sign_in(app, someone.email)
    started = call(
        app,
        "POST",
        "/api/v1/me/mfa/enroll",
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert started.status_code == 200, started.text
    secret = str(started.json()["secret_base32"])
    confirmed = call(
        app,
        "POST",
        "/api/v1/me/mfa/confirm",
        json={"code": totp.code_at(secret, totp.time_step(clock.now()))},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert confirmed.status_code == 200, confirmed.text
    _SEEDS[someone.user_id] = secret
    return workspace(app, someone, refreshed(app, cookie_of(confirmed)), secret)


def step_up(app: FastAPI, clock: FrozenClock, someone: Actor) -> Actor:
    """A fresh TOTP verification of an enrolled actor at the clock's current step."""
    assert someone.secret is not None
    verified = call(
        app,
        "POST",
        SESSION_MFA,
        json={"code": totp.code_at(someone.secret, totp.time_step(clock.now()))},
        headers=cookie_headers(someone.token, someone.csrf_token),
    )
    assert verified.status_code == 200, verified.text
    fresh = refreshed(app, cookie_of(verified))
    return replace(someone, token=fresh.token, csrf_token=fresh.csrf_token)


def carrying[World: DataclassInstance](world: World, **personas: Actor) -> World:
    """``world`` with the sessions of these personas put in place of the ones it was built with.

    Once a persona has a factor — the test enrolled it, or gave it a role with a ``requires_mfa``
    permission — its earlier session owes the second factor and answers 403 ``mfa-required``
    everywhere but the session routes (03 REQ-PLT-005; security review 2026-09-29 S21). The test
    goes on with the verified session, and so does the world its helpers read::

        maya = enrolled(world.app, clock, world.maya.member)
        world = carrying(world, maya=maya)

    A persona is a field of the world; ``maya`` of a world that has none is the author of its
    ``place`` (``support.worlds.ReportWorld``).
    """
    fields = {field.name for field in dataclasses.fields(world)}
    changes: dict[str, Any] = {}
    for name, actor in personas.items():
        if name in fields:
            changes[name] = actor
        else:
            assert name == "maya" and "place" in fields, f"{type(world).__name__} has no {name}"
            changes["place"] = replace(getattr(world, "place"), author=actor)  # noqa: B009
    return replace(world, **changes)
