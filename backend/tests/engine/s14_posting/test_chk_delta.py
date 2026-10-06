"""CHK-022 and CHK-020 at engine level: the January 2023 gross and delta journals (END-10).

POLICIES JET-02, JET-06, JET-15 (CHK-020, CHK-022), §6.3; ENGINE_SPEC_B S13-R-08, S13-R-09,
S14-R-23; legacy 06 §5.3; golden GT-04, GT-05, GT-07; D-34. Golden Contracts 1 and 2 through step
04 are computed by the real engine under ``LEGACY_PARITY`` (billing posting ``ERP``) with the books
``ASC606`` (primary) and ``LEGACY``. ``compute`` posts the relief and the JET-15 lines as ``EVENT``
amounts, and a ``CLOSE_RELEASE`` pass ``NETTING_RECLASS`` over those intents adds JET-06 (RCP-08(b);
L3-2-Q-21). The golden streams book without ``CONTRACT_ACTIVATED``, so ``intent_totals`` activates
them at inception (L2-5-Q-38). No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine.bundle import OutputBundle, PostingIntent
from erev_engine.money import decimal_to_minor
from support import intent_totals

START, END = date(2023, 1, 1), date(2023, 1, 31)
JANUARY = "FY2023-P01"
CL, REVENUE, PRE = "CONTRACT_LIABILITY", "REVENUE", "PRE_STANDARD_REVENUE"


def usd(amount: str) -> int:
    return decimal_to_minor(Decimal(amount), 2)


def intents(output: OutputBundle, book: str, period: str = JANUARY) -> list[PostingIntent]:
    (found,) = [item for item in output.books if item.book_code == book]
    return [intent for intent in found.posting_intents if intent.posting_period_key == period]


def lines(items: list[PostingIntent]) -> list[tuple[str, str, str, str, int]]:
    """(obligation dimension, side, role, account, amount) of every line, sorted."""
    return sorted(
        (
            line.dimensions.get("obligation_key", ""),
            line.side,
            line.account_role,
            line.account_code,
            line.amount_txn,
        )
        for intent in items
        for line in intent.lines
    )


def test_chk_022_january_gross() -> None:
    contract_1 = intent_totals.golden("Contract 1", "04")
    contract_2 = intent_totals.golden("Contract 2", "04")
    command, _ = contract_1
    # Contract 1: Dr 21001 CONTRACT_LIABILITY 295.69 / Cr 5001 128.84, 5002 118.53, 5003 48.32.
    relief = intents(command.output, "ASC606")
    assert {(intent.entry_kind, intent.posting_class) for intent in relief} == {
        ("REVENUE_RECOGNITION", "EVENT")
    }
    assert lines(relief) == [
        ("POB #1", "C", REVENUE, "5001", usd("128.84")),
        ("POB #1", "D", CL, "21001", usd("128.84")),
        ("POB #2", "C", REVENUE, "5002", usd("118.53")),
        ("POB #2", "D", CL, "21001", usd("118.53")),
        ("POB #3", "C", REVENUE, "5003", usd("48.32")),
        ("POB #3", "D", CL, "21001", usd("48.32")),
    ]
    # a_t from exact revenue 128.840436, 118.533201 and 48.315164 (legacy 06 §5.2).
    (asc606,) = [item for item in command.output.books if item.book_code == "ASC606"]
    nodes = {node.id: node for node in asc606.trace.nodes}
    for obligation, exact in (("1", "128.840436"), ("2", "118.533201"), ("3", "48.315164")):
        node = nodes[f"revenue_cum:Contract 1/POB %23{obligation}:{JANUARY}"]
        value = Fraction(Decimal(node.value)) + Fraction(Decimal(node.rounding_residue or "0"))
        assert abs(value - Fraction(Decimal(exact))) < Fraction(1, 10**6), obligation
    # Contract 2 (delivery, no billing): Dr 21002 58.85 / Cr 5001 58.85, then JET-06 Dr 15002
    # 58.85 / Cr 21002 58.85; the preset maps CONTRACT_ASSET to the Unbilled A/R account
    # (L2-4-Q-28).
    command_2, reclass_2 = contract_2
    assert lines(intents(command_2.output, "ASC606")) == [
        ("POB #1", "C", REVENUE, "5001", usd("58.85")),
        ("POB #1", "D", CL, "21002", usd("58.85")),
    ]
    (reclass,) = intents(reclass_2.output, "ASC606")
    assert (reclass.entry_kind, reclass.posting_class) == ("NETTING_RECLASS", "TIME")
    assert lines([reclass]) == [
        ("POB #1", "C", CL, "21002", usd("58.85")),
        ("POB #1", "D", "CONTRACT_ASSET", "15002", usd("58.85")),
    ]
    # The summarised batch equals legacy: 21002 nets to zero (TC-JE-01; GT-05).
    gross = intent_totals.totals([*contract_1, *contract_2], start=START, end=END)
    assert gross == {
        ("Contract 1", None, "21001"): usd("295.69"),
        ("Contract 1", "POB #1", "5001"): -usd("128.84"),
        ("Contract 1", "POB #2", "5002"): -usd("118.53"),
        ("Contract 1", "POB #3", "5003"): -usd("48.32"),
        ("Contract 2", None, "15002"): usd("58.85"),
        ("Contract 2", "POB #1", "5001"): -usd("58.85"),
    }
    assert intent_totals.balance(gross) == (usd("354.54"), usd("354.54"))


def test_chk_020_january_delta() -> None:
    computed = [
        *intent_totals.golden("Contract 1", "04"),
        *intent_totals.golden("Contract 2", "04"),
    ]
    # The LEGACY book reverses the pre-standard revenue the ERP booked: Contract 1 POB #2 66.00 and
    # POB #3 88.00, Dr PRE_STANDARD_REVENUE / Cr CONTRACT_LIABILITY at the obligation's revenue
    # string (S13-R-08; D-89 L7-6-Q-8).
    command = computed[0]
    assert {intent.entry_kind for intent in intents(command.output, "LEGACY")} == {
        "PRE_STANDARD_REVENUE"
    }
    assert lines(intents(command.output, "LEGACY")) == [
        ("POB #2", "C", CL, "21001", usd("66.00")),
        ("POB #2", "D", PRE, "5002", usd("66.00")),
        ("POB #3", "C", CL, "21001", usd("88.00")),
        ("POB #3", "D", PRE, "5003", usd("88.00")),
    ]
    assert intents(computed[2].output, "LEGACY") == []  # Contract 2 booked no pre-standard revenue
    delta = intent_totals.totals(computed, view=intent_totals.DELTA, start=START, end=END)
    assert intent_totals.by_account(delta) == {
        "15002": usd("58.85"),
        "21001": usd("141.69"),  # 295.69 − 154.00
        "5001": -usd("187.69"),  # Contract 1 128.84 + Contract 2 58.85
        "5002": -usd("52.53"),  # 118.53 − 66.00
        "5003": usd("39.68"),  # 88.00 − 48.32
    }
    assert intent_totals.balance(delta) == (usd("240.22"), usd("240.22"))  # CHK-020; GT-07
