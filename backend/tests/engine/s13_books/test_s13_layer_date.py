"""The POL-160 layer date of an invoice in ``ERP`` billing mode (D-87 L6-5-Q-14; FX-POL-160).

Under ``EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE`` (forced in the IFRS15 book) S12-R-04 dates a
billing layer at the earlier of "unconditional due" and the first receipt applied to the invoice. In
``ERP`` mode "unconditional due" is the payload ``due_date`` when present, else the S10-R-06 date
(606-10-55-284, noncancellable); ``ENGINE`` mode keeps the S10-R-06 date. The book loop passed the
S10-R-06 date, which in ``ERP`` mode is the issue date, and never filled the first receipt, so the
IFRS15 layer of FX-POL-160 took the 1 January spot (1.0900) instead of the 10 January receipt
(1.1000). These tests run the answer-key worlds without a database.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import OutputBundle
from erev_engine.stages import s13_books
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities.layers import ControlFlow
from erev_engine.stages.state import AllocatedState, BookContext, Target
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

FX_160 = "FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15"
CANCELLABLE = "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE"


def _bundle(key_id: str, family: str, index: int) -> tuple[object, str]:
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = _build_checkpoint_bundles(loaded)[index]
    (bundle,) = checkpoint.bundles
    return bundle, checkpoint.book


def _compute(
    monkeypatch: pytest.MonkeyPatch, key_id: str, family: str, index: int
) -> tuple[str, list[tuple[BalanceState, ControlFlow]], OutputBundle]:
    """Compute a checkpoint and capture the billing control flows of its book with their state."""
    captured: list[tuple[str, BalanceState, tuple[ControlFlow, ...]]] = []
    original = s13_books._control_flows

    def capture(
        ctx: BookContext, allocated: AllocatedState, st: BalanceState, relief: Sequence[Target]
    ) -> tuple[ControlFlow, ...]:
        flows = original(ctx, allocated, st, relief)
        captured.append((str(ctx.book_code), st, flows))
        return flows

    monkeypatch.setattr(s13_books, "_control_flows", capture)
    bundle, book = _bundle(key_id, family, index)
    output = cast(OutputBundle, erev_engine.compute(bundle))
    billing = [
        (st, flow)
        for code, st, flows in captured
        if code == book
        for flow in flows
        if flow.kind == "BILLING"
    ]
    return book, billing, output


def _liability_functional(output: OutputBundle, book: str, period_key: str) -> int:
    (output_book,) = [item for item in output.books if item.book_code == book]
    (row,) = [item for item in output_book.balances if item.period_key == period_key]
    return int(row.columns["contract_liability_functional"])


@pytest.mark.parametrize(
    ("index", "book", "functional"),
    [(0, "ASC606", 981000), (1, "IFRS15", 990000)],
)
def test_l7_6_erp_invoice_layer_date_from_due_date_and_first_receipt(
    monkeypatch: pytest.MonkeyPatch, index: int, book: str, functional: int
) -> None:
    """FX-POL-160: EUR 12,000.00 invoiced on 1 January, due 31 January, received 10 January, ERP
    mode. The billing flow carries the due date and the first receipt; the ASC606 book keeps its
    INVOICE_ISSUE_DATE election (USD 9,810.00 at 31 March) and the IFRS15 book layers at the
    receipt (USD 9,900.00)."""
    found, billing, output = _compute(monkeypatch, FX_160, "fx", index)
    assert found == book
    assert [
        (flow.effective_date, flow.unconditional_date, flow.first_receipt_date)
        for _, flow in billing
    ] == [(date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 10))]
    # S10-R-06 still governs the balances: the ERP invoice is unconditional at issue.
    (st, _) = billing[0]
    assert [line.unconditional_date for doc in st.documents for line in doc.lines] == [
        date(2026, 1, 1)
    ]
    assert _liability_functional(output, book, "FY2026-P03") == functional


def test_l7_6_engine_invoice_keeps_the_s10_r06_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """JE-CHK-024 case A (ENGINE mode, cancellable invoice due 31 January, paid 1 March): the flow
    keeps the S10-R-06 date (1 March), not the payload due date, and names the first receipt."""
    _, billing, _ = _compute(monkeypatch, CANCELLABLE, "je", -1)
    assert billing
    for st, flow in billing:
        (document,) = [doc for doc in st.documents if doc.document_key == flow.source_key]
        assert {line.mode for line in document.lines} == {"ENGINE"}
        s10_dates = [line.unconditional_date for line in document.lines if line.unconditional_date]
        assert flow.unconditional_date == min(s10_dates) == date(2026, 3, 1)
        assert flow.first_receipt_date == date(2026, 3, 1)
