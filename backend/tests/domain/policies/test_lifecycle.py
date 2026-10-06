"""Configuration lifecycle of rule set versions (04 E-12, §14.1 DB-03, DB-04, DB-10, §15.3
API-R-25, API-R-57; PRD SM-04, BR-POL-01, ERR-75; dev-guide DG-SM-01 to DG-SM-03, DG-KRN-APR-01;
REQ-POL-003, REQ-POL-007; BUILD_SPEC RFD-5, BS3-D-05).

Maya (Revenue Accountant) authors and submits; Marcus (Controller, MFA enrolled) approves.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import subjects
from erev_api.db import migration_ops
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    file_object,
    rule_set_version,
)
from erev_api.domain.policies import lifecycle, simulation
from erev_api.enums import ApprovalSubjectType
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import select
from support.http import HttpResponse
from support.principals import carrying, colleague, enrolled, sign_in, workspace
from support.reference import calendar, entity, reject
from support.rows import insert_role_assignment
from support.subjects import ProbeSubjects, install

if TYPE_CHECKING:
    from conftest import Policies

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
APPROVALS = "/api/v1/approvals"
CONFIG_TEST_CASES = "/api/v1/config-test-cases"
PROBLEM_BASE = "https://erev.dev/problems/"
CONTRACT_STEP = {"name": "Contract approval", "permission": "contract.approve", "min_approvers": 1}
CONTROLLER_STEP = {
    "name": "Controller approval",
    "permission": "config.approve",
    "min_approvers": 1,
}
ROUTE_CON_100K: dict[str, Any] = {
    "rule_key": "ROUTE-CON-100K",
    "priority": 10,
    "conditions": [
        {"field": "subject.type", "op": "eq", "value": "CONTRACT_ACTIVATION"},
        {"field": "amount.functional", "op": "gte", "value": "100000.00"},
    ],
    "outputs": {"steps": [CONTRACT_STEP]},
}
LARGE_ACTIVATION = {"subject.type": "CONTRACT_ACTIVATION", "amount.functional": "150000.00"}
LARGE_CASE = ("Large contract activation", LARGE_ACTIVATION, {"rule_key": "ROUTE-CON-100K"})
TWO_STEPS = {**ROUTE_CON_100K, "outputs": {"steps": [CONTRACT_STEP, CONTROLLER_STEP]}}
GATEWAY: dict[str, Any] = {
    "rule_key": "GW",
    "priority": 10,
    "conditions": [{"field": "product.code", "op": "eq", "value": "AVM-GW"}],
    "outputs": {"pob_template_code": "GATEWAY"},
}
GATEWAY_CASE = ("Gateway", {"product.code": "AVM-GW"}, {"rule_key": "GW"})
# PRD ERR-75: the refusal of a superseding version's effective date, at submission and decision.
ERR_75 = (422, "validation-failed", [("effective_from", "REQ-POL-007")])


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def steps(policies: Policies, request_id: Any) -> list[tuple[str, str]]:
    return [
        (row["name"], row["required_permission"])
        for row in policies.rows(
            select(approval_step.c.name, approval_step.c.required_permission)
            .where(approval_step.c.approval_request_id == request_id)
            .order_by(approval_step.c.step_no)
        )
    ]


def test_status_pairs_equal_db_04() -> None:
    installed = {tuple(pair.split(">")) for pair in migration_ops.CONFIG_STATUS_PAIRS}
    assert lifecycle.STATUS_PAIRS == installed


def test_rule_set_version_lifecycle_registered(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = subjects.LIFECYCLES[ApprovalSubjectType.RULE_SET_VERSION]
    assert registered.on_approved.__module__ == "erev_api.domain.policies.rule_sets"
    # Without a registered lifecycle the spec fails closed, so no decision commits (XR-12).
    monkeypatch.delitem(subjects.LIFECYCLES, ApprovalSubjectType.RULE_SET_VERSION)
    spec = subjects.SUBJECTS[ApprovalSubjectType.RULE_SET_VERSION]
    with pytest.raises(LookupError, match="no registered lifecycle"):
        spec.on_approved(None, uuid4(), uuid4())  # type: ignore[arg-type]


def test_testing_requires_passing_cases(policies: Policies) -> None:
    rule_set_id = policies.rule_set("APPROVAL_ROUTING", "APPROVAL_ROUTING")
    version_id = policies.version(rule_set_id)
    policies.add_rule(version_id, ROUTE_CON_100K)
    test_path = f"{VERSIONS}/{version_id}/test"
    empty = policies.post(test_path)
    assert (empty.status_code, fields(empty)) == (422, [("test_cases", "REQ-POL-003")]), empty.text

    case = policies.add_case(
        version_id, ("Large contract activation", LARGE_ACTIVATION, {"rule_key": "ROUTE-CON-50K"})
    )
    failing = policies.post(test_path)
    assert failing.status_code == 200, failing.text
    body = failing.json()
    assert (body["status"], body["content_sha256"], body["lint_result"]["status"]) == (
        "DRAFT",
        None,
        "PASS",
    )
    assert body["test_evidence"] == {
        "total": 1,
        "passed": 0,
        "failed": 1,
        "not_run": 0,
        "last_run_at": "2026-09-12T12:00:00Z",
    }
    early = policies.post(f"{VERSIONS}/{version_id}/submit", {})
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert early.json()["errors"][0]["rule_id"] == "DB-03"

    listed = policies.get(CONFIG_TEST_CASES, subject_type="rule_set_version", subject_id=version_id)
    [stored] = listed.json()["items"]
    assert (stored["id"], stored["last_result"]) == (case["id"], "FAIL")
    corrected = policies.patch(
        f"{CONFIG_TEST_CASES}/{case['id']}",
        {"expected_output": {"rule_key": "ROUTE-CON-100K"}},
        etag=f'"r{stored["row_version"]}"',
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["last_result"] is None

    passing = policies.post(test_path)
    assert passing.status_code == 200, passing.text
    body = passing.json()
    assert body["status"] == "TESTED"
    assert (body["test_evidence"]["passed"], body["test_evidence"]["failed"]) == (1, 0)
    context = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        content = subjects.rule_set_version_content(session, UUID(version_id))
    assert body["content_sha256"] == sha256_hex(content)
    [event] = policies.rows(
        select(audit_event.c.before, audit_event.c.after, audit_event.c.detail).where(
            audit_event.c.action == "rule_set_version.tested",
            audit_event.c.object_id == UUID(version_id),
        )
    )
    assert (event["before"]["status"], event["after"]["status"]) == ("DRAFT", "TESTED")
    assert (event["detail"]["passed"], event["detail"]["failed"]) == (1, 0)


def test_submission_attaches_simulation_report(policies: Policies) -> None:
    _, version_id = policies.tested(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    body = policies.submit(version_id)
    assert body["status"] == "SUBMITTED"
    assert body["impact_simulation"]["summary"] == {
        "contracts_affected": 0,
        "revenue_delta_by_period": [],
        "balance_delta": [],
        "journal_delta": [],
        "statement": "No contracts affected",
    }
    file_id = UUID(body["impact_simulation"]["file_id"])
    [report] = policies.rows(select(file_object.c.purpose).where(file_object.c.id == file_id))
    assert report["purpose"] == "REPORT_OUTPUT"
    [stored] = policies.rows(
        select(rule_set_version.c.impact_simulation_file_id).where(
            rule_set_version.c.id == UUID(version_id)
        )
    )
    assert stored["impact_simulation_file_id"] == file_id

    [request] = policies.rows(
        select(approval_request.c.id, approval_request.c.status, approval_request.c.summary).where(
            approval_request.c.subject_type == "RULE_SET_VERSION",
            approval_request.c.subject_id == UUID(version_id),
        )
    )
    assert (request["status"], request["summary"]) == (
        "PENDING",
        "Publish version 1 of rule set APPROVAL_ROUTING",
    )
    assert (body["approval_request_id"], body["pending_approval_request_id"]) == (
        str(request["id"]),
        str(request["id"]),
    )
    assert steps(policies, request["id"]) == [("Approval", "config.approve")]
    [event] = policies.rows(
        select(audit_event.c.before, audit_event.c.after, audit_event.c.detail).where(
            audit_event.c.action == "rule_set_version.submitted",
            audit_event.c.object_id == UUID(version_id),
        )
    )
    assert (event["before"]["status"], event["after"]["status"]) == ("TESTED", "SUBMITTED")
    assert event["detail"]["impact_simulation"]["summary"]["statement"] == "No contracts affected"
    again = policies.post(f"{VERSIONS}/{version_id}/submit", {})
    assert (again.status_code, fields(again)) == (409, [("status", "DB-03")]), again.text


def test_simulation_summarises_registered_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert simulation.summarise([])["statement"] == "No contracts affected"
    delta = {"period_key": "2026-10", "amount": {"amount": "-150.00", "currency": "USD"}}
    first = simulation.ProviderResult(contracts_affected=2, revenue_delta_by_period=(delta,))
    summary = simulation.summarise([first, simulation.ProviderResult(contracts_affected=1)])
    assert (summary["contracts_affected"], summary["statement"]) == (3, "3 contracts affected")
    assert summary["revenue_delta_by_period"] == [delta]
    monkeypatch.setitem(simulation.PROVIDERS, "probe", lambda _uow, _subject: first)
    with pytest.raises(ValueError, match="registered already"):
        simulation.register_provider("probe", lambda _uow, _subject: first)


def test_publish_supersedes_prior_version(policies: Policies) -> None:
    rule_set_id, first = policies.published(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    second = policies.version(
        rule_set_id, source_version_id=first, effective_from="2026-10-01T00:00:00Z"
    )
    two_steps = {**ROUTE_CON_100K, "outputs": {"steps": [CONTRACT_STEP, CONTROLLER_STEP]}}
    policies.add_rule(second, two_steps)
    tested = policies.post(f"{VERSIONS}/{second}/test")
    assert tested.json()["status"] == "TESTED", tested.text
    submitted = policies.submit(second)
    assert submitted["supersedes_version_id"] == first
    approved = policies.approve(str(submitted["approval_request_id"]))
    assert approved.status_code == 200, approved.text

    stored = policies.rows(
        select(
            rule_set_version.c.version_no,
            rule_set_version.c.status,
            rule_set_version.c.effective_from,
            rule_set_version.c.effective_to,
            rule_set_version.c.published_by,
        )
        .where(rule_set_version.c.rule_set_id == UUID(rule_set_id))
        .order_by(rule_set_version.c.version_no)
    )
    assert [(row["version_no"], row["status"]) for row in stored] == [
        (1, "SUPERSEDED"),
        (2, "PUBLISHED"),
    ]
    boundary = datetime(2026, 10, 1, tzinfo=UTC)
    assert (stored[0]["effective_to"], stored[1]["effective_from"], stored[1]["effective_to"]) == (
        boundary,
        boundary,
        None,
    )
    # [effective_from, effective_to) is half-open: version 1 is in force through 2026-09-30.
    assert (stored[0]["effective_to"] - timedelta(microseconds=1)).date() == date(2026, 9, 30)
    assert stored[1]["published_by"] == policies.marcus.member.user_id

    before_rules = [
        {
            "rule_key": "ROUTE-CON-100K",
            "priority": 10,
            "specificity": 2,
            "conditions": ROUTE_CON_100K["conditions"],
            "outputs": ROUTE_CON_100K["outputs"],
            "description": None,
        }
    ]
    after_rules = [{**before_rules[0], "outputs": two_steps["outputs"]}]
    [published] = policies.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.action == "rule_set_version.published",
            audit_event.c.object_id == UUID(second),
        )
    )
    assert (published["before"]["status"], published["after"]["status"]) == (
        "APPROVED",
        "PUBLISHED",
    )
    assert (published["before"]["rules"], published["after"]["rules"]) == (
        before_rules,
        after_rules,
    )
    [superseded] = policies.rows(
        select(audit_event.c.before, audit_event.c.after).where(
            audit_event.c.action == "rule_set_version.superseded",
            audit_event.c.object_id == UUID(first),
        )
    )
    assert (superseded["before"]["status"], superseded["after"]["status"]) == (
        "PUBLISHED",
        "SUPERSEDED",
    )
    assert (superseded["before"]["rules"], superseded["after"]["rules"]) == (
        before_rules,
        after_rules,
    )
    assert superseded["before"]["effective_to"] is None
    assert superseded["after"]["effective_to"] is not None

    repeated = policies.post(f"{VERSIONS}/{second}/publish")
    assert (repeated.status_code, repeated.json()["status"]) == (200, "PUBLISHED"), repeated.text
    [item] = policies.get(RULE_SETS, kind="APPROVAL_ROUTING").json()["items"]
    assert (item["current_version"]["version_no"], item["latest_version"]["version_no"]) == (2, 2)


def test_author_cannot_approve(policies: Policies) -> None:
    # Maya also holds Controller and verifies MFA, so only separation of duties refuses her.
    maya = policies.maya.member
    context = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=policies.tenant_id,
            membership_id=maya.membership_id,
            role_code="controller",
        )
    verified = enrolled(policies.app, policies.clock, maya)
    # Maya works on with the verified session: with a factor, her earlier one owes the challenge
    # (REQ-PLT-005).
    policies = carrying(policies, maya=verified)
    _, version_id = policies.tested(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    request_id = str(policies.submit(version_id)["approval_request_id"])
    detail = policies.get(f"{APPROVALS}/{request_id}", verified)
    assert detail.json()["can_decide"] is False, detail.text

    refused = policies.approve(request_id, verified)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    decisions = policies.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert decisions == []
    [row] = policies.rows(
        select(rule_set_version.c.status).where(rule_set_version.c.id == UUID(version_id))
    )
    assert row["status"] == "SUBMITTED"

    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    assert policies.get(f"{VERSIONS}/{version_id}").json()["status"] == "PUBLISHED"


def test_author_who_did_not_submit_cannot_approve(policies: Policies) -> None:
    # Maya authors; Priya submits; Maya, also a Controller with MFA, is still the author (SoD-5).
    maya = policies.maya.member
    priya = colleague(policies.tenant_id, "priya")
    context = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for someone, code in ((maya, "controller"), (priya, "revenue_accountant")):
            insert_role_assignment(
                session,
                tenant_id=policies.tenant_id,
                membership_id=someone.membership_id,
                role_code=code,
            )
    verified = enrolled(policies.app, policies.clock, maya)
    # Maya works on with the verified session: with a factor, her earlier one owes the challenge
    # (REQ-PLT-005).
    policies = carrying(policies, maya=verified)
    submitter = workspace(policies.app, priya, sign_in(policies.app, priya.email))
    _, version_id = policies.tested(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    submitted = policies.post(f"{VERSIONS}/{version_id}/submit", {}, actor=submitter)
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])

    refused = policies.approve(request_id, verified)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert refused.json()["detail"] == lifecycle.AUTHOR_DETAIL
    decisions = policies.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert decisions == []
    [row] = policies.rows(
        select(rule_set_version.c.status).where(rule_set_version.c.id == UUID(version_id))
    )
    assert row["status"] == "SUBMITTED"


@pytest.mark.control("CTL-031")
def test_ctl_031_unpublished_routing_version_not_applied(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = ProbeSubjects()
    install(
        monkeypatch,
        probe.spec(ApprovalSubjectType.JOURNAL_RUN, required_permission="journal.approve"),
    )
    journal_route = {
        "rule_key": "ROUTE-JOURNAL",
        "priority": 10,
        "conditions": [{"field": "subject.type", "op": "eq", "value": "JOURNAL_RUN"}],
        "outputs": {
            "steps": [
                {"name": "Journal review", "permission": "journal.approve", "min_approvers": 1},
                CONTROLLER_STEP,
            ]
        },
    }
    _, version_id = policies.tested(
        "APPROVAL_ROUTING",
        "APPROVAL_ROUTING",
        [journal_route],
        [("Journal run", {"subject.type": "JOURNAL_RUN"}, {"rule_key": "ROUTE-JOURNAL"})],
    )
    submitted = policies.submit(version_id)

    # A SUBMITTED routing version routes nothing: the request takes the subject's default step.
    unrouted = policies.submit_probe(ApprovalSubjectType.JOURNAL_RUN, probe)
    assert unrouted["routing_rule_set_version_id"] is None
    assert steps(policies, unrouted["id"]) == [("Approval", "journal.approve")]

    approved = policies.approve(str(submitted["approval_request_id"]))
    assert approved.status_code == 200, approved.text
    routed = policies.submit_probe(ApprovalSubjectType.JOURNAL_RUN, probe)
    assert routed["routing_rule_set_version_id"] == UUID(version_id)
    assert steps(policies, routed["id"]) == [
        ("Journal review", "journal.approve"),
        ("Controller approval", "config.approve"),
    ]


def superseding(
    policies: Policies, rule_set_id: str, first: str, rule: dict[str, Any], **version: Any
) -> str:
    """Version 2 of the rule set: a copy of the published version with ``rule`` put, TESTED."""
    second = policies.version(rule_set_id, source_version_id=first, **version)
    policies.add_rule(second, rule)
    tested = policies.post(f"{VERSIONS}/{second}/test")
    assert tested.json()["status"] == "TESTED", tested.text
    return second


def redated(policies: Policies, version_id: str, effective_from: str | None) -> None:
    """Move the effective date of a TESTED version; the date is content, so the tests run again."""
    current = policies.get(f"{VERSIONS}/{version_id}").json()
    moved = policies.patch(
        f"{VERSIONS}/{version_id}",
        {"effective_from": effective_from},
        etag=f'"r{current["row_version"]}"',
    )
    assert moved.status_code == 200, moved.text
    tested = policies.post(f"{VERSIONS}/{version_id}/test")
    assert tested.json()["status"] == "TESTED", tested.text


def versions_of(policies: Policies, rule_set_id: str) -> list[tuple[int, str, Any, Any]]:
    return [
        (row["version_no"], row["status"], row["effective_from"], row["effective_to"])
        for row in policies.rows(
            select(
                rule_set_version.c.version_no,
                rule_set_version.c.status,
                rule_set_version.c.effective_from,
                rule_set_version.c.effective_to,
            )
            .where(rule_set_version.c.rule_set_id == UUID(rule_set_id))
            .order_by(rule_set_version.c.version_no)
        )
    ]


def requests_for(policies: Policies, version_id: str) -> list[str]:
    return [
        str(row["status"])
        for row in policies.rows(
            select(approval_request.c.status)
            .where(approval_request.c.subject_id == UUID(version_id))
            .order_by(approval_request.c.created_at)
        )
    ]


def test_err_75_a_rule_set_read_at_an_instant_never_takes_effect_in_the_past(
    policies: Policies,
) -> None:
    """The instant form (supervisor ruling R-113 (b)): the platform reads a routing rule set at the
    instant of an act, so a version that supersedes the published one takes effect at its
    publication or later. A first version keeps a free date."""
    past = "2026-09-12T11:59:59Z"  # one second before the frozen clock
    rule_set_id, first = policies.published(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE], effective_from=past
    )
    second = superseding(policies, rule_set_id, first, TWO_STEPS, effective_from=past)

    refused = policies.post(f"{VERSIONS}/{second}/submit", {"comment": "Ready for review"})
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert requests_for(policies, second) == []
    assert [row[:2] for row in versions_of(policies, rule_set_id)] == [
        (1, "PUBLISHED"),
        (2, "TESTED"),
    ]

    # Without an effective date the version takes effect at the instant of its publication.
    redated(policies, second, None)
    approved = policies.approve(str(policies.submit(second)["approval_request_id"]))
    assert approved.status_code == 200, approved.text
    now = policies.clock.now()
    assert versions_of(policies, rule_set_id) == [
        (1, "SUPERSEDED", datetime(2026, 9, 12, 11, 59, 59, tzinfo=UTC), now),
        (2, "PUBLISHED", None, None),
    ]


def test_err_75_the_decision_checks_the_instant_again_and_the_request_stays_pending(
    policies: Policies,
) -> None:
    rule_set_id, first = policies.published(
        "APPROVAL_ROUTING", "APPROVAL_ROUTING", [ROUTE_CON_100K], [LARGE_CASE]
    )
    ahead = policies.clock.now() + timedelta(minutes=1)
    second = superseding(policies, rule_set_id, first, TWO_STEPS, effective_from=ahead.isoformat())
    request_id = str(policies.submit(second)["approval_request_id"])

    policies.clock.advance(timedelta(minutes=2))  # the decision comes after the instant
    refused = policies.approve(request_id)
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    # Nothing of the decision is kept: the request is pending and the published version stands.
    assert requests_for(policies, second) == ["PENDING"]
    assert (
        policies.rows(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(request_id)
            )
        )
        == []
    )
    assert versions_of(policies, rule_set_id) == [
        (1, "PUBLISHED", None, None),
        (2, "SUBMITTED", ahead, None),
    ]

    rejected = reject(policies.app, request_id, policies.marcus, "The effective time has passed")
    assert rejected.status_code == 200, rejected.text
    assert [row[:2] for row in versions_of(policies, rule_set_id)] == [
        (1, "PUBLISHED"),
        (2, "REJECTED"),
    ]


def test_err_75_an_assignment_rule_set_is_dated_after_today_in_every_entity(
    policies: Policies,
) -> None:
    """The date form: the engine evaluates POB_ASSIGNMENT and SSP_ASSIGNMENT rule sets at a
    contract date (ENGINE_SPEC S03-R-02, S05-R-02), so a superseding version needs an effective
    date whose UTC date is later than today in every active entity's time zone."""
    rule_set_id, first = policies.published(
        "POB-ASSIGNMENT", "POB_ASSIGNMENT", [GATEWAY], [GATEWAY_CASE]
    )
    family = {**GATEWAY, "outputs": {"pob_template_code": "GATEWAY-2027"}}
    second = superseding(policies, rule_set_id, first, family)
    submit = f"{VERSIONS}/{second}/submit"

    undated = policies.post(submit, {})
    assert (undated.status_code, slug(undated), fields(undated)) == ERR_75, undated.text
    assert undated.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_DATE_PASSED
    assert undated.json()["detail"] == lifecycle.EFFECTIVE_DATE_PASSED
    redated(policies, second, "2026-09-12T23:59:59Z")  # today, the day of the frozen clock
    today = policies.post(submit, {})
    assert (today.status_code, slug(today), fields(today)) == ERR_75, today.text

    # Kiritimati is fourteen hours ahead of UTC: 13 September has begun there.
    calendar_id = calendar(policies.app, policies.maya)
    entity(
        policies.app,
        policies.maya,
        code="AVM-KI",
        calendar_id=calendar_id,
        time_zone="Pacific/Kiritimati",
    )
    redated(policies, second, "2026-09-13T00:00:00Z")
    begun = policies.post(submit, {})
    assert (begun.status_code, slug(begun), fields(begun)) == ERR_75, begun.text
    assert requests_for(policies, second) == []

    redated(policies, second, "2026-09-14T00:00:00Z")
    approved = policies.approve(str(policies.submit(second)["approval_request_id"]))
    assert approved.status_code == 200, approved.text
    boundary = datetime(2026, 9, 14, tzinfo=UTC)
    assert versions_of(policies, rule_set_id) == [
        (1, "SUPERSEDED", None, boundary),
        (2, "PUBLISHED", boundary, None),
    ]
