"""Accounting books (04 §15.3 API-R-17, T-REF-02, E-02, §14.3, AUD-CMD; 03 REQ-BK-001; D-24;
BUILD_SPEC RFD-2).

Maya holds Revenue Accountant, which carries ``masterdata.maintain``; Omar holds Viewer, which
carries ``config.read`` only (docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.domain.reference import books
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.principals import colleague, member
from support.reference import (
    BOOKS,
    ENTITIES,
    calendar,
    entity,
    fields,
    get,
    holding,
    patch,
    put,
    slug,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_legacy_book_posting_target_none(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    listed = get(app, BOOKS, maya)
    assert listed.status_code == 200, listed.text
    assert [
        (item["code"], item["name"], item["is_primary"], item["is_enabled"], item["posting_target"])
        for item in listed.json()["items"]
    ] == [
        ("ASC606", "ASC 606", True, True, "GL_PRIMARY"),
        ("IFRS15", "IFRS 15", False, False, "GL_SECONDARY"),
        ("LEGACY", "Legacy", False, False, "NONE"),
    ]

    refused = patch(app, f"{BOOKS}/LEGACY", maya, {"posting_target": "GL_PRIMARY"}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("posting_target", "T-REF-02")]
    assert refused.json()["errors"][0]["message"] == books.LEGACY_TARGET
    legacy = next(
        item for item in get(app, BOOKS, maya).json()["items"] if item["code"] == "LEGACY"
    )
    assert (legacy["posting_target"], legacy["row_version"]) == ("NONE", 1)


def test_book_update_rules(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")

    denied = patch(app, f"{BOOKS}/IFRS15", omar, {"is_enabled": True}, if_match='"r1"')
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    missing = patch(app, f"{BOOKS}/IFRS15", maya, {"is_enabled": True}, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    primary = patch(app, f"{BOOKS}/ASC606", maya, {"is_enabled": False}, if_match='"r1"')
    assert fields(primary) == [("is_enabled", "T-REF-02")]
    coded = patch(app, f"{BOOKS}/ASC606", maya, {"code": "IFRS15"}, if_match='"r1"')
    assert coded.status_code == 422, coded.text

    enabled = patch(
        app,
        f"{BOOKS}/IFRS15",
        maya,
        {"name": "IFRS 15 (statutory)", "is_enabled": True},
        if_match='"r1"',
    )
    assert (enabled.status_code, enabled.headers["ETag"]) == (200, '"r2"'), enabled.text
    assert (enabled.json()["name"], enabled.json()["is_enabled"]) == ("IFRS 15 (statutory)", True)

    # A book an entity keeps is not disabled for the workspace.
    calendar_id = calendar(app, maya)
    uk = entity(app, maya, code="AVM-UK", calendar_id=calendar_id, time_zone="Europe/London")
    kept = put(app, f"{ENTITIES}/{uk['id']}/books/IFRS15", maya, {"is_enabled": True})
    assert kept.status_code == 200, kept.text
    in_use = patch(app, f"{BOOKS}/IFRS15", maya, {"is_enabled": False}, if_match='"r2"')
    assert fields(in_use) == [("is_enabled", "T-REF-03")]
    assert in_use.json()["errors"][0]["message"] == books.BOOK_KEPT.format(codes="AVM-UK")

    context = DbContext(tenant_id=maya_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        events = session.execute(
            select(audit_event.c.before, audit_event.c.after, audit_event.c.object_version).where(
                audit_event.c.action == "book.update", audit_event.c.outcome == "SUCCESS"
            )
        ).all()
    assert [tuple(event) for event in events] == [
        (
            {"name": "IFRS 15", "is_enabled": False},
            {"name": "IFRS 15 (statutory)", "is_enabled": True},
            "2",
        )
    ]
