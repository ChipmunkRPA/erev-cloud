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


def test_opening_links_use_frozen_version_and_never_replace_absent_opening():
    from erev_api.domain.reports.opening_relief_cells import source_links

    old, current = str(UUID(int=11)), str(UUID(int=12))
    source = {
        "contracts": [str(A), str(B)],
        "pob": {
            "members": {
                str(A): {
                    "version": current,
                    "frozen_opening": {"version": old},
                    "obligations": {"A/O1": {"opening_nodes": ["billed_cum:A/O1:P01"]}},
                },
                str(B): {
                    "version": current,
                    "frozen_opening": {"version": None},
                    "obligations": {"B/O1": {"opening_nodes": ["billed_cum:B/O1:P01"]}},
                },
            }
        },
    }
    trace = str(UUID(int=13))
    links = source_links(source, {old: trace, current: str(UUID(int=14))})
    assert {item["href"] for item in links} == {
        f"/contracts/{A}/history",
        f"/contracts/{A}/journals",
        f"/contracts/{B}/history",
        f"/contracts/{B}/journals",
        f"/trace/{trace}?node=billed_cum%3AA%2FO1%3AP01",
    }
    assert all(current not in item["href"] for item in links)


def test_reporting_calculation_explains_original_currency_and_signed_period_changes():
    from erev_api.domain.reports.opening_relief_cells import _details

    source = {
        "contracts": [str(A), str(B)],
        "currency_view": "reporting",
        "currency": "EUR",
        "group_key": f"{A}:{ENTITY}:USD",
        "values": rows()[0] | {},
        "translation_rates": [],
        "pob": {
            "opening": "80",
            "consumed": "26.67",
            "period_relief": {"P01": "40", "P02": "-13.33"},
            "members": {
                str(A): {
                    "obligations": {
                        "A/O1": {
                            "opening_billing": "50",
                            "opening_revenue": "10",
                            "posted_revenue": "26.67",
                            "eligible_relief": "26.67",
                        }
                    }
                }
            },
        },
    }
    source["values"] = {column: {"amount": "24.00", "currency": "EUR"} for column in COLUMNS}
    detail = _details(source)
    assert "Revenue from opening: 24.00 EUR" in detail
    assert "Opening liability cap: 80 USD" in detail
    assert "A/O1 · Opening attributed billing: 50 USD" in detail
    assert "A/O1 · Eligibility before group caps; not allocated group relief: 26.67 USD" in detail
    assert "P02 · Relief before reporting translation: -13.33 USD" in detail
    assert not any("26.67 EUR" in item for item in detail)


def test_zero_consumption_does_not_invent_missing_opening_calculation_inputs():
    from erev_api.domain.reports.opening_relief_cells import _details

    source = {
        "contracts": [str(A)],
        "currency_view": "functional",
        "currency": "USD",
        "group_key": f"{A}:{ENTITY}:USD",
        "values": rows()[0],
        "translation_rates": [],
        "pob": {
            "basis": "ZERO_CONSUMPTION",
            "opening_cap": "40",
            "consumption_cap": "-10",
            "obligations": {"A/O1": {"posted_revenue": "-10"}},
        },
    }
    details = _details(source)
    assert "A/O1 · Selected-range net posted revenue: -10 USD" in details
    assert not any(
        "Opening attributed billing" in item or "Eligibility before" in item for item in details
    )


def ownership_source():
    version, period = str(UUID(int=20)), str(UUID(int=21))
    output = rows()
    output[0]["_opening_source"]["group_key"] = f"{version}:{ENTITY}:USD"
    evidence = {
        "revenue_ownership_alignment_v1": {
            f"{version}:{ENTITY}:{A}:{period}": [
                {
                    "owner": str(A),
                    "layer": "original-A",
                    "posted_relief": "5500",
                    "target_relief": "1100",
                },
                {
                    "owner": str(B),
                    "layer": "original-B",
                    "posted_relief": "0",
                    "target_relief": "4400",
                },
            ],
            f"{UUID(int=99)}:{ENTITY}:{A}:{period}": [
                {
                    "owner": str(UUID(int=98)),
                    "layer": "unrelated",
                    "posted_relief": "9",
                    "target_relief": "9",
                }
            ],
        }
    }
    return output, evidence


def test_ownership_details_retain_zero_sum_adjustments_in_original_currency():
    from erev_api.domain.reports.opening_relief_cells import OWNERSHIP_KEY

    output, evidence = ownership_source()
    sources = SourceCollector()
    sources.evidence.update(evidence)
    retain(Session(), NS(binding=None, sources=sources), output, view="reporting", rates=[])
    assert sources.evidence[OWNERSHIP_KEY] is True
    params = NS(binding=NS(evidence=deepcopy(sources.evidence)), sources=None)
    value, items = cell(None, params, "summary:GBP", "revenue_from_opening")
    assert value == {"amount": "26.67", "currency": "GBP"}
    assert len(items) == 1
    details = items[0]["_source_set_details"]
    assert any("ownership adjustment -4400 USD" in line for line in details)
    assert any("ownership adjustment 4400 USD" in line for line in details)
    assert (
        "Ownership adjustments total: 0 USD; posted and target relief total: 5500 USD." in details
    )
    assert not any("unrelated" in line for line in details)
    assert not any("4400 GBP" in line for line in details)
    retain(Session(), params, ownership_source()[0], view="reporting", rates=[])
    matching = next(iter(params.binding.evidence["revenue_ownership_alignment_v1"].values()))
    matching[0]["target_relief"] = "1101"
    with pytest.raises(Problem, match="validation-failed"):
        retain(Session(), params, ownership_source()[0], view="reporting", rates=[])


def test_old_cell_binding_does_not_acquire_new_ownership_detail():
    output, evidence = ownership_source()
    sources = SourceCollector()
    retain(Session(), NS(binding=None, sources=sources), output, view="reporting", rates=[])
    saved = deepcopy(sources.evidence)
    saved.update(evidence)
    params = NS(binding=NS(evidence=saved), sources=None)
    retain(Session(), params, ownership_source()[0], view="reporting", rates=[])
    _, items = cell(None, params, "summary:GBP", "revenue_from_opening")
    assert not any("ownership adjustment" in line for line in items[0]["_source_set_details"])


def test_alignment_refuses_an_owner_outside_the_retained_source_group():
    output, evidence = ownership_source()
    matching = next(iter(evidence["revenue_ownership_alignment_v1"].values()))
    matching[0]["owner"] = str(UUID(int=98))
    sources = SourceCollector()
    sources.evidence.update(evidence)
    with pytest.raises(Problem, match="validation-failed"):
        retain(Session(), NS(binding=None, sources=sources), output, view="functional", rates=[])
