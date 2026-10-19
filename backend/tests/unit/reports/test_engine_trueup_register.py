"""A partial deferred portion with actual postings is not a settled upgrade."""

from copy import deepcopy
from typing import Any

import pytest
from erev_api.domain.reports.builders.engine_trueup_register import dataset
from erev_api.problems import Problem


def test_deferred_portion_retains_signed_multicurrency_lines() -> None:
    facts: dict[str, Any] = {
        "portions": [
            {
                "id": "portion",
                "group_id": "group",
                "entity_id": "entity",
                "entity_code": "US",
                "book_code": "ASC606",
                "attempt_id": "attempt",
                "upgrade_state": "DEFERRED_NO_OPEN_PERIOD",
                "group_terminal": None,
                "sampled": True,
                "reason": None,
                "unresolved_origins": ["FY2026-P06"],
                "posting_ids": ["posting"],
            }
        ],
        "lines": [
            {
                "id": "debit",
                "entity_id": "entity",
                "book_code": "ASC606",
                "subledger_posting_id": "posting",
                "combination_group_id": "group",
                "release_validation_attempt_id": "attempt",
                "period_key": "FY2026-P03",
                "account_role": "RECEIVABLE",
                "cause": "UPGRADE_AND_OTHER_INPUTS",
                "sampled": True,
                "txn_currency": "EUR",
                "amount_txn": "100.00",
                "functional_currency": "USD",
                "amount_functional": "110.00",
            },
            {
                "id": "credit",
                "entity_id": "entity",
                "book_code": "ASC606",
                "subledger_posting_id": "posting",
                "combination_group_id": "group",
                "release_validation_attempt_id": "attempt",
                "period_key": "FY2026-P03",
                "account_role": "REVENUE",
                "cause": "UPGRADE_AND_OTHER_INPUTS",
                "sampled": True,
                "txn_currency": "EUR",
                "amount_txn": "-100.00",
                "functional_currency": "USD",
                "amount_functional": "-110.00",
            },
        ],
    }
    built = dataset(facts)
    assert built.rows[0]["record_type"] == "PORTION"
    assert all(row["group_terminal"] is None for row in built.rows)
    assert all(row["upgrade_state"] == "DEFERRED_NO_OPEN_PERIOD" for row in built.rows)
    assert built.control_totals["signed_amounts"] == {
        "US:ASC606:FY2026-P03:txn:EUR:RECEIVABLE": "100.00",
        "US:ASC606:FY2026-P03:txn:EUR:REVENUE": "-100.00",
        "US:ASC606:FY2026-P03:functional:USD:RECEIVABLE": "110.00",
        "US:ASC606:FY2026-P03:functional:USD:REVENUE": "-110.00",
    }
    missing = deepcopy(facts)
    missing["lines"] = []
    with pytest.raises(Problem, match="unavailable"):
        dataset(missing)
    wrong = deepcopy(facts)
    wrong["lines"][0]["release_validation_attempt_id"] = "other"
    with pytest.raises(Problem, match="does not match"):
        dataset(wrong)
