"""CLO-6 lock gate outcomes as pure functions: ERR-14 refusal, certification at lock and the
T-CLS-04 `certification` document (BR-CLS-01; BS4-D-08; SCREENS_B §1.1 gate labels). F-CLO
preparation: `docs/reviews/loop/prod/F-CLO-prep.md` §3, §5."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.close import certification as cert
from erev_api.domain.close import gates
from erev_api.domain.platform.provisioning import SYSTEM_CLOSE_GATES
from erev_api.enums import ChecklistStatus
from erev_api.problems import Problem

AT = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
LATER = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


def _passed(code: str) -> gates.GateResult:
    return gates.GateResult(code, ChecklistStatus.PASSED, 0, None, AT)


def _failed(code: str, count: int | None, detail: str) -> gates.GateResult:
    return gates.GateResult(code, ChecklistStatus.FAILED, count, detail, AT)


def _all_passed_but_certification() -> tuple[gates.GateResult, ...]:
    results = [
        _passed(code) for code in gates.GATE_CHECK_CODES if code != gates.CONTROLLER_CERTIFIED
    ]
    results.append(_failed(gates.CONTROLLER_CERTIFIED, None, gates.CERTIFICATION_DETAIL))
    return tuple(results)


def _with(
    results: tuple[gates.GateResult, ...], *replacements: gates.GateResult
) -> tuple[gates.GateResult, ...]:
    by_code = {r.gate_check_code: r for r in replacements}
    return tuple(by_code.get(r.gate_check_code, r) for r in results)


def test_gate_labels_match_provisioning() -> None:
    assert cert.GATE_LABELS == dict(SYSTEM_CLOSE_GATES)
    assert tuple(cert.GATE_LABELS) == gates.GATE_CHECK_CODES


def test_failing_excludes_controller_certification_at_request() -> None:
    results = _all_passed_but_certification()
    assert cert.failing(results, at_request=True) == ()
    assert [r.gate_check_code for r in cert.failing(results, at_request=False)] == [
        gates.CONTROLLER_CERTIFIED
    ]
    assert cert.lock_allowed(results)


def test_refusal_err_14_detail_and_errors() -> None:
    results = _with(
        _all_passed_but_certification(),
        _failed(
            gates.RECONCILIATIONS_GENERATED,
            2,
            "Reconciliation not generated: Billing to subledger; "
            "Reconciliation not generated: Subledger to GL",
        ),
        _failed(gates.APPROVALS_CLEARED, 3, "Pending approvals: 3"),
    )
    refusal = cert.refusal(results)
    assert refusal.slug == "close-gates-failed"
    assert refusal.detail == (
        "2 close gates have not passed: No pending approvals, "
        "Reconciliations generated and reviewed."
    )
    # T-CLS-02 order, rule_id = gate check code, message = the gate detail (BS4-D-08).
    assert [(e.rule_id, e.message) for e in refusal.errors] == [
        ("APPROVALS_CLEARED", "Pending approvals: 3"),
        (
            "RECONCILIATIONS_GENERATED",
            "Reconciliation not generated: Billing to subledger; "
            "Reconciliation not generated: Subledger to GL",
        ),
    ]
    problem = refusal.problem()
    assert isinstance(problem, Problem)
    assert (problem.slug, problem.status) == ("close-gates-failed", 409)
    assert problem.detail is not None and problem.detail.startswith(
        "2 close gates have not passed:"
    )
    assert not cert.lock_allowed(results)


def test_refusal_uses_label_when_gate_has_no_detail() -> None:
    results = _with(
        _all_passed_but_certification(),
        gates.GateResult(gates.JE_COMPLETE, ChecklistStatus.FAILED, None, None, AT),
    )
    refusal = cert.refusal(results)
    assert refusal.detail == "1 close gates have not passed: Journals complete."
    assert refusal.errors[0].message == "Journals complete"


def test_refusal_requires_a_failing_gate() -> None:
    with pytest.raises(ValueError):
        cert.refusal(_all_passed_but_certification())


def test_certify_marks_controller_certified_only() -> None:
    results = _all_passed_but_certification()
    certified = cert.certify(results, at=LATER)
    assert len(certified) == 14  # 04 T-CLS-02 rev 1.172: CLOSE_RUN_COMPLETED (ruling R-114 (b))
    assert [r.gate_check_code for r in certified] == list(gates.GATE_CHECK_CODES)
    last = certified[-1]
    assert (last.gate_check_code, last.status, last.count, last.detail, last.evaluated_at) == (
        gates.CONTROLLER_CERTIFIED,
        ChecklistStatus.PASSED,
        0,
        None,
        LATER,
    )
    assert certified[:-1] == results[:-1]
    assert all(r.status is ChecklistStatus.PASSED for r in certified)


def test_certify_refuses_while_a_gate_fails() -> None:
    results = _with(
        _all_passed_but_certification(), _failed(gates.HOLDS_REVIEWED, 1, "Open holds: 1")
    )
    with pytest.raises(ValueError, match="HOLDS_REVIEWED"):
        cert.certify(results, at=LATER)


def test_certification_document_shape_and_order() -> None:
    document = cert.certification(cert.certify(_all_passed_but_certification(), at=LATER))
    assert [row["gate_check_code"] for row in document] == list(gates.GATE_CHECK_CODES)
    assert all(
        set(row) == {"gate_check_code", "status", "count", "evaluated_at"} for row in document
    )
    assert document[0] == {
        "gate_check_code": "INTERFACES_COMPLETE",
        "status": "PASSED",
        "count": 0,
        "evaluated_at": AT.isoformat(),
    }
    assert document[-1]["evaluated_at"] == LATER.isoformat()


def test_certification_requires_all_fourteen_gates() -> None:
    with pytest.raises(ValueError):
        cert.certification(_all_passed_but_certification()[:-1])
    duplicated = _all_passed_but_certification()[:-1] + (_passed(gates.JE_BALANCED),)
    with pytest.raises(ValueError):
        cert.certification(duplicated)


# --- F-CLO-R1: one canonical-gates validator before every lock / certify decision ---


def _without(results: tuple[gates.GateResult, ...], code: str) -> tuple[gates.GateResult, ...]:
    return tuple(r for r in results if r.gate_check_code != code)


def _malformed() -> dict[str, tuple[gates.GateResult, ...]]:
    complete = _all_passed_but_certification()
    return {
        "empty": (),
        "missing JE_COMPLETE": _without(complete, gates.JE_COMPLETE),
        "duplicate JE_BALANCED for JE_COMPLETE": tuple(
            _passed(gates.JE_BALANCED) if r.gate_check_code == gates.JE_COMPLETE else r
            for r in complete
        ),
        "unknown extra gate": complete + (_passed("VC_ATTESTED"),),
    }


def test_canonical_gates_equal_provisioning_and_gate_module() -> None:
    assert cert.CANONICAL_GATES == tuple(code for code, _ in SYSTEM_CLOSE_GATES)
    assert cert.CANONICAL_GATES == gates.GATE_CHECK_CODES
    ordered = cert.canonical(tuple(reversed(_all_passed_but_certification())))
    assert [r.gate_check_code for r in ordered] == list(gates.GATE_CHECK_CODES)


@pytest.mark.parametrize("label", list(_malformed()))
def test_r1_malformed_gate_population_never_allows_a_lock(label: str) -> None:
    results = _malformed()[label]
    with pytest.raises(ValueError, match="fourteen"):
        cert.canonical(results)
    with pytest.raises(ValueError):
        cert.lock_allowed(results)
    with pytest.raises(ValueError):
        cert.certify(results, at=LATER)
    with pytest.raises(ValueError):
        cert.failing(results, at_request=True)
    with pytest.raises(ValueError):
        cert.refusal(results)
    with pytest.raises(ValueError):
        cert.certification(results)


def test_r1_complete_population_still_decides() -> None:
    complete = _all_passed_but_certification()
    assert cert.lock_allowed(complete)
    failed = _with(complete, _failed(gates.HOLDS_REVIEWED, 1, "Open holds: 1"))
    assert not cert.lock_allowed(failed)
    assert cert.refusal(failed).errors[0].rule_id == gates.HOLDS_REVIEWED


# --- SC-N4 (supervisor rulings R-54 (h), R-55; D-88 L7-2-Q-16; 04 §16.8 rev 1.106) ---------------

WAIVER = UUID("00000000-0000-4000-8000-0000000000f1")


def _waived(code: str, count: int, detail: str, *, waived_count: int) -> gates.GateResult:
    """A gate that still computes ``count`` and whose checklist item an approved waiver waived
    when it held ``waived_count`` (``gates.with_final_items``)."""
    return replace(
        _failed(code, count, detail),
        status=ChecklistStatus.WAIVED,
        waiver_approval_request_id=WAIVER,
        waived_count=waived_count,
    )


def test_r_55_b_an_approved_waiver_clears_its_gate() -> None:
    """A WAIVED gate no longer fails the lock request or the lock decision, and the certification
    records it with its request, the count at the decision and the count when it was waived."""
    results = _with(
        _all_passed_but_certification(),
        _waived(gates.EXCEPTIONS_CLEARED, 3, "Open exceptions: 3", waived_count=2),
    )
    assert cert.failing(results, at_request=True) == ()
    assert cert.lock_allowed(results)
    certified = cert.certify(results, at=LATER)
    rows = {row["gate_check_code"]: row for row in cert.certification(certified)}
    assert rows[gates.EXCEPTIONS_CLEARED] == {
        "gate_check_code": "EXCEPTIONS_CLEARED",
        "status": "WAIVED",
        "count": 3,
        "evaluated_at": AT.isoformat(),
        "waiver_approval_request_id": str(WAIVER),
        "waived_count": 2,
    }
    # Every other row keeps the four documented members.
    assert set(rows[gates.APPROVALS_CLEARED]) == {
        "gate_check_code",
        "status",
        "count",
        "evaluated_at",
    }
    assert rows[gates.CONTROLLER_CERTIFIED]["status"] == "PASSED"
    # NOT_APPLICABLE clears a gate the same way (D-88 L7-2-Q-16).
    skipped = _with(
        _all_passed_but_certification(),
        replace(
            _failed(gates.HOLDS_REVIEWED, 1, "Open holds: 1"), status=ChecklistStatus.NOT_APPLICABLE
        ),
    )
    assert cert.lock_allowed(skipped)


@pytest.mark.parametrize(
    "code",
    [
        gates.JE_BALANCED,
        gates.JE_COMPLETE,
        gates.CLOSE_RUN_COMPLETED,
        gates.CONTROLLER_CERTIFIED,
    ],
)
def test_r_55_c_a_never_waivable_gate_is_cleared_by_passed_only(code: str) -> None:
    """Whatever a checklist item says, journal balancing, journal completeness, the close run
    (supervisor ruling R-114 (b)) and the certification hold the lock until they pass: a WAIVED or
    NOT_APPLICABLE status on them is no clearance (the waive command refuses them; this is the
    rule's own guard)."""
    assert gates.NEVER_WAIVABLE == {
        gates.JE_BALANCED,
        gates.JE_COMPLETE,
        gates.CLOSE_RUN_COMPLETED,
        gates.CONTROLLER_CERTIFIED,
    }
    for status in (ChecklistStatus.WAIVED, ChecklistStatus.NOT_APPLICABLE):
        results = _with(
            _all_passed_but_certification(),
            replace(_failed(code, 1, "held"), status=status, waiver_approval_request_id=WAIVER),
        )
        assert [r.gate_check_code for r in cert.failing(results, at_request=False)] == sorted(
            {code, gates.CONTROLLER_CERTIFIED}, key=gates.GATE_CHECK_CODES.index
        )
        if code != gates.CONTROLLER_CERTIFIED:
            assert not cert.lock_allowed(results)
            with pytest.raises(ValueError, match=f"gate {code} has not passed"):
                cert.certify(results, at=LATER)


def test_r_55_a_an_unsigned_blocking_task_refuses_the_lock() -> None:
    """PRD BR-CLS-01 "custom close tasks signed": the tasks ``gates.evaluate_gates`` found beside
    the results hold the lock with every gate passed; the ERR-14 refusal names each with its
    template code as ``rule_id`` and counts them in its number."""
    passed = _all_passed_but_certification()
    task = gates.BlockingTask("SALES-TAX-REVIEW", "Sales tax review", ChecklistStatus.NOT_STARTED)
    held = gates.GateResults(passed, [task])
    assert cert.blocking_tasks(passed) == () and cert.blocking_tasks(held) == (task,)
    assert cert.lock_allowed(passed) and not cert.lock_allowed(held)
    refusal = cert.refusal(held)
    assert refusal.slug == "close-gates-failed"
    assert refusal.detail == "1 close gates have not passed: Sales tax review."
    assert [(error.rule_id, error.message) for error in refusal.errors] == [
        ("SALES-TAX-REVIEW", "Close task not signed: Sales tax review")
    ]
    with pytest.raises(ValueError, match="close task SALES-TAX-REVIEW is not signed"):
        cert.certify(held, at=LATER)
    # Beside a failing gate: the gates first, then the tasks; both counted.
    mixed = gates.GateResults(
        _with(passed, _failed(gates.APPROVALS_CLEARED, 3, "Pending approvals: 3")), [task]
    )
    both = cert.refusal(mixed)
    assert both.detail == "2 close gates have not passed: No pending approvals, Sales tax review."
    assert [error.rule_id for error in both.errors] == ["APPROVALS_CLEARED", "SALES-TAX-REVIEW"]
    # The results are still the canonical population: the tasks ride beside them.
    assert tuple(held) == passed and len(cert.certification(cert.certify(passed, at=LATER))) == len(
        gates.GATE_CHECK_CODES
    )
