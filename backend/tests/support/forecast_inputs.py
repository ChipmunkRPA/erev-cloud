"""Exercise the forecast input API inside a real created scenario."""

from uuid import UUID

import pytest
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import forecast_event_set
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from support.http import call
from support.principals import Actor, cookie_headers


def exercise_input_sets(app: FastAPI, source: Actor, sandbox: Actor, tenant_id: UUID) -> None:
    base = "/api/v1/forecast-event-sets"
    body = {"code": "Q4_BASE", "name": "Q4 base"}
    denied = call(
        app, "POST", base, json=body, headers=cookie_headers(source.token, source.csrf_token)
    )
    assert denied.status_code == 403 and denied.json()["type"].endswith("sandbox-restricted"), (
        denied.text
    )
    headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    created = call(app, "POST", base, json=body, headers=headers)
    assert created.status_code == 201, created.text
    replay = call(app, "POST", base, json=body, headers=headers)
    assert replay.status_code == 201 and replay.json() == created.json(), replay.text
    path = f"{base}/{created.json()['id']}"
    edit_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    edit_headers["If-Match"] = created.headers["ETag"]
    edited = call(app, "PATCH", path, json={"name": "Q4 reviewed base"}, headers=edit_headers)
    assert edited.status_code == 200, edited.text
    stale_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    stale_headers["If-Match"] = created.headers["ETag"]
    stale = call(app, "POST", path + "/publish", headers=stale_headers)
    assert stale.status_code == 412, stale.text
    publish_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    publish_headers["If-Match"] = edited.headers["ETag"]
    published = call(app, "POST", path + "/publish", headers=publish_headers)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert len(published.json()["content_sha256"]) == 64
    blocked_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    blocked_headers["If-Match"] = published.headers["ETag"]
    blocked = call(app, "PATCH", path, json={"name": "Changed"}, headers=blocked_headers)
    assert blocked.status_code == 409, blocked.text
    with pytest.raises(DBAPIError, match="EREV-CFG-002"):
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            session.execute(
                update(forecast_event_set)
                .where(forecast_event_set.c.id == UUID(created.json()["id"]))
                .values(name="SQL mutation")
            )
    next_version = call(
        app, "POST", base, json=body, headers=cookie_headers(sandbox.token, sandbox.csrf_token)
    )
    assert next_version.status_code == 201, next_version.text
    assert next_version.json()["version_no"] == 2
    assert next_version.json()["supersedes_version_id"] == created.json()["id"]
    next_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    next_headers["If-Match"] = next_version.headers["ETag"]
    next_published = call(
        app, "POST", f"{base}/{next_version.json()['id']}/publish", headers=next_headers
    )
    assert next_published.status_code == 200, next_published.text
    previous = call(app, "GET", path, headers=cookie_headers(sandbox.token, key=False))
    assert previous.status_code == 200 and previous.json()["status"] == "SUPERSEDED", previous.text
    assert previous.json()["content_sha256"] == published.json()["content_sha256"]
    listed = call(
        app,
        "GET",
        base,
        params={"status": "PUBLISHED"},
        headers=cookie_headers(sandbox.token, key=False),
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [next_version.json()["id"]]
