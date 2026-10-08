"""05 PRV-07 erasure commands (BUILD_SPEC SOP-5; 04 API-R-05, API-R-12; 03 REQ-SEC-007).

Tomas is the bootstrap Tenant Admin of a provisioned workspace and Grace a second Tenant Admin,
both enrolled in MFA; Lena is the member whose personal data is erased. These tests need the
test database (``committed_db``): lane P8 records them NOT RUN until a provisioned database and a
gate slot are available (databases are Ray-side). The shred tests are coded to D-98 candidate 145
AMENDMENT 2 (FILES-SHRED-1, P1's ``_admit`` / ``_retained``); that chain is not on the merged
heads 90ac73bf / 0959b560 (they carry P2's earlier ``shred_sidecar``) and landed on main at
4bd5a67f, so the shred tests wait for that merge and for the lane database. Every TOTP step-up
here moves the frozen clock one step first (T-PLT-04 ``last_used_step``; Codex
production-20260921-2353 MFA-1). First run against a database in lane FIX-D2 (2026-09-29):
``user.anonymise`` needed revision 0073 (04 rev 1.86: the DB-13 grant of ``email`` /
``external_id`` under the DB-19 guard), and the workspaces beside the acting one take random
tenant codes (DG-TST-13).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.audit.chain import append_events
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_event,
    file_object,
    role,
    tenant_membership,
    user_session,
)
from erev_api.domain.platform import privacy
from erev_api.domain.platform.privacy import (
    ANONYMISE_ACTION,
    SHRED_ACTION,
    erased_display_name,
    erased_email,
)
from erev_api.enums import FilePurpose, MembershipStatus, UserStatus
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, enrolled, member, step_up
from support.rows import RowContext, insert_role_assignment, membership_row

USERS = "/api/v1/users"
FILES = "/api/v1/files"
PROBLEM_BASE = "https://erev.dev/problems/"
REASON = "Data subject request DSR-2026-014 received"


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    with tenant_session(_context(tomas.tenant_id)) as session:
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


def post_with_key(
    app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any], *, key: str
) -> HttpResponse:
    """A command under a caller-chosen ``Idempotency-Key``; the same key replays the stored response
    (DG-KRN-IDEM-04)."""
    headers = {**cookie_headers(actor.token, actor.csrf_token, key=False), "Idempotency-Key": key}
    return call(app, "POST", path, json=json, headers=headers)


def fresh_step_up(app: FastAPI, clock: FrozenClock, actor: Actor) -> Actor:
    """A TOTP step-up at a step later than any code the actor used so far: the frozen clock moves
    one TOTP step first, so the code is not a replay of the enrolment code (T-PLT-04
    ``last_used_step``; Codex production-20260921-2353 MFA-1, 2359 (4))."""
    clock.advance(totp.STEP)
    return step_up(app, clock, actor)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def user_row(user_id: UUID) -> Mapping[str, Any]:
    with identity_session(request_id="tests-privacy-user-row", user_id=user_id) as db:
        return dict(db.execute(select(app_user).where(app_user.c.id == user_id)).mappings().one())


def open_sessions(user_id: UUID) -> int:
    with identity_session(request_id="tests-privacy-sessions", user_id=user_id) as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(user_session)
                .where(user_session.c.user_id == user_id, user_session.c.ended_at.is_(None))
            ).scalar_one()
        )


def tenant_rows(tenant_id: UUID, statement: Any) -> list[Mapping[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def authored_by(tenant_id: UUID, user_id: UUID) -> int:
    """Audit events of the tenant whose pseudonymous ``actor_id`` is the person (REQ-SEC-007)."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.actor_id == user_id)
            ).scalar_one()
        )


def test_prv_07a_anonymise_user(app: FastAPI, world: World, clock: FrozenClock) -> None:
    """BUILD_SPEC SOP-5: with a fresh step-up the command returns 200; the identity is rewritten,
    credentials cleared, status DISABLED, every session ended and the membership REMOVED; the
    person's earlier audit events keep their pseudonymous ``actor_id``; the anonymise event holds
    the old e-mail only in the PRV-04 HMAC form; without a step-up 403 ``mfa-step-up-required``."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)  # Lena signs in and enrols: open sessions and audit events of hers
    assert open_sessions(lena.user_id) >= 1
    authored_before = authored_by(world.tenant_id, lena.user_id)
    clock.advance(timedelta(minutes=6))
    path = f"{USERS}/{lena.membership_id}/anonymise"

    stale = post(app, path, world.tomas, {"reason": REASON})
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    assert user_row(lena.user_id)["email"] == lena.email

    tomas = fresh_step_up(app, clock, world.tomas)
    erased = post(app, path, tomas, {"reason": REASON})
    assert erased.status_code == 200, erased.text
    assert erased.json()["status"] == MembershipStatus.REMOVED.value

    row = user_row(lena.user_id)
    assert row["display_name"] == erased_display_name(lena.user_id)
    assert row["email"] == erased_email(lena.user_id)
    assert row["password_hash"] is None and row["external_id"] is None
    assert row["status"] == UserStatus.DISABLED.value
    assert open_sessions(lena.user_id) == 0
    [membership] = tenant_rows(
        world.tenant_id,
        select(tenant_membership.c.status, tenant_membership.c.removed_at).where(
            tenant_membership.c.id == lena.membership_id
        ),
    )
    assert membership["status"] == MembershipStatus.REMOVED.value
    assert membership["removed_at"] == clock.now()

    authored_after = authored_by(world.tenant_id, lena.user_id)
    assert authored_after == authored_before, "REQ-SEC-007: pseudonymous actor_id references stay"
    [event] = tenant_rows(
        world.tenant_id,
        select(audit_event.c.before, audit_event.c.after, audit_event.c.actor_id).where(
            audit_event.c.action == ANONYMISE_ACTION, audit_event.c.object_id == lena.user_id
        ),
    )
    assert event["actor_id"] == world.tomas.member.user_id
    assert set(event["before"]["email"]) == {"hmac", "length"}, (
        "05 PRV-04 form, never the clear value"
    )
    assert event["before"]["email"]["length"] == len(lena.email)
    assert lena.email not in str(event["before"]) and lena.email not in str(event["after"])
    assert "display_name" not in event["before"]


def test_prv_07a_negative_paths(app: FastAPI, world: World, clock: FrozenClock) -> None:
    """An administrator cannot erase themselves (403 forbidden); a short reason is refused (422); an
    unknown membership is 404; a second erasure is 409 ``invalid-transition`` / ``PRV-07`` and
    changes nothing."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    tomas = fresh_step_up(app, clock, world.tomas)

    own = post(
        app, f"{USERS}/{world.tomas.member.membership_id}/anonymise", tomas, {"reason": REASON}
    )
    assert (own.status_code, slug(own)) == (403, "forbidden"), own.text

    short = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": "short"})
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    assert user_row(lena.user_id)["email"] == lena.email

    missing = post(app, f"{USERS}/{UUID(int=7)}/anonymise", tomas, {"reason": REASON})
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text

    first = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
    assert first.status_code == 200, first.text
    erased_at = user_row(lena.user_id)["updated_at"]
    clock.advance(timedelta(seconds=30))
    again = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert again.json()["errors"][0]["rule_id"] == "PRV-07"
    assert user_row(lena.user_id)["updated_at"] == erased_at


# ---- PRV-07 b: file.shred (NOT RUN until P1's FILES-SHRED-1 chain lands)


def upload_attachment(app: FastAPI, actor: Actor, content: bytes) -> Mapping[str, Any]:
    response = call(
        app,
        "POST",
        FILES,
        data={"purpose": FilePurpose.ATTACHMENT.value},
        files={"file": ("contract.pdf", content, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def file_row(tenant_id: UUID, file_id: UUID) -> Mapping[str, Any]:
    [row] = tenant_rows(tenant_id, select(file_object).where(file_object.c.id == file_id))
    return row


def sidecar_paths(app_settings: Settings, storage_key: str) -> tuple[Any, Any]:
    root = app_settings.file_root
    return root / f"{storage_key}.dek", root / f"{storage_key}.dek.shredded"


def test_prv_07b_shred_file(
    app: FastAPI, world: World, clock: FrozenClock, app_settings: Settings
) -> None:
    """BUILD_SPEC SOP-5: the shred removes the ``.dek`` sidecar, sets the four shredded columns,
    keeps the row and ``sha256``, writes one audit event naming the file id and SHA-256, and
    ``GET /files/{id}/content`` then returns 404 ``not-found`` with rule ``FILE_SHREDDED``."""
    uploaded = upload_attachment(app, world.tomas, b"%PDF-1.4 personal data inside")
    file_id = UUID(uploaded["id"])
    before = file_row(world.tenant_id, file_id)
    sidecar, marker = sidecar_paths(app_settings, str(before["storage_key"]))
    assert sidecar.exists() and not marker.exists()

    shredded = post(app, f"{FILES}/{file_id}/shred", world.tomas, {"reason": REASON})
    assert shredded.status_code == 200, shredded.text
    assert shredded.json()["shredded_at"] is not None

    after = file_row(world.tenant_id, file_id)
    assert after["sha256"] == before["sha256"] and after["storage_key"] == before["storage_key"]
    assert after["shredded_at"] == clock.now()
    assert after["shredded_by"] == world.tomas.member.user_id
    assert after["shredded_by_kind"] == "USER" and after["shred_reason"] == REASON
    assert not sidecar.exists() and marker.exists()
    [event] = tenant_rows(
        world.tenant_id,
        select(audit_event.c.detail, audit_event.c.object_id).where(
            audit_event.c.action == SHRED_ACTION, audit_event.c.object_id == file_id
        ),
    )
    assert event["detail"]["sha256"] == before["sha256"]
    assert event["detail"]["file_id"] == str(file_id)

    content = call(
        app,
        "GET",
        f"{FILES}/{file_id}/content",
        headers=cookie_headers(world.tomas.token, key=False),
    )
    assert (content.status_code, slug(content)) == (404, "not-found"), content.text
    assert content.json()["errors"][0]["rule_id"] == "FILE_SHREDDED"

    again = post(app, f"{FILES}/{file_id}/shred", world.tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert again.json()["errors"][0]["rule_id"] == "FILE_SHREDDED"


@pytest.mark.parametrize("hold", ["legal_hold", "retention_until"])
def test_shred_refused_under_retention(
    app: FastAPI, world: World, clock: FrozenClock, app_settings: Settings, hold: str
) -> None:
    """BUILD_SPEC SOP-5: with ``legal_hold`` true, or ``retention_until`` in the future, the command
    returns 409 ``invalid-transition`` with rule ``FILE_RETENTION_ACTIVE`` and changes nothing; the
    refusal is on the audit log as ``DENIED`` (04 rev 1.142; supervisor ruling R-86 (f))."""
    uploaded = upload_attachment(app, world.tomas, b"%PDF-1.4 held")
    file_id = UUID(uploaded["id"])
    values: dict[str, Any] = (
        {"legal_hold": True}
        if hold == "legal_hold"
        else {"retention_until": (clock.now() + timedelta(days=30)).date()}
    )
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(update(file_object).where(file_object.c.id == file_id).values(**values))
    before = file_row(world.tenant_id, file_id)
    sidecar, marker = sidecar_paths(app_settings, str(before["storage_key"]))

    refused = post(app, f"{FILES}/{file_id}/shred", world.tomas, {"reason": REASON})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["errors"][0]["rule_id"] == "FILE_RETENTION_ACTIVE"
    assert file_row(world.tenant_id, file_id) == before
    assert sidecar.exists() and not marker.exists()
    events = tenant_rows(
        world.tenant_id,
        select(audit_event.c.outcome, audit_event.c.detail).where(
            audit_event.c.action == SHRED_ACTION, audit_event.c.object_id == file_id
        ),
    )
    # no event of a shred; the refusal itself is the recorded outcome (R-86 (f))
    assert [(str(row["outcome"]), row["detail"]["rule_id"]) for row in events] == [
        ("DENIED", "FILE_RETENTION_ACTIVE")
    ]


def test_shred_plaintext_purpose_is_blocked(app: FastAPI, world: World, clock: FrozenClock) -> None:
    """A purpose outside ``policy.ENCRYPTED_PURPOSES`` has no sidecar to destroy; until the privacy
    owner rules on plaintext erasure (D-98 145 addendum (2)) the command refuses with rule
    ``PRV-06`` and changes nothing."""
    file_id = UUID(int=4242)
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            insert(file_object).values(
                tenant_id=world.tenant_id,
                id=file_id,
                sha256="0" * 64,
                size_bytes=12,
                media_type="text/csv",
                original_filename="report.csv",
                purpose=FilePurpose.REPORT_OUTPUT.value,
                storage_backend="local",
                storage_key=f"{world.tenant_id}/REPORT_OUTPUT/{'0' * 64}",
                created_at=clock.now(),
                created_by=world.tomas.member.user_id,
                created_by_kind="USER",
            )
        )
    refused = post(app, f"{FILES}/{file_id}/shred", world.tomas, {"reason": REASON})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["errors"][0]["rule_id"] == "PRV-06"
    assert file_row(world.tenant_id, file_id)["shredded_at"] is None


# ---- PRV-07 a completion across workspaces (Codex P8-PRV07-COMPLETE-1; NOT RUN: no database)


def second_workspace(
    keyring: FrozenClock | KeyRing, clock: FrozenClock, user_id: UUID, *, code: str | None = None
) -> tuple[UUID, UUID, Member]:
    """A second tenant where the same person is an ACTIVE member: (tenant id, the person's
    membership id there, that tenant's own administrator holding ``tenant_admin``). The tenant
    code is random unless given (DG-TST-13: ``committed_db`` rows are never cleaned up, so a fixed
    code collides on ``ux_tenant__code`` with the workspace an earlier test of the session left)."""
    assert isinstance(keyring, KeyRing)
    other_admin = member(keyring, clock, code=code, name="bea")
    tenant_id = other_admin.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=other_admin.membership_id,
            role_code="tenant_admin",
        )
        row = membership_row(
            RowContext(tenant_id=tenant_id, user_id=user_id), status=MembershipStatus.ACTIVE
        )
        session.execute(insert(tenant_membership).values(**row))
        membership_id = UUID(str(row["id"]))
    return tenant_id, membership_id, other_admin


def second_workspace_membership(
    keyring: KeyRing, clock: FrozenClock, user_id: UUID
) -> tuple[UUID, UUID]:
    tenant_id, membership_id, _admin = second_workspace(keyring, clock, user_id)
    return tenant_id, membership_id


def membership_status(tenant_id: UUID, membership_id: UUID) -> str:
    [row] = tenant_rows(
        tenant_id, select(tenant_membership.c.status).where(tenant_membership.c.id == membership_id)
    )
    return str(row["status"])


def events_in(tenant_id: UUID, action: str, object_id: UUID) -> int:
    return len(
        tenant_rows(
            tenant_id,
            select(audit_event.c.id).where(
                audit_event.c.action == action, audit_event.c.object_id == object_id
            ),
        )
    )


def erasure_removal_events(tenant_id: UUID, membership_id: UUID) -> int:
    return len(
        tenant_rows(
            tenant_id,
            select(audit_event.c.id).where(
                audit_event.c.action == "tenant_membership.remove",
                audit_event.c.object_id == membership_id,
                audit_event.c.detail.op("->>")("erasure") == "true",
            ),
        )
    )


def acting_event_detail(tenant_id: UUID, user_id: UUID) -> Mapping[str, Any]:
    [event] = tenant_rows(
        tenant_id,
        select(audit_event.c.detail).where(
            audit_event.c.action == ANONYMISE_ACTION, audit_event.c.object_id == user_id
        ),
    )
    return dict(event["detail"])


def test_prv_07a_multi_tenant_completion(
    app: FastAPI, world: World, clock: FrozenClock, keyring: KeyRing
) -> None:
    """PRV-07 a with a second workspace: the first run removes both memberships and records in the
    second workspace ONLY its membership removal (no global after-state before the identity change
    is durable); the acting tenant's event carries this request's counts and the workspaces still
    owed their completion event; the second run delivers exactly one ``app_user.anonymise`` event
    there (04 T-PLT-02); the third run is 409 and writes nothing."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    other_tenant, other_membership = second_workspace_membership(keyring, clock, lena.user_id)
    tomas = fresh_step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/anonymise"

    first = post(app, path, tomas, {"reason": REASON})
    assert first.status_code == 200, first.text
    progress = first.json()["erasure"]
    assert progress["status"] == "COMPLETION_PENDING"
    assert progress["other_workspaces_completion_pending"] == [str(other_tenant)]
    assert progress["other_workspaces_removed_now"] == [str(other_tenant)]
    assert progress["other_workspaces_completed_now"] == []
    assert "again" in progress["next_step"] and str(other_tenant) in progress["next_step"]
    assert membership_status(world.tenant_id, lena.membership_id) == MembershipStatus.REMOVED.value
    assert membership_status(other_tenant, other_membership) == MembershipStatus.REMOVED.value
    assert erasure_removal_events(other_tenant, other_membership) == 1
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 0, "no premature after-state"
    detail = acting_event_detail(world.tenant_id, lena.user_id)
    assert detail["other_memberships_removed"] == 1
    assert detail["other_memberships_already_removed"] == 0
    assert detail["other_memberships_skipped_removed"] == 0
    assert detail["other_tenants_completion_pending"] == [str(other_tenant)]
    assert detail["count_scope"].startswith("this request only")

    second = post(app, path, tomas, {"reason": REASON})
    assert second.status_code == 200, second.text
    done = second.json()["erasure"]
    assert (done["status"], done["next_step"]) == ("COMPLETE", None)
    assert done["other_workspaces_completed_now"] == [str(other_tenant)]
    assert done["other_workspaces_completion_pending"] == []
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 1
    [completion] = tenant_rows(
        other_tenant,
        select(audit_event.c.after).where(
            audit_event.c.action == ANONYMISE_ACTION, audit_event.c.object_id == lena.user_id
        ),
    )
    assert completion["after"]["status"] == UserStatus.DISABLED.value
    assert erasure_removal_events(other_tenant, other_membership) == 1, "no duplicate removal"

    third = post(app, path, tomas, {"reason": REASON})
    assert (third.status_code, slug(third)) == (409, "invalid-transition"), third.text
    assert third.json()["errors"][0]["rule_id"] == "PRV-07"
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 1
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 1


def test_prv_07a_secondary_failure_then_retry(
    app: FastAPI,
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure while removing the membership in the second workspace returns the problem, erases
    nothing in the acting tenant and stores no success; the retry completes the removal; the
    completion run delivers the second workspace's event once; no workspace holds a duplicate."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    other_tenant, other_membership = second_workspace_membership(keyring, clock, lena.user_id)
    tomas = fresh_step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/anonymise"
    real = privacy._remove_membership_in_tenant
    calls: list[UUID] = []

    def failing_once(erasure: Any, tenant_id: UUID, membership_id: UUID) -> bool:
        calls.append(tenant_id)
        if len(calls) == 1:
            raise RuntimeError("simulated failure before the second workspace's transaction")
        return bool(real(erasure, tenant_id, membership_id))

    monkeypatch.setattr(privacy, "_remove_membership_in_tenant", failing_once)
    failed = post(app, path, tomas, {"reason": REASON})
    assert failed.status_code >= 500, failed.text
    assert user_row(lena.user_id)["email"] == lena.email, "the identity is untouched"
    assert membership_status(world.tenant_id, lena.membership_id) == MembershipStatus.ACTIVE.value
    assert membership_status(other_tenant, other_membership) == MembershipStatus.ACTIVE.value
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 0

    retried = post(app, path, tomas, {"reason": REASON})
    assert retried.status_code == 200, retried.text
    assert calls == [other_tenant, other_tenant]
    assert user_row(lena.user_id)["email"] == erased_email(lena.user_id)
    assert membership_status(world.tenant_id, lena.membership_id) == MembershipStatus.REMOVED.value
    assert membership_status(other_tenant, other_membership) == MembershipStatus.REMOVED.value
    assert erasure_removal_events(other_tenant, other_membership) == 1
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 0
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 1

    completion = post(app, path, tomas, {"reason": REASON})
    assert completion.status_code == 200, completion.text
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 1
    again = post(app, path, tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert events_in(other_tenant, ANONYMISE_ACTION, lena.user_id) == 1
    assert erasure_removal_events(other_tenant, other_membership) == 1


def test_prv_07a_three_tenant_partial_completion(
    app: FastAPI,
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P8-PRV07-COMPLETE-1 residual: B commits its removal, C enters its transaction and
    fails. At that point B's chain holds its removal and NO global after-state, C and the identity
    are untouched, the acting tenant has no event and no success is stored. The retry skips B
    (enumerated REMOVED, counted as skipped, no duplicate event), completes C and erases the
    identity; the completion run then delivers one ``app_user.anonymise`` event to B and to C; a
    further run is 409."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    tenant_b, membership_b = second_workspace_membership(keyring, clock, lena.user_id)
    other_admin = member(keyring, clock, name="cai")  # a random code (DG-TST-13)
    tenant_c = other_admin.tenant_id
    with tenant_session(_context(tenant_c)) as session:
        row_c = membership_row(
            RowContext(tenant_id=tenant_c, user_id=lena.user_id), status=MembershipStatus.ACTIVE
        )
        session.execute(insert(tenant_membership).values(**row_c))
        membership_c = UUID(str(row_c["id"]))
    tomas = fresh_step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/anonymise"
    failures: list[UUID] = []

    def fail_inside_c(db: Any, *, tenant_id: UUID, keyring: Any, events: Any) -> int:
        if tenant_id == tenant_c and not failures:
            failures.append(tenant_id)
            raise RuntimeError("simulated audit-chain failure inside C's transaction")
        return int(append_events(db, tenant_id=tenant_id, keyring=keyring, events=events))

    monkeypatch.setattr(privacy, "append_events", fail_inside_c)
    failed = post(app, path, tomas, {"reason": REASON})
    assert failed.status_code >= 500, failed.text
    # B really completed; C rolled back; the identity and the acting tenant are untouched.
    assert membership_status(tenant_b, membership_b) == MembershipStatus.REMOVED.value
    assert erasure_removal_events(tenant_b, membership_b) == 1
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 0, "no false global state in B"
    assert membership_status(tenant_c, membership_c) == MembershipStatus.ACTIVE.value
    assert erasure_removal_events(tenant_c, membership_c) == 0
    assert user_row(lena.user_id)["email"] == lena.email
    assert membership_status(world.tenant_id, lena.membership_id) == MembershipStatus.ACTIVE.value
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 0

    retried = post(app, path, tomas, {"reason": REASON})
    assert retried.status_code == 200, retried.text
    assert erasure_removal_events(tenant_b, membership_b) == 1, "B skipped, not re-audited"
    assert membership_status(tenant_c, membership_c) == MembershipStatus.REMOVED.value
    assert erasure_removal_events(tenant_c, membership_c) == 1
    assert user_row(lena.user_id)["email"] == erased_email(lena.user_id)
    detail = acting_event_detail(world.tenant_id, lena.user_id)
    assert detail["other_memberships_removed"] == 1, "C only"
    assert detail["other_memberships_skipped_removed"] == 1, "B, enumerated REMOVED"
    assert detail["other_memberships_already_removed"] == 0
    assert sorted(detail["other_tenants_completion_pending"]) == sorted(
        [str(tenant_b), str(tenant_c)]
    )
    progress = retried.json()["erasure"]
    assert progress["status"] == "COMPLETION_PENDING"
    assert sorted(progress["other_workspaces_completion_pending"]) == sorted(
        [str(tenant_b), str(tenant_c)]
    )
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 0
    assert events_in(tenant_c, ANONYMISE_ACTION, lena.user_id) == 0

    completion = post(app, path, tomas, {"reason": REASON})
    assert completion.status_code == 200, completion.text
    for tenant_id, membership_id in ((tenant_b, membership_b), (tenant_c, membership_c)):
        assert events_in(tenant_id, ANONYMISE_ACTION, lena.user_id) == 1, tenant_id
        assert erasure_removal_events(tenant_id, membership_id) == 1, tenant_id
    done = post(app, path, tomas, {"reason": REASON})
    assert (done.status_code, slug(done)) == (409, "invalid-transition"), done.text
    for tenant_id in (tenant_b, tenant_c):
        assert events_in(tenant_id, ANONYMISE_ACTION, lena.user_id) == 1, tenant_id
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 1


def test_prv_07a_alternate_workspace_completion(
    app: FastAPI, world: World, clock: FrozenClock, keyring: KeyRing
) -> None:
    """Codex production-20260921-2359 §1–§2: A erases an A / B person; B is owed its completion
    event. B's own administrator continues the erasure THROUGH THE PERSON'S REMOVED MEMBERSHIP IN
    B with a fresh step-up and a NEW Idempotency-Key: the owed set is derived from the chains, not
    from the caller, so the 200 delivers B's ``app_user.anonymise`` event and reports COMPLETE;
    the SAME key replays the initial response (``Idempotent-Replay: true``) without a second event;
    a further new key answers 409 ``PRV-07``. Authorization is B's own ``user.manage`` and
    step-up — nothing is widened."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    tenant_b, membership_b, bea = second_workspace(keyring, clock, lena.user_id)
    tomas = fresh_step_up(app, clock, world.tomas)
    first = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
    assert first.status_code == 200, first.text
    assert first.json()["erasure"]["other_workspaces_completion_pending"] == [str(tenant_b)]
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 0

    admin_b = fresh_step_up(app, clock, enrolled(app, clock, bea))
    path_b = f"{USERS}/{membership_b}/anonymise"
    key = f"k-alt-{uuid4()}"
    continued = post_with_key(app, path_b, admin_b, {"reason": REASON}, key=key)
    assert continued.status_code == 200, continued.text
    progress = continued.json()["erasure"]
    assert (progress["status"], progress["next_step"]) == ("COMPLETE", None)
    assert progress["other_workspaces_completed_now"] == [str(tenant_b)]
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 1
    assert events_in(world.tenant_id, ANONYMISE_ACTION, lena.user_id) == 1, "A is never owed"
    assert erasure_removal_events(tenant_b, membership_b) == 1

    replayed = post_with_key(app, path_b, admin_b, {"reason": REASON}, key=key)
    assert replayed.status_code == 200, replayed.text
    assert replayed.headers.get("Idempotent-Replay") == "true"
    assert replayed.json() == continued.json()
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 1, "a replay writes nothing"

    again = post(app, path_b, admin_b, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert again.json()["errors"][0]["rule_id"] == "PRV-07"
    assert events_in(tenant_b, ANONYMISE_ACTION, lena.user_id) == 1


# --- item SBX-COPY-OPEN-INVITATION-1, its second half (PRD SM-13 rev 1.201; 04 T-PLT-07 rev
# 1.293): a removed person is invited again on the same membership — an erased one is not ---


def test_an_erased_person_is_not_invited_again_on_the_erased_membership(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The erasure of 05 PRV-07 a leaves the identity DISABLED under the address
    ``erased+<user id>@invalid.erev`` — which the members list shows for it — and its membership
    REMOVED. That membership is not invited again: the invitation of the erased address answers
    422 as it did before a removed person could be invited again, and nothing changes. The
    person's own address belongs to nobody now: inviting it makes a new identity and a new
    membership.

    Fail-first (the invitation of a removed person without this rule): 201 — the erased
    identity's membership was INVITED again, with a link nobody can open."""
    lena = colleague(world.tenant_id, "lena")
    tomas = fresh_step_up(app, clock, world.tomas)
    erased = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
    assert erased.status_code == 200, erased.text
    [viewer] = tenant_rows(world.tenant_id, select(role.c.id).where(role.c.code == "viewer"))

    def invitation(email: str) -> dict[str, Any]:
        return {
            "email": email,
            "display_name": "Lena Fischer",
            "roles": [{"role_id": str(viewer["id"]), "is_all_entities": True, "entity_codes": []}],
        }

    def of_lena() -> tuple[str, str]:
        [membership] = tenant_rows(
            world.tenant_id,
            select(tenant_membership.c.status).where(tenant_membership.c.id == lena.membership_id),
        )
        return str(membership["status"]), str(user_row(lena.user_id)["status"])

    assert of_lena() == (MembershipStatus.REMOVED.value, UserStatus.DISABLED.value)
    refused = post(app, USERS, tomas, invitation(erased_email(lena.user_id)))
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in refused.json()["errors"]] == [
        ("email", "T-PLT-07")
    ]
    assert of_lena() == (MembershipStatus.REMOVED.value, UserStatus.DISABLED.value)

    anew = post(app, USERS, tomas, invitation(lena.email))
    assert anew.status_code == 201, anew.text
    assert anew.json()["id"] != str(lena.membership_id)
    assert (anew.json()["status"], anew.json()["email"]) == ("INVITED", lena.email)
    assert of_lena() == (MembershipStatus.REMOVED.value, UserStatus.DISABLED.value)


def test_erasure_between_invitation_read_and_membership_lock_refuses_stale_identity(
    app: FastAPI,
    world: World,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed erasure cannot be undone by an invitation holding a pre-erasure read."""
    from erev_api.db.tables import outbox_message
    from erev_api.domain.platform import users

    lena = colleague(world.tenant_id, "lena")
    tomas = fresh_step_up(app, clock, world.tomas)
    removed = post(app, f"{USERS}/{lena.membership_id}/remove", tomas, {"reason": REASON})
    assert removed.status_code == 200, removed.text
    [viewer] = tenant_rows(world.tenant_id, select(role.c.id).where(role.c.code == "viewer"))
    real_lock = users._lock_membership
    erased = False
    before_outbox = tenant_rows(world.tenant_id, select(outbox_message.c.id))

    def erase_then_lock(session: Any, membership_id: UUID) -> Mapping[str, Any]:
        nonlocal erased
        if not erased and membership_id == lena.membership_id:
            erased = True
            result = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
            assert result.status_code == 200, result.text
        return real_lock(session, membership_id)

    monkeypatch.setattr(users, "_lock_membership", erase_then_lock)
    response = post(
        app,
        USERS,
        tomas,
        {
            "email": lena.email,
            "display_name": "Lena Fischer",
            "roles": [{"role_id": str(viewer["id"]), "is_all_entities": True, "entity_codes": []}],
        },
    )
    assert erased
    assert response.status_code == 422, response.text
    assert slug(response) == "validation-failed"
    assert user_row(lena.user_id)["status"] == UserStatus.DISABLED
    [membership] = tenant_rows(
        world.tenant_id,
        select(tenant_membership).where(tenant_membership.c.id == lena.membership_id),
    )
    assert membership["status"] == MembershipStatus.REMOVED
    assert tenant_rows(world.tenant_id, select(outbox_message.c.id)) == before_outbox
    assert not tenant_rows(
        world.tenant_id,
        select(audit_event.c.id).where(
            audit_event.c.object_id == lena.membership_id,
            audit_event.c.action == users.INVITE_ACTION,
        ),
    )


def test_erased_identity_cannot_gain_a_membership_in_another_workspace(
    app: FastAPI,
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
) -> None:
    """The new-membership branch also refuses an existing erased global identity."""
    from erev_api.db.tables import outbox_message

    lena = colleague(world.tenant_id, "lena")
    tomas = fresh_step_up(app, clock, world.tomas)
    erased = post(app, f"{USERS}/{lena.membership_id}/anonymise", tomas, {"reason": REASON})
    assert erased.status_code == 200, erased.text
    other_admin = member(keyring, clock)
    with tenant_session(_context(other_admin.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=other_admin.tenant_id,
            membership_id=other_admin.membership_id,
            role_code="tenant_admin",
        )
    actor = enrolled(app, clock, other_admin)
    [viewer] = tenant_rows(other_admin.tenant_id, select(role.c.id).where(role.c.code == "viewer"))
    before = tenant_rows(other_admin.tenant_id, select(outbox_message.c.id))
    response = post(
        app,
        USERS,
        actor,
        {
            "email": erased_email(lena.user_id),
            "display_name": "Lena Fischer",
            "roles": [{"role_id": str(viewer["id"]), "is_all_entities": True, "entity_codes": []}],
        },
    )
    assert response.status_code == 422, response.text
    assert not tenant_rows(
        other_admin.tenant_id,
        select(tenant_membership.c.id).where(tenant_membership.c.user_id == lena.user_id),
    )
    assert tenant_rows(other_admin.tenant_id, select(outbox_message.c.id)) == before
