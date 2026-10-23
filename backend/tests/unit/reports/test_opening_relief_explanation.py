from types import SimpleNamespace as NS

from erev_api.domain.reports.builders import SourceCollector
from erev_api.domain.reports.opening_relief_explanation import KEY, controls


def test_opening_proofs_are_visible_from_retained_sources_only():
    sources = SourceCollector()
    proof = {
        "basis": "CREATED_AFTER_OPENING",
        "event_id": "event-1",
        "effective_date": "2026-09-16",
    }
    sources.evidence.update(
        {
            "opening_relief_groups_v1": {"group": ["contract-1"]},
            "opening_relief_pob_v1": {
                "group": {
                    "obligations": {
                        "C/O2": {"opening_absence": proof},
                        "C/O1": {"opening_billing": "500"},
                    }
                }
            },
        }
    )
    result = controls(NS(binding=None, sources=sources))
    assert sources.evidence[KEY] is True
    assert result["opening_attribution_explanation"]["items"] == [
        {
            "subject": "C/O2",
            "contract_id": "contract-1",
            **proof,
        }
    ]
    assert controls(NS(binding=NS(evidence=dict(sources.evidence)), sources=None)) == result
    original = {k: v for k, v in sources.evidence.items() if k != KEY}
    assert controls(NS(binding=NS(evidence=original), sources=None)) == {}


def test_combined_zero_consumption_preserves_each_original_member_without_amounts():
    sources = SourceCollector()
    sources.evidence["opening_relief_reporting_pob_v1"] = {
        "group": {
            "members": {
                "contract-1": {
                    "basis": "ZERO_CONSUMPTION",
                    "obligations": {"A/O1": {"posted_revenue": "-10"}},
                },
                "contract-2": {
                    "basis": "ZERO_GROUP_OPENING",
                    "obligations": {"B/O1": {"posted_revenue": "0"}},
                },
            }
        }
    }
    items = controls(NS(binding=None, sources=sources))["opening_attribution_explanation"]["items"]
    assert [(i["subject"], i["contract_id"], i["basis"]) for i in items] == [
        ("A/O1", "contract-1", "ZERO_CONSUMPTION"),
        ("B/O1", "contract-2", "ZERO_GROUP_OPENING"),
    ]
    assert all("amount" not in item for item in items)
