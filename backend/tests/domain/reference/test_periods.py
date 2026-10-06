"""Period states and ``open`` (04 §15.3 API-R-18, §16.8 API-S-Period, T-REF-06, T-REF-07, DB-07,
AUD-FACT; 03 REQ-CLS-001; BUILD_SPEC RFD-2).

Maya holds Revenue Accountant, which carries ``period.close``; Omar holds Viewer, which carries
``config.read`` only (docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import uuid

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, period_state_transition
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
    periods,
    post,
    put,
    slug,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_open_period_writes_transition(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """``future → open`` writes one transition and one audit event, and periods open in order (PRD
    SM-07 guard "Previous period not ``future``"; supervisor ruling R-58 (d), item
    PERIOD-OPEN-GUARD-1). Until that ruling this test opened September first and August after it:
    the guard was not enforced, and a book opened out of order posted nothing in any period. It
    opens the first period the book keeps, which has no previous state."""
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    calendar_id = calendar(app, maya)
    entity(app, maya, code="AVM-US", calendar_id=calendar_id)
    states = {item["period"]["period_key"]: item for item in periods(app, maya, entity="AVM-US")}
    assert min(states) == "FY2026-P01"
    january = states["FY2026-P01"]

    opened = post(
        app, f"{PERIODS}/{january['id']}/open", maya, {"comment": "Setup"}, if_match='"r1"'
    )
    assert opened.status_code == 200, opened.text
    assert opened.headers["ETag"] == '"r2"'
    body = opened.json()
    assert (
        body["id"],
        body["book"],
        body["period"]["period_key"],
        body["state"],
        body["is_first_open"],
        body["row_version"],
    ) == (january["id"], "ASC606", "FY2026-P01", "open", True, 2)

    context = DbContext(tenant_id=maya_member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        transitions = session.execute(
            select(
                period_state_transition.c.id,
                period_state_transition.c.from_state,
                period_state_transition.c.to_state,
                period_state_transition.c.reason_code,
                period_state_transition.c.comment,
                period_state_transition.c.created_by,
            )
            .where(period_state_transition.c.period_state_id == uuid.UUID(january["id"]))
            .order_by(period_state_transition.c.created_txid)
        ).all()
        events = session.execute(
            select(
                audit_event.c.object_type,
                audit_event.c.object_id,
                audit_event.c.after,
                audit_event.c.comment,
            ).where(audit_event.c.action == "period.open")
        ).all()
    # The command inserts one transition future → open; the state was created from NULL.
    assert [
        (row.from_state, row.to_state, row.reason_code, row.comment) for row in transitions
    ] == [
        (None, "future", None, None),
        ("future", "open", None, "Setup"),
    ]
    assert transitions[1].created_by == maya_member.user_id
    assert [(event.object_type, event.object_id, event.comment) for event in events] == [
        ("period_state_transition", transitions[1].id, "Setup")
    ]
    assert events[0].after["from_state"] == "future"
    assert events[0].after["to_state"] == "open"

    listed = periods(app, maya, entity="AVM-US", book="ASC606", state="open")
    assert [
        (item["id"], item["period"]["period_key"], item["is_first_open"]) for item in listed
    ] == [(january["id"], "FY2026-P01", True)]
    shown = get(app, f"{PERIODS}/{january['id']}", maya)
    assert (shown.status_code, shown.headers["ETag"], shown.json()["state"]) == (
        200,
        '"r2"',
        "open",
    )

    # An open period does not open again.
    again = post(app, f"{PERIODS}/{january['id']}/open", maya, {}, if_match='"r2"')
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    # Periods open in order (SM-07): March does not open while February is future, and the
    # refusal leaves it untouched.
    march = post(app, f"{PERIODS}/{states['FY2026-P03']['id']}/open", maya, {}, if_match='"r1"')
    assert (march.status_code, slug(march)) == (409, "invalid-transition"), march.text
    message = (
        "The previous period of AVM-US in book ASC606 is future, so FY2026-P03 does not open yet."
    )
    assert march.json()["detail"] == message
    assert [(error["rule_id"], error["message"]) for error in march.json()["errors"]] == [
        ("DB-07", message)
    ]
    assert get(app, f"{PERIODS}/{states['FY2026-P03']['id']}", maya).json()["state"] == "future"
    # Positive control: February opens after January, then March after February; the earliest
    # open period stays the first open one.
    for key in ("FY2026-P02", "FY2026-P03"):
        following = post(app, f"{PERIODS}/{states[key]['id']}/open", maya, {}, if_match='"r1"')
        assert following.status_code == 200, following.text
    listed = periods(app, maya, entity="AVM-US", state="open")
    assert [(item["period"]["period_key"], item["is_first_open"]) for item in listed] == [
        ("FY2026-P01", True),
        ("FY2026-P02", False),
        ("FY2026-P03", False),
    ]


def test_open_period_preconditions(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")
    calendar_id = calendar(app, maya)
    uk = entity(app, maya, code="AVM-UK", calendar_id=calendar_id, time_zone="Europe/London")
    january = periods(app, maya, entity="AVM-UK")[0]
    path = f"{PERIODS}/{january['id']}/open"

    denied = post(app, path, omar, {}, if_match='"r1"')
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    missing = post(app, path, maya, {}, if_match=None)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = post(app, path, maya, {}, if_match='"r5"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    unknown = post(app, f"{PERIODS}/{uuid.uuid4()}/open", maya, {}, if_match='"r1"')
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    hidden = get(app, f"{PERIODS}/{uuid.uuid4()}", maya)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text

    # A period of a book the entity disabled does not open.
    kept = put(app, f"{ENTITIES}/{uk['id']}/books/IFRS15", maya, {"is_enabled": True})
    assert kept.status_code == 200, kept.text
    ifrs15 = periods(app, maya, entity="AVM-UK", book="IFRS15")[0]
    disabled = put(app, f"{ENTITIES}/{uk['id']}/books/IFRS15", maya, {"is_enabled": False})
    assert disabled.status_code == 200, disabled.text
    refused = post(app, f"{PERIODS}/{ifrs15['id']}/open", maya, {}, if_match='"r1"')
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    # The state filter takes E-04 literals only.
    invalid = get(app, PERIODS, maya, {"state": "shut"})
    assert (invalid.status_code, slug(invalid)) == (422, "validation-failed"), invalid.text
