"""Approval step completion, decision refusal order and the close-subject routing as pure
functions (DG-KRN-APR-02; PRD §2.5 rows :274–286; REQ-CLS-011; D-75 Q12; BR-PLT-06; ERR-02, ERR-03,
ERR-27, ERR-28). F-CLO preparation: `docs/reviews/loop/prod/F-CLO-prep.md` §6."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.approvals import quorum, routing
from erev_api.auth.permissions import spec as permission_spec
from erev_api.enums import ApprovalDecisionKind, ApprovalRequestStatus, ApprovalSubjectType

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
PRIYA = UUID("00000000-0000-0000-0000-0000000000a1")
MARCUS = UUID("00000000-0000-0000-0000-0000000000a2")
ELENA = UUID("00000000-0000-0000-0000-0000000000a3")
RR1 = UUID("00000000-0000-0000-0000-0000000000b1")
RR2 = UUID("00000000-0000-0000-0000-0000000000b2")
RR3 = UUID("00000000-0000-0000-0000-0000000000b3")


def _approve(actor: UUID, *roles: str) -> quorum.Decision:
    return quorum.Decision(actor, ApprovalDecisionKind.APPROVE, frozenset(roles))


def _reject(actor: UUID) -> quorum.Decision:
    return quorum.Decision(actor, ApprovalDecisionKind.REJECT, frozenset())


def test_step_outcome_min_approvers() -> None:
    two = quorum.Quorum(2)
    assert quorum.step_outcome((_approve(RR1),), two) is quorum.StepOutcome.PENDING
    assert quorum.step_outcome((_approve(RR1), _approve(RR2)), two) is quorum.StepOutcome.APPROVED
    assert quorum.step_outcome((_approve(RR1), _reject(RR2)), two) is quorum.StepOutcome.REJECTED
    assert quorum.step_outcome((), two) is quorum.StepOutcome.PENDING
    assert (
        quorum.step_outcome((_approve(MARCUS),), quorum.LOCK_QUORUM) is quorum.StepOutcome.APPROVED
    )


def test_reopen_quorum_needs_a_controller() -> None:
    reviewers = (_approve(RR1, quorum.REVENUE_REVIEWER), _approve(RR2, quorum.REVENUE_REVIEWER))
    assert quorum.REOPEN_QUORUM == quorum.Quorum(2, quorum.CONTROLLER)
    assert quorum.step_outcome(reviewers, quorum.REOPEN_QUORUM) is quorum.StepOutcome.PENDING
    assert (
        quorum.step_outcome(
            (*reviewers, _approve(RR3, quorum.REVENUE_REVIEWER)), quorum.REOPEN_QUORUM
        )
        is quorum.StepOutcome.PENDING
    )
    assert (
        quorum.step_outcome((*reviewers, _approve(MARCUS, quorum.CONTROLLER)), quorum.REOPEN_QUORUM)
        is quorum.StepOutcome.APPROVED
    )
    assert (
        quorum.step_outcome(
            (_approve(MARCUS, quorum.CONTROLLER), _approve(RR1, quorum.REVENUE_REVIEWER)),
            quorum.REOPEN_QUORUM,
        )
        is quorum.StepOutcome.APPROVED
    )
    assert (
        quorum.step_outcome((_approve(MARCUS, quorum.CONTROLLER),), quorum.REOPEN_QUORUM)
        is quorum.StepOutcome.PENDING
    )


def test_quorum_validation() -> None:
    for bad in (0, routing.MAX_APPROVERS + 1):
        with pytest.raises(ValueError):
            quorum.Quorum(bad)
    # the same approver counts once, directly or on behalf of someone (DG-KRN-APR-02)
    twice = (
        _approve(RR1),
        quorum.Decision(RR2, ApprovalDecisionKind.APPROVE, frozenset(), on_behalf_of_id=RR1),
    )
    assert quorum.step_outcome(twice, quorum.Quorum(2)) is quorum.StepOutcome.PENDING


def _facts(**overrides: object) -> quorum.DecisionFacts:
    base: dict[str, object] = dict(
        actor_id=MARCUS,
        preparer_id=PRIYA,
        mfa_verified_at=NOW - timedelta(minutes=1),
        now=NOW,
    )
    base.update(overrides)
    return quorum.DecisionFacts(**base)  # type: ignore[arg-type]


def test_refusal_order_follows_decide() -> None:
    assert quorum.refusal(_facts()) is None
    assert (
        quorum.refusal(_facts(is_person=False, request_status=ApprovalRequestStatus.APPROVED))
        == "forbidden"
    )
    assert (
        quorum.refusal(
            _facts(request_status=ApprovalRequestStatus.APPROVED, holds_permission=False)
        )
        == "invalid-transition"
    )
    assert quorum.refusal(_facts(holds_permission=False, in_scope=False)) == "not-found"
    # R-41 (8): a request the principal cannot read answers 404 before its status is told.
    assert (
        quorum.refusal(_facts(in_scope=False, request_status=ApprovalRequestStatus.APPROVED))
        == "not-found"
    )
    assert quorum.refusal(_facts(holds_permission=False)) == "forbidden"
    assert quorum.refusal(_facts(holds_step_role=False, mfa_verified_at=None)) == "forbidden"
    assert quorum.refusal(_facts(mfa_verified_at=None, actor_id=PRIYA)) == "mfa-required"
    stale = NOW - timedelta(minutes=5, seconds=1)
    assert quorum.refusal(_facts(mfa_verified_at=stale, actor_id=PRIYA)) == "mfa-step-up-required"
    assert quorum.refusal(_facts(mfa_verified_at=NOW - timedelta(minutes=5))) is None
    # today's engine checks presence only (Q-7): the flag reproduces it
    assert quorum.refusal(_facts(mfa_verified_at=stale, step_up_required=False)) is None
    assert (
        quorum.refusal(_facts(actor_id=PRIYA, earlier_decider_ids=frozenset({PRIYA})))
        == "self-approval"
    )
    assert quorum.refusal(_facts(on_behalf_of_id=PRIYA)) == "self-approval"
    assert quorum.refusal(_facts(excluded_ids=frozenset({MARCUS}))) == "self-approval"
    assert (
        quorum.refusal(
            _facts(earlier_decider_ids=frozenset({MARCUS}), decision=ApprovalDecisionKind.REJECT)
        )
        == "approver-already-decided"
    )
    assert (
        quorum.refusal(_facts(on_behalf_of_id=ELENA, earlier_decider_ids=frozenset({ELENA})))
        == "approver-already-decided"
    )
    assert (
        quorum.refusal(_facts(decision=ApprovalDecisionKind.REJECT, comment="  "))
        == "validation-failed"
    )
    assert (
        quorum.refusal(
            _facts(decision=ApprovalDecisionKind.REJECT, comment="Attach the acceptance.")
        )
        is None
    )
    with pytest.raises(ValueError):
        quorum.refusal(_facts(decision=ApprovalDecisionKind.AUTO_APPROVE))


def test_route_manual_adjustment_thresholds() -> None:
    below = quorum.route(
        ApprovalSubjectType.MANUAL_ADJUSTMENT, amount_functional_abs=Decimal("9999.99")
    )
    assert [(s.permission, s.min_approvers, s.role) for s in below] == [
        ("adjustment.approve", 1, None)
    ]
    with pytest.raises(quorum.AttachmentRequired) as caught:
        quorum.route(
            ApprovalSubjectType.MANUAL_ADJUSTMENT, amount_functional_abs=Decimal("10000.00")
        )
    assert (caught.value.field, caught.value.slug) == ("attachments", "validation-failed")
    above = quorum.route(
        ApprovalSubjectType.MANUAL_ADJUSTMENT,
        amount_functional_abs=Decimal("10000.00"),
        has_attachment=True,
    )
    assert [(s.permission, s.min_approvers, s.role) for s in above] == [
        ("adjustment.approve", 1, None),
        ("adjustment.approve", 1, quorum.CONTROLLER),
    ]
    assert quorum.ADJUSTMENT_THRESHOLD == Decimal("10000.00")
    with pytest.raises(ValueError):
        quorum.route(ApprovalSubjectType.MANUAL_ADJUSTMENT)


def test_route_period_lock_reopen_and_journal_run() -> None:
    (lock,) = quorum.route(ApprovalSubjectType.PERIOD_LOCK)
    assert (lock.permission, lock.min_approvers, lock.role, lock.role_required_any) == (
        "period.lock",
        1,
        quorum.CONTROLLER,
        None,
    )
    (reopen,) = quorum.route(ApprovalSubjectType.PERIOD_REOPEN)
    assert (reopen.permission, reopen.min_approvers, reopen.role, reopen.role_required_any) == (
        "period.reopen_approve",
        2,
        None,
        quorum.CONTROLLER,
    )
    assert reopen.quorum() == quorum.REOPEN_QUORUM
    (run,) = quorum.route(ApprovalSubjectType.JOURNAL_RUN)
    assert (run.permission, run.min_approvers) == ("journal.approve", 1)
    with pytest.raises(KeyError):
        quorum.route(ApprovalSubjectType.SSP_OVERRIDE)


def test_routed_permissions_are_approval_permissions() -> None:
    for subject in (
        ApprovalSubjectType.PERIOD_LOCK,
        ApprovalSubjectType.PERIOD_REOPEN,
        ApprovalSubjectType.JOURNAL_RUN,
    ):
        for step in quorum.route(subject):
            assert permission_spec(step.permission).is_approval
            assert 1 <= step.min_approvers <= routing.MAX_APPROVERS


def test_any_role_required_names_the_reopen_controller_only() -> None:
    """CLO-7 / CTL-018: the engine's ``_advance`` reads the any-approver role of a routed step —
    ``controller`` for the PERIOD_REOPEN step, None for every other subject and step, and never an
    exception (MANUAL_ADJUSTMENT routes by amount; the helper does not call ``route`` for it)."""
    assert quorum.any_role_required(ApprovalSubjectType.PERIOD_REOPEN, 1) == quorum.CONTROLLER
    assert quorum.any_role_required(ApprovalSubjectType.PERIOD_REOPEN, 2) is None
    assert quorum.any_role_required(ApprovalSubjectType.PERIOD_REOPEN, 0) is None
    for subject in ApprovalSubjectType:
        for step_no in (1, 2):
            expected = (
                quorum.CONTROLLER
                if (subject, step_no) == (ApprovalSubjectType.PERIOD_REOPEN, 1)
                else None
            )
            assert quorum.any_role_required(subject, step_no) == expected, (subject, step_no)
    assert quorum.any_role_required(ApprovalSubjectType.MANUAL_ADJUSTMENT, 1) is None
