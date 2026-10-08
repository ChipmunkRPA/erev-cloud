"""Frozen journal lines are checked in both currencies, batch by batch."""

from copy import deepcopy
from decimal import Decimal

import pytest
from erev_api.domain.reports.evidence_journals import AMOUNTS, BATCH_FIELDS, checked_batches
from erev_api.problems import Problem

BATCH = {
    **dict.fromkeys(BATCH_FIELDS, None),
    "run_no": "RUN-1",
    "external_id": "BATCH-1",
    "txn_currency": "USD",
    "functional_currency": "GBP",
    "run_state": "acknowledged",
    "line_count": 2,
    "total_debit_txn": Decimal("10"),
    "total_credit_txn": Decimal("10"),
    "total_debit_functional": Decimal("8"),
    "total_credit_functional": Decimal("8"),
}
ROWS = [
    {
        "row_key": str(index),
        "run_no": "RUN-1",
        "batch_external_id": "BATCH-1",
        "txn_currency": "USD",
        "functional_currency": "GBP",
        "run_state": "acknowledged",
        **dict(zip(AMOUNTS, amounts, strict=True)),
    }
    for index, amounts in enumerate([("10", "0", "8", "0"), ("0", "10", "0", "8")])
]


def test_balanced_batches_include_empty_batches_and_have_stable_order() -> None:
    empty = {
        **BATCH,
        "external_id": "EMPTY",
        "line_count": 0,
        **{f"total_{name}": Decimal(0) for name in AMOUNTS},
    }
    result = checked_batches(ROWS, [empty, BATCH])
    assert result == checked_batches(list(reversed(ROWS)), [BATCH, empty])
    assert [row["frozen_line_count"] for row in result] == [2, 0]
    assert all(row["balanced"] for row in result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_no", "OTHER"),
        ("batch_external_id", "OTHER"),
        ("txn_currency", "EUR"),
        ("functional_currency", "EUR"),
        ("run_state", "draft"),
        ("debit_txn", "11"),
        ("debit_functional", "9"),
        ("debit_txn", "NaN"),
        ("debit_txn", "Infinity"),
        ("debit_txn", "-1"),
        ("debit_txn", "text"),
    ],
)
def test_mismatched_or_invalid_frozen_row_is_refused(field: str, value: str) -> None:
    rows = deepcopy(ROWS)
    rows[0][field] = value
    with pytest.raises(Problem):
        checked_batches(rows, [BATCH])


@pytest.mark.parametrize(
    "rows,batches",
    [
        (ROWS, []),
        (ROWS[:-1], [BATCH]),
        (ROWS + [ROWS[0]], [BATCH]),
        (ROWS, [BATCH, BATCH]),
        (ROWS, [{**BATCH, "line_count": 3}]),
    ],
)
def test_missing_duplicate_and_wrong_count_populations_are_refused(
    rows: list, batches: list
) -> None:
    with pytest.raises(Problem):
        checked_batches(rows, batches)


@pytest.mark.parametrize("basis", ["txn", "functional"])
def test_matching_but_unbalanced_stored_figures_are_refused(basis: str) -> None:
    rows = deepcopy(ROWS)
    rows[0][f"debit_{basis}"] = "11"
    batch = {**BATCH, f"total_debit_{basis}": Decimal("11")}
    with pytest.raises(Problem, match="unbalanced"):
        checked_batches(rows, [batch])
