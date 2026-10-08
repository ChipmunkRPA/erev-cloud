"""Saved certification is evidence only with a complete, cleared historical gate set."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from erev_api.domain.close import certification, gates
from erev_api.domain.reports.evidence_certification import (
    SavedGate,
    checked_waiver_basis,
    verified_gates,
)
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex

NOW = datetime(2026, 10, 8, tzinfo=UTC)
ROWS = [
    {"gate_check_code": code, "status": "PASSED", "count": 0, "evaluated_at": NOW.isoformat()}
    for code in certification.CANONICAL_GATES
]
WAIVABLE = next(code for code in certification.CANONICAL_GATES if code not in gates.NEVER_WAIVABLE)


def test_canonical_order_and_replay_marker_are_preserved() -> None:
    rows = deepcopy(ROWS)
    rows[0]["replayed"] = True
    result = verified_gates(list(reversed(rows)), locked_at=NOW)
    assert [row.gate_check_code for row in result] == list(certification.CANONICAL_GATES)
    assert result[0].replayed is True


@pytest.mark.parametrize("value", [None, {}, [], ROWS[:-1], ROWS + [ROWS[0]]])
def test_missing_or_duplicated_population_is_refused(value: object) -> None:
    with pytest.raises(Problem):
        verified_gates(value, locked_at=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"gate_check_code": "UNKNOWN"},
        {"status": "FAILED"},
        {"status": "NOT_STARTED"},
        {"count": -1},
        {"count": True},
        {"count": "0"},
        {"evaluated_at": (NOW + timedelta(seconds=1)).isoformat()},
        {"evaluated_at": "2026-10-08T00:00:00"},
        {"waiver_approval_request_id": str(uuid4())},
        {"waived_count": 0},
        {"replayed": "false"},
    ],
)
def test_invalid_gate_is_refused(changes: dict[str, object]) -> None:
    rows = deepcopy(ROWS)
    rows[0].update(changes)
    with pytest.raises(Problem):
        verified_gates(rows, locked_at=NOW)


@pytest.mark.parametrize("code", sorted(gates.NEVER_WAIVABLE))
@pytest.mark.parametrize("status", ["WAIVED", "NOT_APPLICABLE"])
def test_mandatory_gates_cannot_be_waived_or_inapplicable(code: str, status: str) -> None:
    rows = deepcopy(ROWS)
    row = next(row for row in rows if row["gate_check_code"] == code)
    row["status"] = status
    if status == "WAIVED":
        row.update(waiver_approval_request_id=str(uuid4()), waived_count=0)
    with pytest.raises(Problem):
        verified_gates(rows, locked_at=NOW)


@pytest.mark.parametrize("count,waived_count", [(1, 2), (2, 2), (None, None)])
def test_recorded_waiver_keeps_reference_and_counts(
    count: int | None, waived_count: int | None
) -> None:
    rows = deepcopy(ROWS)
    request_id = uuid4()
    next(row for row in rows if row["gate_check_code"] == WAIVABLE).update(
        status="WAIVED",
        count=count,
        waived_count=waived_count,
        waiver_approval_request_id=str(request_id),
    )
    result = verified_gates(rows, locked_at=NOW)
    saved = next(row for row in result if row.gate_check_code == WAIVABLE)
    assert (saved.count, saved.waived_count, saved.waiver_approval_request_id) == (
        count,
        waived_count,
        request_id,
    )


@pytest.mark.parametrize("reference,count,waived_count", [(None, 1, 1), (str(uuid4()), 2, 1)])
def test_unbound_or_outgrown_waiver_is_refused(
    reference: str | None, count: int, waived_count: int
) -> None:
    rows = deepcopy(ROWS)
    next(row for row in rows if row["gate_check_code"] == WAIVABLE).update(
        status="WAIVED",
        count=count,
        waived_count=waived_count,
        waiver_approval_request_id=reference,
    )
    with pytest.raises(Problem):
        verified_gates(rows, locked_at=NOW)


BASIS = {
    "subject_table": "close_checklist_item",
    "code": "RECONCILIATIONS_GENERATED",
    "gate_kind": "AUTOMATIC",
    "gate_check_code": "RECONCILIATIONS_GENERATED",
    "entity_id": str(UUID(int=1)),
    "book_code": "ASC606",
    "period_id": str(UUID(int=2)),
    "open": True,
    "count": 2,
    "detail": "Two reconciliation kinds are missing",
    "members": [
        "reconciliation:BILLING_TO_SUBLEDGER:missing",
        "reconciliation:SUBLEDGER_TO_GL:missing",
    ],
}


def check_basis(value: object, digest: str | None = None) -> dict:
    return checked_waiver_basis(
        value,
        content_sha256=sha256_hex(value) if digest is None else digest,
        gate=SavedGate(
            gate_check_code="RECONCILIATIONS_GENERATED",
            status="WAIVED",
            count=1,
            evaluated_at=NOW,
            waiver_approval_request_id=UUID(int=3),
            waived_count=2,
        ),
        entity_id=UUID(int=1),
        book_code="ASC606",
        period_id=UUID(int=2),
    )


def test_saved_waiver_retains_full_reviewed_population_after_it_shrinks() -> None:
    assert check_basis(BASIS) == BASIS
    assert len(check_basis(BASIS)["members"]) == 2
    # Equal counts cannot hide replacement of a reviewed member.
    changed = {**BASIS, "members": [BASIS["members"][0], "replacement"]}
    with pytest.raises(Problem, match="missing or has changed"):
        check_basis(changed, sha256_hex(BASIS))


@pytest.mark.parametrize(
    "changes",
    [
        {"subject_table": "exception_item"},
        {"gate_kind": "MANUAL"},
        {"gate_check_code": "EXCEPTIONS_CLEARED"},
        {"entity_id": str(UUID(int=99))},
        {"book_code": "IFRS15"},
        {"period_id": str(UUID(int=99))},
        {"open": False},
        {"count": True},
        {"count": "2"},
        {"count": 1},
        {"members": None},
        {"members": []},
        {"members": ["same", "same"]},
        {"members": ["", "other"]},
        {"members": [1, "other"]},
    ],
)
def test_even_a_matching_hash_must_bind_the_selected_gate(changes: dict) -> None:
    with pytest.raises(Problem, match="does not match its close gate"):
        check_basis({**BASIS, **changes})


@pytest.mark.parametrize("value", [None, [], "missing", {}])
def test_absent_or_legacy_count_only_basis_is_not_reconstructed(value: object) -> None:
    with pytest.raises(Problem):
        check_basis(value)
