"""Rule evaluation, lint and publication checks (04 T-REF-25, T-REF-26, §15.3 API-R-25, §16.5
publish note; PRD SM-04; REQ-POL-002; BUILD_SPEC RFD-5).

Facts carry the ``erev_engine.rules.FIELDS`` names, so the acceptance's ``product`` and ``region``
are ``product.code`` and ``contract.region`` (L1-4-Q-6).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import rule_set_version
from erev_api.enums import ApprovalRequestStatus
from sqlalchemy import select, update
from support.http import HttpResponse
from support.rows import insert_approval_request

if TYPE_CHECKING:
    from conftest import Policies

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
PROBLEM_BASE = "https://erev.dev/problems/"
GW: dict[str, Any] = {
    "rule_key": "GW",
    "priority": 10,
    "conditions": [{"field": "product.code", "op": "eq", "value": "AVM-GW"}],
    "outputs": {"pob_template_code": "GATEWAY"},
}
GW_EU: dict[str, Any] = {
    "rule_key": "GW-EU",
    "priority": 10,
    "conditions": [
        {"field": "product.code", "op": "eq", "value": "AVM-GW"},
        {"field": "contract.region", "op": "eq", "value": "EU"},
    ],
    "outputs": {"pob_template_code": "GATEWAY-EU"},
}
GW_OR_HW: dict[str, Any] = {
    "rule_key": "GW-OR-HW",
    "priority": 10,
    "conditions": [{"field": "product.code", "op": "in", "value": ["AVM-GW", "AVM-HW"]}],
    "outputs": {"pob_template_code": "HARDWARE"},
}
SW: dict[str, Any] = {
    "rule_key": "SW",
    "priority": 10,
    "conditions": [{"field": "product.code", "op": "eq", "value": "AVM-SW"}],
    "outputs": {"pob_template_code": "SOFTWARE"},
}
FAMILY: dict[str, Any] = {
    "rule_key": "GATEWAY-FAMILY",
    "priority": 20,
    "conditions": [{"field": "product.product_family", "op": "eq", "value": "GATEWAY"}],
    "outputs": {"pob_template_code": "GATEWAY-FAMILY"},
}


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def evaluate(
    policies: Policies, rule_set_id: str, facts: dict[str, Any], **extra: Any
) -> HttpResponse:
    return policies.post(f"{RULE_SETS}/{rule_set_id}/evaluate", {"facts": facts, **extra})


def test_publish_rejects_equal_specificity_and_priority(policies: Policies) -> None:
    _, version_id = policies.draft(
        "POB-RULES",
        "POB_ASSIGNMENT",
        [GW, GW_OR_HW, SW],
        [("Software", {"product.code": "AVM-SW"}, {"rule_key": "SW"})],
    )
    linted = policies.post(f"{VERSIONS}/{version_id}/lint")
    assert linted.status_code == 200, linted.text
    lint = linted.json()["lint_result"]
    assert lint["status"] == "FAIL"
    assert [(finding["rule_id"], finding["rule_keys"]) for finding in lint["findings"]] == [
        ("REQ-POL-002", ["GW", "GW-OR-HW"])
    ]
    [item] = policies.get(RULE_SETS, kind="POB_ASSIGNMENT").json()["items"]
    assert item["latest_version"]["lint_status"] == "FAIL"

    # The example case passes, yet the lint keeps the version in DRAFT (T-REF-25 lint_result).
    tested = policies.post(f"{VERSIONS}/{version_id}/test").json()
    assert (
        tested["status"],
        tested["test_evidence"]["passed"],
        tested["lint_result"]["status"],
    ) == (
        "DRAFT",
        1,
        "FAIL",
    )

    # A version left APPROVED is linted again when it is published (04 §16.5 publish note).
    context = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    where = rule_set_version.c.id == UUID(version_id)
    with tenant_session(context) as session:
        session.execute(
            update(rule_set_version)
            .where(where)
            .values(status="TESTED", content_sha256=secrets.token_hex(32))
        )
        session.execute(update(rule_set_version).where(where).values(status="SUBMITTED"))
        request_id = insert_approval_request(
            session,
            tenant_id=policies.tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            subject_type="RULE_SET_VERSION",
            subject_id=UUID(version_id),
        )
        session.execute(
            update(rule_set_version)
            .where(where)
            .values(status="APPROVED", approval_request_id=request_id)
        )
    published = policies.post(f"{VERSIONS}/{version_id}/publish")
    assert (published.status_code, slug(published)) == (422, "validation-failed"), published.text
    assert fields(published) == [("rules", "REQ-POL-002")]
    [row] = policies.rows(select(rule_set_version.c.status).where(where))
    assert row["status"] == "APPROVED"


def test_lint_accepts_rules_that_cannot_match_the_same_item(policies: Policies) -> None:
    contract = {"field": "subject.type", "op": "eq", "value": "CONTRACT_ACTIVATION"}
    modification = {"field": "subject.type", "op": "eq", "value": "MODIFICATION"}
    contract_steps = {
        "steps": [
            {"name": "Contract approval", "permission": "contract.approve", "min_approvers": 1}
        ]
    }
    modification_steps = {
        "steps": [
            {
                "name": "Modification approval",
                "permission": "modification.approve",
                "min_approvers": 1,
            }
        ]
    }
    rules = [
        {
            "rule_key": "CON-STD",
            "priority": 10,
            "conditions": [contract],
            "outputs": contract_steps,
        },
        {
            "rule_key": "MOD-STD",
            "priority": 10,
            "conditions": [modification],
            "outputs": modification_steps,
        },
        {
            "rule_key": "CON-LARGE",
            "priority": 20,
            "conditions": [
                contract,
                {"field": "amount.functional", "op": "gte", "value": "100000.00"},
            ],
            "outputs": contract_steps,
        },
        {
            "rule_key": "CON-SMALL",
            "priority": 20,
            "conditions": [
                contract,
                {"field": "amount.functional", "op": "range", "value": [None, "100000.00"]},
            ],
            "outputs": contract_steps,
        },
        {
            "rule_key": "MOD-CATCH-UP",
            "priority": 20,
            "conditions": [modification, {"field": "flags", "op": "eq", "value": "CATCH_UP"}],
            "outputs": modification_steps,
        },
        {
            "rule_key": "MOD-LARGE",
            "priority": 20,
            "conditions": [modification, {"field": "flags", "op": "eq", "value": "LARGE"}],
            "outputs": modification_steps,
        },
    ]
    _, version_id = policies.draft("APPROVAL_ROUTING", "APPROVAL_ROUTING", rules, [])
    linted = policies.post(f"{VERSIONS}/{version_id}/lint")
    assert linted.status_code == 200, linted.text
    # Different subject types and disjoint amount ranges never tie; one item can carry both flags.
    assert [finding["rule_keys"] for finding in linted.json()["lint_result"]["findings"]] == [
        ["MOD-CATCH-UP", "MOD-LARGE"]
    ]


def test_most_specific_rule_wins_then_priority(policies: Policies) -> None:
    rule_set_id, version_id = policies.draft(
        "POB-ASSIGNMENT", "POB_ASSIGNMENT", [GW, GW_EU, FAMILY], []
    )
    specific = evaluate(
        policies,
        rule_set_id,
        {"product.code": "AVM-GW", "contract.region": "EU"},
        version_id=version_id,
    )
    assert specific.status_code == 200, specific.text
    body = specific.json()
    assert (body["matched"], body["rule_key"], body["specificity"], body["priority"]) == (
        True,
        "GW-EU",
        2,
        10,
    )
    assert (body["outputs"], body["rule_set_version_id"]) == (
        {"pob_template_code": "GATEWAY-EU"},
        version_id,
    )

    tie = evaluate(
        policies,
        rule_set_id,
        {"product.code": "AVM-GW", "product.product_family": "GATEWAY"},
        version_id=version_id,
    )
    assert (tie.json()["rule_key"], tie.json()["specificity"], tie.json()["priority"]) == (
        "GATEWAY-FAMILY",
        1,
        20,
    )
    plain = evaluate(policies, rule_set_id, {"product.code": "AVM-GW"}, version_id=version_id)
    assert plain.json()["rule_key"] == "GW"
    unknown = evaluate(policies, rule_set_id, {"region": "EU"}, version_id=version_id)
    assert (unknown.status_code, fields(unknown)) == (422, [("facts.region", "T-REF-26")])


def test_no_matching_rule(policies: Policies) -> None:
    rule_set_id, version_id = policies.published(
        "POB-ASSIGNMENT",
        "POB_ASSIGNMENT",
        [GW],
        [("Gateway", {"product.code": "AVM-GW"}, {"rule_key": "GW"})],
    )
    unknown = evaluate(policies, rule_set_id, {"product.code": "AVM-XX"})
    assert unknown.status_code == 200, unknown.text
    assert unknown.json() == {
        "matched": False,
        "rule_key": None,
        "rule_id": None,
        "rule_set_version_id": version_id,
        "specificity": None,
        "priority": None,
        "outputs": None,
    }
    known = evaluate(policies, rule_set_id, {"product.code": "AVM-GW"})
    assert (known.json()["matched"], known.json()["rule_key"]) == (True, "GW")

    # Before a version is published nothing is in force, so nothing matches.
    unpublished = policies.rule_set("SSP-ASSIGNMENT", "SSP_ASSIGNMENT")
    empty = evaluate(policies, unpublished, {"product.code": "AVM-GW"})
    assert (empty.json()["matched"], empty.json()["rule_set_version_id"]) == (False, None)
