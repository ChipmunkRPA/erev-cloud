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
