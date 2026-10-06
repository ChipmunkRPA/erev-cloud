"""Obligation templates (04 T-REF-22, T-REF-23, T-REF-27, §15.3 API-R-24, API-R-57; ENGINE_SPEC
Table 0.2-A, S03-R-01, S03-R-02; PRD §2.6, ERR-75; SCREENS §11.2; 03 REQ-POL-001, REQ-POL-003,
REQ-POL-007, REQ-POB-005; CTL-031; BUILD_SPEC RFD-10).

Maya holds Revenue Accountant (``config.author``, ``masterdata.maintain``) and authors templates;
Marcus holds Controller (``config.approve``), is enrolled in MFA and approves them (``policies``
fixture). Example cases are written through API-R-57 and run through stage 03 ``build_lines``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    pob_template_version,
)
from erev_api.domain.policies import lifecycle, templates
from sqlalchemy import select
from support.http import HttpResponse
from support.principals import carrying, enrolled
from support.reference import gl_account
from support.rows import insert_role_assignment

if TYPE_CHECKING:
    from conftest import Policies


def context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


TEMPLATES = "/api/v1/pob-templates"
VERSIONS = "/api/v1/pob-template-versions"
CONFIG_TEST_CASES = "/api/v1/config-test-cases"
PRODUCTS = "/api/v1/products"
APPROVALS = "/api/v1/approvals"
PROBLEM_BASE = "https://erev.dev/problems/"
JANUARY = "2026-01-01T00:00:00Z"
OCTOBER = "2026-10-01T00:00:00Z"
# PRD ERR-75: the refusal of a superseding version's effective date, at submission and decision.
ERR_75 = (422, "validation-failed", [("effective_from", "REQ-POL-007")])
OVER_TIME_DAILY = {
    "satisfaction_pattern": "OVER_TIME",
    "over_time_criterion": "OT_A",
    "recognition_method": "TIME_ELAPSED",
    "ratable_convention": "DAILY",
}
# PRD §2.6 TPL-SUB-DAILY: series by day, over time (25-27(a)), time elapsed, daily convention.
TPL_SUB_DAILY = {"distinctness": "series", "series_increment_unit": "day", **OVER_TIME_DAILY}
PLAT_ENT_LINE = {
    "obligation_key": "POB-01",
    "product_code": "AVM-PLAT-ENT",
    "quantity": "1",
    "total_price": "120000.00",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
}
SERIES_DRAFT = {
    "distinctness": "series",
    "series_increment_unit": "day",
    "recognition_method": "TIME_ELAPSED",
    "ratable_convention": "DAILY",
}


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def new_template(policies: Policies, code: str, name: str) -> str:
    created = policies.post(TEMPLATES, {"code": code, "name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def new_version(policies: Policies, template_id: str, **body: Any) -> dict[str, Any]:
    created = policies.post(f"{TEMPLATES}/{template_id}/versions", body)
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def add_case(
    policies: Policies, version_id: str, name: str, facts: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    created = policies.post(
        CONFIG_TEST_CASES,
        {
            "subject_type": "pob_template_version",
            "subject_id": version_id,
            "name": name,
            "input": facts,
            "expected_output": expected,
        },
    )
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def cases_of(policies: Policies, version_id: str) -> list[dict[str, Any]]:
    listed = policies.get(
        CONFIG_TEST_CASES, subject_type="pob_template_version", subject_id=version_id
    )
    assert listed.status_code == 200, listed.text
    return list(listed.json()["items"])


def plat_ent(policies: Policies) -> dict[str, Any]:
    created = policies.post(
        PRODUCTS,
        {
            "code": "AVM-PLAT-ENT",
            "name": "Platform, enterprise tier, 12 months",
            "revenue_category": "SUBSCRIPTION",
            "principal_agent": "PRINCIPAL",
        },
    )
    assert created.status_code == 201, created.text
    result: dict[str, Any] = created.json()
    return result


def events(policies: Policies, version_id: str) -> list[dict[str, Any]]:
    return policies.rows(
        select(
            audit_event.c.action, audit_event.c.before, audit_event.c.after, audit_event.c.detail
        )
        .where(audit_event.c.object_id == UUID(version_id))
        .order_by(audit_event.c.chain_seq)
    )


def with_passing_case(
    policies: Policies, code: str, outputs: dict[str, Any], **version: Any
) -> tuple[str, str]:
    """A template whose version 1 holds ``outputs`` and one passing PLAT-ENT case, TESTED."""
    template_id = new_template(policies, code, f"Template {code}")
    version_id = str(new_version(policies, template_id, **outputs, **version)["id"])
    add_case(
        policies,
        version_id,
        "AVM-PLAT-ENT 12 months",
        {"booking_date": "2026-01-01", "lines": [PLAT_ENT_LINE]},
        {"drafts": [{"obligation_key": "POB-01"}]},
    )
    ran = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text
    return template_id, version_id


def submitted(policies: Policies, version_id: str) -> str:
    sent = policies.post(f"{VERSIONS}/{version_id}/submit", {"comment": "Ready for review"})
    assert (sent.status_code, sent.json()["status"]) == (200, "SUBMITTED"), sent.text
    return str(sent.json()["pending_approval_request_id"])


def test_series_requires_increment_unit(policies: Policies) -> None:
    template_id = new_template(policies, "TPL-SERIES", "Series template")
    refused = policies.post(
        f"{TEMPLATES}/{template_id}/versions", {"distinctness": "series", **OVER_TIME_DAILY}
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("series_increment_unit", "T-REF-23")]
    assert refused.json()["errors"][0]["message"] == templates.SERIES_UNIT_REQUIRED
    assert policies.get(f"{TEMPLATES}/{template_id}/versions").json()["items"] == []

    created = new_version(
        policies, template_id, distinctness="series", series_increment_unit="day", **OVER_TIME_DAILY
    )
    assert (created["distinctness"], created["series_increment_unit"]) == ("series", "day")
    # Clearing the series with the increment still set is refused the other way round.
    shown = policies.get(f"{VERSIONS}/{created['id']}")
    distinct = policies.patch(
        f"{VERSIONS}/{created['id']}", {"distinctness": "distinct"}, etag=shown.headers["ETag"]
    )
    assert (distinct.status_code, fields(distinct)) == (
        422,
        [("series_increment_unit", "T-REF-23")],
    ), distinct.text
    assert distinct.json()["errors"][0]["message"] == templates.SERIES_UNIT_NOT_ALLOWED
    cleared = policies.patch(
        f"{VERSIONS}/{created['id']}",
        {"distinctness": "distinct", "series_increment_unit": None},
        etag=shown.headers["ETag"],
    )
    assert cleared.status_code == 200, cleared.text
    assert (cleared.json()["distinctness"], cleared.json()["series_increment_unit"]) == (
        "distinct",
        None,
    )
    assert cleared.headers["ETag"] == '"r2"'


def test_time_elapsed_requires_convention(policies: Policies) -> None:
    template_id = new_template(policies, "TPL-SUB", "Subscription")
    without = {key: value for key, value in OVER_TIME_DAILY.items() if key != "ratable_convention"}
    refused = policies.post(f"{TEMPLATES}/{template_id}/versions", without)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("ratable_convention", "T-REF-23")]
    assert refused.json()["errors"][0]["message"] == templates.CONVENTION_REQUIRED

    created = policies.post(f"{TEMPLATES}/{template_id}/versions", OVER_TIME_DAILY)
    assert created.status_code == 201, created.text
    body = created.json()
    assert created.headers["Location"] == f"{VERSIONS}/{body['id']}"
    assert created.headers["ETag"] == '"r1"'
    assert (body["template_code"], body["version_no"], body["status"]) == ("TPL-SUB", 1, "DRAFT")
    assert (body["recognition_method"], body["ratable_convention"]) == ("TIME_ELAPSED", "DAILY")
    assert body["test_evidence"] == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "not_run": 0,
        "last_run_at": None,
    }
    output_percent = policies.patch(
        f"{VERSIONS}/{body['id']}", {"recognition_method": "OUTPUT_PERCENT"}, etag='"r1"'
    )
    assert fields(output_percent) == [("ratable_convention", "T-REF-23")], output_percent.text
    assert output_percent.json()["errors"][0]["message"] == templates.CONVENTION_NOT_ALLOWED


def test_point_in_time_method_restricted(policies: Policies) -> None:
    template_id = new_template(policies, "TPL-PROD-PIT", "Products at a point in time")
    refused = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {"satisfaction_pattern": "POINT_IN_TIME", "recognition_method": "COST_TO_COST"},
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("recognition_method", "T-REF-23")]
    assert refused.json()["errors"][0]["message"] == templates.POINT_IN_TIME_METHOD
    criterion = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {
            "satisfaction_pattern": "POINT_IN_TIME",
            "over_time_criterion": "OT_B",
            "recognition_method": "UNITS_DELIVERED",
        },
    )
    assert fields(criterion) == [("over_time_criterion", "T-REF-23")], criterion.text
    over_time = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {"satisfaction_pattern": "OVER_TIME", "recognition_method": "COST_TO_COST"},
    )
    assert fields(over_time) == [("over_time_criterion", "T-REF-23")], over_time.text
    assert over_time.json()["errors"][0]["message"] == templates.CRITERION_REQUIRED

    created = new_version(
        policies,
        template_id,
        satisfaction_pattern="POINT_IN_TIME",
        recognition_method="UNITS_DELIVERED",
    )
    assert (created["satisfaction_pattern"], created["recognition_method"]) == (
        "POINT_IN_TIME",
        "UNITS_DELIVERED",
    )
    assert created["over_time_criterion"] == "NOT_APPLICABLE"


def test_tpl_sub_daily_case_builds_series_obligation(policies: Policies) -> None:
    product = plat_ent(policies)
    template_id = new_template(policies, "TPL-SUB-DAILY", "Subscription, daily ratable")
    version = new_version(policies, template_id, effective_from=JANUARY, **TPL_SUB_DAILY)
    version_id = str(version["id"])
    facts = {"booking_date": "2026-01-01", "lines": [PLAT_ENT_LINE]}
    wrong = add_case(
        policies,
        version_id,
        "Distinct by mistake",
        facts,
        {"drafts": [{"distinctness": "distinct"}]},
    )

    # A failing case records FAIL and leaves the version DRAFT; its drafts are still recorded.
    first = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (first.status_code, first.json()["status"]) == (200, "DRAFT"), first.text
    assert first.json()["test_evidence"]["failed"] == 1
    [failed] = cases_of(policies, version_id)
    assert failed["last_result"] == "FAIL"
    [run] = [
        event
        for event in events(policies, version_id)
        if event["action"] == "pob_template_version.test"
    ]
    assert run["detail"]["cases"][0]["actual"]["drafts"][0]["distinctness"] == "series"

    fixed = policies.patch(
        f"{CONFIG_TEST_CASES}/{wrong['id']}",
        {"name": "AVM-PLAT-ENT 120,000.00 for 2026", "expected_output": {"drafts": [SERIES_DRAFT]}},
        etag=f'"r{failed["row_version"]}"',
    )
    assert fixed.status_code == 200, fixed.text
    second = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (second.status_code, second.json()["status"]) == (200, "TESTED"), second.text
    body = second.json()
    assert len(body["content_sha256"]) == 64
    assert {
        key: body["test_evidence"][key] for key in ("total", "passed", "failed", "not_run")
    } == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "not_run": 0,
    }
    [case] = cases_of(policies, version_id)
    assert (case["last_result"], case["last_run_at"] is not None) == ("PASS", True)

    [tested_event] = [
        event
        for event in events(policies, version_id)
        if event["action"] == "pob_template_version.tested"
    ]
    assert (tested_event["before"]["status"], tested_event["after"]["status"]) == (
        "DRAFT",
        "TESTED",
    )
    assert tested_event["detail"]["passed"] == 1
    [recorded] = tested_event["detail"]["cases"]
    assert recorded["result"] == "PASS"
    assert recorded["actual"]["error"] is None
    assert recorded["actual"]["findings"] == []
    assert recorded["actual"]["drafts"] == [
        {
            "subject_key": "TEST-CASE/POB-01",
            "obligation_key": "POB-01",
            "product_code": "AVM-PLAT-ENT",
            "quantity": "1",
            "stated_price": "120000",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "pricing_date": "2026-01-01",
            "obligation_kind": "STANDARD",
            "distinctness": "series",
            "series_increment_unit": "day",
            "satisfaction_pattern": "OVER_TIME",
            "over_time_criterion": "OT_A",
            "recognition_method": "TIME_ELAPSED",
            "ratable_convention": "DAILY",
            "principal_agent": product["principal_agent"],
            "warranty_type": "NONE",
            "licence_nature": "NOT_APPLICABLE",
            "revenue_category": "SUBSCRIPTION",
            "account_overrides": {},
            "template_code": "TPL-SUB-DAILY",
            "template_version_key": "TPL-SUB-DAILY@v1",
            "pob_template_version": {
                "id": version_id,
                "template_code": "TPL-SUB-DAILY",
                "version_no": 1,
            },
        }
    ]


def test_outputs_cover_req_pol_001(policies: Policies) -> None:
    revenue = gl_account(
        policies.app,
        policies.maya,
        code="4000",
        name="Revenue - products",
        account_type="REVENUE",
        normal_balance="C",
    )
    clearing = gl_account(
        policies.app,
        policies.maya,
        code="2090",
        name="Subledger clearing",
        account_type="LIABILITY",
        normal_balance="C",
    )
    template_id = new_template(policies, "TPL-PROD-UNITS", "Products per unit")
    outputs = {
        "obligation_kind": "STANDARD",
        "distinctness": "distinct",
        "satisfaction_pattern": "POINT_IN_TIME",
        "recognition_method": "UNITS_DELIVERED",
        "account_role_overrides": {"REVENUE": revenue, "BILLING_CLEARING:INVENTORY": clearing},
        "revenue_category": "PRODUCT",
        "disaggregation": {"channel": "direct", "region": "EMEA"},
        "principal_agent": "AGENT",
        "warranty_type": "ASSURANCE",
        "licence_nature": "FUNCTIONAL",
        "sfc_assessment_required": True,
        "start_date_rule": "CONTROL_TRANSFER",
        "end_date_rule": "START_PLUS_TERM",
        "term_months": 24,
        "stratification_label": "Distinct",
        "is_excluded_from_netting_attribution": True,
        "policy_values": {"material_right.ssp_method": "ENTERED_AMOUNT"},
    }
    created = new_version(policies, template_id, **outputs)
    assert {name: created[name] for name in outputs} == outputs
    shown = policies.get(f"{VERSIONS}/{created['id']}")
    assert shown.status_code == 200, shown.text
    assert {name: shown.json()[name] for name in outputs} == outputs
    assert shown.headers["ETag"] == '"r1"'
    [row] = policies.rows(
        select(
            pob_template_version.c.account_role_overrides, pob_template_version.c.policy_values
        ).where(pob_template_version.c.id == UUID(created["id"]))
    )
    assert row["account_role_overrides"] == {
        "REVENUE": revenue,
        "BILLING_CLEARING:INVENTORY": clearing,
    }
    assert row["policy_values"] == {"material_right.ssp_method": "ENTERED_AMOUNT"}
    # An unchanged PATCH writes nothing and keeps the row version.
    unchanged = policies.patch(
        f"{VERSIONS}/{created['id']}", {"principal_agent": "AGENT"}, etag='"r1"'
    )
    assert (unchanged.status_code, unchanged.headers["ETag"]) == (200, '"r1"'), unchanged.text
    [listed] = policies.get(TEMPLATES).json()["items"]
    assert listed["current_version"] is None
    assert listed["latest_version"] == {
        "id": created["id"],
        "version_no": 1,
        "status": "DRAFT",
        "effective_from": None,
        "published_at": None,
        "rule_count": None,
        "lint_status": None,
    }


def test_publish_needs_other_approver(policies: Policies) -> None:
    # Maya also holds Controller and verifies MFA, so only separation of duties refuses her.
    maya = policies.maya.member
    with tenant_session(
        DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    ) as session:
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
    plat_ent(policies)
    _, version_id = with_passing_case(
        policies, "TPL-SUB-DAILY", TPL_SUB_DAILY, effective_from=JANUARY
    )
    request_id = submitted(policies, version_id)
    request = policies.get(f"{APPROVALS}/{request_id}", verified).json()
    assert (request["subject"]["type"], request["can_decide"]) == ("POB_TEMPLATE_VERSION", False)
    assert request["summary"] == "Publish version 1 of obligation template TPL-SUB-DAILY"

    refused = policies.approve(request_id, verified)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    # Maya prepared the request too, so the engine's preparer check answers first (DG-KRN-APR-02).
    assert refused.json()["detail"] == "You prepared this item, so another user must approve it."
    assert (
        policies.rows(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(request_id)
            )
        )
        == []
    )
    assert policies.get(f"{VERSIONS}/{version_id}").json()["status"] == "SUBMITTED"

    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    published = policies.get(f"{VERSIONS}/{version_id}").json()
    assert (published["status"], published["approval_request_id"]) == ("PUBLISHED", request_id)
    assert published["published_by"] == str(policies.marcus.member.user_id)
    assert published["pending_approval_request_id"] is None
    [listed] = policies.get(TEMPLATES).json()["items"]
    assert (listed["current_version"]["id"], listed["current_version"]["status"]) == (
        version_id,
        "PUBLISHED",
    )


@pytest.mark.control("CTL-031")
def test_ctl_031_unpublished_template_not_resolvable(policies: Policies) -> None:
    plat_ent(policies)
    template_id, version_id = with_passing_case(
        policies, "TPL-SUB-DAILY", TPL_SUB_DAILY, effective_from=JANUARY
    )

    def resolved(at: date) -> Any:
        with tenant_session(context(policies.tenant_id), read_only=True) as session:
            return templates.resolve_template_version(
                session, "TPL-SUB-DAILY", at=at, known_at=policies.clock.now()
            )

    # A TESTED version resolves for no booking line, and no product may default to it.
    assert resolved(date(2026, 3, 1)) is None
    with tenant_session(context(policies.tenant_id), read_only=True) as session:
        assert templates.template_inputs(session, known_at=policies.clock.now()) == ()
    body = {"code": "AVM-PLAT-UK", "name": "Platform (UK)", "default_pob_template_id": template_id}
    refused = policies.post(PRODUCTS, body)
    assert (refused.status_code, fields(refused)) == (
        422,
        [("default_pob_template_id", "T-REF-20")],
    ), refused.text

    request_id = submitted(policies, version_id)
    assert resolved(date(2026, 3, 1)) is None  # SUBMITTED
    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    found = resolved(date(2026, 3, 1))
    assert found is not None
    assert (
        found.version_key,
        found.version_no,
        found.effective_from,
        found.effective_to,
        found.distinctness,
        found.series_increment_unit,
        found.ratable_convention,
    ) == ("TPL-SUB-DAILY@v1", 1, date(2026, 1, 1), None, "series", "day", "DAILY")
    assert resolved(date(2025, 12, 31)) is None
    accepted = policies.post(PRODUCTS, body)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["default_pob_template_id"] == template_id


def test_new_version_supersedes_and_convention_reaches_drafts(policies: Policies) -> None:
    plat_ent(policies)
    template_id, first_id = with_passing_case(
        policies, "TPL-SUB-DAILY", TPL_SUB_DAILY, effective_from=JANUARY
    )
    approved = policies.approve(submitted(policies, first_id))
    assert approved.status_code == 200, approved.text

    # Version 2 copies version 1 and its case, effective 1 October, with the monthly-even
    # convention: a superseding version is dated after today, 12 September (PRD ERR-75).
    created = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {
            "source_version_id": first_id,
            "effective_from": OCTOBER,
            "ratable_convention": "MONTHLY_EVEN",
        },
    )
    assert created.status_code == 201, created.text
    second = created.json()
    second_id = str(second["id"])
    assert (
        second["version_no"],
        second["status"],
        second["supersedes_version_id"],
        second["distinctness"],
        second["series_increment_unit"],
        second["ratable_convention"],
    ) == (2, "DRAFT", first_id, "series", "day", "MONTHLY_EVEN")
    [copied] = cases_of(policies, second_id)
    assert (copied["name"], copied["last_result"]) == ("AVM-PLAT-ENT 12 months", None)
    blocked = policies.post(f"{TEMPLATES}/{template_id}/versions", {"source_version_id": first_id})
    assert (blocked.status_code, slug(blocked)) == (409, "invalid-transition"), blocked.text
    assert fields(blocked) == [(None, "SM-04")]

    ran = policies.post(f"{VERSIONS}/{second_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text
    [tested_event] = [
        event
        for event in events(policies, second_id)
        if event["action"] == "pob_template_version.tested"
    ]
    [draft] = tested_event["detail"]["cases"][0]["actual"]["drafts"]
    # The template's convention is the level P value of POL-090 for its obligations.
    assert (draft["ratable_convention"], draft["template_version_key"]) == (
        "MONTHLY_EVEN",
        "TPL-SUB-DAILY@v2",
    )
    approved = policies.approve(submitted(policies, second_id))
    assert approved.status_code == 200, approved.text

    first = policies.get(f"{VERSIONS}/{first_id}").json()
    assert (first["status"], first["effective_to"]) == ("SUPERSEDED", OCTOBER)
    assert policies.get(f"{VERSIONS}/{second_id}").json()["status"] == "PUBLISHED"
    with tenant_session(context(policies.tenant_id), read_only=True) as session:
        now = policies.clock.now()
        march = templates.resolve_template_version(
            session, "TPL-SUB-DAILY", at=date(2026, 3, 1), known_at=now
        )
        november = templates.resolve_template_version(
            session, "TPL-SUB-DAILY", at=date(2026, 11, 1), known_at=now
        )
        inputs = templates.template_inputs(session, known_at=now)
    assert march is not None and november is not None
    assert (march.version_key, march.effective_to, march.ratable_convention) == (
        "TPL-SUB-DAILY@v1",
        date(2026, 10, 1),
        "DAILY",
    )
    assert (november.version_key, november.effective_from, november.ratable_convention) == (
        "TPL-SUB-DAILY@v2",
        date(2026, 10, 1),
        "MONTHLY_EVEN",
    )
    assert [item.version_key for item in inputs] == ["TPL-SUB-DAILY@v1", "TPL-SUB-DAILY@v2"]
    [listed] = policies.get(TEMPLATES, status="PUBLISHED").json()["items"]
    assert (listed["current_version"]["version_no"], listed["latest_version"]["version_no"]) == (
        2,
        2,
    )


def superseding(policies: Policies, template_id: str, first_id: str, **body: Any) -> str:
    """Version 2 of the template: a copy of the published version and its case, TESTED."""
    created = policies.post(
        f"{TEMPLATES}/{template_id}/versions", {"source_version_id": first_id, **body}
    )
    assert created.status_code == 201, created.text
    second_id = str(created.json()["id"])
    ran = policies.post(f"{VERSIONS}/{second_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text
    return second_id


def redated(policies: Policies, version_id: str, effective_from: str | None) -> None:
    """Move the effective date of a TESTED version; the date is content, so the case runs again."""
    current = policies.get(f"{VERSIONS}/{version_id}").json()
    moved = policies.patch(
        f"{VERSIONS}/{version_id}",
        {"effective_from": effective_from},
        etag=f'"r{current["row_version"]}"',
    )
    assert moved.status_code == 200, moved.text
    ran = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text


def versions_of(policies: Policies, template_id: str) -> list[tuple[int, str, Any, Any]]:
    return [
        (row["version_no"], row["status"], row["effective_from"], row["effective_to"])
        for row in policies.rows(
            select(
                pob_template_version.c.version_no,
                pob_template_version.c.status,
                pob_template_version.c.effective_from,
                pob_template_version.c.effective_to,
            )
            .where(pob_template_version.c.pob_template_id == UUID(template_id))
            .order_by(pob_template_version.c.version_no)
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


def test_err_75_a_superseding_template_version_is_dated_after_today(policies: Policies) -> None:
    """The date form (supervisor ruling R-113 (b)): the engine chooses a template version by the
    contract's inception or the line's pricing date (ENGINE_SPEC S03-R-02), so a version that
    supersedes the published one takes effect on a later day than today and never meets a contract
    dated up to today. A first version keeps a free date (January here)."""
    plat_ent(policies)
    template_id, first_id = with_passing_case(
        policies, "TPL-SUB-DAILY", TPL_SUB_DAILY, effective_from=JANUARY
    )
    approved = policies.approve(submitted(policies, first_id))
    assert approved.status_code == 200, approved.text
    second_id = superseding(policies, template_id, first_id, ratable_convention="MONTHLY_EVEN")
    submit = f"{VERSIONS}/{second_id}/submit"

    # No date, 1 July (the past) and 12 September (the day of the frozen clock) are refused.
    for effective_from in (None, "2026-07-01T00:00:00Z", "2026-09-12T23:59:59Z"):
        if effective_from is not None:
            redated(policies, second_id, effective_from)
        refused = policies.post(submit, {"comment": "Ready for review"})
        assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, effective_from
        assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_DATE_PASSED
        assert refused.json()["detail"] == lifecycle.EFFECTIVE_DATE_PASSED
    assert requests_for(policies, second_id) == []
    january = datetime(2026, 1, 1, tzinfo=UTC)
    assert [row[:2] for row in versions_of(policies, template_id)] == [
        (1, "PUBLISHED"),
        (2, "TESTED"),
    ]

    redated(policies, second_id, "2026-09-13T00:00:00Z")  # tomorrow
    approved = policies.approve(submitted(policies, second_id))
    assert approved.status_code == 200, approved.text
    tomorrow = datetime(2026, 9, 13, tzinfo=UTC)
    assert versions_of(policies, template_id) == [
        (1, "SUPERSEDED", january, tomorrow),
        (2, "PUBLISHED", tomorrow, None),
    ]
    with tenant_session(context(policies.tenant_id), read_only=True) as session:
        chosen = [
            templates.resolve_template_version(
                session, "TPL-SUB-DAILY", at=at, known_at=policies.clock.now()
            )
            for at in (date(2026, 9, 12), date(2026, 9, 13))
        ]
    # A contract dated today keeps version 1; version 2 answers from tomorrow.
    assert [None if found is None else found.version_key for found in chosen] == [
        "TPL-SUB-DAILY@v1",
        "TPL-SUB-DAILY@v2",
    ]


@pytest.fixture
def before_midnight(clock: FrozenClock) -> None:
    """The frozen clock at 23:58:30 UTC on 12 September, set before anybody signs in."""
    clock.set(datetime(2026, 9, 12, 23, 58, 30, tzinfo=UTC))


def test_err_75_the_decision_checks_the_date_again_and_the_request_stays_pending(
    before_midnight: None, policies: Policies
) -> None:
    plat_ent(policies)
    template_id, first_id = with_passing_case(
        policies, "TPL-SUB-DAILY", TPL_SUB_DAILY, effective_from=JANUARY
    )
    approved = policies.approve(submitted(policies, first_id))
    assert approved.status_code == 200, approved.text
    second_id = superseding(
        policies,
        template_id,
        first_id,
        ratable_convention="MONTHLY_EVEN",
        effective_from="2026-09-13T00:00:00Z",
    )
    request_id = submitted(policies, second_id)  # 12 September: tomorrow is later than today

    policies.clock.advance(timedelta(minutes=2))  # 13 September has begun
    refused = policies.approve(request_id)
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_DATE_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_DATE_PASSED
    # Nothing of the decision is kept: the request is pending and version 1 stays published.
    assert requests_for(policies, second_id) == ["PENDING"]
    decisions = policies.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert decisions == []
    assert [row[:2] for row in versions_of(policies, template_id)] == [
        (1, "PUBLISHED"),
        (2, "SUBMITTED"),
    ]


def test_version_and_case_findings(policies: Policies) -> None:
    template_id = new_template(policies, "TPL-X", "Template X")
    duplicate = policies.post(TEMPLATES, {"code": "TPL-X", "name": " "})
    assert (duplicate.status_code, fields(duplicate)) == (
        422,
        [("code", "T-REF-22"), ("name", "T-REF-22")],
    ), duplicate.text
    assert (
        duplicate.json()["errors"][0]["message"]
        == "Obligation template code TPL-X is already used."
    )
    unknown = policies.post(f"{TEMPLATES}/{uuid4()}/versions", OVER_TIME_DAILY)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    account = gl_account(
        policies.app,
        policies.maya,
        code="2090",
        name="Subledger clearing",
        account_type="LIABILITY",
        normal_balance="C",
    )
    findings = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {
            "obligation_kind": None,
            "satisfaction_pattern": "POINT_IN_TIME",
            "recognition_method": "TIME_ELAPSED",
            "series_increment_unit": "unit",
            "over_time_criterion": "OT_B",
            "end_date_rule": "START_PLUS_TERM",
            "revenue_category": "not a category!",
            "disaggregation": {"channel": " "},
            "policy_values": {"rounding.posting_mode": "HALF_UP"},
            "account_role_overrides": {
                "BILLING_CLEARING": account,
                "RETAINED_EARNINGS": account,
                "REVENUE": str(uuid4()),
                "REVENUE:BILLING": account,
            },
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("obligation_kind", "T-REF-23"),
        ("series_increment_unit", "T-REF-23"),
        ("over_time_criterion", "T-REF-23"),
        ("recognition_method", "T-REF-23"),
        ("ratable_convention", "T-REF-23"),
        ("term_months", "T-REF-23"),
        ("revenue_category", "T-REF-23"),
        ("disaggregation.channel", "T-REF-23"),
        ("policy_values.rounding.posting_mode", "POLICY_LEVEL_NOT_ALLOWED"),
        ("account_role_overrides.BILLING_CLEARING", "T-REF-23"),
        ("account_role_overrides.RETAINED_EARNINGS", "T-REF-23"),
        ("account_role_overrides.REVENUE", "T-REF-23"),
        ("account_role_overrides.REVENUE:BILLING", "T-REF-23"),
    ]
    messages = [error["message"] for error in findings.json()["errors"]]
    assert messages[9:] == [
        templates.OVERRIDE_KEY,
        templates.OVERRIDE_RESERVED.format(label="Retained earnings (reserved)"),
        templates.OVERRIDE_ACCOUNT,
        templates.OVERRIDE_KEY,
    ]

    version_id = str(new_version(policies, template_id, **OVER_TIME_DAILY)["id"])
    no_cases = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (no_cases.status_code, fields(no_cases)) == (422, [("test_cases", "REQ-POL-003")]), (
        no_cases.text
    )
    untested = policies.post(f"{VERSIONS}/{version_id}/submit", {})
    assert (untested.status_code, slug(untested)) == (409, "invalid-transition"), untested.text
    shape = policies.post(
        CONFIG_TEST_CASES,
        {
            "subject_type": "pob_template_version",
            "subject_id": version_id,
            "name": "Malformed",
            "input": {
                "booking_date": "01/01/2026",
                "extra": 1,
                "lines": [
                    {"product_code": " ", "total_price": 120000, "quantity": "0", "colour": "red"}
                ],
            },
            "expected_output": {"drafts": {}},
        },
    )
    assert (shape.status_code, fields(shape)) == (
        422,
        [
            ("input.extra", "T-REF-27"),
            ("input.booking_date", "T-REF-27"),
            ("input.lines[0].colour", "T-REF-27"),
            ("input.lines[0].product_code", "T-REF-27"),
            ("input.lines[0].total_price", "T-REF-27"),
            ("input.lines[0].quantity", "T-REF-27"),
            ("expected_output.drafts", "T-REF-27"),
        ],
    ), shape.text

    # An unknown product yields PRODUCT_UNMAPPED, which the case expects.
    add_case(
        policies,
        version_id,
        "Unknown product",
        {
            "booking_date": "2026-02-01",
            "currency": "EUR",
            "lines": [{"product_code": "AVM-NONE", "total_price": "100.00"}],
        },
        {"drafts": [], "findings": ["PRODUCT_UNMAPPED"]},
    )
    ran = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text
    [tested_event] = [
        event
        for event in events(policies, version_id)
        if event["action"] == "pob_template_version.tested"
    ]
    assert tested_event["detail"]["cases"][0]["actual"]["findings"] == [
        {
            "code": "PRODUCT_UNMAPPED",
            "severity": "ERROR",
            "subject_key": "TEST-CASE/POB-01",
            "detail": {"obligation_key": "POB-01", "product_code": "AVM-NONE"},
        }
    ]

    submitted(policies, version_id)
    etag = policies.get(f"{VERSIONS}/{version_id}").headers["ETag"]
    frozen = policies.patch(f"{VERSIONS}/{version_id}", {"principal_agent": "AGENT"}, etag=etag)
    assert (frozen.status_code, slug(frozen), fields(frozen)) == (
        409,
        "configuration-frozen",
        [("status", "DB-04")],
    ), frozen.text
    late_case = policies.post(
        CONFIG_TEST_CASES,
        {
            "subject_type": "pob_template_version",
            "subject_id": version_id,
            "name": "Too late",
            "input": {"booking_date": "2026-02-01", "lines": [PLAT_ENT_LINE]},
            "expected_output": {"drafts": []},
        },
    )
    assert (late_case.status_code, slug(late_case)) == (409, "configuration-frozen"), late_case.text


# --- a level P value no computation reads (item PRODUCT-POLICY-VALUE-NOT-READ-1; PRD ERR-103) --

TIER_METHOD = "usage.tier_minimum_method"  # POL-240: levels P and C; default DERIVED
BENEFIT_PERIOD = "upfront_fee.recognition_period"  # POL-029: level P alone
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021: levels T, E and P
NOT_READ = "POLICY_PRODUCT_LEVEL_NOT_READ"
# PRD ERR-103, the two sentences as ruled, each naming its parameter by the code;
# ``tests/unit/policies/test_level_p_not_read.py`` holds the product's constants to them.
DEFAULT_APPLIES = (
    "This release reads {key} from no product or template. The framework's default applies to "
    "every contract: leave it out, or state the default."
)
REGISTRY_APPLIES = (
    "This release reads {key} from no product or template. The entity's or the workspace's "
    "value applies where the framework does not fix it: set it by a policy version."
)


def answered(response: HttpResponse) -> list[tuple[str | None, str | None, str]]:
    """Field, rule id and sentence of each error of a refusal."""
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def not_read(key: str) -> tuple[str, str, str]:
    """The error of PRD ERR-103 for parameter ``key``: its field, the rule id and the sentence of
    the parameter, which names it."""
    sentence = REGISTRY_APPLIES if key == SHIPPING else DEFAULT_APPLIES
    return (f"policy_values.{key}", NOT_READ, sentence.format(key=key))


def test_err_103_a_template_version_states_no_level_p_value_that_no_computation_reads(
    policies: Policies,
) -> None:
    """Item PRODUCT-POLICY-VALUE-NOT-READ-1 (register index 309; 04 T-REF-23 rev 1.323; POLICIES
    §0.5 rule 1 rev 1.125; PRD ERR-103), the fourth door: the outputs of an obligation template
    version, at its creation and at the change of a draft. A value of POL-240 or POL-029 other
    than the framework's default, and every value of POL-021, is refused by name with what
    applies instead — the engine reads the three for a contract and a template's value is given
    to it for an obligation. Nothing of a refused request is stored, so a version never holds
    such a value when its example cases run: they run on the stored outputs."""
    template_id = new_template(policies, "TPL-USAGE", "Usage and overage")
    of_the_template = select(pob_template_version.c.id).where(
        pob_template_version.c.pob_template_id == UUID(template_id)
    )

    refused = policies.post(
        f"{TEMPLATES}/{template_id}/versions",
        {
            **OVER_TIME_DAILY,
            "policy_values": {
                TIER_METHOD: "ESTIMATE_MEASUREMENT_PERIOD_TP",
                BENEFIT_PERIOD: "CONTRACT_TERM",
                SHIPPING: "TRUE",
            },
        },
    )
    assert refused.status_code == 422, refused.text  # before the rule: 201, the values stored
    assert slug(refused) == "validation-failed"
    assert answered(refused) == [
        not_read(SHIPPING),
        not_read(BENEFIT_PERIOD),
        not_read(TIER_METHOD),
    ]
    assert refused.json()["errors"][0]["message"] == (
        "This release reads pob.shipping_as_fulfilment from no product or template. The entity's "
        "or the workspace's value applies where the framework does not fix it: set it by a "
        "policy version."
    )
    assert policies.rows(of_the_template) == []

    # The framework's default of the two is stated and stored.
    stated = {TIER_METHOD: "DERIVED", BENEFIT_PERIOD: "EXPECTED_BENEFIT_PERIOD"}
    version = new_version(policies, template_id, **OVER_TIME_DAILY, policy_values=stated)
    version_id = str(version["id"])
    assert version["policy_values"] == stated
    etag = policies.get(f"{VERSIONS}/{version_id}").headers["ETag"]

    # The change of the draft: the same refusal, and the draft keeps what it held.
    for values, expected in (
        ({**stated, TIER_METHOD: "ESTIMATE_MEASUREMENT_PERIOD_TP"}, [not_read(TIER_METHOD)]),
        ({BENEFIT_PERIOD: "CONTRACT_TERM"}, [not_read(BENEFIT_PERIOD)]),
        ({**stated, SHIPPING: "FALSE"}, [not_read(SHIPPING)]),
    ):
        changed = policies.patch(f"{VERSIONS}/{version_id}", {"policy_values": values}, etag=etag)
        assert (changed.status_code, slug(changed)) == (422, "validation-failed"), changed.text
        assert answered(changed) == expected
    current = policies.get(f"{VERSIONS}/{version_id}")
    assert (current.json()["policy_values"], current.headers["ETag"]) == (stated, etag)
    assert [str(row["id"]) for row in policies.rows(of_the_template)] == [version_id]

    # The example cases run on what is stored: the outputs the door has passed.
    plat_ent(policies)
    add_case(
        policies,
        version_id,
        "AVM-PLAT-ENT 12 months",
        {"booking_date": "2026-01-01", "lines": [PLAT_ENT_LINE]},
        {"drafts": [{"obligation_key": "POB-01"}]},
    )
    ran = policies.post(f"{VERSIONS}/{version_id}/test")
    assert (ran.status_code, ran.json()["status"]) == (200, "TESTED"), ran.text
    assert ran.json()["policy_values"] == stated

    # The road takes a change the check admits: one default is dropped, the other kept.
    kept = policies.patch(
        f"{VERSIONS}/{version_id}",
        {"policy_values": {TIER_METHOD: "DERIVED"}},
        etag=ran.headers["ETag"],
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["policy_values"] == {TIER_METHOD: "DERIVED"}
