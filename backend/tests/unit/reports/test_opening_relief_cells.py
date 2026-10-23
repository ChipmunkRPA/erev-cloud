from copy import deepcopy
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.problems import Problem
from erev_api.domain.reports.builders import SourceCollector
from erev_api.domain.reports.opening_relief_cells import COLUMNS, KEY, cell, retain

A, B, ENTITY = (UUID(int=i) for i in (1, 2, 3))


class Session:
    def execute(self, statement):
        return NS(all=lambda: [(A, ENTITY), (B, ENTITY)])


def rows():
    return [
        {
            "row_key": "combined:original-group",
            "_opening_source": {
                "entity_id": str(ENTITY),
                "contracts": [str(A), str(B)],
                "group_key": "original-group",
            },
            "currency": "GBP",
            "entity_code": "UK",
            **{
                column: {"amount": value, "currency": "GBP"}
                for column, value in zip(COLUMNS, ("80.00", "26.67", "26.67"), strict=True)
            },
        }
    ]


def test_combined_contribution_is_indivisible_and_rebuild_checks_it():
    sources = SourceCollector()
    params = NS(binding=None, sources=sources)
    output = rows()
    retain(Session(), params, output, view="functional", rates=[])
    assert "_opening_source" not in output[0]
    binding = NS(evidence=deepcopy(sources.evidence))
    params = NS(binding=binding, sources=None)
    value, items = cell(None, params, "summary:GBP", "revenue_from_opening")
    assert value == {"amount": "26.67", "currency": "GBP"}
    assert len(items) == 1
    assert items[0]["value"] == value
    details = items[0]["_source_set_details"]
    assert any(str(A) in text and str(B) in text for text in details)
    assert "Combined-contract group total. Member relief is not allocated." in details
    retain(Session(), params, rows(), view="functional", rates=[])
    changed = rows()
    changed[0]["revenue_from_opening"]["amount"] = "26.68"
    with pytest.raises(Problem, match="validation-failed"):
        retain(Session(), params, changed, view="functional", rates=[])


def test_old_binding_does_not_gain_new_evidence_or_fabricate_drill():
    params = NS(binding=NS(evidence={}), sources=SourceCollector())
    output = rows()
    retain(None, params, output, view="functional", rates=[])
    assert "_opening_source" not in output[0]
    assert KEY not in params.sources.evidence
    with pytest.raises(Problem, match="no retained"):
        cell(None, params, "summary:GBP", "revenue_from_opening")
