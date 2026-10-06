"""API-R-15 webhooks (04 §15.3 API-R-15, T-PLT-35, T-PLT-36, API-C-08; 05 NTR-10, KEY-08;
BUILD_SPEC PLF-24).

Maya holds ``integration_admin``, which carries ``webhook.manage`` and ``audit.read``; Victor is a
viewer without them. Deliveries run as the worker would, through ``deliver`` with a mock transport.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import idempotency_record, webhook_endpoint
from erev_api.enums import JobKind, TenantKind
from erev_api.events.webhooks import (
    DeliveryStats,
    deliver,
    emit_webhook,
    secret_context,
    signature_header,
)
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpRequest, HttpResponse, call, mock_transport
from support.principals import Actor, Member, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

ENDPOINTS = "/api/v1/webhook-endpoints"
DELIVERIES = "/api/v1/webhook-deliveries"
PROBLEM_BASE = "https://erev.dev/problems/"
ENDPOINT_KEYS = {
    "id",
    "url",
    "description",
    "event_kinds",
    "is_active",
    "created_at",
    "updated_at",
    "row_version",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _people(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Member, Actor, Actor]:
    maya_member = member(keyring, clock)
    victor_member = colleague(maya_member.tenant_id, "victor")
    with tenant_session(_db(maya_member.tenant_id)) as session:
        for someone, role_code in ((maya_member, "integration_admin"), (victor_member, "viewer")):
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
            )
    maya = workspace(app, maya_member, sign_in(app, maya_member.email))
    victor = workspace(app, victor_member, sign_in(app, victor_member.email))
    return maya_member, maya, victor


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def send(
    app: FastAPI,
    method: str,
    path: str,
    actor: Actor,
    json: dict[str, Any] | None = None,
    **headers: str,
) -> HttpResponse:
    return call(
        app,
        method,
        path,
        json=json,
        headers=cookie_headers(actor.token, actor.csrf_token, **headers),
    )


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def _emit_period_locked(
    tenant_id: UUID, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> int:
    """Emit ``period.locked`` to the workspace's subscribed endpoints; the number of deliveries."""
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-webhooks-api",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        emitted = emit_webhook(uow, event_kind="period.locked", payload={"period_id": new_id()})
        uow.commit()
    return emitted


def _deliver(
    tenant_id: UUID,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    respond: Callable[[HttpRequest], int],
) -> DeliveryStats:
    """One ``WEBHOOK_DELIVERY`` run as the worker would, through a mock transport."""
    runtime = JobRuntime(
        clock=clock,
        keyring=keyring,
        files=files,
        webhooks=WebhookClient(
            env=Environment.TEST,
            transport=mock_transport(respond),
            resolve=lambda host, port: ["93.184.216.34"],
        ),
    )
    worker = JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.WEBHOOK_DELIVERY,
        principal=system_principal(tenant_id),
        runtime=runtime,
        persisted=False,
    )
    return deliver(worker)


def test_signing_secret_not_kept_for_replay(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """PR-A-02 (D-80): the stored and replayed body carries the signing secret as null."""
    maya_member, maya, _ = _people(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    key = "k-sup-plf-2-webhook-0001"
    body = {"url": "https://hooks.example/erev", "event_kinds": ["period.locked"]}
    headers = cookie_headers(maya.token, maya.csrf_token, key=False, **{"Idempotency-Key": key})
    created = call(app, "POST", ENDPOINTS, json=body, headers=headers)
    assert created.status_code == 201, created.text
    signing_secret = created.json()["signing_secret"]
    assert isinstance(signing_secret, str) and len(signing_secret) == 43
    with tenant_session(_db(tenant_id)) as session:
        record = session.execute(
            select(idempotency_record.c.state, idempotency_record.c.response_body).where(
                idempotency_record.c.idempotency_key == key
            )
        ).one()
    assert (record.state, record.response_body["signing_secret"]) == ("COMPLETED", None)
    assert signing_secret not in json.dumps(record.response_body)

    replay = call(app, "POST", ENDPOINTS, json=body, headers=headers)
    assert (replay.status_code, replay.headers["Idempotent-Replay"]) == (201, "true"), replay.text
    assert (replay.json()["id"], replay.json()["signing_secret"]) == (created.json()["id"], None)

    # Deliveries are still signed with the issued secret.
    files = LocalFileStore(app_settings.file_root)
    assert _emit_period_locked(tenant_id, keyring, clock, files) == 1
    received: list[HttpRequest] = []

    def respond(request: HttpRequest) -> int:
        received.append(request)
        return 204

    assert _deliver(tenant_id, keyring, clock, files, respond) == DeliveryStats(
        claimed=1, succeeded=1, failed=0, abandoned=0
    )
    [delivered] = received
    header = delivered.headers["X-Erev-Signature"]
    timestamp = int(header.split(",", 1)[0].removeprefix("t="))
    assert header == signature_header(signing_secret.encode("ascii"), timestamp, delivered.content)


def test_create_endpoint_shows_secret_once(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    maya_member, maya, victor = _people(app, keyring, clock)
    body = {"url": "https://hooks.example/erev", "event_kinds": ["period.locked"]}

    created = send(app, "POST", ENDPOINTS, maya, body)
    assert created.status_code == 201, created.text
    endpoint = created.json()
    assert set(endpoint) == ENDPOINT_KEYS | {"signing_secret"}
    assert (endpoint["url"], endpoint["event_kinds"], endpoint["is_active"]) == (
        "https://hooks.example/erev",
        ["period.locked"],
        True,
    )
    signing_secret = endpoint["signing_secret"]
    assert isinstance(signing_secret, str) and len(signing_secret) == 43
    location = f"{ENDPOINTS}/{endpoint['id']}"
    assert (created.headers["Location"], created.headers["ETag"]) == (location, '"r1"')

    read = get(app, location, maya)
    assert read.status_code == 200, read.text
    assert set(read.json()) == ENDPOINT_KEYS
    assert read.headers["ETag"] == '"r1"'
    listed = get(app, ENDPOINTS, maya)
    assert listed.status_code == 200, listed.text
    assert [set(item) for item in listed.json()["items"]] == [ENDPOINT_KEYS]
    assert signing_secret not in read.text + listed.text

    # KEY-08: the secret is sealed under the key ring and opens only under its row's context.
    endpoint_id = UUID(endpoint["id"])
    with tenant_session(_db(maya_member.tenant_id)) as session:
        stored = session.execute(
            select(webhook_endpoint.c.secret_ciphertext, webhook_endpoint.c.secret_key_id).where(
                webhook_endpoint.c.id == endpoint_id
            )
        ).one()
    ciphertext = bytes(stored.secret_ciphertext)
    assert ciphertext.startswith(b"erev1")
    assert stored.secret_key_id == keyring.envelope_key_id(ciphertext)
    context = secret_context(maya_member.tenant_id, endpoint_id)
    assert keyring.decrypt(ciphertext, context=context).decode("ascii") == signing_secret

    plain = send(app, "POST", ENDPOINTS, maya, {**body, "url": "http://hooks.example/erev"})
    assert (plain.status_code, slug(plain), fields(plain)) == (
        422,
        "validation-failed",
        [("url", "T-PLT-35")],
    ), plain.text
    unknown = send(app, "POST", ENDPOINTS, maya, {**body, "event_kinds": ["contract.created"]})
    assert (unknown.status_code, slug(unknown), fields(unknown)) == (
        422,
        "validation-failed",
        [("event_kinds", "T-PLT-35")],
    ), unknown.text
    refused = send(app, "POST", ENDPOINTS, victor, body)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    unconditional = send(app, "PATCH", location, maya, {"is_active": False})
    assert (unconditional.status_code, slug(unconditional)) == (428, "precondition-required")
    paused = send(
        app,
        "PATCH",
        location,
        maya,
        {"is_active": False, "description": "Paused"},
        **{"If-Match": '"r1"'},
    )
    assert paused.status_code == 200, paused.text
    assert (paused.json()["is_active"], paused.json()["description"], paused.headers["ETag"]) == (
        False,
        "Paused",
        '"r2"',
    )
    assert "signing_secret" not in paused.json()
    stale = send(app, "PATCH", location, maya, {"is_active": True}, **{"If-Match": '"r1"'})
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text

    # AUD-CMD: one event per command, without the secret.
    audit = get(app, "/api/v1/audit-events", maya, object_id=str(endpoint_id))
    assert audit.status_code == 200, audit.text
    assert [item["action"] for item in audit.json()["items"]] == [
        "webhook_endpoint.update",
        "webhook_endpoint.create",
    ]
    assert signing_secret not in audit.text


def test_deliveries_log_filter(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    maya_member, maya, victor = _people(app, keyring, clock)
    ids: dict[str, str] = {}
    for name in ("ok", "fail"):
        created = send(
            app,
            "POST",
            ENDPOINTS,
            maya,
            {"url": f"https://hooks.example/{name}", "event_kinds": ["period.locked"]},
        )
        assert created.status_code == 201, created.text
        ids[name] = created.json()["id"]

    tenant_id = maya_member.tenant_id
    files = LocalFileStore(app_settings.file_root)
    assert _emit_period_locked(tenant_id, keyring, clock, files) == 2

    def respond(request: HttpRequest) -> int:
        return 200 if request.url.path == "/ok" else 500

    assert _deliver(tenant_id, keyring, clock, files, respond) == DeliveryStats(
        claimed=2, succeeded=1, failed=1, abandoned=0
    )

    failed = get(app, DELIVERIES, maya, status="FAILED")
    assert failed.status_code == 200, failed.text
    [item] = failed.json()["items"]
    assert (item["webhook_endpoint_id"], item["status"], item["attempt_count"]) == (
        ids["fail"],
        "FAILED",
        1,
    )
    assert (item["last_response_status"], item["last_error"]) == (500, "HTTP 500")
    assert set(item["payload"]) == {"id", "kind", "tenant_code", "occurred_at", "data"}
    succeeded = get(app, DELIVERIES, maya, status="SUCCEEDED")
    assert [row["webhook_endpoint_id"] for row in succeeded.json()["items"]] == [ids["ok"]]
    assert len(get(app, DELIVERIES, maya).json()["items"]) == 2
    by_endpoint = get(app, DELIVERIES, maya, webhook_endpoint_id=ids["ok"])
    assert [row["status"] for row in by_endpoint.json()["items"]] == ["SUCCEEDED"]

    bogus = get(app, DELIVERIES, maya, status="DONE")
    assert (bogus.status_code, slug(bogus)) == (422, "validation-failed"), bogus.text
    hidden = get(app, DELIVERIES, victor)
    assert (hidden.status_code, slug(hidden)) == (403, "forbidden"), hidden.text
