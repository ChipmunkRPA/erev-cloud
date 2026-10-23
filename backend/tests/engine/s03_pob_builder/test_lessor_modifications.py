"""Original combined-component price changes reach one modification boundary."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.bundle import ModificationInput
from erev_engine.trace import reevaluate
from tests.engine.s03_pob_builder.test_lessor_combination import example
from tests.engine.s03_pob_builder.test_s03_elections import (
    CONTRACT,
    INCEPTION,
    line,
    points,
    product,
)


def price_change(delta="1000"):
    value = example()
    mod = ModificationInput(
        modification_key="PRICE-1",
        effective_date=date(2026, 1, 15),
        kind="PRICE_CHANGE",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(
            {
                "obligation_key": "LEASE",
                "action": "CHANGE",
                "quantity_delta": Decimal(0),
                "consideration_delta": Decimal(delta),
            },
        ),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    return replace(
        value,
        contracts=(replace(value.contracts[0], modifications=(mod,)),),
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
        events=(
            *value.events,
            bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
            bundles.event(
                CONTRACT,
                3,
                "CONTRACT_AMENDED",
                mod.effective_date,
                {
                    "modification_id": mod.modification_key,
                    "lines": list(mod.lines),
                    "treatments": {"LEASE": "PROSPECTIVE"},
                    "ssp_basis": {},
                },
                obligation_keys=["LEASE"],
            ),
        ),
    )


@pytest.mark.parametrize("delta, expected", [("1000", 1_100_000), ("-1000", 900_000)])
def test_original_lease_price_change_updates_combined_allocation(delta, expected):
    result = compute(price_change(delta)).books[0]
    assert result.contract_version.columns["transaction_price"] == expected
    assert result.obligation_versions[0].columns["allocated_amount"] == expected
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_combined_remaining_ssp_includes_both_original_products():
    value = price_change()
    booked = value.events[0]
    value = replace(
        value,
        group=replace(value.group, products=(*value.group.products, product("OTHER"))),
        ssp_versions=(points(EQUIP="7500", MAINT="2500", OTHER="10000"),),
        events=(
            replace(
                booked,
                payload={
                    **booked.payload,
                    "lines": [*booked.payload["lines"], line("OTHER", "OTHER", price="10000")],
                },
            ),
            *value.events[1:-1],
            replace(
                value.events[-1],
                payload={
                    **value.events[-1].payload,
                    "treatments": {"LEASE": "PROSPECTIVE", "OTHER": "PROSPECTIVE"},
                },
            ),
        ),
    )
    result = compute(value).books[0]
    weights = {
        node.id.split(":")[-2]: node.value
        for node in result.trace.nodes
        if node.measure.startswith("mod_weight@")
    }
    assert weights[f"{CONTRACT}/SERVICE"] == weights[f"{CONTRACT}/OTHER"]
    allocations = {
        ob.columns["obligation_key"]: ob.columns["allocated_amount"]
        for ob in result.obligation_versions
    }
    assert allocations["SERVICE"] == allocations["OTHER"] == 1_050_000
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_lease_predominant_price_change_remains_outside_606():
    value = price_change()
    value = replace(
        value,
        contracts=tuple(
            replace(
                header,
                judgements=tuple(
                    replace(
                        record, outcome={**record.outcome, "lessor_nonlease_predominates": "false"}
                    )
                    for record in header.judgements
                ),
            )
            for header in value.contracts
        ),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["transaction_price"] == 0
    assert result.contract_version.columns["out_of_scope_amount"] == 1_100_000
    assert result.contract_version.columns["revenue_cum"] == 0
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_conflicting_member_treatments_cannot_be_silently_merged():
    value = price_change()
    value = replace(
        value,
        events=(
            *value.events[:-1],
            replace(
                value.events[-1],
                payload={
                    **value.events[-1].payload,
                    "treatments": {"LEASE": "PROSPECTIVE", "SERVICE": "CUMULATIVE_CATCH_UP"},
                },
            ),
        ),
    )
    with pytest.raises(ValueError, match="instructions conflict"):
        compute(value)
