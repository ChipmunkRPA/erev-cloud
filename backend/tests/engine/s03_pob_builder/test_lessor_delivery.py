"""Combined delivery measures include original member events once, with original controls."""

from dataclasses import replace
from datetime import date

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.trace import reevaluate
from tests.engine.s03_pob_builder.test_lessor_combination import example
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT, INCEPTION, points


@pytest.mark.parametrize("method", ["UNITS_DELIVERED", "POINT_IN_TIME"])
@pytest.mark.parametrize("returned", [False, True])
@pytest.mark.parametrize("both_names", [False, True])
def test_original_component_deliveries_and_returns_update_combined_revenue(
    returned, both_names, method
):
    value = example()
    events = [bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})]
    for seq, key in [(3, "LEASE"), (4, "SERVICE")]:
        events.append(
            bundles.event(
                CONTRACT,
                seq,
                "DELIVERY_RECORDED",
                date(2026, 1, 10),
                {"obligation_key": key, "quantity": "1", "trigger": "DELIVERY"},
                obligation_keys=["LEASE", "SERVICE"] if both_names else [key],
            )
        )
    if returned:
        events.append(
            bundles.event(
                CONTRACT,
                5,
                "RETURN_RECORDED",
                date(2026, 1, 20),
                {"obligation_key": "LEASE", "quantity": "1"},
                obligation_keys=["LEASE"],
            )
        )
    value = replace(
        value,
        events=(*value.events, *events),
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
        pob_template_versions=tuple(
            replace(
                template,
                recognition_method=method,
                ratable_convention=None,
                satisfaction_pattern="POINT_IN_TIME" if method == "POINT_IN_TIME" else "OVER_TIME",
                over_time_criterion="NOT_APPLICABLE" if method == "POINT_IN_TIME" else "OT_A",
            )
            for template in value.pob_template_versions
        ),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["transaction_price"] == 1_000_000
    assert result.contract_version.columns["revenue_cum"] == (500_000 if returned else 1_000_000)
    assert len(result.obligation_versions) == 1
    assert reevaluate(result.trace) == {node.id: node.value for node in result.trace.nodes}


def test_original_component_controls_are_not_replaced_by_host_controls():
    from support.recognition import (
        CONTRACT_KEY,
        allocated_state,
        bill_and_hold_judgement,
        book_context,
        event_view,
    )

    from erev_engine.stages.s09_recognition.progress_events import tally
    from tests.engine.s09_recognition.test_s09_outputs import _goods

    host = replace(_goods(quantity=2), combined_component_keys=("POB-01", "POB-02"))
    day = date(2026, 2, 15)

    def delivery(trigger):
        return event_view(
            CONTRACT_KEY,
            2,
            "DELIVERY_RECORDED",
            day,
            {"obligation_key": "POB-02", "quantity": "1", "trigger": trigger},
            obligation_keys=["POB-01", "POB-02"],
        )

    ctx = book_context(
        overrides=(
            (
                "recognition.control_trigger",
                "OBLIGATION",
                f"{CONTRACT_KEY}/POB-02",
                "ACCEPTANCE_ONLY",
            ),
        )
    )
    state = allocated_state([host], events=[delivery("DELIVERY")])
    counted = tally(ctx, state, state.contracts[0], host, day)
    assert counted.counted == 0
    assert counted.held[0][1] == "TRIGGER_NOT_PERMITTED"
    state = allocated_state([host], events=[delivery("ACCEPTANCE")])
    assert tally(ctx, state, state.contracts[0], host, day).counted == 1

    # A host's bill-and-hold judgement cannot authorize its original sibling's transfer.
    ctx = book_context()
    for judged, expected in [("POB-01", 0), ("POB-02", 1)]:
        state = allocated_state(
            [host], events=[delivery("BILL_AND_HOLD")], judgements=[bill_and_hold_judgement(judged)]
        )
        assert tally(ctx, state, state.contracts[0], host, day).counted == expected
