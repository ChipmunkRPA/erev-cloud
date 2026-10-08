"""Close population integrity: omissions are explicit and need the reviewed identities."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.close.gates import REQUIRED_KINDS
from erev_api.domain.reports.evidence_certification import SavedGate
from erev_api.domain.reports.evidence_reconciliation_population import checked_population
from erev_api.problems import Problem

NOW = datetime(2026, 10, 8, tzinfo=UTC)
BILLING, GL = REQUIRED_KINDS
ROWS = [{"id": UUID(int=index + 1), "kind": kind} for index, kind in enumerate(REQUIRED_KINDS)]


def gate(status: str = "PASSED", count: int | None = 0) -> SavedGate:
    return SavedGate(
        gate_check_code="RECONCILIATIONS_GENERATED",
        status=status,
        count=count,
        evaluated_at=NOW,
        waiver_approval_request_id=UUID(int=3) if status == "WAIVED" else None,
        waived_count=2 if status == "WAIVED" else None,
    )


def test_required_population_includes_optional_statements_and_is_sorted() -> None:
    extra = {"id": UUID(int=4), "kind": "RPO_ROLLFORWARD"}
    result = checked_population(REQUIRED_KINDS, [extra, *reversed(ROWS)], gate())
    assert result["waived_absent_kinds"] == []
    assert result["certified"] == [
        {"kind": row["kind"], "reconciliation_id": row["id"]}
        for row in sorted([*ROWS, extra], key=lambda row: row["kind"])
    ]
    assert checked_population((), [], gate())["certified"] == []


@pytest.mark.parametrize(
    "status,count", [("PASSED", 0), ("NOT_APPLICABLE", 0), ("WAIVED", None), ("WAIVED", 1)]
)
def test_missing_required_population_cannot_be_hidden_by_status_or_smaller_count(
    status: str, count: int | None
) -> None:
    with pytest.raises(Problem, match="absent without matching"):
        checked_population(
            REQUIRED_KINDS,
            [],
            gate(status, count),
            reviewed_members=[f"reconciliation:{kind}:missing" for kind in REQUIRED_KINDS],
        )


@pytest.mark.parametrize(
    "member",
    [
        f"reconciliation:{GL}:missing",
        f"reconciliation:{BILLING}:bad-id:unreviewed",
        f"reconciliation:{BILLING}:{UUID(int=5)}:outdated",
        "unrelated",
        "",
    ],
)
def test_same_count_waiver_of_a_different_finding_does_not_cover_absence(member: str) -> None:
    with pytest.raises(Problem, match="absent without matching"):
        checked_population(REQUIRED_KINDS, ROWS[1:], gate("WAIVED", 1), reviewed_members=[member])


@pytest.mark.parametrize(
    "member",
    [f"reconciliation:{BILLING}:missing", f"reconciliation:{BILLING}:{UUID(int=5)}:unreviewed"],
)
def test_reviewed_omission_is_explicit_and_not_called_certified(member: str) -> None:
    result = checked_population(
        REQUIRED_KINDS, ROWS[1:], gate("WAIVED", 1), reviewed_members=[member]
    )
    assert result["waived_absent_kinds"] == [BILLING]
    assert result["certified"] == [{"kind": GL, "reconciliation_id": UUID(int=2)}]


@pytest.mark.parametrize(
    "rows",
    [
        [*ROWS, ROWS[0]],
        [ROWS[0], {"id": UUID(int=7), "kind": BILLING}],
        [ROWS[0], {"id": ROWS[0]["id"], "kind": GL}],
    ],
)
def test_duplicate_sources_are_refused(rows: list[dict]) -> None:
    with pytest.raises(Problem, match="duplicate"):
        checked_population(REQUIRED_KINDS, rows, gate())


def test_passed_gate_cannot_retain_findings() -> None:
    with pytest.raises(Problem, match="unresolved findings"):
        checked_population(REQUIRED_KINDS, ROWS, gate(count=1))
