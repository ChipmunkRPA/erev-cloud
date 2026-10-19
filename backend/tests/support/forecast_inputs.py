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


def exercise_forecast_imports(world: object) -> None:
    """Run a real progress file through validation, diff and scenario commit."""
    from erev_api.db.tables import approval_request, forecast_event_set, import_upload, job
    from sqlalchemy import func, select
    from support.factories import ImportWorld, run_import_job, upload_import_source

    assert isinstance(world, ImportWorld)

    def headers() -> dict[str, str]:
        return cookie_headers(world.actor.token, world.actor.csrf_token)

    created_set = call(
        world.app,
        "POST",
        "/api/v1/forecast-event-sets",
        json={"code": "FILE_BASE", "name": "File base"},
        headers=headers(),
    )
    assert created_set.status_code == 201, created_set.text
    set_id = UUID(created_set.json()["id"])
    content = (
        b"contract,event_type,effective_date,obligation_key,cumulative_progress_ratio,measure\n"
        b"SF-ORD-10001,PROGRESS_RECORDED,2026-02-28,O2,0.60,OUTPUT_PERCENT\n"
    )
    source = upload_import_source(world, "forecast-progress.csv", content)
    created = call(
        world.app,
        "POST",
        "/api/v1/imports",
        headers=headers(),
        json={
            "file_id": source,
            "template_code": "progress_events",
            "forecast_event_set_id": str(set_id),
        },
    )
    assert created.status_code == 202, created.text
    import_id = UUID(created.headers["X-Erev-Import-Id"])
    set_path = f"/api/v1/forecast-event-sets/{set_id}"
    publish_headers = headers()
    publish_headers["If-Match"] = created_set.headers["ETag"]
    premature = call(world.app, "POST", set_path + "/publish", headers=publish_headers)
    assert premature.status_code == 409, premature.text
    run_import_job(world, UUID(created.json()["id"]))
    row = world.rows(select(import_upload).where(import_upload.c.id == import_id))[0]
    assert row["status"] == "VALIDATED", row
    diff_id = world.scalar(
        select(job.c.id).where(job.c.subject_id == import_id, job.c.kind == "IMPORT_DIFF")
    )
    run_import_job(world, diff_id)
    before_approvals = world.scalar(select(func.count()).select_from(approval_request))
    submitted = call(
        world.app, "POST", f"/api/v1/imports/{import_id}/submit", headers=headers(), json={}
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["approval_request_id"] is None
    assert submitted.json()["status"] == "APPROVED"
    assert submitted.json()["forecast_event_set_id"] == str(set_id)
    commit_id = world.scalar(
        select(job.c.id).where(job.c.subject_id == import_id, job.c.kind == "IMPORT_COMMIT")
    )
    run_import_job(world, commit_id)
    committed = world.rows(select(import_upload).where(import_upload.c.id == import_id))[0]
    assert committed["status"] == "COMMITTED", committed
    assert world.scalar(select(func.count()).select_from(approval_request)) == before_approvals
    captured = world.rows(select(forecast_event_set).where(forecast_event_set.c.id == set_id))[0]
    assert captured["import_upload_ids"] == [import_id]
    invalid_source = upload_import_source(
        world,
        "forecast-invalid.csv",
        b"contract,event_type,effective_date,obligation_key,quantity,trigger\n"
        b"SF-ORD-10001,DELIVERY_RECORDED,2026-02-28,O1,2,DELIVERY\n",
    )
    invalid = call(
        world.app,
        "POST",
        "/api/v1/imports",
        headers=headers(),
        json={
            "file_id": invalid_source,
            "template_code": "progress_events",
            "forecast_event_set_id": str(set_id),
        },
    )
    assert invalid.status_code == 202, invalid.text
    run_import_job(world, UUID(invalid.json()["id"]))
    invalid_id = UUID(invalid.headers["X-Erev-Import-Id"])
    assert (
        world.scalar(select(import_upload.c.status).where(import_upload.c.id == invalid_id))
        == "INVALID"
    )
    assert world.scalar(
        select(forecast_event_set.c.import_upload_ids).where(forecast_event_set.c.id == set_id)
    ) == [import_id]
    current = call(world.app, "GET", set_path, headers=cookie_headers(world.actor.token, key=False))
    publish_headers = headers()
    publish_headers["If-Match"] = current.headers["ETag"]
    published = call(world.app, "POST", set_path + "/publish", headers=publish_headers)
    assert published.status_code == 200, published.text
