"""``problems.is_lock_conflict`` (item COMPUTE-BEHIND-GROUP-1; the supervisor's ruling of
2026-10-02; 04 §14.1 "A computation behind its group" and §15.2 ``lock-conflict``, rev 1.298): one
predicate, by name, for every form of the 409 that says "nothing was saved; send it again" — the
retry table of the jobs reads it (05 RCP-20)."""

from __future__ import annotations

from erev_api import problems
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem, ProblemError


def test_every_form_of_the_lock_conflict_is_one_by_the_predicate() -> None:
    forms = [
        # PRD ERR-52: a deadlock, a serialization failure — and a computation behind its group,
        # which answers with the same sentence and no rule
        Problem("lock-conflict", LOCK_CONFLICT_DETAIL),
        # a lock wait beyond the platform's timeout
        Problem(
            "lock-conflict",
            problems.LOCK_TIMEOUT_DETAIL,
            errors=[
                ProblemError(
                    rule_id=problems.RULE_LOCK_TIMEOUT, message=problems.LOCK_TIMEOUT_DETAIL
                )
            ],
        ),
        # PRD ERR-72, in the command's form and in the decision's
        problems.period_state_moved(),
        problems.period_state_moved(deciding=True),
    ]
    assert [problems.is_lock_conflict(form) for form in forms] == [True, True, True, True]
    assert [form.slug for form in forms] == ["lock-conflict"] * 4


def test_no_other_refusal_is_a_lock_conflict() -> None:
    others = [
        Problem("not-found"),
        Problem("invalid-transition", "The period is not open."),
        Problem("stale-approval", "The request changed."),
        Problem("precondition-failed", "The record changed."),
    ]
    assert [problems.is_lock_conflict(other) for other in others] == [False] * 4
