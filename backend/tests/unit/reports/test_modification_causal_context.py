"""Causal rows distinguish the event owner from the affected contract without changing amounts."""

import json
from copy import deepcopy
from datetime import date

from erev_api.domain.reports.modification_causal_report import dataset


def test_event_context_is_retained_without_assigning_baselines_or_other_events():
    assessment = {"HOST": {"decision": "CONTINUE", "component_keys": ["HOST", "LEASE"]}}
    evidence = {
        "analyses": [
            {
                "computation_id": "compute-1",
                "entity_code": "US01",
                "period_key": "2026-09",
                "selected_event_keys": ["OWNER/EV-1"],
                "metrics": [
                    {
                        "contract_external_id": "AFFECTED",
                        "currency": "USD",
                        "baseline": "10",
                        "final": "15",
                        "effects": [
                            {"event_key": "OWNER/EV-1", "amount": "7"},
                            {"event_key": "OTHER/EV-2", "amount": "-2"},
                        ],
                    }
                ],
            }
        ],
        "modifications": {
            "OWNER/EV-1": {
                "modification_no": "MOD-1",
                "contract_external_id": "OWNER",
                "effective_date": "2026-09-10",
                "combined_reassessment": json.dumps(assessment),
                "proposed_treatments": json.dumps({"HOST": "PROSPECTIVE"}),
                "chosen_treatments": json.dumps({"HOST": "CUMULATIVE_CATCH_UP"}),
            }
        },
        "unavailable": [],
    }
    original = deepcopy(evidence)
    old = dataset(evidence)
    evidence["modification_context_columns"] = True
    current = dataset(evidence)
    selected = current.rows[1]
    assert selected["contract_external_id"] == "AFFECTED"
    assert selected["modification_contract"] == "OWNER"
    assert selected["modification_effective_date"] == date(2026, 9, 10)
    assert json.loads(selected["combined_reassessment"]) == assessment
    for row in (current.rows[0], current.rows[2], current.rows[3]):
        assert row["modification_contract"] is None
        assert row["combined_reassessment"] is None
    assert [r["causal_amount"] for r in current.rows] == [r["causal_amount"] for r in old.rows]
    assert current.control_totals == old.control_totals
    assert "combined_reassessment" not in old.rows[1]
    assert dataset(original) == old

    evidence["modification_treatment_maps"] = True
    decisions = dataset(evidence)
    assert json.loads(decisions.rows[1]["modification_proposed_treatments"]) == {
        "HOST": "PROSPECTIVE"
    }
    assert json.loads(decisions.rows[1]["modification_chosen_treatments"]) == {
        "HOST": "CUMULATIVE_CATCH_UP"
    }
    for row in (decisions.rows[0], decisions.rows[2], decisions.rows[3]):
        assert row["modification_proposed_treatments"] is None
        assert row["modification_chosen_treatments"] is None
    assert decisions.control_totals == current.control_totals
    for before, row in zip(current.rows, decisions.rows, strict=True):
        assert {key: row[key] for key in before} == before
        assert "modification_chosen_treatments" not in before
    assert dataset(evidence) == decisions
