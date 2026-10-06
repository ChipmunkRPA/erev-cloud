"""SSP book version publication: study, maker-checker, range validation and immutability (04
T-REF-28, T-REF-29, §14.1 DB-04, DB-05, §15.2, table 15.4-C, T-PLT-31; POLICIES §3.3 POL-073; PRD
§2.5, BR-SSP-01, BR-SSP-02, BR-SSP-05, ERR-09, ERR-10, ERR-32, J-02; 03 REQ-SSP-001, REQ-SSP-007,
REQ-SSP-008; CTL-010, CTL-011; BUILD_SPEC RFD-13), and the scope of a book as part of the approved
content of its versions (04 §16.10 rev 1.110, API-S-SspBook; REQ-PLT-014; CTL-007; security finding
SN-8, supervisor ruling R-27).

Maya holds Revenue Accountant and SSP Analyst (``ssp.create``) and prepares the Avenmoor SSP book
US-LIST (USD) of PRD §2.6; Priya and Marcus hold SSP Approver (``ssp.approve``) and are enrolled in
MFA (docs/02-PRD.md §5.6 PRS-01 to PRS-03). No routing rule set is published, so requests take the
fallback steps. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.approvals.engine import WITHDRAW_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    fiscal_calendar,
    legal_entity,
    ssp_book,
)
from erev_api.domain.ssp import books
from erev_api.enums import RegistryCategory
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support import upload_fixtures
from support.db import TestDatabase
from support.factories import world_calendar
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import (
    APPROVALS,
    approve,
    assign,
    delete,
    fields,
    get,
    holding,
    new_product,
    patch,
    post,
    reject,
    slug,
)
from support.rows import fiscal_calendar_values, legal_entity_values, publish_registry_version
from support.shred_in_flight import beside_a_shred

SSP_BOOKS = "/api/v1/ssp-books"
VERSIONS = "/api/v1/ssp-book-versions"
METHODOLOGY = "Observable standalone sales, Jan-Aug 2026"
PLATFORM = "AVM-PLAT-100"
ENTERPRISE = "AVM-PLAT-ENT"
FIRST_RANGE = "entries[0].ranges[0]"
BLOCK = {"max_half_width_pct": "0.20", "min_coverage_pct": "0.50", "mode": "BLOCK"}
WARN = {**BLOCK, "mode": "WARN"}


@dataclass(frozen=True, slots=True)
class World:
    maya: Actor
    priya: Actor
    marcus: Actor
    book_id: str

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: list[Actor] = []
    for name in ("priya", "marcus"):
        someone = colleague(maya_member.tenant_id, name)
        assign(someone, "ssp_approver")
        approvers.append(enrolled(app, clock, someone))
    for code in (PLATFORM, ENTERPRISE):
        new_product(app, maya, code=code, name=code)
    created = post(
        app, SSP_BOOKS, maya, {"code": "US-LIST", "name": "US list prices", "currency": "USD"}
    )
    assert created.status_code == 201, created.text
    return World(
        maya=maya, priya=approvers[0], marcus=approvers[1], book_id=str(created.json()["id"])
    )


def observable(product_code: str, low: str, mid: str, high: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"low_value": low, "mid_value": mid, "high_value": high}],
    }


# PRD §2.6: US-LIST 2026-H1.
H1_ENTRIES = (
    observable(PLATFORM, "85000.00", "100000.00", "115000.00"),
    {
        "product_code": ENTERPRISE,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "ranges": [{"point_value": "132000.00"}],
    },
)


def new_version(
    app: FastAPI,
    actor: Actor,
    book_id: str,
    *,
    label: str | None,
    effective_from: str | None,
    entries: Iterable[Mapping[str, Any]] = H1_ENTRIES,
    **extra: Any,
) -> dict[str, Any]:
    """``POST /ssp-books/{id}/versions`` and one upsert of ``entries``; returns the 201 body."""
    body = {
        "legacy_version_label": label,
        "effective_from_date": effective_from,
        "methodology_label": METHODOLOGY,
        **extra,
    }
    created = post(app, f"{SSP_BOOKS}/{book_id}/versions", actor, body)
    assert created.status_code == 201, created.text
    version: dict[str, Any] = created.json()
    items = [dict(item) for item in entries]
    if items:
        stored = post(app, f"{VERSIONS}/{version['id']}/entries", actor, {"entries": items})
        assert stored.status_code == 200, stored.text
    return version


def attach(app: FastAPI, actor: Actor, version_id: str, purpose: str = "SSP_STUDY") -> str:
    """Upload a PDF of ``purpose`` and attach it to the version; returns the attachment id."""
    uploaded = call(
        app,
        "POST",
        "/api/v1/files",
        data={"purpose": purpose},
        files={"file": ("study.pdf", upload_fixtures.PDF, "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        app,
        "/api/v1/attachments",
        actor,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "ssp_book_version",
            "subject_id": version_id,
        },
    )
    assert attached.status_code == 201, attached.text
    return str(attached.json()["id"])


def shown(app: FastAPI, actor: Actor, version_id: str) -> dict[str, Any]:
    response = get(app, f"{VERSIONS}/{version_id}", actor)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def submit(
    app: FastAPI, actor: Actor, version_id: str, *, comment: str | None = None
) -> HttpResponse:
    """``POST /ssp-book-versions/{id}/submit`` with the version's current ETag."""
    current = get(app, f"{VERSIONS}/{version_id}", actor)
    assert current.status_code == 200, current.text
    body = {} if comment is None else {"comment": comment}
    return post(
        app, f"{VERSIONS}/{version_id}/submit", actor, body, if_match=current.headers["ETag"]
    )


def submitted(app: FastAPI, actor: Actor, version_id: str) -> dict[str, Any]:
    """Attach the study and submit; returns the SUBMITTED version."""
    attach(app, actor, version_id)
    response = submit(app, actor, version_id, comment="Supported by standalone sales.")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    assert result["status"] == "SUBMITTED", result
    return result


def approved(
    app: FastAPI,
    world: World,
    *,
    label: str,
    effective_from: str,
    entries: Iterable[Mapping[str, Any]] = H1_ENTRIES,
    **extra: Any,
) -> dict[str, Any]:
    """A version Maya submits and Priya, then Marcus for a second step, approves."""
    version = new_version(
        app,
        world.maya,
        world.book_id,
        label=label,
        effective_from=effective_from,
        entries=entries,
        **extra,
    )
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    for approver in (world.priya, world.marcus):
        response = approve(app, request_id, approver)
        assert response.status_code == 200, response.text
        if response.json()["status"] == "APPROVED":
            break
    result = shown(app, world.maya, version["id"])
    assert result["status"] == "APPROVED", result
    return result


def request_of(app: FastAPI, actor: Actor, request_id: str) -> dict[str, Any]:
    response = get(app, f"{APPROVALS}/{request_id}", actor)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def steps(request: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            step["step_no"],
            step["name"],
            step["required_permission"],
            step["status"],
            [decision["approver"]["display_name"] for decision in step["decisions"]],
        )
        for step in request["steps"]
    ]


def audits(world: World, action: str) -> list[dict[str, Any]]:
    """The audit events of ``action`` in chain order."""
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    statement = (
        select(
            audit_event.c.object_id,
            audit_event.c.before,
            audit_event.c.after,
            audit_event.c.detail,
            audit_event.c.approval_request_id,
        )
        .where(audit_event.c.action == action)
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(ctx, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def publish_range_validation(world: World, value: Mapping[str, str], *, at: datetime) -> None:
    """A PUBLISHED TENANT version holding POL-073 ``ssp.range_validation`` from ``at``."""
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={"ssp.range_validation": dict(value)},
            at=at,
        )


def test_submit_requires_study_and_methodology(app: FastAPI, world: World) -> None:
    version = new_version(
        app, world.maya, world.book_id, label="2026-H1", effective_from="2026-01-01"
    )
    refused = submit(app, world.maya, version["id"])
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "ssp-study-required"
    assert refused.json()["detail"] == "Attach the SSP study before submitting this version."
    # An attachment of another purpose is not the study.
    attach(app, world.maya, version["id"], purpose="ATTACHMENT")
    assert slug(submit(app, world.maya, version["id"])) == "ssp-study-required"
    draft = shown(app, world.maya, version["id"])
    assert (draft["status"], draft["approval_request_id"], draft["content_sha256"]) == (
        "DRAFT",
        None,
        None,
    )

    study = attach(app, world.maya, version["id"])
    accepted = submit(app, world.maya, version["id"], comment="Supported by H1 standalone sales.")
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert accepted.headers["ETag"] == f'"r{body["row_version"]}"'
    assert (body["status"], body["methodology_label"], body["study_attachment_ids"]) == (
        "SUBMITTED",
        METHODOLOGY,
        [study],
    )
    assert body["approval_request_id"] is not None
    assert len(body["content_sha256"]) == 64
    assert body["diff_summary"] == {
        "against_version_id": None,
        "added": 2,
        "removed": 0,
        "changed": 0,
    }
    request = request_of(app, world.priya, body["approval_request_id"])
    assert (request["subject"]["type"], request["subject"]["id"]) == (
        "SSP_BOOK_VERSION",
        version["id"],
    )
    assert request["subject"]["content_sha256"] == body["content_sha256"]
    assert (request["status"], request["summary"], request["flags"]) == (
        "PENDING",
        "Approve version 1 of SSP book US-LIST",
        [],
    )
    assert steps(request) == [(1, "Approval", "ssp.approve", "ACTIVE", [])]
    assert request["can_decide"] is True

    (event,) = audits(world, "ssp_book_version.submit")
    assert str(event["object_id"]) == version["id"]
    assert event["detail"]["lifecycle"] == ["DRAFT", "TESTED", "SUBMITTED"]
    # AVM-PLAT-ENT holds a point, not a range; no population is attached before RFD-15.
    assert [
        (finding["code"], finding["severity"], finding["subject"])
        for finding in event["detail"]["range_findings"]
    ] == [("COVERAGE_UNKNOWN", "WARNING", FIRST_RANGE)]

    again = submit(app, world.maya, version["id"])
    assert again.status_code == 409, again.text
    assert (slug(again), fields(again)) == ("invalid-transition", [("status", "SM-04")])


def test_second_approver_when_mid_changes_above_threshold(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    second = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=(observable(PLATFORM, "95200.00", "112000.00", "128800.00"),),
        copy_from_version_id=first["id"],
    )
    diff = get(app, f"{VERSIONS}/{second['id']}/diff", world.maya, {"against": first["id"]})
    assert [
        (item["key"]["product_code"], item["mid_change_ratio"]) for item in diff.json()["changed"]
    ] == [(PLATFORM, "0.12")]
    body = submitted(app, world.maya, second["id"])
    assert body["diff_summary"] == {
        "against_version_id": first["id"],
        "added": 0,
        "removed": 0,
        "changed": 1,
    }
    request_id = body["approval_request_id"]
    request = request_of(app, world.priya, request_id)
    assert request["flags"] == ["ABOVE_THRESHOLD"]
    assert steps(request) == [
        (1, "Approval", "ssp.approve", "ACTIVE", []),
        (2, "Second approval", "ssp.approve", "WAITING", []),
    ]

    step_one = approve(app, request_id, world.priya)
    assert step_one.status_code == 200, step_one.text
    assert (step_one.json()["status"], step_one.json()["current_step_no"]) == ("PENDING", 2)
    assert shown(app, world.maya, second["id"])["status"] == "SUBMITTED"
    repeated = approve(app, request_id, world.priya)
    assert (repeated.status_code, slug(repeated)) == (409, "approver-already-decided")
    assert shown(app, world.maya, second["id"])["status"] == "SUBMITTED"

    step_two = approve(app, request_id, world.marcus)
    assert step_two.status_code == 200, step_two.text
    final = request_of(app, world.priya, request_id)
    assert final["status"] == "APPROVED"
    assert steps(final) == [
        (1, "Approval", "ssp.approve", "APPROVED", ["Priya"]),
        (2, "Second approval", "ssp.approve", "APPROVED", ["Marcus"]),
    ]
    version = shown(app, world.maya, second["id"])
    assert (version["status"], version["approval_request_id"]) == ("APPROVED", request_id)
    assert version["published_at"] is not None
    assert shown(app, world.maya, first["id"])["effective_to_date"] == "2026-09-30"


def test_single_approver_below_threshold(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    # 5%: mid 100,000.00 → 105,000.00 with the same ±15% band.
    second = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=(observable(PLATFORM, "89250.00", "105000.00", "120750.00"),),
        copy_from_version_id=first["id"],
    )
    request_id = submitted(app, world.maya, second["id"])["approval_request_id"]
    request = request_of(app, world.priya, request_id)
    assert request["flags"] == []
    assert steps(request) == [(1, "Approval", "ssp.approve", "ACTIVE", [])]
    accepted = approve(app, request_id, world.priya)
    assert (accepted.status_code, accepted.json()["status"]) == (200, "APPROVED")


def test_methodology_change_forces_second_approver(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    second = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=(),
        copy_from_version_id=first["id"],
        is_methodology_change=True,
    )
    body = submitted(app, world.maya, second["id"])
    assert body["diff_summary"]["changed"] == 0
    request = request_of(app, world.priya, body["approval_request_id"])
    assert request["flags"] == ["METHODOLOGY_CHANGE"]
    assert [step[:4] for step in steps(request)] == [
        (1, "Approval", "ssp.approve", "ACTIVE"),
        (2, "Second approval", "ssp.approve", "WAITING"),
    ]


def test_supersession_sets_effective_to_once(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    entries_path = f"{VERSIONS}/{first['id']}/entries"
    entries_before = get(app, entries_path, world.maya, {"limit": 200}).json()["items"]
    second = approved(
        app,
        world,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=(observable(PLATFORM, "95200.00", "112000.00", "128800.00"),),
        copy_from_version_id=first["id"],
    )
    assert (second["effective_from_date"], second["effective_to_date"]) == ("2026-10-01", None)
    earlier = shown(app, world.maya, first["id"])
    assert (earlier["status"], earlier["effective_from_date"], earlier["effective_to_date"]) == (
        "APPROVED",
        "2026-01-01",
        "2026-09-30",
    )
    assert (earlier["methodology_label"], earlier["content_sha256"]) == (
        first["methodology_label"],
        first["content_sha256"],
    )
    assert get(app, entries_path, world.maya, {"limit": 200}).json()["items"] == entries_before
    (event,) = audits(world, "ssp_book_version.supersede")
    assert (str(event["object_id"]), event["before"], event["after"], event["detail"]) == (
        first["id"],
        {"effective_to_date": None},
        {"effective_to_date": "2026-09-30"},
        {"superseded_by_version_id": second["id"]},
    )
    assert str(event["approval_request_id"]) == second["approval_request_id"]
    approvals = {str(item["object_id"]): item for item in audits(world, "ssp_book_version.approve")}
    assert approvals[second["id"]]["detail"]["superseded_version_id"] == first["id"]
    assert approvals[first["id"]]["detail"]["superseded_version_id"] is None
    book = get(app, f"{SSP_BOOKS}/{world.book_id}", world.maya).json()
    assert book["current_version"]["id"] == second["id"]

    # Once: 2026-H1 now ends, so a version effective inside it is another overlap.
    third = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-Q3",
        effective_from="2026-06-01",
        entries=(),
        copy_from_version_id=second["id"],
    )
    request_id = submitted(app, world.maya, third["id"])["approval_request_id"]
    refused = approve(app, request_id, world.priya)
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "configuration-overlap"
    assert refused.json()["detail"] == (
        "Version 2026-Q3 overlaps approved version 2026-H1 from 01 Jan 2026 to 30 Sep 2026 for "
        "the same scope."
    )
    assert shown(app, world.maya, first["id"])["effective_to_date"] == "2026-09-30"
    assert len(audits(world, "ssp_book_version.supersede")) == 1


def test_other_overlap_refused(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    earlier = new_version(
        app,
        world.maya,
        world.book_id,
        label="2025-Q4",
        effective_from="2025-12-01",
        effective_to_date="2026-03-31",
        entries=(),
        copy_from_version_id=first["id"],
    )
    request_id = submitted(app, world.maya, earlier["id"])["approval_request_id"]
    refused = approve(app, request_id, world.priya)
    assert refused.status_code == 409, refused.text
    problem = refused.json()
    assert (slug(refused), problem["code"], fields(refused)) == (
        "configuration-overlap",
        "EREV-CFG-001",
        [("effective_from_date", "DB-04")],
    )
    assert problem["detail"] == (
        "Version 2025-Q4 overlaps approved version 2026-H1 from 01 Jan 2026 with no end date for "
        "the same scope."
    )
    assert request_of(app, world.priya, request_id)["status"] == "PENDING"
    assert shown(app, world.maya, earlier["id"])["status"] == "SUBMITTED"
    assert shown(app, world.maya, first["id"])["effective_to_date"] is None
    assert audits(world, "ssp_book_version.supersede") == []

    # A version that ends before 2026-H1 starts does not overlap.
    history = approved(
        app,
        world,
        label="2025",
        effective_from="2025-01-01",
        effective_to_date="2025-11-30",
        entries=(),
        copy_from_version_id=first["id"],
    )
    assert (history["effective_from_date"], history["effective_to_date"]) == (
        "2025-01-01",
        "2025-11-30",
    )


def test_block_mode_prevents_publication(app: FastAPI, world: World) -> None:
    publish_range_validation(world, BLOCK, at=datetime(2026, 9, 1, tzinfo=UTC))
    version = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-H1",
        effective_from="2026-01-01",
        entries=(observable(PLATFORM, "120000.00", "160000.00", "200000.00"),),
    )
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    refused = approve(app, request_id, world.priya)
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [(FIRST_RANGE, "RANGE_TOO_WIDE"), (FIRST_RANGE, "COVERAGE_UNKNOWN")]
    assert refused.json()["errors"][0]["message"] == (
        "AVM-PLAT-100: the range extends 25.0% from the midpoint, above the 20% limit."
    )
    assert shown(app, world.maya, version["id"])["status"] == "SUBMITTED"
    request = request_of(app, world.priya, request_id)
    assert (request["status"], steps(request)) == (
        "PENDING",
        [(1, "Approval", "ssp.approve", "ACTIVE", [])],
    )
    assert audits(world, "ssp_book_version.approve") == []

    # Under WARN the version is approved, and the approval record carries the warnings.
    publish_range_validation(world, WARN, at=datetime(2026, 9, 10, tzinfo=UTC))
    accepted = approve(app, request_id, world.priya)
    assert accepted.status_code == 200, accepted.text
    assert shown(app, world.maya, version["id"])["status"] == "APPROVED"
    (event,) = audits(world, "ssp_book_version.approve")
    assert str(event["approval_request_id"]) == request_id
    assert [
        (item["code"], item["severity"], item["subject"], item["half_width"], item["coverage"])
        for item in event["detail"]["range_findings"]
    ] == [
        ("RANGE_TOO_WIDE", "WARNING", FIRST_RANGE, "0.25", None),
        ("COVERAGE_UNKNOWN", "WARNING", FIRST_RANGE, "0.25", None),
    ]


def test_approved_version_read_only(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    path = f"{VERSIONS}/{first['id']}"
    frozen = patch(
        app,
        path,
        world.maya,
        {"methodology_label": "Changed"},
        if_match=f'"r{first["row_version"]}"',
    )
    assert frozen.status_code == 409, frozen.text
    assert (slug(frozen), fields(frozen)) == ("configuration-frozen", [("status", "DB-04")])
    upsert = post(
        app, f"{path}/entries", world.maya, {"entries": [observable(PLATFORM, "1", "2", "3")]}
    )
    assert (upsert.status_code, slug(upsert)) == (409, "configuration-frozen")
    entry_id = get(app, f"{path}/entries", world.maya, {"limit": 200}).json()["items"][0]["id"]
    removed = delete(app, f"{path}/entries/{entry_id}", world.maya)
    assert (removed.status_code, slug(removed)) == (409, "configuration-frozen")
    resubmitted = submit(app, world.maya, first["id"])
    assert (resubmitted.status_code, fields(resubmitted)) == (409, [("status", "SM-04")])
    withdrawn = post(app, f"{path}/withdraw", world.maya, {})
    assert (withdrawn.status_code, slug(withdrawn)) == (409, "invalid-transition")
    assert shown(app, world.maya, first["id"]) == first


def test_book_scope_frozen_once_approved(app: FastAPI, world: World) -> None:
    book_path = f"{SSP_BOOKS}/{world.book_id}"
    channel = patch(app, book_path, world.maya, {"channel": "direct"}, if_match='"r1"')
    assert channel.status_code == 200, channel.text
    approved(app, world, label="2026-H1", effective_from="2026-01-01")
    refused = patch(
        app,
        book_path,
        world.maya,
        {"segment": "Enterprise", "resolution_mode": "BY_LABEL", "name": "US list 2026"},
        if_match='"r2"',
    )
    assert refused.status_code == 422, refused.text
    assert fields(refused) == [("segment", "DB-05"), ("resolution_mode", "DB-05")]
    assert refused.json()["errors"][0]["message"] == (
        "The scope of this SSP book cannot change once a version is approved. Create another book."
    )
    renamed = patch(app, book_path, world.maya, {"name": "US list 2026"}, if_match='"r2"')
    assert (renamed.status_code, renamed.headers["ETag"]) == (200, '"r3"')


def test_book_rescoped_after_submission_voids_the_request(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Supervisor ruling R-41 (2) (04 §16.10 rev 1.104 "The entities are read again at the
    decision"; the independent review's finding on ``SSP_BOOK_VERSION``), beside ruling R-27
    (finding SN-8; 04 §16.10 rev 1.110), which closes the window at its source: the scope of a
    book is frozen while a version is SUBMITTED and is part of the hashed content. Maya submits a
    version of a book scoped to entity A; the route refuses to move the book to entity B. Were
    the book moved by another path — here a direct update of the row — Ana, who approves SSP for
    A only, would put prices in force for B on the authority she holds for A. The decision reads
    the subject's entities again, finds B where the request froze A, voids the request
    ``STALE_SUBJECT`` (409 ``stale-approval``) and the version returns to DRAFT; the void names
    the entities the subject states now. Submitted again the request is bound to B: Ana cannot
    read it, and Priya — SSP Approver for every entity — approves it."""
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        calendar = fiscal_calendar_values(world.tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        entities: dict[str, UUID] = {}
        for code in ("ENT-A", "ENT-B"):
            row = legal_entity_values(world.tenant_id, calendar_id=calendar["id"], code=code)
            session.execute(insert(legal_entity).values(**row))
            entities[code] = UUID(str(row["id"]))
    ana_member = colleague(world.tenant_id, "ana")
    assign(ana_member, "ssp_approver", entity_ids=[entities["ENT-A"]])
    ana = enrolled(app, clock, ana_member)

    def bound_to(request_id: str) -> UUID | None:
        with tenant_session(ctx, read_only=True) as session:
            return session.execute(
                select(approval_request.c.entity_id).where(
                    approval_request.c.id == UUID(request_id)
                )
            ).scalar_one()

    book_path = f"{SSP_BOOKS}/{world.book_id}"
    scoped = patch(app, book_path, world.maya, {"entity_code": "ENT-A"}, if_match='"r1"')
    assert scoped.status_code == 200, scoped.text
    version = new_version(
        app, world.maya, world.book_id, label="2026-H1", effective_from="2026-01-01"
    )
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    assert bound_to(request_id) == entities["ENT-A"]
    before = request_of(app, ana, request_id)
    assert before["can_decide"] is True

    # R-27: the command no longer moves the book while its version is under approval.
    frozen = patch(
        app, book_path, world.maya, {"entity_code": "ENT-B"}, if_match=scoped.headers["ETag"]
    )
    assert (frozen.status_code, slug(frozen), fields(frozen)) == (
        409,
        "configuration-frozen",
        [("entity_code", "REQ-PLT-014")],
    ), frozen.text
    with tenant_session(ctx) as session:  # the book moves behind the command
        session.execute(
            update(ssp_book)
            .where(ssp_book.c.id == UUID(world.book_id))
            .values(entity_id=entities["ENT-B"])
        )
    stale = approve(app, request_id, ana)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    after = request_of(app, world.priya, request_id)
    assert (after["status"], after["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert [step["decisions"] for step in after["steps"]] == [[]]
    # The void names the entities the subject states now — and, since R-27 put the scope into
    # the hashed content, another hash than the one Ana reviewed.
    (void,) = [
        event
        for event in audits(world, "approval_request.void")
        if event["object_id"] == UUID(request_id)
    ]
    assert void["after"]["void_reason"] == "STALE_SUBJECT"
    assert void["after"]["subject_content_sha256"] != before["subject"]["content_sha256"]
    assert void["after"]["entities"] == {
        "entity_ids": [str(entities["ENT-B"])],
        "all_entities": False,
    }
    assert shown(app, world.maya, version["id"])["status"] == "DRAFT"

    again = submit(app, world.maya, version["id"], comment="Supported by standalone sales.")
    assert again.status_code == 200, again.text
    second_id = again.json()["approval_request_id"]
    assert second_id != request_id and bound_to(second_id) == entities["ENT-B"]
    hidden = get(app, f"{APPROVALS}/{second_id}", ana)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    second = request_of(app, world.priya, second_id)
    refused = post(
        app,
        f"{APPROVALS}/{second_id}/approve",
        ana,
        {"subject_content_sha256": second["subject"]["content_sha256"]},
    )
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    granted = approve(app, second_id, world.priya)
    assert granted.status_code == 200, granted.text
    assert shown(app, world.maya, version["id"])["status"] == "APPROVED"


def test_withdraw_and_reject_return_to_draft(app: FastAPI, world: World) -> None:
    version = new_version(
        app, world.maya, world.book_id, label="2026-H2b", effective_from="2026-01-01"
    )
    path = f"{VERSIONS}/{version['id']}"
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    forbidden = post(app, f"{path}/withdraw", world.priya, {})
    assert (forbidden.status_code, slug(forbidden)) == (403, "forbidden")
    # A second analyst holds the route's permission and cannot read Maya's request (she neither
    # prepared it nor approves SSP): she is told she is not its preparer (PRD SM-01), not that
    # the version she has open does not exist.
    noor = holding(app, colleague(world.tenant_id, "noor"), "ssp_analyst")
    not_hers = post(app, f"{path}/withdraw", noor, {})
    assert (not_hers.status_code, slug(not_hers)) == (403, "forbidden"), not_hers.text
    assert not_hers.json()["detail"] == WITHDRAW_DETAIL
    by_request = post(app, f"{APPROVALS}/{request_id}/withdraw", noor, {})
    assert (by_request.status_code, slug(by_request)) == (404, "not-found"), by_request.text
    withdrawn = post(app, f"{path}/withdraw", world.maya, {"comment": "More observations first."})
    assert withdrawn.status_code == 200, withdrawn.text
    draft = withdrawn.json()
    assert (draft["status"], draft["content_sha256"], draft["approval_request_id"]) == (
        "DRAFT",
        None,
        request_id,
    )
    assert request_of(app, world.priya, request_id)["status"] == "WITHDRAWN"
    again = post(app, f"{path}/withdraw", world.maya, {})
    assert (again.status_code, fields(again)) == (409, [("status", "SM-04")])

    # The draft changes again and is resubmitted; Priya rejects it (PRD J-02-ALT-1).
    edited = post(
        app,
        f"{path}/entries",
        world.maya,
        {"entries": [observable(PLATFORM, "86000.00", "100000.00", "114000.00")]},
    )
    assert edited.status_code == 200, edited.text
    resubmitted = submit(app, world.maya, version["id"])
    assert resubmitted.status_code == 200, resubmitted.text
    second_request = resubmitted.json()["approval_request_id"]
    assert second_request != request_id
    rejected = reject(app, second_request, world.priya, "Range too wide.")
    assert rejected.status_code == 200, rejected.text
    back = shown(app, world.maya, version["id"])
    assert (back["status"], back["content_sha256"], back["approval_request_id"]) == (
        "DRAFT",
        None,
        second_request,
    )
    assert [e["detail"]["lifecycle"] for e in audits(world, "ssp_book_version.withdraw")] == [
        ["SUBMITTED", "WITHDRAWN", "DRAFT"]
    ]
    assert [e["detail"]["lifecycle"] for e in audits(world, "ssp_book_version.reject")] == [
        ["SUBMITTED", "REJECTED", "DRAFT"]
    ]


def test_submit_findings_and_permissions(app: FastAPI, world: World) -> None:
    version = new_version(
        app, world.maya, world.book_id, label="2026-H1", effective_from=None, entries=()
    )
    path = f"{VERSIONS}/{version['id']}/submit"
    attach(app, world.maya, version["id"])
    forbidden = submit(app, world.priya, version["id"])
    assert (forbidden.status_code, slug(forbidden)) == (403, "forbidden")
    required = post(app, path, world.maya, {})
    assert (required.status_code, slug(required)) == (428, "precondition-required")
    stale = post(app, path, world.maya, {}, if_match='"r99"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed")
    unknown = post(app, f"{VERSIONS}/{UUID(int=7)}/submit", world.maya, {}, if_match='"r1"')
    assert (unknown.status_code, slug(unknown)) == (404, "not-found")
    incomplete = submit(app, world.maya, version["id"])
    assert incomplete.status_code == 422, incomplete.text
    assert fields(incomplete) == [("effective_from_date", "T-REF-29"), ("entries", "T-REF-30")]

    # A book resolved by label needs the version label.
    legacy = post(
        app,
        SSP_BOOKS,
        world.maya,
        {"code": "LEGACY-SKU-SSP", "name": "Legacy SKU SSP", "resolution_mode": "BY_LABEL"},
    )
    assert legacy.status_code == 201, legacy.text
    unlabelled = new_version(app, world.maya, legacy.json()["id"], label=None, effective_from=None)
    attach(app, world.maya, unlabelled["id"])
    labelless = submit(app, world.maya, unlabelled["id"])
    assert (labelless.status_code, fields(labelless)) == (
        422,
        [("legacy_version_label", "T-REF-28")],
    )


@pytest.mark.control("CTL-010")
def test_ctl_010_ssp_version_self_approval_blocked(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    assign(world.maya.member, "ssp_approver")
    maya = enrolled(app, clock, world.maya.member)
    version = new_version(app, maya, world.book_id, label="2026-H1", effective_from="2026-01-01")
    request_id = submitted(app, maya, version["id"])["approval_request_id"]
    assert request_of(app, maya, request_id)["can_decide"] is False
    refused = approve(app, request_id, maya)
    assert (refused.status_code, slug(refused)) == (403, "self-approval")
    assert shown(app, maya, version["id"])["status"] == "SUBMITTED"
    assert request_of(app, world.priya, request_id)["status"] == "PENDING"

    # The author never approves either: Tomas authors a version that Maya submits.
    tomas_member = colleague(world.tenant_id, "tomas")
    assign(tomas_member, "ssp_analyst")
    assign(tomas_member, "ssp_approver")
    tomas = enrolled(app, clock, tomas_member)
    authored = new_version(
        app,
        tomas,
        world.book_id,
        label="2027-H1",
        effective_from="2027-01-01",
        entries=(),
        copy_from_version_id=version["id"],
    )
    authored_request = submitted(app, maya, authored["id"])["approval_request_id"]
    by_author = approve(app, authored_request, tomas)
    assert (by_author.status_code, slug(by_author)) == (403, "self-approval")
    assert shown(app, maya, authored["id"])["status"] == "SUBMITTED"
    accepted = approve(app, authored_request, world.priya)
    assert (accepted.status_code, accepted.json()["status"]) == (200, "APPROVED")
    assert shown(app, maya, authored["id"])["status"] == "APPROVED"


@pytest.mark.control("CTL-011")
def test_ctl_011_approved_version_immutable_and_non_overlapping(app: FastAPI, world: World) -> None:
    first = approved(app, world, label="2026-H1", effective_from="2026-01-01")
    frozen = patch(
        app,
        f"{VERSIONS}/{first['id']}",
        world.maya,
        {"effective_to_date": "2026-06-30"},
        if_match=f'"r{first["row_version"]}"',
    )
    assert (frozen.status_code, slug(frozen)) == (409, "configuration-frozen")
    rival = new_version(
        app,
        world.maya,
        world.book_id,
        label="2026-H1b",
        effective_from="2026-01-01",
        entries=(),
        copy_from_version_id=first["id"],
    )
    request_id = submitted(app, world.maya, rival["id"])["approval_request_id"]
    overlapping = approve(app, request_id, world.priya)
    assert (overlapping.status_code, slug(overlapping)) == (409, "configuration-overlap")
    assert overlapping.json()["detail"] == (
        "Version 2026-H1b overlaps approved version 2026-H1 from 01 Jan 2026 with no end date "
        "for the same scope."
    )
    assert shown(app, world.maya, first["id"]) == first
    assert shown(app, world.maya, rival["id"])["status"] == "SUBMITTED"


# --- SN-8: the scope of a book is part of what an approval certifies -----------------------------

PILOT_SCOPE = {"entity_code": "AVM-US", "currency": "USD", "channel": None, "segment": "PILOT-ONLY"}
UNDER_APPROVAL = (
    "The scope of this SSP book cannot change while a version is submitted for approval. "
    "Withdraw the version, change the scope and submit it again."
)


def pilot_book(app: FastAPI, world: World) -> str:
    """A book for the pilot segment of AVM-US alone (T-REF-28 scope); returns its path."""
    world_calendar(app, world.maya)
    created = post(
        app,
        SSP_BOOKS,
        world.maya,
        {"code": "US-PILOT", "name": "Pilot price list", **PILOT_SCOPE},
    )
    assert created.status_code == 201, created.text
    return f"{SSP_BOOKS}/{created.json()['id']}"


def scope_of(book: Mapping[str, Any]) -> dict[str, Any]:
    return {name: book[name] for name in (*PILOT_SCOPE, "resolution_mode")}


@pytest.mark.control("CTL-007")
def test_sn8_book_scope_is_frozen_while_a_version_is_submitted(app: FastAPI, world: World) -> None:
    """Security finding SN-8 (ruling R-27). A version is submitted for the pilot segment of AVM-US.
    Before the fix the preparer widened the book to every entity and segment while the version was
    SUBMITTED, the content hash did not move, and the approval put the prices in force everywhere.
    Now the change is refused by name and writes nothing; each scope member alone is refused the
    same way; a member that is not scope stays editable; and the approval that follows certifies
    the scope that was submitted."""
    book_path = pilot_book(app, world)
    version = new_version(
        app, world.maya, book_path.rsplit("/", 1)[1], label="P1", effective_from="2026-01-01"
    )
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    reviewed = request_of(app, world.priya, request_id)
    assert reviewed["entity"]["code"] == "AVM-US"
    book = get(app, book_path, world.maya)
    assert scope_of(book.json()) == {**PILOT_SCOPE, "resolution_mode": "EFFECTIVE_DATE"}

    widened = patch(
        app,
        book_path,
        world.maya,
        {"entity_code": None, "segment": None},
        if_match=book.headers["ETag"],
    )
    assert widened.status_code == 409, widened.text
    assert (slug(widened), fields(widened)) == (
        "configuration-frozen",
        [("entity_code", "REQ-PLT-014"), ("segment", "REQ-PLT-014")],
    )
    assert {error["message"] for error in widened.json()["errors"]} == {UNDER_APPROVAL}
    for name, value in (
        ("currency", None),
        ("channel", "direct"),
        ("resolution_mode", "BY_LABEL"),
    ):
        refused = patch(app, book_path, world.maya, {name: value}, if_match=book.headers["ETag"])
        assert (refused.status_code, slug(refused), fields(refused)) == (
            409,
            "configuration-frozen",
            [(name, "REQ-PLT-014")],
        ), name

    # Nothing was written: the book, its ETag and audit trail, the request and its hash.
    unchanged = get(app, book_path, world.maya)
    assert (unchanged.headers["ETag"], unchanged.json()) == (book.headers["ETag"], book.json())
    assert audits(world, "ssp_book.update") == []
    pending = request_of(app, world.priya, request_id)
    assert (pending["status"], pending["entity"], pending["subject"]["content_sha256"]) == (
        "PENDING",
        reviewed["entity"],
        reviewed["subject"]["content_sha256"],
    )

    # A member that is not scope stays editable while the version is under approval.
    renamed = patch(
        app, book_path, world.maya, {"name": "Pilot list 2026"}, if_match=book.headers["ETag"]
    )
    assert renamed.status_code == 200, renamed.text
    assert [event["after"] for event in audits(world, "ssp_book.update")] == [
        {"name": "Pilot list 2026"}
    ]

    # Positive control: the approver approves, and what is in force is the scope they reviewed.
    decided = approve(app, request_id, world.priya)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    assert shown(app, world.maya, version["id"])["status"] == "APPROVED"
    assert scope_of(get(app, book_path, world.maya).json()) == {
        **PILOT_SCOPE,
        "resolution_mode": "EFFECTIVE_DATE",
    }


def test_sn8_the_approved_content_of_a_version_names_the_scope_of_its_book(
    app: FastAPI, world: World
) -> None:
    """04 §16.10 rev 1.110: the book's scope is a member of the version's content. The legitimate
    way to another scope is to withdraw the version, change the book and submit again — and the
    new request then carries another hash over the same entries, because the scope differs."""
    assert tuple(books.SCOPE_MEMBERS) == subjects._SSP_SCOPE
    book_path = pilot_book(app, world)
    book_id = book_path.rsplit("/", 1)[1]
    version = new_version(app, world.maya, book_id, label="P1", effective_from="2026-01-01")
    first = submitted(app, world.maya, version["id"])
    first_request = request_of(app, world.priya, first["approval_request_id"])
    assert first["content_sha256"] == first_request["subject"]["content_sha256"]
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        content = subjects.ssp_book_version_content(session, UUID(version["id"]))
        entity_id = session.execute(
            select(ssp_book.c.entity_id).where(ssp_book.c.id == UUID(book_id))
        ).scalar_one()
    assert content["scope"] == {
        "entity_id": str(entity_id),
        "currency": "USD",
        "channel": None,
        "segment": "PILOT-ONLY",
        "resolution_mode": "EFFECTIVE_DATE",
    }

    withdrawn = post(app, f"{VERSIONS}/{version['id']}/withdraw", world.maya, {})
    assert withdrawn.status_code == 200, withdrawn.text
    book = get(app, book_path, world.maya)
    widened = patch(
        app,
        book_path,
        world.maya,
        {"entity_code": None, "segment": None},
        if_match=book.headers["ETag"],
    )
    assert widened.status_code == 200, widened.text
    resubmitted = submit(app, world.maya, version["id"])
    assert resubmitted.status_code == 200, resubmitted.text
    second = resubmitted.json()
    second_request = request_of(app, world.priya, second["approval_request_id"])
    assert second["content_sha256"] == second_request["subject"]["content_sha256"]
    assert second["content_sha256"] != first["content_sha256"]
    # The request is scoped as the book now is: every entity.
    assert (first_request["entity"]["code"], second_request["entity"]) == ("AVM-US", None)


@pytest.mark.control("CTL-007")
def test_sn8_a_scope_changed_behind_the_command_makes_the_approval_stale(
    app: FastAPI, world: World
) -> None:
    """The second half of ruling R-27 (REQ-PLT-014; DG-KRN-APR-02). Were the scope to move while a
    version is SUBMITTED by a path other than the command — here a direct update of the row — the
    decision recomputes the content, finds another scope than the one submitted, voids the request
    and approves nothing."""
    book_path = pilot_book(app, world)
    book_id = book_path.rsplit("/", 1)[1]
    version = new_version(app, world.maya, book_id, label="P1", effective_from="2026-01-01")
    request_id = submitted(app, world.maya, version["id"])["approval_request_id"]
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        session.execute(update(ssp_book).where(ssp_book.c.id == UUID(book_id)).values(segment=None))
    decided = approve(app, request_id, world.priya)
    assert (decided.status_code, slug(decided)) == (409, "stale-approval")
    with tenant_session(ctx, read_only=True) as session:
        request = (
            session.execute(
                select(approval_request.c.status, approval_request.c.void_reason).where(
                    approval_request.c.id == UUID(request_id)
                )
            )
            .mappings()
            .one()
        )
    assert (str(request["status"]), str(request["void_reason"])) == ("VOIDED", "STALE_SUBJECT")
    assert shown(app, world.maya, version["id"])["status"] != "APPROVED"


# --- a document a rule asks for is one whose file can still be read ------------------------------
# Item EVIDENCE-COUNT-SHREDDED-1 (supervisor rulings R-119 (g), R-120 (g), R-121 (l); 04 rev 1.216
# T-PLT-29 "A document a rule asks for"; 03 rev 1.131 REQ-SSP-008).

FILES = "/api/v1/files"
SHRED_REASON = "DSR-2026-0917: erase the person's data in this document"


def _answer(response: HttpResponse) -> tuple[int, str | None]:
    """(status, problem) — no problem for an answer that is none."""
    return (response.status_code, slug(response) if response.status_code >= 400 else None)


def _person(app: FastAPI, clock: FrozenClock, world: World, name: str, role: str) -> Actor:
    someone = colleague(world.tenant_id, name)
    assign(someone, role)
    return enrolled(app, clock, someone)


def _book(app: FastAPI, world: World, code: str) -> str:
    created = post(app, SSP_BOOKS, world.maya, {"code": code, "name": code, "currency": "USD"})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _study(app: FastAPI, actor: Actor, version_id: str, name: str) -> UUID:
    """A study of its own bytes uploaded and attached to the version; the stored file's id."""
    uploaded = call(
        app,
        "POST",
        FILES,
        data={"purpose": "SSP_STUDY"},
        files={"file": (name, upload_fixtures.PDF + f"% {name}\n".encode(), "application/pdf")},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    body = {
        "file_object_id": uploaded.json()["id"],
        "subject_type": "ssp_book_version",
        "subject_id": version_id,
    }
    attached = post(app, "/api/v1/attachments", actor, body)
    assert attached.status_code == 201, attached.text
    return UUID(str(uploaded.json()["id"]))


def _sent(app: FastAPI, world: World, version_id: str) -> str:
    """Submit the version; the approval request's id."""
    response = submit(app, world.maya, version_id, comment="Supported by standalone sales.")
    assert response.status_code == 200, response.text
    return str(response.json()["approval_request_id"])


def _last_approver(app: FastAPI, world: World, request_id: str) -> Actor:
    """Take the request to its last step; the approver whose decision approves the version."""
    if len(request_of(app, world.priya, request_id)["steps"]) == 1:
        return world.priya
    first = approve(app, request_id, world.priya)
    assert first.status_code == 200 and first.json()["status"] == "PENDING", first.text
    return world.marcus


def test_evidence_count_shredded_1_a_shredded_study_is_no_study(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """A version is submitted, and approved, only with its SSP study (REQ-SSP-008). The study of
    a DRAFT is no evidence yet and ``file.shred`` erases it; the study of a submitted version is
    erased by an approved ``EVIDENCE_SHRED`` request. Either way the attachment row stays, live
    — and it counted: a version was submitted, and another approved, on a study that no longer
    exists. Both are refused as a version without its study; a study that can be read lets the
    version through."""
    tess = _person(app, clock, world, "tess", "tenant_admin")
    carla = _person(app, clock, world, "carla", "controller")
    # At the submission: the study of a draft, shredded directly.
    draft = new_version(
        app, world.maya, world.book_id, label="2026-H1", effective_from="2026-01-01"
    )
    study = _study(app, world.maya, draft["id"], "study-h1.pdf")
    erased = post(app, f"{FILES}/{study}/shred", tess, {"reason": SHRED_REASON})
    assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text
    at_submission = submit(app, world.maya, draft["id"])
    # At the approval: the study of a submitted version of another book, shredded by approval.
    other = new_version(
        app, world.maya, _book(app, world, "UK-LIST"), label="2026-H1", effective_from="2026-01-01"
    )
    held = _study(app, world.maya, other["id"], "study-uk.pdf")
    request_id = _sent(app, world, other["id"])
    asked = post(app, f"{FILES}/{held}/request-shred", tess, {"reason": SHRED_REASON})
    assert asked.status_code == 200, asked.text
    lifted = approve(app, str(asked.json()["approval_request_id"]), carla)
    assert lifted.status_code == 200, lifted.text
    at_approval = approve(app, request_id, _last_approver(app, world, request_id))

    assert {"submit": _answer(at_submission), "approve": _answer(at_approval)} == {
        "submit": (422, "ssp-study-required"),
        "approve": (422, "ssp-study-required"),
    }
    assert shown(app, world.maya, draft["id"])["status"] == "DRAFT"
    assert shown(app, world.maya, other["id"])["status"] == "SUBMITTED"
    assert request_of(app, world.priya, request_id)["status"] == "PENDING"

    # Positive controls: with a study that can be read the draft is submitted, and the submitted
    # version — withdrawn, supported again, submitted again — is approved.
    _study(app, world.maya, draft["id"], "study-h1-second.pdf")
    assert submit(app, world.maya, draft["id"]).status_code == 200
    withdrawn = post(
        app, f"{VERSIONS}/{other['id']}/withdraw", world.maya, {"comment": "The study is gone."}
    )
    assert withdrawn.status_code == 200, withdrawn.text
    _study(app, world.maya, other["id"], "study-uk-second.pdf")
    again = _sent(app, world, other["id"])
    approved_now = approve(app, again, _last_approver(app, world, again))
    assert approved_now.status_code == 200, approved_now.text
    assert shown(app, world.maya, other["id"])["status"] == "APPROVED"


def test_evidence_count_shredded_1_the_submission_and_the_approval_wait_for_a_shred(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The file row is locked by the commands that count the study, as by the shred, so the
    later of the two sees what the earlier committed. A shred in flight — the row locked and
    marked, not committed — holds the submission of the version back, and the approval of
    another; when it commits, each finds no study."""
    draft = new_version(
        app, world.maya, world.book_id, label="2026-H1", effective_from="2026-01-01"
    )
    study = _study(app, world.maya, draft["id"], "study-h1.pdf")
    submitted_beside = beside_a_shred(
        world.tenant_id, study, lambda: submit(app, world.maya, draft["id"]), at=clock.now()
    )
    other = new_version(
        app, world.maya, _book(app, world, "UK-LIST"), label="2026-H1", effective_from="2026-01-01"
    )
    held = _study(app, world.maya, other["id"], "study-uk.pdf")
    request_id = _sent(app, world, other["id"])
    last = _last_approver(app, world, request_id)
    approved_beside = beside_a_shred(
        world.tenant_id, held, lambda: approve(app, request_id, last), at=clock.now()
    )
    assert {
        "submit": (submitted_beside.waited, *_answer(submitted_beside.response)),
        "approve": (approved_beside.waited, *_answer(approved_beside.response)),
    } == {
        "submit": (True, 422, "ssp-study-required"),
        "approve": (True, 422, "ssp-study-required"),
    }
    assert shown(app, world.maya, draft["id"])["status"] == "DRAFT"
    assert shown(app, world.maya, other["id"])["status"] == "SUBMITTED"
