"""Two native modifications in one computation retain distinct event amounts."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from erev_api.domain.reports.modification_event_amounts import read
from erev_engine import compute
from support import bundles
from tests.engine.s06_modifications.test_s06_prospective import (
    CONTRACT,
    amended,
    booked,
    bundle,
    delivered,
    mod_line,
    modification_input,
    point_entry,
    product,
    ssp_version,
)


def _trace():
    start = date(2026, 1, 1)
    first = modification_input(
        "MOD-ONE",
        date(2026, 4, 1),
        [mod_line("O1", "CHANGE", "SKU", "0", "20000.00")],
        kind="PRICE_CHANGE",
    )
    second = modification_input(
        "MOD-TWO",
        date(2026, 6, 1),
        [mod_line("O1", "CHANGE", "SKU", "0", "-10000.00")],
        kind="PRICE_CHANGE",
    )
    events = [
        amended(4, first, {"O1": "CUMULATIVE_CATCH_UP"}),
        amended(5, second, {"O1": "CUMULATIVE_CATCH_UP"}),
    ]
    value = bundle(
        booked(
            start,
            bundles.booking_line("O1", product_code="SKU", quantity="10", total_price="100000.00"),
        ),
        delivered(3, "O1", "5", date(2026, 3, 31)),
        *events,
        products=[product("SKU", "TPL-UNITS")],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU", "10000.00")], start)],
        inception=start,
        months=12,
        modifications=[first, second],
    )
    output = compute(value)
    assert len(output.books) == 1
    return output.books[0].trace, [event.event_key for event in events]


def test_two_modifications_are_read_independently_from_one_native_trace():
    trace, events = _trace()
    values = [
        read(trace, event_key=event, contract_key=CONTRACT, obligation_keys=["O1"], currency="USD")
        for event in events
    ]
    assert all(value is not None for value in values)
    assert [(value.tp_change, value.catch_up["O1"]) for value in values if value] == [
        (Decimal("20000"), Decimal("10000")),
        (Decimal("-10000"), Decimal("-5000")),
    ]
    assert values[0].components == {
        "fixed": Decimal("20000"),
        "vc_constrained": Decimal(0),
        "expected_returns": Decimal(0),
        "consideration_payable": Decimal(0),
        "financing_adjustment": Decimal(0),
        "noncash": Decimal(0),
        "rounding": Decimal(0),
    }
    assert sum(values[1].components.values()) == values[1].tp_change
    incomplete = replace(
        trace,
        nodes=tuple(
            node
            for node in trace.nodes
            if not node.measure.startswith("modification_tp_component_noncash@")
        ),
    )
    # Remove dependent rounding nodes too, so this tests component completeness,
    # independently of the trace replay's missing-node protection.
    incomplete = replace(
        incomplete,
        nodes=tuple(
            node
            for node in incomplete.nodes
            if not node.measure.startswith("modification_tp_component_rounding@")
        ),
    )
    with pytest.raises(ValueError, match="incomplete"):
        read(
            incomplete,
            event_key=events[0],
            contract_key=CONTRACT,
            obligation_keys=["O1"],
            currency="USD",
        )
    assert set(values[0].node_ids).isdisjoint(values[1].node_ids)
    legacy = replace(
        trace,
        nodes=tuple(
            node for node in trace.nodes if not node.measure.startswith("modification_tp_change@")
        ),
    )
    assert (
        read(
            legacy,
            event_key=events[0],
            contract_key=CONTRACT,
            obligation_keys=["O1"],
            currency="USD",
        )
        is None
    )
    with pytest.raises(ValueError, match="currency"):
        read(
            trace,
            event_key=events[0],
            contract_key=CONTRACT,
            obligation_keys=["O1"],
            currency="EUR",
        )
