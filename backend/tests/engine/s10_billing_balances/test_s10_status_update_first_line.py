"""Policy edge A: a status update dates the identity's first-seen line only (S10-R-07; D-91).

Supervisor reading (ENG-B4 dispatch): "the update applies to the identity's FIRST-SEEN line (it
'keeps the first line's attribution'); the later cancellable repeats stay new lines and remain
cancellable until they receive their own update or payment". ENGINE_SPEC_B S10-R-07 (:808): a
status update "never changes the first line's attribution"; the kernel records "a status update
with its first line" (``billing_identity.iter_billing_lines``). On 0104e86 stage 10 kept the
update per identity key, so every cancellable line of the identity, the first-seen line and each
repeat flagged cancellable alike, took the update as its S10-R-06 unconditional source, even a
repeat of another amount that the §10.2.2 pseudocode (same-amount updates only) would not date.
World: JE-CHK-024 case A with the cancellable INV-38A-1 / INV-38A-1-1 at 600.00 (31 January), a
cancellable repeat of the same identity for 400.00 on 5 February (a new line, D-91 C606-01 (2)), a
same-amount (600.00) noncancellable update on 20 February, the 1,000.00 receipt applied on 1
March and the delivery on 31 March. Public compute; no database.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.stages import s13_books
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities.layers import ControlFlow
from erev_engine.stages.state import AllocatedState, BookContext, Target
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    journal,
    period_balance,
    replace_payload,
    with_events,
)

A38 = ("je", "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE", "march-close")
JAN_31, FEB_5, FEB_20, MAR_1 = (
    date(2026, 1, 31),
    date(2026, 2, 5),
    date(2026, 2, 20),
    date(2026, 3, 1),
)
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
AR, CL = "ACCOUNTS_RECEIVABLE", "CONTRACT_LIABILITY"
JET_03 = "BILLING"


def _world(repeat_amount: str = "400.00") -> tuple[InputBundle, str, str, str]:
    base = checkpoint_bundle(*A38)
    bill = first_billing(base)
    base = replace_payload(base, bill.event_key, amount=Decimal("600.00"))
    repeat = billing_after(
        base, first_billing(base), FEB_5, cancellable=True, amount=Decimal(repeat_amount)
    )
    base = with_events(base, repeat)
    update = billing_after(base, first_billing(base), FEB_20, cancellable=False)
    return with_events(base, update), bill.event_key, repeat.event_key, update.event_key


def _compute(
    monkeypatch: pytest.MonkeyPatch, bundle: InputBundle
) -> tuple[BookOutput, BalanceState, list[tuple[int, date, date | None, date | None, str]]]:
    captured: list[tuple[BalanceState, tuple[ControlFlow, ...]]] = []
    original = s13_books._control_flows

    def capture(
        ctx: BookContext, allocated: AllocatedState, st: BalanceState, relief: Sequence[Target]
    ) -> tuple[ControlFlow, ...]:
        flows = original(ctx, allocated, st, relief)
        captured.append((st, flows))
        return flows

    monkeypatch.setattr(s13_books, "_control_flows", capture)
    book = compute_book(bundle)
    st, flows = captured[-1]
    billing = sorted(
        (f.amount, f.effective_date, f.unconditional_date, f.first_receipt_date, f.source_key)
        for f in flows
        if f.kind == "BILLING"
    )
    return book, st, billing


def test_status_update_dates_the_first_seen_line_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 20 February update dates the 600.00 first-seen line (S10-R-06 20 February); the 400.00
    cancellable repeat stays memo-only until the 1 March receipt applied to the invoice dates it.
    NP 0 / 600 / 0; JET-03 600.00 in February and 400.00 in March; CL 0.00 / 600.00 / 0.00; one
    flow per line, each dated the day it became billing (policy edge B ruling), with its own
    lineage. On 0104e86 both lines took
    the update: NP 1,000 in February, JET-03 1,000.00 in February, none in March."""
    bundle, first, repeat, update = _world()
    book, st, flows = _compute(monkeypatch, bundle)
    lines = {line.event.event_key: line for doc in st.documents for line in doc.lines}
    assert set(lines) == {first, repeat}  # the update is a status update, not a line
    assert (lines[first].unconditional_date, lines[repeat].unconditional_date) == (FEB_20, MAR_1)
    assert lines[first].unconditional_source is not None
    assert lines[first].unconditional_source.event_key == update
    assert {t.period_key: t.value for t in st.positions} == {P01: 0, P02: 60_000, P03: 0}
    assert flows == [
        (40_000, MAR_1, MAR_1, MAR_1, repeat),
        (60_000, FEB_20, FEB_20, MAR_1, first),
    ]
    assert journal(book, JET_03, P01) == []
    assert journal(book, JET_03, P02) == [(AR, "D", 60_000), (CL, "C", 60_000)]
    assert journal(book, JET_03, P03) == [(AR, "D", 40_000), (CL, "C", 40_000)]
    assert [period_balance(book, p, "contract_liability_txn") for p in (P01, P02, P03)] == [
        0,
        60_000,
        0,
    ]
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 100_000


def test_same_amount_repeat_is_not_dated_by_the_first_lines_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the repeat also at 600.00 (a same-amount cancellable repeat, the case where the
    §10.2.2 per-identity, same-amount pseudocode would date both lines), the ruling still dates
    the first-seen line only: NP 600 in February, 1,200 − 1,000 = 200 in March after the receipt
    dates the repeat and the delivery recognises 1,000.00."""
    bundle, first, repeat, _update = _world("600.00")
    book, st, flows = _compute(monkeypatch, bundle)
    lines = {line.event.event_key: line for doc in st.documents for line in doc.lines}
    assert (lines[first].unconditional_date, lines[repeat].unconditional_date) == (FEB_20, MAR_1)
    assert {t.period_key: t.value for t in st.positions} == {P01: 0, P02: 60_000, P03: 20_000}
    assert [f[:3] for f in flows] == [(60_000, FEB_20, FEB_20), (60_000, MAR_1, MAR_1)]
    assert journal(book, JET_03, P02) == [(AR, "D", 60_000), (CL, "C", 60_000)]
    assert journal(book, JET_03, P03) == [(AR, "D", 60_000), (CL, "C", 60_000)]
