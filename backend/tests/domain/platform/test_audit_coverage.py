"""SOP-7 audit coverage of the required actions (BUILD_SPEC SOP-7; 03 REQ-PLT-019; 04 T-PLT-19, §1.7
AUD-CMD / AUD-FACT / AUD-OPS; dev-guide DG-KRN-AUD-04, DG-KRN-AUTH-05; CTL-038).

Three database tests over the catalogue of ``tests/support/audit_catalogue.py``:

- ``test_ctl_038_every_command_route_writes_audit`` walks every POST / PUT / PATCH / DELETE
  operation of the committed OpenAPI. An audited operation is exercised by its scenario of
  ``WALK`` (a successful call in a fresh tenant) and must write at least one ``audit_event`` in
  the same transaction whose ``action`` matches ``^[a-z_]+\\.[a-z_]+$``, whose ``request_id``
  equals the response ``X-Request-Id`` and whose ``actor_kind`` is the caller's. The routes of
  class (a) and the catalogue's ``security_event`` class write ``security_event`` rows instead. A
  ``query`` operation (classes (b) and (c), D-98 (20)) must persist nothing but the 04 §1.7
  personal rows and the ``idempotency_record`` row ``run_command`` writes (D-98 (49)): zero
  ``audit_event`` rows and zero other row-count changes. A ``refused`` operation (class (e),
  fragment 11 rev 1.44: a command the release refuses by name, which stores nothing — the
  creation of a policy override, 04 T-CON-23 rev 1.322) has no successful call: its scenario is
  the call of a person who may ask, and it must answer 422 with exactly the catalogue's rule id,
  write zero ``audit_event`` rows and change no row count; any other answer fails by name. Every
  audited operation WITHOUT a
  scenario is named in the failure message — the walk never hides an uncovered route (the registry
  is filled incrementally; lane P4 wrote it without a lane database, so the scenarios are NOT RUN
  by the lane). Every event the walk reads is also held to the contract key of 04 T-PLT-19 (rev
  1.154; DG-KRN-AUD-09): its object type is in one of the closed lists of
  ``erev_api.audit.contract_key``, and an event of an object that belongs to a contract names the
  contract (``NO_CONTRACT`` below). - ``test_req_plt_019_categories_covered``: the actions and
  security-event kinds
  observed while the walk and the session scenarios run cover every REQ-PLT-019 category of
  ``CATEGORIES``; a missing category fails with its name; a category the catalogue marks pending
  on a lane is reported as such. - ``test_denied_commands_audited``: five command routes called by
  a principal lacking the permission each write exactly one ``DENIED`` audit event carrying the
  response's ``X-Request-Id``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.api.v1.close_runs import CLOSE_RUN_ID_HEADER
from erev_api.api.v1.journal_runs import RUN_ID_HEADER
from erev_api.api.v1.reconciliations import RECONCILIATION_ID_HEADER
from erev_api.api.v1.ssp_calculator import RUN_ID_HEADER as CALC_RUN_ID_HEADER
from erev_api.audit import contract_key
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.mfa import STEP_UP_WINDOW
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.auth.sessions import sha256_hex
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import tables
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract,
    file_object,
    job,
    migration_batch,
    obligation,
    outbox_message,
    security_event,
)
from erev_api.domain.integrations import commands as integration_commands
from erev_api.domain.integrations import sync as sync_module
from erev_api.domain.journals import ports as journal_ports
from erev_api.enums import (
    FilePurpose,
    GlAdapter,
    JobKind,
    MigrationStatus,
    NotificationKind,
    TenantKind,
)
from erev_api.events.notifications import notify
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.uow import UnitOfWork, unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text
from support import close_runs
from support.adapter_secrets import serve_adapter_secrets, tenant_ref
from support.audit_catalogue import (
    QUERY_EXEMPT,
    RELEASE_REFUSED,
    ROUTES,
    required_operations,
    uncovered_categories,
)
from support.close_world import (
    RUN_AUDIT_ACTION,
    RUN_AUDIT_OBJECT_TYPE,
    acknowledged_run_for,
    close_run_succeeded_for,
    reviewed_reconciliations_for,
    run_audit_after,
)
from support.db import TestDatabase
from support.factories import (
    IMPORT_ID_HEADER,
    SKU_SSP_FIXTURE,
    TPL_SUB_DAILY,
    K02World,
    SeatWorld,
    activated_contract,
    booked_contract,
    computed,
    drafted_override,
    k02_seat_month_body,
    k02_world,
    random_suffix,
    seat_body,
    seat_line,
    seat_world,
    set_default_template,
    stamp_test_release,
    step1_criteria,
    workbook_bytes,
)
from support.http import HttpResponse, asgi_client, call
from support.legacy_replay import workbook_rows
from support.links import emailed_token
from support.operators import create_operator, operator_services
from support.principals import (
    LOGIN,
    PASSWORD,
    Actor,
    Member,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    refreshed,
    sign_in,
    step_up,
)
from support.reference import assign, delete, get, holding, patch, periods, post, put
from support.rows import file_object_values, insert_active_membership, migration_batch_values
from support.snapshots import confirm_retention, seeded_sandbox
from support.upload_fixtures import PDF
from support.worlds import estimate_version_ready

API: Final = "/api/v1"
ACTION: Final = re.compile(r"^[a-z_]+\.[a-z_]+$")
REQUEST_ID: Final = "X-Request-Id"
REASON: Final = "Access is no longer required for this duty (SOP-7 walk)."
COMMENT: Final = "SOP-7 coverage walk"
# The close run scenarios use an open period of the K-02 world that no other scenario closes:
# the blocker a failed run raises belongs to that period alone (04 §15.4 CLOSE_RUN_FAILED).
CLOSE_RUN_PERIOD: Final = "FY2026-P08"
JANUARY: Final = "2026-01-01"
# The shipped legacy database the migration tests use (tests/api/test_migrations_api.py FIXTURE).
LEGACY_DB: Final = (
    Path(__file__).resolve().parents[2] / "fixtures" / "legacy_db" / "ASC606-shipped-step04.db"
)
UNMAPPED_SEAT: Final = "AVM-SEAT-NOMAP"  # seat_world(untemplated=...): PRODUCT_UNMAPPED on booking
UNMAPPED_SEAT_2: Final = "AVM-SEAT-NOMAP-2"  # the resolve walk's own untemplated product (slice 7)
CLOCK_STEP: Final = timedelta(seconds=1)  # slice 7: the one test-side step of the walk's clock
Scenario = Callable[["World"], HttpResponse]

# The 04 §1.7 AUD-OPS personal rows a `query` operation may write (class (c)); every `query`
# operation may also write the idempotency_record row of run_command (D-98 (49)); nothing else.
INFRASTRUCTURE_TABLES: Final = frozenset({"idempotency_record"})
PERSONAL_TABLES: Final[Mapping[str, frozenset[str]]] = {
    "me_notification_preferences_put": frozenset({"notification_preference"}),
    "me_notifications_read": frozenset({"notification"}),
    "me_notifications_read_all": frozenset({"notification"}),
    "me_preferences_update": frozenset({"app_user"}),
    # BUILD_SPEC rev 1.25 (R-14): a saved view is its user's own AUD-OPS row (04 T-PLT-37), so the
    # three saved-view commands may write that row and nothing else.
    "saved_views_create": frozenset({"saved_view"}),
    "saved_views_update": frozenset({"saved_view"}),
    "saved_views_delete": frozenset({"saved_view"}),
}
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# Routes whose evidence is written on REFUSAL (D-98 (20): a failed invitation lookup is the probing
# signal; a successful lookup writes nothing): the scenario provokes the refusal on purpose.
REFUSAL_EVIDENCE: Final = frozenset({"session_lookup_invitation"})
# The signature-verified webhook receiver has no session: the product records its audit under the
# tenant's system principal (actor_kind SYSTEM) by design — BUILD_SPEC rev 1.19; supervisor ruling
# of 2026-09-22, limited to this one operation and named in the failure message.
SYSTEM_ACTOR: Final = frozenset({"webhooks_receive"})
# The connection's secret: its reference is this name in the workspace's own namespace of the
# secret store (``tenant_ref``; 05 KEY-09 rev 1.47, supervisor ruling R-48 (f)).
SF_SECRET_NAME: Final = "sf-client-secret"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


# ---- the world ---------------------------------------------------------------------------------


@dataclass
class World:
    """A fresh tenant with the actors the scenarios need and the ids they hand each other."""

    app: FastAPI
    clock: FrozenClock
    keyring: KeyRing
    runtime: JobRuntime
    tenant_id: UUID
    root: Member  # the provisioned admin (maya): revenue_accountant
    maya: Actor  # revenue_accountant: masterdata, configuration, events, reports, periods
    tomas: Actor  # tenant_admin, MFA-enrolled and stepped up: users, roles, API clients
    grace: Actor  # tenant_admin, MFA-enrolled: the approver (never the preparer)
    sam: Actor  # ssp_analyst
    ivy: Actor  # integration_admin, MFA-enrolled (integration.manage needs MFA)
    # controller, MFA-enrolled: approves configuration (config.approve; never the author) and
    # requests tenant snapshots and sandboxes (tenant.snapshot / sandbox.reset are MFA permissions)
    nora: Actor
    ids: dict[str, str] = field(default_factory=dict)
    engine: K02World | None = None  # PRD K-02 world (its own tenant) for the contract routes
    seats: SeatWorld | None = None  # seat world with an untemplated product (its own tenant)
    evidence_tenant_id: UUID | None = None  # set by a scenario whose evidence lives elsewhere

    def role_id(self, code: str) -> str:
        if "roles" not in self.ids:
            listed = get(self.app, f"{API}/roles", self.tomas, {"limit": 200})
            assert listed.status_code == 200, listed.text
            self.ids["roles"] = "|".join(
                f"{item['code']}={item['id']}" for item in listed.json()["items"]
            )
        return dict(pair.split("=") for pair in self.ids["roles"].split("|"))[code]


def _world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime) -> World:
    stamp_test_release()
    root = member(keyring, clock, name="maya")
    maya = holding(app, root, "revenue_accountant")
    tomas_member = colleague(root.tenant_id, "tomas")
    assign(tomas_member, "tenant_admin")
    # Codex 0339 §5: ``enrolled`` confirms the current TOTP code and stores its step (T-PLT-04
    # ``last_used_step``), so a step-up at the SAME frozen step replays that code and is refused.
    # The clock moves one TOTP step first (P8's ``fresh_step_up`` pattern); every scenario then runs
    # at this instant, so the step-up stays within the five-minute window without a second code.
    tomas_enrolled = enrolled(app, clock, tomas_member)
    clock.advance(totp.STEP)
    tomas = step_up(app, clock, tomas_enrolled)
    grace_member = colleague(root.tenant_id, "grace")
    assign(grace_member, "tenant_admin")
    grace = enrolled(app, clock, grace_member)
    sam = holding(app, colleague(root.tenant_id, "sam"), "ssp_analyst")
    ivy_member = colleague(root.tenant_id, "ivy")
    assign(ivy_member, "integration_admin")
    ivy = enrolled(app, clock, ivy_member)  # integration.manage is an MFA permission
    # Configuration approvals need config.approve WITH a fresh MFA verification (slice 4): Nora is
    # an enrolled controller (mfa_verified_at at enrolment, preserved through the tenant switch).
    nora_member = colleague(root.tenant_id, "nora")
    assign(nora_member, "controller")
    nora = enrolled(app, clock, nora_member)
    return World(
        app=app,
        clock=clock,
        keyring=keyring,
        runtime=runtime,
        tenant_id=root.tenant_id,
        root=root,
        maya=maya,
        tomas=tomas,
        grace=grace,
        sam=sam,
        ivy=ivy,
        nora=nora,
        # slice 7: the instant of Tomas's step-up, so the one clock step can assert the window holds
        ids={"tomas.stepped_up_at": clock.now().isoformat()},
    )


def _etag(response: HttpResponse) -> str:
    return str(response.headers["ETag"])


def _created(world: World, key: str, response: HttpResponse) -> HttpResponse:
    """Remember the id of a 2xx creation under ``key`` and return the response unchanged."""
    if response.status_code < 400:
        world.ids[key] = str(response.json()["id"])
        world.ids[f"{key}.etag"] = response.headers.get("ETag", '"r1"')
    return response


def _approve(world: World, request_id: str, approver: Actor) -> HttpResponse:
    detail = get(world.app, f"{API}/approvals/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    request = detail.json()
    body: dict[str, Any] = {
        "subject_content_sha256": request["subject"]["content_sha256"],
        "comment": COMMENT,
    }
    if request.get("impact_preview") is not None:
        body["impact_preview_sha256"] = request["impact_preview"]["sha256"]
    return post(world.app, f"{API}/approvals/{request_id}/approve", approver, body)


def _run_job(world: World, job_id: UUID) -> None:
    """The worker fetches the job's current task and runs it (as the report tests do)."""
    with tenant_session(_db(world.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, world.tenant_id, attempt=1, runtime=world.runtime)


def _me(world: World, method: str, path: str, json: Mapping[str, Any] | None) -> HttpResponse:
    return call(
        world.app,
        method,
        path,
        json=None if json is None else dict(json),
        headers=cookie_headers(world.maya.token, world.maya.csrf_token),
    )


# ---- scenarios: each performs ONE successful call of its operation and returns the response ------


def s_calendars_create(w: World) -> HttpResponse:
    return _created(
        w,
        "calendar",
        post(w.app, f"{API}/calendars", w.maya, {"code": "GREG", "name": "Gregorian"}),
    )


def s_calendars_generate_year(w: World) -> HttpResponse:
    return post(
        w.app, f"{API}/calendars/{w.ids['calendar']}/generate-year", w.maya, {"fiscal_year": 2026}
    )


def s_entities_create(w: World) -> HttpResponse:
    body = {
        "code": "AVM-US",
        "name": "AVM-US (Demo)",
        "functional_currency": "USD",
        "time_zone": "America/New_York",
        "calendar_id": w.ids["calendar"],
    }
    return _created(w, "entity", post(w.app, f"{API}/entities", w.maya, body))


def s_entities_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/entities/{w.ids['entity']}",
        w.maya,
        {"name": "AVM-US Inc."},
        if_match=w.ids["entity.etag"],
    )


def s_entities_put_book(w: World) -> HttpResponse:
    return put(
        w.app, f"{API}/entities/{w.ids['entity']}/books/IFRS15", w.maya, {"is_enabled": True}
    )


def s_books_update(w: World) -> HttpResponse:
    listed = get(w.app, f"{API}/books", w.maya, {"limit": 50})  # there is no GET /books/{code}
    assert listed.status_code == 200, listed.text
    book = next(i for i in listed.json()["items"] if i["code"] == "IFRS15")
    body = {"name": "IFRS 15 book"}
    return patch(w.app, f"{API}/books/IFRS15", w.maya, body, if_match=f'"r{book["row_version"]}"')


def s_periods_open(w: World) -> HttpResponse:
    states = {
        item["period"]["period_key"]: item for item in periods(w.app, w.maya, entity="AVM-US")
    }
    state = states["FY2026-P01"]
    w.ids["period"] = str(state["id"])
    return post(
        w.app,
        f"{API}/periods/{state['id']}/open",
        w.maya,
        {"comment": COMMENT},
        if_match=f'"r{state["row_version"]}"',
    )


def _period_state(w: World) -> dict[str, Any]:
    states = {
        item["period"]["period_key"]: item for item in periods(w.app, w.maya, entity="AVM-US")
    }
    result: dict[str, Any] = states["FY2026-P01"]
    return result


def s_periods_start_close(w: World) -> HttpResponse:
    state = _period_state(w)
    return post(
        w.app,
        f"{API}/periods/{state['id']}/start-close",
        w.maya,
        {"comment": COMMENT},
        if_match=f'"r{state["row_version"]}"',
    )


def s_periods_cancel_close(w: World) -> HttpResponse:
    state = _period_state(w)
    return post(
        w.app,
        f"{API}/periods/{state['id']}/cancel-close",
        w.maya,
        {"reason_code": "CLOSE_RESTARTED", "comment": COMMENT},
        if_match=f'"r{state["row_version"]}"',
    )


def s_gl_accounts_create(w: World) -> HttpResponse:
    body = {"code": "4000", "name": "Revenue", "account_type": "REVENUE", "normal_balance": "C"}
    return _created(w, "gl_account", post(w.app, f"{API}/gl-accounts", w.maya, body))


def s_gl_accounts_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/gl-accounts/{w.ids['gl_account']}",
        w.maya,
        {"name": "Subscription revenue"},
        if_match=w.ids["gl_account.etag"],
    )


def s_account_mappings_create(w: World) -> HttpResponse:
    return _created(
        w,
        "mapping",
        post(
            w.app,
            f"{API}/account-mappings",
            w.maya,
            {"name": "AVM-MAP-2026-01", "effective_from": f"{JANUARY}T00:00:00Z"},  # aware
        ),
    )


def s_account_mappings_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/account-mappings/{w.ids['mapping']}",
        w.maya,
        {"notes": COMMENT},
        if_match=w.ids["mapping.etag"],
    )


def s_account_mapping_rules_create(w: World) -> HttpResponse:
    """Two REVENUE rules on the DRAFT version: A is kept (the version's /test needs one), B
    (priority 1) is the one the delete scenario removes."""
    path = f"{API}/account-mappings/{w.ids['mapping']}/rules"
    kept = post(
        w.app, path, w.maya, {"account_role": "REVENUE", "gl_account_id": w.ids["gl_account"]}
    )
    assert kept.status_code == 201, kept.text
    body = {"account_role": "REVENUE", "gl_account_id": w.ids["gl_account"], "priority": 1}
    return _created(w, "mapping_rule_b", post(w.app, path, w.maya, body))


def s_account_mapping_rules_delete(w: World) -> HttpResponse:
    path = f"{API}/account-mappings/{w.ids['mapping']}/rules/{w.ids['mapping_rule_b']}"
    return delete(w.app, path, w.maya)


def s_account_mappings_test(w: World) -> HttpResponse:
    return post(w.app, f"{API}/account-mappings/{w.ids['mapping']}/test", w.maya, {})


def s_account_mappings_submit(w: World) -> HttpResponse:
    response = post(
        w.app, f"{API}/account-mappings/{w.ids['mapping']}/submit", w.maya, {"comment": COMMENT}
    )
    if response.status_code < 400:
        w.ids["mapping.approval"] = str(response.json()["pending_approval_request_id"])
    return response


def _confirm_publish(w: World, approval_key: str, path: str, approver: Actor) -> HttpResponse:
    """Approve the SUBMITTED version (the approval publishes and audits it), record the Codex 0527
    correlation facts, snapshot the bounded state, then POST the DISTINCT fresh confirm (post()
    sends a fresh Idempotency-Key) and snapshot the state again."""
    approval_id = w.ids[approval_key]
    detail = get(w.app, f"{API}/approvals/{approval_id}", approver).json()
    approved = _approve(w, approval_id, approver)
    assert approved.status_code == 200, approved.text
    version_path = path.removesuffix("/publish")
    w.ids["confirm.approve_request"] = str(approved.headers[REQUEST_ID])
    w.ids["confirm.approval_id"] = str(approval_id)
    w.ids["confirm.subject_id"] = str(detail["subject"]["id"])
    w.ids["confirm.approver_user_id"] = str(approver.member.user_id)
    w.ids["confirm.before"] = _bounded_state(w, version_path, w.maya)
    response = post(w.app, path, w.maya, {})
    w.ids["confirm.after"] = _bounded_state(w, version_path, w.maya)
    return response


def s_account_mappings_publish(w: World) -> HttpResponse:
    return _confirm_publish(
        w, "mapping.approval", f"{API}/account-mappings/{w.ids['mapping']}/publish", w.nora
    )


def s_customers_create(w: World) -> HttpResponse:
    return _created(
        w,
        "customer",
        post(w.app, f"{API}/customers", w.maya, {"code": "C-01", "name": "Pellworth (Demo)"}),
    )


def s_customers_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/customers/{w.ids['customer']}",
        w.maya,
        {"segment": "Enterprise"},
        if_match=w.ids["customer.etag"],
    )


def s_related_party_groups_create(w: World) -> HttpResponse:
    return _created(
        w,
        "rpg",
        post(
            w.app,
            f"{API}/related-party-groups",
            w.maya,
            {"code": "HOLLENBRAND", "name": "Hollenbrand (Demo)"},
        ),
    )


def s_related_party_groups_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/related-party-groups/{w.ids['rpg']}",
        w.maya,
        {"description": COMMENT},
        if_match=w.ids["rpg.etag"],
    )


def s_dimensions_create(w: World) -> HttpResponse:
    return _created(
        w,
        "dimension",
        post(w.app, f"{API}/dimensions", w.maya, {"code": "region", "name": "Region"}),  # T-REF-16
    )


def s_dimension_values_create(w: World) -> HttpResponse:
    return _created(
        w,
        "dimension_value",
        post(w.app, f"{API}/dimensions/region/values", w.maya, {"code": "emea", "name": "EMEA"}),
    )


def s_dimension_values_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/dimensions/region/values/{w.ids['dimension_value']}",
        w.maya,
        {"name": "Europe, Middle East and Africa"},
        if_match=w.ids["dimension_value.etag"],
    )


def s_products_create(w: World) -> HttpResponse:
    return _created(
        w,
        "product",
        post(
            w.app,
            f"{API}/products",
            w.maya,
            {"code": "SUB-STD", "name": "Standard subscription", "principal_agent": "PRINCIPAL"},
        ),
    )


def s_products_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/products/{w.ids['product']}",
        w.maya,
        {"name": "Standard subscription (annual)"},
        if_match=w.ids["product.etag"],
    )


def s_pob_templates_create(w: World) -> HttpResponse:
    return _created(
        w,
        "template",
        post(
            w.app, f"{API}/pob-templates", w.maya, {"code": "TPL-SUB", "name": "Template TPL-SUB"}
        ),
    )


def s_ssp_books_create(w: World) -> HttpResponse:
    return _created(
        w,
        "ssp_book",
        post(
            w.app,
            f"{API}/ssp-books",
            w.sam,
            {"code": "US-LIST", "name": "US-LIST list prices", "currency": "USD"},
        ),
    )


def s_ssp_books_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/ssp-books/{w.ids['ssp_book']}",
        w.sam,
        {"name": "US list prices"},
        if_match=w.ids["ssp_book.etag"],
    )


def s_ssp_book_versions_create(w: World) -> HttpResponse:
    body = {
        "legacy_version_label": "v1",
        "effective_from_date": JANUARY,
        "methodology_label": "List-price study",
    }
    return _created(
        w, "ssp_version", post(w.app, f"{API}/ssp-books/{w.ids['ssp_book']}/versions", w.sam, body)
    )


def s_ssp_book_versions_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/ssp-book-versions/{w.ids['ssp_version']}",
        w.sam,
        {"methodology_label": "List-price study (2026)"},
        if_match=w.ids["ssp_version.etag"],
    )


def s_ssp_entries_upsert(w: World) -> HttpResponse:
    entry = {
        "product_code": "SUB-STD",
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"point_value": "100.00"}],
    }
    response = post(
        w.app,
        f"{API}/ssp-book-versions/{w.ids['ssp_version']}/entries",
        w.sam,
        {"entries": [entry]},
    )
    if response.status_code < 400:
        entries = response.json().get("entries") or []  # SspEntriesOut.entries
        if entries and "id" in entries[0]:
            w.ids["ssp_entry"] = str(entries[0]["id"])
    return response


def s_rule_sets_create(w: World) -> HttpResponse:
    return _created(
        w,
        "rule_set",
        post(
            w.app,
            f"{API}/rule-sets",
            w.maya,
            {"code": "APPROVAL_ROUTING", "kind": "APPROVAL_ROUTING"},
        ),
    )


def s_rule_set_versions_create(w: World) -> HttpResponse:
    return _created(
        w,
        "rule_set_version",
        post(w.app, f"{API}/rule-sets/{w.ids['rule_set']}/versions", w.maya, {}),
    )


def s_rule_set_versions_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/rule-set-versions/{w.ids['rule_set_version']}",
        w.maya,
        {"effective_from": "2026-10-01T00:00:00Z"},
        if_match=w.ids["rule_set_version.etag"],
    )


def s_fx_rate_sets_create(w: World) -> HttpResponse:
    return _created(
        w,
        "fx_set",
        post(
            w.app,
            f"{API}/fx-rate-sets",
            w.maya,
            {"code": "SPOT-USD", "name": "USD spot rates", "rate_type": "spot"},
        ),
    )


def s_fx_rate_set_versions_create(w: World) -> HttpResponse:
    return _created(
        w,
        "fx_version",
        post(
            w.app,
            f"{API}/fx-rate-sets/{w.ids['fx_set']}/versions",
            w.maya,
            {
                "coverage_from": JANUARY,
                "coverage_to": "2026-12-31",
                # T-REF-11: the submit refuses a version without a rate; a spot rate names its
                # day (T-REF-12)
                "rates": [
                    {
                        "base_currency": "EUR",
                        "quote_currency": "USD",
                        "rate": "1.100000",
                        "effective_date": "2026-01-31",
                    }
                ],
            },
        ),
    )


def s_fx_rate_set_versions_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/fx-rate-set-versions/{w.ids['fx_version']}",
        w.maya,
        {"coverage_to": "2027-12-31"},
        if_match=w.ids["fx_version.etag"],
    )


def s_tenant_currencies_put(w: World) -> HttpResponse:
    return put(w.app, f"{API}/tenant-currencies", w.tomas, {"currency_codes": ["USD", "EUR"]})


def s_tenant_update(w: World) -> HttpResponse:
    shown = call(w.app, "GET", f"{API}/tenant", headers=cookie_headers(w.tomas.token, key=False))
    assert shown.status_code == 200, shown.text
    return patch(
        w.app, f"{API}/tenant", w.tomas, {"display_name": "Acme Holdings"}, if_match=_etag(shown)
    )


def s_close_checklist_templates_create(w: World) -> HttpResponse:
    second = {"code": "RECON-AR", "name": "Receivables reconciled", "gate_kind": "MANUAL"}
    other = post(w.app, f"{API}/close-checklist-templates", w.tomas, second)  # the item to waive
    assert other.status_code == 201, other.text
    body = {"code": "RECON-BANK", "name": "Bank reconciliation signed", "gate_kind": "MANUAL"}
    return _created(w, "checklist", post(w.app, f"{API}/close-checklist-templates", w.tomas, body))


def s_close_checklist_templates_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/close-checklist-templates/{w.ids['checklist']}",
        w.tomas,
        {"description": COMMENT},
        if_match=w.ids["checklist.etag"],
    )


def s_webhook_endpoints_create(w: World) -> HttpResponse:
    body = {"url": "https://hooks.example.test/erev", "event_kinds": ["period.locked"]}
    return _created(w, "webhook", post(w.app, f"{API}/webhook-endpoints", w.ivy, body))


def s_webhook_endpoints_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/webhook-endpoints/{w.ids['webhook']}",
        w.ivy,
        {"description": COMMENT},
        if_match=w.ids["webhook.etag"],
    )


@contextmanager
def _integration_hooks(w: World) -> Iterator[None]:
    """Composition hooks of the adapter framework, not DB seams (supervisor ruling of 2026-09-22):
    the connection's secret reference names a secret of the workspace's own namespace; the local
    provider serves no adapter credential (05 KEY-09; rulings R-1 and R-50 (d): the store serves
    the three master keys only and an environment variable resolves nothing), so the app's key
    ring is given a secret store that serves the mock adapter's FIXTURE value under that name
    (adapters/mocks/salesforce.py SHARED_SECRET — never a credential) and is restored afterwards;
    the adapter's HTTP client is the in-process ASGI client over the app's mounted mock routes
    (sync.register_http_client_factory), restored to the previous factory in the finally — no
    socket, no network, no live third-party call (the same hooks F-ADM's API tests use)."""
    previous_keyring = w.app.state.keyring
    previous_factory = sync_module._HOOKS.get("http")
    serve_adapter_secrets(w.app, {tenant_ref(w.tenant_id, SF_SECRET_NAME): sf_mock.SHARED_SECRET})
    sync_module.register_http_client_factory(lambda base_url: asgi_client(w.app))
    try:
        yield
    finally:
        sync_module.register_http_client_factory(previous_factory)
        w.app.state.keyring = previous_keyring


def s_integrations_create(w: World) -> HttpResponse:
    body = {
        "code": "sf-sop7",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",  # registered by create_app; mock routes mounted for env test
        "direction": "INBOUND",
        "base_url": f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}",
        "config": {"default_performing_entity": "AVM-US"},
        "secret_ref": tenant_ref(w.tenant_id, SF_SECRET_NAME),
    }
    return _created(w, "integration", post(w.app, f"{API}/integrations", w.ivy, body))


def s_integrations_update(w: World) -> HttpResponse:
    path = f"{API}/integrations/{w.ids['integration']}"  # precondition="row": If-Match
    return patch(w.app, path, w.ivy, {"status": "ACTIVE"}, if_match=_etag_of(w.app, path, w.ivy))


def s_integrations_test(w: World) -> HttpResponse:
    with _integration_hooks(w):
        response = post(w.app, f"{API}/integrations/{w.ids['integration']}/test", w.ivy, {})
    if response.status_code < 400:  # the positive path is a SUCCESS probe through the mock
        assert response.json()["last_test_result"] == "SUCCESS", response.json()
    return response


def s_integrations_sync(w: World) -> HttpResponse:
    # 202 + sync_run.request written at acceptance; the SYNC_RUN job is NOT run here (it would
    # ingest the mock's orders into the walk tenant), as for migrations_import.
    return post(w.app, f"{API}/integrations/{w.ids['integration']}/sync", w.ivy, {})


def s_webhooks_receive(w: World) -> HttpResponse:
    """ADP-01: an unauthenticated, signature-verified receiver; the body is signed by the mock's own
    helper and the audit is written under the tenant's system principal (SYSTEM_ACTOR)."""
    receiver = integration_commands.receiver_id(w.tenant_id, UUID(w.ids["integration"]))
    body = (
        b'{"events": [{"notificationId": "NTF-SOP7-0001", "orderId": "SF-ORD-SOP7-001",'
        b' "version": "1", "replayId": 1}]}'
    )
    with _integration_hooks(w):
        with asgi_client(w.app) as client:
            signed = client.post(
                f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}/webhooks/sign", content=body
            )
        assert signed.status_code == 200, signed.text
        header = {signed.json()["header"]: signed.json()["signature"]}
        return call(
            w.app, "POST", f"{API}/webhooks/SALESFORCE/{receiver}", content=body, headers=header
        )


def s_external_ids_create(w: World) -> HttpResponse:
    body = {
        "integration_connection_id": w.ids["integration"],
        "object_type": "customer",
        "internal_id": w.ids["customer"],
        "external_id": "SF-ACC-SOP7-001",
    }
    return _created(w, "external_id", post(w.app, f"{API}/external-ids", w.maya, body))


def s_roles_create(w: World) -> HttpResponse:
    body = {
        "code": "deal_desk_analyst",
        "name": "Deal desk analyst",
        "permissions": ["contract.read", "report.run"],
    }
    response = _created(w, "role", post(w.app, f"{API}/roles", w.tomas, body))
    if response.status_code < 400:
        w.ids["role.approval"] = str(response.json()["pending_approval_request_id"])
    return response


def s_approvals_approve(w: World) -> HttpResponse:
    return _approve(w, w.ids["role.approval"], w.grace)


def s_approvals_reject(w: World) -> HttpResponse:
    created = post(
        w.app,
        f"{API}/roles",
        w.tomas,
        {"code": "rejected_role", "name": "Rejected role", "permissions": ["contract.read"]},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["pending_approval_request_id"]
    return post(w.app, f"{API}/approvals/{request_id}/reject", w.grace, {"comment": "Not needed."})


def s_approvals_withdraw(w: World) -> HttpResponse:
    created = post(
        w.app,
        f"{API}/roles",
        w.tomas,
        {"code": "withdrawn_role", "name": "Withdrawn role", "permissions": ["contract.read"]},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["pending_approval_request_id"]
    return post(w.app, f"{API}/approvals/{request_id}/withdraw", w.tomas, {"comment": "Wrong role"})


def s_users_invite(w: World) -> HttpResponse:
    body = {
        "email": f"probe-{random_suffix()}@members.test",
        "display_name": "Probe User",
        "roles": [{"role_id": w.role_id("viewer"), "is_all_entities": True}],
    }
    return _created(w, "membership", post(w.app, f"{API}/users", w.tomas, body))


def s_users_resend_invitation(w: World) -> HttpResponse:
    return post(w.app, f"{API}/users/{w.ids['membership']}/resend-invitation", w.tomas, {})


def s_users_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/users/{w.ids['membership']}",
        w.tomas,
        {"display_name": "Probe User (renamed)"},
        if_match=_etag_of(w.app, f"{API}/users/{w.ids['membership']}", w.tomas),  # resend moved it
    )


def _assigned(w: World, membership_id: UUID) -> HttpResponse:
    """POST /role-assignments answers REQUESTED with the id the row WILL take; the row exists once
    the ROLE_ASSIGNMENT request is approved (access.approve — Grace, never the assignee)."""
    body = {
        "membership_id": str(membership_id),
        "role_id": w.role_id("viewer"),
        "is_all_entities": True,
    }
    response = post(w.app, f"{API}/role-assignments", w.tomas, body)
    if response.status_code < 400:
        approved = _approve(w, str(response.json()["approval_request_id"]), w.grace)
        assert approved.status_code == 200, approved.text
    return response


def _revoked_assignment(w: World, membership_id: UUID) -> None:
    created = _assigned(w, membership_id)
    assert created.status_code == 201, created.text
    path = f"{API}/role-assignments/{created.json()['id']}/revoke"
    revoked = post(w.app, path, w.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text


def s_role_assignments_create(w: World) -> HttpResponse:
    return _created(w, "assignment", _assigned(w, w.sam.member.membership_id))


def s_role_assignments_revoke(w: World) -> HttpResponse:
    return post(
        w.app, f"{API}/role-assignments/{w.ids['assignment']}/revoke", w.tomas, {"reason": REASON}
    )


def s_users_suspend(w: World) -> HttpResponse:
    # Only an ACTIVE membership suspends (users.NOT_ACTIVE); the invited probe never accepted.
    active = colleague(w.tenant_id, "probe_active")
    w.ids["membership_active"] = str(active.membership_id)
    path = f"{API}/users/{w.ids['membership_active']}/suspend"
    return post(w.app, path, w.tomas, {"reason": REASON})


def s_users_reactivate(w: World) -> HttpResponse:
    path = f"{API}/users/{w.ids['membership_active']}/reactivate"
    return post(w.app, path, w.tomas, {"reason": REASON})


def s_users_remove(w: World) -> HttpResponse:
    return post(w.app, f"{API}/users/{w.ids['membership']}/remove", w.tomas, {"reason": REASON})


def s_users_anonymise(w: World) -> HttpResponse:
    """05 PRV-07 a (P8 SOP-5; main 143062c8): erase another person of the tenant — never the caller
    (403 forbidden) — with a reason of at least 10 characters. The command needs a step-up at most
    five minutes old: Tomas's step-up at the world build (one TOTP step after his enrolment) is at
    the clock's current instant and the frozen clock does not move afterwards, so it is fresh; a
    second code at that step would be a T-PLT-04 replay, so none is sent."""
    lena = colleague(w.tenant_id, "lena")
    return post(w.app, f"{API}/users/{lena.membership_id}/anonymise", w.tomas, {"reason": REASON})


def s_api_clients_create(w: World) -> HttpResponse:
    """The client's scopes are an access grant (supervisor ruling R-38 (iii)): Tomas's request
    waits for another access approver, and the scenario that issues its secret has Grace approve
    it first."""
    created = _created(
        w,
        "client",
        post(
            w.app,
            f"{API}/api-clients",
            w.tomas,
            {"name": "svc-salesforce", "scopes": ["contract.read"]},
        ),
    )
    if created.status_code < 400:
        w.ids["client.request"] = str(created.json()["approval_request_id"])
    return created


def s_api_clients_rotate_secret(w: World) -> HttpResponse:
    """Grace approves the grant of ``s_api_clients_create`` (ruling R-38 (iii): only a client in
    force is issued a secret, and later revoked); Tomas then issues the first secret, the
    command this scenario walks."""
    granted = _approve(w, w.ids["client.request"], w.grace)
    assert granted.status_code == 200, granted.text
    return post(w.app, f"{API}/api-clients/{w.ids['client']}/rotate-secret", w.tomas, {})


def s_api_clients_revoke(w: World) -> HttpResponse:
    return post(w.app, f"{API}/api-clients/{w.ids['client']}/revoke", w.tomas, {"reason": REASON})


def s_approvals_bulk_approve(w: World) -> HttpResponse:
    """Two fresh ROLE_CHANGE requests of Tomas's, approved together by Grace (access.approve, MFA at
    enrolment) with each subject hash and impact-preview hash; HTTP stays 200 when an item is
    refused, so every result is asserted APPROVED with no problem."""
    items: list[dict[str, Any]] = []
    for code in ("bulk_role_one", "bulk_role_two"):
        created = post(
            w.app,
            f"{API}/roles",
            w.tomas,
            {"code": code, "name": f"Bulk {code}", "permissions": ["contract.read"]},
        )
        assert created.status_code == 201, created.text
        request_id = str(created.json()["pending_approval_request_id"])
        detail = get(w.app, f"{API}/approvals/{request_id}", w.grace)
        assert detail.status_code == 200, detail.text
        request = detail.json()
        item = {
            "approval_request_id": request_id,
            "subject_content_sha256": request["subject"]["content_sha256"],
        }
        if request.get("impact_preview") is not None:
            item["impact_preview_sha256"] = request["impact_preview"]["sha256"]
        items.append(item)
    response = post(
        w.app, f"{API}/approvals/bulk-approve", w.grace, {"items": items, "comment": COMMENT}
    )
    if response.status_code < 400:
        results = response.json()["results"]
        outcomes = [(item["status"], item["problem"]) for item in results]
        assert outcomes == [("APPROVED", None)] * 2, results
    return response


def s_approval_delegations_create(w: World) -> HttpResponse:
    now = w.clock.now()
    body = {
        "delegate_membership_id": str(w.grace.member.membership_id),
        "permissions": ["access.approve"],  # only approval permissions delegate (T-PLT-21)
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=7)).isoformat(),
        "reason": "Covering the close week",
    }
    return _created(w, "delegation", post(w.app, f"{API}/approval-delegations", w.tomas, body))


def s_approval_delegations_revoke(w: World) -> HttpResponse:
    return post(
        w.app,
        f"{API}/approval-delegations/{w.ids['delegation']}/revoke",
        w.tomas,
        {"reason": REASON},
    )


def s_sod_rule_versions_create(w: World) -> HttpResponse:
    body = {
        "name": "Prepare vs approve journals",
        "function_a_permissions": ["journal.run"],
        "function_b_permissions": ["journal.approve"],
        "rationale": "One person must not prepare and approve the same journal.",
    }
    return post(w.app, f"{API}/sod-rules/SoD-3/versions", w.tomas, body)


def s_sod_exceptions_create(w: World) -> HttpResponse:
    now = w.clock.now()
    body = {
        "sod_rule_code": "SoD-3",
        "membership_id": str(w.root.membership_id),
        "compensating_control": "The controller reviews every journal of the month.",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=30)).isoformat(),
        "comment": "Small team during the migration.",
    }
    response = _created(w, "sod_exception", post(w.app, f"{API}/sod-exceptions", w.tomas, body))
    if response.status_code < 400:
        w.ids["sod_exception.approval"] = str(response.json()["approval_request_id"])
    return response


def s_access_reviews_create(w: World) -> HttpResponse:
    body = {
        "name": "Q3 access review",
        "as_of": w.clock.now().isoformat(),
        "reviewer_membership_ids": [
            str(w.grace.member.membership_id),
            str(w.tomas.member.membership_id),
        ],
    }
    return _created(w, "review", post(w.app, f"{API}/access-reviews", w.tomas, body))


def s_access_reviews_start(w: World) -> HttpResponse:
    return post(w.app, f"{API}/access-reviews/{w.ids['review']}/start", w.tomas, {})


def s_access_reviews_items_decide(w: World) -> HttpResponse:
    listed = get(w.app, f"{API}/access-reviews/{w.ids['review']}/items", w.grace)
    assert listed.status_code == 200, listed.text
    item = next(
        i for i in listed.json()["items"] if i["membership_id"] == str(w.sam.member.membership_id)
    )
    w.ids["review_item"] = str(item["id"])
    # Sam's access is questioned: the revocation is confirmed by the next scenario.
    return post(
        w.app,
        f"{API}/access-reviews/{w.ids['review']}/items/{item['id']}/decide",
        w.grace,
        {"decision": "REVOKE_REQUESTED", "comment": "Contractor left the engagement."},
    )


def s_access_reviews_cancel(w: World) -> HttpResponse:
    created = post(
        w.app,
        f"{API}/access-reviews",
        w.tomas,
        {
            "name": "Cancelled review",
            "as_of": w.clock.now().isoformat(),
            "reviewer_membership_ids": [str(w.grace.member.membership_id)],
        },
    )
    assert created.status_code == 201, created.text
    return post(w.app, f"{API}/access-reviews/{created.json()['id']}/cancel", w.tomas, {})


def s_report_runs_create(w: World) -> HttpResponse:
    response = post(
        w.app,
        f"{API}/report-runs",
        w.maya,
        {"report_code": "api_client_inventory", "parameters": {}, "output_format": "JSON"},
    )
    if response.status_code < 400:
        w.ids["run"] = str(response.headers["x-erev-report-run-id"])
        _run_job(w, UUID(str(response.json()["id"])))
    return response


def s_report_runs_rerun(w: World) -> HttpResponse:
    return post(w.app, f"{API}/report-runs/{w.ids['run']}/rerun", w.maya, {})


def s_jobs_cancel(w: World) -> HttpResponse:
    queued = post(
        w.app,
        f"{API}/report-runs",
        w.maya,
        {"report_code": "api_client_inventory", "parameters": {}, "output_format": "JSON"},
    )
    assert queued.status_code == 202, queued.text
    return post(w.app, f"{API}/jobs/{queued.json()['id']}/cancel", w.maya, {})


def s_audit_events_verify(w: World) -> HttpResponse:
    return post(w.app, f"{API}/audit-events/verify", w.maya, {})


def s_me_notification_preferences_put(w: World) -> HttpResponse:
    return _me(
        w,
        "PUT",
        f"{API}/me/notification-preferences",
        {"items": [{"kind": "ITEM_APPROVED", "in_app": True, "email": False}]},
    )


def s_me_preferences_update(w: World) -> HttpResponse:
    return _me(w, "PATCH", f"{API}/me/preferences", {"theme": "DARK"})


def s_me_notifications_read_all(w: World) -> HttpResponse:
    return _me(w, "POST", f"{API}/me/notifications/read-all", {"before": w.clock.now().isoformat()})


@contextmanager
def _system_uow(w: World, request_id: str) -> Iterator[UnitOfWork]:
    """A unit of work of the walk tenant's SYSTEM principal: a fixture's own writes (a notification
    to read, a fixture run's producer audit fact), never the evidence of a walked route."""
    ctx = RequestContext(
        principal=system_principal(w.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=w.clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=w.clock, keyring=w.keyring, files=w.runtime.files) as uow:
        yield uow


def s_me_notifications_read(w: World) -> HttpResponse:
    with _system_uow(w, "sop7-notify") as uow:
        notify(
            uow,
            recipient_membership_ids=[w.root.membership_id],
            kind=NotificationKind.ITEM_APPROVED,
            title="SOP-7 probe",
        )
        uow.commit()
    listed = call(
        w.app, "GET", f"{API}/me/notifications", headers=cookie_headers(w.maya.token, key=False)
    )
    assert listed.status_code == 200, listed.text
    notification_id = listed.json()["items"][0]["id"]
    return _me(w, "POST", f"{API}/me/notifications/{notification_id}/read", None)


# --- session and identity routes (security_event evidence) ---------------------------------------


def s_session_login(w: World) -> HttpResponse:
    fresh = colleague(w.tenant_id, "leo")
    w.ids["leo.email"] = fresh.email
    return call(w.app, "POST", LOGIN, json={"email": fresh.email, "password": PASSWORD})


def s_me_mfa_enroll(w: World) -> HttpResponse:
    signed = sign_in(w.app, w.ids["leo.email"])
    w.ids["leo.token"] = signed.token
    w.ids["leo.csrf"] = signed.csrf_token
    response = call(
        w.app,
        "POST",
        f"{API}/me/mfa/enroll",
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    if response.status_code < 400:
        w.ids["leo.secret"] = str(response.json()["secret_base32"])
    return response


def s_me_change_password(w: World) -> HttpResponse:
    body = {"current_password": PASSWORD, "new_password": "Oskar!Ledger2027"}
    return call(
        w.app,
        "POST",
        f"{API}/me/password",
        json=body,
        headers=cookie_headers(w.ids["leo.token"], w.ids["leo.csrf"]),
    )


def s_session_verify_mfa(w: World) -> HttpResponse:
    """The sign-in challenge of an enrolled user (04 E-79 ``MFA_CHALLENGE_PASSED``, rev 1.189;
    ruling R-111 (6)), passed with the code of the next TOTP step: a step is accepted once, and
    the confirmation spent the current one."""
    signed = sign_in(w.app, w.ids["leo.email"], "Oskar!Ledger2027")
    code = totp.code_at(w.ids["leo.secret"], totp.time_step(w.clock.now()) + 1)
    return call(
        w.app,
        "POST",
        f"{API}/session/mfa",
        json={"code": code},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )


def s_session_logout(w: World) -> HttpResponse:
    signed = sign_in(w.app, w.ids["leo.email"], "Oskar!Ledger2027")
    return call(
        w.app,
        "POST",
        f"{API}/session/logout",
        headers=cookie_headers(signed.token, signed.csrf_token),
    )


# --- second tranche ------------------------------------------------------------------------------


def s_access_reviews_items_confirm_revocation(w: World) -> HttpResponse:
    # T-PLT-41: the member's access must have been revoked at or after the campaign started — a
    # viewer role assigned to Sam (approved by Grace) and revoked by Tomas, under the frozen clock.
    _revoked_assignment(w, w.sam.member.membership_id)
    return post(
        w.app,
        f"{API}/access-reviews/{w.ids['review']}/items/{w.ids['review_item']}/confirm-revocation",
        w.tomas,
        {},
    )


def s_access_reviews_complete(w: World) -> HttpResponse:
    """Every remaining item is certified first (grace decides the others, tomas decides grace's)."""
    listed = get(w.app, f"{API}/access-reviews/{w.ids['review']}/items", w.tomas)
    assert listed.status_code == 200, listed.text
    for item in listed.json()["items"]:
        if item["decision"] != "PENDING" or item["id"] == w.ids["review_item"]:
            continue  # undecided items carry the literal "PENDING", which is truthy
        reviewer = (
            w.tomas if item["membership_id"] == str(w.grace.member.membership_id) else w.grace
        )
        decided = post(
            w.app,
            f"{API}/access-reviews/{w.ids['review']}/items/{item['id']}/decide",
            reviewer,
            {"decision": "CERTIFIED"},
        )
        assert decided.status_code == 200, decided.text
    return post(w.app, f"{API}/access-reviews/{w.ids['review']}/complete", w.tomas, {})


def s_files_upload(w: World) -> HttpResponse:
    response = call(
        w.app,
        "POST",
        f"{API}/files",
        data={"purpose": "SSP_STUDY"},
        files={"file": ("study.pdf", PDF, "application/pdf")},
        headers=cookie_headers(w.sam.token, w.sam.csrf_token),
    )
    if response.status_code < 400:
        w.ids["file"] = str(response.json()["id"])
    return response


def s_files_shred(w: World) -> HttpResponse:
    """05 PRV-07 b (P8 SOP-5; main 143062c8): a fresh ATTACHMENT-purpose upload of Tomas's
    (``settings.manage``) is shredded — its own file, so the walk's SSP study stays readable."""
    uploaded = call(
        w.app,
        "POST",
        f"{API}/files",
        data={"purpose": "ATTACHMENT"},
        files={"file": ("personal.pdf", PDF, "application/pdf")},
        headers=cookie_headers(w.tomas.token, w.tomas.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    return post(w.app, f"{API}/files/{uploaded.json()['id']}/shred", w.tomas, {"reason": REASON})


def s_files_request_shred(w: World) -> HttpResponse:
    """05 PRV-07 b rev 1.81 (rulings R-49 (a), R-86 (c); lane SECFIX-IMP): the walk's SSP study
    is the evidence of the version submitted one step before, so one person does not shred it
    — Tomas (``settings.manage``; his step-up of the world build is fresh, as for
    ``users_anonymise``) requests its shred. The request stays pending: the walk decides
    nothing about it, so the study stays readable."""
    return post(w.app, f"{API}/files/{w.ids['file']}/request-shred", w.tomas, {"reason": REASON})


def s_attachments_create(w: World) -> HttpResponse:
    body = {
        "file_object_id": w.ids["file"],
        "subject_type": "ssp_book_version",
        "subject_id": w.ids["ssp_version"],
        "description": "List-price study (SOP-7 walk)",
    }
    return _created(w, "attachment", post(w.app, f"{API}/attachments", w.sam, body))


def s_ssp_book_versions_submit(w: World) -> HttpResponse:
    path = (
        f"{API}/ssp-book-versions/{w.ids['ssp_version']}"  # If-Match, re-read (stale after update)
    )
    body = {"comment": COMMENT}
    return post(w.app, f"{path}/submit", w.sam, body, if_match=_etag_of(w.app, path, w.sam))


def s_ssp_book_versions_withdraw(w: World) -> HttpResponse:
    return post(
        w.app,
        f"{API}/ssp-book-versions/{w.ids['ssp_version']}/withdraw",
        w.sam,
        {"comment": COMMENT},
    )


def s_ssp_entries_delete(w: World) -> HttpResponse:
    return delete(
        w.app, f"{API}/ssp-book-versions/{w.ids['ssp_version']}/entries/{w.ids['ssp_entry']}", w.sam
    )


def s_attachments_void(w: World) -> HttpResponse:
    return post(w.app, f"{API}/attachments/{w.ids['attachment']}/void", w.sam, {"reason": REASON})


def s_fx_rate_set_versions_submit(w: World) -> HttpResponse:
    path = f"{API}/fx-rate-set-versions/{w.ids['fx_version']}"  # If-Match required (API-C-08)
    body = {"comment": COMMENT}
    return post(w.app, f"{path}/submit", w.maya, body, if_match=_etag_of(w.app, path, w.maya))


def s_fx_rate_set_versions_withdraw(w: World) -> HttpResponse:
    path = f"{API}/fx-rate-set-versions/{w.ids['fx_version']}"
    body = {"comment": COMMENT}
    return post(w.app, f"{path}/withdraw", w.maya, body, if_match=_etag_of(w.app, path, w.maya))


def s_config_test_cases_create(w: World) -> HttpResponse:
    body = {
        "subject_type": "rule_set_version",
        "subject_id": w.ids["rule_set_version"],
        "name": "Contract activation",
        "input": {"subject.type": "CONTRACT_ACTIVATION"},
        "expected_output": {"matched": False},
    }
    return _created(w, "test_case", post(w.app, f"{API}/config-test-cases", w.maya, body))


def s_config_test_cases_update(w: World) -> HttpResponse:
    response = patch(
        w.app,
        f"{API}/config-test-cases/{w.ids['test_case']}",
        w.maya,
        {"name": "Contract activation (renamed)"},
        if_match=w.ids["test_case.etag"],
    )
    if response.status_code < 400:  # the delete needs the CURRENT ETag; there is no GET by id
        w.ids["test_case.etag"] = response.headers["ETag"]
    return response


def s_config_test_cases_delete(w: World) -> HttpResponse:
    # precondition="row": the delete carries If-Match (the support delete() helper sends none).
    headers = cookie_headers(
        w.maya.token, w.maya.csrf_token, **{"If-Match": w.ids["test_case.etag"]}
    )
    return call(w.app, "DELETE", f"{API}/config-test-cases/{w.ids['test_case']}", headers=headers)


def s_rule_set_version_rules_upsert(w: World) -> HttpResponse:
    """A DATA_QUALITY set, whose rule outputs are the documented severity / message pair."""
    created = post(w.app, f"{API}/rule-sets", w.maya, {"code": "DQ-PROBE", "kind": "DATA_QUALITY"})
    assert created.status_code == 201, created.text
    w.ids["dq_set"] = str(created.json()["id"])
    version = post(w.app, f"{API}/rule-sets/{created.json()['id']}/versions", w.maya, {})
    assert version.status_code == 201, version.text
    w.ids["dq_version"] = str(version.json()["id"])
    body = {
        "rule_key": "DQ-PROBE-1",
        "conditions": [],
        "outputs": {"severity": "WARNING", "message": "Probe rule (SOP-7 walk)"},
        "priority": 0,
    }
    return _created(
        w,
        "dq_rule",
        post(w.app, f"{API}/rule-set-versions/{w.ids['dq_version']}/rules", w.maya, body),
    )


def s_rule_set_version_rules_delete(w: World) -> HttpResponse:
    """A throwaway second rule is deleted BEFORE the version's tests run: a delete after /test
    changes the content and submit refuses CONTENT_CHANGED (REQ-POL-003)."""
    path = f"{API}/rule-set-versions/{w.ids['dq_version']}/rules"
    body = {
        "rule_key": "DQ-PROBE-TMP",
        "conditions": [],
        # 04 T-REF-26 DATA_QUALITY outputs: `severity` is ERROR or WARNING (table 15.4-E)
        "outputs": {"severity": "WARNING", "message": "Throwaway rule (SOP-7 walk)"},
        "priority": 1,
    }
    created = post(w.app, path, w.maya, body)
    assert created.status_code == 201, created.text
    return delete(w.app, f"{path}/{created.json()['id']}", w.maya)


def s_rule_set_version_test_cases_create(w: World) -> HttpResponse:
    # DQ-PROBE-1 has no conditions, so it matches every fact set (rules.py all([]) is True).
    body = {"name": "Probe case", "input": {}, "expected_output": {"matched": True}}
    return post(w.app, f"{API}/rule-set-versions/{w.ids['dq_version']}/test-cases", w.maya, body)


def s_rule_set_versions_lint(w: World) -> HttpResponse:
    return post(w.app, f"{API}/rule-set-versions/{w.ids['dq_version']}/lint", w.maya, {})


def s_rule_set_versions_test(w: World) -> HttpResponse:
    return post(w.app, f"{API}/rule-set-versions/{w.ids['dq_version']}/test", w.maya, {})


def s_rule_set_versions_submit(w: World) -> HttpResponse:
    response = post(
        w.app, f"{API}/rule-set-versions/{w.ids['dq_version']}/submit", w.maya, {"comment": COMMENT}
    )
    if response.status_code < 400:
        w.ids["dq_version.approval"] = str(response.json()["pending_approval_request_id"])
    return response


def s_rule_set_versions_publish(w: World) -> HttpResponse:
    return _confirm_publish(
        w, "dq_version.approval", f"{API}/rule-set-versions/{w.ids['dq_version']}/publish", w.nora
    )


def s_pob_template_versions_create(w: World) -> HttpResponse:
    body = {**TPL_SUB_DAILY, "effective_from": f"{JANUARY}T00:00:00Z"}  # AwareDatetime
    return _created(
        w,
        "tpl_version",
        post(w.app, f"{API}/pob-templates/{w.ids['template']}/versions", w.maya, body),
    )


def s_pob_template_versions_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/pob-template-versions/{w.ids['tpl_version']}",
        w.maya,
        {"effective_from": "2026-02-01T00:00:00Z"},
        if_match=w.ids["tpl_version.etag"],
    )


def s_pob_template_versions_test(w: World) -> HttpResponse:
    # /test refuses a version without a case (CASES_REQUIRED): one passing case, the walk's product.
    case = {
        "subject_type": "pob_template_version",
        "subject_id": w.ids["tpl_version"],
        "name": "SUB-STD 12 months",
        "input": {
            "booking_date": JANUARY,
            "lines": [
                {
                    "obligation_key": "POB-01",
                    "product_code": "SUB-STD",
                    "quantity": "12",
                    "total_price": "12000.00",
                    "start_date": JANUARY,
                    "end_date": "2026-12-31",
                }
            ],
        },
        "expected_output": {"drafts": [{"obligation_key": "POB-01"}]},
    }
    added = post(w.app, f"{API}/config-test-cases", w.maya, case)
    assert added.status_code == 201, added.text
    return post(w.app, f"{API}/pob-template-versions/{w.ids['tpl_version']}/test", w.maya, {})


def s_pob_template_versions_submit(w: World) -> HttpResponse:
    response = post(
        w.app,
        f"{API}/pob-template-versions/{w.ids['tpl_version']}/submit",
        w.maya,
        {"comment": COMMENT},
    )
    if response.status_code < 400:
        w.ids["tpl_version.approval"] = str(response.json()["pending_approval_request_id"])
    return response


def s_pob_template_versions_publish(w: World) -> HttpResponse:
    path = f"{API}/pob-template-versions/{w.ids['tpl_version']}/publish"
    return _confirm_publish(w, "tpl_version.approval", path, w.nora)


def s_saved_views_create(w: World) -> HttpResponse:
    body = {
        "screen_code": "SF-02",
        "name": "Probe view",
        "config": {"filters": {"status": "DRAFT"}},
    }
    return _created(w, "view", post(w.app, f"{API}/saved-views", w.maya, body))


def s_saved_views_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/saved-views/{w.ids['view']}",
        w.maya,
        {"name": "Probe view (renamed)"},
        if_match=w.ids["view.etag"],
    )


def s_saved_views_delete(w: World) -> HttpResponse:
    return delete(w.app, f"{API}/saved-views/{w.ids['view']}", w.maya)


def s_sod_exceptions_revoke(w: World) -> HttpResponse:
    approved = _approve(w, w.ids["sod_exception.approval"], w.grace)
    assert approved.status_code == 200, approved.text
    return post(
        w.app, f"{API}/sod-exceptions/{w.ids['sod_exception']}/revoke", w.tomas, {"reason": REASON}
    )


def s_roles_propose_change(w: World) -> HttpResponse:
    body = {"permissions": ["contract.read", "report.run", "audit.read"], "comment": COMMENT}
    path = f"{API}/roles/{w.ids['role']}"  # precondition="row": If-Match required
    return post(
        w.app, f"{path}/propose-change", w.tomas, body, if_match=_etag_of(w.app, path, w.tomas)
    )


def s_products_propose_principal_agent_change(w: World) -> HttpResponse:
    body = {"principal_agent": "AGENT", "rationale": "Marketplace resale (SOP-7 walk)."}
    return post(
        w.app, f"{API}/products/{w.ids['product']}/propose-principal-agent-change", w.maya, body
    )


def s_products_propose_policy_values_change(w: World) -> HttpResponse:
    # One request per product is open at a time (the step above left one on ``product``), so the
    # proposal names a product of its own (04 API-R-23 rev 1.110).
    created = post(
        w.app, f"{API}/products", w.maya, {"code": "PV-1", "name": "Policy values (SOP-7 walk)"}
    )
    assert created.status_code == 201, created.text
    body = {
        "policy_values": {"recognition.time_convention": "MONTHLY_EVEN"},
        "rationale": "Earned by whole months (SOP-7 walk).",
    }
    return post(
        w.app,
        f"{API}/products/{created.json()['id']}/propose-policy-values-change",
        w.maya,
        body,
    )


def s_products_bundle_components_put(w: World) -> HttpResponse:
    bundle = post(
        w.app,
        f"{API}/products",
        w.maya,
        {"code": "BNDL-1", "name": "Bundle", "is_bundle": True, "principal_agent": "PRINCIPAL"},
    )
    assert bundle.status_code == 201, bundle.text
    component = {
        "component_product_id": w.ids["product"],
        "sequence": 1,
        "valid_from": JANUARY,
        "quantity_per_bundle": "1",
    }
    return put(
        w.app,
        f"{API}/products/{bundle.json()['id']}/bundle-components",
        w.maya,
        {"components": [component]},
    )


def s_support_grants_create(w: World) -> HttpResponse:
    services = operator_services(w.keyring, w.clock, w.app.state.settings.file_root)
    operator = create_operator(services)
    now = w.clock.now()
    body = {
        "operator_email": operator["email"],
        "reason": "Investigate export failure (SOP-7 walk)",
        "ticket_ref": "SUP-2291",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(days=1)).isoformat(),
    }
    response = _created(w, "grant", post(w.app, f"{API}/support-grants", w.tomas, body))
    if response.status_code < 400 and response.json().get("approval_request_id"):
        w.ids["grant.approval"] = str(response.json()["approval_request_id"])
    return response


def s_support_grants_revoke(w: World) -> HttpResponse:
    if "grant.approval" in w.ids:
        approved = _approve(w, w.ids["grant.approval"], w.grace)
        assert approved.status_code == 200, approved.text
    return post(w.app, f"{API}/support-grants/{w.ids['grant']}/revoke", w.tomas, {"reason": REASON})


@contextmanager
def _snapshot_handler() -> Iterator[None]:
    """``TENANT_SNAPSHOT`` registered for the block, as the snapshot witnesses register it
    (``test_sandbox_load.py`` fixture ``job``): only the worker's import of its handler modules
    registers the kind (DG-ARC-08), and this module never imports the worker."""
    from erev_api.domain.platform import snapshot_job

    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    try:
        yield
    finally:
        if not present:
            registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


def s_tenant_snapshots_request(w: World) -> HttpResponse:
    """Walk line 9 (supervisor ruling R-50 (d); lane F-SNP): ``tenant_sandboxes_request`` restores
    a SUCCEEDED snapshot, so this scenario's job must run to its end. The exporter refuses without
    a human retention confirmation (ruling Q-4), which is a precondition of the export and not
    the audited subject: it is seeded by the snapshot lane's helper
    (``support.snapshots.confirm_retention``, in force from the day before the walk's instant), as
    every snapshot witness seeds it; the job then runs under a registered handler."""
    with tenant_session(_db(w.tenant_id)) as session:
        confirm_retention(session, w.tenant_id, at=w.clock.now() - timedelta(days=1))
    body = {"known_at": w.clock.now().isoformat(), "purpose": "STORED_BACKUP"}
    response = post(w.app, f"{API}/tenant/snapshots", w.nora, body)  # tenant.snapshot needs MFA
    if response.status_code < 400:
        w.ids["snapshot"] = str(response.headers["X-Erev-Tenant-Snapshot-Id"])
        with _snapshot_handler():
            _run_job(w, UUID(str(response.json()["id"])))
    return response


def s_tenant_sandboxes_request(w: World) -> HttpResponse:
    body = {"tenant_snapshot_id": w.ids["snapshot"], "name": "Probe sandbox"}
    return post(w.app, f"{API}/tenant/sandboxes", w.nora, body)  # an MFA permission, as above


def s_tenant_reset_request(w: World) -> HttpResponse:
    """BUILD_SPEC SNP-3 (lane F-SNP): ``POST /tenant/reset`` exists only in a sandbox (a production
    tenant answers 409), so the call runs in a sandbox tenant of its own — the tenant row, its
    chain head and the system roles, as a load's first steps leave them
    (``support.snapshots.seeded_sandbox``) — by a Controller of it, verified at enrolment
    (``sandbox.reset`` is an MFA permission with a step-up). The evidence is that sandbox's."""
    sandbox = seeded_sandbox(w.keyring, w.clock)
    rhea_member = colleague(sandbox, "rhea")
    assign(rhea_member, "controller")
    rhea = enrolled(w.app, w.clock, rhea_member)
    w.evidence_tenant_id = sandbox
    body = {"mode": "EMPTY", "reason": "Rehearsal complete (SOP-7 walk)"}
    return post(w.app, f"{API}/tenant/reset", rhea, body)


def _lock_gate_facts(w: World, state: Mapping[str, Any]) -> None:
    """SOP7-SEAM-EXC-1 (supervisor ruling of 2026-09-22; for Codex review at this commit). The
    audited subjects are the lock / permanent-lock / reopen commands; the gate facts are
    preconditions produced by an external GL acknowledgement for which the product deliberately
    exposes no route; the seeds are the close lane's reviewed helpers. Only the two gate facts a
    lock decision needs are seeded — an acknowledged journal run (JE_BALANCED, JE_COMPLETE,
    BATCHES_ACKNOWLEDGED) and reviewed reconciliations (RECONCILIATIONS_GENERATED) — exactly as
    tests/domain/close/test_reopen.py does. The reconciliation-gate parameter is tenant-publishable
    but period-pinned (effective only from a future period's first day), so it cannot apply at the
    walk's lock instant — verified at file:line: registry/platform.py:56–78 (allowed_levels TENANT,
    pin "P"), registry_versions.py:350–394 (a pin-"P" version starts on the first day of a FUTURE
    open period), gates.py:575–586 (the gates resolve it at the lock's known_at, the frozen clock).
    No policy is published for it here. The evidence covers the lock COMMANDS, not the production
    of gate facts. The fixture run carries the producer's ``journal_run.calculate`` audit fact, as
    ``close_world.acknowledged_run`` records it: without it the run is unverifiable under
    R5-ORDER-1, covers nothing and ``JE_COMPLETE`` fails "held detail unverifiable" (F-CLO record
    §25.22)."""
    entity_id, period_id = UUID(w.ids["entity"]), UUID(str(state["period"]["id"]))
    with tenant_session(_db(w.tenant_id)) as session:
        run = acknowledged_run_for(
            session,
            tenant_id=w.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=w.clock.now(),
        )
        reviewed_reconciliations_for(
            session,
            tenant_id=w.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=w.clock.now(),
        )
        # The third gate fact since 04 rev 1.172 (supervisor ruling R-114 (b)): the period's close
        # run SUCCEEDED (CLOSE_RUN_COMPLETED) — the close lane's fixture row, as the two above.
        close_run_succeeded_for(
            session,
            tenant_id=w.tenant_id,
            entity_id=entity_id,
            period_id=period_id,
            now=w.clock.now(),
        )
    with _system_uow(w, "sop7-run-calculation") as uow:
        uow.audit(
            action=RUN_AUDIT_ACTION,
            object_type=RUN_AUDIT_OBJECT_TYPE,
            object_id=UUID(str(run.run["id"])),
            object_version="1",
            after=run_audit_after(run),
        )
        uow.commit()


def s_periods_request_lock(w: World) -> HttpResponse:
    """FY2026-P01 — the earliest period first (SM-07): put back in close after the cancel, the
    pending checklist waiver decided by Nora, the two gate facts seeded (SOP7-SEAM-EXC-1, see
    _lock_gate_facts), then the lock requested by Maya; Nora (MFA controller, not the requester)
    approves it in the next scenario. A lock request reads the gates from the period's FACTS
    (``gates.evaluate_gates``; BR-CLS-01); an APPROVED waiver clears the gate it names (supervisor
    ruling R-55 (b)), a waive only opens an ``EXCEPTION_WAIVER`` request, and every pending
    request of the entity fails APPROVALS_CLEARED — so no further waiver is requested here."""
    state = _period_state(w)
    closing = post(
        w.app,
        f"{API}/periods/{state['id']}/start-close",
        w.maya,
        {"comment": COMMENT},
        if_match=f'"r{state["row_version"]}"',
    )
    assert closing.status_code == 200, closing.text
    waived = _approve(w, w.ids["period.waiver_approval"], w.nora)
    assert waived.status_code == 200, waived.text
    _lock_gate_facts(w, state)
    current = _period_state(w)
    response = post(
        w.app,
        f"{API}/periods/{state['id']}/request-lock",
        w.maya,
        {"certification_comment": "Reconciliations signed and reviewed (SOP-7 walk)."},
        if_match=f'"r{current["row_version"]}"',
    )
    if response.status_code < 400 and response.json().get("approval_request_id"):
        w.ids["period_p01.lock_approval"] = str(response.json()["approval_request_id"])
    return response


def s_users_reset_mfa(w: World) -> HttpResponse:
    """Last of the tenant-admin scenarios: grace's factor is reset after her approvals are done."""
    return post(
        w.app,
        f"{API}/users/{w.grace.member.membership_id}/reset-mfa",
        w.tomas,
        {"reason": "Lost her phone (SOP-7 walk)."},
    )


# --- third tranche: engine (PRD K-02 world), imports, journals, migrations, policies, session --


def _engine(w: World) -> K02World:
    """The K-02 world (its own tenant, actors maya = ``place.author``, priya, marcus); every engine
    scenario reads its evidence there (``evidence_tenant_id``)."""
    if w.engine is None:
        files = w.runtime.files
        w.engine = k02_world(w.app, w.keyring, w.clock, files)  # type: ignore[arg-type]
        booked = booked_contract(
            w.engine.place, k02_seat_month_body(w.engine.customer_id), activate=False
        )
        activated = activated_contract(w.engine.place, booked)
        computed(w.engine.place, UUID(str(activated.combination_group["id"])))
        w.ids["k02.active"] = str(activated.contract["id"])
    w.evidence_tenant_id = w.engine.place.tenant_id
    return w.engine


def _etag_of(app: FastAPI, path: str, actor: Actor) -> str:
    shown = get(app, path, actor)
    assert shown.status_code == 200, shown.text
    return _etag(shown)


def _run_job_in(w: World, tenant_id: UUID, job_id: UUID) -> None:
    with tenant_session(_db(tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=w.runtime)


def _draft_body(w: World) -> dict[str, Any]:
    """The walk's K-02 draft: a fresh external id that replace-draft keeps (T-CON-01
    EXTERNAL_ID_FIXED) and a source reference (activation checklist SOURCE_REFERENCE)."""
    e = _engine(w)
    if "k02.draft.external_id" not in w.ids:
        suffix = random_suffix()
        w.ids["k02.draft.external_id"] = f"SOP7-{suffix}"
        w.ids["k02.draft.document_ref"] = f"SO-SOP7-{suffix}"
    return {
        **k02_seat_month_body(e.customer_id),
        "external_id": w.ids["k02.draft.external_id"],
        "document_ref": w.ids["k02.draft.document_ref"],
    }


def s_contracts_create(w: World) -> HttpResponse:
    e = _engine(w)
    return _created(w, "k02.draft", post(e.app, f"{API}/contracts", e.place.author, _draft_body(w)))


def s_combination_suggestions_dismiss(w: World) -> HttpResponse:
    """POST /contracts of the same customer inside the detection window raised a suggestion naming
    the draft; activation's COMBINATION_SUGGESTIONS checklist item fails while one is open
    (activation.py combination_suggestions / evaluate), so every suggestion of the draft is
    dismissed here — before contracts_submit_activation."""
    e = _engine(w)
    listed = get(
        e.app, f"{API}/combination-suggestions", e.place.author, {"contract": w.ids["k02.draft"]}
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert items, "the same-customer draft raised no combination suggestion"
    response = listed
    for item in items:
        response = post(
            e.app,
            f"{API}/combination-suggestions/{item['id']}/dismiss",
            e.place.author,
            {"rationale": "Negotiated independently of SF-ORD-10002 (SOP-7 walk)."},
        )
        if response.status_code >= 400:
            return response
    return response


def s_contracts_replace_draft(w: World) -> HttpResponse:
    e = _engine(w)
    body = _draft_body(w)  # the same external id: a replace keeps the draft's identity
    return post(
        e.app,
        f"{API}/contracts/{w.ids['k02.draft']}/replace-draft",
        e.place.author,
        body,
        if_match=_etag_of(e.app, f"{API}/contracts/{w.ids['k02.draft']}", e.place.author),
    )


def _step1_recorded(w: World, contract_id: str) -> None:
    """Activation checklist STEP1_RECORD (activation.py step1_record): a REVIEWED COLLECTIBILITY
    judgement of the draft and a probable COLLECTIBILITY_ASSESSED event for the enabled book — the
    shape of tests/domain/contracts/test_activation.py::_reviewed_record / _step1."""
    e = _engine(w)
    created = post(
        e.app,
        f"{API}/judgements",
        e.place.author,
        {
            "topic": "COLLECTIBILITY",
            "subject_type": "contract",
            "subject_id": contract_id,
            "book": "ASC606",
            "conclusion": "Collection of the consideration is probable.",
            "rationale": "Credit review of the customer and its payment history (SOP-7 walk).",
            "questionnaire": {"criteria": step1_criteria()},  # R-113 (f)
        },
    )
    assert created.status_code == 201, created.text
    record_id = str(created.json()["id"])
    submitted = post(
        e.app, f"{API}/judgements/{record_id}/submit", e.place.author, {"comment": COMMENT}
    )
    assert submitted.status_code == 200, submitted.text
    approved = _approve(w, str(submitted.json()["approval_request_id"]), e.marcus)
    assert approved.status_code == 200, approved.text
    path = f"{API}/contracts/{contract_id}"
    event = {
        "event_type": "COLLECTIBILITY_ASSESSED",
        "effective_date": JANUARY,
        "payload": {"book": "ASC606", "is_probable": True, "judgement_record_id": record_id},
    }
    appended = post(
        e.app,
        f"{path}/events",
        e.place.author,
        {"events": [event], "comment": COMMENT},
        if_match=_etag_of(e.app, path, e.place.author),
    )
    assert appended.status_code == 201, appended.text


def s_contracts_submit_activation(w: World) -> HttpResponse:
    e = _engine(w)
    _step1_recorded(w, w.ids["k02.draft"])  # suggestions dismissed and document_ref set already
    return post(
        e.app,
        f"{API}/contracts/{w.ids['k02.draft']}/submit-activation",
        e.place.author,
        {"comment": COMMENT},
        if_match=_etag_of(e.app, f"{API}/contracts/{w.ids['k02.draft']}", e.place.author),
    )


def _delivery(quantity: str) -> dict[str, Any]:
    return {
        "event_type": "DELIVERY_RECORDED",
        "effective_date": "2026-09-12",
        "obligation_key": "O1",
        "payload": {"obligation_key": "O1", "quantity": quantity, "trigger": "DELIVERY"},
    }


def s_contract_events_append(w: World) -> HttpResponse:
    """A delivery recorded by a signed-in person: the request waits as an event submission
    (BUILD_SPEC CTR-6; 04 §16.3 "Manual events") and the command writes the submission's audit
    event. A delivery on trigger DELIVERY needs no evidence."""
    e = _engine(w)
    active = w.ids["k02.active"]
    return post(
        e.app,
        f"{API}/contracts/{active}/events",
        e.place.author,
        {"events": [_delivery("10")], "comment": COMMENT},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )


def s_contract_events_preview(w: World) -> HttpResponse:
    e = _engine(w)
    active = w.ids["k02.active"]
    return post(
        e.app,
        f"{API}/contracts/{active}/events/preview",
        e.place.author,
        {"events": [_delivery("5")]},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )


def s_contracts_update_memos(w: World) -> HttpResponse:
    e = _engine(w)
    active = w.ids["k02.active"]
    return post(
        e.app,
        f"{API}/contracts/{active}/update-memos",
        e.place.author,
        {"comment": COMMENT, "memo_1": "SOP-7 walk"},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )


def s_contracts_apply_hold(w: World) -> HttpResponse:
    e = _engine(w)
    active = w.ids["k02.active"]
    response = post(
        e.app,
        f"{API}/contracts/{active}/apply-hold",
        e.place.author,
        {"hold_type": "recognition", "reason": "Pending credit review (SOP-7 walk)."},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )
    if response.status_code < 400:
        # apply-hold answers ContractOut (no holds member): the hold id equals the id of the
        # HOLD_APPLIED event it appended (test_holds.py: hold["id"] == applied_event_id).
        listed = get(e.app, f"{API}/contracts/{active}/events", e.place.author, {"limit": 200})
        assert listed.status_code == 200, listed.text
        held = [i for i in listed.json()["items"] if i["event_type"] == "HOLD_APPLIED"]
        w.ids["k02.hold"] = str(held[-1]["id"])
    return response


def s_contracts_release_hold(w: World) -> HttpResponse:
    e = _engine(w)
    active = w.ids["k02.active"]
    return post(
        e.app,
        f"{API}/contracts/{active}/release-hold",
        e.place.author,
        {"hold_id": w.ids["k02.hold"], "comment": COMMENT},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )


def s_contracts_request_void(w: World) -> HttpResponse:
    e = _engine(w)
    draft = post(
        e.app,
        f"{API}/contracts",
        e.place.author,
        {**k02_seat_month_body(e.customer_id), "external_id": f"SOP7V-{random_suffix()}"},
    )
    assert draft.status_code == 201, draft.text
    return post(
        e.app,
        f"{API}/contracts/{draft.json()['id']}/request-void",
        e.place.author,
        {"reason_code": "CREATED_IN_ERROR", "comment": "Booked twice (SOP-7 walk)."},
        if_match=_etag(draft),
    )


def s_contracts_distinct_review(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/contracts/{w.ids['k02.active']}/obligations/O1/distinct-review",
        e.place.author,
        {"distinctness": "distinct", "rationale": "Separately identifiable (SOP-7 walk)."},
    )


def s_obligations_request_ssp_override(w: World) -> HttpResponse:
    e = _engine(w)
    (row,) = e.place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == UUID(w.ids["k02.active"]),
            obligation.c.obligation_key == "O1",
        )
    )
    return post(
        e.app,
        f"{API}/obligations/{row['id']}/request-ssp-override",
        e.place.author,
        {"ssp_book_version_id": e.version_id, "justification": "Negotiated list (SOP-7 walk)."},
    )


def s_contract_estimates_create(w: World) -> HttpResponse:
    e = _engine(w)
    body = {
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": "REBATE-1",
        "vc_element_type": "REBATE",
        "method": "MOST_LIKELY_AMOUNT",
    }
    return _created(
        w,
        "k02.estimate",
        post(e.app, f"{API}/contracts/{w.ids['k02.active']}/estimates", e.place.author, body),
    )


def s_estimate_versions_create(w: World) -> HttpResponse:
    e = _engine(w)
    body = {
        "effective_date": "2026-09-30",
        "scenarios": [{"outcome": "Expected rebate", "amount": "1000.00"}],
        "unconstrained_amount": "1000.00",
        "most_conservative_amount": "1000.00",
        "constrained_amount": "1000.00",
        "rationale": "Rebate expected at the current run rate (SOP-7 walk).",
    }
    return _created(
        w,
        "k02.estimate_version",
        post(e.app, f"{API}/estimates/{w.ids['k02.estimate']}/versions", e.place.author, body),
    )


def s_estimate_versions_update(w: World) -> HttpResponse:
    e = _engine(w)
    return patch(
        e.app,
        f"{API}/estimate-versions/{w.ids['k02.estimate_version']}",
        e.place.author,
        {"rationale": "Rebate expected at the current run rate (revised)."},
        if_match=w.ids["k02.estimate_version.etag"],
    )


def s_estimate_versions_preview(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/estimate-versions/{w.ids['k02.estimate_version']}/preview",
        e.place.author,
        {},
    )


def s_estimate_versions_submit(w: World) -> HttpResponse:
    """A version is submitted with its evidence and the reviewed ``CONSTRAINT`` record of its
    element (04 §16.14 rev 1.241). Both are given first, by maya and — the walk's K-02 world
    gives priya the SSP approvals only — by marcus, its Controller, who reviews the record; the
    command under the walk is the submission."""
    e = _engine(w)
    estimate_version_ready(
        e.app,
        e.place.author,
        w.ids["k02.estimate_version"],
        constraint_of="REBATE-1",
        reviewer=e.marcus,
    )
    return post(
        e.app,
        f"{API}/estimate-versions/{w.ids['k02.estimate_version']}/submit",
        e.place.author,
        {"comment": COMMENT},
    )


def s_estimate_versions_withdraw(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/estimate-versions/{w.ids['k02.estimate_version']}/withdraw",
        e.place.author,
        {"comment": COMMENT},
    )


def s_estimate_versions_discard(w: World) -> HttpResponse:
    """Item EST-DISCARD-1: a discard takes a DRAFT, and the walk's version is WITHDRAWN by now —
    so a second version of the element is drafted here and discarded."""
    e = _engine(w)
    body = {
        "effective_date": "2026-09-30",
        "scenarios": [{"outcome": "Expected rebate", "amount": "1200.00"}],
        "unconstrained_amount": "1200.00",
        "most_conservative_amount": "1200.00",
        "constrained_amount": "1200.00",
        "rationale": "A second draft, to be discarded (SOP-7 walk).",
    }
    drafted = post(e.app, f"{API}/estimates/{w.ids['k02.estimate']}/versions", e.place.author, body)
    assert drafted.status_code == 201, drafted.text
    return post(
        e.app, f"{API}/estimate-versions/{drafted.json()['id']}/discard", e.place.author, {}
    )


def s_judgements_create(w: World) -> HttpResponse:
    e = _engine(w)
    body = {
        "topic": "COLLECTIBILITY",
        "subject_type": "contract",
        "subject_id": w.ids["k02.active"],
        "book": "ASC606",
        "conclusion": "Collection of the consideration is probable.",
        "rationale": "Credit review of the customer and its payment history (SOP-7 walk).",
        "questionnaire": {"criteria": step1_criteria()},  # R-113 (f): whole at submission
    }
    return _created(w, "k02.judgement", post(e.app, f"{API}/judgements", e.place.author, body))


def s_judgements_update(w: World) -> HttpResponse:
    e = _engine(w)
    return patch(
        e.app,
        f"{API}/judgements/{w.ids['k02.judgement']}",
        e.place.author,
        {"rationale": "Credit review of the customer and its payment history (revised)."},
        if_match=w.ids["k02.judgement.etag"],
    )


def s_judgements_submit(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/judgements/{w.ids['k02.judgement']}/submit",
        e.place.author,
        {"comment": COMMENT},
    )


def s_judgements_discard(w: World) -> HttpResponse:
    """The discard of a judgement record (04 T-CON-19 rev 1.242): a discard takes a DRAFT, and
    the walk's record waits for its review by now — so a second record of the contract is
    drafted here and discarded."""
    e = _engine(w)
    body = {
        "topic": "OTHER",
        "subject_type": "contract",
        "subject_id": w.ids["k02.active"],
        "conclusion": "A record drafted by mistake.",
        "rationale": "A second draft, to be discarded (SOP-7 walk).",
    }
    drafted = post(e.app, f"{API}/judgements", e.place.author, body)
    assert drafted.status_code == 201, drafted.text
    return post(e.app, f"{API}/judgements/{drafted.json()['id']}/discard", e.place.author, {})


def s_contracts_regroup(w: World) -> HttpResponse:
    """D-98 140 regroup BEFORE posting: O2 moves from a fresh two-line draft to a fresh one-line
    draft of the same customer (tests/domain/contracts/test_regroup.py shapes; that module is
    recorded "not run" and only the pre-posting path is witnessed here)."""
    e = _engine(w)
    suffix = random_suffix()
    lines = [
        seat_line("O1", seats="1440", price="144000.00", start="2026-01-01", end="2027-12-31"),
        seat_line("O2", seats="960", price="96000.00", start="2026-01-01", end="2027-12-31"),
    ]
    source = post(
        e.app,
        f"{API}/contracts",
        e.place.author,
        seat_body(
            e.customer_id, external_id=f"SOP7-RG-A-{suffix}", inception="2026-01-01", lines=lines
        ),
    )
    assert source.status_code == 201, source.text
    target = post(
        e.app,
        f"{API}/contracts",
        e.place.author,
        seat_body(
            e.customer_id,
            external_id=f"SOP7-RG-B-{suffix}",
            inception="2026-01-01",
            lines=lines[:1],
        ),
    )
    assert target.status_code == 201, target.text
    body = {
        "obligation_keys": ["O2"],
        "target_contract_id": target.json()["id"],
        "comment": COMMENT,
    }
    return post(e.app, f"{API}/contracts/{source.json()['id']}/regroup", e.place.author, body)


def s_combination_groups_create(w: World) -> HttpResponse:
    e = _engine(w)
    body = {
        "contract_ids": [w.ids["k02.active"], w.ids["k02.draft"]],
        "criterion": "606-10-25-9(a)",
        "rationale": "Negotiated as a package (SOP-7 walk).",
    }
    return _created(w, "k02.group", post(e.app, f"{API}/combination-groups", e.place.author, body))


def s_combination_groups_submit(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/combination-groups/{w.ids['k02.group']}/submit",
        e.place.author,
        {"comment": COMMENT},
    )


def s_combination_groups_discard(w: World) -> HttpResponse:
    """The discard of a proposed combination (04 T-CON-19 rev 1.289): the group of the walk
    has gone on to its approval, so a second proposal of the same two contracts is made
    here and given up."""
    e = _engine(w)
    body = {
        "contract_ids": [w.ids["k02.active"], w.ids["k02.draft"]],
        "criterion": "606-10-25-9(a)",
        "rationale": "Proposed a second time by mistake (SOP-7 walk).",
    }
    proposed = post(e.app, f"{API}/combination-groups", e.place.author, body)
    assert proposed.status_code == 201, proposed.text
    group_id = proposed.json()["id"]
    return post(e.app, f"{API}/combination-groups/{group_id}/discard", e.place.author, {})


def s_events_request_void(w: World) -> HttpResponse:
    e = _engine(w)
    listed = get(
        e.app, f"{API}/contracts/{w.ids['k02.active']}/events", e.place.author, {"limit": 200}
    )
    assert listed.status_code == 200, listed.text
    # The walk's delivery waits for approval (CTR-6), so the stream holds none: the event the
    # walk voids is the memo ``contracts_update_memos`` appended.
    event = next(i for i in listed.json()["items"] if i["event_type"] == "MEMO_UPDATED")
    response = post(
        e.app,
        f"{API}/events/{event['id']}/request-void",
        e.place.author,
        {"reason_code": "CREATED_IN_ERROR", "comment": "Recorded against the wrong line."},
    )
    if response.status_code < 400:
        w.ids["k02.submission"] = str(response.json()["event_submission_id"])
    return response


def s_event_submissions_withdraw(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/event-submissions/{w.ids['k02.submission']}/withdraw",
        e.place.author,
        {"comment": COMMENT},
    )


def _co_term_body() -> dict[str, Any]:
    """ENGINE_SPEC S06-R-19 (03 REQ-MOD-012; 04 §16.14 rev 1.84; PRD ERR-55): "`CO_TERM`: `ADD` line
    starting on d and ending on the original end date" — the shape of this body; an `UPGRADE` is a
    `CHANGE` line on the subscription obligation, so the landed shape check rightly refused the
    former kind."""
    return {
        "effective_date": "2026-09-16",
        "kind": "CO_TERM",
        "reference": "SO-UPG-1",
        "lines": [
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "775",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            }
        ],
        "rationale": "Marrowby adds 50 seats for the remaining term (SOP-7 walk).",
    }


def s_contract_modifications_create(w: World) -> HttpResponse:
    e = _engine(w)
    return _created(
        w,
        "k02.modification",
        post(
            e.app,
            f"{API}/contracts/{w.ids['k02.active']}/modifications",
            e.place.author,
            _co_term_body(),
        ),
    )


def s_modifications_classify(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app, f"{API}/modifications/{w.ids['k02.modification']}/classify", e.place.author, {}
    )


def s_modifications_update(w: World) -> HttpResponse:
    e = _engine(w)
    path = f"{API}/modifications/{w.ids['k02.modification']}"
    return patch(
        e.app,
        path,
        e.place.author,
        {"rationale": "Marrowby adds 50 seats for the remaining term (revised)."},
        if_match=_etag_of(e.app, path, e.place.author),
    )


def s_modifications_preview(w: World) -> HttpResponse:
    e = _engine(w)
    path = f"{API}/modifications/{w.ids['k02.modification']}"
    queued = post(e.app, f"{path}/preview", e.place.author, {})
    if queued.status_code < 400:
        # Codex 0223 MODIFICATION-1: the POST only defers the job; the worker run (the K-02
        # modification tests' seam, in the engine tenant) stores the preview that submit needs.
        job_id = UUID(str(queued.json()["id"]))
        _run_job_in(w, e.place.tenant_id, job_id)
        finished = get(e.app, f"{API}/jobs/{job_id}", e.place.author).json()
        assert finished["state"] == "SUCCEEDED", finished
        # API-S-Modification: the stored preview is the row's `impact_preview_sha256` (T-CON-06);
        # `impact_preview` is its API-S-ImpactSummary and carries no hash of its own.
        shown = get(e.app, path, e.place.author).json()
        assert shown.get("impact_preview") and shown.get("impact_preview_sha256"), (
            "no persisted impact preview on the row"
        )
    return queued


def s_modifications_submit(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/modifications/{w.ids['k02.modification']}/submit",
        e.place.author,
        {"comment": COMMENT},
    )


def s_modifications_withdraw(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/modifications/{w.ids['k02.modification']}/withdraw",
        e.place.author,
        {"comment": "Superseded by a new order (SOP-7 walk)."},
    )


def s_modifications_discard(w: World) -> HttpResponse:
    """Item MOD-DISCARD-1: the withdrawn draft is discarded (any DRAFT without a pending
    request; PRD SM-03)."""
    e = _engine(w)
    return post(
        e.app, f"{API}/modifications/{w.ids['k02.modification']}/discard", e.place.author, {}
    )


def _adjustment_path(w: World) -> str:
    return f"{API}/manual-adjustments/{w.ids['k02.adjustment']}"


def s_manual_adjustments_create(w: World) -> HttpResponse:
    """API-R-37 (CLO-12): a manual release of USD 100.00 on O1 of the K-02 contract, dated in the
    open September period; the chain below submits it, asks to defer it past lock, withdraws that
    request and discards the draft, so nothing posts."""
    e = _engine(w)
    (row,) = e.place.rows(
        select(obligation.c.id).where(
            obligation.c.contract_id == UUID(w.ids["k02.active"]),
            obligation.c.obligation_key == "O1",
        )
    )
    body = {
        "kind": "MANUAL_RELEASE",
        "contract_id": w.ids["k02.active"],
        "effective_date": "2026-09-12",
        "reason_code": "DATA_CORRECTION",
        "memo": "Seats delivered ahead of plan (SOP-7 walk).",
        "payload": {
            "obligation_id": str(row["id"]),
            "amount": {"amount": "100.00", "currency": "USD"},
        },
    }
    created = post(e.app, f"{API}/manual-adjustments", e.place.author, body)
    return _created(w, "k02.adjustment", created)


def s_manual_adjustments_update(w: World) -> HttpResponse:
    e = _engine(w)
    path = _adjustment_path(w)
    return patch(
        e.app,
        path,
        e.place.author,
        {"memo": "Seats delivered ahead of plan (revised)."},
        if_match=_etag_of(e.app, path, e.place.author),
    )


def s_manual_adjustments_preview(w: World) -> HttpResponse:
    e = _engine(w)
    return post(e.app, f"{_adjustment_path(w)}/preview", e.place.author, {})


def s_manual_adjustments_submit(w: World) -> HttpResponse:
    e = _engine(w)
    return post(e.app, f"{_adjustment_path(w)}/submit", e.place.author, {"comment": COMMENT})


def s_manual_adjustments_request_defer_past_lock(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{_adjustment_path(w)}/request-defer-past-lock",
        e.place.author,
        {"comment": "Customer acceptance arrives after the close (SOP-7 walk)."},
    )


def s_manual_adjustments_withdraw(w: World) -> HttpResponse:
    e = _engine(w)
    return post(e.app, f"{_adjustment_path(w)}/withdraw", e.place.author, {"comment": COMMENT})


def s_manual_adjustments_discard(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{_adjustment_path(w)}/discard",
        e.place.author,
        {"reason": "Entered against the wrong obligation (SOP-7 walk)."},
    )


OVERRIDE_KEY: Final = "step1.term_with_termination_rights"  # a CONTRACT-level (OVR) parameter
OVERRIDE_RATIONALE: Final = (
    "The stated term governs; termination rights not substantive (SOP-7 walk)."
)


def s_policy_overrides_create(w: World) -> HttpResponse:
    """SOP-7 class (e): release 1.0 refuses the creation by name (04 T-CON-23 rev 1.322). Maya
    holds ``contract.create`` and reads the K-02 contract, so the answer is the command's own
    refusal and not a 403 or a 404; ``_exercise`` holds it to the rule id and to storing nothing."""
    e = _engine(w)
    body = {
        "contract_id": w.ids["k02.active"],
        "policy_key": OVERRIDE_KEY,
        "value": "STATED_TERM",
        "rationale": OVERRIDE_RATIONALE,
    }
    return post(e.app, f"{API}/policy-overrides", e.place.author, body)


def s_policy_overrides_submit(w: World) -> HttpResponse:
    """The kept command on a row the product no longer creates: the walk's world writes the DRAFT
    override as Maya (``support.factories.drafted_override``) and the product submits it."""
    e = _engine(w)
    w.ids["k02.override"] = str(
        drafted_override(
            e.place,
            UUID(w.ids["k02.active"]),
            OVERRIDE_KEY,
            "STATED_TERM",
            rationale=OVERRIDE_RATIONALE,
        )
    )
    return post(
        e.app,
        f"{API}/policy-overrides/{w.ids['k02.override']}/submit",
        e.place.author,
        {"comment": COMMENT},
    )


def _journal_run(w: World, period_key: str) -> tuple[HttpResponse, str | None]:
    """POST /journal-runs (202 API-S-Job) and the JOURNAL_RUN_CALCULATE job run: the run row exists
    only after the job; the run id is the response header, the body's id is the JOB id."""
    e = _engine(w)
    body = {"entity_code": "AVM-US", "period_key": period_key, "book": "ASC606"}
    response = post(e.app, f"{API}/journal-runs", e.place.author, body)
    if response.status_code >= 400:
        return response, None
    run_id = str(response.headers[RUN_ID_HEADER])
    _run_job_in(w, e.place.tenant_id, UUID(str(response.json()["id"])))
    shown = get(e.app, f"{API}/journal-runs/{run_id}", e.place.author).json()
    assert shown["state"] == "draft", shown
    return response, run_id


def s_journal_runs_create(w: World) -> HttpResponse:
    response, run_id = _journal_run(w, "FY2026-P09")
    if run_id is not None:
        w.ids["k02.run"] = run_id
    return response


def s_journal_runs_submit(w: World) -> HttpResponse:
    e = _engine(w)
    response = post(
        e.app, f"{API}/journal-runs/{w.ids['k02.run']}/submit", e.place.author, {"comment": COMMENT}
    )
    if response.status_code < 400:
        w.ids["k02.run.approval"] = str(response.json()["approval_request_id"])
    return response


def s_journal_runs_export(w: World) -> HttpResponse:
    """Export needs an approved run: Marcus (journal.approve; MFA at enrolment; neither the
    submitter nor the calculation's author) approves first. The 202 defers a JOURNAL_EXPORT job
    that is NOT run here (no GL adapter is registered in the walk)."""
    e = _engine(w)
    approved = _approve(w, w.ids["k02.run.approval"], e.marcus)
    assert approved.status_code == 200, approved.text
    return post(e.app, f"{API}/journal-runs/{w.ids['k02.run']}/export", e.place.author, {})


class _RefusingGl(CsvGl):
    """The walk's ledger refuses every chunk (05 ADP-12 ``Permanent``)."""

    def post_chunk(self, chunk: journal_ports.JournalChunk) -> journal_ports.PostingResult:
        raise journal_ports.Permanent("The ledger period FY2026-P09 is closed.")


@contextmanager
def _gl_adapter(
    factory: journal_ports.GLAdapterFactory, code: GlAdapter = GlAdapter.CSV
) -> Iterator[None]:
    """The GL adapter the worker's composition root would register for the E-37 literal ``code``
    (the CSV literal unless a scenario says otherwise), for the jobs one scenario runs
    (DG-LAY-03)."""
    adapters = journal_ports.GL_ADAPTERS
    previous = adapters.get(code)
    adapters[code] = factory
    try:
        yield
    finally:
        if previous is None:
            del adapters[code]
        else:
            adapters[code] = previous


def _walk_batch(w: World) -> dict[str, Any]:
    """The one batch of the walk's FY2026-P09 run (USD)."""
    e = _engine(w)
    shown = get(e.app, f"{API}/journal-runs/{w.ids['k02.run']}", e.place.author)
    assert shown.status_code == 200, shown.text
    [batch] = shown.json()["batches"]
    return dict(batch)


def s_journal_batches_retry(w: World) -> HttpResponse:
    """Retry needs a ``failed`` batch: the export of the approved P09 run is requested again (no
    second message) and its job runs against a ledger that refuses the chunk, so the batch and
    the run are ``failed``. The 202 defers a JOURNAL_EXPORT job that the next scenario runs."""
    e = _engine(w)
    requested = post(e.app, f"{API}/journal-runs/{w.ids['k02.run']}/export", e.place.author, {})
    assert requested.status_code == 202, requested.text
    with _gl_adapter(_RefusingGl):
        _run_job_in(w, e.place.tenant_id, UUID(str(requested.json()["id"])))
    batch = _walk_batch(w)
    assert batch["state"] == "failed", batch
    response = post(e.app, f"{API}/journal-batches/{batch['id']}/retry", e.place.author, {})
    if response.status_code < 400:
        w.ids["k02.batch.retry_job"] = str(response.json()["id"])
    return response


def s_journal_batches_acknowledge(w: World) -> HttpResponse:
    """Acknowledge needs an ``exported`` batch: the retry's job runs with the CSV adapter, which
    writes the file and waits for the person who imports it (05 ADP-33)."""
    e = _engine(w)
    with _gl_adapter(CsvGl):
        _run_job_in(w, e.place.tenant_id, UUID(w.ids["k02.batch.retry_job"]))
    batch = _walk_batch(w)
    assert batch["state"] == "exported", batch
    body = {"gl_document_id": "NS-JE-10045", "gl_posted_date": "2026-09-30"}
    return post(e.app, f"{API}/journal-batches/{batch['id']}/acknowledge", e.place.author, body)


def s_journal_batches_hand_over(w: World) -> HttpResponse:
    """Hand-over needs a ``failed`` batch of an ERP adapter (04 §16.7 rev 1.159; item
    JRN-FAILED-CANCEL-1): an Integration Admin connects the engine world's entity to NetSuite, the
    activity recorded since the acknowledged P09 run is calculated as a second run — its batches
    name ``NETSUITE`` — approved by Marcus and exported to a ledger that refuses every chunk. The
    connection is disabled again before the command, so nothing else of the walk is calculated
    for it. The 202 defers a JOURNAL_EXPORT job (mode ``HAND_OVER``) that is NOT run here."""
    e = _engine(w)
    someone = colleague(e.place.tenant_id, "nikhil")
    assign(someone, "integration_admin")
    admin = enrolled(e.app, w.clock, someone)
    created = post(
        e.app,
        f"{API}/integrations",
        admin,
        {
            "code": "netsuite-sop7",
            "name": "NetSuite (mock)",
            "adapter": "NETSUITE",
            "direction": "BOTH",
            "base_url": f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}",
        },
    )
    assert created.status_code == 201, created.text
    path = f"{API}/integrations/{created.json()['id']}"
    enabled = patch(e.app, path, admin, {"status": "ACTIVE"}, if_match=_etag_of(e.app, path, admin))
    assert enabled.status_code == 200, enabled.text
    calculated, run_id = _journal_run(w, "FY2026-P09")
    assert run_id is not None, calculated.text
    run = f"{API}/journal-runs/{run_id}"
    submitted = post(e.app, f"{run}/submit", e.place.author, {"comment": COMMENT})
    assert submitted.status_code == 200, submitted.text
    approved = _approve(w, str(submitted.json()["approval_request_id"]), e.marcus)
    assert approved.status_code == 200, approved.text
    requested = post(e.app, f"{run}/export", e.place.author, {})
    assert requested.status_code == 202, requested.text
    with _gl_adapter(_RefusingGl, GlAdapter.NETSUITE):
        _run_job_in(w, e.place.tenant_id, UUID(str(requested.json()["id"])))
    shown = get(e.app, run, e.place.author)
    assert shown.status_code == 200, shown.text
    batches = shown.json()["batches"]
    assert batches and {(item["adapter"], item["state"]) for item in batches} == {
        ("NETSUITE", "failed")
    }, batches
    disabled = patch(
        e.app, path, admin, {"status": "DISABLED"}, if_match=_etag_of(e.app, path, admin)
    )
    assert disabled.status_code == 200, disabled.text
    return post(e.app, f"{API}/journal-batches/{batches[0]['id']}/hand-over", e.place.author, {})


def s_journal_runs_cancel(w: World) -> HttpResponse:
    # A second run (FY2026-P08) — the P09 run is exported; only a draft or approved run cancels.
    response, run_id = _journal_run(w, "FY2026-P08")
    assert run_id is not None, response.text
    e = _engine(w)
    return post(e.app, f"{API}/journal-runs/{run_id}/cancel", e.place.author, {"reason": REASON})


def _billing_line() -> dict[str, Any]:
    """A ``BILLING_RECORDED`` through the events API: a billed line with no source document, the
    difference the walk's reconciliation itemises (UNMATCHED_SUBLEDGER)."""
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": "2026-09-12",
        "obligation_key": "O1",
        "payload": {
            "invoice_number": "INV-SOP7-1",
            "line_external_id": "INV-SOP7-1-1",
            "obligation_key": "O1",
            "amount": {"amount": "1000.00", "currency": "USD"},
            "issue_date": "2026-09-12",
        },
    }


def s_reconciliations_create(w: World) -> HttpResponse:
    """POST /reconciliations (202 API-S-Job) and the RECONCILIATION_GENERATE job run: the
    reconciliation exists only after the job; its id is the response header, the body's id is the
    JOB id (as journal runs)."""
    e = _engine(w)
    active = w.ids["k02.active"]
    billed = post(
        e.app,
        f"{API}/contracts/{active}/events",
        e.place.author,
        {"events": [_billing_line()], "comment": COMMENT},
        if_match=_etag_of(e.app, f"{API}/contracts/{active}", e.place.author),
    )
    assert billed.status_code == 201, billed.text
    body = {"kind": "BILLING_TO_SUBLEDGER", "entity_code": "AVM-US", "period_key": "FY2026-P09"}
    response = post(e.app, f"{API}/reconciliations", e.place.author, body)
    if response.status_code < 400:
        w.ids["k02.recon"] = str(response.headers[RECONCILIATION_ID_HEADER])
        _run_job_in(w, e.place.tenant_id, UUID(str(response.json()["id"])))
    return response


def s_reconciliations_attach_trial_balance(w: World) -> HttpResponse:
    """A subledger-to-GL reconciliation of the same period, generated first, takes an uploaded
    trial balance: 202 API-S-Job; the attach job is run as the worker runs it."""
    e = _engine(w)
    body = {"kind": "SUBLEDGER_TO_GL", "entity_code": "AVM-US", "period_key": "FY2026-P09"}
    generated = post(e.app, f"{API}/reconciliations", e.place.author, body)
    assert generated.status_code == 202, generated.text
    _run_job_in(w, e.place.tenant_id, UUID(str(generated.json()["id"])))
    uploaded = call(
        e.app,
        "POST",
        f"{API}/files",
        data={"purpose": "IMPORT_SOURCE"},
        files={
            "file": ("trial-balance.csv", b"account,currency,amount\n2100,USD,0.00\n", "text/csv")
        },
        headers=cookie_headers(e.place.author.token, e.place.author.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    reconciliation_id = generated.headers[RECONCILIATION_ID_HEADER]
    response = post(
        e.app,
        f"{API}/reconciliations/{reconciliation_id}/attach-trial-balance",
        e.place.author,
        {"file_id": uploaded.json()["id"]},
    )
    if response.status_code < 400:
        _run_job_in(w, e.place.tenant_id, UUID(str(response.json()["id"])))
    return response


def s_reconciliations_items_update(w: World) -> HttpResponse:
    e = _engine(w)
    path = f"{API}/reconciliations/{w.ids['k02.recon']}/items"
    listed = get(e.app, path, e.place.author, {"limit": 50})
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    return patch(
        e.app,
        f"{path}/{item['id']}",
        e.place.author,
        {"explanation": "Billed through the events API; the source document follows."},
        if_match=f'"r{item["row_version"]}"',
    )


def s_reconciliations_prepare(w: World) -> HttpResponse:
    """The preparer's sign-off needs an MFA-verified session (T-CLS-08 ``mfa_verified_at``): a
    second Revenue Accountant, enrolled, prepares (``place.author`` is not enrolled)."""
    e = _engine(w)
    someone = colleague(e.place.tenant_id, "rina")
    assign(someone, "revenue_accountant")
    preparer = enrolled(e.app, w.clock, someone)
    return post(e.app, f"{API}/reconciliations/{w.ids['k02.recon']}/prepare", preparer, {})


def s_reconciliations_sign(w: World) -> HttpResponse:
    # Marcus (recon.signoff; MFA at enrolment, inside the step-up window) did not prepare it.
    e = _engine(w)
    return post(
        e.app,
        f"{API}/reconciliations/{w.ids['k02.recon']}/sign",
        e.marcus,
        {"role": "REVIEWER", "statement_accepted": True},
    )


def s_reconciliations_reopen(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app, f"{API}/reconciliations/{w.ids['k02.recon']}/reopen", e.marcus, {"reason": REASON}
    )


def s_close_runs_create(w: World) -> HttpResponse:
    """POST /close-runs (202 API-S-Job): the run's id is the response header. The job stays
    queued; the run is cancelled by the scenario after the next."""
    e = _engine(w)
    body = {"entity_code": "AVM-US", "period_key": CLOSE_RUN_PERIOD}
    response = post(e.app, f"{API}/close-runs", e.place.author, body)
    if response.status_code < 400:
        w.ids["k02.close_run"] = str(response.headers[CLOSE_RUN_ID_HEADER])
        w.ids["k02.close_run.job"] = str(response.json()["id"])
    return response


def s_close_runs_resume(w: World) -> HttpResponse:
    """The run's job is dead-lettered (a worker took it and died; 05 JOB-06), which fails the
    run through the handler's failure hook; the FAILED run is resumed (202 API-S-Job)."""
    e = _engine(w)
    close_runs.dead_lettered(e.place.tenant_id, w.runtime, UUID(w.ids["k02.close_run.job"]))
    return post(e.app, f"{API}/close-runs/{w.ids['k02.close_run']}/resume", e.place.author, {})


def s_close_runs_cancel(w: World) -> HttpResponse:
    # The resumed run's job has not started: the run is cancelled at once.
    e = _engine(w)
    path = f"{API}/close-runs/{w.ids['k02.close_run']}/cancel"
    return post(e.app, path, e.place.author, {"reason": REASON})


def s_explain_verify(w: World) -> HttpResponse:
    """A query: recompute the K-02 contract version's transaction price from its stored trace."""
    e = _engine(w)
    versions = get(
        e.app, f"{API}/contracts/{w.ids['k02.active']}/versions", e.place.author, {"book": "ASC606"}
    )
    assert versions.status_code == 200, versions.text
    version_id = versions.json()["items"][0]["id"]
    path = f"{API}/explain/contract_version/{version_id}/transaction_price/verify?book=ASC606"
    return post(e.app, path, e.place.author, {})


# R-50 (d): two more standalone seat-month sales for the calculator study of the walk.
STUDY_EXTERNAL_IDS: Final = ("SF-ORD-10002-S1", "SF-ORD-10002-S2")


def s_ssp_calculator_runs_create(w: World) -> HttpResponse:
    """The study reads the ``committed_obligations`` of the engine world: each obligation of an
    ACTIVE single-obligation seat-month contract is one observation (BS3-D-21). Two such
    contracts are booked and activated here, after every other engine scenario has run, so the
    exclusion scenario can exclude one of them and the run keeps another of the same product and
    key (04 T-REF-34 "Keep at least one observation of <product>"; supervisor ruling R-50 (d))."""
    e = _engine(w)
    for external_id in STUDY_EXTERNAL_IDS:
        body = {**k02_seat_month_body(e.customer_id), "external_id": external_id}
        activated_contract(e.place, booked_contract(e.place, body, activate=False))
    products = get(e.app, f"{API}/products", e.place.author, {"limit": 50})
    assert products.status_code == 200, products.text
    product_ids = [i["id"] for i in products.json()["items"] if i["code"] == "AVM-SEAT-MO"]
    body = {
        "name": "Seat-month SSP study (SOP-7 walk)",
        "parameters": {
            "source": "committed_obligations",
            "product_ids": product_ids,
            "date_from": JANUARY,
            "date_to": "2026-09-30",
            "currency": "USD",
            "ssp_book_id": e.book_id,
        },
    }
    response = post(e.app, f"{API}/ssp-calculator-runs", e.place.author, body)
    if response.status_code < 400:
        # 202 API-S-Job: the body id is the JOB id; the run id is the header (as journal runs).
        w.ids["k02.calc"] = str(response.headers[CALC_RUN_ID_HEADER])
        _run_job_in(w, e.place.tenant_id, UUID(str(response.json()["id"])))
    return response


def s_ssp_calculator_exclusions_create(w: World) -> HttpResponse:
    """Excludes an observation the run holds, named as the run names it (``<contract external id>
    <obligation key>``): the first study contract's. The second stays, so the exclusion is
    accepted and the run keeps a result (R-50 (d); until then the scenario named a reference no
    run held and was refused 422 "Choose an observation of this run.")."""
    e = _engine(w)
    run = f"{API}/ssp-calculator-runs/{w.ids['k02.calc']}"
    listed = get(e.app, f"{run}/observations", e.place.author, {"limit": 50})
    assert listed.status_code == 200, listed.text
    references = [item["source_reference"] for item in listed.json()["items"]]
    chosen, kept = (f"{external_id} O1" for external_id in STUDY_EXTERNAL_IDS)
    assert chosen in references and kept in references, references
    return post(
        e.app,
        f"{run}/exclusions",
        e.place.author,
        {"source_reference": chosen, "reason": "One-off promotional order (SOP-7 walk)."},
    )


def s_ssp_calculator_runs_create_draft_version(w: World) -> HttpResponse:
    e = _engine(w)
    return post(
        e.app,
        f"{API}/ssp-calculator-runs/{w.ids['k02.calc']}/create-draft-version",
        e.place.author,
        {"version_label": "2026-H2 (SOP-7 walk)"},  # required; NO_RESULTS on a thin run is named
    )


def _no_data_import(w: World) -> str:
    """The only public path to an open exception item: a header-only SKU-SSP workbook (the fixture's
    sheet title and headers, zero rows) imported and validated is INVALID with one BLOCKING
    IMPORT_NO_DATA_ROWS item (tests/domain/imports/test_exception_queue.py::test_sort_and_filters
    precedent; validate.py raises it through raise_exception_item)."""
    headers, _ = workbook_rows(SKU_SSP_FIXTURE)
    uploaded = call(
        w.app,
        "POST",
        f"{API}/files",
        data={"purpose": "IMPORT_SOURCE"},
        files={
            "file": (
                "SKU SSP headers only.xlsx",
                workbook_bytes("SKU Setup", headers, []),
                "application/octet-stream",
            )
        },
        headers=cookie_headers(w.maya.token, w.maya.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    body = {"file_id": uploaded.json()["id"], "template_code": "legacy_sku_ssp"}
    created = post(w.app, f"{API}/imports", w.maya, body)
    assert created.status_code == 202, created.text
    import_id = str(created.headers[IMPORT_ID_HEADER])
    _run_job(w, UUID(str(created.json()["id"])))
    shown = get(w.app, f"{API}/imports/{import_id}", w.maya).json()
    assert shown["status"] == "INVALID", shown
    listed = get(w.app, f"{API}/exceptions", w.maya, {"import_upload_id": import_id})
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert item["code"] == "IMPORT_NO_DATA_ROWS", item
    return str(item["id"])


def s_exceptions_assign(w: World) -> HttpResponse:
    w.ids["exception"] = _no_data_import(w)
    body = {"owner_membership_id": str(w.grace.member.membership_id)}  # an ACTIVE membership
    return post(w.app, f"{API}/exceptions/{w.ids['exception']}/assign", w.maya, body)


def s_exceptions_request_waiver(w: World) -> HttpResponse:
    # The route submits the waiver's approval request (approval_request.submit);
    # exception_item.waive is written only when the waiver is approved.
    path = f"{API}/exceptions/{w.ids['exception']}/request-waiver"
    return post(w.app, path, w.maya, {"comment": COMMENT})


def s_exceptions_dismiss(w: World) -> HttpResponse:
    # An import item whose input is uncommitted (INVALID upload) may be dismissed.
    return post(
        w.app, f"{API}/exceptions/{w.ids['exception']}/dismiss", w.maya, {"comment": COMMENT}
    )


def _seats(w: World) -> SeatWorld:
    """The seat world (its own tenant) with one untemplated product: booking it raises the only
    reprocessable exception shape reachable through the public API (PRODUCT_UNMAPPED, ENGINE)."""
    if w.seats is None:
        w.seats = seat_world(
            w.app,
            w.keyring,
            w.clock,
            w.runtime.files,  # type: ignore[arg-type]
            untemplated=(UNMAPPED_SEAT, UNMAPPED_SEAT_2),
        )
    w.evidence_tenant_id = w.seats.place.tenant_id
    return w.seats


def s_exceptions_reprocess(w: World) -> HttpResponse:
    s = _seats(w)
    maya = s.place.author
    line = seat_line(
        "O1",
        seats="10",
        price="24000.00",
        start="2026-09-01",
        end="2027-08-31",
        product_code=UNMAPPED_SEAT,
    )
    booking = seat_body(
        s.customers["C-09"],
        external_id=f"SOP7-NOMAP-{random_suffix()}",
        inception="2026-09-01",
        lines=[line],
    )
    created = post(s.app, f"{API}/contracts", maya, booking)
    assert created.status_code == 201, created.text
    listed = get(
        s.app,
        f"{API}/exceptions",
        maya,
        {"contract": created.json()["id"], "code": "PRODUCT_UNMAPPED"},
    )
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    # The input must change first: reprocessing an unchanged input is a replay and never resolves
    # (test_exception_queue.py::test_reprocess_remediable_item). Map the product to the template.
    products = get(s.app, f"{API}/products", maya, {"limit": 200}).json()["items"]
    product_id = next(p["id"] for p in products if p["code"] == UNMAPPED_SEAT)
    templates = get(s.app, f"{API}/pob-templates", maya, {"limit": 200}).json()["items"]
    template_id = next(t["id"] for t in templates if t["code"] == "TPL-SUB-DAILY")
    set_default_template(s.app, maya, str(product_id), str(template_id))
    response = post(s.app, f"{API}/exceptions/{item['id']}/reprocess", maya, {})
    if response.status_code < 400:
        # 202: the CONTRACT_COMPUTE job settles the item (RESOLVED when the run succeeds).
        _run_job_in(w, s.place.tenant_id, UUID(str(response.json()["id"])))
        shown = get(s.app, f"{API}/exceptions/{item['id']}", maya).json()
        assert shown["status"] == "RESOLVED", shown
    return response


def s_exceptions_resolve(w: World) -> HttpResponse:
    """RESOLVE needs ``_cleared`` (imports/exceptions.py): a SUCCEEDED head computation of the
    item's group created AFTER the item's ``last_seen_at``. Public path: book the seat world's
    SECOND untemplated product (its own group — ENGINE items dedupe per code and group) →
    PRODUCT_UNMAPPED; map the product publicly; step the walk's FrozenClock by ONE second — the
    test controlling its own time input, not a DB seam (supervisor ruling of 2026-09-22) — so the
    recompute is strictly later than the item; replace-draft recomputes the provisional version (a
    public command) and its SUCCEEDED head clears the item; then resolve. Every audited timestamp
    comes from the advanced clock; nothing is hand-set. DB-time residual (NOT RUN): whether the
    refused first compute leaves a DRAFT that replace-draft accepts."""
    s = _seats(w)
    maya = s.place.author
    line = seat_line(
        "O1",
        seats="10",
        price="24000.00",
        start="2026-09-01",
        end="2027-08-31",
        product_code=UNMAPPED_SEAT_2,
    )
    booking = seat_body(
        s.customers["C-09"],
        external_id=f"SOP7-RESOLVE-{random_suffix()}",
        inception="2026-09-01",
        lines=[line],
    )
    created = post(s.app, f"{API}/contracts", maya, booking)
    assert created.status_code == 201, created.text
    contract_id = str(created.json()["id"])
    listed = get(
        s.app,
        f"{API}/exceptions",
        maya,
        {"contract": contract_id, "code": "PRODUCT_UNMAPPED"},
    )
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    products = get(s.app, f"{API}/products", maya, {"limit": 200}).json()["items"]
    product_id = next(p["id"] for p in products if p["code"] == UNMAPPED_SEAT_2)
    templates = get(s.app, f"{API}/pob-templates", maya, {"limit": 200}).json()["items"]
    template_id = next(t["id"] for t in templates if t["code"] == "TPL-SUB-DAILY")
    set_default_template(s.app, maya, str(product_id), str(template_id))
    before = w.clock.now()
    w.clock.advance(CLOCK_STEP)
    assert w.clock.now() - before == CLOCK_STEP
    # No control window is skipped: Tomas's step-up (world build) stays inside BS1-D-19's window.
    stepped_up_at = datetime.fromisoformat(w.ids["tomas.stepped_up_at"])
    assert w.clock.now() - stepped_up_at < STEP_UP_WINDOW, (w.clock.now(), stepped_up_at)
    path = f"{API}/contracts/{contract_id}"
    replaced = post(
        s.app, f"{path}/replace-draft", maya, booking, if_match=_etag_of(s.app, path, maya)
    )
    assert replaced.status_code < 400, replaced.text
    shown = get(s.app, f"{API}/exceptions/{item['id']}", maya).json()
    assert "RESOLVE" in shown["available_actions"], shown
    return post(
        s.app,
        f"{API}/exceptions/{item['id']}/resolve",
        maya,
        {"resolution": "Product mapped; the recompute succeeded (SOP-7 walk)."},
    )


def s_migrations_create(w: World) -> HttpResponse:
    uploaded = call(
        w.app,
        "POST",
        f"{API}/files",
        data={"purpose": "LEGACY_DATABASE"},
        # The 100-byte SQLITE header fixture is "not a database" to legacy_db.recognise (422
        # legacy-database-unrecognized): the shipped legacy database is the recognised source.
        files={"file": (LEGACY_DB.name, LEGACY_DB.read_bytes(), "application/octet-stream")},
        headers=cookie_headers(w.maya.token, w.maya.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    body = {"mode": "OPENING_BALANCES", "source_file_id": uploaded.json()["id"]}
    return _created(w, "migration", post(w.app, f"{API}/migrations", w.maya, body))


def s_migrations_profile(w: World) -> HttpResponse:
    response = post(w.app, f"{API}/migrations/{w.ids['migration']}/profile", w.maya, {})
    if response.status_code < 400:
        # 202: the PROFILE phase job reads the legacy database → PROFILED (import needs it).
        _run_job(w, UUID(str(response.json()["id"])))
        shown = get(w.app, f"{API}/migrations/{w.ids['migration']}", w.maya).json()
        assert shown["status"] == "PROFILED", shown
    return response


def s_migrations_import(w: World) -> HttpResponse:
    """202 with migration_batch.import written at acceptance; the IMPORT phase job is NOT run: its
    success over the shipped fixture needs 2023 periods and the legacy parity templates, which no
    committed HTTP test provisions (tests/pg/test_migration_capture_pg.py is the only IMPORTED
    path). ``s_migrations_reconcile`` therefore starts from its own IMPORTED batch."""
    body = {
        "mode": "OPENING_BALANCES",
        "cutover_date": "2023-01-31",  # the fixture's latest current period
        "entity_mapping": [
            {"legacy_name": name, "entity_code": name, "calendar_id": w.ids["calendar"]}
            for name in ("Mock Entity 1", "Mock Entity 2")
        ],
        "entity_defaults": {"time_zone": "UTC"},
        "batch_parameters": {},
    }
    return post(w.app, f"{API}/migrations/{w.ids['migration']}/import", w.maya, body)


def s_migrations_cancel(w: World) -> HttpResponse:
    return post(w.app, f"{API}/migrations/{w.ids['migration']}/cancel", w.maya, {})


def s_migrations_reconcile(w: World) -> HttpResponse:
    """SOP7-SEAM-MIG-1 (supervisor ruling R-50 (d); for review at this commit). The audited
    subject is the reconcile COMMAND — ``POST /migrations/{id}/reconcile``, 202, IMPORTED only. Its
    precondition is the state the IMPORT phase job leaves, and that job's success over the shipped
    legacy database needs the 2023 periods and the legacy parity templates of another world (see
    ``s_migrations_import``). The batch is therefore written IMPORTED as rows, the seam
    ``tests/pg/test_migration_reconcile_job_pg.py`` uses (``migration_batch_values`` over a
    LEGACY_DATABASE file row); nothing of the command is seeded. The MIGRATION_RECONCILE job the
    command defers is not run: the evidence covers the command, not the reconciliation."""
    with tenant_session(_db(w.tenant_id)) as session:
        source = file_object_values(w.tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**source))
        batch = migration_batch_values(
            w.tenant_id, source_file_id=source["id"], status=MigrationStatus.IMPORTED.value
        )
        session.execute(insert(migration_batch).values(**batch))
    return post(w.app, f"{API}/migrations/{batch['id']}/reconcile", w.maya, {})


def s_policies_create(w: World) -> HttpResponse:
    body = {
        "category": "ACCOUNTING_POLICY",
        "scope": "TENANT",
        "values": {"billing.posting": "ERP"},
    }
    return _created(w, "policy", post(w.app, f"{API}/policies", w.maya, body))


def s_policies_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/policies/{w.ids['policy']}",
        w.maya,
        # pin "P": the first day of a FUTURE open period in the entity's zone (America/New_York)
        {"effective_from": "2026-10-01T04:00:00Z"},
        if_match=w.ids["policy.etag"],
    )


def s_policies_test(w: World) -> HttpResponse:
    response = post(w.app, f"{API}/policies/{w.ids['policy']}/test", w.maya, {})
    if response.status_code < 400:
        # 202: the POLICY_SIMULATION job is only deferred; submit needs the version TESTED.
        job_id = UUID(str(response.json()["id"]))
        _run_job(w, job_id)
        finished = get(w.app, f"{API}/jobs/{job_id}", w.maya).json()
        assert finished["state"] == "SUCCEEDED", finished
        shown = get(w.app, f"{API}/policies/{w.ids['policy']}", w.maya).json()
        assert shown["status"] == "TESTED", shown
    return response


def s_policies_submit(w: World) -> HttpResponse:
    return post(w.app, f"{API}/policies/{w.ids['policy']}/submit", w.maya, {"comment": COMMENT})


def s_policies_withdraw(w: World) -> HttpResponse:
    return post(w.app, f"{API}/policies/{w.ids['policy']}/withdraw", w.maya, {"comment": COMMENT})


def s_policies_publish(w: World) -> HttpResponse:
    """The withdrawn version is reopened (PATCH: WITHDRAWN → DRAFT; the key has no other open
    version yet — the legacy-parity preset runs later), re-tested (job), re-submitted, approved by
    Nora (config.approve, MFA) and then confirmed."""
    path = f"{API}/policies/{w.ids['policy']}"
    reopened = patch(
        w.app,
        path,
        w.maya,
        # pin "P" (04 §16.5 rule 3; T-PLT-32): the first day of a FUTURE open period in the
        # entity's zone — 1 November 2026 starts at 04:00Z in America/New_York, not at 00:00Z
        {"effective_from": "2026-11-01T04:00:00Z"},
        if_match=_etag_of(w.app, path, w.maya),
    )
    assert reopened.status_code == 200, reopened.text
    tested = post(w.app, f"{path}/test", w.maya, {})
    assert tested.status_code == 202, tested.text
    _run_job(w, UUID(str(tested.json()["id"])))
    assert get(w.app, path, w.maya).json()["status"] == "TESTED"
    submitted = post(w.app, f"{path}/submit", w.maya, {"comment": COMMENT})
    assert submitted.status_code == 200, submitted.text
    w.ids["policy.approval"] = str(submitted.json()["pending_approval_request_id"])
    return _confirm_publish(w, "policy.approval", f"{path}/publish", w.nora)


def s_policies_presets_legacy_parity(w: World) -> HttpResponse:
    return post(w.app, f"{API}/policies/presets/legacy-parity", w.maya, {"scope": "TENANT"})


def s_import_mapping_profiles_create(w: World) -> HttpResponse:
    body = {  # CSV v2 templates only (mapping_errors: TEMPLATE_UNKNOWN for a legacy code)
        "code": "SF-EXPORT",
        "name": "Salesforce export",
        "template_code": "contracts",
        "mappings": {
            "aliases": {"Order Ref": "external_id"},
            "constants": {},
            "custom_attributes": [],
        },
    }
    return _created(w, "profile", post(w.app, f"{API}/import-mapping-profiles", w.maya, body))


def s_import_mapping_profiles_update(w: World) -> HttpResponse:
    return patch(
        w.app,
        f"{API}/import-mapping-profiles/{w.ids['profile']}",
        w.maya,
        {"name": "Salesforce export (renamed)"},
        if_match=w.ids["profile.etag"],
    )


def s_import_mapping_profiles_test(w: World) -> HttpResponse:
    return post(w.app, f"{API}/import-mapping-profiles/{w.ids['profile']}/test", w.maya, {})


def s_import_mapping_profiles_submit(w: World) -> HttpResponse:
    response = post(
        w.app,
        f"{API}/import-mapping-profiles/{w.ids['profile']}/submit",
        w.maya,
        {"comment": COMMENT},
    )
    if response.status_code < 400:
        w.ids["profile.approval"] = str(response.json()["approval_request_id"])
    return response


def s_import_mapping_profiles_publish(w: World) -> HttpResponse:
    path = f"{API}/import-mapping-profiles/{w.ids['profile']}/publish"
    return _confirm_publish(w, "profile.approval", path, w.nora)


def _import_upload(w: World, name: str, content: bytes) -> str:
    uploaded = call(
        w.app,
        "POST",
        f"{API}/files",
        data={"purpose": "IMPORT_SOURCE"},
        files={"file": (name, content, "application/octet-stream")},
        headers=cookie_headers(w.maya.token, w.maya.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    return str(uploaded.json()["id"])


def _import_source(w: World) -> str:
    return _import_upload(w, "SKU SSP Template.xlsx", SKU_SSP_FIXTURE.read_bytes())


def _run_import_jobs(w: World, import_id: str, job_id: UUID) -> None:
    """IMPORT_VALIDATE, then the IMPORT_DIFF job it defers (validate.py: DIFFING → DIFF_READY is
    that second job's work; submit needs DIFF_READY)."""
    _run_job(w, job_id)
    jobs = get(
        w.app,
        f"{API}/jobs",
        w.maya,
        {"subject_type": "import_upload", "subject_id": import_id, "kind": "IMPORT_DIFF"},
    )
    assert jobs.status_code == 200, jobs.text
    (diff,) = jobs.json()["items"]
    _run_job(w, UUID(str(diff["id"])))


def s_imports_create(w: World) -> HttpResponse:
    body = {"file_id": _import_source(w), "template_code": "legacy_sku_ssp"}
    response = post(w.app, f"{API}/imports", w.maya, body)
    if response.status_code < 400:
        w.ids["import"] = str(response.headers[IMPORT_ID_HEADER])
        _run_import_jobs(w, w.ids["import"], UUID(str(response.json()["id"])))
        shown = get(w.app, f"{API}/imports/{w.ids['import']}", w.maya).json()
        assert shown["status"] == "DIFF_READY", shown
    return response


def s_imports_submit(w: World) -> HttpResponse:
    return post(w.app, f"{API}/imports/{w.ids['import']}/submit", w.maya, {"comment": COMMENT})


def s_imports_cancel(w: World) -> HttpResponse:
    # A second import of IDENTICAL bytes is refused (upload._refuse_duplicate): rebuild the fixture
    # under another sheet title so the file hash differs.
    headers, rows = workbook_rows(SKU_SSP_FIXTURE)
    file_id = _import_upload(
        w, "SKU SSP (cancel).xlsx", workbook_bytes("SKU Setup 2", headers, rows)
    )
    body = {"file_id": file_id, "template_code": "legacy_sku_ssp"}
    second = post(w.app, f"{API}/imports", w.maya, body)
    assert second.status_code == 202, second.text
    _run_job(w, UUID(str(second.json()["id"])))
    return post(w.app, f"{API}/imports/{second.headers[IMPORT_ID_HEADER]}/cancel", w.maya, {})


def _checklist_items(w: World, period_id: str) -> list[dict[str, Any]]:
    listed = get(w.app, f"{API}/periods/{period_id}/checklist", w.maya, {"limit": 50})
    assert listed.status_code == 200, listed.text
    items: list[dict[str, Any]] = listed.json()["items"]
    return items


def _open_item(
    w: World, period_id: str, *, manual: bool = False, waivable: bool = False
) -> dict[str, Any]:
    """The first checklist item still to do (E-60: NOT_STARTED / IN_PROGRESS / FAILED); ``manual``
    restricts it to MANUAL-gate items, the only kind a person signs, and ``waivable`` to the items
    a waiver may be requested for (04 §16.8 ``is_waivable``; supervisor ruling R-55 (c): the two
    journal gates and the controller's certification are never waivable)."""
    return next(
        i
        for i in _checklist_items(w, period_id)
        if i.get("status") in ("NOT_STARTED", "IN_PROGRESS", "FAILED")
        and (not manual or i.get("gate_kind") == "MANUAL")
        and (not waivable or i.get("is_waivable") is True)
    )


def s_periods_checklist_sign(w: World) -> HttpResponse:
    item = _open_item(w, w.ids["period"], manual=True)
    state = _period_state(w)  # precondition="row": the period state's ETag
    return post(
        w.app,
        f"{API}/periods/{w.ids['period']}/checklist/{item['id']}/sign",
        w.nora,  # period.close holder with an MFA-verified session
        {"statement_accepted": True},
        if_match=f'"r{state["row_version"]}"',
    )


def s_periods_checklist_waive(w: World) -> HttpResponse:
    """Maya (``period.close``) requests the waiver: the route opens an ``EXCEPTION_WAIVER`` request
    for an ``exception.waive`` holder OTHER than the requester (BS4-D-07), which Nora — the walk's
    one MFA-verified holder — decides before the lock is requested (a pending request of the
    entity fails APPROVALS_CLEARED). The item is the tenant's second close task, the one the
    sign scenario left open: an unsigned blocking task refuses the lock until it is signed or its
    waiver is approved (supervisor ruling R-55 (a)), and a never-waivable gate answers 409
    ``invalid-transition`` (R-55 (c))."""
    item = _open_item(w, w.ids["period"], manual=True, waivable=True)
    state = _period_state(w)
    response = post(
        w.app,
        f"{API}/periods/{w.ids['period']}/checklist/{item['id']}/waive",
        w.maya,
        {"reason": "Balance below the review threshold this month (SOP-7 walk)."},
        if_match=f'"r{state["row_version"]}"',
    )
    if response.status_code < 400:
        w.ids["period.waiver_approval"] = str(response.json()["approval_request_id"])
    return response


def _period(w: World, key: str) -> dict[str, Any]:
    states = {i["period"]["period_key"]: i for i in periods(w.app, w.maya, entity="AVM-US")}
    result: dict[str, Any] = states[key]
    return result


def s_periods_request_permanent_lock(w: World) -> HttpResponse:
    """Nora (MFA controller, distinct from the requester) approves the P01 lock → CLOSED; then the
    permanent lock of P01 is requested (no earlier period: SM-07 holds)."""
    approved = _approve(w, w.ids["period_p01.lock_approval"], w.nora)
    assert approved.status_code == 200, approved.text
    state = _period_state(w)
    assert state["state"] == "closed", state  # E-04 literal
    return post(
        w.app,
        f"{API}/periods/{state['id']}/request-permanent-lock",
        w.nora,
        {"comment": "Audit complete for the period (SOP-7 walk)."},
        if_match=f'"r{state["row_version"]}"',
    )


def s_periods_request_reopen(w: World) -> HttpResponse:
    state = _period_state(w)  # P01 is CLOSED; the permanent lock is only requested
    return post(
        w.app,
        f"{API}/periods/{state['id']}/request-reopen",
        w.nora,
        {"reason_code": "ERROR_CORRECTION", "comment": "Late invoice to record (SOP-7 walk)."},
        if_match=f'"r{state["row_version"]}"',
    )


def s_rule_sets_evaluate(w: World) -> HttpResponse:
    return post(
        w.app,
        f"{API}/rule-sets/{w.ids['dq_set']}/evaluate",
        w.maya,
        {"facts": {}, "version_id": w.ids["dq_version"]},  # DATA_QUALITY takes no condition fields
    )


def s_session_select_tenant(w: World) -> HttpResponse:
    """The walk's root user gains a second membership, so a fresh sign-in opens no workspace and
    the selection writes TENANT_SELECTED."""
    other = member(w.keyring, w.clock, name="elsewhere")
    with tenant_session(_db(other.tenant_id)) as session:
        insert_active_membership(session, tenant_id=other.tenant_id, user_id=w.root.user_id)
    signed = sign_in(w.app, w.root.email)
    return call(
        w.app,
        "POST",
        f"{API}/session/tenant",
        json={"tenant_id": str(w.tenant_id)},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )


def _fresh_invitation(w: World) -> tuple[UUID, str]:
    """A membership invited now and ITS current token (Codex 0223 INVITATION-1): the walk's
    original membership was resent (token rotated) and then removed (token nulled), so acceptance
    needs an INVITED row. The token is read from the ONE outbox message of that aggregate, and its
    digest must equal the row's stored ``invitation_token_sha256``."""
    body = {
        "email": f"accept-{random_suffix()}@members.test",
        "display_name": "Accepting User",
        "roles": [{"role_id": w.role_id("viewer"), "is_all_entities": True}],
    }
    invited = post(w.app, f"{API}/users", w.tomas, body)
    assert invited.status_code == 201, invited.text
    membership_id = UUID(str(invited.json()["id"]))
    with tenant_session(_db(w.tenant_id), read_only=True) as session:
        payload = session.execute(
            select(outbox_message.c.payload).where(outbox_message.c.aggregate_id == membership_id)
        ).scalar_one()
        digest = session.execute(
            select(tables.tenant_membership.c.invitation_token_sha256).where(
                tables.tenant_membership.c.id == membership_id
            )
        ).scalar_one()
    token = emailed_token(payload, prefix="/accept-invitation#token=")
    assert sha256_hex(token) == digest, "the outbox token is not the membership's current token"
    return membership_id, token


def _membership_status(w: World, membership_id: UUID) -> str:
    with tenant_session(_db(w.tenant_id), read_only=True) as session:
        return str(
            session.execute(
                select(tables.tenant_membership.c.status).where(
                    tables.tenant_membership.c.id == membership_id
                )
            ).scalar_one()
        )


def s_session_lookup_invitation(w: World) -> HttpResponse:
    # Refusal on purpose (REFUSAL_EVIDENCE): a malformed token writes INVITATION_LOOKUP_FAILED.
    return call(w.app, "POST", f"{API}/session/invitations/lookup", json={"token": "not-a-token"})


def s_session_accept_invitation(w: World) -> HttpResponse:
    # Not REFUSAL_EVIDENCE: a 404 / 422 here is a named failure, never success.
    membership_id, token = _fresh_invitation(w)
    response = call(
        w.app,
        "POST",
        f"{API}/session/accept-invitation",
        json={"token": token, "password": "Probe!Ledger2027x"},
    )
    if response.status_code < 400:
        status = _membership_status(w, membership_id)
        assert status == "ACTIVE", f"the accepted membership is {status}"
    return response


def s_me_mfa_confirm(w: World) -> HttpResponse:
    code = totp.code_at(w.ids["leo.secret"], totp.time_step(w.clock.now()))
    response = call(
        w.app,
        "POST",
        f"{API}/me/mfa/confirm",
        json={"code": code},
        headers=cookie_headers(w.ids["leo.token"], w.ids["leo.csrf"]),
    )
    if response.status_code < 400:
        # SAR-09: the verified session rotates and the CSRF token is derived from the session token
        # (auth/sessions.csrf_token_for); the confirm body carries none, so re-read GET /session.
        signed = refreshed(w.app, cookie_of(response))
        w.ids["leo.token"], w.ids["leo.csrf"] = signed.token, signed.csrf_token
    return response


def s_me_regenerate_recovery_codes(w: World) -> HttpResponse:
    return call(
        w.app,
        "POST",
        f"{API}/me/recovery-codes",
        headers=cookie_headers(w.ids["leo.token"], w.ids["leo.csrf"]),
    )


# Order matters: creations precede the updates, submissions and revocations that reuse their ids.
WALK: Final[tuple[tuple[str, Scenario], ...]] = (
    ("calendars_create", s_calendars_create),
    ("calendars_generate_year", s_calendars_generate_year),
    ("entities_create", s_entities_create),
    ("entities_update", s_entities_update),
    ("entities_put_book", s_entities_put_book),
    ("books_update", s_books_update),
    ("close_checklist_templates_create", s_close_checklist_templates_create),
    ("close_checklist_templates_update", s_close_checklist_templates_update),
    ("periods_open", s_periods_open),
    ("periods_start_close", s_periods_start_close),
    ("periods_checklist_sign", s_periods_checklist_sign),
    ("periods_checklist_waive", s_periods_checklist_waive),
    ("periods_cancel_close", s_periods_cancel_close),
    ("periods_request_lock", s_periods_request_lock),
    ("periods_request_permanent_lock", s_periods_request_permanent_lock),
    ("periods_request_reopen", s_periods_request_reopen),
    ("gl_accounts_create", s_gl_accounts_create),
    ("gl_accounts_update", s_gl_accounts_update),
    ("account_mappings_create", s_account_mappings_create),
    ("account_mappings_update", s_account_mappings_update),
    ("account_mapping_rules_create", s_account_mapping_rules_create),
    ("account_mapping_rules_delete", s_account_mapping_rules_delete),
    ("account_mappings_test", s_account_mappings_test),
    ("account_mappings_submit", s_account_mappings_submit),
    ("account_mappings_publish", s_account_mappings_publish),
    ("customers_create", s_customers_create),
    ("customers_update", s_customers_update),
    ("related_party_groups_create", s_related_party_groups_create),
    ("related_party_groups_update", s_related_party_groups_update),
    ("dimensions_create", s_dimensions_create),
    ("dimension_values_create", s_dimension_values_create),
    ("dimension_values_update", s_dimension_values_update),
    ("products_create", s_products_create),
    ("products_update", s_products_update),
    ("products_propose_principal_agent_change", s_products_propose_principal_agent_change),
    ("products_propose_policy_values_change", s_products_propose_policy_values_change),
    ("products_bundle_components_put", s_products_bundle_components_put),
    ("pob_templates_create", s_pob_templates_create),
    ("pob_template_versions_create", s_pob_template_versions_create),
    ("pob_template_versions_update", s_pob_template_versions_update),
    ("pob_template_versions_test", s_pob_template_versions_test),
    ("pob_template_versions_submit", s_pob_template_versions_submit),
    ("pob_template_versions_publish", s_pob_template_versions_publish),
    ("ssp_books_create", s_ssp_books_create),
    ("ssp_books_update", s_ssp_books_update),
    ("ssp_book_versions_create", s_ssp_book_versions_create),
    ("ssp_book_versions_update", s_ssp_book_versions_update),
    ("ssp_entries_upsert", s_ssp_entries_upsert),
    ("files_upload", s_files_upload),
    ("attachments_create", s_attachments_create),
    ("files_shred", s_files_shred),
    ("ssp_book_versions_submit", s_ssp_book_versions_submit),
    ("files_request_shred", s_files_request_shred),
    ("ssp_book_versions_withdraw", s_ssp_book_versions_withdraw),
    ("ssp_entries_delete", s_ssp_entries_delete),
    ("attachments_void", s_attachments_void),
    ("rule_sets_create", s_rule_sets_create),
    ("rule_set_versions_create", s_rule_set_versions_create),
    ("rule_set_versions_update", s_rule_set_versions_update),
    ("config_test_cases_create", s_config_test_cases_create),
    ("config_test_cases_update", s_config_test_cases_update),
    ("config_test_cases_delete", s_config_test_cases_delete),
    ("rule_set_version_rules_upsert", s_rule_set_version_rules_upsert),
    ("rule_set_version_rules_delete", s_rule_set_version_rules_delete),
    ("rule_set_version_test_cases_create", s_rule_set_version_test_cases_create),
    ("rule_set_versions_lint", s_rule_set_versions_lint),
    ("rule_set_versions_test", s_rule_set_versions_test),
    ("rule_sets_evaluate", s_rule_sets_evaluate),
    ("rule_set_versions_submit", s_rule_set_versions_submit),
    ("rule_set_versions_publish", s_rule_set_versions_publish),
    ("policies_create", s_policies_create),
    ("policies_update", s_policies_update),
    ("policies_test", s_policies_test),
    ("policies_submit", s_policies_submit),
    ("policies_withdraw", s_policies_withdraw),
    ("policies_publish", s_policies_publish),
    ("policies_presets_legacy_parity", s_policies_presets_legacy_parity),
    ("fx_rate_sets_create", s_fx_rate_sets_create),
    ("fx_rate_set_versions_create", s_fx_rate_set_versions_create),
    ("fx_rate_set_versions_update", s_fx_rate_set_versions_update),
    ("fx_rate_set_versions_submit", s_fx_rate_set_versions_submit),
    ("fx_rate_set_versions_withdraw", s_fx_rate_set_versions_withdraw),
    ("tenant_currencies_put", s_tenant_currencies_put),
    ("tenant_update", s_tenant_update),
    ("webhook_endpoints_create", s_webhook_endpoints_create),
    ("webhook_endpoints_update", s_webhook_endpoints_update),
    ("integrations_create", s_integrations_create),
    ("integrations_update", s_integrations_update),
    ("integrations_test", s_integrations_test),
    ("integrations_sync", s_integrations_sync),
    ("webhooks_receive", s_webhooks_receive),
    ("external_ids_create", s_external_ids_create),
    ("saved_views_create", s_saved_views_create),
    ("saved_views_update", s_saved_views_update),
    ("saved_views_delete", s_saved_views_delete),
    ("import_mapping_profiles_create", s_import_mapping_profiles_create),
    ("import_mapping_profiles_update", s_import_mapping_profiles_update),
    ("import_mapping_profiles_test", s_import_mapping_profiles_test),
    ("import_mapping_profiles_submit", s_import_mapping_profiles_submit),
    ("import_mapping_profiles_publish", s_import_mapping_profiles_publish),
    ("imports_create", s_imports_create),
    ("imports_submit", s_imports_submit),
    ("imports_cancel", s_imports_cancel),
    ("exceptions_assign", s_exceptions_assign),
    ("exceptions_request_waiver", s_exceptions_request_waiver),
    ("exceptions_dismiss", s_exceptions_dismiss),
    ("exceptions_reprocess", s_exceptions_reprocess),
    ("exceptions_resolve", s_exceptions_resolve),
    ("migrations_create", s_migrations_create),
    ("migrations_profile", s_migrations_profile),
    ("migrations_import", s_migrations_import),
    ("migrations_cancel", s_migrations_cancel),
    ("migrations_reconcile", s_migrations_reconcile),
    ("roles_create", s_roles_create),
    ("approvals_approve", s_approvals_approve),
    ("approvals_reject", s_approvals_reject),
    ("approvals_withdraw", s_approvals_withdraw),
    ("approvals_bulk_approve", s_approvals_bulk_approve),
    ("roles_propose_change", s_roles_propose_change),
    ("users_invite", s_users_invite),
    ("users_resend_invitation", s_users_resend_invitation),
    ("users_update", s_users_update),
    ("role_assignments_create", s_role_assignments_create),
    ("role_assignments_revoke", s_role_assignments_revoke),
    ("users_suspend", s_users_suspend),
    ("users_reactivate", s_users_reactivate),
    ("users_remove", s_users_remove),
    ("users_anonymise", s_users_anonymise),
    ("api_clients_create", s_api_clients_create),
    ("api_clients_rotate_secret", s_api_clients_rotate_secret),
    ("api_clients_revoke", s_api_clients_revoke),
    ("approval_delegations_create", s_approval_delegations_create),
    ("approval_delegations_revoke", s_approval_delegations_revoke),
    ("sod_rule_versions_create", s_sod_rule_versions_create),
    ("sod_exceptions_create", s_sod_exceptions_create),
    ("sod_exceptions_revoke", s_sod_exceptions_revoke),
    ("support_grants_create", s_support_grants_create),
    ("support_grants_revoke", s_support_grants_revoke),
    ("access_reviews_create", s_access_reviews_create),
    ("access_reviews_start", s_access_reviews_start),
    ("access_reviews_items_decide", s_access_reviews_items_decide),
    ("access_reviews_items_confirm_revocation", s_access_reviews_items_confirm_revocation),
    ("access_reviews_complete", s_access_reviews_complete),
    ("access_reviews_cancel", s_access_reviews_cancel),
    ("report_runs_create", s_report_runs_create),
    ("report_runs_rerun", s_report_runs_rerun),
    ("jobs_cancel", s_jobs_cancel),
    ("audit_events_verify", s_audit_events_verify),
    ("tenant_snapshots_request", s_tenant_snapshots_request),
    ("tenant_sandboxes_request", s_tenant_sandboxes_request),
    ("tenant_reset_request", s_tenant_reset_request),
    ("contracts_create", s_contracts_create),
    ("combination_suggestions_dismiss", s_combination_suggestions_dismiss),
    ("contracts_replace_draft", s_contracts_replace_draft),
    ("contracts_submit_activation", s_contracts_submit_activation),
    ("contract_events_append", s_contract_events_append),
    ("contract_events_preview", s_contract_events_preview),
    ("contracts_update_memos", s_contracts_update_memos),
    ("contracts_apply_hold", s_contracts_apply_hold),
    ("contracts_release_hold", s_contracts_release_hold),
    ("contracts_request_void", s_contracts_request_void),
    ("contracts_distinct_review", s_contracts_distinct_review),
    ("obligations_request_ssp_override", s_obligations_request_ssp_override),
    ("contract_estimates_create", s_contract_estimates_create),
    ("estimate_versions_create", s_estimate_versions_create),
    ("estimate_versions_update", s_estimate_versions_update),
    ("estimate_versions_preview", s_estimate_versions_preview),
    ("estimate_versions_submit", s_estimate_versions_submit),
    ("estimate_versions_withdraw", s_estimate_versions_withdraw),
    ("estimate_versions_discard", s_estimate_versions_discard),
    ("judgements_create", s_judgements_create),
    ("judgements_update", s_judgements_update),
    ("judgements_submit", s_judgements_submit),
    ("judgements_discard", s_judgements_discard),
    ("combination_groups_create", s_combination_groups_create),
    ("combination_groups_submit", s_combination_groups_submit),
    ("combination_groups_discard", s_combination_groups_discard),
    ("contracts_regroup", s_contracts_regroup),
    ("events_request_void", s_events_request_void),
    ("event_submissions_withdraw", s_event_submissions_withdraw),
    ("contract_modifications_create", s_contract_modifications_create),
    # Codex 0223 MODIFICATION-1: the edit precedes the final classification (update resets
    # proposed_treatments and the preview pointers).
    ("modifications_update", s_modifications_update),
    ("modifications_classify", s_modifications_classify),
    ("modifications_preview", s_modifications_preview),
    ("modifications_submit", s_modifications_submit),
    ("modifications_withdraw", s_modifications_withdraw),
    ("modifications_discard", s_modifications_discard),
    # API-R-37 (CLO-12): prepared, edited, previewed, submitted, deferral asked, the request
    # withdrawn, the draft discarded — every command of the adjustment, and nothing posts.
    ("manual_adjustments_create", s_manual_adjustments_create),
    ("manual_adjustments_update", s_manual_adjustments_update),
    ("manual_adjustments_preview", s_manual_adjustments_preview),
    ("manual_adjustments_submit", s_manual_adjustments_submit),
    ("manual_adjustments_request_defer_past_lock", s_manual_adjustments_request_defer_past_lock),
    ("manual_adjustments_withdraw", s_manual_adjustments_withdraw),
    ("manual_adjustments_discard", s_manual_adjustments_discard),
    ("policy_overrides_create", s_policy_overrides_create),
    ("policy_overrides_submit", s_policy_overrides_submit),
    ("journal_runs_create", s_journal_runs_create),
    ("journal_runs_submit", s_journal_runs_submit),
    ("journal_runs_export", s_journal_runs_export),
    # CLO-14: the export fails, is retried and, once the file is written, acknowledged.
    ("journal_batches_retry", s_journal_batches_retry),
    ("journal_batches_acknowledge", s_journal_batches_acknowledge),
    ("journal_runs_cancel", s_journal_runs_cancel),
    ("explain_verify", s_explain_verify),
    ("ssp_calculator_runs_create", s_ssp_calculator_runs_create),
    ("ssp_calculator_exclusions_create", s_ssp_calculator_exclusions_create),
    ("ssp_calculator_runs_create_draft_version", s_ssp_calculator_runs_create_draft_version),
    ("reconciliations_create", s_reconciliations_create),
    ("reconciliations_attach_trial_balance", s_reconciliations_attach_trial_balance),
    ("reconciliations_items_update", s_reconciliations_items_update),
    ("reconciliations_prepare", s_reconciliations_prepare),
    ("reconciliations_sign", s_reconciliations_sign),
    ("reconciliations_reopen", s_reconciliations_reopen),
    ("close_runs_create", s_close_runs_create),
    ("close_runs_resume", s_close_runs_resume),
    ("close_runs_cancel", s_close_runs_cancel),
    # JRN-FAILED-CANCEL-1: after every other scenario of the engine world — the second P09 run
    # journalises what they recorded, and its failed batches stay with nobody.
    ("journal_batches_hand_over", s_journal_batches_hand_over),
    ("me_notification_preferences_put", s_me_notification_preferences_put),
    ("me_preferences_update", s_me_preferences_update),
    ("me_notifications_read_all", s_me_notifications_read_all),
    ("me_notifications_read", s_me_notifications_read),
    ("users_reset_mfa", s_users_reset_mfa),
    ("session_login", s_session_login),
    ("me_mfa_enroll", s_me_mfa_enroll),
    ("me_mfa_confirm", s_me_mfa_confirm),
    ("me_regenerate_recovery_codes", s_me_regenerate_recovery_codes),
    ("me_change_password", s_me_change_password),
    ("session_verify_mfa", s_session_verify_mfa),
    ("session_logout", s_session_logout),
    ("session_select_tenant", s_session_select_tenant),
    ("session_lookup_invitation", s_session_lookup_invitation),
    ("session_accept_invitation", s_session_accept_invitation),
)


# ---- evidence readers ------------------------------------------------------------------------


CONFIRM_KEYS: Final = (
    "confirm.approve_request",  # X-Request-Id of the FINAL approving call
    "confirm.approval_id",  # the business approval request id
    "confirm.subject_id",  # the version-row UUID the approval published
    "confirm.approver_user_id",  # the approving actor
    "confirm.before",  # bounded subject state before the confirm
    "confirm.after",  # ... and after it
)
BOUNDED_STATE: Final = ("status", "row_version", "updated_at", "content_sha256")


def _bounded_state(w: World, path: str, actor: Actor) -> str:
    """The subject's bounded state (status, row_version, updated_at, content hash) as one string."""
    shown = get(w.app, path, actor)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    return json.dumps({key: body.get(key) for key in BOUNDED_STATE}, sort_keys=True, default=str)


def _audit_events(tenant_id: UUID, request_id: str) -> list[Mapping[str, Any]]:
    """The audit rows of one request with what the confirm correlation needs: action, actor,
    outcome, object type and id, and the approval request (``object_version`` is nullable and is
    not read)."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return [
            dict(row)
            for row in session.execute(
                select(
                    audit_event.c.action,
                    audit_event.c.actor_kind,
                    audit_event.c.actor_id,
                    audit_event.c.outcome,
                    audit_event.c.object_type,
                    audit_event.c.object_id,
                    audit_event.c.approval_request_id,
                    audit_event.c.detail,
                ).where(audit_event.c.request_id == request_id)
            ).mappings()
        ]


def _audit_rows(tenant_id: UUID, request_id: str) -> list[Mapping[str, Any]]:
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return [
            dict(row)
            for row in session.execute(
                select(
                    audit_event.c.action,
                    audit_event.c.actor_kind,
                    audit_event.c.outcome,
                    audit_event.c.object_type,
                    audit_event.c.detail,
                ).where(audit_event.c.request_id == request_id)
            ).mappings()
        ]


def _contract_ids(tenant_id: UUID) -> frozenset[str]:
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return frozenset(str(value) for value in session.execute(select(contract.c.id)).scalars())


# 04 T-PLT-19 ``detail.contract_id`` / ``detail.contract_ids`` (rev 1.154; DG-KRN-AUD-09; ruling
# R-108): an event of an object that belongs to a contract names the contract. The object types are
# the closed lists of ``erev_api.audit.contract_key``. An event of a type that MAY name no contract
# (``WHERE_NAMED``) carries the key as well, unless its operation and object type are named here
# with why that object is about no contract; an entry no event of the walk used fails by name, so
# the list cannot outlive its reason.
NO_CONTRACT: Final[Mapping[tuple[str, str], str]] = {
    # ``_no_data_import``: an IMPORT_NO_DATA_ROWS item of an upload that booked nothing — T-IMP-05
    # ``contract_id`` and ``combination_group_id`` are null.
    ("exceptions_assign", "exception_item"): "the item of an upload without data rows",
    ("exceptions_dismiss", "exception_item"): "the item of an upload without data rows",
}


def _contract_key_failures(
    operation_id: str,
    rows: Sequence[Mapping[str, Any]],
    contracts: Collection[str],
    unkeyed: set[tuple[str, str]],
) -> list[str]:
    """The contract key check, pure: what the events of one operation miss of 04 T-PLT-19.
    ``contracts`` are the ids of the tenant's contracts; ``unkeyed`` collects the ``NO_CONTRACT``
    entries the events used."""
    known = contract_key.ALWAYS | contract_key.WHERE_NAMED | contract_key.OTHER
    failures: list[str] = []
    for row in rows:
        object_type, action = str(row["object_type"]), str(row["action"])
        if object_type not in known:
            failures.append(
                f"{operation_id}: {action} is of object type {object_type}, which is in none of "
                "the contract key lists (erev_api.audit.contract_key)"
            )
            continue
        detail = row["detail"] or {}
        one = detail.get(contract_key.CONTRACT_ID)
        several = detail.get(contract_key.CONTRACT_IDS)
        if one is not None and several is not None:
            failures.append(f"{operation_id}: {action} carries contract_id and contract_ids")
        if several is not None and (len(several) < 2 or several != sorted(set(several))):
            failures.append(
                f"{operation_id}: contract_ids of {action} is not two or more ids, sorted: "
                f"{several}"
            )
        named = [*([] if one is None else [one]), *(several or [])]
        strangers = sorted(str(value) for value in named if str(value) not in contracts)
        if strangers:
            failures.append(f"{operation_id}: {action} names {strangers}, which is no contract")
        if named or not contract_key.scoped(object_type):
            continue
        if (operation_id, object_type) in NO_CONTRACT:
            unkeyed.add((operation_id, object_type))
            continue
        failures.append(
            f"{operation_id}: {action} is an event of {object_type} and names no contract"
        )
    return failures


def _security_kinds(request_id: str) -> list[str]:
    with identity_session(request_id="sop7-read-security-events") as session:
        return [
            str(kind)
            for kind in session.execute(
                select(security_event.c.kind).where(security_event.c.request_id == request_id)
            ).scalars()
        ]


def _counts(tenant_id: UUID) -> dict[str, int]:
    """Row counts of every tenant-scoped table, read as the app role (the walk's write boundary)."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return {
            table.name: int(session.execute(select(func.count()).select_from(table)).scalar_one())
            for table in tables.metadata.sorted_tables
            if "tenant_id" in table.c
        }


@dataclass
class Walk:
    covered: dict[str, str] = field(default_factory=dict)  # operation id → request id
    actions: set[str] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)
    failures: list[str] = field(default_factory=list)
    unkeyed: set[tuple[str, str]] = field(default_factory=set)  # the NO_CONTRACT entries used


REQUEST_TENANT: Final[Mapping[str, Callable[[World], UUID]]] = {
    # Codex 0545 QUERY-TENANT-1: a query operation whose request runs in another world's tenant
    # names it here, so that world is prepared and its tenant selected BEFORE the no-write baseline.
    "explain_verify": lambda w: _engine(w).place.tenant_id,
    # SOP-7 class (e): the refused creation is asked in the K-02 world, whose tables are counted.
    "policy_overrides_create": lambda w: _engine(w).place.tenant_id,
}


def _request_tenant(world: World, operation_id: str) -> UUID:
    """The tenant the operation's request runs in: the walk's tenant unless REQUEST_TENANT names
    another (selecting it prepares that world first, e.g. builds the K-02 engine)."""
    select = REQUEST_TENANT.get(operation_id)
    return world.tenant_id if select is None else select(world)


def _changed_tables(
    before: Mapping[str, int], after: Mapping[str, int], operation_id: str
) -> list[str]:
    """The no-write check, pure: the tenant-scoped tables whose row counts moved across a query
    operation, minus the idempotency row and the operation's own 04 §1.7 personal rows."""
    allowed = INFRASTRUCTURE_TABLES | PERSONAL_TABLES.get(operation_id, frozenset())
    return sorted(name for name in after if after[name] != before.get(name) and name not in allowed)


def _refused_failures(
    operation_id: str,
    expected: Sequence[str],
    status_code: int,
    rule_ids: Sequence[str | None],
    audit_rows: int,
    changed: Sequence[str],
) -> list[str]:
    """SOP-7 class (e), pure: what a command the release refuses by name answered and left
    behind. It must answer 422 with exactly the rule ids the catalogue states — a success above
    all is a failure, the command being refused in this release — write no audit event under its
    request and change no row count; each miss is named."""
    failures: list[str] = []
    if status_code != 422 or list(rule_ids) != list(expected):
        failures.append(
            f"{operation_id}: a command the release refuses by name answered HTTP {status_code} "
            f"with rule ids {list(rule_ids)}, not 422 with {list(expected)}"
        )
    if audit_rows:
        failures.append(f"{operation_id}: a refused command wrote {audit_rows} audit_event row(s)")
    if changed:
        failures.append(f"{operation_id}: a refused command changed rows of {list(changed)}")
    return failures


def _exercise(world: World, walk: Walk, operation_id: str, scenario: Scenario) -> None:
    route = ROUTES[operation_id]
    world.evidence_tenant_id = None
    # The request tenant is selected before the baseline and the SAME tenant is compared after the
    # command (Codex 0545 QUERY-TENANT-1); the evidence tenant a scenario sets afterwards only
    # scopes the audit lookup.
    request_tenant = _request_tenant(world, operation_id)
    before = _counts(request_tenant) if route.evidence in ("query", "refused") else {}
    try:
        response = scenario(world)
    except Exception as exc:  # a scenario's own precondition failed (Codex 2338): record, go on
        walk.failures.append(f"{operation_id}: the scenario raised {type(exc).__name__}")
        return
    tenant_id = world.evidence_tenant_id or request_tenant
    if route.evidence == "refused":
        # BUILD_SPEC SOP-7 class (e): no successful call exists, so the refusal is the evidence —
        # its rule id, no audit event under the request, no changed table of the request tenant.
        request_id = response.headers.get(REQUEST_ID)
        if not request_id:
            walk.failures.append(f"{operation_id}: the response carries no {REQUEST_ID}")
            return
        errors = response.json().get("errors") or [] if response.status_code >= 400 else []
        walk.failures += _refused_failures(
            operation_id,
            route.rule_ids,
            response.status_code,
            [error.get("rule_id") for error in errors],
            len(_audit_rows(tenant_id, request_id)),
            _changed_tables(before, _counts(request_tenant), operation_id),
        )
        walk.covered[operation_id] = request_id
        return
    refused_on_purpose = operation_id in REFUSAL_EVIDENCE and response.status_code in (404, 422)
    if response.status_code >= 400 and not refused_on_purpose:
        walk.failures.append(
            f"{operation_id}: the scenario call failed with HTTP {response.status_code}"
        )
        return
    request_id = response.headers.get(REQUEST_ID)
    if not request_id:
        walk.failures.append(f"{operation_id}: the response carries no {REQUEST_ID}")
        return
    walk.covered[operation_id] = request_id
    if route.evidence == "audit_event":
        rows = _audit_rows(tenant_id, request_id)
        if not rows:
            walk.failures.append(f"{operation_id}: no audit_event for request {request_id}")
            return
        bad = [str(row["action"]) for row in rows if not ACTION.match(str(row["action"]))]
        if bad:
            walk.failures.append(f"{operation_id}: action not <object>.<verb>: {bad}")
        # BUILD_SPEC SOP-7: "writes at least one `audit_event` in the same transaction, with
        # `action` matching …, `request_id` equal to the response `X-Request-Id`, and `actor_kind`
        # of the caller" — AT LEAST ONE such row (supervisor ruling R-15). Every row read here
        # carries the response's request id; a row the command's own fact append writes as SYSTEM
        # beside the caller's rows — the EVENT_VOIDED of a replaced draft (04 §16.1), the
        # HOLD_APPLIED of a SYSTEM recognition hold (REQ-POL-010; contracts/holds.py) — does not
        # contradict the acceptance.
        kinds = {str(row["actor_kind"]) for row in rows}
        expected_kind = "SYSTEM" if operation_id in SYSTEM_ACTOR else "USER"
        if expected_kind not in kinds:
            note = (
                " (SYSTEM_ACTOR: the receiver records the system principal)"
                if expected_kind == "SYSTEM"
                else ""
            )
            walk.failures.append(
                f"{operation_id}: no audit_event carries the caller's actor_kind "
                f"{expected_kind}; found {sorted(kinds)}{note}"
            )
        walk.failures += _contract_key_failures(
            operation_id, rows, _contract_ids(tenant_id), walk.unkeyed
        )
        walk.actions.update(str(row["action"]) for row in rows)
    elif route.evidence == "security_event":
        kinds = _security_kinds(request_id)
        if not kinds:
            walk.failures.append(f"{operation_id}: no security_event for request {request_id}")
            return
        if route.security_events and not set(kinds) & set(route.security_events):
            walk.failures.append(
                f"{operation_id}: kinds {sorted(kinds)} miss {route.security_events}"
            )
        walk.kinds.update(kinds)
    elif route.evidence == "confirm":
        # SOP7-PUBLISH-CONFIRM-1 (Codex 0527 §2): (a) the FINAL approving request's audit rows hold
        # the SUCCESS <table>.published row for THIS version row, this approval and this approver;
        # (b) the confirm was a DISTINCT fresh request (post() sends a fresh Idempotency-Key) that
        # answered the same PUBLISHED version and wrote no audit row of its own; (c) the bounded
        # subject state is unchanged across the confirm. The APPROVED-left-unpublished /publish
        # branch is NOT what this witnesses.
        facts = {key: world.ids.pop(key, None) for key in CONFIRM_KEYS}
        if any(value is None for value in facts.values()):
            walk.failures.append(f"{operation_id}: the scenario recorded no approval correlation")
            return
        table = route.actions[0].rsplit(".", 1)[0]
        events = _audit_events(tenant_id, facts["confirm.approve_request"])
        published = [
            row
            for row in events
            if str(row["action"]) == route.actions[0]
            and str(row["object_type"]) == table
            and str(row["object_id"]) == facts["confirm.subject_id"]
            and str(row["approval_request_id"]) == facts["confirm.approval_id"]
            and str(row["actor_id"]) == facts["confirm.approver_user_id"]
            and str(row["outcome"]) == "SUCCESS"
        ]
        if not published:
            walk.failures.append(
                f"{operation_id}: approval {facts['confirm.approval_id']} (request "
                f"{facts['confirm.approve_request']}) wrote no SUCCESS {route.actions[0]} for "
                f"{table} {facts['confirm.subject_id']} by {facts['confirm.approver_user_id']}; "
                f"it wrote {sorted(str(row['action']) for row in events)}"
            )
        # Codex 1458 §1 "APPROVED → PUBLISHED": the same approving request also wrote the version's
        # approval transition, so the publication is the approval's own unit of work.
        if not any(
            str(row["action"]) == f"{table}.approved"
            and str(row["object_id"]) == facts["confirm.subject_id"]
            for row in events
        ):
            walk.failures.append(
                f"{operation_id}: the approving request wrote no {table}.approved for the row"
            )
        if response.json().get("status") != "PUBLISHED":
            walk.failures.append(f"{operation_id}: the confirm did not answer PUBLISHED")
        if str(response.json().get("id")) != facts["confirm.subject_id"]:
            walk.failures.append(f"{operation_id}: the confirm answered another version row")
        if _audit_rows(tenant_id, request_id):
            walk.failures.append(f"{operation_id}: an idempotent confirm wrote an audit_event")
        if facts["confirm.before"] != facts["confirm.after"]:
            walk.failures.append(
                f"{operation_id}: the confirm changed the bounded subject state "
                f"{facts['confirm.before']} -> {facts['confirm.after']}"
            )
        walk.failures += _contract_key_failures(
            operation_id, events, _contract_ids(tenant_id), walk.unkeyed
        )
        walk.actions.update(str(row["action"]) for row in events)
    elif route.evidence == "query":
        if _audit_rows(tenant_id, request_id):
            walk.failures.append(f"{operation_id}: a query operation wrote an audit_event")
        changed = _changed_tables(before, _counts(request_tenant), operation_id)
        if changed:
            walk.failures.append(f"{operation_id}: a query operation changed rows of {changed}")
    else:  # provisioning: DG-KRN-TEN-01 events, exercised by the operator provisioning tests
        walk.failures.append(f"{operation_id}: provisioning routes are not walked here")


def _run_walk(world: World) -> Walk:
    walk = Walk()
    for operation_id, scenario in WALK:
        _exercise(world, walk, operation_id, scenario)
    return walk


def uncovered_operations() -> tuple[list[str], list[str]]:
    """The required operations WITHOUT a scenario in ``WALK`` — (audited, query) — computed from the
    registry alone and reported in the same assertion as the scenario failures; a scenario that
    raises (a failed precondition such as ``books_update``'s GET) is recorded as a named failure and
    the walk goes on, so one run reports the full set (Codex P4-SOP7 C1; Codex 2338 wording)."""
    authored = {operation_id for operation_id, _ in WALK}
    missing = sorted(required_operations() - authored)
    return (
        [op for op in missing if op not in QUERY_EXEMPT],
        [op for op in missing if op in QUERY_EXEMPT],
    )


def authored_count() -> int:
    """Scenarios of ``WALK`` that count towards the 188 required operations (an exempt class (a)
    route such as ``session_login`` may be exercised for its security evidence but is not one)."""
    return len({operation_id for operation_id, _ in WALK} & required_operations())


# ---- the tests -------------------------------------------------------------------------------


@pytest.mark.control("CTL-038")
def test_ctl_038_every_command_route_writes_audit(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    assert {operation_id for operation_id, _ in WALK} <= set(ROUTES), (
        "WALK names unknown operations"
    )
    audited, queries = uncovered_operations()
    world = _world(app, keyring, clock, runtime)
    walk = _run_walk(world)
    problems = list(walk.failures)
    if audited:
        problems.append(
            f"audited operations without a walk scenario ({len(audited)} of "
            f"{len(required_operations())} required; {authored_count()} authored): {audited}"
        )
    if queries:
        problems.append(f"query operations without a no-write scenario ({len(queries)}): {queries}")
    unused = sorted(entry for entry in NO_CONTRACT if entry not in walk.unkeyed)
    if unused:
        problems.append(f"NO_CONTRACT entries no event of the walk used: {unused}")
    assert not problems, "\n".join(problems)


def test_req_plt_019_categories_covered(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Every REQ-PLT-019 category fails by name when unobserved — a category pending on a lane is
    named with its owner and fails all the same (Codex P4-SOP7 R1: no silent pending path)."""
    world = _world(app, keyring, clock, runtime)
    walk = _run_walk(world)
    missing = uncovered_categories(walk.actions, walk.kinds)
    assert not missing, f"REQ-PLT-019 categories without an observed action or kind: {missing}"


def test_denied_commands_audited(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    root = member(keyring, clock, name="maya")
    vera = holding(app, colleague(root.tenant_id, "vera"), "viewer")
    calls: tuple[tuple[str, Callable[[], HttpResponse]], ...] = (
        (
            "roles_create",
            lambda: post(
                app,
                f"{API}/roles",
                vera,
                {"code": "x_role", "name": "X", "permissions": ["contract.read"]},
            ),
        ),
        (
            "api_clients_create",
            lambda: post(
                app, f"{API}/api-clients", vera, {"name": "svc-x", "scopes": ["contract.read"]}
            ),
        ),
        (
            "customers_create",
            lambda: post(app, f"{API}/customers", vera, {"code": "C-X", "name": "X"}),
        ),
        (
            "gl_accounts_create",
            lambda: post(
                app,
                f"{API}/gl-accounts",
                vera,
                {"code": "9999", "name": "X", "account_type": "ASSET", "normal_balance": "D"},
            ),
        ),
        (
            "users_invite",
            lambda: post(
                app,
                f"{API}/users",
                vera,
                {"email": "x@members.test", "display_name": "X", "roles": []},
            ),
        ),
    )
    for operation_id, request in calls:
        response = request()
        assert response.status_code == 403, (
            f"{operation_id}: {response.status_code} {response.text}"
        )
        rows = _audit_rows(root.tenant_id, response.headers[REQUEST_ID])
        denied = [row for row in rows if str(row["outcome"]) == "DENIED"]
        assert len(denied) == 1, f"{operation_id}: DENIED events {len(denied)} (rows {rows})"
        assert ACTION.match(str(denied[0]["action"])), denied[0]
        assert str(denied[0]["actor_kind"]) == "USER"


def test_contract_key_check_names_each_kind_of_miss() -> None:
    """The contract key check is exercised against events that miss it (04 T-PLT-19, rev 1.154)."""
    a, b = "00000000-0000-7000-8000-00000000000a", "00000000-0000-7000-8000-00000000000b"

    def event(object_type: str, **detail: Any) -> dict[str, Any]:
        return {"action": f"{object_type}.update", "object_type": object_type, "detail": detail}

    used: set[tuple[str, str]] = set()
    assert _contract_key_failures(
        "op",
        [
            event("modification", contract_id=a),
            event("combination_group", contract_ids=[a, b]),
            event("tenant"),
            event("contract_hold"),  # a contract's object without the key
            event("estimate_version"),  # may name none, but no NO_CONTRACT entry says why
            event("brand_new_table"),
            event("modification", contract_id=a, contract_ids=[a, b]),
            event("combination_group", contract_ids=[b, a]),
            event("combination_group", contract_ids=[a]),
            event("obligation", contract_id="00000000-0000-7000-8000-00000000000c"),
        ],
        {a, b},
        used,
    ) == [
        "op: contract_hold.update is an event of contract_hold and names no contract",
        "op: estimate_version.update is an event of estimate_version and names no contract",
        "op: brand_new_table.update is of object type brand_new_table, which is in none of the "
        "contract key lists (erev_api.audit.contract_key)",
        "op: modification.update carries contract_id and contract_ids",
        f"op: contract_ids of combination_group.update is not two or more ids, sorted: {[b, a]}",
        f"op: contract_ids of combination_group.update is not two or more ids, sorted: {[a]}",
        "op: obligation.update names ['00000000-0000-7000-8000-00000000000c'], which is no "
        "contract",
    ]
    assert used == set()
    # An event of a type that may name no contract passes unkeyed only under its NO_CONTRACT entry.
    (entry,) = [key for key in NO_CONTRACT if key[0] == "exceptions_assign"]
    assert _contract_key_failures(entry[0], [event(entry[1])], set(), used) == []
    assert used == {entry}


def test_query_no_write_check_names_a_mutation() -> None:
    """Discriminating witness (Codex 0545 QUERY-TENANT-1), CPU: a row written by a query operation
    is named; the idempotency row and the operation's own personal rows are not; the request-tenant
    selectors name only operations whose no-write baseline the walk reads — the query class and,
    since fragment 11 rev 1.44, the refused class."""
    before = {"customer": 3, "idempotency_record": 10, "notification": 1}
    assert _changed_tables(before, {**before, "customer": 4}, "explain_verify") == ["customer"]
    assert _changed_tables(before, {**before, "idempotency_record": 11}, "explain_verify") == []
    assert _changed_tables(before, {**before, "notification": 2}, "me_notifications_read") == []
    assert _changed_tables(before, {**before, "notification": 2}, "explain_verify") == [
        "notification"
    ]
    assert set(REQUEST_TENANT) <= QUERY_EXEMPT | RELEASE_REFUSED
    assert set(REQUEST_TENANT) & QUERY_EXEMPT == {"explain_verify"}
    assert set(REQUEST_TENANT) & RELEASE_REFUSED == RELEASE_REFUSED


def test_query_no_write_check_fails_on_a_request_tenant_mutation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Discriminating witness (Codex 0545 QUERY-TENANT-1), DB-bound: a customer created in the
    REQUEST tenant (the K-02 world) around explain_verify must fail the no-write check by name —
    the baseline and the comparison read that same tenant, selected before the command."""
    world = _world(app, keyring, clock, runtime)

    def mutating(w: World) -> HttpResponse:
        e = _engine(w)
        body = {"code": f"C-MUT-{random_suffix()}", "name": "Mutation witness (SOP-7 walk)"}
        created = post(e.app, f"{API}/customers", e.place.author, body)
        assert created.status_code == 201, created.text
        return s_explain_verify(w)

    walk = Walk()
    _exercise(world, walk, "explain_verify", mutating)
    named = [
        failure
        for failure in walk.failures
        if failure.startswith("explain_verify: a query operation changed rows of")
    ]
    assert named and "customer" in named[0], walk.failures


def test_refused_check_names_each_kind_of_miss() -> None:
    """Discriminating witness of SOP-7 class (e), CPU (BUILD_SPEC fragment 11 rev 1.44; item
    POLICY-OVERRIDE-WITHDRAW-1): a command the release refuses by name passes the walk only by its
    refusal. A success, another status, another rule id, a second error, an audit row and a
    changed table are each named; the refusal that stores nothing is not."""
    rule = ROUTES["policy_overrides_create"].rule_ids
    assert rule == ("POLICY_OVERRIDE_NOT_OFFERED",)
    op = "policy_overrides_create"
    assert _refused_failures(op, rule, 422, list(rule), 0, []) == []
    # The command as it was until 04 rev 1.322: a DRAFT stored, 201.
    assert _refused_failures(op, rule, 201, [], 1, ["policy_override"]) == [
        f"{op}: a command the release refuses by name answered HTTP 201 with rule ids [], not 422 "
        "with ['POLICY_OVERRIDE_NOT_OFFERED']",
        f"{op}: a refused command wrote 1 audit_event row(s)",
        f"{op}: a refused command changed rows of ['policy_override']",
    ]
    # Another refusal is not this one: the level rule of before, a 404, a 403, two errors.
    for status, rule_ids in (
        (422, ["POLICY_LEVEL_NOT_ALLOWED"]),
        (422, ["POLICY_OVERRIDE_NOT_OFFERED", "POLICY_VALUE_INVALID"]),
        (422, []),
        (404, []),
        (403, [None]),
        (409, ["POLICY_OVERRIDE_NOT_OFFERED"]),
    ):
        (named,) = _refused_failures(op, rule, status, rule_ids, 0, [])
        assert named.startswith(f"{op}: a command the release refuses by name answered HTTP")
    # The right answer with something left behind is a failure all the same.
    assert _refused_failures(op, rule, 422, list(rule), 2, []) == [
        f"{op}: a refused command wrote 2 audit_event row(s)"
    ]
    assert _refused_failures(op, rule, 422, list(rule), 0, ["approval_request"]) == [
        f"{op}: a refused command changed rows of ['approval_request']"
    ]


def test_refused_check_fails_on_a_stored_row_and_on_a_success(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Discriminating witness of SOP-7 class (e), DB-bound. The walk's own scenario passes: the
    creation answers its refusal in the K-02 world, writes no audit event and changes no table.
    The same refusal with a row written beside it in the request tenant fails by name — the
    baseline is read before the scenario, in the tenant the request runs in — and so does a
    scenario that answers a success."""
    world = _world(app, keyring, clock, runtime)
    op = "policy_overrides_create"

    clean = Walk()
    _exercise(world, clean, op, s_policy_overrides_create)
    assert clean.failures == [] and op in clean.covered
    stored = select(func.count()).select_from(tables.policy_override)
    with tenant_session(_db(_engine(world).place.tenant_id), read_only=True) as session:
        assert session.execute(stored).scalar_one() == 0

    def storing(w: World) -> HttpResponse:
        e = _engine(w)
        body = {"code": f"C-MUT-{random_suffix()}", "name": "Mutation witness (SOP-7 walk)"}
        created = post(e.app, f"{API}/customers", e.place.author, body)
        assert created.status_code == 201, created.text
        return s_policy_overrides_create(w)

    beside = Walk()
    _exercise(world, beside, op, storing)
    # The customer and the audit event of ITS creation: the refusal itself wrote neither.
    assert beside.failures == [
        f"{op}: a refused command changed rows of ['audit_event', 'customer']"
    ]

    def succeeding(w: World) -> HttpResponse:
        e = _engine(w)
        body = {"code": f"C-OK-{random_suffix()}", "name": "Success witness (SOP-7 walk)"}
        return post(e.app, f"{API}/customers", e.place.author, body)

    success = Walk()
    _exercise(world, success, op, succeeding)
    assert success.failures == [
        f"{op}: a command the release refuses by name answered HTTP 201 with rule ids [], not "
        "422 with ['POLICY_OVERRIDE_NOT_OFFERED']",
        f"{op}: a refused command wrote 1 audit_event row(s)",
        f"{op}: a refused command changed rows of ['audit_event', 'customer']",
    ]
