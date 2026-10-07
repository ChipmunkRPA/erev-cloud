"""A waiver covers the count it was approved for, without a database (item
CLO-WAIVER-COVERS-LATER-1; the supervisor's ruling of 2026-10-02 17:32; 04 T-CLS-03 rev 1.305):
``gates.outgrown`` as a rule, what the evaluation stores, what is laid over a result that is
not stored, the two DB-03 pairs and what a waiver's request hashes. The database witnesses are
``tests/domain/close/test_waiver_covers_count.py``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.db import transitions
from erev_api.domain.close import gates
from erev_api.enums import ChecklistStatus

AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
CODE = gates.EXCEPTIONS_CLEARED


def _computed(count: int) -> gates.GateResult:
    status = ChecklistStatus.FAILED if count else ChecklistStatus.PASSED
    return gates.GateResult(
        CODE,
        status,
        count,
        f"Open exceptions: {count}" if count else None,
        AT,
        members=tuple(str(i) for i in range(count)),
    )


def _row(status: str, stored: dict[str, Any] | None, request_no: str | None = "APR-000002") -> Any:
    return {
        "status": status,
        "result": stored,
        "gate_check_code": CODE,
        gates.WAIVER_REQUEST_NO: request_no,
    }


def test_a_waived_gate_that_counts_more_fails_with_the_sentence() -> None:
    """Count above the waived one: FAILED, the gate's own sentence and then the waiver's number
    and count, which the stored result keeps for every later evaluation."""
    waived = _row("WAIVED", {"count": 2, "detail": "Open exceptions: 2", "members": ["0", "1"]})
    found = gates.outgrown(waived, _computed(4))
    assert (found.status, found.count) == (ChecklistStatus.FAILED, 4)
    assert found.detail == "Open exceptions: 4 The waiver APR-000002 covered 2."
    assert found.waiver_outgrown == {"request_no": "APR-000002", "count": 2}
    assert found.result()[gates.OUTGROWN] == {"request_no": "APR-000002", "count": 2}
    assert gates._to_store(waived, {CODE: _computed(4)}) == found


def test_a_count_the_waiver_covers_leaves_the_item_waived() -> None:
    """A subset of the approved identities remains covered; a legacy waiver fails closed."""
    waived = _row("WAIVED", {"count": 2, "detail": "Open exceptions: 2", "members": ["0", "1"]})
    for count in (2, 1, 0):
        assert gates.outgrown(waived, _computed(count)) == _computed(count)
        assert gates._to_store(waived, {CODE: _computed(count)}) is None
    uncounted = _row("WAIVED", None)
    assert gates.outgrown(uncounted, _computed(4)).waiver_outgrown is not None
    assert gates._to_store(uncounted, {CODE: _computed(4)}) is not None
    assert gates.GateResult(CODE, ChecklistStatus.FAILED, 4, "d", AT).result().keys() == {
        "count",
        "detail",
        "evaluated_at",
    }


def test_a_failing_item_that_remembers_a_spent_waiver_states_it_until_the_gate_passes() -> None:
    """After the move the item is FAILED and names no request: the stored result carries the
    waiver, so the next evaluation states the same sentence and stores nothing new; a count that
    changes is stored with it — also a count that falls back to what the waiver covered: a spent
    waiver does not cover again, a new one is asked for; a gate that passes is stored plain."""
    spent = {"request_no": "APR-000002", "count": 2}
    detail = "Open exceptions: 4 The waiver APR-000002 covered 2."
    failed = _row(
        "FAILED",
        {"count": 4, "detail": detail, "members": ["0", "1", "2", "3"], gates.OUTGROWN: spent},
        request_no=None,
    )
    assert gates._to_store(failed, {CODE: _computed(4)}) is None
    grown = gates._to_store(failed, {CODE: _computed(5)})
    assert grown is not None and grown.waiver_outgrown == spent
    assert grown.detail == "Open exceptions: 5 The waiver APR-000002 covered 2."
    fallen = gates._to_store(failed, {CODE: _computed(2)})
    assert fallen is not None and fallen.status is ChecklistStatus.FAILED
    assert (fallen.count, fallen.waiver_outgrown) == (2, spent)
    assert fallen.detail == "Open exceptions: 2 The waiver APR-000002 covered 2."
    passed = gates._to_store(failed, {CODE: _computed(0)})
    assert passed is not None and passed.status is ChecklistStatus.PASSED
    assert passed.waiver_outgrown is None and gates.OUTGROWN not in passed.result()


def test_the_final_items_lay_a_failing_result_over_a_waiver_the_gate_outgrew(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``with_final_items`` reads the items as they are stored. Where the evaluation has stored
    nothing — a period that is not evaluated — a ``WAIVED`` item whose gate counts more is still
    laid ``FAILED`` with the sentence and neither the request nor a waived count; at or below
    the waived count it is laid ``WAIVED`` with both, as before."""
    monkeypatch.setattr(gates, "remark_pending", lambda session, scope: False)
    request = UUID(int=7)
    waived = {
        **_row("WAIVED", {"count": 2, "detail": "Open exceptions: 2", "members": ["0", "1"]}),
        "waiver_approval_request_id": request,
    }
    session = SimpleNamespace(execute=lambda statement: SimpleNamespace(mappings=lambda: [waived]))
    scope = SimpleNamespace(entity_id=UUID(int=1), book_code="ASC606", period_id=UUID(int=2))
    (more,) = gates.with_final_items(session, scope, [_computed(4)])  # type: ignore[arg-type]
    assert (more.status, more.count) == (ChecklistStatus.FAILED, 4)
    assert more.detail == "Open exceptions: 4 The waiver APR-000002 covered 2."
    assert (more.waiver_approval_request_id, more.waived_count) == (None, None)
    for count in (2, 1):
        (laid,) = gates.with_final_items(session, scope, [_computed(count)])  # type: ignore[arg-type]
        assert (laid.status, laid.count) == (ChecklistStatus.WAIVED, count)
        assert (laid.waiver_approval_request_id, laid.waived_count) == (request, 2)


def test_two_pairs_lead_out_of_waived_and_none_out_of_not_applicable() -> None:
    pairs = transitions.TRANSITIONS["close_checklist_item"].pairs
    assert {after for before, after in pairs if before == "WAIVED"} == {"FAILED", "NOT_STARTED"}
    assert not [pair for pair in pairs if pair[0] == "NOT_APPLICABLE"]


def test_a_not_applicable_item_is_never_stored_over() -> None:
    """``NOT_APPLICABLE`` stays final whatever its stored result remembers: no pair leads out of
    it, so an evaluation that stored a failing result over it would be refused by the database."""
    spent = {"request_no": "APR-000002", "count": 2}
    final = _row(
        "NOT_APPLICABLE", {"count": 4, "detail": "d", gates.OUTGROWN: spent}, request_no=None
    )
    for count in (5, 4, 0):
        assert gates._to_store(final, {CODE: _computed(count)}) is None


def test_a_gate_waivers_request_hashes_the_count_and_the_sentence(monkeypatch: Any) -> None:
    """``exception_waiver_content`` of a checklist item: the stored count and detail are part of
    what the approver decides on, so a count that moves makes the request stale; a manual task,
    which stores no result, hashes neither."""
    item = {
        "code": "GATE-EXCEPTIONS",
        "gate_kind": "AUTOMATIC",
        "gate_check_code": CODE,
        "entity_id": UUID(int=1),
        "book_code": "ASC606",
        "period_id": UUID(int=2),
        "status": "FAILED",
        "result": {"count": 1, "detail": "Open exceptions: 1", "evaluated_at": AT.isoformat()},
    }
    read = {"row": item}
    monkeypatch.setattr(subjects, "checklist_waiver_row", lambda session, item_id: read["row"])
    one = subjects.exception_waiver_content(None, UUID(int=9))  # type: ignore[arg-type]
    assert (one["count"], one["detail"], one["open"]) == (1, "Open exceptions: 1", True)
    read["row"] = {**item, "result": {**item["result"], "count": 2, "detail": "Open exceptions: 2"}}
    two = subjects.exception_waiver_content(None, UUID(int=9))  # type: ignore[arg-type]
    assert {key for key in one if one[key] != two[key]} == {"count", "detail"}
    read["row"] = {**item, "gate_kind": "MANUAL", "gate_check_code": None, "result": None}
    task = subjects.exception_waiver_content(None, UUID(int=9))  # type: ignore[arg-type]
    assert (task["count"], task["detail"]) == (None, None)


@pytest.mark.parametrize("code", sorted(set(gates.GATE_CHECK_CODES) - gates.NEVER_WAIVABLE))
def test_every_waivable_gate_refuses_new_members_even_below_its_approved_count(code: str) -> None:
    row = {**_row("WAIVED", {"count": 2, "members": ["a", "b"]}), "gate_check_code": code}
    current = replace(_computed(1), gate_check_code=code, members=("new",))
    refused = gates.outgrown(row, current)
    assert refused.status is ChecklistStatus.FAILED
    assert refused.waiver_outgrown is not None
    assert gates._to_store(row, {code: current}) == refused
    old = replace(current, members=("a",))
    assert gates.outgrown(row, old).waiver_outgrown is None
    assert gates._to_store(row, {code: old}) is None


def test_legacy_count_only_waiver_cannot_cover_live_blockers() -> None:
    row = _row("WAIVED", {"count": 99, "detail": "Previously approved"})
    assert gates.outgrown(row, _computed(1)).waiver_outgrown is not None
    assert gates.outgrown(row, _computed(0)).waiver_outgrown is None


def test_changed_member_id_alone_changes_approval_basis(monkeypatch: Any) -> None:
    item = {
        "code": "GATE-EXCEPTIONS",
        "gate_kind": "AUTOMATIC",
        "gate_check_code": CODE,
        "entity_id": UUID(int=1),
        "book_code": "ASC606",
        "period_id": UUID(int=2),
        "status": "FAILED",
        "result": {"count": 1, "detail": "Open exceptions: 1", "members": ["old"]},
    }
    monkeypatch.setattr(subjects, "checklist_waiver_row", lambda session, item_id: item)
    before = subjects.exception_waiver_content(None, UUID(int=9))  # type: ignore[arg-type]
    item["result"]["members"] = ["new"]
    after = subjects.exception_waiver_content(None, UUID(int=9))  # type: ignore[arg-type]
    assert {key for key in before if before[key] != after[key]} == {"members"}
