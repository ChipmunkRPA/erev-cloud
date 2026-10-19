from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.reports.forecast_actuals import posted_rows
from erev_api.problems import Problem

ENTITY = UUID(int=1)
CUTOFF = datetime(2026, 10, 19, tzinfo=UTC)
EARLY = "2026-10-18T00:00:00+00:00"
LATE = "2026-10-20T00:00:00+00:00"


def line(**changes):
    return {
        "id": "line-1",
        "journal_entry_id": "entry",
        "journal_batch_id": "batch",
        "run_id": "run",
        "entity_id": str(ENTITY),
        "book_code": "ASC606",
        "account_role": "REVENUE",
        "period_id": "period",
        "period_key": "FY2026-P10",
        "contract_id": "contract",
        "obligation_id": "obligation",
        "dimensions": {},
        "txn_currency": "USD",
        "debit_txn": "0.00",
        "credit_txn": "100.00",
        "functional_currency": "EUR",
        "debit_functional": "0.00",
        "credit_functional": "90.00",
        "created_at": EARLY,
        "run_updated_at": EARLY,
        "run_state": "acknowledged",
        "run_no": "JE-1",
        "run_approved_at": EARLY,
        "run_acknowledged_at": EARLY,
        "batch_acknowledged_at": EARLY,
        "_transitions": [],
        **changes,
    }


def read(rows):
    return posted_rows(rows, known_at=CUTOFF, entity_ids=[ENTITY], book_code="ASC606")


def test_actuals_require_each_batch_acknowledgement_and_keep_both_currency_amounts():
    rows = read(
        [
            line(),
            line(id="unposted", batch_acknowledged_at=None),
            line(id="later", batch_acknowledged_at=LATE),
            line(id="receivable", account_role="RECEIVABLE"),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["credit_txn"] == "100.00"
    assert rows[0]["credit_functional"] == "90.00"
    assert rows[0]["acknowledged_at"] == EARLY


def test_later_cancellation_does_not_change_historical_actuals():
    later = line(run_state="cancelled", run_updated_at=LATE, run_cancelled_at=LATE)
    assert read([later])[0]["run_state_at_cutoff"] == "acknowledged"
    assert read([line(run_state="cancelled", run_cancelled_at=EARLY)]) == []
    reversal = read([line(debit_txn="20.00", credit_txn="0.00")])[0]
    assert reversal["debit_txn"] == "20.00"  # credits/reversals stay signed at projection time


@pytest.mark.parametrize(
    "rows",
    [
        [line(), line()],
        [line(entity_id=str(UUID(int=2)))],
        [line(created_at=LATE)],
        [line(book_code="IFRS15")],
    ],
)
def test_duplicates_and_scope_mismatches_fail_closed(rows):
    with pytest.raises(Problem):
        read(rows)
