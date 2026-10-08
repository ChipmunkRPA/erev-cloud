"""Access, configuration, approvals and audit registers (SCREENS_B §5.6.5 RPT-23 to RPT-26, RPT-43,
RPT-44; PRD J-01.1 to J-01.5, J-17.5, J-17.6, J-17.8, J-22.1 to J-22.8, BR-PLT-02; 03 REQ-RPT-001,
REQ-RPT-022, REQ-PLT-010, REQ-PLT-018 to REQ-PLT-020; BUILD_SPEC RPS-10).

Worlds, each built through the product's commands; every report runs through ``POST
/report-runs`` and its ``REPORT_RUN`` job, as ``test_ssp_reports.py`` does; the frozen clock starts
at 2026-09-12T12:00:00Z.

- ``support.worlds.ssp_h2_publication`` (PRD J-02): US-LIST ``2026-H1`` and ``2026-H2`` authored by
  Maya and approved by Priya, then Priya and Marcus. The configuration register test adds the
  account mapping AVM-MAP-2026-01, authored by Maya and approved by Marcus (J-17.8).
- ``access_world`` of this module (PRD J-01.1 to J-01.3, J-22.1, J-22.2): the provisioned workspace
  whose bootstrap administrator Tomas accepts the invitation, creates AVM-US and invites Maya,
  Priya, Marcus, Nikhil, Grace and Hannah while setup is incomplete (rule ``AUTO-BOOTSTRAP``
  approves the grants); the invited people but Nikhil accept; Tomas opens the first period, which
  completes setup (BR-PLT-02); he then invites Lena as Revenue Reviewer, which Grace approves.
  ``lena_exception`` continues with J-22.6 and J-22.7: the SoD-3 refusal, the exception Grace
  approves and the Revenue Accountant grant under it. Two deviations from the PRD, both product
  limits: a grant names all entities, because a grant scoped to entity codes fails closed with
  ``EREV-REF-002`` (BS1-D-06; J-22.1 scopes Lena to AVM-DE), and Hannah (Auditor) runs the
  reports, because the default role ``tenant_admin`` holds no ``report.run`` (J-22.8 names Tomas).
- ``support.worlds.k03_castellan`` (PRD WLD-K-03): ``PRJ-CB-2026-01`` with its estimates for the
  audit log export; ``support.worlds.k01_pellworth`` for the catalogue.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLE_NAMES, DEFAULT_ROLES
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    account_mapping_version,
    approval_decision,
    approval_request,
    audit_chain_head,
    audit_chain_verification,
    audit_event,
    outbox_message,
    report_definition,
    role_assignment,
    rule_test_case,
    sod_rule,
    tenant_membership,
)
from erev_api.domain.platform import audit_jobs
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import audit_log_export as audit_export
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import Select, delete, exc, insert, select, update
from support.db import TestDatabase
from support.factories import (
    published_mapping,
    stamp_test_release,
    tenant_factory,
    tenant_id_of,
    workspace,
)
from support.http import call
from support.links import emailed_token
from support.principals import (
    PASSWORD,
    Actor,
    Member,
    colleague,
    cookie_headers,
    enrolled,
    sign_in,
    step_up,
)
from support.principals import workspace as signed_workspace
from support.reference import PERIODS, assign, calendar, entity, get, holding, periods, post, slug
from support.rows import insert_approval_delegation, insert_contract_rows, tamper_audit_event
from support.worlds import (
    AVM_US,
    H2_LABEL,
    H2_PRIYA_COMMENT,
    K03_EXTERNAL_ID,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    SEPTEMBER_2026,
    US_LIST,
    K03World,
    ReportWorld,
    SspPublicationWorld,
    k01_pellworth,
    k03_castellan,
    k03_change_order,
    report_run,
    run_now,
    ssp_h2_publication,
    ssp_version_submitted,
)

USERS: Final = "/api/v1/users"
ROLES: Final = "/api/v1/roles"
ROLE_ASSIGNMENTS: Final = "/api/v1/role-assignments"
SOD_EXCEPTIONS: Final = "/api/v1/sod-exceptions"
APPROVALS: Final = "/api/v1/approvals"
ACCEPT: Final = "/api/v1/session/accept-invitation"
VERIFY: Final = "/api/v1/audit-events/verify"
DEFINITIONS: Final = "/api/v1/report-definitions"
DELEGATIONS: Final = "/api/v1/approval-delegations"
MINUTE: Final = timedelta(minutes=1)
SETUP_GRANT: Final = "Setup grant (AUTO-BOOTSTRAP)"
MAPPING_NAME: Final = "AVM-MAP-2026-01"
# SCREENS_B RPT-25 sample world (PRD J-22.7).
CONTROL: Final = (
    "Controller reviews every approval by Lena Fischer monthly using the approvals register."
)
LENA_COMMENT: Final = "Joins the revenue team as a second reviewer."
EXCEPTION_COMMENT: Final = "Reviewed the compensating control."
# PRD §1.2 personas and J-01.3: (first name, display name, role codes).
PEOPLE: Final = (
    ("maya", "Maya Chen", ("revenue_accountant", "ssp_analyst")),
    ("priya", "Priya Raman", ("revenue_reviewer", "ssp_approver")),
    ("marcus", "Marcus Webb", ("controller",)),
    ("nikhil", "Nikhil Rao", ("integration_admin",)),
    ("grace", "Grace Okafor", ("tenant_admin",)),
    ("hannah", "Hannah Lindqvist", ("auditor",)),
)
ACCEPTING: Final = ("maya", "priya", "marcus", "grace", "hannah")
INSTANT: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
CANONICAL_INSTANT: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def publication(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> SspPublicationWorld:
    return ssp_h2_publication(app, keyring, clock, files)


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # a row key occurs once
    return found


def utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def stored(tenant_id: UUID, statement: Select[Any]) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def decide(
    app: FastAPI, approver: Actor, request_id: str, comment: str, *, verb: str = "approve"
) -> dict[str, Any]:
    """``POST /approvals/{id}/approve`` (with the hashes the request shows) or ``/reject``."""
    shown = get(app, f"{APPROVALS}/{request_id}", approver)
    assert shown.status_code == 200, shown.text
    body: dict[str, Any] = {"comment": comment}
    if verb == "approve":
        body["subject_content_sha256"] = shown.json()["subject"]["content_sha256"]
        if shown.json()["impact_preview"] is not None:
            body["impact_preview_sha256"] = shown.json()["impact_preview"]["sha256"]
    decided = post(app, f"{APPROVALS}/{request_id}/{verb}", approver, body)
    assert decided.status_code == 200, decided.text
    return dict(decided.json())


def direct(world: ReportWorld, code: str, parameters: Mapping[str, Any], **given: Any) -> Any:
    """The builder of ``code`` called in a unit of work: the way a refusal is read."""
    with world.place.uow() as uow:
        return framework.BUILDERS[code](
            uow,
            ReportParams(
                report_code=code,
                report_version=1,
                parameters=dict(parameters),
                entity_ids=(world.entity_id,),
                known_at=world.place.clock.now(),
                **given,
            ),
        )


# --- the access world (PRD J-01.1 to J-01.3, J-22.1, J-22.2) --------------------------------------


@dataclass(slots=True)
class AccessWorld:
    """The provisioned workspace with its people; ``report.place.author`` is Hannah (Auditor)."""

    report: ReportWorld
    clock: FrozenClock
    people: Mapping[str, Member]  # by first name
    roles: Mapping[str, str]  # role code → id
    lena_request_id: str  # J-22.1: the Revenue Reviewer request Grace approved
    actors: dict[str, Actor] = field(default_factory=dict)

    @property
    def app(self) -> FastAPI:
        return self.report.app

    @property
    def tenant_id(self) -> UUID:
        return self.report.tenant_id

    def fresh(self, name: str) -> Actor:
        """The member's session after a fresh TOTP verification (BR-PLT-06); call it once per
        clock instant, because a TOTP step verifies once."""
        self.actors[name] = step_up(self.app, self.clock, self.actors[name])
        return self.actors[name]

    def email(self, name: str) -> str:
        return self.people[name].email


def _accept(app: FastAPI, someone: Member) -> None:
    """Accept the invitation with the token of its email (04 T-PLT-07; PRD J-01.1)."""
    (message,) = stored(
        someone.tenant_id,
        select(outbox_message.c.payload).where(
            outbox_message.c.aggregate_id == someone.membership_id
        ),
    )
    token = emailed_token(message["payload"], prefix="/accept-invitation#token=")
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["id"] == str(someone.user_id)


def _invite(
    app: FastAPI,
    admin: Actor,
    roles: Mapping[str, str],
    *,
    email: str,
    display_name: str,
    codes: Sequence[str],
) -> dict[str, Any]:
    """``POST /users`` with one all-entities grant per role code; API-S-User."""
    body = {
        "email": email,
        "display_name": display_name,
        "roles": [
            {"role_id": roles[code], "is_all_entities": True, "entity_codes": []} for code in codes
        ],
    }
    invited = post(app, USERS, admin, body)
    assert invited.status_code == 201, invited.text
    return dict(invited.json())


def _member(tenant_id: UUID, user: Mapping[str, Any]) -> Member:
    return Member(
        user_id=UUID(str(user["user_id"])),
        email=str(user["email"]),
        tenant_id=tenant_id,
        membership_id=UUID(str(user["id"])),
    )


def access_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> AccessWorld:
    """The module docstring's access world. The clock advances one minute before the period
    opens, before Lena's invitation and before Grace's approval."""
    code = f"avm-{secrets.token_hex(5)}"
    domain = f"{code}.test"
    result = tenant_factory(keyring=keyring, clock=clock, code=code, admin_email=f"tomas@{domain}")
    tenant_id = tenant_id_of(result)
    (admin,) = stored(
        tenant_id,
        select(tenant_membership.c.user_id).where(
            tenant_membership.c.id == result.admin_membership_id
        ),
    )
    tomas_member = Member(
        user_id=UUID(str(admin["user_id"])),
        email=f"tomas@{domain}",
        tenant_id=tenant_id,
        membership_id=result.admin_membership_id,
    )
    _accept(app, tomas_member)  # J-01.1
    tomas = enrolled(app, clock, tomas_member)
    created = entity(app, tomas, code=AVM_US, calendar_id=calendar(app, tomas, years=(2026,)))
    listed = get(app, ROLES, tomas, {"limit": 200})
    assert listed.status_code == 200, listed.text
    roles = {str(item["code"]): str(item["id"]) for item in listed.json()["items"]}
    people: dict[str, Member] = {"tomas": tomas_member}
    for name, display_name, codes in PEOPLE:  # J-01.3
        invited = _invite(
            app, tomas, roles, email=f"{name}@{domain}", display_name=display_name, codes=codes
        )
        assert [(item["status"], item["setup_grant"]) for item in invited["roles"]] == [
            ("ACTIVE", True)
        ] * len(codes), invited
        people[name] = _member(tenant_id, invited)
    for name in ACCEPTING:
        _accept(app, people[name])
    actors = {"tomas": tomas}
    for name in ("grace", "marcus", "priya"):
        actors[name] = enrolled(app, clock, people[name])
    sign_in(app, people["maya"].email)  # a sign-in without an MFA factor
    actors["hannah"] = signed_workspace(app, people["hannah"], sign_in(app, people["hannah"].email))

    clock.advance(MINUTE)  # J-01.2: the first open period completes setup (BR-PLT-02)
    first = periods(app, tomas, entity=AVM_US)[0]
    opened = post(app, f"{PERIODS}/{first['id']}/open", tomas, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text

    clock.advance(MINUTE)  # J-22.1: after setup the grant waits for another administrator
    lena = _invite(
        app,
        tomas,
        roles,
        email=f"lena@{domain}",
        display_name="Lena Fischer",
        codes=("revenue_reviewer",),
    )
    ((status, setup_grant, request_id),) = [
        (item["status"], item["setup_grant"], item["approval_request_id"]) for item in lena["roles"]
    ]
    assert (status, setup_grant) == ("REQUESTED", False), lena
    people["lena"] = _member(tenant_id, lena)
    stamp_test_release()
    world = AccessWorld(
        report=ReportWorld(
            place=workspace(app, clock, keyring, files, actors["hannah"]),
            priya=actors["priya"],
            marcus=actors["marcus"],
            runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
            entity_id=UUID(str(created["id"])),
            contracts=MappingProxyType({}),
        ),
        clock=clock,
        people=MappingProxyType(people),
        roles=MappingProxyType(roles),
        lena_request_id=str(request_id),
        actors=actors,
    )
    clock.advance(MINUTE)  # J-22.2: Grace approves with a fresh TOTP
    approved = decide(app, world.fresh("grace"), str(request_id), LENA_COMMENT)
    assert approved["status"] == "APPROVED", approved
    _accept(app, people["lena"])
    return world


def lena_exception(world: AccessWorld) -> dict[str, Any]:
    """PRD J-22.6 and J-22.7: Tomas may not add Revenue Accountant to Lena (SoD-3); he requests an
    exception with the compensating control for 90 days, Grace approves it, and the grant Tomas
    then requests under the exception is approved by Grace. Returns the exception as requested,
    with ``assignment_request_id``. One minute passes before each step."""
    app, clock = world.app, world.clock
    lena = world.people["lena"]
    body = {"membership_id": str(lena.membership_id), "role_id": world.roles["revenue_accountant"]}
    clock.advance(MINUTE)
    tomas = world.fresh("tomas")
    blocked = post(app, ROLE_ASSIGNMENTS, tomas, body)
    assert (blocked.status_code, slug(blocked)) == (409, "sod-conflict"), blocked.text
    (error,) = blocked.json()["errors"]
    assert error["rule_id"] == "SoD-3"
    assert error["message"].startswith("Separation of duties conflict SoD-3: ")
    start = clock.now()
    requested = post(
        app,
        SOD_EXCEPTIONS,
        tomas,
        {
            "sod_rule_code": "SoD-3",
            "membership_id": str(lena.membership_id),
            "compensating_control": CONTROL,
            "valid_from": start.isoformat(),
            "valid_to": (start + timedelta(days=90)).isoformat(),
            "comment": "Small team until a second reviewer joins.",
        },
    )
    assert requested.status_code == 201, requested.text
    exception = dict(requested.json())
    clock.advance(MINUTE)
    decided = decide(
        app, world.fresh("grace"), str(exception["approval_request_id"]), EXCEPTION_COMMENT
    )
    assert decided["status"] == "APPROVED", decided
    clock.advance(MINUTE)
    granted = post(
        app, ROLE_ASSIGNMENTS, world.fresh("tomas"), {**body, "sod_exception_id": exception["id"]}
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["status"] == "REQUESTED", granted.text
    clock.advance(MINUTE)
    assignment_request_id = str(granted.json()["approval_request_id"])
    approved = decide(
        app, world.fresh("grace"), assignment_request_id, "Covered by the approved exception."
    )
    assert approved["status"] == "APPROVED", approved
    return {**exception, "assignment_request_id": assignment_request_id, "valid_from_at": start}


@pytest.fixture
def access(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> AccessWorld:
    return access_world(app, keyring, clock, files)


# --- RPT-23 ---------------------------------------------------------------------------------------


def test_config_change_register_author_differs(
    publication: SspPublicationWorld, clock: FrozenClock
) -> None:
    """PRD J-17.8, J-01.5: the register for Jan to Sep 2026 lists account mapping
    ``AVM-MAP-2026-01`` and SSP book version ``US-LIST 2026-H2``, each with author ≠ approver and
    its field diff."""
    world = publication.report
    app = world.app
    assign(world.marcus.member, "controller")  # PRD §1.2: Marcus is the Controller
    clock.advance(MINUTE)
    marcus = step_up(app, clock, world.marcus)
    mapping_id = published_mapping(app, world.maya, marcus)
    clock.advance(MINUTE)

    run, rows = report_run(
        world, "config_change_register", {"from_date": "2026-01-01", "to_date": "2026-09-30"}
    )
    assert run["status"] == "SUCCEEDED"
    found = {str(row["object_label"]): row for row in rows}
    assert len(found) == len(rows) == 3
    assert [row["row_key"] for row in rows] == sorted(f"change:{row['request_no']}" for row in rows)

    mapping = found[f"{MAPPING_NAME} v1"]
    (mapping_request,) = stored(
        world.tenant_id,
        select(approval_request).where(approval_request.c.subject_id == UUID(mapping_id)),
    )
    assert (mapping["request_no"], mapping["subject_type"], mapping["status"]) == (
        mapping_request["request_no"],
        "ACCOUNT_MAPPING_VERSION",
        "APPROVED",
    )
    assert mapping["effective_from"] == "2026-01-01"
    assert "maya" in mapping["author"].lower() and mapping["approvers"] == "Marcus"
    assert mapping["author_differs"] is True
    assert (mapping["submitted_at"], mapping["decided_at"]) == (
        utc(mapping_request["submitted_at"]),
        utc(mapping_request["decided_at"]),
    )
    # the field diff the approval recorded: the published content against no prior version
    (published,) = stored(
        world.tenant_id,
        select(audit_event.c.diff).where(
            audit_event.c.object_id == UUID(mapping_id),
            audit_event.c.action == "account_mapping_version.published",
        ),
    )
    content = [
        entry
        for entry in published["diff"]
        if entry["path"].split(".")[0] not in ("status", "published_at", "published_by")
    ]
    assert mapping["changed_field_count"] == len(content) > 0
    assert all(entry["before"] is None for entry in content)  # the first version of the mapping
    # REQ-POL-006: the mapping's test attached its impact simulation; it has no example cases
    (version,) = stored(
        world.tenant_id,
        select(account_mapping_version.c.impact_simulation_file_id).where(
            account_mapping_version.c.id == UUID(mapping_id)
        ),
    )
    assert version["impact_simulation_file_id"] is not None
    cases = stored(
        world.tenant_id,
        select(rule_test_case.c.id).where(rule_test_case.c.subject_id == UUID(mapping_id)),
    )
    assert (mapping["simulation_attached"], mapping["test_evidence_count"]) == (True, len(cases))

    h2 = found[f"{US_LIST} {H2_LABEL} v2"]
    assert (h2["subject_type"], h2["status"], h2["effective_from"]) == (
        "SSP_BOOK_VERSION",
        "APPROVED",
        "2026-10-01",
    )
    assert "maya" in h2["author"].lower() and h2["approvers"] == "Priya, Marcus"
    assert h2["author_differs"] is True
    assert h2["decided_at"] == publication.h2["published_at"]
    assert h2["changed_field_count"] == 1  # J-02-AC-2: AVM-PLAT-100 is the one changed entry
    h1 = found[f"{US_LIST} 2026-H1 v1"]
    assert (h1["approvers"], h1["author_differs"], h1["changed_field_count"]) == ("Priya", True, 7)
    assert run["control_totals"] == {
        "row_count": 3,
        "author_equals_approver_count": 0,
        "from_date": "2026-01-01",
        "to_date": "2026-09-30",
    }

    # a rejected version is a decided change that changed nothing
    drafted = post(
        app,
        f"/api/v1/ssp-books/{publication.book_id}/versions",
        world.maya,
        {
            "copy_from_version_id": publication.h2["id"],
            "legacy_version_label": "2027-H1",
            "effective_from_date": "2027-01-01",
            "methodology_label": "Observable prices, second review",
        },
    )
    assert drafted.status_code == 201, drafted.text
    request_id = ssp_version_submitted(
        app, world.maya, str(drafted.json()["id"]), "Carried forward unchanged."
    )
    clock.advance(MINUTE)
    rejected = decide(
        app,
        step_up(app, clock, world.priya),
        request_id,
        "No study supports a new version.",
        verb="reject",
    )
    assert rejected["status"] == "REJECTED", rejected
    clock.advance(MINUTE)
    _, again = report_run(world, "config_change_register", {"subject_types": ["SSP_BOOK_VERSION"]})
    assert [row["subject_type"] for row in again] == ["SSP_BOOK_VERSION"] * 3
    (refused,) = [row for row in again if row["status"] == "REJECTED"]
    assert refused["object_label"] == f"{US_LIST} 2027-H1 v3"
    assert (refused["approvers"], refused["changed_field_count"]) == (None, 0)
    assert refused["author_differs"] is True and refused["decided_at"] == rejected["decided_at"]

    # a range before the decisions lists nothing
    _, earlier = report_run(
        world, "config_change_register", {"from_date": "2026-01-01", "to_date": "2026-08-31"}
    )
    assert earlier == []


# --- RPT-24 ---------------------------------------------------------------------------------------


def test_user_access_listing_fields(access: AccessWorld, clock: FrozenClock) -> None:
    """PRD J-17.6, J-01.3, BR-PLT-02: every membership with roles, entity scopes, last login,
    grant date and grantor; the grants rule ``AUTO-BOOTSTRAP`` approved carry "Setup grant"."""
    world = access.report
    app = world.app
    clock.advance(MINUTE)
    run, rows = report_run(world, "user_access_listing", {})
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    expected = {
        f"access:{access.email(name)}:{code}"
        for name, _, codes in (*PEOPLE, ("tomas", "", ("tenant_admin",)))
        for code in codes
    } | {f"access:{access.email('lena')}:revenue_reviewer"}
    assert set(found) == expected and len(rows) == 10
    assert list(found) == sorted(found)  # ordered by email, then role code

    # the listing agrees with API-S-User, role by role (the product's own read of the same facts)
    users = get(app, USERS, access.actors["tomas"], {"limit": 200})
    assert users.status_code == 200, users.text
    by_email = {str(item["email"]): item for item in users.json()["items"]}
    assert set(by_email) == {member.email for member in access.people.values()}
    names = {access.email(name): display_name for name, display_name, _ in PEOPLE}
    names |= {access.email("lena"): "Lena Fischer", access.email("tomas"): access.email("tomas")}
    for row in rows:
        user = by_email[row["email"]]
        (role,) = [item for item in user["roles"] if row["row_key"].endswith(item["role"]["code"])]
        assert (row["display_name"], row["membership_status"]) == (
            names[row["email"]],
            user["status"],
        )
        assert (row["role_name"], row["entity_scope"]) == (role["role"]["name"], [])
        assert row["granted_at"] == role["granted_at"] and INSTANT.match(row["granted_at"])
        assert (row["mfa_enrolled"], row["last_login_at"]) == (
            user["mfa_enrolled"],
            user["last_login_at"],
        )
        assert (row["sod_exception_id"], row["revoked_at"]) == (None, None)
        if row["email"] == access.email("lena"):
            assert role["setup_grant"] is False and row["granted_by"] == "Grace Okafor"
        else:
            assert role["setup_grant"] is True and row["granted_by"] == SETUP_GRANT
    # J-01.3: the people Tomas invited during setup, and the states the world leaves them in
    nikhil = found[f"access:{access.email('nikhil')}:integration_admin"]
    # an INVITED row shows no MFA state and no last sign-in (04 T-PLT-02 rev 1.316): null, where
    # the MFA cell answered false
    assert (nikhil["membership_status"], nikhil["mfa_enrolled"], nikhil["last_login_at"]) == (
        "INVITED",
        None,
        None,
    )
    maya = found[f"access:{access.email('maya')}:revenue_accountant"]
    assert (maya["membership_status"], maya["mfa_enrolled"]) == ("ACTIVE", False)
    assert INSTANT.match(maya["last_login_at"])
    marcus = found[f"access:{access.email('marcus')}:controller"]
    assert (marcus["role_name"], marcus["mfa_enrolled"]) == ("Controller", True)
    assert run["control_totals"] == {
        "membership_count": 8,
        "assignment_count": 10,
        "as_of": run["parameters"]["known_at"],
    }

    # D-80 rule 2: as of the instant before Grace's approval Lena held no role, and is listed so
    before_lena = clock.now() - 2 * MINUTE
    _, earlier = report_run(world, "user_access_listing", {"as_of": utc(before_lena)})
    lena = keyed(earlier)[f"access:{access.email('lena')}:"]
    assert (lena["role_name"], lena["granted_at"], lena["granted_by"]) == (None, None, None)
    assert len(earlier) == 10

    # removal revokes the roles: the member leaves the listing, returns with include_removed and
    # stays in a listing as of an instant before the removal, with the revocation shown
    clock.advance(MINUTE)
    removed = post(
        app,
        f"{USERS}/{access.people['nikhil'].membership_id}/remove",
        access.fresh("tomas"),
        {"reason": "The integration project was cancelled."},
    )
    assert removed.status_code == 200, removed.text
    removed_at = clock.now()
    clock.advance(MINUTE)
    after, current = report_run(world, "user_access_listing", {})
    assert f"access:{access.email('nikhil')}:integration_admin" not in keyed(current)
    assert (
        after["control_totals"]["membership_count"],
        after["control_totals"]["assignment_count"],
    ) == (7, 9)
    _, included = report_run(world, "user_access_listing", {"include_removed": True})
    gone = keyed(included)[f"access:{access.email('nikhil')}:integration_admin"]
    assert (gone["membership_status"], gone["revoked_at"]) == ("REMOVED", utc(removed_at))
    assert gone["granted_by"] == SETUP_GRANT
    _, as_of = report_run(
        world, "user_access_listing", {"as_of": utc(removed_at - timedelta(seconds=1))}
    )
    held = keyed(as_of)[f"access:{access.email('nikhil')}:integration_admin"]
    assert (held["role_name"], held["revoked_at"]) == ("Integration Admin", utc(removed_at))

    # SCREENS_B RPT-24 validation copy; REGISTER-CUTOFF-1 for the explicit historical read
    with pytest.raises(Problem) as future:
        direct(world, "user_access_listing", {"as_of": utc(clock.now() + MINUTE)})
    (error,) = future.value.errors
    assert (error.field, error.message) == (
        "parameters.as_of",
        "Enter a time that is not in the future.",
    )
    with pytest.raises(Problem) as refused:
        direct(world, "user_access_listing", {}, historical=True)
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at"
    assert "keep no history of the status, name or last sign-in" in error.message

    # an entity-scoped grant: no command creates one yet (BS1-D-06 fails closed with
    # EREV-REF-002), so this one row is written by the test support helper
    assign(access.people["hannah"], "viewer", entity_ids=[world.entity_id])
    clock.advance(MINUTE)
    _, scoped = report_run(world, "user_access_listing", {})
    viewer = keyed(scoped)[f"access:{access.email('hannah')}:viewer"]
    assert (viewer["entity_scope"], viewer["granted_by"]) == ([AVM_US], None)


def test_user_access_listing_states_a_removal_that_a_later_invitation_ended(
    access: AccessWorld, clock: FrozenClock
) -> None:
    """A listing as of a past instant states the same after a later command (item
    ACCESS-LISTING-SECOND-LIFE-1; 04 T-PLT-07 rev 1.307; REQ-CTL-006). Marcus, Controller, is
    removed: the listing as of an instant inside his removal leaves him out and, with removed
    members, shows his Controller grant revoked at the removal. He is invited again as a Viewer
    — ``removed_at`` goes back to NULL on his row (04 T-PLT-07 "Invited again") — and the listing
    as of that same instant still reads the removal, from the invitation's audit event. Removed
    and invited a second time, both ended removals are read; an instant between them, when he
    was invited and held no role, lists him without one; and an instant of his first life lists
    his grant as before, because ``invited_at`` stays. The Membership cell is the status at the
    run's cutoff, as the listing says of that column, and each invitation is a change of the row
    (what REGISTER-CUTOFF-1 reads for an explicit historical run).

    Fail-first (the row alone, 317f62a9b): after the invitation the same instant listed Marcus
    as a member without a role — ``membership_count`` 8 where 7."""
    world = access.report
    app = world.app
    marcus = access.people["marcus"]
    email = access.email("marcus")
    prefix = f"access:{email}:"

    def listing(at: datetime, **more: Any) -> tuple[dict[str, int], dict[str, Mapping[str, Any]]]:
        """(the two control totals, Marcus's rows by role code) of the listing as of ``at``."""
        run, rows = report_run(world, "user_access_listing", {"as_of": utc(at), **more})
        assert run["status"] == "SUCCEEDED"
        totals = {
            name: int(run["control_totals"][name])
            for name in ("membership_count", "assignment_count")
        }
        mine = {
            row_key.removeprefix(prefix): row
            for row_key, row in keyed(rows).items()
            if row_key.startswith(prefix)
        }
        return totals, mine

    def row() -> dict[str, Any]:
        (found,) = stored(
            access.tenant_id,
            select(tenant_membership.c.invited_at, tenant_membership.c.updated_at).where(
                tenant_membership.c.id == marcus.membership_id
            ),
        )
        return found

    def removed() -> datetime:
        answer = post(
            app,
            f"{USERS}/{marcus.membership_id}/remove",
            access.fresh("tomas"),
            {"reason": "Left the company in September."},
        )
        assert answer.status_code == 200, answer.text
        return clock.now()

    def invited_again() -> None:
        before = row()
        answer = post(
            app,
            USERS,
            access.fresh("tomas"),
            {
                "email": email,
                "display_name": "Marcus Webb",
                "roles": [
                    {"role_id": access.roles["viewer"], "is_all_entities": True, "entity_codes": []}
                ],
            },
        )
        assert answer.status_code == 201, answer.text
        assert (answer.json()["id"], answer.json()["status"]) == (
            str(marcus.membership_id),
            "INVITED",
        )
        after = row()
        assert after["invited_at"] == before["invited_at"]
        assert after["updated_at"] > before["updated_at"]  # the database's stamp of the change

    out = {"membership_count": 7, "assignment_count": 9}
    everyone = {"membership_count": 8, "assignment_count": 10}
    without_a_role = {"membership_count": 8, "assignment_count": 9}

    clock.advance(MINUTE)
    first_life = clock.now()  # a member, Controller
    clock.advance(MINUTE)
    first_removal = removed()
    clock.advance(MINUTE)
    inside_first = clock.now()
    clock.advance(MINUTE)
    # While he is removed the row says it.
    assert listing(inside_first) == (out, {})
    totals, mine = listing(inside_first, include_removed=True)
    assert (totals, list(mine)) == (everyone, ["controller"])
    assert (mine["controller"]["membership_status"], mine["controller"]["revoked_at"]) == (
        "REMOVED",
        utc(first_removal),
    )
    # Removed: his MFA state and his last sign-in are not shown (04 T-PLT-02 rev 1.316) — null
    # in the data, where the row gave the factor he had enrolled and the instant he signed in.
    assert (mine["controller"]["mfa_enrolled"], mine["controller"]["last_login_at"]) == (None, None)
    totals, mine = listing(first_life)
    assert (totals, list(mine)) == (everyone, ["controller"])
    assert mine["controller"]["revoked_at"] == utc(first_removal)

    invited_again()
    clock.advance(MINUTE)
    # Invited again: the same instant, the same listing — read from the trail now.
    assert listing(inside_first) == (out, {})
    totals, mine = listing(inside_first, include_removed=True)
    assert (totals, list(mine)) == (everyone, ["controller"])
    assert (mine["controller"]["membership_status"], mine["controller"]["revoked_at"]) == (
        "INVITED",  # the status at the run's cutoff
        utc(first_removal),
    )
    # Invited again and not yet a member: still not shown.
    assert (mine["controller"]["mfa_enrolled"], mine["controller"]["last_login_at"]) == (None, None)
    between = clock.now()  # invited, and the Viewer role waits for its approver

    clock.advance(MINUTE)
    removed()
    clock.advance(MINUTE)
    inside_second = clock.now()
    clock.advance(MINUTE)
    invited_again()
    clock.advance(MINUTE)
    # Two removals ended by two invitations: each is read, and so is the time between them.
    assert listing(inside_first) == (out, {})
    assert listing(inside_second) == (out, {})
    totals, mine = listing(inside_second, include_removed=True)
    assert (totals, list(mine)) == (everyone, ["controller"])
    assert mine["controller"]["revoked_at"] == utc(first_removal)
    totals, mine = listing(between)
    assert (totals, list(mine)) == (without_a_role, [""])
    totals, mine = listing(clock.now())
    assert (totals, list(mine)) == (without_a_role, [""])
    assert mine[""]["membership_status"] == "INVITED"
    # The first life is read as it was: the membership existed (``invited_at``) and held the grant.
    totals, mine = listing(first_life)
    assert (totals, list(mine)) == (everyone, ["controller"])
    assert mine["controller"]["revoked_at"] == utc(first_removal)


# --- RPT-25 ---------------------------------------------------------------------------------------


def test_sod_conflict_report(access: AccessWorld, clock: FrozenClock) -> None:
    """PRD J-17.6, J-22.8: without exceptions the run has zero rows (the empty state names the
    ``as_of`` of the control totals); with the approved SoD-3 exception it lists Lena, SoD-3, the
    exception id, the compensating control and its validity."""
    world = access.report
    app = world.app
    clock.advance(MINUTE)
    empty, none = report_run(world, "sod_conflict_report", {})
    assert empty["status"] == "SUCCEEDED" and none == []
    assert empty["control_totals"] == {
        "conflict_count": 0,
        "uncovered_conflict_count": 0,
        "as_of": empty["parameters"]["known_at"],  # "No member holds conflicting permissions at …"
    }
    before = clock.now()

    exception = lena_exception(access)  # J-22.6, J-22.7
    clock.advance(MINUTE)
    run, rows = report_run(world, "sod_conflict_report", {})
    (row,) = rows
    (rule,) = stored(
        world.tenant_id,
        select(sod_rule).where(sod_rule.c.code == "SoD-3", sod_rule.c.status == "PUBLISHED"),
    )
    assert row["row_key"] == f"sod:{access.email('lena')}:SoD-3"
    assert (row["display_name"], row["rule_code"], row["rule_name"]) == (
        "Lena Fischer",
        "SoD-3",
        rule["name"],
    )
    # the permissions of each function Lena holds, through both roles
    assert row["function_a_permissions"] and row["function_b_permissions"]
    assert set(row["function_a_permissions"]) <= set(rule["function_a_permissions"])
    assert set(row["function_b_permissions"]) <= set(rule["function_b_permissions"])
    assert row["roles"] == "Revenue Accountant, Revenue Reviewer"
    assert row["delegations"] is None  # held through roles alone
    start: datetime = exception["valid_from_at"]
    assert (row["sod_exception_id"], row["compensating_control"]) == (exception["id"], CONTROL)
    assert (row["valid_from"], row["valid_to"], row["exception_status"]) == (
        start.date().isoformat(),
        (start + timedelta(days=90)).date().isoformat(),  # J-22.7: valid for 90 days
        "APPROVED",
    )
    assert run["control_totals"] == {
        "conflict_count": 1,
        "uncovered_conflict_count": 0,
        "as_of": run["parameters"]["known_at"],
    }
    # the grant carries the exception in the access listing (J-22.7 "with sod_exception_id")
    _, listing = report_run(world, "user_access_listing", {})
    granted = keyed(listing)[f"access:{access.email('lena')}:revenue_accountant"]
    assert (granted["sod_exception_id"], granted["granted_by"]) == (exception["id"], "Grace Okafor")
    # as of the instant of the empty run nothing conflicted (D-80 rule 2)
    _, earlier = report_run(world, "sod_conflict_report", {"as_of": utc(before)})
    assert earlier == []

    # a revoked exception stops covering: the conflict stays, without an exception; as of an
    # instant before the revocation the exception still covered it (status at as_of)
    clock.advance(MINUTE)
    revoked = post(
        app,
        f"{SOD_EXCEPTIONS}/{exception['id']}/revoke",
        access.fresh("tomas"),
        {"reason": "The second reviewer joined the team."},
    )
    assert revoked.status_code == 200, revoked.text
    revoked_at = clock.now()
    clock.advance(MINUTE)
    open_run, uncovered = report_run(world, "sod_conflict_report", {})
    (bare,) = uncovered
    assert bare["row_key"] == row["row_key"] and bare["roles"] == row["roles"]
    assert [
        bare[name]
        for name in (
            "sod_exception_id",
            "compensating_control",
            "valid_from",
            "valid_to",
            "exception_status",
        )
    ] == [None] * 5
    assert (
        open_run["control_totals"]["conflict_count"],
        open_run["control_totals"]["uncovered_conflict_count"],
    ) == (1, 1)
    _, covered = report_run(
        world, "sod_conflict_report", {"as_of": utc(revoked_at - timedelta(seconds=1))}
    )
    assert covered == rows

    with pytest.raises(Problem) as future:
        direct(world, "sod_conflict_report", {"as_of": utc(clock.now() + MINUTE)})
    assert future.value.errors[0].message == "Enter a time that is not in the future."


@pytest.mark.control("CTL-034")
def test_sod_conflict_report_names_the_delegations_a_conflict_is_held_through(
    access: AccessWorld, clock: FrozenClock
) -> None:
    """SCREENS_B RPT-25 rev 1.73 (04 T-PLT-21 rev 1.189; supervisor ruling R-111 (4)). A duty held
    through a delegation is held: Maya prepares contracts by her role (SoD-3 function A) and
    approves them by Priya's delegation (function B). As built the report read roles only and
    listed nobody. It lists Maya, names the delegation — delegator and end — beside her role and
    counts the conflict as uncovered; as of an instant before the delegation nothing conflicted;
    once Priya revokes it the row is gone, and it stays for an instant before the revocation.
    A delegation whose delegator holds the permission for another entity only counts for nothing
    in a run of this entity, and counts in a run of both."""
    world = access.report
    app, tenant_id = world.app, access.tenant_id
    maya, priya = access.people["maya"], access.people["priya"]
    clock.advance(MINUTE)
    before = clock.now()
    _, none = report_run(world, "sod_conflict_report", {})
    assert none == []

    # The rows of a state the command refuses without an exception (PRD BR-PLT-07): what stands.
    clock.advance(MINUTE)
    given = clock.now()
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    omar = colleague(tenant_id, "omar")  # prepares for every entity
    nora = colleague(tenant_id, "nora")  # reviews for the other entity only
    with tenant_session(context) as session:
        elsewhere = insert_contract_rows(session, tenant_id).entity_id
        held_by_maya = insert_approval_delegation(
            session,
            tenant_id=tenant_id,
            delegator_membership_id=priya.membership_id,
            delegate_membership_id=maya.membership_id,
            valid_from=given,
            valid_to=given + timedelta(days=30),
        )
        insert_approval_delegation(
            session,
            tenant_id=tenant_id,
            delegator_membership_id=nora.membership_id,
            delegate_membership_id=omar.membership_id,
            valid_from=given,
            valid_to=given + timedelta(days=10),
        )
    assign(omar, "revenue_accountant")
    assign(nora, "revenue_reviewer", entity_ids=(elsewhere,))

    clock.advance(MINUTE)
    run, rows = report_run(world, "sod_conflict_report", {"entity_codes": [AVM_US]})
    assert [item["display_name"] for item in rows] == ["Maya Chen"]
    (row,) = rows
    (rule,) = stored(
        tenant_id,
        select(sod_rule).where(sod_rule.c.code == "SoD-3", sod_rule.c.status == "PUBLISHED"),
    )
    function_a = set(rule["function_a_permissions"])
    both = function_a | set(rule["function_b_permissions"])
    own = ("revenue_accountant", "ssp_analyst")  # Maya's roles (PRD J-01.3)
    assert (row["row_key"], row["display_name"], row["rule_code"]) == (
        f"sod:{access.email('maya')}:SoD-3",
        "Maya Chen",
        "SoD-3",
    )
    assert set(row["function_a_permissions"]) == function_a & (
        DEFAULT_ROLES[own[0]] | DEFAULT_ROLES[own[1]]
    )
    assert row["function_b_permissions"] == ["contract.approve"]
    assert row["roles"] == ", ".join(
        sorted(DEFAULT_ROLE_NAMES[code] for code in own if DEFAULT_ROLES[code] & both)
    )
    assert row["delegations"] == f"Priya Raman until {given + timedelta(days=30):%d %b %Y}"
    assert [
        row[name]
        for name in (
            "sod_exception_id",
            "compensating_control",
            "valid_from",
            "valid_to",
            "exception_status",
        )
    ] == [None] * 5
    assert (
        run["control_totals"]["conflict_count"],
        run["control_totals"]["uncovered_conflict_count"],
    ) == (1, 1)
    # Nora holds contract.approve for the other entity: in a run of both, her delegation counts.
    _, everywhere = report_run(world, "sod_conflict_report", {})
    assert [(item["display_name"], item["delegations"]) for item in everywhere] == [
        ("Maya Chen", row["delegations"]),
        ("Omar", f"Nora until {given + timedelta(days=10):%d %b %Y}"),
    ]
    # As of an instant before the delegations nothing conflicted (D-80).
    _, earlier = report_run(
        world, "sod_conflict_report", {"as_of": utc(before), "entity_codes": [AVM_US]}
    )
    assert earlier == []

    # Priya ends her delegation: the conflict is gone, and stays for the instant before.
    clock.advance(MINUTE)
    revoked = post(
        app,
        f"{DELEGATIONS}/{held_by_maya}/revoke",
        access.fresh("priya"),
        {"reason": "Maya prepares these contracts."},
    )
    assert revoked.status_code == 200, revoked.text
    revoked_at = clock.now()
    clock.advance(MINUTE)
    _, after = report_run(world, "sod_conflict_report", {"entity_codes": [AVM_US]})
    assert after == []
    _, still = report_run(
        world,
        "sod_conflict_report",
        {"as_of": utc(revoked_at - timedelta(seconds=1)), "entity_codes": [AVM_US]},
    )
    assert still == rows

    # "Through delegations" names the person who GAVE the delegation, whatever the workspace is
    # shown of that membership now (04 T-PLT-02 rev 1.316; the supervisor's ruling on item
    # IDENTITY-WITHHELD-BY-STATUS-1). Nora's identity is not one an invitation of this workspace
    # created. Removed, she is shown to it by her address — and a run as of an instant when her
    # delegation stood names her as it did then.
    stood = clock.now()
    clock.advance(MINUTE)
    gone = post(
        app,
        f"{USERS}/{nora.membership_id}/remove",
        access.fresh("tomas"),
        {"reason": "Left the reviewing team in September."},
    )
    assert gone.status_code == 200, gone.text
    assert (gone.json()["status"], gone.json()["display_name"]) == ("REMOVED", nora.email)
    clock.advance(MINUTE)
    _, as_it_stood = report_run(world, "sod_conflict_report", {"as_of": utc(stood)})
    assert [(item["display_name"], item["delegations"]) for item in as_it_stood] == [
        ("Omar", f"Nora until {given + timedelta(days=10):%d %b %Y}")
    ]


# --- RPT-26 ---------------------------------------------------------------------------------------


def test_approvals_register(
    access: AccessWorld, publication: SspPublicationWorld, clock: FrozenClock
) -> None:
    """Rows carry subject type, subject reference, preparer, each decision with approver and UTC
    time, and ``subject_content_sha256``; a request without a decision has its own row."""
    world = access.report
    app = world.app
    exception = lena_exception(access)
    clock.advance(MINUTE)
    tomas = access.fresh("tomas")
    viewer = {"role_id": access.roles["viewer"]}
    pending = post(
        app,
        ROLE_ASSIGNMENTS,
        tomas,
        {**viewer, "membership_id": str(access.people["maya"].membership_id)},
    )
    assert pending.status_code == 201, pending.text
    unwanted = post(
        app,
        ROLE_ASSIGNMENTS,
        tomas,
        {**viewer, "membership_id": str(access.people["marcus"].membership_id)},
    )
    assert unwanted.status_code == 201, unwanted.text
    clock.advance(MINUTE)
    rejected = decide(
        app,
        access.fresh("grace"),
        str(unwanted.json()["approval_request_id"]),
        "The Controller role already reads every report.",
        verb="reject",
    )
    assert rejected["status"] == "REJECTED", rejected
    clock.advance(MINUTE)

    run, rows = report_run(world, "approvals_register", {})
    assert run["status"] == "SUCCEEDED"
    assert (run["parameters"]["currency_view"], run["control_totals"]["from_date"]) == (
        "functional",
        "2026-09-01",  # the first day of the context period
    )
    found = keyed(rows)
    requests = stored(
        world.tenant_id, select(approval_request).order_by(approval_request.c.request_no)
    )
    decisions = stored(world.tenant_id, select(approval_decision))
    assert {row["request_no"] for row in rows} == {item["request_no"] for item in requests}
    setup_grants = sum(len(codes) for _, _, codes in PEOPLE) + 1  # and Tomas's own
    assert run["control_totals"] == {
        "request_count": len(requests),
        "decision_count": len(decisions),
        "auto_approval_count": setup_grants,
        "from_date": "2026-09-01",
        "to_date": "2026-09-12",
    }
    assert (len(requests), len(decisions), setup_grants) == (14, 13, 9)
    assert len(rows) == len(decisions) + 1  # and the one request that still waits
    by_id = {item["id"]: item for item in requests}
    hashes = {
        (by_id[item["approval_request_id"]]["request_no"], item["decision"]): item[
            "subject_content_sha256"
        ]
        for item in decisions
    }
    for row in rows:
        request = next(item for item in requests if item["request_no"] == row["request_no"])
        # the subject reference: its type and id (the assignment or exception the request names)
        assert (row["subject_type"], row["subject_id"], row["summary"]) == (
            request["subject_type"],
            str(request["subject_id"]),
            request["summary"],
        )
        assert row["submitted_at"] == utc(request["submitted_at"])
        assert (row["entity_code"], row["amount_currency"], row["amount_functional"]) == (
            None,
            None,
            None,
        )
        assert SHA256.match(row["subject_content_sha256"])
        if row["decision"] is not None:
            assert row["subject_content_sha256"] == hashes[(row["request_no"], row["decision"])]
            assert INSTANT.match(row["decided_at"])  # UTC (API-C-07)

    # the setup grants: rule AUTO-BOOTSTRAP version 1 decides as the SYSTEM principal
    automatic = [row for row in rows if row["decision"] == "AUTO_APPROVE"]
    assert len(automatic) == setup_grants
    for row in automatic:
        assert (row["approver"], row["auto_rule_key"], row["auto_rule_version"]) == (
            "System",
            "AUTO-BOOTSTRAP",
            1,
        )
        assert (row["subject_type"], row["status"], row["on_behalf_of"]) == (
            "ROLE_ASSIGNMENT",
            "APPROVED",
            None,
        )
        assert row["row_key"] == f"decision:{row['request_no']}:{row['step_no']}:1"
    # Tomas prepared the grants of his invitations; provisioning prepared his own
    invited = [row for row in automatic if row["preparer"] == access.email("tomas")]
    assert len(invited) == setup_grants - 1
    (bootstrap,) = [row for row in automatic if row not in invited]
    (own,) = stored(
        world.tenant_id,
        select(role_assignment.c.id).where(
            role_assignment.c.membership_id == access.people["tomas"].membership_id
        ),
    )
    assert bootstrap["subject_id"] == str(own["id"])

    # J-22.2: Lena's grant, decided by Grace
    (lena_request,) = [item for item in requests if str(item["id"]) == access.lena_request_id]
    lena = found[f"decision:{lena_request['request_no']}:1:1"]
    assert (lena["preparer"], lena["approver"], lena["decision"], lena["status"]) == (
        access.email("tomas"),
        "Grace Okafor",
        "APPROVE",
        "APPROVED",
    )
    assert (lena["comment"], lena["decided_at"]) == (
        LENA_COMMENT,
        utc(lena_request["decided_at"]),
    )
    assert (lena["auto_rule_key"], lena["auto_rule_version"]) == (None, None)
    assert lena["step_name"] and lena["step_no"] == 1
    (assignment,) = stored(
        world.tenant_id,
        select(role_assignment.c.id).where(
            role_assignment.c.approval_request_id == lena_request["id"]
        ),
    )
    assert lena["subject_id"] == str(assignment["id"])
    # J-22.7: the exception request names the exception
    (sod,) = [row for row in rows if row["subject_type"] == "SOD_EXCEPTION"]
    assert (sod["subject_id"], sod["approver"], sod["comment"]) == (
        exception["id"],
        "Grace Okafor",
        EXCEPTION_COMMENT,
    )

    waiting_request = str(pending.json()["approval_request_id"])
    (waiting,) = [row for row in rows if row["status"] == "PENDING"]
    (waiting_stored,) = [item for item in requests if str(item["id"]) == waiting_request]
    assert waiting["row_key"] == f"decision:{waiting_stored['request_no']}:1:0"
    assert [
        waiting[name] for name in ("approver", "decision", "decided_at", "comment", "on_behalf_of")
    ] == [None] * 5
    assert waiting["step_name"] and waiting["step_no"] == 1
    assert waiting["subject_content_sha256"] == waiting_stored["subject_content_sha256"].strip()
    (refused,) = [row for row in rows if row["decision"] == "REJECT"]
    assert (refused["status"], refused["approver"], refused["comment"]) == (
        "REJECTED",
        "Grace Okafor",
        "The Controller role already reads every report.",
    )

    # the filters and the refused view
    _, open_only = report_run(world, "approvals_register", {"status": ["PENDING"]})
    assert [row["row_key"] for row in open_only] == [waiting["row_key"]]
    _, exceptions = report_run(world, "approvals_register", {"subject_types": ["SOD_EXCEPTION"]})
    assert exceptions == [sod]
    _, earlier = report_run(
        world, "approvals_register", {"from_date": "2026-09-01", "to_date": "2026-09-11"}
    )
    assert earlier == []
    with pytest.raises(Problem) as view:
        direct(world, "approvals_register", {"currency_view": "transaction"})
    (error,) = view.value.errors
    assert error.field == "parameters.currency_view" and "functional view only" in error.message

    # a request decided in two steps has one row per decision (PRD J-02-AC-3)
    _, steps = report_run(publication.report, "approvals_register", {})
    two = [row for row in steps if str(row["subject_id"]) == str(publication.h2["id"])]
    assert [(row["step_no"], row["approver"], row["decision"]) for row in two] == [
        (1, "Priya", "APPROVE"),
        (2, "Marcus", "APPROVE"),
    ]
    assert [row["row_key"].rsplit(":", 2)[1:] for row in two] == [["1", "1"], ["2", "1"]]
    assert two[0]["comment"] == H2_PRIYA_COMMENT and two[0]["status"] == "APPROVED"
    assert two[0]["step_name"] != two[1]["step_name"]
    assert "maya" in two[0]["preparer"].lower()


# --- RPT-44 ---------------------------------------------------------------------------------------


def _verified(world: ReportWorld, *, state: str = "SUCCEEDED") -> dict[str, Any]:
    """``POST /audit-events/verify`` run by the worker (``audit_jobs`` holds its handler); the
    stored T-PLT-23 row of that job."""
    requested = post(world.app, VERIFY, world.maya, {})
    assert requested.status_code == 202, requested.text
    finished = run_now(world, UUID(str(requested.json()["id"])))
    assert finished["state"] == state, finished.get("problem")
    assert finished["result"]["href"] == audit_jobs.VERIFICATIONS_HREF
    (row,) = stored(
        world.tenant_id,
        select(audit_chain_verification).where(
            audit_chain_verification.c.job_id == UUID(str(requested.json()["id"]))
        ),
    )
    return row


def test_chain_verification_report(
    publication: SspPublicationWorld, clock: FrozenClock, committed_db: TestDatabase
) -> None:
    """PRD J-17.5, DG-TST-22: a passing verification lists ``PASS``, the event count and the last
    chain value; a verification after owner tampering with a data-fix ticket lists ``FAIL`` at the
    tampered sequence."""
    world = publication.report
    clock.advance(MINUTE)
    passed = _verified(world)
    (head,) = stored(world.tenant_id, select(audit_chain_head))
    assert passed["result"] == "PASS" and passed["digest_last_hmac"] is not None
    clock.advance(MINUTE)
    run, rows = report_run(world, "chain_verification_report", {})
    assert run["status"] == "SUCCEEDED"
    (row,) = rows
    assert (
        row["row_key"] == f"verification:{passed['finished_at'].strftime('%Y-%m-%dT%H:%M:%S.%fZ')}"
    )
    assert (row["finished_at"], row["trigger"], row["result"]) == (
        utc(passed["finished_at"]),
        "ON_DEMAND",
        "PASS",
    )
    assert (row["from_chain_seq"], row["to_chain_seq"], row["events_checked"]) == (
        1,
        passed["to_chain_seq"],
        passed["to_chain_seq"],
    )
    assert row["events_checked"] > 0 and row["first_failure_seq"] is None
    assert row["digest_last_hmac"] == passed["digest_last_hmac"].strip()
    assert SHA256.match(row["digest_last_hmac"])
    assert row["digest_file_id"] == str(passed["digest_file_id"])
    # the last chain value is the hmac of the last event the verification checked
    (last,) = stored(
        world.tenant_id,
        select(audit_event.c.hmac).where(audit_event.c.chain_seq == passed["to_chain_seq"]),
    )
    assert row["digest_last_hmac"] == last["hmac"].strip()
    assert head["last_chain_seq"] >= passed["to_chain_seq"]
    assert run["control_totals"] == {
        "verification_count": 1,
        "failure_count": 0,
        "from": utc(datetime.fromisoformat(run["parameters"]["known_at"]) - timedelta(days=30)),
    }

    tampered = 3
    tamper_audit_event(committed_db.owner_engine, tenant_id=world.tenant_id, chain_seq=tampered)
    clock.advance(MINUTE)
    failed = _verified(world, state="SUCCEEDED_WITH_EXCEPTIONS")  # BS1-D-13
    assert (failed["result"], failed["first_failure_seq"]) == ("FAIL", tampered)
    clock.advance(MINUTE)
    again, both = report_run(world, "chain_verification_report", {})
    assert [item["result"] for item in both] == ["PASS", "FAIL"] and both[0] == row
    second = both[1]
    assert (second["first_failure_seq"], second["trigger"]) == (tampered, "ON_DEMAND")
    # a FAIL keeps the last chain value it confirmed (the event before the tampered one) and
    # stores no digest
    (confirmed,) = stored(
        world.tenant_id, select(audit_event.c.hmac).where(audit_event.c.chain_seq == tampered - 1)
    )
    assert (second["digest_last_hmac"], second["digest_file_id"]) == (
        confirmed["hmac"].strip(),
        None,
    )
    assert (second["from_chain_seq"], second["to_chain_seq"], second["events_checked"]) == (
        1,
        tampered,
        tampered,
    )
    assert second["finished_at"] == utc(failed["finished_at"])
    assert (
        again["control_totals"]["verification_count"],
        again["control_totals"]["failure_count"],
    ) == (2, 1)

    # "Finished to" is exclusive; a start after its end is refused at creation
    to = utc(failed["finished_at"])
    bounded, first_only = report_run(world, "chain_verification_report", {"to": to})
    assert first_only == [row] and bounded["control_totals"]["to"] == to
    refused = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {
            "report_code": "chain_verification_report",
            "parameters": {"from": to, "to": utc(passed["finished_at"])},
            "output_format": "JSON",
        },
    )
    assert refused.status_code == 422, refused.text
    assert [(item["field"], item["message"]) for item in refused.json()["errors"]] == [
        ("parameters.from", "Start must be on or before end.")
    ]


# --- RPT-43 ---------------------------------------------------------------------------------------


@pytest.fixture
def k03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K03World:
    return k03_castellan(app, keyring, clock, files)


def _events(world: ReportWorld, *where: Any) -> list[dict[str, Any]]:
    return stored(
        world.tenant_id, select(audit_event).where(*where).order_by(audit_event.c.chain_seq)
    )


@pytest.mark.slow
def test_audit_log_export_object_filter(k03: K03World, clock: FrozenClock) -> None:
    """PRD J-17.5: filtered to object ``PRJ-CB-2026-01`` the export returns the events of that
    contract with their field-level diffs; the estimate events carry theirs under their own
    object."""
    world = k03.report
    clock.advance(MINUTE)
    run, rows = report_run(
        world, "audit_log_export", {"object_type": "contract", "object_id": str(k03.contract_id)}
    )
    assert run["status"] == "SUCCEEDED"
    events = _events(world, audit_event.c.object_id == k03.contract_id)
    assert events and {event["object_type"] for event in events} == {"contract"}
    assert [row["row_key"] for row in rows] == [f"event:{event['chain_seq']}" for event in events]
    # every T-PLT-19 column; their table order is the CSV header's, asserted below
    assert set(rows[0]) == {"row_key", *audit_export.FIELDS}
    for row, event in zip(rows, events, strict=True):
        assert (row["chain_seq"], row["id"], row["action"]) == (
            event["chain_seq"],
            str(event["id"]),
            event["action"],
        )
        assert (row["object_type"], row["object_id"]) == ("contract", str(k03.contract_id))
        assert CANONICAL_INSTANT.match(row["occurred_at"])
        assert datetime.fromisoformat(row["occurred_at"]) == event["occurred_at"]
        assert (row["hmac"], row["prev_hmac"], row["hmac_key_id"]) == (
            event["hmac"].strip(),
            event["prev_hmac"].strip(),
            event["hmac_key_id"],
        )
        assert (row["actor_kind"], row["outcome"], row["request_id"]) == (
            event["actor_kind"],
            event["outcome"],
            event["request_id"],
        )
        # the JSON columns are canonical JSON strings of the stored values
        for name in ("before", "after", "diff", "detail"):
            value = event[name]
            assert row[name] == (
                None
                if value is None
                else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            )
    # the field-level diff of the activation: status DRAFT → ACTIVE
    activated = next(row for row in rows if row["action"] == "contract.active")
    assert {"path": "status", "before": "DRAFT", "after": "ACTIVE"} in json.loads(activated["diff"])
    assert run["control_totals"] == {
        "row_count": len(events),
        "first_chain_seq": events[0]["chain_seq"],
        "last_chain_seq": events[-1]["chain_seq"],
        "last_hmac": events[-1]["hmac"].strip(),
    }

    # the estimate versions of the contract carry their diffs under their own object
    _, estimate_rows = report_run(
        world,
        "audit_log_export",
        {"object_type": "estimate_version", "object_id": k03.eac_v1_id},
    )
    assert [row["action"] for row in estimate_rows] == [
        "estimate_version.create",
        "estimate_version.submitted",
        "estimate_version.approved",
    ]
    assert [row["row_key"] for row in estimate_rows] == [
        f"event:{event['chain_seq']}"
        for event in _events(world, audit_event.c.object_id == UUID(k03.eac_v1_id))
    ]
    approved = estimate_rows[-1]
    changed = {entry["path"]: entry for entry in json.loads(approved["diff"])}
    assert (changed["status"]["before"], changed["status"]["after"]) == ("SUBMITTED", "APPROVED")
    assert changed["approval_request_id"]["after"] is not None
    assert approved["actor_id"] == str(world.priya.member.user_id)  # Priya approves (PRD §2.5)

    # the other filters of the audit log, and the whole log in chain order
    _, by_action = report_run(world, "audit_log_export", {"action": "contract.active"})
    assert [row["row_key"] for row in by_action] == [activated["row_key"]]
    _, by_actor = report_run(
        world, "audit_log_export", {"actor_id": str(world.priya.member.user_id)}
    )
    assert by_actor and {row["actor_id"] for row in by_actor} == {str(world.priya.member.user_id)}
    whole, every = report_run(world, "audit_log_export", {})
    assert [row["chain_seq"] for row in every] == list(range(1, len(every) + 1))
    assert whole["control_totals"]["last_hmac"] == every[-1]["hmac"]
    _, none = report_run(
        world, "audit_log_export", {"object_type": "contract", "to": "2026-09-01T00:00:00Z"}
    )
    assert none == []

    # CSV with its manifest (SCREENS_B RPT-43 "CSV with manifest")
    exported, _ = report_run(
        world,
        "audit_log_export",
        {"object_type": "contract", "object_id": str(k03.contract_id)},
        output_format="CSV",
    )
    output = call(
        world.app,
        "GET",
        f"{REPORT_RUNS}/{exported['id']}/output",
        headers=cookie_headers(world.maya.token, key=False),
    )
    assert output.status_code == 200, output.text
    lines = output.text.split("\r\n")
    assert lines[0] == ",".join(audit_export.FIELDS)
    assert len([line for line in lines[1:] if line]) == len(events)
    manifest = call(
        world.app,
        "GET",
        f"{REPORT_RUNS}/{exported['id']}/output",
        params={"part": "manifest"},
        headers=cookie_headers(world.maya.token, key=False),
    )
    assert manifest.status_code == 200, manifest.text
    assert manifest.json()["row_count"] == len(events)
    assert manifest.json()["control_totals"] == run["control_totals"]
    assert K03_EXTERNAL_ID == "PRJ-CB-2026-01"


# --- REQ-RPT-001 ----------------------------------------------------------------------------------

AT_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026}
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
THIS_YEAR: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_date": "2026-01-01",
    "to_date": "2026-09-30",
}
AS_OF_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": "ASC606", "as_of": "2026-09-30"}
# 03 REQ-RPT-001: the requirements the standard catalogue covers at least, each with its reports
# (SCREENS_B §5.6 "REQ and evidence") and parameters that build in the K-01 world.
CATALOGUE: Final[Mapping[str, Mapping[str, Mapping[str, Any]]]] = MappingProxyType(
    {
        "REQ-RPT-004": {"revenue_waterfall": SEPTEMBER},
        "REQ-RPT-005": {"contract_balances": AT_SEPTEMBER},
        "REQ-RPT-006": {"contract_balance_rollforward": SEPTEMBER},
        "REQ-RPT-007": {"revenue_from_opening_liability": SEPTEMBER},
        "REQ-RPT-008": {"revenue_from_prior_period_obligations": SEPTEMBER},
        "REQ-RPT-009": {"rpo": AT_SEPTEMBER},
        "REQ-RPT-010": {"rpo_rollforward": SEPTEMBER},
        "REQ-RPT-011": {"disaggregation": SEPTEMBER},
        "REQ-RPT-012": {"contract_history": THIS_YEAR, "legacy_contract_history_export": THIS_YEAR},
        "REQ-RPT-013": {
            "latest_contract_status": AS_OF_SEPTEMBER,
            "legacy_latest_contract_export": AS_OF_SEPTEMBER,
        },
        "REQ-RPT-022": {
            "manual_adjustment_register": SEPTEMBER,
            "ssp_change_log": {},
            "config_change_register": {},
            "user_access_listing": {},
            "sod_conflict_report": {},
            "approvals_register": {},
        },
        "REQ-MOD-014": {"modification_register": THIS_YEAR},
        "REQ-JE-018": {"je_population": SEPTEMBER},
        "REQ-CLS-006": {"out_of_period_register": SEPTEMBER},
        "REQ-CLS-007": {
            "late_entry_report": {"entity_codes": [AVM_US], "period_key": SEPTEMBER_2026}
        },
    }
)


@pytest.mark.slow
def test_standard_catalogue_complete(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """03 REQ-RPT-001: a current definition exists and builds for REQ-RPT-004 to REQ-RPT-013,
    REQ-RPT-022, REQ-MOD-014, REQ-JE-018, REQ-CLS-006 and REQ-CLS-007; tenants cannot create or
    change a definition. Every report is attempted; the failures are collected by requirement and
    report, so one unbuilt report does not hide the state of the others."""
    world = k01_pellworth(app, keyring, clock, files)
    failures: dict[str, str] = {}
    built: list[str] = []
    for requirement, reports in CATALOGUE.items():
        for code, parameters in reports.items():
            name = f"{requirement} {code}"
            definition = get(world.app, f"{DEFINITIONS}/{code}", world.maya)
            if definition.status_code != 200:
                failures[name] = f"definition {definition.status_code}"
                continue
            assert (definition.json()["code"], definition.json()["version"]) == (code, 1)
            started = post(
                world.app,
                REPORT_RUNS,
                world.maya,
                {"report_code": code, "parameters": dict(parameters), "output_format": "JSON"},
            )
            if started.status_code != 202:
                failures[name] = f"{started.status_code} " + "; ".join(
                    f"{item['field']}: {item['message']}" for item in started.json()["errors"]
                )
                continue
            finished = run_now(world, UUID(str(started.json()["id"])))
            shown = get(
                world.app, f"{REPORT_RUNS}/{started.headers[REPORT_RUN_ID_HEADER]}", world.maya
            )
            if finished["state"] != "SUCCEEDED" or shown.json()["status"] != "SUCCEEDED":
                failures[name] = f"job {finished['state']}: {finished.get('problem')}"
                continue
            built.append(code)
    assert len(built) + len(failures) == sum(len(reports) for reports in CATALOGUE.values()) == 22

    # tenants cannot create or change a definition: the API serves reads only, and the tenant's
    # database role may not write the catalogue (04 T-RPT-01; §14.2)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for path in (DEFINITIONS, f"{DEFINITIONS}/revenue_waterfall"):
            refused = call(
                world.app,
                method,
                path,
                json={"name": "Tenant report"},
                headers=cookie_headers(world.maya.token, world.maya.csrf_token),
            )
            assert refused.status_code in (404, 405), (method, path, refused.status_code)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    waterfall = report_definition.c.code == "revenue_waterfall"
    for statement in (
        insert(report_definition).values(
            code="tenant_report",
            version=1,
            name="Tenant report",
            kind="STANDARD",
            description="A report the tenant defines.",
            parameters_schema={"type": "object", "additionalProperties": False},
            output_formats=["CSV"],
            ipe_logic={"version": 1},
            tie_outs=[],
        ),
        update(report_definition).where(waterfall).values(name="Tampered"),
        delete(report_definition).where(waterfall),
    ):
        with pytest.raises(exc.DBAPIError) as denied, tenant_session(context) as session:
            session.execute(statement)
        assert getattr(denied.value.orig, "sqlstate", None) == "42501"  # insufficient_privilege
    (kept,) = stored(world.tenant_id, select(report_definition.c.name).where(waterfall))
    assert kept["name"] == "Revenue waterfall"

    assert failures == {}, failures


# --- ruling R-13: the audit reports need audit.read -----------------------------------------------

AUDIT_READ: Final = "audit.read"
EXPLAIN_CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"


def _report_denials(world: ReportWorld) -> list[tuple[Any, ...]]:
    """(actor, action, run id, report code, permission) of every ``DENIED`` audit event on a
    report run, in chain order."""
    return [
        (
            row["actor_id"],
            row["action"],
            None if row["object_id"] is None else str(row["object_id"]),
            row["detail"].get("report_code"),
            row["detail"].get("permission"),
        )
        for row in stored(
            world.tenant_id,
            select(
                audit_event.c.actor_id,
                audit_event.c.action,
                audit_event.c.object_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.outcome == "DENIED", audit_event.c.object_type == "report_run")
            .order_by(audit_event.c.chain_seq),
        )
    ]


def _refused(response: Any) -> None:
    """403 ``forbidden``: the catalogue problem of every permission refusal."""
    assert response.status_code == 403, response.text
    assert slug(response) == "forbidden"


@pytest.mark.slow
def test_audit_reports_need_audit_read(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-13 (04 API-R-41 rev 1.99): a report run must not reveal data whose own
    API route the caller's permissions refuse. A viewer holds ``report.run`` and ``report.export``
    without ``audit.read``: the audit log export and the chain verification report are refused on
    create, on the read of an auditor's run (detail, data, cell explanation), on export and on
    re-run — each 403 ``forbidden`` after one ``DENIED`` audit event — and no list names such a
    run. The auditor succeeds. Ruling R-28: an auditor of one entity does not reach the audit log
    export, whose rows carry no entity, and does reach the verification report."""
    world = k01_pellworth(app, keyring, clock, files)
    hannah = holding(app, colleague(world.tenant_id, "hannah"), "auditor")
    vera = holding(app, colleague(world.tenant_id, "vera"), "viewer")
    exported, events = report_run(world, "audit_log_export", {}, actor=hannah)
    as_file, _ = report_run(world, "audit_log_export", {}, output_format="CSV", actor=hannah)
    verified, _ = report_run(world, "chain_verification_report", {}, actor=hannah)
    assert exported["status"] == verified["status"] == "SUCCEEDED" and events
    audit_runs = {str(exported["id"]), str(as_file["id"]), str(verified["id"])}
    assert _report_denials(world) == []

    viewer = vera.member.user_id
    expected: list[tuple[Any, ...]] = []
    for code in ("audit_log_export", "chain_verification_report"):
        body = {"report_code": code, "parameters": {}, "output_format": "JSON"}
        _refused(post(app, REPORT_RUNS, vera, body))
        expected.append((viewer, AUDIT_READ, None, code, AUDIT_READ))
    headers = cookie_headers(vera.token, key=False)
    for run, code in ((exported, "audit_log_export"), (verified, "chain_verification_report")):
        run_id = str(run["id"])
        _refused(get(app, f"{REPORT_RUNS}/{run_id}", vera))
        _refused(get(app, f"{REPORT_RUNS}/{run_id}/data", vera, {"limit": "200"}))
        _refused(
            get(
                app,
                EXPLAIN_CELL.format(run_id=run_id),
                vera,
                {"row_key": "event:1", "column_key": "action"},
            )
        )
        _refused(post(app, f"{REPORT_RUNS}/{run_id}/rerun", vera, {}))
        expected += [(viewer, AUDIT_READ, run_id, code, AUDIT_READ)] * 4
    for part in ("output", "manifest"):
        _refused(
            call(
                app,
                "GET",
                f"{REPORT_RUNS}/{as_file['id']}/output",
                params={"part": part},
                headers=headers,
            )
        )
        expected.append((viewer, AUDIT_READ, str(as_file["id"]), "audit_log_export", AUDIT_READ))
    assert _report_denials(world) == expected  # one DENIED event per refusal, none besides

    # no list names an audit run to the viewer; her own report runs and is listed
    own, _ = report_run(
        world,
        "contract_balances",
        {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026},
        actor=vera,
    )
    listed = get(app, REPORT_RUNS, vera, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    seen = {str(item["id"]) for item in listed.json()["items"]}
    assert str(own["id"]) in seen and not seen & audit_runs
    for code in ("audit_log_export", "chain_verification_report"):
        only = get(app, REPORT_RUNS, vera, {"report_code": code, "count": "true"})
        assert only.status_code == 200 and only.json()["items"] == [], only.text
        assert only.headers["X-Erev-Total-Count"] == "0"
    # the definitions are catalogue text: they stay listed
    codes = {item["code"] for item in get(app, DEFINITIONS, vera).json()["items"]}
    assert {"audit_log_export", "chain_verification_report"} <= codes

    # the auditor, and Maya (Revenue Accountant: audit.read), read, export and re-run
    for reader in (hannah, world.maya):
        shown = get(app, f"{REPORT_RUNS}/{exported['id']}", reader)
        assert shown.status_code == 200, shown.text
        data = get(app, f"{REPORT_RUNS}/{exported['id']}/data", reader, {"limit": "200"})
        assert data.status_code == 200 and data.json()["items"], data.text
        visible = {
            str(item["id"])
            for item in get(app, REPORT_RUNS, reader, {"limit": "200"}).json()["items"]
        }
        assert audit_runs <= visible
    output = call(
        app,
        "GET",
        f"{REPORT_RUNS}/{as_file['id']}/output",
        headers=cookie_headers(hannah.token, key=False),
    )
    assert output.status_code == 200 and output.text.startswith("chain_seq,"), output.text[:80]
    again = post(app, f"{REPORT_RUNS}/{verified['id']}/rerun", hannah, {})
    assert again.status_code == 202, again.text
    assert _report_denials(world) == expected  # no denial for a holder

    # R-28: audit.read for one entity does not open the audit log export (an audit event names no
    # entity and may hold entity financial data); the verification report holds none and opens
    nora = holding(app, colleague(world.tenant_id, "nora"), "auditor", entity_ids=[world.entity_id])
    _refused(
        post(
            app,
            REPORT_RUNS,
            nora,
            {"report_code": "audit_log_export", "parameters": {}, "output_format": "JSON"},
        )
    )
    _refused(get(app, f"{REPORT_RUNS}/{exported['id']}", nora))
    scoped = nora.member.user_id
    assert _report_denials(world)[len(expected) :] == [
        (scoped, AUDIT_READ, None, "audit_log_export", AUDIT_READ),
        (scoped, AUDIT_READ, str(exported["id"]), "audit_log_export", AUDIT_READ),
    ]
    allowed, _ = report_run(world, "chain_verification_report", {}, actor=nora)
    assert allowed["status"] == "SUCCEEDED"


# --- ruling R-63 (a): the access registers answer to audit.read, not report.run -------------------

THREE_REGISTERS: Final = ("user_access_listing", "sod_conflict_report", "api_client_inventory")
TWO_REGISTERS: Final = ("config_change_register", "approvals_register")
RUN: Final = "report.run"
EXPORT: Final = "report.export"
CELL: Final = {"row_key": "row", "column_key": "column"}


def _route_denials(world: ReportWorld, actor_id: UUID) -> list[tuple[Any, ...]]:
    """(action, method, path, permission) of the ``DENIED`` events of ``actor_id`` whose object
    is a route — what a guard writes (DG-KRN-AUTH-05) — in chain order."""
    return [
        (
            row["action"],
            row["detail"].get("method"),
            row["detail"].get("path"),
            row["detail"].get("permission"),
        )
        for row in stored(
            world.tenant_id,
            select(audit_event.c.action, audit_event.c.detail)
            .where(
                audit_event.c.outcome == "DENIED",
                audit_event.c.object_type == "route",
                audit_event.c.actor_id == actor_id,
            )
            .order_by(audit_event.c.chain_seq),
        )
    ]


def _json_run(code: str, **parameters: Any) -> dict[str, Any]:
    return {"report_code": code, "parameters": parameters, "output_format": "JSON"}


@pytest.mark.slow
def test_access_registers_need_audit_read_not_report_run(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-63 (a) (PRD J-17.6, J-22.8; 04 API-R-41): the user access listing, the
    SoD conflict report and the API client inventory need ``audit.read`` and not ``report.run``;
    the configuration change register and the approvals register need both. Every path a run is
    reached by is played for a Tenant Admin (``audit.read`` without ``report.run``): he creates,
    reads, re-runs and lists the three, reads their definitions, and reaches nothing else; a file
    still needs ``report.export``. A viewer and the two SSP roles lose the five. An Auditor runs
    and exports them. A principal that may run no report is refused by the routes as before. The
    run's entities lie in the caller's ``audit.read`` scope."""
    world = k01_pellworth(app, keyring, clock, files)
    # a second entity, so that an audit.read scope of one entity is narrower than the workspace
    other = entity(
        app, world.maya, code="AVM-UK", calendar_id=calendar(app, world.maya, code="UK-CAL")
    )
    tomas = holding(app, colleague(world.tenant_id, "tomas"), "tenant_admin")
    hannah = holding(app, colleague(world.tenant_id, "hannah"), "auditor")
    vera = holding(app, colleague(world.tenant_id, "vera"), "viewer")
    admin, viewer = tomas.member.user_id, vera.member.user_id
    expected: list[tuple[Any, ...]] = []

    # --- a Tenant Admin: the three registers on every path ---------------------------------------
    own: dict[str, dict[str, Any]] = {}
    for code in THREE_REGISTERS:
        run, _ = report_run(world, code, {}, actor=tomas)  # create, the job, detail and data
        assert run["status"] == "SUCCEEDED", run
        # tenant-wide by default: every entity of his audit.read scope
        assert run["parameters"]["entity_codes"] == ["AVM-UK", AVM_US]
        own[code] = run
        again = post(app, f"{REPORT_RUNS}/{run['id']}/rerun", tomas, {})
        assert again.status_code == 202, again.text
        # the cell route reaches the run and answers by name: these reports name no contributors
        cell = get(app, EXPLAIN_CELL.format(run_id=run["id"]), tomas, CELL)
        assert cell.status_code == 404, cell.text
        assert cell.json()["detail"] == framework.NO_CELL_EXPLAINER
    listed = get(app, REPORT_RUNS, tomas, {"limit": "200", "count": "true"})
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Erev-Total-Count"] == "6"  # three runs and their re-runs
    assert {item["report"]["code"] for item in listed.json()["items"]} == set(THREE_REGISTERS)
    # his catalogue: the definitions of the reports he may run
    catalogue = get(app, DEFINITIONS, tomas)
    assert catalogue.status_code == 200, catalogue.text
    assert sorted(item["code"] for item in catalogue.json()["items"]) == sorted(THREE_REGISTERS)
    for code in THREE_REGISTERS:
        assert get(app, f"{DEFINITIONS}/{code}", tomas).status_code == 200
    for code in (*TWO_REGISTERS, "contract_balances"):
        assert get(app, f"{DEFINITIONS}/{code}", tomas).status_code == 404
    assert _report_denials(world) == []

    # --- a Tenant Admin: nothing else ------------------------------------------------------------
    for code in (*TWO_REGISTERS, "contract_balances", "audit_log_export"):
        _refused(post(app, REPORT_RUNS, tomas, _json_run(code)))
        expected.append((admin, RUN, None, code, RUN))
    # a file needs report.export, which the role does not hold (RV-06)
    as_file = {**_json_run("user_access_listing"), "output_format": "CSV"}
    _refused(post(app, REPORT_RUNS, tomas, as_file))
    expected.append((admin, EXPORT, None, None, EXPORT))
    # Maya's run of an accounting report is not his to see: 404 on every addressed path
    balances, _ = report_run(world, "contract_balances", AT_SEPTEMBER)
    changes, _ = report_run(world, "config_change_register", {})
    # — and answers as an id no run has
    unknown = str(uuid4())
    for run_id in (str(balances["id"]), str(changes["id"]), unknown):
        assert get(app, f"{REPORT_RUNS}/{run_id}", tomas).status_code == 404
        assert get(app, f"{REPORT_RUNS}/{run_id}/data", tomas).status_code == 404
        assert get(app, EXPLAIN_CELL.format(run_id=run_id), tomas, CELL).status_code == 404
        assert post(app, f"{REPORT_RUNS}/{run_id}/rerun", tomas, {}).status_code == 404
    assert _report_denials(world) == expected

    # --- a viewer and the two SSP roles lose the five --------------------------------------------
    for code in (*THREE_REGISTERS, *TWO_REGISTERS):
        _refused(post(app, REPORT_RUNS, vera, _json_run(code)))
        expected.append((viewer, AUDIT_READ, None, code, AUDIT_READ))
    for role in ("ssp_analyst", "ssp_approver"):
        someone = holding(app, colleague(world.tenant_id, role), role)
        for code in (*THREE_REGISTERS, *TWO_REGISTERS):
            _refused(post(app, REPORT_RUNS, someone, _json_run(code)))
            expected.append((someone.member.user_id, AUDIT_READ, None, code, AUDIT_READ))
    # a run of the three is not visible to the viewer at all; no list names one of the five
    for run_id in (*(str(run["id"]) for run in own.values()), unknown):
        assert get(app, f"{REPORT_RUNS}/{run_id}", vera).status_code == 404
        assert get(app, f"{REPORT_RUNS}/{run_id}/data", vera).status_code == 404
        assert post(app, f"{REPORT_RUNS}/{run_id}/rerun", vera, {}).status_code == 404
    # a run of the two lies in her report.run scope and is refused by name, as R-13 refuses
    _refused(get(app, f"{REPORT_RUNS}/{changes['id']}", vera))
    expected.append((viewer, AUDIT_READ, str(changes["id"]), "config_change_register", AUDIT_READ))
    seen = get(app, REPORT_RUNS, vera, {"limit": "200"}).json()["items"]
    assert {item["report"]["code"] for item in seen} == {"contract_balances"}
    # her catalogue is unchanged: definitions are catalogue text (04 rev 1.99)
    codes = {item["code"] for item in get(app, DEFINITIONS, vera).json()["items"]}
    assert len(codes) == 56 and {*THREE_REGISTERS, *TWO_REGISTERS} <= codes
    assert _report_denials(world) == expected

    # --- an Auditor runs the five and exports (PRD J-17.6, J-17.8) --------------------------------
    for code in (*THREE_REGISTERS, *TWO_REGISTERS):
        run, _ = report_run(world, code, {}, actor=hannah)
        assert run["status"] == "SUCCEEDED", run
    exported, _ = report_run(world, "user_access_listing", {}, output_format="CSV", actor=hannah)
    output = call(
        app,
        "GET",
        f"{REPORT_RUNS}/{exported['id']}/output",
        headers=cookie_headers(hannah.token, key=False),
    )
    assert output.status_code == 200 and output.text.startswith("User,Email,"), output.text[:80]
    # the Tenant Admin reads that run (JSON or not, it is a run of his register) and cannot
    # download it: the output route is guarded by report.export
    assert get(app, f"{REPORT_RUNS}/{exported['id']}", tomas).status_code == 200
    refused = call(
        app,
        "GET",
        f"{REPORT_RUNS}/{exported['id']}/output",
        headers=cookie_headers(tomas.token, key=False),
    )
    _refused(refused)
    assert _route_denials(world, admin) == [
        (EXPORT, "GET", "/api/v1/report-runs/{run_id}/output", EXPORT)
    ]
    assert _report_denials(world) == expected  # no denial for the holders

    # --- the run's entities lie in the caller's audit.read scope ----------------------------------
    nora = holding(app, colleague(world.tenant_id, "nora"), "auditor", entity_ids=[world.entity_id])
    scoped, _ = report_run(world, "user_access_listing", {}, actor=nora)
    assert scoped["parameters"]["entity_codes"] == [AVM_US]
    beyond = post(app, REPORT_RUNS, nora, _json_run("user_access_listing", entity_codes=["AVM-UK"]))
    assert beyond.status_code == 422, beyond.text
    assert [error["field"] for error in beyond.json()["errors"]] == ["parameters.entity_codes"]
    # a run that names an entity outside her scope is not hers to read
    wide = own["user_access_listing"]
    assert str(other["id"]) and get(app, f"{REPORT_RUNS}/{wide['id']}", nora).status_code == 404
    assert get(app, f"{REPORT_RUNS}/{scoped['id']}", tomas).status_code == 200  # within his

    # --- a principal that may run no report: the routes refuse, as require("report.run") did -----
    service = holding(app, colleague(world.tenant_id, "svc"), "service_account")
    _refused(get(app, REPORT_RUNS, service))
    _refused(get(app, DEFINITIONS, service))
    _refused(post(app, REPORT_RUNS, service, _json_run("user_access_listing")))
    # a register's run and an id no run has are refused alike, event for event: the denial names
    # the route, never the run, so the caller cannot tell one from the other
    for run_id in (str(wide["id"]), unknown):
        _refused(get(app, f"{REPORT_RUNS}/{run_id}", service))
        _refused(get(app, f"{REPORT_RUNS}/{run_id}/data", service))
        _refused(get(app, EXPLAIN_CELL.format(run_id=run_id), service, CELL))
        _refused(post(app, f"{REPORT_RUNS}/{run_id}/rerun", service, {}))
    addressed = [
        (RUN, "GET", "/api/v1/report-runs/{run_id}", RUN),
        (RUN, "GET", "/api/v1/report-runs/{run_id}/data", RUN),
        (RUN, "GET", "/api/v1/explain/report-runs/{run_id}/cell", RUN),
        (RUN, "POST", "/api/v1/report-runs/{run_id}/rerun", RUN),
    ]
    assert _route_denials(world, service.member.user_id) == [
        (RUN, "GET", "/api/v1/report-runs", RUN),
        (RUN, "GET", "/api/v1/report-definitions", RUN),
        (RUN, "POST", "/api/v1/report-runs", RUN),
        *addressed,  # the register's run
        *addressed,  # the unknown id
    ]
    assert _report_denials(world) == expected


# --- item RPT-43-PARAMS-1: the export states the rows of the list ---------------------------------

AUDIT_EVENTS: Final = "/api/v1/audit-events"


def _paged(
    world: ReportWorld, path: str, params: Sequence[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Every item of a list read as Maya, page after page (API-C-09 ``next_cursor``)."""
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = call(
            world.app,
            "GET",
            path,
            params=[*params, *([] if cursor is None else [("cursor", cursor)])],
            headers=cookie_headers(world.maya.token, key=False),
        )
        assert page.status_code == 200, page.text
        items += page.json()["items"]
        cursor = page.json()["next_cursor"]
        if cursor is None:
            return items


def _listed(world: ReportWorld, **filters: Any) -> list[str]:
    """``GET /audit-events`` under ``filters`` in chain order (a repeatable filter as a list):
    the row key the export gives each event listed."""
    params: list[tuple[str, str]] = [("limit", "25"), ("sort", "chain_seq")]
    for name, value in filters.items():
        params += [(name, str(item)) for item in (value if isinstance(value, list) else [value])]
    return [
        f"{audit_export.ROW_KEY_PREFIX}{item['chain_seq']}"
        for item in _paged(world, AUDIT_EVENTS, params)
    ]


def _exported(
    world: ReportWorld, parameters: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A run of ``audit_log_export`` under ``parameters`` and EVERY row of its data — the rows
    of an export are compared whole, not by its first page."""
    run, first = report_run(world, "audit_log_export", parameters)
    rows = _paged(world, f"{REPORT_RUNS}/{run['id']}/data", [("limit", "200")])
    assert rows[: len(first)] == first and run["control_totals"]["row_count"] == len(rows)
    return run, rows


def _keys(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(row["row_key"]) for row in rows]


@pytest.mark.slow
def test_audit_log_export_states_the_rows_of_the_list(k03: K03World, clock: FrozenClock) -> None:
    """Item RPT-43-PARAMS-1 (SCREENS_B RPT-43; 04 §16.14; PRD J-17.5). The audit log lists the
    trail of a contract — ``contract_id``: every event that names it, whatever its object type —
    and filters by outcome; the export takes both, so that "Export" under those filters states
    the rows on the screen. For ``PRJ-CB-2026-01`` with its change order (J-06) the export holds
    the field-level diffs of the modification and of the estimate versions beside the contract's
    own events. Before, the report took neither parameter (422 for the key): under
    ``object_type`` and ``object_id`` it stated the events recorded on the contract itself, and
    the screen refused the export under an Object or an Outcome filter."""
    world = k03.report
    change = k03_change_order(k03, clock)
    contract_id = str(k03.contract_id)
    # one refusal for the outcome filter: Maya holds no user.manage (the guard's DENIED event)
    refused = call(world.app, "GET", USERS, headers=cookie_headers(world.maya.token, key=False))
    assert refused.status_code == 403, refused.text
    clock.advance(MINUTE)
    exports_from = clock.now()  # every event so far occurred before this instant

    # the trail: the list's rows, page after page, and more than the contract's own events
    _, trail = _exported(world, {"contract_id": contract_id})
    listed = _listed(world, contract_id=contract_id)
    assert _keys(trail) == listed and len(listed) > 25  # more than one page of the list
    _, own = _exported(world, {"object_type": "contract", "object_id": contract_id})
    assert own and set(_keys(own)) < set(listed)
    assert {"contract", "estimate_version", "modification"} <= {row["object_type"] for row in trail}

    # J-17.5: the modification and the estimate versions with their field-level diffs
    modified = [row for row in trail if row["object_id"] == change.modification_id]
    assert [row["action"] for row in modified] == [
        "modification.create",
        "modification.classify",  # initial treatment proposal
        "modification.classify",  # confirm_answers reads the proposed questionnaire
        "modification.update",  # preparer explicitly saves the answers
        "modification.classify",  # classify those saved answers
        "modification.preview_stored",
        "modification.submit",
        "modification.applied",
    ]
    applied = {entry["path"]: entry for entry in json.loads(modified[-1]["diff"])}
    assert applied["status"]["after"] == "APPLIED"
    approvals = [row for row in trail if row["action"] == "estimate_version.approved"]
    assert {row["object_id"] for row in approvals} >= {
        k03.eac_v1_id,
        change.eac_v2_id,
        change.bonus_v2_id,
    }
    for row in approvals:
        changed = {entry["path"]: entry for entry in json.loads(row["diff"])}
        assert (changed["status"]["before"], changed["status"]["after"]) == (
            "SUBMITTED",
            "APPROVED",
        )

    # the other filters narrow the trail as they narrow the list
    _, estimates = _exported(world, {"contract_id": contract_id, "object_type": "estimate_version"})
    assert _keys(estimates) == _listed(
        world, contract_id=contract_id, object_type="estimate_version"
    )
    assert estimates and {row["object_type"] for row in estimates} == {"estimate_version"}

    # the outcome, one literal or several, over a range with both ends, as the list sends one for
    # the log as a whole (SCREENS_B §6.3 "Range"). It ends before the first export started: a
    # run writes events of its own while and after it reads, and the list is read later.
    whole = {"from": "2026-09-01T00:00:00Z", "to": utc(exports_from)}
    for outcomes in (["DENIED"], ["DENIED", "FAILED"], ["SUCCESS", "DENIED"]):
        _, rows = _exported(world, {"outcome": outcomes, **whole})
        assert _keys(rows) == _listed(world, outcome=outcomes, **whole), outcomes
        assert rows and {row["outcome"] for row in rows} <= set(outcomes)
    assert len(rows) > 200  # more than one page of a run's data
    _, denied = _exported(world, {"outcome": ["DENIED"], **whole})
    assert [(row["action"], row["outcome"]) for row in denied] == [("user.manage", "DENIED")]
    # the trail holds no refusal: the two filters together, as the list answers them
    _, none = _exported(world, {"contract_id": contract_id, "outcome": ["DENIED"]})
    assert none == [] and _listed(world, contract_id=contract_id, outcome="DENIED") == []
    _, succeeded = _exported(world, {"contract_id": contract_id, "outcome": ["SUCCESS"]})
    assert _keys(succeeded) == listed

    # a contract no event names lists nothing; a literal outside E-81 and a value that is no id
    # are refused at creation, by the parameter
    _, unknown = _exported(world, {"contract_id": str(uuid4())})
    assert unknown == []
    for parameters, field_name in (
        ({"outcome": ["MAYBE"]}, "parameters.outcome"),
        ({"contract_id": "PRJ-CB-2026-01"}, "parameters.contract_id"),
    ):
        answered = post(
            world.app,
            REPORT_RUNS,
            world.maya,
            {"report_code": "audit_log_export", "parameters": parameters, "output_format": "JSON"},
        )
        assert answered.status_code == 422, answered.text
        assert [item["field"] for item in answered.json()["errors"]] == [field_name]
