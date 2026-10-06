"""Approval step completion, the decision refusal order and the close-subject routing as pure
functions (dev-guide DG-KRN-APR-02; PRD §2.5 routing rows for ``MANUAL_ADJUSTMENT``,
``PERIOD_LOCK``, ``PERIOD_REOPEN`` and ``JOURNAL_RUN``; REQ-CLS-011 and D-75 Q12; BR-PLT-06;
ERR-02, ERR-03, ERR-27, ERR-28).

``step_outcome`` decides whether a step is still ``PENDING``, ``APPROVED`` or ``REJECTED`` from
its decisions and a ``Quorum``: ``min_approvers`` distinct approvers (a person and the delegator
they act for count once) and, when ``role_required_any`` is set, at least one approver holding
that role. The ``PERIOD_REOPEN`` step (two approvers, at least one Controller) is the case
``routing.StepPlan.role_id`` cannot express, because a step role narrows every approver (CTR-9);
the engine's ``_advance`` adopts this predicate in CLO-7 under CTL-018.

``refusal`` reproduces the check order of ``engine.decide`` and adds the BR-PLT-06 step-up window
(``mfa.STEP_UP_WINDOW``) after the presence check, which the engine does not apply yet (F-CLO
preparation record Q-7). ``route`` is the PRD §2.5 routing of the close subjects as
``RoutedStep`` rows with role codes (T-PLT-09; ``auth/permissions.py`` ``DEFAULT_ROLES``).

Nothing here reads a session; ``tests/unit/approvals/test_quorum.py`` is the contract
(``docs/reviews/loop/prod/F-CLO-prep.md`` §6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from erev_api.approvals import routing
from erev_api.auth import mfa
from erev_api.enums import ApprovalDecisionKind, ApprovalRequestStatus, ApprovalSubjectType

CONTROLLER: Final = "controller"  # T-PLT-09 role code
REVENUE_REVIEWER: Final = "revenue_reviewer"
ADJUSTMENT_THRESHOLD: Final = Decimal(10000)  # PRD §2.5 :274-275, functional USD
ATTACHMENT_REQUIRED: Final = (
    "Attach supporting evidence: adjustments of USD 10,000.00 or more need an attachment."
)
RULE_ATTACHMENT: Final = "PRD-2.5"


class StepOutcome(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class Quorum:
    """How a step completes: ``min_approvers`` distinct approvers and, when set, at least one of
    them holding ``role_required_any`` (04 T-PLT-18 ``ck_approval_step__min_approvers``: 1 to 5)."""

    min_approvers: int
    role_required_any: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.min_approvers <= routing.MAX_APPROVERS:
            raise ValueError("a step needs between 1 and 5 approvers")


@dataclass(frozen=True, slots=True)
class Decision:
    """One recorded decision: the acting person, their role codes and the delegator they act for."""

    actor_id: UUID
    kind: ApprovalDecisionKind
    roles: frozenset[str] = frozenset()
    on_behalf_of_id: UUID | None = None

    def acting(self) -> frozenset[UUID]:
        ids = {self.actor_id}
        if self.on_behalf_of_id is not None:
            ids.add(self.on_behalf_of_id)
        return frozenset(ids)


LOCK_QUORUM: Final = Quorum(1)  # PRD :285, one Controller on a role-narrowed step
REOPEN_QUORUM: Final = Quorum(2, CONTROLLER)  # PRD :286; REQ-CLS-011; D-75 Q12


def step_outcome(decisions: Sequence[Decision], quorum: Quorum) -> StepOutcome:
    """``REJECTED`` on any rejection; ``APPROVED`` when the quorum is met; otherwise ``PENDING``."""
    if any(decision.kind is ApprovalDecisionKind.REJECT for decision in decisions):
        return StepOutcome.REJECTED
    seen: set[UUID] = set()
    counted: list[Decision] = []
    for decision in decisions:
        if decision.kind is not ApprovalDecisionKind.APPROVE:
            continue
        acting = decision.acting()
        if acting & seen:
            continue  # the same person, directly or through a delegation, counts once
        seen |= acting
        counted.append(decision)
    if len(counted) < quorum.min_approvers:
        return StepOutcome.PENDING
    role = quorum.role_required_any
    if role is not None and not any(role in decision.roles for decision in counted):
        return StepOutcome.PENDING
    return StepOutcome.APPROVED


@dataclass(frozen=True, slots=True)
class DecisionFacts:
    """What ``engine.decide`` establishes before it writes, as plain facts."""

    actor_id: UUID
    preparer_id: UUID | None
    now: datetime
    mfa_verified_at: datetime | None
    is_person: bool = True
    request_status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING
    holds_permission: bool = True  # one authority covers every entity; a delegate reads them
    in_scope: bool = True  # the principal can read the request (``engine.visible_to``)
    holds_step_role: bool = True
    on_behalf_of_id: UUID | None = None
    excluded_ids: frozenset[UUID] = frozenset()
    earlier_decider_ids: frozenset[UUID] = frozenset()
    decision: ApprovalDecisionKind = ApprovalDecisionKind.APPROVE
    comment: str | None = None
    step_up_required: bool = True  # BR-PLT-06; False reproduces the engine as built


def refusal(facts: DecisionFacts) -> str | None:
    """The problem slug ``decide`` raises for these facts, in its check order, or None."""
    if facts.decision is ApprovalDecisionKind.AUTO_APPROVE:
        raise ValueError("a person decides APPROVE or REJECT")
    if not facts.is_person:
        return "forbidden"  # DG-KRN-APR-04
    if not facts.in_scope:
        # The principal cannot read the request (``engine.visible_to``): 404 like an unknown id,
        # before its status or anything else is told (REQ-PLT-012; R-41 (8)).
        return "not-found"
    if facts.request_status is not ApprovalRequestStatus.PENDING:
        return "invalid-transition"
    if not facts.holds_permission:
        return "forbidden"  # readable, and no authority for every entity of the request
    if not facts.holds_step_role:
        return "forbidden"  # CTR-9 step role
    if facts.mfa_verified_at is None:
        return "mfa-required"  # ERR-27
    if facts.step_up_required and not mfa.step_up_fresh_at(facts.mfa_verified_at, facts.now):
        return "mfa-step-up-required"  # ERR-28; BR-PLT-06
    acting = {facts.actor_id}
    if facts.on_behalf_of_id is not None:
        acting.add(facts.on_behalf_of_id)
    if facts.preparer_id in acting or acting & facts.excluded_ids:
        return "self-approval"  # ERR-02; DB-10
    if acting & facts.earlier_decider_ids:
        return "approver-already-decided"  # ERR-03
    if facts.decision is ApprovalDecisionKind.REJECT and not (facts.comment or "").strip():
        return "validation-failed"  # T-PLT-20 comment on rejection
    return None


class AttachmentRequired(ValueError):
    """PRD §2.5: a manual adjustment at or above the threshold needs an attachment before it
    routes."""

    slug: Final = "validation-failed"
    field: Final = "attachments"
    rule_id: Final = RULE_ATTACHMENT

    def __init__(self) -> None:
        super().__init__(ATTACHMENT_REQUIRED)


@dataclass(frozen=True, slots=True)
class RoutedStep:
    """A PRD §2.5 step with role codes: ``role`` narrows every approver (T-PLT-18
    ``required_role_id``); ``role_required_any`` is the any-approver requirement of ``Quorum``."""

    name: str
    permission: str
    min_approvers: int
    role: str | None = None
    role_required_any: str | None = None

    def quorum(self) -> Quorum:
        return Quorum(self.min_approvers, self.role_required_any)


def any_role_required(subject: ApprovalSubjectType, step_no: int) -> str | None:
    """The ``role_required_any`` of step ``step_no`` (1-based) of a close subject's PRD §2.5
    routing — ``controller`` for the ``PERIOD_REOPEN`` step (REQ-CLS-011; D-75 Q12) — and None for
    every other subject or step. ``engine._advance`` reads it so that two approvals without a
    Controller leave the request PENDING (BUILD_SPEC CLO-7; CTL-018)."""
    if ApprovalSubjectType(subject) is not ApprovalSubjectType.PERIOD_REOPEN:
        return None  # MANUAL_ADJUSTMENT routes by amount and attachment; no any-role step exists
    steps = route(ApprovalSubjectType.PERIOD_REOPEN)
    if not 1 <= step_no <= len(steps):
        return None
    return steps[step_no - 1].role_required_any


def floor_role_required(subject: ApprovalSubjectType) -> str | None:
    """The ``role_required_any`` of the subject's OWN step — the first step of its PRD §2.5 routing
    (``controller`` for ``PERIOD_REOPEN``). ``engine._advance`` applies it to the step of a request
    that carries the subject's permission, wherever routing placed that step, so the quorum is part
    of the floor a routing rule cannot lower (R-26 (c); 04 T-REF-26 rev 1.104)."""
    return any_role_required(subject, 1)


def route(
    subject: ApprovalSubjectType,
    *,
    amount_functional_abs: Decimal | None = None,
    has_attachment: bool = False,
) -> tuple[RoutedStep, ...]:
    """The PRD §2.5 steps of a close subject; ``KeyError`` for a subject this module does not
    route."""
    subject = ApprovalSubjectType(subject)
    if subject is ApprovalSubjectType.MANUAL_ADJUSTMENT:
        if amount_functional_abs is None:
            raise ValueError("a manual adjustment routes by amount_functional_abs")
        first = RoutedStep("adjustment", "adjustment.approve", 1)
        if amount_functional_abs < ADJUSTMENT_THRESHOLD:
            return (first,)
        if not has_attachment:
            raise AttachmentRequired
        return (first, RoutedStep("controller", "adjustment.approve", 1, role=CONTROLLER))
    if subject is ApprovalSubjectType.PERIOD_LOCK:
        return (RoutedStep("lock", "period.lock", 1, role=CONTROLLER),)
    if subject is ApprovalSubjectType.PERIOD_REOPEN:
        return (RoutedStep("reopen", "period.reopen_approve", 2, role_required_any=CONTROLLER),)
    if subject is ApprovalSubjectType.JOURNAL_RUN:
        return (RoutedStep("journal_run", "journal.approve", 1),)
    raise KeyError(f"{subject.value} is not routed by erev_api.approvals.quorum")
