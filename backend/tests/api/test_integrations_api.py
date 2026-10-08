"""API-R-45 integrations over a database (04 §15.3 API-R-45, §16.14; T-INT-01, T-INT-02; 05
ADP-01, ADP-14, DG-API-09 / D-72; 03 REQ-INT-006; PRD BR-INT-01, J-23.1, J-23-AC-1; BUILD_SPEC
DIN-12 named cases ``test_connection_stores_secret_reference_only`` and
``test_mock_routes_absent_in_production``).

DB-bound except ``test_mock_routes_absent_in_production`` (no database: synthetic production
settings never connected to). World: Nikhil, an Integration Admin (``integration.manage`` requires
MFA, so the actor is TOTP-enrolled) of a provisioned tenant; the connection's ``base_url``
is the in-process Salesforce mock reached through ``support.http.asgi_client`` — the test registers
that client as the adapters' HTTP client factory (DG-LAY-03) — and its ``secret_ref`` names a
secret the app's key ring serves through a ``SecretStore`` (``support.adapter_secrets``): locally
``EnvSecretStore`` serves the three master keys only (dev-guide DG-KRN-KEY-01; 05 KEY-09), so an
environment variable of that name would not resolve.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.crm import salesforce
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import integration_connection, job, source_record, sync_run
from erev_api.domain.integrations import commands
from erev_api.domain.integrations import sync as sync_module
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.adapter_secrets import (
    serve_adapter_secrets,
    serve_hosted_adapter_secrets,
    tenant_ref,
)
from support.db import TestDatabase
from support.fake_gcp import ServiceUnavailable
from support.http import HttpResponse, asgi_client, call
from support.principals import Actor, enrolled, member
from support.reference import assign, fields, get, patch, post, slug

INTEGRATIONS = "/api/v1/integrations"
SYNC_RUNS = "/api/v1/sync-runs"
MOCK_BASE = f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}"
# The workspace's Salesforce secret; its reference lies in the workspace's own namespace of the
# secret store (``World.secret_ref``; 05 KEY-09 rev 1.47, supervisor ruling R-48 (f)).
SECRET_NAME = "sf-client-secret"
SYNTHETIC_KEY = "0" * 64
SYNTHETIC_DB = "postgresql://erev_none:none@127.0.0.1:1/erev_arch_test_none"


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    nikhil: Actor
    tenant_id: UUID

    @property
    def secret_ref(self) -> str:
        return tenant_ref(self.tenant_id, SECRET_NAME)

    def rows(self, statement: Any) -> list[dict[str, Any]]:
        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Iterator[World]:
    someone = member(keyring, clock)
    assign(someone, "integration_admin")
    nikhil = enrolled(app, clock, someone)
    # ADP-14 / REQ-INT-006: the reference names a secret the key ring resolves through its
    # SecretStore; the value below is a fixture, never stored by the API.
    serve_adapter_secrets(app, {tenant_ref(someone.tenant_id, SECRET_NAME): sf_mock.SHARED_SECRET})
    salesforce.register()
    previous = sync_module._HOOKS.get("http")
    sync_module.register_http_client_factory(lambda base_url: asgi_client(app))
    try:
        yield World(app=app, nikhil=nikhil, tenant_id=someone.tenant_id)
    finally:
        sync_module.register_http_client_factory(previous)


def _connection_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "sf-quayside",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "base_url": MOCK_BASE,
        "config": {"default_performing_entity": "QUAY-US"},
        "secret_ref": None,
    }
    body.update(over)
    return body


def _create(world: World, **over: Any) -> dict[str, Any]:
    """A connection of the world; it names the workspace's secret unless the test names another."""
    body = _connection_body(**{"secret_ref": world.secret_ref, **over})
    created = post(world.app, INTEGRATIONS, world.nikhil, body)
    assert created.status_code == 201, created.text
    assert created.headers["Location"] == f"{INTEGRATIONS}/{created.json()['id']}"
    assert created.headers["ETag"] == '"r1"'
    result: dict[str, Any] = created.json()
    return result


def _activate(world: World, connection: dict[str, Any]) -> dict[str, Any]:
    changed = patch(
        world.app,
        f"{INTEGRATIONS}/{connection['id']}",
        world.nikhil,
        {"status": "ACTIVE"},
        if_match=f'"r{connection["row_version"]}"',
    )
    assert changed.status_code == 200, changed.text
    result: dict[str, Any] = changed.json()
    assert result["status"] == "ACTIVE"
    return result


def test_integration_owner_is_explicit_and_tenant_scoped(
    world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    from support.principals import colleague

    # An explicit null keeps a historical/unassigned connection unassigned.
    first = _create(world, owner_membership_id=None)
    assert first["owner_membership_id"] is None
    unqualified = colleague(world.tenant_id, "unqualified-owner")
    refused = patch(
        world.app,
        f"{INTEGRATIONS}/{first['id']}",
        world.nikhil,
        {"owner_membership_id": str(unqualified.membership_id)},
        if_match='"r1"',
    )
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("owner_membership_id", "INTEGRATION_OWNER_SCOPE")]

    assign(world.nikhil.member, "revenue_accountant")
    owned = _create(world, code="sf-owned")
    assert owned["owner_membership_id"] == str(world.nikhil.member.membership_id)
    assigned = patch(
        world.app,
        f"{INTEGRATIONS}/{first['id']}",
        world.nikhil,
        {"owner_membership_id": str(world.nikhil.member.membership_id)},
        if_match='"r1"',
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["owner_membership_id"] == owned["owner_membership_id"]

    outsider = member(keyring, clock)
    assign(outsider, "integration_admin")
    assign(outsider, "revenue_accountant")
    cross_tenant = patch(
        world.app,
        f"{INTEGRATIONS}/{first['id']}",
        world.nikhil,
        {"owner_membership_id": str(outsider.membership_id)},
        if_match='"r2"',
    )
    assert cross_tenant.status_code == 422, cross_tenant.text
    assert fields(cross_tenant) == fields(refused)
    assert (
        world.rows(
            select(integration_connection.c.owner_membership_id).where(
                integration_connection.c.id == UUID(first["id"])
            )
        )[0]["owner_membership_id"]
        == world.nikhil.member.membership_id
    )


def test_connection_stores_secret_reference_only(world: World, clock: FrozenClock) -> None:
    """BUILD_SPEC DIN-12: ``POST /integrations {…, secret_ref: <reference>}`` stores the
    reference name and no secret value; ``/test`` records ``last_test_result = SUCCESS`` and
    ``last_test_at`` in UTC through the secret store (REQ-INT-006; 05 ADP-14; PRD BR-INT-01).
    The reference names a secret of the workspace's own namespace (04 T-INT-01 rev 1.108)."""
    created = _create(world)
    assert created["secret_ref"] == world.secret_ref
    assert created["status"] == "DISABLED" and created["last_sync_run"] is None
    assert sf_mock.SHARED_SECRET not in str(created)
    [row] = world.rows(
        select(integration_connection).where(integration_connection.c.id == UUID(created["id"]))
    )
    assert row["secret_ref"] == world.secret_ref
    assert not any(str(value) == sf_mock.SHARED_SECRET for value in row.values())
    assert "secret" not in {key for key in row if key != "secret_ref"}

    tested = post(world.app, f"{INTEGRATIONS}/{created['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    body = tested.json()
    assert body["last_test_result"] == "SUCCESS"
    assert body["last_test_at"] is not None
    assert body["last_test_at"].endswith(("Z", "+00:00"))
    assert body["last_test_at"].replace("Z", "+00:00") == clock.now().isoformat()
    assert body["last_sync_run"]["status"] == "SUCCEEDED"
    assert sf_mock.SHARED_SECRET not in tested.text
    runs = world.rows(
        select(sync_run).where(sync_run.c.integration_connection_id == UUID(created["id"]))
    )
    assert [run["kind"] for run in runs] == ["TEST_CONNECTION"]
    assert runs[0]["status"] == "SUCCEEDED" and runs[0]["started_at"] == runs[0]["finished_at"]

    shown = get(world.app, f"{INTEGRATIONS}/{created['id']}", world.nikhil)
    assert shown.status_code == 200 and shown.json()["secret_ref"] == world.secret_ref  # J-23-AC-1
    assert sf_mock.SHARED_SECRET not in shown.text


def test_test_connection_records_a_failure_for_an_unresolvable_reference(world: World) -> None:
    missing = tenant_ref(world.tenant_id, "sf-missing-reference")
    created = _create(world, code="sf-noref", secret_ref=missing)
    tested = post(world.app, f"{INTEGRATIONS}/{created['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    body = tested.json()
    assert body["last_test_result"] == "FAILURE"
    assert missing in body["last_test_detail"]
    assert body["last_sync_run"]["status"] == "FAILED"


def test_p3_23_a_connection_names_only_a_secret_of_its_own_workspace(
    world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review 2026-09-29 P3-23 and the lead's finding 4 (supervisor ruling R-48 (f); 03
    REQ-INT-006; 04 T-INT-01 rev 1.108; 05 KEY-09, ADP-14 rev 1.47). As built ``secret_ref`` was
    any name the service identity could read: an Integration Admin of one workspace named the
    credential of another — or a secret of the platform — and had it read for a connection whose
    ``base_url`` it chose. A reference outside the workspace's own namespace is refused when the
    connection is saved, and is served nothing when it is read."""
    other = member(keyring, clock)  # another workspace; the store serves its secret too
    theirs = tenant_ref(other.tenant_id, SECRET_NAME)
    platform = "idp-corp-client"  # a secret of the platform: an identity provider's client secret
    serve_adapter_secrets(
        world.app, {name: sf_mock.SHARED_SECRET for name in (world.secret_ref, theirs, platform)}
    )
    namespace = f"tenant-{world.tenant_id}-"
    outside = (
        theirs,
        f"{theirs}@1",
        platform,
        "EREV_SF_CLIENT_SECRET",
        namespace,  # the bare prefix names no secret
        f"x-{world.secret_ref}",  # the prefix is the beginning of the name
        f"TENANT-{world.tenant_id}-{SECRET_NAME}",
    )

    def refusal(response: HttpResponse) -> None:
        assert response.status_code == 422, response.text
        assert slug(response) == "validation-failed"
        [error] = response.json()["errors"]
        assert (error["field"], error["rule_id"]) == ("secret_ref", "T-INT-01"), error
        assert error["message"] == (
            f"Enter the name of a secret of this workspace. It begins with {namespace} and"
            " continues after it."
        )

    # 1. Saved: POST refuses each of them and writes nothing.
    for number, reference in enumerate(outside):
        body = _connection_body(code=f"sf-outside-{number}", secret_ref=reference)
        refusal(post(world.app, INTEGRATIONS, world.nikhil, body))
    assert world.rows(select(integration_connection)) == []

    # Positive control: the workspace's own secret, by name and by pinned version, is accepted.
    own = _activate(world, _create(world))
    pinned = _create(world, code="sf-pinned", secret_ref=f"{world.secret_ref}@3")
    assert pinned["secret_ref"] == f"{world.secret_ref}@3"
    # ... and PATCH refuses the same references on an existing connection; the row keeps its own.
    for reference in outside:
        refusal(
            patch(
                world.app,
                f"{INTEGRATIONS}/{own['id']}",
                world.nikhil,
                {"secret_ref": reference},
                if_match=f'"r{own["row_version"]}"',
            )
        )
    [kept] = world.rows(
        select(integration_connection).where(integration_connection.c.id == UUID(own["id"]))
    )
    assert (kept["secret_ref"], kept["row_version"]) == (world.secret_ref, own["row_version"])

    # 2. Read: a row that names another workspace's secret all the same — written before the rule,
    #    or by any path other than the commands — is served nothing. The store holds that secret
    #    and its value signs the notification below, so a key ring that read it would verify it.
    from support.rows import integration_connection_values

    smuggled = integration_connection_values(world.tenant_id, status="ACTIVE", secret_ref=theirs)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(integration_connection.insert().values(**smuggled))
    tested = post(world.app, f"{INTEGRATIONS}/{smuggled['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert (tested.json()["last_test_result"], tested.json()["last_test_detail"]) == (
        "FAILURE",
        f"secret reference {theirs} is not resolvable",
    )
    body = (
        b'{"events": [{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001",'
        b' "version": "1", "replayId": 1}]}'
    )
    with asgi_client(world.app) as client:
        signed = client.post(f"{MOCK_BASE}/webhooks/sign", content=body).json()
    header = {signed["header"]: signed["signature"]}

    def notified(connection_id: str) -> HttpResponse:
        receiver = commands.receiver_id(world.tenant_id, UUID(connection_id))
        path = f"/api/v1/webhooks/SALESFORCE/{receiver}"
        return call(world.app, "POST", path, content=body, headers=header)

    refused = notified(str(smuggled["id"]))
    assert (refused.status_code, slug(refused)) == (401, "unauthenticated"), refused.text
    assert world.rows(select(sync_run).where(sync_run.c.kind == "WEBHOOK_BATCH")) == []

    # Positive control: the same notification reaches the connection that names its own secret.
    accepted = notified(own["id"])
    assert accepted.status_code == 202, accepted.text
    [batch] = world.rows(select(sync_run).where(sync_run.c.kind == "WEBHOOK_BATCH"))
    assert str(batch["integration_connection_id"]) == own["id"]


def test_sync_queues_a_run_and_its_job_only_for_an_active_connection(world: World) -> None:
    created = _create(world)
    refused = post(world.app, f"{INTEGRATIONS}/{created['id']}/sync", world.nikhil, {})
    assert refused.status_code == 409 and slug(refused) == "invalid-transition"
    active = _activate(world, created)
    accepted = post(world.app, f"{INTEGRATIONS}/{active['id']}/sync", world.nikhil, {})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    assert accepted.headers["Location"] == f"/api/v1/jobs/{job_id}"
    run_id = accepted.headers["X-Erev-Sync-Run-Id"]
    [run] = world.rows(select(sync_run).where(sync_run.c.id == UUID(run_id)))
    assert run["kind"] == "INBOUND_POLL" and run["status"] == "QUEUED"
    assert str(run["job_id"]) == job_id and run["checkpoint_before"] == {}
    [queued] = world.rows(select(job.c.kind, job.c.params).where(job.c.id == UUID(job_id)))
    assert queued["kind"] == "SYNC_RUN" and queued["params"]["sync_run_id"] == run_id
    listed = get(world.app, SYNC_RUNS, world.nikhil, {"connection": active["id"]})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [run_id]
    assert listed.json()["items"][0]["duration_seconds"] is None
    wrong_kind = post(
        world.app, f"{INTEGRATIONS}/{active['id']}/sync", world.nikhil, {"kind": "COA_SYNC"}
    )
    assert wrong_kind.status_code == 422 and slug(wrong_kind) == "validation-failed"


def test_update_requires_if_match_and_audits_field_changes(world: World) -> None:
    created = _create(world)
    missing = patch(
        world.app, f"{INTEGRATIONS}/{created['id']}", world.nikhil, {"name": "CRM"}, if_match=None
    )
    assert missing.status_code == 428 and slug(missing) == "precondition-required"
    stale = patch(
        world.app, f"{INTEGRATIONS}/{created['id']}", world.nikhil, {"name": "CRM"}, if_match='"r9"'
    )
    assert stale.status_code == 412 and slug(stale) == "precondition-failed"
    changed = patch(
        world.app, f"{INTEGRATIONS}/{created['id']}", world.nikhil, {"name": "CRM"}, if_match='"r1"'
    )
    assert changed.status_code == 200 and changed.json()["name"] == "CRM"
    assert changed.headers["ETag"] == '"r2"'
    unknown_entity = patch(
        world.app,
        f"{INTEGRATIONS}/{created['id']}",
        world.nikhil,
        {"entity_ids": [str(UUID(int=99))]},
        if_match='"r2"',
    )
    assert unknown_entity.status_code == 422 and slug(unknown_entity) == "validation-failed"


def test_webhook_receiver_verifies_the_signature_and_stores_only_a_run(world: World) -> None:
    """05 ADP-01 at the route: a valid signature answers 202 with a ``WEBHOOK_BATCH`` sync run and a
    queued ``SYNC_RUN`` job and stores no source record; every refusal is one 401."""
    active = _activate(world, _create(world))
    receiver = commands.receiver_id(world.tenant_id, UUID(active["id"]))
    body = (
        b'{"events": [{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001",'
        b' "version": "1", "replayId": 1}]}'
    )
    with asgi_client(world.app) as client:
        signed = client.post(f"{MOCK_BASE}/webhooks/sign", content=body)
    assert signed.status_code == 200, signed.text
    header = {signed.json()["header"]: signed.json()["signature"]}
    path = f"/api/v1/webhooks/SALESFORCE/{receiver}"

    accepted = call(world.app, "POST", path, content=body, headers=header)
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["notifications"] == 1
    run_id = UUID(accepted.json()["sync_run_id"])
    [run] = world.rows(select(sync_run).where(sync_run.c.id == run_id))
    assert run["kind"] == "WEBHOOK_BATCH" and run["status"] == "QUEUED"
    assert str(run["job_id"]) == accepted.json()["job_id"]
    assert world.rows(select(func.count()).select_from(source_record))[0]["count_1"] == 0

    wrong_signature = call(
        world.app, "POST", path, content=body, headers={"X-Erev-Mock-Signature": "0" * 64}
    )
    assert wrong_signature.status_code == 401 and slug(wrong_signature) == "unauthenticated"
    no_header = call(world.app, "POST", path, content=body)
    assert no_header.status_code == 401
    other_adapter = call(
        world.app, "POST", f"/api/v1/webhooks/STRIPE/{receiver}", content=body, headers=header
    )
    assert other_adapter.status_code == 401
    unknown = call(
        world.app,
        "POST",
        f"/api/v1/webhooks/SALESFORCE/{UUID(int=5)}",
        content=body,
        headers=header,
    )
    assert unknown.status_code == 401
    assert (
        wrong_signature.json()["detail"] == no_header.json()["detail"] == unknown.json()["detail"]
    )


def hosted_refusals(world: World) -> tuple[tuple[str, str], ...]:
    """What the hosted store will not serve inside the workspace's namespace (05 KEY-09, SAR-25),
    each with why. A reference outside the namespace — the unprefixed DIN-12 name, a database URL
    — is refused when the connection is saved (``test_p3_23_…`` below)."""
    hosted = world.secret_ref  # a Secret Manager secret name; `<name>@1` is its reference
    return (
        (hosted, "not pinned as <name>@<version>"),
        (f"{hosted}@latest", "latest is never read"),
        (f"{tenant_ref(world.tenant_id, 'sf-absent')}@1", "no such secret"),
        (f"{hosted}@7", "no such version"),
    )


def _signed(world: World, body: bytes) -> dict[str, str]:
    with asgi_client(world.app) as client:
        signed = client.post(f"{MOCK_BASE}/webhooks/sign", content=body)
    assert signed.status_code == 200, signed.text
    return {signed.json()["header"]: signed.json()["signature"]}


def _webhook(world: World, connection: dict[str, Any], body: bytes) -> tuple[Any, list[str]]:
    """The receiver's answer to a VALIDLY signed notification, and the refusal reasons it logged."""
    import structlog.testing

    receiver = commands.receiver_id(world.tenant_id, UUID(connection["id"]))
    with structlog.testing.capture_logs() as logged:
        answered = call(
            world.app,
            "POST",
            f"/api/v1/webhooks/SALESFORCE/{receiver}",
            content=body,
            headers=_signed(world, body),
        )
    reasons = [entry["reason"] for entry in logged if entry.get("event") == "webhook.refused"]
    return answered, reasons


def test_hosted_store_refusals_fail_the_probe_and_answer_the_uniform_401(world: World) -> None:
    """05 ADP-01, ADP-14 on the HOSTED secret path (the real ``GcpKeyProvider.secret`` over the
    fake Secret Manager): a ``secret_ref`` the store will not serve — not pinned, absent, or
    denied to the identity — makes ``/test`` record FAILURE naming the reference and the
    webhook receiver answer its one 401 with the reason logged, never a 500; the pinned reference
    of a secret the store serves passes both. The local provider refuses alike
    (``test_test_connection_records_a_failure_for_an_unresolvable_reference``)."""
    hosted = world.secret_ref
    serve_hosted_adapter_secrets(world.app, {hosted: sf_mock.SHARED_SECRET})
    body = (
        b'{"events": [{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001",'
        b' "version": "1", "replayId": 1}]}'
    )

    served = _activate(world, _create(world, code="sf-hosted", secret_ref=f"{hosted}@1"))
    tested = post(world.app, f"{INTEGRATIONS}/{served['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_test_result"] == "SUCCESS"
    assert sf_mock.SHARED_SECRET not in tested.text
    accepted, reasons = _webhook(world, served, body)
    assert accepted.status_code == 202 and reasons == [], accepted.text

    for number, (reference, why) in enumerate(hosted_refusals(world)):
        refused = _activate(
            world, _create(world, code=f"sf-refused-{number}", secret_ref=reference)
        )
        tested = post(world.app, f"{INTEGRATIONS}/{refused['id']}/test", world.nikhil, {})
        assert tested.status_code == 200, (why, tested.text)
        assert tested.json()["last_test_result"] == "FAILURE", why
        assert tested.json()["last_test_detail"] == (
            f"secret reference {reference} is not resolvable"
        ), why
        assert tested.json()["last_sync_run"]["status"] == "FAILED", why
        answered, reasons = _webhook(world, refused, body)
        assert (answered.status_code, slug(answered)) == (401, "unauthenticated"), (
            why,
            answered.text,
        )
        assert reasons == ["secret_ref not resolvable"], why

    # An identity the store denies (no accessor grant on the secret): refused alike.
    serve_hosted_adapter_secrets(
        world.app, {hosted: sf_mock.SHARED_SECRET}, permissions=frozenset()
    )
    tested = post(world.app, f"{INTEGRATIONS}/{served['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_test_result"] == "FAILURE"
    assert tested.json()["last_test_detail"] == (f"secret reference {hosted}@1 is not resolvable")
    answered, reasons = _webhook(world, served, body)
    assert (answered.status_code, slug(answered)) == (401, "unauthenticated"), answered.text
    assert reasons == ["secret_ref not resolvable"]
    runs = world.rows(
        select(func.count()).select_from(sync_run).where(sync_run.c.kind == "WEBHOOK_BATCH")
    )
    assert runs[0]["count_1"] == 1  # only the served reference's notification was accepted


def test_a_silent_secret_store_fails_the_probe_and_keeps_the_receivers_5xx(world: World) -> None:
    """04 §16.14 rev 1.115 (ruling R-45 (c)) on the hosted path: a Secret Manager that does not
    answer — a transient provider failure, no refusal — makes ``/test`` record FAILURE with a
    detail that names the reference and says the store did not answer (it was an unhandled error,
    a 500, and nothing recorded); the webhook receiver keeps its 5xx for the same outage, so the
    source retries the notification instead of reading the uniform 401 of a bad signature. Both
    recover with the store: the next probe and the redelivered notification succeed."""
    hosted = world.secret_ref
    manager = serve_hosted_adapter_secrets(world.app, {hosted: sf_mock.SHARED_SECRET})
    body = (
        b'{"events": [{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001",'
        b' "version": "1", "replayId": 1}]}'
    )
    served = _activate(world, _create(world, code="sf-hosted", secret_ref=f"{hosted}@1"))

    manager.faults.fail_next("access_secret_version", ServiceUnavailable())
    tested = post(world.app, f"{INTEGRATIONS}/{served['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_test_result"] == "FAILURE"
    assert tested.json()["last_test_detail"] == (
        f"the secret store did not answer for secret reference {hosted}@1"
    )
    assert tested.json()["last_sync_run"]["status"] == "FAILED"
    # The exact safe detail is checked above; arbitrary UUIDs may contain "503".
    assert sf_mock.SHARED_SECRET not in tested.text
    again = post(world.app, f"{INTEGRATIONS}/{served['id']}/test", world.nikhil, {})
    assert again.status_code == 200, again.text
    assert again.json()["last_test_result"] == "SUCCESS"  # the store answers again

    manager.faults.fail_next("access_secret_version", ServiceUnavailable())
    unanswered, reasons = _webhook(world, served, body)
    assert unanswered.status_code >= 500, unanswered.text
    assert reasons == []  # no refusal was logged: the receiver did not judge the notification
    assert sf_mock.SHARED_SECRET not in unanswered.text
    batches = select(func.count()).select_from(sync_run).where(sync_run.c.kind == "WEBHOOK_BATCH")
    assert world.rows(batches)[0]["count_1"] == 0
    redelivered, reasons = _webhook(world, served, body)
    assert redelivered.status_code == 202 and reasons == [], redelivered.text
    assert world.rows(batches)[0]["count_1"] == 1


def _loaded_sandbox(keyring: KeyRing, clock: FrozenClock) -> UUID:
    """A sandbox tenant as a snapshot load leaves it for this scenario (05 SBX-04): the tenant row
    of kind ``sandbox`` (``kind`` is immutable, 04 T-PLT-01, so a provisioned production tenant
    cannot become one), its audit chain head (load step 2, as ``provision_tenant`` writes it last)
    and the ten system roles with their grants (the COPIED ``role`` / ``role_permission`` datasets,
    here the product's own ``default_role_rows``). ``insert_sandbox_tenant`` alone has none of
    them, so no member of it could hold a role or write an audit event."""
    from erev_api.db.session import name_platform_tenant, platform_session, set_tenant_context
    from erev_api.db.tables import role, role_permission
    from erev_api.db.tables.platform import audit_chain_head
    from erev_api.domain.platform.provisioning import default_role_rows
    from support.rows import insert_sandbox_tenant

    sandbox = insert_sandbox_tenant(keyring)
    context = DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
    now = clock.now()
    stamp = {
        "created_at": now,
        "created_by": None,
        "created_by_kind": "SYSTEM",
        "updated_at": now,
        "updated_by": None,
        "updated_by_kind": "SYSTEM",
    }
    roles, grants = default_role_rows(sandbox, stamp=stamp)
    with platform_session(
        "provisioning", actor_user_id=None, request_id="tests-sandbox-load", keyring=keyring
    ) as session:
        name_platform_tenant(session, sandbox)
        set_tenant_context(session, context)
        session.execute(role.insert(), roles)
        session.execute(role_permission.insert(), grants)
        session.execute(
            audit_chain_head.insert().values(tenant_id=sandbox, last_chain_seq=0, updated_at=now)
        )
    return sandbox


def test_sandbox_refuses_inbound_connections_and_audits_the_attempt(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """05 SBX-08 (Codex 0339 §3 DIN12-SANDBOX-ADMISSION-1): in a sandbox tenant an inbound
    connection cannot be created (403 ``sandbox-restricted``, audited DENIED in its own
    transaction, nothing written), a CSV_GL export connection can (DISABLED; DB-15 refuses its
    activation), and the webhook receiver answers the uniform 401."""
    from erev_api.db.tables import audit_event
    from support.principals import colleague

    sandbox = _loaded_sandbox(keyring, clock)
    someone = colleague(sandbox, "nikhil")
    assign(someone, "integration_admin")
    nikhil = enrolled(app, clock, someone)
    secret_ref = tenant_ref(sandbox, SECRET_NAME)
    refused = post(app, INTEGRATIONS, nikhil, _connection_body(secret_ref=secret_ref))
    assert refused.status_code == 403 and slug(refused) == "sandbox-restricted"
    context = DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        denied = [
            dict(row)
            for row in session.execute(
                select(audit_event).where(
                    audit_event.c.action == "integration_connection.create",
                    audit_event.c.outcome == "DENIED",
                )
            ).mappings()
        ]
        rows = session.execute(
            select(func.count()).select_from(integration_connection)
        ).scalar_one()
    assert len(denied) == 1 and denied[0]["detail"]["problem"] == "sandbox-restricted"
    assert rows == 0  # nothing was written in the refused command's transaction
    exported = post(
        app,
        INTEGRATIONS,
        nikhil,
        _connection_body(code="csv-gl", adapter="CSV_GL", direction="OUTBOUND", secret_ref=None),
    )
    assert exported.status_code == 201 and exported.json()["status"] == "DISABLED"
    # Codex 0417 §3: only the SANDBOX branch may refuse this — an ACTIVE inbound connection whose
    # secret IS resolvable (the ``world`` fixture is not requested here, so the synthetic secret is
    # served explicitly; Codex 0505 §2 (c)), inserted directly (the API refuses to create one), and
    # a VALID signature over the body.
    import structlog.testing

    serve_adapter_secrets(app, {secret_ref: sf_mock.SHARED_SECRET})
    from erev_api.db.tables import job, sync_run
    from support.rows import integration_connection_values

    active = integration_connection_values(sandbox, status="ACTIVE", secret_ref=secret_ref)
    with tenant_session(context) as session:
        session.execute(integration_connection.insert().values(**active))
    receiver = commands.receiver_id(sandbox, UUID(str(active["id"])))
    body = (
        b'{"events": [{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001",'
        b' "version": "1", "replayId": 1}]}'
    )
    with asgi_client(app) as client:
        signed = client.post(f"{MOCK_BASE}/webhooks/sign", content=body).json()
    with structlog.testing.capture_logs() as logged:
        answered = call(
            app,
            "POST",
            f"/api/v1/webhooks/SALESFORCE/{receiver}",
            content=body,
            headers={signed["header"]: signed["signature"]},
        )
    assert answered.status_code == 401 and slug(answered) == "unauthenticated"
    refusals = [entry for entry in logged if entry.get("event") == "webhook.refused"]
    assert [entry["reason"] for entry in refusals] == ["sandbox tenant"]
    with tenant_session(context, read_only=True) as session:
        runs = session.execute(select(func.count()).select_from(sync_run)).scalar_one()
        jobs = session.execute(select(func.count()).select_from(job)).scalar_one()
    assert runs == 0 and jobs == 0  # nothing queued before the refusal


def test_base_url_is_held_to_the_static_rule_under_production(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-INT-01 rev 1.115 and 05 SAR-15 rev 1.54 (ruling R-45 (c)): a test deployment keeps
    the in-process mock URL; the same routes under ``EREV_ENV=production`` refuse at create and at
    update a ``base_url`` that is not a public https address — 422 ``validation-failed`` naming
    ``base_url``, nothing written — and admit one that is."""
    kept = _create(world)  # dev / test / e2e: the mock URL stands
    assert kept["base_url"] == MOCK_BASE

    production = world.app.state.settings.model_copy(update={"env": Environment.PRODUCTION})
    monkeypatch.setattr(world.app.state, "settings", production)
    for url, reason in (
        (MOCK_BASE, "it does not use https"),
        ("http://acme.my.salesforce.com", "it does not use https"),
        ("https://127.0.0.1:8190/api/v1/__mocks__/salesforce", "non-public address"),
        ("https://169.254.169.254/latest", "non-public address"),
        ("https://crm.corp.internal", "it names a local host"),
        ("https://intranet", "it names a single-label host"),
        ("https://127.1/services", "a form other than dotted decimal"),
    ):
        refused = post(
            world.app,
            INTEGRATIONS,
            world.nikhil,
            _connection_body(code="sf-prod", base_url=url, secret_ref=world.secret_ref),
        )
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), (
            url,
            refused.text,
        )
        [error] = refused.json()["errors"]
        assert error["field"] == "base_url" and reason in error["message"], (url, error)
    assert [row["code"] for row in world.rows(select(integration_connection))] == ["sf-quayside"]

    public = post(
        world.app,
        INTEGRATIONS,
        world.nikhil,
        _connection_body(
            code="sf-prod",
            base_url="https://acme.my.salesforce.com",
            secret_ref=world.secret_ref,
        ),
    )
    assert public.status_code == 201, public.text
    moved = patch(
        world.app,
        f"{INTEGRATIONS}/{public.json()['id']}",
        world.nikhil,
        {"base_url": "https://10.20.30.40/services"},
        if_match='"r1"',
    )
    assert (moved.status_code, slug(moved)) == (422, "validation-failed"), moved.text
    assert [error["field"] for error in moved.json()["errors"]] == ["base_url"]
    renamed = patch(
        world.app,
        f"{INTEGRATIONS}/{public.json()['id']}",
        world.nikhil,
        {"name": "Salesforce", "base_url": "https://acme.my.salesforce.com/services/data"},
        if_match='"r1"',
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["base_url"] == "https://acme.my.salesforce.com/services/data"


def test_integration_permission_is_required(
    world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    someone = member(keyring, clock)
    assign(someone, "viewer")
    viewer = enrolled(world.app, clock, someone)
    assert get(world.app, INTEGRATIONS, viewer).status_code == 403
    body = _connection_body(secret_ref=world.secret_ref)
    assert post(world.app, INTEGRATIONS, viewer, body).status_code == 403


# --- DG-API-09 / D-72 (no database) ---------------------------------------------------------------


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: str, env: str) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_"):
            monkeypatch.delenv(name)
    values = {
        "EREV_ENV": env,
        "EREV_DB_OWNER_URL": SYNTHETIC_DB,
        "EREV_DB_APP_URL": SYNTHETIC_DB,
        "EREV_TEST_DB_OWNER_URL": SYNTHETIC_DB,
        "EREV_TEST_DB_APP_URL": SYNTHETIC_DB,
        "EREV_ENCRYPTION_KEY": SYNTHETIC_KEY,
        "EREV_AUDIT_HMAC_MASTER_KEY": SYNTHETIC_KEY,
        "EREV_SECURITY_EVENT_HMAC_KEY": SYNTHETIC_KEY,
        "EREV_SECURITY_HMAC_SECRET_VERSION": "1",  # 05 KEY-03: production pins the version
        "EREV_FILE_ROOT": tmp_path,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_mock_routes_absent_in_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """BUILD_SPEC DIN-12: an app built with ``EREV_ENV=production`` has no ``/api/v1/__mocks__``
    route and the OpenAPI document never lists them (DG-ARC-04; D-72); the API-R-45 routes and the
    ADP-01 receiver are mounted in every environment."""
    settings = _settings(monkeypatch, str(tmp_path), "production")
    assert settings.env is Environment.PRODUCTION
    app = create_app(settings)
    assert mocks.mounted_mock_routes(app) == []
    document = app.openapi()
    assert not any(path.startswith(mocks.MOCKS_PREFIX) for path in document["paths"])
    assert f"{INTEGRATIONS}/{{connection_id}}/sync" in document["paths"]
    assert "/api/v1/webhooks/{adapter}/{connection_id}" in document["paths"]


def test_owner_assignment_prevents_lossy_downgrade(
    world: World, committed_db: TestDatabase
) -> None:
    import importlib

    from erev_api.db import migration_ops
    from sqlalchemy.exc import IntegrityError

    created = _create(world)
    assert created["owner_membership_id"] is not None
    migration = importlib.import_module("erev_api.db.migrations.versions.0140_integration_owner")
    # No tenant context: the physical validation must still find the assignment through RLS.
    with committed_db.owner_engine.connect() as conn:
        transaction = conn.begin()
        try:
            with migration_ops.bound_to(conn), pytest.raises(IntegrityError, match="0140_no_owner"):
                migration.downgrade()
        finally:
            transaction.rollback()
    assert (
        world.rows(select(integration_connection.c.owner_membership_id))[0]["owner_membership_id"]
        == world.nikhil.member.membership_id
    )
