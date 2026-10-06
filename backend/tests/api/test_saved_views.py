"""API-R-16 saved views and favourites (04 §15.3 API-R-16, T-PLT-37, API-C-08; SCREENS SCR-IA-07,
SCR-IA-08; BUILD_SPEC PLF-21).

Maya and Omar are members of one workspace without roles: saving views needs only a signed-in
member.
"""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, member, sign_in, workspace

SAVED_VIEWS = "/api/v1/saved-views"
PROBLEM_BASE = "https://erev.dev/problems/"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def send(
    app: FastAPI, method: str, path: str, actor: Actor, json: dict[str, Any] | None = None
) -> HttpResponse:
    return call(app, method, path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def names(app: FastAPI, actor: Actor, screen_code: str) -> list[str]:
    listed = call(
        app,
        "GET",
        SAVED_VIEWS,
        params={"screen_code": screen_code},
        headers=cookie_headers(actor.token, key=False),
    )
    assert listed.status_code == 200, listed.text
    return [item["name"] for item in listed.json()["items"]]


def test_saved_view_crud_and_favourite(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    maya_member = member(keyring, clock)
    omar_member = colleague(maya_member.tenant_id, "omar")
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    omar = workspace(app, omar_member, sign_in(app, omar_member.email))

    private = send(
        app,
        "POST",
        SAVED_VIEWS,
        omar,
        {"screen_code": "SF-02", "name": "Omar drafts", "config": {"filters": {"status": "DRAFT"}}},
    )
    assert private.status_code == 201, private.text
    shared = send(
        app,
        "POST",
        SAVED_VIEWS,
        omar,
        {
            "screen_code": "SF-02",
            "name": "Team open contracts",
            "config": {"sort": "-id"},
            "is_shared": True,
        },
    )
    assert shared.status_code == 201, shared.text

    view_body = {
        "screen_code": "SF-02",
        "name": "Open contracts",
        "config": {"sort": "-inception_date"},
    }
    created = send(app, "POST", SAVED_VIEWS, maya, view_body)
    assert created.status_code == 201, created.text
    assert created.headers["ETag"] == '"r1"'
    view = created.json()
    assert (
        view["membership_id"],
        view["screen_code"],
        view["name"],
        view["config"],
        view["is_shared"],
        view["is_favourite"],
    ) == (
        str(maya_member.membership_id),
        "SF-02",
        "Open contracts",
        {"sort": "-inception_date"},
        False,
        False,
    )

    duplicate = send(app, "POST", SAVED_VIEWS, maya, {**view_body, "config": {}})
    assert (duplicate.status_code, slug(duplicate)) == (422, "validation-failed"), duplicate.text
    assert fields(duplicate) == [("name", "T-PLT-37")]

    favourite = send(
        app,
        "POST",
        SAVED_VIEWS,
        maya,
        {
            "screen_code": "SF-08:report",
            "name": "RPO",
            "is_favourite": True,
            "config": {"target": "report", "path": "/reports/rpo", "label": "RPO"},
        },
    )
    assert favourite.status_code == 201, favourite.text
    assert favourite.json()["is_favourite"] is True
    loose = send(
        app,
        "POST",
        SAVED_VIEWS,
        maya,
        {
            "screen_code": "SF-08:report",
            "name": "Waterfall",
            "is_favourite": True,
            "config": {"target": "dashboard", "path": "reports", "label": ""},
        },
    )
    assert (loose.status_code, fields(loose)) == (422, [("config", "SCR-IA-08")]), loose.text

    # The caller's views and the shared ones, never another member's private view or other screens.
    assert names(app, maya, "SF-02") == ["Open contracts", "Team open contracts"]
    assert names(app, omar, "SF-02") == ["Omar drafts", "Team open contracts"]

    pinned = f"{SAVED_VIEWS}/{favourite.json()['id']}"
    unpinned = send(app, "PATCH", pinned, maya, {"is_favourite": False})
    assert unpinned.status_code == 200, unpinned.text
    assert (unpinned.json()["is_favourite"], unpinned.headers["ETag"]) == (False, '"r2"')

    others = f"{SAVED_VIEWS}/{shared.json()['id']}"
    renamed = send(app, "PATCH", others, maya, {"name": "Mine now"})
    assert (renamed.status_code, slug(renamed)) == (404, "not-found"), renamed.text
    removed = send(app, "DELETE", others, maya)
    assert (removed.status_code, slug(removed)) == (404, "not-found"), removed.text

    deleted = send(app, "DELETE", f"{SAVED_VIEWS}/{view['id']}", maya)
    assert deleted.status_code == 204, deleted.text
    assert deleted.text == ""
    assert names(app, maya, "SF-02") == ["Team open contracts"]
