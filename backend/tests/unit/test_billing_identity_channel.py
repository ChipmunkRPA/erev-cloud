"""The channel's S10-R-07 repeat rule (``erev_api.domain.contracts.events``) agrees with the
kernel (``erev_engine.billing_identity``): one identity rule, one home (D-91; 04 table 15.4-B
rev 1.45; D-97 (30)). CPU only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from erev_api.domain.contracts import events
from erev_api.enums import ContractEventType
from erev_api.events.payloads import CreditMemoRecordedV1, DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.money import MoneyIn
from erev_engine import billing_identity


class _Event:
    """A canonical-looking event for the kernel iterator."""

    def __init__(self, key: str, payload: dict[str, Any]) -> None:
        self.event_key = key
        self.contract_key = "C"
        self.event_type = "BILLING_RECORDED"
        self.effective_date = date(2026, 9, 1)
        self.payload = payload
        self.order_key = (self.effective_date, int(key), key)


def _line(amount: str, key: str | None, cancellable: object = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "invoice_number": "INV-1",
        "line_external_id": "1",
        "amount": amount,  # the kernel reads a text amount; the channel reads text or Money
    }
    if key is not None:
        payload["obligation_key"] = key
    if cancellable is not None:
        payload["is_cancellable"] = cancellable
    return payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), ("true", True), (False, False), ("false", False), (None, False), (1, False),
     ("TRUE", False), ("yes", False)],
)  # fmt: skip
def test_is_cancellable_literal_rule_read_from_the_kernel(value: object, expected: bool) -> None:
    payload = _line("100.00", "O1", value)
    view = events.PayloadView(payload)
    assert billing_identity.is_cancellable(view) is expected
    first = events.first_line(_line("100.00", "O1"))
    finding = events.repeat_finding(first, payload)
    assert (finding == ("invoice_number", events.IDENTITY_REPEATED)) is expected


MISMATCH = "INVOICE_STATUS_UPDATE_MISMATCH"
REPEATED = "INVOICE_IDENTITY_REPEATED"


@pytest.mark.parametrize(
    ("first", "repeat", "expected"),
    [
        (_line("100.00", "O1"), _line("100.00", "O1"), None),
        (_line("100.00", "O1"), _line("100.00", None), None),
        (_line("100.00", None), _line("100.00", "O2"), None),
        (_line("100.00", "O1"), _line("100.00", "O2"), ("obligation_key", MISMATCH)),
        (_line("100.00", "O1"), _line("120.00", "O1"), ("amount", MISMATCH)),
        (_line("100.00", "O1"), _line("120.00", "O2"), ("amount", MISMATCH)),
        (_line("100.00", "O1"), _line("100.00", "O2", "true"), ("invoice_number", REPEATED)),
        (_line("100.00", "O1"), _line("100.00", "O1", "false"), None),
    ],
)
def test_repeat_finding_matches_kernel_classification(
    first: dict[str, Any], repeat: dict[str, Any], expected: tuple[str, str] | None
) -> None:
    channel = events.repeat_finding(events.first_line(first), repeat)
    assert channel == expected
    [line, update] = list(
        billing_identity.iter_billing_lines([_Event("1", first), _Event("2", repeat)])
    )
    assert not line.is_status_update
    if expected == ("invoice_number", REPEATED):
        assert not update.is_status_update  # the kernel keeps it as another line (stored history)
        return
    assert update.is_status_update and update.line is line.event
    # The kernel flags every mismatch; the channel names the amount first, else the obligation.
    amount_differs = first["amount"] != repeat["amount"]
    keys_differ = (
        first.get("obligation_key") is not None
        and repeat.get("obligation_key") is not None
        and first["obligation_key"] != repeat["obligation_key"]
    )
    assert (update.amount_mismatch, update.obligation_mismatch) == (amount_differs, keys_differ)
    assert (channel is not None) is (amount_differs or keys_differ)
    if channel is not None:
        assert channel[0] == ("amount" if amount_differs else "obligation_key")


def test_first_line_reads_money_payloads() -> None:
    first = events.first_line(
        {"invoice_number": "INV-1", "line_external_id": "1",
         "amount": {"amount": "54000.00", "currency": "EUR"}, "obligation_key": "O1"}
    )  # fmt: skip
    assert (first.amount, first.currency, first.obligation_key) == (
        Decimal("54000.00"),
        "EUR",
        "O1",
    )
    assert events.line_identity({"invoice_number": "INV-1", "line_external_id": "1"}) == (
        "INV-1",
        "1",
    )
    assert events.line_identity({}) == ("", "")


def _ledger(**buckets: dict[str, Decimal]) -> events._Ledger:
    """A channel ledger of contract C with O1 booked; ``buckets`` seed billed / credited. The
    ledger's quantities are the quantities in force (04 §16.3 rev 1.232): here the booked ones,
    with no obligation ended."""
    from collections import defaultdict

    ledger = events._Ledger(
        external_id="C",
        currency="EUR",
        in_force={"O1": Decimal("10"), "O9": Decimal("5")},
        ended=frozenset(),
        products={"O1": "P1", "O9": "P9"},
        delivered=defaultdict(Decimal),
        returned=defaultdict(Decimal),
        billed=defaultdict(Decimal),
        credited=defaultdict(Decimal),
        lines={},
        vc=frozenset(),
        keys_by_id={},
    )
    for name, values in buckets.items():
        getattr(ledger, name).update(values)
    return ledger


def _credit(key: str, amount: str) -> EventIn:
    return EventIn(
        event_type=ContractEventType.CREDIT_MEMO_RECORDED,
        effective_date=date(2026, 9, 12),
        payload=CreditMemoRecordedV1(
            credit_memo_number="CM-1",
            credited_invoice_number="INV-1",
            obligation_key=key,
            amount=MoneyIn(amount=amount, currency="EUR"),
            issue_date=date(2026, 9, 12),
        ),
        obligation_keys=(key,),
    )


def test_codex_1150_bound_reads_never_create_buckets() -> None:
    """Codex packet 1150 ``credit_100_credited`` (VOID-3c native retest 12 / 13): after EUR 100.00
    billed on O1 (the same-identity status update adds nothing), a 150.00 credit is refused and a
    100.00 credit is folded — and the credited map is exactly ``{"O1": 100.00}``: no empty-string
    contract bucket appears as a side effect of the cover lookup, and no bucket is created by any
    read. Reads use ``.get``; only folds write."""
    ledger = _ledger(billed={"O1": Decimal("100.00")})
    ledger.lines[("INV-1", "1")] = events.FirstLine(Decimal("100.00"), "EUR", "O1")
    refused = events._bound_finding(ledger, 0, _credit("O1", "150.00"))
    assert refused is not None and refused.rule_id == events.REFUND_EXCEEDS
    assert dict(ledger.credited) == {} and set(ledger.billed) == {"O1"}
    assert events._bound_finding(ledger, 0, _credit("O1", "100.00")) is None
    assert dict(ledger.credited) == {"O1": Decimal("100.00")}
    assert set(ledger.billed) == {"O1"}  # no "" bucket from the referenced-cover read
    assert dict(ledger.delivered) == {} and dict(ledger.returned) == {}
    delivery = EventIn(
        event_type=ContractEventType.DELIVERY_RECORDED,
        effective_date=date(2026, 9, 12),
        payload=DeliveryRecordedV1(obligation_key="O9", quantity="1", trigger="DELIVERY"),
        obligation_keys=("O9",),
    )
    assert events._bound_finding(ledger, 1, delivery) is None
    assert dict(ledger.delivered) == {"O9": Decimal("1")} and dict(ledger.returned) == {}
