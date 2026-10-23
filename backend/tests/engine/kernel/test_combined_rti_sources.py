"""Combined pricing retains original rates, source precedence and event identity."""

from datetime import date
from fractions import Fraction

import pytest
from support.recognition import event_view

from erev_engine import usage

AT = date(2026, 1, 31)


def realised(events, *, rates):
    return usage.right_to_invoice(
        events,
        contract_key="C",
        obligation_key="SERVICE",
        subject_key="C/SERVICE",
        component_keys=("LEASE", "SERVICE"),
        booking={"lines": [{"obligation_key": key, "unit_price": rate} for key, rate in rates]},
        at=AT,
        admits=lambda ev: True,
    )


def event(number, kind, key, **payload):
    return event_view("C", number, kind, AT, {"obligation_key": key, **payload})


def test_original_rates_ignore_advance_billing_and_apply_returns():
    events = (
        event(1, "BILLING_RECORDED", "LEASE", amount="9000"),
        event(2, "DELIVERY_RECORDED", "SERVICE", quantity="3"),
        event(3, "DELIVERY_RECORDED", "LEASE", quantity="2"),
        event(4, "RETURN_RECORDED", "SERVICE", quantity="1"),
    )
    rates = (("LEASE", "200"), ("SERVICE", "50"))
    assert realised(events[:1], rates=rates).amount == 0
    result = realised(events, rates=rates)
    assert [item.amount for item in result.items] == [Fraction(150), Fraction(400), Fraction(-50)]
    assert result.amount == 500
    assert [item.event_key for item in result.items] == [ev.event_key for ev in events[1:]]


def test_shared_event_is_counted_once_and_conflicting_rates_are_rejected():
    shared = event_view(
        "C",
        1,
        "DELIVERY_RECORDED",
        AT,
        {"quantity": "2"},
        obligation_keys=("LEASE", "SERVICE"),
    )
    assert realised((shared,), rates=(("LEASE", "50"), ("SERVICE", "50"))).amount == 100
    with pytest.raises(ValueError, match="different priced amounts"):
        realised((shared,), rates=(("LEASE", "50"), ("SERVICE", "100")))


def test_rated_component_does_not_hide_other_components_net_invoices():
    events = (
        event(1, "USAGE_REPORTED", "LEASE", rated_amount="200"),
        event(2, "BILLING_RECORDED", "LEASE", amount="200"),
        event(3, "BILLING_RECORDED", "SERVICE", amount="120", tax_amount="20"),
        event(4, "CREDIT_MEMO_RECORDED", "SERVICE", amount="30"),
    )
    result = realised(events, rates=())
    assert result.amount == 290
    assert [item.event_key for item in result.items] == [events[i].event_key for i in (0, 2, 3)]
