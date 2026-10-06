"""``ENGINE`` mode receivables of a foreign-currency entity: JET-03 and JET-10a′ (L6-5; FX-CHK-083).

Stage 14 posts JET-03 per obligation and S14-R-01 takes its functional amount from stage 12, but the
book loop bound no receivable flows (L3-2-Q-14), so a EUR invoice of a USD entity in ``ENGINE``
billing mode raised ``ENGINE_INVARIANT_VIOLATED`` "stage 12 publishes no functional amount for a
foreign-currency part target", and stage 12 never remeasured the receivable (POLICIES CHK-083).
The book loop now binds the S10-R-19 receivable movements of such an entity; stage 12 creates the
receivable at spot, apportions it over the obligations' billing and publishes the JET-03 functional
targets, and T-CON-09 takes the remeasured receivable. These tests run the answer-key worlds without
a database.
"""

from __future__ import annotations

import decimal
from collections.abc import Callable
from datetime import date
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import OutputBundle
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.stages import s13_books
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.state import BookContext
from support import intent_totals
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

FX_083 = "FX-CHK-083-ENGINE-RECEIVABLE-REMEASUREMENT"
CANCELLABLE = "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE"
AR, CL, GAIN_LOSS = "ACCOUNTS_RECEIVABLE", "CONTRACT_LIABILITY", "FX_GAIN_LOSS"


def _bundle(key_id: str, family: str, index: int = 0) -> tuple[object, str]:
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = _build_checkpoint_bundles(loaded)[index]
    (bundle,) = checkpoint.bundles
    return bundle, checkpoint.book


def _lines(output: OutputBundle, book_code: str, kind: str) -> list[tuple[str, str, str, int, int]]:
    """(period, class, role, signed txn, signed functional) of the book's ``kind`` intents."""
    (book,) = [item for item in output.books if item.book_code == book_code]
    return sorted(
        (
            intent.posting_period_key,
            intent.posting_class,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
            line.amount_functional if line.side == "D" else -line.amount_functional,
        )
        for intent in book.posting_intents
        if intent.entry_kind == kind and intent.posting_period_key == "FY2026-P01"
        for line in intent.lines
    )


def test_l6_5_foreign_engine_invoice_posts_jet_03_and_remeasures_the_receivable() -> None:
    """FX-CHK-083 `january-close`: EUR 12,000.00 invoiced on 1 January at spot 1.1000 posts JET-03
    Dr ACCOUNTS_RECEIVABLE / Cr CONTRACT_LIABILITY USD 13,200.00 at compute; the pass remeasures the
    open receivable at the January closing 1.1200 (JET-10a′ 240.00), and T-CON-09 holds the
    receivable at USD 13,440.00."""
    bundle, book = _bundle(FX_083, "fx")
    command = cast(OutputBundle, erev_engine.compute(bundle))
    assert _lines(command, book, "BILLING") == [
        ("FY2026-P01", "EVENT", AR, 1200000, 1320000),
        ("FY2026-P01", "EVENT", CL, -1200000, -1320000),
    ]
    with decimal.localcontext(DECIMAL_CONTEXT):
        remeasured = intent_totals.close_pass(bundle, [command], "FX_REMEASUREMENT")
    assert _lines(remeasured, book, "FX_REMEASUREMENT") == [
        ("FY2026-P01", "TIME", AR, 0, 24000),
        ("FY2026-P01", "TIME", GAIN_LOSS, 0, -24000),
    ]
    (output_book,) = [item for item in command.books if item.book_code == book]
    (row,) = [item for item in output_book.balances if item.period_key == "FY2026-P01"]
    assert row.columns["accounts_receivable_txn"] == 1200000
    assert row.columns["accounts_receivable_functional"] == 1344000


def test_l6_5_receivable_flows_tie_to_the_stage_10_receivable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JE-CHK-024 case A (cancellable invoice, then a receipt; USD): the receivable flows the book
    loop derives for an entity reproduce S10-R-19 at every period end, invoices less receipts and
    credit memos applied; with the default entity selection a same-currency book binds none."""
    captured: list[tuple[BookContext, CostLossState]] = []
    original: Callable[[BookContext, CostLossState], s13_books.CostsView] = s13_books.costs_view

    def capture(ctx: BookContext, st: CostLossState) -> s13_books.CostsView:
        captured.append((ctx, st))
        return original(ctx, st)

    monkeypatch.setattr(s13_books, "costs_view", capture)
    bundle, book = _bundle(CANCELLABLE, "je", index=-1)
    erev_engine.compute(bundle)
    ctx, st = next(item for item in captured if str(item[0].book_code) == book)
    balances = st.balances
    targets = [
        item for item in balances.accounts_receivable if item.measure == "accounts_receivable"
    ]
    assert targets, "the world posts billing in ENGINE mode"
    entities = {item.entity for item in targets}
    flows = s13_books._receivable_flows(ctx, st.allocated, balances, entities=entities)
    assert {flow.kind for flow in flows} == {"INVOICE", "REDUCTION"}
    ends = {
        period.period_key: period.end_date
        for view in ctx.entities.values()
        for period in view.periods
    }
    for target in targets:
        end: date = ends[target.period_key]
        signed = sum(
            flow.amount if flow.kind == "INVOICE" else -flow.amount
            for flow in flows
            if flow.effective_date <= end and flow.subject_key == target.subject_key
        )
        assert signed == target.value, target.period_key
    assert s13_books._receivable_flows(ctx, st.allocated, balances) == ()
