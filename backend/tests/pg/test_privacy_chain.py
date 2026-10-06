"""03 REQ-SEC-007 on the audit chain (BUILD_SPEC SOP-5; 05 PRV-03, PRV-04, PRV-07 a; 04 T-PLT-19,
DB-09, DB-19; dev-guide DG-KRN-AUD-06, DG-KRN-AUD-07).

Erasing a person rewrites the mutable identity row only. The immutable audit chain is not
touched: it never held the person's e-mail in clear — the writer stores a personal value in the
PRV-04 form ``{"hmac": <hex>, "length": n}`` when the event is appended — and it keeps its
pseudonymous ``actor_id`` references, so the whole chain still verifies after the erasure.

Lena's twelve events are appended through the production writer (``build_event`` +
``append_events``) with her USER actor, six of them carrying her e-mail under the personal key as
a membership or identity event would; the erasure itself runs through
``POST /users/{membership_id}/anonymise`` with a fresh step-up (revision 0073: the DB-13 grant and
the DB-19 guard admit its UPDATE).
"""

from __future__ import annotations

import json
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.audit.chain import append_events
from erev_api.audit.redact import pseudonym
from erev_api.audit.verify import verify_tenant_chain
from erev_api.audit.writer import AuditActor, build_event
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import app_user, audit_chain_head, audit_event, tenant
from erev_api.domain.platform.privacy import ANONYMISE_ACTION, erased_email
from erev_api.enums import ControlResult, MembershipStatus, PrincipalKind, UserStatus
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import call
from support.principals import Member, colleague, cookie_headers, enrolled, member, step_up
from support.rows import insert_role_assignment

pytestmark = pytest.mark.pg

AUTHORED: Final = 12
REASON: Final = "Data subject request DSR-2026-021 received"
PAYLOAD_COLUMNS: Final = ("before", "after", "diff", "detail")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _author(lena: Member, keyring: KeyRing, clock: FrozenClock) -> list[UUID]:
    """Twelve audit events whose actor is Lena; the even ones carry her e-mail under the personal
    key in ``before`` and ``after`` (so also in ``diff`` when it changes). Returns their ids."""
    actor = AuditActor(
        kind=PrincipalKind.USER,
        id=lena.user_id,
        roles=(),
        auth_method="password",
        mfa_verified=False,
        on_behalf_of_id=None,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id="tests-req-sec-007",
    )
    events = []
    for number in range(1, AUTHORED + 1):
        personal = number % 2 == 0
        events.append(
            build_event(
                tenant_id=lena.tenant_id,
                actor=actor,
                occurred_at=clock.now(),
                action="tenant_membership.update",
                object_type="tenant_membership",
                object_id=lena.membership_id,
                before={"note": number - 1, **({"email": f"old-{lena.email}"} if personal else {})},
                after={"note": number, **({"email": lena.email} if personal else {})},
            )
        )
    with tenant_session(_context(lena.tenant_id)) as session:
        appended = append_events(session, tenant_id=lena.tenant_id, keyring=keyring, events=events)
    assert appended == AUTHORED
    return [UUID(str(event["id"])) for event in events]


def _events(tenant_id: UUID) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        rows = session.execute(select(audit_event).order_by(audit_event.c.chain_seq)).mappings()
        return [dict(row) for row in rows]


def test_req_sec_007_chain_verifies_after_anonymise(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """BUILD_SPEC SOP-5: after anonymising a user who authored 12 audit events,
    ``verify_tenant_chain`` returns PASS over every event; the twelve events keep ``actor_id``
    equal to the user id; no clear e-mail of the user remains in ``audit_event.before``, ``after``
    or ``diff`` (nor in ``detail``) — where an event names it, it is the 05 PRV-04 HMAC form
    ``{"hmac": <hex>, "length": n}`` under the tenant's audit key."""
    tomas = member(keyring, clock)
    tenant_id = tomas.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=tomas.membership_id,
            role_code="tenant_admin",
        )
        key_id = session.execute(
            select(tenant.c.audit_hmac_key_id).where(tenant.c.id == tenant_id)
        ).scalar_one()
    admin = enrolled(app, clock, tomas)
    lena = colleague(tenant_id, "lena")
    authored = _author(lena, keyring, clock)
    assert len(authored) == AUTHORED
    stored_before = [event for event in _events(tenant_id) if event["actor_id"] == lena.user_id]
    assert [event["id"] for event in stored_before] == authored

    clock.advance(totp.STEP)  # a TOTP step later than the enrolment code (T-PLT-04 last_used_step)
    admin = step_up(app, clock, admin)
    erased = call(
        app,
        "POST",
        f"/api/v1/users/{lena.membership_id}/anonymise",
        json={"reason": REASON},
        headers=cookie_headers(admin.token, admin.csrf_token),
    )
    assert erased.status_code == 200, erased.text
    assert erased.json()["status"] == MembershipStatus.REMOVED.value
    with identity_session(request_id="tests-req-sec-007-user", user_id=lena.user_id) as session:
        person = session.execute(
            select(app_user.c.email, app_user.c.status).where(app_user.c.id == lena.user_id)
        ).one()
    assert (person.email, person.status) == (erased_email(lena.user_id), UserStatus.DISABLED.value)

    # 1. The whole chain verifies: every event, first to head, none skipped.
    with tenant_session(_context(tenant_id), read_only=True) as session:
        head = session.execute(select(audit_chain_head)).mappings().one()
        verified = verify_tenant_chain(session, tenant_id=tenant_id, keyring=keyring)
    events = _events(tenant_id)
    assert verified.result is ControlResult.PASS, verified.failure_detail
    assert verified.first_failure_seq is None
    assert (verified.from_chain_seq, verified.to_chain_seq) == (1, head["last_chain_seq"])
    assert verified.events_checked == head["last_chain_seq"] == len(events)
    assert verified.digest_last_hmac == head["last_hmac"] == events[-1]["hmac"]

    # 2. The pseudonymous references stay: her twelve events, still hers, every column as it was
    #    stored before the erasure (the chain is not rewritten; DB-01).
    hers = [event for event in events if event["actor_id"] == lena.user_id]
    assert [event["id"] for event in hers] == authored
    assert hers == stored_before

    # 3. No clear e-mail of hers anywhere in the payload columns of any event of the tenant.
    key = keyring.tenant_audit_key(str(key_id))
    for event in events:
        for column in PAYLOAD_COLUMNS:
            stored = json.dumps(event[column])
            assert lena.email not in stored, (event["chain_seq"], column)
    # 4. Where an event names the e-mail, it is the PRV-04 form under the tenant's audit key.
    current, previous = pseudonym(key, lena.email), pseudonym(key, f"old-{lena.email}")
    assert set(current) == {"hmac", "length"} and current["length"] == len(lena.email)
    assert len(current["hmac"]) == 64 and int(current["hmac"], 16) >= 0
    personal = [event for event in hers if "email" in event["after"]]
    assert len(personal) == AUTHORED // 2
    for event in personal:
        assert event["before"]["email"] == previous and event["after"]["email"] == current
        (changed,) = [entry for entry in event["diff"] if entry["path"] == "email"]
        assert (changed["before"], changed["after"]) == (previous, current)
    (anonymise,) = [event for event in events if event["action"] == ANONYMISE_ACTION]
    assert anonymise["object_id"] == lena.user_id
    assert anonymise["actor_id"] == tomas.user_id
    assert anonymise["before"]["email"] == current, "the old e-mail, PRV-04 form only"
    # The erased address is not the person's e-mail; being a personal key, it is pseudonymised too.
    assert anonymise["after"]["email"] == pseudonym(key, erased_email(lena.user_id))
