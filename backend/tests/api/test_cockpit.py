"""CLO-4 cockpit reads, close tasks and checklist commands (04 §15.3 API-R-18, §16.8
API-S-PeriodCockpit, "Period commands"; T-CLS-02, T-CLS-03, T-CLS-08; PRD §2.5 routing row
``EXCEPTION_WAIVER``; SCREENS_B §1.1 BLK-16, "Sign task", "Request waiver"; 03 REQ-CLS-008,
REQ-CLS-021; BUILD_SPEC CLO-4, BS4-D-06, BS4-D-07).

World: Maya (Revenue Accountant, ``period.close``) keeps AVM-US on a January calendar with
FY2026-P01 to P09 open (``support.factories.world_calendar``). Marcus (Controller and Tenant Admin:
``period.close``, ``exception.waive``, ``settings.manage``) and Priya (Revenue Reviewer:
``exception.waive``) are enrolled in MFA. The journal preview uses ``support.worlds.journal_world``
with the CHK-022 intents posted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    close_checklist_item,
    exception_item,
    legal_entity,
    notification,
    signoff,
)
from erev_api.enums import NotificationKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.close_world import (
    CloseWorld,
    close_world,
    contract_of,
    earlier_periods_closed,
    identity_duplicates,
    other_entity,
    system_session,
    wld_b,
)
from support.db import TestDatabase
from support.factories import world_calendar
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, fields, get, holding, patch, periods, post, slug
from support.rows import approval_request_values
from support.worlds import ENTITY_1, JANUARY, journal_world, post_chk_022

PERIODS = "/api/v1/periods"
APPROVALS = "/api/v1/approvals"
TOTAL_COUNT = "X-Erev-Total-Count"
TEMPLATES = "/api/v1/close-checklist-templates"
SALES_TAX: dict[str, Any] = {
    "code": "SALES-TAX-REVIEW",
    "name": "Sales tax review",
    "gate_kind": "MANUAL",
    "is_blocking": True,
    "due_offset_days": 3,
}
SYSTEM_GATES = (
    "INTERFACES_COMPLETE",
    "JE_BALANCED",
    "JE_COMPLETE",
    "APPROVALS_CLEARED",
    "EXCEPTIONS_CLEARED",
    "HOLDS_REVIEWED",
    "BATCHES_ACKNOWLEDGED",
    "RECONCILIATIONS_GENERATED",
    "JUDGEMENTS_REVIEWED",
    "DATA_QUALITY_CLEAR",
    "NO_DIRTY_GROUPS",
    "MANUAL_ADJUSTMENTS_CLEARED",
    "CLOSE_RUN_COMPLETED",  # 04 T-CLS-02 rev 1.172 (item CLO-GATE-RUN-1; ruling R-114 (b))
    "CONTROLLER_CERTIFIED",
)
STATEMENT = "I completed this close task for AVM-US Sep 2026."
WAIVER_REASON = "Accepted by the controller for this period."
CLEARED = frozenset({"PASSED", "WAIVED", "NOT_APPLICABLE"})


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@dataclass(frozen=True, slots=True)
class Team:
    maya: Actor
    marcus: Actor
    priya: Actor


@pytest.fixture
def team(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Team:
    someone = member(keyring, clock)
    maya = holding(app, someone, "revenue_accountant")
    world_calendar(app, maya)
    marcus_member = colleague(someone.tenant_id, "marcus")
    assign(marcus_member, "controller")
    assign(marcus_member, "tenant_admin")
    priya_member = colleague(someone.tenant_id, "priya")
    assign(priya_member, "revenue_reviewer")
    return Team(
        maya=maya,
        marcus=enrolled(app, clock, marcus_member),
        priya=enrolled(app, clock, priya_member),
    )


def _september(app: FastAPI, actor: Actor) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(app, actor, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    return found


def _cockpit(app: FastAPI, actor: Actor, state: dict[str, Any]) -> dict[str, Any]:
    shown = get(app, f"{PERIODS}/{state['id']}/cockpit", actor)
    assert shown.status_code == 200, shown.text
    body: dict[str, Any] = shown.json()
    return body


def _item(cockpit: dict[str, Any], code: str) -> dict[str, Any]:
    (found,) = [item for item in cockpit["checklist"] if item["code"] == code]
    return found


def _if_match(cockpit: dict[str, Any]) -> str:
    return f'"r{cockpit["period"]["row_version"]}"'


def _unsigned_tasks(cockpit: dict[str, Any]) -> int:
    """SCREENS_B §1.1 BLK-16: manual checklist items not PASSED, WAIVED or NOT_APPLICABLE."""
    return sum(
        1
        for item in cockpit["checklist"]
        if item["gate_kind"] == "MANUAL" and item["status"] not in CLEARED
    )


def _sign(app: FastAPI, actor: Actor, cockpit: dict[str, Any], item: dict[str, Any]) -> Any:
    return post(
        app,
        f"{PERIODS}/{cockpit['period']['id']}/checklist/{item['id']}/sign",
        actor,
        {"statement_accepted": True},
        if_match=_if_match(cockpit),
    )


def test_sign_manual_task_requires_mfa(app: FastAPI, clock: FrozenClock, team: Team) -> None:
    created = post(app, TEMPLATES, team.marcus, SALES_TAX)
    assert created.status_code == 201, created.text
    shown = _cockpit(app, team.maya, _september(app, team.maya))
    task = _item(shown, "SALES-TAX-REVIEW")

    refused = _sign(app, team.maya, shown, task)
    assert (refused.status_code, slug(refused)) == (403, "mfa-required"), refused.text
    assert _item(_cockpit(app, team.maya, shown["period"]), "SALES-TAX-REVIEW")["status"] == (
        "NOT_STARTED"
    )

    maya = enrolled(app, clock, team.maya.member)
    unconfirmed = post(
        app,
        f"{PERIODS}/{shown['period']['id']}/checklist/{task['id']}/sign",
        maya,
        {"statement_accepted": False},
        if_match=_if_match(shown),
    )
    assert (unconfirmed.status_code, fields(unconfirmed)) == (
        422,
        [("statement_accepted", "STATEMENT_NOT_ACCEPTED")],
    )
    signed = _sign(app, maya, shown, task)
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["status"] == "PASSED"
    assert body["signoff"]["signer"]["id"] == str(team.maya.member.user_id)

    context = DbContext(tenant_id=team.maya.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        rows = [
            dict(row)
            for row in session.execute(
                select(
                    signoff.c.subject_type,
                    signoff.c.role,
                    signoff.c.signer_id,
                    signoff.c.statement,
                    signoff.c.subject_content_sha256,
                    signoff.c.mfa_verified_at,
                ).where(signoff.c.subject_id == UUID(task["id"]))
            ).mappings()
        ]
    assert len(rows) == 1
    (row,) = rows
    assert (
        row["subject_type"],
        str(row["role"].value if hasattr(row["role"], "value") else row["role"]),
    ) == (
        "close_checklist_item",
        "PREPARER",
    )
    assert (row["signer_id"], row["statement"]) == (team.maya.member.user_id, STATEMENT)
    assert re.fullmatch(r"[0-9a-f]{64}", str(row["subject_content_sha256"]))
    assert row["mfa_verified_at"] is not None

    # An automatic gate is not signed, and a signed task is not signed again.
    gate = _item(shown, "CONTROLLER_CERTIFIED")
    automatic = _sign(app, maya, shown, gate)
    assert (automatic.status_code, slug(automatic)) == (409, "invalid-transition"), automatic.text
    again = _sign(app, maya, shown, task)
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text


def test_custom_close_task_blocks_until_signed(
    app: FastAPI, clock: FrozenClock, team: Team
) -> None:
    created = post(app, TEMPLATES, team.marcus, SALES_TAX)
    assert created.status_code == 201, created.text
    assert created.headers["ETag"] == '"r1"'
    template = created.json()
    # the first tenant task follows the fourteen system gates (04 T-CLS-02 rev 1.172)
    assert (template["gate_kind"], template["is_system"], template["sequence"]) == (
        "MANUAL",
        False,
        15,
    )
    listed = get(app, TEMPLATES, team.maya)
    assert listed.status_code == 200, listed.text
    assert [item["code"] for item in listed.json()["items"]] == [*SYSTEM_GATES, "SALES-TAX-REVIEW"]

    shown = _cockpit(app, team.maya, _september(app, team.maya))
    assert [item["code"] for item in shown["checklist"]] == [*SYSTEM_GATES, "SALES-TAX-REVIEW"]
    task = _item(shown, "SALES-TAX-REVIEW")
    assert (
        task["gate_kind"],
        task["status"],
        task["is_blocking"],
        task["due_date"],
        task["result"],
        task["signoff"],
    ) == ("MANUAL", "NOT_STARTED", True, "2026-10-05", None, None)
    assert _unsigned_tasks(shown) == 1

    maya = enrolled(app, clock, team.maya.member)
    signed = _sign(app, maya, shown, task)
    assert signed.status_code == 200, signed.text
    # Her earlier password-only session owes the challenge now that she has a factor
    # (REQ-PLT-005), so the verified session reads the cockpit.
    after = _cockpit(app, maya, shown["period"])
    assert _item(after, "SALES-TAX-REVIEW")["status"] == "PASSED"
    assert _unsigned_tasks(after) == 0

    # T-CLS-02: a system gate changes only in its owner role and due offset; codes are unique.
    (gate,) = [item for item in listed.json()["items"] if item["code"] == "CONTROLLER_CERTIFIED"]
    path = f"{TEMPLATES}/{gate['id']}"
    renamed = patch(app, path, team.marcus, {"name": "Certification"}, if_match='"r1"')
    assert (renamed.status_code, fields(renamed)) == (422, [("name", "T-CLS-02")]), renamed.text
    stale = patch(app, path, team.marcus, {"due_offset_days": 5}, if_match='"r9"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    offset = patch(app, path, team.marcus, {"due_offset_days": 5}, if_match='"r1"')
    assert offset.status_code == 200, offset.text
    assert (offset.json()["due_offset_days"], offset.headers["ETag"]) == (5, '"r2"')
    duplicate = post(app, TEMPLATES, team.marcus, SALES_TAX)
    assert (duplicate.status_code, fields(duplicate)) == (422, [("code", "T-CLS-02")])
    automatic = post(
        app, TEMPLATES, team.marcus, {**SALES_TAX, "code": "X", "gate_kind": "AUTOMATIC"}
    )
    assert (automatic.status_code, fields(automatic)) == (422, [("gate_kind", "T-CLS-02")])
    forbidden = post(app, TEMPLATES, maya, {**SALES_TAX, "code": "OTHER-TASK"})
    assert (forbidden.status_code, slug(forbidden)) == (403, "forbidden"), forbidden.text


def test_waiver_routes_exception_waiver(app: FastAPI, team: Team) -> None:
    shown = _cockpit(app, team.marcus, _september(app, team.marcus))
    gate = _item(shown, "RECONCILIATIONS_GENERATED")
    assert (gate["status"], gate["result"]["count"]) == ("FAILED", 2)
    waive_path = f"{PERIODS}/{shown['period']['id']}/checklist/{gate['id']}/waive"
    waived = post(
        app, waive_path, team.marcus, {"reason": WAIVER_REASON}, if_match=_if_match(shown)
    )
    assert waived.status_code == 200, waived.text
    request_id = waived.json()["approval_request_id"]
    assert waived.json()["request_no"]

    pending = _item(_cockpit(app, team.marcus, shown["period"]), "RECONCILIATIONS_GENERATED")
    assert (pending["status"], pending["waiver_approval_request_id"]) == ("FAILED", request_id)
    twice = post(app, waive_path, team.marcus, {"reason": WAIVER_REASON}, if_match=_if_match(shown))
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text

    own = approve(app, request_id, team.marcus)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    approved = approve(app, request_id, team.priya)
    assert approved.status_code == 200, approved.text

    after = _item(_cockpit(app, team.marcus, shown["period"]), "RECONCILIATIONS_GENERATED")
    assert (after["status"], after["waiver_approval_request_id"]) == ("WAIVED", request_id)

    # [J] D-88 L7-2-Q-7: the request and the requester's decision notification link to the SF-05
    # task drawer of the item, not to an SF-11 exception item.
    task_link = "/close/AVM-US/ASC606/FY2026-P09?drawer=task&task=RECONCILIATIONS_GENERATED"
    detail = get(app, f"{APPROVALS}/{request_id}", team.marcus)
    assert detail.status_code == 200, detail.text
    assert detail.json()["subject"]["href"] == task_link
    marcus = team.marcus.member
    context = DbContext(tenant_id=marcus.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        decided = (
            session.execute(
                select(notification.c.link_path, notification.c.subject_id).where(
                    notification.c.recipient_membership_id == marcus.membership_id,
                    notification.c.kind == NotificationKind.ITEM_APPROVED,
                )
            )
            .tuples()
            .all()
        )
    assert decided == [(task_link, UUID(gate["id"]))]
    # A waived gate is not evaluated again and not waived again.
    again = post(app, waive_path, team.marcus, {"reason": WAIVER_REASON}, if_match=_if_match(shown))
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text


@pytest.mark.slow
def test_never_waivable_gates_refuse_a_waiver(app: FastAPI, team: Team) -> None:
    """SC-N4 / supervisor ruling R-55 (c); 04 §16.8 rev 1.106: journal balancing, journal
    completeness and the controller certification are never waivable — the checklist rows say so
    (``is_waivable``) and the waive command refuses them by name, opening no request. Rev 1.172
    (supervisor ruling R-114 (b)): nor is the close run. Every other gate and every tenant task is
    waivable (``test_waiver_routes_exception_waiver``)."""
    created = post(app, TEMPLATES, team.marcus, SALES_TAX)
    assert created.status_code == 201, created.text
    shown = _cockpit(app, team.marcus, _september(app, team.marcus))
    never = {item["code"] for item in shown["checklist"] if not item["is_waivable"]}
    assert never == {"JE_BALANCED", "JE_COMPLETE", "CLOSE_RUN_COMPLETED", "CONTROLLER_CERTIFIED"}
    assert _item(shown, "SALES-TAX-REVIEW")["is_waivable"] is True
    for code, label in (
        ("JE_BALANCED", "Journals balance per currency"),
        ("JE_COMPLETE", "Journals complete"),
        ("CLOSE_RUN_COMPLETED", "Close run completed"),
        ("CONTROLLER_CERTIFIED", "Controller certification"),
    ):
        gate = _item(shown, code)
        assert gate["status"] == "FAILED", gate
        refused = post(
            app,
            f"{PERIODS}/{shown['period']['id']}/checklist/{gate['id']}/waive",
            team.marcus,
            {"reason": WAIVER_REASON},
            if_match=_if_match(shown),
        )
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
        assert refused.json()["detail"] == (
            f"{label} cannot be waived. The period locks only when this gate passes."
        )
    after = _cockpit(app, team.marcus, shown["period"])
    assert {item["waiver_approval_request_id"] for item in after["checklist"]} == {None}
    context = DbContext(tenant_id=team.marcus.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        waivers = session.execute(
            select(func.count())
            .select_from(approval_request)
            .where(approval_request.c.subject_type == "EXCEPTION_WAIVER")
        ).scalar_one()
    assert waivers == 0


def test_cockpit_journal_preview_balanced(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = journal_world(app, keyring, clock, files)
    post_chk_022(world)
    maya = world.legacy.maya
    (january,) = [
        item
        for item in periods(app, maya, entity=ENTITY_1)
        if item["period"]["period_key"] == JANUARY
    ]
    preview = _cockpit(app, maya, january)["journal_preview"]
    assert (
        preview["debit_functional"],
        preview["credit_functional"],
        preview["difference_functional"],
        preview["balanced"],
    ) == (
        {"amount": "295.69", "currency": "USD"},
        {"amount": "295.69", "currency": "USD"},
        {"amount": "0.00", "currency": "USD"},
        True,
    )
    assert {
        row["account_role"]: (row["debit"]["amount"], row["credit"]["amount"])
        for row in preview["by_account_role"]
    } == {"CONTRACT_LIABILITY": ("295.69", "0.00"), "REVENUE": ("0.00", "295.69")}


# --- [J] D-88 L7-2-Q-13: approval counts beside the cockpit ------------------------------------


@pytest.fixture
def close(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    """``support.close_world``: Maya and AVM-US; ``wld_b`` writes the WLD-B rows of
    ``test_cockpit_blocker_counts``."""
    return close_world(app, keyring, clock, files)


def _pending(close: CloseWorld, **params: Any) -> int:
    listed = get(
        close.app,
        APPROVALS,
        close.maya,
        {"status": "PENDING", "limit": 1, "count": "true", **params},
    )
    assert listed.status_code == 200, listed.text
    return int(listed.headers[TOTAL_COUNT])


def test_approvals_entity_counts_blockers(close: CloseWorld) -> None:
    """GET /approvals ``entity`` takes codes or ids and counts what BLK-01 counts; BLK-06 and BLK-15
    subtract API-S-PeriodCockpit ``pending_requests``, which counts the same requests of the entity
    (SCREENS_B §1.1 rev 1.3; D-90a QA-L9-7)."""
    wld_b(close)
    shown = get(close.app, f"{PERIODS}/{close.state_id}", close.maya)
    assert shown.status_code == 200, shown.text
    blockers = shown.json()["blockers"]
    assert _pending(close, entity="AVM-US") == blockers["approvals_pending"] == 3
    assert _pending(close, entity=str(close.entity_id)) == 3
    judgements = _pending(close, entity="AVM-US", subject_type="JUDGEMENT_RECORD")
    adjustments = _pending(close, entity="AVM-US", subject_type="MANUAL_ADJUSTMENT")
    assert (judgements, adjustments) == (1, 1)
    cockpit = get(close.app, f"{PERIODS}/{close.state_id}/cockpit", close.maya)
    assert cockpit.status_code == 200, cockpit.text
    pending = {item["subject_type"]: item["count"] for item in cockpit.json()["pending_requests"]}
    # Maya prepared every WLD-B request, so her list sees what the cockpit counts.
    assert pending == {"JUDGEMENT_RECORD": judgements, "MANUAL_ADJUSTMENT": adjustments}
    assert max(0, blockers["judgements_unreviewed"] - pending["JUDGEMENT_RECORD"]) == 0  # 1 - 1
    assert max(0, blockers["manual_adjustments_pending"] - pending["MANUAL_ADJUSTMENT"]) == 0

    # A request for another entity's contract answers 0 for AVM-US.
    with system_session(close) as session:
        uk = other_entity(session, close)
        uk_contract, _, _ = contract_of(session, close, uk)
        foreign = approval_request_values(
            close.tenant_id,
            subject_type="CONTRACT_ACTIVATION",
            subject_id=uk_contract,
            preparer_id=close.maya.member.user_id,
            summary="Activate BG-AVM-0031",
        )
        session.execute(insert(approval_request).values(**foreign))
        us_name = session.execute(
            select(legal_entity.c.name).where(legal_entity.c.id == close.entity_id)
        ).scalar_one()
    assert _pending(close, entity="AVM-US") == 3
    assert _pending(close, entity="AVM-UK") == 1
    assert _pending(close, entity=["AVM-US", str(uk)]) == 4
    listed = get(close.app, APPROVALS, close.maya, {"status": "PENDING", "entity": "AVM-US"})
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert str(foreign["id"]) not in {item["id"] for item in items}
    # API-S-Approval ``entity`` is API-S-Ref read from legal_entity.
    (adjustment,) = [item for item in items if item["subject"]["type"] == "MANUAL_ADJUSTMENT"]
    assert adjustment["entity"] == {"id": str(close.entity_id), "code": "AVM-US", "name": us_name}
    assert {item["entity"] is None for item in items if item["id"] != adjustment["id"]} == {True}

    # An unknown code answers 422 validation-failed with rule_id API-C-11.
    unknown = get(close.app, APPROVALS, close.maya, {"entity": ["AVM-US", "AVM-XX"]})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert fields(unknown) == [("entity", "API-C-11")]


def test_cockpit_request_counts_reader_independent(close: CloseWorld) -> None:
    """D-90a QA-L9-7 and L8-C-Q-2: API-S-PeriodCockpit ``pending_requests`` (04 rev 1.8) lists
    JUDGEMENT_RECORD then MANUAL_ADJUSTMENT, both always present, counting the PENDING requests of
    the entity without API-R-09 visibility, so an approver and a reader without approval permission
    read the same BLK-06 and BLK-15 inputs (SCREENS_B §1.1 rev 1.3). BLK-03 is out of scope: the
    cockpit still reads it from the permission-filtered GET /exceptions count."""
    cockpit = f"{PERIODS}/{close.state_id}/cockpit"
    none = get(close.app, cockpit, close.maya)
    assert none.status_code == 200, none.text
    assert none.json()["pending_requests"] == [
        {"subject_type": "JUDGEMENT_RECORD", "count": 0},
        {"subject_type": "MANUAL_ADJUSTMENT", "count": 0},
    ]

    wld_b(close)
    priya = holding(close.app, colleague(close.tenant_id, "priya"), "revenue_reviewer")
    robert = holding(close.app, colleague(close.tenant_id, "robert"), "viewer")
    # Maya prepared the requests; Priya holds the approval permission judgement.review; Robert
    # holds no approval permission.
    readers = {"maya": close.maya, "priya": priya, "robert": robert}
    bodies: dict[str, dict[str, Any]] = {}
    for name, actor in readers.items():
        shown = get(close.app, cockpit, actor)
        assert shown.status_code == 200, (name, shown.text)
        bodies[name] = shown.json()
    for name, body in bodies.items():
        # Exact member order: the fixed type order, and subject_type before count.
        assert [list(item) for item in body["pending_requests"]] == [["subject_type", "count"]] * 2
        assert body["pending_requests"] == [
            {"subject_type": "JUDGEMENT_RECORD", "count": 1},
            {"subject_type": "MANUAL_ADJUSTMENT", "count": 1},
        ], name
    # The BLK-06 and BLK-15 inputs: the two blocker counts and the request counts they subtract.
    inputs = {
        name: (
            body["period"]["blockers"]["judgements_unreviewed"],
            body["period"]["blockers"]["manual_adjustments_pending"],
            body["pending_requests"],
        )
        for name, body in bodies.items()
    }
    assert inputs["maya"] == inputs["priya"] == inputs["robert"]
    assert bodies["priya"]["period"]["blockers"] == bodies["robert"]["period"]["blockers"]
    blockers = bodies["robert"]["period"]["blockers"]
    assert (blockers["approvals_pending"], blockers["judgements_unreviewed"]) == (3, 1)
    assert max(0, blockers["judgements_unreviewed"] - 1) == 0  # BLK-06 hidden for every reader

    # API-R-09 list visibility is unchanged and differs between readers: Maya prepared the requests
    # and lists them, while Robert neither prepared nor may decide them and lists none.
    query = {
        "status": "PENDING",
        "entity": "AVM-US",
        "subject_type": "JUDGEMENT_RECORD",
        "limit": 1,
        "count": "true",
    }
    for actor, expected in ((close.maya, 1), (robert, 0)):
        listed = get(close.app, APPROVALS, actor, query)
        assert listed.status_code == 200, listed.text
        assert (int(listed.headers[TOTAL_COUNT]), len(listed.json()["items"])) == (expected,) * 2


# --- security finding SC-8: a read appends no audit event (supervisor ruling R-32) --------------

REQUEST_ID = "X-Request-Id"
RUN_MONITORS = "close.run_monitors"


def _audit_actions(close: CloseWorld) -> list[str]:
    with system_session(close) as session:
        return [
            str(action)
            for action in session.execute(
                select(audit_event.c.action).order_by(audit_event.c.chain_seq)
            ).scalars()
        ]


def _stored_items(close: CloseWorld) -> list[tuple[Any, ...]]:
    """The checklist rows of September as stored: a row a request wrote differs in ``row_version``
    and ``updated_at``."""
    with system_session(close) as session:
        rows = session.execute(
            select(
                close_checklist_item.c.id,
                close_checklist_item.c.status,
                close_checklist_item.c.result,
                close_checklist_item.c.row_version,
                close_checklist_item.c.updated_at,
                close_checklist_item.c.created_by_kind,
            )
            .where(
                close_checklist_item.c.entity_id == close.entity_id,
                close_checklist_item.c.period_id == close.period_id,
            )
            .order_by(close_checklist_item.c.id)
        ).all()
    return [(row[0], str(row[1]), row[2], row[3], row[4], str(row[5])) for row in rows]


def test_sc_8_cockpit_reads_write_no_audit_event_and_only_a_changed_checklist(
    close: CloseWorld,
) -> None:
    """Security finding SC-8 (supervisor ruling R-32; 04 T-CLS-03 rev 1.106). Every cockpit or
    checklist GET used to run ``refresh_checklist`` as SYSTEM and commit: a Viewer's reads appended
    ``close.run_monitors`` each time and ``close_checklist_item.create`` / ``.evaluate`` events
    whose actor was SYSTEM. A read now appends no audit event at all, and writes a row only when
    the stored checklist differs from what the reader must see. Positive control: the command
    that evaluates the gates next still audits the change it stores."""
    app = close.app
    vic = holding(app, colleague(close.tenant_id, "vic"), "viewer")
    cockpit = f"{PERIODS}/{close.state_id}/cockpit"
    checklist = f"{PERIODS}/{close.state_id}/checklist"
    assert _stored_items(close) == []
    audited = _audit_actions(close)

    # The first view materialises the fourteen gates as SYSTEM — and audits none of them.
    first = get(app, cockpit, vic)
    assert first.status_code == 200, first.text
    assert [item["code"] for item in first.json()["checklist"]] == list(SYSTEM_GATES)
    stored = _stored_items(close)
    assert len(stored) == len(SYSTEM_GATES)
    assert {row[5] for row in stored} == {"SYSTEM"}
    assert _audit_actions(close) == audited

    # Reads of an unchanged period write nothing: the same rows, versions and timestamps.
    for _ in range(3):
        assert get(app, cockpit, vic).status_code == 200
        listed = get(app, checklist, vic)
        assert listed.status_code == 200, listed.text
        assert [item["code"] for item in listed.json()["items"]] == list(SYSTEM_GATES)
    assert _stored_items(close) == stored
    assert _audit_actions(close) == audited

    # A gate state that changed is stored by the next read — still without an audit event.
    wld_b(close)
    audited = _audit_actions(close)
    changed = get(app, cockpit, vic)
    assert changed.status_code == 200, changed.text
    approvals = _item(changed.json(), "APPROVALS_CLEARED")
    assert (approvals["status"], approvals["result"]["count"]) == ("FAILED", 3)
    materialised = _stored_items(close)
    assert materialised != stored
    assert _audit_actions(close) == audited
    assert get(app, checklist, vic).status_code == 200
    assert _stored_items(close) == materialised
    assert _audit_actions(close) == audited

    # Positive control: a fourth pending request arrives, and the command that evaluates the gates
    # (a waiver request by Maya, period.close) audits the result it stores.
    with system_session(close) as session:
        adjusted, _, _ = contract_of(session, close)
        session.execute(
            insert(approval_request).values(
                **approval_request_values(
                    close.tenant_id,
                    subject_type="MANUAL_ADJUSTMENT",
                    subject_id=adjusted,
                    entity_id=close.entity_id,
                    preparer_id=close.maya.member.user_id,
                    summary="Schedule override (SC-8 witness)",
                )
            )
        )
    gate = _item(changed.json(), "RECONCILIATIONS_GENERATED")
    assert gate["status"] == "FAILED"
    waived = post(
        app,
        f"{PERIODS}/{close.state_id}/checklist/{gate['id']}/waive",
        close.maya,
        {"reason": WAIVER_REASON},
        if_match=_if_match(changed.json()),
    )
    assert waived.status_code == 200, waived.text
    by_command = _audit_actions(close)[len(audited) :]
    assert "close_checklist_item.evaluate" in by_command  # APPROVALS_CLEARED 3 -> 4, audited
    assert "close_checklist_item.request_waiver" in by_command
    assert RUN_MONITORS not in _audit_actions(close)


def _monitor_runs(close: CloseWorld) -> list[tuple[str, str]]:
    """(actor kind, request id) of every ``close.run_monitors`` audit event, in chain order."""
    with system_session(close) as session:
        rows = session.execute(
            select(audit_event.c.actor_kind, audit_event.c.request_id)
            .where(audit_event.c.action == RUN_MONITORS)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [(str(kind), str(request_id)) for kind, request_id in rows]


def _duplicates_raised(close: CloseWorld) -> int:
    with system_session(close) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(exception_item)
                .where(exception_item.c.code == "DQ_DUPLICATE_INVOICE")
            ).scalar_one()
        )


def test_sc_8_monitors_run_before_the_period_commands_and_never_on_a_read(
    close: CloseWorld,
) -> None:
    """Security finding SC-8: the data-quality monitors (CLO-5 ``close.run_monitors``) ran on every
    cockpit GET. They now run before ``start-close`` and ``request-lock`` — as SYSTEM, in their own
    unit of work, under the command's request id — and in the scheduled sweep (05 SCH-10). So the
    certification request evaluates ``DATA_QUALITY_CLEAR`` on current findings without anyone
    having opened the cockpit, a refused request keeps the finding it raised, a read runs nothing,
    and a caller who may not close the entity's period cannot make them run. January to August
    are closed first (PRD WLD-P-02; BR-CLS-08, supervisor ruling R-6), so the certification
    request is judged on its gates."""
    app = close.app
    earlier_periods_closed(close)
    with system_session(close) as session:
        uk = other_entity(session, close)
    vic = holding(app, colleague(close.tenant_id, "vic"), "viewer")
    pat = holding(app, colleague(close.tenant_id, "pat"), "revenue_accountant", entity_ids=[uk])
    cockpit = f"{PERIODS}/{close.state_id}/cockpit"
    start_close = f"{PERIODS}/{close.state_id}/start-close"
    shown = get(app, cockpit, vic)
    assert shown.status_code == 200, shown.text
    assert _monitor_runs(close) == []

    # No period.close at all (403), or period.close for another entity only (404): no monitor run.
    viewer = post(app, start_close, vic, {"comment": "No."}, if_match=_if_match(shown.json()))
    assert (viewer.status_code, slug(viewer)) == (403, "forbidden"), viewer.text
    foreign = post(app, start_close, pat, {"comment": "No."}, if_match=_if_match(shown.json()))
    assert (foreign.status_code, slug(foreign)) == (404, "not-found"), foreign.text
    assert _monitor_runs(close) == []

    # start-close runs the monitors first, as SYSTEM, under the command's own request id.
    started = post(
        app,
        start_close,
        close.maya,
        {"comment": "Start the September close."},
        if_match=_if_match(shown.json()),
    )
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "closing"
    assert _monitor_runs(close) == [("SYSTEM", started.headers[REQUEST_ID])]
    assert _duplicates_raised(close) == 0

    # A duplicate invoice arrives during the close. Reads do not raise it ...
    with system_session(close) as session:
        identity_duplicates(session, close, issue_date=date(2026, 9, 3))
    closing = get(app, cockpit, vic)
    assert closing.status_code == 200, closing.text
    assert _item(closing.json(), "DATA_QUALITY_CLEAR")["status"] == "PASSED"
    assert _duplicates_raised(close) == 0
    assert len(_monitor_runs(close)) == 1

    # ... the certification request does: the gate fails on the finding, and the refusal keeps it.
    refused = post(
        app,
        f"{PERIODS}/{close.state_id}/request-lock",
        close.maya,
        {"certification_comment": "I certify the September 2026 close."},
        if_match=_if_match(closing.json()),
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert "DATA_QUALITY_CLEAR" in {error["rule_id"] for error in refused.json()["errors"]}
    assert _duplicates_raised(close) == 1
    assert _monitor_runs(close) == [
        ("SYSTEM", started.headers[REQUEST_ID]),
        ("SYSTEM", refused.headers[REQUEST_ID]),
    ]
    after = get(app, cockpit, vic)
    assert after.status_code == 200, after.text
    quality = _item(after.json(), "DATA_QUALITY_CLEAR")
    assert (quality["status"], quality["result"]["count"]) == ("FAILED", 1)
    assert len(_monitor_runs(close)) == 2
