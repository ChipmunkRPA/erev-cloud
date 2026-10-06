"""The separation-of-duties commands and the access review campaigns under a role held for named
entities (item SCOPE-WORKSPACE-LISTS-1, part (c3); supervisor rulings R-28, R-115 (c) and R-119
(b), and the supervisor's ruling of 2026-10-01, answer Q3; 03 REQ-PLT-010, REQ-PLT-012,
REQ-CTL-006; 04 API-C-03, API-R-07, API-R-51, T-PLT-10, T-PLT-14, T-PLT-40, T-PLT-41).

A separation-of-duties rule binds every member of the workspace: a new version of one asks
``role.manage`` for ALL entities. An exception is a member's: asking for one and revoking one
need ``role.manage`` for every entity of the member's role assignments — the rule of the
membership commands — and are refused by name (403, rule ``T-PLT-10``) after a DENIED event of
the command. The two lists stay as they are. An access review campaign snapshots every member of
the workspace with the roles and entities each holds: every route of it asks ``access.approve``
for ALL entities, and a reviewer named in a campaign holds it for all entities in person.

WLD-K-04 (``worlds.k04_saltmarsh``; AVM-UK and AVM-US). Every scoped role is granted through the
product (``POST /role-assignments``, requested by Marcus, approved by Grace): Tia is Tenant Admin
of AVM-US alone, Una an Auditor of AVM-UK alone, Uma an Auditor of AVM-US alone. Grace and Marcus
hold their roles for all entities.

Measured before the item, with the same grants: Tia proposed a new version of SoD-1, revoked
Una's approved exception and asked for another; created a campaign with herself as reviewer,
started it — the stored item of Una then named her entity by its id, because Tia's session does
not read AVM-UK — decided Una's item, and cancelled a campaign reviewed by Grace.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    access_review_campaign,
    access_review_item,
    audit_event,
    sod_exception,
)
from erev_api.domain.platform.access_reviews import REVIEWER_UNKNOWN, RULE_CAMPAIGN
from erev_api.domain.platform.users import MEMBER_BEYOND_SCOPE
from erev_api.enums import AuditOutcome, GrantStatus
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor
from support.reference import get, post
from support.rows import sod_exception_values
from support.worlds import AVM_UK, AVM_US
from tests.api.test_tenant_wide_acts_scope import denials, slug
from tests.domain.reports.test_entity_scoped_runs_db import scoped, second_admin

API: Final = "/api/v1"
RULES: Final = f"{API}/sod-rules"
VERSIONS: Final = f"{API}/sod-rules/{{code}}/versions"
EXCEPTIONS: Final = f"{API}/sod-exceptions"
REVIEWS: Final = f"{API}/access-reviews"
REVIEW: Final = f"{REVIEWS}/{{access_review_id}}"
ITEM: Final = f"{REVIEW}/items/{{item_id}}"
# the nine routes of 04 API-R-51, as the router declares them: method, route template
REVIEW_ROUTES: Final = (
    ("GET", REVIEWS),
    ("POST", REVIEWS),
    ("GET", REVIEW),
    ("POST", f"{REVIEW}/start"),
    ("POST", f"{REVIEW}/complete"),
    ("POST", f"{REVIEW}/cancel"),
    ("GET", f"{REVIEW}/items"),
    ("POST", f"{ITEM}/decide"),
    ("POST", f"{ITEM}/confirm-revocation"),
)
MANAGE: Final = "role.manage"
REVIEW_PERMISSION: Final = "access.approve"
REQUEST: Final = "sod_exception.request"
REVOKE: Final = "sod_exception.revoke"
REASON: Final = "The audit engagement ended on 30 September."
BEYOND: Final = {"rule_id": "T-PLT-10", "permission": MANAGE}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def refused_by_name(response: Any) -> tuple[int, str, str | None, list[tuple[str, str]]]:
    body = response.json()
    errors = [(error["rule_id"], error["message"]) for error in body.get("errors", ())]
    return response.status_code, slug(response), body.get("detail"), errors


def command_denials(world: worlds.ReportWorld, action: str) -> list[tuple[str, dict[str, Any]]]:
    """(the member the command was about, detail) of the DENIED events of a command."""
    rows = world.place.rows(
        select(audit_event.c.object_type, audit_event.c.object_id, audit_event.c.detail)
        .where(audit_event.c.action == action, audit_event.c.outcome == AuditOutcome.DENIED.value)
        .order_by(audit_event.c.chain_seq)
    )
    assert {row["object_type"] for row in rows} <= {"tenant_membership"}
    return [(str(row["object_id"]), dict(row["detail"])) for row in rows]


def exceptions_of(world: worlds.ReportWorld, member: Actor) -> list[tuple[str, str, bool]]:
    """(rule, status, revoked) of a member's exceptions, in rule order."""
    rows = world.place.rows(
        select(sod_exception.c.sod_rule_code, sod_exception.c.status, sod_exception.c.revoked_at)
        .where(sod_exception.c.membership_id == member.member.membership_id)
        .order_by(sod_exception.c.sod_rule_code)
    )
    return [
        (str(row["sod_rule_code"]), str(row["status"]), row["revoked_at"] is not None)
        for row in rows
    ]


def approved_exception(world: worlds.ReportWorld, member: Actor, rule_code: str) -> str:
    """An APPROVED exception of the member, a row of the test world; its id."""
    values = sod_exception_values(
        world.tenant_id,
        membership_id=member.member.membership_id,
        rule_code=rule_code,
        status=GrantStatus.APPROVED,
    )
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(sod_exception).values(**values))
    return str(values["id"])


@pytest.mark.slow
def test_a_sod_rule_is_the_workspaces_and_an_exception_is_its_members(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Tia, Tenant Admin of AVM-US alone, reads the rules and the exceptions as before. A new
    version of a rule answers her 403 ``forbidden`` after a DENIED event that states the scope,
    and Grace, of all entities, proposes it. An exception of Una (AVM-UK) or of Marcus (all
    entities) she neither asks for nor revokes — 403 by name, rule ``T-PLT-10``, after a DENIED
    event of the command, before anything of the body is judged — while those of Uma (AVM-US)
    she asks for and revokes. Before: every one of these answered Tia as it answers Grace."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    tia = scoped(world, clock, grace, "tia", ("tenant_admin", AVM_US))
    una = scoped(world, clock, grace, "una", ("auditor", AVM_UK))
    uma = scoped(world, clock, grace, "uma", ("auditor", AVM_US))
    now = clock.now()

    # the two lists, as they are
    rules = get(app, RULES, tia, {"limit": "200"})
    assert rules.status_code == 200, rules.text
    rule = next(item for item in rules.json()["items"] if item["code"] == "SoD-1")
    assert get(app, EXCEPTIONS, tia).status_code == 200

    # a rule's next version: the workspace's
    version = {
        "name": rule["name"],
        "function_a_permissions": rule["function_a_permissions"],
        "function_b_permissions": rule["function_b_permissions"],
        "rationale": "Restated for the review of the 2026 financial year.",
        "comment": None,
    }
    path = VERSIONS.replace("{code}", "SoD-1")
    refused = post(app, path, tia, version)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert denials(world, MANAGE) == [
        {"method": "POST", "path": VERSIONS, "scope": "*", "permission": MANAGE}
    ]
    proposed = post(app, path, grace, version)
    assert proposed.status_code == 201, proposed.text

    # an exception: the member's
    def asked_for(member: Actor) -> dict[str, Any]:
        return {
            "sod_rule_code": "SoD-3",
            "membership_id": str(member.member.membership_id),
            # a control too short to pass: the scope is judged first, the body after
            "compensating_control": "Reviewed.",
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "comment": "Cover for the audit of the 2026 financial year",
        }

    by_name = (
        403,
        "forbidden",
        MEMBER_BEYOND_SCOPE,
        [("T-PLT-10", MEMBER_BEYOND_SCOPE)],
    )
    assert refused_by_name(post(app, EXCEPTIONS, tia, asked_for(una))) == by_name
    assert refused_by_name(post(app, EXCEPTIONS, tia, asked_for(world.marcus))) == by_name
    in_scope = post(app, EXCEPTIONS, tia, asked_for(uma))
    assert (in_scope.status_code, slug(in_scope)) == (422, "validation-failed"), in_scope.text
    complete = asked_for(uma) | {
        "compensating_control": "The Controller reviews every approval of the month."
    }
    requested = post(app, EXCEPTIONS, tia, complete)
    assert requested.status_code == 201, requested.text
    assert command_denials(world, REQUEST) == [
        (str(una.member.membership_id), BEYOND),
        (str(world.marcus.member.membership_id), BEYOND),
    ]
    assert exceptions_of(world, una) == []
    assert exceptions_of(world, uma) == [("SoD-3", "REQUESTED", False)]

    # a revocation
    of_una = approved_exception(world, una, "SoD-4")
    of_uma = approved_exception(world, uma, "SoD-4")
    # a reason too short to pass: the scope is judged first
    kept = post(app, f"{EXCEPTIONS}/{of_una}/revoke", tia, {"reason": "Ended."})
    assert refused_by_name(kept) == by_name
    assert command_denials(world, REVOKE) == [(str(una.member.membership_id), BEYOND)]
    assert exceptions_of(world, una) == [("SoD-4", "APPROVED", False)]
    unknown = post(app, f"{EXCEPTIONS}/{uuid4()}/revoke", tia, {"reason": REASON})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    ended = post(app, f"{EXCEPTIONS}/{of_uma}/revoke", tia, {"reason": REASON})
    assert ended.status_code == 200, ended.text
    assert exceptions_of(world, uma) == [
        ("SoD-3", "REQUESTED", False),
        ("SoD-4", "REVOKED", True),
    ]
    by_grace = post(app, f"{EXCEPTIONS}/{of_una}/revoke", grace, {"reason": REASON})
    assert by_grace.status_code == 200, by_grace.text
    assert exceptions_of(world, una) == [("SoD-4", "REVOKED", True)]
    # no denial but Tia's
    assert len(denials(world, MANAGE)) == 1
    assert len(command_denials(world, REQUEST)) == 2 and len(command_denials(world, REVOKE)) == 1


def asked(app: FastAPI, actor: Actor, method: str, template: str, review: str, item: str) -> Any:
    path = template.replace("{access_review_id}", review).replace("{item_id}", item)
    if method == "GET":
        return get(app, path, actor)
    body: dict[str, Any] = {}
    if template.endswith("/decide"):
        body = {"decision": "CERTIFIED", "comment": None}
    return post(app, path, actor, body)


@pytest.mark.slow
def test_an_access_review_is_run_by_approvers_of_all_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A reviewer named in a campaign holds ``access.approve`` for all entities: Tia, Tenant
    Admin of AVM-US alone, is refused at creation, 422 on her place in the list. The campaign
    Grace starts states each role with the CODES of its entities — Una's as AVM-UK. Each of the
    nine routes then answers Tia 403 ``forbidden`` after one DENIED event naming the route and
    the scope ``"*"``, the campaign and its items stay as they were, and Marcus, a reviewer of
    all entities, certifies Una's item. Before: Tia created, started, decided and cancelled, and
    a campaign she started stored AVM-UK by its id."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    tia = scoped(world, clock, grace, "tia", ("tenant_admin", AVM_US))
    una = scoped(world, clock, grace, "una", ("auditor", AVM_UK))
    marcus = world.marcus

    def campaign(*reviewers: Actor) -> dict[str, Any]:
        return {
            "name": "Q3 2026 access review",
            "as_of": clock.now().isoformat(),
            "reviewer_membership_ids": [str(who.member.membership_id) for who in reviewers],
        }

    # a reviewer holds the permission for all entities
    scoped_reviewer = post(app, REVIEWS, grace, campaign(marcus, tia))
    assert (scoped_reviewer.status_code, slug(scoped_reviewer)) == (422, "validation-failed")
    assert [
        (error["field"], error["rule_id"], error["message"])
        for error in scoped_reviewer.json()["errors"]
    ] == [("reviewer_membership_ids[1]", RULE_CAMPAIGN, REVIEWER_UNKNOWN)]
    created = post(app, REVIEWS, grace, campaign(marcus))
    assert created.status_code == 201, created.text
    review = str(created.json()["id"])
    started = post(app, f"{REVIEWS}/{review}/start", grace, {})
    assert started.status_code == 200, started.text

    # the snapshot names every entity by its code
    items = get(app, f"{REVIEWS}/{review}/items", grace, {"limit": "200"})
    assert items.status_code == 200, items.text
    by_member = {str(item["membership_id"]): item for item in items.json()["items"]}
    of_una = by_member[str(una.member.membership_id)]
    assert [
        (role["role_code"], role["is_all_entities"], role["entity_codes"])
        for role in of_una["roles_snapshot"]
    ] == [("auditor", False, [AVM_UK])]
    assert {
        code
        for item in by_member.values()
        for role in item["roles_snapshot"]
        for code in role["entity_codes"]
    } == {AVM_UK, AVM_US}

    def state() -> tuple[list[Any], list[Any]]:
        campaigns = world.place.rows(
            select(access_review_campaign).order_by(access_review_campaign.c.id)
        )
        decided = world.place.rows(select(access_review_item).order_by(access_review_item.c.id))
        return campaigns, decided

    # every route refuses the approver of one entity
    before = state()
    for method, template in REVIEW_ROUTES:
        refused = asked(app, tia, method, template, review, str(of_una["id"]))
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), (
            method,
            template,
            refused.text,
        )
    assert denials(world, REVIEW_PERMISSION) == [
        {"method": method, "path": template, "scope": "*", "permission": REVIEW_PERMISSION}
        for method, template in REVIEW_ROUTES
    ]
    assert state() == before

    # the reviewer of all entities decides
    decided = asked(app, marcus, "POST", f"{ITEM}/decide", review, str(of_una["id"]))
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"] == "CERTIFIED"
    assert UUID(str(decided.json()["reviewer"]["id"])) == marcus.member.user_id
    assert len(denials(world, REVIEW_PERMISSION)) == len(REVIEW_ROUTES)
