from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from erev_api.domain.reports import opening_relief_availability as availability
from erev_api.domain.reports.builders import SourceCollector
from erev_api.problems import Problem


def rows():
    return [
        {
            "row_key": "group",
            "currency": "GBP",
            "_opening_unavailable": ["A/O1"],
            "revenue_from_opening": {"amount": "0", "currency": "GBP"},
        },
        {
            "row_key": "resolved",
            "currency": "GBP",
            "revenue_from_opening": {"amount": "10", "currency": "GBP"},
        },
    ]


def test_unknown_group_is_null_and_known_subtotal_is_not_a_complete_total():
    sources = SourceCollector()
    output = rows()
    currencies, controls = availability.apply(NS(binding=None, sources=sources), output)
    assert currencies == {"GBP"}
    assert output[0]["revenue_from_opening"] is None
    assert "unavailable" in output[0]["summary"]
    assert "_opening_unavailable" not in output[0]
    evidence = controls["opening_attribution_availability"]
    assert evidence["status"] == "INCOMPLETE"
    assert evidence["known_subtotals"] == {"GBP": "10.00"}
    binding = NS(evidence=deepcopy(sources.evidence))
    assert availability.apply(NS(binding=binding, sources=None), rows())[1] == controls
    binding.evidence[availability.KEY]["status"] = "COMPLETE"
    with pytest.raises(Problem):
        availability.apply(NS(binding=binding, sources=None), rows())


def test_old_runs_keep_strict_behavior_and_nested_unknown_facts_are_masked():
    assert not availability.enabled(NS(binding=NS(evidence={})))
    facts = {
        "relief": "0",
        "eligible_relief_capped_by_group": "0",
        "members": {"A": {"unresolved_subjects": ["A/O1"]}},
    }
    availability.mask_facts(facts)
    assert facts["relief"] is None
    assert facts["eligible_relief_capped_by_group"] is None
    assert facts["unresolved_subjects"] == ["A/O1"]


def test_export_keeps_unknown_amount_blank_with_explanation():
    import csv
    import io
    from erev_api.domain.reports.builders.revenue_from_opening_liability import COLUMNS
    from erev_api.domain.reports.outputs import ReportData
    from erev_api.domain.reports.outputs.csv import render_csv

    output = rows()
    availability.apply(NS(binding=None, sources=None), output)
    rendered = render_csv(ReportData(columns=COLUMNS, rows=tuple(output), control_totals={}))
    table = list(csv.reader(io.StringIO(rendered.decode())))
    assert availability.NOTE in rendered.decode()
    assert table[1][-2:] == ["", ""]
