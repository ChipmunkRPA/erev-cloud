"""POL-212 changes units, preserving source facts and all monetary opening balances."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_api.domain.migration import capture, opening_balances
from erev_api.domain.migration.field_mapping import BatchParameters
from erev_api.problems import Problem
from support import bundles
from tests.domain.migration.test_field_mapping import CODEX_MATERIAL_RIGHT, _synthetic_row
from tests.unit.test_migration_capture import _batch

CUTOVER = date(2026, 1, 31)


def converted(source_quantity: str = "25") -> opening_balances.ContractOpening:
    quantity = Decimal(source_quantity)
    remaining = Decimal("1") if source_quantity == "3" else Decimal("10")
    delivered = quantity - remaining
    source = _synthetic_row(
        "P1",
        1,
        **(
            CODEX_MATERIAL_RIGHT
            | {
                "Original POB Total Qty": source_quantity,
                "Original Extended SSP": source_quantity,
                "Original Total Contract Price": str(quantity * Decimal("2.5")),
                "Original Allocation": str(quantity * Decimal("2.5")),
                "Current Remaining Qty": str(remaining),
                "Current Delivery - Cumulative": str(delivered),
                "Current Remaining SSP": str(remaining),
                "Current SSP Delivered - Cumulative": str(delivered),
                "Current Rev Rec - Cumulative": str(delivered * Decimal("2.5")),
                "Current Remaining Allocation": str(remaining * Decimal("2.5")),
                "Current Unit SSP": "1",
                "Current Remaining Unit Rev Rec": "2.5",
            }
        ),
    )
    return opening_balances.stage(
        [source], CUTOVER, BatchParameters(material_right_convention="CONVERT_TO_OPTION_RECORD")
    ).contracts[0]


def test_converted_opening_uses_option_units_and_preserves_money() -> None:
    contract = converted()
    source = dict(contract.rows[0].values)
    row = opening_balances.opening_payload(contract, CUTOVER)["rows"][0]
    assert Decimal(row["remaining_quantity"]) == Decimal("0.4")
    assert Decimal(row["delivered_quantity_cum"]) == Decimal("0.6")
    assert Decimal(row["unit_ssp"]) == 25
    assert Decimal(row["remaining_unit_revenue_rate"]) == Decimal("62.5")
    changed = {
        "remaining_quantity",
        "delivered_quantity_cum",
        "unit_ssp",
        "remaining_unit_revenue_rate",
    }
    for member, value in source.items():
        if member not in changed:
            assert Decimal(row[member]) == value
    assert contract.rows[0].values == source
    assert (
        Fraction(row["remaining_quantity"]) * Fraction(row["unit_ssp"]) == source["remaining_ssp"]
    )
    body = capture.opening_body(contract, batch=_batch(cutover_date=CUTOVER), currency="USD")
    assert Decimal(body.obligations[0].remaining_quantity) == Decimal("0.4")
    assert Decimal(body.obligations[0].delivered_quantity_cum) == Decimal("0.6")


def test_keep_quantity_convention_preserves_source_units() -> None:
    source = _synthetic_row("P1", 1, **CODEX_MATERIAL_RIGHT)
    contract = opening_balances.stage([source], CUTOVER).contracts[0]
    payload = opening_balances.opening_payload(contract, CUTOVER)["rows"][0]
    assert {key: Decimal(payload[key]) for key in contract.rows[0].values} == contract.rows[
        0
    ].values


def test_unrepresentable_conversion_refuses_without_rounding() -> None:
    contract = converted("3")
    with pytest.raises(ValueError, match="remaining_quantity.*exact.*POL-212"):
        opening_balances.opening_payload(contract, CUTOVER)
    with pytest.raises(Problem, match="remaining_quantity"):
        capture.opening_body(contract, batch=_batch(cutover_date=CUTOVER), currency="USD")


@pytest.mark.parametrize("book", ["ASC606", "IFRS15"])
def test_converted_payload_reaches_engine_opening_segment(book: str) -> None:
    from dataclasses import replace

    from erev_api.domain.contracts.bundles import engine_payload
    from erev_engine.stages import s07_onboarding
    from erev_engine.trace import TraceBuilder
    from tests.engine.s03_pob_builder import test_s03_specialist as base

    contract = converted()
    body = capture.opening_body(contract, batch=_batch(cutover_date=CUTOVER), currency="USD")
    key = contract.rows[0].mapped.obligation_key
    right = replace(
        base.voucher(),
        obligation_key=key,
        ssp_method="ENTERED_AMOUNT",
        entered_ssp_amount=Decimal("25"),
    )
    opening = bundles.event(
        base.CONTRACT,
        3,
        "OPENING_BALANCE_ESTABLISHED",
        CUTOVER,
        engine_payload(body.model_dump(mode="json")),
        obligation_keys=[key],
    )
    opening = replace(opening, schema_version=2)
    value = base.world(
        base.booked(base.line(key, "VOUCHER", "62.50", quantity="1")),
        base.activated(2),
        opening,
        products=[base.product("VOUCHER", "TPL-MR")],
        templates=[
            base.template(
                "TPL-MR", obligation_kind="MATERIAL_RIGHT", recognition_method="UNITS_DELIVERED"
            )
        ],
        contract=base.header(material_rights=(right,)),
        ssp=[base.ssp_book(base.entry("VOUCHER", "1"))],
        books=base.BOTH_BOOKS,
        policies={
            code: {"onboarding.method": "OPENING_BALANCES_AT_CUTOVER"} for code in base.BOTH_BOOKS
        },
    )
    _, _, allocated, _ = base.fold(value, book)
    assert allocated is not None
    ctx, identified = base.identify(value, book)
    event = next(
        item
        for item in identified.canonical.events
        if item.event_type == "OPENING_BALANCE_ESTABLISHED"
    )
    after = s07_onboarding.apply(
        ctx, allocated, event, TraceBuilder(engine_version=value.engine_version)
    )
    assert after.findings == ()
    segment = after.obligations[0].segments[-1]
    assert segment.totals.quantity == Fraction(2, 5)
    assert segment.unit_ssp == 25
    assert segment.remaining_ssp == 10
    assert segment.x_exact == Fraction(125, 2)
    assert segment.base_revenue_posted == 3750
