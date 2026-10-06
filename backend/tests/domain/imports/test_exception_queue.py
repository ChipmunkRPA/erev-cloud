"""DIN-11 exception queue commands (04 §15.3 API-R-44, §16.14 exception item additions, T-IMP-05,
E-42 to E-44, E-106, E-117; PRD SM-06, BR-DAT-04, ACT-17, ACT-18, §2.5 routing row
``EXCEPTION_WAIVER``, NTF-11, IMP-39, IMP-41, J-13.3, WLD-B-04; SCREENS SCR-IA-06, §13; 03
REQ-DAT-009, REQ-REF-014; BUILD_SPEC DIN-11).

Worlds: ``support.legacy_replay.legacy_world`` for import and engine items. Maya (Revenue
Accountant) holds ``exception.resolve``; Priya (Revenue Reviewer) and Marcus (Controller) hold
``exception.waive`` and are enrolled in MFA. ``support.factories.seat_world`` with a product
without a template gives the ``PRODUCT_UNMAPPED`` item that is reprocessed. Jobs run as the worker
runs them.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    contract,
    contract_computation,
    exception_item,
    job,
    notification,
    obligation_version,
    pob_template,
    product,
)
from erev_api.domain.imports.exceptions import dedupe_key, raise_exception_item
from erev_api.enums import ExceptionDisposition, ExceptionSeverity, ExceptionSource
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    Workspace,
    imported,
    seat_body,
    seat_line,
    seat_world,
    set_default_template,
    workbook_bytes,
)
from support.legacy_replay import LegacyWorld, legacy_world, replayed
from support.principals import Actor, step_up
from support.reference import approve, get, post, slug

EXCEPTIONS = "/api/v1/exceptions"
CONTRACTS = "/api/v1/contracts"
APPROVALS = "/api/v1/approvals"
PROGRESS = "legacy_progress_tracking"
PROGRESS_SHEET = "Progress Tracking"
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
DISMISS_COMMENT = "Replaced by the corrected import committed on the same day."  # PRD J-13.3
WAIVER_COMMENT = "Accepted after review: the quarantined calculation posted nothing."
DISMISS_BLOCKED = (
    "Dismissal applies only to input that was never committed. Request a waiver instead."
)
UNMAPPED = "AVM-SEAT-NOMAP"
TASK_FETCHED = "UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files, untemplated=(UNMAPPED,))


# --- helpers -------------------------------------------------------------------------------------


def _progress_row(name: str, pob: str, sku: str, delivery: int) -> list[Any]:
    return [name, pob, sku, delivery, 0, 0, "Delivery 1", "Delivery 2", "Delivery 3"]


def _raised(
    place: Workspace,
    *,
    code: str,
    severity: ExceptionSeverity,
    source: ExceptionSource = ExceptionSource.ENGINE,
    message: str | None = None,
    **extra: Any,
) -> UUID:
    """One queue item raised in Maya's unit of work, as an engine or adapter raises it."""
    with place.uow() as uow:
        item = raise_exception_item(
            uow,
            source=source,
            code=code,
            severity=severity,
            message=message or f"Probe {code}.",
            dedupe=dedupe_key(source, code, new_id()),
            **extra,
        )
        uow.commit()
    return item.id


def _shown(app: FastAPI, actor: Actor, item_id: object) -> dict[str, Any]:
    response = get(app, f"{EXCEPTIONS}/{item_id}", actor)
    assert response.status_code == 200, response.text
    assert response.headers["ETag"] == f'"r{response.json()["row_version"]}"'
    return dict(response.json())


def _stored(place: Workspace, item_id: UUID) -> dict[str, Any]:
    (row,) = place.rows(select(exception_item).where(exception_item.c.id == item_id))
    return row


def _run(place: Workspace, job_id: UUID) -> None:
    """The worker fetches the job's task and runs it."""
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(text(TASK_FETCHED), {"id": task_id})
    runtime = JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files)
    run_job(job_id, place.tenant_id, attempt=1, runtime=runtime)


# --- tests ---------------------------------------------------------------------------------------


def test_dismiss_uncommitted_input(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    rows = [
        _progress_row("Contract 1", "POB #1", "Hardware 1", 6),
        _progress_row("Contract 2", "VC #1", "Variable Consideration", 2),
    ]
    import_id, validated = imported(
        legacy.imports,
        "progress-invalid 1.31.2023.xlsx",
        workbook_bytes(PROGRESS_SHEET, PROGRESS_HEADERS, rows),
        PROGRESS,
        {"effective_date": "2023-01-31"},
    )
    assert validated["status"] == "INVALID", validated
    listed = get(legacy.app, EXCEPTIONS, legacy.maya, {"import_upload_id": import_id})
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [
        (item["code"], item["severity"], item["status"], item["source"], item["disposition"])
        for item in items
    ] == [("PROGRESS_OVER_DELIVERY", "BLOCKING", "OPEN", "IMPORT", "remediable")] * 2
    for item in items:
        assert item["title"] == "Delivery exceeds the remaining quantity"
        assert item["available_actions"] == ["ASSIGN", "REQUEST_WAIVER", "DISMISS"]
        assert item["dismiss_blocked_reason"] is None

    first = f"{EXCEPTIONS}/{items[0]['id']}/dismiss"
    short = post(legacy.app, first, legacy.maya, {"comment": "Replaced"})
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    for item in items:
        dismissed = post(
            legacy.app,
            f"{EXCEPTIONS}/{item['id']}/dismiss",
            legacy.maya,
            {"comment": DISMISS_COMMENT},
        )
        assert dismissed.status_code == 200, dismissed.text
        body = dismissed.json()
        # 04 rev 1.139: `resolved_by` is API-S-Actor — who resolved, read with the item.
        resolver = body["resolved_by"]
        assert (body["status"], body["resolution"], resolver["id"], resolver["kind"]) == (
            "DISMISSED",
            DISMISS_COMMENT,
            str(legacy.maya.member.user_id),
            "USER",
        )
        assert (body["available_actions"], body["dismiss_blocked_reason"]) == ([], None)
        assert dismissed.headers["ETag"] == f'"r{body["row_version"]}"'
    audits = legacy.imports.rows(
        select(audit_event.c.object_id, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.action == "exception_item.dismiss"
        )
    )
    assert sorted(
        (str(row["object_id"]), row["before"]["status"], row["after"]["status"]) for row in audits
    ) == sorted((item["id"], "OPEN", "DISMISSED") for item in items)
    again = post(legacy.app, first, legacy.maya, {"comment": DISMISS_COMMENT})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text


def test_committed_input_needs_waiver(legacy: LegacyWorld, clock: FrozenClock) -> None:
    place = legacy.place()
    item_id = _raised(
        place,
        code="ENGINE_INVARIANT_VIOLATION",
        severity=ExceptionSeverity.BLOCKING,
        message="Contract 1: the calculation stopped with ENGINE_INVARIANT_VIOLATED and was "
        "quarantined. Nothing was posted for it.",
    )
    shown = _shown(legacy.app, legacy.maya, item_id)
    assert (shown["source"], shown["available_actions"], shown["dismiss_blocked_reason"]) == (
        "ENGINE",
        ["ASSIGN", "REQUEST_WAIVER"],
        "INPUT_COMMITTED",
    )
    path = f"{EXCEPTIONS}/{item_id}"
    refused = post(legacy.app, f"{path}/dismiss", legacy.maya, {"comment": DISMISS_COMMENT})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["errors"][0]["message"] == DISMISS_BLOCKED

    # Marcus owns the item, so he may not approve its waiver (PRD §2.5).
    owner = {"owner_membership_id": str(legacy.marcus.member.membership_id)}
    assigned = post(legacy.app, f"{path}/assign", legacy.maya, owner)
    assert assigned.status_code == 200, assigned.text
    requested = post(legacy.app, f"{path}/request-waiver", legacy.maya, {"comment": WAIVER_COMMENT})
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    assert requested.json()["request_no"]
    (request,) = place.rows(select(approval_request).where(approval_request.c.id == request_id))
    assert (
        str(request["subject_type"]),
        str(request["status"]),
        request["subject_id"],
        request["comment"],
    ) == ("EXCEPTION_WAIVER", "PENDING", item_id, WAIVER_COMMENT)
    pending = _shown(legacy.app, legacy.maya, item_id)
    assert (pending["status"], pending["available_actions"]) == ("IN_PROGRESS", ["ASSIGN"])
    twice = post(legacy.app, f"{path}/request-waiver", legacy.maya, {"comment": WAIVER_COMMENT})
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text

    decidable = {
        name: get(legacy.app, f"{APPROVALS}/{request_id}", actor).json()["can_decide"]
        for name, actor in (("priya", legacy.priya), ("marcus", legacy.marcus))
    }
    assert decidable == {"priya": True, "marcus": False}
    # [J] D-88 L7-2-Q-7: an exception item keeps the SF-11 link; only checklist items link to SF-05.
    detail = get(legacy.app, f"{APPROVALS}/{request_id}", legacy.maya)
    assert detail.status_code == 200, detail.text
    assert detail.json()["subject"]["href"] == f"/data/exceptions/{item_id}"
    by_owner = approve(legacy.app, request_id, legacy.marcus)
    assert (by_owner.status_code, slug(by_owner)) == (403, "self-approval"), by_owner.text
    by_requester = approve(legacy.app, request_id, legacy.maya)
    assert by_requester.status_code == 403, by_requester.text

    # Step-up MFA (BR-PLT-06): a verification older than five minutes is refused.
    clock.advance(timedelta(minutes=6))
    stale = approve(legacy.app, request_id, legacy.priya)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    approved = approve(legacy.app, request_id, step_up(legacy.app, clock, legacy.priya))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    stored = _stored(place, item_id)
    assert (
        str(stored["status"]),
        stored["waiver_approval_request_id"],
        stored["resolution"],
        stored["resolved_by"],
    ) == ("WAIVED", UUID(request_id), WAIVER_COMMENT, legacy.priya.member.user_id)
    final = _shown(legacy.app, legacy.maya, item_id)
    assert (final["available_actions"], final["dismiss_blocked_reason"]) == ([], None)


def test_reprocess_remediable_item(seats: SeatWorld) -> None:
    maya = seats.place.author
    line = seat_line(
        "O1",
        seats="10",
        price="24000.00",
        start="2026-09-01",
        end="2027-08-31",
        product_code=UNMAPPED,
    )
    body = seat_body(
        seats.customers["C-09"], external_id="SF-ORD-10490", inception="2026-09-01", lines=[line]
    )
    created = post(seats.app, CONTRACTS, maya, body)
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    (item,) = seats.place.rows(
        select(exception_item).where(exception_item.c.contract_id == contract_id)
    )
    assert (
        str(item["source"]),
        item["code"],
        str(item["severity"]),
        str(item["status"]),
        str(item["disposition"]),
    ) == ("ENGINE", "PRODUCT_UNMAPPED", "BLOCKING", "OPEN", "remediable")
    item_id = item["id"]
    shown = _shown(seats.app, maya, item_id)
    assert shown["available_actions"] == ["ASSIGN", "REPROCESS", "REQUEST_WAIVER"]
    assert (shown["dismiss_blocked_reason"], shown["contract_external_id"]) == (
        "INPUT_COMMITTED",
        "SF-ORD-10490",
    )
    path = f"{EXCEPTIONS}/{item_id}/reprocess"

    # Before the product is mapped, reprocessing raises the same finding and the item stays open.
    early = post(seats.app, path, maya, {})
    assert early.status_code == 202, early.text
    assert early.json()["kind"] == "CONTRACT_COMPUTE"
    _run(seats.place, UUID(early.json()["id"]))
    still = _stored(seats.place, item_id)
    assert (str(still["status"]), still["occurrence_count"]) == ("OPEN", 2)
    assert still["reprocessed_at"] is not None

    (template,) = seats.place.rows(
        select(pob_template.c.id).where(pob_template.c.code == "TPL-SUB-DAILY")
    )
    (mapped,) = seats.place.rows(select(product.c.id).where(product.c.code == UNMAPPED))
    set_default_template(seats.app, maya, str(mapped["id"]), str(template["id"]))

    started = post(seats.app, path, maya, {})
    assert started.status_code == 202, started.text
    assert started.headers["Location"] == f"/api/v1/jobs/{started.json()['id']}"
    _run(seats.place, UUID(started.json()["id"]))
    resolved = _shown(seats.app, maya, item_id)
    assert (
        resolved["status"],
        resolved["available_actions"],
        resolved["dismiss_blocked_reason"],
    ) == (
        "RESOLVED",
        [],
        None,
    )
    assert resolved["reprocessed_at"] is not None
    assert resolved["resolved_at"] is not None
    assert resolved["resolution"].startswith("Reprocessed. Computation ")
    # The input is processed: the latest computation succeeded and O1 has an obligation version.
    computations = seats.place.rows(
        select(contract_computation.c.status)
        .join(
            contract, contract.c.combination_group_id == contract_computation.c.combination_group_id
        )
        .where(contract.c.id == contract_id)
        .order_by(contract_computation.c.id)
    )
    assert [str(row["status"]) for row in computations] == [
        "QUARANTINED",
        "QUARANTINED",
        "SUCCEEDED",
    ]
    versions = seats.place.rows(
        select(obligation_version.c.obligation_key).where(
            obligation_version.c.contract_id == contract_id
        )
    )
    assert {row["obligation_key"] for row in versions} == {"O1"}


def test_sort_and_filters(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    place = legacy.place()
    contracts = {
        str(row["external_id"]): row["id"]
        for row in place.rows(select(contract.c.external_id, contract.c.id))
    }
    import_id, validated = imported(
        legacy.imports,
        "progress headers only.xlsx",
        workbook_bytes(PROGRESS_SHEET, PROGRESS_HEADERS, []),
        PROGRESS,
        {"effective_date": "2023-01-31"},
    )
    assert validated["status"] == "INVALID", validated
    (found,) = place.rows(
        select(exception_item.c.id).where(exception_item.c.import_upload_id == UUID(import_id))
    )
    imported_item = found["id"]
    entity_1 = legacy.entity_ids["Mock Entity 1"]
    info = _raised(
        place,
        code="COST_NO_EAC",
        severity=ExceptionSeverity.INFO,
        contract_id=contracts["Contract 1"],
        entity_id=entity_1,
    )
    warning = _raised(
        place,
        code="LATE_EVENT",
        severity=ExceptionSeverity.WARNING,
        contract_id=contracts["Contract 1"],
    )
    blocking = _raised(
        place,
        code="ENGINE_INVARIANT_VIOLATION",
        severity=ExceptionSeverity.BLOCKING,
        contract_id=contracts["Contract 2"],
    )
    mine = {imported_item, info, warning, blocking}

    def listed(params: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        response = get(legacy.app, EXCEPTIONS, legacy.maya, {"limit": 200, **params})
        assert response.status_code == 200, response.text
        return response.json()["items"], response.json()["next_cursor"]

    def ids(params: Mapping[str, Any]) -> list[UUID]:
        return [UUID(item["id"]) for item in listed(params)[0] if UUID(item["id"]) in mine]

    # BLOCKING before WARNING before INFO, then newest first (04 API-R-44).
    items, _ = listed({"sort": "severity"})
    rank = {"BLOCKING": 0, "WARNING": 1, "INFO": 2}
    severities = [item["severity"] for item in items]
    assert severities == sorted(severities, key=rank.__getitem__)
    assert ids({"sort": "severity"}) == [blocking, imported_item, warning, info]
    assert ids({}) == [blocking, imported_item, warning, info]
    page, cursor = listed({"sort": "severity", "limit": 2})
    assert cursor is not None
    rest, _ = listed({"sort": "severity", "cursor": cursor})
    assert [item["id"] for item in page + rest] == [item["id"] for item in items]

    assert ids({"import_upload_id": import_id}) == [imported_item]
    assert ids({"source": "IMPORT"}) == [imported_item]
    assert ids({"code": "LATE_EVENT"}) == [warning]
    assert set(ids({"contract": str(contracts["Contract 1"])})) == {info, warning}
    # Supervisor ruling R-121 (i), one attribution of an item to an entity (04 T-IMP-05 "An item
    # that names no entity", rev 1.206): Mock Entity 1's items are the one that names it, the one
    # of its contract (Contract 1) and the import's — an upload that is not resolved is every
    # entity's; Contract 2 is Mock Entity 2's. By the item's own column before: [info] — a stale
    # expectation by that ruling.
    assert ids({"entity": "Mock Entity 1"}) == [imported_item, warning, info]
    assert ids({"entity": str(entity_1)}) == [imported_item, warning, info]
    assert ids({"entity": "Mock Entity 2"}) == [blocking, imported_item]
    assert ids({"severity": "WARNING"}) == [warning]

    dismissed = post(
        legacy.app,
        f"{EXCEPTIONS}/{imported_item}/dismiss",
        legacy.maya,
        {"comment": "Header-only file; the corrected file follows."},
    )
    assert dismissed.status_code == 200, dismissed.text
    assert ids({"status": "DISMISSED"}) == [imported_item]
    assert ids({"status": "OPEN"}) == [blocking, warning, info]
    assigned = post(
        legacy.app,
        f"{EXCEPTIONS}/{warning}/assign",
        legacy.maya,
        {"owner_membership_id": str(legacy.maya.member.membership_id)},
    )
    assert assigned.status_code == 200, assigned.text
    assert ids({"owner": "me"}) == [warning]
    assert ids({"status": "IN_PROGRESS"}) == [warning]

    for params in ({"sort": "-severity"}, {"status": "NOPE"}, {"owner": "someone"}):
        refused = get(legacy.app, EXCEPTIONS, legacy.maya, params)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text


def test_discarded_items_keep_payload(legacy: LegacyWorld, app: FastAPI) -> None:
    place = legacy.place()
    payload = {"order_number": "SF-ORD-30417", "line": 2, "product": "SF-PROD-X99"}
    message = "Order SF-ORD-30417, line 2: product SF-PROD-X99 has no approved product record."
    suggestion = "Create product SF-PROD-X99, then reprocess the order."
    item_id = _raised(
        place,
        source=ExceptionSource.SYNC,
        code="PRODUCT_UNMAPPED",
        severity=ExceptionSeverity.BLOCKING,
        message=message,
        suggestion=suggestion,
        source_payload=payload,
        business_key="SF-ORD-30417",
        disposition=ExceptionDisposition.DISCARDED,
    )
    shown = _shown(legacy.app, legacy.maya, item_id)
    assert (shown["disposition"], shown["source_payload"], shown["message"]) == (
        "discarded",
        payload,
        message,
    )
    assert shown["suggestion"] == suggestion
    assert shown["available_actions"] == ["ASSIGN", "REQUEST_WAIVER", "DISMISS"]

    dismissed = post(
        legacy.app,
        f"{EXCEPTIONS}/{item_id}/dismiss",
        legacy.maya,
        {"comment": "The order notification was discarded; nothing was booked."},
    )
    assert dismissed.status_code == 200, dismissed.text
    after = _shown(legacy.app, legacy.maya, item_id)
    assert (after["status"], after["source_payload"], after["message"], after["suggestion"]) == (
        "DISMISSED",
        payload,
        message,
        suggestion,
    )

    # No route deletes an item, and the application role cannot delete one (IM-M).
    paths = {
        path: set(methods)
        for path, methods in app.openapi()["paths"].items()
        if path.startswith(EXCEPTIONS)
    }
    assert paths == {
        EXCEPTIONS: {"get"},
        f"{EXCEPTIONS}/{{item_id}}": {"get"},
        **{
            f"{EXCEPTIONS}/{{item_id}}/{name}": {"post"}
            for name in ("assign", "resolve", "reprocess", "request-waiver", "dismiss")
        },
    }
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with pytest.raises(DBAPIError), tenant_session(context) as session:
        session.execute(delete(exception_item).where(exception_item.c.id == item_id))
    assert _stored(place, item_id)["source_payload"] == payload


def test_assign_notifies_owner(legacy: LegacyWorld) -> None:
    place = legacy.place()
    message = (
        "Effective 2023-01-15 in closed period FY2023-P01. The effect posts to FY2023-P02 with "
        "origin period FY2023-P01."
    )
    item_id = _raised(place, code="LATE_EVENT", severity=ExceptionSeverity.WARNING, message=message)
    path = f"{EXCEPTIONS}/{item_id}/assign"
    unknown = post(legacy.app, path, legacy.maya, {"owner_membership_id": str(new_id())})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert unknown.json()["errors"][0]["field"] == "owner_membership_id"

    priya = legacy.priya.member.membership_id
    assigned = post(legacy.app, path, legacy.maya, {"owner_membership_id": str(priya)})
    assert assigned.status_code == 200, assigned.text
    assert (assigned.json()["status"], assigned.json()["owner_membership_id"]) == (
        "IN_PROGRESS",
        str(priya),
    )
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        sent = [
            dict(row)
            for row in session.execute(
                select(
                    notification.c.kind,
                    notification.c.title,
                    notification.c.body,
                    notification.c.link_path,
                    notification.c.subject_type,
                    notification.c.subject_id,
                ).where(notification.c.recipient_membership_id == priya)
            ).mappings()
        ]
    assert [{**row, "kind": str(row["kind"])} for row in sent] == [
        {
            "kind": "EXCEPTION_ASSIGNED",
            "title": "Exception: LATE_EVENT",
            "body": message,
            "link_path": f"/data/exceptions/{item_id}",
            "subject_type": "exception_item",
            "subject_id": item_id,
        }
    ]
    (audit,) = place.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.object_id == item_id, audit_event.c.action == "exception_item.assign"
        )
    )
    assert (audit["before"], audit["after"]) == (
        {"owner_membership_id": None, "status": "OPEN"},
        {"owner_membership_id": str(priya), "status": "IN_PROGRESS"},
    )
