"""DIN-3 submit, approval, atomic commit, quarantine mode and control totals (05 IPL-06 to IPL-12;
04 T-IMP-02, T-IMP-04, T-PLT-31 ``data.quarantine_failed_rows``, table 15.4-B; PRD SM-05, §2.5
``IMPORT_COMMIT`` and ``AUTO-IMP-01``, BR-DAT-01 to BR-DAT-05, IMP-43, NTF-11; 03 REQ-DAT-001,
REQ-DAT-008, REQ-DAT-010, REQ-PLT-014, REQ-PLT-026; controls CTL-001, CTL-044; BUILD_SPEC DIN-3).

Worlds: ``support.factories.import_world`` (Maya, Revenue Accountant, uploads CSV v2 ``customers``
files; Priya, Revenue Reviewer with MFA, approves) and ``support.factories.j03_world`` for the
``contracts`` template. Jobs run as the worker runs them.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
import io
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals.engine import EVERY_ENTITY_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_request,
    audit_event,
    contract,
    contract_event,
    contract_version,
    customer,
    exception_item,
    import_row_lineage,
    import_upload,
    job,
    notification,
    source_record,
)
from erev_api.domain.imports import commit, csv_v2, upload
from erev_api.enums import (
    ContractEventType,
    FilePurpose,
    PrincipalKind,
    RegistryCategory,
    RuleSetKind,
    TenantKind,
)
from erev_api.events.payloads import MemoUpdatedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore, store_file
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.schemas.imports import ImportCreateIn, ImportSubmitIn
from erev_api.uow import UnitOfWork, unit_of_work
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    ImportWorld,
    J03World,
    appended,
    booked_contract,
    create_import,
    import_world,
    imported,
    j03_world,
    maya_principal,
    run_import_job,
    sf_ord_20417_body,
    upload_import_source,
)
from support.http import call
from support.principals import Actor, carrying, colleague, cookie_headers, enrolled
from support.reference import approve, assign, get
from support.rows import api_client_values, publish_registry_version, publish_rule_set

CUSTOMER_HEADERS = ("code", "name", "segment", "country_code")
CUSTOMERS = (
    ("C-501", "Harbourline Freight Ltd (Demo)", "Logistics", "PT"),
    ("C-502", "Orla Quay Foods SA (Demo)", "Food", "ES"),
    ("C-503", "Tamsin Row Studios LLP (Demo)", "Media", "GB"),
)
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


def customers_csv(rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CUSTOMER_HEADERS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def contracts_csv(
    customer_id: UUID,
    *,
    external_id: str = "SF-ORD-30001",
    implementation: str = "24000.00",
    contracting: str = "AVM-US",
) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CONTRACT_HEADERS)
    header = [external_id, str(customer_id), contracting, "USD", "2026-09-01", external_id]
    writer.writerow(
        [*header, "O1", "AVM-PLAT-100", "1", "96000.00", "USD", "2026-09-01", "2027-08-31", ""]
    )
    writer.writerow([*header, "O2", "AVM-IMPL-PLUS", "1", implementation, "USD", "", "", "AVM-UK"])
    return buffer.getvalue().encode("utf-8")


def job_of(world: ImportWorld, import_id: UUID, kind: str) -> UUID:
    rows = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == import_id, job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    assert rows, f"no {kind} job for {import_id}"
    return UUID(str(rows[-1]["id"]))


def shown(world: ImportWorld, import_id: str) -> dict[str, Any]:
    response = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor)
    assert response.status_code == 200, response.text
    return dict(response.json())


def diffed(world: ImportWorld, name: str, content: bytes, template_code: str) -> str:
    """Upload, validate and diff a file; the import id of a DIFF_READY import."""
    import_id, validated = imported(world, name, content, template_code)
    assert validated["status"] == "VALIDATED", validated
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_DIFF"))
    assert shown(world, import_id)["status"] == "DIFF_READY"
    return import_id


def submit(world: ImportWorld, import_id: str, *, key: str | None = None) -> Any:
    headers = cookie_headers(
        world.actor.token,
        world.actor.csrf_token,
        key=False,
        **{"Idempotency-Key": key or f"k-{uuid4()}"},
    )
    return call(
        world.app,
        "POST",
        f"{IMPORTS_PATH}/{import_id}/submit",
        json={"comment": "Customer master from the CRM export"},
        headers=headers,
    )


def reviewer(world: ImportWorld) -> Actor:
    someone = colleague(world.tenant_id, "priya")
    assign(someone, "revenue_reviewer")
    return enrolled(world.app, world.clock, someone)


def committed(world: ImportWorld, import_id: str, approver: Actor) -> dict[str, Any]:
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_COMMIT"))
    return shown(world, import_id)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ImportWorld:
    return import_world(app, keyring, clock, files)


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    return j03_world(app, keyring, clock, files)


@pytest.fixture
def contract_importer(
    j03: J03World, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ImportWorld:
    return ImportWorld(
        app=j03.app,
        actor=j03.place.author,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )


def test_customers_csv_full_pipeline(world: ImportWorld) -> None:
    priya = reviewer(world)
    file_id = upload_import_source(world, "crm-customers.csv", customers_csv(CUSTOMERS))
    created = create_import(world, file_id, "customers")
    assert created.status_code == 202, created.text
    import_id = created.headers["X-Erev-Import-Id"]
    upload_id = UUID(import_id)
    assert shown(world, import_id)["status"] == "UPLOADED"
    run_import_job(world, UUID(str(created.json()["id"])))
    validated = shown(world, import_id)
    assert (validated["status"], validated["counts"]["rows"], validated["counts"]["valid"]) == (
        "VALIDATED",
        3,
        3,
    ), validated
    run_import_job(world, job_of(world, upload_id, "IMPORT_DIFF"))
    ready = shown(world, import_id)
    assert ready["status"] == "DIFF_READY"
    assert ready["diff_summary"]["contracts_affected"] == 0

    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "SUBMITTED"
    request_id = UUID(str(body["approval_request_id"]))
    (request,) = world.rows(select(approval_request).where(approval_request.c.id == request_id))
    assert (request["subject_type"], request["subject_id"], request["status"]) == (
        "IMPORT_COMMIT",
        upload_id,
        "PENDING",
    )
    decided = approve(world.app, str(request_id), priya)
    assert decided.status_code == 200, decided.text
    assert shown(world, import_id)["status"] == "APPROVED"
    run_import_job(world, job_of(world, upload_id, "IMPORT_COMMIT"))

    done = shown(world, import_id)
    assert done["status"] == "COMMITTED"
    assert done["committed_at"] is not None
    assert done["control_totals"]["source"]["rows"] == done["control_totals"]["loaded"]["rows"] == 3
    stored = world.rows(
        select(customer.c.code, customer.c.name, customer.c.source_system)
        .where(customer.c.code.in_([row[0] for row in CUSTOMERS]))
        .order_by(customer.c.code)
    )
    assert [(row["code"], row["name"], str(row["source_system"])) for row in stored] == [
        (code, name, "CSV_V2") for code, name, _, _ in CUSTOMERS
    ]
    lineage = world.rows(
        select(import_row_lineage.c.import_row_id, import_row_lineage.c.target_type).where(
            import_row_lineage.c.import_upload_id == upload_id
        )
    )
    by_type = sorted(str(row["target_type"]) for row in lineage)
    assert by_type == ["customer"] * 3 + ["source_record"] * 3
    assert len({row["import_row_id"] for row in lineage}) == 3
    assert (
        world.scalar(
            select(func.count())
            .select_from(source_record)
            .where(source_record.c.import_upload_id == upload_id)
        )
        == 3
    )
    statuses = [
        (row["before"], row["after"])
        for row in world.rows(
            select(
                import_upload.c.status.label("after"), import_upload.c.status.label("before")
            ).where(import_upload.c.id == upload_id)
        )
    ]
    assert statuses == [("COMMITTED", "COMMITTED")]


@pytest.mark.parametrize("failure_stage", [None, "commit", "compute"])
def test_import_events_carry_row_lineage(
    j03: J03World,
    contract_importer: ImportWorld,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str | None,
) -> None:
    import_id = diffed(
        contract_importer, "sf-ord-30001.csv", contracts_csv(j03.customer_id), "contracts"
    )
    assign(j03.priya.member, "revenue_reviewer")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Injected failure after scheduling computation")

    if failure_stage == "commit":
        monkeypatch.setattr(commit, "_recorded", fail)
    done = committed(contract_importer, import_id, j03.priya)
    if failure_stage == "commit":
        assert done["status"] == "FAILED", done
        assert (
            contract_importer.rows(
                select(job.c.id).where(
                    job.c.params["import_upload_id"].astext == import_id,
                    job.c.kind == "CONTRACT_COMPUTE",
                )
            )
            == []
        )
        assert (
            contract_importer.rows(
                select(contract.c.id).where(contract.c.external_id == "SF-ORD-30001")
            )
            == []
        )
        return
    assert done["status"] == "COMMITTED", done
    (booked,) = contract_importer.rows(
        select(contract.c.id).where(contract.c.external_id == "SF-ORD-30001")
    )
    response = get(j03.app, f"/api/v1/contracts/{booked['id']}/events", j03.place.author)
    assert response.status_code == 200, response.text
    (event,) = response.json()["items"]
    assert (event["event_type"], event["origin"], event["import_upload_id"]) == (
        "CONTRACT_BOOKED",
        "IMPORT",
        import_id,
    )
    assert event["source_row"] == {"import_upload_id": import_id, "sheet": "CSV", "row_number": 2}
    # 04 T-PLT-19 rev 1.154: the append's audit event names the contract and the import, so the
    # contract's trail names the commit that booked it (the commit's own events name no contract).
    (append,) = contract_importer.rows(
        select(audit_event.c.detail).where(
            audit_event.c.action == "contract_event.append",
            audit_event.c.detail["contract_id"].astext == str(booked["id"]),
        )
    )
    assert append["detail"]["import_upload_id"] == import_id
    assert append["detail"]["ids"] == [event["id"]]
    (record,) = contract_importer.rows(
        select(source_record.c.id, source_record.c.external_id).where(
            source_record.c.id == UUID(str(event["source_record_id"]))
        )
    )
    assert record["external_id"] == f"{import_id}:CSV:2"
    lineage = contract_importer.rows(
        select(import_row_lineage.c.target_type, import_row_lineage.c.target_id).where(
            import_row_lineage.c.import_upload_id == UUID(import_id),
            import_row_lineage.c.target_type == "contract_event",
        )
    )
    assert [str(row["target_id"]) for row in lineage] == [event["id"], event["id"]]
    # Two source rows for the same contract schedule exactly one post-commit computation.
    (child,) = contract_importer.rows(
        select(job.c.id, job.c.parent_job_id, job.c.state, job.c.params).where(
            job.c.kind == "CONTRACT_COMPUTE",
            job.c.params["import_upload_id"].astext == import_id,
        )
    )
    assert child["state"] == "QUEUED" and child["parent_job_id"] is not None
    assert len(child["params"]["combination_group_ids"]) == 1
    if failure_stage == "compute":
        from erev_api.domain.contracts import compute_job

        monkeypatch.setattr(compute_job, "compute_group", fail)
    run_import_job(contract_importer, child["id"])
    (computed,) = contract_importer.rows(select(job).where(job.c.id == child["id"]))
    if failure_stage == "compute":
        assert computed["state"] == "FAILED", computed
    else:
        assert computed["state"] == "SUCCEEDED", computed["problem"]
        assert computed["result"]["counts"]["succeeded"] == 1
    (upload_state,) = contract_importer.rows(
        select(import_upload.c.status).where(import_upload.c.id == UUID(import_id))
    )
    assert upload_state["status"] == "COMMITTED"
    assert contract_importer.rows(
        select(contract_event.c.id).where(contract_event.c.id == UUID(event["id"]))
    )


def test_import_commit_needs_approval_rights_for_every_named_entity(
    j03: J03World, contract_importer: ImportWorld
) -> None:
    """Security review SC-5 (supervisor rulings R-25, R-29, R-41 (5) and R-87 (1); 04 §16.10 rev
    1.104 "Entity scope of a request"; REQ-PLT-012): an ``IMPORT_COMMIT`` request names every
    entity the upload's rows write for — the set the validation job stores on the upload
    (T-IMP-02 ``named_entity_ids``), which the approvals kernel reads through the imports domain.
    The file books a contract of AVM-US and a contract of AVM-UK: the request names both. Rhea,
    whose ``import.approve`` covers AVM-UK only (Rhea approved the import of an AVM-US contract
    before the fix), reads the request and cannot decide it, and nothing is committed; Priya,
    Revenue Reviewer for all entities, approves it and the import commits. (Until the imports
    domain stored the set, the kernel read such an upload as spanning every entity and the request
    was hidden from Rhea: STALE EXPECTATION under R-87 (1). Until 04 T-IMP-02 rev 1.256 the file
    named AVM-UK by the entity that performs a line of its AVM-US contract; a performing entity
    is no named entity since — ruling R-114 (g), replacing R-41 (5)'s clause —, so the file
    names its two entities by two contracts: STALE TEST WORLD.)"""
    of_uk = contracts_csv(j03.customer_id, external_id="UK-ORD-30001", contracting="AVM-UK")
    import_id = diffed(
        contract_importer,
        "sf-ord-30001.csv",
        contracts_csv(j03.customer_id) + of_uk.split(b"\n", 1)[1],  # one header, two contracts
        "contracts",
    )
    submitted = submit(contract_importer, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    (scope,) = contract_importer.rows(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == UUID(request_id))
    )
    assert (scope["entity_id"], sorted(scope["entity_ids"]), scope["is_all_entities"]) == (
        None,
        sorted([j03.entity_id, j03.uk_entity_id]),
        False,
    )

    rhea_member = colleague(contract_importer.tenant_id, "rhea")
    assign(rhea_member, "revenue_reviewer", entity_ids=[j03.uk_entity_id])
    rhea = enrolled(j03.app, contract_importer.clock, rhea_member)
    detail = get(j03.app, f"/api/v1/approvals/{request_id}", rhea)
    assert detail.status_code == 200, detail.text
    assert (detail.json()["can_decide"], detail.json()["entity_count"]) == (False, 2)
    refused = approve(j03.app, request_id, rhea)
    assert refused.status_code == 403, refused.text
    assert refused.json()["type"].endswith("/forbidden")
    assert refused.json()["detail"] == EVERY_ENTITY_DETAIL
    assert shown(contract_importer, import_id)["status"] == "SUBMITTED"
    booked = select(contract.c.contracting_entity_id).where(
        contract.c.external_id == "SF-ORD-30001"
    )
    assert contract_importer.rows(booked) == []

    # Positive control: import.approve for all entities decides it, and the import commits.
    assign(j03.priya.member, "revenue_reviewer")
    decided = approve(j03.app, request_id, j03.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(contract_importer, job_of(contract_importer, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(contract_importer, import_id)["status"] == "COMMITTED"
    assert contract_importer.rows(booked) == [{"contracting_entity_id": j03.entity_id}]


def test_change_since_diff_voids_approval(j03: J03World, contract_importer: ImportWorld) -> None:
    booked = booked_contract(j03.place, sf_ord_20417_body(j03.customer_id), activate=False)
    contract_id = UUID(str(booked.contract["id"]))
    import_id = diffed(
        contract_importer,
        "sf-ord-20417-replace.csv",
        contracts_csv(j03.customer_id, external_id="SF-ORD-20417", implementation="20000.00"),
        "contracts",
    )
    ready = shown(contract_importer, import_id)
    assert (
        ready["diff_summary"]["contracts_affected"],
        ready["diff_summary"]["contracts_created"],
    ) == (1, 0)
    submitted = submit(contract_importer, import_id)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])

    # An event reaches the affected contract between the diff and the approval.
    appended(
        j03.place,
        contract_id,
        1,
        [
            EventIn(
                event_type=ContractEventType.MEMO_UPDATED,
                effective_date=date(2026, 9, 2),
                payload=MemoUpdatedV1(memo_1="Customer asked for a call"),
            )
        ],
    )
    assign(j03.priya.member, "revenue_reviewer")
    decided = approve(j03.app, request_id, j03.priya)
    assert decided.status_code == 409, decided.text
    assert decided.json()["type"].endswith("stale-approval")
    (request,) = contract_importer.rows(
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(request_id)
        )
    )
    assert (request["status"], request["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert shown(contract_importer, import_id)["status"] == "REJECTED"
    assert (
        contract_importer.rows(
            select(job.c.id).where(
                job.c.subject_id == UUID(import_id), job.c.kind == "IMPORT_COMMIT"
            )
        )
        == []
    )
    events = contract_importer.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    assert [str(row["event_type"]) for row in events] == ["CONTRACT_BOOKED", "MEMO_UPDATED"]


def test_quarantine_mode_commits_valid_rows(
    world: ImportWorld, app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    rows = [
        ("C-601", "Kestrel Mill Paper Co (Demo)", "Industrial", "US"),
        ("C-602", "Wren Harbour Ales Ltd (Demo)", "Food", "GB"),
        ("C-603", "", "Media", "FR"),
    ]
    content = customers_csv(rows)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )
    priya = reviewer(world)
    import_id, validated = imported(world, "quarantine.csv", content, "customers")
    assert validated["is_quarantine_mode"] is True
    assert (validated["status"], validated["counts"]["valid"], validated["counts"]["errors"]) == (
        "VALIDATED",
        2,
        1,
    ), validated
    run_import_job(world, job_of(world, UUID(import_id), "IMPORT_DIFF"))
    done = committed(world, import_id, priya)
    assert done["status"] == "COMMITTED", done
    assert done["control_totals"]["loaded"] == {"rows": 2, "quarantined": 1}
    codes = [
        row["code"]
        for row in world.rows(
            select(customer.c.code).where(customer.c.code.in_(["C-601", "C-602", "C-603"]))
        )
    ]
    assert sorted(codes) == ["C-601", "C-602"]
    items = world.rows(
        select(exception_item.c.code, exception_item.c.status, exception_item.c.field).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert [(row["code"], row["status"], row["field"]) for row in items] == [
        ("REQUIRED_VALUE_BLANK", "OPEN", "name")
    ]

    # With the default ``false`` the same file is INVALID.
    other = import_world(app, keyring, clock, files)
    _, refused = imported(other, "quarantine.csv", content, "customers")
    assert (refused["status"], refused["is_quarantine_mode"]) == ("INVALID", False)


def test_control_totals_mismatch_fails_batch(
    world: ImportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    priya = reviewer(world)
    import_id = diffed(world, "crm-customers.csv", customers_csv(CUSTOMERS), "customers")
    upload_id = UUID(import_id)
    original = csv_v2.TEMPLATES["customers"]

    def dropping(rows: Any) -> Any:
        return original.plans(rows)[:-1]

    monkeypatch.setattr(
        csv_v2, "TEMPLATES", {"customers": dataclasses.replace(original, plans=dropping)}
    )
    done = committed(world, import_id, priya)

    assert done["status"] == "FAILED", done
    assert world.rows(select(customer.c.code).where(customer.c.code.in_(["C-501", "C-502"]))) == []
    assert (
        world.rows(select(source_record.c.id).where(source_record.c.import_upload_id == upload_id))
        == []
    )
    assert (
        world.rows(
            select(import_row_lineage.c.id).where(
                import_row_lineage.c.import_upload_id == upload_id
            )
        )
        == []
    )
    (item,) = world.rows(
        select(exception_item).where(
            exception_item.c.import_upload_id == upload_id,
            exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
        )
    )
    membership_id = world.actor.member.membership_id
    assert (item["source"], item["severity"], item["status"], item["owner_membership_id"]) == (
        "IMPORT",
        "BLOCKING",
        "OPEN",
        membership_id,
    )
    assert item["message"] == (
        f"Control totals do not match for {done['import_no']}: source 3 records, no amounts; "
        "loaded 2 records, no amounts. Nothing was committed."
    )
    notes = world.rows(
        select(
            notification.c.kind, notification.c.title, notification.c.recipient_membership_id
        ).where(notification.c.subject_id == item["id"])
    )
    assert [(row["kind"], row["title"], row["recipient_membership_id"]) for row in notes] == [
        ("EXCEPTION_ASSIGNED", "Exception: CONTROL_TOTALS_MISMATCH", membership_id)
    ]


@contextmanager
def _unit(world: ImportWorld, principal: Principal) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-import-api-client",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=world.clock.now(),
        format_locale="en-US",
    )
    runtime = world.runtime
    assert runtime.keyring is not None and runtime.files is not None
    with unit_of_work(ctx, clock=world.clock, keyring=runtime.keyring, files=runtime.files) as uow:
        yield uow


def test_api_client_upload_auto_approved(world: ImportWorld) -> None:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    client = api_client_values(world.tenant_id, name="svc-salesforce")
    with tenant_session(context) as session:
        session.execute(insert(api_client).values(**client))
        version_id, rule_ids = publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="AVM-AUTO-APPROVAL",
            rules=[
                {
                    "rule_key": "AUTO-IMP-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"},
                        {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    permissions = frozenset({"import.upload", "contract.read"})
    service = dataclasses.replace(
        maya_principal(world.actor.member),
        kind=PrincipalKind.API_CLIENT,
        id=UUID(str(client["id"])),
        membership_id=None,
        display_name="svc-salesforce",
        roles=(),
        permissions=permissions,
        permission_scopes=MappingProxyType({code: "*" for code in permissions}),
    )
    with _unit(world, service) as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.IMPORT_SOURCE,
            stream=io.BytesIO(customers_csv(CUSTOMERS)),
            original_filename="svc-salesforce-customers.csv",
            media_type="text/csv",
        )
        created = upload.create_import(
            uow, body=ImportCreateIn(file_id=stored["id"], template_code="customers")
        )
        uow.commit()
    run_import_job(world, created.job.id)
    run_import_job(world, job_of(world, created.import_id, "IMPORT_DIFF"))
    with _unit(world, service) as uow:
        out = commit.submit_import(uow, import_id=created.import_id, body=ImportSubmitIn())
        uow.commit()
    assert out.status == "APPROVED"
    assert out.approval_request_id is not None
    (decision,) = world.rows(
        select(approval_decision.c.decision, approval_decision.c.auto_rule_set_version_id).where(
            approval_decision.c.approval_request_id == out.approval_request_id
        )
    )
    assert (decision["decision"], decision["auto_rule_set_version_id"]) == (
        "AUTO_APPROVE",
        version_id,
    )
    assert "AUTO-IMP-01" in rule_ids
    run_import_job(world, job_of(world, created.import_id, "IMPORT_COMMIT"))
    done = shown(world, str(created.import_id))
    assert done["status"] == "COMMITTED", done
    assert done["control_totals"]["loaded"]["rows"] == 3


def test_submit_retry_same_idempotency_key(world: ImportWorld) -> None:
    import_id = diffed(world, "crm-customers.csv", customers_csv(CUSTOMERS), "customers")
    key = f"k-{uuid4()}"
    first = submit(world, import_id, key=key)
    again = submit(world, import_id, key=key)
    assert first.status_code == again.status_code == 200, again.text
    assert again.json() == first.json()
    assert (
        world.scalar(
            select(func.count())
            .select_from(approval_request)
            .where(approval_request.c.subject_id == UUID(import_id))
        )
        == 1
    )
    assert shown(world, import_id)["status"] == "SUBMITTED"


@pytest.mark.control("CTL-044")
def test_ctl_044_uploader_cannot_approve_import(world: ImportWorld) -> None:
    import_id = diffed(world, "crm-customers.csv", customers_csv(CUSTOMERS), "customers")
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    assign(world.actor.member, "revenue_reviewer")
    uploader = enrolled(world.app, world.clock, world.actor.member)
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), uploader)
    assert decided.status_code == 403, decided.text
    assert decided.json()["type"].endswith("self-approval")
    # The uploader now holds an MFA-mandatory role and a factor: the session of before the role
    # owes the challenge (REQ-PLT-005), so the uploader reads with the verified one.
    assert shown(carrying(world, actor=uploader), import_id)["status"] == "SUBMITTED"
    assert (
        world.rows(
            select(job.c.id).where(
                job.c.subject_id == UUID(import_id), job.c.kind == "IMPORT_COMMIT"
            )
        )
        == []
    )


@pytest.mark.control("CTL-001")
def test_ctl_001_committed_file_refused_again(
    j03: J03World, contract_importer: ImportWorld
) -> None:
    content = contracts_csv(j03.customer_id)
    import_id = diffed(contract_importer, "sf-ord-30001.csv", content, "contracts")
    assign(j03.priya.member, "revenue_reviewer")
    assert committed(contract_importer, import_id, j03.priya)["status"] == "COMMITTED"
    versions = contract_importer.scalar(select(func.count()).select_from(contract_version))
    events = contract_importer.scalar(select(func.count()).select_from(contract_event))

    file_id = upload_import_source(contract_importer, "sf-ord-30001-again.csv", content)
    refused = create_import(contract_importer, file_id, "contracts")
    assert refused.status_code == 409, refused.text
    problem = refused.json()
    assert problem["type"].endswith("duplicate-import")
    assert problem["errors"][0]["rule_id"] == "IMPORT_FILE_DUPLICATE"
    assert contract_importer.scalar(select(func.count()).select_from(import_upload)) == 1
    assert contract_importer.scalar(select(func.count()).select_from(contract_version)) == versions
    assert contract_importer.scalar(select(func.count()).select_from(contract_event)) == events


@pytest.mark.parametrize("fault", ["duplicate", "unknown"])
def test_equal_count_duplicate_lineage_fails_import_atomically(
    world: ImportWorld, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """A repeated row cannot account for a different omitted row, even with equal counts."""
    priya = reviewer(world)
    import_id = diffed(world, "crm-customers.csv", customers_csv(CUSTOMERS), "customers")
    original = csv_v2.TEMPLATES["customers"]
    first: list[UUID] = []

    def duplicate(unit: Any, plan: Any, *, context: Any) -> Any:
        applied = original.apply(unit, plan, context=context)
        for row_id, targets in list(applied.row_targets.items()):
            if not first:
                first.append(row_id)
            else:
                del applied.row_targets[row_id]
                applied.row_targets[first[0] if fault == "duplicate" else uuid4()] = targets
        return applied

    monkeypatch.setattr(
        csv_v2, "TEMPLATES", {"customers": dataclasses.replace(original, apply=duplicate)}
    )
    done = committed(world, import_id, priya)
    assert done["status"] == "FAILED", done
    assert world.rows(select(customer.c.code).where(customer.c.code.in_(["C-501", "C-502"]))) == []
    for table in (source_record, import_row_lineage):
        assert (
            world.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id))) == []
        )
    [item] = world.rows(
        select(exception_item).where(
            exception_item.c.import_upload_id == UUID(import_id),
            exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
        )
    )
    assert item["severity"] == "BLOCKING"


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("corrupt", [False, True])
def test_contract_price_readback_reconciles_new_and_replacement_bookings(
    j03: J03World,
    contract_importer: ImportWorld,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bool,
    corrupt: bool,
) -> None:
    assign(j03.priya.member, "revenue_reviewer")
    external_id = "SF-ORD-20417"
    before = None
    if replacement:
        booked = booked_contract(j03.place, sf_ord_20417_body(j03.customer_id), activate=False)
        before = contract_importer.rows(
            select(contract).where(contract.c.id == UUID(str(booked.contract["id"])))
        )[0]
    import_id = diffed(
        contract_importer,
        "contract-prices.csv",
        contracts_csv(j03.customer_id, external_id=external_id),
        "contracts",
    )
    submitted = submit(contract_importer, import_id)
    assert submitted.status_code == 200
    assert (
        approve(j03.app, str(submitted.json()["approval_request_id"]), j03.priya).status_code == 200
    )
    template = csv_v2.TEMPLATES["contracts"]

    def changed(uow: Any, plan: Any, *, context: Any) -> Any:
        body = copy.deepcopy(plan.body)
        if corrupt:
            # The same 120,000 total conceals different prices on the two obligations.
            body["lines"][0]["total_price"]["amount"] = "95000.00"
            body["lines"][1]["total_price"]["amount"] = "25000.00"
        return template.apply(uow, dataclasses.replace(plan, body=body), context=context)

    monkeypatch.setattr(
        csv_v2,
        "TEMPLATES",
        {**csv_v2.TEMPLATES, "contracts": dataclasses.replace(template, apply=changed)},
    )
    run_import_job(contract_importer, job_of(contract_importer, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(contract_importer, import_id)
    assert done["status"] == ("FAILED" if corrupt else "COMMITTED"), done
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    events = contract_importer.rows(
        select(contract_event).where(contract_event.c.import_upload_id == UUID(import_id))
    )
    if not corrupt:
        assert check["source"] == check["stored"]
        assert (
            done["control_totals"]["loaded"]["amount_sums"]
            == done["control_totals"]["source"]["amount_sums"]
        )
        (event,) = events
        assert event["origin"] == "IMPORT" and event["source_record_id"] is not None
        assert event["event_type"] == "CONTRACT_BOOKED"
    else:
        assert check["source"] != check["stored"]
        assert events == []
        for table in (source_record, import_row_lineage):
            assert (
                contract_importer.rows(
                    select(table.c.id).where(table.c.import_upload_id == UUID(import_id))
                )
                == []
            )
        assert (
            contract_importer.rows(
                select(job.c.id).where(
                    job.c.kind == "CONTRACT_COMPUTE",
                    job.c.params["import_upload_id"].astext == import_id,
                )
            )
            == []
        )
        current = contract_importer.rows(
            select(contract).where(contract.c.external_id == external_id)
        )
        assert current == ([] if before is None else [before])
        (finding,) = contract_importer.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
