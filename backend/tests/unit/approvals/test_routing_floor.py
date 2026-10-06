"""The limits on approval rules as pure functions (04 T-REF-26 and §16.10 rev 1.104 "Auto-approval
and the routing floor"; dev-guide DG-KRN-APR-08; REQ-PLT-013, REQ-PLT-016; supervisor rulings R-26
on the security review's finding SN-9, R-38 and R-41 (7) on the lane's independent review).

(a) an approval rule without a condition never matches and an auto-approval rule names its subject
types; (b) the allow-list of system-originated standard items and the two subjects only their
seeded rule set approves; (c) the floor of the subject's own steps, counted as approvers per
permission and role. The evaluation of a case applies the same limits. The database-bound
witnesses — the authoring refusals and the enforcement at submission — are
``tests/domain/policies/test_rule_floor.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import quorum, routing, subjects
from erev_api.approvals.routing import FloorItem, StepPlan, apply_floor, floor_gaps
from erev_api.domain.demo.avenmoor import policies as demo
from erev_api.domain.policies import rule_sets
from erev_api.enums import ApprovalSubjectType, PrincipalKind, RuleSetKind

CONTROLLER = UUID("00000000-0000-0000-0000-0000000000c1")
REVIEWER = UUID("00000000-0000-0000-0000-0000000000c2")
_S = ApprovalSubjectType
_K = PrincipalKind


def _step(
    name: str, permission: str = "contract.approve", approvers: int = 1, role: UUID | None = None
) -> StepPlan:
    return StepPlan(name=name, permission=permission, min_approvers=approvers, role_id=role)


def _shape(steps: tuple[StepPlan, ...]) -> list[tuple[str, str, int, UUID | None]]:
    return [(step.name, step.permission, step.min_approvers, step.role_id) for step in steps]


# --- (c) the floor -------------------------------------------------------------------------------


def test_steps_that_meet_the_floor_are_kept_as_they_are() -> None:
    floor = (_step("Approval"),)
    for routed in (
        (_step("Revenue review"),),
        (_step("Revenue review", approvers=2),),  # more approvers
        (_step("Controller review", role=CONTROLLER),),  # a narrower step
        (_step("Revenue review"), _step("Second review", "judgement.review")),  # an added step
        (_step("First", "judgement.review"), _step("Revenue review")),  # an added step before
    ):
        assert apply_floor(routed, floor) == routed


def test_another_permission_does_not_replace_the_subjects_own_step() -> None:
    """The SN-9 exploit: ``PERIOD_REOPEN`` routed to one ``judgement.review`` holder. The subject's
    own step — two ``period.reopen_approve`` approvers — is put back in front of the rule's step."""
    floor = (_step("Approval", "period.reopen_approve", 2),)
    routed = (_step("Any reviewer", "judgement.review", 1),)
    assert _shape(apply_floor(routed, floor)) == [
        ("Approval", "period.reopen_approve", 2, None),
        ("Any reviewer", "judgement.review", 1, None),
    ]


def test_fewer_approvers_are_raised_in_place() -> None:
    floor = (_step("Approval", "period.reopen_approve", 2),)
    routed = (_step("Reopen approval", "period.reopen_approve", 1),)
    assert _shape(apply_floor(routed, floor)) == [
        ("Reopen approval", "period.reopen_approve", 2, None)
    ]


def test_second_step_and_its_role_are_part_of_the_floor() -> None:
    """PRD §2.5: a second step held by a Controller. A rule with one step gets the second step
    added; a rule whose second step names no role gets the role (the demo ``ROUTE-CON-02`` shape);
    a rule whose only step is the Controller's owes the open step, not a second Controller."""
    floor = (_step("Approval"), _step("Second approval", role=CONTROLLER))
    assert _shape(apply_floor((_step("Revenue review"),), floor)) == [
        ("Revenue review", "contract.approve", 1, None),
        ("Second approval", "contract.approve", 1, CONTROLLER),
    ]
    two = (_step("Revenue review"), _step("Controller approval"))
    assert _shape(apply_floor(two, floor)) == [
        ("Revenue review", "contract.approve", 1, None),
        ("Controller approval", "contract.approve", 1, CONTROLLER),
    ]
    only_controller = (_step("Controller approval", role=CONTROLLER),)
    assert _shape(apply_floor(only_controller, floor)) == [
        ("Approval", "contract.approve", 1, None),
        ("Controller approval", "contract.approve", 1, CONTROLLER),
    ]
    complete = (_step("Revenue review"), _step("Controller approval", role=CONTROLLER))
    assert apply_floor(complete, floor) == complete


def test_a_requirement_a_routed_step_already_meets_is_not_added_again() -> None:
    """R-41 (7): the floor is a number of approvers per permission and role, not a sequence — one
    decision per person per request makes every step another person. A rule that lists the
    Controller's step FIRST already meets the floor: one Controller can decide, and no second
    Controller step appears. One step of two approvers meets two floor steps of one approver
    each: no third approver is asked for."""
    floor = (_step("Approval"), _step("Second approval", role=CONTROLLER))
    controller_first = (_step("Controller step", role=CONTROLLER), _step("Revenue review"))
    assert apply_floor(controller_first, floor) == controller_first

    ssp_floor = (_step("Approval", "ssp.approve"), _step("Second approval", "ssp.approve"))
    two_in_one = (_step("SSP review", "ssp.approve", 2),)
    assert apply_floor(two_in_one, ssp_floor) == two_in_one

    # A step of two open approvers does not contain the Controller: the floor's step is added,
    # and one Controller suffices for it.
    assert _shape(apply_floor((_step("Two reviewers", approvers=2),), floor)) == [
        ("Two reviewers", "contract.approve", 2, None),
        ("Second approval", "contract.approve", 1, CONTROLLER),
    ]


def test_subjects_own_step_role_is_part_of_the_floor() -> None:
    """R-41 (7): PRD §2.5 ``PERIOD_LOCK`` "1: period.lock (Controller)". A rule whose lock step
    names no role gets the role in place; a step held by another role does not stand in for it."""
    floor = (_step("Approval", "period.lock", role=CONTROLLER),)
    assert _shape(apply_floor((_step("Lock review", "period.lock"),), floor)) == [
        ("Lock review", "period.lock", 1, CONTROLLER)
    ]
    other_role = (_step("Reviewer approval", "period.lock", role=REVIEWER),)
    assert _shape(apply_floor(other_role, floor)) == [
        ("Approval", "period.lock", 1, CONTROLLER),
        ("Reviewer approval", "period.lock", 1, REVIEWER),
    ]
    spec = subjects.SUBJECTS[_S.PERIOD_LOCK]
    assert spec.step_role == "controller"
    assert routing.floor_items(spec, ()) == [("Approval", "period.lock", 1, "controller")]
    estimate = subjects.SUBJECTS[_S.ESTIMATE_VERSION]
    assert routing.floor_items(estimate, [subjects.ESTIMATE_PL_IMPACT_FLAG]) == [
        ("Approval", "estimate.approve", 1, None),
        ("Second approval", "estimate.approve", 1, "controller"),
    ]
    assert routing.floor_items(estimate, ()) == [("Approval", "estimate.approve", 1, None)]


def test_a_step_held_by_another_role_does_not_stand_in_for_the_floors_role() -> None:
    floor = (_step("Approval", role=CONTROLLER),)
    routed = (_step("Reviewer approval", role=REVIEWER),)
    assert _shape(apply_floor(routed, floor)) == [
        ("Approval", "contract.approve", 1, CONTROLLER),
        ("Reviewer approval", "contract.approve", 1, REVIEWER),
    ]


def _items(steps: tuple[StepPlan, ...]) -> list[FloorItem]:
    return [(step.name, step.permission, step.min_approvers, step.role_id) for step in steps]


def test_floor_is_never_lowered_whatever_the_routed_steps() -> None:
    """Whatever a rule outputs, the result supplies every approver of the floor — counted as
    submission counts them — and no routed step is lost, reordered or asked for fewer approvers."""
    floor = (_step("Approval", approvers=2), _step("Second approval", role=CONTROLLER))
    shapes = (
        (),
        (_step("x", "judgement.review"),),
        (_step("x", approvers=1),),
        (_step("x", approvers=1), _step("y", approvers=1)),
        (_step("x", role=REVIEWER), _step("y", "event.approve", 3)),
        (_step("y", role=CONTROLLER), _step("x", approvers=5)),
        (_step("x", approvers=5), _step("y", approvers=5)),
    )
    for routed in shapes:
        raised = apply_floor(routed, floor)
        assert floor_gaps(_items(raised), _items(floor)) == [], routed
        assert len(raised) >= max(len(routed), 1)
        kept = [step for step in raised if step.name in {"x", "y"}]
        assert [step.name for step in kept] == [step.name for step in routed]
        for before, after in zip(routed, kept, strict=True):
            assert after.permission == before.permission
            assert after.min_approvers >= before.min_approvers
            assert before.role_id is None or after.role_id == before.role_id
        assert all(1 <= step.min_approvers <= routing.MAX_APPROVERS for step in raised)
        # Raising twice changes nothing: the raised steps already meet the floor.
        assert apply_floor(raised, floor) == raised


def test_floor_gaps_names_what_authoring_refuses() -> None:
    """``floor_gaps`` returns the indexes of the floor steps the rule's steps do not meet, counted
    like ``apply_floor`` and without raising anything."""
    reopen: list[FloorItem] = [("Approval", "period.reopen_approve", 2, None)]
    assert floor_gaps([("x", "judgement.review", 1, None)], reopen) == [0]
    assert floor_gaps([("x", "period.reopen_approve", 1, None)], reopen) == [0]
    assert floor_gaps([("x", "period.reopen_approve", 2, None)], reopen) == []
    assert floor_gaps([("x", "period.reopen_approve", 3, "controller")], reopen) == []
    # Two steps of one approver each are two approvers.
    split: list[FloorItem] = [
        ("x", "period.reopen_approve", 1, None),
        ("y", "period.reopen_approve", 1, None),
    ]
    assert floor_gaps(split, reopen) == []
    void: list[FloorItem] = [
        ("Approval", "contract.approve", 1, None),
        ("Second approval", "contract.approve", 1, "controller"),
    ]
    assert floor_gaps([("x", "contract.approve", 1, None)], void) == [1]
    assert floor_gaps(
        [("x", "contract.approve", 1, None), ("y", "contract.approve", 1, None)], void
    ) == [1]
    assert floor_gaps([("x", "contract.approve", 1, "controller")], void) == [0]
    for complete in (
        [("x", "contract.approve", 1, None), ("y", "contract.approve", 1, "controller")],
        [("y", "contract.approve", 1, "controller"), ("x", "contract.approve", 1, None)],
        [("y", "contract.approve", 2, "controller")],
    ):
        assert floor_gaps(complete, void) == [], complete


def test_raised_steps_of_rule_outputs_carry_role_codes() -> None:
    """The evaluation of a case raises the authored steps — role codes, not ids (R-41 (7))."""
    floor: list[FloorItem] = [
        ("Approval", "contract.approve", 1, None),
        ("Second approval", "contract.approve", 1, "controller"),
    ]
    authored = [{"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1}]
    assert routing.raised_steps(authored, floor) == [
        {"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1},
        {
            "name": "Second approval",
            "permission": "contract.approve",
            "min_approvers": 1,
            "role": "controller",
        },
    ]
    assert routing.raised_steps(authored, floor[:1]) == authored


def test_quorum_role_belongs_to_the_subjects_own_step() -> None:
    assert quorum.floor_role_required(_S.PERIOD_REOPEN) == quorum.CONTROLLER
    assert quorum.floor_role_required(_S.PERIOD_LOCK) is None
    assert quorum.floor_role_required(_S.CONTRACT_ACTIVATION) is None


# --- (a) rules that may match --------------------------------------------------------------------


def _condition(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def test_rule_without_a_condition_never_matches_an_approval_kind() -> None:
    for kind in (RuleSetKind.APPROVAL_ROUTING, RuleSetKind.AUTO_APPROVAL):
        assert not routing.admissible(kind, [])
    # The other kinds keep their unconditional rules (DQ-SYSTEM, a catch-all assignment).
    for kind in (RuleSetKind.DATA_QUALITY, RuleSetKind.POB_ASSIGNMENT, RuleSetKind.HOLD):
        assert routing.admissible(kind, [])


def test_kind_is_coerced_where_it_enters() -> None:
    """R-41 (7): the limits compare E-55 members by identity, so a kind spelt as its value — or as
    the engine's own enum of the same values — is the same kind, never an unlimited one."""
    from erev_engine.enums import RuleSetKind as EngineKind

    channel = [_condition("source.channel", "eq", "USER")]
    for spelt in ("AUTO_APPROVAL", RuleSetKind.AUTO_APPROVAL, EngineKind.AUTO_APPROVAL):
        assert routing.rule_set_kind(spelt) is RuleSetKind.AUTO_APPROVAL
        assert not routing.admissible(spelt, channel)
        assert not routing.admissible(spelt, [])
        assert [error.message for error in rule_sets.approval_rule_errors(spelt, channel, {})] == [
            rule_sets.SUBJECT_TYPE_REQUIRED
        ]
    assert [
        error.message
        for error in rule_sets.approval_rule_errors("APPROVAL_ROUTING", [], {"steps": []})
    ] == [rule_sets.CONDITION_REQUIRED]
    with pytest.raises(ValueError, match="NOT_A_KIND"):
        routing.rule_set_kind("NOT_A_KIND")


def test_auto_approval_rule_names_the_subject_types_it_covers() -> None:
    channel = _condition("source.channel", "eq", "API_CLIENT")
    subject = _condition("subject.type", "eq", "IMPORT_COMMIT")
    assert not routing.admissible(RuleSetKind.AUTO_APPROVAL, [channel])
    assert routing.admissible(RuleSetKind.AUTO_APPROVAL, [subject])
    assert routing.admissible(RuleSetKind.AUTO_APPROVAL, [subject, channel])
    # A prefix names nothing: it is no list of subject types.
    assert not routing.admissible(
        RuleSetKind.AUTO_APPROVAL, [_condition("subject.type", "prefix", "PERIOD")]
    )
    # A routing rule may key on an amount alone; its steps then face every subject's floor.
    assert routing.admissible(
        RuleSetKind.APPROVAL_ROUTING, [_condition("amount.functional", "gte", "1000000.00")]
    )


def test_named_subject_types_and_guaranteed_flags() -> None:
    both = [
        _condition("subject.type", "in", ["CONTRACT_VOID", "CONTRACT_ACTIVATION"]),
        _condition("subject.type", "eq", "CONTRACT_VOID"),
        _condition("flags", "eq", "POSTED_LINES"),
        _condition("flags", "in", ["ABOVE_THRESHOLD", "METHODOLOGY_CHANGE"]),
    ]
    assert routing.named_subject_types(both) == frozenset({"CONTRACT_VOID"})
    assert routing.named_subject_types([_condition("flags", "eq", "POSTED_LINES")]) is None
    assert routing.guaranteed_flags(both) == [
        frozenset({"POSTED_LINES"}),
        frozenset({"ABOVE_THRESHOLD", "METHODOLOGY_CHANGE"}),
    ]


# --- (b) the allow-list --------------------------------------------------------------------------


def test_allow_list_is_the_one_the_documents_name() -> None:
    """04 §16.10 rev 1.104: two subject types a tenant's rule may approve, each with the principal
    kinds that originate it, and two subjects only their seeded rule set approves. A change here
    is a documented row first."""
    assert dict(routing.AUTO_APPROVABLE) == {
        _S.CONTRACT_ACTIVATION: frozenset({_K.API_CLIENT, _K.SYSTEM}),
        _S.IMPORT_COMMIT: frozenset({_K.API_CLIENT}),
    }
    assert dict(routing.SEEDED_RULE_SETS) == {
        _S.ROLE_ASSIGNMENT: "AUTO-BOOTSTRAP",
        _S.MIGRATION_SSP_REPLAY: "AUTO-MIG-01",
    }
    assert (routing.AUTO_BOOTSTRAP, routing.BOOTSTRAP_ROLE) == ("AUTO-BOOTSTRAP", "tenant_admin")
    assert routing.seeded_rule_set(_S.ROLE_ASSIGNMENT) == "AUTO-BOOTSTRAP"
    assert routing.seeded_rule_set(_S.IMPORT_COMMIT) is None


def _admitted(subject: _S, kind: _K, *, on_behalf_of_id: UUID | None = None) -> bool:
    return routing.auto_approval_admitted(
        subject, principal_kind=kind, on_behalf_of_id=on_behalf_of_id
    )


def test_only_system_originated_standard_items_are_auto_approvable() -> None:
    assert _admitted(_S.CONTRACT_ACTIVATION, _K.API_CLIENT)
    assert _admitted(_S.CONTRACT_ACTIVATION, _K.SYSTEM)
    assert _admitted(_S.IMPORT_COMMIT, _K.API_CLIENT)
    # The same items prepared by a person — or by an operator — wait for a person.
    assert not _admitted(_S.CONTRACT_ACTIVATION, _K.USER)
    assert not _admitted(_S.IMPORT_COMMIT, _K.USER)
    assert not _admitted(_S.IMPORT_COMMIT, _K.SYSTEM)
    assert not _admitted(_S.CONTRACT_ACTIVATION, _K.OPERATOR)
    # The kind may arrive as its value (the source channel of a case).
    assert routing.auto_approval_admitted(_S.IMPORT_COMMIT, principal_kind="API_CLIENT")


def test_system_is_system_originated_only_on_behalf_of_no_user() -> None:
    """R-41 (7): a job a person started runs as SYSTEM on that person's behalf and carries their
    content; it is no system-originated preparer."""
    assert _admitted(_S.CONTRACT_ACTIVATION, _K.SYSTEM, on_behalf_of_id=None)
    assert not _admitted(_S.CONTRACT_ACTIVATION, _K.SYSTEM, on_behalf_of_id=uuid4())
    # An API client acts for itself; the member is not read for it.
    assert _admitted(_S.CONTRACT_ACTIVATION, _K.API_CLIENT, on_behalf_of_id=None)


@pytest.mark.parametrize(
    "subject", sorted(set(_S) - set(routing.AUTO_APPROVABLE), key=lambda s: s.value)
)
def test_no_other_subject_is_auto_approvable_for_anyone(subject: _S) -> None:
    """R-26 (b): a rule set of any kind, every other configuration subject, the access subjects,
    period lock and reopen, a journal run — and the two seeded-only subjects, which the allow-list
    of tenant rules never admits — for every principal kind."""
    for kind in _K:
        assert not _admitted(subject, kind), (subject, kind)


def _auto_facts(subject: str, channel: str, **more: Any) -> dict[str, Any]:
    return {"subject.type": subject, "source.channel": channel, **more}


def test_evaluation_of_a_case_applies_the_allow_list() -> None:
    """R-41 (7): the evaluate / example-case path reports a match only where a submission with the
    same facts would read the rule."""
    auto = RuleSetKind.AUTO_APPROVAL
    admitted = routing.evaluation_admitted
    assert admitted(auto, _auto_facts("IMPORT_COMMIT", "API_CLIENT"), rule_set_code="ANY")
    assert not admitted(auto, _auto_facts("IMPORT_COMMIT", "USER"), rule_set_code="ANY")
    assert not admitted(auto, _auto_facts("RULE_SET_VERSION", "API_CLIENT"), rule_set_code="ANY")
    assert not admitted(auto, {"subject.type": "IMPORT_COMMIT"}, rule_set_code="ANY")
    assert not admitted(auto, {"source.channel": "API_CLIENT"}, rule_set_code="ANY")
    # A seeded-only subject matches in its own seeded rule set alone.
    replay = _auto_facts("MIGRATION_SSP_REPLAY", "USER")
    assert admitted(auto, replay, rule_set_code="AUTO-MIG-01")
    assert not admitted(auto, replay, rule_set_code="AUTO_APPROVAL")
    assert not admitted(auto, replay, rule_set_code=None)
    grant = _auto_facts(
        "ROLE_ASSIGNMENT",
        "USER",
        **{"preparer.role_codes": ("tenant_admin",), "tenant.setup_completed": False},
    )
    assert admitted(auto, grant, rule_set_code="AUTO-BOOTSTRAP")
    assert not admitted(auto, grant, rule_set_code="SEC-AUTO")
    assert not admitted(
        auto, {**grant, "tenant.setup_completed": True}, rule_set_code="AUTO-BOOTSTRAP"
    )
    assert not admitted(
        auto, {**grant, "preparer.role_codes": ("controller",)}, rule_set_code="AUTO-BOOTSTRAP"
    )
    # Provisioning records the bootstrap admin's own grant on the OPERATOR channel and reads the
    # seeded rule for it: the evaluation of that case agrees. No other channel is admitted, and
    # the legacy SSP replay is a user's request only.
    by_operator = {**grant, "source.channel": "OPERATOR"}
    assert admitted(auto, by_operator, rule_set_code="AUTO-BOOTSTRAP")
    assert not admitted(auto, by_operator, rule_set_code="SEC-AUTO")
    for channel in ("API_CLIENT", "SYSTEM"):
        assert not admitted(
            auto, {**grant, "source.channel": channel}, rule_set_code="AUTO-BOOTSTRAP"
        )
    assert not admitted(
        auto, _auto_facts("MIGRATION_SSP_REPLAY", "OPERATOR"), rule_set_code="AUTO-MIG-01"
    )
    # Every other kind is evaluated as written.
    assert admitted(RuleSetKind.APPROVAL_ROUTING, {}, rule_set_code=None)
    assert admitted(RuleSetKind.DATA_QUALITY, {}, rule_set_code=None)


def test_evaluation_of_a_routing_case_returns_the_steps_as_raised() -> None:
    """R-41 (7): a routing case shows the steps a submission with its facts gets — the rule's
    steps raised to the own steps of the subject type it names, with the second step when the case
    carries one of the subject's second-step flags."""
    one = {
        "steps": [{"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1}]
    }
    plain = {"subject.type": "CONTRACT_VOID", "flags": ()}
    assert routing.evaluated_outputs(RuleSetKind.APPROVAL_ROUTING, plain, one) == one
    posted = {"subject.type": "CONTRACT_VOID", "flags": ("POSTED_LINES",)}
    assert routing.evaluated_outputs(RuleSetKind.APPROVAL_ROUTING, posted, one)["steps"] == [
        {"name": "Revenue review", "permission": "contract.approve", "min_approvers": 1},
        {
            "name": "Second approval",
            "permission": "contract.approve",
            "min_approvers": 1,
            "role": "controller",
        },
    ]
    # A case without a subject type, and every other kind, is returned as written.
    assert routing.evaluated_outputs(RuleSetKind.APPROVAL_ROUTING, {}, one) == one
    auto = {"auto_approve": True}
    assert routing.evaluated_outputs(RuleSetKind.AUTO_APPROVAL, plain, auto) == auto

    rule = {
        "id": uuid4(),
        "rule_key": "VOID",
        "priority": 0,
        "specificity": 1,
        "conditions": [_condition("subject.type", "eq", "CONTRACT_VOID")],
        "outputs": one,
    }
    found = rule_sets.evaluate(RuleSetKind.APPROVAL_ROUTING, [rule], posted)
    assert found["matched"] is True and len(found["outputs"]["steps"]) == 2
    # The kind is coerced at entry: its E-55 value answers as the member does.
    assert rule_sets.evaluate("APPROVAL_ROUTING", [rule], posted) == found
    auto_rule = {
        **rule,
        "rule_key": "AUTO",
        "conditions": [_condition("subject.type", "eq", "IMPORT_COMMIT")],
        "outputs": auto,
    }
    by_client = rule_sets.evaluate(
        RuleSetKind.AUTO_APPROVAL, [auto_rule], _auto_facts("IMPORT_COMMIT", "API_CLIENT")
    )
    by_user = rule_sets.evaluate(
        RuleSetKind.AUTO_APPROVAL, [auto_rule], _auto_facts("IMPORT_COMMIT", "USER")
    )
    assert (by_client["matched"], by_client["rule_key"]) == (True, "AUTO")
    assert by_user == dict(rule_sets.NO_MATCH)


# --- authoring -----------------------------------------------------------------------------------


def _errors(kind: RuleSetKind, conditions: list[Any], outputs: dict[str, Any]) -> list[str]:
    return [
        f"{error.field}: {error.message}"
        for error in rule_sets.approval_rule_errors(kind, conditions, outputs)
    ]


def _steps(*steps: tuple[str, int] | tuple[str, int, str]) -> dict[str, Any]:
    rows = []
    for index, step in enumerate(steps, start=1):
        row: dict[str, Any] = {
            "name": f"Step {index}",
            "permission": step[0],
            "min_approvers": step[1],
        }
        if len(step) == 3:
            row["role"] = step[2]
        rows.append(row)
    return {"steps": rows}


def test_authoring_refuses_an_unconditional_approval_rule() -> None:
    expected = [f"conditions: {rule_sets.CONDITION_REQUIRED}"]
    assert _errors(RuleSetKind.AUTO_APPROVAL, [], {"auto_approve": True}) == expected
    assert _errors(RuleSetKind.APPROVAL_ROUTING, [], _steps(("config.approve", 1))) == expected
    assert _errors(RuleSetKind.DATA_QUALITY, [], {"severity": "ERROR", "message": "m"}) == []


def test_authoring_refuses_an_auto_approval_rule_outside_the_allow_list() -> None:
    auto = {"auto_approve": True}
    channel = _condition("source.channel", "eq", "USER")
    assert _errors(RuleSetKind.AUTO_APPROVAL, [channel], auto) == [
        f"conditions: {rule_sets.SUBJECT_TYPE_REQUIRED}"
    ]
    for refused in (
        "RULE_SET_VERSION",
        "ROLE_ASSIGNMENT",
        "PERIOD_REOPEN",
        "REGISTRY_VERSION",
        # R-41 (7): only its seeded rule set approves the legacy SSP replay.
        "MIGRATION_SSP_REPLAY",
    ):
        found = _errors(
            RuleSetKind.AUTO_APPROVAL,
            [_condition("subject.type", "in", ["IMPORT_COMMIT", refused]), channel],
            auto,
        )
        assert found == ["conditions: " + rule_sets.NOT_AUTO_APPROVABLE.format(subjects=refused)], (
            refused
        )
    for admitted in ("CONTRACT_ACTIVATION", "IMPORT_COMMIT"):
        assert (
            _errors(RuleSetKind.AUTO_APPROVAL, [_condition("subject.type", "eq", admitted)], auto)
            == []
        )


def test_authoring_refuses_a_routing_rule_below_the_subjects_own_steps() -> None:
    reopen = [_condition("subject.type", "eq", "PERIOD_REOPEN")]
    routing_kind = RuleSetKind.APPROVAL_ROUTING
    (lowered,) = _errors(routing_kind, reopen, _steps(("judgement.review", 1)))
    assert lowered.startswith("outputs.steps: This rule lowers the approval of PERIOD_REOPEN.")
    assert "period.reopen_approve and at least 2 approvers" in lowered
    assert len(_errors(routing_kind, reopen, _steps(("period.reopen_approve", 1)))) == 1
    assert _errors(routing_kind, reopen, _steps(("period.reopen_approve", 2))) == []
    assert (
        _errors(routing_kind, reopen, _steps(("period.reopen_approve", 2), ("judgement.review", 1)))
        == []
    )

    # A rule that pins a second-step flag owes the second step with its role.
    posted = [
        _condition("subject.type", "eq", "CONTRACT_VOID"),
        _condition("flags", "eq", "POSTED_LINES"),
    ]
    (second,) = _errors(routing_kind, posted, _steps(("contract.approve", 1)))
    assert second == "outputs.steps: " + rule_sets.FLOOR_SECOND_STEP.format(
        subject="CONTRACT_VOID",
        permission="contract.approve",
        approvers=1,
        approver_word="approver",
        role=rule_sets.FLOOR_ROLE.format(role="controller"),
    )
    # The Controller's step first, the open step second: the same two approvers (R-41 (7)).
    assert (
        _errors(
            routing_kind,
            posted,
            _steps(("contract.approve", 1, "controller"), ("contract.approve", 1)),
        )
        == []
    )
    assert (
        _errors(
            routing_kind,
            posted,
            _steps(("contract.approve", 1), ("contract.approve", 1, "controller")),
        )
        == []
    )
    # Without the pin the second step depends on the request: enforced at submission.
    assert _errors(routing_kind, posted[:1], _steps(("contract.approve", 1))) == []

    # A rule that names no item type reaches every subject: one finding, not one per subject.
    (every,) = _errors(
        routing_kind,
        [_condition("amount.functional", "gte", "1000000.00")],
        _steps(("contract.approve", 1)),
    )
    assert every.startswith("outputs.steps: This rule reaches every item type")


def test_every_floor_is_the_subject_specifications_own_step() -> None:
    """The floor authoring judges is read from ``SubjectSpec``: one step with the subject's
    permission and approver count — and its step role, where it names one — for every registered
    subject."""
    with_role = set()
    for subject_type, spec in subjects.SUBJECTS.items():
        conditions = [_condition("subject.type", "eq", subject_type.value)]
        step: tuple[str, int] | tuple[str, int, str] = (
            (spec.required_permission, spec.min_approvers)
            if spec.step_role is None
            else (spec.required_permission, spec.min_approvers, spec.step_role)
        )
        assert _errors(RuleSetKind.APPROVAL_ROUTING, conditions, _steps(step)) == [], subject_type
        if spec.min_approvers > 1:
            fewer = _steps((spec.required_permission, spec.min_approvers - 1))
            assert len(_errors(RuleSetKind.APPROVAL_ROUTING, conditions, fewer)) == 1
        if spec.step_role is not None:
            with_role.add(subject_type)
            without = _steps((spec.required_permission, spec.min_approvers))
            (finding,) = _errors(RuleSetKind.APPROVAL_ROUTING, conditions, without)
            assert f"held by the role {spec.step_role}" in finding
    # PRD §2.5 "1: period.lock (Controller)" and, since rev 1.71, "1: config.approve held by a
    # Controller" of ``EVIDENCE_SHRED`` (R-49 (a)) are the step roles of the registered subjects.
    assert with_role == {_S.PERIOD_LOCK, _S.EVIDENCE_SHRED}


def test_demo_rule_sets_pass_authoring() -> None:
    """The published rules of the sample world (PRD §2.5; ``demo.avenmoor.policies``) are valid
    under R-26: every routing rule keeps its subjects' own steps and every auto-approval rule names
    an allow-listed subject type."""
    for rule in demo.ROUTING_RULES:
        found = _errors(
            RuleSetKind.APPROVAL_ROUTING, demo.routing_conditions(rule), demo.routing_outputs(rule)
        )
        assert found == [], (rule.rule_key, found)
    for auto in demo.AUTO_RULES:
        found = _errors(
            RuleSetKind.AUTO_APPROVAL, demo.auto_conditions(auto), {"auto_approve": True}
        )
        assert found == [], (auto.rule_key, found)
        assert auto.source_channel in {
            kind.value for kind in routing.AUTO_APPROVABLE[auto.subject]
        }, auto.rule_key
    # The sample world's auto-approval set holds the two tenant rules; the legacy SSP replay is
    # approved by the rule set provisioning seeds (04 §14.3 item 2), never by a rule of this set.
    assert [auto.rule_key for auto in demo.AUTO_RULES] == ["AUTO-CON-01", "AUTO-IMP-01"]


def test_seeded_approval_rule_sets_are_named_by_kind_and_code() -> None:
    """04 §14.3 item 2: the two rule sets provisioning seeds for the seeded-only subjects. A
    tenant creates no further version of them (``commands.create_rule_set_version``); a rule set
    of another kind, or a tenant's own auto-approval set, is no seeded set."""
    seeded = rule_sets.is_seeded_approval_set
    assert seeded(RuleSetKind.AUTO_APPROVAL, "AUTO-BOOTSTRAP")
    assert seeded("AUTO_APPROVAL", "AUTO-MIG-01")
    assert not seeded(RuleSetKind.AUTO_APPROVAL, "AVM-AUTO-APPROVAL")
    assert not seeded(RuleSetKind.APPROVAL_ROUTING, "AUTO-BOOTSTRAP")
    assert not seeded(RuleSetKind.DATA_QUALITY, "DQ-SYSTEM")


@pytest.mark.parametrize(
    ("ranked", "winners", "unruled"),
    [
        # No rule meets the other facts: the subject's own steps are the only outcome.
        ([], [], True),
        # The best rule needs no amount: it wins whatever the amount is.
        ([(False, "A"), (True, "B")], ["A"], False),
        # Two thresholds above a rule that needs no amount: each could win, nothing below can.
        (
            [(True, "HIGH"), (True, "LOW"), (False, "ANY"), (True, "LOWER")],
            ["HIGH", "LOW", "ANY"],
            False,
        ),
        # Every rule needs the amount: an amount none of them meets leaves the subject's own steps.
        ([(True, "HIGH"), (True, "LOW")], ["HIGH", "LOW"], True),
    ],
)
def test_r109_an_unknown_amount_reaches_every_rule_that_could_win(
    ranked: list[tuple[bool, str]], winners: list[str], unruled: bool
) -> None:
    """Item IMP-FLOOR-AMOUNT-1 (supervisor ruling R-109 (d)): with the amount unknown, every rule
    the other facts meet could route the request — down to and including the best-ranked rule
    that states no condition on the amount, below which nothing can win."""
    assert routing.possible_winners(ranked) == (winners, unruled)
