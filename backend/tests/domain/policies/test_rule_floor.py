"""Approval rules cannot lower a subject's own approval (04 T-REF-26 and §16.10 rev 1.104
"Auto-approval and the routing floor"; dev-guide DG-KRN-APR-08; 03 REQ-PLT-013, REQ-PLT-016;
controls CTL-005, CTL-031; supervisor ruling R-26 on the security review's finding SN-9).

The finding: an ``AUTO_APPROVAL`` rule with ``conditions: []`` was accepted by authoring, lint and
tests; once ONE Controller had approved it, every later submission of its author approved itself
— including a routing rule set that sent ``PERIOD_REOPEN`` to a single ``judgement.review``
holder. Each limit is witnessed twice: refused by name where a rule is authored (the rule upsert
and the publication), and without effect at submission for a rule that reached the table another
way (``support.rows.publish_rule_set`` writes a PUBLISHED version directly, the state the exploit
left behind). Maya (Revenue Accountant) authors; Marcus (Controller, MFA) approves. Beside every
refusal stands the path that still works: the legitimate approver, the rule that adds a step, the
system-originated item a rule may approve (``test_auto_approval.py``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.approvals import routing
from erev_api.auth.principal import system_principal
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    role,
    rule,
    rule_set,
    rule_set_version,
)
from erev_api.domain.policies import rule_sets
from erev_api.enums import ApprovalSubjectType, PrincipalKind, RuleSetKind
from sqlalchemy import select
from support.rows import publish_rule_set
from support.subjects import ProbeSubjects, install

if TYPE_CHECKING:
    from conftest import Policies

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
PROBLEM_BASE = "https://erev.dev/problems/"
_S = ApprovalSubjectType
AUTO = {"auto_approve": True}
REOPEN_TO_ONE_REVIEWER = {
    "steps": [{"name": "Any reviewer", "permission": "judgement.review", "min_approvers": 1}]
}
CONFIG_STEP = {"name": "Configuration review", "permission": "config.approve", "min_approvers": 1}


def _condition(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def _subject(*values: str) -> dict[str, Any]:
    if len(values) == 1:
        return _condition("subject.type", "eq", values[0])
    return _condition("subject.type", "in", list(values))


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _draft(policies: Policies, code: str, kind: str) -> str:
    """A rule set of ``kind`` with its DRAFT version 1; the version id."""
    return policies.version(policies.rule_set(code, kind))


def _refused(
    policies: Policies, version_id: str, rule_key: str, conditions: list[Any], outputs: Any
) -> list[tuple[str | None, str | None, str]]:
    """The findings of a refused rule upsert: 422 ``validation-failed``, nothing stored."""
    response = policies.post(
        f"{VERSIONS}/{version_id}/rules",
        {"rule_key": rule_key, "priority": 0, "conditions": conditions, "outputs": outputs},
    )
    assert response.status_code == 422, response.text
    assert str(response.json()["type"]).removeprefix(PROBLEM_BASE) == "validation-failed"
    stored = policies.rows(
        select(rule.c.id).where(
            rule.c.rule_set_version_id == UUID(version_id), rule.c.rule_key == rule_key
        )
    )
    assert stored == [], rule_key
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def _steps(policies: Policies, request_id: Any) -> list[tuple[Any, ...]]:
    return [
        tuple(row.values())
        for row in policies.rows(
            select(
                approval_step.c.step_no,
                approval_step.c.name,
                approval_step.c.required_permission,
                approval_step.c.min_approvers,
                approval_step.c.required_role_id,
                approval_step.c.status,
            )
            .where(approval_step.c.approval_request_id == request_id)
            .order_by(approval_step.c.step_no)
        )
    ]


def _decisions(policies: Policies, request_id: Any) -> list[dict[str, Any]]:
    return policies.rows(
        select(approval_decision.c.decision, approval_decision.c.approver_kind).where(
            approval_decision.c.approval_request_id == request_id
        )
    )


def _force_published(
    policies: Policies, kind: RuleSetKind, code: str, rules: list[dict[str, Any]]
) -> tuple[UUID, dict[str, UUID]]:
    """A PUBLISHED version written straight to the tables: a rule that authoring would refuse."""
    with tenant_session(_context(policies.tenant_id)) as session:
        return publish_rule_set(
            session, tenant_id=policies.tenant_id, kind=kind, code=code, rules=rules
        )


# --- (a) no unconditional rule; an auto-approval rule names its subject types ------------------


def test_unconditional_approval_rule_is_refused_at_authoring(policies: Policies) -> None:
    """R-26 (a): the rule the exploit started from — ``conditions: []`` — is refused at the rule
    upsert for both kinds that decide who approves; a kind that legitimately holds unconditional
    rules (``DATA_QUALITY``; ``DQ-SYSTEM``) is unaffected."""
    auto = _draft(policies, "SEC-AUTO-ALL", "AUTO_APPROVAL")
    assert _refused(policies, auto, "ALL", [], AUTO) == [
        ("conditions", "T-REF-26", rule_sets.CONDITION_REQUIRED)
    ]
    routed = _draft(policies, "SEC-ROUTE-ALL", "APPROVAL_ROUTING")
    assert _refused(policies, routed, "ALL", [], {"steps": [CONFIG_STEP]}) == [
        ("conditions", "T-REF-26", rule_sets.CONDITION_REQUIRED)
    ]

    quality = _draft(policies, "SEC-DQ", "DATA_QUALITY")
    added = policies.add_rule(
        quality,
        {
            "rule_key": "DQ_DUPLICATE_INVOICE",
            "priority": 0,
            "conditions": [],
            "outputs": {"severity": "WARNING", "message": "An invoice number repeats."},
        },
    )
    assert added["conditions"] == []


def test_auto_approval_rule_names_allow_listed_subject_types(policies: Policies) -> None:
    """R-26 (a), (b): an ``AUTO_APPROVAL`` rule names the subject types it covers and each is one
    a tenant's rule may approve. A rule set, an access subject, a period reopen, a registry version
    and a subject only its seeded rule set approves are refused by name; the two documented items
    are accepted."""
    version_id = _draft(policies, "SEC-AUTO", "AUTO_APPROVAL")
    channel = _condition("source.channel", "eq", "USER")
    assert _refused(policies, version_id, "BY-CHANNEL", [channel], AUTO) == [
        ("conditions", "T-REF-26", rule_sets.SUBJECT_TYPE_REQUIRED)
    ]
    for refused in (
        "RULE_SET_VERSION",
        "ROLE_ASSIGNMENT",
        "PERIOD_REOPEN",
        "REGISTRY_VERSION",
        # R-41 (7): only the rule set provisioning seeds approves the legacy SSP replay.
        "MIGRATION_SSP_REPLAY",
    ):
        found = _refused(
            policies, version_id, f"AUTO-{refused}", [_subject("IMPORT_COMMIT", refused)], AUTO
        )
        assert found == [
            ("conditions", "T-REF-26", rule_sets.NOT_AUTO_APPROVABLE.format(subjects=refused))
        ], refused

    admitted = sorted(subject.value for subject in routing.AUTO_APPROVABLE)
    assert admitted == ["CONTRACT_ACTIVATION", "IMPORT_COMMIT"]
    added = policies.add_rule(
        version_id,
        {
            "rule_key": "AUTO-DOCUMENTED",
            "priority": 0,
            "conditions": [_subject(*admitted)],
            "outputs": AUTO,
        },
    )
    assert added["specificity"] == 1


# --- (c) the routing floor, at authoring ---------------------------------------------------------


def test_routing_rule_below_the_subjects_own_steps_is_refused_at_authoring(
    policies: Policies,
) -> None:
    """R-26 (c): the second half of the exploit — ``PERIOD_REOPEN`` routed to ONE
    ``judgement.review`` holder — is refused at the rule upsert, as is the subject's own permission
    with fewer approvers. A rule that keeps the subject's step and adds one is accepted."""
    version_id = _draft(policies, "SEC-ROUTE-REOPEN", "APPROVAL_ROUTING")
    reopen = [_subject("PERIOD_REOPEN")]
    ((field, rule_id, message),) = _refused(
        policies, version_id, "REOPEN", reopen, REOPEN_TO_ONE_REVIEWER
    )
    assert (field, rule_id) == ("outputs.steps", "T-REF-26")
    assert message == rule_sets.FLOOR_LOWERED.format(
        subject="PERIOD_REOPEN",
        permission="period.reopen_approve",
        approvers=2,
        approver_word="approvers",
        role="",
    )
    fewer = {
        "steps": [{"name": "Reopen", "permission": "period.reopen_approve", "min_approvers": 1}]
    }
    assert [finding[:2] for finding in _refused(policies, version_id, "REOPEN", reopen, fewer)] == [
        ("outputs.steps", "T-REF-26")
    ]

    raised = {
        "steps": [
            {"name": "Reopen approval", "permission": "period.reopen_approve", "min_approvers": 2},
            {"name": "Judgement review", "permission": "judgement.review", "min_approvers": 1},
        ]
    }
    added = policies.add_rule(
        version_id,
        {"rule_key": "REOPEN", "priority": 0, "conditions": reopen, "outputs": raised},
    )
    assert added["outputs"] == raised


def test_publication_refuses_stored_rules_that_authoring_refuses(policies: Policies) -> None:
    """R-26 "validated at publish": the publication check re-reads the stored rules, so a rule
    that reached a version another way — written directly here — is a publication finding: the
    unconditional rule, the auto-approval rule outside the allow-list, the routing rule below the
    floor."""
    tenant_id = policies.tenant_id
    cases: list[tuple[str, str, list[Any], Any, tuple[str, str]]] = [
        ("SEC-P-AUTO", "AUTO_APPROVAL", [], AUTO, ("conditions", rule_sets.CONDITION_REQUIRED)),
        (
            "SEC-P-AUTO-RSV",
            "AUTO_APPROVAL",
            [_subject("RULE_SET_VERSION")],
            AUTO,
            (
                "conditions",
                rule_sets.NOT_AUTO_APPROVABLE.format(subjects="RULE_SET_VERSION"),
            ),
        ),
        (
            "SEC-P-ROUTE",
            "APPROVAL_ROUTING",
            [_subject("PERIOD_REOPEN")],
            REOPEN_TO_ONE_REVIEWER,
            (
                "outputs.steps",
                rule_sets.FLOOR_LOWERED.format(
                    subject="PERIOD_REOPEN",
                    permission="period.reopen_approve",
                    approvers=2,
                    approver_word="approvers",
                    role="",
                ),
            ),
        ),
    ]
    for code, kind, conditions, outputs, (field, message) in cases:
        version_id = _draft(policies, code, kind)
        with tenant_session(_context(tenant_id)) as session:
            session.execute(
                rule.insert().values(
                    tenant_id=tenant_id,
                    id=new_id(),
                    rule_set_version_id=UUID(version_id),
                    rule_key="STORED",
                    priority=0,
                    conditions=conditions,
                    outputs=outputs,
                    specificity=len(conditions),
                    description=None,
                )
            )
            version = rule_sets.lock_version(session, UUID(version_id))
            findings = rule_sets._publish_errors(session, version)
        assert [(error.field, error.rule_id, error.message) for error in findings] == [
            (f"rules[STORED].{field}", "T-REF-26", message)
        ], code


# --- enforced at submission ----------------------------------------------------------------------


@pytest.mark.control("CTL-005")
def test_ctl_005_match_all_auto_approval_rule_approves_nobodys_own_item(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exploit's step 3, with its precondition forced into the tables: a PUBLISHED
    ``AUTO_APPROVAL`` rule without conditions and one that names ``RULE_SET_VERSION`` for users.
    Maya's own routing rule set is NOT published by her submission: it waits SUBMITTED for a
    Controller, no AUTO_APPROVE decision exists, and a probe item she prepares stays PENDING.
    Marcus then approves it — the change control of REQ-PLT-016 still works."""
    _force_published(
        policies,
        RuleSetKind.AUTO_APPROVAL,
        "SEC-AUTO-FORCED",
        [
            {"rule_key": "ALL", "conditions": [], "outputs": AUTO},
            {
                "rule_key": "CONFIG-BY-USER",
                "conditions": [
                    _subject("RULE_SET_VERSION", "PERIOD_REOPEN", "ROLE_CHANGE"),
                    _condition("source.channel", "eq", "USER"),
                ],
                "outputs": AUTO,
            },
        ],
    )
    # Maya's own routing rule set: valid (it keeps each configuration subject's own step).
    _, version_id = policies.tested(
        "SEC-ROUTE-OWN",
        "APPROVAL_ROUTING",
        [
            {
                "rule_key": "CONFIG",
                "priority": 0,
                "conditions": [_subject("RULE_SET_VERSION")],
                "outputs": {"steps": [CONFIG_STEP]},
            }
        ],
        [("Rule set version", {"subject.type": "RULE_SET_VERSION"}, {"rule_key": "CONFIG"})],
    )
    submitted = policies.submit(version_id)
    assert submitted["status"] == "SUBMITTED"
    request_id = submitted["pending_approval_request_id"]
    assert request_id is not None
    assert (submitted["published_at"], submitted["published_by"]) == (None, None)
    assert _decisions(policies, request_id) == []
    assert (
        policies.rows(
            select(audit_event.c.id).where(
                audit_event.c.action == "approval_request.auto_approve",
                audit_event.c.object_id == UUID(str(request_id)),
            )
        )
        == []
    )

    probe = ProbeSubjects()
    for subject in (_S.PERIOD_REOPEN, _S.ROLE_CHANGE):
        install(monkeypatch, probe.spec(subject))
        pending = policies.submit_probe(subject, probe)
        assert pending["status"] == "PENDING", subject
        assert _decisions(policies, pending["id"]) == [], subject
    assert probe.calls == []

    # Positive control: the Controller approves, and only then is the version PUBLISHED.
    approved = policies.approve(str(request_id))
    assert approved.status_code == 200, approved.text
    shown = policies.get(f"{VERSIONS}/{version_id}").json()
    assert shown["status"] == "PUBLISHED"
    assert shown["published_by"] == str(policies.marcus.member.user_id)
    assert _decisions(policies, request_id) == [{"decision": "APPROVE", "approver_kind": "USER"}]


@pytest.mark.control("CTL-031")
def test_ctl_031_routed_steps_are_raised_to_the_subjects_own_steps(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-26 (c) "enforced at submit": with the exploit's routing rule forced into the tables, a
    ``PERIOD_REOPEN`` request still opens with the subject's own step — two
    ``period.reopen_approve`` approvers — in front of the rule's step; the request names the rule
    and the audit event lists the steps as raised."""
    version_id, rule_ids = _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-FORCED",
        [
            {
                "rule_key": "REOPEN",
                "conditions": [_subject("PERIOD_REOPEN")],
                "outputs": REOPEN_TO_ONE_REVIEWER,
            }
        ],
    )
    probe = ProbeSubjects()
    install(
        monkeypatch,
        probe.spec(_S.PERIOD_REOPEN, required_permission="period.reopen_approve", min_approvers=2),
    )
    request = policies.submit_probe(_S.PERIOD_REOPEN, probe)
    assert request["status"] == "PENDING"
    assert (request["routing_rule_set_version_id"], request["routing_rule_id"]) == (
        version_id,
        rule_ids["REOPEN"],
    )
    assert _steps(policies, request["id"]) == [
        (1, "Approval", "period.reopen_approve", 2, None, "ACTIVE"),
        (2, "Any reviewer", "judgement.review", 1, None, "WAITING"),
    ]
    (event,) = policies.rows(
        select(audit_event.c.after).where(
            audit_event.c.action == "approval_request.submit",
            audit_event.c.object_id == request["id"],
        )
    )
    assert event["after"]["steps"] == [
        {"name": "Approval", "permission": "period.reopen_approve", "min_approvers": 2},
        {"name": "Any reviewer", "permission": "judgement.review", "min_approvers": 1},
    ]


def test_second_step_and_its_role_survive_a_one_step_rule(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-26 (c): the subject's second step and its Controller are part of the floor (PRD §2.5). A
    request that carries the second-step flag gets the second step although the matching rule
    lists one; a rule whose second step names no role gets the role (the sample world's
    ``ROUTE-CON-02`` shape), with the rule's step names kept."""
    (controller,) = policies.rows(select(role.c.id).where(role.c.code == "controller"))
    flagged = frozenset({"POSTED_LINES"})
    probe = ProbeSubjects()

    def spec(subject: ApprovalSubjectType) -> Any:
        return replace(
            probe.spec(subject, required_permission="contract.approve"),
            flags=lambda _session, _subject_id: flagged,
            second_step_flags=flagged,
            second_step_role="controller",
        )

    contract_step = {"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1}
    _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-ONE-STEP",
        [
            {
                "rule_key": "VOID",
                "conditions": [_subject("CONTRACT_VOID")],
                "outputs": {"steps": [contract_step]},
            },
            {
                "rule_key": "ACTIVATION",
                "conditions": [_subject("CONTRACT_ACTIVATION")],
                "outputs": {
                    "steps": [contract_step, {**contract_step, "name": "Controller approval"}]
                },
            },
        ],
    )
    install(monkeypatch, spec(_S.CONTRACT_VOID))
    one = policies.submit_probe(_S.CONTRACT_VOID, probe)
    assert _steps(policies, one["id"]) == [
        (1, "Revenue review", "contract.approve", 1, None, "ACTIVE"),
        (2, "Second approval", "contract.approve", 1, controller["id"], "WAITING"),
    ]
    install(monkeypatch, spec(_S.CONTRACT_ACTIVATION))
    two = policies.submit_probe(_S.CONTRACT_ACTIVATION, probe)
    assert _steps(policies, two["id"]) == [
        (1, "Revenue review", "contract.approve", 1, None, "ACTIVE"),
        (2, "Controller approval", "contract.approve", 1, controller["id"], "WAITING"),
    ]


def test_rule_that_adds_a_step_is_applied_as_written(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control of R-26 (c): "a routing rule may add steps or raise a requirement". A rule
    authored, tested, submitted and approved through the API that keeps the subject's step and adds
    a second one routes exactly its two steps."""
    steps = [
        {"name": "Access approval", "permission": "access.approve", "min_approvers": 2},
        {"name": "Configuration review", "permission": "config.approve", "min_approvers": 1},
    ]
    policies.published(
        "SEC-ROUTE-RAISED",
        "APPROVAL_ROUTING",
        [
            {
                "rule_key": "ROLE-CHANGE",
                "priority": 0,
                "conditions": [_subject("ROLE_CHANGE")],
                "outputs": {"steps": steps},
            }
        ],
        [("Role change", {"subject.type": "ROLE_CHANGE"}, {"rule_key": "ROLE-CHANGE"})],
    )
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(_S.ROLE_CHANGE))
    request = policies.submit_probe(_S.ROLE_CHANGE, probe)
    assert _steps(policies, request["id"]) == [
        (1, "Access approval", "access.approve", 2, None, "ACTIVE"),
        (2, "Configuration review", "config.approve", 1, None, "WAITING"),
    ]


# --- the reviewer's scenario, end to end -------------------------------------------------------


def test_sn9_author_cannot_publish_routing_alone(policies: Policies) -> None:
    """The proof of concept of finding SN-9, with each of its steps now refused: (1) the match-all
    ``AUTO_APPROVAL`` rule is not accepted by authoring; (2) so no Controller approval of it can
    exist; (3) the routing rule that sent ``PERIOD_REOPEN`` to one ``judgement.review`` holder is
    not accepted either; and a routing rule set the author does submit waits for the Controller."""
    auto_version = _draft(policies, "SEC-AUTO-ALL", "AUTO_APPROVAL")
    assert _refused(policies, auto_version, "ALL", [], AUTO) == [
        ("conditions", "T-REF-26", rule_sets.CONDITION_REQUIRED)
    ]
    # A version without a rule and without a passing example case never reaches a Controller.
    policies.post(f"{VERSIONS}/{auto_version}/test")
    unsubmitted = policies.post(f"{VERSIONS}/{auto_version}/submit", {"comment": "routing"})
    assert unsubmitted.status_code == 409, unsubmitted.text
    assert str(unsubmitted.json()["type"]).removeprefix(PROBLEM_BASE) == "invalid-transition"

    routing_set = policies.rule_set("SEC-ROUTE-REOPEN", "APPROVAL_ROUTING")
    routing_version = policies.version(routing_set)
    ((field, _, message),) = _refused(
        policies, routing_version, "REOPEN", [_subject("PERIOD_REOPEN")], REOPEN_TO_ONE_REVIEWER
    )
    assert field == "outputs.steps" and "period.reopen_approve and at least 2 approvers" in message
    # Nothing of the rule set is in force: PERIOD_REOPEN keeps its own routing.
    evaluated = policies.post(
        f"{RULE_SETS}/{routing_set}/evaluate", {"facts": {"subject.type": "PERIOD_REOPEN"}}
    )
    assert evaluated.status_code == 200 and evaluated.json()["matched"] is False, evaluated.text


# --- R-38 (vi) and R-41 (7): each limit isolated at submission -----------------------------------


def _import_probe(monkeypatch: pytest.MonkeyPatch) -> ProbeSubjects:
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(_S.IMPORT_COMMIT, required_permission="import.approve"))
    return probe


def test_auto_rule_that_names_no_subject_type_never_matches_an_allow_listed_item(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-26 (a) at submission, isolated from (b) (the review's gap): an API client's import commit
    IS on the allow-list, so only ``routing.admissible`` holds back a published rule that names no
    subject type — a channel-only rule and a rule without conditions, forced into the tables. The
    item waits for a person; a rule that names the item type approves the same submission."""
    _force_published(
        policies,
        RuleSetKind.AUTO_APPROVAL,
        "SEC-AUTO-CHANNEL",
        [
            {
                "rule_key": "BY-CHANNEL",
                "conditions": [_condition("source.channel", "eq", "API_CLIENT")],
                "outputs": AUTO,
            },
            {"rule_key": "ALL", "conditions": [], "outputs": AUTO},
        ],
    )
    probe = _import_probe(monkeypatch)
    held = policies.submit_probe(_S.IMPORT_COMMIT, probe, kind=PrincipalKind.API_CLIENT)
    assert held["status"] == "PENDING"
    assert _decisions(policies, held["id"]) == []

    version_id, rule_ids = _force_published(
        policies,
        RuleSetKind.AUTO_APPROVAL,
        "SEC-AUTO-NAMED",
        [
            {
                "rule_key": "IMPORTS",
                "conditions": [
                    _subject("IMPORT_COMMIT"),
                    _condition("source.channel", "eq", "API_CLIENT"),
                ],
                "outputs": AUTO,
            }
        ],
    )
    approved = policies.submit_probe(_S.IMPORT_COMMIT, probe, kind=PrincipalKind.API_CLIENT)
    assert approved["status"] == "APPROVED"
    assert policies.rows(
        select(
            approval_decision.c.decision,
            approval_decision.c.auto_rule_set_version_id,
            approval_decision.c.auto_rule_id,
        ).where(approval_decision.c.approval_request_id == approved["id"])
    ) == [
        {
            "decision": "AUTO_APPROVE",
            "auto_rule_set_version_id": version_id,
            "auto_rule_id": rule_ids["IMPORTS"],
        }
    ]


def test_routing_rule_without_a_condition_routes_nothing(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-26 (a) at submission for ``APPROVAL_ROUTING`` (the review's gap): a published routing rule
    without a condition — which would send every subject to its one step — never matches. The
    request names no routing rule and takes the subject's own step; the same steps under a
    condition that names the subject are applied, raised to the floor."""
    any_reviewer = {"steps": [dict(REOPEN_TO_ONE_REVIEWER["steps"][0])]}
    _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-ALL-FORCED",
        [{"rule_key": "ALL", "conditions": [], "outputs": any_reviewer}],
    )
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(_S.ROLE_CHANGE))
    request = policies.submit_probe(_S.ROLE_CHANGE, probe)
    assert (request["routing_rule_set_version_id"], request["routing_rule_id"]) == (None, None)
    assert _steps(policies, request["id"]) == [(1, "Approval", "access.approve", 1, None, "ACTIVE")]

    version_id, rule_ids = _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-NAMED",
        [{"rule_key": "ROLE", "conditions": [_subject("ROLE_CHANGE")], "outputs": any_reviewer}],
    )
    routed = policies.submit_probe(_S.ROLE_CHANGE, probe)
    assert (routed["routing_rule_set_version_id"], routed["routing_rule_id"]) == (
        version_id,
        rule_ids["ROLE"],
    )
    assert _steps(policies, routed["id"]) == [
        (1, "Approval", "access.approve", 1, None, "ACTIVE"),
        (2, "Any reviewer", "judgement.review", 1, None, "WAITING"),
    ]


def test_routed_step_below_the_subjects_approver_count_is_raised_in_place(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-26 (c) at submission, the in-place raise (the review's gap): a published rule whose step
    carries the subject's permission with fewer approvers keeps its step — name and position — with
    the subject's approver count; no second step appears."""
    _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-FEWER",
        [
            {
                "rule_key": "REOPEN",
                "conditions": [_subject("PERIOD_REOPEN")],
                "outputs": {
                    "steps": [
                        {
                            "name": "Reopen approval",
                            "permission": "period.reopen_approve",
                            "min_approvers": 1,
                        }
                    ]
                },
            }
        ],
    )
    probe = ProbeSubjects()
    install(
        monkeypatch,
        probe.spec(_S.PERIOD_REOPEN, required_permission="period.reopen_approve", min_approvers=2),
    )
    request = policies.submit_probe(_S.PERIOD_REOPEN, probe)
    assert _steps(policies, request["id"]) == [
        (1, "Reopen approval", "period.reopen_approve", 2, None, "ACTIVE")
    ]


def test_controller_step_in_any_order_meets_the_second_step(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-41 (7): the floor counts approvers per permission and role, not a sequence. A rule that
    lists the Controller's step FIRST for a flagged item already meets the subject's two steps —
    no second Controller step is added, so one Controller can decide — and the submit audit event
    names the role of the step that carries one."""
    (controller,) = policies.rows(select(role.c.id).where(role.c.code == "controller"))
    flagged = frozenset({"POSTED_LINES"})
    probe = ProbeSubjects()
    install(
        monkeypatch,
        replace(
            probe.spec(_S.CONTRACT_VOID, required_permission="contract.approve"),
            flags=lambda _session, _subject_id: flagged,
            second_step_flags=flagged,
            second_step_role="controller",
        ),
    )
    step = {"permission": "contract.approve", "min_approvers": 1}
    _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-ROUTE-CONTROLLER-FIRST",
        [
            {
                "rule_key": "VOID",
                "conditions": [_subject("CONTRACT_VOID")],
                "outputs": {
                    "steps": [
                        {**step, "name": "Controller approval", "role": "controller"},
                        {**step, "name": "Revenue review"},
                    ]
                },
            }
        ],
    )
    request = policies.submit_probe(_S.CONTRACT_VOID, probe)
    assert _steps(policies, request["id"]) == [
        (1, "Controller approval", "contract.approve", 1, controller["id"], "ACTIVE"),
        (2, "Revenue review", "contract.approve", 1, None, "WAITING"),
    ]
    (event,) = policies.rows(
        select(audit_event.c.after).where(
            audit_event.c.action == "approval_request.submit",
            audit_event.c.object_id == request["id"],
        )
    )
    assert event["after"]["steps"] == [
        {**step, "name": "Controller approval", "role": "controller"},
        {**step, "name": "Revenue review"},
    ]
    assert event["after"]["entities"] == {"entity_ids": [], "all_entities": False}


def test_seeded_only_subject_is_approved_by_its_seeded_rule_set_alone(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-41 (7): ``MIGRATION_SSP_REPLAY`` is pinned to the rule set provisioning seeds
    (``AUTO-MIG-01``; 04 §14.3). A published rule of another set that names the subject with a
    higher priority neither approves the replay nor outranks the seeded rule: the decision names
    the seeded rule. A tenant cannot author such a rule in the first place."""
    forced_version, forced_rules = _force_published(
        policies,
        RuleSetKind.AUTO_APPROVAL,
        "SEC-AUTO-MIG",
        [
            {
                "rule_key": "REPLAY",
                "priority": 100,
                "conditions": [
                    _subject("MIGRATION_SSP_REPLAY"),
                    _condition("source.channel", "eq", "USER"),
                ],
                "outputs": AUTO,
            }
        ],
    )
    (seeded,) = policies.rows(
        select(rule.c.id, rule.c.rule_set_version_id).where(rule.c.rule_key == "AUTO-MIG-01")
    )
    probe = ProbeSubjects()
    install(
        monkeypatch, probe.spec(_S.MIGRATION_SSP_REPLAY, required_permission="migration.approve")
    )
    request = policies.submit_probe(_S.MIGRATION_SSP_REPLAY, probe)
    assert request["status"] == "APPROVED"
    (decision,) = policies.rows(
        select(
            approval_decision.c.auto_rule_set_version_id, approval_decision.c.auto_rule_id
        ).where(approval_decision.c.approval_request_id == request["id"])
    )
    assert (decision["auto_rule_set_version_id"], decision["auto_rule_id"]) == (
        seeded["rule_set_version_id"],
        seeded["id"],
    )
    assert decision["auto_rule_id"] != forced_rules["REPLAY"]
    assert decision["auto_rule_set_version_id"] != forced_version
    # The replay is a user's request at /import: an API client's is not read at all.
    by_client = policies.submit_probe(_S.MIGRATION_SSP_REPLAY, probe, kind=PrincipalKind.API_CLIENT)
    assert by_client["status"] == "PENDING"


def test_seeded_approval_rule_sets_take_no_further_version(policies: Policies) -> None:
    """The second independent review (R-26 (b), R-41 (7); 04 §14.3 item 2): the two rule sets
    provisioning seeds — ``AUTO-BOOTSTRAP`` and ``AUTO-MIG-01`` — are read by their code and a
    tenant's rule that names their subjects is refused, so a further version could only supersede
    the seeded rule without being able to restore it (the migration import would then find no
    rule). ``POST /rule-sets/{id}/versions`` answers 409 ``configuration-frozen`` for both and
    writes nothing; a tenant's own auto-approval set is versioned as before."""
    seeded = {
        item["code"]: item for item in policies.get(RULE_SETS, kind="AUTO_APPROVAL").json()["items"]
    }
    assert sorted(seeded) == ["AUTO-BOOTSTRAP", "AUTO-MIG-01"]
    for code, item in sorted(seeded.items()):
        refused = policies.post(f"{RULE_SETS}/{item['id']}/versions", {})
        assert refused.status_code == 409, refused.text
        assert str(refused.json()["type"]).removeprefix(PROBLEM_BASE) == "configuration-frozen"
        assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
            ("T-REF-24", rule_sets.SEEDED_SET.format(code=code))
        ]
        copied = policies.post(
            f"{RULE_SETS}/{item['id']}/versions",
            {"source_version_id": item["current_version"]["id"]},
        )
        assert copied.status_code == 409, copied.text
    versions = policies.rows(
        select(rule_set.c.code, rule_set_version.c.version_no, rule_set_version.c.status)
        .select_from(
            rule_set.join(rule_set_version, rule_set_version.c.rule_set_id == rule_set.c.id)
        )
        .where(rule_set.c.code.in_(sorted(seeded)))
        .order_by(rule_set.c.code)
    )
    assert [tuple(str(value) for value in row.values()) for row in versions] == [
        ("AUTO-BOOTSTRAP", "1", "PUBLISHED"),
        ("AUTO-MIG-01", "1", "PUBLISHED"),
    ]
    # Positive control: a tenant's own set of the same kind takes versions.
    own = _draft(policies, "SEC-OWN-AUTO", "AUTO_APPROVAL")
    assert policies.rows(
        select(rule_set_version.c.version_no).where(rule_set_version.c.id == UUID(own))
    ) == [{"version_no": 1}]


def test_system_job_on_behalf_of_a_user_is_not_system_originated(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-41 (7): SYSTEM counts as system-originated only when the job acts on behalf of no user.
    A contract activation submitted by SYSTEM for a person waits for a person although a published
    rule names it; the same submission on nobody's behalf is approved."""
    _force_published(
        policies,
        RuleSetKind.AUTO_APPROVAL,
        "SEC-AUTO-ACTIVATION",
        [
            {
                "rule_key": "ACTIVATION",
                "conditions": [_subject("CONTRACT_ACTIVATION")],
                "outputs": AUTO,
            }
        ],
    )
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(_S.CONTRACT_ACTIVATION, required_permission="contract.approve"))
    tenant_id = policies.tenant_id
    for_maya = system_principal(tenant_id, on_behalf_of_id=policies.maya.member.user_id)
    held = policies.submit_probe_as(_S.CONTRACT_ACTIVATION, probe, for_maya)
    assert held["status"] == "PENDING"
    assert _decisions(policies, held["id"]) == []
    approved = policies.submit_probe_as(_S.CONTRACT_ACTIVATION, probe, system_principal(tenant_id))
    assert approved["status"] == "APPROVED"
    assert _decisions(policies, approved["id"]) == [
        {"decision": "AUTO_APPROVE", "approver_kind": "SYSTEM"}
    ]


def test_approval_of_a_version_with_an_inadmissible_rule_is_refused_and_rolled_back(
    policies: Policies,
) -> None:
    """R-26 "validated at publish", end to end through an approver's decision (the review's gap):
    a TESTED auto-approval version gains, behind the rule commands, a rule that names a rule set,
    and is tested and submitted with it. The Controller's approval would publish it: the decision
    answers 422 with the finding, and nothing of it stays — no decision row, the request PENDING,
    the version SUBMITTED."""
    tenant_id = policies.tenant_id
    _, version_id = policies.tested(
        "SEC-P-E2E",
        "AUTO_APPROVAL",
        [
            {
                "rule_key": "IMPORTS",
                "priority": 0,
                "conditions": [
                    _subject("IMPORT_COMMIT"),
                    _condition("source.channel", "eq", "API_CLIENT"),
                ],
                "outputs": AUTO,
            }
        ],
        [
            (
                "Import commit uploaded by an API client",
                {"subject.type": "IMPORT_COMMIT", "source.channel": "API_CLIENT"},
                {"rule_key": "IMPORTS"},
            )
        ],
    )
    with tenant_session(_context(tenant_id)) as session:
        session.execute(
            rule.insert().values(
                tenant_id=tenant_id,
                id=new_id(),
                rule_set_version_id=UUID(version_id),
                rule_key="STORED",
                priority=0,
                conditions=[_subject("RULE_SET_VERSION")],
                outputs=AUTO,
                specificity=1,
                description=None,
            )
        )
    # The stored rule changed the tested content, so the version is not submittable as it stands
    # (REQ-POL-003); tested again — the example case still passes — it is, with the rule in it.
    stale = policies.post(f"{VERSIONS}/{version_id}/submit", {"comment": "Ready for review"})
    assert stale.status_code == 409, stale.text
    assert str(stale.json()["type"]).removeprefix(PROBLEM_BASE) == "invalid-transition"
    retested = policies.post(f"{VERSIONS}/{version_id}/test")
    assert retested.status_code == 200, retested.text
    submitted = policies.post(f"{VERSIONS}/{version_id}/submit", {"comment": "Ready for review"})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["pending_approval_request_id"]
    assert request_id is not None

    refused = policies.approve(str(request_id))
    assert refused.status_code == 422, refused.text
    assert str(refused.json()["type"]).removeprefix(PROBLEM_BASE) == "validation-failed"
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ] == [
        (
            "rules[STORED].conditions",
            "T-REF-26",
            rule_sets.NOT_AUTO_APPROVABLE.format(subjects="RULE_SET_VERSION"),
        )
    ]
    assert _decisions(policies, request_id) == []
    shown = policies.get(f"{VERSIONS}/{version_id}").json()
    assert (shown["status"], shown["published_at"]) == ("SUBMITTED", None)
    (request,) = policies.rows(
        select(approval_request.c.status).where(approval_request.c.id == UUID(str(request_id)))
    )
    assert request["status"] == "PENDING"


def test_evaluation_applies_the_limits_of_a_submission(policies: Policies) -> None:
    """R-41 (7): ``POST /rule-sets/{id}/evaluate`` answers what a submission with the same facts
    gets — the steps of a routing rule raised to the subject's own steps, and no match for an
    auto-approval case the allow-list refuses."""
    routing_set, _ = policies.published(
        "SEC-EVAL-ROUTE",
        "APPROVAL_ROUTING",
        [
            {
                "rule_key": "VOID",
                "priority": 0,
                "conditions": [_subject("CONTRACT_VOID")],
                "outputs": {
                    "steps": [
                        {
                            "name": "Revenue review",
                            "permission": "contract.approve",
                            "min_approvers": 1,
                        }
                    ]
                },
            }
        ],
        [("Contract void", {"subject.type": "CONTRACT_VOID"}, {"rule_key": "VOID"})],
    )
    plain = policies.post(
        f"{RULE_SETS}/{routing_set}/evaluate", {"facts": {"subject.type": "CONTRACT_VOID"}}
    )
    assert plain.status_code == 200 and len(plain.json()["outputs"]["steps"]) == 1, plain.text
    posted = policies.post(
        f"{RULE_SETS}/{routing_set}/evaluate",
        {"facts": {"subject.type": "CONTRACT_VOID", "flags": ["POSTED_LINES"]}},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["outputs"]["steps"] == [
        {"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1},
        {
            "name": "Second approval",
            "permission": "contract.approve",
            "min_approvers": 1,
            "role": "controller",
        },
    ]

    auto_set, _ = policies.published(
        "SEC-EVAL-AUTO",
        "AUTO_APPROVAL",
        [
            {
                "rule_key": "IMPORTS",
                "priority": 0,
                "conditions": [_subject("IMPORT_COMMIT")],
                "outputs": AUTO,
            }
        ],
        [
            (
                "Import commit uploaded by an API client",
                {"subject.type": "IMPORT_COMMIT", "source.channel": "API_CLIENT"},
                {"rule_key": "IMPORTS"},
            )
        ],
    )
    by_client = policies.post(
        f"{RULE_SETS}/{auto_set}/evaluate",
        {"facts": {"subject.type": "IMPORT_COMMIT", "source.channel": "API_CLIENT"}},
    )
    by_user = policies.post(
        f"{RULE_SETS}/{auto_set}/evaluate",
        {"facts": {"subject.type": "IMPORT_COMMIT", "source.channel": "USER"}},
    )
    assert (by_client.json()["matched"], by_client.json()["rule_key"]) == (True, "IMPORTS")
    assert (by_user.status_code, by_user.json()["matched"]) == (200, False), by_user.text


def test_condition_the_matcher_cannot_evaluate_is_refused_where_it_is_written(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-66 (9), second half (04 T-REF-26 rev 1.104 part 6): a condition whose
    operator or value the matcher cannot evaluate on its field's fact — an ordering on the list
    ``flags``, a prefix on a number, text where a field holds true or false — is refused at the
    rule upsert and again at publication. Before the ruling authoring accepted every operator on
    every field, and such a rule made the matcher raise on EVERY request that read the rule set
    — which a rule that reaches the table another way still does (the last block: nothing is
    routed on a rule nobody can evaluate), so it must not get there through the product."""
    version_id = _draft(policies, "SEC-OP-ROUTE", "APPROVAL_ROUTING")
    steps = {"steps": [CONFIG_STEP]}
    named = _subject("RULE_SET_VERSION")
    refusals = [
        (
            _condition("flags", "gte", "METHODOLOGY_CHANGE"),
            ("conditions[1].op", "flags holds a list of values. Compare it with eq or in."),
        ),
        (
            _condition("entity.code", "prefix", "AVM"),
            ("conditions[1].op", "entity.code holds a list of values. Compare it with eq or in."),
        ),
        (
            _condition("amount.functional", "prefix", "10"),
            (
                "conditions[1].op",
                "amount.functional holds a number. Compare it with eq, in, gte, lte or range.",
            ),
        ),
        (
            _condition("amount.functional", "gte", "a lot"),
            ("conditions[1].value", "amount.functional holds a number. Enter a number as text."),
        ),
    ]
    for condition, (field, message) in refusals:
        found = _refused(policies, version_id, "UNEVALUABLE", [named, condition], steps)
        assert found == [(field, "T-REF-26", message)], condition
    auto = _draft(policies, "SEC-OP-AUTO", "AUTO_APPROVAL")
    assert _refused(
        policies,
        auto,
        "UNEVALUABLE",
        [_subject("IMPORT_COMMIT"), _condition("tenant.setup_completed", "eq", "false")],
        AUTO,
    ) == [
        (
            "conditions[1].value",
            "T-REF-26",
            "tenant.setup_completed holds true or false. Enter true or false.",
        )
    ]

    # Positive controls: the same fields with an operator and a value the matcher evaluates
    # (one priority each, so the lint has nothing to say about rules that can meet).
    accepted = (
        ("FLAGS", _condition("flags", "in", ["METHODOLOGY_CHANGE"])),
        ("ENTITY", _condition("entity.code", "eq", "AVM-US")),
        ("AMOUNT", _condition("amount.functional", "gte", "1000.00")),
    )
    for priority, (key, condition) in enumerate(accepted, start=1):
        body = {"rule_key": key, "priority": priority, "conditions": [named, condition]}
        policies.add_rule(version_id, {**body, "outputs": steps})

    # Publication reads the stored rules again: one written behind the rule commands is a finding.
    tenant_id = policies.tenant_id
    stored = [named, _condition("flags", "lte", "METHODOLOGY_CHANGE")]
    with tenant_session(_context(tenant_id)) as session:
        session.execute(
            rule.insert().values(
                tenant_id=tenant_id,
                id=new_id(),
                rule_set_version_id=UUID(version_id),
                rule_key="STORED",
                priority=9,
                conditions=stored,
                outputs=steps,
                specificity=2,
                description=None,
            )
        )
        findings = rule_sets._publish_errors(
            session, rule_sets.lock_version(session, UUID(version_id))
        )
    assert [(error.field, error.rule_id, error.message) for error in findings] == [
        (
            "rules[STORED].conditions[1].op",
            "T-REF-26",
            "flags holds a list of values. Compare it with eq or in.",
        )
    ]

    # What such a rule does once it is in force: every request of every subject is refused,
    # whatever it names — the state the product now keeps a tenant out of.
    _force_published(
        policies,
        RuleSetKind.APPROVAL_ROUTING,
        "SEC-OP-FORCED",
        [{"rule_key": "FORCED", "conditions": stored, "outputs": steps}],
    )
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(_S.SOD_EXCEPTION))
    with pytest.raises(ValueError, match="does not apply to the collection fact flags"):
        policies.submit_probe(_S.SOD_EXCEPTION, probe)
