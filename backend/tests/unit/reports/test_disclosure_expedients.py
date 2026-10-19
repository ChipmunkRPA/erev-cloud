"""Omission affects rendering only; underlying policy facts remain available for snapshots."""

from copy import deepcopy

import pytest
from erev_api.domain.reports.disclosure_expedients import dataset
from erev_api.problems import Problem


def test_elected_relief_hides_rows_without_discarding_policy_facts() -> None:
    facts = {
        "version": 1,
        "omitted": True,
        "omission_note": "Omitted under the elected relief.",
        "rows": [
            {
                "row_key": "costs.obtain_expedient",
                "registry_key": "costs.obtain_expedient",
                "expedient": "Expense qualifying costs?",
                "value": "Applied",
                "disclosure": "ASC 340-40-25-4",
            }
        ],
    }
    retained = deepcopy(facts)
    shown = dataset(facts)
    assert shown.rows == ()
    assert shown.control_totals["omitted_sections"][0]["section"] == 7
    assert facts == retained
    assert dataset({**facts, "omitted": False}).rows == tuple(facts["rows"])
    with pytest.raises(Problem, match="Unsupported"):
        dataset({**facts, "version": 2})
