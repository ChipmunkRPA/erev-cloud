"""The DATA_QUALITY_CLEAR gate reads the real signal (BUILD_SPEC CLO-5: ``gates.py`` "real signal";
SCREENS_B §1.1 :368; REQ-CLS-019 "error results block lock"). Pure: ``gates.gate_results`` over a
``CloseSignals`` built in memory. Fail-first on main ``4141f322``: ``CloseSignals`` has no
``data_quality_blocking`` field and the gate is ``FAILED`` / "not evaluated"."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from erev_api.domain.close import gates
from erev_api.enums import ChecklistStatus, DerivedBlockerCode

AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


def _signals(blocking: int) -> gates.CloseSignals:
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
        data_quality_blocking=blocking,
    )


def _gate(blocking: int) -> gates.GateResult:
    results = {r.gate_check_code: r for r in gates.gate_results(_signals(blocking), at=AT)}
    assert list(results) == list(gates.GATE_CHECK_CODES)
    return results[gates.DATA_QUALITY_CLEAR]


def test_data_quality_clear_passes_without_open_blocking_items() -> None:
    result = _gate(0)
    assert (result.status, result.count, result.detail) == (ChecklistStatus.PASSED, 0, None)
    assert result.evaluated_at == AT


def test_data_quality_clear_fails_with_the_open_blocking_count() -> None:
    result = _gate(3)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        3,
        "Data-quality errors: 3",
    )


def test_data_quality_gate_helper_is_the_gate_module_s() -> None:
    from erev_api.domain.close import monitor_rules

    assert monitor_rules.data_quality_gate(2, at=AT) == gates.data_quality_gate(2, at=AT)
    assert gates.DATA_QUALITY_DETAIL == "Data-quality errors: {n}"
    with pytest.raises(ValueError):
        gates.data_quality_gate(-1, at=AT)


def test_placeholder_wording_is_gone_for_data_quality() -> None:
    result = _gate(0)
    assert result.detail != gates.NOT_EVALUATED


def _interface_gate(failures: int, *names: str) -> gates.GateResult:
    from dataclasses import replace

    base = _signals(0)
    facts = replace(
        base,
        blockers={**base.blockers, "interface_failures": failures},
        failing_interfaces=names,
    )
    results = {r.gate_check_code: r for r in gates.gate_results(facts, at=AT)}
    return results[gates.INTERFACES_COMPLETE]


def test_interface_gate_names_the_failing_connections() -> None:
    """CLO-GATE-SYNC-1 (supervisor ruling R-45 (d)): SCREENS_B §1.1 "Interface batch not complete:
    <connection name> (<n> runs)" names the connections whose runs hold the gate — sync
    connections by name, then "File imports" — with the total of their runs."""
    passed = _interface_gate(0)
    assert (passed.status, passed.count, passed.detail) == (ChecklistStatus.PASSED, 0, None)
    one = _interface_gate(1, "Salesforce (orders)")
    assert (one.status, one.count) == (ChecklistStatus.FAILED, 1)
    assert one.detail == "Interface batch not complete: Salesforce (orders) (1 runs)"
    mixed = _interface_gate(3, "Salesforce (orders)", gates.IMPORT_CONNECTION)
    assert mixed.detail == (
        "Interface batch not complete: Salesforce (orders), File imports (3 runs)"
    )
    # Signals built without the names (the pure rule's earlier callers) keep the import label.
    assert _interface_gate(2).detail == "Interface batch not complete: File imports (2 runs)"
    assert gates.FAILED_SYNC_STATUSES == ("FAILED", "CONTROL_TOTAL_MISMATCH")
    # R-56 (a): which run kinds a later run of the kind can clear, and how.
    assert gates.PROBE_KIND == "TEST_CONNECTION"
    assert gates.CHECKPOINT_KINDS == ("INBOUND_POLL",)
    assert gates.WHOLE_SET_KINDS == ("RECONCILIATION_SWEEP", "COA_SYNC")


# --- NO_DIRTY_GROUPS and the re-marking of a period a lock opened (supervisor ruling R-106 (a)) ---


def _dirty_gate(*, dirty: int, remark_pending: bool) -> gates.GateResult:
    facts = _signals(0)
    signals = gates.CloseSignals(
        blockers={**facts.blockers, "groups_dirty": dirty},
        derived=facts.derived,
        unbalanced_currencies=(),
        unacknowledged_batches=0,
        missing_kinds=(),
        unreviewed_kinds=(),
        remark_pending=remark_pending,
    )
    results = {r.gate_check_code: r for r in gates.gate_results(signals, at=AT)}
    assert list(results) == list(gates.GATE_CHECK_CODES)
    return results[gates.NO_DIRTY_GROUPS]


@pytest.mark.parametrize("dirty", [0, 2])
def test_no_dirty_groups_fails_by_name_while_the_re_marking_has_not_succeeded(dirty: int) -> None:
    """R-106 (a): while the re-marking job of a period a lock opened has not succeeded the gate
    fails with no count — the number of dirty groups proves nothing before the marking — whatever
    the count of dirty groups is. Fail-first: ``CloseSignals`` had no ``remark_pending`` and the
    gate passed on a count of 0."""
    result = _dirty_gate(dirty=dirty, remark_pending=True)
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        None,
        "Contracts not re-marked since the period was opened",
    )
    assert result.detail == gates.REMARK_PENDING_DETAIL


def test_no_dirty_groups_counts_the_dirty_groups_otherwise() -> None:
    passed = _dirty_gate(dirty=0, remark_pending=False)
    assert (passed.status, passed.count, passed.detail) == (ChecklistStatus.PASSED, 0, None)
    failed = _dirty_gate(dirty=2, remark_pending=False)
    assert (failed.status, failed.count, failed.detail) == (
        ChecklistStatus.FAILED,
        2,
        "Contracts changed since the last close run: 2",
    )
    assert gates.CloseSignals.__dataclass_fields__["remark_pending"].default is False


def test_the_gate_is_not_waivable_while_it_fails_for_the_re_marking() -> None:
    """R-55 (c), R-106 (a), R-112 (j): the three gates no waiver clears stay so; ``NO_DIRTY_GROUPS``
    joins them only while the period's re-marking has not succeeded; a tenant task (no gate check
    code) and every other gate are waivable either way."""
    for pending in (False, True):
        for code in sorted(gates.NEVER_WAIVABLE):
            assert gates.waivable(code, remark_pending=pending) is False
        assert gates.waivable(None, remark_pending=pending) is True
        assert gates.waivable(gates.DATA_QUALITY_CLEAR, remark_pending=pending) is True
    assert gates.waivable(gates.NO_DIRTY_GROUPS, remark_pending=False) is True
    assert gates.waivable(gates.NO_DIRTY_GROUPS, remark_pending=True) is False
