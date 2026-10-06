"""SM-07 period state machine as a pure decision function (PRD §5.2 SM-07; BR-CLS-01, -02, -03,
-05, -08; BR-PLT-06, -08; ERR-14, ERR-16, ERR-28, ERR-42, ERR-65; 04 DB-07, E-110 table 3.4-R).
F-CLO preparation: `docs/reviews/loop/prod/F-CLO-prep.md` §5."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.approvals import quorum
from erev_api.domain.close import certification as cert
from erev_api.domain.close import commands, gates
from erev_api.domain.close import period_machine as pm
from erev_api.domain.reference import periods
from erev_api.enums import ApprovalDecisionKind, ChecklistStatus, PeriodState, ReasonCode

CTX = pm.Context(period_key="FY2026-P09", entity_code="AVM-US", book_code="ASC606")
NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
PRIYA = UUID("00000000-0000-0000-0000-0000000000a1")
MARCUS = UUID("00000000-0000-0000-0000-0000000000a2")
ELENA = UUID("00000000-0000-0000-0000-0000000000a3")
RR1 = UUID("00000000-0000-0000-0000-0000000000b1")
RR2 = UUID("00000000-0000-0000-0000-0000000000b2")
COMMENT = "September 2026 close complete"


def _gates(*failing: gates.GateResult) -> tuple[gates.GateResult, ...]:
    by_code = {r.gate_check_code: r for r in failing}
    results = []
    for code in gates.GATE_CHECK_CODES:
        if code in by_code:
            results.append(by_code[code])
        elif code == gates.CONTROLLER_CERTIFIED:
            results.append(
                gates.GateResult(
                    code, ChecklistStatus.FAILED, None, gates.CERTIFICATION_DETAIL, NOW
                )
            )
        else:
            results.append(gates.GateResult(code, ChecklistStatus.PASSED, 0, None, NOW))
    return tuple(results)


def _approve(actor: UUID, *roles: str) -> quorum.Decision:
    return quorum.Decision(actor, ApprovalDecisionKind.APPROVE, frozenset(roles))


def test_transition_pairs_equal_reference_rules() -> None:
    expected = {(a, b) for a, b in periods.ALLOWED_TRANSITIONS if a is not None}
    assert pm.pairs() == expected
    assert {s for pair in pm.pairs() for s in pair} == set(PeriodState)


def test_messages_shared_with_commands() -> None:
    assert pm.NOT_STARTABLE == commands.NOT_STARTABLE
    assert pm.NOT_CLOSING == commands.NOT_CLOSING
    assert pm.NOT_FUTURE == periods.NOT_FUTURE
    assert pm.PREVIOUS_FUTURE == periods.PREVIOUS_FUTURE  # SM-07 guard, enforced at the command
    assert pm.CANCEL_CLOSE_REASONS == commands.CANCEL_CLOSE_REASONS
    assert pm.REASON_NOT_ALLOWED == commands.REASON_NOT_ALLOWED
    assert pm.RULE_REASON == commands.RULE_REASON == "REASON_CODE_NOT_ALLOWED"
    assert pm.REOPEN_REASONS == frozenset(
        {
            ReasonCode.ERROR_CORRECTION,
            ReasonCode.LATE_SOURCE_DATA,
            ReasonCode.AUDIT_ADJUSTMENT,
            ReasonCode.OTHER,
        }
    )


@pytest.mark.parametrize("state", list(PeriodState))
@pytest.mark.parametrize("command", list(pm.Command))
def test_every_other_pair_is_invalid_transition(state: PeriodState, command: pm.Command) -> None:
    allowed_from, _ = pm.TRANSITIONS[pm.EXECUTES.get(command, command)]
    guards = pm.Guards(
        comment=COMMENT,
        reason_code=ReasonCode.ERROR_CORRECTION
        if command in (pm.Command.REQUEST_REOPEN, pm.Command.REOPEN)
        else ReasonCode.OTHER,
        gate_results=_gates(),
        requester_id=PRIYA,
        approver_id=MARCUS,
        mfa_verified_at=NOW,
        now=NOW,
        approvals=(_approve(MARCUS, quorum.CONTROLLER), _approve(ELENA, quorum.CONTROLLER)),
    )
    outcome = pm.decide(state, command, guards, ctx=CTX)
    if state in allowed_from:
        assert not isinstance(outcome, pm.Refusal), outcome
    else:
        assert isinstance(outcome, pm.Refusal)
        assert (outcome.slug, outcome.rule_id, outcome.code) == (
            "invalid-transition",
            "DB-07",
            "EREV-PER-001",
        )
        assert "FY2026-P09" in outcome.detail and state.value in outcome.detail


def test_request_lock_comment_rule_br_plt_08() -> None:
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.REQUEST_LOCK,
        pm.Guards(comment="short", gate_results=_gates()),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Refusal)
    assert (outcome.slug, outcome.detail) == ("validation-failed", "1 field needs attention.")
    assert (outcome.errors[0].field, outcome.errors[0].rule_id) == (
        "certification_comment",
        "BR-PLT-08",
    )
    assert outcome.problem().status == 422


def test_request_lock_gates_failed_err_14() -> None:
    results = _gates(
        gates.GateResult(
            gates.APPROVALS_CLEARED, ChecklistStatus.FAILED, 3, "Pending approvals: 3", NOW
        ),
        gates.GateResult(
            gates.RECONCILIATIONS_GENERATED,
            ChecklistStatus.FAILED,
            2,
            "Reconciliation not generated: Billing to subledger; "
            "Reconciliation not generated: Subledger to GL",
            NOW,
        ),
    )
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.REQUEST_LOCK,
        pm.Guards(comment=COMMENT, gate_results=results),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Refusal)
    assert outcome.slug == "close-gates-failed"
    assert outcome.detail.startswith("2 close gates have not passed:")
    assert [e.rule_id for e in outcome.errors] == ["APPROVALS_CLEARED", "RECONCILIATIONS_GENERATED"]
    assert outcome == cert.refusal(results)


def test_request_lock_accepted_routes_period_lock() -> None:
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.REQUEST_LOCK,
        pm.Guards(comment=COMMENT, gate_results=_gates()),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Accepted)
    assert outcome.transition is None  # the state changes when the approval executes
    assert pm.Effect.REQUEST_PERIOD_LOCK in outcome.effects


def test_br_cls_08_request_lock_refuses_while_an_earlier_period_is_postable() -> None:
    """PRD BR-CLS-08 / ERR-65 (supervisor ruling R-6, CLO-LOCK-ORDER-1): the ordinary lock is
    chronological. The refusal precedes the gates — it is a guard of the state machine, as
    BR-CLS-05 is for the reopen — and follows the comment rule; its detail is the ERR-65 copy."""
    failing = _gates(
        gates.GateResult(gates.HOLDS_REVIEWED, ChecklistStatus.FAILED, 1, "Open holds: 1", NOW)
    )
    for results in (_gates(), failing):
        outcome = pm.decide(
            PeriodState.CLOSING,
            pm.Command.REQUEST_LOCK,
            pm.Guards(comment=COMMENT, gate_results=results, earlier_postable_period="Aug 2026"),
            ctx=CTX,
        )
        assert isinstance(outcome, pm.Refusal)
        assert (outcome.slug, outcome.rule_id) == ("earlier-period-open", "BR-CLS-08")
        assert outcome.detail == (
            "Lock Aug 2026 first. An earlier period of AVM-US in book ASC606 is not closed."
        )
        assert outcome.errors == ()
        assert outcome.problem().status == 409
    short = pm.decide(
        PeriodState.CLOSING,
        pm.Command.REQUEST_LOCK,
        pm.Guards(comment="short", gate_results=_gates(), earlier_postable_period="Aug 2026"),
        ctx=CTX,
    )
    assert isinstance(short, pm.Refusal) and short.slug == "validation-failed"
    # Positive control: with no earlier postable period the same request is accepted.
    accepted = pm.decide(
        PeriodState.CLOSING,
        pm.Command.REQUEST_LOCK,
        pm.Guards(comment=COMMENT, gate_results=_gates(), earlier_postable_period=None),
        ctx=CTX,
    )
    assert isinstance(accepted, pm.Accepted)


def test_br_cls_08_lock_execution_rechecks_the_earlier_periods() -> None:
    """R-6: "checked at the request AND at the approval execution" — a request can outlive the
    state of an earlier period (one reopened after the request). Order at execution: the
    requester (BR-CLS-02), the step-up (BR-PLT-06), the earlier periods, the gates. The permanent
    lock keeps its own order rule and ignores this fact."""
    base = dict(comment=COMMENT, gate_results=_gates(), requester_id=PRIYA, now=NOW)
    fresh = NOW - timedelta(minutes=1)
    refused = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(
            approver_id=MARCUS, mfa_verified_at=fresh, earlier_postable_period="Aug 2026", **base
        ),
        ctx=CTX,
    )
    assert isinstance(refused, pm.Refusal)
    assert (refused.slug, refused.rule_id) == ("earlier-period-open", "BR-CLS-08")
    by_requester = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(
            approver_id=PRIYA, mfa_verified_at=fresh, earlier_postable_period="Aug 2026", **base
        ),
        ctx=CTX,
    )
    assert isinstance(by_requester, pm.Refusal) and by_requester.slug == "self-approval"
    stale = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(
            approver_id=MARCUS, mfa_verified_at=None, earlier_postable_period="Aug 2026", **base
        ),
        ctx=CTX,
    )
    assert isinstance(stale, pm.Refusal) and stale.slug == "mfa-step-up-required"
    accepted = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(approver_id=MARCUS, mfa_verified_at=fresh, **base),
        ctx=CTX,
    )
    assert isinstance(accepted, pm.Accepted)
    permanent = pm.decide(
        PeriodState.CLOSED,
        pm.Command.PERMANENT_LOCK,
        pm.Guards(
            approver_id=MARCUS, mfa_verified_at=fresh, earlier_postable_period="Aug 2026", **base
        ),
        ctx=CTX,
    )
    assert isinstance(permanent, pm.Accepted)


def test_lock_execution_checks_in_order() -> None:
    base = dict(comment=COMMENT, gate_results=_gates(), requester_id=PRIYA, now=NOW)
    # 1. the requester cannot lock (BR-CLS-02), whatever the MFA state
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(approver_id=PRIYA, mfa_verified_at=None, **base),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Refusal) and outcome.slug == "self-approval"
    # 2. a fresh TOTP within five minutes (BR-PLT-06; ERR-28)
    for verified in (None, NOW - timedelta(minutes=5, seconds=1)):
        outcome = pm.decide(
            PeriodState.CLOSING,
            pm.Command.LOCK,
            pm.Guards(approver_id=MARCUS, mfa_verified_at=verified, **base),
            ctx=CTX,
        )
        assert isinstance(outcome, pm.Refusal)
        assert (outcome.slug, outcome.detail) == (
            "mfa-step-up-required",
            "Enter a code from your authenticator app to continue.",
        )
    # 3. gates re-evaluated at execution
    failing = dict(
        base,
        gate_results=_gates(
            gates.GateResult(gates.HOLDS_REVIEWED, ChecklistStatus.FAILED, 1, "Open holds: 1", NOW)
        ),
    )
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(approver_id=MARCUS, mfa_verified_at=NOW - timedelta(minutes=5), **failing),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Refusal) and outcome.slug == "close-gates-failed"
    # 4. accepted: closing → closed with the lock effects
    outcome = pm.decide(
        PeriodState.CLOSING,
        pm.Command.LOCK,
        pm.Guards(approver_id=MARCUS, mfa_verified_at=NOW - timedelta(minutes=5), **base),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Accepted)
    assert outcome.transition == pm.Transition(
        PeriodState.CLOSING, PeriodState.CLOSED, pm.Command.LOCK
    )
    assert {
        pm.Effect.CONTROLLER_CERTIFIED,
        pm.Effect.PERIOD_LOCK_LOCK,
        pm.Effect.LOCK_SNAPSHOTS,
        pm.Effect.RECONCILIATIONS_CERTIFIED,
        pm.Effect.NEXT_PERIOD_OPEN,
        pm.Effect.NOTIFY_PERIOD_LOCKED,
    } <= set(outcome.effects)


@pytest.mark.parametrize("reason", [None, ReasonCode.CLOSE_RESTARTED, ReasonCode.DATA_CORRECTION])
def test_request_reopen_reason_subset(reason: ReasonCode | None) -> None:
    outcome = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REQUEST_REOPEN,
        pm.Guards(comment=COMMENT, reason_code=reason),
        ctx=CTX,
    )
    assert isinstance(outcome, pm.Refusal)
    assert outcome.slug == "validation-failed"
    assert (outcome.errors[0].field, outcome.errors[0].rule_id) == (
        "reason_code",
        "REASON_CODE_NOT_ALLOWED",
    )
    assert outcome.errors[0].message == pm.REOPEN_REASON_NOT_ALLOWED


def test_request_reopen_later_period_closed_err_16() -> None:
    guards = pm.Guards(
        comment=COMMENT,
        reason_code=ReasonCode.ERROR_CORRECTION,
        later_closed_period_key="FY2026-P09",
    )
    outcome = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REQUEST_REOPEN,
        guards,
        ctx=pm.Context("FY2026-P08", "AVM-US", "ASC606"),
    )
    assert isinstance(outcome, pm.Refusal)
    assert (outcome.slug, outcome.rule_id) == ("later-period-closed", "BR-CLS-05")
    assert (
        outcome.detail
        == "Reopen FY2026-P09 first. A later period of AVM-US in book ASC606 is closed."
    )
    accepted = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REQUEST_REOPEN,
        pm.Guards(comment=COMMENT, reason_code=ReasonCode.ERROR_CORRECTION),
        ctx=CTX,
    )
    assert isinstance(accepted, pm.Accepted) and pm.Effect.REQUEST_PERIOD_REOPEN in accepted.effects


def test_reopen_execution_quorum_and_requester() -> None:
    base = dict(comment=COMMENT, reason_code=ReasonCode.ERROR_CORRECTION, requester_id=PRIYA)
    # two Revenue Reviewers: pending (CTL-018)
    pending = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REOPEN,
        pm.Guards(
            approvals=(
                _approve(RR1, quorum.REVENUE_REVIEWER),
                _approve(RR2, quorum.REVENUE_REVIEWER),
            ),
            **base,
        ),
        ctx=CTX,
    )
    assert isinstance(pending, pm.Pending)
    # the requester among the approvers: self-approval
    refused = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REOPEN,
        pm.Guards(
            approvals=(_approve(PRIYA, quorum.CONTROLLER), _approve(MARCUS, quorum.CONTROLLER)),
            **base,
        ),
        ctx=CTX,
    )
    assert isinstance(refused, pm.Refusal) and refused.slug == "self-approval"
    # one Controller and one Revenue Reviewer complete it
    accepted = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REOPEN,
        pm.Guards(
            approvals=(_approve(RR1, quorum.REVENUE_REVIEWER), _approve(MARCUS, quorum.CONTROLLER)),
            **base,
        ),
        ctx=CTX,
    )
    assert isinstance(accepted, pm.Accepted)
    assert accepted.transition == pm.Transition(
        PeriodState.CLOSED, PeriodState.REOPENED, pm.Command.REOPEN
    )
    assert {
        pm.Effect.PERIOD_LOCK_REOPEN,
        pm.Effect.SNAPSHOTS_KEPT,
        pm.Effect.NOTIFY_PERIOD_REOPENED,
    } <= set(accepted.effects)


def test_request_permanent_lock_needs_every_earlier_period_locked() -> None:
    refused = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REQUEST_PERMANENT_LOCK,
        pm.Guards(comment=COMMENT, earlier_unlocked_period_key="FY2026-P07"),
        ctx=CTX,
    )
    assert isinstance(refused, pm.Refusal)
    assert (refused.slug, refused.rule_id) == ("invalid-transition", "SM-07")
    assert (
        refused.detail
        == "Permanently lock FY2026-P07 first. Every earlier period of AVM-US in book ASC606 "
        "must be permanently locked."
    )
    accepted = pm.decide(
        PeriodState.CLOSED, pm.Command.REQUEST_PERMANENT_LOCK, pm.Guards(comment=COMMENT), ctx=CTX
    )
    assert (
        isinstance(accepted, pm.Accepted) and pm.Effect.REQUEST_PERMANENT_LOCK in accepted.effects
    )


def test_permanent_lock_then_reopen_refused() -> None:
    executed = pm.decide(
        PeriodState.CLOSED,
        pm.Command.PERMANENT_LOCK,
        pm.Guards(requester_id=PRIYA, approver_id=MARCUS, mfa_verified_at=NOW, now=NOW),
        ctx=CTX,
    )
    assert isinstance(executed, pm.Accepted)
    assert executed.transition == pm.Transition(
        PeriodState.CLOSED, PeriodState.PERMANENTLY_LOCKED, pm.Command.PERMANENT_LOCK
    )
    later = pm.decide(
        PeriodState.PERMANENTLY_LOCKED,
        pm.Command.REQUEST_REOPEN,
        pm.Guards(comment=COMMENT, reason_code=ReasonCode.OTHER),
        ctx=CTX,
    )
    assert isinstance(later, pm.Refusal) and later.slug == "invalid-transition"


def test_open_requires_previous_period_not_future() -> None:
    refused = pm.decide(
        PeriodState.FUTURE, pm.Command.OPEN, pm.Guards(previous_period_future=True), ctx=CTX
    )
    assert isinstance(refused, pm.Refusal) and refused.slug == "invalid-transition"
    accepted = pm.decide(PeriodState.FUTURE, pm.Command.OPEN, pm.Guards(), ctx=CTX)
    assert isinstance(accepted, pm.Accepted)
    assert accepted.transition == pm.Transition(
        PeriodState.FUTURE, PeriodState.OPEN, pm.Command.OPEN
    )


def test_start_close_comment_and_cancel_close_reason() -> None:
    refused = pm.decide(PeriodState.OPEN, pm.Command.START_CLOSE, pm.Guards(comment=None), ctx=CTX)
    assert isinstance(refused, pm.Refusal) and refused.errors[0].field == "comment"
    accepted = pm.decide(
        PeriodState.REOPENED,
        pm.Command.START_CLOSE,
        pm.Guards(comment="September close in progress"),
        ctx=CTX,
    )
    assert isinstance(accepted, pm.Accepted)
    assert accepted.transition == pm.Transition(
        PeriodState.REOPENED, PeriodState.CLOSING, pm.Command.START_CLOSE
    )
    bad_reason = pm.decide(
        PeriodState.CLOSING,
        pm.Command.CANCEL_CLOSE,
        pm.Guards(comment=COMMENT, reason_code=ReasonCode.ERROR_CORRECTION),
        ctx=CTX,
    )
    assert isinstance(bad_reason, pm.Refusal)
    assert (bad_reason.errors[0].rule_id, bad_reason.errors[0].message) == (
        "REASON_CODE_NOT_ALLOWED",
        commands.REASON_NOT_ALLOWED,
    )
    short = pm.decide(
        PeriodState.CLOSING,
        pm.Command.CANCEL_CLOSE,
        pm.Guards(comment="short", reason_code=ReasonCode.CLOSE_RESTARTED),
        ctx=CTX,
    )
    assert isinstance(short, pm.Refusal) and short.errors[0].rule_id == "BR-PLT-08"
    ok = pm.decide(
        PeriodState.CLOSING,
        pm.Command.CANCEL_CLOSE,
        pm.Guards(comment=COMMENT, reason_code=ReasonCode.CLOSE_RESTARTED),
        ctx=CTX,
    )
    assert isinstance(ok, pm.Accepted)
    assert ok.transition == pm.Transition(
        PeriodState.CLOSING, PeriodState.OPEN, pm.Command.CANCEL_CLOSE
    )
    # SM-07 rev 1.99 (CLO-CANCEL-CLOSE-REOPENED-1): a period that has been locked before was
    # soft-closed from ``reopened`` and returns there, under the same reason and comment rules.
    back = pm.decide(
        PeriodState.CLOSING,
        pm.Command.CANCEL_CLOSE,
        pm.Guards(comment=COMMENT, reason_code=ReasonCode.CLOSE_RESTARTED, locked_before=True),
        ctx=CTX,
    )
    assert isinstance(back, pm.Accepted)
    assert back.transition == pm.Transition(
        PeriodState.CLOSING, PeriodState.REOPENED, pm.Command.CANCEL_CLOSE
    )
    assert pm.cancel_close_target(locked_before=False) is PeriodState.OPEN
    assert pm.cancel_close_target(locked_before=True) is PeriodState.REOPENED
    assert (PeriodState.CLOSING, PeriodState.REOPENED) in pm.pairs()


# --- F-CLO-R1: malformed gate populations never reach Accepted ---


def _without(results: tuple[gates.GateResult, ...], code: str) -> tuple[gates.GateResult, ...]:
    return tuple(r for r in results if r.gate_check_code != code)


def _malformed_gates() -> dict[str, tuple[gates.GateResult, ...]]:
    complete = _gates()
    return {
        "empty": (),
        "missing JE_COMPLETE": _without(complete, gates.JE_COMPLETE),
        "duplicate JE_BALANCED for JE_COMPLETE": tuple(
            gates.GateResult(gates.JE_BALANCED, ChecklistStatus.PASSED, 0, None, NOW)
            if r.gate_check_code == gates.JE_COMPLETE
            else r
            for r in complete
        ),
        "unknown extra gate": complete
        + (gates.GateResult("VC_ATTESTED", ChecklistStatus.PASSED, 0, None, NOW),),
    }


@pytest.mark.parametrize("label", list(_malformed_gates()))
def test_r1_request_lock_and_lock_refuse_malformed_gate_sets(label: str) -> None:
    results = _malformed_gates()[label]
    with pytest.raises(ValueError):
        pm.decide(
            PeriodState.CLOSING,
            pm.Command.REQUEST_LOCK,
            pm.Guards(comment=COMMENT, gate_results=results),
            ctx=CTX,
        )
    with pytest.raises(ValueError):
        pm.decide(
            PeriodState.CLOSING,
            pm.Command.LOCK,
            pm.Guards(
                comment=COMMENT,
                gate_results=results,
                requester_id=PRIYA,
                approver_id=MARCUS,
                mfa_verified_at=NOW,
                now=NOW,
            ),
            ctx=CTX,
        )


# --- F-CLO-R2: the REOPEN execution re-checks BR-CLS-05 with the current fact ---


def test_r2_reopen_execution_rechecks_later_period_closed() -> None:
    base = dict(
        comment=COMMENT,
        reason_code=ReasonCode.ERROR_CORRECTION,
        requester_id=PRIYA,
        approvals=(_approve(RR1, quorum.REVENUE_REVIEWER), _approve(MARCUS, quorum.CONTROLLER)),
    )
    ctx = pm.Context("FY2026-P08", "AVM-US", "ASC606")
    refused = pm.decide(
        PeriodState.CLOSED,
        pm.Command.REOPEN,
        pm.Guards(later_closed_period_key="FY2026-P09", **base),  # type: ignore[arg-type]
        ctx=ctx,
    )
    assert isinstance(refused, pm.Refusal)
    assert (refused.slug, refused.rule_id) == ("later-period-closed", "BR-CLS-05")
    assert (
        refused.detail
        == "Reopen FY2026-P09 first. A later period of AVM-US in book ASC606 is closed."
    )
    accepted = pm.decide(PeriodState.CLOSED, pm.Command.REOPEN, pm.Guards(**base), ctx=ctx)  # type: ignore[arg-type]
    assert isinstance(accepted, pm.Accepted)
    assert accepted.transition == pm.Transition(
        PeriodState.CLOSED, PeriodState.REOPENED, pm.Command.REOPEN
    )
