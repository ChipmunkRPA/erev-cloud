"""BUILD_SPEC SNP-4 — what a sandbox may not do, and that a workspace's type is fixed (05 §10
SBX-08 rev 1.116; 04 §14.1 DB-05 and DB-15 rev 1.125, API-R-04, API-R-15, API-R-45; 03 REQ-PLT-003,
REQ-PLT-022, REQ-PLT-024; PRD ERR-17, ERR-25, ERR-26, BR-FC-03; control CTL-043), with the
regression of security finding SF-1 (supervisor ruling R-33).

Every refusal is asserted the same way: the status and the problem type, the ``DENIED`` audit
event the guard wrote in a transaction of its own, and that nothing of the refused command was
written. Each has a positive control — the same command where it is allowed — so that a refusal
cannot pass because the request was malformed.

The sandbox is ``support.snapshots.seeded_sandbox``: a tenant row of kind ``sandbox`` with its
system roles and its audit chain head, as the first steps of a load leave it. Its members sign in
and send the commands through the API. The SF-1 case calls the two domain functions the reviewer's
proof called (lane SEC, helper sec-fe, case B1) and then the emission and the delivery, which no
route reaches directly. ``tests/api/test_tenant_header.py`` holds the API-C-02 header case.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.controls.release import current_release
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    audit_event,
    integration_connection,
    job,
    journal_batch,
    journal_run,
    outbox_message,
    sync_run,
    tenant,
    tenant_membership,
    tenant_snapshot,
    webhook_delivery,
    webhook_endpoint,
)
from erev_api.domain.integrations import commands as integration_commands
from erev_api.domain.integrations import sync as integration_sync
from erev_api.domain.platform import sandbox_reset, webhook_endpoints
from erev_api.enums import JobKind, MembershipStatus, OutboxTopic, PrincipalKind, TenantKind
from erev_api.events import webhooks
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext, JobRuntime, system_unit_of_work
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import Executable, exc, func, insert, select, update
from sqlalchemy.orm import Session
from support.adapter_secrets import tenant_ref
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.http import HttpRequest, mock_transport
from support.principals import Actor, Member, colleague, enrolled, member
from support.reference import assign, get, patch, post, slug
from support.rows import (
    RowContext,
    insert_app_user,
    insert_journal_rows,
    insert_sandbox_tenant,
    insert_sealed_webhook_endpoint,
    integration_connection_values,
    membership_row,
    tenant_snapshot_values,
    webhook_endpoint_values,
)
from support.snapshots import seeded_sandbox

API = "/api/v1"
RUNS = f"{API}/journal-runs"
BATCHES = f"{API}/journal-batches"
INTEGRATIONS = f"{API}/integrations"
ENDPOINTS = f"{API}/webhook-endpoints"
TENANT = f"{API}/tenant"
RESET = f"{API}/tenant/reset"
RESTRICTED = "sandbox-restricted"
ERR_17 = "Sandbox workspaces cannot post or export journals."
ERR_26 = "A workspace's type is fixed when it is created."
EVENT_KIND = "period.locked"
ENDPOINT_BODY = {"url": "https://hooks.example/erev", "event_kinds": [EVENT_KIND]}
TRIGGER = "tg_webhook_endpoint__sandbox"
PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    """The app with the release its startup would stamp (05 REL-03)."""
    application = create_app(app_settings, clock=clock)
    stamp_test_release()
    application.state.engine_release = current_release()
    return application


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _holding(app: FastAPI, clock: FrozenClock, tenant_id: UUID, name: str, role: str) -> Actor:
    """A member of ``tenant_id`` holding the system role ``role`` for every entity, signed in
    with a verified second factor and the workspace open."""
    someone = colleague(tenant_id, name)
    assign(someone, role)
    return enrolled(app, clock, someone)


def _production(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, role: str
) -> tuple[Actor, Member]:
    """A provisioned production tenant whose administrator also holds ``role``."""
    lena = member(keyring, clock)
    assign(lena, role)
    return enrolled(app, clock, lena), lena


def _denied(tenant_id: UUID) -> list[dict[str, Any]]:
    """The ``DENIED`` audit events of the tenant, oldest first."""
    statement = (
        select(
            audit_event.c.action,
            audit_event.c.object_type,
            audit_event.c.object_id,
            audit_event.c.actor_id,
            audit_event.c.detail,
        )
        .where(audit_event.c.outcome == "DENIED")
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _count(tenant_id: UUID, table: Any, *where: Any) -> int:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return int(
            session.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
        )


def _fails(session: Session, statement: Executable) -> tuple[str | None, str]:
    """SQLSTATE and message of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    orig = excinfo.value.orig
    diag = getattr(orig, "diag", None)
    return getattr(orig, "sqlstate", None), str(getattr(diag, "message_primary", "") or "")


def _approved_run(tenant_id: UUID) -> tuple[UUID, UUID, str]:
    """An approved journal run with one approved CSV batch of two lines: (run, batch, external
    id of the batch)."""
    with tenant_session(_context(tenant_id)) as session:
        rows = insert_journal_rows(session, tenant_id)
        for table, row_id in ((journal_batch, rows.batch["id"]), (journal_run, rows.run["id"])):
            session.execute(update(table).where(table.c.id == row_id).values(state="approved"))
    return rows.run["id"], rows.batch["id"], str(rows.batch["external_id"])


def _export_state(tenant_id: UUID, batch_id: UUID) -> tuple[int, int, str, Any, Any]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        messages = session.execute(
            select(func.count())
            .select_from(outbox_message)
            .where(outbox_message.c.topic == OutboxTopic.JOURNAL_EXPORT.value)
        ).scalar_one()
        jobs = session.execute(
            select(func.count()).select_from(job).where(job.c.kind == JobKind.JOURNAL_EXPORT.value)
        ).scalar_one()
        stored = session.execute(
            select(
                journal_batch.c.state,
                journal_batch.c.outbox_message_id,
                journal_batch.c.export_file_id,
            ).where(journal_batch.c.id == batch_id)
        ).one()
    return (
        int(messages),
        int(jobs),
        str(stored.state),
        stored.outbox_message_id,
        stored.export_file_id,
    )


# --- the journal export (CTL-043) -----------------------------------------------------------------


@pytest.mark.control("CTL-043")
def test_ctl_043_sandbox_adapter_export_blocked(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """REQ-PLT-022 / ERR-17: in a sandbox ``POST /journal-runs/{id}/export`` with adapter
    ``NETSUITE`` answers 403 ``sandbox-restricted`` with the catalogue sentence and leaves a
    ``DENIED`` audit event; no export message, job or state change is written; the CSV download of
    the same batch succeeds; ``POST /journal-batches/{id}/retry`` and ``POST
    /journal-batches/{id}/hand-over`` are refused the same way. The export is accepted in a
    production tenant."""
    sandbox = seeded_sandbox(keyring, clock)
    run_id, batch_id, external_id = _approved_run(sandbox)
    kofi = _holding(app, clock, sandbox, "kofi", "revenue_accountant")

    refused = post(app, f"{RUNS}/{run_id}/export", kofi, {"adapter": "NETSUITE"})
    assert (refused.status_code, slug(refused)) == (403, RESTRICTED), refused.text
    assert refused.json()["detail"] == ERR_17
    assert refused.headers["X-Erev-Tenant-Kind"] == "sandbox"
    # The restriction is the tenant's, not the adapter's: the run's own adapter is refused too.
    own = post(app, f"{RUNS}/{run_id}/export", kofi, {})
    assert (own.status_code, slug(own), own.json()["detail"]) == (403, RESTRICTED, ERR_17)

    denials = _denied(sandbox)
    assert [(d["action"], d["object_type"], d["object_id"], d["actor_id"]) for d in denials] == [
        ("journal_run.request_export", "journal_run", run_id, kofi.member.user_id)
    ] * 2
    assert [d["detail"] for d in denials] == [
        {"adapter": "NETSUITE", "problem": RESTRICTED},
        {"adapter": None, "problem": RESTRICTED},
    ]
    assert _export_state(sandbox, batch_id) == (0, 0, "approved", None, None)
    assert _count(sandbox, outbox_message) == 0  # of any topic: a sandbox has no outbox

    download = get(app, f"{BATCHES}/{batch_id}/download", kofi)
    assert download.status_code == 200, download.text
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    name = external_id.replace(":", "_")
    [_, *lines] = list(csv.reader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))
    manifest = json.loads(archive.read(f"{name}.manifest.json"))
    assert (len(lines), manifest["row_count"]) == (2, 2)
    assert _count(sandbox, audit_event, audit_event.c.action == "journal_batch.download") == 1
    assert len(_denied(sandbox)) == 2  # the download added none

    # The retry of a failed batch exports again (BUILD_SPEC CLO-14): the same refusal through the
    # same guard, before the batch's state is looked at, and nothing is queued.
    retried = post(app, f"{BATCHES}/{batch_id}/retry", kofi, {})
    assert (retried.status_code, slug(retried)) == (403, RESTRICTED), retried.text
    assert retried.json()["detail"] == ERR_17
    [_, _, denied_retry] = _denied(sandbox)
    assert denied_retry == {
        "action": "journal_batch.retry",
        "object_type": "journal_batch",
        "object_id": batch_id,
        "actor_id": kofi.member.user_id,
        "detail": {"problem": RESTRICTED},
    }
    assert _export_state(sandbox, batch_id) == (0, 0, "approved", None, None)

    # The hand-over of a failed batch exports it as its file (05 SBX-08 rev 1.98; item
    # JRN-FAILED-CANCEL-1): the same guard, before the batch's state is looked at.
    handed = post(app, f"{BATCHES}/{batch_id}/hand-over", kofi, {})
    assert (handed.status_code, slug(handed)) == (403, RESTRICTED), handed.text
    assert handed.json()["detail"] == ERR_17
    [_, _, _, denied_hand_over] = _denied(sandbox)
    assert denied_hand_over == {
        "action": "journal_batch.request_hand_over",
        "object_type": "journal_batch",
        "object_id": batch_id,
        "actor_id": kofi.member.user_id,
        "detail": {"problem": RESTRICTED},
    }
    assert _export_state(sandbox, batch_id) == (0, 0, "approved", None, None)

    # Positive control: the same request is an accepted export in a production tenant.
    accountant, lena = _production(app, keyring, clock, "revenue_accountant")
    production_run, production_batch, _ = _approved_run(lena.tenant_id)
    accepted = post(app, f"{RUNS}/{production_run}/export", accountant, {})
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["kind"] == "JOURNAL_EXPORT"
    assert accepted.headers["X-Erev-Tenant-Kind"] == "production"
    messages, jobs, state, message_id, _ = _export_state(lena.tenant_id, production_batch)
    assert (messages, jobs, state) == (1, 1, "approved") and message_id is not None
    assert _denied(lena.tenant_id) == []


# --- restore and reset never touch production (CTL-043) -------------------------------------------


@pytest.mark.control("CTL-043")
def test_ctl_043_no_restore_over_production(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """REQ-PLT-024: no route accepts a production target. ``POST /tenant/reset`` in a production
    tenant answers 409 ``production-reset-forbidden`` (ERR-25) and changes nothing; no command of
    the API takes a tenant as the target of a copy; and the database refuses a snapshot row that
    names a production tenant as its target (DB-15, ``EREV-SBX-001``) while it accepts a sandbox."""
    controller, lena = _production(app, keyring, clock, "controller")
    production = lena.tenant_id
    for mode in ("SNAPSHOT", "EMPTY"):
        refused = post(app, RESET, controller, {"mode": mode, "reason": "Start the quarter over"})
        assert (refused.status_code, slug(refused)) == (409, "production-reset-forbidden")
        assert refused.json()["detail"] == sandbox_reset.PRODUCTION_RESET
    with tenant_session(_context(production), read_only=True) as session:
        kind, status = session.execute(
            select(tenant.c.kind, tenant.c.status).where(tenant.c.id == production)
        ).one()
    assert (str(kind), str(status)) == ("production", "ACTIVE")
    assert _count(production, job, job.c.kind == JobKind.SANDBOX_RESET.value) == 0

    # The copy, restore and reset commands name a snapshot, never a tenant: the one request member
    # of the whole API that names a tenant opens a workspace.
    document = app.openapi()
    naming_a_tenant = set()
    for path, item in document["paths"].items():
        for method, operation in item.items():
            content = operation.get("requestBody", {}).get("content", {}) if method != "get" else {}
            schema = content.get("application/json", {}).get("schema", {})
            while "$ref" in schema:
                schema = document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
            for name in schema.get("properties", {}):
                if name.endswith("tenant_id"):
                    naming_a_tenant.add((path, name))
    assert naming_a_tenant == {(f"{API}/session/tenant", "tenant_id")}

    # DB-15: whatever writes the row, its target is a sandbox.
    other_production = tenant_id_of(tenant_factory(keyring=keyring))
    sandbox = insert_sandbox_tenant(keyring)
    with identity_session(request_id="tests-ctl-043-user") as session:
        user_id = insert_app_user(session)

    def join(tenant_id: UUID) -> None:
        with tenant_session(_context(tenant_id)) as db:
            db.execute(
                insert(tenant_membership).values(
                    **membership_row(RowContext(tenant_id, user_id), status=MembershipStatus.ACTIVE)
                )
            )

    for tenant_id in (production, other_production, sandbox):
        join(tenant_id)
    row = tenant_snapshot_values(production)

    def target(tenant_id: UUID) -> Executable:
        return (
            update(tenant_snapshot)
            .where(tenant_snapshot.c.id == row["id"])
            .values(target_tenant_id=tenant_id)
        )

    actor = DbContext(tenant_id=production, user_id=user_id, entity_scope="*")
    with tenant_session(actor) as session:
        session.execute(insert(tenant_snapshot).values(**row))
        for refused_target in (production, other_production):
            state, message = _fails(session, target(refused_target))
            assert state == "P0001" and message.startswith("EREV-SBX-001"), message
            assert "of kind production" in message
        session.execute(target(sandbox))  # the positive control
    with tenant_session(_context(production), read_only=True) as session:
        stored = session.execute(
            select(tenant_snapshot.c.target_tenant_id).where(tenant_snapshot.c.id == row["id"])
        ).scalar_one()
    assert stored == sandbox


# --- connections and webhook endpoints ------------------------------------------------------------


def _connection(code: str, adapter: str, direction: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "name": code, "adapter": adapter, "direction": direction, **extra}


def _crm(tenant_id: UUID) -> dict[str, Any]:
    """An inbound Salesforce connection whose secret is one of the workspace's own namespace of
    the secret store, the only reference a connection may be saved with (04 T-INT-01 rev 1.108;
    05 KEY-09; supervisor ruling R-48 (f))."""
    reference = tenant_ref(tenant_id, "sf-client-secret")
    return _connection("sf-crm", "SALESFORCE", "INBOUND", secret_ref=reference)


def _stored_endpoint(tenant_id: UUID, *, is_active: bool) -> UUID:
    """An endpoint row written without the command, as a row from before the rule would be."""
    values = {**webhook_endpoint_values(tenant_id), "is_active": is_active}
    with tenant_session(_context(tenant_id)) as session:
        session.execute(insert(webhook_endpoint).values(**values))
    return UUID(str(values["id"]))


def _endpoint_row(tenant_id: UUID, endpoint_id: UUID) -> tuple[bool, int, str | None]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = session.execute(
            select(
                webhook_endpoint.c.is_active,
                webhook_endpoint.c.row_version,
                webhook_endpoint.c.description,
            ).where(webhook_endpoint.c.id == endpoint_id)
        ).one()
    return bool(row.is_active), int(row.row_version), row.description


def test_inbound_connection_and_webhook_blocked(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """05 SBX-08: in a sandbox, creating a Salesforce connection, creating a webhook endpoint,
    activating a webhook endpoint and activating an outbound adapter other than ``CSV_GL`` each
    answer 403 ``sandbox-restricted`` with a ``DENIED`` event and write nothing. What stays
    possible there — editing an inactive endpoint, activating the CSV export — and the same
    commands in production are the positive controls. A connection the sandbox may keep is saved
    with a secret reference of the sandbox's own namespace; another workspace's is refused at
    save (05 KEY-09)."""
    sandbox = seeded_sandbox(keyring, clock)
    nikhil = _holding(app, clock, sandbox, "nikhil", "integration_admin")

    crm = post(app, INTEGRATIONS, nikhil, _crm(sandbox))
    assert (crm.status_code, slug(crm)) == (403, RESTRICTED), crm.text

    created = post(app, ENDPOINTS, nikhil, ENDPOINT_BODY)
    assert (created.status_code, slug(created)) == (403, RESTRICTED), created.text
    assert created.json()["detail"] == webhook_endpoints.SANDBOX_ENDPOINT
    assert created.headers["X-Erev-Tenant-Kind"] == "sandbox"
    assert "signing_secret" not in created.json()
    assert _count(sandbox, webhook_endpoint) == 0

    endpoint_id = _stored_endpoint(sandbox, is_active=False)
    shown = get(app, f"{ENDPOINTS}/{endpoint_id}", nikhil)
    assert shown.status_code == 200 and shown.json()["is_active"] is False, shown.text
    etag = shown.headers["ETag"]
    activated = patch(app, f"{ENDPOINTS}/{endpoint_id}", nikhil, {"is_active": True}, if_match=etag)
    assert (activated.status_code, slug(activated)) == (403, RESTRICTED), activated.text
    assert _endpoint_row(sandbox, endpoint_id) == (False, 1, None)

    ledger = post(app, INTEGRATIONS, nikhil, _connection("ns-gl", "NETSUITE", "OUTBOUND"))
    assert ledger.status_code == 201 and ledger.json()["status"] == "DISABLED", ledger.text
    ledger_id = UUID(ledger.json()["id"])
    switched_on = patch(
        app,
        f"{INTEGRATIONS}/{ledger_id}",
        nikhil,
        {"status": "ACTIVE"},
        if_match=ledger.headers["ETag"],
    )
    assert (switched_on.status_code, slug(switched_on)) == (403, RESTRICTED), switched_on.text

    actor = nikhil.member.user_id
    assert _denied(sandbox) == [
        {
            "action": "integration_connection.create",
            "object_type": "integration_connection",
            "object_id": None,
            "actor_id": actor,
            "detail": {
                "code": "sf-crm",
                "adapter": "SALESFORCE",
                "direction": "INBOUND",
                "problem": RESTRICTED,
            },
        },
        {
            "action": "webhook_endpoint.create",
            "object_type": "webhook_endpoint",
            "object_id": None,
            "actor_id": actor,
            "detail": {"is_active": True, "problem": RESTRICTED},
        },
        {
            "action": "webhook_endpoint.update",
            "object_type": "webhook_endpoint",
            "object_id": endpoint_id,
            "actor_id": actor,
            "detail": {"is_active": True, "was_active": False, "problem": RESTRICTED},
        },
        {
            "action": "integration_connection.update",
            "object_type": "integration_connection",
            "object_id": ledger_id,
            "actor_id": actor,
            "detail": {
                "status": "ACTIVE",
                "adapter": "NETSUITE",
                "direction": "OUTBOUND",
                "problem": RESTRICTED,
            },
        },
    ]
    with tenant_session(_context(sandbox), read_only=True) as session:
        connections = [
            (str(row.code), str(row.status), int(row.row_version))
            for row in session.execute(
                select(
                    integration_connection.c.code,
                    integration_connection.c.status,
                    integration_connection.c.row_version,
                )
            )
        ]
    assert connections == [("ns-gl", "DISABLED", 1)]
    assert _count(sandbox, webhook_endpoint) == 1 and _count(sandbox, webhook_delivery) == 0

    # What a sandbox may still do: edit an endpoint that stays inactive, activate the CSV export.
    edited = patch(
        app,
        f"{ENDPOINTS}/{endpoint_id}",
        nikhil,
        {"description": "Kept for reference"},
        if_match=etag,
    )
    assert edited.status_code == 200 and edited.json()["is_active"] is False, edited.text
    assert _endpoint_row(sandbox, endpoint_id) == (False, 2, "Kept for reference")
    export = post(app, INTEGRATIONS, nikhil, _connection("csv-gl", "CSV_GL", "OUTBOUND"))
    assert export.status_code == 201, export.text
    exporting = patch(
        app,
        f"{INTEGRATIONS}/{export.json()['id']}",
        nikhil,
        {"status": "ACTIVE"},
        if_match=export.headers["ETag"],
    )
    assert exporting.status_code == 200 and exporting.json()["status"] == "ACTIVE", exporting.text
    assert len(_denied(sandbox)) == 4

    # In production the four refused commands are ordinary commands.
    admin, lena = _production(app, keyring, clock, "integration_admin")
    assert post(app, INTEGRATIONS, admin, _crm(lena.tenant_id)).status_code == 201
    endpoint = post(app, ENDPOINTS, admin, ENDPOINT_BODY)
    assert endpoint.status_code == 201 and endpoint.json()["is_active"] is True, endpoint.text
    path = f"{ENDPOINTS}/{endpoint.json()['id']}"
    off = patch(app, path, admin, {"is_active": False}, if_match=endpoint.headers["ETag"])
    assert off.status_code == 200 and off.json()["is_active"] is False, off.text
    on = patch(app, path, admin, {"is_active": True}, if_match=off.headers["ETag"])
    assert on.status_code == 200 and on.json()["is_active"] is True, on.text
    gl = post(app, INTEGRATIONS, admin, _connection("ns-gl", "NETSUITE", "OUTBOUND"))
    assert gl.status_code == 201, gl.text
    live = patch(
        app,
        f"{INTEGRATIONS}/{gl.json()['id']}",
        admin,
        {"status": "ACTIVE"},
        if_match=gl.headers["ETag"],
    )
    assert live.status_code == 200 and live.json()["status"] == "ACTIVE", live.text
    assert _denied(lena.tenant_id) == []

    # A sandbox is a workspace of its own in the secret store (05 KEY-09; ruling R-48 (f)): a
    # connection is saved there with a reference of the sandbox's namespace only. Another
    # workspace's reference, as a source's would be, is a field error and no refusal of SBX-08.
    foreign = _connection(
        "ns-src", "NETSUITE", "OUTBOUND", secret_ref=tenant_ref(lena.tenant_id, "netsuite")
    )
    refused = post(app, INTEGRATIONS, nikhil, foreign)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [error["field"] for error in refused.json()["errors"]] == ["secret_ref"]
    own = _connection("ns-own", "NETSUITE", "OUTBOUND", secret_ref=tenant_ref(sandbox, "netsuite"))
    saved = post(app, INTEGRATIONS, nikhil, own)
    assert saved.status_code == 201 and saved.json()["status"] == "DISABLED", saved.text
    assert len(_denied(sandbox)) == 4


# 05 SBX-08 rev 1.116: every adapter but the CSV export calls out when its connection is tested.
CALLING_ADAPTERS = (
    ("SALESFORCE", "INBOUND"),
    ("STRIPE", "INBOUND"),
    ("NETSUITE", "OUTBOUND"),
    ("QUICKBOOKS_ONLINE", "OUTBOUND"),
)
CSV_EXPORT = ("CSV_GL", "OUTBOUND")


def _stored_connection(tenant_id: UUID, adapter: str, direction: str) -> UUID:
    """A ``DISABLED`` connection written without the command. An inbound connection cannot be
    created in a sandbox, so there it is a row from before that rule; an outbound one could have
    been created there."""
    values = integration_connection_values(
        tenant_id, code=f"{adapter.lower()}-probe", adapter=adapter, direction=direction
    )
    with tenant_session(_context(tenant_id)) as session:
        session.execute(insert(integration_connection).values(**values))
    return UUID(str(values["id"]))


def _tested(tenant_id: UUID, connection_id: UUID) -> tuple[Any, Any, int, int]:
    """What a test leaves: ``last_test_at``, ``last_test_result``, the row version and the number
    of the connection's sync runs."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        row = session.execute(
            select(
                integration_connection.c.last_test_at,
                integration_connection.c.last_test_result,
                integration_connection.c.row_version,
            ).where(integration_connection.c.id == connection_id)
        ).one()
        runs = session.execute(
            select(func.count())
            .select_from(sync_run)
            .where(sync_run.c.integration_connection_id == connection_id)
        ).scalar_one()
    return row.last_test_at, row.last_test_result, int(row.row_version), int(runs)


def test_a_sandbox_tests_no_connection_that_calls_out(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SBX-08 rev 1.116 (item SBX-PROBE-1): a sandbox reaches no external system, a probe
    included. ``POST /integrations/{id}/test`` on a connection of each adapter that calls out
    answers 403 ``sandbox-restricted`` with a ``DENIED`` event, and the probe — the one function
    that asks the secret store and sends the request — is not reached; the connection's
    ``last_test_*`` and its sync runs stay as they were. The CSV export calls nothing and is
    tested in a sandbox as in production, and in production the same command probes every
    adapter: the positive controls, which also show that the recorded probe is the one the route
    reaches."""
    probed: list[tuple[UUID, str]] = []
    probe = integration_sync.probe_connection

    def recording(uow: UnitOfWork, connection: Mapping[str, Any]) -> integration_sync.ProbeResult:
        probed.append((uow.principal.tenant_id, str(connection["adapter"])))
        return probe(uow, connection)

    monkeypatch.setattr(integration_sync, "probe_connection", recording)
    sandbox = seeded_sandbox(keyring, clock)
    nikhil = _holding(app, clock, sandbox, "nikhil", "integration_admin")
    stored = {
        adapter: _stored_connection(sandbox, adapter, direction)
        for adapter, direction in CALLING_ADAPTERS
    }
    for adapter in stored:
        refused = post(app, f"{INTEGRATIONS}/{stored[adapter]}/test", nikhil, {})
        assert refused.status_code == 403, refused.text
        assert slug(refused) == RESTRICTED
        assert refused.json()["detail"] == integration_commands.SANDBOX_PROBE
        assert _tested(sandbox, stored[adapter]) == (None, None, 1, 0)
    assert probed == []
    assert _denied(sandbox) == [
        {
            "action": "integration_connection.test",
            "object_type": "integration_connection",
            "object_id": stored[adapter],
            "actor_id": nikhil.member.user_id,
            "detail": {"adapter": adapter, "direction": direction, "problem": RESTRICTED},
        }
        for adapter, direction in CALLING_ADAPTERS
    ]

    # The CSV export calls nothing: its test runs in a sandbox as it does in production.
    export = _stored_connection(sandbox, *CSV_EXPORT)
    in_sandbox = post(app, f"{INTEGRATIONS}/{export}/test", nikhil, {})
    assert in_sandbox.status_code == 200, in_sandbox.text
    assert probed == [(sandbox, "CSV_GL")]
    at, result, version, runs = _tested(sandbox, export)
    assert at is not None and result is not None and (version, runs) == (2, 1)
    assert len(_denied(sandbox)) == len(CALLING_ADAPTERS)

    # In production the same command probes every adapter.
    admin, lena = _production(app, keyring, clock, "integration_admin")
    every = (*CALLING_ADAPTERS, CSV_EXPORT)
    answers = {}
    for adapter, direction in every:
        connection_id = _stored_connection(lena.tenant_id, adapter, direction)
        answered = post(app, f"{INTEGRATIONS}/{connection_id}/test", admin, {})
        assert answered.status_code == 200, answered.text
        at, result, version, runs = _tested(lena.tenant_id, connection_id)
        assert at is not None and result is not None and (version, runs) == (2, 1)
        answers[adapter] = answered.json()["last_test_result"]
    assert probed[1:] == [(lena.tenant_id, adapter) for adapter, _ in every]
    assert in_sandbox.json()["last_test_result"] == answers["CSV_GL"]
    assert _denied(lena.tenant_id) == []


# --- the tenant kind ------------------------------------------------------------------------------


def test_tenant_kind_immutable(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """ERR-26 / DB-05 / REQ-PLT-003: ``PATCH /tenant`` with ``kind = production`` in a sandbox
    answers 409 ``tenant-kind-immutable`` with the catalogue sentence, alone or beside a member
    that could change; the row keeps its kind and its version; and the column itself is frozen in
    the database for the tenant's own session (``EREV-REF-001``)."""
    sandbox = seeded_sandbox(keyring, clock)
    tomas = _holding(app, clock, sandbox, "tomas", "tenant_admin")
    before = get(app, TENANT, tomas)
    assert before.status_code == 200 and before.json()["kind"] == "sandbox", before.text
    etag = before.headers["ETag"]

    for body in ({"kind": "production"}, {"kind": "production", "display_name": "Promoted"}):
        refused = patch(app, TENANT, tomas, body, if_match=etag)
        assert (refused.status_code, slug(refused)) == (409, "tenant-kind-immutable"), refused.text
        assert refused.json()["detail"] == ERR_26
        assert refused.headers["X-Erev-Tenant-Kind"] == "sandbox"
    after = get(app, TENANT, tomas)
    assert after.headers["ETag"] == etag
    assert (after.json()["kind"], after.json()["display_name"]) == (
        "sandbox",
        before.json()["display_name"],
    )
    assert _count(sandbox, audit_event, audit_event.c.action == "tenant.update") == 0

    # Positive control: the same request without ``kind`` is an ordinary rename.
    renamed = patch(app, TENANT, tomas, {"display_name": "Rehearsal copy"}, if_match=etag)
    assert renamed.status_code == 200 and renamed.json()["kind"] == "sandbox", renamed.text

    own = tenant.c.id == sandbox
    with tenant_session(_context(sandbox)) as session:
        state, message = _fails(session, update(tenant).where(own).values(kind="production"))
    assert state == "P0001" and message.startswith("EREV-REF-001"), message
    with tenant_session(_context(sandbox), read_only=True) as session:
        assert str(session.execute(select(tenant.c.kind).where(own)).scalar_one()) == "sandbox"


# --- security finding SF-1 ------------------------------------------------------------------------


class _Receiver:
    """A mock endpoint answering 204 and keeping what it was sent."""

    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> int:
        self.requests.append(request)
        return 204


def _resolve(host: str, port: int) -> list[str]:
    return [PUBLIC_ADDRESS]


def _runtime(
    settings: Settings, keyring: KeyRing, clock: FrozenClock, receiver: _Receiver
) -> JobRuntime:
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
        email=build_email_sender(settings, clock),
        public_origin=settings.public_origin,
        webhooks=WebhookClient(
            env=Environment.TEST, transport=mock_transport(receiver), resolve=_resolve
        ),
    )


def _integration_admin(tenant_id: UUID) -> Principal:
    return Principal(
        kind=PrincipalKind.USER,
        id=new_id(),
        tenant_id=tenant_id,
        membership_id=None,
        display_name="Integration admin",
        roles=("integration_admin",),
        permissions=frozenset({"webhook.manage"}),
        permission_scopes={"webhook.manage": "*"},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,  # webhook.manage needs no second factor
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _request(principal: Principal, kind: TenantKind, clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=principal,
        tenant_kind=kind,
        request_id="tests-sf-1",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@contextmanager
def _db_15_trigger_disabled(database: TestDatabase) -> Iterator[None]:
    """The schema owner switches the table's DB-15 trigger off and on again. It is the only way
    an ACTIVE endpoint row can come to exist in a sandbox — the application role cannot do it —
    and it is what "whatever the endpoint rows say" means for the layer under test."""
    owner = database.owner_engine
    with owner.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE erev.webhook_endpoint DISABLE TRIGGER {TRIGGER}")
    try:
        yield
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE erev.webhook_endpoint ENABLE TRIGGER {TRIGGER}"
            )


def _queued_delivery(
    session: Session, tenant_id: UUID, endpoint_id: UUID, clock: FrozenClock
) -> UUID:
    """A PENDING delivery that is due now, as ``emit_webhook`` writes one."""
    delivery_id = new_id()
    envelope = {
        "id": str(new_id()),
        "kind": EVENT_KIND,
        "tenant_code": "sandbox",
        "occurred_at": clock.now().isoformat(),
        "data": {"period_id": str(new_id())},
    }
    session.execute(
        insert(webhook_delivery).values(
            tenant_id=tenant_id,
            id=delivery_id,
            webhook_endpoint_id=endpoint_id,
            event_kind=EVENT_KIND,
            payload=envelope,
            payload_sha256=sha256_hex(envelope),
            status="PENDING",
            attempt_count=0,
            next_attempt_at=clock.now(),
            abandon_at=clock.now() + timedelta(hours=24),
            created_at=clock.now(),
            created_by=None,
            created_by_kind="SYSTEM",
        )
    )
    return delivery_id


def _emit(tenant_id: UUID, runtime: JobRuntime) -> int:
    """One ``period.locked`` event emitted as a job emits it: the unit of work reads the tenant
    kind from the tenant row (DG-KRN-UOW-04)."""
    with system_unit_of_work(
        runtime, system_principal(tenant_id), request_id="tests-sf-1-emit"
    ) as uow:
        emitted = webhooks.emit_webhook(uow, event_kind=EVENT_KIND, payload={"period_id": new_id()})
        uow.commit()
    return emitted


def _deliver(tenant_id: UUID, runtime: JobRuntime) -> webhooks.DeliveryStats:
    worker = JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.WEBHOOK_DELIVERY,
        principal=system_principal(tenant_id),
        runtime=runtime,
        persisted=False,
    )
    return webhooks.deliver(worker)


def _refused(command: Callable[[], Any]) -> Problem:
    with pytest.raises(Problem) as excinfo:
        command()
    return excinfo.value


@pytest.mark.control("CTL-043")
def test_sf_1_a_sandbox_neither_creates_activates_emits_nor_delivers_a_webhook(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """Security finding SF-1 (CONFIRMED P2; ruling R-33). The reviewer's proof created an ACTIVE
    endpoint in a sandbox through ``create_endpoint``, re-activated it through ``update_endpoint``
    and saw ``emit_webhook`` fan an event out to it, with no ``DENIED`` event. Each step is now a
    refusal, and each of the three layers of 05 SBX-08 holds without the other two:

    1. the commands — 403 ``sandbox-restricted``, a ``DENIED`` event, nothing written;
    2. the emission and the delivery — with an ACTIVE endpoint and a queued delivery put into the
       sandbox behind the commands and the trigger, no delivery is created and the queued one
       ends ``ABANDONED`` without a request leaving the process;
    3. the database — an endpoint row cannot become active in a sandbox (``EREV-SBX-001``).

    The positive control runs the same sequence in a production tenant, where the receiver gets
    one signed request."""
    receiver = _Receiver()
    runtime = _runtime(app_settings, keyring, clock, receiver)
    files = LocalFileStore(app_settings.file_root)
    sandbox = seeded_sandbox(keyring, clock)
    admin = _integration_admin(sandbox)
    ctx = _request(admin, TenantKind.SANDBOX, clock)

    # Layer 1, creation: the endpoint would be created active.
    def create() -> Any:
        with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
            webhook_endpoints.create_endpoint(
                uow,
                url="https://hooks.example/sandbox-leak",
                description=None,
                event_kinds=[EVENT_KIND],
            )
            uow.commit()

    problem = _refused(create)
    assert (problem.slug, problem.status) == (RESTRICTED, 403)
    assert _count(sandbox, webhook_endpoint) == 0

    # Layer 1, activation: the change the SPA's "Activate" toggle sends, on a row that exists.
    endpoint_id = _stored_endpoint(sandbox, is_active=False)

    def activate() -> Any:
        with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
            webhook_endpoints.update_endpoint(
                uow, endpoint_id, {"is_active": True}, check_version=lambda _actual: None
            )
            uow.commit()

    problem = _refused(activate)
    assert (problem.slug, problem.status) == (RESTRICTED, 403)
    assert _endpoint_row(sandbox, endpoint_id) == (False, 1, None)
    assert [
        (d["action"], d["object_id"], d["actor_id"], d["detail"]) for d in _denied(sandbox)
    ] == [
        ("webhook_endpoint.create", None, admin.id, {"is_active": True, "problem": RESTRICTED}),
        (
            "webhook_endpoint.update",
            endpoint_id,
            admin.id,
            {"is_active": True, "was_active": False, "problem": RESTRICTED},
        ),
    ]
    assert _emit(sandbox, runtime) == 0  # nothing is subscribed, and nothing would be read

    # Layer 3: without the commands, the row still cannot become active.
    with tenant_session(_context(sandbox)) as session:
        state, message = _fails(
            session, insert(webhook_endpoint).values(**webhook_endpoint_values(sandbox))
        )
        assert state == "P0001" and message.startswith("EREV-SBX-001: webhook endpoint "), message
        state, message = _fails(
            session,
            update(webhook_endpoint)
            .where(webhook_endpoint.c.id == endpoint_id)
            .values(is_active=True),
        )
        assert state == "P0001" and message.startswith("EREV-SBX-001"), message

    # Layer 2: an ACTIVE endpoint with a real sealed secret and a delivery that is due, put into
    # the sandbox behind the commands and with the trigger off.
    with _db_15_trigger_disabled(committed_db), tenant_session(_context(sandbox)) as session:
        live = insert_sealed_webhook_endpoint(session, sandbox, keyring=keyring)
        queued = _queued_delivery(session, sandbox, live, clock)
    assert _endpoint_row(sandbox, live)[0] is True
    assert _emit(sandbox, runtime) == 0
    assert _count(sandbox, webhook_delivery) == 1  # the queued one; the event added none
    assert _count(sandbox, outbox_message) == 0
    assert _deliver(sandbox, runtime) == webhooks.DeliveryStats(
        claimed=1, succeeded=0, failed=0, abandoned=1
    )
    with tenant_session(_context(sandbox), read_only=True) as session:
        delivery = session.execute(
            select(
                webhook_delivery.c.status,
                webhook_delivery.c.attempt_count,
                webhook_delivery.c.next_attempt_at,
                webhook_delivery.c.last_error,
            ).where(webhook_delivery.c.id == queued)
        ).one()
    assert tuple(delivery) == ("ABANDONED", 0, None, webhooks.SANDBOX_TENANT)
    assert receiver.requests == []  # nothing left the process

    # Positive control: the same sequence in a production tenant delivers one signed request.
    production = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    owner = _request(_integration_admin(production), TenantKind.PRODUCTION, clock)
    with unit_of_work(owner, clock=clock, keyring=keyring, files=files) as uow:
        created = webhook_endpoints.create_endpoint(
            uow, url="https://hooks.example/erev", description=None, event_kinds=[EVENT_KIND]
        )
        uow.commit()
    assert created.endpoint["is_active"] is True
    assert _emit(production, runtime) == 1
    assert _deliver(production, runtime) == webhooks.DeliveryStats(
        claimed=1, succeeded=1, failed=0, abandoned=0
    )
    [request] = receiver.requests
    # The client posts to the address it resolved and pinned (SAR-15), naming the host.
    assert (request.method, request.url.host, request.url.path) == ("POST", PUBLIC_ADDRESS, "/erev")
    assert request.headers["Host"] == "hooks.example"
    assert request.headers[webhooks.SIGNATURE_HEADER].startswith("t=")
    assert _denied(production) == []
