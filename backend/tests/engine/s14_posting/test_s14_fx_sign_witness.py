"""The public-event witness of ENG-S14R10-FX-SIGN-1: a role delta whose transaction and functional
amounts differ in sign posts as two lines (ENGINE_SPEC_B S14-R-04, S14-R-06, S14-R-10, S14-R-15,
S14-R-28, S14-INV-09; supervisor ruling R-44 (a), option B of the design note
``docs/accounting/reviews/ENG-S14R10-FX-SIGN-DESIGN-2026-09-29.md``; §12.2.2, S12-R-04 to S12-R-06).

A period delta of one role is derived in the transaction currency and in the functional currency
independently (target less posted, S14-R-04). ``IntentLine`` has one side for both, and decision
L2-5-Q-34 refused a delta whose two amounts differ in sign, so the contract could not be computed.
Such a delta now posts as two lines of the same role in its entry: a transaction line (functional
amount 0) and a functional line (transaction amount 0), each on the side of its own amount. No
amount or rate is derived; the two signed totals of the role are those of the delta.

The two former strict expected failures of ``tests/unit/test_prp7_open_items.py`` reach the case
through the stateful machine's platform with a locked period and rate sets far from a market. This
witness is the case of the second of them — one point-in-time line, a delivery that is computed,
then an invoice and one more unit — at market-like rates, and in its first form without any lock
or late event:

USD contract of a GBP-functional entity, 101 units at USD 1,000.00. USD to GBP: spot 0.8000 (1
January 2026), January average 0.8100, January closing 0.8200; ``fx.unbilled_revenue_rate`` is
``PERIOD_AVERAGE``, ``fx.cl_layer_consumption`` ``FIFO`` and ``billing.posting`` ``ERP`` (the
defaults).

1. 10 January: 100 units delivered. Revenue USD 100,000.00 has no liability layer to relieve, so
   it is an asset layer at the January average: GBP 81,000.00 (S12-R-06). The computation posts
   Dr CONTRACT_LIABILITY / Cr REVENUE 100,000.00 / 81,000.00.
2. An invoice of USD 100,000.00 and one more unit delivered on 21 January then become known. The
   revenue of a period relieves the control role in one flow dated the period end (§12.2.2
   "period-end flows"), so an invoice dated anywhere in January is layered before January's
   revenue — dated before the first delivery (5 January) or after it (20 January), and every test
   that takes the invoice runs for both dates. The invoice creates a liability layer at spot,
   80,000.00 (S12-R-04); the period's revenue of 101,000.00 relieves it at its historical amount
   (S12-R-05) and the remaining 1,000.00 is an asset layer at the average, 810.00. The cumulative
   January target is 101,000.00 / 80,810.00.
3. Target less posted: +1,000.00 USD and −190.00 GBP — one more unit in the transaction currency,
   while 100,000.00 of revenue moves from the average to the invoice's historical rate in the
   functional currency (−1,000.00 + 810.00). The entry: Dr CONTRACT_LIABILITY USD 1,000.00 and
   Cr CONTRACT_LIABILITY GBP 190.00; Cr REVENUE USD 1,000.00 and Dr REVENUE GBP 190.00.

Computed after each event, the same history posts two ordinary entries and reaches the same
totals; and with two further units instead of one the delta is +2,000.00 USD / +620.00 GBP and
posts on one line per role.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal

import pytest
from erev_engine import compute
from erev_engine.bundle import (
    FxRateInput,
    InputBundle,
    OutputBundle,
    PostedAmountInput,
    PostingIntent,
)
from erev_engine.canonical import sha256_hex
from support import intent_totals, platform_props
from support.prop_worlds import INCEPTION, LineSpec, MeasureSpec, WorldSpec

P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
KEYS = (P01, P02, P03)
OBLIGATION = "K-1/POB-01"
REVENUE_KIND = "REVENUE_RECOGNITION"
FX_KIND = "FX_REMEASUREMENT"
CL, REVENUE, GAIN_LOSS = "CONTRACT_LIABILITY", "REVENUE", "FX_GAIN_LOSS"
RATE_SET = "FX@v1"
SPOT_JAN_1 = "USDGBP-SPOT-2026-01-01"
AVERAGE_P01 = "USDGBP-AVERAGE-FY2026-P01"

LINE = LineSpec("POB-01", "PIT", 10100000, 100000, 101, 0, 0)  # 101 units at USD 1,000.00
LONGER = LineSpec("POB-01", "PIT", 10200000, 100000, 102, 0, 0)  # 102 units at USD 1,000.00
FIRST = MeasureSpec("K-1", "POB-01", "DELIVERY", 9, 100)  # 10 January: 100 units
ONE_MORE = MeasureSpec("K-1", "POB-01", "DELIVERY", 20, 1)  # 21 January: 1 unit
JANUARY_OPEN = {P01: "open", P02: "future", P03: "future"}
JANUARY_LOCKED = {P01: "closed", P02: "closing", P03: "future"}
# The invoice of USD 100,000.00 that becomes known after the first computation, by its date (days
# after 1 January). Spot on either date is the rate of 1 January.
INVOICE_DAYS = {
    "invoice of 5 January, before the delivery": 4,
    "invoice of 20 January, after the delivery": 19,
}
either_invoice = pytest.mark.parametrize("day", INVOICE_DAYS.values(), ids=INVOICE_DAYS.keys())

# (period, origin, reason, side, role, transaction minor units, functional minor units)
Row = tuple[str, str | None, str | None, str, str, int, int]


def _rate(kind: str, on: date, period: str | None, value: str) -> FxRateInput:
    key = f"USDGBP-{kind.upper()}-{period or on.isoformat()}"
    return FxRateInput(key, RATE_SET, kind, "USD", "GBP", on, period, Decimal(value))


RATES = (
    _rate("spot", date(2026, 1, 1), None, "0.8000"),
    _rate("average", date(2026, 1, 31), P01, "0.8100"),
    _rate("average", date(2026, 2, 28), P02, "0.8300"),
    _rate("average", date(2026, 3, 31), P03, "0.8350"),
    _rate("closing", date(2026, 1, 31), P01, "0.8200"),
    _rate("closing", date(2026, 2, 28), P02, "0.8500"),
    _rate("closing", date(2026, 3, 31), P03, "0.8600"),
)


def _world(
    measures: Sequence[MeasureSpec],
    states: Mapping[str, str],
    posted: Sequence[PostedAmountInput] = (),
    line: LineSpec = LINE,
) -> InputBundle:
    return platform_props.machine_bundle(
        WorldSpec("USD", (("K-1", (line,)),), tuple(measures)),
        period_states=states,
        posted=posted,
        books=("ASC606",),
        months=len(KEYS),
        functional_currency="GBP",
        fx_rates=RATES,
    )


def _later(day: int) -> list[MeasureSpec]:
    """The events in arrival order once the invoice dated ``day`` and the last unit are known."""
    return [FIRST, MeasureSpec("K-1", "POB-01", "BILLING", day, 10000000), ONE_MORE]


def _intents(output: OutputBundle, kind: str = REVENUE_KIND) -> list[PostingIntent]:
    (book,) = output.books
    return [intent for intent in book.posting_intents if intent.entry_kind == kind]


def _rows(output: OutputBundle, kind: str = REVENUE_KIND) -> list[Row]:
    return sorted(
        (
            intent.posting_period_key,
            intent.origin_period_key,
            intent.reason_code,
            line.side,
            line.account_role,
            line.amount_txn,
            line.amount_functional,
        )
        for intent in _intents(output, kind)
        for line in intent.lines
    )


def _rate_keys(output: OutputBundle) -> set[tuple[str, ...]]:
    (book,) = output.books
    rates = dict(book.line_rates)
    return {
        tuple(rate_key for rate_key, _ in rates[line.line_key])
        for intent in _intents(output)
        for line in intent.lines
    }


def _posted(items: Sequence[PostedAmountInput], role: str) -> tuple[int, int]:
    """The posted (transaction, functional) amount of January's revenue entries on ``role``: the
    lines posted in January, and those posted later with January as their origin."""
    found = [
        item
        for item in items
        if item.entry_kind == REVENUE_KIND
        and item.account_role == role
        and P01 in (item.period_key, item.origin_period_key)
    ]
    return sum(item.amount_txn for item in found), sum(item.amount_functional for item in found)


def _line_key(role: str, period: str, origin: str | None, *, functional_leg: bool) -> str:
    """S14-R-15: the ten-member line-key object of the delta, which its transaction line keeps;
    the functional line adds ``currency_leg``."""
    members: dict[str, object] = {
        "account_role": role,
        "book_code": "ASC606",
        "clearing_purpose": None,
        "counterparty_entity": None,
        "entity": "US01",
        "entry_kind": REVENUE_KIND,
        "origin_period_key": origin,
        "posting_class": "EVENT",
        "posting_period_key": period,
        "subject_key": OBLIGATION,
    }
    if functional_leg:
        members["currency_leg"] = "FUNCTIONAL"
    return sha256_hex(members)


def _assert_the_two_line_entry(output: OutputBundle, period: str, origin: str | None) -> None:
    """The one revenue entry of the opposed delta +1,000.00 USD / −190.00 GBP on
    CONTRACT_LIABILITY (REVENUE the reverse): per role a transaction line and a functional line,
    debits first then by role (S14-R-12); the entry balances in each currency (S14-INV-01); the
    non-zero amounts of a line share its side (S14-INV-09); the keys are those of S14-R-15; and
    all four lines name the references of the delta (S14-R-28)."""
    (intent,) = _intents(output)
    assert (intent.posting_period_key, intent.origin_period_key) == (period, origin)
    assert [
        (line.side, line.account_role, line.amount_txn, line.amount_functional)
        for line in intent.lines
    ] == [
        ("D", CL, 100000, 0),
        ("D", REVENUE, 0, 19000),
        ("C", CL, 0, 19000),
        ("C", REVENUE, 100000, 0),
    ]
    for currency in ("amount_txn", "amount_functional"):
        debits = sum(getattr(line, currency) for line in intent.lines if line.side == "D")
        credits = sum(getattr(line, currency) for line in intent.lines if line.side == "C")
        assert debits == credits
    assert [line.line_key for line in intent.lines] == [
        _line_key(CL, period, origin, functional_leg=False),
        _line_key(REVENUE, period, origin, functional_leg=True),
        _line_key(CL, period, origin, functional_leg=True),
        _line_key(REVENUE, period, origin, functional_leg=False),
    ]
    assert len({line.line_key for line in intent.lines}) == 4
    assert _rate_keys(output) == {(AVERAGE_P01, SPOT_JAN_1)}
    (book,) = output.books
    assert {line.line_key for line in intent.lines} <= set(dict(book.line_rates))


def test_the_first_delivery_posts_100_000_at_the_january_average() -> None:
    """Step 1, the amounts posted before: Dr CONTRACT_LIABILITY / Cr REVENUE USD 100,000.00 at the
    January average 0.8100, GBP 81,000.00, stamped with that rate."""
    first = compute(_world([FIRST], JANUARY_OPEN))
    assert _rows(first) == [
        (P01, None, None, "C", REVENUE, 10000000, 8100000),
        (P01, None, None, "D", CL, 10000000, 8100000),
    ]
    assert _rate_keys(first) == {(AVERAGE_P01,)}
    posted = intent_totals.posted(first)
    assert _posted(posted, CL) == (10000000, 8100000)
    assert _posted(posted, REVENUE) == (-10000000, -8100000)


@either_invoice
def test_the_revised_january_target_is_101_000_at_80_810(day: int) -> None:
    """Step 2, the upstream target: the same events computed with nothing posted. The invoice's
    liability layer (spot 0.8000, 80,000.00), created on the invoice date, is relieved at its
    historical amount at the period end and the last 1,000.00 is an asset layer at the average
    (810.00), so January revenue is USD 101,000.00 / GBP 80,810.00 and names both rates."""
    fresh = compute(_world(_later(day), JANUARY_OPEN))
    assert _rows(fresh) == [
        (P01, None, None, "C", REVENUE, 10100000, 8081000),
        (P01, None, None, "D", CL, 10100000, 8081000),
    ]
    assert _rate_keys(fresh) == {(AVERAGE_P01, SPOT_JAN_1)}
    movements = [
        (
            str(row["movement_kind"]),
            str(row["effective_date"]),
            row["amount_txn"],
            row["amount_functional"],
        )
        for row in platform_props.layer_movements(fresh.books[0])
        if row["movement_kind"] != "ASSET_LAYER_REMEASURED"
    ]
    assert movements == [
        ("LIABILITY_LAYER_CREATED", str(INCEPTION + timedelta(days=day)), 10000000, 8000000),
        ("LIABILITY_LAYER_CONSUMED", "2026-01-31", 10000000, 8000000),
        ("ASSET_LAYER_CREATED", "2026-01-31", 100000, 81000),
    ]


@either_invoice
def test_eng_s14r10_fx_sign_1_one_open_month_posts_a_transaction_and_a_functional_line(
    day: int,
) -> None:
    """Step 3 with no lock and no late event: January stays open, the first computation's revenue
    is posted, and the invoice and the last unit arrive. Target less posted on CONTRACT_LIABILITY
    is +1,000.00 USD and −190.00 GBP (on REVENUE the reverse): one entry of four lines in January.
    The posted totals then equal the target, and the same events computed over them post nothing
    (S14-INV-02)."""
    posted = intent_totals.posted(compute(_world([FIRST], JANUARY_OPEN)))
    assert (10100000 - _posted(posted, CL)[0], 8081000 - _posted(posted, CL)[1]) == (100000, -19000)
    second = compute(_world(_later(day), JANUARY_OPEN, posted))
    _assert_the_two_line_entry(second, P01, None)
    after = intent_totals.posted(second, sealed=posted)
    assert _posted(after, CL) == (10100000, 8081000)
    assert _posted(after, REVENUE) == (-10100000, -8081000)
    again = compute(_world(_later(day), JANUARY_OPEN, after))
    assert [intent for book in again.books for intent in book.posting_intents] == []


@either_invoice
def test_eng_s14r10_fx_sign_1_after_the_january_lock_the_two_lines_post_as_a_late_event(
    day: int,
) -> None:
    """The same delta as a late event (S14-R-06): January is closed with its lines sealed (the
    close run's remeasurement and reclass included) before the invoice and the last unit arrive.
    The delta is redirected unchanged to February with origin January: the same four lines, with
    reason ``LATE_EVENT``. February's remeasurement pass takes back 960.00 of the 1,000.00 posted
    for January's asset position (20.00 + 20.00 remain on the 1,000.00 layer). The read-back then
    holds a posted amount with opposed signs, and a recompute over it posts nothing."""
    january = platform_props.close_run(_world([FIRST], {**JANUARY_OPEN, P01: "closing"}))
    sealed = platform_props.sealed_through(january.outputs, KEYS, P01)
    assert _posted(sealed, CL) == (10000000, 8100000)
    late = platform_props.close_run(_world(_later(day), JANUARY_LOCKED, sealed))
    _assert_the_two_line_entry(late.command, P02, P01)
    (carry,) = _intents(late.command)
    assert carry.reason_code == "LATE_EVENT"
    remeasured = [row for output in late.passes for row in _rows(output, FX_KIND)]
    assert remeasured == [
        (P02, None, None, "C", CL, 0, 96000),
        (P02, None, None, "D", GAIN_LOSS, 0, 96000),
    ]
    after = platform_props.merge_sealed(
        sealed, platform_props.sealed_through(late.outputs, KEYS, P02)
    )
    opposed = [
        (
            item.account_role,
            item.period_key,
            item.origin_period_key,
            item.amount_txn,
            item.amount_functional,
        )
        for item in after
        if item.entry_kind == REVENUE_KIND and item.period_key == P02
    ]
    assert sorted(opposed) == [
        (CL, P02, P01, 100000, -19000),
        (REVENUE, P02, P01, -100000, 19000),
    ]
    assert _posted(after, CL) == (10100000, 8081000)
    again = platform_props.close_run(_world(_later(day), JANUARY_LOCKED, after))
    assert [
        intent
        for output in again.outputs
        for book in output.books
        for intent in book.posting_intents
    ] == []


@either_invoice
def test_the_same_history_computed_after_each_event_posts_two_ordinary_entries(day: int) -> None:
    """The opposed delta is the sum of two movements the ledger has always taken. Computed when
    the invoice alone is known, the history posts the re-layering of the posted revenue on
    functional-only lines (Dr REVENUE / Cr CONTRACT_LIABILITY GBP 1,000.00, no transaction amount,
    at the invoice's spot); computed again when the last unit is known, it posts Dr
    CONTRACT_LIABILITY / Cr REVENUE USD 1,000.00 / GBP 810.00. The posted totals are the target of
    the witness, 101,000.00 / 80,810.00 — the totals the single computation above reaches with a
    transaction line and a functional line per role."""
    invoice = _later(day)[1]
    posted = intent_totals.posted(compute(_world([FIRST], JANUARY_OPEN)))
    alone = compute(_world([FIRST, invoice], JANUARY_OPEN, posted))
    assert _rows(alone) == [
        (P01, None, None, "C", CL, 0, 100000),
        (P01, None, None, "D", REVENUE, 0, 100000),
    ]
    assert _rate_keys(alone) == {(SPOT_JAN_1,)}
    posted = intent_totals.posted(alone, sealed=posted)
    then = compute(_world(_later(day), JANUARY_OPEN, posted))
    assert _rows(then) == [
        (P01, None, None, "C", REVENUE, 100000, 81000),
        (P01, None, None, "D", CL, 100000, 81000),
    ]
    posted = intent_totals.posted(then, sealed=posted)
    assert _posted(posted, CL) == (10100000, 8081000)
    assert _posted(posted, REVENUE) == (-10100000, -8081000)


def _longer_posted() -> tuple[PostedAmountInput, ...]:
    """The first delivery of the line of 102 units, computed and posted: 100,000.00 / 81,000.00."""
    posted = intent_totals.posted(compute(_world([FIRST], JANUARY_OPEN, line=LONGER)))
    assert _posted(posted, CL) == (10000000, 8100000)
    return posted


def test_two_further_units_instead_of_one_post_one_net_line() -> None:
    """The neighbouring case, whose amounts agree in sign. With a line of 102 units, the invoice
    and two further units give a delta of +2,000.00 USD / +620.00 GBP (−1,000.00 of re-layering and
    +1,620.00 for the two units): one line per role, whose functional amount is the net of both
    and is no conversion of its transaction amount at any one rate."""
    second = MeasureSpec("K-1", "POB-01", "DELIVERY", 21, 1)  # 22 January: 1 unit
    two = compute(_world([*_later(19), second], JANUARY_OPEN, _longer_posted(), line=LONGER))
    assert _rows(two) == [
        (P01, None, None, "C", REVENUE, 200000, 62000),
        (P01, None, None, "D", CL, 200000, 62000),
    ]


def test_eng_s14r10_fx_sign_1_one_further_unit_of_the_longer_line_posts_the_two_lines() -> None:
    """The same line of 102 units with one further unit instead of two is the delta of the
    witness, +1,000.00 USD / −190.00 GBP: the four lines of the two-line entry. Whether one line
    or two are posted turns on the signs of the delta alone."""
    one = compute(_world(_later(19), JANUARY_OPEN, _longer_posted(), line=LONGER))
    _assert_the_two_line_entry(one, P01, None)
