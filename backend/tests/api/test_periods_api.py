"""API-R-18 ``open`` during setup (04 §15.3 API-R-18, §16.8, T-PLT-01 ``setup_completed_at``;
SCREENS_B OQ-B-19; PRD ACT-44; BUILD_SPEC RFD-2).

Lena holds Tenant Admin, which carries ``settings.manage`` (MFA-gated) and not ``period.close``
(docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, api_token, audit_event, tenant
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import enrolled, member
from support.reference import PERIODS, assign, calendar, entity, periods, post, slug
from support.rows import api_client_values


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_open_permission_while_setup_incomplete(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    assert "period.close" not in DEFAULT_ROLES["tenant_admin"]
    assert "settings.manage" in DEFAULT_ROLES["tenant_admin"]
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    calendar_id = calendar(app, lena)
    entity(app, lena, code="AVM-US", calendar_id=calendar_id)
    january, february = periods(app, lena, entity="AVM-US")[:2]

    # tenant.setup_completed_at IS NULL: settings.manage opens a period.
    opened = post(app, f"{PERIODS}/{january['id']}/open", lena, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text
    assert (opened.json()["state"], opened.json()["period"]["period_key"]) == ("open", "FY2026-P01")

    context = DbContext(tenant_id=lena_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == lena_member.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    refused = post(app, f"{PERIODS}/{february['id']}/open", lena, {}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    with tenant_session(context) as session:
        denied = session.execute(
            select(audit_event.c.object_id, audit_event.c.detail).where(
                audit_event.c.action == "period.open", audit_event.c.outcome == "DENIED"
            )
        ).all()
    assert [(row.object_id, row.detail["permissions"]) for row in denied] == [
        (UUID(february["id"]), ["period.close"])
    ]
    assert [item["id"] for item in periods(app, lena, entity="AVM-US", state="open")] == [
        january["id"]
    ]


def test_a_period_is_opened_only_with_the_permission_for_its_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security finding S18 (supervisor ruling R-28; 03 REQ-PLT-012): ``POST /periods/{id}/open``
    needs ``period.close`` FOR the period's entity. Pat is Revenue Accountant for AVM-UK and
    Viewer for AVM-US — both roles granted through the product for named entities — so she sees
    the periods of AVM-US and may not open them: 404, as for a period she does not see. Before:
    200 — the command asked for the permission on any entity."""
    from support.principals import colleague
    from support.reference import get

    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    calendar_id = calendar(app, lena)
    for code in ("AVM-US", "AVM-UK"):
        entity(app, lena, code=code, calendar_id=calendar_id)
    pat_member = colleague(lena_member.tenant_id, "pat")
    roles = {
        str(item["code"]): str(item["id"])
        for item in get(app, "/api/v1/roles", lena, {"limit": 200}).json()["items"]
    }
    for role_code, entity_code in (("revenue_accountant", "AVM-UK"), ("viewer", "AVM-US")):
        granted = post(
            app,
            "/api/v1/role-assignments",
            lena,
            {
                "membership_id": str(pat_member.membership_id),
                "role_id": roles[role_code],
                "is_all_entities": False,
                "entity_codes": [entity_code],
            },
        )
        assert granted.status_code == 201, granted.text
        assert granted.json()["status"] == "ACTIVE", granted.text  # setup: AUTO-BOOTSTRAP
    context = DbContext(tenant_id=lena_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == lena_member.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    pat = enrolled(app, clock, pat_member)
    (us_january,) = periods(app, pat, entity="AVM-US")[:1]
    (uk_january,) = periods(app, pat, entity="AVM-UK")[:1]
    assert (us_january["state"], uk_january["state"]) == ("future", "future")

    refused = post(app, f"{PERIODS}/{us_january['id']}/open", pat, {}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert [item["state"] for item in periods(app, pat, entity="AVM-US")[:1]] == ["future"]
    opened = post(app, f"{PERIODS}/{uk_january['id']}/open", pat, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text
    assert opened.json()["state"] == "open"


def test_an_api_client_opens_the_periods_of_its_own_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The entity guard of ``POST /periods/{id}/open`` and a principal that is no member (the
    table of principals against the guards, from the repair of SECFIX-SCOPE item 1: this cell was
    stated from the code). An API client holds each of its scopes for its own entity scope and
    for no other (``api_client_grants``), and ``period.close`` needs no second factor. A client
    of AVM-UK opens a period of AVM-UK. A period of AVM-US is no row of its session: 404, before
    the guard is asked and as before the guard existed, and the period stays ``future``."""
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    calendar_id = calendar(app, lena)
    ids = {
        code: UUID(str(entity(app, lena, code=code, calendar_id=calendar_id)["id"]))
        for code in ("AVM-US", "AVM-UK")
    }
    (us_january,) = periods(app, lena, entity="AVM-US")[:1]
    (uk_january,) = periods(app, lena, entity="AVM-UK")[:1]
    assert (us_january["state"], uk_january["state"]) == ("future", "future")

    # world setup by rows (04 T-PLT-15, T-PLT-16): POST /api-clients takes no entity code yet
    tenant_id = lena_member.tenant_id
    token = f"erevt_{tenant_id.hex}_{secrets.token_urlsafe(32)}"
    client = api_client_values(
        tenant_id,
        name="svc-close-uk",
        scopes=["period.close"],
        is_all_entities=False,
        entity_ids=[ids["AVM-UK"]],
    )
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(tenant).where(tenant.c.id == tenant_id).values(setup_completed_at=clock.now())
        )
        session.execute(insert(api_client).values(**client))
        session.execute(
            insert(api_token).values(
                tenant_id=tenant_id,
                id=new_id(),
                api_client_id=client["id"],
                token_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
                scopes=["period.close"],
                issued_at=clock.now(),
                expires_at=clock.now() + timedelta(hours=1),
            )
        )

    def opened_by_the_client(period_id: str) -> HttpResponse:
        return call(
            app,
            "POST",
            f"{PERIODS}/{period_id}/open",
            json={},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"k-{secrets.token_hex(8)}",
                "If-Match": '"r1"',
            },
        )

    refused = opened_by_the_client(us_january["id"])
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert [item["state"] for item in periods(app, lena, entity="AVM-US")[:1]] == ["future"]
    opened = opened_by_the_client(uk_january["id"])
    assert opened.status_code == 200, opened.text
    assert (opened.json()["state"], opened.json()["entity"]["code"]) == ("open", "AVM-UK")
