"""API-R-18 calendars and period generation (04 §15.3 API-R-18, T-REF-04, T-REF-05, API-C-08;
BUILD_SPEC RFD-1).

Maya holds Revenue Accountant, which carries ``masterdata.maintain``; Omar holds Viewer, which
carries ``config.read`` only (docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

CALENDARS = "/api/v1/calendars"
PROBLEM_BASE = "https://erev.dev/problems/"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def post(app: FastAPI, path: str, actor: Actor, json: dict[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def holding(app: FastAPI, someone: Member, role_code: str) -> Actor:
    """Assign the tenant's role ``role_code``, then sign in to the workspace."""
    ctx = DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
        )
    return workspace(app, someone, sign_in(app, someone.email))


def test_week_pattern_requires_anchor(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    retail: dict[str, Any] = {
        "code": "RETAIL-445",
        "name": "Retail 4-4-5",
        "pattern": "P445",
        "fiscal_year_start_month": 2,
        "year_end_anchor": "NEAREST_WEEKDAY_TO_MONTH_END",
    }
    refused = post(app, CALENDARS, maya, retail)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert refused.json()["errors"][0]["field"] == "week_end_day"
    assert fields(refused) == [("week_end_day", "T-REF-04")]

    created = post(app, CALENDARS, maya, {**retail, "week_end_day": 6})
    assert created.status_code == 201, created.text
    assert created.headers["ETag"] == '"r1"'
    body = created.json()
    assert (body["code"], body["pattern"], body["week_end_day"], body["year_end_anchor"]) == (
        "RETAIL-445",
        "P445",
        6,
        "NEAREST_WEEKDAY_TO_MONTH_END",
    )


def test_generate_year_permission(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    omar = holding(app, colleague(maya_member.tenant_id, "omar"), "viewer")

    created = post(app, CALENDARS, maya, {"code": "GREGORIAN", "name": "Gregorian"})
    assert created.status_code == 201, created.text
    calendar_id = created.json()["id"]
    assert created.json()["pattern"] == "MONTHLY"

    # config.read lists calendars; creating one needs masterdata.maintain or settings.manage.
    listed = call(app, "GET", CALENDARS, headers=cookie_headers(omar.token, key=False))
    assert listed.status_code == 200, listed.text
    assert [item["code"] for item in listed.json()["items"]] == ["GREGORIAN"]
    denied = post(app, CALENDARS, omar, {"code": "OMAR", "name": "Omar"})
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text

    generate = f"{CALENDARS}/{calendar_id}/generate-year"
    refused = post(app, generate, omar, {"fiscal_year": 2026})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    generated = post(app, generate, maya, {"fiscal_year": 2026})
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert (body["calendar_id"], body["fiscal_year"], body["inserted_count"]) == (
        calendar_id,
        2026,
        12,
    )
    assert [p["period_key"] for p in body["periods"]] == [f"FY2026-P{n:02d}" for n in range(1, 13)]
    assert (body["periods"][8]["name"], body["periods"][8]["start_date"]) == (
        "Sep 2026",
        "2026-09-01",
    )

    unknown = post(app, f"{CALENDARS}/{uuid.uuid4()}/generate-year", maya, {"fiscal_year": 2026})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
