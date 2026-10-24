"""Complete original-component termination retains one combined allocation boundary."""

from dataclasses import replace
from decimal import Decimal

import pytest

from erev_engine import compute
from erev_engine.trace import reevaluate
from tests.engine.s03_pob_builder.test_lessor_modifications import price_change


def termination(kind="FULL", keys=("LEASE", "SERVICE")):
    value = price_change()
    original = value.contracts[0].modifications[0]
    lines = tuple(
        {
            "obligation_key": key,
            "action": "REMOVE",
            "quantity_delta": Decimal(0),
            "consideration_delta": Decimal("-6750" if key == "LEASE" else "-2250"),
        }
        for key in ("LEASE", "SERVICE")
    )
    mod = replace(original, kind="TERMINATION", lines=lines)
    event = replace(
        value.events[-1],
        event_type="CONTRACT_TERMINATED",
        payload={
            "modification_id": mod.modification_key,
            "termination_kind": kind,
            "obligation_keys": list(keys),
        },
    )
    return replace(
        value,
        evidence_revision=10,
        contracts=(replace(value.contracts[0], modifications=(mod,)),),
        events=(*value.events[:-1], event),
    )


@pytest.mark.parametrize("kind", ["FULL", "PARTIAL"])
def test_all_original_components_terminate_one_combined_obligation(kind):
    result = compute(termination(kind)).books[0]
    assert result.contract_version.columns["transaction_price"] == 100_000
    assert result.contract_version.columns["revenue_cum"] == 100_000
    assert len(result.obligation_versions) == 1
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


@pytest.mark.parametrize("keys", [("LEASE",), ("SERVICE",)])
def test_partial_original_component_termination_requires_reassessment(keys):
    with pytest.raises(ValueError, match="requires reassessment"):
        compute(termination("PARTIAL", keys))


def test_full_termination_requires_removal_lines_for_every_original_component():
    value = termination()
    header = value.contracts[0]
    mod = replace(header.modifications[0], lines=header.modifications[0].lines[:1])
    value = replace(value, contracts=(replace(header, modifications=(mod,)),))
    with pytest.raises(ValueError, match="require reassessment"):
        compute(value)


def test_lease_predominant_combination_termination_stays_outside_606():
    value = termination()
    header = value.contracts[0]
    header = replace(
        header,
        judgements=tuple(
            replace(record, outcome={**record.outcome, "lessor_nonlease_predominates": "false"})
            for record in header.judgements
        ),
    )
    result = compute(replace(value, contracts=(header,))).books[0]
    assert result.contract_version.columns["transaction_price"] == 0
    assert result.contract_version.columns["revenue_cum"] == 0
    assert result.contract_version.columns["out_of_scope_amount"] == 100_000
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


@pytest.mark.parametrize("delta", ["-1.5", "-0.5"])
def test_original_member_removal_cannot_borrow_another_members_quantity(delta):
    value = termination()
    header = value.contracts[0]
    mod = header.modifications[0]
    mod = replace(mod, lines=({**mod.lines[0], "quantity_delta": Decimal(delta)}, mod.lines[1]))
    value = replace(value, contracts=(replace(header, modifications=(mod,)),))
    if delta == "-1.5":
        with pytest.raises(
            ValueError, match="LEASE removal exceeds its original remaining quantity"
        ):
            compute(value)
    else:
        assert compute(value).books[0].contract_version.columns["revenue_cum"] == 100_000


@pytest.mark.parametrize("returned", [False, True])
def test_original_member_removal_uses_net_deliveries_before_termination(returned):
    from datetime import date
    from support import bundles
    from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT

    value = termination()
    header = value.contracts[0]
    mod = header.modifications[0]
    mod = replace(mod, lines=({**mod.lines[0], "quantity_delta": Decimal("-0.5")}, mod.lines[1]))
    events = [
        *value.events[:-1],
        bundles.event(
            CONTRACT,
            3,
            "DELIVERY_RECORDED",
            date(2026, 1, 5),
            {
                "obligation_key": "LEASE",
                "quantity": "0.75",
                "trigger": "DELIVERY",
            },
            obligation_keys=["LEASE"],
        ),
    ]
    if returned:
        events.append(
            bundles.event(
                CONTRACT,
                4,
                "RETURN_RECORDED",
                date(2026, 1, 6),
                {
                    "obligation_key": "LEASE",
                    "quantity": "0.5",
                    "reason": "Returned original units",
                },
                obligation_keys=["LEASE"],
            )
        )
    events.append(
        bundles.event(
            CONTRACT,
            len(events) + 1,
            "CONTRACT_TERMINATED",
            mod.effective_date,
            value.events[-1].payload,
        )
    )
    value = replace(
        value,
        contracts=(replace(header, modifications=(mod,)),),
        events=tuple(events),
        pob_template_versions=tuple(
            replace(template, recognition_method="UNITS_DELIVERED")
            for template in value.pob_template_versions
        ),
    )
    if returned:
        assert compute(value).books[0].contract_version.columns["revenue_cum"] == 100_000
    else:
        with pytest.raises(
            ValueError, match="LEASE removal exceeds its original remaining quantity"
        ):
            compute(value)
