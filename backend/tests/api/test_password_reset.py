"""API-R-01 password reset (04 T-PLT-42 rules 1 to 3, §16.12; SCREENS_B §12.3; BUILD_SPEC
PLF-15)."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    outbox_message,
    password_reset_token,
    security_event,
    tenant_membership,
    user_session,
)
from erev_api.domain.platform.provisioning import invitation_token
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.links import emailed_token
from support.principals import (
    LOGIN,
    PASSWORD,
    Member,
    cookie_headers,
    member,
    sign_in,
    workspace,
)
from support.rows import RowContext, membership_row

RESET = "/api/v1/session/password-reset"
CONFIRM = "/api/v1/session/password-reset/confirm"
PASSWORD_CHANGE = "/api/v1/me/password"
NEW_PASSWORD_VALUE = "Oskar!Ledger2027"
THIRD_PASSWORD_VALUE = "Tilde!Ledger2029"
WEAK_PASSWORD = "password1234"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).rsplit("/", 1)[1]


def tokens_of(user_id: UUID) -> list[Mapping[str, Any]]:
    with identity_session(request_id="tests-reset-tokens") as db:
        return list(
            db.execute(
                select(password_reset_token)
                .where(password_reset_token.c.user_id == user_id)
                .order_by(password_reset_token.c.created_at, password_reset_token.c.id)
            ).mappings()
        )


def all_token_count() -> int:
    with identity_session(request_id="tests-reset-count") as db:
        return int(db.execute(select(func.count()).select_from(password_reset_token)).scalar_one())


def reset_events(user_id: UUID) -> list[tuple[str, str]]:
    with identity_session(request_id="tests-reset-events") as db:
        rows = db.execute(
            select(security_event.c.kind, security_event.c.outcome)
            .where(security_event.c.user_id == user_id)
            .order_by(security_event.c.chain_seq)
        ).all()
    return [(str(kind), str(outcome)) for kind, outcome in rows]


def reset_messages(lena: Member) -> list[Mapping[str, Any]]:
    context = DbContext(tenant_id=lena.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as db:
        return list(
            db.execute(
                select(outbox_message)
                .where(outbox_message.c.aggregate_type == "password_reset_token")
                .order_by(outbox_message.c.created_at, outbox_message.c.id)
            ).mappings()
        )


def reset_token(message: Mapping[str, Any]) -> str:
    """The token of the reset email: the message names it, the link is composed as the email
    carries it (04 T-INT-03 ``payload``; T-PLT-42)."""
    return emailed_token(message["payload"], prefix="/password/reset/confirm#token=")


def test_request_always_202(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    before = all_token_count()
    unknown = call(app, "POST", RESET, json={"email": f"nobody-{secrets.token_hex(6)}@x.test"})
    assert (unknown.status_code, unknown.content) == (202, b""), unknown.text
    assert all_token_count() == before
    assert reset_messages(lena) == []

    known = call(app, "POST", RESET, json={"email": lena.email.upper()})
    assert (known.status_code, known.content) == (202, b""), known.text
    [token] = tokens_of(lena.user_id)
    assert token["token_expires_at"] == clock.now() + timedelta(minutes=60)
    assert (token["used_at"], token["superseded_at"]) == (None, None)
    assert reset_events(lena.user_id) == [("PASSWORD_RESET_REQUESTED", "SUCCESS")]
    [message] = reset_messages(lena)
    assert (message["topic"], message["aggregate_id"], message["payload"]["to"]) == (
        "EMAIL",
        token["id"],
        lena.email,
    )
    assert "/password/reset/confirm#token=" in message["payload"]["link_path"]
    # Security review P3-17 (ruling R-48 (g)): the row names the token and never holds it — the
    # link stood here in clear, token included. The token the email carries is the one whose
    # SHA-256 the T-PLT-42 row stores.
    assert message["payload"]["link_path"] == "/password/reset/confirm#token={token}"
    assert message["payload"]["link_token"] == {
        "purpose": "password-reset",
        "reference": str(token["id"]),
        "key_id": keyring.current_security_key_id(),
    }
    emailed = reset_token(message)
    assert hashlib.sha256(emailed.encode("ascii")).hexdigest() == token["token_sha256"]
    assert emailed not in json.dumps(dict(message), default=str)

    for _ in range(4):
        assert call(app, "POST", RESET, json={"email": lena.email}).status_code == 202
    issued = tokens_of(lena.user_id)
    assert len(issued) == 5
    assert [row["superseded_at"] is not None for row in issued] == [True] * 4 + [False]
    assert len(reset_messages(lena)) == 5

    sixth = call(app, "POST", RESET, json={"email": lena.email})
    assert (sixth.status_code, sixth.content) == (202, b"")
    assert len(tokens_of(lena.user_id)) == 5
    assert len(reset_messages(lena)) == 5
    assert reset_events(lena.user_id)[-1] == ("PASSWORD_RESET_REQUESTED", "DENIED")


# --- Item RESET-EMAIL-OPEN-INVITATION-1 (the supervisor's order of 2026-10-02, register index
# 290; 04 T-PLT-42 rule 1 rev 1.308): a person without an active membership is answered in the
# workspace of an open invitation ----------------------------------------------------------------

ACCEPT = "/api/v1/session/accept-invitation"


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _invited(
    lena: Member,
    keyring: KeyRing,
    clock: FrozenClock,
    *,
    code: str | None = None,
    expires_in: timedelta | None = timedelta(days=7),
    acceptable: bool = True,
) -> tuple[Member, str]:
    """Another workspace that invites Lena as she is: its admin, and the invitation's token.
    Not ``acceptable``: an INVITED row whose token hash is null, with its expiry or — without
    ``expires_in`` — with none: the rows T-PLT-07's checks refuse."""
    other = member(keyring, clock, name="bea", code=code)
    issued = invitation_token(keyring)
    digest = hashlib.sha256(issued.token.encode()).hexdigest() if acceptable else None
    row = {
        **membership_row(RowContext(tenant_id=other.tenant_id, user_id=lena.user_id)),
        "invited_at": clock.now(),
        "invitation_token_sha256": digest,
        "invitation_expires_at": None if expires_in is None else clock.now() + expires_in,
    }
    with tenant_session(_context(other.tenant_id)) as db:
        db.execute(insert(tenant_membership).values(row))
    return other, issued.token


def _removed(lena: Member, clock: FrozenClock) -> None:
    """Lena's one membership ends: she is a person with a password and no workspace."""
    with tenant_session(_context(lena.tenant_id)) as db:
        db.execute(
            update(tenant_membership)
            .where(tenant_membership.c.id == lena.membership_id)
            .values(status="REMOVED", removed_at=clock.now())
        )


def _asked(app: FastAPI, lena: Member) -> dict[str, Any]:
    """One reset request of Lena's: 202 with no body, and what the security log says of it."""
    sent = call(app, "POST", RESET, json={"email": lena.email})
    assert (sent.status_code, sent.content) == (202, b""), sent.text
    with identity_session(request_id="tests-reset-detail") as db:
        found = db.execute(
            select(security_event.c.outcome, security_event.c.detail)
            .where(security_event.c.user_id == lena.user_id)
            .order_by(security_event.c.chain_seq.desc())
            .limit(1)
        ).one()
    return {"outcome": str(found.outcome), **dict(found.detail)}


def test_reset_email_open_invitation_1_an_invited_person_resets_and_accepts(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item RESET-EMAIL-OPEN-INVITATION-1, a release blocker. Measured before: a person removed
    from a workspace and invited again — there or elsewhere — who had forgotten the earlier
    password could neither accept (the invitation asks a person who has a password for it) nor
    reset it: the request answered 202, wrote its token and NO email, because the email was
    written only in the workspace of an ACTIVE membership. Now the email is written in the
    workspace of the open invitation, the security log says where, and the invitation is
    accepted with the new password. The limit of five requests an hour counts as before."""
    lena = member(keyring, clock)
    _removed(lena, clock)
    other, invitation = _invited(lena, keyring, clock)

    said = _asked(app, lena)
    assert (said["outcome"], said["email"]) == ("SUCCESS", True)  # before: no email
    assert said["email_tenant_id"] == str(other.tenant_id)
    assert reset_messages(lena) == []  # nothing in the workspace she left
    [message] = reset_messages(other)
    assert message["payload"]["to"] == lena.email

    forgotten = call(app, "POST", ACCEPT, json={"token": invitation, "password": "Wrong!Guess2031"})
    assert forgotten.status_code == 422, forgotten.text
    confirmed = call(
        app,
        "POST",
        CONFIRM,
        json={"token": reset_token(message), "new_password": NEW_PASSWORD_VALUE},
    )
    assert (confirmed.status_code, confirmed.content) == (204, b""), confirmed.text
    accepted = call(app, "POST", ACCEPT, json={"token": invitation, "password": NEW_PASSWORD_VALUE})
    assert accepted.status_code == 200, accepted.text
    with tenant_session(_context(other.tenant_id)) as db:
        status = db.execute(
            select(tenant_membership.c.status).where(
                tenant_membership.c.user_id == lena.user_id,
                tenant_membership.c.tenant_id == other.tenant_id,
            )
        ).scalar_one()
    assert str(status) == "ACTIVE"


def test_reset_email_open_invitation_1_who_gets_no_email_and_who_gets_it_elsewhere(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The controls. A member is answered as before, in the workspace of the ACTIVE membership,
    whatever invitation stands beside it. Without one: an EXPIRED invitation gets no email (the
    token is written, the log says ``email`` false and no workspace); of several open
    invitations the one sent last, a tie by ascending tenant id; a disabled identity gets
    neither token nor email. And the limit of the request counts for an invited person too."""
    # --- a member with an invitation elsewhere: in her own workspace, as before ---
    member_too = member(keyring, clock, name="mia")
    elsewhere, _ = _invited(member_too, keyring, clock)
    said = _asked(app, member_too)
    assert (said["email"], said["email_tenant_id"]) == (True, str(member_too.tenant_id))
    assert (len(reset_messages(member_too)), reset_messages(elsewhere)) == (1, [])

    # --- an expired invitation alone: a token, no email ---
    late = member(keyring, clock, name="lou")
    _removed(late, clock)
    expired, _ = _invited(late, keyring, clock, expires_in=timedelta(seconds=-1))
    said = _asked(app, late)
    assert (said["outcome"], said["email"], said["email_tenant_id"]) == ("SUCCESS", False, None)
    assert (len(tokens_of(late.user_id)), reset_messages(expired)) == (1, [])

    # --- several invitations: a tie by the workspace's code, then the one sent last ---
    lena = member(keyring, clock)
    _removed(lena, clock)
    one, _ = _invited(lena, keyring, clock)
    two, _ = _invited(lena, keyring, clock)
    first, second = sorted((one, two), key=lambda found: found.tenant_id)
    assert _asked(app, lena)["email_tenant_id"] == str(first.tenant_id)
    clock.advance(timedelta(seconds=1))
    last, _ = _invited(lena, keyring, clock)
    assert _asked(app, lena)["email_tenant_id"] == str(last.tenant_id)
    assert (len(reset_messages(first)), len(reset_messages(last)), reset_messages(second)) == (
        1,
        1,
        [],
    )

    # --- the limit of five requests an hour holds for her as for a member ---
    for _ in range(3):
        assert _asked(app, lena)["outcome"] == "SUCCESS"
    assert _asked(app, lena) == {"outcome": "DENIED", "limit": "user"}
    assert (len(tokens_of(lena.user_id)), len(reset_messages(last))) == (5, 4)

    # --- a disabled identity with an open invitation: neither token nor email ---
    gone = member(keyring, clock, name="ida")
    _removed(gone, clock)
    waiting, _ = _invited(gone, keyring, clock)
    with identity_session(request_id="tests-reset-disabled") as db:
        db.execute(update(app_user).where(app_user.c.id == gone.user_id).values(status="DISABLED"))
    sent = call(app, "POST", RESET, json={"email": gone.email})
    assert (sent.status_code, sent.content) == (202, b""), sent.text
    assert (tokens_of(gone.user_id), reset_messages(waiting)) == ([], [])


def test_reset_email_open_invitation_1_no_invitation_is_without_a_token_hash(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """An OPEN invitation is what the acceptance reads: INVITED, a token hash, not expired. The
    reset's read names the hash as well, and no row can tell the two apart: an invitation nobody
    can accept — INVITED, the token hash null, the expiry as it stood or null too — is a row
    T-PLT-07's two checks refuse, so it never is the workspace an email is written in. (For the
    same reason a sandbox copy carries an open invitation as REMOVED: 04 T-PLT-07 rev 1.293.)"""
    lena = member(keyring, clock)
    _removed(lena, clock)
    with pytest.raises(IntegrityError, match="ck_tenant_membership__invitation_"):
        _invited(lena, keyring, clock, acceptable=False)
    with pytest.raises(IntegrityError, match="ck_tenant_membership__invitation_token"):
        _invited(lena, keyring, clock, acceptable=False, expires_in=None)
    # And she, with no invitation at all, gets her token and no email.
    said = _asked(app, lena)
    assert (said["outcome"], said["email"], said["email_tenant_id"]) == ("SUCCESS", False, None)


def test_confirm_resets_and_ends_sessions(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    first, second = sign_in(app, lena.email), sign_in(app, lena.email)
    wrong = call(app, "POST", LOGIN, json={"email": lena.email, "password": NEW_PASSWORD_VALUE})
    assert wrong.status_code == 401
    assert call(app, "POST", RESET, json={"email": lena.email}).status_code == 202
    [message] = reset_messages(lena)
    token = reset_token(message)

    weak = call(app, "POST", CONFIRM, json={"token": token, "new_password": WEAK_PASSWORD})
    assert (weak.status_code, slug(weak)) == (422, "password-policy"), weak.text
    assert weak.json()["errors"][0]["field"] == "new_password"
    assert tokens_of(lena.user_id)[0]["used_at"] is None

    confirmed = call(
        app, "POST", CONFIRM, json={"token": token, "new_password": NEW_PASSWORD_VALUE}
    )
    assert (confirmed.status_code, confirmed.content) == (204, b""), confirmed.text
    assert tokens_of(lena.user_id)[0]["used_at"] == clock.now()
    with identity_session(request_id="tests-reset-sessions") as db:
        ended = db.execute(
            select(user_session.c.end_reason).where(user_session.c.user_id == lena.user_id)
        ).scalars()
        reasons = sorted(str(reason) for reason in ended)
        failures = db.execute(
            select(app_user.c.failed_login_count).where(app_user.c.id == lena.user_id)
        ).scalar_one()
    assert reasons == ["PASSWORD_CHANGED", "PASSWORD_CHANGED"]
    assert failures == 0
    kinds = [kind for kind, _ in reset_events(lena.user_id)]
    assert kinds[-2:] == ["PASSWORD_RESET_COMPLETED", "PASSWORD_CHANGED"]
    for signed in (first, second):
        cookie = {"Cookie": f"erev_session={signed.token}"}
        assert call(app, "GET", "/api/v1/session", headers=cookie).json()["authenticated"] is False

    reused = call(app, "POST", CONFIRM, json={"token": token, "new_password": NEW_PASSWORD_VALUE})
    assert (reused.status_code, slug(reused)) == (404, "not-found")
    unknown = call(
        app, "POST", CONFIRM, json={"token": secrets.token_urlsafe(32), "new_password": PASSWORD}
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found")
    old = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert old.status_code == 401
    assert sign_in(app, lena.email, NEW_PASSWORD_VALUE).body["authenticated"] is True


def test_t_plt_42_rule_4_a_password_change_supersedes_an_open_reset_link(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """04 T-PLT-42 rule 4, rev 1.151 (security review P3-17). A reset link stayed good for its
    hour after the user had changed the password through ``POST /me/password``: whoever could
    read the mailbox — the reason a user changes a password — still set a new one with it. The
    change supersedes the user's open tokens; the link then answers what an expired link
    answers, and a link requested after the change works."""
    lena = member(keyring, clock)

    def requested_link() -> str:
        """Request a reset; the token of the user's one open link, read from its email."""
        assert call(app, "POST", RESET, json={"email": lena.email}).status_code == 202
        [row] = [
            row
            for row in tokens_of(lena.user_id)
            if row["used_at"] is None and row["superseded_at"] is None
        ]
        [message] = [m for m in reset_messages(lena) if m["aggregate_id"] == row["id"]]
        return reset_token(message)

    before = requested_link()
    current = workspace(app, lena, sign_in(app, lena.email))
    changed = call(
        app,
        "POST",
        PASSWORD_CHANGE,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD_VALUE},
        headers=cookie_headers(current.token, current.csrf_token),
    )
    assert (changed.status_code, changed.content) == (204, b""), changed.text

    stale = call(app, "POST", CONFIRM, json={"token": before, "new_password": THIRD_PASSWORD_VALUE})
    assert stale.status_code == 404, "the link issued before the change still sets a password"
    assert slug(stale) == "not-found", stale.text
    [superseded] = tokens_of(lena.user_id)
    assert (superseded["used_at"], superseded["superseded_at"]) == (None, clock.now())
    wrong = call(app, "POST", LOGIN, json={"email": lena.email, "password": THIRD_PASSWORD_VALUE})
    assert wrong.status_code == 401
    assert sign_in(app, lena.email, NEW_PASSWORD_VALUE).body["authenticated"] is True

    # A link requested after the change is open; past its hour it answers exactly what the
    # superseded link answered.
    after = requested_link()
    clock.advance(timedelta(minutes=61))
    expired = call(app, "POST", CONFIRM, json={"token": after, "new_password": NEW_PASSWORD_VALUE})
    assert (expired.status_code, slug(expired)) == (404, "not-found"), expired.text
    assert {**stale.json(), "instance": None} == {**expired.json(), "instance": None}

    # Positive control: a link that is neither superseded nor expired sets the password.
    fresh = requested_link()
    done = call(app, "POST", CONFIRM, json={"token": fresh, "new_password": THIRD_PASSWORD_VALUE})
    assert (done.status_code, done.content) == (204, b""), done.text
    assert sign_in(app, lena.email, THIRD_PASSWORD_VALUE).body["authenticated"] is True
