"""The POL-160 layer date of a billing line stays in the accounting period in which the line
enters the position (ENGINE_SPEC_B S12-R-04 rev 1.83, S12-INV-03; POLICIES POL-160, ALG-08 §2.9.1
rev 1.52; supervisor ruling R-81 of 2026-09-30, amending D-87 L6-5-Q-14, to be transcribed as
D-100; precedent D-92 (5); item ENG-S12-DUE-DATE-1; candidate AD-51 for the accountant).

D-87 L6-5-Q-14 dated the contract-liability layer of an ``ERP`` invoice at the earlier of its
payload ``due_date`` and the first receipt naming it, while S10-R-06 kept the position on the issue
date. An invoice on ordinary payment terms — issued in one period, due in the next, not yet paid —
then stood in the position at the period end with no layer behind it: S12-INV-03 failed and the
group was quarantined at every later computation (lane F-RPS-REG measured it on K-07 through the
events route). The mirror needed no due date: a receipt dated in an earlier period than the line it
names put the layer before the position, in either billing mode.

The rule: a POL-160 date in a later period than the line's S10-R-06 date gives the end of that
period; a date in an earlier period gives the S10-R-06 date; inside the period nothing changes.
"Due beyond the period end" therefore computes exactly as "due on the period end", a shape that
always computed, and a same-currency figure does not depend on the layer date at all.

Worlds (frozen answer-key checkpoints edited in memory, ``support.billing_lines``; no database):
FX-POL-160 (``ERP``; EUR 12,000.00 issued 1 January, USD entity, monthly periods to March; ASC606
elects ``INVOICE_ISSUE_DATE``, IFRS15 is forced to the earlier-of option; spot 1.0900 on 1 January,
1.1000 on 10 January, 1.1050 on 31 January; January average 1.1100); JE-CHK-024 cases A and B
(USD, 1,000.00 of 31 January, receipt 1 March; ``ENGINE`` as keyed, ``ERP`` by policy); JE-CHK-023
and FX-CHK-083 (``ENGINE``).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine.bundle import BookOutput, EventInput, InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.stages import s13_books
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities.layers import ControlFlow
from erev_engine.stages.state import AllocatedState, BookContext, Target
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    period_balance,
    replace_payload,
    with_events,
    with_policy,
)

FX_160 = ("fx", "FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15", "ifrs15-march-close")
A38 = ("je", "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE")
B38 = ("je", "JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE")
TAX = ("je", "JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING", "january-close")
FX_083 = ("fx", "FX-CHK-083-ENGINE-RECEIVABLE-REMEASUREMENT", "january-close")
EARLIER = "EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE"
JAN_1, JAN_10, JAN_15, JAN_20, JAN_31 = (
    date(2026, 1, 1),
    date(2026, 1, 10),
    date(2026, 1, 15),
    date(2026, 1, 20),
    date(2026, 1, 31),
)
FEB_5, FEB_15, FEB_20, FEB_28 = (
    date(2026, 2, 5),
    date(2026, 2, 15),
    date(2026, 2, 20),
    date(2026, 2, 28),
)
MAR_1, MAR_2, APR_30 = date(2026, 3, 1), date(2026, 3, 2), date(2026, 4, 30)
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
QUARTER = (P01, P02, P03)

# (layer date, transaction minor units, functional minor units) of a created liability layer.
Created = tuple[date, int, int]
# (amount, effective date, unconditional due, first receipt, source key) of a BILLING flow.
Flow = tuple[int, date, date | None, date | None, str]


# --- Worlds ---------------------------------------------------------------------------------------


def _without(bundle: InputBundle, event_type: str) -> InputBundle:
    """``bundle`` without its events of ``event_type`` (the last events of their streams here)."""
    return dataclasses.replace(
        bundle, events=tuple(e for e in bundle.events if e.event_type != event_type)
    )


def _only(bundle: InputBundle, event_type: str) -> EventInput:
    (event,) = [e for e in bundle.events if e.event_type == event_type]
    return event


def _moved(bundle: InputBundle, event: EventInput, on: date, **changes: object) -> InputBundle:
    """``event`` re-dated to ``on`` (effective date and record time) with payload ``changes``; a
    ``None`` change removes the member. The bundle is re-sequenced in ENG-06 order with
    non-decreasing record times (``with_events``), so nothing becomes a late event."""
    payload = {k: v for k, v in {**event.payload, **changes}.items() if v is not None}
    new = dataclasses.replace(
        event,
        effective_date=on,
        recorded_at=datetime(on.year, on.month, on.day, 17, tzinfo=UTC),
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )
    rest = dataclasses.replace(
        bundle, events=tuple(e for e in bundle.events if e.event_key != event.event_key)
    )
    return with_events(rest, new)


def _receipt(bundle: InputBundle, bill: EventInput, on: date) -> EventInput:
    """A ``PAYMENT_RECEIVED`` on ``on`` of the invoice's amount, naming the invoice."""
    version = max(e.stream_version for e in bundle.events if e.contract_key == bill.contract_key)
    payload: dict[str, object] = {
        "receipt_reference": f"RCPT-{on.isoformat()}",
        "amount": bill.payload["amount"],
        "receipt_date": on,
        "applied_invoice_numbers": [bill.payload["invoice_number"]],
    }
    return dataclasses.replace(
        bill,
        event_key=f"{bill.contract_key}/EV-{version + 1:06d}",
        stream_version=version + 1,
        event_type="PAYMENT_RECEIVED",
        record_seq=max(e.record_seq for e in bundle.events) + 1,
        effective_date=on,
        recorded_at=datetime(on.year, on.month, on.day, 17, tzinfo=UTC),
        obligation_keys=(),
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )


def _dated(bundle: InputBundle, due: date | None, receipt: date | None) -> InputBundle:
    """``bundle`` with its invoice due on ``due`` (``None``: no due date) and its receipt on
    ``receipt`` (``None``: no receipt); the issue date stays."""
    bill = first_billing(bundle)
    if due is None:
        bundle = _moved(bundle, bill, bill.effective_date, due_date=None)
    else:
        bundle = replace_payload(bundle, bill.event_key, due_date=due)
    paid = _only(bundle, "PAYMENT_RECEIVED")
    if receipt is None:
        return _without(bundle, "PAYMENT_RECEIVED")
    if receipt == paid.effective_date:
        return bundle
    return _moved(bundle, paid, receipt, receipt_date=receipt)


def _fx(due: date | None, receipt: date | None) -> InputBundle:
    """FX-POL-160 with the EUR 12,000.00 invoice of 1 January due on ``due`` and paid on
    ``receipt``."""
    return _dated(checkpoint_bundle(*FX_160), due, receipt)


def _fx_issued(on: date) -> InputBundle:
    """FX-POL-160 with the invoice issued (and due) on ``on``; the receipt of 10 January, which
    names it, stays."""
    base = checkpoint_bundle(*FX_160)
    return _moved(base, first_billing(base), on, issue_date=on, due_date=on)


def _fx_second_line(on: date) -> InputBundle:
    """FX-POL-160 as keyed plus a second line of the same invoice, EUR 1,200.00 without a due
    date, recorded on ``on`` — after the receipt of 10 January that names the invoice."""
    base = checkpoint_bundle(*FX_160)
    second = billing_after(
        base,
        first_billing(base),
        on,
        drop=("due_date",),
        line_external_id="INV-EU-0401-2",
        amount=Decimal("1200.00"),
        issue_date=on,
    )
    return with_events(base, second)


def _example_38_erp(due: date | None, receipt: date | None) -> InputBundle:
    """JE-CHK-024 case A under ``billing.posting`` ``ERP`` (USD contract, USD entity; 1,000.00
    issued 31 January; horizon March): due on ``due``, paid on ``receipt``."""
    base = with_policy(checkpoint_bundle(*A38, "receipt-1-march"), "billing.posting", "ERP")
    return _dated(base, due, receipt)


def _receipt_first(world: tuple[str, str], checkpoint: str, *, erp: bool) -> InputBundle:
    """Example 38 with the receipt re-dated to 20 January and the invoice to 15 February: the
    receipt names an invoice issued in a later period."""
    base = checkpoint_bundle(*world, checkpoint)
    if erp:
        base = with_policy(base, "billing.posting", "ERP")
    base = _moved(base, _only(base, "PAYMENT_RECEIVED"), JAN_20, receipt_date=JAN_20)
    due = None if erp else FEB_15
    return _moved(base, first_billing(base), FEB_15, issue_date=FEB_15, due_date=due)


# --- Reading a computed book ----------------------------------------------------------------------


def _billing_flows(
    monkeypatch: pytest.MonkeyPatch, bundle: InputBundle, book_code: str = "ASC606"
) -> tuple[BookOutput, list[Flow], dict[str, int]]:
    """Compute one book; its BILLING control flows as the book loop emitted them and the stage 10
    net position per period. Every flow's effective date is the S10-R-06 date of its line — the
    date the rule reads as "enters the position"."""
    captured: list[tuple[str, BalanceState, tuple[ControlFlow, ...]]] = []
    original = s13_books._control_flows

    def capture(
        ctx: BookContext, allocated: AllocatedState, st: BalanceState, relief: Sequence[Target]
    ) -> tuple[ControlFlow, ...]:
        flows = original(ctx, allocated, st, relief)
        captured.append((str(ctx.book_code), st, flows))
        return flows

    monkeypatch.setattr(s13_books, "_control_flows", capture)
    book = compute_book(bundle, book_code)
    (state, found) = next(
        (st, flows) for code, st, flows in reversed(captured) if code == book_code
    )
    billing = [flow for flow in found if flow.kind == "BILLING"]
    entered = {
        line.event.event_key: line.unconditional_date
        for document in state.documents
        for line in document.lines
    }
    assert all(flow.effective_date == entered[flow.source_key] for flow in billing)
    flows = sorted(
        (
            flow.amount,
            flow.effective_date,
            flow.unconditional_date,
            flow.first_receipt_date,
            flow.source_key,
        )
        for flow in billing
    )
    return book, flows, {target.period_key: target.value for target in state.positions}


def _created(book: BookOutput) -> list[Created]:
    """The contract-liability layers the book created, in processing order."""
    return [
        (
            date.fromisoformat(str(m.columns["effective_date"])),
            int(str(m.columns["amount_txn"])),
            int(str(m.columns["amount_functional"])),
        )
        for m in book.fx_layer_movements
        if m.columns.get("movement_kind") == "LIABILITY_LAYER_CREATED"
        and m.columns.get("balance_role") == "CONTRACT_LIABILITY"
    ]


def _liability(book: BookOutput, column: str = "contract_liability_functional") -> list[int]:
    return [period_balance(book, period, column) for period in QUARTER]


def _figures(book: BookOutput) -> tuple[object, ...]:
    """Every money figure of a book: balances, layer movements and journal lines."""
    balances = sorted(
        (row.period_key, row.subject_key, tuple(sorted(row.columns.items())))
        for row in book.balances
    )
    movements = [tuple(sorted(m.columns.items())) for m in book.fx_layer_movements]
    journal = sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            intent.subject_key,
            tuple(
                (line.account_role, line.side, line.amount_txn, line.amount_functional)
                for line in intent.lines
            ),
        )
        for intent in book.posting_intents
    )
    return tuple(balances), tuple(movements), tuple(journal)


# --- A due date in a later period than the issue date: foreign currency ---------------------------


@pytest.mark.parametrize(
    ("due", "receipt"),
    [
        pytest.param(FEB_28, None, id="due_next_period_unpaid"),
        pytest.param(FEB_28, FEB_20, id="due_next_period_paid_after_the_period_end"),
        pytest.param(APR_30, None, id="due_beyond_the_horizon"),
    ],
)
def test_erp_due_date_in_a_later_period_layers_at_the_end_of_the_issue_period(
    due: date, receipt: date | None
) -> None:
    """EUR 12,000.00 issued 1 January, due after 31 January and not paid by then. IFRS15 (the
    earlier-of option): the credit is processed on 31 January, after the January release — EUR
    1,000.00 of revenue entered as an asset at the average 1.1100 (USD 1,110.00) and is settled at
    the spot 1.1050 (1,105.00; JET-10a 5.00), and the remaining EUR 11,000.00 layers at 1.1050 =
    USD 12,155.00; contract liability 12,155.00 / 11,050.00 / 9,945.00 at the three closes. Every
    figure of the book is that of the same invoice due ON 31 January, which always computed. The
    ASC606 book elects the issue date and keeps 13,080.00 at 1.0900. Before the rule the IFRS15
    book failed S12-INV-03 at FY2026-P01 (layers −1,000.00, position 11,000.00)."""
    bundle = _fx(due, receipt)
    ifrs = compute_book(bundle, "IFRS15")
    assert _created(ifrs) == [(JAN_31, 1_100_000, 1_215_500)]
    assert _liability(ifrs, "contract_liability_txn") == [1_100_000, 1_000_000, 900_000]
    assert _liability(ifrs) == [1_215_500, 1_105_000, 994_500]
    assert _figures(ifrs) == _figures(compute_book(_fx(JAN_31, None), "IFRS15"))
    asc = compute_book(bundle, "ASC606")
    assert _created(asc) == [(JAN_1, 1_200_000, 1_308_000)]
    assert _liability(asc) == [1_199_000, 1_090_000, 981_000]


def test_erp_due_date_in_a_later_period_on_the_default_option_in_both_books() -> None:
    """The same invoice (due 28 February, unpaid) with the ASC606 book on the default option too:
    both books layer at 31 January and carry the same figures; before the rule the ASC606 book
    failed first."""
    bundle = with_policy(_fx(FEB_28, None), "fx.cl_layer_date", EARLIER)
    asc, ifrs = compute_book(bundle, "ASC606"), compute_book(bundle, "IFRS15")
    assert _created(asc) == _created(ifrs) == [(JAN_31, 1_100_000, 1_215_500)]
    assert _liability(asc) == _liability(ifrs) == [1_215_500, 1_105_000, 994_500]


# --- A due date in a later period: same currency --------------------------------------------------


@pytest.mark.parametrize(
    ("due", "receipt"),
    [
        pytest.param(FEB_15, MAR_1, id="due_next_period"),
        pytest.param(MAR_2, MAR_1, id="due_two_periods_on_paid_a_day_before"),
        pytest.param(MAR_2, None, id="due_two_periods_on_unpaid"),
    ],
)
def test_erp_due_date_in_a_later_period_same_currency_keeps_the_position(
    monkeypatch: pytest.MonkeyPatch, due: date, receipt: date | None
) -> None:
    """USD 1,000.00 issued 31 January in a USD entity, due in February or March. The flow still
    carries the payload due date (D-87 L6-5-Q-14's definition stands); the layer is created on
    31 January, the end of the period in which the position counts the line, so the layers tie to
    the position 1,000.00 at every close and the contract liability is what it is without a due
    date. Before the rule: S12-INV-03 at FY2026-P01 (and P02 when due in March), layers 0 against
    1,000.00."""
    bundle = _example_38_erp(due, receipt)
    bill = first_billing(bundle)
    book, flows, positions = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, JAN_31, due, receipt, bill.event_key)]
    assert positions == {P01: 100_000, P02: 100_000, P03: 100_000}
    assert _created(book) == [(JAN_31, 100_000, 100_000)]
    assert _liability(book, "contract_liability_txn") == [100_000, 100_000, 100_000]
    undated = compute_book(_example_38_erp(None, receipt))
    assert _figures(book) == _figures(undated)


# --- The first receipt in an earlier period than the line it names --------------------------------


@pytest.mark.parametrize(
    ("world", "checkpoint", "erp", "march"),
    [
        pytest.param(A38, "receipt-1-march", True, 100_000, id="erp"),
        pytest.param(B38, "march-close", False, 0, id="engine_noncancellable"),
        pytest.param(A38, "march-close", False, 0, id="engine_cancellable"),
    ],
)
def test_receipt_in_an_earlier_period_layers_when_the_line_enters_the_position(
    monkeypatch: pytest.MonkeyPatch,
    world: tuple[str, str],
    checkpoint: str,
    erp: bool,
    march: int,
) -> None:
    """A receipt of 20 January names an invoice issued on 15 February (no due date in ``ERP``
    mode; due at issue in ``ENGINE`` mode). The position counts the line from 15 February in every
    case — a cancellable ``ENGINE`` line is billing from the later of its own date and the receipt
    (S10-R-06) — so the layer is created on 15 February, not on 20 January: a layer cannot predate
    the contract liability it represents (D-92 (5)). Position 0 / 1,000.00, then 1,000.00 (``ERP``)
    or 0 after the March delivery (``ENGINE``). Before the rule: S12-INV-03 at FY2026-P01, layers
    1,000.00 against 0."""
    bundle = _receipt_first(world, checkpoint, erp=erp)
    bill = first_billing(bundle)
    book, flows, positions = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, FEB_15, FEB_15, JAN_20, bill.event_key)]
    assert positions == {P01: 0, P02: 100_000, P03: march}
    assert _created(book) == [(FEB_15, 100_000, 100_000)]
    assert _liability(book, "contract_liability_txn") == [0, 100_000, march]


def test_receipt_in_an_earlier_period_foreign_currency() -> None:
    """FX-POL-160 with the invoice issued on 5 February and the receipt of 10 January naming it.
    IFRS15 layers on 5 February, when the line enters the position — the date the ASC606 election
    gives — so both books carry the same figures: the January revenue of EUR 1,000.00 is an asset
    at the January close, settled on 5 February at 1.1050, and EUR 11,000.00 layers at 1.1050 =
    USD 12,155.00. Before the rule the IFRS15 book raised "a netting reclass names no open
    contract-asset layer" (S12-R-09) at FY2026-P01."""
    bundle = _fx_issued(FEB_5)
    asc, ifrs = compute_book(bundle, "ASC606"), compute_book(bundle, "IFRS15")
    assert _created(asc) == _created(ifrs) == [(FEB_5, 1_100_000, 1_215_500)]
    assert _liability(ifrs, "contract_liability_txn") == [0, 1_000_000, 900_000]
    assert _liability(asc) == _liability(ifrs) == [0, 1_105_000, 994_500]


def test_later_line_of_a_paid_invoice_layers_when_it_enters_the_position() -> None:
    """FX-POL-160 as keyed (paid on 10 January) plus a second line of the same invoice, EUR
    1,200.00, recorded on 5 February. The invoice's first receipt predates the line; its layer is
    created on 5 February at 1.1050 (USD 1,326.00) in both books, and the first line keeps its own
    layer (ASC606 1 January, 13,080.00; IFRS15 10 January, 13,200.00). Before the rule the IFRS15
    book dated the second layer 10 January and failed S12-INV-03 at FY2026-P01 (layers 12,200.00
    against 11,000.00)."""
    bundle = _fx_second_line(FEB_5)
    asc, ifrs = compute_book(bundle, "ASC606"), compute_book(bundle, "IFRS15")
    assert _created(asc) == [(JAN_1, 1_200_000, 1_308_000), (FEB_5, 120_000, 132_600)]
    assert _created(ifrs) == [(JAN_10, 1_200_000, 1_320_000), (FEB_5, 120_000, 132_600)]
    assert _liability(asc) == [1_199_000, 1_222_600, 1_113_600]
    assert _liability(ifrs) == [1_210_000, 1_232_600, 1_122_600]


# --- Controls: inside the period nothing changes --------------------------------------------------


def test_dates_inside_the_issue_period_keep_the_earlier_of_receipt_and_due_date() -> None:
    """The IFRS15 layer of FX-POL-160 while the governing date lies in January, as before the
    rule: the receipt of 10 January (1.1000, USD 13,200.00) whether the invoice is due on 31
    January or on 28 February; the due date 31 January when nothing is paid (12,155.00 after the
    January release); the receipt of 10 January for an invoice issued on 20 January and for a
    second line recorded on 20 January (the layer predates the line inside the period only)."""
    assert _created(compute_book(_fx(JAN_31, JAN_10), "IFRS15")) == [(JAN_10, 1_200_000, 1_320_000)]
    assert _created(compute_book(_fx(FEB_28, JAN_10), "IFRS15")) == [(JAN_10, 1_200_000, 1_320_000)]
    assert _created(compute_book(_fx(JAN_31, None), "IFRS15")) == [(JAN_31, 1_100_000, 1_215_500)]
    assert _created(compute_book(_fx(None, None), "IFRS15")) == [(JAN_1, 1_200_000, 1_308_000)]
    issued_later = _fx_issued(JAN_20)
    assert _created(compute_book(issued_later, "IFRS15")) == [(JAN_10, 1_200_000, 1_320_000)]
    assert _created(compute_book(issued_later, "ASC606")) == [(JAN_20, 1_200_000, 1_320_000)]
    assert _created(compute_book(_fx_second_line(JAN_20), "IFRS15")) == [
        (JAN_10, 1_200_000, 1_320_000),
        (JAN_10, 120_000, 132_000),
    ]


def test_engine_mode_does_not_read_the_due_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ENGINE`` mode keeps the S10-R-06 date (D-87 L6-5-Q-14): JE-CHK-023 as keyed (issued 15
    January, due 14 February) layers on 15 January; FX-CHK-083 with its due date moved to 28
    February layers on 1 January at 1.1000 (USD 13,200.00), with or without a receipt on 20
    January."""
    tax = checkpoint_bundle(*TAX)
    book, flows, _ = _billing_flows(monkeypatch, tax)
    assert flows == [(100_000, JAN_15, JAN_15, None, first_billing(tax).event_key)]
    assert first_billing(tax).payload["due_date"] == date(2026, 2, 14)
    assert _created(book) == [(JAN_15, 100_000, 100_000)]
    base = checkpoint_bundle(*FX_083)
    bill = first_billing(base)
    unpaid = replace_payload(base, bill.event_key, due_date=FEB_28)
    paid = with_events(unpaid, _receipt(unpaid, bill, JAN_20))
    for bundle, receipt in ((unpaid, None), (paid, JAN_20)):
        book, flows, _ = _billing_flows(monkeypatch, bundle)
        assert flows == [(1_200_000, JAN_1, JAN_1, receipt, bill.event_key)]
        assert _created(book) == [(JAN_1, 1_200_000, 1_320_000)]
