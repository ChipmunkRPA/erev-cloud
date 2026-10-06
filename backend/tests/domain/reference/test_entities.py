"""Legal entities and entity books (04 §15.3 API-R-17, T-REF-01, T-REF-03, T-REF-06, T-REF-07,
T-PLT-26, AUD-CMD, AUD-FACT; 03 REQ-REF-001, REQ-BK-001; PRD §2.5; BUILD_SPEC RFD-2).

Maya holds Revenue Accountant, which carries ``masterdata.maintain``; Omar holds Viewer, which
carries ``config.read`` only (docs/02-PRD.md §5.6). The Avenmoor entities follow PRD §2.5.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    numbering_series,
    period,
    period_state,
    period_state_transition,
)
from erev_api.domain.reference import books, entities
from erev_api.domain.reference import periods as period_rules
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support.db import TestDatabase
from support.principals import colleague, member
from support.reference import (
    BOOKS,
    CALENDARS,
    ENTITIES,
    calendar,
    entity,
    fields,
    get,
    holding,
    patch,
    periods,
    post,
    put,
    slug,
)

KEYS_2026 = [f"FY2026-P{number:02d}" for number in range(1, 13)]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _context(tenant_id: uuid.UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _events(tenant_id: uuid.UUID, *actions: str) -> list[dict[str, Any]]:
    statement = (
        select(audit_event.c.action, audit_event.c.object_id, audit_event.c.before)
        .add_columns(audit_event.c.after, audit_event.c.detail)
        .where(audit_event.c.tenant_id == tenant_id, audit_event.c.action.in_(actions))
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(_context(tenant_id)) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def test_create_entity_creates_je_series_and_primary_book_states(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya, code="MONTHLY-JAN")

    created = post(
        app,
        ENTITIES,
        maya,
        {
            "code": "AVM-US",
            "name": "Avenmoor Inc. (Demo)",
            "functional_currency": "USD",
            "time_zone": "America/New_York",
            "calendar_id": calendar_id,
            "country_code": "US",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert created.headers["ETag"] == '"r1"'
    assert created.headers["Location"] == f"/api/v1/entities/{body['id']}"
    assert (
        body["code"],
        body["name"],
        body["functional_currency"],
        body["time_zone"],
        body["calendar_id"],
        body["country_code"],
        body["parent_entity_id"],
        body["is_active"],
    ) == (
        "AVM-US",
        "Avenmoor Inc. (Demo)",
        "USD",
        "America/New_York",
        calendar_id,
        "US",
        None,
        True,
    )
    assert [(b["book_code"], b["first_period_key"], b["is_enabled"]) for b in body["books"]] == [
        ("ASC606", "FY2026-P01", True)
    ]

    entity_id = uuid.UUID(body["id"])
    tenant_id = maya_member.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        series = session.execute(
            select(
                numbering_series.c.series_code,
                numbering_series.c.scope_key,
                numbering_series.c.prefix,
                numbering_series.c.next_value,
                numbering_series.c.is_gapless,
            ).where(numbering_series.c.series_code == "JE")
        ).all()
        states = session.execute(
            select(
                period.c.period_key,
                period_state.c.book_code,
                period_state.c.state,
                period_state.c.period_end_date,
            )
            .select_from(
                period_state.join(
                    period,
                    and_(
                        period.c.tenant_id == period_state.c.tenant_id,
                        period.c.id == period_state.c.period_id,
                    ),
                )
            )
            .where(period_state.c.entity_id == entity_id)
            .order_by(period.c.start_date)
        ).all()
        creations = session.execute(
            select(func.count())
            .select_from(period_state_transition)
            .where(
                period_state_transition.c.entity_id == entity_id,
                period_state_transition.c.from_state.is_(None),
                period_state_transition.c.to_state == "future",
            )
        ).scalar_one()
    # T-PLT-26: the gapless JE series of the entity, numbering JE-AVM-US-000001 (SPEC-Q-165).
    assert [tuple(row) for row in series] == [("JE", str(entity_id), "JE-AVM-US-", 1, True)]
    # One future ASC606 state per generated period, each created by a NULL → future transition.
    assert [row.period_key for row in states] == KEYS_2026
    assert {(row.book_code, row.state) for row in states} == {("ASC606", "future")}
    assert states[8].period_end_date == date(2026, 9, 30)
    assert creations == 12

    events = _events(
        tenant_id,
        "legal_entity.create",
        "entity_book.create",
        period_rules.CREATE_TRANSITIONS_ACTION,
    )
    assert [event["action"] for event in events] == [
        "legal_entity.create",
        "entity_book.create",
        "period_state_transition.create",
    ]
    assert events[0]["after"]["time_zone"] == "America/New_York"
    assert events[1]["after"] == {
        "entity_id": str(entity_id),
        "book_code": "ASC606",
        "first_period_id": body["books"][0]["first_period_id"],
        "first_period_key": "FY2026-P01",
        "is_enabled": True,
    }
    assert (events[2]["detail"]["book_code"], len(events[2]["detail"]["ids"])) == ("ASC606", 12)

    # API-S-Period rows: no lock and no close run until CLO; the blocker counts are answered by
    # the single read, zero, and null in a row of the list (04 §16.8 rev 1.199).
    listed = periods(app, maya, entity="AVM-US", book="ASC606", fiscal_year=2026)
    assert [item["period"]["period_key"] for item in listed] == KEYS_2026
    assert listed[8]["period"] == {
        "id": listed[8]["period"]["id"],
        "period_key": "FY2026-P09",
        "name": "Sep 2026",
        "fiscal_year": 2026,
        "period_no": 9,
        "quarter_no": 3,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }
    assert listed[0]["entity"] == {
        "id": body["id"],
        "code": "AVM-US",
        "name": "Avenmoor Inc. (Demo)",
    }
    assert {
        (
            item["book"],
            item["state"],
            item["is_first_open"],
            item["current_lock"],
            item["close_run"],
        )
        for item in listed
    } == {("ASC606", "future", False, None, None)}
    assert listed[0]["blockers"] is None
    shown = get(app, f"/api/v1/periods/{listed[0]['id']}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.json() == {
        **listed[0],
        "blockers": dict.fromkeys(period_rules.BLOCKER_COUNTS, 0),
    }
    assert listed[0]["row_version"] == 1

    # generate-year adds the states of the next fiscal year; the book defaults to the primary one.
    generated = post(app, f"{CALENDARS}/{calendar_id}/generate-year", maya, {"fiscal_year": 2027})
    assert generated.status_code == 200, generated.text
    assert len(periods(app, maya, entity="AVM-US", fiscal_year=2027)) == 12
    assert len(periods(app, maya, entity=str(entity_id))) == 24


def test_create_entity_findings(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    calendar_id = calendar(app, maya)
    refused = post(
        app,
        ENTITIES,
        maya,
        {
            "code": "#AVM",
            "name": " ",
            "functional_currency": "XXX",
            "time_zone": "Mars/Olympus_Mons",
            "calendar_id": str(uuid.uuid4()),
            "parent_entity_id": str(uuid.uuid4()),
            "country_code": "us",
        },
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        ("code", "T-REF-01"),
        ("name", "T-REF-01"),
        ("functional_currency", "T-REF-01"),
        ("time_zone", "T-REF-01"),
        ("calendar_id", "T-REF-01"),
        ("parent_entity_id", "T-REF-01"),
        ("country_code", "T-REF-01"),
    ]

    # A calendar without generated periods cannot start a book; an unknown first period is refused.
    empty = post(app, CALENDARS, maya, {"code": "EMPTY", "name": "Empty"})
    assert empty.status_code == 201, empty.text
    base = {"code": "AVM-US", "name": "Avenmoor Inc. (Demo)", "functional_currency": "USD"}
    base |= {"time_zone": "America/New_York"}
    no_periods = post(app, ENTITIES, maya, {**base, "calendar_id": empty.json()["id"]})
    assert fields(no_periods) == [("calendar_id", "T-REF-01")]
    assert no_periods.json()["errors"][0]["message"] == entities.CALENDAR_EMPTY
    unknown_key = post(
        app, ENTITIES, maya, {**base, "calendar_id": calendar_id, "first_period_key": "FY2031-P01"}
    )
    assert fields(unknown_key) == [("first_period_key", "T-REF-03")]
    assert unknown_key.json()["errors"][0]["message"] == books.PERIOD_UNKNOWN

    # A later first period: the states start there.
    later = post(
        app, ENTITIES, maya, {**base, "calendar_id": calendar_id, "first_period_key": "FY2026-P07"}
    )
    assert later.status_code == 201, later.text
    assert [item["period"]["period_key"] for item in periods(app, maya, entity="AVM-US")] == (
        KEYS_2026[6:]
    )
    taken = post(app, ENTITIES, maya, {**base, "calendar_id": calendar_id})
    assert fields(taken) == [("code", "T-REF-01")]
    # A Viewer reads entities but does not create them.
    denied = post(app, ENTITIES, omar, {**base, "code": "AVM-DE", "calendar_id": calendar_id})
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    assert [item["code"] for item in get(app, ENTITIES, omar).json()["items"]] == ["AVM-US"]


def test_update_entity_requires_if_match(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    us = entity(app, maya, code="AVM-US", calendar_id=calendar_id)
    uk = entity(
        app,
        maya,
        code="AVM-UK",
        calendar_id=calendar_id,
        functional_currency="GBP",
        time_zone="Europe/London",
        parent_entity_id=us["id"],
    )
    path = f"{ENTITIES}/{us['id']}"
    read = get(app, path, maya)
    assert (read.status_code, read.headers["ETag"]) == (200, '"r1"'), read.text

    missing = patch(app, path, maya, {"name": "Avenmoor Inc."}, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = patch(app, path, maya, {"name": "Avenmoor Inc."}, if_match='"r7"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    # The code and the calendar do not change; an entity does not report to an entity below it.
    fixed = patch(app, path, maya, {"code": "AVM"}, if_match='"r1"')
    assert fixed.status_code == 422, fixed.text
    cycle = patch(app, path, maya, {"parent_entity_id": uk["id"], "tax_id": None}, if_match='"r1"')
    assert fields(cycle) == [("parent_entity_id", "T-REF-01")]
    blank = patch(app, path, maya, {"time_zone": None, "country_code": "USA"}, if_match='"r1"')
    assert blank.status_code == 422, blank.text

    renamed = patch(
        app, path, maya, {"name": "Avenmoor Inc.", "tax_id": "12-3456789"}, if_match='"r1"'
    )
    assert (renamed.status_code, renamed.headers["ETag"]) == (200, '"r2"'), renamed.text
    assert (renamed.json()["name"], renamed.json()["tax_id"]) == ("Avenmoor Inc.", "12-3456789")
    assert get(app, f"{ENTITIES}/{uuid.uuid4()}", maya).status_code == 404
    events = _events(maya_member.tenant_id, "legal_entity.update")
    assert [(event["before"], event["after"]) for event in events] == [
        (
            {"name": "AVM-US (Demo)", "tax_id": None},
            {"name": "Avenmoor Inc.", "tax_id": "12-3456789"},
        )
    ]


def test_enable_ifrs15_for_entity(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    uk = entity(
        app,
        maya,
        code="AVM-UK",
        calendar_id=calendar_id,
        functional_currency="GBP",
        time_zone="Europe/London",
        country_code="GB",
    )
    path = f"{ENTITIES}/{uk['id']}/books/IFRS15"

    enabled = put(app, path, maya, {"is_enabled": True, "first_period_key": "FY2026-P01"})
    assert enabled.status_code == 200, enabled.text
    assert enabled.headers["ETag"] == '"r1"'
    assert (
        enabled.json()["book_code"],
        enabled.json()["first_period_key"],
        enabled.json()["is_enabled"],
    ) == ("IFRS15", "FY2026-P01", True)
    listed = periods(app, maya, entity="AVM-UK", book="IFRS15", fiscal_year=2026)
    assert len(listed) == 12
    assert [item["period"]["period_key"] for item in listed] == KEYS_2026
    assert {(item["book"], item["state"]) for item in listed} == {("IFRS15", "future")}
    # The ASC606 states are unchanged, and the workspace book is enabled with the entity's.
    assert len(periods(app, maya, entity="AVM-UK", book="ASC606", fiscal_year=2026)) == 12
    ifrs15 = next(
        item for item in get(app, BOOKS, maya).json()["items"] if item["code"] == "IFRS15"
    )
    assert (ifrs15["is_enabled"], ifrs15["row_version"]) == (True, 2)
    kept = get(app, f"{ENTITIES}/{uk['id']}", maya).json()["books"]
    assert [(item["book_code"], item["first_period_key"]) for item in kept] == [
        ("ASC606", "FY2026-P01"),
        ("IFRS15", "FY2026-P01"),
    ]

    # Repeating the command changes nothing; the first period of a kept book does not move.
    repeated = put(app, path, maya, {"is_enabled": True})
    assert (repeated.status_code, repeated.headers["ETag"]) == (200, '"r1"'), repeated.text
    assert len(periods(app, maya, entity="AVM-UK", book="IFRS15")) == 12
    moved = put(app, path, maya, {"is_enabled": True, "first_period_key": "FY2026-P04"})
    assert fields(moved) == [("first_period_key", "T-REF-03")]
    # Disabling keeps the states; the primary book stays kept; a book not kept is not disabled.
    disabled = put(app, path, maya, {"is_enabled": False})
    assert (disabled.status_code, disabled.json()["is_enabled"]) == (200, False), disabled.text
    primary = put(app, f"{ENTITIES}/{uk['id']}/books/ASC606", maya, {"is_enabled": False})
    assert fields(primary) == [("is_enabled", "T-REF-03")]
    legacy = put(app, f"{ENTITIES}/{uk['id']}/books/LEGACY", maya, {"is_enabled": False})
    assert fields(legacy) == [("is_enabled", "T-REF-03")]
    unknown = put(
        app,
        f"{ENTITIES}/{uk['id']}/books/LEGACY",
        maya,
        {"is_enabled": True, "first_period_key": "FY2031-P01"},
    )
    assert fields(unknown) == [("first_period_key", "T-REF-03")]
    outside = put(app, f"{ENTITIES}/{uuid.uuid4()}/books/IFRS15", maya, {"is_enabled": True})
    assert (outside.status_code, slug(outside)) == (404, "not-found"), outside.text
    events = _events(maya_member.tenant_id, "entity_book.update", "book.update")
    assert [(event["action"], event["before"], event["after"]) for event in events] == [
        ("book.update", {"is_enabled": False}, {"is_enabled": True}),
        ("entity_book.update", {"is_enabled": True}, {"is_enabled": False}),
    ]
