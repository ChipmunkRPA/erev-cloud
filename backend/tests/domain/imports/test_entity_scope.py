"""Imports stay inside the uploader's entity scope, and the import reads inside the reader's
(security findings SC-2 and SC-3, imports part; supervisor rulings R-28, R-29, R-41 (5); 04 rev
1.107 T-IMP-02 ``named_entity_ids``, table 15.4-B ``IMPORT_ENTITY_NOT_AVAILABLE``, API-R-43; 05
rev 1.46 IPL-05, IPL-07, IPL-08, IPL-10; 03 REQ-PLT-012). R-41 (5)'s clause on performing and
selling entities is replaced by ruling R-114 (g) (04 T-IMP-02 rev 1.256; 05 IPL-08 rev 1.186):
one set, the contracting entities — a line's performing entity must exist and need not be
covered, in the row's finding, in the uploader's cover and in the stored set alike.

The reviewer's proof (``sec-close/test_poc_imports_scope.py``) inverted: every step asserts the
REFUSAL, next to a positive control in which the same act succeeds for a person whose role covers
the entity — so a refusal can only be the scope.

World ``support.factories.j03_world``: AVM-US and AVM-UK; Maya prepares for every entity. Eve is a
Revenue Accountant and Rhea a Revenue Reviewer, each for AVM-UK only. The legacy v1 case runs in
``support.legacy_replay.legacy_world`` (Mock Entity 1 and 2), where Lena is a Revenue Accountant
for Mock Entity 1 only. Jobs run as the worker runs them (``run_import_job``).

The ``test_r98_`` tests are the residuals of the independent review of merge 4ac6c1d1 (supervisor
rulings R-98 and R-109; 04 rev 1.147; 05 rev 1.86): exact keys and the write-permission scope
(2), the unresolved set (2), the scope findings before the rules that read stored state (6), 404
for submit and cancel outside the read scope (8), whole contracts in quarantine mode (10), an API
client's upload held to what its token carried, and the templates and reads the review found
without a database scope test.
"""

from __future__ import annotations

import csv
import hashlib
import io
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals.engine import EVERY_ENTITY_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import effective_grants
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    api_token,
    approval_request,
    audit_event,
    contract,
    contract_event,
    exception_item,
    gl_account,
    import_row,
    import_upload,
    job,
    legal_entity,
    notification,
    obligation_version,
)
from erev_api.domain.imports import csv_v2, scope
from erev_api.domain.imports.exceptions import OWNER_CANNOT_READ
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support import upload_fixtures
from support.db import TestDatabase
from support.factories import (
    IMPORT_ID_HEADER,
    IMPORTS_PATH,
    PLATFORM_100,
    ImportWorld,
    J03World,
    create_import,
    imported,
    j03_world,
    run_import_job,
    sf_ord_20417_body,
    tenant_factory,
    tenant_id_of,
    upload_import_source,
    workbook_bytes,
)
from support.http import call
from support.legacy_replay import (
    SETUP_2023,
    SKU_SSP,
    LegacyWorld,
    committed,
    legacy_world,
    replayed,
    workbook_rows,
)
from support.principals import Actor, colleague, cookie_headers, enrolled
from support.reference import APPROVALS, approve, assign, fields, get, holding, post, slug
from support.rows import (
    api_client_values,
    insert_active_membership,
    insert_role_assignment,
    publish_registry_version,
    revoke_role_assignments,
)
from tests.domain.imports.csv_v2.test_ssp_values_declarations import HEADERS as SSP_HEADERS
from tests.domain.imports.csv_v2.test_ssp_values_declarations import _book as _ssp_book
from tests.domain.imports.csv_v2.test_ssp_values_declarations import _row as _ssp_row

CONTRACTS = "/api/v1/contracts"
CODE = "IMPORT_ENTITY_NOT_AVAILABLE"
CONTRACT_HEADERS = (
    "external_id",
    "customer_id",
    "contracting_entity_code",
    "transaction_currency",
    "inception_date",
    "document_ref",
    "lines.obligation_key",
    "lines.product_code",
    "lines.quantity",
    "lines.total_price.amount",
    "lines.total_price.currency",
    "lines.start_date",
    "lines.end_date",
    "lines.performing_entity_code",
)
COST_HEADERS = (
    "contract",
    "effective_date",
    "purpose",
    "amount.amount",
    "amount.currency",
    "plan_code",
)
CUSTOMER_HEADERS = ("code", "name", "segment", "country_code")


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def contracts_csv(
    customer_id: UUID,
    *,
    external_id: str,
    contracting: str = "AVM-US",
    performing: str = "AVM-UK",
    implementation: str = "24000.00",
) -> bytes:
    """PRD WLD-F-20 as a CSV v2 ``contracts`` file: O1 AVM-PLAT-100 96,000.00 and O2 AVM-IMPL-PLUS
    performed by ``performing``, contracted by ``contracting``."""
    header = [external_id, str(customer_id), contracting, "USD", "2026-09-01", external_id]
    return csv_bytes(
        CONTRACT_HEADERS,
        [
            [*header, "O1", "AVM-PLAT-100", "1", "96000.00", "USD", "2026-09-01", "2027-08-31", ""],
            [*header, "O2", "AVM-IMPL-PLUS", "1", implementation, "USD", "", "", performing],
        ],
    )


def cost_events_csv(contract_key: str) -> bytes:
    return csv_bytes(
        COST_HEADERS,
        [[contract_key, "2026-09-05", "COST_TO_OBTAIN", "5760.00", "USD", "SALES-2026"]],
    )


@dataclass(frozen=True, slots=True)
class Cast:
    world: J03World
    maya: ImportWorld  # every entity
    eve: ImportWorld  # Revenue Accountant, AVM-UK only
    rhea: Actor  # Revenue Reviewer, AVM-UK only

    @property
    def app(self) -> FastAPI:
        return self.world.app

    def all_entities(self) -> DbContext:
        return DbContext(tenant_id=self.maya.tenant_id, user_id=None, entity_scope="*")


def job_ids(world: ImportWorld, import_id: str, kind: str) -> list[UUID]:
    rows = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == UUID(import_id), job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    return [UUID(str(row["id"])) for row in rows]


def findings_of(world: ImportWorld, import_id: str) -> list[dict[str, Any]]:
    """The exception items of an upload's rows, in row order (read without an entity filter)."""
    return world.rows(
        select(exception_item.c.code, exception_item.c.message, import_row.c.row_number)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )


def named(world: ImportWorld, import_id: str) -> list[UUID] | None:
    value = world.scalar(
        select(import_upload.c.named_entity_ids).where(import_upload.c.id == UUID(import_id))
    )
    return None if value is None else sorted((UUID(str(item)) for item in value), key=str)


def diffed(world: ImportWorld, name: str, content: bytes, template_code: str) -> str:
    import_id, validated = imported(world, name, content, template_code)
    assert validated["status"] == "VALIDATED", validated
    (diff_job,) = job_ids(world, import_id, "IMPORT_DIFF")
    run_import_job(world, diff_job)
    ready = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor).json()
    assert ready["status"] == "DIFF_READY", ready
    return import_id


def submit(world: ImportWorld, import_id: str) -> Any:
    return post(
        world.app, f"{IMPORTS_PATH}/{import_id}/submit", world.actor, {"comment": "new order"}
    )


def status_of(world: ImportWorld, import_id: str) -> str:
    return str(
        world.scalar(select(import_upload.c.status).where(import_upload.c.id == UUID(import_id)))
    )


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def cast(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Cast:
    world = j03_world(app, keyring, clock, files)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    tenant_id = world.place.tenant_id
    eve = holding(
        app, colleague(tenant_id, "eve"), "revenue_accountant", entity_ids=[world.uk_entity_id]
    )
    rhea_member = colleague(tenant_id, "rhea")
    assign(rhea_member, "revenue_reviewer", entity_ids=[world.uk_entity_id])
    return Cast(
        world=world,
        maya=ImportWorld(app=app, actor=world.place.author, runtime=runtime, clock=clock),
        eve=ImportWorld(app=app, actor=eve, runtime=runtime, clock=clock),
        rhea=enrolled(app, clock, rhea_member),
    )


def test_sc2_a_row_naming_an_entity_outside_the_uploaders_scope_fails_validation(
    cast: Cast,
) -> None:
    """R-29; 04 table 15.4-B: Eve's file books a NEW contract for AVM-US, which her role does not
    cover — the upload is INVALID by name, nothing is diffed, submitted or written; the same file
    of Maya's validates and diffs, and Eve's file for her own entity validates."""
    world = cast.world
    us, uk = world.entity_id, world.uk_entity_id
    # The direct command is refused for Eve too (RLS-TE hides AVM-US from her).
    direct = post(
        cast.app, CONTRACTS, cast.eve.actor, sf_ord_20417_body(world.customer_id, external_id="D1")
    )
    assert direct.status_code == 422, direct.text

    import_id, shown = imported(
        cast.eve,
        "eve-new.csv",
        contracts_csv(world.customer_id, external_id="EVE-US-0001"),
        "contracts",
    )
    assert shown["status"] == "INVALID", shown
    found = findings_of(cast.maya, import_id)
    assert [(item["code"], item["row_number"]) for item in found] == [(CODE, 2), (CODE, 3)]
    for item in found:
        assert (
            "Legal entity AVM-US is not available for this import. "
            "Upload these rows under a role that covers the entity."
        ) in item["message"], item
    # 04 T-IMP-02 (rev 1.256): the entities the data rows WRITE for are stored, whoever
    # uploaded — the contracting entity. AVM-UK performs the second line and is none of them.
    assert named(cast.maya, import_id) == [us]
    with tenant_session(cast.all_entities(), read_only=True) as session:
        assert scope.named_entity_ids(session, UUID(import_id)) == frozenset({us})
        with pytest.raises(LookupError):
            scope.named_entity_ids(session, uuid4())
    # Nothing follows: no dry run, no submission, no contract.
    assert job_ids(cast.maya, import_id, "IMPORT_DIFF") == []
    refused = submit(cast.eve, import_id)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert (
        cast.maya.rows(select(contract.c.id).where(contract.c.external_id == "EVE-US-0001")) == []
    )

    # REQ-PLT-012: an entity that does not exist answers with the same code and the same copy.
    ghost_id, ghost = imported(
        cast.eve,
        "eve-ghost.csv",
        contracts_csv(world.customer_id, external_id="EVE-ZZ-0001", contracting="AVM-ZZ"),
        "contracts",
    )
    assert ghost["status"] == "INVALID", ghost
    unknown = findings_of(cast.maya, ghost_id)
    assert [(item["code"], item["row_number"]) for item in unknown] == [(CODE, 2), (CODE, 3)]
    assert [item["message"] for item in unknown] == [
        item["message"].replace("AVM-US", "AVM-ZZ") for item in found
    ]

    # Positive control 1: the same AVM-US file of Maya's, whose role covers every entity.
    maya_id = diffed(
        cast.maya,
        "maya-new.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30001"),
        "contracts",
    )
    assert named(cast.maya, maya_id) == [us]
    # Positive control 2: Eve's file for her own entity validates; its set names AVM-UK only.
    own_id, own = imported(
        cast.eve,
        "eve-uk.csv",
        contracts_csv(world.customer_id, external_id="EVE-UK-0001", contracting="AVM-UK"),
        "contracts",
    )
    assert own["status"] == "VALIDATED", (own, findings_of(cast.maya, own_id))
    assert named(cast.maya, own_id) == [uk]
    # … and runs to its commit with people whose roles cover AVM-UK only: the dry run and the
    # commit act inside that scope (05 IPL-07, IPL-10), and Eve reads the contract she imported.
    (own_diff,) = job_ids(cast.maya, own_id, "IMPORT_DIFF")
    run_import_job(cast.eve, own_diff)
    ready = get(cast.app, f"{IMPORTS_PATH}/{own_id}", cast.eve.actor).json()
    assert ready["status"] == "DIFF_READY", ready
    assert ready["diff_summary"]["contracts_created"] == 1, (ready, findings_of(cast.maya, own_id))
    submitted = submit(cast.eve, own_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(cast.app, str(submitted.json()["approval_request_id"]), cast.rhea)
    assert decided.status_code == 200, decided.text
    run_import_job(cast.eve, job_ids(cast.maya, own_id, "IMPORT_COMMIT")[-1])
    assert status_of(cast.maya, own_id) == "COMMITTED"
    (booked,) = cast.maya.rows(
        select(contract.c.id, contract.c.contracting_entity_id).where(
            contract.c.external_id == "EVE-UK-0001"
        )
    )
    assert booked["contracting_entity_id"] == uk
    assert get(cast.app, f"{CONTRACTS}/{booked['id']}", cast.eve.actor).status_code == 200


def test_sc2_the_dry_run_diff_shows_nothing_of_another_entitys_contract(cast: Cast) -> None:
    """R-29; 05 IPL-05 / IPL-07: Maya's DRAFT contract of AVM-US (transaction price 120,000.00) is
    invisible to Eve — and stays so through a file of hers that names it: a contract template row
    is refused by name, a contract-event row answers ``CONTRACT_NOT_FOUND`` exactly as an unknown
    contract does, and no diff exists that could carry a ``before`` value."""
    world = cast.world
    created = post(cast.app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    hidden = get(cast.app, f"{CONTRACTS}/{created.json()['id']}", cast.eve.actor)
    assert hidden.status_code == 404, hidden.text

    # A `contracts` file that would replace the AVM-US draft, written for Eve's own entity.
    leak_id, leak = imported(
        cast.eve,
        "eve-replace.csv",
        contracts_csv(
            world.customer_id,
            external_id="SF-ORD-20417",
            contracting="AVM-UK",
            implementation="30000.00",
        ),
        "contracts",
    )
    assert leak["status"] == "INVALID", leak
    found = findings_of(cast.maya, leak_id)
    assert {item["code"] for item in found} == {CODE}
    assert all(
        "Contract SF-ORD-20417 is not available for this import." in item["message"]
        for item in found
    ), found
    assert job_ids(cast.maya, leak_id, "IMPORT_DIFF") == []
    diff = get(cast.app, f"{IMPORTS_PATH}/{leak_id}/diff", cast.eve.actor)
    assert (diff.status_code, slug(diff)) == (409, "invalid-transition"), diff.text
    for path in ("", "/rows", "/error-report"):
        answer = get(cast.app, f"{IMPORTS_PATH}/{leak_id}{path}", cast.eve.actor)
        assert answer.status_code == 200, (path, answer.text)
        assert "120000.00" not in answer.text and "120,000.00" not in answer.text, path

    # A contract-event template: the other entity's contract is unknown, word for word.
    event_id, event = imported(
        cast.eve, "eve-costs.csv", cost_events_csv("SF-ORD-20417"), "cost_events"
    )
    ghost_id, ghost = imported(
        cast.eve, "eve-costs-ghost.csv", cost_events_csv("SF-ORD-99999"), "cost_events"
    )
    assert (event["status"], ghost["status"]) == ("INVALID", "INVALID")
    (outside,) = findings_of(cast.maya, event_id)
    (unknown,) = findings_of(cast.maya, ghost_id)
    assert (outside["code"], unknown["code"]) == ("CONTRACT_NOT_FOUND", "CONTRACT_NOT_FOUND")
    assert outside["message"] == unknown["message"].replace("SF-ORD-99999", "SF-ORD-20417")
    # The upload names the contract's entity all the same (the readers are scoped by it).
    assert named(cast.maya, event_id) == [world.entity_id]
    # Supervisor ruling R-98 (2) moved this expectation (STALE EXPECTATION: it read ``[]``, the
    # set of a tenant-level upload): an upload naming a contract that does not exist names
    # something this job could not place, so it is NOT resolved — NULL, read by its uploader
    # and by a reader of every entity only.
    assert named(cast.maya, ghost_id) is None

    # Positive control: Maya's replacing file is diffed and shows her the stored price.
    maya_id = diffed(
        cast.maya,
        "maya-replace.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-20417", implementation="30000.00"),
        "contracts",
    )
    items = get(cast.app, f"{IMPORTS_PATH}/{maya_id}/diff", cast.maya.actor).json()["items"]
    price = [item for item in items if item["measure"] == "transaction_price"]
    assert price and price[0]["before"] == "120000.00", items


def test_sc2_the_uploaders_scope_is_read_again_at_submit_and_at_commit(
    cast: Cast, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """05 IPL-08 / IPL-10 rev 1.46: Zoe's role covers AVM-US when she uploads; once it no longer
    does, her DIFF_READY import cannot be submitted (403) and her APPROVED import commits nothing
    (FAILED) — while the import she committed before stands."""
    world = cast.world
    app = cast.app
    zoe_member = colleague(world.place.tenant_id, "zoe")
    both = [world.entity_id, world.uk_entity_id]
    zoe = ImportWorld(
        app=app,
        actor=holding(app, zoe_member, "revenue_accountant", entity_ids=both),
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )
    assign(world.priya.member, "revenue_reviewer")  # every entity; MFA enrolled

    def approved(external_id: str) -> str:
        import_id = diffed(
            zoe,
            f"{external_id}.csv",
            contracts_csv(world.customer_id, external_id=external_id),
            "contracts",
        )
        submitted = submit(zoe, import_id)
        assert submitted.status_code == 200, submitted.text
        decided = approve(app, str(submitted.json()["approval_request_id"]), world.priya)
        assert decided.status_code == 200, decided.text
        return import_id

    # Positive control: inside her scope the whole pipeline runs.
    done = approved("ZOE-US-0001")
    run_import_job(zoe, job_ids(zoe, done, "IMPORT_COMMIT")[-1])
    assert status_of(cast.maya, done) == "COMMITTED"
    pending = approved("ZOE-US-0002")  # APPROVED, its commit job not yet run
    waiting = diffed(
        zoe,
        "ZOE-US-0003.csv",
        contracts_csv(world.customer_id, external_id="ZOE-US-0003"),
        "contracts",
    )

    # An administrator narrows Zoe to AVM-UK.
    with tenant_session(cast.all_entities()) as session:
        revoke_role_assignments(
            session,
            tenant_id=zoe_member.tenant_id,
            membership_id=zoe_member.membership_id,
            at=clock.now(),
        )
    assign(zoe_member, "revenue_accountant", entity_ids=[world.uk_entity_id])

    refused = submit(zoe, waiting)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.SCOPE_LOST
    assert status_of(cast.maya, waiting) == "DIFF_READY"

    run_import_job(zoe, job_ids(zoe, pending, "IMPORT_COMMIT")[-1])
    assert status_of(cast.maya, pending) == "FAILED"
    failed = cast.maya.rows(
        select(exception_item.c.code).where(exception_item.c.import_upload_id == UUID(pending))
    )
    assert [str(row["code"]) for row in failed] == ["IMPORT_PROCESSING_FAILED"]
    stored = cast.maya.rows(
        select(contract.c.external_id)
        .where(contract.c.external_id.like("ZOE-US-%"))
        .order_by(contract.c.external_id)
    )
    assert [row["external_id"] for row in stored] == ["ZOE-US-0001"]


def test_sc2_quarantine_mode_commits_only_the_rows_inside_the_uploaders_scope(
    cast: Cast,
) -> None:
    """REQ-DAT-008 with R-29 (04 table 15.4-B: "or the row stays behind in quarantine mode"): with
    ``data.quarantine_failed_rows`` the rows of Eve's file that name AVM-US stay behind with
    their finding, and the rows of her own entity are diffed, submitted, approved and committed —
    the scope read again at submit and at commit is the one of the rows that commit."""
    world = cast.world
    us, uk = world.entity_id, world.uk_entity_id
    with tenant_session(cast.all_entities()) as session:
        publish_registry_version(
            session,
            tenant_id=cast.maya.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )
    own = contracts_csv(world.customer_id, external_id="EVE-UK-0002", contracting="AVM-UK")
    other = contracts_csv(world.customer_id, external_id="EVE-US-0002")
    content = own + other.split(b"\n", 1)[1]  # one header, rows 2-3 AVM-UK, rows 4-5 AVM-US
    import_id, shown = imported(cast.eve, "eve-mixed.csv", content, "contracts")
    assert shown["is_quarantine_mode"] is True
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        2,
        2,
    ), (shown, findings_of(cast.maya, import_id))
    found = findings_of(cast.maya, import_id)
    assert [(item["code"], item["row_number"]) for item in found] == [(CODE, 4), (CODE, 5)]
    # The stored set names the entities of EVERY data row: readers and approvers are scoped by it.
    assert named(cast.maya, import_id) == sorted([us, uk], key=str)

    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    ready = get(cast.app, f"{IMPORTS_PATH}/{import_id}", cast.eve.actor).json()
    assert (ready["status"], ready["diff_summary"]["contracts_created"]) == ("DIFF_READY", 1)
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    assign(world.priya.member, "revenue_reviewer")  # every entity
    decided = approve(cast.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(cast.eve, job_ids(cast.maya, import_id, "IMPORT_COMMIT")[-1])
    done = get(cast.app, f"{IMPORTS_PATH}/{import_id}", cast.eve.actor).json()
    assert done["status"] == "COMMITTED", (done, findings_of(cast.maya, import_id))
    assert done["control_totals"]["loaded"] == {"rows": 2, "quarantined": 2}
    stored = cast.maya.rows(
        select(contract.c.external_id, contract.c.contracting_entity_id).where(
            contract.c.external_id.like("EVE-U%-0002")
        )
    )
    assert [(row["external_id"], row["contracting_entity_id"]) for row in stored] == [
        ("EVE-UK-0002", uk)
    ]


def test_r106_a_quarantine_mode_request_holds_its_uploader_to_the_rows_that_commit(
    cast: Cast, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-106 (b), beside the test above: the uploader is held to the entities
    of the rows that COMMIT, the request to every entity any row names (R-87 (1)).

    - Zoe's role covers both entities when she uploads, so all four rows are usable. Once it
      covers AVM-UK only, a committing row names an entity outside her scope and the submission
      is refused by name — quarantine mode changes nothing about that.
    - Eve's file: two AVM-UK rows commit, two AVM-US rows stay behind; her request names both
      entities. Rhea approves imports for AVM-UK only — the entity of the rows that commit: the
      request does not wait for her, her approval is refused by name, and she cannot read the
      upload (404). She lists and reads the REQUEST, as 04 §16.10 has it for a scope that covers
      one of its entities, with her own entity named and the other one counted.
    - Eve reads and withdraws her own request."""
    world = cast.world
    app = cast.app
    us, uk = world.entity_id, world.uk_entity_id
    with tenant_session(cast.all_entities()) as session:
        publish_registry_version(
            session,
            tenant_id=cast.maya.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )

    def mixed(prefix: str) -> bytes:
        own = contracts_csv(
            world.customer_id, external_id=f"{prefix}-UK-0003", contracting="AVM-UK"
        )
        other = contracts_csv(world.customer_id, external_id=f"{prefix}-US-0003")
        return own + other.split(b"\n", 1)[1]  # one header, rows 2-3 AVM-UK, rows 4-5 AVM-US

    # A committing row outside the uploader's scope: refused at submission.
    zoe_member = colleague(world.place.tenant_id, "zoe")
    zoe = ImportWorld(
        app=app,
        actor=holding(app, zoe_member, "revenue_accountant", entity_ids=[us, uk]),
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )
    waiting = diffed(zoe, "zoe-mixed.csv", mixed("ZOE"), "contracts")
    assert get(app, f"{IMPORTS_PATH}/{waiting}", zoe.actor).json()["counts"]["valid"] == 4
    with tenant_session(cast.all_entities()) as session:
        revoke_role_assignments(
            session,
            tenant_id=zoe_member.tenant_id,
            membership_id=zoe_member.membership_id,
            at=clock.now(),
        )
    assign(zoe_member, "revenue_accountant", entity_ids=[uk])
    refused = submit(zoe, waiting)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.SCOPE_LOST
    assert status_of(cast.maya, waiting) == "DIFF_READY"

    # Eve's rows that commit are inside her scope; the rows that stay behind are not.
    import_id, shown = imported(cast.eve, "eve-mixed-2.csv", mixed("EVE"), "contracts")
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        2,
        2,
    ), shown
    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    bound = cast.maya.rows(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == UUID(request_id))
    )
    assert [(row["entity_id"], sorted(row["entity_ids"], key=str)) for row in bound] == [
        (None, sorted([us, uk], key=str))
    ]

    # Rhea covers the entity of the rows that commit, and not every entity the request names.
    read = get(app, f"{APPROVALS}/{request_id}", cast.rhea)
    assert read.status_code == 200, read.text
    body = read.json()
    assert (
        body["can_decide"],
        body["entity"],
        [ref["code"] for ref in body["entities"]],
        body["entity_count"],
    ) == (False, None, ["AVM-UK"], 2)
    listed = get(app, APPROVALS, cast.rhea, {"assigned_to_me": "true"})
    assert listed.status_code == 200, listed.text
    assert request_id not in {str(item["id"]) for item in listed.json()["items"]}
    decided = approve(app, request_id, cast.rhea)
    assert (decided.status_code, slug(decided)) == (403, "forbidden"), decided.text
    assert decided.json()["detail"] == EVERY_ENTITY_DETAIL
    upload = get(app, f"{IMPORTS_PATH}/{import_id}", cast.rhea)
    assert (upload.status_code, slug(upload)) == (404, "not-found"), upload.text

    # The uploader reads her own request and withdraws it; nothing was decided or committed.
    own = get(app, f"{APPROVALS}/{request_id}", cast.eve.actor)
    assert (own.status_code, own.json()["status"]) == (200, "PENDING"), own.text
    withdrawn = post(
        app, f"{APPROVALS}/{request_id}/withdraw", cast.eve.actor, {"comment": "Wrong file."}
    )
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "WITHDRAWN"), withdrawn.text
    assert job_ids(cast.maya, import_id, "IMPORT_COMMIT") == []
    stored = cast.maya.rows(select(contract.c.id).where(contract.c.external_id.like("%-0003")))
    assert stored == []


def test_sc3_import_reads_stay_inside_the_readers_contract_read_scope(cast: Cast) -> None:
    """R-28; 04 API-R-43 rev 1.107: an upload naming an entity outside the reader's
    ``contract.read`` scope answers 404 on every import read, exactly as an unknown id, and is not
    listed; the uploader reads her own upload, and tenant-level uploads stay visible."""
    world = cast.world
    app, eve, maya = cast.app, cast.eve.actor, cast.maya.actor
    us_id = diffed(
        cast.maya,
        "maya-us.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30001"),
        "contracts",
    )
    # AVM-UK only, and a file of a template that names no entity (tenant-level, R-41 (5)).
    uk_id, _ = imported(
        cast.maya,
        "maya-uk.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30002", contracting="AVM-UK"),
        "contracts",
    )
    customers_id, customers = imported(
        cast.maya,
        "maya-customers.csv",
        csv_bytes(
            CUSTOMER_HEADERS, [["C-501", "Harbourline Freight Ltd (Demo)", "Logistics", "PT"]]
        ),
        "customers",
    )
    assert customers["status"] == "VALIDATED", customers
    assert named(cast.maya, customers_id) == []
    # Eve's own upload names AVM-US too (and is INVALID for it): hers to read all the same.
    own_id, own = imported(
        cast.eve,
        "eve-new.csv",
        contracts_csv(world.customer_id, external_id="EVE-US-0001"),
        "contracts",
    )
    assert own["status"] == "INVALID", own
    # An upload whose validation has not run names nothing yet: every-entity readers only.
    created = create_import(
        cast.maya,
        upload_import_source(
            cast.maya,
            "maya-later.csv",
            contracts_csv(world.customer_id, external_id="SF-ORD-30003"),
        ),
        "contracts",
    )
    assert created.status_code == 202, created.text
    unresolved_id = created.headers[IMPORT_ID_HEADER]
    assert named(cast.maya, unresolved_id) is None

    unknown = get(app, f"{IMPORTS_PATH}/{uuid4()}", eve)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found")
    for hidden in (us_id, unresolved_id):
        for path in ("", "/rows", "/diff", "/error-report"):
            answer = get(app, f"{IMPORTS_PATH}/{hidden}{path}", eve)
            assert (answer.status_code, slug(answer)) == (404, "not-found"), (path, answer.text)
            body = answer.json()
            assert (body["title"], body["detail"], body["errors"]) == (
                unknown.json()["title"],
                unknown.json()["detail"],
                unknown.json()["errors"],
            ), path
            assert "SF-ORD-3000" not in answer.text and "AVM-US" not in answer.text, path
    listed = get(app, IMPORTS_PATH, eve)
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()["items"]} == {uk_id, customers_id, own_id}

    # Positive controls: the same reads answer for a reader whose scope covers the entity …
    for path, expected in (("", 200), ("/rows", 200), ("/diff", 200), ("/error-report", 200)):
        answer = get(app, f"{IMPORTS_PATH}/{us_id}{path}", maya)
        assert answer.status_code == expected, (path, answer.text)
    every = get(app, IMPORTS_PATH, maya)
    assert {item["id"] for item in every.json()["items"]} == {
        us_id,
        uk_id,
        customers_id,
        own_id,
        unresolved_id,
    }
    # … for Eve on what her scope covers, on tenant-level data, and on her own upload.
    for visible in (uk_id, customers_id, own_id):
        for path in ("", "/rows", "/error-report"):
            answer = get(app, f"{IMPORTS_PATH}/{visible}{path}", eve)
            assert answer.status_code == 200, (visible, path, answer.text)
    raw = get(app, f"{IMPORTS_PATH}/{own_id}/rows", eve).json()["items"][0]["raw"]
    assert raw["contracting_entity_code"] == "AVM-US"


# --- legacy v1 Contract Setup: the commit activates (BR-DAT-06) ---------------------------------


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


def test_sc2_a_legacy_contract_setup_activates_only_inside_the_uploaders_scope(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """The legacy v1 Contract Setup commit books AND activates (BR-DAT-06), so a file naming
    another entity would post there. Lena's role covers Mock Entity 1: the delivered file, whose
    Contract 2 is of Mock Entity 2, is INVALID on the row that names that contract's entity —
    its first (04 T-IMP-02 rev 1.256: on a contract's later rows the Selling Entity is the
    line's performing entity, which must exist and need not be covered); the contract of
    Lena's own entity alone is committed and ACTIVE — booked, reviewed and activated inside
    Lena's scope."""
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    first, second = legacy.entity_ids["Mock Entity 1"], legacy.entity_ids["Mock Entity 2"]
    every = legacy.imports
    lena = ImportWorld(
        app=legacy.app,
        actor=holding(
            legacy.app, colleague(every.tenant_id, "lena"), "revenue_accountant", entity_ids=[first]
        ),
        runtime=every.runtime,
        clock=clock,
    )
    import_id, shown = imported(
        lena,
        "Contract Setup Template 1.1.2023.xlsx",
        SETUP_2023.read_bytes(),
        "legacy_contract_setup",
    )
    assert shown["status"] == "INVALID", shown
    found = findings_of(every, import_id)
    assert {item["code"] for item in found} == {CODE}
    assert sorted({item["row_number"] for item in found}) == [6]  # Contract 2's first row
    assert all(
        "Legal entity Mock Entity 2 is not available for this import." in item["message"]
        for item in found
    ), found
    assert named(every, import_id) == sorted([first, second], key=str)
    assert every.rows(select(contract.c.id)) == []

    # Positive control: the rows of her own entity.
    headers, rows = workbook_rows(SETUP_2023)
    entity = headers.index("Selling Entity")
    own = workbook_bytes("Sheet1", headers, [row for row in rows if row[entity] == "Mock Entity 1"])
    own_id = diffed(lena, "Contract Setup entity 1.xlsx", own, "legacy_contract_setup")
    assert named(every, own_id) == [first]
    submitted = submit(lena, own_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(lena, job_ids(every, own_id, "IMPORT_COMMIT")[-1])
    assert status_of(every, own_id) == "COMMITTED", findings_of(every, own_id)
    stored = every.rows(
        select(contract.c.external_id, contract.c.status, contract.c.contracting_entity_id)
    )
    assert [
        (row["external_id"], str(row["status"]), row["contracting_entity_id"]) for row in stored
    ] == [("Contract 1", "ACTIVE", first)]


def elsewhere(keyring: KeyRing, clock: FrozenClock, someone: Actor, role_code: str) -> UUID:
    """Another workspace in which ``someone`` is an ACTIVE member holding ``role_code`` for every
    entity. ``tenant_membership`` is RLS-TM (04 §2.3): the person's own session reads the
    memberships of both workspaces."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        membership_id = insert_active_membership(
            session, tenant_id=tenant_id, user_id=someone.member.user_id
        )
        insert_role_assignment(
            session, tenant_id=tenant_id, membership_id=membership_id, role_code=role_code
        )
    return tenant_id


def test_sc2_a_membership_of_another_workspace_neither_widens_nor_breaks_the_scope(
    cast: Cast, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The uploader's grants are read in the workspace of the import. Eve and Rhea are also ACTIVE
    members of other workspaces, with their roles for EVERY entity there: Eve's file naming AVM-US
    is still INVALID here, and her own entity's file is submitted — the scope re-read at
    submission runs in her own session, which reads both of her memberships — approved and
    committed."""
    world = cast.world
    elsewhere(keyring, clock, cast.eve.actor, "revenue_accountant")
    elsewhere(keyring, clock, cast.rhea, "revenue_reviewer")

    _, refused = imported(
        cast.eve,
        "eve-elsewhere-us.csv",
        contracts_csv(world.customer_id, external_id="EVE-US-0002"),
        "contracts",
    )
    assert refused["status"] == "INVALID", refused

    own_id = diffed(
        cast.eve,
        "eve-elsewhere-uk.csv",
        contracts_csv(world.customer_id, external_id="EVE-UK-0002", contracting="AVM-UK"),
        "contracts",
    )
    submitted = submit(cast.eve, own_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(cast.app, str(submitted.json()["approval_request_id"]), cast.rhea)
    assert decided.status_code == 200, decided.text
    run_import_job(cast.eve, job_ids(cast.maya, own_id, "IMPORT_COMMIT")[-1])
    assert status_of(cast.maya, own_id) == "COMMITTED", findings_of(cast.maya, own_id)


# --- the residuals of the independent review (rulings R-98, R-109) ------------------------------


def all_findings(world: ImportWorld, import_id: str) -> list[str]:
    """The codes of every exception item of an upload, file-level ones included."""
    found = world.rows(
        select(exception_item.c.code)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(exception_item.c.code)
    )
    return [str(row["code"]) for row in found]


def row_statuses(world: ImportWorld, import_id: str) -> list[tuple[int, str]]:
    found = world.rows(
        select(import_row.c.row_number, import_row.c.status)
        .where(import_row.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number)
    )
    return [(int(row["row_number"]), str(row["status"])) for row in found]


def denied(world: ImportWorld, import_id: str) -> list[str]:
    """The actions of the DENIED audit events on an upload."""
    found = world.rows(
        select(audit_event.c.action).where(
            audit_event.c.object_id == UUID(import_id), audit_event.c.outcome == "DENIED"
        )
    )
    return [str(row["action"]) for row in found]


def quarantine_mode(cast: Cast) -> None:
    with tenant_session(cast.all_entities()) as session:
        publish_registry_version(
            session,
            tenant_id=cast.maya.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )


def test_r98_submit_and_cancel_answer_404_outside_the_callers_read_scope(cast: Cast) -> None:
    """R-98 (8): Maya's DIFF_READY upload names AVM-US, which Eve's ``contract.read`` does not
    cover. ``submit`` and ``cancel`` answered Eve 403 — "only the uploader …", with a DENIED
    audit event for the cancel — where the reads answer 404: the commands told her that the
    upload exists. They now answer exactly as for an unknown id. Positive control: Zed, who may
    read the upload and did not upload it, is still told so (403), and his refused cancel is on
    the audit log; Maya's own cancel works."""
    world = cast.world
    app, eve = cast.app, cast.eve.actor
    hidden_id = diffed(
        cast.maya,
        "maya-us.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30001"),
        "contracts",
    )
    assert get(app, f"{IMPORTS_PATH}/{hidden_id}", eve).status_code == 404
    commands = (("submit", {"comment": "mine now"}), ("cancel", {}))
    for command, body in commands:
        unknown = post(app, f"{IMPORTS_PATH}/{uuid4()}/{command}", eve, body)
        assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
        answer = post(app, f"{IMPORTS_PATH}/{hidden_id}/{command}", eve, body)
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (command, answer.text)
        assert (answer.json()["title"], answer.json()["detail"], answer.json()["errors"]) == (
            unknown.json()["title"],
            unknown.json()["detail"],
            unknown.json()["errors"],
        ), command
    assert status_of(cast.maya, hidden_id) == "DIFF_READY"
    assert denied(cast.maya, hidden_id) == []

    # Positive control: a reader of every entity who is not the uploader.
    zed = holding(app, colleague(world.place.tenant_id, "zed"), "revenue_accountant")
    assert get(app, f"{IMPORTS_PATH}/{hidden_id}", zed).status_code == 200
    for command, body in commands:
        refused = post(app, f"{IMPORTS_PATH}/{hidden_id}/{command}", zed, body)
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), (command, refused.text)
    assert denied(cast.maya, hidden_id) == ["import_upload.cancel"]
    assert status_of(cast.maya, hidden_id) == "DIFF_READY"
    cancelled = post(app, f"{IMPORTS_PATH}/{hidden_id}/cancel", cast.maya.actor, {})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"


def test_r98_a_role_that_only_reads_another_entity_does_not_let_a_file_write_there(
    cast: Cast,
) -> None:
    """R-98 (2), the write outside scope: an AVM-US contract whose external id ends in a space,
    and Vera — Revenue Accountant for AVM-UK, Viewer for every entity, so the union of her roles
    is every entity while her ``event.record`` covers AVM-UK only. Her ``cost_events`` file names
    the key exactly. The scope read the key stripped and found no entity, took the upload for
    tenant-level data and processed it under the UNION of her roles; the template matched the
    key as typed, the upload VALIDATED and its commit would have appended to the AVM-US
    contract. Now the key is exact text and the job runs inside her ``event.record`` scope: the
    contract is unknown to her file, word for word as a contract that does not exist."""
    world = cast.world
    app = cast.app
    spaced = "SF-ORD-20417 "
    created = post(
        app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id, external_id=spaced)
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]
    vera_member = colleague(world.place.tenant_id, "vera")
    assign(vera_member, "viewer")
    vera = ImportWorld(
        app=app,
        actor=holding(app, vera_member, "revenue_accountant", entity_ids=[world.uk_entity_id]),
        runtime=cast.maya.runtime,
        clock=cast.maya.clock,
    )
    # She reads the AVM-US contract (Viewer) — the union of her roles reaches it.
    assert get(app, f"{CONTRACTS}/{contract_id}", vera.actor).status_code == 200

    event_id, event = imported(vera, "vera-costs.csv", cost_events_csv(spaced), "cost_events")
    ghost_id, ghost = imported(
        vera, "vera-costs-ghost.csv", cost_events_csv("SF-ORD-99999 "), "cost_events"
    )
    assert (event["status"], ghost["status"]) == ("INVALID", "INVALID"), (event, ghost)
    (outside,) = findings_of(cast.maya, event_id)
    (unknown,) = findings_of(cast.maya, ghost_id)
    assert (outside["code"], unknown["code"]) == ("CONTRACT_NOT_FOUND", "CONTRACT_NOT_FOUND")
    assert outside["message"] == unknown["message"].replace("SF-ORD-99999 ", spaced)
    # The exact key resolves: the upload names AVM-US, and is scoped by it.
    assert named(cast.maya, event_id) == [world.entity_id]
    assert named(cast.maya, ghost_id) is None
    assert job_ids(cast.maya, event_id, "IMPORT_DIFF") == []
    assert (
        cast.maya.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == UUID(event_id))
        )
        == []
    )

    # Positive control: the same file of Maya's, whose ``event.record`` covers AVM-US.
    maya_id, shown = imported(cast.maya, "maya-costs.csv", cost_events_csv(spaced), "cost_events")
    assert shown["status"] == "VALIDATED", (shown, findings_of(cast.maya, maya_id))
    assert named(cast.maya, maya_id) == [world.entity_id]


def test_r98_an_upload_naming_a_reference_that_does_not_resolve_is_unresolved(cast: Cast) -> None:
    """R-98 (2), the read exposure: an upload of a template that can name an entity, with a row
    naming a reference that does not resolve — a contract that does not exist, a misspelt entity
    code — stored the empty set, the set of tenant-level data, and every holder of
    ``contract.read`` listed it and read its raw rows. It is now unresolved: Uma, a colleague of
    Eve's own scope, is answered as for an unknown id and does not see it listed; Eve reads her
    own upload and Maya, who reads every entity, reads it too. Positive control: Eve's
    tenant-level upload and her upload whose every reference resolves inside AVM-UK are read by
    Uma."""
    world = cast.world
    app = cast.app
    uma = holding(
        app,
        colleague(world.place.tenant_id, "uma"),
        "revenue_accountant",
        entity_ids=[world.uk_entity_id],
    )
    ghost_id, ghost = imported(
        cast.eve, "eve-costs-ghost.csv", cost_events_csv("SF-ORD-99999"), "cost_events"
    )
    typo_id, typo = imported(
        cast.eve,
        "eve-typo.csv",
        contracts_csv(world.customer_id, external_id="EVE-ZZ-0001", contracting="AVM-ZZ"),
        "contracts",
    )
    assert (ghost["status"], typo["status"]) == ("INVALID", "INVALID")
    unknown = get(app, f"{IMPORTS_PATH}/{uuid4()}", uma)
    for unresolved in (ghost_id, typo_id):
        assert named(cast.maya, unresolved) is None
        with tenant_session(cast.all_entities(), read_only=True) as session:
            assert scope.named_entity_ids(session, UUID(unresolved)) is None
        for path in ("", "/rows", "/diff", "/error-report"):
            answer = get(app, f"{IMPORTS_PATH}/{unresolved}{path}", uma)
            assert (answer.status_code, slug(answer)) == (404, "not-found"), (path, answer.text)
            assert answer.json()["detail"] == unknown.json()["detail"], path
        assert get(app, f"{IMPORTS_PATH}/{unresolved}/rows", cast.eve.actor).status_code == 200
        assert get(app, f"{IMPORTS_PATH}/{unresolved}", cast.maya.actor).status_code == 200

    # Positive controls: what names no entity, and what names AVM-UK only, Uma reads.
    customers_id, customers = imported(
        cast.eve,
        "eve-customers.csv",
        csv_bytes(CUSTOMER_HEADERS, [["C-502", "Marlow Cold Chain Ltd (Demo)", "Logistics", "GB"]]),
        "customers",
    )
    own_id, own = imported(
        cast.eve,
        "eve-uk.csv",
        contracts_csv(world.customer_id, external_id="EVE-UK-0001", contracting="AVM-UK"),
        "contracts",
    )
    assert (customers["status"], own["status"]) == ("VALIDATED", "VALIDATED")
    assert named(cast.maya, customers_id) == []
    assert named(cast.maya, own_id) == [world.uk_entity_id]
    listed = get(app, IMPORTS_PATH, uma)
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()["items"]} == {customers_id, own_id}
    for visible in (customers_id, own_id):
        assert get(app, f"{IMPORTS_PATH}/{visible}/rows", uma).status_code == 200


def test_r98_quarantine_mode_loads_a_contract_whole_or_not_at_all(cast: Cast) -> None:
    """R-98 (10), R-109 (c): with ``data.quarantine_failed_rows`` the refused rows stay behind
    and the others commit (REQ-DAT-008) — row by row, so a contract one line of which was
    refused was booked from the lines that remained. Eve's file holds EVE-UK-0003, all of
    AVM-UK, and EVE-UK-0004, of AVM-UK by its first row, whose second row states AVM-US as the
    contracting entity: that row is refused by the scope, and the first row is now refused
    with it, by name. Only the whole contract is diffed, approved and committed. (Until 04
    T-IMP-02 rev 1.256 the refused row was one whose line AVM-US performs; the performing
    entity of a line is no longer refused for the uploader's scope. Since 04 rev 1.310 that
    second row is refused a first time on the file alone — it states another contracting entity
    than its contract's first row, ``HEADER_VALUE_CONFLICT`` — and the scope's finding stands
    beside it: the rule of the repeated cell reads no scope and the scope's rule reads every
    row's cell as before.)"""
    world = cast.world
    us, uk = world.entity_id, world.uk_entity_id
    quarantine_mode(cast)
    whole = contracts_csv(world.customer_id, external_id="EVE-UK-0003", contracting="AVM-UK")
    of_uk = contracts_csv(world.customer_id, external_id="EVE-UK-0004", contracting="AVM-UK")
    of_us = contracts_csv(world.customer_id, external_id="EVE-UK-0004", contracting="AVM-US")
    # one header; rows 2-3 whole; row 4 the first row of EVE-UK-0004, of AVM-UK; row 5 its
    # second row as a file of AVM-US states it
    content = whole + of_uk.split(b"\n")[1] + b"\n" + of_us.split(b"\n")[2] + b"\n"
    import_id, shown = imported(cast.eve, "eve-split.csv", content, "contracts")
    assert shown["is_quarantine_mode"] is True
    found = findings_of(cast.maya, import_id)
    assert [(item["code"], item["row_number"]) for item in found] == [
        ("IMPORT_CONTRACT_INCOMPLETE", 4),
        ("HEADER_VALUE_CONFLICT", 5),
        (CODE, 5),
    ], found
    assert (
        "Another row of contract EVE-UK-0004 was refused, so none of its rows is loaded. "
        "Correct that row and upload the contract's rows again."
    ) in found[0]["message"], found[0]
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        2,
        2,
    ), shown
    assert row_statuses(cast.maya, import_id) == [
        (2, "VALID"),
        (3, "VALID"),
        (4, "ERROR"),
        (5, "ERROR"),
    ]
    assert named(cast.maya, import_id) == sorted([us, uk], key=str)

    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    ready = get(cast.app, f"{IMPORTS_PATH}/{import_id}", cast.eve.actor).json()
    assert (ready["status"], ready["diff_summary"]["contracts_created"]) == ("DIFF_READY", 1)
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    assign(world.priya.member, "revenue_reviewer")  # every entity
    decided = approve(cast.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(cast.eve, job_ids(cast.maya, import_id, "IMPORT_COMMIT")[-1])
    done = get(cast.app, f"{IMPORTS_PATH}/{import_id}", cast.eve.actor).json()
    assert done["status"] == "COMMITTED", (done, findings_of(cast.maya, import_id))
    assert done["control_totals"]["loaded"] == {"rows": 2, "quarantined": 2}
    stored = cast.maya.rows(
        select(contract.c.external_id).where(contract.c.external_id.like("EVE-UK-000%"))
    )
    assert [row["external_id"] for row in stored] == ["EVE-UK-0003"]


def test_r98_quarantine_mode_keeps_the_events_of_a_contract_together(cast: Cast) -> None:
    """R-109 (c), the wide reading: the contract is the unit for every template with a contract
    column — the cross-row rules of an event template were evaluated with the refused row
    present. Two ``cost_events`` rows of one contract, the first with an amount that is no
    number: the second is refused with it; the row of another contract stays usable."""
    world = cast.world
    quarantine_mode(cast)
    for key in ("SF-ORD-40001", "SF-ORD-40002"):
        created = post(
            cast.app,
            CONTRACTS,
            cast.maya.actor,
            sf_ord_20417_body(world.customer_id, external_id=key),
        )
        assert created.status_code == 201, created.text
    rows = [
        ["SF-ORD-40001", "2026-09-05", "COST_TO_OBTAIN", "five thousand", "USD", "SALES-2026"],
        ["SF-ORD-40001", "2026-09-06", "COST_TO_OBTAIN", "120.00", "USD", "SALES-2026"],
        ["SF-ORD-40002", "2026-09-07", "COST_TO_OBTAIN", "240.00", "USD", "SALES-2026"],
    ]
    import_id, shown = imported(
        cast.maya, "maya-costs-mixed.csv", csv_bytes(COST_HEADERS, rows), "cost_events"
    )
    found = findings_of(cast.maya, import_id)
    assert [(item["code"], item["row_number"]) for item in found] == [
        ("VALUE_NOT_NUMERIC", 2),
        ("IMPORT_CONTRACT_INCOMPLETE", 3),
    ], found
    assert "Another row of contract SF-ORD-40001 was refused" in found[1]["message"]
    assert row_statuses(cast.maya, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID")]
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        1,
        2,
    ), shown


def template_row(code: str, contract_key: str) -> tuple[list[str], list[str]]:
    """The headers of a contract-keyed CSV v2 template and one row naming ``contract_key``, every
    required cell filled with a value of its type."""
    samples = {
        "document_kind": "INVOICE",
        "event_type": "DELIVERY_RECORDED",
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "method": "EXPECTED_VALUE",
        "obligation_key": "O1",
        "lines.amount.currency": "USD",
        "amount.currency": "USD",
    }
    by_type = {"date": "2026-09-05", "amount": "100.00", "quantity": "1", "text": "X-1"}
    template = csv_v2.TEMPLATES[code]
    headers = [column.name for column in template.columns]
    row = []
    for column in template.columns:
        if column.name == template.key_column:
            row.append(contract_key)
        elif column.required:
            row.append(samples.get(column.name, by_type[column.type]))
        else:
            row.append("")
    return headers, row


@pytest.mark.parametrize(
    "code", ["invoices", "progress_events", "usage", "pre_standard_revenue", "estimates"]
)
def test_r98_every_contract_keyed_template_stays_inside_the_uploaders_scope(
    cast: Cast, code: str
) -> None:
    """The templates the review found without a database scope test. A row of Eve's file that
    names Maya's AVM-US contract is ``CONTRACT_NOT_FOUND``, word for word as a contract that does
    not exist — the template's own rule reads inside her scope for the template's write
    permission — and nothing is diffed. The upload naming the AVM-US contract is scoped by that
    entity; the one naming nothing known is unresolved. Positive control: the same row of
    Maya's finds the contract."""
    world = cast.world
    created = post(cast.app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    headers, row = template_row(code, "SF-ORD-20417")
    _, ghost_row = template_row(code, "SF-ORD-99999")
    event_id, event = imported(cast.eve, f"eve-{code}.csv", csv_bytes(headers, [row]), code)
    ghost_id, ghost = imported(
        cast.eve, f"eve-{code}-ghost.csv", csv_bytes(headers, [ghost_row]), code
    )
    assert (event["status"], ghost["status"]) == ("INVALID", "INVALID"), (event, ghost)
    (outside,) = findings_of(cast.maya, event_id)
    (unknown,) = findings_of(cast.maya, ghost_id)
    assert (outside["code"], unknown["code"]) == ("CONTRACT_NOT_FOUND", "CONTRACT_NOT_FOUND")
    assert outside["message"] == unknown["message"].replace("SF-ORD-99999", "SF-ORD-20417")
    assert job_ids(cast.maya, event_id, "IMPORT_DIFF") == []
    assert named(cast.maya, event_id) == [world.entity_id]
    assert named(cast.maya, ghost_id) is None

    maya_id, _ = imported(cast.maya, f"maya-{code}.csv", csv_bytes(headers, [row]), code)
    codes = all_findings(cast.maya, maya_id)
    assert "CONTRACT_NOT_FOUND" not in codes and "IMPORT_PROCESSING_FAILED" not in codes, codes
    assert named(cast.maya, maya_id) == [world.entity_id]


def test_r98_an_uploader_without_the_write_permission_writes_no_entity_data(cast: Cast) -> None:
    """A holder of ``import.upload`` who does not hold the template's write permission at all:
    Sven holds the Service Account role for every entity — ``contract.read`` and
    ``import.upload``, no ``estimate.create``. He reads Maya's AVM-US contract, and his
    ``estimates`` file that names it is processed inside an EMPTY entity scope: the contract is
    unknown to it, exactly as one that does not exist. Positive control: the same file of
    Maya's, who holds ``estimate.create`` for AVM-US, finds the contract."""
    world = cast.world
    app = cast.app
    created = post(app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    sven = ImportWorld(
        app=app,
        actor=holding(app, colleague(world.place.tenant_id, "sven"), "service_account"),
        runtime=cast.maya.runtime,
        clock=cast.maya.clock,
    )
    assert get(app, f"{CONTRACTS}/{created.json()['id']}", sven.actor).status_code == 200
    headers, row = template_row("estimates", "SF-ORD-20417")
    _, ghost_row = template_row("estimates", "SF-ORD-99999")
    event_id, event = imported(sven, "sven-estimates.csv", csv_bytes(headers, [row]), "estimates")
    ghost_id, ghost = imported(
        sven, "sven-estimates-ghost.csv", csv_bytes(headers, [ghost_row]), "estimates"
    )
    assert (event["status"], ghost["status"]) == ("INVALID", "INVALID"), (event, ghost)
    (outside,) = findings_of(cast.maya, event_id)
    (unknown,) = findings_of(cast.maya, ghost_id)
    assert (outside["code"], unknown["code"]) == ("CONTRACT_NOT_FOUND", "CONTRACT_NOT_FOUND")
    assert outside["message"] == unknown["message"].replace("SF-ORD-99999", "SF-ORD-20417")

    maya_id, _ = imported(cast.maya, "maya-estimates.csv", csv_bytes(headers, [row]), "estimates")
    codes = all_findings(cast.maya, maya_id)
    assert "CONTRACT_NOT_FOUND" not in codes and "IMPORT_PROCESSING_FAILED" not in codes, codes


def test_r98_a_usable_row_outside_the_scope_fails_the_job_closed(
    cast: Cast, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last line of defence in the validation job: before a row is kept as usable the job
    reads once more whether it names an entity outside the uploader's scope (``scope.outside``)
    and fails closed if no rule refused it. With the scope findings switched off — a rule that
    did not fire — Eve's file naming AVM-US ends INVALID as a whole: one file-level
    ``IMPORT_PROCESSING_FAILED``, no row stored, nothing resolved, nothing diffed."""
    world = cast.world
    monkeypatch.setattr(scope, "findings", lambda *args, **kwargs: {})
    import_id, shown = imported(
        cast.eve,
        "eve-gap.csv",
        contracts_csv(world.customer_id, external_id="EVE-US-0009"),
        "contracts",
    )
    assert shown["status"] == "INVALID", shown
    assert all_findings(cast.maya, import_id) == ["IMPORT_PROCESSING_FAILED"]
    assert row_statuses(cast.maya, import_id) == []
    assert named(cast.maya, import_id) is None
    assert job_ids(cast.maya, import_id, "IMPORT_DIFF") == []


def test_r98_the_dry_run_runs_inside_the_scope_the_uploader_has_when_it_runs(
    cast: Cast, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """05 IPL-07: the uploader's scope is read when the dry run runs, not when the file was
    validated. Zoe's role covers AVM-US when her file validates and no longer does when the
    dry run starts: the plan fails inside her scope as her own API command would — nothing is
    booked provisionally, the diff shows nothing — and the upload cannot be submitted."""
    world = cast.world
    app = cast.app
    zoe_member = colleague(world.place.tenant_id, "zoe")
    zoe = ImportWorld(
        app=app,
        actor=holding(
            app, zoe_member, "revenue_accountant", entity_ids=[world.entity_id, world.uk_entity_id]
        ),
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )
    import_id, validated = imported(
        zoe,
        "ZOE-US-0005.csv",
        contracts_csv(world.customer_id, external_id="ZOE-US-0005"),
        "contracts",
    )
    assert validated["status"] == "VALIDATED", validated
    with tenant_session(cast.all_entities()) as session:
        revoke_role_assignments(
            session,
            tenant_id=zoe_member.tenant_id,
            membership_id=zoe_member.membership_id,
            at=clock.now(),
        )
    assign(zoe_member, "revenue_accountant", entity_ids=[world.uk_entity_id])

    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(zoe, diff_job)
    ready = get(app, f"{IMPORTS_PATH}/{import_id}", zoe.actor).json()
    assert ready["status"] == "DIFF_READY", ready
    assert (
        ready["diff_summary"]["contracts_affected"],
        ready["diff_summary"]["contracts_created"],
    ) == (0, 0), ready["diff_summary"]
    assert all_findings(cast.maya, import_id) == ["IMPORT_PROCESSING_FAILED"]
    listed = get(app, f"{IMPORTS_PATH}/{import_id}/diff", zoe.actor)
    assert listed.status_code == 200 and listed.json()["items"] == [], listed.text
    refused = submit(zoe, import_id)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.SCOPE_LOST
    booked = select(contract.c.id).where(contract.c.external_id == "ZOE-US-0005")
    assert cast.maya.rows(booked) == []


def test_r98_quarantine_mode_reads_the_scope_of_an_event_file_from_the_rows_that_commit(
    cast: Cast,
) -> None:
    """05 IPL-08 in quarantine mode, for a contract-keyed template: the uploader's scope has to
    cover the entities of the rows that COMMIT, read again from the usable rows
    (``scope.committing_entity_ids``). Eve's ``cost_events`` file names a contract of AVM-UK and
    Maya's contract of AVM-US: the second row is ``CONTRACT_NOT_FOUND`` and stays behind; the
    upload names both entities for its readers, the rows that commit name AVM-UK, and Eve
    submits it."""
    world = cast.world
    us, uk = world.entity_id, world.uk_entity_id
    quarantine_mode(cast)
    home = {
        **sf_ord_20417_body(world.customer_id, external_id="UK-ORD-0001"),
        "contracting_entity_code": "AVM-UK",
    }
    for body in (home, sf_ord_20417_body(world.customer_id)):
        created = post(cast.app, CONTRACTS, cast.maya.actor, body)
        assert created.status_code == 201, created.text
    rows = [
        ["UK-ORD-0001", "2026-09-05", "COST_TO_OBTAIN", "5760.00", "USD", "SALES-2026"],
        ["SF-ORD-20417", "2026-09-05", "COST_TO_OBTAIN", "5760.00", "USD", "SALES-2026"],
    ]
    import_id, shown = imported(
        cast.eve, "eve-costs-mixed.csv", csv_bytes(COST_HEADERS, rows), "cost_events"
    )
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        1,
        1,
    ), (shown, findings_of(cast.maya, import_id))
    found = findings_of(cast.maya, import_id)
    assert [(item["code"], item["row_number"]) for item in found] == [("CONTRACT_NOT_FOUND", 3)]
    assert named(cast.maya, import_id) == sorted([us, uk], key=str)
    (upload,) = cast.maya.rows(select(import_upload).where(import_upload.c.id == UUID(import_id)))
    assert scope.committing_entity_ids(upload) == frozenset({uk})

    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    assert status_of(cast.maya, import_id) == "DIFF_READY"
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text


def performed_by(world: ImportWorld, external_id: str) -> set[tuple[str, str]]:
    """(obligation key, performing entity code) of every computed obligation of a contract, read
    without an entity filter."""
    found = world.rows(
        select(obligation_version.c.obligation_key, legal_entity.c.code)
        .join(legal_entity, legal_entity.c.id == obligation_version.c.performing_entity_id)
        .join(contract, contract.c.id == obligation_version.c.contract_id)
        .where(contract.c.external_id == external_id)
    )
    return {(str(row["obligation_key"]), str(row["code"])) for row in found}


def test_r114_a_performing_entity_must_exist_and_need_not_be_covered(cast: Cast) -> None:
    """Ruling R-114 (g) with the supervisor's word of 2026-10-01 (04 T-IMP-02 rev 1.256; 05
    IPL-08 rev 1.186), replacing R-41 (5)'s clause "a performing entity counts": one set, the
    contracting entities. Eve's role covers AVM-UK alone. Eve's file replaces the DRAFT contract
    UK-ORD-0002 of AVM-UK — inside that scope — with a second line that AVM-US performs: the row
    is usable, the upload names AVM-UK alone, and it runs to its commit with people of AVM-UK
    alone — Eve submits it, Rhea approves it — as the booking command itself takes that line
    from such people (tests/domain/contracts/test_reader_independence.py). A performing entity
    that does not exist is refused by name on its row, with the copy of an entity outside the
    scope. Before: the line AVM-US performs was refused for Eve, the upload named both entities,
    and its approver had to cover AVM-US."""
    world = cast.world
    uk = world.uk_entity_id
    home = {
        **sf_ord_20417_body(world.customer_id, external_id="UK-ORD-0002"),
        "contracting_entity_code": "AVM-UK",
    }
    created = post(cast.app, CONTRACTS, cast.maya.actor, home)
    assert created.status_code == 201, created.text
    assert get(cast.app, f"{CONTRACTS}/{created.json()['id']}", cast.eve.actor).status_code == 200
    assert ("O2", "AVM-US") not in performed_by(cast.maya, "UK-ORD-0002")

    def replacing(performing: str) -> bytes:
        return contracts_csv(
            world.customer_id,
            external_id="UK-ORD-0002",
            contracting="AVM-UK",
            performing=performing,
            implementation="30000.00",
        )

    # it must exist: a code that names no entity is refused on its row, by name
    ghost_id, ghost = imported(cast.eve, "eve-replace-zz.csv", replacing("AVM-ZZ"), "contracts")
    assert ghost["status"] == "INVALID", ghost
    found = findings_of(cast.maya, ghost_id)
    assert [(item["code"], item["row_number"]) for item in found] == [(CODE, 3)], found
    assert NOT_AVAILABLE.replace("AVM-US", "AVM-ZZ") in found[0]["message"], found[0]
    assert job_ids(cast.maya, ghost_id, "IMPORT_DIFF") == []

    # it need not be covered: AVM-US performs the line, and the upload is AVM-UK's alone
    import_id = diffed(cast.eve, "eve-replace-us.csv", replacing("AVM-US"), "contracts")
    assert findings_of(cast.maya, import_id) == []
    assert named(cast.maya, import_id) == [uk]
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(cast.app, str(submitted.json()["approval_request_id"]), cast.rhea)
    assert decided.status_code == 200, decided.text
    run_import_job(cast.eve, job_ids(cast.maya, import_id, "IMPORT_COMMIT")[-1])
    assert status_of(cast.maya, import_id) == "COMMITTED", findings_of(cast.maya, import_id)
    assert ("O2", "AVM-US") in performed_by(cast.maya, "UK-ORD-0002")
    (kept,) = cast.maya.rows(
        select(contract.c.contracting_entity_id).where(contract.c.external_id == "UK-ORD-0002")
    )
    assert kept["contracting_entity_id"] == uk


def mapping_row(account_id: UUID, name: str, entity: str) -> tuple[list[str], list[str]]:
    """One ``account_mapping`` row: a REVENUE rule of the version ``name`` for ``entity`` (an
    entity id as text, or blank for a rule of every entity)."""
    headers = [column.name for column in csv_v2.TEMPLATES["account_mapping"].columns]
    values = dict.fromkeys(headers, "")
    values |= {
        "name": name,
        "effective_from": "2026-07-01T00:00:00Z",
        "lines.account_role": "REVENUE",
        "lines.gl_account_id": str(account_id),
        "lines.priority": "10",
        "lines.entity_id": entity,
    }
    return headers, [values[header] for header in headers]


def test_r98_an_account_mapping_rule_stays_inside_the_scope_of_config_author(cast: Cast) -> None:
    """The ``account_mapping`` template names an entity by id, in the rule of a row (04 §16.6
    template scope). Eve's ``config.author`` covers AVM-UK: her rule for AVM-US is refused by
    name — with the copy of an entity id that does not exist — and such an upload is scoped by
    what resolves: AVM-US for the first, nothing for the second (unresolved, ruling R-98 (2)).
    Positive controls: her rule for AVM-UK validates and names AVM-UK; her rule for every
    entity is tenant-level data."""
    world = cast.world
    us, uk = world.entity_id, world.uk_entity_id
    (account,) = cast.maya.rows(select(gl_account.c.id).where(gl_account.c.code == "4010"))
    account_id = UUID(str(account["id"]))
    absent = uuid4()

    def upload(name: str, entity: str) -> tuple[str, dict[str, Any]]:
        headers, row = mapping_row(account_id, name, entity)
        return imported(cast.eve, f"{name}.csv", csv_bytes(headers, [row]), "account_mapping")

    other_id, other = upload("EVE-MAP-US", str(us))
    ghost_id, ghost = upload("EVE-MAP-ZZ", str(absent))
    assert (other["status"], ghost["status"]) == ("INVALID", "INVALID"), (other, ghost)
    (outside,) = findings_of(cast.maya, other_id)
    (unknown,) = findings_of(cast.maya, ghost_id)
    assert (outside["code"], unknown["code"]) == (CODE, CODE)
    assert f"Legal entity {us} is not available for this import." in outside["message"]
    assert outside["message"] == unknown["message"].replace(str(absent), str(us))
    assert named(cast.maya, other_id) == [us]
    assert named(cast.maya, ghost_id) is None

    own_id, own = upload("EVE-MAP-UK", str(uk))
    assert own["status"] == "VALIDATED", (own, findings_of(cast.maya, own_id))
    assert named(cast.maya, own_id) == [uk]
    every_id, every = upload("EVE-MAP-ALL", "")
    assert every["status"] == "VALIDATED", (every, findings_of(cast.maya, every_id))
    assert named(cast.maya, every_id) == []


# --- legacy v1 templates by a scoped uploader ---------------------------------------------------

PROGRESS_HEADERS = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Current Delivery",
    "Current Billing",
    "Current Pre-ASC606 Revenue (Net Design Only)",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
MODIFICATION_HEADERS = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Mod Start Date",
    "Mod End Date",
    "ASC 606 Stratification",
    "Mod Billing",
    "Mod Qty",
    "Selling Entity",
    "Deferred Revenue Account",
    "Unbilled A/R Account",
    "SSP Version",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
MEMOS = ("Delivery 1", "Delivery 2", "Delivery 3")


def lena_of(legacy: LegacyWorld, clock: FrozenClock) -> ImportWorld:
    """Lena: a Revenue Accountant for Mock Entity 1 only."""
    every = legacy.imports
    first = legacy.entity_ids["Mock Entity 1"]
    return ImportWorld(
        app=legacy.app,
        actor=holding(
            legacy.app, colleague(every.tenant_id, "lena"), "revenue_accountant", entity_ids=[first]
        ),
        runtime=every.runtime,
        clock=clock,
    )


def progress_file(contract_name: str) -> bytes:
    """Two rows of one (contract, POB, SKU) key: the second is aggregated into the first."""
    row = [contract_name, "POB #1", "Hardware 1", 1, 0, 0, *MEMOS]
    return workbook_bytes("Progress Tracking", PROGRESS_HEADERS, [row, row])


def test_r98_a_repeated_key_of_another_entitys_contract_answers_as_an_unknown_one(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """R-98 (5): a legacy progress file sums the rows of one key (DEV-012) and puts the key's
    finding on its lowest row. Lena's file repeats a key of Contract 2, of Mock Entity 2: the
    lead row was refused as ``CONTRACT_NOT_FOUND``, the aggregated row stayed usable, the
    fail-closed check tripped on it and the whole job failed (``IMPORT_PROCESSING_FAILED``, no
    row stored) — an answer an unknown contract does not give, so the file told her that the
    name exists outside her scope. Both now answer alike, row for row. Positive control: Maya's
    same file validates."""
    replayed(legacy, "02")
    every = legacy.imports
    lena = lena_of(legacy, clock)
    parameters = {"effective_date": "2023-01-31"}
    other_id, other = imported(
        lena,
        "Progress other.xlsx",
        progress_file("Contract 2"),
        "legacy_progress_tracking",
        parameters,
    )
    ghost_id, ghost = imported(
        lena,
        "Progress ghost.xlsx",
        progress_file("Contract 9"),
        "legacy_progress_tracking",
        parameters,
    )
    assert (other["status"], ghost["status"]) == ("INVALID", "INVALID"), (other, ghost)
    assert all_findings(every, other_id) == ["CONTRACT_NOT_FOUND"]
    assert all_findings(every, ghost_id) == ["CONTRACT_NOT_FOUND"]
    (outside,) = findings_of(every, other_id)
    (unknown,) = findings_of(every, ghost_id)
    assert (outside["row_number"], unknown["row_number"]) == (2, 2)
    assert outside["message"] == unknown["message"].replace("Contract 9", "Contract 2")
    assert row_statuses(every, other_id) == row_statuses(every, ghost_id)
    assert row_statuses(every, other_id) == [(2, "ERROR"), (3, "AGGREGATED")]
    assert other["counts"] == ghost["counts"]
    # The readers are scoped by what resolves: Contract 2 is of Mock Entity 2.
    assert named(every, other_id) == [legacy.entity_ids["Mock Entity 2"]]
    assert named(every, ghost_id) is None

    maya_id, shown = imported(
        every,
        "Progress maya.xlsx",
        progress_file("Contract 2"),
        "legacy_progress_tracking",
        parameters,
    )
    assert shown["status"] == "VALIDATED", (shown, findings_of(every, maya_id))
    assert row_statuses(every, maya_id) == [(2, "VALID"), (3, "AGGREGATED")]


def modification_file(contract_name: str, pob: str, entity: str) -> bytes:
    row = [
        contract_name,
        pob,
        "Hardware 1",
        "2023-01-01",
        "2024-05-31",
        "Hardware 1",
        100,
        1,
        entity,
        21001,
        15001,
        "2023-01-01",
        *MEMOS,
    ]
    return workbook_bytes("Contract Modification", MODIFICATION_HEADERS, [row])


def test_r98_a_legacy_modification_stays_inside_the_uploaders_scope(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """The legacy modification template names its contract; a row's Selling Entity is the
    performing entity of the line it adds (04 T-IMP-02 rev 1.256; ruling R-114 (g), replacing
    R-41 (5)'s clause): it must exist and need not be covered. Lena's file for Contract 2, of
    Mock Entity 2, is ``CONTRACT_NOT_FOUND`` word for word as an unknown contract — the
    template's rule reads inside Lena's scope —, whichever entity its row sells for; a row that
    adds an obligation to Lena's own Contract 1 sold by Mock Entity 2 is not refused for that
    entity, and its upload names Mock Entity 1 alone; a Selling Entity that does not exist is
    refused by name BEFORE the template's rule and gets no second finding (R-98 (6)), whether
    its contract exists or not. Nothing of a refused file is diffed. Positive control: Lena's
    change of an obligation of Contract 1 validates."""
    replayed(legacy, "02")
    every = legacy.imports
    lena = lena_of(legacy, clock)
    first, second = legacy.entity_ids["Mock Entity 1"], legacy.entity_ids["Mock Entity 2"]
    parameters = {"effective_date": "2023-02-15", "mode": "prospective"}
    code = "legacy_contract_modification"

    def upload(name: str, contract_name: str, pob: str, entity: str) -> tuple[str, dict[str, Any]]:
        return imported(lena, name, modification_file(contract_name, pob, entity), code, parameters)

    # The contract of another entity, the row's own entity inside her scope.
    other_id, other = upload("Mod other.xlsx", "Contract 2", "POB #1", "Mock Entity 1")
    ghost_id, ghost = upload("Mod ghost.xlsx", "Contract 9", "POB #1", "Mock Entity 1")
    assert (other["status"], ghost["status"]) == ("INVALID", "INVALID"), (other, ghost)
    (outside,) = findings_of(every, other_id)
    (unknown,) = findings_of(every, ghost_id)
    assert (outside["code"], unknown["code"]) == ("CONTRACT_NOT_FOUND", "CONTRACT_NOT_FOUND")
    assert outside["message"] == unknown["message"].replace("Contract 9", "Contract 2")
    assert job_ids(every, other_id, "IMPORT_DIFF") == []
    # the upload names the entity of the contract its key names; the row's Selling Entity, the
    # performing entity of a line, is none of its entities (rev 1.256)
    assert named(every, other_id) == [second]
    assert named(every, ghost_id) is None
    # What an approval of either would have to satisfy: the modification, for the entities the
    # upload names — every entity for the unresolved one (``None``) — and, the dry run having
    # stated nothing, unevaluated.
    context = DbContext(tenant_id=every.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        (resolved,) = scope.approval_floor(session, UUID(other_id))
        (unresolved,) = scope.approval_floor(session, UUID(ghost_id))
    assert (resolved.subject_type.value, resolved.entity_ids, resolved.evaluated) == (
        "MODIFICATION",
        frozenset({second}),
        False,
    )
    assert (unresolved.entity_ids, unresolved.evaluated) == (None, False)

    # A Selling Entity outside Lena's scope is the performing entity of the row's line, and is
    # not what refuses the row: a contract outside that scope, or none, answers as above …
    for name, contract_name in (
        ("Mod entity other.xlsx", "Contract 2"),
        ("Mod entity ghost.xlsx", "Contract 9"),
    ):
        refused_id, refused = upload(name, contract_name, "POB #1", "Mock Entity 2")
        assert refused["status"] == "INVALID", refused
        (finding,) = findings_of(every, refused_id)
        assert finding["code"] == "CONTRACT_NOT_FOUND", finding
        assert job_ids(every, refused_id, "IMPORT_DIFF") == []
    # … and a line added to Lena's own contract, which Mock Entity 2 performs, is Lena's to add
    added_id, added = upload("Mod entity add.xlsx", "Contract 1", "POB #9", "Mock Entity 2")
    assert CODE not in {item["code"] for item in findings_of(every, added_id)}, added
    assert added["status"] == "VALIDATED", (added, findings_of(every, added_id))
    assert named(every, added_id) == [first]

    # A Selling Entity that does not exist: refused by name, and not examined further.
    for name, contract_name, pob in (
        ("Mod nobody other.xlsx", "Contract 2", "POB #1"),
        ("Mod nobody ghost.xlsx", "Contract 9", "POB #1"),
        ("Mod nobody add.xlsx", "Contract 1", "POB #9"),
    ):
        refused_id, refused = upload(name, contract_name, pob, "Mock Entity 9")
        assert refused["status"] == "INVALID", refused
        (finding,) = findings_of(every, refused_id)
        assert finding["code"] == CODE, finding
        assert (
            "Legal entity Mock Entity 9 is not available for this import." in finding["message"]
        ), finding
        assert job_ids(every, refused_id, "IMPORT_DIFF") == []

    own_id, own = upload("Mod own.xlsx", "Contract 1", "POB #1", "Mock Entity 1")
    assert own["status"] == "VALIDATED", (own, findings_of(every, own_id))
    assert named(every, own_id) == [first]


def test_r114_a_legacy_line_sold_by_another_entity_is_the_uploaders_to_write(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """Ruling R-114 (g) for the legacy Contract Setup (04 T-IMP-02 rev 1.256): the ``Selling
    Entity`` names the contracting entity on a contract's first row and the line's performing
    entity on every row. Lena's role covers Mock Entity 1. Lena's file sets up Contract 1 — its
    first row of Mock Entity 1 — with its second line sold by Mock Entity 2: no row is refused,
    the upload names Mock Entity 1 alone, Lena submits it, Priya approves, and the contract is
    booked and ACTIVE, of Mock Entity 1, its second obligation performed by Mock Entity 2. The
    same line sold by an entity that does not exist is refused by name on its row. Before: the
    second row was refused for Lena, and the request named both entities."""
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    first = legacy.entity_ids["Mock Entity 1"]
    every = legacy.imports
    lena = lena_of(legacy, clock)
    headers, rows = workbook_rows(SETUP_2023)
    entity = headers.index("Selling Entity")
    own = [row for row in rows if row[entity] == "Mock Entity 1"]  # the rows of Contract 1

    def setup(sold_by: str) -> bytes:
        changed = [list(row) for row in own]
        changed[1][entity] = sold_by  # the second line, POB #2
        return workbook_bytes("Sheet1", headers, changed)

    template = "legacy_contract_setup"
    ghost_id, ghost = imported(lena, "Setup sold by nobody.xlsx", setup("Mock Entity 9"), template)
    assert ghost["status"] == "INVALID", ghost
    found = findings_of(every, ghost_id)
    assert [(item["code"], item["row_number"]) for item in found] == [(CODE, 3)], found
    assert "Legal entity Mock Entity 9 is not available for this import." in found[0]["message"], (
        found[0]
    )

    import_id = diffed(lena, "Setup sold by entity 2.xlsx", setup("Mock Entity 2"), template)
    assert findings_of(every, import_id) == []
    assert named(every, import_id) == [first]
    submitted = submit(lena, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(lena, job_ids(every, import_id, "IMPORT_COMMIT")[-1])
    assert status_of(every, import_id) == "COMMITTED", findings_of(every, import_id)
    stored = every.rows(
        select(contract.c.external_id, contract.c.status, contract.c.contracting_entity_id)
    )
    assert [
        (row["external_id"], str(row["status"]), row["contracting_entity_id"]) for row in stored
    ] == [("Contract 1", "ACTIVE", first)]
    performed = performed_by(every, "Contract 1")
    assert ("POB #2", "Mock Entity 2") in performed
    assert ("POB #1", "Mock Entity 1") in performed


def test_r98_a_scoped_uploader_commits_a_legacy_sku_ssp_file(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """The legacy SKU SSP template names no entity (the book LEGACY-SKU-SSP has none): a
    tenant-level upload, R-41 (5). Lena, whose role covers Mock Entity 1 only, uploads the
    delivered file: it names nothing, runs under the scope of her own session, and is committed
    once an SSP Approver approves it — the version is APPROVED."""
    every = legacy.imports
    lena = lena_of(legacy, clock)
    import_id = diffed(lena, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    assert named(every, import_id) == []
    submitted = submit(lena, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(lena, job_ids(every, import_id, "IMPORT_COMMIT")[-1])
    assert status_of(every, import_id) == "COMMITTED", findings_of(every, import_id)


# --- an API client's upload (rulings R-98 and R-109 (a); 04 rev 1.147 T-IMP-02) ----------------

FILES_PATH = "/api/v1/files"
CLIENT_HOLDS = ("contract.create", "contract.read", "import.upload", "masterdata.maintain")
NOT_AVAILABLE = (
    "Legal entity AVM-US is not available for this import. "
    "Upload these rows under a role that covers the entity."
)


@dataclass(frozen=True, slots=True)
class Client:
    id: UUID
    token: str  # an access token of the client


def client_of(
    cast: Cast, name: str, held: Sequence[str], carried: Sequence[str], **values: Any
) -> Client:
    """World setup by rows (04 T-PLT-15, T-PLT-16): an ACTIVE API client that holds ``held`` and
    an open access token of it that carries ``carried``, as ``POST /oauth/token`` issues one for
    a requested scope."""
    tenant_id = cast.maya.tenant_id
    now = cast.maya.clock.now()
    row = api_client_values(tenant_id, name=name, scopes=sorted(held), **values)
    token = f"erevt_{tenant_id.hex}_{secrets.token_urlsafe(32)}"
    with tenant_session(cast.all_entities()) as session:
        session.execute(insert(api_client).values(**row))
        session.execute(
            insert(api_token).values(
                tenant_id=tenant_id,
                id=new_id(),
                api_client_id=row["id"],
                token_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
                scopes=sorted(carried),
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
    return Client(id=UUID(str(row["id"])), token=token)


def client_upload(
    cast: Cast, client: Client, name: str, content: bytes, template_code: str
) -> tuple[str, UUID]:
    """``POST /files`` and ``POST /imports`` with the client's token: the import id and the id of
    its deferred validation job."""

    def headers() -> dict[str, str]:
        return {"Authorization": f"Bearer {client.token}", "Idempotency-Key": f"k-{uuid4()}"}

    stored = call(
        cast.app,
        "POST",
        FILES_PATH,
        data={"purpose": "IMPORT_SOURCE"},
        files={"file": (name, content, "application/octet-stream")},
        headers=headers(),
    )
    assert stored.status_code == 201, stored.text
    created = call(
        cast.app,
        "POST",
        IMPORTS_PATH,
        json={"file_id": stored.json()["id"], "template_code": template_code},
        headers=headers(),
    )
    assert created.status_code == 202, created.text
    return created.headers[IMPORT_ID_HEADER], UUID(str(created.json()["id"]))


def carried_by(world: ImportWorld, import_id: str) -> list[str] | None:
    value = world.scalar(
        select(import_upload.c.uploader_scopes).where(import_upload.c.id == UUID(import_id))
    )
    return None if value is None else [str(code) for code in value]


def test_r98_an_api_clients_upload_is_held_to_what_its_token_carried(cast: Cast) -> None:
    """R-98 (gap) and R-109 (a). An API client's upload was held to the client's stored scopes:
    a token issued for ``import.upload`` and ``contract.read`` alone imported contracts because
    its CLIENT also holds ``contract.create``, and a scope the client gained after the upload
    widened an upload already made. The upload now keeps what its creating token carried, and
    every stage holds it to the narrower of that and the client's grants in force.

    - The client holds ``contract.create``; this token does not carry it: its ``contracts`` file
      is refused at validation, row by row, with the copy a person whose role does not cover
      the entity gets.
    - The client holds no ``contract.create`` when its token uploads; the client's grant is
      widened before the validation job runs: refused all the same.
    - Positive control: a token that carries ``contract.create`` — validated."""
    world = cast.world
    narrow_scopes = ["contract.read", "import.upload"]

    narrow = client_of(cast, "svc-narrow", CLIENT_HOLDS, narrow_scopes)
    narrow_id, narrow_job = client_upload(
        cast,
        narrow,
        "svc-narrow.csv",
        contracts_csv(world.customer_id, external_id="SVC-US-0001"),
        "contracts",
    )
    run_import_job(cast.maya, narrow_job)
    assert status_of(cast.maya, narrow_id) == "INVALID", findings_of(cast.maya, narrow_id)
    found = findings_of(cast.maya, narrow_id)
    # rows 2 and 3 name AVM-US, the contracting entity; AVM-UK, which performs row 3's line,
    # must exist and need not be covered (rev 1.256), so it raises no finding of its own
    assert [(item["code"], item["row_number"]) for item in found] == [
        (CODE, 2),
        (CODE, 3),
    ], found
    assert NOT_AVAILABLE in found[0]["message"], found[0]
    assert job_ids(cast.maya, narrow_id, "IMPORT_DIFF") == []
    assert carried_by(cast.maya, narrow_id) == narrow_scopes

    late = client_of(cast, "svc-late", narrow_scopes, narrow_scopes)
    late_id, late_job = client_upload(
        cast,
        late,
        "svc-late.csv",
        contracts_csv(world.customer_id, external_id="SVC-US-0002"),
        "contracts",
    )
    with tenant_session(cast.all_entities()) as session:
        session.execute(
            update(api_client).where(api_client.c.id == late.id).values(scopes=list(CLIENT_HOLDS))
        )
    run_import_job(cast.maya, late_job)
    assert status_of(cast.maya, late_id) == "INVALID", findings_of(cast.maya, late_id)
    assert {item["code"] for item in findings_of(cast.maya, late_id)} == {CODE}
    assert carried_by(cast.maya, late_id) == narrow_scopes
    assert (
        cast.maya.rows(select(contract.c.id).where(contract.c.external_id.like("SVC-US-%"))) == []
    )

    wide = client_of(cast, "svc-wide", CLIENT_HOLDS, CLIENT_HOLDS)
    wide_id, wide_job = client_upload(
        cast,
        wide,
        "svc-wide.csv",
        contracts_csv(world.customer_id, external_id="SVC-US-0003"),
        "contracts",
    )
    run_import_job(cast.maya, wide_job)
    assert status_of(cast.maya, wide_id) == "VALIDATED", findings_of(cast.maya, wide_id)
    assert carried_by(cast.maya, wide_id) == list(CLIENT_HOLDS)
    # A person's upload is held to that person's grants and stores no scopes.
    own_id, _ = imported(
        cast.eve,
        "eve-uk.csv",
        contracts_csv(world.customer_id, external_id="EVE-UK-0001", contracting="AVM-UK"),
        "contracts",
    )
    assert carried_by(cast.maya, own_id) is None


def test_r98_the_bounds_of_an_api_clients_upload_are_the_narrower_of_client_and_token(
    cast: Cast,
) -> None:
    """``scope.uploader_bounds`` for an upload an API client created (04 T-IMP-02
    ``uploader_scopes``): the client's grants in force NOW — its scopes, status and entities —
    narrowed to the codes the creating token carried. The client here holds ``contract.create``
    for AVM-UK only."""
    world = cast.world
    uk = world.uk_entity_id
    client = client_of(
        cast,
        "svc-uk",
        ("contract.create", "contract.read", "import.upload"),
        ("import.upload",),
        is_all_entities=False,
        entity_ids=[uk],
    )
    nothing = scope.Bounds(allowed=frozenset(), db_scope=frozenset())
    inside = scope.Bounds(allowed=frozenset({uk}), db_scope=frozenset({uk}))

    def bounds(
        template_code: str, carried: Sequence[str] | None, at: datetime | None = None
    ) -> scope.Bounds:
        upload = {
            "tenant_id": cast.maya.tenant_id,
            "created_by": client.id,
            "created_by_kind": "API_CLIENT",
            "uploader_scopes": None if carried is None else list(carried),
        }
        with tenant_session(cast.all_entities(), read_only=True) as session:
            return scope.uploader_bounds(
                session, upload, template_code, at=at or cast.maya.clock.now()
            )

    # carried and held: the client's entities
    assert bounds("contracts", ["contract.create", "import.upload"]) == inside
    # held by the client, not carried by the token
    assert bounds("contracts", ["import.upload"]) == nothing
    # carried by the token, not held by the client (any more)
    assert bounds("estimates", ["estimate.create", "import.upload"]) == nothing
    # an upload stored without the codes (created before revision 0102): fail closed
    assert bounds("contracts", None) == nothing
    # a tenant-level template runs under the client's own entity scope
    assert bounds("customers", ["import.upload"]) == scope.Bounds(
        allowed=frozenset(), db_scope=frozenset({uk})
    )
    # the client's expiry (12 Sep 2027) and its status are read when the bounds are
    assert (
        bounds("contracts", ["contract.create", "import.upload"], datetime(2027, 9, 13, tzinfo=UTC))
        == nothing
    )
    with tenant_session(cast.all_entities()) as session:
        session.execute(
            update(api_client).where(api_client.c.id == client.id).values(status="REVOKED")
        )
    assert bounds("contracts", ["contract.create", "import.upload"]) == nothing
    # an upload no principal created (a system path) is restricted by no role
    system = {
        "tenant_id": cast.maya.tenant_id,
        "created_by": None,
        "created_by_kind": "SYSTEM",
        "uploader_scopes": None,
    }
    with tenant_session(cast.all_entities(), read_only=True) as session:
        assert scope.uploader_bounds(
            session, system, "contracts", at=cast.maya.clock.now()
        ) == scope.Bounds(allowed="*", db_scope="*")


def test_r98_an_api_client_reads_the_imports_its_entities_cover(cast: Cast) -> None:
    """04 API-R-43 for an API client: ``svc-uk-reader`` holds ``contract.read`` for AVM-UK only.
    Maya's upload naming AVM-US answers it 404 on every import read, exactly as an unknown id,
    and is not listed; her AVM-UK upload and a tenant-level upload are read."""
    world = cast.world
    app = cast.app
    reader = client_of(
        cast,
        "svc-uk-reader",
        ("contract.read",),
        ("contract.read",),
        is_all_entities=False,
        entity_ids=[world.uk_entity_id],
    )
    us_id = diffed(
        cast.maya,
        "maya-us.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30001"),
        "contracts",
    )
    uk_id, _ = imported(
        cast.maya,
        "maya-uk.csv",
        contracts_csv(world.customer_id, external_id="SF-ORD-30002", contracting="AVM-UK"),
        "contracts",
    )
    customers_id, _ = imported(
        cast.maya,
        "maya-customers.csv",
        csv_bytes(CUSTOMER_HEADERS, [["C-503", "Tarn Valley Dairies Ltd (Demo)", "Food", "GB"]]),
        "customers",
    )

    def read(path: str) -> Any:
        return call(app, "GET", path, headers={"Authorization": f"Bearer {reader.token}"})

    unknown = read(f"{IMPORTS_PATH}/{uuid4()}")
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    for path in ("", "/rows", "/diff", "/error-report"):
        answer = read(f"{IMPORTS_PATH}/{us_id}{path}")
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (path, answer.text)
        assert answer.json()["detail"] == unknown.json()["detail"], path
    listed = read(IMPORTS_PATH)
    assert listed.status_code == 200, listed.text
    assert {item["id"] for item in listed.json()["items"]} == {uk_id, customers_id}
    for visible in (uk_id, customers_id):
        assert read(f"{IMPORTS_PATH}/{visible}/rows").status_code == 200, visible


def test_r98_the_header_match_of_an_upload_outside_the_readers_scope_is_not_read(
    cast: Cast,
) -> None:
    """The review's list, reads: ``header_match`` (04 §16.6, API-S-Import) is built from the FILE
    each time the import is read — up to three values of every source column, also of a file
    whose headers did not match the template — so it is served only where the import itself is
    (04 API-R-43). Maya's ``contracts`` file names AVM-US and validates; her second file calls
    the entity column "Selling Co", so it is INVALID at the header and its entities are not
    resolved. Maya reads the samples of both. Eve, whose ``contract.read`` covers AVM-UK only,
    is answered 404 for both, exactly as for an unknown id, with nothing of either file.
    Positive control: Eve's own file with the same header is hers to read, samples included —
    the 404 is the scope, not the state of the upload."""
    world = cast.world
    app, eve = cast.app, cast.eve.actor

    def renamed(content: bytes) -> bytes:
        head, rows = content.split(b"\n", 1)
        return head.replace(b"contracting_entity_code", b"Selling Co") + b"\n" + rows

    def column(shown: dict[str, Any], source_column: str) -> dict[str, Any]:
        (found,) = [
            item for item in shown["header_match"] if item["source_column"] == source_column
        ]
        return dict(found)

    us_file = contracts_csv(world.customer_id, external_id="SF-ORD-31001")
    valid_id, valid = imported(cast.maya, "maya-us.csv", us_file, "contracts")
    assert valid["status"] == "VALIDATED", valid
    assert column(valid, "external_id")["samples"] == ["SF-ORD-31001", "SF-ORD-31001"]
    assert column(valid, "contracting_entity_code")["samples"] == ["AVM-US", "AVM-US"]
    mismatch_id, mismatch = imported(
        cast.maya, "maya-us-renamed.csv", renamed(us_file), "contracts"
    )
    assert mismatch["status"] == "INVALID", mismatch
    assert "TEMPLATE_HEADER_MISMATCH" in {item["code"] for item in mismatch["finding_counts"]}
    assert named(cast.maya, mismatch_id) is None
    assert column(mismatch, "Selling Co") == {
        "source_column": "Selling Co",
        "samples": ["AVM-US", "AVM-US"],
        "template_field": None,
        "match": "NOT_MAPPED",
        "alias_profile_code": None,
    }

    unknown = get(app, f"{IMPORTS_PATH}/{uuid4()}", eve)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    for hidden in (valid_id, mismatch_id):
        answer = get(app, f"{IMPORTS_PATH}/{hidden}", eve)
        assert answer.status_code == 404, answer.text
        body = answer.json()
        assert "header_match" not in body
        assert slug(answer) == "not-found"
        assert (body["title"], body["detail"], body["errors"]) == (
            unknown.json()["title"],
            unknown.json()["detail"],
            unknown.json()["errors"],
        )
        for told in ("SF-ORD-31001", "AVM-US", "Selling Co", "AVM-PLAT-100"):
            assert told not in answer.text, told
    listed = get(app, IMPORTS_PATH, eve)
    assert listed.status_code == 200, listed.text
    assert {valid_id, mismatch_id}.isdisjoint(item["id"] for item in listed.json()["items"])

    # Positive control: her own upload with that header — INVALID and unresolved in the same way.
    own_file = renamed(
        contracts_csv(world.customer_id, external_id="EVE-UK-0009", contracting="AVM-UK")
    )
    own_id, own = imported(cast.eve, "eve-uk-renamed.csv", own_file, "contracts")
    assert own["status"] == "INVALID", own
    assert named(cast.maya, own_id) is None
    assert column(own, "Selling Co")["samples"] == ["AVM-UK", "AVM-UK"]
    assert column(own, "external_id")["samples"] == ["EVE-UK-0009", "EVE-UK-0009"]


def test_apr_content_scope_an_approver_for_one_entity_of_an_import_reads_none_of_its_rows(
    cast: Cast, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item APR-CONTENT-SCOPE-1, the finding itself through the product (04 §16.10 rev 1.208).
    Zoe uploads one file for AVM-UK and AVM-US and submits it; the request names both entities.
    Rhea approves imports for AVM-UK only. Before the ruling she read the request's impact
    preview — the file and its bytes — which states the other entity's contract by its
    external id with its figures, while the import itself answered her 404.

    She is answered the header of the request: its number and status, her own entity and the
    count of all, ``can_decide`` false, and ``content_withheld``. The summary names no import,
    the preview is null, and both file routes answer 404 as the import does. Nothing in her
    answer names AVM-US, either contract or the import. Zoe, who covers both entities, reads
    the whole request and the file (positive control)."""
    world = cast.world
    app = cast.app
    us, uk = world.entity_id, world.uk_entity_id
    zoe_member = colleague(world.place.tenant_id, "zoe")
    zoe = ImportWorld(
        app=app,
        actor=holding(app, zoe_member, "revenue_accountant", entity_ids=[us, uk]),
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )
    own = contracts_csv(world.customer_id, external_id="ZOE-UK-0003", contracting="AVM-UK")
    other = contracts_csv(world.customer_id, external_id="ZOE-US-0003")
    import_id = diffed(zoe, "zoe-mixed.csv", own + other.split(b"\n", 1)[1], "contracts")
    import_no = str(get(app, f"{IMPORTS_PATH}/{import_id}", zoe.actor).json()["import_no"])
    submitted = submit(zoe, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    path = f"{APPROVALS}/{request_id}"

    whole = get(app, path, zoe.actor)
    assert whole.status_code == 200, whole.text
    shown = whole.json()
    preview = shown["impact_preview"]
    assert (shown["content_withheld"], shown["summary"]) == (False, f"Commit import {import_no}")
    assert sorted(ref["code"] for ref in shown["entities"]) == ["AVM-UK", "AVM-US"]
    routes = [f"/api/v1/files/{preview['file_id']}", f"/api/v1/files/{preview['file_id']}/content"]
    document = get(app, routes[1], zoe.actor)
    assert document.status_code == 200, document.text
    assert "ZOE-US-0003" in document.text

    answered = get(app, path, cast.rhea)
    assert answered.status_code == 200, answered.text
    body = answered.json()
    withheld = f"Import commit {shown['request_no']}"
    assert (body["content_withheld"], body["summary"], body["subject"]["display"]) == (
        True,
        withheld,
        withheld,
    )
    assert (body["amount"], body["flags"], body["impact_preview"], body["attachments"]) == (
        None,
        [],
        None,
        [],
    )
    assert (
        body["request_no"],
        body["status"],
        body["can_decide"],
        body["entity"],
        [ref["code"] for ref in body["entities"]],
        body["entity_count"],
    ) == (shown["request_no"], "PENDING", False, None, ["AVM-UK"], 2)
    for word in ("AVM-US", str(us), "ZOE-US-0003", "ZOE-UK-0003", import_no, preview["file_id"]):
        assert str(word) not in answered.text, word
    unknown = get(app, f"/api/v1/files/{uuid4()}/content", cast.rhea)
    for route in routes:
        hidden = get(app, route, cast.rhea)
        assert hidden.status_code == 404, route
        assert slug(hidden) == "not-found", route
        assert {**hidden.json(), "instance": None} == {**unknown.json(), "instance": None}
    upload = get(app, f"{IMPORTS_PATH}/{import_id}", cast.rhea)
    assert (upload.status_code, slug(upload)) == (404, "not-found"), upload.text
    decided = approve(app, request_id, cast.rhea)
    assert (decided.status_code, slug(decided)) == (403, "forbidden"), decided.text
    assert decided.json()["detail"] == EVERY_ENTITY_DETAIL


# --- EXC-IMPORT-SCOPE-1: who reads and acts on the exception item of an import -------------------
#
# 04 T-IMP-05 "An item that names no entity", §15.3 API-R-44, §16.10, T-PLT-30 Subjects (rev
# 1.218); supervisor ruling R-121 (k). Measured before the change, in this world: Eve, a Revenue
# Accountant of AVM-UK alone, is answered 404 for an import of AVM-US and yet lists its finding,
# reads it by id, assigns it, asks a waiver for it and dismisses it.

EXCEPTIONS = "/api/v1/exceptions"
ATTACHMENTS = "/api/v1/attachments"
FILES = "/api/v1/files"
PERIODS = "/api/v1/periods"
COMMANDS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("resolve", {"resolution": "Corrected at the source."}),
    ("reprocess", {}),
    ("request-waiver", {"comment": "Accepted for this period."}),
    ("dismiss", {"comment": "The corrected file follows."}),
)


def bad_cost_events_csv(contract_key: str) -> bytes:
    """One ``cost_events`` row whose amount is no number."""
    return csv_bytes(
        COST_HEADERS,
        [[contract_key, "2026-09-05", "COST_TO_OBTAIN", "not-a-number", "USD", "SALES-2026"]],
    )


def item_rows(world: ImportWorld, import_id: str) -> list[dict[str, Any]]:
    """The exception items of an upload in number order, read without an entity filter."""
    return world.rows(
        select(exception_item)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(exception_item.c.exception_no)
    )


def listed_ids(app: FastAPI, actor: Actor, **params: Any) -> set[str]:
    answer = get(app, EXCEPTIONS, actor, {"limit": 200, **params})
    assert answer.status_code == 200, answer.text
    return {str(item["id"]) for item in answer.json()["items"]}


def answered(
    app: FastAPI, actor: Actor, item_id: str, upload_id: str
) -> tuple[dict[str, Any], Any]:
    """What ``actor`` is answered about the item, answer by answer: whether the list shows it —
    whole, and under its upload — and the status of the read by id and of each of the five
    commands, with the slug of a refusal. Every command is sent whatever the earlier answers were,
    so that ONE comparison states them all; and the answers themselves, for their bodies."""
    sent = {"read": get(app, f"{EXCEPTIONS}/{item_id}", actor)}
    sent["assign"] = post(
        app,
        f"{EXCEPTIONS}/{item_id}/assign",
        actor,
        {"owner_membership_id": str(actor.member.membership_id)},
    )
    for name, body in COMMANDS:
        sent[name] = post(app, f"{EXCEPTIONS}/{item_id}/{name}", actor, body)
    table: dict[str, Any] = {
        "listed": item_id in listed_ids(app, actor),
        "listed under its upload": item_id in listed_ids(app, actor, import_upload_id=upload_id),
    }
    for name, answer in sent.items():
        refused = answer.status_code >= 400
        table[name] = (answer.status_code, slug(answer)) if refused else answer.status_code
    return table, list(sent.values())


def as_unknown() -> dict[str, Any]:
    """``answered`` for an id that names nothing."""
    refused = (404, "not-found")
    return {
        "listed": False,
        "listed under its upload": False,
        "read": refused,
        "assign": refused,
        **dict.fromkeys((name for name, _ in COMMANDS), refused),
    }


def refused_as_unknown(
    cast: Cast, actor: Actor, item_id: str, *, told: Sequence[str], resolver: bool = True
) -> None:
    """The item is no item for ``actor``: not listed — neither whole nor by its upload — and its
    id answers on the read and on each of the five commands exactly as an unknown id does, with
    none of ``told`` in the answer: 404 everywhere for a holder of ``exception.resolve``
    (``as_unknown``); for a member who does not hold it (``resolver`` false), 404 on the read
    and the route's 403 on the commands, which an unknown id answers too. The row is as it was
    and no waiver was asked for."""
    app = cast.app
    before = cast.maya.rows(select(exception_item).where(exception_item.c.id == UUID(item_id)))
    upload_id = str(before[0]["import_upload_id"])
    nothing, unknown = answered(app, actor, str(uuid4()), upload_id)
    assert nothing["read"] == (404, "not-found")
    if resolver:
        assert nothing == as_unknown()
    table, answers = answered(app, actor, item_id, upload_id)
    assert table == nothing
    for answer, same in zip(answers, unknown, strict=True):
        body = answer.json()
        assert (body["title"], body["detail"], body["errors"]) == (
            same.json()["title"],
            same.json()["detail"],
            same.json()["errors"],
        )
        for word in told:
            assert word not in answer.text, word
    after = cast.maya.rows(select(exception_item).where(exception_item.c.id == UUID(item_id)))
    assert after == before
    assert (
        cast.maya.rows(
            select(approval_request.c.id).where(approval_request.c.subject_id == UUID(item_id))
        )
        == []
    )


def reads(cast: Cast, actor: Actor, item_id: str) -> dict[str, Any]:
    """The item is listed for ``actor`` and read by id; the single item."""
    assert item_id in listed_ids(cast.app, actor)
    shown = get(cast.app, f"{EXCEPTIONS}/{item_id}", actor)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


@dataclass(frozen=True, slots=True)
class Readers:
    una: Actor  # Revenue Accountant, AVM-US only
    bo: Actor  # Revenue Accountant, AVM-US and AVM-UK by name: not every entity
    vic: Actor  # Viewer of both entities and Revenue Accountant of AVM-US: reads two, acts in one


def acts_as_nobody(app: FastAPI, actor: Actor, item_id: str, upload_id: str) -> None:
    """``actor`` reads the item and may not act on it: it is listed and read with no available
    action, and each of the five commands answers 404, the answer a holder of
    ``exception.resolve`` for another entity has for an entity-named item."""
    table, answers = answered(app, actor, item_id, upload_id)
    assert table == {
        **as_unknown(),
        "listed": True,
        "listed under its upload": True,
        "read": 200,
    }
    assert answers[0].json()["available_actions"] == []


def readers(cast: Cast) -> Readers:
    world = cast.world
    tenant_id = world.place.tenant_id
    vic = colleague(tenant_id, "vic")
    assign(vic, "viewer", entity_ids=[world.entity_id, world.uk_entity_id])
    return Readers(
        vic=holding(cast.app, vic, "revenue_accountant", entity_ids=[world.entity_id]),
        una=holding(
            cast.app,
            colleague(tenant_id, "una"),
            "revenue_accountant",
            entity_ids=[world.entity_id],
        ),
        bo=holding(
            cast.app,
            colleague(tenant_id, "bo"),
            "revenue_accountant",
            entity_ids=[world.entity_id, world.uk_entity_id],
        ),
    )


def two_entity_finding(cast: Cast) -> tuple[str, str]:
    """Maya's ``contracts`` file for two NEW contracts, SF-ORD-41001 of AVM-US with a price
    that is no number and UK-ORD-41001 of AVM-UK: INVALID, the upload names both entities — by
    its two contracting entities (04 T-IMP-02 rev 1.256: a performing entity is no named
    entity, which is how the file named AVM-UK before) — and its finding names no contract —
    none exists — and no entity. (import id, item id)."""
    world = cast.world
    priced = contracts_csv(
        world.customer_id, external_id="SF-ORD-41001", implementation="not-a-number"
    )
    other = contracts_csv(world.customer_id, external_id="UK-ORD-41001", contracting="AVM-UK")
    import_id, shown = imported(
        cast.maya,
        "maya-two-entities.csv",
        priced + other.split(b"\n", 1)[1],  # one header; rows 2-3 of AVM-US, rows 4-5 of AVM-UK
        "contracts",
    )
    assert shown["status"] == "INVALID", shown
    assert named(cast.maya, import_id) == sorted([world.entity_id, world.uk_entity_id], key=str)
    items = item_rows(cast.maya, import_id)
    assert items, shown
    assert {(row["entity_id"], row["contract_id"]) for row in items} == {(None, None)}
    return import_id, str(items[0]["id"])


def test_exc_import_scope_a_finding_without_an_entity_is_for_the_readers_of_its_import(
    cast: Cast,
) -> None:
    """04 T-IMP-05 "An item that names no entity: who reads it" (rev 1.218): the finding of an
    import that names AVM-US and AVM-UK, and itself no entity, is listed, read and acted on by a
    member who reads that import — Maya, who uploaded it and reads every entity, and Bo, whose
    ``contract.read`` names both entities — and by nobody else: to Eve (AVM-UK alone) and to Una
    (AVM-US alone) its id is an unknown id on the read and on all five commands, and nothing of it
    is written. Reading is not acting (API-R-44 rev 1.218): Vic reads both entities and holds
    ``exception.resolve`` for AVM-US alone — he is shown the item without an action, and his
    commands answer 404. An owner is someone who reads the item: Bo cannot assign it to Una, and
    assigns it to Vic. The item still holds the close of each entity it is: Una is told the count
    of AVM-US's September with it and is not shown it."""
    app = cast.app
    people = readers(cast)
    import_id, item_id = two_entity_finding(cast)

    for outsider in (cast.eve.actor, people.una):
        hidden = get(app, f"{IMPORTS_PATH}/{import_id}", outsider)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
        refused_as_unknown(cast, outsider, item_id, told=("SF-ORD-41001", "not-a-number"))

    for reader in (cast.maya.actor, people.bo):
        shown = reads(cast, reader, item_id)
        assert shown["import_upload_id"] == import_id
        assert "ASSIGN" in shown["available_actions"]
    acts_as_nobody(app, people.vic, item_id, import_id)

    def assigned_to(owner: Actor) -> Any:
        return post(
            app,
            f"{EXCEPTIONS}/{item_id}/assign",
            people.bo,
            {"owner_membership_id": str(owner.member.membership_id)},
        )

    refused = assigned_to(people.una)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("owner_membership_id", "T-IMP-05")]
    assert refused.json()["detail"] == refused.json()["errors"][0]["message"] == OWNER_CANNOT_READ
    (kept,) = cast.maya.rows(select(exception_item).where(exception_item.c.id == UUID(item_id)))
    assert (str(kept["status"]), kept["owner_membership_id"]) == ("OPEN", None)
    assigned = assigned_to(people.vic)
    assert assigned.status_code == 200, assigned.text
    assert (assigned.json()["status"], assigned.json()["owner_membership_id"]) == (
        "IN_PROGRESS",
        str(people.vic.member.membership_id),
    )

    # holding is not reading: the count of AVM-US's September is the same for Una and for Maya,
    # and the list under ``blocking`` shows Una one item fewer
    (september,) = [
        item
        for item in get(app, PERIODS, cast.maya.actor, {"entity": "AVM-US", "limit": 200}).json()[
            "items"
        ]
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    state_id = str(september["id"])
    counts = {
        name: int(get(app, f"{PERIODS}/{state_id}", actor).json()["blockers"]["exceptions_open"])
        for name, actor in (("maya", cast.maya.actor), ("una", people.una))
    }
    assert counts["maya"] == counts["una"] >= 1
    assert item_id in listed_ids(app, cast.maya.actor, blocking=state_id)
    assert listed_ids(app, people.una, blocking=state_id) == (
        listed_ids(app, cast.maya.actor, blocking=state_id) - {item_id}
    )


def test_exc_import_scope_a_finding_on_an_existing_contract_names_it_and_its_entity(
    cast: Cast,
) -> None:
    """04 T-IMP-05 (rev 1.218): a finding on a row names the contract the row names and that
    contract's contracting entity, when the contract exists and lies inside the scope the upload
    writes with. Maya's ``cost_events`` file for SF-ORD-20417, a contract of AVM-US, has one
    amount that is no number: its finding names the contract and AVM-US, and is then an item of
    AVM-US as any other — Una reads and assigns it, Eve (AVM-UK alone) is answered as for an
    unknown id. Before the change the item named neither, and Eve listed it, read it, assigned
    it, asked a waiver for it and dismissed it."""
    app, world = cast.app, cast.world
    people = readers(cast)
    created = post(app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    contract_id = str(created.json()["id"])
    import_id, shown = imported(
        cast.maya, "maya-costs.csv", bad_cost_events_csv("SF-ORD-20417"), "cost_events"
    )
    assert shown["status"] == "INVALID", shown
    assert named(cast.maya, import_id) == [world.entity_id]
    (item,) = item_rows(cast.maya, import_id)
    assert (str(item["contract_id"]), item["entity_id"], item["import_row_id"] is not None) == (
        contract_id,
        world.entity_id,
        True,
    )
    item_id = str(item["id"])

    refused_as_unknown(cast, cast.eve.actor, item_id, told=("SF-ORD-20417", "not-a-number"))
    for reader in (cast.maya.actor, people.una, people.bo):
        seen = reads(cast, reader, item_id)
        assert (seen["contract_id"], seen["contract_external_id"], seen["entity_id"]) == (
            contract_id,
            "SF-ORD-20417",
            str(world.entity_id),
        )
    assigned = post(
        app,
        f"{EXCEPTIONS}/{item_id}/assign",
        people.una,
        {"owner_membership_id": str(people.una.member.membership_id)},
    )
    assert assigned.status_code == 200, assigned.text
    # the import's own reads keep the finding: its entity is one the upload names
    report = get(app, f"{IMPORTS_PATH}/{import_id}", people.una)
    assert report.status_code == 200, report.text
    assert sum(int(count["rows"]) for count in report.json()["finding_counts"]) == 1


def test_exc_import_scope_a_row_refused_for_scope_names_nothing_and_its_uploader_reads_it(
    cast: Cast,
) -> None:
    """04 T-IMP-05 (rev 1.218): a row refused because its contract lies outside the uploader's
    scope names neither the contract nor its entity — the finding answers as for an unknown
    contract, and its uploader reads it on her own row. Eve's ``cost_events`` file names
    SF-ORD-20417 of AVM-US: ``CONTRACT_NOT_FOUND``, the item names nothing, the upload names
    AVM-US. Eve reads the item as the uploader; Una as a reader of the import; Rhea, who reads
    AVM-UK alone and uploaded nothing, does not. Acting asks ``exception.resolve`` for the
    entities the upload names: Una, who holds it for AVM-US, may act; Eve, who holds it for
    AVM-UK, reads her finding without an action. The same file for a contract that does not exist
    leaves the upload unresolved: Eve reads its finding — and may not act on it, as only a holder
    for all entities may —, Una and Bo do not."""
    app, world = cast.app, cast.world
    people = readers(cast)
    created = post(app, CONTRACTS, cast.maya.actor, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    import_id, shown = imported(
        cast.eve, "eve-costs.csv", cost_events_csv("SF-ORD-20417"), "cost_events"
    )
    assert shown["status"] == "INVALID", shown
    assert named(cast.maya, import_id) == [world.entity_id]
    (item,) = item_rows(cast.maya, import_id)
    assert (item["code"], item["contract_id"], item["entity_id"]) == (
        "CONTRACT_NOT_FOUND",
        None,
        None,
    )
    item_id = str(item["id"])
    for reader in (cast.eve.actor, cast.maya.actor, people.una):
        reads(cast, reader, item_id)
    assert "ASSIGN" in reads(cast, people.una, item_id)["available_actions"]
    acts_as_nobody(app, cast.eve.actor, item_id, import_id)
    # Rhea reviews and resolves nothing: the route refuses her commands whatever the id
    refused_as_unknown(cast, cast.rhea, item_id, told=("SF-ORD-20417",), resolver=False)

    ghost_id, ghost = imported(
        cast.eve, "eve-costs-ghost.csv", cost_events_csv("SF-ORD-99999"), "cost_events"
    )
    assert ghost["status"] == "INVALID", ghost
    assert named(cast.maya, ghost_id) is None
    (unknown,) = item_rows(cast.maya, ghost_id)
    assert (unknown["contract_id"], unknown["entity_id"]) == (None, None)
    for reader in (cast.eve.actor, cast.maya.actor):
        reads(cast, reader, str(unknown["id"]))
    assert "ASSIGN" in reads(cast, cast.maya.actor, str(unknown["id"]))["available_actions"]
    acts_as_nobody(app, cast.eve.actor, str(unknown["id"]), ghost_id)
    for outsider in (people.una, people.bo):
        refused_as_unknown(cast, outsider, str(unknown["id"]), told=("SF-ORD-99999",))


def test_exc_import_scope_a_file_level_finding_follows_what_its_upload_names(cast: Cast) -> None:
    """04 T-IMP-05 (rev 1.218), T-IMP-02 ``named_entity_ids``: a finding on the file as a whole
    names no row and no entity. Of an upload that is not resolved — here a header that does not
    match — it is read by the uploader and by a reader of all entities (Marcus) and by nobody
    else, Bo with both entities by name included. Of a tenant-level upload — a ``customers`` file
    — it is read by every holder of ``contract.read`` and acted on by a holder of
    ``exception.resolve`` for all entities alone: Maya; Eve, Una and Bo read it without an
    action."""
    world = cast.world
    people = readers(cast)

    def renamed(content: bytes) -> bytes:
        head, rows = content.split(b"\n", 1)
        return head.replace(b"contracting_entity_code", b"Selling Co") + b"\n" + rows

    mismatch_id, mismatch = imported(
        cast.maya,
        "maya-renamed.csv",
        renamed(contracts_csv(world.customer_id, external_id="SF-ORD-41002")),
        "contracts",
    )
    assert mismatch["status"] == "INVALID", mismatch
    assert named(cast.maya, mismatch_id) is None
    file_level = [row for row in item_rows(cast.maya, mismatch_id) if row["import_row_id"] is None]
    assert [row["code"] for row in file_level] == ["TEMPLATE_HEADER_MISMATCH"]
    item_id = str(file_level[0]["id"])
    for reader in (cast.maya.actor, world.marcus):
        reads(cast, reader, item_id)
    for outsider in (cast.eve.actor, people.una, people.bo):
        refused_as_unknown(cast, outsider, item_id, told=("Selling Co",))

    customers_id, customers = imported(
        cast.maya,
        "maya-customers.csv",
        csv_bytes(CUSTOMER_HEADERS, [["C-502", "", "Logistics", "PT"]]),
        "customers",
    )
    assert customers["status"] == "INVALID", customers
    assert named(cast.maya, customers_id) == []
    tenant_level = item_rows(cast.maya, customers_id)
    assert tenant_level and {row["entity_id"] for row in tenant_level} == {None}
    for reader in (cast.maya.actor, cast.eve.actor, people.una, people.bo):
        reads(cast, reader, str(tenant_level[0]["id"]))
    shown = reads(cast, cast.maya.actor, str(tenant_level[0]["id"]))
    assert "ASSIGN" in shown["available_actions"]
    for reader in (cast.eve.actor, people.una, people.bo):
        acts_as_nobody(cast.app, reader, str(tenant_level[0]["id"]), customers_id)


def test_exc_import_scope_the_waiver_of_an_imports_finding_is_decided_for_its_entities(
    cast: Cast,
    clock: FrozenClock,
) -> None:
    """04 §16.10 (rev 1.218): the ``EXCEPTION_WAIVER`` of an import's finding that names no entity
    is bound to the entities its upload names, as the upload's ``IMPORT_COMMIT`` request is. The
    waiver Maya asks for the finding of the two-entity import names AVM-US and AVM-UK: Rhea, a
    Revenue Reviewer of AVM-UK alone, reads its header and cannot decide it; Priya, a reviewer of
    every entity, approves it and the item is waived. While it is pending it is a pending approval
    of each entity's September. Before the change the request named no entity, and any holder of
    ``exception.waive`` decided it. The waiver of a TENANT-LEVEL upload's finding binds every
    entity (the supervisor's ruling of 2026-10-01): Rhea cannot decide it either."""
    app, world = cast.app, cast.world
    us, uk = world.entity_id, world.uk_entity_id
    assign(world.priya.member, "revenue_reviewer")  # every entity; MFA enrolled
    _, item_id = two_entity_finding(cast)

    def pending(entity_code: str) -> int:
        (september,) = [
            item
            for item in get(
                app, PERIODS, cast.maya.actor, {"entity": entity_code, "limit": 200}
            ).json()["items"]
            if item["period"]["period_key"] == "FY2026-P09"
        ]
        shown = get(app, f"{PERIODS}/{september['id']}", cast.maya.actor)
        assert shown.status_code == 200, shown.text
        return int(shown.json()["blockers"]["approvals_pending"])

    before = {code: pending(code) for code in ("AVM-US", "AVM-UK")}
    asked = post(
        app,
        f"{EXCEPTIONS}/{item_id}/request-waiver",
        cast.maya.actor,
        {"comment": "Accepted: the corrected file follows next week."},
    )
    assert asked.status_code == 200, asked.text
    request_id = str(asked.json()["approval_request_id"])
    bound = cast.maya.rows(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == UUID(request_id))
    )
    assert [
        (row["entity_id"], sorted(row["entity_ids"], key=str), row["is_all_entities"])
        for row in bound
    ] == [(None, sorted([us, uk], key=str), False)]
    assert {code: pending(code) for code in before} == {
        code: count + 1 for code, count in before.items()
    }

    read = get(app, f"{APPROVALS}/{request_id}", cast.rhea)
    assert read.status_code == 200, read.text
    assert (read.json()["can_decide"], read.json()["entity_count"]) == (False, 2)
    refused = approve(app, request_id, cast.rhea)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == EVERY_ENTITY_DETAIL

    priya = world.priya  # enrolled in the world; a Revenue Reviewer of every entity from here on
    decided = approve(app, request_id, priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    (waived,) = cast.maya.rows(select(exception_item).where(exception_item.c.id == UUID(item_id)))
    assert (str(waived["status"]), str(waived["waiver_approval_request_id"])) == (
        "WAIVED",
        request_id,
    )
    assert {code: pending(code) for code in before} == before

    customers_id, customers = imported(
        cast.maya,
        "maya-customers.csv",
        csv_bytes(CUSTOMER_HEADERS, [["C-502", "", "Logistics", "PT"]]),
        "customers",
    )
    assert customers["status"] == "INVALID", customers
    assert named(cast.maya, customers_id) == []
    (finding, *_) = item_rows(cast.maya, customers_id)
    asked = post(
        app,
        f"{EXCEPTIONS}/{finding['id']}/request-waiver",
        cast.maya.actor,
        {"comment": "Accepted: the customer is corrected at the source."},
    )
    assert asked.status_code == 200, asked.text
    tenant_level = str(asked.json()["approval_request_id"])
    (every,) = cast.maya.rows(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == UUID(tenant_level))
    )
    assert (every["entity_id"], list(every["entity_ids"] or ()), every["is_all_entities"]) == (
        None,
        [],
        True,
    )
    # a request that spans every entity is listed for an all-entities scope alone: to Rhea its
    # id is an unknown one
    unseen = get(app, f"{APPROVALS}/{tenant_level}", cast.rhea)
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text
    decided = approve(app, tenant_level, priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def test_exc_import_scope_the_attachments_of_an_imports_finding_follow_its_readers(
    cast: Cast,
) -> None:
    """04 T-PLT-30 Subjects (rev 1.218): the attachments of an exception item are read, and
    added, by the people who read the item. Bo attaches a file to the finding of the two-entity
    import; Maya lists it and reads the file. Una and Eve, who do not read the import, are
    answered for the item's attachments as for a record they do not see, read no byte of the file
    and attach nothing. Before the change the item was a tenant-level record for attachments:
    any holder of ``contract.read`` anywhere opened its files."""
    app = cast.app
    people = readers(cast)
    _, item_id = two_entity_finding(cast)

    def uploaded(actor: Actor) -> str:
        answer = call(
            app,
            "POST",
            FILES,
            data={"purpose": "ATTACHMENT"},
            files={"file": ("evidence.pdf", upload_fixtures.PDF, "application/pdf")},
            headers=cookie_headers(actor.token, actor.csrf_token),
        )
        assert answer.status_code == 201, answer.text
        return str(answer.json()["id"])

    def attach(actor: Actor, file_id: str) -> Any:
        return post(
            app,
            ATTACHMENTS,
            actor,
            {"file_object_id": file_id, "subject_type": "exception_item", "subject_id": item_id},
        )

    subject = {"subject_type": "exception_item", "subject_id": item_id}
    file_id = uploaded(people.bo)
    attached = attach(people.bo, file_id)
    assert attached.status_code == 201, attached.text
    listed = get(app, ATTACHMENTS, cast.maya.actor, subject)
    assert listed.status_code == 200, listed.text
    assert [str(row["file_object_id"]) for row in listed.json()["items"]] == [file_id]
    assert get(app, f"{FILES}/{file_id}/content", cast.maya.actor).status_code == 200

    for outsider in (people.una, cast.eve.actor):
        # a subject the caller does not see lists nothing, and attaching to it is 404
        answer = get(app, ATTACHMENTS, outsider, subject)
        assert (answer.status_code, answer.json()["items"]) == (200, []), answer.text
        for path in (f"{FILES}/{file_id}", f"{FILES}/{file_id}/content"):
            hidden = get(app, path, outsider)
            assert (hidden.status_code, slug(hidden)) == (404, "not-found"), (path, hidden.text)
        refused = attach(outsider, uploaded(outsider))
        assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert len(get(app, ATTACHMENTS, cast.maya.actor, subject).json()["items"]) == 1


def test_apr_rejection_reason_a_quarantine_uploader_is_told_why_her_import_was_rejected(
    cast: Cast, clock: FrozenClock
) -> None:
    """Item APR-REJECTION-REASON-PREPARER-1 (the supervisor's ruling of 2026-10-01; 04 §16.10 rev
    1.240): the comment of a rejection is written to the preparer of the request.

    Eve uploads for AVM-UK, in quarantine mode, a file that also names AVM-US. Her request names
    both entities, so its content is withheld from her and her own request answers its header
    (item APR-CONTENT-SCOPE-1: no exception for the requester). Rita, who approves imports for
    both entities, rejects it and says why. Eve is told why — in the notification, after the
    summary she is shown, and on her read of the request, where that decision's comment is
    answered and nothing else of the content. Rhea approves for AVM-UK and reads the same
    header: she is not the preparer and reads no comment. Rita reads the whole request.

    The decision's reason code goes with its comment (item APR-DECISION-CODE-CONTENT-1; the
    supervisor's ruling of 2026-10-01; 04 §16.10 rev 1.252): it is free text of the decider, so
    Eve reads it with the comment of the rejection, and Rhea reads neither — until then every
    reader of the header read the code.

    Fail-first: the rejection reached Eve as "Rita rejected Import commit APR-….", and the
    decision's comment was null on her read — she could not correct what she was not told."""
    world = cast.world
    app = cast.app
    us, uk = world.entity_id, world.uk_entity_id
    quarantine_mode(cast)
    own = contracts_csv(world.customer_id, external_id="EVE-UK-0004", contracting="AVM-UK")
    other = contracts_csv(world.customer_id, external_id="EVE-US-0004")
    import_id, shown = imported(
        cast.eve, "eve-mixed-4.csv", own + other.split(b"\n", 1)[1], "contracts"
    )
    assert (shown["status"], shown["counts"]["valid"], shown["counts"]["errors"]) == (
        "VALIDATED",
        2,
        2,
    ), shown
    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    path = f"{APPROVALS}/{request_id}"

    # Her own request answers its header: it names AVM-US, which she does not cover.
    before = get(app, path, cast.eve.actor)
    assert before.status_code == 200, before.text
    withheld = f"Import commit {before.json()['request_no']}"
    assert (
        before.json()["content_withheld"],
        before.json()["summary"],
        before.json()["status"],
    ) == (True, withheld, "PENDING")

    # An approver of imports for both entities rejects it and says why.
    rita_member = colleague(world.place.tenant_id, "rita")
    assign(rita_member, "revenue_reviewer", entity_ids=[us, uk])
    rita = enrolled(app, clock, rita_member)
    comment = "The US rows name a customer that is not onboarded."
    code = "customer of the second row is not onboarded"
    rejected = post(app, f"{path}/reject", rita, {"comment": comment, "reason_code": code})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    # Eve is told why, after the summary she is shown ...
    told = cast.maya.rows(
        select(notification.c.title, notification.c.body).where(
            notification.c.kind == "ITEM_REJECTED",
            notification.c.recipient_membership_id == cast.eve.actor.member.membership_id,
        )
    )
    assert [(row["title"], row["body"]) for row in told] == [
        (f"Rejected: {withheld}", f"Rita rejected {withheld}: {comment}")
    ]

    # ... and reads it on her own request: that decision's comment, in an answer still a header.
    after = get(app, path, cast.eve.actor)
    assert after.status_code == 200, after.text
    body = after.json()
    assert (body["status"], body["content_withheld"], body["summary"]) == (
        "REJECTED",
        True,
        withheld,
    )
    assert (body["subject"]["display"], body["amount"], body["flags"]) == (withheld, None, [])
    assert (body["impact_preview"], body["attachments"]) == (None, [])
    assert [
        (decision["decision"], decision["comment"], decision["reason_code"])
        for step in body["steps"]
        for decision in step["decisions"]
    ] == [("REJECT", comment, code)]
    for word in ("AVM-US", str(us), "EVE-US-0004", "EVE-UK-0004"):
        assert word not in after.text, word

    # Rhea reads the same header and is not the preparer: no comment.
    header = get(app, path, cast.rhea)
    assert header.status_code == 200, header.text
    assert header.json()["content_withheld"] is True
    assert [
        (decision["decision"], decision["comment"], decision["reason_code"])
        for step in header.json()["steps"]
        for decision in step["decisions"]
    ] == [("REJECT", None, None)]
    assert comment not in header.text
    assert code not in header.text

    # Positive control: Rita covers both entities and reads the whole request.
    whole = get(app, path, rita)
    assert whole.status_code == 200, whole.text
    assert whole.json()["content_withheld"] is False
    assert [
        (decision["comment"], decision["reason_code"])
        for step in whole.json()["steps"]
        for decision in step["decisions"]
    ] == [(comment, code)]


def test_apr_request_reason_a_quarantine_uploader_reads_the_comment_she_submitted_with(
    cast: Cast, clock: FrozenClock
) -> None:
    """Item APR-REQUEST-REASON-1 (supervisor rulings R-83 (d) and R-104 (a); the ruling of
    2026-10-01; 04 §16.10 rev 1.252): a request answers the comment it was submitted with, and
    the comment is content.

    Eve uploads for AVM-UK, in quarantine mode, a file that also names AVM-US, and submits it
    with a comment. Her request names both entities, so it answers her its header — and her
    comment, because she wrote it. Rhea approves for AVM-UK and reads the same header without
    it. Rita approves imports for both entities and reads it with the whole request: the
    justification she decides on (SCREENS §15.4 region 3). The command takes no reason code, so
    the request states none.

    Fail-first: API-S-Approval had no member for it — the approver read no justification."""
    world = cast.world
    app = cast.app
    us, uk = world.entity_id, world.uk_entity_id
    quarantine_mode(cast)
    own = contracts_csv(world.customer_id, external_id="EVE-UK-0005", contracting="AVM-UK")
    other = contracts_csv(world.customer_id, external_id="EVE-US-0005")
    import_id, shown = imported(
        cast.eve, "eve-mixed-5.csv", own + other.split(b"\n", 1)[1], "contracts"
    )
    assert shown["status"] == "VALIDATED", shown
    (diff_job,) = job_ids(cast.maya, import_id, "IMPORT_DIFF")
    run_import_job(cast.eve, diff_job)
    submitted = submit(cast.eve, import_id)
    assert submitted.status_code == 200, submitted.text
    path = f"{APPROVALS}/{submitted.json()['approval_request_id']}"
    rita_member = colleague(world.place.tenant_id, "rita")
    assign(rita_member, "revenue_reviewer", entity_ids=[us, uk])
    rita = enrolled(app, clock, rita_member)

    def submitted_with(actor: Actor) -> tuple[bool, str | None, str | None]:
        answered = get(app, path, actor)
        assert answered.status_code == 200, answered.text
        body = answered.json()
        return body["content_withheld"], body["reason_code"], body["comment"]

    # Her own request answers its header, and the comment she submitted it with.
    assert submitted_with(cast.eve.actor) == (True, None, "new order")
    # Rhea reads the same header and wrote nothing of it: no comment.
    assert submitted_with(cast.rhea) == (True, None, None)
    assert "new order" not in get(app, path, cast.rhea).text
    # Positive control: Rita covers both entities and reads the justification she decides on.
    assert submitted_with(rita) == (False, None, "new order")


def test_read_scope_301_an_import_is_submitted_for_the_entity_its_rows_name(cast: Cast) -> None:
    """Item READ-SCOPE-BY-PERMISSION-1 (register index 301; 04 §16.10 rev 1.319 "The request's
    row is the kernel's"; lane SECFIX-APR's reading; the supervisor's ruling of 2026-10-03): an
    import's submission is the one place where three scopes meet. Its route asks
    ``import.upload``; its rows are bound by the template's write permission (R-29); and its
    preparer is asked whether she reads what she submits (R-64 (6)). Ana is an SSP Analyst of
    AVM-UK and a Revenue Accountant of AVM-US: ``import.upload`` is hers for AVM-US alone,
    ``ssp.create`` and the reads for AVM-UK. Her ``ssp_values`` file for a book of AVM-UK is
    validated, diffed and submitted: the ``IMPORT_COMMIT`` request names AVM-UK, is PENDING and
    hers, and nothing is refused on record.

    Measured before the kernel's statements moved under the tenant's scope (2026-10-03, with the
    route's transaction already under ``import.upload``): 403 ``forbidden`` without a detail —
    the row policy's check refused the insert of a request of AVM-UK — and the import stayed
    DIFF_READY. On the base of the item the union of her roles let it through."""
    world, place = cast.world, cast.world.place
    us, uk = world.entity_id, world.uk_entity_id
    _ssp_book(world, "UK-LIST", "AVM-UK")
    someone = colleague(place.tenant_id, "ana")
    assign(someone, "ssp_analyst", entity_ids=[uk])
    ana = ImportWorld(
        app=cast.app,
        actor=holding(cast.app, someone, "revenue_accountant", entity_ids=[us]),
        runtime=cast.maya.runtime,
        clock=cast.maya.clock,
    )
    with tenant_session(cast.all_entities(), read_only=True) as session:
        held = effective_grants(session, someone.membership_id, at=cast.maya.clock.now())
    assert held.permission_scopes["import.upload"] == frozenset({us})
    assert held.permission_scopes["ssp.create"] == frozenset({uk})
    assert held.permission_scopes["contract.read"] == frozenset({us, uk})

    row = _ssp_row(
        PLATFORM_100, "2026-H2-UK", ssp_book_code="UK-LIST", **{"lines.value_basis": "AMOUNT"}
    )
    import_id = diffed(ana, "ana-uk.csv", csv_bytes(SSP_HEADERS, [row]), "ssp_values")
    assert named(ana, import_id) == [uk]
    sent = submit(ana, import_id)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED"
    assert status_of(ana, import_id) == "SUBMITTED"
    assert denied(ana, import_id) == []
    (request,) = ana.rows(
        select(
            approval_request.c.id,
            approval_request.c.entity_id,
            approval_request.c.status,
            approval_request.c.preparer_id,
        ).where(approval_request.c.subject_id == UUID(import_id))
    )
    assert (request["entity_id"], str(request["status"])) == (uk, "PENDING")
    assert request["preparer_id"] == someone.user_id
    assert str(request["id"]) == sent.json()["approval_request_id"]
    # her own import is hers to read, and its request too
    assert get(cast.app, f"{IMPORTS_PATH}/{import_id}", ana.actor).status_code == 200
    assert get(cast.app, f"{APPROVALS}/{request['id']}", ana.actor).status_code == 200
