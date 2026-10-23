"""Original component usage enters a nonlease-predominant combined component once."""

from dataclasses import replace
from datetime import date

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.errors import EngineError
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


def rti_world(*, lease_predominates=False):
    value = usage_world(lease_fee="12000")
    value = replace(
        value,
        events=tuple(
            replace(
                ev,
                event_type="BILLING_RECORDED",
                payload={
                    "obligation_key": "SERVICE",
                    "amount": "6000",
                    "invoice_number": "SERVICE-1",
                    "line_external_id": "SERVICE-1-1",
                    "issue_date": JAN_END,
                    "tax_amount": "500",
                },
            )
            if ev.event_type == "USAGE_REPORTED" and ev.payload["obligation_key"] == "SERVICE"
            else ev
            for ev in value.events
        ),
        pob_template_versions=tuple(
            replace(template, recognition_method="RIGHT_TO_INVOICE")
            for template in value.pob_template_versions
        ),
    )
    if lease_predominates:
        value = replace(
            value,
            contracts=tuple(
                replace(
                    header,
                    judgements=tuple(
                        replace(
                            record,
                            outcome={**record.outcome, "lessor_nonlease_predominates": "false"},
                        )
                        for record in header.judgements
                    ),
                )
                for header in value.contracts
            ),
        )
    return value


def test_combined_rti_retains_each_components_source_priority():
    result = compute(rti_world()).books[0]
    columns = result.contract_version.columns
    assert columns["transaction_price"] == 1_800_000
    assert columns["billed_cum"] == 600_000
    assert columns["revenue_cum"] == 1_800_000
    assert columns["out_of_scope_amount"] == 0
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_combined_lease_rti_routes_fixed_and_excess_performance_once():
    result = compute(rti_world(lease_predominates=True)).books[0]
    columns = result.contract_version.columns
    assert columns["transaction_price"] == columns["revenue_cum"] == columns["rpo_amount"] == 0
    assert columns["out_of_scope_amount"] == 1_800_000
    assert columns["billed_cum"] == 600_000
    assert result.obligation_versions[0].columns["allocated_amount"] == 1_800_000
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_combined_rti_guard_checks_the_original_lease_pricing():
    value = rti_world()
    value = replace(
        value,
        events=tuple(
            replace(
                ev,
                payload={
                    **ev.payload,
                    "lines": [
                        {**line, "unit_price": "100"} if line["obligation_key"] == "LEASE" else line
                        for line in ev.payload["lines"]
                    ],
                },
            )
            if ev.event_type == "CONTRACT_BOOKED"
            else ev
            for ev in value.events
        ),
    )
    with pytest.raises(EngineError, match="RTI_EXPEDIENT_NOT_APPLICABLE"):
        compute(value)
