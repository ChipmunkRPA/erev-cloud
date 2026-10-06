"""Evaluation equals submission: every seeded and demo approval rule through both paths (04
T-REF-26 rev 1.104 part 6 and §16.10 "Auto-approval and the routing floor"; dev-guide
DG-KRN-APR-08; PRD §2.5; 03 REQ-PLT-013, REQ-PLT-016; supervisor ruling R-66 (8)).

``POST /rule-sets/{id}/evaluate`` and the example cases of a rule set version answer what a
submission with the same facts gets. The independent review found the two paths apart in four
places — a submission passed no entity, the allow-list was applied by two functions, the channel
of a job acting for a user, the spelling of the kind — so the claim is held here rule by rule:
the routing and auto-approval rules the sample world publishes (``demo.avenmoor.policies``: PRD
§2.5) are authored and published through the API as Maya and Marcus do, and each is then read
twice with the facts of its own example case — by the evaluation route, and by the functions a
submission calls (``engine.routed_steps``, ``engine.auto_approval_rule``). The two rule sets
provisioning seeds (``AUTO-BOOTSTRAP``, ``AUTO-MIG-01``) are read the same way.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_api.approvals import engine
from erev_api.approvals.subjects import SUBJECTS
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, role, rule_set
from erev_api.domain.demo.avenmoor import policies as demo
from erev_api.enums import ApprovalSubjectType, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import insert, select
from support.rows import api_client_values

if TYPE_CHECKING:
    from conftest import Policies

RULE_SETS = "/api/v1/rule-sets"
_S = ApprovalSubjectType
AUTO = {"auto_approve": True}
Step = tuple[str, str, int, str | None]


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _evaluated(policies: Policies, rule_set_id: str, facts: Mapping[str, Any]) -> dict[str, Any]:
    """The evaluation path: ``POST /rule-sets/{id}/evaluate`` as Maya."""
    response = policies.post(f"{RULE_SETS}/{rule_set_id}/evaluate", {"facts": dict(facts)})
    assert response.status_code == 200, response.text
    return dict(response.json())


def _steps(outputs: Mapping[str, Any]) -> list[Step]:
    return [
        (step["name"], step["permission"], step["min_approvers"], step.get("role"))
        for step in outputs["steps"]
    ]


def _person(policies: Policies, *roles: str) -> Principal:
    """Maya — the workspace's bootstrap Tenant Admin — as a session holding ``roles``."""
    return Principal(
        kind=PrincipalKind.USER,
        id=policies.maya.member.user_id,
        tenant_id=policies.tenant_id,
        membership_id=policies.maya.member.membership_id,
        display_name="Maya",
        roles=roles,
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _client(policies: Policies) -> Principal:
    """An integration's API client, as its bearer token states it."""
    client = api_client_values(policies.tenant_id, name="svc-salesforce")
    with tenant_session(_context(policies.tenant_id)) as session:
        session.execute(insert(api_client).values(**client))
    return Principal(
        kind=PrincipalKind.API_CLIENT,
        id=UUID(str(client["id"])),
        tenant_id=policies.tenant_id,
        membership_id=None,
        display_name="svc-salesforce",
        roles=(),
        permissions=frozenset({"contract.create"}),
        permission_scopes=MappingProxyType({"contract.create": "*"}),
        entity_scope="*",
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@contextmanager
def _unit(policies: Policies, principal: Principal) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-rule-paths",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=policies.clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(policies.settings.file_root)
    with unit_of_work(ctx, clock=policies.clock, keyring=policies.keyring, files=files) as uow:
        yield uow


def _submitted_rule(
    policies: Policies, principal: Principal, subject_type: ApprovalSubjectType
) -> str | None:
    """The submission path of an auto-approval rule: the rule ``submit`` would apply to a request
    of ``subject_type`` by ``principal`` now, or None when a person will decide."""
    with _unit(policies, principal) as uow:
        found = engine.auto_approval_rule(uow, subject_type)
    return None if found is None else found.rule_key


def test_every_demo_routing_rule_answers_alike_in_evaluation_and_at_submission(
    policies: Policies,
) -> None:
    """R-66 (8) over the routing rules of the sample world (PRD §2.5): for each rule and each
    subject type it names, the facts of its example case reach the same rule on both paths, and
    the steps the evaluation returns are the steps the submission would create — raised to the
    subject's own steps the same way, the second step and its role included when the case carries
    a second-step flag. A subject type without a specification cannot be submitted; its rules are
    evaluated as written."""
    rules = [
        {
            "rule_key": rule.rule_key,
            "priority": 0,
            "conditions": demo.routing_conditions(rule),
            "outputs": demo.routing_outputs(rule),
        }
        for rule in demo.ROUTING_RULES
    ]
    cases = [
        (
            f"{rule.rule_key} {rule.subjects[0].value}",
            {"subject.type": rule.subjects[0].value, **rule.case_facts},
            {"rule_key": rule.rule_key},
        )
        for rule in demo.ROUTING_RULES
    ]
    rule_set_id, _ = policies.published("APPROVAL-ROUTING", "APPROVAL_ROUTING", rules, cases)

    compared = unsubmittable = 0
    with tenant_session(_context(policies.tenant_id), read_only=True) as session:
        codes = {
            UUID(str(role_id)): str(code)
            for role_id, code in session.execute(select(role.c.id, role.c.code))
        }
        for rule in demo.ROUTING_RULES:
            for subject in rule.subjects:
                facts = {"subject.type": subject.value, **rule.case_facts}
                evaluated = _evaluated(policies, rule_set_id, facts)
                assert (evaluated["matched"], evaluated["rule_key"]) == (True, rule.rule_key), facts
                spec = SUBJECTS.get(subject)
                if spec is None:
                    assert _steps(evaluated["outputs"]) == _steps(demo.routing_outputs(rule))
                    unsubmittable += 1
                    continue
                amount = rule.case_facts.get("amount.functional")
                routed = engine.routed_steps(
                    session,
                    spec,
                    entity_codes=(),
                    amount=None if amount is None else Decimal(str(amount)),
                    flags=list(rule.case_facts.get("flags", ())),
                    at=policies.clock.now(),
                )
                assert routed.rule is not None and routed.rule.rule_key == rule.rule_key, facts
                submitted = [
                    (
                        step.name,
                        step.permission,
                        step.min_approvers,
                        None if step.role_id is None else codes[step.role_id],
                    )
                    for step in routed.steps
                ]
                assert submitted == _steps(evaluated["outputs"]), (rule.rule_key, subject.value)
                compared += 1
    # Every rule was read on both paths but the ones of the two subject types nobody can submit
    # yet (``subjects.PENDING_SUBJECTS``: two rules of the sample world name them). The three
    # rules of ``MANUAL_ADJUSTMENT`` are compared since CLO-12 gave the subject its specification,
    # and the rule of ``EVIDENCE_SHRED`` since the subject came with its routing row (lane
    # SECFIX-IMP part B, 2c45103d; rulings R-49 (a), R-86): 37 + 1.
    assert (compared, unsubmittable) == (
        sum(len(rule.subjects) for rule in demo.ROUTING_RULES) - unsubmittable,
        sum(subject not in SUBJECTS for rule in demo.ROUTING_RULES for subject in rule.subjects),
    )
    assert (compared, unsubmittable) == (38, 2)


def test_every_seeded_and_demo_auto_approval_rule_answers_alike_on_both_paths(
    policies: Policies,
) -> None:
    """R-66 (8) over the auto-approval rules: the two of the sample world (an integration's
    contract activation and import commit) and the two provisioning seeds (the bootstrap grants,
    the legacy SSP replay). For each, the case that matches in the evaluation is the principal
    the rule approves at a submission; and the cases the allow-list refuses — a person, a job
    that acts for a person — match on neither path. One function applies the allow-list to
    both (``routing.evaluation_admitted``)."""
    rules = [
        {
            "rule_key": rule.rule_key,
            "priority": 0,
            "conditions": demo.auto_conditions(rule),
            "outputs": AUTO,
        }
        for rule in demo.AUTO_RULES
    ]
    cases = [
        (
            f"{rule.rule_key} {rule.subject.value}",
            {"subject.type": rule.subject.value, "source.channel": rule.source_channel},
            {"rule_key": rule.rule_key},
        )
        for rule in demo.AUTO_RULES
    ]
    rule_set_id, _ = policies.published("AUTO-APPROVAL", "AUTO_APPROVAL", rules, cases)
    seeded = {
        str(row["code"]): str(row["id"])
        for row in policies.rows(
            select(rule_set.c.code, rule_set.c.id).where(
                rule_set.c.code.in_(["AUTO-BOOTSTRAP", "AUTO-MIG-01"])
            )
        )
    }
    client = _client(policies)
    job = system_principal(policies.tenant_id)
    for_maya = system_principal(policies.tenant_id, on_behalf_of_id=policies.maya.member.user_id)

    def both(
        set_id: str, principal: Principal, subject: ApprovalSubjectType, **facts: Any
    ) -> tuple[str | None, str | None]:
        """(the evaluation's rule, the submission's rule) for the principal's own facts."""
        case = {
            "subject.type": subject.value,
            "source.channel": engine.source_channel(principal),
            **facts,
        }
        evaluated = _evaluated(policies, set_id, case)
        return evaluated["rule_key"], _submitted_rule(policies, principal, subject)

    # The sample world's rules: the integration's client on both paths, nobody else on either.
    for rule in demo.AUTO_RULES:
        assert rule.source_channel == "API_CLIENT"
        assert both(rule_set_id, client, rule.subject) == (rule.rule_key, rule.rule_key)
        for other in (_person(policies, "revenue_accountant"), job, for_maya):
            assert both(rule_set_id, other, rule.subject) == (None, None), (rule.rule_key, other)

    # The seeded rule sets: the bootstrap Tenant Admin's grant before setup completes, and the
    # legacy SSP replay a member starts; an integration's client on neither path.
    admin = _person(policies, "tenant_admin")
    setup = {"preparer.role_codes": ["tenant_admin"], "tenant.setup_completed": False}
    assert both(seeded["AUTO-BOOTSTRAP"], admin, _S.ROLE_ASSIGNMENT, **setup) == (
        "AUTO-BOOTSTRAP",
        "AUTO-BOOTSTRAP",
    )
    accountant = _person(policies, "revenue_accountant")
    no_admin = {"preparer.role_codes": ["revenue_accountant"], "tenant.setup_completed": False}
    assert both(seeded["AUTO-BOOTSTRAP"], accountant, _S.ROLE_ASSIGNMENT, **no_admin) == (
        None,
        None,
    )
    assert both(seeded["AUTO-MIG-01"], accountant, _S.MIGRATION_SSP_REPLAY) == (
        "AUTO-MIG-01",
        "AUTO-MIG-01",
    )
    for subject, code in (
        (_S.ROLE_ASSIGNMENT, "AUTO-BOOTSTRAP"),
        (_S.MIGRATION_SSP_REPLAY, "AUTO-MIG-01"),
    ):
        assert both(seeded[code], client, subject) == (None, None)
        # A seeded-only subject is read in its own rule set alone: a case of it evaluated
        # against the tenant's rule set matches nothing, whoever it names.
        for channel in ("USER", "API_CLIENT", "SYSTEM"):
            case = {"subject.type": subject.value, "source.channel": channel, **setup}
            assert _evaluated(policies, rule_set_id, case)["matched"] is False
