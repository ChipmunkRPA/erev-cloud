"""A posted transfer leaves prior income at source and moves only remaining consideration."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.boundary_basis import fixed_boundary_basis
from erev_engine.trace import reevaluate
from tests.engine.s06_modifications.test_regroup_future_service import incoming
from tests.engine.s06_modifications.test_s06_prospective import MOD_DATE, ex_09_a


@pytest.mark.parametrize("measure", ["TIME_ELAPSED", "UNITS_DELIVERED"])
def test_source_transfer_retains_prior_income_and_stops_future_income(measure):
    value = replace(ex_09_a(), evidence_revision=37)
    if measure == "UNITS_DELIVERED":
        delivery = bundles.event(
            value.contracts[0].external_id,
            3,
            "DELIVERY_RECORDED",
            date(2026, 9, 1),
            {"obligation_key": "POB-01", "quantity": "0.25", "trigger": "DELIVERY"},
            obligation_keys=["POB-01"],
        )
        value = replace(
            value,
            pob_template_versions=tuple(
                replace(t, recognition_method=measure) for t in value.pob_template_versions
            ),
            events=tuple(
                sorted(
                    (*value.events, delivery),
                    key=lambda e: (e.effective_date, e.record_seq, e.event_key),
                )
            ),
        )

    contract = value.contracts[0]
    old = contract.modifications[0]
    event = next(e for e in value.events if e.event_type == "CONTRACT_AMENDED")
    basis = fixed_boundary_basis(
        value,
        book_code="ASC606",
        event_key=event.event_key,
        contract_key=contract.external_id,
        obligation_keys=("POB-01",),
    )[0]
    amount = Decimal(basis.remaining_minor) / 100
    line = {
        "obligation_key": "POB-01",
        "action": "REMOVE",
        "quantity_delta": -Decimal(basis.remaining_quantity.numerator)
        / Decimal(basis.remaining_quantity.denominator),
        "consideration_delta": -amount,
    }
    mod = replace(
        old, kind="REMOVE_OBLIGATION", lines=(line,), chosen_treatments={"POB-01": "PROSPECTIVE"}
    )
    event = replace(
        event,
        event_type="REGROUPED",
        payload={
            **event.payload,
            "lines": [line],
            "direction": "OUT",
            "regroup_id": "RG-1",
            "counterpart_contract_id": "TARGET",
            "modification_id": mod.modification_key,
            "obligation_keys": ["POB-01"],
            "treatments": {"POB-01": "PROSPECTIVE"},
        },
    )
    value = replace(
        value,
        contracts=(replace(contract, modifications=(mod,)),),
        events=tuple(event if e.event_type == "CONTRACT_AMENDED" else e for e in value.events),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["transaction_price"] == basis.recognized_minor
    assert result.contract_version.columns["revenue_cum"] == basis.recognized_minor
    assert result.obligation_versions[0].columns["remaining_allocation"] == 0
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    for patch in ({"consideration_delta": -amount + 1}, {"quantity_delta": Decimal("-0.5")}):
        wrong = replace(mod, lines=({**line, **patch},))
        with pytest.raises(ValueError, match="basis changed"):
            compute(replace(value, contracts=(replace(contract, modifications=(wrong,)),)))
    wrong_treatment = replace(mod, chosen_treatments={"POB-01": "CUMULATIVE_CATCH_UP"})
    with pytest.raises(ValueError, match="preserve prior income"):
        compute(replace(value, contracts=(replace(contract, modifications=(wrong_treatment,)),)))

    target = incoming(MOD_DATE, revision=37, unpooled=True)
    if measure == "UNITS_DELIVERED":
        target = replace(
            target,
            pob_template_versions=tuple(
                replace(t, recognition_method=measure) for t in target.pob_template_versions
            ),
        )
    target_contract = target.contracts[0]
    target_mod = target_contract.modifications[0]
    target_mod = replace(
        target_mod,
        questionnaire={
            "regroup_book_lines": {
                "ASC606": [
                    {
                        "obligation_key": "POB-02",
                        "action": "ADD",
                        "quantity_delta": str(-line["quantity_delta"]),
                        "consideration_delta": {"amount": str(amount), "currency": "USD"},
                    }
                ]
            }
        },
    )
    target = replace(target, contracts=(replace(target_contract, modifications=(target_mod,)),))
    received = compute(target).books[0]
    moved = next(o for o in received.obligation_versions if o.columns["obligation_key"] == "POB-02")
    assert moved.columns["allocated_amount"] == basis.remaining_minor
    assert (
        result.contract_version.columns["transaction_price"] + moved.columns["allocated_amount"]
        == basis.allocation_minor
    )
