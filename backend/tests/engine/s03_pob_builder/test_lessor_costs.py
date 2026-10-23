"""Combined cost recognition consumes original additive costs exactly once."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support.recognition import estimate_version

from erev_engine import compute
from erev_engine.trace import SourceRef, reevaluate
from tests.engine.s03_pob_builder.test_lessor_combination import example
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT, INCEPTION, points


@pytest.mark.parametrize("wasted", [False, True])
@pytest.mark.parametrize("method", ["COST_RECOVERY", "COST_TO_COST"])
@pytest.mark.parametrize("both_names", [False, True])
def test_combined_costs_include_original_lease_once(method, both_names, wasted):
    value = example()
    events = [bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})]
    for seq, key, amount in [(3, "SERVICE", "100"), (4, "LEASE", "200")]:
        events.append(
            bundles.event(
                CONTRACT,
                seq,
                "COST_INCURRED",
                date(2026, 1, 31),
                {
                    "obligation_key": key,
                    "purpose": "PROGRESS_INPUT",
                    "amount": amount,
                    "is_wasted": wasted and key == "LEASE",
                },
                obligation_keys=["SERVICE", "LEASE"] if both_names else [key],
            )
        )
    estimates = ()
    if method == "COST_TO_COST":
        estimates = (
            replace(
                estimate_version(
                    f"{CONTRACT}/EAC-1", "EAC", 1, INCEPTION, obligation_key="SERVICE"
                ),
                expected_total_amount=Decimal("1000"),
            ),
        )
        events.append(
            replace(
                bundles.event(
                    CONTRACT,
                    5,
                    "ESTIMATE_CHANGED",
                    INCEPTION,
                    {"estimate_version_id": estimates[0].version_key},
                ),
                estimate_version_key=estimates[0].version_key,
            )
        )
    value = replace(
        value,
        events=tuple(
            sorted(
                (*value.events, *events),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        estimate_versions=estimates,
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
        pob_template_versions=tuple(
            replace(t, recognition_method=method, ratable_convention=None)
            for t in value.pob_template_versions
        ),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == (
        30_000 if method == "COST_RECOVERY" else (100_000 if wasted else 300_000)
    )
    sources = {
        source.ref_id
        for node in result.trace.nodes
        for source in node.inputs
        if isinstance(source, SourceRef) and source.ref_type == "contract_event"
    }
    assert {e.event_key for e in events if e.event_type == "COST_INCURRED"} <= sources
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}

    progress_nodes = [
        n
        for n in result.trace.nodes
        if n.measure == "progress_ratio" and n.formula_id.endswith(".v2")
    ]
    assert progress_nodes
    for node in progress_nodes:
        held = [x for x in node.inputs if isinstance(x, SourceRef)]
        expected = {
            e.event_key
            for e in events
            if e.event_type == "COST_INCURRED"
            and e.effective_date.isoformat() <= node.params["as_of"]
        }
        assert {x.ref_id for x in held if x.ref_type == "contract_event"} == expected
        assert {x.ref_id for x in held if x.ref_type == "estimate_version"} == {
            e.version_key for e in estimates
        }
    node = next(n for n in progress_nodes if n.params["costs"] != "0")
    original = node.inputs[0]
    assert isinstance(original, SourceRef)
    altered = replace(original, detail={**original.detail, "value": "999"})
    corrupted = replace(node, inputs=(altered, *node.inputs[1:]))
    with pytest.raises(ValueError, match="do not reconcile"):
        reevaluate(
            replace(
                result.trace,
                nodes=tuple(corrupted if n.id == node.id else n for n in result.trace.nodes),
            )
        )
