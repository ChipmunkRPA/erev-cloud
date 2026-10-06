"""API-R-17 entity scope and entity changes (04 §15.1 API-C-03, §15.3 API-R-17, API-R-18, RLS-TE;
03 REQ-PLT-012, REQ-REF-001; BUILD_SPEC RFD-2, BS3-D-07).

Maya holds Revenue Accountant for all entities; Omar holds Revenue Accountant for AVM-US only.
"""

from __future__ import annotations

import uuid

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.principals import colleague, member
from support.reference import (
    ENTITIES,
    PERIODS,
    calendar,
    entity,
    get,
    holding,
    patch,
    periods,
    post,
    slug,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_entity_scope_returns_404_outside_scope(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    us = entity(app, maya, code="AVM-US", calendar_id=calendar_id)
    de = entity(
        app,
        maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
        country_code="DE",
    )
    de_state = periods(app, maya, entity="AVM-DE")[0]
    omar = holding(
        app,
        colleague(maya_member.tenant_id, "omar"),
        "revenue_accountant",
        entity_ids=[uuid.UUID(us["id"])],
    )

    listed = get(app, ENTITIES, omar)
    assert listed.status_code == 200, listed.text
    assert [item["code"] for item in listed.json()["items"]] == ["AVM-US"]
    for path in (f"{ENTITIES}/{de['id']}", f"{PERIODS}/{de_state['id']}"):
        hidden = get(app, path, omar)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    assert get(app, f"{ENTITIES}/{us['id']}", omar).status_code == 200
    # Period lists and commands stay inside the scope as well.
    assert {item["entity"]["code"] for item in periods(app, omar)} == {"AVM-US"}
    assert periods(app, omar, entity="AVM-DE") == []
    blocked = post(app, f"{PERIODS}/{de_state['id']}/open", omar, {}, if_match='"r1"')
    assert (blocked.status_code, slug(blocked)) == (404, "not-found"), blocked.text
    renamed = patch(app, f"{ENTITIES}/{de['id']}", omar, {"name": "Renamed"}, if_match='"r1"')
    assert (renamed.status_code, slug(renamed)) == (404, "not-found"), renamed.text
    # Maya still sees both entities.
    assert [item["code"] for item in get(app, ENTITIES, maya).json()["items"]] == [
        "AVM-DE",
        "AVM-US",
    ]


def test_functional_currency_change_before_postings(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    us = entity(app, maya, code="AVM-US", calendar_id=calendar_id)

    # No subledger line can exist before CTR-3, which adds the DB-05 freeze (BS3-D-07).
    changed = patch(
        app,
        f"{ENTITIES}/{us['id']}",
        maya,
        {"functional_currency": "EUR", "time_zone": "Europe/Berlin"},
        if_match='"r1"',
    )
    assert changed.status_code == 200, changed.text
    assert changed.headers["ETag"] == '"r2"'
    assert (changed.json()["functional_currency"], changed.json()["time_zone"]) == (
        "EUR",
        "Europe/Berlin",
    )
    unknown = patch(
        app, f"{ENTITIES}/{us['id']}", maya, {"functional_currency": "ZZZ"}, if_match='"r2"'
    )
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text

    context = DbContext(tenant_id=maya_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        events = session.execute(
            select(audit_event.c.before, audit_event.c.after).where(
                audit_event.c.action == "legal_entity.update"
            )
        ).all()
    assert [tuple(event) for event in events] == [
        (
            {"functional_currency": "USD", "time_zone": "America/New_York"},
            {"functional_currency": "EUR", "time_zone": "Europe/Berlin"},
        )
    ]
