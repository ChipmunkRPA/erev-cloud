"""API-R-25 rule set authoring (04 T-REF-24 to T-REF-27, §14.1 DB-04, §15.3 API-R-25, §16.14
API-S-VersionSummary; PRD ERR-09; REQ-POL-002, REQ-POL-003; BUILD_SPEC RFD-4).

Maya holds Revenue Accountant (``config.author``) in a provisioned workspace. She authors the
``APPROVAL_ROUTING`` decision table of PRD §2.5.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, rule, rule_set_version, rule_test_case
from erev_api.domain.policies import rule_sets
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Select, select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
PROBLEM_BASE = "https://erev.dev/problems/"
ROUTING_SET: Mapping[str, Any] = {"code": "APPROVAL_ROUTING", "kind": "APPROVAL_ROUTING"}
CONTRACT_STEP: Mapping[str, Any] = {
    "name": "Contract approval",
    "permission": "contract.approve",
    "min_approvers": 1,
}
ROUTE_CON_100K: Mapping[str, Any] = {
    "rule_key": "ROUTE-CON-100K",
    "priority": 10,
    "conditions": [{"field": "subject.type", "op": "eq", "value": "CONTRACT_ACTIVATION"}],
    "outputs": {"steps": [CONTRACT_STEP]},
}


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    someone = member(keyring, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="revenue_accountant",
        )
    return workspace(app, someone, sign_in(app, someone.email))


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def rows(tenant_id: UUID, statement: Select[Any]) -> list[Mapping[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def draft_version(app: FastAPI, maya: Actor) -> tuple[str, str]:
    """The ``APPROVAL_ROUTING`` set and its DRAFT version 1."""
    created = post(app, RULE_SETS, maya, ROUTING_SET)
    assert created.status_code == 201, created.text
    version = post(app, f"{RULE_SETS}/{created.json()['id']}/versions", maya, {})
    assert version.status_code == 201, version.text
    return str(created.json()["id"]), str(version.json()["id"])


def walk(tenant_id: UUID, version_id: str, *statuses: str) -> None:
    """Move a version along E-12 directly, as the lifecycle commands of RFD-5 will (DB-04)."""
    with tenant_session(_context(tenant_id)) as session:
        for status in statuses:
            values: dict[str, Any] = {"status": status}
            if status == "TESTED":
                values["content_sha256"] = secrets.token_hex(32)
            session.execute(
                update(rule_set_version)
                .where(rule_set_version.c.id == UUID(version_id))
                .values(**values)
            )


def test_create_routing_version_and_upsert_rule(app: FastAPI, maya: Actor) -> None:
    created = post(app, RULE_SETS, maya, ROUTING_SET)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["code"], body["kind"], body["name"]) == (
        "APPROVAL_ROUTING",
        "APPROVAL_ROUTING",
        "APPROVAL_ROUTING",
    )
    assert (body["current_version"], body["latest_version"]) == (None, None)
    assert created.headers["Location"] == f"{RULE_SETS}/{body['id']}"
    taken = post(app, RULE_SETS, maya, ROUTING_SET)
    assert (taken.status_code, fields(taken)) == (422, [("code", "T-REF-24")]), taken.text

    version = post(app, f"{RULE_SETS}/{body['id']}/versions", maya, {})
    assert version.status_code == 201, version.text
    assert (version.json()["version_no"], version.json()["status"]) == (1, "DRAFT")
    version_id = version.json()["id"]
    rules_path = f"{VERSIONS}/{version_id}/rules"

    first = post(app, rules_path, maya, ROUTE_CON_100K)
    assert first.status_code == 201, first.text
    assert (first.json()["rule_key"], first.json()["specificity"]) == ("ROUTE-CON-100K", 1)

    threshold = {"field": "amount.functional", "op": "gte", "value": "100000.00"}
    replaced = post(
        app,
        rules_path,
        maya,
        {
            **ROUTE_CON_100K,
            "priority": 20,
            "conditions": [*ROUTE_CON_100K["conditions"], threshold],
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["id"] == first.json()["id"]
    assert (replaced.json()["priority"], replaced.json()["specificity"]) == (20, 2)

    listed = get(app, rules_path, maya)
    assert listed.status_code == 200, listed.text
    assert [(item["rule_key"], item["priority"]) for item in listed.json()["items"]] == [
        ("ROUTE-CON-100K", 20)
    ]
    stored = rows(
        maya.member.tenant_id,
        select(rule.c.rule_key, rule.c.specificity, rule.c.conditions).where(
            rule.c.rule_set_version_id == UUID(version_id)
        ),
    )
    assert [(row["rule_key"], row["specificity"]) for row in stored] == [("ROUTE-CON-100K", 2)]
    assert stored[0]["conditions"][1] == threshold
    events = rows(
        maya.member.tenant_id,
        select(audit_event.c.action, audit_event.c.detail)
        .where(
            audit_event.c.action.in_(["rule_set.create", "rule_set_version.create", "rule.upsert"])
        )
        .order_by(audit_event.c.chain_seq),
    )
    assert [event["action"] for event in events] == [
        "rule_set.create",
        "rule_set_version.create",
        "rule.upsert",
        "rule.upsert",
    ]
    assert [event["detail"]["created"] for event in events[2:]] == [True, False]


def test_condition_field_outside_fields_rejected(app: FastAPI, maya: Actor) -> None:
    _, version_id = draft_version(app, maya)
    refused = post(
        app,
        f"{VERSIONS}/{version_id}/rules",
        maya,
        {
            **ROUTE_CON_100K,
            "conditions": [
                {"field": "product.code", "op": "eq", "value": "AVM-GW"},
                {"field": "subject.type", "op": "like", "value": "CONTRACT"},
                {"field": "amount.functional", "op": "gte", "value": 100000.5},
            ],
            "outputs": {"steps": [{**CONTRACT_STEP, "permission": "contract.read"}]},
        },
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert refused.json()["errors"][0]["field"] == "conditions[0].field"
    assert fields(refused) == [
        ("conditions[0].field", "T-REF-26"),
        ("conditions[1].op", "T-REF-26"),
        ("conditions[2].value", "T-REF-26"),
        ("outputs.steps[0].permission", "T-REF-26"),
    ]
    assert (
        rows(
            maya.member.tenant_id,
            select(rule.c.id).where(rule.c.rule_set_version_id == UUID(version_id)),
        )
        == []
    )


def test_d98_93_step_role_is_an_optional_code(app: FastAPI, maya: Actor) -> None:
    """04 T-REF-26 ``outputs`` (D-98 93): a routing step may carry ``role`` — the code of the role
    every approver of the step must hold (T-PLT-18 ``required_role_id``) — and the rule is stored
    with it; a malformed role is refused on the step's member and the step shape still names the
    members. Whether the code names an active role is checked when a submission routes over the
    published step (``routing._step_role_id``, fail closed; ``test_routing``). Found by the demo
    seed, whose ROUTE-VOID-02 carries ``role: controller`` (VOID-2 follow-up)."""
    _, version_id = draft_version(app, maya)
    rules_path = f"{VERSIONS}/{version_id}/rules"
    with_role = {**CONTRACT_STEP, "role": "controller"}
    created = post(app, rules_path, maya, {**ROUTE_CON_100K, "outputs": {"steps": [with_role]}})
    assert created.status_code == 201, created.text
    stored = rows(
        maya.member.tenant_id,
        select(rule.c.outputs).where(rule.c.rule_set_version_id == UUID(version_id)),
    )
    assert [row["outputs"]["steps"] for row in stored] == [[with_role]]
    for malformed in ("", " ", 5, "not a code!"):
        refused = post(
            app,
            rules_path,
            maya,
            {
                **ROUTE_CON_100K,
                "rule_key": "ROUTE-BAD",
                "outputs": {"steps": [{**CONTRACT_STEP, "role": malformed}]},
            },
        )
        assert (refused.status_code, fields(refused)) == (
            422,
            [("outputs.steps[0].role", "T-REF-26")],
        ), refused.text
    shape = post(
        app,
        rules_path,
        maya,
        {
            **ROUTE_CON_100K,
            "rule_key": "ROUTE-BAD",
            "outputs": {"steps": [{**CONTRACT_STEP, "roles": ["controller"]}]},
        },
    )
    assert (shape.status_code, fields(shape)) == (422, [("outputs.steps[0]", "T-REF-26")])
    assert [
        row["rule_key"]
        for row in rows(
            maya.member.tenant_id,
            select(rule.c.rule_key).where(rule.c.rule_set_version_id == UUID(version_id)),
        )
    ] == ["ROUTE-CON-100K"]


def test_item7_step_role_must_name_an_active_role_at_upsert_and_publish(
    app: FastAPI, maya: Actor
) -> None:
    """04 T-REF-26 (lane F-CTR record §6 item 7, ruled): a routing step's ``role`` must name an
    existing active role of the tenant — refused at the rule upsert with a named error on the step's
    member, and again by the publication check over the stored rules — so a mistyped or since-
    deactivated role fails once at authoring instead of at every submission; the submission-time
    fail-closed check (``routing._step_role_id``) stays as it is."""
    _, version_id = draft_version(app, maya)
    rules_path = f"{VERSIONS}/{version_id}/rules"
    unknown = post(
        app,
        rules_path,
        maya,
        {**ROUTE_CON_100K, "outputs": {"steps": [{**CONTRACT_STEP, "role": "cfo"}]}},
    )
    assert (unknown.status_code, fields(unknown)) == (
        422,
        [("outputs.steps[0].role", "T-REF-26")],
    ), unknown.text
    assert unknown.json()["errors"][0]["message"] == (
        "No active role has the code cfo; choose an existing active role."
    )
    known = post(
        app,
        rules_path,
        maya,
        {**ROUTE_CON_100K, "outputs": {"steps": [{**CONTRACT_STEP, "role": "controller"}]}},
    )
    assert known.status_code == 201, known.text
    # Publication re-checks the stored rules: a rule that reached the version another way (here
    # written directly) naming a role that no longer exists is a publication finding on its step.
    tenant_id = maya.member.tenant_id
    with tenant_session(_context(tenant_id)) as session:
        session.execute(
            rule.insert().values(
                tenant_id=tenant_id,
                id=UUID(int=7),
                rule_set_version_id=UUID(version_id),
                rule_key="ROUTE-GONE",
                priority=30,
                conditions=[{"field": "subject.type", "op": "eq", "value": "CONTRACT_VOID"}],
                outputs={"steps": [{**CONTRACT_STEP, "role": "cfo"}]},
                specificity=1,
                description=None,
            )
        )
        version = rule_sets.lock_version(session, UUID(version_id))
        findings = rule_sets._publish_errors(session, version)
    assert [(error.field, error.rule_id, error.message) for error in findings] == [
        (
            "rules[ROUTE-GONE].outputs.steps[0].role",
            "T-REF-26",
            "No active role has the code cfo; choose an existing active role.",
        )
    ]


def test_rules_frozen_outside_draft_or_tested(app: FastAPI, maya: Actor) -> None:
    _, version_id = draft_version(app, maya)
    rules_path = f"{VERSIONS}/{version_id}/rules"
    created = post(app, rules_path, maya, ROUTE_CON_100K)
    assert created.status_code == 201, created.text

    # TESTED versions still take rule changes (API-R-25; DB-04).
    walk(maya.member.tenant_id, version_id, "TESTED")
    tested = post(app, rules_path, maya, {**ROUTE_CON_100K, "priority": 15})
    assert tested.status_code == 200, tested.text

    walk(maya.member.tenant_id, version_id, "SUBMITTED")
    frozen = post(app, rules_path, maya, {**ROUTE_CON_100K, "priority": 30})
    assert (frozen.status_code, slug(frozen)) == (409, "configuration-frozen"), frozen.text
    assert fields(frozen) == [("status", "DB-04")]
    removed = call(
        app,
        "DELETE",
        f"{rules_path}/{created.json()['id']}",
        headers=cookie_headers(maya.token, maya.csrf_token),
    )
    assert (removed.status_code, slug(removed)) == (409, "configuration-frozen"), removed.text
    case = post(
        app,
        f"{VERSIONS}/{version_id}/test-cases",
        maya,
        {
            "name": "Contract",
            "input": {"subject.type": "CONTRACT_ACTIVATION"},
            "expected_output": {"matched": True},
        },
    )
    assert (case.status_code, slug(case)) == (409, "configuration-frozen"), case.text
    version = get(app, f"{VERSIONS}/{version_id}", maya)
    patched = call(
        app,
        "PATCH",
        f"{VERSIONS}/{version_id}",
        json={"effective_from": "2026-10-01T00:00:00Z"},
        headers=cookie_headers(
            maya.token, maya.csrf_token, **{"If-Match": version.headers["ETag"]}
        ),
    )
    assert (patched.status_code, slug(patched)) == (409, "configuration-frozen"), patched.text
    assert [
        row["priority"]
        for row in rows(
            maya.member.tenant_id,
            select(rule.c.priority).where(rule.c.rule_set_version_id == UUID(version_id)),
        )
    ] == [15]


def test_list_items_carry_version_summary(app: FastAPI, maya: Actor) -> None:
    _, version_id = draft_version(app, maya)
    assert post(app, f"{VERSIONS}/{version_id}/rules", maya, ROUTE_CON_100K).status_code == 201

    listed = get(app, RULE_SETS, maya, kind="APPROVAL_ROUTING", count="true")
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Erev-Total-Count"] == "1"
    [item] = listed.json()["items"]
    assert item["current_version"] is None
    assert item["latest_version"] == {
        "id": version_id,
        "version_no": 1,
        "status": "DRAFT",
        "effective_from": None,
        "published_at": None,
        "rule_count": 1,
        "lint_status": None,
    }
    by_status = get(app, RULE_SETS, maya, status="DRAFT")
    assert [entry["code"] for entry in by_status.json()["items"]] == ["APPROVAL_ROUTING"]

    # The provisioned AUTO_APPROVAL sets are PUBLISHED, so each carries a current version (04
    # §14.3 item 2): AUTO-BOOTSTRAP and, since rev 1.72 (D-98 133 AMENDMENT 4), AUTO-MIG-01.
    seeded = {
        item["code"]: item
        for item in get(app, RULE_SETS, maya, kind="AUTO_APPROVAL").json()["items"]
    }
    assert sorted(seeded) == ["AUTO-BOOTSTRAP", "AUTO-MIG-01"]
    for item in seeded.values():
        assert item["current_version"]["version_no"] == 1
        assert item["current_version"] == item["latest_version"]
        # API-S-VersionSummary `published_at` (04 rev 1.183): a published version says when.
        assert item["current_version"]["published_at"] is not None
    unknown = get(app, RULE_SETS, maya, kind="PAYMENT_TERMS")
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text


def test_test_cases_written_while_draft(app: FastAPI, maya: Actor) -> None:
    _, version_id = draft_version(app, maya)
    path = f"{VERSIONS}/{version_id}/test-cases"
    invalid = post(
        app,
        path,
        maya,
        {"name": "Contract", "input": {"product.code": "AVM-GW"}, "expected_output": {"steps": 1}},
    )
    assert (invalid.status_code, fields(invalid)) == (
        422,
        [("input.product.code", "T-REF-27"), ("expected_output", "T-REF-27")],
    ), invalid.text

    created = post(
        app,
        path,
        maya,
        {
            "name": "Large contract activation",
            "input": {"subject.type": "CONTRACT_ACTIVATION", "amount.functional": "150000.00"},
            "expected_output": {"rule_key": "ROUTE-CON-100K"},
        },
    )
    assert created.status_code == 201, created.text
    [row] = rows(
        maya.member.tenant_id,
        select(rule_test_case).where(rule_test_case.c.subject_id == UUID(version_id)),
    )
    assert (row["subject_type"], row["name"], row["last_result"]) == (
        "rule_set_version",
        "Large contract activation",
        None,
    )
    assert row["expected_output"] == {"rule_key": "ROUTE-CON-100K"}
    listed = get(app, path, maya)
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
