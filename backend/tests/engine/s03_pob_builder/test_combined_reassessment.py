"""Reviewed quantity continuation keeps original component identities and prior revenue."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.trace import reevaluate
from tests.engine.s03_pob_builder.test_lessor_modifications import price_change
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT


def continuation(delta="1"):
    value = price_change()
    old = value.contracts[0].modifications[0]
    decision = {
        "decision": "CONTINUE",
        "effective_date": old.effective_date.isoformat(),
        "component_keys": ["LEASE", "SERVICE"],
        "same_transfer_pattern": True,
        "operating_lease": True,
        "nonlease_predominates": True,
    }
    mod = replace(
        old,
        lines=({**old.lines[0], "quantity_delta": Decimal(delta)},),
        questionnaire={"combined_reassessment": {"SERVICE": decision}},
    )
    amended = value.events[-1]
    return replace(
        value,
        evidence_revision=29,
        contracts=(replace(value.contracts[0], modifications=(mod,)),),
        pob_template_versions=tuple(
            replace(t, recognition_method="UNITS_DELIVERED") for t in value.pob_template_versions
        ),
        events=(
            *value.events[:-1],
            bundles.event(
                CONTRACT,
                3,
                "DELIVERY_RECORDED",
                date(2026, 1, 5),
                {"obligation_key": "LEASE", "quantity": "0.5", "trigger": "DELIVERY"},
                obligation_keys=["LEASE"],
            ),
            bundles.event(
                CONTRACT,
                4,
                "CONTRACT_AMENDED",
                amended.effective_date,
                {**amended.payload, "lines": list(mod.lines)},
                obligation_keys=["LEASE"],
            ),
        ),
    )


@pytest.mark.parametrize("delta, quantity", [("1", 3), ("-0.25", Decimal("1.75"))])
def test_reviewed_quantity_change_preserves_transferred_income(delta, quantity):
    value = continuation(delta)
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 250_000
    assert Fraction(str(result.obligation_versions[0].columns["quantity"])) == quantity
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    with pytest.raises(ValueError, match="require reassessment"):
        compute(replace(value, evidence_revision=28))


@pytest.mark.parametrize(
    "field,value",
    [
        ("component_keys", ["LEASE"]),
        ("effective_date", "2026-01-16"),
        ("same_transfer_pattern", False),
        ("nonlease_predominates", False),
    ],
)
def test_continuation_requires_complete_matching_assessment(field, value):
    source = continuation()
    header = source.contracts[0]
    mod = header.modifications[0]
    decision = {**mod.questionnaire["combined_reassessment"]["SERVICE"], field: value}
    mod = replace(mod, questionnaire={"combined_reassessment": {"SERVICE": decision}})
    with pytest.raises(ValueError, match="complete dated eligibility"):
        compute(replace(source, contracts=(replace(header, modifications=(mod,)),)))


def test_continuation_cannot_remove_transferred_units():
    with pytest.raises(ValueError, match="transferred units"):
        compute(continuation("-0.75"))


def test_later_price_boundary_keeps_reassessed_member_quantities():
    value = continuation()
    header = value.contracts[0]
    first = header.modifications[0]
    second = replace(
        first,
        modification_key="PRICE-2",
        effective_date=date(2026, 1, 20),
        questionnaire={},
        lines=({**first.lines[0], "quantity_delta": Decimal(0)},),
    )
    event = bundles.event(
        CONTRACT,
        5,
        "CONTRACT_AMENDED",
        second.effective_date,
        {
            "modification_id": second.modification_key,
            "lines": list(second.lines),
            "treatments": {"LEASE": "PROSPECTIVE"},
            "ssp_basis": {},
        },
        obligation_keys=["LEASE"],
    )
    value = replace(
        value,
        contracts=(replace(header, modifications=(first, second)),),
        events=(*value.events, event),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 250_000
    assert result.obligation_versions[0].columns["quantity"] == 3
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}


def test_continuation_rejects_retroactive_recognition_treatment():
    value = continuation()
    event = value.events[-1]
    event = replace(
        event, payload={**event.payload, "treatments": {"LEASE": "CUMULATIVE_CATCH_UP"}}
    )
    with pytest.raises(ValueError, match="preserve prior revenue prospectively"):
        compute(replace(value, events=(*value.events[:-1], event)))


def test_added_units_keep_the_original_component_ssp_stratification():
    value = continuation()
    booking = value.events[0]
    booking = replace(
        booking,
        payload={
            **booking.payload,
            "lines": [
                {**line, "stratification": "LEASE-GRADE"}
                if line["obligation_key"] == "LEASE"
                else line
                for line in booking.payload["lines"]
            ],
        },
    )
    value = replace(
        value,
        events=(booking, *value.events[1:]),
        ssp_versions=tuple(
            replace(
                version,
                entries=tuple(
                    replace(entry, stratification="LEASE-GRADE")
                    if entry.product_code == "EQUIP"
                    else entry
                    for entry in version.entries
                ),
            )
            for version in value.ssp_versions
        ),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["transaction_price"] == 1_100_000
    assert result.contract_version.columns["revenue_cum"] == 250_000
    assert result.obligation_versions[0].columns["quantity"] == 3
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
