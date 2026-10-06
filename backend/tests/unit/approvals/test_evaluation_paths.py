"""Evaluation equals submission, and what the matcher can evaluate — the pure functions (04
T-REF-26 rev 1.104 part 6, §16.10 "Auto-approval and the routing floor"; dev-guide DG-KRN-APR-08;
REQ-PLT-013, REQ-PLT-016; supervisor rulings R-66 (8) and (9)).

A condition is refused where the matcher would raise on its field's fact — never at a request —
and the refusal is checked here against ``erev_engine.rules.match`` itself: every condition the
platform accepts evaluates without an error on a fact of the field's type, and every condition
it refuses for its operator or its value makes the matcher raise. The facts a submission states
are the facts a case states: ``entity.code`` is a set of codes on both paths and
``source.channel`` names the origin of the content.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.approvals import engine, routing
from erev_api.auth.principal import Principal, system_principal
from erev_api.domain.policies import rule_sets
from erev_api.enums import ApprovalSubjectType, PrincipalKind, RuleSetKind
from erev_engine.rules import FIELDS, OPERATORS, match

TENANT: Final = UUID("00000000-0000-0000-0000-0000000000f0")
USER: Final = UUID("00000000-0000-0000-0000-0000000000f1")
ROUTING: Final = RuleSetKind.APPROVAL_ROUTING
AUTO: Final = RuleSetKind.AUTO_APPROVAL

# One fact of each approval field, typed as a submission states it (``routing.routing_facts``,
# ``routing.auto_approval_facts``) — and, for the three ``reconciliation.*`` fields BUILD_SPEC
# CLO-17 added to ``AUTO_APPROVAL``, as the certification of a reconciliation states them
# (``close.reconciliations.certifying_rule``: the kind, a count, an amount).
SUBMISSION_FACTS: Final[dict[RuleSetKind, dict[str, object]]] = {
    ROUTING: routing.routing_facts(
        subject_type=ApprovalSubjectType.CONTRACT_VOID,
        entity_codes=("AVM-US", "AVM-UK"),
        amount_functional=Decimal("1250.00"),
        flags=("POSTED_LINES",),
    ),
    AUTO: routing.auto_approval_facts(
        subject_type=ApprovalSubjectType.CONTRACT_ACTIVATION,
        preparer_role_codes=("revenue_accountant",),
        setup_completed=False,
        source_channel="API_CLIENT",
    )
    | {
        "reconciliation.kind": "BILLING_TO_SUBLEDGER",
        "reconciliation.variance_count": 0,
        "reconciliation.unexplained_other_amount": Decimal("0.00"),
    },
}
# A value of each JSON type a condition can carry.
VALUES: Final[tuple[object, ...]] = ("AVM-US", "1250.00", 7, True, "2026-09-30")


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: list[dict[str, Any]]
    outputs: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: list[_Rule]


def _condition(field: str, op: str, value: object) -> dict[str, Any]:
    if op == "in":
        return {"field": field, "op": op, "value": [value]}
    if op == "range":
        return {"field": field, "op": op, "value": [value, None]}
    return {"field": field, "op": op, "value": value}


def _matcher_evaluates(kind: RuleSetKind, condition: dict[str, Any]) -> bool:
    """Whether ``erev_engine.rules.match`` evaluates a rule with ``condition`` on the facts of a
    submission — False when it raises, which refuses the request that reads the rule set."""
    rule = _Rule("R-1", 0, 1, [condition], {})
    try:
        match(_RuleSet(kind.value, [rule]), SUBMISSION_FACTS[kind])
    except (TypeError, ValueError):
        return False
    return True


@pytest.mark.parametrize("kind", [ROUTING, AUTO])
def test_a_condition_is_accepted_exactly_when_the_matcher_can_evaluate_it(
    kind: RuleSetKind,
) -> None:
    """R-66 (9) over every field of the two approval kinds, every operator and a value of every
    type: the platform's verdict (``condition_errors``, as the rule upsert calls it) equals the
    matcher's behaviour on the facts a submission states. Before the ruling the platform accepted
    every operator on every field, and ``flags gte …`` made each submission raise."""
    accepted = refused = 0
    for field in FIELDS[kind]:
        for op in OPERATORS:
            for value in VALUES:
                condition = _condition(field, op, value)
                _, errors = rule_sets.condition_errors(kind, [condition])
                evaluates = _matcher_evaluates(kind, condition)
                assert (not errors) == evaluates, (field, op, value, errors)
                accepted += evaluates
                refused += not evaluates
    assert accepted and refused  # both verdicts occur: the comparison is not vacuous


def test_refusals_name_the_operator_or_the_value() -> None:
    """The finding sits on the member that is wrong, with copy that says what the field holds."""

    def finding(field: str, op: str, value: object) -> tuple[str, str]:
        _, errors = rule_sets.condition_errors(ROUTING, [_condition(field, op, value)])
        (error,) = errors
        return error.field, error.message

    assert finding("flags", "gte", "POSTED_LINES") == (
        "conditions[0].op",
        "flags holds a list of values. Compare it with eq or in.",
    )
    assert finding("entity.code", "prefix", "AVM") == (
        "conditions[0].op",
        "entity.code holds a list of values. Compare it with eq or in.",
    )
    assert finding("amount.functional", "prefix", "12") == (
        "conditions[0].op",
        "amount.functional holds a number. Compare it with eq, in, gte, lte or range.",
    )
    assert finding("amount.functional", "gte", "a lot") == (
        "conditions[0].value",
        "amount.functional holds a number. Enter a number as text.",
    )
    assert finding("subject.type", "eq", 7) == (
        "conditions[0].value",
        "subject.type holds text. Enter text.",
    )
    _, errors = rule_sets.condition_errors(
        AUTO, [_condition("tenant.setup_completed", "eq", "false")]
    )
    assert [(error.field, error.message) for error in errors] == [
        ("conditions[0].value", "tenant.setup_completed holds true or false. Enter true or false.")
    ]
    # Positive controls: the conditions the seeded and the demo rules use.
    for kind, field, op, value in (
        (ROUTING, "flags", "in", "ABOVE_THRESHOLD"),
        (ROUTING, "flags", "eq", "POSTED_LINES"),
        (ROUTING, "amount.functional", "gte", "1000000.00"),
        (ROUTING, "amount.functional", "lte", "-50000.00"),
        (ROUTING, "entity.code", "in", "AVM-US"),
        (ROUTING, "subject.type", "prefix", "CONTRACT_"),
        (AUTO, "tenant.setup_completed", "eq", False),
        (AUTO, "preparer.role_codes", "in", "tenant_admin"),
        (AUTO, "source.channel", "eq", "USER"),
    ):
        assert rule_sets.condition_errors(kind, [_condition(field, op, value)])[1] == []
    # A range keeps its open bound.
    open_range = {"field": "amount.functional", "op": "range", "value": [None, "50000.00"]}
    assert rule_sets.condition_errors(ROUTING, [open_range])[1] == []


def test_stored_conditions_are_judged_again_for_publication() -> None:
    """``evaluable_errors`` is the publication form: every stored condition, with the rule's
    prefix, so a rule that reached the table another way is not put in force."""
    stored = [
        _condition("subject.type", "eq", "CONTRACT_VOID"),
        _condition("flags", "lte", "POSTED_LINES"),
    ]
    (error,) = rule_sets.evaluable_errors(stored, prefix="rules[ROUTE-X].")
    assert (error.field, error.rule_id) == ("rules[ROUTE-X].conditions[1].op", "T-REF-26")
    assert rule_sets.evaluable_errors(stored[:1], prefix="rules[ROUTE-X].") == []


def test_entity_code_is_a_set_of_codes_on_both_paths() -> None:
    """R-66 (8): a submission states the codes of the request's entities; a case may state one
    code or a list, and both become the same fact — so a rule on ``entity.code`` answers alike in
    an evaluation and at a submission. Before the ruling a submission passed no entity at all."""
    submitted = routing.routing_facts(
        subject_type=ApprovalSubjectType.CONTRACT_VOID,
        entity_codes=["AVM-UK", "AVM-US"],
        amount_functional=None,
        flags=(),
    )
    assert submitted["entity.code"] == ("AVM-UK", "AVM-US")
    one, errors = rule_sets.facts_of(
        ROUTING, {"entity.code": "AVM-US"}, where="input", rule_id="T-REF-27"
    )
    assert (one["entity.code"], errors) == (("AVM-US",), [])
    several, errors = rule_sets.facts_of(
        ROUTING, {"entity.code": ["AVM-UK", "AVM-US"]}, where="input", rule_id="T-REF-27"
    )
    assert (several["entity.code"], errors) == (("AVM-UK", "AVM-US"), [])
    _, errors = rule_sets.facts_of(ROUTING, {"entity.code": 7}, where="input", rule_id="T-REF-27")
    assert [error.field for error in errors] == ["input.entity.code"]

    rule = {
        "id": USER,
        "rule_key": "ROUTE-UK",
        "priority": 0,
        "specificity": 2,
        "conditions": [
            _condition("subject.type", "eq", "CONTRACT_VOID"),
            _condition("entity.code", "eq", "AVM-UK"),
        ],
        "outputs": {
            "steps": [{"name": "UK review", "permission": "contract.approve", "min_approvers": 1}]
        },
    }

    def evaluated(facts: dict[str, object]) -> object:
        return rule_sets.evaluate(ROUTING, [rule], facts)["rule_key"]

    case = {"subject.type": "CONTRACT_VOID", **several}
    assert evaluated(case) == "ROUTE-UK"  # a request that names the entity among others
    assert evaluated({"subject.type": "CONTRACT_VOID", **one}) is None  # another entity
    # A tenant-level request names no entity: no condition on ``entity.code`` holds for it.
    tenant_level = routing.routing_facts(
        subject_type=ApprovalSubjectType.CONTRACT_VOID,
        entity_codes=(),
        amount_functional=None,
        flags=(),
    )
    assert evaluated(tenant_level) is None
    assert evaluated(dict(submitted)) == "ROUTE-UK"


def _person(on_behalf_of_id: UUID | None = None) -> Principal:
    return Principal(
        kind=PrincipalKind.USER,
        id=USER,
        tenant_id=TENANT,
        membership_id=None,
        display_name="Probe person",
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=on_behalf_of_id,
    )


def test_source_channel_is_the_origin_of_the_content() -> None:
    """R-66 (8), R-41 (7): the ``source.channel`` of a job that acts on behalf of a user is
    ``USER`` — it carries that person's content — so a case of channel ``SYSTEM`` is a job that
    acts for no user, in an evaluation as at a submission, and ONE function answers both."""
    assert engine.source_channel(system_principal(TENANT)) == "SYSTEM"
    assert engine.source_channel(system_principal(TENANT, on_behalf_of_id=USER)) == "USER"
    assert engine.source_channel(_person()) == "USER"

    def admitted(channel: str) -> bool:
        facts = routing.auto_approval_facts(
            subject_type=ApprovalSubjectType.CONTRACT_ACTIVATION,
            preparer_role_codes=(),
            setup_completed=True,
            source_channel=channel,
        )
        return routing.evaluation_admitted(AUTO, facts, rule_set_code=None)

    assert admitted(engine.source_channel(system_principal(TENANT)))
    assert not admitted(engine.source_channel(system_principal(TENANT, on_behalf_of_id=USER)))
    assert admitted("API_CLIENT") and not admitted("USER")


# --- R-38 (v): the two discriminating conditions of an AUTO_APPROVAL rule -------------------------

KIND_IS_BILLING: Final = {
    "field": "reconciliation.kind",
    "op": "eq",
    "value": "BILLING_TO_SUBLEDGER",
}
NO_VARIANCE: Final = {"field": "reconciliation.variance_count", "op": "eq", "value": 0}
AUTO_OUTPUT: Final = {"auto_approve": True}


def _stored(rule_key: str, conditions: list[dict[str, Any]], priority: int = 0) -> dict[str, Any]:
    """A stored rule as ``rule_sets.evaluate`` reads it."""
    return {
        "id": rule_key,
        "rule_key": rule_key,
        "priority": priority,
        "specificity": len({condition["field"] for condition in conditions}),
        "conditions": conditions,
        "outputs": dict(AUTO_OUTPUT),
    }


def test_an_auto_approval_rule_carries_one_of_two_discriminating_conditions() -> None:
    """Supervisor ruling R-38 (v): ``subject.type`` for the rules the approvals engine matches,
    ``reconciliation.kind`` for the auto-certification rules of BUILD_SPEC CLO-17. The rule check
    accepts a rule with either and refuses a rule with neither; the approvals engine reads only
    the first. Before the two lanes met, the check refused ``AUTO-REC-01``."""

    def errors(conditions: list[dict[str, Any]]) -> list[str]:
        found = rule_sets.approval_rule_errors(AUTO, conditions, AUTO_OUTPUT)
        return [error.message for error in found]

    certification = [KIND_IS_BILLING, NO_VARIANCE]
    assert errors(certification) == []
    assert routing.certifies(certification)
    assert not routing.admissible(AUTO, certification)  # no rule of the approvals engine
    # Neither discriminator: a reconciliation fact that is not the kind names nothing.
    assert errors([NO_VARIANCE]) == [rule_sets.SUBJECT_TYPE_REQUIRED]
    assert not routing.certifies([NO_VARIANCE])
    assert not routing.admissible(AUTO, [NO_VARIANCE])
    # The approvals side is unchanged: a subject type on the allow-list, and nothing else.
    import_commit = [{"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"}]
    assert errors(import_commit) == []
    assert routing.admissible(AUTO, import_commit)
    assert not routing.certifies(import_commit)
    period_lock = [{"field": "subject.type", "op": "eq", "value": "PERIOD_LOCK"}, KIND_IS_BILLING]
    assert errors(period_lock) == [rule_sets.NOT_AUTO_APPROVABLE.format(subjects="PERIOD_LOCK")]


def test_a_certification_case_is_answered_as_the_certification_reads_the_rule_set() -> None:
    """R-38 (v), evaluation equals the path that would read the rule set: a case that states
    ``reconciliation.kind`` is answered from the rules that carry that condition alone, and never
    matches with a variance — whatever a rule states (04 T-CLS-06 "Auto-certification"). A case
    of the approvals engine is never answered by a certification rule."""
    rules = [
        _stored("AUTO-REC-01", [KIND_IS_BILLING, NO_VARIANCE]),
        # Stored another way: names neither discriminator, so neither path reads it.
        _stored("AUTO-ANY-ZERO", [NO_VARIANCE], priority=50),
        # Certifies a billing reconciliation whatever its count says.
        _stored("AUTO-REC-ANY", [KIND_IS_BILLING], priority=-5),
        _stored(
            "AUTO-IMP-01",
            [
                {"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"},
                {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
            ],
        ),
    ]

    def certified(kind: str, variance_count: int | None) -> str | None:
        facts: dict[str, object] = {"reconciliation.kind": kind}
        if variance_count is not None:
            facts["reconciliation.variance_count"] = variance_count
        found = rule_sets.evaluate(AUTO, rules, facts)
        return found["rule_key"] if found["matched"] else None

    assert certified("BILLING_TO_SUBLEDGER", 0) == "AUTO-REC-01"
    # A variance is never certified, although AUTO-REC-ANY states no count.
    assert certified("BILLING_TO_SUBLEDGER", 1) is None
    assert certified("BILLING_TO_SUBLEDGER", None) == "AUTO-REC-ANY"
    assert certified("SUBLEDGER_TO_GL", 0) is None
    # The approvals engine's case: its own rule, never a certification rule or AUTO-ANY-ZERO.
    by_client = rule_sets.evaluate(
        AUTO,
        rules,
        routing.auto_approval_facts(
            subject_type=ApprovalSubjectType.IMPORT_COMMIT,
            preparer_role_codes=(),
            setup_completed=True,
            source_channel="API_CLIENT",
        ),
    )
    assert (by_client["matched"], by_client["rule_key"]) == (True, "AUTO-IMP-01")
    by_user = rule_sets.evaluate(
        AUTO,
        rules,
        routing.auto_approval_facts(
            subject_type=ApprovalSubjectType.IMPORT_COMMIT,
            preparer_role_codes=(),
            setup_completed=True,
            source_channel="USER",
        ),
    )
    assert by_user == dict(rule_sets.NO_MATCH)
