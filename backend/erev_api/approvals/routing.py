"""Approval routing and auto-approval (dev-guide §5.6 DG-KRN-APR-01; 04 T-REF-24 to T-REF-26,
T-PLT-17, T-PLT-20; PRD §2.5; REQ-PLT-013, REQ-PLT-016; BUILD_SPEC PLF-12, BS1-D-05).

``resolve_steps`` evaluates the PUBLISHED ``APPROVAL_ROUTING`` rule set versions in force through
``erev_engine.rules.match``: the matching rule's ``outputs.steps`` become the steps of a new
request, and without a match the request takes the DG-KRN-APR-01 fallback, one step with the
subject's permission and minimum approvers. ``auto_approval`` evaluates the PUBLISHED
``AUTO_APPROVAL`` versions the same way; a matching rule whose outputs hold ``auto_approve: true``
approves the request at submission. Across versions the most specific rule wins, then the highest
priority, the ascending rule key and the ascending rule set code (SPEC-Q-173). Malformed rules or
outputs raise, so no request is created on a rule nobody can explain (XR-12).

**Rules cannot lower the subject's own approval (supervisor rulings R-26, R-38 and R-41 on the
security review's finding SN-9; 04 T-REF-26 and §16.10 rev 1.104; dev-guide DG-KRN-APR-08).** Three
limits hold at submission whatever a published rule says, rule authoring refuses the same rules by
name (``domain/policies/rule_sets.approval_rule_errors``), and the evaluation of a rule set version
against a case answers as a submission would (``evaluation_admitted``, ``evaluated_outputs``):

- (a) an ``APPROVAL_ROUTING`` or ``AUTO_APPROVAL`` rule without a condition never matches, and an
  ``AUTO_APPROVAL`` rule matches only when it names the subject types it covers
  (``admissible``; ``rule_set_kind`` reads the kind from an enum member or its value alike);
- (b) auto-approval applies only to the system-originated standard items the documents name.
  ``AUTO_APPROVABLE`` is what a tenant's own rule may approve: a subject type with the principal
  kinds that originate it, ``SYSTEM`` only when the job acts on behalf of no user
  (``auto_approval_admitted``). ``SEEDED_RULE_SETS`` are the subjects only the rule set
  provisioning seeds approves (``seeded_rule_set``): the legacy SSP replay under ``AUTO-MIG-01``
  and the bootstrap grants of 04 §14.3 under ``AUTO-BOOTSTRAP`` — for THE bootstrap Tenant Admin
  (``is_bootstrap_admin``), while setup is incomplete and no other person has ever been an active
  access approver (``second_approver_has_existed``: the exception ends one way). A rule of any
  other rule set that names such a subject is not read (``_matched``);
- (c) the subject specification's own steps are a floor (``floor_items``: the step with its role,
  the second step its flags demand, and the steps its content demands): the routed steps are
  raised to it (``apply_floor``), so a rule may add steps or raise a requirement and never drop
  the subject's permission, approver count, second step or role. The floor counts approvers per
  permission and role, in any order: a requirement a routed step already meets is not added again.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_engine.rules import match
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import SUBJECTS, SubjectEntities, SubjectSpec
from erev_api.auth.permissions import spec as permission_spec
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    role,
    role_assignment,
    role_permission,
    rule,
    rule_set,
    rule_set_version,
    tenant,
    tenant_membership,
)
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalSubjectType,
    ConfigStatus,
    PrincipalKind,
    RuleSetKind,
)

FALLBACK_STEP_NAME: Final = "Approval"
SECOND_STEP_NAME: Final = "Second approval"  # [J] REQ-SSP-007 second approver
MAX_APPROVERS: Final = 5  # 04 T-PLT-18 ck_approval_step__min_approvers
STEP_KEYS: Final = frozenset({"name", "permission", "min_approvers"})  # 04 T-REF-26 outputs
# 04 T-REF-26 outputs (D-98 93): an optional active role code every approver of the step must
# hold, parsed into T-PLT-18 ``required_role_id``; a step name is never an enforced role.
STEP_ROLE_KEY: Final = "role"
SUBJECT_TYPE_FIELD: Final = "subject.type"
FLAGS_FIELD: Final = "flags"
AMOUNT_FIELD: Final = "amount.functional"
SOURCE_CHANNEL_FIELD: Final = "source.channel"
# Supervisor ruling R-38 (v); BUILD_SPEC BS4-D-09, CLO-17: the discriminating condition of an
# auto-certification rule (``AUTO-REC-01``). Only the certification of a reconciliation reads such
# a rule (``domain.close.reconciliations.certifying_rule``); the approvals engine reads the rules
# that name subject types.
RECONCILIATION_KIND_FIELD: Final = "reconciliation.kind"
# One step as the floor arithmetic reads it: (name, permission, approvers, role). ``role`` is
# whatever identifies the role — a T-PLT-09 id for a ``StepPlan``, a role code at authoring.
type FloorItem = tuple[str, str, int, object | None]
# The kinds whose rules decide WHO approves: R-26 (a) refuses their unconditional rules.
APPROVAL_KINDS: Final = frozenset({RuleSetKind.APPROVAL_ROUTING, RuleSetKind.AUTO_APPROVAL})

# R-26 (b); REQ-PLT-016 "system-originated standard items"; 04 §16.10 rev 1.104 "Auto-approval":
# the subject types a tenant's AUTO_APPROVAL rule may approve, each with the principal kinds that
# originate such an item. The documents name exactly these — REQ-CON-006 and PRD §2.5 AUTO-CON-01
# (a contract originated by an integration) and PRD §2.5 AUTO-IMP-01 (an import uploaded by an API
# client). Every other subject waits for a person: configuration (rule sets of every kind,
# registry versions, mappings, templates), access subjects, period lock and reopen, journal runs,
# judgements, estimates, modifications.
AUTO_APPROVABLE: Final[Mapping[ApprovalSubjectType, frozenset[PrincipalKind]]] = MappingProxyType(
    {
        ApprovalSubjectType.CONTRACT_ACTIVATION: frozenset(
            {PrincipalKind.API_CLIENT, PrincipalKind.SYSTEM}
        ),
        ApprovalSubjectType.IMPORT_COMMIT: frozenset({PrincipalKind.API_CLIENT}),
    }
)
# 04 §14.3 item 2: the two subjects that only the rule set provisioning seeds for them approves —
# never a tenant-authored rule, which authoring refuses and submission does not read (R-26 (b);
# R-41 (7)).
# ``AUTO-BOOTSTRAP`` (PRD BR-PLT-02; REQ-PLT-038): the role assignments THE bootstrap Tenant Admin
# makes while setup is incomplete and until another person has been an active access approver —
# from then on never again (supervisor rulings R-66 (2), R-73). The engine itself establishes
# those facts (``engine.auto_approval_rule``), so rule data can neither widen the exception nor
# reach another access subject.
# ``AUTO-MIG-01`` (PRD §2.5 rev 1.15): the legacy SSP replay a user starts at ``/import``, whose
# two guards the route enforces before it submits.
AUTO_BOOTSTRAP: Final = "AUTO-BOOTSTRAP"
AUTO_MIGRATION: Final = "AUTO-MIG-01"
BOOTSTRAP_ROLE: Final = "tenant_admin"
SEEDED_RULE_SETS: Final[Mapping[ApprovalSubjectType, str]] = MappingProxyType(
    {
        ApprovalSubjectType.ROLE_ASSIGNMENT: AUTO_BOOTSTRAP,
        ApprovalSubjectType.MIGRATION_SSP_REPLAY: AUTO_MIGRATION,
    }
)


@dataclass(frozen=True, slots=True)
class StepPlan:
    name: str
    permission: str
    min_approvers: int
    role_id: UUID | None = None

    def __post_init__(self) -> None:
        # 04 T-PLT-18: the step permission is an approval permission of the catalogue.
        if not permission_spec(self.permission).is_approval:
            raise ValueError(f"{self.permission!r} is not an approval permission")
        if not 1 <= self.min_approvers <= MAX_APPROVERS:
            raise ValueError("a step needs between 1 and 5 approvers")


@dataclass(frozen=True, slots=True)
class RuleRef:
    """The matched rule, recorded on the request or the decision (04 T-PLT-17, T-PLT-20)."""

    rule_set_version_id: UUID
    rule_id: UUID
    rule_set_code: str
    rule_key: str


@dataclass(frozen=True, slots=True)
class Routing:
    steps: tuple[StepPlan, ...]
    rule: RuleRef | None  # None: the fallback step


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


def fallback_step(spec: SubjectSpec, *, role_id: UUID | None = None) -> StepPlan:
    """The DG-KRN-APR-01 fallback: one step with the subject's permission and approvers, narrowed
    to ``role_id`` — the subject's own step role, where it names one (R-41 (7); PRD §2.5
    ``PERIOD_LOCK``: "1: period.lock (Controller)")."""
    return StepPlan(
        name=FALLBACK_STEP_NAME,
        permission=spec.required_permission,
        min_approvers=spec.min_approvers,
        role_id=role_id,
    )


def fallback_steps(
    spec: SubjectSpec,
    flags: Iterable[str],
    *,
    step_role_id: UUID | None = None,
    second_step_role_id: UUID | None = None,
) -> tuple[StepPlan, ...]:
    """The subject's own steps: the fallback step (narrowed to ``step_role_id`` when the subject
    names a step role), and a second step with the same permission and approvers when the request
    carries one of ``spec.second_step_flags`` (REQ-SSP-007; PRD §2.5; BUILD_SPEC RFD-13), narrowed
    to ``second_step_role_id`` when given (BUILD_SPEC CTR-9). They are the steps of a request
    without a matching rule and the floor under a matching one (R-26 (c))."""
    first = fallback_step(spec, role_id=step_role_id)
    if spec.second_step_flags.isdisjoint(flags):
        return (first,)
    second = StepPlan(
        name=SECOND_STEP_NAME,
        permission=spec.required_permission,
        min_approvers=spec.min_approvers,
        role_id=second_step_role_id,
    )
    return (first, second)


def floor_items(spec: SubjectSpec, flags: Iterable[str]) -> list[FloorItem]:
    """``fallback_steps`` with role CODES instead of role ids: the subject's own steps as rule
    authoring and the evaluation of a case read them, without a session."""
    items: list[FloorItem] = [
        (FALLBACK_STEP_NAME, spec.required_permission, spec.min_approvers, spec.step_role)
    ]
    if not spec.second_step_flags.isdisjoint(flags):
        items.append(
            (SECOND_STEP_NAME, spec.required_permission, spec.min_approvers, spec.second_step_role)
        )
    return items


def routing_facts(
    *,
    subject_type: ApprovalSubjectType,
    entity_codes: Sequence[str],
    amount_functional: Decimal | None,
    flags: Sequence[str],
) -> dict[str, object]:
    """The ``APPROVAL_ROUTING`` facts of ``erev_engine.rules.FIELDS``; a None fact never matches.
    ``entity.code`` is the set of codes of the legal entities the request names (04 T-REF-26 rev
    1.104; supervisor ruling R-66 (8)): a condition on it holds when ANY of them meets it, and
    never for a tenant-level request, which names none."""
    return {
        "subject.type": ApprovalSubjectType(subject_type).value,
        "entity.code": tuple(sorted(entity_codes)),
        "amount.functional": amount_functional,
        "flags": tuple(sorted(flags)),
    }


def auto_approval_facts(
    *,
    subject_type: ApprovalSubjectType,
    preparer_role_codes: Sequence[str],
    setup_completed: bool,
    source_channel: str,
) -> dict[str, object]:
    """The ``AUTO_APPROVAL`` facts of ``erev_engine.rules.FIELDS``."""
    return {
        "subject.type": ApprovalSubjectType(subject_type).value,
        "preparer.role_codes": tuple(sorted(preparer_role_codes)),
        "tenant.setup_completed": setup_completed,
        "source.channel": source_channel,
    }


def setup_completed(session: Session, tenant_id: UUID) -> bool:
    """The ``tenant.setup_completed`` fact: ``setup_completed_at`` is set (04 T-PLT-01)."""
    completed_at = session.execute(
        select(tenant.c.setup_completed_at).where(tenant.c.id == tenant_id)
    ).scalar_one()
    return completed_at is not None


def resolve_steps(
    session: Session,
    facts: Mapping[str, object],
    *,
    fallback: StepPlan | Sequence[StepPlan],
    at: datetime,
) -> Routing:
    """The steps of a new request, in activation order, and the routing rule that chose them.
    ``fallback`` is the subject specification's own steps for this request — the steps without a
    matching rule AND the floor under a matching one (R-26 (c)): the rule's steps are raised to it
    (``apply_floor``)."""
    floor = (fallback,) if isinstance(fallback, StepPlan) else tuple(fallback)
    matched = _matched(session, RuleSetKind.APPROVAL_ROUTING, facts, at)
    if matched is None:
        return Routing(steps=floor, rule=None)
    ref, outputs = matched
    return Routing(steps=apply_floor(_steps(session, ref, outputs), floor), rule=ref)


@dataclass(slots=True, eq=False)
class _Routed:
    """One routed step while it is measured against the floor: ``used`` of its approvers already
    count towards a floor step."""

    name: str
    permission: str
    approvers: int
    role: object | None
    used: int = 0

    def free(self) -> int:
        return self.approvers - self.used


def _serves(step: _Routed, permission: str, wanted_role: object | None) -> bool:
    """``step`` supplies approvers the floor asks for: it carries the permission, and the role
    when the floor names one. A routed step may be narrower than a floor step that is open to
    every holder of the permission."""
    return step.permission == permission and (wanted_role is None or step.role == wanted_role)


def _allocate(
    routed: list[_Routed], floor: Sequence[FloorItem]
) -> tuple[list[int], list[list[_Routed]]]:
    """Count the routed approvers towards the floor: every approver of a routed step satisfies at
    most one approver of one floor step, whatever the order of the steps — one decision per person
    per request makes every step another person (DB-10), so the floor is a number of approvers per
    permission and role, not a sequence. Floor steps that name a role are served first, so an open
    floor step does not take the one routed step that carries the role. Returns, per floor step,
    the approvers still missing and the routed steps that serve it."""
    short = [approvers for _, _, approvers, _ in floor]
    served: list[list[_Routed]] = [[] for _ in floor]
    for index in sorted(range(len(floor)), key=lambda at: (floor[at][3] is None, at)):
        _, permission, _, wanted_role = floor[index]
        candidates = [step for step in routed if _serves(step, permission, wanted_role)]
        if wanted_role is None:
            candidates.sort(key=lambda step: step.role is not None)  # open steps first; stable
        for step in candidates:
            taken = min(short[index], step.free())
            if taken:
                step.used += taken
                short[index] -= taken
                served[index].append(step)
    return short, served


def _position(routed: list[_Routed], step: _Routed) -> int:
    return next(index for index, found in enumerate(routed) if found is step)


def _raise_to_floor(steps: Sequence[FloorItem], floor: Sequence[FloorItem]) -> list[FloorItem]:
    """``steps`` raised to ``floor`` (R-26 (c) as refined by R-41 (7)). What the routed steps
    already supply is counted first (``_allocate``): a requirement a routed step satisfies is
    never added a second time, in whatever order the rule lists its steps. For the approvers a
    floor step still lacks, in floor order: a routed step with the permission, no role and no
    approver counted yet takes the floor's role in place when it asks for no more approvers than
    the floor step (the rule's "Controller approval" step without the role reference); otherwise a
    routed step with the same permission and role gets the missing approvers, up to five; and
    what remains becomes the floor step itself, placed behind the routed steps that serve the
    earlier floor steps. The result never has fewer steps, fewer approvers or a lesser role than
    the floor, and equals ``steps`` whenever they already meet it."""
    routed = [_Routed(*step) for step in steps]
    short, served = _allocate(routed, floor)
    for index, (name, permission, _, wanted_role) in enumerate(floor):
        missing = short[index]
        if missing and wanted_role is not None:
            found = next(
                (
                    step
                    for step in routed
                    if step.permission == permission
                    and step.role is None
                    and step.used == 0
                    and step.approvers <= missing
                ),
                None,
            )
            if found is not None:
                found.role = wanted_role
                found.approvers = missing
                found.used = missing
                served[index].append(found)
                missing = 0
        if missing:
            found = next(
                (
                    step
                    for step in routed
                    if step.permission == permission and step.role == wanted_role
                ),
                None,
            )
            if found is not None:
                added = min(found.approvers + missing, MAX_APPROVERS) - found.approvers
                if added:
                    found.approvers += added
                    found.used += added
                    served[index].append(found)
                    missing -= added
        if missing:
            earlier = [step for before in served[:index] for step in before]
            position = max((_position(routed, step) for step in earlier), default=-1) + 1
            inserted = _Routed(name, permission, missing, wanted_role, used=missing)
            routed.insert(position, inserted)
            served[index].append(inserted)
    return [(step.name, step.permission, step.approvers, step.role) for step in routed]


def apply_floor(steps: Sequence[StepPlan], floor: Sequence[StepPlan]) -> tuple[StepPlan, ...]:
    """``steps`` raised to ``floor`` (R-26 (c); 04 T-REF-26 rev 1.104): a routing rule may add
    steps or raise a requirement; the subject's own permission, approver count, second step and
    role are a floor its output cannot lower (``_raise_to_floor``)."""
    raised = _raise_to_floor(
        [(step.name, step.permission, step.min_approvers, step.role_id) for step in steps],
        [(step.name, step.permission, step.min_approvers, step.role_id) for step in floor],
    )
    return tuple(
        StepPlan(
            name=name,
            permission=permission,
            min_approvers=approvers,
            role_id=None if held is None else UUID(str(held)),
        )
        for name, permission, approvers, held in raised
    )


def raised_steps(
    steps: Sequence[Mapping[str, object]], floor: Sequence[FloorItem]
) -> list[dict[str, object]]:
    """``apply_floor`` over rule outputs as they are authored — ``{name, permission,
    min_approvers, role?}`` with role codes — for the evaluation of a case (R-41 (7))."""
    raised = _raise_to_floor(
        [
            (
                str(step.get("name")),
                str(step.get("permission")),
                int(str(step.get("min_approvers"))),
                step.get(STEP_ROLE_KEY),
            )
            for step in steps
        ],
        floor,
    )
    return [
        {"name": name, "permission": permission, "min_approvers": approvers}
        | ({} if held is None else {STEP_ROLE_KEY: held})
        for name, permission, approvers, held in raised
    ]


def floor_gaps(steps: Sequence[FloorItem], floor: Sequence[FloorItem]) -> list[int]:
    """The indexes of the ``floor`` steps that ``steps`` do not meet as they are — counted like
    ``apply_floor`` counts them and without raising anything: what rule authoring refuses (R-26
    (c), "validated at publish")."""
    short, _ = _allocate([_Routed(*step) for step in steps], floor)
    return [index for index, missing in enumerate(short) if missing]


def _conditions_on(conditions: object, field: str) -> list[Mapping[str, object]]:
    if isinstance(conditions, str | bytes) or not isinstance(conditions, Sequence):
        return []
    return [
        condition
        for condition in conditions
        if isinstance(condition, Mapping) and condition.get("field") == field
    ]


def _named(condition: Mapping[str, object]) -> frozenset[str] | None:
    """The values an ``eq`` or ``in`` condition names; None for another operator."""
    op, value = condition.get("op"), condition.get("value")
    if op == "eq" and isinstance(value, str):
        return frozenset({value})
    if op == "in" and isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return frozenset(str(item) for item in value)
    return None


def named_subject_types(conditions: object) -> frozenset[str] | None:
    """The subject types a rule names: the values of its ``subject.type`` conditions with ``eq``
    or ``in``, intersected when it holds several (every condition must hold). None when no
    condition names any — such a rule reaches every subject type."""
    named: frozenset[str] | None = None
    for condition in _conditions_on(conditions, SUBJECT_TYPE_FIELD):
        values = _named(condition)
        if values is not None:
            named = values if named is None else named & values
    return named


def certifies(conditions: object) -> bool:
    """Whether a rule is an auto-certification rule: it carries a ``reconciliation.kind``
    condition (supervisor ruling R-38 (v)). An ``AUTO_APPROVAL`` rule carries one of two
    discriminating conditions — ``subject.type`` for the approvals engine (``admissible``), this
    one for the certification of a reconciliation — and a rule with neither is invalid."""
    return bool(_conditions_on(conditions, RECONCILIATION_KIND_FIELD))


def guaranteed_flags(conditions: object) -> list[frozenset[str]]:
    """Per ``flags`` condition with ``eq`` or ``in``, the flags of which a matching request carries
    at least one (a collection fact matches through any member)."""
    found: list[frozenset[str]] = []
    for condition in _conditions_on(conditions, FLAGS_FIELD):
        values = _named(condition)
        if values:
            found.append(values)
    return found


def rule_set_kind(kind: object) -> RuleSetKind:
    """``kind`` as the E-55 member, however it is spelt — the member, its value, or the engine's
    own enum of the same values. The limits compare members by identity, so a kind is coerced
    where it enters (R-41 (7): a plain ``"AUTO_APPROVAL"`` passed for an unlimited kind)."""
    return RuleSetKind(str(getattr(kind, "value", kind)))


def admissible(kind: object, conditions: object) -> bool:
    """R-26 (a): whether a rule of ``kind`` may match at all. An ``APPROVAL_ROUTING`` or
    ``AUTO_APPROVAL`` rule needs a condition — without one it would apply to every subject — and
    an ``AUTO_APPROVAL`` rule names the subject types it covers (R-38 (v): ``subject.type`` is the
    discriminating condition of every rule the approvals engine matches — an auto-certification
    rule, which carries ``reconciliation.kind`` instead (``certifies``), is no rule of the
    approvals engine and never matches a request). Other kinds keep their unconditional default
    rules (``DQ-SYSTEM``, a catch-all assignment)."""
    found = rule_set_kind(kind)
    if found not in APPROVAL_KINDS:
        return True
    if isinstance(conditions, str | bytes) or not isinstance(conditions, Sequence):
        return False
    if len(conditions) == 0:
        return False
    return found is not RuleSetKind.AUTO_APPROVAL or bool(named_subject_types(conditions))


def auto_approval_admitted(
    subject_type: ApprovalSubjectType,
    *,
    principal_kind: object,
    on_behalf_of_id: UUID | None = None,
) -> bool:
    """R-26 (b) for the subjects a tenant's rules may approve (``AUTO_APPROVABLE``): whether a
    request of ``subject_type`` prepared by a principal of this kind may be auto-approved at all —
    asked before any rule is read. A SYSTEM principal is system-originated only when it acts on
    behalf of no user (R-41 (7)): a job a person started carries that person's content. The
    seeded-only subjects (``SEEDED_RULE_SETS``) are never admitted here."""
    subject_type = ApprovalSubjectType(subject_type)
    kind = PrincipalKind(str(getattr(principal_kind, "value", principal_kind)))
    if kind not in AUTO_APPROVABLE.get(subject_type, frozenset()):
        return False
    return kind is not PrincipalKind.SYSTEM or on_behalf_of_id is None


def seeded_rule_set(subject_type: ApprovalSubjectType) -> str | None:
    """The code of the provisioning-seeded rule set that alone approves ``subject_type`` (04 §14.3
    item 2), or None for every other subject."""
    return SEEDED_RULE_SETS.get(ApprovalSubjectType(subject_type))


def is_bootstrap_admin(session: Session, membership_id: UUID) -> bool:
    """The membership is THE bootstrap Tenant Admin (R-38 (iv); PRD BR-PLT-02 "the bootstrap
    Tenant Admin"): the user of the ``tenant_admin`` assignment the seed of the workspace wrote
    (04 §14.3 item 2 rev 1.254). The assignment is known by the grant's own request and not by
    a stamp: its ``approval_request_id`` names a ``ROLE_ASSIGNMENT`` request whose subject is
    that assignment, prepared by SYSTEM with no preparer and approved by rule
    ``AUTO-BOOTSTRAP`` — the pair ``provisioning.grant_bootstrap_admin`` writes, for
    ``tenant.provision`` and for the requester of an EMPTY sandbox (05 SBX-07). No command of a
    member writes it: the engine reads the rule for a signed-in member only
    (``engine._seeded_admitted``), so a request the rule approves at a submission carries the
    member who prepared it, and the request of a job is never the rule's
    (``tests/architecture/test_bootstrap_grant_writers.py`` lists the writers).
    ``created_by_kind`` stays the record of who wrote the rows and decides nothing.

    Another holder of the role is not the bootstrap Tenant Admin — neither one whose grant the
    rule itself approved, nor the member of a grant an operator writes without a request, nor
    the member of an assignment that names the seed's request without being its subject. The
    assignment counts whether or not it is still in force: whether the member still holds the
    role is the caller's check (the preparer's role codes). The answer does not depend on the
    caller's entity scope: the seed request is for all entities, which no scope hides (04
    T-PLT-17), and the other rows are the tenant's.

    Two conditions say what the tables hold already and stay because the rule is worded so: a
    request without a preparer is SYSTEM's (``ck_approval_request__preparer``), and only an
    automatic decision names a rule set version — by the two writers of decisions; no check
    says it."""
    found = session.execute(
        select(role_assignment.c.id)
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            )
            .join(
                approval_request,
                and_(
                    approval_request.c.tenant_id == role_assignment.c.tenant_id,
                    approval_request.c.id == role_assignment.c.approval_request_id,
                    approval_request.c.subject_id == role_assignment.c.id,
                ),
            )
            .join(
                approval_decision,
                and_(
                    approval_decision.c.tenant_id == approval_request.c.tenant_id,
                    approval_decision.c.approval_request_id == approval_request.c.id,
                ),
            )
            .join(
                rule_set_version,
                and_(
                    rule_set_version.c.tenant_id == approval_decision.c.tenant_id,
                    rule_set_version.c.id == approval_decision.c.auto_rule_set_version_id,
                ),
            )
            .join(
                rule_set,
                and_(
                    rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                    rule_set.c.id == rule_set_version.c.rule_set_id,
                ),
            )
        )
        .where(
            role_assignment.c.membership_id == membership_id,
            role.c.code == BOOTSTRAP_ROLE,
            approval_request.c.subject_type == ApprovalSubjectType.ROLE_ASSIGNMENT.value,
            approval_request.c.preparer_kind == PrincipalKind.SYSTEM.value,
            approval_request.c.preparer_id.is_(None),
            approval_decision.c.decision == ApprovalDecisionKind.AUTO_APPROVE.value,
            rule_set.c.code == AUTO_BOOTSTRAP,
        )
        .limit(1)
    ).first()
    return found is not None


def second_approver_has_existed(
    session: Session,
    *,
    bootstrap_membership_id: UUID,
    permission: str,
    at: datetime,
    entities: SubjectEntities | None = None,
) -> bool:
    """Whether a person other than the bootstrap Tenant Admin has been ACTIVE in the workspace
    while holding ``permission`` for every entity of ``entities`` — the one-way end of the
    bootstrap exception (supervisor rulings R-66 (2) and R-73; 04 §14.3 item 3): from that moment
    ``AUTO-BOOTSTRAP`` never again approves a request of those entities, or of a subset of them,
    whatever that person's later status, revocation or expiry.

    The end is per request (04 rev 1.197; the supervisor's ruling of 2026-10-01 on the join with
    entity-scoped grants): ``entities`` is the set the request names, and it is covered by ONE
    person's grants — an assignment for all entities, or assignments that between them name
    every entity of the set; a request for all entities is covered only by an assignment for all
    entities. A grant another person could decide waits for that person; a grant nobody else
    could ever have decided is still the bootstrap case. Without ``entities`` any other holder
    counts, the strictest reading.

    It is read from rows nothing erases: the member's acceptance (T-PLT-07 ``activated_at``, set
    once) and the period of an assignment of a role that carries the permission (T-PLT-10
    ``valid_from`` up to the earlier of ``valid_to`` and ``revoked_at``), which must reach past the
    acceptance and have begun by ``at``. A suspension inside that period is not subtracted, and the
    scopes of a person's assignments are added up whether or not their periods met — the measure
    errs towards a person deciding. The role's permissions are read as they are now: a system
    role's never change (BS1-D-31), and a custom role comes into force only through a
    ``ROLE_CHANGE`` that a second access approver decided, whose own assignment already counts."""
    rows = _other_holders(
        session, bootstrap_membership_id=bootstrap_membership_id, permission=permission, at=at
    )
    if entities is None:
        return bool(rows)
    named: dict[UUID, set[UUID]] = {}
    for membership_id, is_all_entities, entity_ids in rows:
        if is_all_entities:
            return True
        named.setdefault(membership_id, set()).update(entity_ids)
    return any(entities.covered_by(frozenset(held)) for held in named.values())


def entities_with_another_approver(
    session: Session,
    *,
    bootstrap_membership_id: UUID,
    permission: str,
    at: datetime,
    entities: SubjectEntities,
) -> frozenset[UUID]:
    """The legal entities of ``entities`` that a person other than the bootstrap Tenant Admin has
    covered as an active holder of ``permission`` — read from the rows, and by the reading, of
    ``second_approver_has_existed`` (04 §14.3 item 3 rev 1.224; the supervisor's ruling of
    2026-10-01 on the independent review of the setup rule, item APR-SETUP-RULE-2).

    The bootstrap exception ends for a request only when ONE other person covers every entity it
    names, so the rule still approves a grant for AVM-DE and AVM-US, or for all entities, when
    another approver has covered AVM-DE alone: that approver does not constrain the grant. The
    audit event of such an approval states these entities beside its basis, so that its reader
    sees what another person did cover. A request for all entities names every entity, so each
    entity another person's assignments name is one of its own. A holder for all entities covers
    every entity a request names — and ends the exception for every request, so the rule approves
    nothing beside one. Empty when nobody else has held the permission."""
    held: set[UUID] = set()
    for _, is_all_entities, entity_ids in _other_holders(
        session, bootstrap_membership_id=bootstrap_membership_id, permission=permission, at=at
    ):
        if is_all_entities:
            held |= entities.ids
        held.update(entity_ids)
    return frozenset(held if entities.all_entities else held & entities.ids)


def _other_holders(
    session: Session, *, bootstrap_membership_id: UUID, permission: str, at: datetime
) -> list[tuple[UUID, bool, frozenset[UUID]]]:
    """One row per assignment through which a person other than the bootstrap Tenant Admin has
    held ``permission`` while ACTIVE in the workspace, by ``at``: the membership, whether the
    assignment is for all entities, and the entities it names (``second_approver_has_existed``
    says what counts)."""
    begins = func.greatest(role_assignment.c.valid_from, tenant_membership.c.activated_at)
    ends = func.least(role_assignment.c.valid_to, role_assignment.c.revoked_at)  # NULLs ignored
    rows = session.execute(
        select(
            role_assignment.c.membership_id,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
        )
        .select_from(
            role_assignment.join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
                    tenant_membership.c.id == role_assignment.c.membership_id,
                ),
            ).join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role_assignment.c.tenant_id,
                    role_permission.c.role_id == role_assignment.c.role_id,
                ),
            )
        )
        .where(
            role_assignment.c.membership_id != bootstrap_membership_id,
            role_permission.c.permission_code == permission,
            tenant_membership.c.activated_at.is_not(None),
            begins <= at,
            or_(ends.is_(None), ends > begins),
            or_(tenant_membership.c.removed_at.is_(None), tenant_membership.c.removed_at > begins),
        )
    ).all()
    return [
        (
            UUID(str(membership_id)),
            bool(is_all_entities),
            frozenset(UUID(str(value)) for value in entity_ids or ()),
        )
        for membership_id, is_all_entities, entity_ids in rows
    ]


def evaluation_admitted(
    kind: object, facts: Mapping[str, object], *, rule_set_code: str | None
) -> bool:
    """Whether the evaluation of a case may report a match (R-41 (7)): the allow-list of R-26 (b)
    as submission applies it, read from the facts of the case. Every kind but ``AUTO_APPROVAL``:
    yes. ``AUTO_APPROVAL``: the subject type and the source channel are on ``AUTO_APPROVABLE``; a
    seeded-only subject matches only in its own seeded rule set, for a USER — and for a role
    assignment a Tenant Admin before setup completes, a USER or the OPERATOR channel on which
    provisioning records the bootstrap admin's own grant
    (``provisioning._grant_bootstrap_admin``). Who the bootstrap Tenant Admin is, and whether a
    second approver has existed, are read from the tenant at submission and are no facts of a
    case."""
    if rule_set_kind(kind) is not RuleSetKind.AUTO_APPROVAL:
        return True
    try:
        subject_type = ApprovalSubjectType(str(facts.get(SUBJECT_TYPE_FIELD)))
        principal_kind = PrincipalKind(str(facts.get(SOURCE_CHANNEL_FIELD)))
    except ValueError:
        return False
    seeded = SEEDED_RULE_SETS.get(subject_type)
    if seeded is None:
        return auto_approval_admitted(subject_type, principal_kind=principal_kind)
    if rule_set_code != seeded:
        return False
    if subject_type is not ApprovalSubjectType.ROLE_ASSIGNMENT:
        return principal_kind is PrincipalKind.USER
    if principal_kind not in (PrincipalKind.USER, PrincipalKind.OPERATOR):
        return False
    role_codes = facts.get("preparer.role_codes")
    held = role_codes if isinstance(role_codes, tuple | list | frozenset | set) else ()
    return BOOTSTRAP_ROLE in held and facts.get("tenant.setup_completed") is False


def evaluated_outputs(
    kind: object, facts: Mapping[str, object], outputs: Mapping[str, object]
) -> dict[str, object]:
    """The outputs a matching rule has in force for ``facts`` (R-41 (7)): for ``APPROVAL_ROUTING``
    the rule's steps raised to the own steps of the subject type the case names, with the second
    step when the case carries one of its second-step flags — what a submission with these facts
    gets; every other kind as written."""
    found = dict(outputs)
    if rule_set_kind(kind) is not RuleSetKind.APPROVAL_ROUTING:
        return found
    steps = found.get("steps")
    try:
        spec = SUBJECTS.get(ApprovalSubjectType(str(facts.get(SUBJECT_TYPE_FIELD))))
    except ValueError:
        spec = None
    if spec is None or not isinstance(steps, list):
        return found
    flags = facts.get(FLAGS_FIELD)
    carried = [str(flag) for flag in flags] if isinstance(flags, tuple | list) else []
    found["steps"] = raised_steps(steps, floor_items(spec, carried))
    return found


def auto_approval(
    session: Session,
    facts: Mapping[str, object],
    *,
    at: datetime,
    rule_set_code: str | None = None,
) -> RuleRef | None:
    """The ``AUTO_APPROVAL`` rule that approves the request at submission, if any (REQ-PLT-016).
    A seeded-only subject — a ``ROLE_ASSIGNMENT``, a ``MIGRATION_SSP_REPLAY`` — is approved only
    by the rule set provisioning seeds for it (04 §14.3 item 2): the caller names that set in
    ``rule_set_code`` and no other rule set is read, so a rule of another set neither approves the
    subject nor outranks the seeded one (R-26 (b); R-41 (7))."""
    seeded = SEEDED_RULE_SETS.get(ApprovalSubjectType(str(facts.get(SUBJECT_TYPE_FIELD))))
    if seeded is not None and rule_set_code != seeded:
        return None
    matched = _matched(session, RuleSetKind.AUTO_APPROVAL, facts, at, rule_set_code=rule_set_code)
    if matched is None or matched[1].get("auto_approve") is not True:
        return None
    return matched[0]


def _steps(session: Session, ref: RuleRef, outputs: Mapping[str, object]) -> tuple[StepPlan, ...]:
    steps = outputs.get("steps")
    where = f"rule {ref.rule_key} of rule set {ref.rule_set_code}"
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"{where} names no steps")
    plans: list[StepPlan] = []
    for step in steps:
        if (
            not isinstance(step, Mapping)
            or not STEP_KEYS <= set(step)
            or not set(step) <= STEP_KEYS | {STEP_ROLE_KEY}
        ):
            raise ValueError(
                f"{where}: a step needs exactly name, permission and min_approvers, "
                "and optionally role"
            )
        name, permission, min_approvers = step["name"], step["permission"], step["min_approvers"]
        if (
            not isinstance(name, str)
            or not isinstance(permission, str)
            or isinstance(min_approvers, bool)
            or not isinstance(min_approvers, int)
        ):
            raise ValueError(f"{where}: malformed step {name!r}")
        plans.append(
            StepPlan(
                name=name,
                permission=permission,
                min_approvers=min_approvers,
                role_id=_step_role_id(session, where, name, step.get(STEP_ROLE_KEY)),
            )
        )
    return tuple(plans)


def _step_role_id(session: Session, where: str, name: str, code: object) -> UUID | None:
    """The active role a published step names (04 T-REF-26 ``role``; D-98 93), or None without one;
    an unknown or inactive code refuses the submission (fail closed) rather than routing without
    the restriction the rule states."""
    if code is None:
        return None
    if not isinstance(code, str) or not code:
        raise ValueError(f"{where}: malformed step {name!r} role")
    found = session.execute(
        select(role.c.id).where(role.c.code == code, role.c.is_active.is_(True))
    ).scalar_one_or_none()
    if found is None:
        raise ValueError(f"{where}: step {name!r} names no active role {code!r}")
    return UUID(str(found))


def _versions(
    session: Session, kind: RuleSetKind, at: datetime, *, rule_set_code: str | None = None
) -> list[tuple[UUID, str]]:
    """The PUBLISHED versions of ``kind`` in force at ``at``, each with its rule set's code — of
    the one rule set ``rule_set_code`` when it is given (a seeded-only subject)."""
    in_force = [
        rule_set_version.c.kind == kind.value,
        rule_set_version.c.status == ConfigStatus.PUBLISHED.value,
        or_(rule_set_version.c.effective_from.is_(None), rule_set_version.c.effective_from <= at),
        or_(rule_set_version.c.effective_to.is_(None), rule_set_version.c.effective_to > at),
    ]
    if rule_set_code is not None:
        in_force.append(rule_set.c.code == rule_set_code)
    return [
        (UUID(str(version_id)), str(code))
        for version_id, code in session.execute(
            select(rule_set_version.c.id, rule_set.c.code)
            .select_from(
                rule_set_version.join(
                    rule_set,
                    and_(
                        rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                        rule_set.c.id == rule_set_version.c.rule_set_id,
                    ),
                )
            )
            .where(*in_force)
            .order_by(rule_set.c.code, rule_set_version.c.id)
        ).all()
    ]


def _admissible_rules(session: Session, kind: RuleSetKind, version_id: UUID) -> list[Any]:
    """The rules of one version that may match at all. R-26 (a), enforced at submission: a stored
    rule that authoring would refuse today — no condition, or an auto-approval rule that names no
    subject type — never matches."""
    return [
        row
        for row in session.execute(
            select(
                rule.c.id,
                rule.c.rule_key,
                rule.c.priority,
                rule.c.specificity,
                rule.c.conditions,
                rule.c.outputs,
            )
            .where(rule.c.rule_set_version_id == version_id)
            .order_by(rule.c.rule_key)
        ).all()
        if admissible(kind, row.conditions)
    ]


def _matched(
    session: Session,
    kind: RuleSetKind,
    facts: Mapping[str, object],
    at: datetime,
    *,
    rule_set_code: str | None = None,
) -> tuple[RuleRef, Mapping[str, object]] | None:
    """The best matching rule of the PUBLISHED versions of ``kind`` in force at ``at`` — of the
    one rule set ``rule_set_code`` when it is given (a seeded-only subject)."""
    best: tuple[tuple[int, int, str, str], RuleRef, Mapping[str, object]] | None = None
    for version_id, code in _versions(session, kind, at, rule_set_code=rule_set_code):
        rows = _admissible_rules(session, kind, version_id)
        ids = {str(row.rule_key): UUID(str(row.id)) for row in rows}
        found = match(
            _RuleSet(
                kind=kind.value,
                rules=tuple(
                    _Rule(
                        rule_key=str(row.rule_key),
                        priority=int(row.priority),
                        specificity=int(row.specificity),
                        conditions=row.conditions,
                        outputs=row.outputs,
                    )
                    for row in rows
                ),
            ),
            facts,
        )
        if found is None:
            continue
        rank = (-found.specificity, -found.priority, found.rule_key, code)
        if best is None or rank < best[0]:
            ref = RuleRef(
                rule_set_version_id=version_id,
                rule_id=ids[found.rule_key],
                rule_set_code=code,
                rule_key=found.rule_key,
            )
            best = (rank, ref, found.outputs)
    return None if best is None else (best[1], best[2])


def possible_winners[T](ranked: Sequence[tuple[bool, T]]) -> tuple[list[T], bool]:
    """Of rules a request's other facts meet, best first — each with whether it also states a
    condition on the amount — the ones that could be the rule that routes the request for SOME
    amount, and whether no rule at all could be the outcome. A rule without a condition on the
    amount matches whatever the amount is: it could win, and nothing ranked below it can."""
    possible: list[T] = []
    for needs_amount, item in ranked:
        possible.append(item)
        if not needs_amount:
            return possible, False
    return possible, True


def possible_steps(
    session: Session,
    facts: Mapping[str, object],
    *,
    fallback: StepPlan | Sequence[StepPlan],
    at: datetime,
) -> tuple[Routing, ...]:
    """Every routing a request with ``facts`` could take for SOME functional amount: the reading
    of a request whose amount could not be stated (item IMP-FLOOR-AMOUNT-1; supervisor ruling
    R-109 (d) — an unevaluated amount counts as the strictest outcome). The rule that routes a
    request is the best one its facts meet (``_matched``), so with the amount unknown every rule
    the OTHER facts meet could be that rule, down to the best-ranked one that states no condition
    on the amount (``possible_winners``). Each one's steps are raised to ``fallback`` exactly as
    ``resolve_steps`` raises them; where every such rule needs the amount, the subject's own
    steps alone are a possible outcome too. The caller asks for all of them."""
    kind = RuleSetKind.APPROVAL_ROUTING
    floor = (fallback,) if isinstance(fallback, StepPlan) else tuple(fallback)
    others = {name: value for name, value in facts.items() if name != AMOUNT_FIELD}
    ranked: list[tuple[tuple[int, int, str, str], bool, RuleRef, Mapping[str, object]]] = []
    for version_id, code in _versions(session, kind, at):
        for row in _admissible_rules(session, kind, version_id):
            on_amount = _conditions_on(row.conditions, AMOUNT_FIELD)
            rest = [
                condition
                for condition in row.conditions
                if not (isinstance(condition, Mapping) and condition.get("field") == AMOUNT_FIELD)
            ]
            candidate = _Rule(
                rule_key=str(row.rule_key),
                priority=int(row.priority),
                # the matcher holds a rule to the number of fields its conditions name
                specificity=int(row.specificity) - (1 if on_amount else 0),
                conditions=rest,
                outputs=row.outputs,
            )
            found = match(_RuleSet(kind=kind.value, rules=(candidate,)), others)
            if found is None:
                continue
            ref = RuleRef(
                rule_set_version_id=version_id,
                rule_id=UUID(str(row.id)),
                rule_set_code=code,
                rule_key=str(row.rule_key),
            )
            rank = (-int(row.specificity), -int(row.priority), str(row.rule_key), code)
            ranked.append((rank, bool(on_amount), ref, found.outputs))
    ranked.sort(key=lambda item: item[0])
    winners, unruled = possible_winners(
        [(needs_amount, (ref, outputs)) for _, needs_amount, ref, outputs in ranked]
    )
    routings = [
        Routing(steps=apply_floor(_steps(session, ref, outputs), floor), rule=ref)
        for ref, outputs in winners
    ]
    if unruled:
        routings.append(Routing(steps=floor, rule=None))
    return tuple(routings)
