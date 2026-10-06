"""The lock's fourteenth gate as a pure rule (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and
R-116 (e); 04 T-CLS-02 rev 1.172 ``CLOSE_RUN_COMPLETED`` and §16.8 "The close-run gate"; SCREENS_B
§1.1 gate label table rev 1.50). ``gates.gate_results`` over a ``CloseSignals`` built in memory;
the database witnesses are ``tests/domain/close/test_close_run_gate.py``."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from erev_api.domain.close import certification, gates, run_inputs
from erev_api.domain.platform import sandbox_periods
from erev_api.domain.platform.provisioning import SYSTEM_CLOSE_GATES
from erev_api.enums import ChecklistStatus, CloseRunStatus, DerivedBlockerCode

AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
RUN_NO = "CLS-000007"


def _signals(run: gates.CloseRunFacts | None) -> gates.CloseSignals:
    return gates.CloseSignals(
        blockers={key: 0 for key in gates.BLOCKER_KEYS},
        derived={
            DerivedBlockerCode.JOURNAL_RUN_NOT_CALCULATED.value: 0,
            DerivedBlockerCode.RECONCILIATIONS_NOT_GENERATED.value: 0,
        },
        unbalanced_currencies=(),
        unacknowledged_batches=0,
        missing_kinds=(),
        unreviewed_kinds=(),
        close_run=run,
    )


def _gate(run: gates.CloseRunFacts | None) -> gates.GateResult:
    results = {r.gate_check_code: r for r in gates.gate_results(_signals(run), at=AT)}
    assert list(results) == list(gates.GATE_CHECK_CODES)
    return results[gates.CLOSE_RUN_COMPLETED]


def test_the_gate_is_the_thirteenth_and_the_certification_stays_last() -> None:
    """04 T-CLS-02 rev 1.172: fourteen system gates; ``CLOSE_RUN_COMPLETED`` is the thirteenth in
    provisioning's order and ``CONTROLLER_CERTIFIED`` the last line of every checklist."""
    assert len(gates.GATE_CHECK_CODES) == 14
    assert gates.GATE_CHECK_CODES[12] == "CLOSE_RUN_COMPLETED"
    assert gates.GATE_CHECK_CODES[13] == "CONTROLLER_CERTIFIED"
    assert SYSTEM_CLOSE_GATES[12] == ("CLOSE_RUN_COMPLETED", "Close run completed")
    assert certification.CANONICAL_GATES == gates.GATE_CHECK_CODES


def test_the_gate_fails_by_name_without_a_close_run() -> None:
    result = _gate(None)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        "Close run not completed",
    )
    assert result.evaluated_at == AT
    # a signal built without the fact — the pure rule's earlier callers — fails closed
    assert gates.CloseSignals.__dataclass_fields__["close_run"].default is None


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (CloseRunStatus.PENDING, "Queued"),
        (CloseRunStatus.RUNNING, "Running"),
        (CloseRunStatus.BLOCKED, "Blocked"),
        (CloseRunStatus.FAILED, "Failed"),
        (CloseRunStatus.CANCELLED, "Cancelled"),
    ],
)
def test_the_gate_names_a_latest_run_that_has_not_succeeded(
    status: CloseRunStatus, label: str
) -> None:
    """The status reads as SCREENS_B §0.4 labels E-62; a count of contracts out of date is not
    read while the run has not succeeded."""
    result = _gate(gates.CloseRunFacts(RUN_NO, status.value, out_of_date=5))
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        f"Close run {RUN_NO} is {label}",
    )


def test_the_gate_passes_on_a_succeeded_run_nothing_overtook() -> None:
    result = _gate(gates.CloseRunFacts(RUN_NO, CloseRunStatus.SUCCEEDED.value))
    assert (result.status, result.count, result.detail) == (ChecklistStatus.PASSED, 0, None)


def test_the_gate_counts_the_contracts_that_overtook_the_run() -> None:
    result = _gate(gates.CloseRunFacts(RUN_NO, CloseRunStatus.SUCCEEDED.value, out_of_date=3))
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        3,
        "Close run out of date, run it again: 3 contracts",
    )


PRICE = " A run posts nothing where the change moves nothing for this entity."


@pytest.mark.parametrize(
    ("changed", "what"),
    [
        (("exchange rates",), "exchange rates"),
        (("policies",), "policies"),
        (("exchange rates", "policies"), "exchange rates and policies"),
    ],
)
def test_the_gate_names_what_the_run_read_that_is_no_longer_in_force(
    changed: tuple[str, ...], what: str
) -> None:
    """Item CLO-RATE-AFTER-RUN-1 (04 §16.8 "The close-run gate" rev 1.291; SCREENS_B §1.1 rev
    1.100): a succeeded run that no contract overtook is out of date while what its passes read
    of the rates or the policies differs now — count 1, the remedy and the price in the gate's
    own words. The names are ``run_inputs``'s."""
    assert (run_inputs.RATES, run_inputs.POLICIES) == ("exchange rates", "policies")
    run = gates.CloseRunFacts(RUN_NO, CloseRunStatus.SUCCEEDED.value, inputs_changed=changed)
    result = _gate(run)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        f"Close run out of date, run it again: {what} changed since it ran." + PRICE,
    )


def test_contracts_that_overtook_the_run_are_named_before_what_it_read() -> None:
    """Both at once: the contracts are counted, as before the item — the run that posts their
    period ends reads the rates and the policies in force as well."""
    run = gates.CloseRunFacts(
        RUN_NO, CloseRunStatus.SUCCEEDED.value, out_of_date=2, inputs_changed=("exchange rates",)
    )
    result = _gate(run)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        2,
        "Close run out of date, run it again: 2 contracts",
    )


def test_a_run_that_has_not_succeeded_is_named_by_its_status_whatever_it_read() -> None:
    run = gates.CloseRunFacts(
        RUN_NO, CloseRunStatus.FAILED.value, inputs_changed=("exchange rates", "policies")
    )
    assert _gate(run).detail == f"Close run {RUN_NO} is Failed"
    # and a run that recorded nothing of what it read is read as before the item
    assert gates.CloseRunFacts(RUN_NO, CloseRunStatus.SUCCEEDED.value).inputs_changed == ()


def test_the_gate_is_never_waivable() -> None:
    """Supervisor ruling R-114 (b): a period end that was not posted is not a risk a signature
    accepts. A WAIVED or NOT_APPLICABLE item does not clear the gate, the lock is refused by its
    label and detail (ERR-14), and the certification cannot be made."""
    assert gates.CLOSE_RUN_COMPLETED in gates.NEVER_WAIVABLE
    for pending in (False, True):
        assert gates.waivable(gates.CLOSE_RUN_COMPLETED, remark_pending=pending) is False
    stale = _gate(gates.CloseRunFacts(RUN_NO, CloseRunStatus.SUCCEEDED.value, out_of_date=1))
    held = {
        gates.CLOSE_RUN_COMPLETED: stale,
        gates.CONTROLLER_CERTIFIED: gates.GateResult(
            gates.CONTROLLER_CERTIFIED, ChecklistStatus.FAILED, None, gates.CERTIFICATION_DETAIL, AT
        ),
    }
    for status in (ChecklistStatus.WAIVED, ChecklistStatus.NOT_APPLICABLE):
        held[gates.CLOSE_RUN_COMPLETED] = replace(stale, status=status)
        results = tuple(
            held.get(code, gates.GateResult(code, ChecklistStatus.PASSED, 0, None, AT))
            for code in gates.GATE_CHECK_CODES
        )
        assert not certification.lock_allowed(results)
        refusal = certification.refusal(results)
        assert refusal.detail == "1 close gates have not passed: Close run completed."
        assert [(e.rule_id, e.message) for e in refusal.errors] == [
            ("CLOSE_RUN_COMPLETED", "Close run out of date, run it again: 1 contracts")
        ]
        with pytest.raises(ValueError, match="gate CLOSE_RUN_COMPLETED has not passed"):
            certification.certify(results, at=AT)


def test_a_replayed_result_is_named_in_the_certification() -> None:
    """Supervisor ruling R-116 (e); 04 T-CLS-04 rev 1.172: the one result a sandbox replay takes
    from the source lock carries ``replayed`` in the certification; every other row keeps the four
    members."""
    passed = tuple(
        replace(r, status=ChecklistStatus.PASSED, count=0, detail=None)
        for r in gates.gate_results(_signals(None), at=AT)
    )
    laid = tuple(
        replace(r, replayed=True) if r.gate_check_code == gates.CLOSE_RUN_COMPLETED else r
        for r in passed
    )
    rows = {row["gate_check_code"]: row for row in certification.certification(laid)}
    assert rows["CLOSE_RUN_COMPLETED"] == {
        "gate_check_code": "CLOSE_RUN_COMPLETED",
        "status": "PASSED",
        "count": 0,
        "evaluated_at": AT.isoformat(),
        "replayed": True,
    }
    assert all(
        set(row) == {"gate_check_code", "status", "count", "evaluated_at"}
        for code, row in rows.items()
        if code != "CLOSE_RUN_COMPLETED"
    )


# --- the sandbox replay of a source lock (supervisor ruling R-116 (e); 05 SBX-04 rev 1.111) -------

SOURCE_AT = datetime(2026, 10, 1, 8, 15, tzinfo=UTC)


def _sandbox_results() -> gates.GateResults:
    """What a sandbox evaluates for a replayed lock: it has no close run of its own."""
    task = gates.BlockingTask("SALES-TAX-REVIEW", "Sales tax review", ChecklistStatus.NOT_STARTED)
    return gates.GateResults(gates.gate_results(_signals(None), at=AT), (task,))


def _source_lock(*rows: dict[str, object]) -> dict[str, object]:
    return {"id": "lock", "certification": list(rows)}


def _source_row(status: str, count: int | None) -> dict[str, object]:
    return {
        "gate_check_code": "CLOSE_RUN_COMPLETED",
        "status": status,
        "count": count,
        "evaluated_at": SOURCE_AT.isoformat(),
    }


def test_a_replayed_lock_takes_the_close_run_gate_from_the_source_lock() -> None:
    """The source lock certified the gate ``PASSED``: the replay lays that result — its status,
    count and evaluation time, marked ``replayed`` — over the sandbox's own evaluation of this
    gate alone; every other gate and the unsigned tasks stay as the sandbox found them."""
    evaluated = _sandbox_results()
    other = {"gate_check_code": "JE_BALANCED", "status": "PASSED", "count": 0}
    laid = sandbox_periods._with_source_close_run(
        evaluated, _source_lock(other, _source_row("PASSED", 0)), passed_only=True
    )
    assert isinstance(laid, gates.GateResults)
    assert laid.blocking_tasks == evaluated.blocking_tasks
    by_code = {result.gate_check_code: result for result in laid}
    assert list(by_code) == list(gates.GATE_CHECK_CODES)
    assert by_code[gates.CLOSE_RUN_COMPLETED] == gates.GateResult(
        gates.CLOSE_RUN_COMPLETED, ChecklistStatus.PASSED, 0, None, SOURCE_AT, replayed=True
    )
    assert [r for r in laid if r.gate_check_code != gates.CLOSE_RUN_COMPLETED] == [
        r for r in evaluated if r.gate_check_code != gates.CLOSE_RUN_COMPLETED
    ]


def test_a_source_lock_without_the_result_leaves_the_sandboxs_own_evaluation() -> None:
    """A source lock decided before the gate existed certified no such result: the sandbox's own
    evaluation stands, and it refuses the lock by name ("Close run not completed")."""
    evaluated = _sandbox_results()
    for lock in (_source_lock(), {"id": "lock", "certification": None}, {"id": "lock"}):
        assert (
            sandbox_periods._with_source_close_run(evaluated, lock, passed_only=True) is evaluated
        )
    (own,) = [r for r in evaluated if r.gate_check_code == gates.CLOSE_RUN_COMPLETED]
    assert (own.status, own.detail, own.replayed) == (
        ChecklistStatus.FAILED,
        "Close run not completed",
        False,
    )


def test_a_judged_lock_lays_a_passed_result_only() -> None:
    """A ``LOCK`` judges its gates, so only a ``PASSED`` source result is laid; a permanent lock
    records the gates without judging them and takes the source's result as it is."""
    evaluated = _sandbox_results()
    failed = _source_lock(_source_row("FAILED", 2))
    assert sandbox_periods._with_source_close_run(evaluated, failed, passed_only=True) is evaluated
    recorded = sandbox_periods._with_source_close_run(evaluated, failed, passed_only=False)
    (laid,) = [r for r in recorded if r.gate_check_code == gates.CLOSE_RUN_COMPLETED]
    assert (laid.status, laid.count, laid.detail, laid.evaluated_at, laid.replayed) == (
        ChecklistStatus.FAILED,
        2,
        None,
        SOURCE_AT,
        True,
    )
