"""SAR-42 IDOR: another tenant's and another entity's ids answer 404 (04 §1.4 RLS templates,
API-C-05; 05 SAR-11; BUILD_SPEC SOP-8).

``test_sar_42_get_by_id_routes_inventory`` runs on the CPU over the committed OpenAPI document and
pins the sweep list the database tests walk; ``test_sar_42_route_table_map_is_complete`` pins the
table each route reads. The spec-named ``test_sar_42_other_tenant_and_entity_ids_not_found``
probes every route with a REAL row of the other tenant (one row per table, inserted as the other
tenant), with the caller's own row of the same table as the authorized 200 control, and
``test_sar_42_entity_excluded_ids_not_found`` does the same for rows of the caller's tenant in an
entity outside the caller's scope (Codex production-20260921-2353 P8-SOP8-IDOR-1). Both need the
test database."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import metadata
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.rows import (
    PROVISIONED_TABLES,
    ROW_BUILDERS,
    ROW_COMPLETERS,
    RowContext,
    approval_request_values,
    approval_step_values,
    close_run_values,
    contract_event_values,
    event_submission_values,
    exception_item_values,
    insert_app_user,
    insert_journal_rows,
    insert_obligation_rows,
    insert_role_assignment,
    insert_version_rows,
    manual_adjustment_values,
    modification_values,
    obligation_version_values,
    publish_registry_version,
    reconciliation_values,
)

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "docs" / "api" / "openapi.json"
PROBLEM_BASE = "https://erev.dev/problems/"
_ID_ROUTE: Final = re.compile(r"^/api/v1/([a-z-]+)/\{([a-z_]+)\}$")


def get_by_id_routes() -> tuple[tuple[str, str], ...]:
    """Every ``GET /api/v1/{resource}/{id}`` operation of the committed document: (path, param)."""
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    routes: list[tuple[str, str]] = []
    for path, operations in sorted(document["paths"].items()):
        match = _ID_ROUTE.match(path)
        if match is not None and "get" in operations:
            routes.append((path, match.group(2)))
    return tuple(routes)


def test_sar_42_get_by_id_routes_inventory() -> None:
    """The sweep list is not empty, every route declares 404 ``not-found``, and its size is pinned
    so that a new resource route joins the sweep knowingly."""
    routes = get_by_id_routes()
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    # 42 + GET /modifications/{id} (CTR-17) + GET /integrations/{id} and GET /sync-runs/{id}
    # (DIN-12; 04 §15.3 API-R-45) + GET /reconciliations/{id} (CLO-16; 04 §15.3 API-R-40)
    # + GET /close-runs/{id} (CLO-19; 04 §15.3 API-R-39)
    # + GET /manual-adjustments/{id} (CLO-12; 04 §15.3 API-R-37).
    assert len(routes) == 48, [path for path, _ in routes]
    for path, _ in routes:
        responses = document["paths"][path]["get"]["responses"]
        assert "404" in responses, f"{path} declares no 404"
    assert ("/api/v1/users/{membership_id}", "membership_id") in routes
    assert ("/api/v1/files/{file_id}", "file_id") in routes


# The tenant table each ``GET /{resource}/{id}`` route reads, so the sweep can insert a REAL row of
# the other tenant for it (Codex P8-SOP8-IDOR-1). ``report-definitions`` is the global catalogue
# (no tenant row exists; its foreign probe is an unknown code and its control a real code).
ROUTE_TABLES: Final[Mapping[str, str | None]] = {
    "access-reviews": "access_review_campaign",
    "account-mappings": "account_mapping_version",
    "api-clients": "api_client",
    "approvals": "approval_request",
    "calc-traces": "calc_trace",
    "close-runs": "close_run",  # T-CLS-01 (CLO-19, API-R-39)
    "combination-groups": "combination_group",
    "contracts": "contract",
    "customers": "customer",
    "entities": "legal_entity",
    "estimate-versions": "estimate_version",
    "event-submissions": "event_submission",
    "events": "contract_event",
    "exceptions": "exception_item",
    "files": "file_object",
    "fx-rate-set-versions": "fx_rate_set_version",
    "gl-accounts": "gl_account",
    "import-mapping-profiles": "import_mapping_profile",
    "imports": "import_upload",
    "integrations": "integration_connection",  # T-INT-01 (DIN-12, API-R-45)
    "jobs": "job",
    "journal-batches": "journal_batch",
    "journal-runs": "journal_run",
    "judgements": "judgement_record",
    "manual-adjustments": "manual_adjustment",  # T-SL-05 (CLO-12, API-R-37)
    "migrations": "migration_batch",
    "modifications": "modification",  # T-CON-06 (F-CTR CTR-17, main 0959b560)
    "obligations": "obligation",
    "periods": "period_state",  # API-S-Period: "`id` is `period_state.id`" (04 §16.8)
    "pob-template-versions": "pob_template_version",
    "pob-templates": "pob_template",
    "policies": "registry_version",
    "policy-overrides": "policy_override",
    "products": "product",
    "reconciliations": "reconciliation",  # T-CLS-06 (CLO-16, API-R-40)
    "report-definitions": None,
    "report-runs": "report_run",
    "roles": "role",
    "rule-set-versions": "rule_set_version",
    "rule-sets": "rule_set",
    "source-records": "source_record",
    "ssp-book-versions": "ssp_book_version",
    "ssp-books": "ssp_book",
    "ssp-calculator-runs": "ssp_calculator_run",
    "subledger-postings": "subledger_posting",
    "sync-runs": "sync_run",  # T-INT-02 (DIN-12, API-R-45)
    "users": "tenant_membership",
    "webhook-endpoints": "webhook_endpoint",
}
REPORT_CODE_CONTROL: Final = "revenue_waterfall"  # a code of the global catalogue
REPORT_CODE_FOREIGN: Final = "no_such_report"
# The roles the sweeping caller holds together, so every read route is permissioned and a 404 can
# only be the tenancy or the entity scope (T-PLT-11 keeps the Tenant Admin off transactions; the
# reads the sweep needs come from the Controller and Auditor grants, except ``integration.manage``
# of the API-R-45 reads, the Integration Admin's alone, and ``migration.run`` of the API-R-48
# reads, the Revenue Accountant's alone). A guard refusal would answer 403 before any lookup.
SWEEP_ROLES: Final = (
    "tenant_admin",
    "controller",
    "auditor",
    "integration_admin",
    "revenue_accountant",
)


def resource_of(path: str) -> str:
    return path.split("/")[3]


def test_sar_42_route_table_map_is_complete() -> None:
    """Every swept route names the tenant table it reads (or is marked global), every named table
    has a row builder, and nothing in the map is stale."""
    resources = {resource_of(path) for path, _ in get_by_id_routes()}
    assert set(ROUTE_TABLES) == resources, sorted(set(ROUTE_TABLES) ^ resources)
    for resource, table_name in ROUTE_TABLES.items():
        if table_name is not None:
            assert table_name in ROW_BUILDERS, (resource, table_name)
    assert ROUTE_TABLES["report-definitions"] is None


# ---- the sweep against two tenants (needs the test database)


@dataclass(frozen=True, slots=True)
class Tenants:
    alpha: Actor  # the caller's tenant
    beta: Actor  # the other tenant, whose ids must answer 404 to alpha


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _admin(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    code: str,
    name: str,
    *,
    roles: tuple[str, ...] = SWEEP_ROLES,
    entity_ids: tuple[UUID, ...] = (),
) -> Actor:
    someone = member(keyring, clock, code=code, name=name)
    with tenant_session(_context(someone.tenant_id)) as session:
        for role_code in roles:
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=role_code,
                entity_ids=entity_ids,
            )
    return enrolled(app, clock, someone)


@pytest.fixture
def tenants(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Tenants:
    # A fresh pair per test: the database tests commit for real (DG-TST-13), so a fixed tenant code
    # would collide on ``ux_tenant__code`` in the second test of a session.
    suffix = secrets.token_hex(4)
    return Tenants(
        alpha=_admin(app, keyring, clock, f"alpha-idor-{suffix}", "tomas"),
        beta=_admin(app, keyring, clock, f"beta-idor-{suffix}", "bea"),
    )


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


@dataclass(frozen=True, slots=True)
class Computed:
    """A legitimately computed contract of one entity: chain, version 1 in the primary book with
    its calc trace, and one obligation with its obligation version — the rows ``obligation_out``
    and the contract reads require (Codex P8-SOP8-IDOR-1 residual: ``obligation_row`` alone has
    no versions and answers 404 ``NO_VERSION``)."""

    entity_id: UUID
    contract_id: UUID
    obligation_id: UUID
    group_id: UUID
    customer_id: UUID


def seed_computed(session: Session, tenant_id: UUID, *, entity_id: UUID | None = None) -> Computed:
    # DB-17 checks at commit that the obligation versions allocate the version's transaction price:
    # the one obligation version below allocates 100 (``obligation_version_values``).
    rows = insert_version_rows(
        session, tenant_id, transaction_price=Decimal("100"), entity_id=entity_id
    )
    parts = insert_obligation_rows(session, tenant_id, rows)
    version = obligation_version_values(
        tenant_id,
        contract_version_id=rows.version_id,
        obligation_id=parts["obligation_id"],
        contract_id=rows.chain.contract_id,
        combination_group_id=rows.chain.group_id,
        product_id=parts["product_id"],
        pob_template_version_id=parts["pob_template_version_id"],
        entity_id=rows.chain.entity_id,
    )
    session.execute(insert(metadata.tables["erev.obligation_version"]).values(**version))
    return Computed(
        entity_id=rows.chain.entity_id,
        contract_id=rows.chain.contract_id,
        obligation_id=parts["obligation_id"],
        group_id=rows.chain.group_id,
        customer_id=rows.chain.customer_id,
    )


COMPUTED_RESOURCES: Final = ("contracts", "obligations")


def route_request(session: Session, tenant_id: UUID, request_id: UUID) -> None:
    """The ACTIVE first step of an approval request. A request is readable by its preparer, its
    deciders and the holders of the permission of one of its steps for its entity (04 §15.3
    API-R-09: "any approval permission of the active step"; ``approval_queries.visible``); the
    probe rows are system-prepared and undecided, so without a step nobody could read them and the
    authorized control could not be a 200. The step asks for ``access.approve``, which the sweeping
    caller holds as Tenant Admin."""
    step = approval_step_values(tenant_id, approval_request_id=request_id)
    session.execute(insert(metadata.tables["erev.approval_step"]).values(**step))


def attach_file(session: Session, ctx: RowContext, file_id: UUID, contract_id: UUID) -> None:
    """The probe file attached to the tenant's contract. A stored file is read through a record
    that owns it (04 T-PLT-29 "Read access"; supervisor ruling R-48 (c)) — it was read through
    ``audit.read``, which opens audit artefacts only — so without an owner nobody could read the
    probe file and the authorized control could not be a 200. The sweeping caller reads the
    contract (``contract.read``)."""
    link = {
        **ROW_BUILDERS["file_attachment"](ctx, session),
        "file_object_id": file_id,
        "subject_type": "contract",
        "subject_id": contract_id,
    }
    session.execute(insert(metadata.tables["erev.file_attachment"]).values(**link))


def seed_rows(tenant_id: UUID) -> dict[str, UUID]:
    """One REAL row per mapped table, inserted as ``erev_app`` under the tenant's own context
    through the catalogue-complete ``ROW_BUILDERS`` (the rows the RLS suite proves invisible across
    tenants) — except the contract and the obligation, which come from a computed chain so that the
    version-reading routes answer 200 for the own row; returns resource → the id the route reads."""
    with identity_session(request_id="tests-idor-user") as session:
        user_id = insert_app_user(session)
    ids: dict[str, UUID] = {}
    with tenant_session(_context(tenant_id)) as session:
        computed = seed_computed(session, tenant_id)
        ids["contracts"], ids["obligations"] = computed.contract_id, computed.obligation_id
        for resource, table_name in ROUTE_TABLES.items():
            if table_name is None or resource in COMPUTED_RESOURCES:
                continue
            table = metadata.tables[f"erev.{table_name}"]
            ctx = RowContext(tenant_id, user_id)
            row = ROW_BUILDERS[table_name](ctx, session)
            if table_name not in PROVISIONED_TABLES:
                session.execute(insert(table).values(**row))
                complete = ROW_COMPLETERS.get(table_name)
                if complete is not None:
                    complete(ctx, session, row)
                if table_name == "approval_request":
                    route_request(session, tenant_id, UUID(str(row["id"])))
                if table_name == "file_object":
                    attach_file(session, ctx, UUID(str(row["id"])), ids["contracts"])
            ids[resource] = UUID(str(row["id"]))
    return ids


def visible_count(tenant_id: UUID, table_name: str, row_id: UUID) -> int:
    table = metadata.tables[f"erev.{table_name}"]
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return len(list(session.scalars(select(table.c.id).where(table.c.id == row_id))))


def get(app: FastAPI, actor: Actor, path: str) -> HttpResponse:
    return call(app, "GET", path, headers=cookie_headers(actor.token, key=False))


def assert_not_found(response: HttpResponse, path: str, *leaked: object) -> None:
    assert response.status_code == 404, (path, response.status_code, response.text[:200])
    assert slug(response) == "not-found", path
    body = json.dumps(response.json())
    for value in leaked:
        assert str(value) not in body, (path, value)


def test_sar_42_other_tenant_and_entity_ids_not_found(app: FastAPI, tenants: Tenants) -> None:
    """For every ``GET /{resource}/{id}`` route of the OpenAPI document, the id of a REAL row of
    tenant beta (inserted as beta, visible to beta) returns 404 ``not-found`` to the sweeping
    caller of tenant alpha — never 403, never a body of beta's — while the same route answers 200
    for alpha's own row of the same table (the authorized control), so a 404 can only be the
    tenancy. The global report catalogue is probed with an unknown code and a real one."""
    alpha, beta = tenants.alpha, tenants.beta
    foreign = seed_rows(beta.member.tenant_id)
    own = seed_rows(alpha.member.tenant_id)
    foreign["users"], own["users"] = beta.member.membership_id, alpha.member.membership_id
    for resource, table_name in ROUTE_TABLES.items():
        if table_name is not None:
            assert visible_count(beta.member.tenant_id, table_name, foreign[resource]) == 1, (
                f"{resource}: the foreign row really exists in beta"
            )
    for path, param in get_by_id_routes():
        resource = resource_of(path)
        if ROUTE_TABLES[resource] is None:
            probe, control = REPORT_CODE_FOREIGN, REPORT_CODE_CONTROL
        else:
            probe, control = str(foreign[resource]), str(own[resource])
        response = get(app, alpha, path.replace("{" + param + "}", probe))
        assert_not_found(response, path, beta.member.tenant_id, probe)
        allowed = get(app, alpha, path.replace("{" + param + "}", control))
        assert allowed.status_code == 200, (path, allowed.status_code, allowed.text[:200])
    # A nonexistent id is 404 too, and indistinguishable from a foreign one (no oracle).
    ghost = get(app, alpha, f"/api/v1/users/{uuid4()}")
    assert_not_found(ghost, "/api/v1/users/{membership_id}")


# Resources of the entity-exclusion sweep whose row names its entity itself (no owner to resolve).
ENTITY_OWNED: Final = ("exceptions", "manual-adjustments", "modifications", "policies")


def assert_import_reads_are_entity_scoped(
    app: FastAPI, scoped: Actor, unscoped: Actor, *, inside: UUID, outside: UUID
) -> None:
    """Import uploads are tenant-level rows (RLS-T) read through the entities their rows name
    (security finding SC-3, ruling R-28; 04 rev 1.107 T-IMP-02 ``named_entity_ids``, API-R-43):
    ``GET /imports/{id}`` and the reads below it answer 404 ``not-found`` to a caller whose
    ``contract.read`` scope does not cover them, and the list leaves the upload out — while the
    in-scope upload answers (UPLOADED: rows and error report 200, no diff yet 409) and the
    unscoped caller of the same tenant reads both."""
    from erev_api.enums import FilePurpose
    from support.rows import file_object_values, import_upload_values

    tenant_id = scoped.member.tenant_id
    uploads: dict[UUID, UUID] = {}
    with tenant_session(_context(tenant_id)) as session:
        for entity_id in (inside, outside):
            source = file_object_values(tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
            session.execute(insert(metadata.tables["erev.file_object"]).values(**source))
            upload = import_upload_values(
                tenant_id, file_object_id=UUID(str(source["id"])), named_entity_ids=[entity_id]
            )
            session.execute(insert(metadata.tables["erev.import_upload"]).values(**upload))
            uploads[entity_id] = UUID(str(upload["id"]))
    path = "/api/v1/imports/{}"
    for suffix, visible in (("", 200), ("/rows", 200), ("/error-report", 200), ("/diff", 409)):
        hidden = get(app, scoped, path.format(uploads[outside]) + suffix)
        assert_not_found(hidden, path + suffix, outside, uploads[outside])
        shown = get(app, scoped, path.format(uploads[inside]) + suffix)
        assert shown.status_code == visible, (suffix, shown.status_code, shown.text[:200])
        for upload_id in uploads.values():
            both = get(app, unscoped, path.format(upload_id) + suffix)
            assert both.status_code == visible, (suffix, both.status_code, both.text[:200])
    listed = get(app, scoped, "/api/v1/imports")
    assert listed.status_code == 200, listed.text[:200]
    listed_ids = {item["id"] for item in listed.json()["items"]}
    assert str(uploads[inside]) in listed_ids and str(uploads[outside]) not in listed_ids


def assert_rows_without_an_entity_are_for_all_entities(
    app: FastAPI, scoped: Actor, unscoped: Actor
) -> None:
    """A job and a source record carry no entity (RLS-T) and may hold the data of any: a caller
    reads a job it started and a source record through a contract in its reach, and either of
    them at large only with the guarding permission for ALL entities (ruling R-28; item
    SCOPE-WORKSPACE-LISTS-1; 04 API-C-03 rev 1.219, API-R-11, API-R-56). A job the system started
    and a source record no contract names answer the scoped caller 404 ``not-found`` and the
    unscoped caller of the same tenant 200."""
    from support.rows import job_row, source_record_values

    tenant_id = scoped.member.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        started = job_row(RowContext(tenant_id, scoped.member.user_id), session)
        session.execute(insert(metadata.tables["erev.job"]).values(**started))
        record = source_record_values(tenant_id)
        session.execute(insert(metadata.tables["erev.source_record"]).values(**record))
    for path, row_id in (
        ("/api/v1/jobs/{}", started["id"]),
        ("/api/v1/source-records/{}", record["id"]),
    ):
        assert_not_found(get(app, scoped, path.format(row_id)), path, row_id)
        shown = get(app, unscoped, path.format(row_id))
        assert shown.status_code == 200, (path, shown.status_code, shown.text[:200])


def test_sar_42_entity_excluded_ids_not_found(
    app: FastAPI, tenants: Tenants, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Rows of the caller's OWN tenant in an entity outside the caller's scope answer 404
    ``not-found`` on every entity-scoped route (RLS-TE; API-C-03), while the same routes answer
    200 for rows of an entity in scope: entities, contracts, computed obligations, events, event
    submissions, approval requests, journal runs, journal batches, period states, exception
    items, modifications, manual adjustments (T-SL-05; CLO-12), reconciliations, close runs and
    ENTITY-scope policy versions (Codex P8-SOP8-IDOR-1 residual: the obligation cases use computed
    versions in and out of scope). ``GET /periods/{id}`` reads
    ``period_state`` (API-S-Period: "`id` is `period_state.id`", 04 §16.8), an RLS-TE table: the
    probed row is the January state of the journal entity. These are all the get-by-id routes whose
    own table carries the RLS-TE entity policy (``pl_<table>__entity``; ruling R-28). Two rows
    without an entity follow them — a job the caller did not start and a source record no
    contract names (``assert_rows_without_an_entity_are_for_all_entities``)."""
    tenant_id = tenants.alpha.member.tenant_id
    e_in, e_out, j_in, j_out = new_id(), new_id(), new_id(), new_id()
    ids: dict[str, dict[str, UUID]] = {}
    with tenant_session(_context(tenant_id)) as session:
        for label, entity_id, journal_entity in (("in", e_in, j_in), ("out", e_out, j_out)):
            chain = seed_computed(session, tenant_id, entity_id=entity_id)
            # DB-08: an event's version is at most the contract's head and follows its predecessor
            # (``seed_computed`` left the head at 1 with the first event), so the head rises first.
            contracts = metadata.tables["erev.contract"]
            session.execute(
                update(contracts)
                .where(contracts.c.id == chain.contract_id)
                .values(head_stream_version=2, row_version=contracts.c.row_version + 1)
            )
            event = contract_event_values(
                tenant_id,
                contract_id=chain.contract_id,
                contracting_entity_id=chain.entity_id,
                stream_version=2,
            )
            session.execute(insert(metadata.tables["erev.contract_event"]).values(**event))
            submission = event_submission_values(
                tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
            )
            session.execute(insert(metadata.tables["erev.event_submission"]).values(**submission))
            request = approval_request_values(tenant_id, entity_id=chain.entity_id)
            session.execute(insert(metadata.tables["erev.approval_request"]).values(**request))
            route_request(session, tenant_id, UUID(str(request["id"])))
            journals = insert_journal_rows(session, tenant_id, entity_id=journal_entity)
            states = metadata.tables["erev.period_state"]
            period_state_id = session.execute(
                select(states.c.id).where(
                    states.c.entity_id == journal_entity,
                    states.c.period_id == journals.parts.period_id,
                )
            ).scalar_one()
            item = exception_item_values(tenant_id, entity_id=chain.entity_id)
            session.execute(insert(metadata.tables["erev.exception_item"]).values(**item))
            # T-CLS-06 (RLS-TE; CLO-16): a reconciliation of the journal entity's January.
            reconciled = reconciliation_values(
                tenant_id, entity_id=journal_entity, period_id=journals.parts.period_id
            )
            session.execute(insert(metadata.tables["erev.reconciliation"]).values(**reconciled))
            # T-CLS-01 (RLS-TE; CLO-19): a close run of the journal entity's January.
            closing = close_run_values(
                tenant_id, entity_id=journal_entity, period_id=journals.parts.period_id
            )
            session.execute(insert(metadata.tables["erev.close_run"]).values(**closing))
            change = modification_values(
                tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
            )
            session.execute(insert(metadata.tables["erev.modification"]).values(**change))
            # T-SL-05 (RLS-TE; CLO-12): a draft adjustment of the chain's contract and entity.
            adjustment = manual_adjustment_values(
                tenant_id,
                contract_id=chain.contract_id,
                entity_id=chain.entity_id,
                period_id=journals.parts.period_id,
            )
            session.execute(insert(metadata.tables["erev.manual_adjustment"]).values(**adjustment))
            policy_id = publish_registry_version(
                session,
                tenant_id=tenant_id,
                category=RegistryCategory.ACCOUNTING_POLICY,
                scope=RegistryScope.ENTITY,
                entity_id=chain.entity_id,
                values={"rpo.time_bands": [24]},
                at=clock.now(),
            )
            ids[label] = {
                "entities": chain.entity_id,
                "contracts": chain.contract_id,
                "obligations": chain.obligation_id,
                "events": UUID(str(event["id"])),
                "event-submissions": UUID(str(submission["id"])),
                "approvals": UUID(str(request["id"])),
                "journal-runs": UUID(str(journals.run["id"])),
                "journal-batches": UUID(str(journals.batch["id"])),
                "periods": UUID(str(period_state_id)),
                "exceptions": UUID(str(item["id"])),
                "reconciliations": UUID(str(reconciled["id"])),
                "close-runs": UUID(str(closing["id"])),
                "modifications": UUID(str(change["id"])),
                "manual-adjustments": UUID(str(adjustment["id"])),
                "policies": policy_id,
            }
    scoped_member = colleague(tenant_id, "erin")
    with tenant_session(_context(tenant_id)) as session:
        for role_code in SWEEP_ROLES:
            insert_role_assignment(
                session,
                tenant_id=tenant_id,
                membership_id=scoped_member.membership_id,
                role_code=role_code,
                entity_ids=(e_in, j_in),
            )
    erin = enrolled(app, clock, scoped_member)
    routes = {resource_of(path): (path, param) for path, param in get_by_id_routes()}
    for resource, outside in ids["out"].items():
        path, param = routes[resource]
        response = get(app, erin, path.replace("{" + param + "}", str(outside)))
        assert_not_found(response, path, e_out, j_out, outside)
        allowed = get(app, erin, path.replace("{" + param + "}", str(ids["in"][resource])))
        assert allowed.status_code == 200, (path, allowed.status_code, allowed.text[:200])
    assert_import_reads_are_entity_scoped(
        app, erin, tenants.alpha, inside=ids["in"]["entities"], outside=ids["out"]["entities"]
    )
    assert_rows_without_an_entity_are_for_all_entities(app, erin, tenants.alpha)
    # The unscoped caller of the same tenant reads both (the exclusion is the scope, not the row).
    for resource in ("contracts", "obligations", "periods", *ENTITY_OWNED):
        path, param = routes[resource]
        for label in ("in", "out"):
            both = get(
                app, tenants.alpha, path.replace("{" + param + "}", str(ids[label][resource]))
            )
            assert both.status_code == 200, (resource, label, both.text[:200])
