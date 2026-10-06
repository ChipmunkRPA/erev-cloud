"""Contract event payload models (dev-guide §5.11 DG-KRN-EVT-03; 04 §3.3, §16.1, §16.3, API-C-06;
BUILD_SPEC CTR-1)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.enums import ContractEventType
from erev_api.events import payloads
from pydantic import ValidationError

DELIVERY = {"obligation_key": "O1", "quantity": "5", "trigger": "DELIVERY"}
BILLING = {
    "invoice_number": "INV-US-1001",
    "line_external_id": "INV-US-1001-1",
    "obligation_key": "O1",
    "amount": {"amount": "120000.00", "currency": "USD"},
    "issue_date": "2026-01-01",
}
CUSTOMER_ID = "0191e0a0-0000-7000-8000-0000000000c1"


def booking(**extra: Any) -> dict[str, Any]:
    """PRD WLD-K-01 as a booking payload."""
    return {
        "external_id": "SF-ORD-10001",
        "customer_id": CUSTOMER_ID,
        "contracting_entity_code": "AVM-US",
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": "AVM-PLAT-ENT",
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
            {
                "obligation_key": "O2",
                "product_code": "AVM-IMPL-STD",
                "quantity": "1",
                "total_price": {"amount": "15000.00", "currency": "USD"},
            },
        ],
        **extra,
    }


def _errors(excinfo: pytest.ExceptionInfo[ValidationError]) -> list[tuple[Any, ...]]:
    return [
        (error["type"], error["loc"], (error.get("ctx") or {}).get("rule_id"))
        for error in excinfo.value.errors()
    ]


def test_payload_models_forbid_extra_fields() -> None:
    delivery = payloads.DeliveryRecordedV1.model_validate(DELIVERY)
    assert (delivery.obligation_key, delivery.quantity, delivery.trigger) == ("O1", "5", "DELIVERY")
    # An unknown member raises a validation error (DG-KRN-EVT-03).
    with pytest.raises(ValidationError) as excinfo:
        payloads.DeliveryRecordedV1.model_validate({**DELIVERY, "unit_price": "10.00"})
    assert _errors(excinfo) == [("extra_forbidden", ("unit_price",), None)]
    # A payload is frozen once validated.
    with pytest.raises(ValidationError) as excinfo:
        delivery.quantity = "6"  # type: ignore[misc]
    assert [error["type"] for error in excinfo.value.errors()] == ["frozen_instance"]
    # Money members accept only strings, and so do decimal members (API-C-06).
    assert payloads.BillingRecordedV1.model_validate(BILLING).amount.amount == "120000.00"
    with pytest.raises(ValidationError) as excinfo:
        payloads.BillingRecordedV1.model_validate(
            {**BILLING, "amount": {"amount": 120000.00, "currency": "USD"}}
        )
    assert _errors(excinfo) == [("api_c_06", ("amount", "amount"), "API-C-06")]
    with pytest.raises(ValidationError) as excinfo:
        payloads.DeliveryRecordedV1.model_validate({**DELIVERY, "quantity": 5})
    assert _errors(excinfo) == [("api_c_06", ("quantity",), "API-C-06")]
    # Every registered model forbids unknown members and is frozen.
    for model in payloads.PAYLOADS.values():
        assert (model.model_config.get("extra"), model.model_config.get("frozen")) == (
            "forbid",
            True,
        ), model.__name__


def test_payload_bounds_and_rules() -> None:
    # §16.3 "Decimal > 0", "Decimal 0-1" and "Money > 0"; signed amounts stay signed.
    with pytest.raises(ValidationError) as excinfo:
        payloads.DeliveryRecordedV1.model_validate({**DELIVERY, "quantity": "0"})
    assert _errors(excinfo) == [("payload_bound", ("quantity",), None)]
    progress = {
        "obligation_key": "O2",
        "cumulative_progress_ratio": "0.4",
        "measure": "OUTPUT_PERCENT",
    }
    assert payloads.ProgressRecordedV1.model_validate(progress).cumulative_progress_ratio == "0.4"
    with pytest.raises(ValidationError):
        payloads.ProgressRecordedV1.model_validate({**progress, "cumulative_progress_ratio": "1.2"})
    with pytest.raises(ValidationError):
        payloads.BillingRecordedV1.model_validate(
            {**BILLING, "amount": {"amount": "-1.00", "currency": "USD"}}
        )
    revenue = {"obligation_key": "O1", "amount": {"amount": "-2500.00", "currency": "USD"}}
    assert payloads.PreStandardRevenueRecordedV1.model_validate(revenue).amount.amount == "-2500.00"
    receipt = {
        "receipt_reference": "RCPT-1",
        "amount": {"amount": "100.00", "currency": "USD"},
        "receipt_date": "2026-02-01",
        "form": "NONCASH",
    }
    with pytest.raises(ValidationError):
        payloads.PaymentReceivedV1.model_validate(receipt)
    assert (
        payloads.PaymentReceivedV1.model_validate({**receipt, "units_received": "10"}).form
        == "NONCASH"
    )
    # The E-110 subset of table 3.4-R.
    with pytest.raises(ValidationError):
        payloads.EventVoidedV1.model_validate({"reason_code": "CLOSE_RESTARTED", "comment": "x"})
    assert payloads.EventVoidedV1.model_validate(
        {"reason_code": "DUPLICATE", "comment": "Sent twice"}
    )
    # A clawback names its payee and plan (§16.3 COST_INCURRED).
    cost = {"purpose": "COST_TO_OBTAIN", "amount": {"amount": "500.00", "currency": "USD"}}
    with pytest.raises(ValidationError):
        payloads.CostIncurredV1.model_validate({**cost, "cost_adjustment": "CLAWBACK"})
    assert payloads.CostIncurredV1.model_validate(
        {**cost, "cost_adjustment": "CLAWBACK", "payee": "E-1001", "plan_code": "FY26-AE"}
    )
    with pytest.raises(ValidationError):
        payloads.CostIncurredV1.model_validate({**cost, "purpose": "WARRANTY_CLAIM"})
    # Tax lines sum to the tax amount.
    taxed = {**BILLING, "tax_amount": {"amount": "10.00", "currency": "USD"}}
    line = {
        "tax_type": "SALES",
        "amount": {"amount": "4.00", "currency": "USD"},
        "principal_or_agent": "AGENT",
    }
    with pytest.raises(ValidationError):
        payloads.BillingRecordedV1.model_validate({**taxed, "tax_lines": [line]})
    assert payloads.BillingRecordedV1.model_validate(
        {**taxed, "tax_lines": [line, {**line, "amount": {"amount": "6.00", "currency": "USD"}}]}
    )


def test_booking_payload_rules() -> None:
    booked = payloads.ContractBookedV1.model_validate(booking())
    assert (booked.has_commercial_substance, booked.scope_605_35) == (True, False)
    assert [line.obligation_key for line in booked.lines] == ["O1", "O2"]
    assert booked.customer_id == UUID(CUSTOMER_ID)
    # ux_obligation__key: keys are unique within the booking.
    lines = booking()["lines"]
    with pytest.raises(ValidationError) as excinfo:
        payloads.ContractBookedV1.model_validate(
            booking(lines=[lines[0], {**lines[1], "obligation_key": "O1"}])
        )
    assert "obligation keys repeat" in str(excinfo.value)
    # One of customer_id or customer; at least one line; non-zero quantities (REQ-DAT-005).
    without_customer = {key: value for key, value in booking().items() if key != "customer_id"}
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(without_customer)
    assert payloads.ContractBookedV1.model_validate(
        {
            **without_customer,
            "customer": {"code": "C-01", "name": "Pellworth Logistics Inc. (Demo)"},
        }
    )
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(booking(lines=[]))
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(booking(lines=[{**lines[0], "quantity": "0"}]))
    # A bundle parent names a line; the payment schedule ascends.
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(
            booking(lines=[lines[0], {**lines[1], "bundle_parent_obligation_key": "O9"}])
        )
    point = {"date": "2026-02-01", "amount": {"amount": "1000.00", "currency": "USD"}}
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(booking(payment_schedule=[point, point]))
    with pytest.raises(ValidationError):
        payloads.ContractBookedV1.model_validate(booking(submit_for_activation=True))


def test_parse_payload_upcast_and_stored_form() -> None:
    parsed = payloads.parse_payload(ContractEventType.DELIVERY_RECORDED, 1, DELIVERY)
    assert isinstance(parsed, payloads.DeliveryRecordedV1)
    assert payloads.upcast(ContractEventType.DELIVERY_RECORDED, 1, DELIVERY) == (1, DELIVERY)
    for version in (0, 2):
        with pytest.raises(ValueError):
            payloads.upcast(ContractEventType.DELIVERY_RECORDED, version, DELIVERY)
    stored = payloads.payload_json(payloads.ContractBookedV1.model_validate(booking()))
    assert stored["customer_id"] == CUSTOMER_ID
    assert (stored["inception_date"], stored["customer"], stored["payment_schedule"]) == (
        "2026-01-01",
        None,
        [],
    )
    assert stored["lines"][0]["total_price"] == {"amount": "120000.00", "currency": "USD"}
    assert stored["lines"][0]["scope_flag"] == "IN_SCOPE_606"
    # The stored form validates again as the same payload.
    assert payloads.parse_payload(ContractEventType.CONTRACT_BOOKED, 1, stored) == (
        payloads.ContractBookedV1.model_validate(booking())
    )


def test_memo_updated_presence_set_round_trips_and_older_form_has_none() -> None:
    """CV-47 (a) / 04 §16.3 (Codex T1F2-MEMO-R1): ``named`` survives the stored form — the omitted
    siblings serialize as null, so only ``named`` tells a clear from an omission — and a stored V1
    body without it parses with ``named`` None (read as strings replace, nulls are omissions)."""
    payload = payloads.MemoUpdatedV1(obligation_key="POB #1", memo_2=None, named=("memo_2",))
    body = payloads.payload_json(payload)
    assert body["named"] == ["memo_2"]
    assert body["memo_1"] is None and body["memo_2"] is None and body["memo_3"] is None
    parsed = payloads.MemoUpdatedV1.model_validate(body)
    assert parsed.named == ("memo_2",) and parsed.memo_2 is None
    older = payloads.MemoUpdatedV1.model_validate(
        {"obligation_key": "POB #1", "memo_1": "Delivery 1", "memo_2": None, "memo_3": None}
    )
    assert older.named is None
    with pytest.raises(ValidationError):
        payloads.MemoUpdatedV1(obligation_key="POB #1", named=("memo_9",))  # type: ignore[arg-type]
