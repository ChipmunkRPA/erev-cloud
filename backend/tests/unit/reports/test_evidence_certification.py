"""Saved certification is evidence only with a complete, cleared historical gate set."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from erev_api.domain.close import certification, gates
from erev_api.domain.reports.evidence_certification import verified_gates
from erev_api.problems import Problem

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
