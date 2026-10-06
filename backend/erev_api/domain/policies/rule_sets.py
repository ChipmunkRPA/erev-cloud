"""Rule set authoring rules (04 T-REF-24 to T-REF-27, §14.1 DB-04, §16.2 API-S-VersionSummary;
PRD SM-04; REQ-POL-002, REQ-POL-003; BUILD_SPEC RFD-4).

A rule set (T-REF-24) is a decision table of one E-55 kind. Its versions (T-REF-25) hold rules
(T-REF-26) and example cases (T-REF-27), which change only while the version is DRAFT or TESTED
(DB-04). ``condition_errors`` checks each condition against ``erev_engine.rules.FIELDS`` and returns
the specificity the engine verifies when it evaluates; ``output_errors`` checks the kind-specific
outputs; ``facts_of`` turns the JSON facts of an example case or an evaluation into the types the
engine compares (decimals from text, dates from ISO text).

RFD-5: ``lint_findings`` reports each pair of rules with equal specificity and priority that can
match the same item (REQ-POL-002); ``evaluate`` runs ``erev_engine.rules.match``; ``run_case``
checks an example case against the evaluation; ``RULE_SET_VERSION_KIND`` hands rule set versions to
the configuration lifecycle, whose approval callbacks this module registers when it is imported.

``approval_rule_errors`` (supervisor ruling R-26 on the security review's finding SN-9; 04 T-REF-26
rev 1.104; dev-guide DG-KRN-APR-08) refuses, at the rule upsert and again at publication, the
``APPROVAL_ROUTING`` and ``AUTO_APPROVAL`` rules that would lower a subject's own approval: a rule
without a condition, an auto-approval rule that does not name the subject types it covers or names
one a person always approves, and a routing rule whose steps fall below the subject specification's
own steps. The approval engine enforces the same three limits at submission
(``erev_api.approvals.routing``), so a rule that reached the table another way changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.rules import FIELDS, OPERATORS, match, validate_conditions
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals import routing, subjects
from erev_api.auth.permissions import spec as permission_spec
from erev_api.db.tables import (
    approval_request,
    role,
    rule,
    rule_set,
    rule_set_version,
    rule_test_case,
)
from erev_api.domain.policies import lifecycle, simulation
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, ConfigStatus, RuleSetKind
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

OBJECT_RULE_SET: Final = "rule_set"
OBJECT_VERSION: Final = "rule_set_version"
OBJECT_RULE: Final = "rule"
OBJECT_TEST_CASE: Final = "rule_test_case"
SUBJECT_TYPE: Final = "rule_set_version"  # T-REF-27 `subject_type` of a rule set version
RULE_SET_RULE: Final = "T-REF-24"
RULE_RULE: Final = "T-REF-26"
RULE_TEST_CASE: Final = "T-REF-27"
RULE_FROZEN: Final = "DB-04"
RULE_OPEN_VERSION: Final = "SM-04"
EDITABLE: Final = frozenset({ConfigStatus.DRAFT.value, ConfigStatus.TESTED.value})
# [J] One version of a set is worked on at a time, as for SoD rule versions (SPEC-Q-184).
OPEN_STATUSES: Final = frozenset(
    {
        ConfigStatus.DRAFT.value,
        ConfigStatus.TESTED.value,
        ConfigStatus.SUBMITTED.value,
        ConfigStatus.APPROVED.value,
    }
)
LABEL_LENGTH: Final = 400  # TY-07
MEMO_LENGTH: Final = 4000  # TY-08
MAX_STEPS: Final = 10  # [J] the documents set no limit on routed steps
MAX_WINDOW_DAYS: Final = 3660  # [J] ten years
EXPECTED_MEMBERS: Final = frozenset({"matched", "rule_key", "outputs"})
MATCH_KINDS: Final = frozenset({"same_customer", "related_party"})
HOLD_LEVELS: Final = frozenset({"contract", "obligation"})
DATA_QUALITY_SEVERITIES: Final = frozenset({"ERROR", "WARNING"})  # 04 Table 15.4-E

# T-REF-26 `outputs` members per kind.
OUTPUT_MEMBERS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        RuleSetKind.POB_ASSIGNMENT: frozenset({"pob_template_code"}),
        RuleSetKind.SSP_ASSIGNMENT: frozenset({"ssp_book_code"}),
        RuleSetKind.APPROVAL_ROUTING: frozenset({"steps"}),
        RuleSetKind.AUTO_APPROVAL: frozenset({"auto_approve"}),
        RuleSetKind.COMBINATION_DETECTION: frozenset({"window_days", "match"}),
        RuleSetKind.HOLD: frozenset({"hold_type", "level"}),
        RuleSetKind.DATA_QUALITY: frozenset({"severity", "message"}),
    }
)

# Fact types of the `erev_engine.rules.FIELDS` names; every other field holds text.
DECIMAL_FACTS: Final = frozenset({"amount.functional", "reconciliation.unexplained_other_amount"})
INTEGER_FACTS: Final = frozenset({"reconciliation.variance_count"})
# The count the certification of a reconciliation reads before any rule (04 T-CLS-06
# "Auto-certification": a variance is never certified whatever a rule states).
RECONCILIATION_VARIANCE_FACT: Final = "reconciliation.variance_count"
DATE_FACTS: Final = frozenset({"effective_date"})
BOOLEAN_FACTS: Final = frozenset({"tenant.setup_completed"})
LIST_FACTS: Final = frozenset({"flags", "preparer.role_codes"})
# A set of codes that a case may state as one code (04 T-REF-26 rev 1.104; R-66 (8)): a request
# names every legal entity of its subject, a case usually one.
CODE_SET_FACTS: Final = frozenset({"entity.code"})

_DECIMAL: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")  # ASCII digits only (D-78)
_ISO_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CODE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}")  # TY-06
_INVALID: Final = object()

# [J] Copy the documents leave open, in the PRD §5.5 tone.
CODE_TAKEN: Final = "A rule set with this code already exists."
FIELD_NOT_ALLOWED: Final = "Choose a condition field that this rule set kind allows."
OPERATOR_UNKNOWN: Final = "Choose one of eq, in, range, prefix, gte or lte."
VALUE_INVALID: Final = "Enter a value that suits the operator."
# 04 T-REF-26 rev 1.104 (supervisor ruling R-66 (9)): what the matcher can evaluate on a field.
OPERATOR_NOT_FOR_FIELD: Final = "{field} holds {holds}. Compare it with {operators}."
VALUE_NOT_FOR_FIELD: Final = "{field} holds {holds}. Enter {enter}."
DECIMAL_AS_TEXT: Final = "Enter decimal numbers as text, for example 100000.00."
OUTPUTS_SHAPE: Final = "Give exactly these outputs: {members}."
CODE_INVALID: Final = "Enter a code of letters, digits and the characters _ . : / # ( ) + -."
AUTO_APPROVE_TRUE: Final = "Set auto_approve to true."
WINDOW_DAYS: Final = "Enter a whole number of days from 0 to 3660."
MATCH_KIND: Final = "Choose same_customer or related_party."
HOLD_LEVEL: Final = "Choose contract or obligation."
SEVERITY: Final = "Choose ERROR or WARNING."
MESSAGE_TEXT: Final = "Enter a message of at most 4000 characters."
STEPS_COUNT: Final = "Add between 1 and 10 approval steps."
STEP_SHAPE: Final = (
    "Give each step exactly a name, a permission and min_approvers, and at most a role."
)
STEP_ROLE: Final = "Enter the code of the role every approver of this step must hold."
# 04 T-REF-26 (lane F-CTR record §6 item 7 ruling): the role must exist and be active at the rule
# upsert and at publication; the submission keeps its own fail-closed check.
STEP_ROLE_UNKNOWN: Final = "No active role has the code {code}; choose an existing active role."
STEP_NAME: Final = "Enter a step name of at most 400 characters."
STEP_PERMISSION: Final = "Choose an approval permission from the catalogue."
STEP_APPROVERS: Final = "Choose between 1 and 5 approvers."
# R-26 (a), (b), (c): the refusals of ``approval_rule_errors``.
CONDITION_REQUIRED: Final = (
    "Add at least one condition. A rule without conditions would apply to every item."
)
SUBJECT_TYPE_REQUIRED: Final = (
    "Name what this rule covers: add a subject.type condition with eq or in for the item types "
    "it approves, or a reconciliation.kind condition for the reconciliations it certifies."
)
NOT_AUTO_APPROVABLE: Final = (
    "A rule cannot auto-approve these item types: {subjects}. "
    "Auto-approval rules cover contract activations and import commits sent by an integration."
)
FLOOR_LOWERED: Final = (
    "This rule lowers the approval of {subject}. Keep a step with permission {permission} "
    "and at least {approvers} {approver_word}{role}; a routing rule can add steps or raise "
    "them."
)
FLOOR_SECOND_STEP: Final = (
    "This rule lowers the approval of {subject}: the items it matches take a second step with "
    "permission {permission} and at least {approvers} {approver_word}{role}. Keep both steps; a "
    "routing rule can add steps or raise them."
)
FLOOR_ROLE: Final = ", held by the role {role}"
FLOOR_EVERY_SUBJECT: Final = (
    "This rule reaches every item type and lowers the approval of {count} of them. Name the item "
    "types it routes with a subject.type condition (eq or in), and keep each one's own step."
)
VERSION_FROZEN: Final = "This version is no longer a draft, so it cannot change."
VERSION_OPEN: Final = "Another version of this rule set is open. Finish it or withdraw it first."
SEEDED_SET: Final = (
    "Rule set {code} is provisioned with every workspace and cannot be changed. "
    "It takes no further version."
)
SOURCE_UNKNOWN: Final = "Choose a version of this rule set to copy."
NAME_EMPTY: Final = "Enter a name."
FACT_UNKNOWN: Final = "Use only the condition fields of this rule set kind."
FACT_INVALID: Final = (
    "Enter a value of the field's type: text, a decimal as text, a date or a list."
)
EXPECTED_SHAPE: Final = "Expect at least one of matched, rule_key and outputs, and nothing else."
EXPECTED_MATCHED: Final = "Set matched to true or false."
EXPECTED_RULE_KEY: Final = "Enter the expected rule key, or null for no match."
EXPECTED_OUTPUTS: Final = "Enter the expected outputs as an object, or null for no match."


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, list | tuple):
        return any(_contains_float(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class _FactType:
    """What ``erev_engine.rules`` can evaluate on the fact of a condition field: the operators
    that apply to it and the operands it compares with."""

    holds: str  # copy: "<field> holds <holds>"
    operators: tuple[str, ...]
    enter: str  # copy: "Enter <enter>"
    operand: Callable[[Any], bool]


def _is_text(value: Any) -> bool:
    return isinstance(value, str)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and bool(_DECIMAL.fullmatch(value)))


def _is_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


_ORDERED: Final = ("eq", "in", "gte", "lte", "range")
_TEXT_FACT: Final = _FactType("text", OPERATORS, "text", _is_text)
_LIST_FACT: Final = _FactType("a list of values", ("eq", "in"), "text", _is_text)
_BOOLEAN_FACT: Final = _FactType(
    "true or false", ("eq", "in"), "true or false", lambda value: isinstance(value, bool)
)
_NUMBER_FACT: Final = _FactType("a number", _ORDERED, "a number as text", _is_number)
_DATE_FACT: Final = _FactType("a date", _ORDERED, "a date as YYYY-MM-DD", _is_date)


def _fact_type(name: str) -> _FactType:
    """The type of the fact ``_fact`` builds for ``name`` — and a submission states."""
    if name in LIST_FACTS | CODE_SET_FACTS:
        return _LIST_FACT
    if name in BOOLEAN_FACTS:
        return _BOOLEAN_FACT
    if name in DECIMAL_FACTS | INTEGER_FACTS:
        return _NUMBER_FACT
    if name in DATE_FACTS:
        return _DATE_FACT
    return _TEXT_FACT


def evaluable_error(condition: Mapping[str, Any], *, where: str) -> ProblemError | None:
    """The finding on a condition the matcher cannot evaluate on its field's fact (04 T-REF-26 rev
    1.104; supervisor ruling R-66 (9)): an operator that does not apply to the fact's type — an
    ordering or a prefix on a list or on true / false, a prefix on a number or a date — or an
    operand of another type. ``erev_engine.rules.match`` raises on such a rule for every fact it
    meets, so every request that reads the rule set would be refused, the one that publishes its
    correction included. Refused where the rule is written and again at publication; the engine
    is unchanged. Called for a condition whose shape ``validate_conditions`` accepted."""
    name, op, value = str(condition["field"]), str(condition["op"]), condition["value"]
    found = _fact_type(name)
    if op not in found.operators:
        message = OPERATOR_NOT_FOR_FIELD.format(
            field=name,
            holds=found.holds,
            operators=", ".join(found.operators[:-1]) + " or " + found.operators[-1],
        )
        return ProblemError(field=f"{where}.op", rule_id=RULE_RULE, message=message)
    operands = list(value) if op in ("in", "range") else [value]
    if all(found.operand(operand) or (op == "range" and operand is None) for operand in operands):
        return None
    message = VALUE_NOT_FOR_FIELD.format(field=name, holds=found.holds, enter=found.enter)
    return ProblemError(field=f"{where}.value", rule_id=RULE_RULE, message=message)


def evaluable_errors(
    conditions: Sequence[Mapping[str, Any]], *, prefix: str = ""
) -> list[ProblemError]:
    """``evaluable_error`` over the stored conditions of a rule, for publication."""
    findings = (
        evaluable_error(condition, where=f"{prefix}conditions[{index}]")
        for index, condition in enumerate(conditions)
    )
    return [finding for finding in findings if finding is not None]


def condition_errors(
    kind: RuleSetKind, conditions: Sequence[Mapping[str, Any]]
) -> tuple[int, list[ProblemError]]:
    """The specificity of ``conditions`` and every finding, at most one per condition (T-REF-26).

    A field outside ``FIELDS[kind]`` is reported on ``conditions[i].field``, an unknown operator on
    ``conditions[i].op`` and a malformed value, including a float, on ``conditions[i].value``; an
    operator or a value the matcher cannot evaluate on the field's fact on ``.op`` or ``.value``
    (``evaluable_error``).
    """
    allowed = FIELDS[kind]
    errors: list[ProblemError] = []
    for index, condition in enumerate(conditions):
        where = f"conditions[{index}]"
        if condition.get("field") not in allowed:
            errors.append(
                ProblemError(field=f"{where}.field", rule_id=RULE_RULE, message=FIELD_NOT_ALLOWED)
            )
        elif condition.get("op") not in OPERATORS:
            errors.append(
                ProblemError(field=f"{where}.op", rule_id=RULE_RULE, message=OPERATOR_UNKNOWN)
            )
        elif _contains_float(condition.get("value")):
            errors.append(
                ProblemError(field=f"{where}.value", rule_id=RULE_RULE, message=DECIMAL_AS_TEXT)
            )
        else:
            try:
                validate_conditions(kind.value, [condition])
            except (TypeError, ValueError):
                errors.append(
                    ProblemError(field=f"{where}.value", rule_id=RULE_RULE, message=VALUE_INVALID)
                )
            else:
                finding = evaluable_error(condition, where=where)
                if finding is not None:
                    errors.append(finding)
    if errors:
        return 0, errors
    return validate_conditions(kind.value, conditions), []


def _is_code(value: Any) -> bool:
    return isinstance(value, str) and _CODE.fullmatch(value) is not None


def _choice(value: Any, choices: frozenset[str]) -> bool:
    return isinstance(value, str) and value in choices


def _approval_permission(code: Any) -> bool:
    if not isinstance(code, str):
        return False
    try:
        return permission_spec(code).is_approval
    except KeyError:
        return False


def _step_errors(steps: Any) -> list[ProblemError]:
    """``APPROVAL_ROUTING`` steps: 1 to 10 of ``{name, permission, min_approvers, role?}`` whose
    permission is an approval permission, whose approvers number 1 to 5 (04 T-PLT-18) and whose
    optional ``role`` is a code (04 T-REF-26; D-98 93 — whether it names an active role is checked
    when a submission routes over the published step, ``routing._step_role_id``, fail closed)."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        return [ProblemError(field="outputs.steps", rule_id=RULE_RULE, message=STEPS_COUNT)]
    errors: list[ProblemError] = []
    for index, step in enumerate(steps):
        where = f"outputs.steps[{index}]"
        if not isinstance(step, Mapping) or set(step) not in (
            routing.STEP_KEYS,
            routing.STEP_KEYS | {routing.STEP_ROLE_KEY},
        ):
            errors.append(ProblemError(field=where, rule_id=RULE_RULE, message=STEP_SHAPE))
            continue
        name = step["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > LABEL_LENGTH:
            errors.append(ProblemError(field=f"{where}.name", rule_id=RULE_RULE, message=STEP_NAME))
        if not _approval_permission(step["permission"]):
            errors.append(
                ProblemError(
                    field=f"{where}.permission", rule_id=RULE_RULE, message=STEP_PERMISSION
                )
            )
        approvers = step["min_approvers"]
        if (
            isinstance(approvers, bool)
            or not isinstance(approvers, int)
            or not 1 <= approvers <= routing.MAX_APPROVERS
        ):
            errors.append(
                ProblemError(
                    field=f"{where}.min_approvers", rule_id=RULE_RULE, message=STEP_APPROVERS
                )
            )
        if routing.STEP_ROLE_KEY in step and not _is_code(step[routing.STEP_ROLE_KEY]):
            errors.append(
                ProblemError(
                    field=f"{where}.{routing.STEP_ROLE_KEY}", rule_id=RULE_RULE, message=STEP_ROLE
                )
            )
    return errors


def step_role_errors(
    session: Session, outputs: Mapping[str, Any], *, prefix: str = "outputs"
) -> list[ProblemError]:
    """04 T-REF-26 (record §6 item 7): every ``APPROVAL_ROUTING`` step naming a ``role`` names an
    existing active role of the tenant — checked at the rule upsert and again at publication over
    the stored rules, so a mistyped or since-deactivated role fails once at authoring; the
    submission-time check (``routing._step_role_id``) still fails closed for a role deactivated
    after publication. Steps without a well-formed ``role`` are the shape check's business."""
    steps = outputs.get("steps") if isinstance(outputs, Mapping) else None
    if not isinstance(steps, list):
        return []
    named = {
        index: str(step[routing.STEP_ROLE_KEY])
        for index, step in enumerate(steps)
        if isinstance(step, Mapping) and _is_code(step.get(routing.STEP_ROLE_KEY))
    }
    if not named:
        return []
    active = set(
        session.execute(
            select(role.c.code).where(
                role.c.code.in_(sorted(set(named.values()))), role.c.is_active.is_(True)
            )
        ).scalars()
    )
    return [
        ProblemError(
            field=f"{prefix}.steps[{index}].{routing.STEP_ROLE_KEY}",
            rule_id=RULE_RULE,
            message=STEP_ROLE_UNKNOWN.format(code=code),
        )
        for index, code in named.items()
        if code not in active
    ]


def _reachable_subjects(
    conditions: Sequence[Mapping[str, Any]],
) -> list[ApprovalSubjectType]:
    """The registered subject types an ``APPROVAL_ROUTING`` rule can match: the ones its
    ``subject.type`` conditions name with ``eq`` or ``in``, else every registered subject. A
    condition with another operator on ``subject.type`` names nothing and is judged against every
    subject it could reach."""
    named = routing.named_subject_types(conditions)
    return [
        subject_type
        for subject_type in subjects.SUBJECTS
        if named is None or subject_type.value in named
    ]


def _static_floor(
    spec: subjects.SubjectSpec, conditions: Sequence[Mapping[str, Any]]
) -> list[routing.FloorItem]:
    """The subject specification's own steps as far as the rule itself fixes them: the first step
    always — with the subject's step role, where it names one — and the second step when one of
    the rule's ``flags`` conditions guarantees a second-step flag on every request it matches
    (``routing.floor_items``). What depends on the request — a flag the rule does not pin — is
    enforced at submission (``routing.apply_floor``)."""
    guaranteed = [
        flags for flags in routing.guaranteed_flags(conditions) if flags <= spec.second_step_flags
    ]
    return routing.floor_items(spec, guaranteed[0] if guaranteed else ())


def floor_errors(
    conditions: Sequence[Mapping[str, Any]], outputs: Mapping[str, Any], *, prefix: str = ""
) -> list[ProblemError]:
    """R-26 (c): an ``APPROVAL_ROUTING`` rule whose steps fall below the own steps of a subject it
    can match — another permission instead of the subject's, fewer approvers, a missing step role,
    a missing second step or a second step without its role. The steps are counted as submission
    counts them (``routing.floor_gaps``): a requirement one of the rule's steps already meets is
    met, in whatever order the rule lists them. One finding per subject type, on
    ``outputs.steps``, naming the first of the subject's steps the rule does not meet."""
    raw = outputs.get("steps") if isinstance(outputs, Mapping) else None
    if not isinstance(raw, list):
        return []
    steps: list[routing.FloorItem] = []
    for step in raw:
        if not isinstance(step, Mapping):
            return []  # the shape findings of ``_step_errors`` already name it
        role_code = step.get(routing.STEP_ROLE_KEY)
        steps.append(
            (
                str(step.get("name")),
                str(step.get("permission")),
                int(step["min_approvers"]) if isinstance(step.get("min_approvers"), int) else 0,
                role_code if isinstance(role_code, str) else None,
            )
        )
    field = f"{prefix}outputs.steps"
    errors: list[ProblemError] = []
    for subject_type in _reachable_subjects(conditions):
        spec = subjects.SUBJECTS[subject_type]
        floor = _static_floor(spec, conditions)
        gaps = routing.floor_gaps(steps, floor)
        if not gaps:
            continue
        _, permission, approvers, role_code = floor[gaps[0]]  # one finding per subject
        template = FLOOR_LOWERED if gaps[0] == 0 else FLOOR_SECOND_STEP
        errors.append(
            ProblemError(
                field=field,
                rule_id=RULE_RULE,
                message=template.format(
                    subject=subject_type.value,
                    permission=permission,
                    approvers=approvers,
                    approver_word="approver" if approvers == 1 else "approvers",
                    role="" if role_code is None else FLOOR_ROLE.format(role=role_code),
                ),
            )
        )
    if errors and routing.named_subject_types(conditions) is None:
        # The rule names no item type: one finding instead of one per registered subject.
        message = FLOOR_EVERY_SUBJECT.format(count=len(errors))
        return [ProblemError(field=field, rule_id=RULE_RULE, message=message)]
    return errors


def approval_rule_errors(
    kind: object,
    conditions: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Any],
    *,
    prefix: str = "",
) -> list[ProblemError]:
    """The findings of supervisor ruling R-26 on a rule that decides who approves (04 T-REF-26 rev
    1.104); none for the other kinds.

    (a) An ``APPROVAL_ROUTING`` or ``AUTO_APPROVAL`` rule holds at least one condition; an
    ``AUTO_APPROVAL`` rule carries a discriminating condition (R-38 (v)) — ``subject.type`` with
    ``eq`` or ``in`` for the subject types it covers, which is what the approvals engine
    matches, or ``reconciliation.kind`` for an auto-certification rule (BUILD_SPEC CLO-17), which
    only the certification of a reconciliation reads; a rule with neither is refused.
    (b) Every subject type it names is one a tenant's rule may approve (``routing.AUTO_APPROVABLE``;
    REQ-PLT-016): never a rule set, an access subject, a period lock or reopen, any other item a
    person approves, or a subject only its seeded rule set approves (``routing.SEEDED_RULE_SETS``).
    (c) The steps of an ``APPROVAL_ROUTING`` rule meet the own steps of every subject it can match
    (``floor_errors``). Called with conditions and outputs that already passed
    ``condition_errors`` and ``output_errors``. ``kind`` is coerced where it enters (R-41 (7))."""
    kind = routing.rule_set_kind(kind)
    if kind not in routing.APPROVAL_KINDS:
        return []
    field = f"{prefix}conditions"
    if not conditions:
        return [ProblemError(field=field, rule_id=RULE_RULE, message=CONDITION_REQUIRED)]
    if kind is RuleSetKind.APPROVAL_ROUTING:
        return floor_errors(conditions, outputs, prefix=prefix)
    named = routing.named_subject_types(conditions)
    if not named:
        if routing.certifies(conditions):
            return []  # an auto-certification rule: no rule of the approvals engine (R-38 (v))
        return [ProblemError(field=field, rule_id=RULE_RULE, message=SUBJECT_TYPE_REQUIRED)]
    admitted = {subject_type.value for subject_type in routing.AUTO_APPROVABLE}
    refused = sorted(named - admitted)
    if refused:
        message = NOT_AUTO_APPROVABLE.format(subjects=", ".join(refused))
        return [ProblemError(field=field, rule_id=RULE_RULE, message=message)]
    return []


def output_errors(kind: RuleSetKind, outputs: Mapping[str, Any]) -> list[ProblemError]:
    """The findings on a rule's kind-specific ``outputs`` (T-REF-26)."""
    members = OUTPUT_MEMBERS[kind]
    if set(outputs) != members:
        message = OUTPUTS_SHAPE.format(members=", ".join(sorted(members)))
        return [ProblemError(field="outputs", rule_id=RULE_RULE, message=message)]
    if kind is RuleSetKind.APPROVAL_ROUTING:
        return _step_errors(outputs["steps"])
    findings: list[tuple[str, str]] = []
    if kind in (RuleSetKind.POB_ASSIGNMENT, RuleSetKind.SSP_ASSIGNMENT):
        (member,) = members
        if not _is_code(outputs[member]):
            findings.append((member, CODE_INVALID))
    elif kind is RuleSetKind.AUTO_APPROVAL:
        if outputs["auto_approve"] is not True:
            findings.append(("auto_approve", AUTO_APPROVE_TRUE))
    elif kind is RuleSetKind.COMBINATION_DETECTION:
        window = outputs["window_days"]
        if (
            isinstance(window, bool)
            or not isinstance(window, int)
            or not 0 <= window <= MAX_WINDOW_DAYS
        ):
            findings.append(("window_days", WINDOW_DAYS))
        if not _choice(outputs["match"], MATCH_KINDS):
            findings.append(("match", MATCH_KIND))
    elif kind is RuleSetKind.HOLD:
        if not _is_code(outputs["hold_type"]):
            findings.append(("hold_type", CODE_INVALID))
        if not _choice(outputs["level"], HOLD_LEVELS):
            findings.append(("level", HOLD_LEVEL))
    else:
        if not _choice(outputs["severity"], DATA_QUALITY_SEVERITIES):
            findings.append(("severity", SEVERITY))
        message = outputs["message"]
        if not isinstance(message, str) or not message.strip() or len(message) > MEMO_LENGTH:
            findings.append(("message", MESSAGE_TEXT))
    return [
        ProblemError(field=f"outputs.{member}", rule_id=RULE_RULE, message=text)
        for member, text in findings
    ]


def _fact(name: str, value: Any) -> object:
    """``value`` as the type the engine compares for ``name``; ``_INVALID`` when it cannot be."""
    if value is None:
        return None
    if name in DECIMAL_FACTS:
        if isinstance(value, int) and not isinstance(value, bool):
            return Decimal(value)
        if isinstance(value, str) and _DECIMAL.fullmatch(value):
            return Decimal(value)
        return _INVALID
    if name in INTEGER_FACTS:
        return value if isinstance(value, int) and not isinstance(value, bool) else _INVALID
    if name in DATE_FACTS:
        if isinstance(value, str) and _ISO_DATE.fullmatch(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return _INVALID
        return _INVALID
    if name in BOOLEAN_FACTS:
        return value if isinstance(value, bool) else _INVALID
    if name in LIST_FACTS | CODE_SET_FACTS:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        if name in CODE_SET_FACTS and isinstance(value, str):
            return (value,)  # as a submission states it: the set of the request's entity codes
        return _INVALID
    return value if isinstance(value, str) else _INVALID


def facts_of(
    kind: RuleSetKind, raw: Mapping[str, Any], *, where: str, rule_id: str
) -> tuple[dict[str, object], list[ProblemError]]:
    """``raw`` as engine facts, with a finding on ``<where>.<name>`` for each unknown or mistyped
    fact. A null fact never matches a condition (``erev_engine.rules.match``)."""
    allowed = FIELDS[kind]
    facts: dict[str, object] = {}
    errors: list[ProblemError] = []
    for name in sorted(raw):
        field = f"{where}.{name}"
        if name not in allowed:
            errors.append(ProblemError(field=field, rule_id=rule_id, message=FACT_UNKNOWN))
            continue
        converted = _fact(name, raw[name])
        if converted is _INVALID:
            errors.append(ProblemError(field=field, rule_id=rule_id, message=FACT_INVALID))
        else:
            facts[name] = converted
    return facts, errors


def case_errors(
    kind: RuleSetKind, facts: Mapping[str, Any], expected: Mapping[str, Any]
) -> list[ProblemError]:
    """The findings on an example case of a rule set version: its ``input`` facts, and an
    ``expected_output`` naming ``matched`` (boolean), ``rule_key`` (text or null) or ``outputs``
    (object or null) and nothing else."""
    _, errors = facts_of(kind, facts, where="input", rule_id=RULE_TEST_CASE)
    if not expected or not set(expected) <= EXPECTED_MEMBERS:
        errors.append(
            ProblemError(field="expected_output", rule_id=RULE_TEST_CASE, message=EXPECTED_SHAPE)
        )
        return errors
    if "matched" in expected and not isinstance(expected["matched"], bool):
        errors.append(
            ProblemError(
                field="expected_output.matched", rule_id=RULE_TEST_CASE, message=EXPECTED_MATCHED
            )
        )
    rule_key = expected.get("rule_key")
    if rule_key is not None and not isinstance(rule_key, str):
        errors.append(
            ProblemError(
                field="expected_output.rule_key", rule_id=RULE_TEST_CASE, message=EXPECTED_RULE_KEY
            )
        )
    outputs = expected.get("outputs")
    if outputs is not None and not isinstance(outputs, dict):
        errors.append(
            ProblemError(
                field="expected_output.outputs", rule_id=RULE_TEST_CASE, message=EXPECTED_OUTPUTS
            )
        )
    return errors


def lock_version(session: Session, version_id: UUID) -> Mapping[str, Any]:
    """The ``rule_set_version`` row under ``FOR UPDATE``; 404 when it is not visible."""
    row = (
        session.execute(
            select(rule_set_version).where(rule_set_version.c.id == version_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def require_editable(version: Mapping[str, Any]) -> None:
    """409 ``configuration-frozen`` unless the version is DRAFT or TESTED (DB-04; PRD ERR-09)."""
    if version["status"] not in EDITABLE:
        raise Problem(
            "configuration-frozen",
            errors=[ProblemError(field="status", rule_id=RULE_FROZEN, message=VERSION_FROZEN)],
        )


def rule_rows(session: Session, version_id: UUID) -> list[dict[str, Any]]:
    """The rules of a version in ``rule_key`` order."""
    return [
        dict(row)
        for row in session.execute(
            select(rule).where(rule.c.rule_set_version_id == version_id).order_by(rule.c.rule_key)
        ).mappings()
    ]


def rule_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """API-S-Rule of a ``rule`` row."""
    return {
        "id": row["id"],
        "rule_set_version_id": row["rule_set_version_id"],
        "rule_key": row["rule_key"],
        "priority": row["priority"],
        "specificity": row["specificity"],
        "conditions": list(row["conditions"]),
        "outputs": dict(row["outputs"]),
        "description": row["description"],
    }


def case_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """API-S-ConfigTestCase of a ``rule_test_case`` row."""
    return {
        "id": row["id"],
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
        "name": row["name"],
        "input": dict(row["input"]),
        "expected_output": dict(row["expected_output"]),
        "last_result": row["last_result"],
        "last_run_at": row["last_run_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "row_version": row["row_version"],
    }


def lint_status(lint_result: Mapping[str, Any] | None) -> str | None:
    """API-S-VersionSummary ``lint_status``: the stored lint status, or null before lint runs."""
    if not lint_result:
        return None
    status = lint_result.get("status")
    return None if status is None else str(status)


def rule_counts(session: Session, version_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not version_ids:
        return {}
    return {
        UUID(str(version_id)): int(count)
        for version_id, count in session.execute(
            select(rule.c.rule_set_version_id, func.count())
            .where(rule.c.rule_set_version_id.in_(version_ids))
            .group_by(rule.c.rule_set_version_id)
        ).tuples()
    }


type Summary = dict[str, Any]


def version_summaries(
    session: Session, rule_set_ids: Sequence[UUID]
) -> dict[UUID, tuple[Summary | None, Summary | None]]:
    """For each set, API-S-VersionSummary of ``current_version`` (the latest PUBLISHED version)
    and of ``latest_version`` (the highest ``version_no``); None when there is none (04 §16.14)."""
    if not rule_set_ids:
        return {}
    rows = (
        session.execute(
            select(
                rule_set_version.c.id,
                rule_set_version.c.rule_set_id,
                rule_set_version.c.version_no,
                rule_set_version.c.status,
                rule_set_version.c.effective_from,
                rule_set_version.c.published_at,
                rule_set_version.c.lint_result,
            )
            .where(rule_set_version.c.rule_set_id.in_(rule_set_ids))
            .order_by(rule_set_version.c.rule_set_id, rule_set_version.c.version_no)
        )
        .mappings()
        .all()
    )
    counts = rule_counts(session, [row["id"] for row in rows])
    current: dict[UUID, Summary] = {}
    latest: dict[UUID, Summary] = {}
    for row in rows:  # ascending version_no: later versions replace earlier ones
        summary: Summary = {
            "id": row["id"],
            "version_no": row["version_no"],
            "status": row["status"],
            "effective_from": row["effective_from"],
            "published_at": row["published_at"],
            "rule_count": counts.get(row["id"], 0),
            "lint_status": lint_status(row["lint_result"]),
        }
        latest[row["rule_set_id"]] = summary
        if row["status"] == ConfigStatus.PUBLISHED.value:
            current[row["rule_set_id"]] = summary
    return {set_id: (current.get(set_id), latest.get(set_id)) for set_id in rule_set_ids}


def rule_set_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-RuleSet of each ``rule_set`` row with its version summaries."""
    summaries = version_summaries(session, [row["id"] for row in rows])
    outs: list[dict[str, Any]] = []
    for row in rows:
        current, latest = summaries.get(row["id"], (None, None))
        outs.append(
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "kind": row["kind"],
                "description": row["description"],
                "current_version": current,
                "latest_version": latest,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


CASE_PASS: Final = "PASS"
CASE_FAIL: Final = "FAIL"
LINT_PASS: Final = "PASS"
LINT_FAIL: Final = "FAIL"
RULE_EVALUATION: Final = "REQ-POL-002"
RULE_EVIDENCE: Final = "REQ-POL-003"
AMBIGUOUS: Final = (
    "Rules {first} and {second} have the same specificity and priority and can match the same "
    "item. Change a condition or a priority."
)
EVIDENCE_INCOMPLETE: Final = "Run the tests again: every test case and the lint must pass."


def case_evidence(session: Session, version_ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """``test_evidence`` of each version: its example cases by last result (REQ-POL-003)."""
    evidence: dict[UUID, dict[str, Any]] = {
        UUID(str(version_id)): {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "not_run": 0,
            "last_run_at": None,
        }
        for version_id in version_ids
    }
    if not version_ids:
        return evidence
    rows = session.execute(
        select(
            rule_test_case.c.subject_id, rule_test_case.c.last_result, rule_test_case.c.last_run_at
        ).where(
            rule_test_case.c.subject_type == SUBJECT_TYPE,
            rule_test_case.c.subject_id.in_(version_ids),
        )
    ).all()
    for subject_id, result, run_at in rows:
        entry = evidence[UUID(str(subject_id))]
        entry["total"] += 1
        if result == CASE_PASS:
            entry["passed"] += 1
        elif result == CASE_FAIL:
            entry["failed"] += 1
        else:
            entry["not_run"] += 1
        if run_at is not None and (entry["last_run_at"] is None or run_at > entry["last_run_at"]):
            entry["last_run_at"] = run_at
    return evidence


def version_outs(
    session: Session, rows: Sequence[Mapping[str, Any]], *, files: FileStore, keyring: KeyRing
) -> list[dict[str, Any]]:
    """API-S-RuleSetVersion of each ``rule_set_version`` row, with ``test_evidence``, the stored
    simulation summary and the id of its pending approval request."""
    if not rows:
        return []
    codes = {
        UUID(str(set_id)): str(code)
        for set_id, code in session.execute(
            select(rule_set.c.id, rule_set.c.code).where(
                rule_set.c.id.in_({row["rule_set_id"] for row in rows})
            )
        ).tuples()
    }
    ids = [row["id"] for row in rows]
    counts = rule_counts(session, ids)
    evidence = case_evidence(session, ids)
    pending = {
        UUID(str(subject_id)): request_id
        for subject_id, request_id in session.execute(
            select(approval_request.c.subject_id, approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.RULE_SET_VERSION.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_(ids),
            )
        ).tuples()
    }
    outs: list[dict[str, Any]] = []
    for row in rows:
        file_id = row["impact_simulation_file_id"]
        impact = (
            None
            if file_id is None
            else {
                "file_id": file_id,
                "summary": simulation.read_summary(session, file_id, files=files, keyring=keyring),
            }
        )
        outs.append(
            {
                "id": row["id"],
                "rule_set_id": row["rule_set_id"],
                "rule_set_code": codes[row["rule_set_id"]],
                "kind": row["kind"],
                "version_no": row["version_no"],
                "status": row["status"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "content_sha256": row["content_sha256"],
                "approval_request_id": row["approval_request_id"],
                "pending_approval_request_id": pending.get(row["id"]),
                "published_at": row["published_at"],
                "published_by": row["published_by"],
                "supersedes_version_id": row["supersedes_version_id"],
                "rule_count": counts.get(row["id"], 0),
                "lint_result": row["lint_result"],
                "test_evidence": evidence[row["id"]],
                "impact_simulation": impact,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


# --- lint (REQ-POL-002) ------------------------------------------------------------------------

type _Key = tuple[str, Any]
type _Bound = tuple[bool, _Key, bool]  # (is lower bound, operand, inclusive)
_ORDERED_TAGS: Final = frozenset({"number", "date", "text"})


def _key(value: Any) -> _Key:
    """An operand as a comparable value with its type; text that reads as a decimal or an ISO date
    compares as one, because the engine converts it for numeric and date facts."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int | Decimal):
        return ("number", Fraction(value))
    if isinstance(value, str):
        if _DECIMAL.fullmatch(value):
            return ("number", Fraction(Decimal(value)))
        if _ISO_DATE.fullmatch(value):
            try:
                return ("date", date.fromisoformat(value))
            except ValueError:
                return ("text", value)
        return ("text", value)
    return ("other", repr(value))


def _within(member: _Key, bounds: Sequence[_Bound]) -> bool:
    """Whether ``member`` meets every bound of its own type; other bounds prove nothing."""
    tag, value = member
    for is_lower, (bound_tag, bound), inclusive in bounds:
        if bound_tag != tag or tag not in _ORDERED_TAGS:
            continue
        if is_lower and (value < bound or (value == bound and not inclusive)):
            return False
        if not is_lower and (value > bound or (value == bound and not inclusive)):
            return False
    return True


def _interval_holds(bounds: Sequence[_Bound]) -> bool:
    """Whether some value meets every bound; bounds of mixed or unordered types prove nothing."""
    tags = {bound[1][0] for bound in bounds}
    if len(tags) != 1 or not tags <= _ORDERED_TAGS:
        return True
    lowers = [(bound[1][1], bound[2]) for bound in bounds if bound[0]]
    uppers = [(bound[1][1], bound[2]) for bound in bounds if not bound[0]]
    if not lowers or not uppers:
        return True
    # The tightest bounds: at an equal value an exclusive bound is tighter.
    low, low_inclusive = max(lowers, key=lambda item: (item[0], not item[1]))
    high, high_inclusive = min(uppers, key=lambda item: (item[0], item[1]))
    return bool(low < high or (low == high and low_inclusive and high_inclusive))


def _satisfiable(conditions: Sequence[Mapping[str, Any]]) -> bool:
    """Whether one fact value can meet every condition on one field; True unless provably not."""
    members: set[_Key] | None = None
    texts: dict[_Key, Any] = {}
    bounds: list[_Bound] = []
    prefixes: list[str] = []
    for condition in conditions:
        op, value = condition["op"], condition["value"]
        if op in ("eq", "in"):
            values = list(value) if op == "in" else [value]
            for item in values:
                texts.setdefault(_key(item), item)
            keys = {_key(item) for item in values}
            members = keys if members is None else members & keys
        elif op == "prefix":
            prefixes.append(str(value))
        elif op == "gte":
            bounds.append((True, _key(value), True))
        elif op == "lte":
            bounds.append((False, _key(value), True))
        elif op == "range":
            lower, upper = value
            if lower is not None:
                bounds.append((True, _key(lower), True))
            if upper is not None:
                bounds.append((False, _key(upper), False))
    if members is not None:
        return any(
            _within(member, bounds)
            and all(
                not isinstance(texts[member], str) or texts[member].startswith(prefix)
                for prefix in prefixes
            )
            for member in members
        )
    agree = all(
        first.startswith(second) or second.startswith(first)
        for first in prefixes
        for second in prefixes
    )
    return _interval_holds(bounds) and agree


def _may_overlap(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Whether some item can match both rules: every field both rules name has a value meeting both
    rules' conditions on it. A collection fact (``flags``, role codes) matches through any member,
    so it never separates two rules."""
    by_field: dict[str, list[Mapping[str, Any]]] = {}
    for condition in [*first["conditions"], *second["conditions"]]:
        by_field.setdefault(str(condition["field"]), []).append(condition)
    shared = {str(condition["field"]) for condition in first["conditions"]} & {
        str(condition["field"]) for condition in second["conditions"]
    }
    return all(field in LIST_FACTS or _satisfiable(by_field[field]) for field in sorted(shared))


def lint_findings(rules: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """REQ-POL-002: each pair of rules with equal specificity and equal priority that can match the
    same item, in ``rule_key`` order; the engine could only tell them apart by their keys."""
    ordered = sorted(rules, key=lambda row: str(row["rule_key"]))
    findings: list[dict[str, Any]] = []
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            tie = (first["specificity"], first["priority"]) == (
                second["specificity"],
                second["priority"],
            )
            if tie and _may_overlap(first, second):
                keys = [str(first["rule_key"]), str(second["rule_key"])]
                findings.append(
                    {
                        "rule_id": RULE_EVALUATION,
                        "severity": "ERROR",
                        "rule_keys": keys,
                        "message": AMBIGUOUS.format(first=keys[0], second=keys[1]),
                    }
                )
    return findings


def lint_result(rules: Sequence[Mapping[str, Any]], *, at: datetime) -> dict[str, Any]:
    """T-REF-25 ``lint_result``: PASS without findings, else FAIL (REQ-POL-002)."""
    findings = lint_findings(rules)
    return {
        "status": LINT_FAIL if findings else LINT_PASS,
        "findings": findings,
        "linted_at": at.isoformat(),
    }


# --- evaluation and example cases -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: Sequence[Mapping[str, object]]
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: Sequence[_Rule]


NO_MATCH: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "matched": False,
        "rule_key": None,
        "rule_id": None,
        "specificity": None,
        "priority": None,
        "outputs": None,
    }
)


def is_seeded_approval_set(kind: object, code: object) -> bool:
    """The rule set is one provisioning seeds for a seeded-only subject (``AUTO-BOOTSTRAP``,
    ``AUTO-MIG-01``; 04 §14.3 item 2). The approvals engine reads it by its code, so it is system
    configuration: a tenant creates no further version of it."""
    return (
        routing.rule_set_kind(kind) is RuleSetKind.AUTO_APPROVAL
        and str(code) in routing.SEEDED_RULE_SETS.values()
    )


def evaluate(
    kind: object,
    rules: Sequence[Mapping[str, Any]],
    facts: Mapping[str, object],
    *,
    rule_set_code: str | None = None,
) -> dict[str, Any]:
    """The most specific matching rule, then the highest priority (``erev_engine.rules.match``),
    as a submission with these facts would apply it (R-26; R-41 (7)): an approval rule that may
    not match at all is left out (``routing.admissible``); an ``AUTO_APPROVAL`` case whose subject
    type and source channel are not on the allow-list matches nothing
    (``routing.evaluation_admitted`` — ``rule_set_code`` names the evaluated rule set, for the
    subjects only their seeded set approves); and the steps of a matching ``APPROVAL_ROUTING``
    rule are returned raised to the own steps of the case's subject type
    (``routing.evaluated_outputs``). A case that states ``reconciliation.kind`` is a
    certification case (R-38 (v)) and is answered as the certification of a reconciliation reads
    the rule set (``close.reconciliations.certifying_rule``): from the rules that carry a
    ``reconciliation.kind`` condition alone, and never for a reconciliation with a variance.
    ``kind`` is an E-55 member or its value."""
    kind = routing.rule_set_kind(kind)
    certification = (
        kind is RuleSetKind.AUTO_APPROVAL
        and facts.get(routing.RECONCILIATION_KIND_FIELD) is not None
    )
    if certification:
        if facts.get(RECONCILIATION_VARIANCE_FACT) not in (None, 0):
            return dict(NO_MATCH)
    elif not routing.evaluation_admitted(kind, facts, rule_set_code=rule_set_code):
        return dict(NO_MATCH)
    found = match(
        _RuleSet(
            kind=kind.value,
            rules=tuple(
                _Rule(
                    rule_key=str(row["rule_key"]),
                    priority=int(row["priority"]),
                    specificity=int(row["specificity"]),
                    conditions=row["conditions"],
                    outputs=row["outputs"],
                )
                for row in rules
                if (
                    routing.certifies(row["conditions"])
                    if certification
                    else routing.admissible(kind, row["conditions"])
                )
            ),
        ),
        facts,
    )
    if found is None:
        return dict(NO_MATCH)
    ids = {str(row["rule_key"]): row["id"] for row in rules}
    return {
        "matched": True,
        "rule_key": found.rule_key,
        "rule_id": ids[found.rule_key],
        "specificity": found.specificity,
        "priority": found.priority,
        "outputs": routing.evaluated_outputs(kind, facts, found.outputs),
    }


def run_case(
    kind: RuleSetKind,
    rules: Sequence[Mapping[str, Any]],
    case: Mapping[str, Any],
    *,
    rule_set_code: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """PASS when every member of ``expected_output`` equals that member of the evaluation of
    ``input``; malformed facts or rules fail the case."""
    facts, errors = facts_of(kind, case["input"], where="input", rule_id=RULE_TEST_CASE)
    expected = case["expected_output"]
    if errors or not expected or not set(expected) <= EXPECTED_MEMBERS:
        return CASE_FAIL, None
    try:
        result = evaluate(kind, rules, facts, rule_set_code=rule_set_code)
    except (TypeError, ValueError):
        return CASE_FAIL, None
    passed = all(result[member] == value for member, value in expected.items())
    return (CASE_PASS if passed else CASE_FAIL), result


def evaluate_rule_set(
    session: Session,
    rule_set_id: UUID,
    *,
    raw_facts: Mapping[str, Any],
    version_id: UUID | None,
    at: datetime,
) -> dict[str, Any]:
    """``POST /rule-sets/{id}/evaluate``: the facts against ``version_id``, or else against the
    PUBLISHED version in force at ``at``, as routing reads rule sets (DG-KRN-APR-01).

    404 for an unknown set or a version of another set; 422 for unknown or mistyped facts. Without a
    version to evaluate, nothing matches (CTR-9 raises the exception item for booking lines).
    """
    found_set = session.execute(
        select(rule_set.c.kind, rule_set.c.code).where(rule_set.c.id == rule_set_id)
    ).one_or_none()
    if found_set is None:
        raise Problem("not-found")
    kind = RuleSetKind(found_set.kind)
    facts, errors = facts_of(kind, raw_facts, where="facts", rule_id=RULE_RULE)
    if errors:
        raise Problem("validation-failed", errors=errors)
    in_set = rule_set_version.c.rule_set_id == rule_set_id
    if version_id is not None:
        found = session.execute(
            select(rule_set_version.c.id).where(rule_set_version.c.id == version_id, in_set)
        ).scalar_one_or_none()
        if found is None:
            raise Problem("not-found")
    else:
        found = session.execute(
            select(rule_set_version.c.id)
            .where(
                in_set,
                rule_set_version.c.status == ConfigStatus.PUBLISHED.value,
                or_(
                    rule_set_version.c.effective_from.is_(None),
                    rule_set_version.c.effective_from <= at,
                ),
                or_(
                    rule_set_version.c.effective_to.is_(None), rule_set_version.c.effective_to > at
                ),
            )
            .order_by(rule_set_version.c.version_no.desc())
            .limit(1)
        ).scalar_one_or_none()
        if found is None:
            return {**NO_MATCH, "rule_set_version_id": None}
    evaluated = UUID(str(found))
    return {
        **evaluate(kind, rule_rows(session, evaluated), facts, rule_set_code=str(found_set.code)),
        "rule_set_version_id": evaluated,
    }


# --- the configuration lifecycle of rule set versions (RFD-5) ----------------------------------


def _submit_errors(session: Session, version: Mapping[str, Any]) -> list[ProblemError]:
    evidence = case_evidence(session, [version["id"]])[UUID(str(version["id"]))]
    complete = evidence["total"] > 0 and evidence["passed"] == evidence["total"]
    if complete and lint_status(version["lint_result"]) == LINT_PASS:
        return []
    return [ProblemError(field="status", rule_id=RULE_EVIDENCE, message=EVIDENCE_INCOMPLETE)]


def _publish_errors(session: Session, version: Mapping[str, Any]) -> list[ProblemError]:
    rules = rule_rows(session, version["id"])
    errors = [
        ProblemError(field="rules", rule_id=RULE_EVALUATION, message=str(finding["message"]))
        for finding in lint_findings(rules)
    ]
    kind = RuleSetKind(version["kind"])
    if kind is RuleSetKind.APPROVAL_ROUTING:
        for row in rules:  # 04 T-REF-26 (record §6 item 7): the roles the stored steps name
            errors += step_role_errors(
                session, row["outputs"], prefix=f"rules[{row['rule_key']}].outputs"
            )
    for row in rules:  # R-26: validated at publish over the stored rules, as at the upsert
        errors += approval_rule_errors(
            kind, row["conditions"], row["outputs"], prefix=f"rules[{row['rule_key']}]."
        )
        # R-66 (9): a stored condition the matcher cannot evaluate is not put in force.
        errors += evaluable_errors(row["conditions"], prefix=f"rules[{row['rule_key']}].")
    return errors


def _snapshot(session: Session, version_id: UUID) -> dict[str, Any]:
    """The field-level ``before`` and ``after`` of publication audits: the rules."""
    return {"rules": subjects.rule_set_version_content(session, version_id)["rules"]}


def _summary(session: Session, version: Mapping[str, Any]) -> str:
    code = session.execute(
        select(rule_set.c.code).where(rule_set.c.id == version["rule_set_id"])
    ).scalar_one()
    return f"Publish version {version['version_no']} of rule set {code}"


# The kinds the engine evaluates at a contract date (ENGINE_SPEC S03-R-02, S05-R-02).
CHOSEN_BY_DATE: Final = frozenset({RuleSetKind.POB_ASSIGNMENT, RuleSetKind.SSP_ASSIGNMENT})


def _chosen_by(version: Mapping[str, Any]) -> str:
    """PRD ERR-75: an assignment rule set is chosen by a contract date; every other kind is read
    by the platform at the instant of an act (routing, automatic approval, holds, combination
    detection, data-quality monitors)."""
    if RuleSetKind(version["kind"]) in CHOSEN_BY_DATE:
        return lifecycle.BY_DATE
    return lifecycle.BY_INSTANT


RULE_SET_VERSION_KIND: Final = lifecycle.ConfigVersionKind(
    table=rule_set_version,
    subject_type=ApprovalSubjectType.RULE_SET_VERSION,
    scope_columns=("rule_set_id",),
    content=subjects.rule_set_version_content,
    snapshot=_snapshot,
    submit_errors=_submit_errors,
    publish_errors=_publish_errors,
    summary=_summary,
    chosen_by=_chosen_by,
)


def _on_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.approve(uow, RULE_SET_VERSION_KIND, subject_id, approval_request_id)


def _on_rejected(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow, RULE_SET_VERSION_KIND, subject_id, approval_request_id, to_status=ConfigStatus.REJECTED
    )


def _on_voided(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(
        uow,
        RULE_SET_VERSION_KIND,
        subject_id,
        approval_request_id,
        to_status=ConfigStatus.WITHDRAWN,
    )


subjects.register_lifecycle(
    ApprovalSubjectType.RULE_SET_VERSION,
    subjects.SubjectLifecycle(
        on_approved=_on_approved, on_rejected=_on_rejected, on_voided=_on_voided
    ),
)
