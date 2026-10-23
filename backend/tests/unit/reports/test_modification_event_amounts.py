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


def _trace(*, foreign=False, same_period=False, return_input=False, second_delta="-10000.00"):
    start = date(2026, 1, 1)
    first = modification_input(
        "MOD-ONE",
        date(2026, 4, 1),
        [mod_line("O1", "CHANGE", "SKU", "0", "20000.00")],
        kind="PRICE_CHANGE",
    )
    second = modification_input(
        "MOD-TWO",
        date(2026, 4, 2) if same_period else date(2026, 6, 1),
        [mod_line("O1", "CHANGE", "SKU", "0", second_delta)],
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
    if foreign:
        from erev_engine.bundle import FxRateInput

        calendar = replace(value.entities[0], functional_currency="GBP")
        rates = tuple(
            FxRateInput(
                f"USD-GBP/{kind}/{period.period_key}",
                "FX@v1",
                kind,
                "USD",
                "GBP",
                period.start_date if kind == "spot" else period.end_date,
                None if kind == "spot" else period.period_key,
                Decimal("0.8") if period.start_date.month < 6 else Decimal("0.9"),
            )
            for period in calendar.periods
            for kind in ("spot", "average", "closing")
        )
        value = replace(
            value,
            entities=(calendar,),
            books=(
                replace(
                    value.books[0],
                    account_mapping=bundles.account_mapping(extra=(("FX_GAIN_LOSS", None, "FX"),)),
                ),
            ),
            currencies=bundles.currencies("USD", "GBP"),
            fx_rates=tuple(
                sorted(
                    rates,
                    key=lambda r: (
                        r.rate_type,
                        r.base_currency,
                        r.quote_currency,
                        r.effective_date,
                        r.version_key,
                    ),
                )
            ),
        )
    if return_input:
        return value, [event.event_key for event in events]
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


@pytest.mark.parametrize("foreign", [False, True])
def test_exclusive_modification_period_keeps_original_functional_calculation(foreign):
    from erev_api.domain.reports.modification_functional import read as functional
    from erev_engine.stages.s01_canonicalize import obligation_subject_key

    trace, events = _trace(foreign=foreign)
    currency = "GBP" if foreign else "USD"

    def measure(event, held=trace):
        return functional(
            held,
            event_key=event,
            subject=obligation_subject_key(CONTRACT, "O1"),
            entity="US01",
            transaction_currency="USD",
            functional_currency=currency,
        )

    first, second = [measure(event) for event in events]
    assert first.amount == Decimal("8000" if foreign else "10000")
    assert second.amount == Decimal("-4500" if foreign else "-5000")
    assert first.currency == second.currency == currency
    assert first.period_key == "FY2026-P04" and second.period_key == "FY2026-P06"
    assert any(node.startswith("revenue_activity_functional:") for node in first.node_ids)
    missing = replace(
        trace, nodes=tuple(n for n in trace.nodes if n.measure != "revenue_activity_functional")
    )
    assert measure(events[0], missing) is None
    mixed, events = _trace(foreign=foreign, same_period=True)
    assert all(measure(event, mixed) is None for event in events)
    # An unrelated upstream revenue producer must not borrow the period's FX amount.
    original_trace, original_events = _trace(foreign=foreign)
    altered = replace(
        original_trace,
        nodes=tuple(
            replace(
                node,
                params={
                    **node.params,
                    "recognition_source_node": "revenue_cum:"
                    + obligation_subject_key(CONTRACT, "O1")
                    + ":FY2026-P03",
                },
            )
            if node.measure == "revenue_activity_functional" and node.id.endswith("FY2026-P04")
            else node
            for node in original_trace.nodes
        ),
    )
    assert measure(original_events[0], altered) is None
    corrupted = replace(
        original_trace,
        nodes=tuple(
            replace(node, value=str(Decimal(node.value) + 1))
            if node.measure == "revenue_activity_functional" and node.id.endswith("FY2026-P04")
            else node
            for node in original_trace.nodes
        ),
    )
    with pytest.raises(ValueError, match="reproduce"):
        measure(original_events[0], corrupted)
