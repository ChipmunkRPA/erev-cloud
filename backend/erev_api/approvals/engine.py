"""Approval engine (dev-guide §5.6 DG-KRN-APR-01 to DG-KRN-APR-05; 04 T-PLT-17, T-PLT-18,
T-PLT-20, T-PLT-21; PRD SM-01, BR-PLT-04, BR-PLT-05, BR-PLT-07, ERR-02 to ERR-04; REQ-PLT-011,
REQ-PLT-013 to REQ-PLT-015, REQ-PLT-017).

``submit`` opens one request for a subject: it hashes the subject content, stores the impact
preview of a revenue-affecting subject, numbers the request from series ``APPROVAL`` and creates the
routed steps with the first one ACTIVE. A matching ``AUTO_APPROVAL`` rule approves the request at
submission with one SYSTEM decision naming the rule (REQ-PLT-016). ``insert_request`` and
``record_auto_approval`` serve provisioning too (04 §14.3). ``decide`` records one human decision
under the separation
rules of REQ-PLT-011, directly or through a delegation, and advances the request. The final approval
runs ``SubjectSpec.on_approved`` in the same transaction, so a failing callback rolls the decision
back. A changed subject voids the request, and the void is committed before ``decide`` raises 409
``stale-approval``. ``withdraw`` lets the preparer close a pending request, ``void_if_stale``
voids a pending request whose subject a command changed, and ``bulk_approve`` decides each item in
its own transaction. The DB-10 trigger enforces the same separation in the database.

Notifications follow PRD §5.4 in the deciding transaction: ``APPROVAL_ASSIGNED`` to the holders of
an activated step's permission and their delegates, less the preparer and earlier approvers
(NTF-01); ``ITEM_APPROVED`` and ``ITEM_REJECTED`` to the preparer (NTF-02, NTF-03); and
``APPROVAL_VOIDED`` to the assigned approvers and, for a void, the preparer (NTF-04).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, NoReturn
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from sqlalchemy import Executable, and_, func, insert, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.approvals import preview, quorum, readers, routing
from erev_api.approvals.subjects import (
    ALL_ENTITIES,
    SUBJECTS,
    TENANT_LEVEL,
    DeciderRefusal,
    SubjectEntities,
    SubjectNotVisible,
    SubjectSpec,
    contract_group_entities,
    covered_link,
    spec_for,
    withheld_summary,
)
from erev_api.audit import writer as audit_writer
from erev_api.auth.mfa import VERIFICATION_REQUIRED
from erev_api.auth.permissions import effective_grants
from erev_api.auth.permissions import spec as permission_spec
from erev_api.auth.principal import SYSTEM_DISPLAY_NAME
from erev_api.db import new_id, transitions
from erev_api.db.session import of_session_tenant, system_entity_scope, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_delegation,
    approval_request,
    approval_step,
    legal_entity,
    role,
    tenant_membership,
)
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    MembershipStatus,
    NotificationKind,
    PrincipalKind,
    RuleSetKind,
)
from erev_api.events import notifications
from erev_api.numbering import next_number
from erev_api.problems import (
    Problem,
    ProblemError,
    from_db_error,
    is_period_state_moved,
    period_state_moved,
)
from erev_api.uow import unit_of_work

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.clock import Clock
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "approval_request"
SUBMIT_ACTION: Final = "approval_request.submit"
AUTO_APPROVE_ACTION: Final = "approval_request.auto_approve"
DECISION_ACTIONS: Final[Mapping[str, str]] = MappingProxyType(
    {"APPROVE": "approval_request.approve", "REJECT": "approval_request.reject"}
)
VOID_ACTION: Final = "approval_request.void"
WITHDRAW_ACTION: Final = "approval_request.withdraw"
# 04 T-PLT-17 ``void_reason`` literals.
VOID_STALE_SUBJECT: Final = "STALE_SUBJECT"
VOID_SUBJECT_VOIDED: Final = "SUBJECT_VOIDED"
VOID_WITHDRAWN_BY_PREPARER: Final = "WITHDRAWN_BY_PREPARER"
SERIES: Final = "APPROVAL"
BULK_LIMIT: Final = 200  # 04 API-R-09 `POST /approvals/bulk-approve`: 1 to 200 items
RULE_PREVIEW: Final = "REQ-PLT-015"
RULE_LIFECYCLE: Final = "SM-01"
RULE_REJECT_COMMENT: Final = "T-PLT-20"
RULE_BULK: Final = "REQ-PLT-017"
# PRD §5.5 copy.
PREVIEW_REQUIRED: Final = "Generate the impact preview before submitting this item for approval."
ALREADY_PENDING: Final = "This item already has a pending approval request."
NOT_PENDING: Final = "This approval request is no longer pending."
# 409 for a pending request of a subject type that has no specification yet (04 §16.10 rev 1.224).
NO_SPECIFICATION: Final = "Requests of this subject type cannot be decided or withdrawn yet."
REJECT_COMMENT_REQUIRED: Final = "Add a comment that explains the rejection."
NON_HUMAN_DETAIL: Final = "Only a signed-in person can approve or reject an item."
ROLE_REQUIRED_DETAIL: Final = "This approval step needs a holder of the {role} role."  # CTR-9
OUTSIDE_SCOPE_DETAIL: Final = (
    "This item belongs to legal entities outside your roles, so you cannot submit it for approval."
)
# The same refusal of a preview, which submits nothing (04 §16.10 rev 1.295 "Who may ask for a
# preview"; supervisor ruling R-103 (b) (5); item CTR-PREVIEW-GROUP-SCOPE-1).
OUTSIDE_PREVIEW_DETAIL: Final = (
    "This item belongs to legal entities outside your roles, so you cannot preview it."
)
# The closed reason codes of the kernel's ``DENIED`` events (``record_denial``): never a sentence.
# The preparer — of a submission or of a preview — who does not read in full what they ask about
# (``own_scope_covers``; until 04 rev 1.319: whose roles' entities did not cover it).
DENIED_PREPARER_SCOPE: Final = "PREPARER_SCOPE"
# ``detail.subject_type`` of a refused preview of pending events, which are no stored subject:
# the contract they would be recorded on.
CONTRACT_SUBJECT: Final = "contract"
WITHDRAW_DETAIL: Final = "Only the preparer can withdraw this approval request."
BULK_SIZE: Final = "Approve between 1 and 200 items at a time."
SELF_APPROVAL_DETAIL: Final = "You prepared this item, so another user must approve it."  # ERR-02
# [J] L6-1-Q-13: ERR-02 for a decider the subject excludes, such as the exception owner (DIN-11).
EXCLUDED_DETAIL: Final = "You own this item, so another user must approve it."
# ERR-01 detail for a holder of the step permission who may not decide the item: her authority
# does not reach every legal entity it names (04 §16.10 rev 1.104: one authority covers all of
# them), or she holds it through a delegation and does not herself read every one of them (rev
# 1.319: a delegation conveys the permission, not the view). One sentence, true of both.
EVERY_ENTITY_DETAIL: Final = (
    "Deciding this item takes the approval permission and the permission to read it, "
    "for every legal entity it names."
)
# Why one of the kernel's own checks refused a decision or a withdrawal, as its ``DENIED`` audit
# event states it in ``detail.reason`` (``record_denial``; item APR-DENIED-AUDIT-1). Of a
# decision: the step's permission is not held at all; it is held, and not by one authority for
# every entity of the request; the step's role is not held for those entities; the decider, or
# the delegator they act for, prepared the request; the subject excludes them. Of a withdrawal:
# the caller did not prepare the request. Before a request is read: the caller is no person.
# The two second-factor refusals take the slug of the problem they answer, as the guards of the
# other routes record theirs (DG-KRN-AUTH-05).
DENIED_NO_AUTHORITY: Final = "NO_AUTHORITY"
DENIED_ENTITIES_NOT_COVERED: Final = "ENTITIES_NOT_COVERED"
DENIED_STEP_ROLE: Final = "STEP_ROLE"
DENIED_SELF_APPROVAL: Final = "SELF_APPROVAL"
DENIED_EXCLUDED_DECIDER: Final = "EXCLUDED_DECIDER"
DENIED_NOT_PREPARER: Final = "NOT_PREPARER"
DENIED_NOT_A_PERSON: Final = "NOT_A_PERSON"
DENIED_MFA: Final = "mfa-required"
DENIED_STEP_UP: Final = "mfa-step-up-required"
ALREADY_DECIDED_DETAIL: Final = (  # ERR-03
    "You approved an earlier step of this item. Another approver must decide this step."
)
RULE_STEPS: Final = "T-PLT-18"
# 409 for the person a later step of the request cannot do without (04 §16.10 rev 1.104;
# supervisor ruling R-66 (7)).
SOLE_LATER_DECIDER_DETAIL: Final = (
    "You are the only person who can decide a later step of this item, "
    "so another approver must decide this step."
)
STALE_DETAIL: Final = (  # ERR-04
    "This item changed after submission, so the approval request was voided. "
    "Review the latest version."
)
# SCREENS SCR-IA-06: NTF-01 links to the request; NTF-02 to NTF-04 link to the subject route.
REQUEST_LINK: Final = "/approvals/requests/{request_id}"
VOIDED_BODY: Final = (  # PRD NTF-04
    "The item changed after submission, so the approval request was voided. "
    "Resubmit to route it again."
)
# 04 §14.3 item 3 rev 1.197: the basis the audit event of a grant approved under the bootstrap
# exception states — nobody but the bootstrap Tenant Admin had ever held the step's permission for
# every entity of the request.
BOOTSTRAP_BASIS: Final = "NO_OTHER_APPROVER_FOR_ENTITIES"


@dataclass(frozen=True, slots=True)
class ImpactPreview:
    before: Mapping[str, Any]  # revenue by period, contract balances, journal lines
    after: Mapping[str, Any]
    # The snapshot the subject's own command retained before the submission (a modification's
    # preview, 04 §16.14): both or neither. The request then keeps THAT ``IMPACT_PREVIEW`` file
    # and hash — whose document carries ``before`` and ``after`` — instead of storing a second
    # document (DG-KRN-APR-01 rev 1.75; REQ-PLT-015: the preview is stored with the approval).
    retained_file_id: UUID | None = None
    retained_sha256: str | None = None

    def __post_init__(self) -> None:
        if (self.retained_file_id is None) != (self.retained_sha256 is None):
            raise ValueError("a retained impact preview names its file and its hash")

    def sha256(self) -> str:
        if self.retained_sha256 is not None:
            return self.retained_sha256
        return preview.preview_sha256(self.before, self.after)


@dataclass(frozen=True, slots=True)
class BulkApproveItem:
    """One item of 04 `POST /approvals/bulk-approve`."""

    approval_request_id: UUID
    subject_content_sha256: str
    impact_preview_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class BulkApproveResult:
    """The request status after the attempt (None when the request is not visible) and the
    problem that refused it, if any."""

    approval_request_id: UUID
    status: ApprovalRequestStatus | None
    problem: Problem | None


@dataclass(frozen=True, slots=True)
class _Authority:
    """The delegation a decision relies on; both None when the approver holds the permission."""

    delegation_id: UUID | None = None
    on_behalf_of_id: UUID | None = None


def _execute(session: Session, statement: Executable) -> Any:
    """Execute and map a §14.1 database error to its problem (DG-KRN-ERR-02)."""
    try:
        return session.execute(statement)
    except DBAPIError as error:
        problem = from_db_error(error)
        if problem is None:
            raise
        raise problem from error


def _request_row(session: Session, request_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(select(approval_request).where(approval_request.c.id == request_id))
        .mappings()
        .one()
    )
    return MappingProxyType(dict(row))


def _lock_request(session: Session, request_id: UUID) -> Mapping[str, Any]:
    """The request row under ``FOR UPDATE``; 404 when it is not visible."""
    request = (
        session.execute(
            select(approval_request).where(approval_request.c.id == request_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if request is None:
        raise Problem("not-found")
    return MappingProxyType(dict(request))


def _require_pending(request: Mapping[str, Any]) -> None:
    if request["status"] != ApprovalRequestStatus.PENDING.value:
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=NOT_PENDING)],
        )


def _require_specified(request: Mapping[str, Any]) -> SubjectSpec:
    """The specification of the request's subject type, or 409 ``invalid-transition`` by name for
    a type that has none yet (``subjects.PENDING_SUBJECTS``; 04 §16.10 rev 1.224; the supervisor's
    ruling of 2026-10-01, item APR-SETUP-RULE-2). No command submits such a request, so its row
    comes from a seed; it waits for nobody and ``can_decide`` is false for everyone (R-64 (7)
    (c), R-87 (3)). A decision or a withdrawal of it would run nothing for its subject, so the
    command refuses, where ``spec_for`` raised an error no route answers."""
    spec = SUBJECTS.get(ApprovalSubjectType(request["subject_type"]))
    if spec is None:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(field="subject.type", rule_id=RULE_LIFECYCLE, message=NO_SPECIFICATION)
            ],
        )
    return spec


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """ONE submission-time evaluation of the published routing state — the steps and the
    ``AUTO_APPROVAL`` rule — taken by ``route_submission`` and handed to ``submit`` so a subject
    command binds its own side effects (the judgement hold) and the request's outcome to the same
    reading (DG-KRN-APR-01 / APR-05 rev 1.40; D-98 candidate 101d, Codex ROUTING-R1). Internal:
    built only here, never a request parameter."""

    subject_type: ApprovalSubjectType
    subject_id: UUID
    amount: tuple[Decimal, str] | None
    flags: list[str]
    routed: routing.Routing
    auto_rule: routing.RuleRef | None


class _Unread:
    """Sentinel: ``route_submission`` reads the spec callable (the default)."""


UNREAD: Final = _Unread()


def route_submission(
    uow: UnitOfWork,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    *,
    auto_approval: bool = True,
    amount: tuple[Decimal, str] | None | _Unread = UNREAD,
    flags: Iterable[str] | None = None,
    entities: SubjectEntities | None = None,
) -> RoutingDecision:
    """The routing decision ``submit`` will apply to a request of ``subject_type`` / ``subject_id``
    by this principal now: the subject's amount and flags, the PUBLISHED ``APPROVAL_ROUTING``
    steps and the ``AUTO_APPROVAL`` rule, read ONCE. A subject command that mutates the subject
    according to the outcome (``judgements.submit_judgement`` holds the contract when a person will
    decide) evaluates it under its own locks before the mutation and passes it to ``submit``.

    The floor under the routed steps is the subject's own steps — with the subject's step role and
    its second step (``routing.fallback_steps``) — and the steps its content demands
    (``SubjectSpec.floor``, which reads the request's entities and this instant). ``entities`` is
    what ``submit`` resolved for the request — read here when a subject command routes before it
    submits: their codes are the ``entity.code`` fact the routing rules match (R-66 (8))."""
    subject_type = ApprovalSubjectType(subject_type)
    spec = spec_for(subject_type)
    session = uow.session
    # CTR-17 (D-98 140 Q-5): a subject command whose routing facts live in its stored impact
    # preview (a file the spec callables cannot read from a Session) supplies them here; the
    # request row keeps them (``amount_functional``, ``flags``) as for every other subject.
    with system_entity_scope(session):
        # R-64 (1): what the subject states is read under the tenant's SYSTEM scope, never under
        # the preparer's entity scope, so the routing does not depend on who submits.
        read_amount = (
            spec.amount_functional(session, subject_id) if isinstance(amount, _Unread) else amount
        )
        read_flags = sorted(spec.flags(session, subject_id) if flags is None else flags)
        named = subject_entities(session, spec, subject_id) if entities is None else entities
        content_floor = _content_floor(session, spec, subject_id, named, uow.now)
        codes = entity_codes(session, named)
    routed = routed_steps(
        session,
        spec,
        entity_codes=codes,
        amount=None if read_amount is None else read_amount[0],
        flags=read_flags,
        content_floor=content_floor,
        at=uow.now,
    )
    return RoutingDecision(
        subject_type=subject_type,
        subject_id=subject_id,
        amount=read_amount,
        flags=read_flags,
        routed=routed,
        auto_rule=auto_approval_rule(
            uow, subject_type, auto_approval=auto_approval, entities=named
        ),
    )


def routed_steps(
    session: Session,
    spec: SubjectSpec,
    *,
    entity_codes: Sequence[str],
    amount: Decimal | None,
    flags: Sequence[str],
    content_floor: Sequence[routing.StepPlan] = (),
    at: datetime,
) -> routing.Routing:
    """The steps a request of ``spec`` takes with these routing facts, and the rule that chose
    them: the PUBLISHED ``APPROVAL_ROUTING`` rules over the subject's own steps as the floor.
    ``route_submission`` applies exactly this reading, and the evaluation of a rule set version
    against a case answers the same (``routing.evaluated_outputs``; R-66 (8))."""
    return routing.resolve_steps(
        session,
        routing.routing_facts(
            subject_type=spec.subject_type,
            entity_codes=entity_codes,
            amount_functional=amount,
            flags=flags,
        ),
        fallback=_own_steps(session, spec, flags, content_floor),
        at=at,
    )


def possible_routed_steps(
    session: Session,
    spec: SubjectSpec,
    *,
    entity_codes: Sequence[str],
    flags: Sequence[str],
    content_floor: Sequence[routing.StepPlan] = (),
    at: datetime,
) -> tuple[routing.Routing, ...]:
    """``routed_steps`` for a request whose functional amount could not be stated: every routing
    it could take for SOME amount (``routing.possible_steps``; item IMP-FLOOR-AMOUNT-1,
    supervisor ruling R-109 (d)). The caller holds its approvers to all of them — the strictest
    outcome, never a guess at the amount."""
    return routing.possible_steps(
        session,
        routing.routing_facts(
            subject_type=spec.subject_type,
            entity_codes=entity_codes,
            amount_functional=None,
            flags=flags,
        ),
        fallback=_own_steps(session, spec, flags, content_floor),
        at=at,
    )


def _own_steps(
    session: Session,
    spec: SubjectSpec,
    flags: Sequence[str],
    content_floor: Sequence[routing.StepPlan],
) -> tuple[routing.StepPlan, ...]:
    """The subject's own steps for a request with ``flags`` — the steps without a matching rule
    and the floor under one (R-26 (c)) — followed by the steps its content adds."""
    return (
        *routing.fallback_steps(
            spec,
            flags,
            step_role_id=_role_id(session, spec, spec.step_role),
            second_step_role_id=_second_step_role_id(session, spec, flags),
        ),
        *content_floor,
    )


def entity_codes(session: Session, entities: SubjectEntities) -> tuple[str, ...]:
    """The ``entity.code`` fact of a request (04 T-REF-26 rev 1.104; supervisor ruling R-66 (8)):
    the codes of the legal entities it names — of every entity of the tenant for a subject that
    spans them all, and none for a tenant-level subject, which no ``entity.code`` condition
    matches. Called under the tenant's SYSTEM scope (``route_submission``; a subject's own
    ``floor`` and ``deciders``)."""
    statement = select(legal_entity.c.code)
    if not entities.all_entities:
        if not entities.ids:
            return ()
        statement = statement.where(legal_entity.c.id.in_(sorted(entities.ids)))
    return tuple(sorted(str(code) for code in session.scalars(statement)))


def source_channel(principal: Principal) -> str:
    """The ``source.channel`` fact (04 T-REF-26 rev 1.104; R-66 (8)): the kind of principal the
    item comes from — the preparer's kind, and ``USER`` for a SYSTEM principal that acts on behalf
    of a user, because a job a person started carries that person's content (R-41 (7)). A case
    with the channel ``SYSTEM`` is therefore a job that acts for no user, in an evaluation as at
    a submission."""
    if principal.kind is PrincipalKind.SYSTEM and principal.on_behalf_of_id is not None:
        return PrincipalKind.USER.value
    return principal.kind.value


def auto_approval_rule(
    uow: UnitOfWork,
    subject_type: ApprovalSubjectType,
    *,
    auto_approval: bool = True,
    entities: SubjectEntities | None = None,
) -> routing.RuleRef | None:
    """The ``AUTO_APPROVAL`` rule ``submit`` will apply to a request of ``subject_type`` by this
    principal now — None when a person will decide. The facts are the subject type, the preparer's
    roles, the tenant's setup state and the source channel, never the subject's content, so a
    subject command may evaluate it BEFORE mutating the subject (DG-KRN-APR-05 rev 1.40; D-98
    candidate 101d: ``judgements.submit_judgement`` applies its hold before the basis is hashed
    exactly when the request will wait for a person). ``entities`` is the set the request names:
    the bootstrap exception of a ``ROLE_ASSIGNMENT`` ends per request (``_seeded_admitted``).

    REQ-PLT-016 admits system-originated standard items only (supervisor rulings R-26 (b), R-38 and
    R-41 (7); DG-KRN-APR-08). No rule is read unless the subject type and the source channel are
    on ``routing.AUTO_APPROVABLE`` — a SYSTEM principal only when it acts on behalf of no user
    (``source_channel``) — or the subject is one of the two seeded-only subjects, whose own
    seeded rule set alone is read, and only on what the tenant's rows tell (``_seeded_admitted``).
    The allow-list is applied by the function that answers the evaluation of a case
    (``routing.evaluation_admitted``), so the two cannot differ (R-66 (8)). So a published rule
    cannot approve a person's own configuration, access, close or journal item."""
    if not auto_approval:
        return None
    session = uow.session
    principal = uow.principal
    subject_type = ApprovalSubjectType(subject_type)
    setup_completed = routing.setup_completed(session, principal.tenant_id)
    seeded = routing.seeded_rule_set(subject_type)
    facts = routing.auto_approval_facts(
        subject_type=subject_type,
        preparer_role_codes=principal.roles,
        setup_completed=setup_completed,
        source_channel=source_channel(principal),
    )
    if not routing.evaluation_admitted(RuleSetKind.AUTO_APPROVAL, facts, rule_set_code=seeded):
        return None
    if seeded is not None and not _seeded_admitted(
        uow, subject_type, setup_completed=setup_completed, entities=entities
    ):
        return None
    return routing.auto_approval(session, facts, at=uow.now, rule_set_code=seeded)


def _seeded_admitted(
    uow: UnitOfWork,
    subject_type: ApprovalSubjectType,
    *,
    setup_completed: bool,
    entities: SubjectEntities | None = None,
) -> bool:
    """Whether the seeded rule set of a seeded-only subject is read for this request (04 §14.3
    rev 1.104; R-38 (iv) and its addendum; R-41 (7); R-66 (2) and R-73). Both subjects are
    prepared by a signed-in member. ``MIGRATION_SSP_REPLAY``: the request
    ``POST /migrations/{id}/import`` submits, whose two guards the route enforces.
    ``ROLE_ASSIGNMENT`` — the bootstrap exception of PRD BR-PLT-02, "a new tenant has no second
    approver": the preparer is THE bootstrap Tenant Admin (the user of the assignment the seed of
    the workspace wrote, known by the grant's own request: ``routing.is_bootstrap_admin``, 04
    §14.3 item 2 rev 1.254) and still holds that role, setup is incomplete, and no OTHER person
    has ever been active in the workspace while holding the step's permission for every entity of
    the request (``routing.second_approver_has_existed``; per request since 04 rev 1.197 —
    ``entities`` is the set the request names, and without it any other holder counts). The
    exception ends one way, per coverage: once such a person has existed, every grant of those
    entities waits for a person, whatever became of that approver since — a workspace left
    without a second approver is shown as such and repaired by the operator, never by the
    exception coming back."""
    principal = uow.principal
    if principal.kind is not PrincipalKind.USER or principal.membership_id is None:
        return False
    if subject_type is not ApprovalSubjectType.ROLE_ASSIGNMENT:
        return True
    if setup_completed or routing.BOOTSTRAP_ROLE not in principal.roles:
        return False
    if not routing.is_bootstrap_admin(uow.session, principal.membership_id):
        return False
    return not routing.second_approver_has_existed(
        uow.session,
        bootstrap_membership_id=principal.membership_id,
        permission=spec_for(subject_type).required_permission,
        at=uow.now,
        entities=entities,
    )


def _refuse_pending(session: Session, subject_type: ApprovalSubjectType, subject_id: UUID) -> None:
    """409 ``invalid-transition`` when the subject has a PENDING request the session reads.
    ``submit`` asks it twice: first under its caller's scope, as before, and again under the
    tenant's once the kernel's question has admitted the caller — a request of one entity that
    the route's permission does not cover is hidden from the first by the row policy (04 §16.10
    rev 1.319)."""
    pending = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == subject_type.value,
            approval_request.c.subject_id == subject_id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
    ).first()
    if pending is not None:
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(rule_id=RULE_LIFECYCLE, message=ALREADY_PENDING)],
        )


def submit(
    uow: UnitOfWork,
    *,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    summary: str,
    impact_preview: ImpactPreview | None = None,
    comment: str | None = None,
    reason_code: str | None = None,
    auto_approval: bool = True,
    routing_decision: RoutingDecision | None = None,
    amount: tuple[Decimal, str] | None | _Unread = UNREAD,
    flags: Iterable[str] | None = None,
) -> Mapping[str, Any]:
    """Open a PENDING request for the subject with its first step ACTIVE (DG-KRN-APR-01).

    The subject command authorizes the preparer before calling. A revenue-affecting subject
    without a preview is 422 ``validation-failed`` (REQ-PLT-015); a subject with a pending request
    is 409 ``invalid-transition``. Steps come from the PUBLISHED routing rules. When an
    ``AUTO_APPROVAL`` rule matches, the request is APPROVED before it is returned and
    ``SubjectSpec.on_approved`` runs in the same transaction (REQ-PLT-016). ``auto_approval =
    False`` keeps a non-standard item away from the auto-approval rules (BUILD_SPEC CTR-9).
    ``routing_decision`` is the subject command's own ``route_submission`` reading (rev 1.40; Codex
    ROUTING-R1): when given, the steps and the auto-approval rule are NOT read again, so the
    command's side effects and the request's outcome bind to one evaluation of the published state.
    A reading that auto-approves beside ``auto_approval = False`` is a contradiction and raises
    ``ValueError`` (R-66 (9)): the command that withholds auto-approval says so when it reads.
    ``amount`` and ``flags`` (rev 1.273; item ACT-FLAGS-1) are the routing facts of a subject
    command that holds what a Session cannot read — ``activation.submit_activation`` holds its dry
    run: they are handed to this function's own ``route_submission``, which then reads neither
    from the subject specification, and the request row keeps them. The command reads no routing
    of its own, so the rule of R-66 (9) stands as it was; beside a ``routing_decision`` they are a
    second statement of the same facts and raise ``ValueError``.

    A preparer who does not read in full what the request would put in force — one read
    permission of the subject for every entity the preparer is held to (``own_scope_covers``; 04
    §16.10 rev 1.319) — is refused by name, 403 ``forbidden``, with its ``DENIED`` audit event
    (``refuse_outside_scope``; R-64 (6); 04 §16.10 rev 1.295). Once that question has answered,
    the request's row is the kernel's: it is looked for, inserted, auto-approved and read back
    under the tenant's scope, whatever the scope of the caller's route (rev 1.319).
    """
    subject_type = ApprovalSubjectType(subject_type)
    spec = spec_for(subject_type)
    session = uow.session
    principal = uow.principal
    if (spec.revenue_affecting or spec.proposal_content is not None) and impact_preview is None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field="impact_preview", rule_id=RULE_PREVIEW, message=PREVIEW_REQUIRED)
            ],
        )
    _refuse_pending(session, subject_type, subject_id)

    with system_entity_scope(session):
        # R-64 (1): the content and the entity set are what the SUBJECT states, read under the
        # tenant's SYSTEM scope — tenant isolation only — so the hash a decider recomputes is the
        # hash stored here whoever the two are.
        if spec.proposal_content is not None and impact_preview is not None:
            content_sha256 = sha256_hex(spec.proposal_content(session, impact_preview.after))
        else:
            content_sha256 = sha256_hex(spec.content(session, subject_id))
        entities, asked = _scope_of(session, spec, subject_id, impact_preview)
    # R-64 (6): a preparer who does not read every entity the subject names submits nothing — it
    # could not read all of what it asks others to approve. One refusal by name, whether the
    # request would name one entity or several, and on record since 04 rev 1.295. It is the only
    # check of the preparer's entities: the row is inserted under the tenant's scope below.
    refuse_outside_scope(
        uow, asked, action=SUBMIT_ACTION, subject_type=subject_type.value, subject_id=subject_id
    )
    # 04 §16.10 rev 1.319 ("The request's row is the kernel's"): the question has answered, and
    # from here the question decides, not the route. ``approval_request`` is under the entity
    # policy on ``entity_id``; the command's transaction reads under the scope of its route's
    # permission (04 API-C-03), which need not hold the one entity a request names — an import's
    # route asks ``import.upload`` while its rows name the entities of the template's write
    # permission (R-29). So a pending request the caller's transaction cannot read is looked for
    # again here, and the row is inserted, auto-approved and read back below, under the tenant's
    # scope — where the content and the hooks already are.
    with system_entity_scope(session):
        _refuse_pending(session, subject_type, subject_id)
    if routing_decision is None:
        routing_decision = route_submission(
            uow,
            subject_type,
            subject_id,
            auto_approval=auto_approval,
            amount=amount,
            flags=flags,
            entities=entities,
        )
    elif flags is not None or not isinstance(amount, _Unread):
        raise ValueError("amount or flags beside a routing decision that states them")
    elif (routing_decision.subject_type, routing_decision.subject_id) != (subject_type, subject_id):
        raise ValueError("routing decision of another subject")
    elif not auto_approval and routing_decision.auto_rule is not None:
        # R-66 (9): a command that withholds auto-approval takes its reading with
        # ``route_submission(auto_approval=False)``; a reading that auto-approves contradicts it.
        raise ValueError("auto_approval=False with a routing decision that auto-approves")
    amount = routing_decision.amount
    flags = routing_decision.flags
    preview_file_id: UUID | None = None
    preview_sha256: str | None = None
    if impact_preview is not None:
        preview_sha256 = impact_preview.sha256()
        if impact_preview.retained_file_id is not None:
            preview_file_id = preview.retained_snapshot(
                session, impact_preview.retained_file_id, preview_sha256
            )
        else:
            stored = preview.store_preview(
                uow, before=impact_preview.before, after=impact_preview.after
            )
            preview_file_id = stored["id"]
    routed = routing_decision.routed
    auto_rule = routing_decision.auto_rule

    request_id = new_id()
    request_no = next_number(uow, SERIES)
    with system_entity_scope(session):
        insert_request(
            session,
            values={
                "tenant_id": principal.tenant_id,
                "id": request_id,
                "request_no": request_no,
                "subject_type": subject_type.value,
                "subject_id": subject_id,
                "subject_content_sha256": content_sha256,
                "summary": summary,
                **entity_columns(entities),
                "amount_functional": None if amount is None else amount[0],
                "amount_currency": None if amount is None else amount[1],
                "flags": flags,
                "preparer_id": principal.id,
                "preparer_kind": principal.kind.value,
                "impact_preview_file_id": preview_file_id,
                "impact_preview_sha256": preview_sha256,
                "reason_code": reason_code,
                "comment": comment,
                "created_by": principal.id,
                "created_by_kind": principal.kind.value,
            },
            routed=routed,
            now=uow.now,
        )
        uow.audit(
            action=SUBMIT_ACTION,
            object_type=OBJECT_TYPE,
            object_id=request_id,
            after=submit_audit_after(
                request_no=request_no,
                subject_type=subject_type,
                subject_id=subject_id,
                subject_content_sha256=content_sha256,
                impact_preview_sha256=preview_sha256,
                routed=routed,
                entities=entities,
                role_codes=role_codes(session, routed.steps),
            ),
            reason_code=reason_code,
            comment=comment,
            approval_request_id=request_id,
        )
        if auto_rule is not None:
            record_auto_approval(
                session,
                tenant_id=principal.tenant_id,
                approval_request_id=request_id,
                subject_content_sha256=content_sha256,
                rule=auto_rule,
                now=uow.now,
            )
            uow.audit(
                action=AUTO_APPROVE_ACTION,
                object_type=OBJECT_TYPE,
                object_id=request_id,
                before={"status": ApprovalRequestStatus.PENDING.value},
                after=auto_approve_audit_after(
                    auto_rule, basis=_auto_basis(uow, subject_type, auto_rule, entities)
                ),
                approval_request_id=request_id,
            )
            with system_entity_scope(session):
                spec.on_approved(uow, subject_id, request_id)
            approved = _request_row(session, request_id)
            told = _preparer_summary(uow, approved)
            _notify_preparer(
                uow,
                spec,
                approved,
                NotificationKind.ITEM_APPROVED,
                title=f"Approved: {told}",
                body=f"{SYSTEM_DISPLAY_NAME} approved {told}.",
            )
        else:
            _notify_assigned(uow, request_id)
        return _request_row(session, request_id)


def _preparer_entities(
    session: Session, spec: SubjectSpec, subject_id: UUID, entities: SubjectEntities
) -> SubjectEntities:
    """The entities the preparer of a new request is held to (supervisor rulings R-64 (6) and
    R-106 (b); 04 §16.10 rev 1.104): those of what the request would put in force. They are the
    entities of the request (``entities``), unless the subject states a NARROWER set
    (``SubjectSpec.preparer_entities``) — named entities, at least one, every one of them among
    the entities the request names. The statement fails closed: one that names an entity the
    request does not, an unresolved one (every entity), an empty one beside a request that names
    entities, and any statement beside a request that spans every entity are no narrowing, and
    the preparer is then held to the request's entities and the stated ones together."""
    if spec.preparer_entities is None:
        return entities
    stated = spec.preparer_entities(session, subject_id)
    if stated.all_entities or entities.all_entities:
        return ALL_ENTITIES
    if stated.ids and stated.ids <= entities.ids:
        return stated
    return SubjectEntities(entities.ids | stated.ids)


def _scope_of(
    session: Session, spec: SubjectSpec, subject_id: UUID, impact_preview: ImpactPreview | None
) -> tuple[SubjectEntities, SubjectEntities]:
    """(The entities of a request of the subject as it stands, the entities its preparer is held
    to.) The caller holds the tenant's SYSTEM scope: what a subject states does not depend on who
    asks (R-64 (1))."""
    entities = _submission_entities(session, spec, subject_id, impact_preview)
    return entities, _preparer_entities(session, spec, subject_id, entities)


def preparer_scope(
    session: Session, subject_type: ApprovalSubjectType, subject_id: UUID
) -> SubjectEntities:
    """The entities the preparer of a STORED subject is held to now, read as ``submit`` reads them:
    under the tenant's SYSTEM scope, so that an entity the caller cannot read is named and not
    guessed (R-64 (1), (6); dev-guide DG-KRN-APR-07 rev 1.279)."""
    spec = spec_for(ApprovalSubjectType(subject_type))
    with system_entity_scope(session):
        return _scope_of(session, spec, subject_id, None)[1]


def contract_scope(session: Session, contract_id: UUID) -> SubjectEntities:
    """The entities a subject of one contract is bound to — the contracting entities of every
    current member of its combination group (``subjects.contract_group_entities``; R-87 (1)) —
    for what is asked about a contract before a subject of it is stored: the pending events of
    a preview. Read under the tenant's SYSTEM scope, as a stored subject's are."""
    with system_entity_scope(session):
        return contract_group_entities(session, [contract_id])


def refuse_outside_scope(
    uow: UnitOfWork,
    asked: SubjectEntities,
    *,
    action: str,
    subject_type: str,
    sentence: str = OUTSIDE_SCOPE_DETAIL,
    permission: str = "",
    subject_id: UUID | None = None,
) -> None:
    """Pass when the caller reads ``asked`` in full — one read permission of a subject of
    ``subject_type`` for every entity of it (``own_scope_covers``; 04 §16.10 rev 1.319);
    otherwise put the refusal on record and raise it: 403 ``forbidden`` with ``sentence`` (R-64
    (6); 04 §16.10 rev 1.295; dev-guide DG-KRN-APR-07 rev 1.279). The one function of the kernel
    that refuses a caller who does not cover what they ask about — a submission and a preview
    alike.

    The ``DENIED`` audit event is written first (``record_denial``, reason
    ``DENIED_PREPARER_SCOPE``): ``action`` is the audit action of the refused command,
    ``permission`` the one it ran under where its command says it, and the subject is named as
    the caller holds it. Like the answer the event names no entity."""
    if own_scope_covers(uow.principal, subject_type, asked):
        return
    record_denial(
        uow,
        action=action,
        reason=DENIED_PREPARER_SCOPE,
        permission=permission,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    raise Problem("forbidden", sentence)


def require_preparer_scope(
    uow: UnitOfWork, subject_type: ApprovalSubjectType, subject_id: UUID
) -> None:
    """The question of ``submit``, asked by a subject command BEFORE its own findings (04 §16.10
    rev 1.295 "A modification's submission asks first"; R-64 (1), (6)): the findings of a
    submission read the subject, and under a scope that cannot read the subject whole they are
    not the subject's — the refusal by name comes first. The answer and its event are those of
    ``submit``."""
    subject_type = ApprovalSubjectType(subject_type)
    refuse_outside_scope(
        uow,
        preparer_scope(uow.session, subject_type, subject_id),
        action=SUBMIT_ACTION,
        subject_type=subject_type.value,
        subject_id=subject_id,
    )


def require_preview_scope(
    uow: UnitOfWork,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    *,
    action: str,
    permission: str,
) -> None:
    """A preview is asked by who could submit the subject (04 §16.10 rev 1.295 "Who may ask for
    a preview"; supervisor ruling R-103 (b) (5); item CTR-PREVIEW-GROUP-SCOPE-1). A dry run reads
    its group whole and its summary holds the group's figures, so the command that defers one
    asks first whether the caller covers every entity the stored subject is bound to — the
    question of ``submit`` with a sentence of its own. ``action`` is the audit action of the
    command that is refused, ``permission`` the one it ran under."""
    subject_type = ApprovalSubjectType(subject_type)
    refuse_outside_scope(
        uow,
        preparer_scope(uow.session, subject_type, subject_id),
        action=action,
        sentence=OUTSIDE_PREVIEW_DETAIL,
        permission=permission,
        subject_type=subject_type.value,
        subject_id=subject_id,
    )


def require_contract_preview_scope(
    uow: UnitOfWork, contract_id: UUID, *, action: str, permission: str
) -> None:
    """``require_preview_scope`` for what is no stored subject: the pending events of a contract,
    which take the set of their contract (``contract_scope``) and are named by it."""
    refuse_outside_scope(
        uow,
        contract_scope(uow.session, contract_id),
        action=action,
        sentence=OUTSIDE_PREVIEW_DETAIL,
        permission=permission,
        subject_type=CONTRACT_SUBJECT,
        subject_id=contract_id,
    )


def subject_entities(session: Session, spec: SubjectSpec, subject_id: UUID) -> SubjectEntities:
    """The legal entities a subject is bound to now (R-25; 04 T-PLT-17 rev 1.104):
    ``spec.entities`` for a subject that can span several, else the one entity of
    ``spec.entity_id`` — None there is a tenant-level subject."""
    if spec.entities is not None:
        return spec.entities(session, subject_id)
    entity_id = spec.entity_id(session, subject_id)
    return TENANT_LEVEL if entity_id is None else SubjectEntities(frozenset({entity_id}))


def _submission_entities(
    session: Session, spec: SubjectSpec, subject_id: UUID, impact_preview: ImpactPreview | None
) -> SubjectEntities:
    """The entities of a new request: what the proposal names for a subject without a row
    (``SubjectSpec.proposal_entities``; R-41 (4)), else ``subject_entities``."""
    if spec.proposal_entities is not None and impact_preview is not None:
        return spec.proposal_entities(session, impact_preview.after)
    return subject_entities(session, spec, subject_id)


def current_entities(
    uow: UnitOfWork, spec: SubjectSpec, request: Mapping[Any, Any]
) -> SubjectEntities:
    """The entities the subject of ``request`` states NOW (R-41 (2)): of its stored proposal for a
    subject without a row, else of its row. ``decide`` compares them with the set the request
    froze at submission."""
    with system_entity_scope(uow.session):
        if spec.proposal_entities is not None:
            return spec.proposal_entities(uow.session, preview.request_proposal(uow, request["id"]))
        return subject_entities(uow.session, spec, request["subject_id"])


def entities_audit(entities: SubjectEntities) -> dict[str, Any]:
    """The entity set as audit events state it: the ids in ascending order and whether the subject
    spans every entity."""
    return {
        "entity_ids": sorted(str(entity_id) for entity_id in entities.ids),
        "all_entities": entities.all_entities,
    }


def entity_columns(entities: SubjectEntities) -> dict[str, Any]:
    """The T-PLT-17 columns that freeze ``entities`` on a request at submission: ``entity_id`` for
    exactly one entity (the RLS-TE key), ``entity_ids`` for several and ``is_all_entities`` for a
    subject that spans every entity (``ck_approval_request__entity_scope``)."""
    ids = sorted(entities.ids)
    return {
        "entity_id": ids[0] if len(ids) == 1 else None,
        "entity_ids": ids if len(ids) > 1 else [],
        "is_all_entities": entities.all_entities,
    }


def request_entities(request: Mapping[str, Any]) -> SubjectEntities:
    """The entities a request froze at submission (``entity_columns`` read back). Every authority
    check reads them from here: the step permission, a delegation and a step's role each have to
    cover ALL of them (DG-KRN-APR-06)."""
    if request["is_all_entities"]:
        return ALL_ENTITIES
    if request["entity_id"] is not None:
        return SubjectEntities(frozenset({UUID(str(request["entity_id"]))}))
    return SubjectEntities(frozenset(UUID(str(value)) for value in request["entity_ids"] or ()))


def _role_id(session: Session, spec: SubjectSpec, code: str | None) -> UUID | None:
    """The active role ``code`` a step of ``spec`` names (04 T-PLT-18 ``required_role_id``), or
    None without one; ``LookupError`` when the named role is not active (XR-12: never a step
    without the restriction the subject states)."""
    if code is None:
        return None
    found = session.execute(
        select(role.c.id).where(role.c.code == code, role.c.is_active.is_(True))
    ).scalar_one_or_none()
    if found is None:
        raise LookupError(f"role {code} of {spec.subject_type} is not active")
    return UUID(str(found))


def _second_step_role_id(session: Session, spec: SubjectSpec, flags: Sequence[str]) -> UUID | None:
    """The role that narrows the fallback's second step (04 T-PLT-18 ``required_role_id``;
    BUILD_SPEC CTR-9); ``LookupError`` when the named role is not active (XR-12)."""
    if spec.second_step_flags.isdisjoint(flags):
        return None
    return _role_id(session, spec, spec.second_step_role)


def _content_floor(
    session: Session, spec: SubjectSpec, subject_id: UUID, entities: SubjectEntities, at: datetime
) -> tuple[routing.StepPlan, ...]:
    """The steps the subject's content demands besides its own (``SubjectSpec.floor``; R-38 (ii),
    R-92): part of the floor the routed steps are raised to."""
    if spec.floor is None:
        return ()
    return tuple(
        routing.StepPlan(
            name=step.name,
            permission=step.permission,
            min_approvers=step.min_approvers,
            role_id=_role_id(session, spec, step.role),
        )
        for step in spec.floor(session, subject_id, entities, at)
    )


def role_codes(session: Session, steps: Sequence[routing.StepPlan]) -> dict[UUID, str]:
    """Role id → code of the roles ``steps`` name: for the audit event of the submission, and
    for a subject that states the steps of another one (``SubjectSpec.floor``)."""
    ids = sorted({step.role_id for step in steps if step.role_id is not None})
    if not ids:
        return {}
    return {
        UUID(str(role_id)): str(code)
        for role_id, code in session.execute(
            select(role.c.id, role.c.code).where(role.c.id.in_(ids))
        )
    }


def _step_role(session: Session, role_id: UUID | None) -> Mapping[str, Any] | None:
    if role_id is None:
        return None
    return dict(
        session.execute(select(role.c.code, role.c.name).where(role.c.id == role_id))
        .mappings()
        .one()
    )


def _holds_role(principal: Principal, code: str, entities: SubjectEntities) -> bool:
    """The principal holds role ``code`` through assignments that cover every entity of the subject
    (04 T-PLT-18 rev 1.104; REQ-PLT-012; SC-N5): a role held for another entity does not count."""
    scope = principal.role_scopes.get(code)
    return scope is not None and entities.covered_by(scope)


def _holds_step_role(
    principal: Principal, step_role: Mapping[str, Any] | None, entities: SubjectEntities
) -> bool:
    """04 T-PLT-18 ``required_role_id`` narrows a step to holders of the role (BUILD_SPEC CTR-9)
    for the subject's entities."""
    return step_role is None or _holds_role(principal, str(step_role["code"]), entities)


def _rule_audit(rule: routing.RuleRef | None) -> dict[str, str] | None:
    if rule is None:
        return None
    return {
        "rule_set_code": rule.rule_set_code,
        "rule_key": rule.rule_key,
        "rule_set_version_id": str(rule.rule_set_version_id),
        "rule_id": str(rule.rule_id),
    }


def submit_audit_after(
    *,
    request_no: str,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    subject_content_sha256: str,
    impact_preview_sha256: str | None,
    routed: routing.Routing,
    entities: SubjectEntities = TENANT_LEVEL,
    role_codes: Mapping[UUID, str] | None = None,
) -> dict[str, Any]:
    """The ``after`` payload of ``approval_request.submit``: the request's identity and hashes,
    the entities it froze (R-41 (8)), the routing rule and the steps as created — each with the
    role code it is narrowed to, when it names one (R-41 (7))."""
    codes = role_codes or {}
    return {
        "request_no": request_no,
        "subject_type": subject_type.value,
        "subject_id": str(subject_id),
        "subject_content_sha256": subject_content_sha256,
        "impact_preview_sha256": impact_preview_sha256,
        "entities": entities_audit(entities),
        "routing_rule": _rule_audit(routed.rule),
        "steps": [
            {"name": plan.name, "permission": plan.permission, "min_approvers": plan.min_approvers}
            | ({} if plan.role_id is None else {"role": codes.get(plan.role_id, str(plan.role_id))})
            for plan in routed.steps
        ],
    }


def auto_approve_audit_after(
    rule: routing.RuleRef, *, basis: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The ``after`` payload of ``approval_request.auto_approve``; ``basis`` holds the members
    that state what the engine established from the tenant's rows before it read a seeded rule
    (``_auto_basis``)."""
    return {
        "status": ApprovalRequestStatus.APPROVED.value,
        "approver_kind": PrincipalKind.SYSTEM.value,
        "auto_rule": _rule_audit(rule),
        **(basis or {}),
    }


def _auto_basis(
    uow: UnitOfWork,
    subject_type: ApprovalSubjectType,
    rule: routing.RuleRef,
    entities: SubjectEntities,
) -> dict[str, Any]:
    """The members by which the audit event of an automatic approval states its basis (04 §14.3
    item 3 rev 1.197 and rev 1.224): a grant approved under the bootstrap exception was one whose
    entities no ONE approver but the bootstrap Tenant Admin had ever covered (``_seeded_admitted``)
    — ``basis`` — and ``entity_ids_with_another_approver`` names, in ascending order, the entities
    of the request that another approver did cover, each for a part of it
    (``routing.entities_with_another_approver``): empty when nobody else has approved access. A
    scoped second approver does not constrain a grant that reaches beyond its scope, and the
    trail says so (the supervisor's ruling of 2026-10-01, item APR-SETUP-RULE-2). No member for
    any other automatic approval."""
    if (
        subject_type is not ApprovalSubjectType.ROLE_ASSIGNMENT
        or rule.rule_set_code != routing.AUTO_BOOTSTRAP
    ):
        return {}
    membership_id = uow.principal.membership_id
    if membership_id is None:  # ``_seeded_admitted`` reads the seeded rule for a member only
        raise ValueError("the bootstrap rule approves the request of a member only")
    covered = routing.entities_with_another_approver(
        uow.session,
        bootstrap_membership_id=membership_id,
        permission=spec_for(subject_type).required_permission,
        at=uow.now,
        entities=entities,
    )
    return {
        "basis": BOOTSTRAP_BASIS,
        "entity_ids_with_another_approver": sorted(str(entity_id) for entity_id in covered),
    }


def insert_request(
    session: Session, *, values: Mapping[str, Any], routed: routing.Routing, now: datetime
) -> UUID:
    """Insert a PENDING request with the routed steps, the first one ACTIVE.

    ``values`` holds the T-PLT-17 subject, preparer, preview and SC-C columns; the status, step
    number, submission time and routing rule are set here.
    """
    tenant_id, request_id = values["tenant_id"], values["id"]
    _execute(
        session,
        insert(approval_request).values(
            **values,
            status=ApprovalRequestStatus.PENDING.value,
            current_step_no=1,
            submitted_at=now,
            created_at=now,
            routing_rule_set_version_id=(
                None if routed.rule is None else routed.rule.rule_set_version_id
            ),
            routing_rule_id=None if routed.rule is None else routed.rule.rule_id,
        ),
    )
    _execute(
        session,
        insert(approval_step).values(
            [
                {
                    "tenant_id": tenant_id,
                    "id": new_id(),
                    "approval_request_id": request_id,
                    "step_no": step_no,
                    "name": plan.name,
                    "required_permission": plan.permission,
                    "required_role_id": plan.role_id,
                    "min_approvers": plan.min_approvers,
                    "status": (
                        ApprovalStepStatus.ACTIVE if step_no == 1 else ApprovalStepStatus.WAITING
                    ).value,
                    "activated_at": now if step_no == 1 else None,
                }
                for step_no, plan in enumerate(routed.steps, start=1)
            ]
        ),
    )
    return UUID(str(request_id))


def record_auto_approval(
    session: Session,
    *,
    tenant_id: UUID,
    approval_request_id: UUID,
    subject_content_sha256: str,
    rule: routing.RuleRef,
    now: datetime,
) -> None:
    """One ``AUTO_APPROVE`` decision by SYSTEM on the active first step, naming the rule set
    version and rule; the step is APPROVED, later steps SKIPPED and the request APPROVED
    (REQ-PLT-016; SPEC-Q-173). The caller audits and runs the subject callback."""
    step_id = session.execute(
        select(approval_step.c.id).where(
            approval_step.c.approval_request_id == approval_request_id,
            approval_step.c.step_no == 1,
        )
    ).scalar_one()
    _execute(
        session,
        insert(approval_decision).values(
            tenant_id=tenant_id,
            id=new_id(),
            approval_request_id=approval_request_id,
            approval_step_id=step_id,
            decision=ApprovalDecisionKind.AUTO_APPROVE.value,
            approver_id=None,
            approver_kind=PrincipalKind.SYSTEM.value,
            auto_rule_set_version_id=rule.rule_set_version_id,
            auto_rule_id=rule.rule_id,
            subject_content_sha256=subject_content_sha256,
            decided_at=now,
        ),
    )
    transitions.apply(
        session,
        "approval_step",
        step_id,
        to_status=ApprovalStepStatus.APPROVED.value,
        expected_status=ApprovalStepStatus.ACTIVE.value,
        set_values={"completed_at": now},
    )
    _skip_waiting(session, approval_request_id)
    transitions.apply(
        session,
        "approval_request",
        approval_request_id,
        to_status=ApprovalRequestStatus.APPROVED.value,
        expected_status=ApprovalRequestStatus.PENDING.value,
        set_values={"decided_at": now},
    )


def _skip_waiting(session: Session, approval_request_id: UUID) -> None:
    waiting = session.scalars(
        select(approval_step.c.id)
        .where(
            approval_step.c.approval_request_id == approval_request_id,
            approval_step.c.status == ApprovalStepStatus.WAITING.value,
        )
        .order_by(approval_step.c.step_no)
    ).all()
    for step_id in waiting:
        transitions.apply(
            session,
            "approval_step",
            step_id,
            to_status=ApprovalStepStatus.SKIPPED.value,
            expected_status=ApprovalStepStatus.WAITING.value,
            set_values={},
        )


def _covers(scope: Literal["*"] | frozenset[UUID], entities: SubjectEntities) -> bool:
    """``scope`` covers EVERY entity of the subject (DG-KRN-APR-06); a tenant-level subject names
    none, so any holder covers it."""
    return entities.covered_by(scope)


@dataclass(frozen=True, slots=True)
class Delegation:
    """A delegation to a membership that is in force (T-PLT-21; BR-PLT-07)."""

    id: UUID
    permissions: tuple[str, ...]
    delegator_membership_id: UUID
    delegator_user_id: UUID


def in_force_delegations(
    session: Session, membership_id: UUID, *, at: datetime
) -> list[Delegation]:
    """The delegations to ``membership_id`` in force at ``at``, oldest first.

    A delegation is in force when it is not revoked, ``valid_from <= at < valid_to`` and the
    delegator's membership is ACTIVE. Whether the delegator still holds a permission is the
    caller's check (``effective_grants``).
    """
    rows = session.execute(
        select(
            approval_delegation.c.id,
            approval_delegation.c.permissions,
            approval_delegation.c.delegator_membership_id,
            tenant_membership.c.user_id,
        )
        .select_from(
            approval_delegation.join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == approval_delegation.c.tenant_id,
                    tenant_membership.c.id == approval_delegation.c.delegator_membership_id,
                ),
            )
        )
        .where(
            approval_delegation.c.delegate_membership_id == membership_id,
            approval_delegation.c.revoked_at.is_(None),
            approval_delegation.c.valid_from <= at,
            approval_delegation.c.valid_to > at,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(approval_delegation.c.valid_from, approval_delegation.c.id)
    ).all()
    return [
        Delegation(
            id=UUID(str(row.id)),
            permissions=tuple(row.permissions),
            delegator_membership_id=UUID(str(row.delegator_membership_id)),
            delegator_user_id=UUID(str(row.user_id)),
        )
        for row in rows
    ]


Scope = Literal["*"] | frozenset[UUID]


def asked_by_entity_scope(principal: Principal) -> bool:
    """Whether the kernel's own-scope question is answered by the principal's ENTITY SCOPE in
    place of its permissions (04 §16.10 rev 1.321 "Who is not asked"; dev-guide DG-KRN-APR-06 rev
    1.297; item SUPPORT-GRANT-OPERATOR-SCOPE-1, register index 307): a principal that holds no
    permission of its own and that no route admitted. The one predicate of ``own_scope_covers``
    and of its SQL twin (``approval_queries._own_scope_covers``).

    - Kind SYSTEM — a job, provisioning, an import on behalf of its uploader.
    - Kind OPERATOR that a command built (``auth_method`` ``"system"``) and that holds no
      permission: the provider's operator at the command line. ``erev support-grant request``
      acts as it (``support_grants.request_as_operator``) — the preparer of the
      ``SUPPORT_GRANT`` request, a subject of every entity that any permission of a person's
      own reads, and it holds none. Measured on d3a1aa5f6: asked by permission, as rev 1.319
      asked every principal but SYSTEM, the request was refused 403 as a preparer "outside your
      roles".

    Everyone else is asked by permission. A person and an API client, whoever built their
    principal: a job that acts as its requester carries her grants
    (``sandboxes.sandbox_actor``: ``auth_method`` ``"system"`` too), and a role on an entity is
    not a read of it. The operator signed in under an approved grant (``auth.operators``): a
    route admitted it, and it holds the read-only permissions. And an operator a command built
    WITH permissions, should one ever be: what it holds is then the question."""
    if principal.kind is PrincipalKind.SYSTEM:
        return True
    return (
        principal.kind is PrincipalKind.OPERATOR
        and principal.auth_method == "system"
        and not principal.permission_scopes
    )


def own_scope_covers(
    principal: Principal, subject_type: ApprovalSubjectType | str, entities: SubjectEntities
) -> bool:
    """The principal reads a subject of ``subject_type`` bound to ``entities`` in full, in its
    OWN right: ONE permission that reads the subject is held for every entity of it (04 §16.10
    rev 1.319 "Who reads a subject in full"; ``readers.read_in_full``; item
    READ-SCOPE-BY-PERMISSION-1). Until that revision the question was the principal's entity
    scope — the union of the entities of every role — and a role on an entity is not a read of
    it; a guarded transaction, moreover, no longer runs under the union
    (``auth.dependencies.require``), so the question is asked of ``permission_scopes``, which no
    route narrows.

    A delegation conveys a permission, never the view (R-41 (1); REQ-PLT-015: the approver sees
    what they approve), so a delegate who could not read part of the subject is refused before
    anything is read — the content itself is hashed under the tenant's SYSTEM scope and does not
    depend on the decider (R-64 (1)). The same rule holds a preparer at submission (R-64 (6): a
    preparer asks others to approve only what she can read in full). A subject that spans every
    entity takes a permission for all entities; a tenant-level subject asks nothing.

    A SYSTEM principal — a job, provisioning, an import on behalf of its uploader — holds no
    permission of its own and no route admits it: it covers what its entity scope covers, as
    before. So does the provider's operator at the command line (rev 1.321;
    ``asked_by_entity_scope`` names the two)."""
    if asked_by_entity_scope(principal):
        scope: Scope = "*" if principal.entity_scope == "*" else frozenset(principal.entity_scope)
        return entities.covered_by(scope)
    return readers.read_in_full(principal.permission_scopes, subject_type, entities)


def decision_authorities(
    session: Session, principal: Principal, *, at: datetime
) -> list[dict[str, Scope]]:
    """The authorities the principal may decide with, each as approval permission → entity scope:
    its own grants first, then one per delegation in force with the named permissions the delegator
    still holds. A decision needs ONE of them to cover every entity of the subject
    (``find_authority``; dev-guide DG-KRN-APR-06), so they are kept apart."""
    authorities: list[dict[str, Scope]] = [
        {
            code: scope
            for code, scope in principal.permission_scopes.items()
            if permission_spec(code).is_approval
        }
    ]
    if principal.membership_id is None:
        return authorities
    for delegation in in_force_delegations(session, principal.membership_id, at=at):
        granted = effective_grants(session, delegation.delegator_membership_id, at=at)
        authorities.append(
            {
                code: granted.permission_scopes[code]
                for code in delegation.permissions
                if code in granted.permission_scopes
            }
        )
    return authorities


def union_scopes(authorities: Sequence[Mapping[str, Scope]]) -> dict[str, Scope]:
    """Approval permission → the union of its scopes over ``authorities``: what the principal may
    see, not what one authority may decide."""
    scopes: dict[str, Scope] = {}
    for authority in authorities:
        for code, scope in authority.items():
            held = scopes.get(code)
            scopes[code] = (
                scope
                if held is None
                else held | scope
                if isinstance(held, frozenset) and isinstance(scope, frozenset)
                else "*"
            )
    return scopes


def find_authority(
    session: Session,
    principal: Principal,
    permission: str,
    entities: SubjectEntities,
    *,
    at: datetime,
    subject_type: ApprovalSubjectType | str,
    avoid: Collection[UUID] = (),
) -> _Authority | None:
    """The authority the principal decides a step of ``permission`` with, or None: its own grants
    for the subject's entities, else an in-force delegation of the permission (DG-KRN-APR-06: the
    set form).

    ONE authority covers every entity of the subject — the principal's own scope, or a delegation
    that names the permission and whose delegator still holds it for all of them
    (``effective_grants``); scopes of several authorities are never added up. A delegation is
    taken only by a principal who reads the subject in full in its OWN right
    (``own_scope_covers``; R-41 (1); 04 §16.10 rev 1.319): a delegate who does not read every
    entity of a subject of ``subject_type`` does not decide for it. The principal's own grants
    ask nothing further — who holds the step's permission for every entity is the approver the
    request is put before (REQ-PLT-015). Among several delegations the first whose
    delegator is not in ``avoid`` — the people who may not decide this request — is taken, so a
    delegate of the preparer who also acts for another approver decides on that approver's behalf
    (R-41 (8)); when every delegator is barred, the first one stands and ``decide`` names the
    refusal.
    """
    own = principal.permission_scopes.get(permission)
    if own is not None and _covers(own, entities):
        return _Authority()
    if not own_scope_covers(principal, subject_type, entities):
        return None
    barred: _Authority | None = None
    if principal.membership_id is not None:
        for delegation in in_force_delegations(session, principal.membership_id, at=at):
            if permission not in delegation.permissions:
                continue
            grants = effective_grants(session, delegation.delegator_membership_id, at=at)
            scope = grants.permission_scopes.get(permission)
            if scope is None or not _covers(scope, entities):
                continue
            authority = _Authority(
                delegation_id=delegation.id, on_behalf_of_id=delegation.delegator_user_id
            )
            if delegation.delegator_user_id not in avoid:
                return authority
            barred = barred or authority
    return barred


def in_entity_scope(principal: Principal, entities: SubjectEntities) -> bool:
    """The principal's entity scope (the union ``app.entity_scope`` is set from) reaches the
    subject: row-level security applies this to a request of ONE entity (RLS-TE on ``entity_id``);
    the engine applies the same rule to a request of several, whose row no policy hides
    (REQ-PLT-012: out-of-scope ids answer 404 like unknown ids)."""
    scope: Scope = "*" if principal.entity_scope == "*" else frozenset(principal.entity_scope)
    return scope == "*" or entities.all_entities or entities.touched_by(scope)


def visible_to(
    session: Session, principal: Principal, request: Mapping[str, Any], *, at: datetime
) -> bool:
    """Whether ``GET /approvals/{id}`` answers the request for the principal — the rule of
    ``approval_queries.visible`` for one request (04 §16.10 rev 1.104): within the principal's
    entity scope, it prepared the request, decided it (in person or as the delegator), or holds
    the permission of one of its steps for at least one of its entities — through its own grants,
    or through a delegation when it reads the subject in full in its OWN right
    (``own_scope_covers``; R-41 (1): a delegation is effective and listed for a request only
    where the delegate may read all of it). ``decide`` and ``withdraw`` answer 404 exactly where
    this is false, so an id the principal could not read is never confirmed by another status
    (REQ-PLT-012; R-41 (8))."""
    entities = request_entities(request)
    if not in_entity_scope(principal, entities):
        return False
    if principal.id is not None:
        if request["preparer_id"] == principal.id:
            return True
        decided = session.execute(
            select(approval_decision.c.id)
            .where(
                approval_decision.c.approval_request_id == request["id"],
                or_(
                    approval_decision.c.approver_id == principal.id,
                    approval_decision.c.on_behalf_of_id == principal.id,
                ),
            )
            .limit(1)
        ).first()
        if decided is not None:
            return True
    own, *delegated = decision_authorities(session, principal, at=at)
    scopes = dict(own)
    if delegated and own_scope_covers(principal, request["subject_type"], entities):
        scopes = union_scopes([own, *delegated])
    if not scopes:
        return False
    permissions = session.scalars(
        select(approval_step.c.required_permission).where(
            approval_step.c.approval_request_id == request["id"]
        )
    ).all()
    return any(
        str(code) in scopes and entities.touched_by(scopes[str(code)]) for code in set(permissions)
    )


def _require_visible(uow: UnitOfWork, request: Mapping[str, Any]) -> SubjectEntities:
    """The request's entities, or 404 ``not-found`` when the principal could not read the request
    (``visible_to``) — exactly what an unknown id answers."""
    if not visible_to(uow.session, uow.principal, request, at=uow.now):
        raise Problem("not-found")
    return request_entities(request)


def _acting(user_id: UUID, authority: _Authority) -> list[UUID]:
    """The approver and, for a delegated decision, the delegator."""
    if authority.on_behalf_of_id is None:
        return [user_id]
    return [user_id, authority.on_behalf_of_id]


def _earlier_decision(session: Session, request_id: UUID, acting: Sequence[UUID]) -> Any:
    return session.execute(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == request_id,
            or_(
                approval_decision.c.approver_id.in_(acting),
                approval_decision.c.on_behalf_of_id.in_(acting),
            ),
        )
    ).first()


def approvers_of(session: Session, approval_request_id: UUID) -> frozenset[UUID]:
    """The people whose APPROVE decisions the request holds, delegators included: an approval hook
    that excludes someone (the run's runner, BR-JE-01) compares against every acting person, never
    the deciding principal alone (REQ-PLT-011)."""
    rows = session.execute(
        select(approval_decision.c.approver_id, approval_decision.c.on_behalf_of_id).where(
            approval_decision.c.approval_request_id == approval_request_id,
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).all()
    return frozenset(UUID(str(value)) for row in rows for value in row if value is not None)


def _excluded(session: Session, request: Mapping[str, Any], acting: Sequence[UUID]) -> bool:
    """A subject may exclude deciders besides the preparer — the owner of the exception item a
    waiver clears, the runner of a journal run (``SubjectSpec.excluded_deciders``; PRD §2.5,
    BR-JE-01; BUILD_SPEC DIN-11) — and ``acting`` holds the approver AND the delegator, so an
    excluded person is refused through a delegate as in person."""
    spec = spec_for(ApprovalSubjectType(request["subject_type"]))
    return bool(set(acting) & _excluded_deciders(session, spec, request["subject_id"]))


def _excluded_deciders(session: Session, spec: SubjectSpec, subject_id: UUID) -> frozenset[UUID]:
    """The deciders ``spec`` excludes for the subject, read under the tenant's SYSTEM scope
    (supervisor ruling R-64 (1)): who is excluded is a fact of the subject, never of the entity
    scope of whoever asks — a viewer who cannot read the author's row is still not the author's
    way around the rule."""
    if spec.excluded_deciders is None:
        return frozenset()
    with system_entity_scope(session):
        return frozenset(spec.excluded_deciders(session, subject_id))


def _barred(session: Session, request: Mapping[str, Any]) -> frozenset[UUID]:
    """The people who may not decide ``request`` whatever they hold: its preparer, the deciders
    its subject excludes and everyone who decided it, in person or as the delegator. ``decide``
    refuses each by its own name; ``find_authority`` prefers an authority none of them stands
    behind."""
    people: set[UUID] = set()
    if request["preparer_id"] is not None:
        people.add(UUID(str(request["preparer_id"])))
    spec = spec_for(ApprovalSubjectType(request["subject_type"]))
    people |= _excluded_deciders(session, spec, request["subject_id"])
    rows = session.execute(
        select(approval_decision.c.approver_id, approval_decision.c.on_behalf_of_id).where(
            approval_decision.c.approval_request_id == request["id"]
        )
    ).all()
    people |= {UUID(str(value)) for row in rows for value in row if value is not None}
    return frozenset(people)


def can_decide(
    session: Session, principal: Principal, request: Mapping[str, Any], *, at: datetime
) -> bool:
    """04 §16.10 ``can_decide``: a person holds the active step's permission — and the step's
    role, when it names one — for EVERY entity of the request, directly or through a delegation
    of a subject they read in full themselves (``find_authority``), and neither they nor the
    delegator prepared the
    request, is excluded by its subject or decided an earlier step (DG-KRN-APR-02, DG-KRN-APR-06),
    the subject's own check of its deciders admits them (``SubjectSpec.deciders``; R-92) and a
    later step of the request does not depend on them (``_reserved_for_later_step``; R-66 (7)).
    MFA is checked when deciding. False, never an error, for a request of a subject type that has
    no specification yet: nobody decides it (R-64 (7) (c))."""
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        return False
    if request["status"] != ApprovalRequestStatus.PENDING.value:
        return False
    if ApprovalSubjectType(request["subject_type"]) not in SUBJECTS:
        return False
    step = session.execute(
        select(approval_step.c.required_permission, approval_step.c.required_role_id).where(
            approval_step.c.approval_request_id == request["id"],
            approval_step.c.step_no == request["current_step_no"],
            approval_step.c.status == ApprovalStepStatus.ACTIVE.value,
        )
    ).one_or_none()
    if step is None:
        return False
    permission = step.required_permission
    entities = request_entities(request)
    authority = find_authority(
        session,
        principal,
        str(permission),
        entities,
        at=at,
        subject_type=request["subject_type"],
        avoid=_barred(session, request),
    )
    if authority is None or not _holds_step_role(
        principal, _step_role(session, step.required_role_id), entities
    ):
        return False
    acting = _acting(principal.id, authority)
    if request["preparer_id"] in acting or _excluded(session, request, acting):
        return False
    if _earlier_decision(session, request["id"], acting) is not None:
        return False
    try:
        if _refused_deciders(session, request, [principal.id], at=at):
            return False
    except SubjectNotVisible:
        return False  # the subject row is gone: nobody decides the request (``decide``: 404)
    return not _reserved_for_later_step(session, request, acting, at=at)


def _next_ordinal(session: Session, request: Mapping[str, Any]) -> int:
    """The ordinal of the next approval of ``request``, counted over the whole request: one more
    than the approvals people have given it (an auto-approval is none). A step takes as many as
    its ``min_approvers``, so the first approval of a later step follows the last of the earlier
    ones (``_later_steps``)."""
    given = session.execute(
        select(func.count())
        .select_from(approval_decision)
        .where(
            approval_decision.c.approval_request_id == request["id"],
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).scalar_one()
    return int(given) + 1


def _refused_deciders(
    session: Session,
    request: Mapping[str, Any],
    user_ids: Collection[UUID],
    *,
    ordinal: int | None = None,
    at: datetime,
) -> Mapping[UUID, DeciderRefusal]:
    """The people of ``user_ids`` the SUBJECT refuses approval number ``ordinal`` of ``request``
    — the next one when none is named — (``SubjectSpec.deciders``; supervisor ruling R-92),
    asked under the tenant's SYSTEM scope like every fact of a subject (R-64 (1)): what a subject
    asks of its deciders does not depend on who asks. Empty for a subject without such a check.
    ``SubjectNotVisible`` when the subject row is gone."""
    spec = SUBJECTS.get(ApprovalSubjectType(request["subject_type"]))
    if spec is None or spec.deciders is None or not user_ids:
        return {}
    if ordinal is None:
        ordinal = _next_ordinal(session, request)
    with system_entity_scope(session):
        return spec.deciders(
            session, request["subject_id"], request_entities(request), ordinal, user_ids, at
        )


def _record_refusal(
    uow: UnitOfWork,
    request: Mapping[str, Any],
    decision_kind: ApprovalDecisionKind,
    refusal: DeciderRefusal,
) -> None:
    """The ``DENIED`` audit event of a decision the subject refused (supervisor ruling R-98;
    DG-KRN-AUTH-05), appended in a transaction of its own: it stays when the refusal rolls the
    command back, so the attempt is on record with the permission the person lacked."""
    audit_writer.record_denied(
        uow.ctx,
        action=DECISION_ACTIONS[decision_kind.value],
        object_type=OBJECT_TYPE,
        object_id=UUID(str(request["id"])),
        permission=refusal.permission,
        detail={
            "subject_type": str(request["subject_type"]),
            "subject_id": str(request["subject_id"]),
            **refusal.detail,
        },
        keyring=uow.keyring,
    )


def record_denial(
    uow: UnitOfWork,
    *,
    action: str,
    reason: str,
    permission: str = "",
    approval_request_id: UUID | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    **facts: Any,
) -> None:
    """The kernel's ONE writer of a ``DENIED`` audit event for the checks the kernel itself makes
    (DG-KRN-AUTH-05; 04 §16.10 rev 1.295; the supervisor's ruling of 2026-10-02, in the shape
    lane SECFIX-APR set for its register index 220). ``_record_refusal`` stays beside it: that
    one writes the SUBJECT's own refusal of a decider (R-98).

    One event for one refused call, written BEFORE the 403 is raised and in a transaction of
    its own, so it stays when the refusal rolls the command back; a 404, a 409 and a 422
    record nothing. ``action`` is the audit action of the refused command. ``reason`` is a
    closed code, a module constant ``DENIED_…`` — never a sentence. ``permission`` is the
    permission whose lack refused, "" where no single permission is refused.
    ``approval_request_id`` names the request where one exists. It is the id AS SENT where a
    decision command is refused before its request is read — nothing of a request is then
    read or stated (item APR-DENIED-AUDIT-1) — and None for a refused submission or preview,
    which opens none, and for a bulk approval refused as a whole. ``subject_type`` and
    ``subject_id`` are given when the caller holds the subject. ``facts`` are closed and
    content-free — a step ordinal, a role code, a delegator's id, a count, ids as sent —
    never a comment, a summary or any other content of a request: the audit log is read
    whatever a request withholds (04 §16.10)."""
    detail: dict[str, Any] = {}
    if subject_type is not None:
        detail["subject_type"] = str(subject_type)
    if subject_id is not None:
        detail["subject_id"] = str(subject_id)
    detail["reason"] = reason
    detail.update(facts)
    audit_writer.record_denied(
        uow.ctx,
        action=action,
        object_type=OBJECT_TYPE,
        object_id=approval_request_id,
        permission=permission,
        detail=detail,
        keyring=uow.keyring,
    )


def _of(request: Mapping[str, Any]) -> dict[str, Any]:
    """A request that was read, as ``record_denial`` names it: its id and its subject."""
    return {
        "approval_request_id": UUID(str(request["id"])),
        "subject_type": str(request["subject_type"]),
        "subject_id": UUID(str(request["subject_id"])),
    }


def _through(authority: Any) -> dict[str, str]:
    """The delegator a refused decision was attempted for, as its ``DENIED`` event names them."""
    if authority.on_behalf_of_id is None:
        return {}
    return {"on_behalf_of_id": str(authority.on_behalf_of_id)}


def require_person(
    uow: UnitOfWork, *, action: str, approval_request_id: UUID | None = None, **facts: Any
) -> None:
    """DG-KRN-APR-04: API clients, service accounts, SYSTEM principals and AI never decide, so they
    get 403 ``forbidden`` before any write or any other check (REQ-PLT-011). The attempt is
    recorded (``record_denial``) with the id as sent: nothing of a request is read."""
    principal = uow.principal
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        record_denial(
            uow,
            action=action,
            reason=DENIED_NOT_A_PERSON,
            approval_request_id=approval_request_id,
            **facts,
        )
        raise Problem("forbidden", NON_HUMAN_DETAIL)


def decide(
    uow: UnitOfWork,
    *,
    approval_request_id: UUID,
    decision: Literal["APPROVE", "REJECT"],
    subject_content_sha256: str,
    impact_preview_sha256: str | None,
    comment: str | None,
    reason_code: str | None,
) -> Mapping[str, Any]:
    """Record one decision on the active step and advance the request (DG-KRN-APR-02).

    Checks, before any write and in this order: a human principal (403 ``forbidden``,
    DG-KRN-APR-04); a request the principal can read (404 ``not-found``, as for an unknown id and
    exactly where ``GET /approvals/{id}`` answers 404 — ``visible_to``); a PENDING request (409
    ``invalid-transition``) whose subject type has a specification (the same 409, by name:
    ``_require_specified``); the step permission is held for every entity of the request,
    directly or through ONE delegation of a subject the principal reads in full in its OWN right
    (403 ``forbidden``; ``find_authority``); the step's role, when it names one, held for the
    same entities (403
    ``forbidden``); an MFA-verified session (403 ``mfa-required``); neither the approver nor the
    delegator is the preparer or a decider the subject excludes (403 ``self-approval``); no earlier
    decision on the request by either of them, directly or on behalf of someone (409
    ``approver-already-decided``); no later step of the request that would be left without its
    approvers by this decision (409 ``invalid-transition``, R-66 (7)); the subject's own check of
    the decider, where it has one (``SubjectSpec.deciders``: 403 ``forbidden`` by name, with a
    ``DENIED`` audit event written in a transaction of its own — R-92, R-98); a comment on a
    rejection (422). Then the subject is read under the tenant's SYSTEM entity scope, never under
    the decider's (R-64 (1): what a control hashes does not depend on who decides): it still
    states the entities the request froze, and its content matches the stored hash and the
    client's — otherwise the request is voided with ``STALE_SUBJECT``, the void is committed, and
    409 ``stale-approval`` is raised (REQ-PLT-014). A subject row that is gone is 404, never an
    unhandled error, and never a void. The hooks of the decision run under the same scope. The
    entity checks above are what refuse a decider who does not cover the request: nothing is
    read for one (R-41 (1)).
    """
    decision_kind = ApprovalDecisionKind(decision)
    if decision_kind is ApprovalDecisionKind.AUTO_APPROVE:
        raise ValueError("a person decides APPROVE or REJECT")
    action = DECISION_ACTIONS[decision_kind.value]
    principal = uow.principal
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        # ``require_person``, stated here so that the person's id is known below.
        record_denial(
            uow,
            action=action,
            reason=DENIED_NOT_A_PERSON,
            approval_request_id=approval_request_id,
        )
        raise Problem("forbidden", NON_HUMAN_DETAIL)
    session = uow.session
    request = _lock_request(session, approval_request_id)
    entities = _require_visible(uow, request)
    _require_pending(request)
    _require_specified(request)
    step = (
        session.execute(
            select(approval_step).where(
                approval_step.c.approval_request_id == approval_request_id,
                approval_step.c.step_no == request["current_step_no"],
            )
        )
        .mappings()
        .one()
    )
    permission = str(step["required_permission"])

    def denied(reason: str, **facts: Any) -> None:
        """Record this attempt as refused by one of the checks below (``record_denial``)."""
        record_denial(
            uow,
            action=action,
            reason=reason,
            permission=permission,
            **_of(request),
            step_no=int(step["step_no"]),
            **facts,
        )

    authority = find_authority(
        session,
        principal,
        permission,
        entities,
        at=uow.now,
        subject_type=request["subject_type"],
        avoid=_barred(session, request),
    )
    if authority is None:
        held = permission in union_scopes(decision_authorities(session, principal, at=uow.now))
        denied(DENIED_ENTITIES_NOT_COVERED if held else DENIED_NO_AUTHORITY)
        raise Problem("forbidden", EVERY_ENTITY_DETAIL if held else None)
    required_role = _step_role(session, step["required_role_id"])
    if required_role is not None and not _holds_role(
        principal, str(required_role["code"]), entities
    ):
        denied(DENIED_STEP_ROLE, role=str(required_role["code"]), **_through(authority))
        raise Problem("forbidden", ROLE_REQUIRED_DETAIL.format(role=required_role["name"]))
    if principal.mfa_verified_at is None:
        denied(DENIED_MFA, **_through(authority))
        raise Problem("mfa-required", VERIFICATION_REQUIRED)
    acting = [principal.id]
    if authority.on_behalf_of_id is not None:
        acting.append(authority.on_behalf_of_id)
    if request["preparer_id"] in acting:
        denied(DENIED_SELF_APPROVAL, **_through(authority))
        raise Problem("self-approval", SELF_APPROVAL_DETAIL)
    if _excluded(session, request, acting):
        denied(DENIED_EXCLUDED_DECIDER, **_through(authority))
        excluded_spec = spec_for(ApprovalSubjectType(request["subject_type"]))
        raise Problem("self-approval", excluded_spec.excluded_detail or EXCLUDED_DETAIL)
    earlier = session.execute(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == approval_request_id,
            or_(
                approval_decision.c.approver_id.in_(acting),
                approval_decision.c.on_behalf_of_id.in_(acting),
            ),
        )
    ).first()
    if earlier is not None:
        raise Problem("approver-already-decided", ALREADY_DECIDED_DETAIL)
    if _reserved_for_later_step(session, request, acting, at=uow.now):
        raise Problem(
            "invalid-transition",
            SOLE_LATER_DECIDER_DETAIL,
            errors=[
                ProblemError(
                    field="current_step_no", rule_id=RULE_STEPS, message=SOLE_LATER_DECIDER_DETAIL
                )
            ],
        )
    try:
        refusal = _refused_deciders(session, request, [principal.id], at=uow.now).get(principal.id)
    except SubjectNotVisible as error:
        # The subject row is gone: 404 like an unknown id, as for the content read below.
        raise Problem("not-found") from error
    if refusal is not None:
        # R-92: checked at EVERY decision, approve and reject alike, so a person who does not hold
        # what the subject asks of this approver takes no step. R-98: the refusal is the recorded
        # outcome of the attempt.
        _record_refusal(uow, request, decision_kind, refusal)
        raise refusal.problem
    if decision_kind is ApprovalDecisionKind.REJECT and not (comment or "").strip():
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="comment", rule_id=RULE_REJECT_COMMENT, message=REJECT_COMMENT_REQUIRED
                )
            ],
        )
    spec = spec_for(ApprovalSubjectType(request["subject_type"]))
    stored_sha256 = str(request["subject_content_sha256"])
    try:
        stated = current_entities(uow, spec, request)
        current_sha256 = current_content_sha256(uow, spec, request)
    except SubjectNotVisible as error:
        # A content or entity function found no subject row under the tenant's SYSTEM scope: the
        # row is gone. 404 like an unknown id (REQ-PLT-012; R-25), not an escaped error and not
        # a void.
        raise Problem("not-found") from error
    # R-41 (2): the entities the request froze are the entities the subject still states. A
    # request that spans every entity already takes the permission for all of them — its set
    # cannot grow — so only a named set (or none) is compared.
    moved = not entities.all_entities and stated != entities
    if moved or stored_sha256 != current_sha256 or stored_sha256 != subject_content_sha256:
        _void(
            uow,
            request,
            spec,
            status=ApprovalRequestStatus.VOIDED,
            reason=VOID_STALE_SUBJECT,
            action=VOID_ACTION,
            comment=None,
            after={"subject_content_sha256": current_sha256}
            | ({"entities": entities_audit(stated)} if moved else {}),
        )
        # The void survives the 409: it is committed before the problem is raised (REQ-PLT-014).
        uow.commit()
        raise Problem("stale-approval", STALE_DETAIL)

    stored_preview = request["impact_preview_sha256"]
    if (
        decision_kind is ApprovalDecisionKind.APPROVE
        and stored_preview is not None
        and impact_preview_sha256 != stored_preview
    ):
        # 04 §16.10: an approval of a request with a preview names the preview it reviewed.
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="impact_preview_sha256",
                    rule_id=RULE_PREVIEW,
                    message="Review the impact preview of this request before approving it.",
                )
            ],
        )

    try:
        # DG-KRN-UOW-03 rev 1.40 (D-98 candidate 101d, Codex CONTEXT-R1): the decision's writes and
        # the subject hook run inside a savepoint, so a StaleBasis from the hook undoes them while
        # the session keeps its tenant context and the request lock taken above.
        with uow.savepoint():
            _apply_decision(
                uow,
                request=request,
                step=step,
                spec=spec,
                decision_kind=decision_kind,
                authority=authority,
                stored_sha256=stored_sha256,
                impact_preview_sha256=impact_preview_sha256,
                reason_code=reason_code,
                comment=comment,
            )
    except StaleBasis:
        _refuse_stale_basis(uow, approval_request_id, spec)
    except Problem as problem:
        # PRD ERR-72 (rev 1.86; supervisor ruling of 2026-10-01): a hook whose computation met a
        # period lock decided since this decision began. Nothing of the decision is saved and the
        # request stays pending; the answer names the act to repeat — "Decide again".
        if is_period_state_moved(problem):
            raise period_state_moved(deciding=True) from problem
        raise
    return _request_row(session, approval_request_id)


def _apply_decision(
    uow: UnitOfWork,
    *,
    request: Mapping[str, Any],
    step: Mapping[Any, Any],
    spec: SubjectSpec,
    decision_kind: ApprovalDecisionKind,
    authority: Any,
    stored_sha256: str,
    impact_preview_sha256: str | None,
    reason_code: str | None,
    comment: str | None,
) -> None:
    """The writes of one decision: the decision row, the step / request advance, the audit event,
    then the subject hook and the notifications (``decide`` runs it inside a savepoint)."""
    session = uow.session
    principal = uow.principal
    approval_request_id = UUID(str(request["id"]))
    _execute(
        session,
        insert(approval_decision).values(
            tenant_id=principal.tenant_id,
            id=new_id(),
            approval_request_id=approval_request_id,
            approval_step_id=step["id"],
            decision=decision_kind.value,
            approver_id=principal.id,
            approver_kind=PrincipalKind.USER.value,
            delegation_id=authority.delegation_id,
            on_behalf_of_id=authority.on_behalf_of_id,
            subject_content_sha256=stored_sha256,
            impact_preview_sha256=impact_preview_sha256,
            mfa_verified_at=principal.mfa_verified_at,
            reason_code=reason_code,
            comment=comment,
            decided_at=uow.now,
        ),
    )
    status = _advance(uow, request, step, decision_kind)
    uow.audit(
        action=DECISION_ACTIONS[decision_kind.value],
        object_type=OBJECT_TYPE,
        object_id=approval_request_id,
        before={"status": request["status"], "current_step_no": request["current_step_no"]},
        after={
            "status": status.value,
            "current_step_no": _request_row(session, approval_request_id)["current_step_no"],
            "decided_step_no": step["step_no"],
            "impact_preview_sha256": impact_preview_sha256,
            "delegation_id": _text(authority.delegation_id),
            "on_behalf_of_id": _text(authority.on_behalf_of_id),
        },
        reason_code=reason_code,
        comment=comment,
        approval_request_id=approval_request_id,
    )
    if status is ApprovalRequestStatus.APPROVED:
        # R-64 (1): the hook recomputes, reverses and posts under the tenant's SYSTEM scope, so
        # what an approval puts in force does not depend on the decider's entity scope.
        with system_entity_scope(session):
            spec.on_approved(uow, request["subject_id"], approval_request_id)  # StaleBasis
        summary = _preparer_summary(uow, request)
        _notify_preparer(
            uow,
            spec,
            request,
            NotificationKind.ITEM_APPROVED,
            title=f"Approved: {summary}",
            body=f"{principal.display_name} approved {summary}.",
        )
    elif status is ApprovalRequestStatus.REJECTED:
        with system_entity_scope(session):
            spec.on_rejected(uow, request["subject_id"], approval_request_id)
        # The comment of a rejection is written to the preparer (04 §16.10 rev 1.240; item
        # APR-REJECTION-REASON-PREPARER-1): a preparer who is not shown the request's content is
        # told the summary it is shown (``_preparer_summary``) and, all the same, why the request
        # was rejected — she cannot correct what she is not told.
        summary = _preparer_summary(uow, request)
        _notify_preparer(
            uow,
            spec,
            request,
            NotificationKind.ITEM_REJECTED,
            title=f"Rejected: {summary}",
            body=f"{principal.display_name} rejected {summary}: {comment}",
        )
    elif (
        _request_row(session, approval_request_id)["current_step_no"] != request["current_step_no"]
    ):
        _notify_assigned(uow, approval_request_id)


def _text(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def current_content_sha256(uow: UnitOfWork, spec: SubjectSpec, request: Mapping[Any, Any]) -> str:
    """The subject's content hash now: ``spec.content`` of the subject row, or for a subject
    without a row the stored proposal with the current base state (BS1-D-24)."""
    with system_entity_scope(uow.session):
        if spec.proposal_content is None:
            return sha256_hex(spec.content(uow.session, request["subject_id"]))
        proposal = preview.request_proposal(uow, request["id"])
        return sha256_hex(spec.proposal_content(uow.session, proposal))


HOOK_NOT_APPROVED: Final = (
    "Approval request {request_id} is {status}, not APPROVED: an approval hook acts only on an "
    "approved request."
)


class StaleBasis(Problem):
    """The approved basis no longer matches under the hook's locks (D-98 candidate 101d)."""

    def __init__(self) -> None:
        super().__init__("stale-approval", STALE_DETAIL)


def assert_fresh_basis(uow: UnitOfWork, approval_request_id: UUID) -> None:
    """Called by an approval hook UNDER the locks that protect its subject (DG-KRN-DB-08 order),
    immediately before it applies the decision (DG-KRN-APR-05 rev 1.40; D-98 candidate 101d): the
    subject content must still hash to the basis the approver reviewed — the request's stored
    ``subject_content_sha256``, which ``decide`` compared BEFORE taking any lock. Under READ
    COMMITTED an append committed between that comparison and the hook's locks would otherwise be
    applied against. A difference raises ``StaleBasis``; ``decide`` discards the decision and the
    hook's partial work, voids the request ``STALE_SUBJECT`` and answers 409 ``stale-approval`` —
    no retry."""
    request = _request_row(uow.session, approval_request_id)
    spec = spec_for(ApprovalSubjectType(request["subject_type"]))
    if current_content_sha256(uow, spec, request) != str(request["subject_content_sha256"]):
        raise StaleBasis()


@dataclass(frozen=True, slots=True)
class ConsumedBasis:
    """The explicit composition relationship of a deferred-job subject (D-98 candidate 119; Codex
    0216): approval request ``approval_request_id`` for ``(subject_type, subject_id)`` was
    consumed FRESH — its stored basis re-hashed under the authoritative locks, before any effect —
    in the transaction ``session``, and covers the contracts whose external ids are ``keys`` (the
    business keys its content pins). The job hands it to the hooks it drives (BR-DAT-06: the
    import approval stands as the activation approval); ``activation.activate`` verifies it —
    same transaction, the contract's key among ``keys``, the same request — instead of re-hashing
    a subject it does not apply. Internal: built only by ``consume_fresh_basis``."""

    approval_request_id: UUID
    subject_type: ApprovalSubjectType
    subject_id: UUID
    keys: frozenset[str]
    # The APPROVED bases (Codex 0226): each covered key's stream head at the approval, None for an
    # expected absence — carried into the protected consumption so a later plan compares against
    # the approved head, not a re-read one; the named contracts stay locked from the consumption to
    # the commit, so no external edit can land between the initial check and a later plan.
    bases: Mapping[str, int | None]
    session: Session

    def covers(self, uow: UnitOfWork, *, key: str, approval_request_id: UUID | None) -> bool:
        """True when ``uow`` is the consuming transaction, ``key`` is one of the covered business
        keys and ``approval_request_id`` (when given) is the consumed request."""
        return (
            uow.session is self.session
            and key in self.keys
            and (approval_request_id is None or approval_request_id == self.approval_request_id)
        )


def _own_request(
    uow: UnitOfWork,
    approval_request_id: UUID,
    *,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
) -> Mapping[str, Any]:
    """The request row, which must name ``(subject_type, subject_id)`` — a hook re-validates the
    basis of ITS OWN request only; a request for another subject is a provenance id that needs its
    consumed composition, never a bare id (``LookupError``, not a skip)."""
    request = _request_row(uow.session, approval_request_id)
    if (
        ApprovalSubjectType(request["subject_type"]) is not ApprovalSubjectType(subject_type)
        or UUID(str(request["subject_id"])) != subject_id
    ):
        raise LookupError(
            f"approval request {approval_request_id} is for {request['subject_type']} "
            f"{request['subject_id']}, not {ApprovalSubjectType(subject_type).value} {subject_id}: "
            "a hook re-validates its own request's basis; a provenance id needs its consumed "
            "composition (DG-KRN-APR-05 rev 1.51)"
        )
    return request


def assert_own_fresh_basis(
    uow: UnitOfWork,
    approval_request_id: UUID,
    *,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
) -> None:
    """``assert_fresh_basis`` for a hook that may be handed another subject's request: the request
    must be this hook's own (``LookupError`` otherwise) and its basis must still hold under the
    hook's locks (``StaleBasis`` otherwise). DG-KRN-APR-05 rev 1.51; D-98 candidate 119."""
    request = _own_request(
        uow, approval_request_id, subject_type=subject_type, subject_id=subject_id
    )
    # D-98 candidate 143 AMENDMENT 1 (Codex 0147 §2): subject and freshness are not authorization
    # — the hook acts only on a request the engine has decided APPROVED (``_finish`` writes the
    # status before ``on_approved`` runs); a PENDING, REJECTED or VOIDED request handed to a hook
    # is refused by name, never acted on.
    status = str(request["status"])
    if status != ApprovalRequestStatus.APPROVED.value:
        raise Problem(
            "invalid-transition",
            HOOK_NOT_APPROVED.format(request_id=approval_request_id, status=status),
        )
    spec = spec_for(ApprovalSubjectType(subject_type))
    if current_content_sha256(uow, spec, request) != str(request["subject_content_sha256"]):
        raise StaleBasis()


def consume_fresh_basis(
    uow: UnitOfWork,
    approval_request_id: UUID,
    *,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    keys: Iterable[str],
    bases: Mapping[str, int | None] | None = None,
) -> ConsumedBasis:
    """The one basis validation of a deferred-job subject (IMPORT_COMMIT), at the point the job
    consumes its approved request: called under the authoritative locks (the named contracts'
    groups, then the contracts — DG-KRN-DB-08) and BEFORE any effect, so a stale basis is refused
    atomically (``StaleBasis``; nothing was written). The request must name the subject
    (``LookupError`` otherwise). Returns the composition relationship the job carries into the
    hooks it drives (DG-KRN-APR-05 rev 1.51; D-98 candidate 119; Codex 0216)."""
    request = _own_request(
        uow, approval_request_id, subject_type=subject_type, subject_id=subject_id
    )
    spec = spec_for(ApprovalSubjectType(subject_type))
    if current_content_sha256(uow, spec, request) != str(request["subject_content_sha256"]):
        raise StaleBasis()
    return ConsumedBasis(
        approval_request_id=approval_request_id,
        subject_type=ApprovalSubjectType(subject_type),
        subject_id=subject_id,
        keys=frozenset(str(key) for key in keys),
        bases=MappingProxyType(dict(bases or {})),
        session=uow.session,
    )


def _refuse_stale_basis(uow: UnitOfWork, approval_request_id: UUID, spec: SubjectSpec) -> NoReturn:
    """The hook found the basis stale under its locks: roll the decision and the hook's partial
    work back, then void the request as the pre-lock check would have (REQ-PLT-014: the void
    survives the 409). Codex CONTEXT-R1: ``uow.discard()`` here rolled the transaction back, the
    app engine dropped ``erev.context`` and the very next statement was refused
    ``TenantContextMissing`` — the void and the 409 were never reached; ``decide``'s savepoint now
    undoes the decision and the hook's partial work without a rollback, so the session keeps its
    tenant context and the request lock."""
    request = _lock_request(uow.session, approval_request_id)
    _void(
        uow,
        request,
        spec,
        status=ApprovalRequestStatus.VOIDED,
        reason=VOID_STALE_SUBJECT,
        action=VOID_ACTION,
        comment=None,
        after={"subject_content_sha256": current_content_sha256(uow, spec, request)},
    )
    uow.commit()
    raise Problem("stale-approval", STALE_DETAIL)


def withdraw(
    uow: UnitOfWork,
    *,
    approval_request_id: UUID,
    comment: str | None,
    through_subject: bool = False,
) -> Mapping[str, Any]:
    """The preparer closes a PENDING request as WITHDRAWN (PRD SM-01).

    Another principal who can read the request receives 403 ``forbidden``, one who cannot 404
    ``not-found`` (``visible_to``): the answer of ``POST /approvals/{id}/withdraw``, which names
    the request, so that no command confirms an id the read denies (ruling R-41 (8)). A request
    that is no longer pending answers 409 ``invalid-transition``, and so does, by name, a pending
    one whose subject type has no specification (``_require_specified``). Open steps become VOIDED,
    ``void_reason`` is ``WITHDRAWN_BY_PREPARER``, and ``SubjectSpec.on_voided`` returns the
    subject to Draft.

    ``through_subject``: the caller is a command of the subject's own domain. Its route names the
    SUBJECT, it has authorised the principal for the subject and it found the pending request
    there, so the request is no secret to that principal and anyone but the preparer receives the
    403 those routes document (PRD SM-01; 04 §16.14 API-R-37 shapes) — also a second preparer,
    who holds the route's permission and cannot read the request. The routes of the approvals API
    never pass it (``tests/architecture/test_withdraw_through_subject.py``).

    Through a subject the request is locked, closed and read back under the tenant's scope (04
    §16.10 rev 1.319 "The request's row is the kernel's"): the subject's command runs under the
    scope of its own permission, which need not hold the one entity the request names, and the
    row policy would answer 404 for the subject's own pending request. On the approvals routes
    the lock stays behind the row policy: a lock on a row the caller cannot read would confirm
    an id by its wait (R-41 (8)).
    """
    if not through_subject:
        return _withdraw(uow, approval_request_id, comment, through_subject=False)
    with system_entity_scope(uow.session):
        return _withdraw(uow, approval_request_id, comment, through_subject=True)


def _withdraw(
    uow: UnitOfWork, approval_request_id: UUID, comment: str | None, *, through_subject: bool
) -> Mapping[str, Any]:
    """``withdraw``, under the scope it is called in."""
    principal = uow.principal
    session = uow.session
    request = _lock_request(session, approval_request_id)
    if not through_subject:
        _require_visible(uow, request)
    person = principal.kind is PrincipalKind.USER and principal.id is not None
    if not person or principal.id != request["preparer_id"]:
        # The caller reads the request, or reached it through the subject's own command: the
        # refused attempt is on record (item APR-DENIED-AUDIT-1). No permission is refused —
        # a withdrawal is its preparer's own.
        record_denial(
            uow,
            action=WITHDRAW_ACTION,
            reason=DENIED_NOT_PREPARER if person else DENIED_NOT_A_PERSON,
            **_of(request),
        )
        raise Problem("forbidden", WITHDRAW_DETAIL)
    _require_pending(request)
    spec = _require_specified(request)
    _void(
        uow,
        request,
        spec,
        status=ApprovalRequestStatus.WITHDRAWN,
        reason=VOID_WITHDRAWN_BY_PREPARER,
        action=WITHDRAW_ACTION,
        comment=comment,
    )
    return _request_row(session, approval_request_id)


def void_if_stale(
    uow: UnitOfWork, *, subject_type: ApprovalSubjectType, subject_id: UUID
) -> Mapping[str, Any] | None:
    """Void the subject's PENDING request when its content changed (DG-KRN-APR-05; BR-PLT-05).

    Commands that change a subject call it in their own transaction. Returns the voided request, or
    None when no request is pending or the content hash is unchanged.

    The request is found, voided and read back under the tenant's scope (04 §16.10 rev 1.319
    "The request's row is the kernel's"): the command has authorised its caller for the subject,
    and under the scope of its own permission the row policy could hide the one entity the
    request names — a changed subject would then leave its pending request standing until a
    decision hashed it again.
    """
    subject_type = ApprovalSubjectType(subject_type)
    session = uow.session
    with system_entity_scope(session):
        request = _pending_of(session, subject_type, subject_id)
        if request is None:
            return None
        spec = spec_for(subject_type)
        current_sha256 = current_content_sha256(uow, spec, request)
        if current_sha256 == request["subject_content_sha256"]:
            return None
        _void(
            uow,
            MappingProxyType(dict(request)),
            spec,
            status=ApprovalRequestStatus.VOIDED,
            reason=VOID_STALE_SUBJECT,
            action=VOID_ACTION,
            comment=None,
            after={"subject_content_sha256": current_sha256},
        )
        return _request_row(session, request["id"])


def _pending_of(
    session: Session, subject_type: ApprovalSubjectType, subject_id: UUID
) -> Mapping[str, Any] | None:
    """The subject's PENDING request, locked; None without one. The caller holds the scope."""
    found = (
        session.execute(
            select(approval_request)
            .where(
                approval_request.c.subject_type == subject_type.value,
                approval_request.c.subject_id == subject_id,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    return None if found is None else dict(found)


def void_subject(
    uow: UnitOfWork,
    *,
    subject_type: ApprovalSubjectType,
    subject_id: UUID,
    comment: str | None,
) -> Mapping[str, Any] | None:
    """Void the subject's PENDING request because a command ended the subject, with
    ``void_reason`` ``SUBJECT_VOIDED`` (04 T-PLT-17; PRD SM-08 "Cancel journal run"; BUILD_SPEC
    CLO-11). Returns the voided request, or None when no request is pending. Found, voided and
    read back under the tenant's scope, as ``void_if_stale`` does (04 §16.10 rev 1.319)."""
    subject_type = ApprovalSubjectType(subject_type)
    session = uow.session
    with system_entity_scope(session):
        request = _pending_of(session, subject_type, subject_id)
        if request is None:
            return None
        _void(
            uow,
            MappingProxyType(dict(request)),
            spec_for(subject_type),
            status=ApprovalRequestStatus.VOIDED,
            reason=VOID_SUBJECT_VOIDED,
            action=VOID_ACTION,
            comment=comment,
        )
        return _request_row(session, request["id"])


def bulk_approve(
    ctx: RequestContext,
    items: Sequence[BulkApproveItem],
    *,
    comment: str | None,
    clock: Clock,
    keyring: KeyRing,
    files: FileStore,
) -> list[BulkApproveResult]:
    """Approve each item through ``decide`` in its own unit of work (DG-KRN-APR-03; REQ-PLT-017).

    Every item gets its own decision, preview hash and separation checks. A refused item keeps its
    problem and the request's status after the attempt (VOIDED for a stale subject); the other
    items are unaffected. More than 200 items, or none, is 422 ``validation-failed``.
    """
    if not 1 <= len(items) <= BULK_LIMIT:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="items", rule_id=RULE_BULK, message=BULK_SIZE)],
        )
    results: list[BulkApproveResult] = []
    for item in items:
        try:
            with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
                row = decide(
                    uow,
                    approval_request_id=item.approval_request_id,
                    decision="APPROVE",
                    subject_content_sha256=item.subject_content_sha256,
                    impact_preview_sha256=item.impact_preview_sha256,
                    comment=comment,
                    reason_code=None,
                )
                uow.commit()
        except Problem as problem:
            # A 404 is an id outside the caller's scope: no status either (REQ-PLT-012).
            status = (
                None
                if problem.slug == "not-found"
                else _visible_status(ctx, item.approval_request_id)
            )
            results.append(BulkApproveResult(item.approval_request_id, status, problem))
            continue
        results.append(
            BulkApproveResult(item.approval_request_id, ApprovalRequestStatus(row["status"]), None)
        )
    return results


def _visible_status(ctx: RequestContext, request_id: UUID) -> ApprovalRequestStatus | None:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one_or_none()
    return None if status is None else ApprovalRequestStatus(status)


def _void(
    uow: UnitOfWork,
    request: Mapping[str, Any],
    spec: SubjectSpec,
    *,
    status: ApprovalRequestStatus,
    reason: str,
    action: str,
    comment: str | None,
    after: Mapping[str, Any] | None = None,
) -> None:
    """Close a PENDING request without a decision: open steps become VOIDED, the request takes
    ``status`` with ``voided_at`` and ``void_reason``, one audit event is written and
    ``spec.on_voided`` runs in the same transaction."""
    session = uow.session
    request_id = request["id"]
    assigned = _assigned_memberships(uow, request)
    open_steps = session.execute(
        select(approval_step.c.id, approval_step.c.status)
        .where(
            approval_step.c.approval_request_id == request_id,
            approval_step.c.status.in_(
                [ApprovalStepStatus.ACTIVE.value, ApprovalStepStatus.WAITING.value]
            ),
        )
        .order_by(approval_step.c.step_no)
    ).all()
    for step_id, step_status in open_steps:
        active = step_status == ApprovalStepStatus.ACTIVE.value
        transitions.apply(
            session,
            "approval_step",
            step_id,
            to_status=ApprovalStepStatus.VOIDED.value,
            expected_status=str(step_status),
            set_values={"completed_at": uow.now} if active else {},
        )
    transitions.apply(
        session,
        "approval_request",
        request_id,
        to_status=status.value,
        expected_status=ApprovalRequestStatus.PENDING.value,
        set_values={"voided_at": uow.now, "void_reason": reason},
    )
    uow.audit(
        action=action,
        object_type=OBJECT_TYPE,
        object_id=request_id,
        before={"status": request["status"], "current_step_no": request["current_step_no"]},
        after={"status": status.value, "void_reason": reason, **(after or {})},
        comment=comment,
        approval_request_id=request_id,
    )
    with system_entity_scope(session):
        spec.on_voided(uow, request["subject_id"], request_id)
    # Each recipient is told the summary it is shown (04 §16.10 rev 1.208): the people the
    # request was waiting for could decide it and read its content; the preparer is told the
    # summary only while it reads the subject in full (``_preparer_summary``; rev 1.319).
    told: dict[str, set[UUID]] = {str(request["summary"]): set(assigned)}
    preparer = _membership_of(session, request["tenant_id"], request["preparer_id"])
    if preparer is not None and status is ApprovalRequestStatus.VOIDED:
        told.setdefault(_preparer_summary(uow, request), set()).add(preparer)
    for summary, recipients in told.items():
        notifications.notify(
            uow,
            recipient_membership_ids=sorted(recipients),
            kind=NotificationKind.APPROVAL_VOIDED,
            title=f"Approval voided: {summary}",
            body=VOIDED_BODY,
            link_path=_subject_link(session, spec, request),
            subject_type=str(request["subject_type"]),
            subject_id=request["subject_id"],
        )


def _advance(
    uow: UnitOfWork,
    request: Mapping[Any, Any],
    step: Mapping[Any, Any],
    decision: ApprovalDecisionKind,
) -> ApprovalRequestStatus:
    """Step and request transitions after a decision; returns the request status."""
    session = uow.session
    request_id = request["id"]
    if decision is ApprovalDecisionKind.REJECT:
        transitions.apply(
            session,
            "approval_step",
            step["id"],
            to_status=ApprovalStepStatus.REJECTED.value,
            expected_status=ApprovalStepStatus.ACTIVE.value,
            set_values={"completed_at": uow.now},
        )
        _skip_waiting(session, request_id)
        return _finish(uow, request_id, ApprovalRequestStatus.REJECTED)

    approvals = session.execute(
        select(func.count()).where(
            approval_decision.c.approval_step_id == step["id"],
            approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
        )
    ).scalar_one()
    if approvals < step["min_approvers"]:
        return ApprovalRequestStatus.PENDING
    # BUILD_SPEC CLO-7 / CTL-018: a close subject's step may need one approver of a role among the
    # ``min_approvers`` (PERIOD_REOPEN: at least one Controller; PRD §2.5, D-75 Q12). Distinct
    # approvers are counted as ``quorum.step_outcome`` counts them; ``decisions_of`` counts a role
    # only when it is held for the request's entities (REQ-CLS-011 rev 1.19; SC-N5).
    required = _any_role_required(session, request, step)
    if required is not None:
        decisions = decisions_of(
            session,
            request_id,
            tenant_id=uow.principal.tenant_id,
            at=uow.now,
            step_id=UUID(str(step["id"])),
        )
        outcome = quorum.step_outcome(
            decisions, quorum.Quorum(int(step["min_approvers"]), required)
        )
        if outcome is not quorum.StepOutcome.APPROVED:
            return ApprovalRequestStatus.PENDING
    transitions.apply(
        session,
        "approval_step",
        step["id"],
        to_status=ApprovalStepStatus.APPROVED.value,
        expected_status=ApprovalStepStatus.ACTIVE.value,
        set_values={"completed_at": uow.now},
    )
    following = session.execute(
        select(approval_step.c.id, approval_step.c.step_no).where(
            approval_step.c.approval_request_id == request_id,
            approval_step.c.step_no == step["step_no"] + 1,
        )
    ).one_or_none()
    if following is None:
        return _finish(uow, request_id, ApprovalRequestStatus.APPROVED)
    transitions.apply(
        session,
        "approval_step",
        following.id,
        to_status=ApprovalStepStatus.ACTIVE.value,
        expected_status=ApprovalStepStatus.WAITING.value,
        set_values={"activated_at": uow.now},
    )
    transitions.apply(
        session,
        "approval_request",
        request_id,
        to_status=None,
        set_values={"current_step_no": following.step_no},
    )
    return ApprovalRequestStatus.PENDING


def _any_role_required(
    session: Session, request: Mapping[Any, Any], step: Mapping[Any, Any]
) -> str | None:
    """The role at least one approver of ``step`` must hold (``PERIOD_REOPEN``: a Controller;
    REQ-CLS-011), or None. The requirement belongs to the subject's OWN step — the first step of
    the request that carries the subject's permission, which ``routing.apply_floor`` guarantees —
    wherever a routing rule placed it, so a rule that adds a step before it cannot shed the quorum
    (R-26 (c); 04 T-REF-26 rev 1.104)."""
    subject_type = ApprovalSubjectType(
        str(getattr(request["subject_type"], "value", request["subject_type"]))
    )
    required = quorum.floor_role_required(subject_type)
    if required is None:
        return None
    own_step_no = session.execute(
        select(func.min(approval_step.c.step_no)).where(
            approval_step.c.approval_request_id == request["id"],
            approval_step.c.required_permission == spec_for(subject_type).required_permission,
        )
    ).scalar_one()
    return required if own_step_no is not None and int(step["step_no"]) == own_step_no else None


def decisions_of(
    session: Session,
    approval_request_id: UUID,
    *,
    tenant_id: UUID,
    at: datetime,
    step_id: UUID | None = None,
) -> tuple[quorum.Decision, ...]:
    """The recorded decisions of a request (of one step when ``step_id`` is given) as
    ``quorum.Decision`` rows in decision order, each with the role codes its approver holds at
    ``at`` FOR THE REQUEST'S ENTITIES — a role assigned for another entity is not among them (04
    T-PLT-18 rev 1.104; REQ-CLS-011; SC-N5); AUTO_APPROVE rows (no person) are left out. Shared by
    ``_advance`` (the any-role predicate, CTL-018) and the close domain's ``PERIOD_REOPEN``
    handler (SM-07)."""
    entities = request_entities(_request_row(session, approval_request_id))
    conditions = [approval_decision.c.approval_request_id == approval_request_id]
    if step_id is not None:
        conditions.append(approval_decision.c.approval_step_id == step_id)
    rows = session.execute(
        select(
            approval_decision.c.approver_id,
            approval_decision.c.decision,
            approval_decision.c.on_behalf_of_id,
        )
        .where(*conditions)
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    ).all()
    memberships: dict[UUID, UUID | None] = {}
    for row in rows:
        if row.approver_id is not None:
            approver = UUID(str(row.approver_id))
            memberships.setdefault(approver, _membership_of(session, tenant_id, approver))
    roles = notifications.role_codes_of(
        session,
        membership_ids=[value for value in memberships.values() if value is not None],
        at=at,
        entity_ids=entities.ids,
        all_entities=entities.all_entities,
    )
    decisions: list[quorum.Decision] = []
    for row in rows:
        if row.approver_id is None:
            continue
        approver = UUID(str(row.approver_id))
        membership = memberships.get(approver)
        decisions.append(
            quorum.Decision(
                actor_id=approver,
                kind=ApprovalDecisionKind(str(getattr(row.decision, "value", row.decision))),
                roles=frozenset() if membership is None else roles.get(membership, frozenset()),
                on_behalf_of_id=None
                if row.on_behalf_of_id is None
                else UUID(str(row.on_behalf_of_id)),
            )
        )
    return tuple(decisions)


def _finish(
    uow: UnitOfWork, request_id: UUID, status: ApprovalRequestStatus
) -> ApprovalRequestStatus:
    transitions.apply(
        uow.session,
        "approval_request",
        request_id,
        to_status=status.value,
        expected_status=ApprovalRequestStatus.PENDING.value,
        set_values={"decided_at": uow.now},
    )
    return status


def _membership_of(session: Session, tenant_id: UUID, user_id: UUID | None) -> UUID | None:
    """The user's membership of the request's tenant; None for a SYSTEM preparer.

    The tenant is named because RLS-TM also shows the signed-in user their memberships of other
    tenants (04 §3 RLS-TM), so a preparer who belongs to two workspaces matched two rows (WEB-10).
    """
    if user_id is None:
        return None
    value = session.execute(
        select(tenant_membership.c.id).where(
            tenant_membership.c.tenant_id == tenant_id, tenant_membership.c.user_id == user_id
        )
    ).scalar_one_or_none()
    return None if value is None else UUID(str(value))


def _display_name(session: Session, user_id: UUID | None) -> str:
    if user_id is None:
        return SYSTEM_DISPLAY_NAME
    value = session.execute(
        select(app_user.c.display_name).where(app_user.c.id == user_id)
    ).scalar_one_or_none()
    return SYSTEM_DISPLAY_NAME if value is None else str(value)


def _subject_link(session: Session, spec: SubjectSpec, request: Mapping[str, Any]) -> str:
    """The subject route of NTF-02 to NTF-04: the covered table's link when a covered table holds
    the subject ([J] D-88 L7-2-Q-7), else the spec's route, else the request detail."""
    covered = covered_link(session, spec.subject_type, request["subject_id"])
    if covered is not None:
        return covered
    if spec.link_path is not None:
        return spec.link_path(request["subject_id"])
    return REQUEST_LINK.format(request_id=request["id"])


def _impact(request: Mapping[str, Any]) -> str | None:
    """The request amount with its currency code, at the currency's minor unit (PRD NTF-01)."""
    amount, currency = request["amount_functional"], request["amount_currency"]
    if amount is None or currency is None:
        return None
    places = ISO_4217[str(currency)].minor_unit
    return f"{Decimal(amount):,.{places}f} {currency}"


def _eligible_memberships(
    session: Session,
    request: Mapping[str, Any],
    *,
    permission: str,
    role_id: UUID | None,
    barred: Collection[UUID],
    ordinal: int,
    at: datetime,
) -> list[UUID]:
    """The memberships that could decide a step of ``request`` with ``permission`` — and the role
    ``role_id``, when the step names one: the holders for EVERY entity of the request and those
    of their delegates who read the request's subject in full themselves (``find_authority``;
    04 §16.10 rev 1.319), the role held in their own right for the same entities, less the people in
    ``barred``; a delegate counts only through a delegator who is none of those. ``ordinal`` is
    the approval the step begins with, counted over the request: the members the subject's own
    check refuses that approval are left out (``SubjectSpec.deciders``; R-92)."""
    excluded = (
        {
            UUID(str(value))
            for value in session.scalars(
                select(tenant_membership.c.id).where(
                    of_session_tenant(tenant_membership),
                    tenant_membership.c.user_id.in_(set(barred)),
                )
            )
        }
        if barred
        else set()
    )
    entities = request_entities(request)
    # ``barred``: a delegate counts only through a delegator who may decide the request itself.
    holders = notifications.permission_holders_covering(
        session,
        permission=permission,
        entity_ids=entities.ids,
        all_entities=entities.all_entities,
        at=at,
        barred=excluded,
        readers=readers.of(request["subject_type"]),
    )
    required_role = _step_role(session, role_id)
    if required_role is not None and holders:
        held = notifications.role_codes_of(
            session,
            membership_ids=holders,
            at=at,
            entity_ids=entities.ids,
            all_entities=entities.all_entities,
        )
        code = str(required_role["code"])
        holders = [holder for holder in holders if code in held.get(holder, frozenset())]
    return _admitted(session, request, holders, ordinal=ordinal, at=at)


def _admitted(
    session: Session,
    request: Mapping[str, Any],
    membership_ids: Sequence[UUID],
    *,
    ordinal: int,
    at: datetime,
) -> list[UUID]:
    """``membership_ids`` less the members the subject's own check refuses approval number
    ``ordinal`` of ``request`` (``SubjectSpec.deciders``; R-92): the notified approvers and the
    approvers counted for a later step are the people ``can_decide`` would answer true for."""
    found = [UUID(str(membership_id)) for membership_id in membership_ids]
    spec = SUBJECTS.get(ApprovalSubjectType(request["subject_type"]))
    if spec is None or spec.deciders is None or not found:
        return found
    users = {
        UUID(str(membership_id)): UUID(str(user_id))
        for membership_id, user_id in session.execute(
            select(tenant_membership.c.id, tenant_membership.c.user_id).where(
                of_session_tenant(tenant_membership), tenant_membership.c.id.in_(found)
            )
        )
    }
    try:
        refused = _refused_deciders(
            session, request, sorted(set(users.values()), key=str), ordinal=ordinal, at=at
        )
    except SubjectNotVisible:
        return []  # the subject row is gone: nobody decides the request
    return [membership_id for membership_id in found if users.get(membership_id) not in refused]


def assignment_blocked(
    session: Session, request: Mapping[str, Any], *, at: datetime
) -> bool | None:
    """Current active-step availability, without writing or altering routing facts.

    A request whose subject implementation is unavailable cannot be assessed here. Its
    existing named lifecycle refusal remains authoritative; a role change cannot fix it.
    """
    if request["status"] != ApprovalRequestStatus.PENDING.value:
        return False
    if ApprovalSubjectType(request["subject_type"]) not in SUBJECTS:
        return None
    return not assigned_memberships(session, request, at=at)


def _assigned_memberships(uow: UnitOfWork, request: Mapping[str, Any]) -> list[UUID]:
    return assigned_memberships(uow.session, request, at=uow.now)


def assigned_memberships(
    session: Session, request: Mapping[str, Any], *, at: datetime
) -> list[UUID]:
    """NTF-01 recipients (NTF-04 on a void): the people ``can_decide`` answers true for (R-64
    (5)) — those who could decide the active step (``_eligible_memberships``), less the preparer,
    the deciders the subject excludes and everyone who decided the request, and less a person a
    later step cannot do without (``_reserved_for_later_step``; R-66 (7)), who is told when that
    step becomes active; a delegate counts only through a delegator who is none of those."""
    step = session.execute(
        select(approval_step.c.required_permission, approval_step.c.required_role_id).where(
            approval_step.c.approval_request_id == request["id"],
            approval_step.c.status == ApprovalStepStatus.ACTIVE.value,
        )
    ).one_or_none()
    if step is None:
        return []
    barred = _barred(session, request)
    ordinal = _next_ordinal(session, request)

    def eligible(people: Collection[UUID]) -> list[UUID]:
        return _eligible_memberships(
            session,
            request,
            permission=str(step.required_permission),
            role_id=step.required_role_id,
            barred=people,
            ordinal=ordinal,
            at=at,
        )

    found = eligible(barred)
    later = _later_steps(session, request)
    if not found or not later:
        return found
    users = {
        UUID(str(user_id))
        for user_id in session.scalars(
            select(tenant_membership.c.user_id).where(
                of_session_tenant(tenant_membership), tenant_membership.c.id.in_(found)
            )
        )
    }
    available = [_step_deciders(session, request, item, barred, at=at) for item in later]
    reserved = {
        user_id
        for user_id in users
        if any(
            _starves(session, request, item, barred, [user_id], count, at=at)
            for item, count in zip(later, available, strict=True)
        )
    }
    return eligible(barred | reserved) if reserved else found


@dataclass(frozen=True, slots=True)
class _LaterStep:
    """A step of a request that is not active yet, with the ordinal of its first approval."""

    required_permission: str
    required_role_id: UUID | None
    min_approvers: int
    ordinal: int


def _later_steps(session: Session, request: Mapping[str, Any]) -> list[_LaterStep]:
    """The steps of ``request`` after its current one, in order, each with the ordinal of the
    approval it begins with: one more than the approvers of all steps before it."""
    rows = session.execute(
        select(
            approval_step.c.step_no,
            approval_step.c.required_permission,
            approval_step.c.required_role_id,
            approval_step.c.min_approvers,
        )
        .where(approval_step.c.approval_request_id == request["id"])
        .order_by(approval_step.c.step_no)
    ).all()
    found: list[_LaterStep] = []
    before = 0
    for row in rows:
        if row.step_no > request["current_step_no"]:
            found.append(
                _LaterStep(
                    required_permission=str(row.required_permission),
                    required_role_id=row.required_role_id,
                    min_approvers=int(row.min_approvers),
                    ordinal=before + 1,
                )
            )
        before += int(row.min_approvers)
    return found


def _step_deciders(
    session: Session,
    request: Mapping[str, Any],
    step: _LaterStep,
    barred: Collection[UUID],
    *,
    at: datetime,
) -> int:
    """How many people could decide ``step`` of ``request`` now, were it active, when the people
    in ``barred`` may not."""
    return len(
        _eligible_memberships(
            session,
            request,
            permission=step.required_permission,
            role_id=step.required_role_id,
            barred=barred,
            ordinal=step.ordinal,
            at=at,
        )
    )


def _starves(
    session: Session,
    request: Mapping[str, Any],
    step: _LaterStep,
    barred: frozenset[UUID],
    acting: Sequence[UUID],
    available: int,
    *,
    at: datetime,
) -> bool:
    """Whether a later ``step`` that has its approvers now (``available``) would no longer have
    them once the people in ``acting`` have decided an earlier step. A step that is short of
    approvers already is not their doing."""
    needed = step.min_approvers
    if available < needed:
        return False
    return _step_deciders(session, request, step, barred | set(acting), at=at) < needed


def _reserved_for_later_step(
    session: Session, request: Mapping[str, Any], acting: Sequence[UUID], *, at: datetime
) -> bool:
    """Whether a decision on the active step by ``acting`` — the approver and, for a delegated
    decision, the delegator — would leave a later step of the request without its approvers
    (supervisor rulings R-66 (7) and R-87 (2); 04 §16.10 rev 1.104). One decision per person per
    request: whoever decides this step decides no later one, so a person a later step cannot do
    without is kept for it — the request would otherwise stop there and only a withdrawal could
    end it (a tenant's only Controller approving the first step of a request whose second step
    takes a Controller). A later step that is short of approvers already is not this decision's
    doing and refuses nobody. Approvers are counted as people who could decide the step now; a
    delegate and the one delegator it acts for count as two."""
    later = _later_steps(session, request)
    if not later:
        return False
    barred = _barred(session, request)
    return any(
        _starves(
            session,
            request,
            step,
            barred,
            acting,
            _step_deciders(session, request, step, barred, at=at),
            at=at,
        )
        for step in later
    )


def _notify_assigned(uow: UnitOfWork, request_id: UUID) -> None:
    """NTF-01 assignments or NTF-13 access-admin alert when a step becomes active."""
    session = uow.session
    request = _request_row(session, request_id)
    recipients = _assigned_memberships(uow, request)
    if not recipients:
        entities = request_entities(request)
        administrators = notifications.permission_holders_direct(
            session,
            permission="role.manage",
            entity_ids=entities.ids,
            all_entities=entities.all_entities,
            at=uow.now,
        )
        notifications.notify(
            uow,
            recipient_membership_ids=sorted(administrators, key=str),
            kind=NotificationKind.APPROVAL_UNASSIGNED,
            title=f"Approval {request['request_no']} needs an independent approver",
            body=(
                f"Approval {request['request_no']} has no independent eligible approver "
                "for its active step. Review role assignments and separation of duties."
            ),
            link_path="/settings/roles",
            subject_type=OBJECT_TYPE,
            subject_id=request_id,
        )
        return
    summary = str(request["summary"])
    body = f"{_display_name(session, request['preparer_id'])} submitted {summary} for approval."
    impact = _impact(request)
    if impact is not None:
        body += f" Impact: {impact}."
    notifications.notify(
        uow,
        recipient_membership_ids=recipients,
        kind=NotificationKind.APPROVAL_ASSIGNED,
        title=f"Approval needed: {summary}",
        body=body,
        link_path=REQUEST_LINK.format(request_id=request_id),
        subject_type=OBJECT_TYPE,
        subject_id=request_id,
    )


def _preparer_summary(uow: UnitOfWork, request: Mapping[str, Any]) -> str:
    """The request's summary as its preparer is shown it NOW (04 §16.10 rev 1.208; item
    APR-CONTENT-SCOPE-1): a notification is a read of the summary too, composed for its
    recipient. The preparer reads the content of its request
    while it reads the subject in full — one read permission of the subject for every entity
    the request names (rev 1.319; ``readers.read_in_full``) — or holds the permission of a step
    for all of them (``approval_queries.content_visible`` for the one who prepared it). It may
    never have: an uploader is held to the entities of the rows that commit, the request to
    every entity a row names (R-106 (b)) — and may no longer. Otherwise it is told the subject
    type's name and the request's number (``withheld_summary``). A preparer without a membership
    is told nothing, so the summary stands."""
    summary = str(request["summary"])
    preparer = _membership_of(uow.session, request["tenant_id"], request["preparer_id"])
    if preparer is None:
        return summary
    held = effective_grants(uow.session, preparer, at=uow.now).permission_scopes
    entities = request_entities(request)
    if readers.read_in_full(held, request["subject_type"], entities):
        return summary
    steps = uow.session.scalars(
        select(approval_step.c.required_permission).where(
            approval_step.c.approval_request_id == request["id"]
        )
    )
    if any(str(code) in held and entities.covered_by(held[str(code)]) for code in set(steps)):
        return summary
    return withheld_summary(request["subject_type"], str(request["request_no"]))


def _notify_preparer(
    uow: UnitOfWork,
    spec: SubjectSpec,
    request: Mapping[str, Any],
    kind: NotificationKind,
    *,
    title: str,
    body: str,
) -> None:
    """NTF-02 and NTF-03: the preparer learns the outcome. The caller composes ``title`` and
    ``body`` with ``_preparer_summary``."""
    preparer = _membership_of(uow.session, request["tenant_id"], request["preparer_id"])
    if preparer is None:
        return
    notifications.notify(
        uow,
        recipient_membership_ids=[preparer],
        kind=kind,
        title=title,
        body=body,
        link_path=_subject_link(uow.session, spec, request),
        subject_type=str(request["subject_type"]),
        subject_id=request["subject_id"],
    )
