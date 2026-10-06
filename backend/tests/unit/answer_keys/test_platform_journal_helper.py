"""The journal summariser's grain: (contract, account, transaction currency), aligned with the
domain journal grouping that preserves currency (POL-006; ``journals/summarise.py``). Codex
platform review of ca2e82c, helper observation (record §14); lane F-RPS + ENG-E1.

Balanced USD and EUR posting intents with a common USD functional currency keep one line per
(account, currency); a currency-blind (contract, account) net made them disappear.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from erev_engine.bundle import IntentLine, PostingIntent
from support.answer_keys.platform_runner import summarise_intents

PERIOD = "FY2023-P01"


def _line(key: str, side: str, role: str, account: str, currency: str, amount: int) -> IntentLine:
    return IntentLine(
        line_key=key,
        side=side,
        account_role=role,
        clearing_purpose=None,
        counterparty_entity=None,
        account_code=account,
        amount_txn=amount,
        amount_functional=amount,
        txn_currency=currency,
        functional_currency="USD",
        dimensions={},
        source_event_key=None,
        trace_node_id="t",
    )


def _intent(entry_key: str, currency: str, amount: int) -> PostingIntent:
    return PostingIntent(
        entry_key=entry_key,
        book_code="ASC606",
        entity="ME1",
        posting_period_key=PERIOD,
        origin_period_key=None,
        entry_kind="REVENUE_RECOGNITION",
        posting_class="EVENT",
        subject_key="C-1/L1",
        reason_code=None,
        lines=(
            _line(f"{entry_key}/1", "D", "CONTRACT_LIABILITY", "21001", currency, amount),
            _line(f"{entry_key}/2", "C", "REVENUE", "5001", currency, amount),
        ),
    )


def test_journal_helper_nets_per_transaction_currency() -> None:
    entries = [
        ("CG-1", ("C-1",), _intent("E1", "USD", 100)),
        ("CG-1", ("C-1",), _intent("E2", "EUR", 100)),
    ]
    lines = summarise_intents(entries, entity="ME1", period_key=PERIOD, per_contract=False)
    assert {(line.account, line.currency): line.net for line in lines} == {
        ("21001", "USD"): Fraction(1),
        ("21001", "EUR"): Fraction(1),
        ("5001", "USD"): Fraction(-1),
        ("5001", "EUR"): Fraction(-1),
    }
    # A same-currency reversal nets away; the other currency stays.
    usd = _intent("E1", "USD", 100)
    flipped = replace(
        usd,
        entry_key="E3",
        lines=tuple(replace(line, side="C" if line.side == "D" else "D") for line in usd.lines),
    )
    lines = summarise_intents(
        [*entries, ("CG-1", ("C-1",), flipped)], entity="ME1", period_key=PERIOD, per_contract=False
    )
    assert {(line.account, line.currency): line.net for line in lines} == {
        ("21001", "EUR"): Fraction(1),
        ("5001", "EUR"): Fraction(-1),
    }
    # Other entities and periods never enter.
    other = replace(_intent("E4", "USD", 100), entity="ME2")
    assert (
        summarise_intents(
            [("CG-1", ("C-1",), other)], entity="ME1", period_key=PERIOD, per_contract=False
        )
        == ()
    )


def test_helper_1_journal_totals_are_qualified_per_transaction_currency() -> None:
    """F-RPS-HELPER-1 (Codex retest of e0652b9): with mixed-currency lines the scalar totals must
    not sum across currencies at the first line's precision (``dr 2.00`` / ``cr 2.00``); one debit
    and one credit total per transaction currency, each at its own precision, balanced per
    currency. Single-currency runs keep their figures (DLT 240.22 unchanged elsewhere)."""
    from support.answer_keys.platform_runner import journal_totals

    entries = [
        ("CG-1", ("C-1",), _intent("E1", "USD", 100)),
        ("CG-1", ("C-1",), _intent("E2", "EUR", 100)),
    ]
    lines = summarise_intents(entries, entity="ME1", period_key=PERIOD, per_contract=False)
    assert len(lines) == 4
    assert journal_totals(lines) == {
        "debits EUR": "dr 1.00",
        "credits EUR": "cr 1.00",
        "balanced EUR": "true",
        "debits USD": "dr 1.00",
        "credits USD": "cr 1.00",
        "balanced USD": "true",
    }
    jpy = replace(
        _intent("E3", "JPY", 1200),
        lines=tuple(replace(line, txn_currency="JPY") for line in _intent("E3", "JPY", 1200).lines),
    )
    lines = summarise_intents(
        [("CG-1", ("C-1",), jpy)], entity="ME1", period_key=PERIOD, per_contract=False
    )
    assert journal_totals(lines) == {
        "debits JPY": "dr 1200",
        "credits JPY": "cr 1200",
        "balanced JPY": "true",
    }
    assert journal_totals(()) == {}
