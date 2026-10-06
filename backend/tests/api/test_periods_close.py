"""CLO-3 period commands over HTTP (04 §16.8 "Period commands", API-C-08, §15.2 ``period-closed``;
PRD §5.5 ERR-15; 03 REQ-CLS-002; BUILD_SPEC CLO-3).

Worlds: Maya (Revenue Accountant, which holds ``period.close``) with AVM-US FY2026-P01 to P09 open
(``support.factories.world_calendar``); ``support.factories.seat_world`` with K-09
(``SF-ORD-10417``, AVM-US) for the closed-period problem. The lock command is post-rc (CLO-6), so
the test that needs ``closed`` writes the T-REF-07 transition itself, as DB-07 requires.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_event,
    period_lock,
    period_state,
    period_state_transition,
)
from erev_api.enums import PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from support.db import TestDatabase
from support.factories import (
    activated_contract,
    booked_contract,
    k09_body,
    seat_world,
    world_calendar,
)
from support.principals import Actor, member
from support.reference import PERIODS, get, holding, periods, post, slug
from support.rows import (
    CloseParts,
    insert_approval_request,
    period_lock_values,
    period_state_transition_values,
)

PROBE_ID = UUID("01920000-0000-7000-8000-00000000c103")
EVENTS = "/api/v1/contracts/{contract_id}/events"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    actor = holding(app, member(keyring, clock), "revenue_accountant")
    world_calendar(app, actor)
    return actor


def _state(app: FastAPI, actor: Actor, key: str) -> dict[str, Any]:
    (found,) = [
        item for item in periods(app, actor, entity="AVM-US") if item["period"]["period_key"] == key
    ]
    return found


def test_period_commands_require_if_match(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya = _maya(app, keyring, clock)
    september = _state(app, maya, "FY2026-P09")
    path = f"{PERIODS}/{september['id']}"
    current = f'"r{september["row_version"]}"'

    missing = post(app, f"{path}/start-close", maya, {})
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = post(
        app, f"{path}/start-close", maya, {}, if_match=f'"r{september["row_version"] + 7}"'
    )
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    assert _state(app, maya, "FY2026-P09")["state"] == "open"

    started = post(app, f"{path}/start-close", maya, {}, if_match=current)
    assert started.status_code == 200, started.text
    body = {"reason_code": "CLOSE_RESTARTED"}
    missing = post(app, f"{path}/cancel-close", maya, body)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    # The version before start-close is stale now.
    stale = post(app, f"{path}/cancel-close", maya, body, if_match=current)
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    assert _state(app, maya, "FY2026-P09")["state"] == "closing"
    ended = post(app, f"{path}/cancel-close", maya, body, if_match=started.headers["ETag"])
    assert ended.status_code == 200, ended.text
    assert ended.json()["state"] == "open"


def test_transitions_list(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = _maya(app, keyring, clock)
    september = _state(app, maya, "FY2026-P09")
    path = f"{PERIODS}/{september['id']}"
    started = post(
        app,
        f"{path}/start-close",
        maya,
        {"comment": "September close started"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    clock.advance(timedelta(minutes=5))
    ended = post(
        app,
        f"{path}/cancel-close",
        maya,
        {"reason_code": "DATA_CORRECTION_PENDING", "comment": "Corrected usage file expected"},
        if_match=started.headers["ETag"],
    )
    assert ended.status_code == 200, ended.text

    listed = get(app, f"{path}/transitions", maya)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [(item["from_state"], item["to_state"]) for item in items] == [
        ("closing", "open"),
        ("open", "closing"),
        ("future", "open"),
        (None, "future"),
    ]
    assert [(item["reason_code"], item["comment"]) for item in items[:2]] == [
        ("DATA_CORRECTION_PENDING", "Corrected usage file expected"),
        (None, "September close started"),
    ]
    assert items[0]["created_by"]["id"] == str(maya.member.user_id)
    assert items[0]["created_by"]["kind"] == "USER"
    assert items[0]["created_at"] > items[1]["created_at"]
    oldest_first = get(app, f"{path}/transitions", maya, {"sort": "created_at", "limit": 2})
    assert oldest_first.status_code == 200, oldest_first.text
    stamps = [item["created_at"] for item in oldest_first.json()["items"]]
    assert (len(stamps), stamps == sorted(stamps)) == (2, True)
    assert oldest_first.json()["next_cursor"] is not None

    unknown = get(app, f"{PERIODS}/{PROBE_ID}/transitions", maya)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text


def _closed(actor: Actor, state_id: str) -> None:
    """``closing`` → ``closed`` through its T-REF-07 transition (the CLO-6 lock is post-rc)."""
    tenant_id = actor.member.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        row = (
            session.execute(select(period_state).where(period_state.c.id == UUID(state_id)))
            .mappings()
            .one()
        )
        transition_id = new_id()
        parts = CloseParts(
            calendar_id=PROBE_ID,
            entity_id=row["entity_id"],
            period_id=row["period_id"],
            period_state_transition_id=transition_id,
            approval_request_id=insert_approval_request(
                session, tenant_id=tenant_id, entity_id=row["entity_id"]
            ),
            file_id=PROBE_ID,
        )
        lock = period_lock_values(tenant_id, parts=parts)
        session.execute(insert(period_lock).values(**lock))
        session.execute(
            insert(period_state_transition).values(
                **period_state_transition_values(
                    tenant_id,
                    period_state_id=row["id"],
                    entity_id=row["entity_id"],
                    period_id=row["period_id"],
                    from_state="closing",
                    to_state="closed",
                    id=transition_id,
                    approval_request_id=parts.approval_request_id,
                    period_lock_id=lock["id"],
                )
            )
        )
        session.execute(
            update(period_state)
            .where(period_state.c.id == row["id"])
            .values(state="closed", updated_by_kind=PrincipalKind.SYSTEM.value)
        )


def test_period_closed_problem(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = seat_world(app, keyring, clock, files)
    booked = booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    activated_contract(world.place, booked)
    maya = world.place.author
    contract_id = UUID(str(booked.contract["id"]))
    september = _state(app, maya, "FY2026-P09")
    started = post(
        app,
        f"{PERIODS}/{september['id']}/start-close",
        maya,
        {},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    _closed(maya, september["id"])
    assert _state(app, maya, "FY2026-P09")["state"] == "closed"

    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    events_before = world.place.scalar(
        select(func.count()).where(contract_event.c.contract_id == contract_id)
    )
    billing = {
        "event_type": "BILLING_RECORDED",
        "effective_date": "2026-09-20",
        "payload": {
            "invoice_number": "INV-US-5001",
            "line_external_id": "INV-US-5001-1",
            "amount": {"amount": "3000.00", "currency": "USD"},
            "issue_date": "2026-09-20",
        },
    }
    refused = post(
        app,
        EVENTS.format(contract_id=contract_id),
        maya,
        {"events": [billing]},
        if_match=f'"s{head}"',
    )
    assert (refused.status_code, slug(refused)) == (409, "period-closed"), refused.text
    assert refused.json()["detail"] == (
        "Sep 2026 is closed for AVM-US in book ASC606. Postings to a closed period are not allowed."
    )
    assert refused.json()["code"] == "EREV-LED-003"
    assert (
        world.place.scalar(select(func.count()).where(contract_event.c.contract_id == contract_id))
        == events_before
    )
