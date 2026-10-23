"""Original component usage enters a nonlease-predominant combined component once."""

from dataclasses import replace
from datetime import date

from support import bundles

from erev_engine import compute
from erev_engine.trace import SourceRef, reevaluate
from tests.engine.s03_pob_builder.test_lessor_combination import example
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT, INCEPTION, points

JAN_END = date(2026, 1, 31)


def usage_world(*, both_names: bool = False, lease_fee: str = "200"):
    value = example()
    events = [bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})]
    for seq, key, amount in [(3, "SERVICE", "100"), (4, "LEASE", lease_fee)]:
        events.append(
            bundles.event(
                CONTRACT,
                seq,
                "USAGE_REPORTED",
                JAN_END,
                {
                    "obligation_key": key,
                    "metric": "UNITS",
                    "quantity": "1",
                    "rated_amount": amount,
                    "usage_period_start": "2026-01-01",
                    "usage_period_end": "2026-01-31",
                },
                obligation_keys=["SERVICE", "LEASE"] if both_names else [key],
            )
        )
    return replace(
        value,
        events=(*value.events, *events),
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
        pob_template_versions=tuple(
            replace(template, recognition_method="USAGE", ratable_convention=None)
            for template in value.pob_template_versions
        ),
    )


def test_original_lease_usage_moves_price_and_revenue_with_source_identity():
    baseline = compute(usage_world(lease_fee="0")).books[0]
    value = usage_world()
    result = compute(value).books[0]
    old, new = baseline.contract_version.columns, result.contract_version.columns
    assert new["vc_constrained_amount"] == 30_000
    assert new["transaction_price"] == 1_030_000
    assert new["revenue_cum"] - old["revenue_cum"] == 20_000
    assert new["transaction_price"] - old["transaction_price"] == 20_000
    assert new["out_of_scope_amount"] == 0
    sources = {
        source.ref_id
        for node in result.trace.nodes
        for source in node.inputs
        if isinstance(source, SourceRef) and source.ref_type == "contract_event"
    }
    assert {event.event_key for event in value.events[-2:]} <= sources
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_event_naming_both_components_is_counted_once():
    single = compute(usage_world()).books[0]
    both = compute(usage_world(both_names=True)).books[0]
    for key in ("vc_constrained_amount", "transaction_price", "revenue_cum"):
        assert both.contract_version.columns[key] == single.contract_version.columns[key]


def test_lease_predominant_usage_routes_entire_amount_without_revenue_or_rpo():
    value = usage_world()
    header = value.contracts[0]
    value = replace(
        value,
        contracts=(
            replace(
                header,
                judgements=tuple(
                    replace(
                        record, outcome={**record.outcome, "lessor_nonlease_predominates": "false"}
                    )
                    for record in header.judgements
                ),
            ),
        ),
    )
    result = compute(value).books[0]
    columns = result.contract_version.columns
    assert columns["transaction_price"] == 0
    assert columns["out_of_scope_amount"] == 1_030_000
    assert columns["revenue_cum"] == columns["rpo_amount"] == 0
    assert len(result.obligation_versions) == 1
    assert result.obligation_versions[0].columns["allocated_amount"] == 1_030_000
    assert result.schedules == ()
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}
