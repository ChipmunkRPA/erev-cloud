"""API-R-03 me: API-S-Me and display preferences (04 §15.3 API-R-03, §16.12 API-S-Me and
``PATCH /me/preferences``, T-PLT-02 ``preferences``, E-123, E-124; SCREENS_B OQ-B-20, OQ-B-24;
BUILD_SPEC PLF-21, BS1-D-32).

The app runs its lifespan startup, so ``GET /me`` returns the release row the process stamped. Lena
holds the Tenant Admin role of her workspace, is enrolled in MFA and belongs to two more workspaces
she never opened, plus one she was removed from.
"""

from __future__ import annotations

import asyncio
import secrets
from uuid import UUID

import pytest
from alembic.script import ScriptDirectory
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.release import EngineRelease
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import tenant_membership
from erev_api.enums import MembershipStatus, NotificationKind, TenantKind
from erev_api.events.notifications import notify
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from erev_engine import ENGINE_VERSION
from fastapi import FastAPI
from sqlalchemy import update
from support.db import TestDatabase, alembic_config
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.principals import Member, cookie_headers, enrolled, member, sign_in, workspace
from support.rows import insert_active_membership, insert_role_assignment

ME = "/api/v1/me"
PREFERENCES = "/api/v1/me/preferences"
PROBLEM_BASE = "https://erev.dev/problems/"
DEFAULT_PREFERENCES = {
    "format_locale": "en-US",
    "theme": "SYSTEM",
    "density": "COMFORTABLE",
    "shortcuts_enabled": True,
    "tour_completed": None,
}


async def _start(application: FastAPI) -> None:
    """Run the app's startup and shutdown as uvicorn does; startup stamps the release (REL-03)."""
    async with application.router.lifespan_context(application):
        pass


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)
    asyncio.run(_start(application))
    return application


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def _other_workspace(
    keyring: KeyRing, clock: FrozenClock, user_id: UUID, prefix: str, *, removed: bool = False
) -> str:
    """An ACTIVE (or REMOVED) membership of ``user_id`` in a fresh workspace coded ``prefix-…``."""
    code = f"{prefix}-{secrets.token_hex(6)}"
    result = tenant_factory(
        keyring=keyring, clock=clock, code=code, admin_email=f"admin@{code}.test"
    )
    tenant_id = tenant_id_of(result)
    with tenant_session(_context(tenant_id)) as session:
        membership_id = insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
        if removed:
            session.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == membership_id)
                .values(
                    status=MembershipStatus.REMOVED.value,
                    removed_at=clock.now(),
                    updated_by_kind="SYSTEM",
                )
            )
    return code


def _notify(lena: Member, *, clock: FrozenClock, keyring: KeyRing, settings: Settings) -> None:
    ctx = RequestContext(
        principal=system_principal(lena.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-me",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        notify(
            uow,
            recipient_membership_ids=[lena.membership_id],
            kind=NotificationKind.ITEM_APPROVED,
            title="Approved: Grant the revenue reviewer role",
        )
        uow.commit()


def test_api_s_me_shape(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    lena = member(keyring, clock)
    own_code = lena.email.split("@", 1)[1].removesuffix(".test")
    with tenant_session(_context(lena.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=lena.tenant_id,
            membership_id=lena.membership_id,
            role_code="tenant_admin",
        )
    later = _other_workspace(keyring, clock, lena.user_id, "b")
    earlier = _other_workspace(keyring, clock, lena.user_id, "a")
    _other_workspace(keyring, clock, lena.user_id, "c", removed=True)
    actor = enrolled(app, clock, lena)
    _notify(lena, clock=clock, keyring=keyring, settings=app_settings)

    response = call(app, "GET", ME, headers=cookie_headers(actor.token, key=False))
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == [
        "user",
        "memberships",
        "active_membership_id",
        "permissions",
        "entity_scope",
        "permission_scopes",
        "mfa",
        "preferences",
        "tenant_settings",
        "engine_release",
        "unread_notification_count",
    ]
    user = body["user"]
    assert (user["id"], user["email"], user["status"]) == (str(lena.user_id), lena.email, "ACTIVE")

    # Opened last first, then never-opened memberships by tenant code; REMOVED is left out.
    memberships = body["memberships"]
    assert [item["tenant"]["code"] for item in memberships] == [own_code, earlier, later]
    own, *others = memberships
    assert own["membership_id"] == str(lena.membership_id)
    assert own["tenant"] == {
        "id": str(lena.tenant_id),
        "code": own_code,
        "display_name": f"Tenant {own_code}",
        "kind": "production",
        "is_demo": False,
        # 04 §16.12 rev 1.125 (BUILD_SPEC SNP-3, 05 SBX-07): the workspace's E-101 status and,
        # for a sandbox, where and as of when it was copied
        "status": "ACTIVE",
        "source_tenant_id": None,
        "source_known_at": None,
    }
    assert (own["status"], own["last_opened_at"] is not None) == ("ACTIVE", True)
    assert [(item["status"], item["last_opened_at"]) for item in others] == [("ACTIVE", None)] * 2

    assert body["active_membership_id"] == str(lena.membership_id)
    assert body["permissions"] == sorted(DEFAULT_ROLES["tenant_admin"])
    assert body["entity_scope"] == "*"
    # ME-SCOPE-PER-PERMISSION-1 (04 §16.12): each permission with the entities it is held for
    assert body["permission_scopes"] == dict.fromkeys(sorted(DEFAULT_ROLES["tenant_admin"]), "*")
    assert body["mfa"]["enrolled"] is True
    assert body["mfa"]["verified_at"] is not None
    assert body["preferences"] == DEFAULT_PREFERENCES
    assert body["tenant_settings"] == {
        "negative_number_style": "PARENTHESES",
        "default_locale": "en-US",
        "ai_enabled": False,
    }
    release = app.state.engine_release
    assert isinstance(release, EngineRelease)
    # 0058: the F-ADM head (04 §18 rule 9; assigned 2026-09-20) on P4's 0057 (SOP-1, T-PLT-39),
    # above F-LMG's 0056 and P5's 0055.
    # Lane F-CLO CLO-6 revision (T-CLS-06 period_lock_id write-once): 0059 on 0058, assigned at
    # merge prep 2026-09-20.
    # Lane P2 revision (T-PLT-06 key attribution): 0061 on ENG-C1b's 0060, landed at merge prep.
    # Lane F-SNP revisions (T-PLT-34 tenant_snapshot; retention parameter seed): 0062 / 0063 on
    # P2's 0061, assigned at merge prep 2026-09-20.
    # Lane ENG-C6 revision (T-SL-12 subledger_line_event): 0064 on F-SNP's 0063, assigned at merge
    # prep 2026-09-20.
    # Lane F-RPS revision 0065 (report_run.source_binding) on ENG-C6's 0064; lane F-SNP revision
    # 0066 (T-PLT-47 registry_parameter_correction) on 0065; lane F-LMG revision 0067 (T-MIG-04 /
    # T-MIG-05 durable capture; 04 rev 1.60) on 0066 — re-pointed from 0065 at the single main merge
    # after F-SNP landed (main 38ee8793 → fe8e85df, 2026-09-21; the ENG-C6 0064 precedent). Lane
    # F-CTR revision 0068 (CTR-17 T-CON-06 modification; 04 rev 1.70; D-98 140) on 0067; F-CTR
    # revision 0069 (D-98 candidate 143 GUARD-TRN-1 re-render of six transition functions) on 0068;
    # F-CTR revision 0070 (D-98 candidate 143 AMENDMENT 1: the contract (DRAFT, ACTIVE) pair,
    # tg_contract__transition re-rendered) on 0069; F-LMG 0071 (migration_ssp_replay_subject) on
    # 0070; F-ADM 0072 (DIN-12 integrations) on 0071.
    # MIG-PIN-2 (2026-09-22): this assertion checks that the release records the RUNNING schema,
    # not which revision is newest — the expected value is the Alembic script directory's head, so
    # a new migration (P8's 0073 next) cannot re-break it; the literal head pin lives in
    # tests/pg/test_migrations.py::test_single_head (F-LMG-MIG-PIN-1).
    assert (
        release.schema_revision == ScriptDirectory.from_config(alembic_config()).get_current_head()
    )
    assert body["engine_release"] == {
        "engine_version": ENGINE_VERSION,
        "build_sha": release.build_sha,
        "schema_revision": release.schema_revision,
    }
    assert body["unread_notification_count"] == 1


def test_d83_api_s_me_without_workspace(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """D-83: a session that opened no workspace reads API-S-Me with 200 and its memberships."""
    lena = member(keyring, clock)
    own_code = lena.email.split("@", 1)[1].removesuffix(".test")
    other = _other_workspace(keyring, clock, lena.user_id, "b")
    _other_workspace(keyring, clock, lena.user_id, "c", removed=True)
    signed = sign_in(app, lena.email)
    assert signed.body["active_tenant"] is None

    response = call(app, "GET", ME, headers=cookie_headers(signed.token, key=False))
    assert response.status_code == 200, response.text
    assert "X-Erev-Tenant-Kind" not in response.headers
    body = response.json()
    assert body["user"] == {
        "id": str(lena.user_id),
        "email": lena.email,
        "display_name": lena.email,
        "status": "ACTIVE",
    }
    # Neither workspace was opened, so both order by tenant code; REMOVED is left out.
    memberships = body["memberships"]
    assert [item["tenant"]["code"] for item in memberships] == [other, own_code]
    own = memberships[1]
    assert (own["membership_id"], own["status"], own["last_opened_at"]) == (
        str(lena.membership_id),
        "ACTIVE",
        None,
    )
    assert own["tenant"] == {
        "id": str(lena.tenant_id),
        "code": own_code,
        "display_name": f"Tenant {own_code}",
        "kind": "production",
        "is_demo": False,
        # 04 §16.12 rev 1.125 (BUILD_SPEC SNP-3, 05 SBX-07): the workspace's E-101 status and,
        # for a sandbox, where and as of when it was copied
        "status": "ACTIVE",
        "source_tenant_id": None,
        "source_known_at": None,
    }
    assert body["active_membership_id"] is None
    assert body["permissions"] == []
    assert body["entity_scope"] == []
    assert body["permission_scopes"] == {}
    assert body["mfa"] == {"enrolled": False, "verified_at": None}
    assert body["preferences"] == DEFAULT_PREFERENCES
    assert body["tenant_settings"] == {
        "negative_number_style": "PARENTHESES",
        "default_locale": "en-US",
        "ai_enabled": False,
    }
    release = app.state.engine_release
    assert isinstance(release, EngineRelease)
    assert body["engine_release"] == {
        "engine_version": ENGINE_VERSION,
        "build_sha": release.build_sha,
        "schema_revision": release.schema_revision,
    }
    assert body["unread_notification_count"] == 0

    # Without a session, 401 as before; tenant reads of the caller still need a workspace.
    assert (call(app, "GET", ME).status_code, slug(call(app, "GET", ME))) == (
        401,
        "unauthenticated",
    )
    notifications = call(
        app, "GET", "/api/v1/me/notifications", headers=cookie_headers(signed.token, key=False)
    )
    assert (notifications.status_code, slug(notifications)) == (401, "unauthenticated")


def test_patch_preferences(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    actor = workspace(app, lena, sign_in(app, lena.email))

    def patch(json: dict[str, object]) -> HttpResponse:
        return call(
            app,
            "PATCH",
            PREFERENCES,
            json=json,
            headers=cookie_headers(actor.token, actor.csrf_token),
        )

    patched = patch({"theme": "DARK", "density": "COMPACT"})
    assert patched.status_code == 200, patched.text
    assert patched.json() == {
        "preferences": {**DEFAULT_PREFERENCES, "theme": "DARK", "density": "COMPACT"}
    }

    tour = {"variant": "production", "completed_at": "2026-09-12T12:30:00Z"}
    completed = patch({"format_locale": "de-DE", "tour_completed": tour})
    assert completed.status_code == 200, completed.text
    assert completed.json()["preferences"] == {
        **DEFAULT_PREFERENCES,
        "theme": "DARK",
        "density": "COMPACT",
        "format_locale": "de-DE",
        "tour_completed": tour,
    }

    # A null member returns to its default: the workspace locale, no completed tour.
    reset = patch({"format_locale": None, "tour_completed": None})
    assert reset.status_code == 200, reset.text
    assert reset.json()["preferences"] == {
        **DEFAULT_PREFERENCES,
        "theme": "DARK",
        "density": "COMPACT",
    }
    profile = call(app, "GET", ME, headers=cookie_headers(actor.token, key=False))
    assert profile.status_code == 200, profile.text
    assert profile.json()["preferences"] == reset.json()["preferences"]

    unknown = patch({"colour": "red"})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert [error["field"] for error in unknown.json()["errors"]] == ["colour"]
    wrong = patch({"theme": "SEPIA"})
    assert (wrong.status_code, slug(wrong)) == (422, "validation-failed"), wrong.text
