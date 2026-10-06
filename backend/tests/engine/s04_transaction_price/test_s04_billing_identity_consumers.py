"""The 05h consumers on one scenario table: amounts, sources, windows and mismatch flags (D-91).

Native (no compute) rows over ``taxes.collected_tax``, ``taxes.excluded``, ``specialist.invoices``
and the kernel's mismatch flags, each with expectations derived from the rules: S10-R-07 identity
(contract key, ``invoice_number``, ``line_external_id``) classified over the whole ENG-06 stream
before any consumer filter; a repeat whose ``is_cancellable`` is not true (``false``, ``"false"``,
absent, a number) is a status update that adds nothing and never re-attributes; a repeat flagged
``True`` or ``"true"`` is another line; consumers keep their own cutoffs (``taxes.excluded`` has
``before`` and ``at``, ``collected_tax`` has ``at``, ``specialist.invoices`` has [since, at] and the
obligation filter). The table mirrors the shape of Codex's independent probe
(``2026-09-19-b4-05h-independent-probe.py``) with the lane's own oracles; 11 rows fail on the
0c853cb engine (``.run/l9/d91-b4/fail-first-native.log``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from erev_engine import billing_identity
from erev_engine.stages.s04_transaction_price import specialist, taxes
from erev_engine.stages.state import EventView
from support import bundles
from support.recognition import book_context, event_view

C1, C2 = "C1", "C2"


def bill(
    seq: int,
    day: int,
    amount: str = "100",
    tax: str = "8",
    *,
    contract: str = C1,
    key: str | None = "L1",
    cancel: object = False,
    absent: bool = False,
    line: str = "1",
    tax_lines: list[dict[str, object]] | None = None,
) -> EventView:
    payload: dict[str, object] = {
        "invoice_number": "I",
        "line_external_id": line,
        "amount": Decimal(amount),
        "tax_amount": Decimal(tax),
        "issue_date": date(2026, 1, day),
    }
    if key is not None:
        payload["obligation_key"] = key
    if not absent:
        payload["is_cancellable"] = cancel
    if tax_lines is not None:
        payload["tax_lines"] = tax_lines
    keys = [key] if key else []
    return event_view(
        contract, seq, "BILLING_RECORDED", date(2026, 1, day), payload, obligation_keys=keys
    )


@dataclass(frozen=True)
class Row:
    name: str
    events: Sequence[EventView]
    tax_total: int  # Σ tax of the kept member lines dated ≤ at (excluded and collected agree)
    tax_sources: Sequence[EventView]  # excluded() source events, in order
    invoices: Sequence[tuple[EventView, int]]  # specialist.invoices rows
    since: int = 1
    at: int = 31
    contract: str = C1
    keys: tuple[str, ...] = ()
    before: EventView | None = None
    tax_contract: str | None = None
    collected_total: int | None = None  # when ``before`` makes excluded() and collected differ
    flags: Sequence[tuple[EventView, bool, bool]] | None = None  # kernel mismatch flags to check


A = bill(1, 5)
UPDATE = bill(2, 20)
REPEAT = bill(2, 20, "200", "16", cancel=True)
OTHER_CONTRACT = bill(1, 5, "250", "20", contract=C2)
BAD_AMOUNT = bill(2, 20, "999", "99")
OTHER_KEY = bill(2, 20, key="L2")
ANON = bill(1, 5, key=None)
ATTRIBUTED = bill(2, 20, key="L1")
NULL_UPDATE = bill(2, 20, key=None)
SAME_DAY_A = bill(1, 20)
SAME_DAY_B = bill(2, 20, "200", "16", cancel=True)
TAX_LINES = bill(
    1,
    5,
    tax="999",
    tax_lines=[
        {"tax_type": "SALES", "amount": Decimal("3"), "principal_or_agent": "AGENT"},
        {"tax_type": "VAT", "amount": Decimal("5"), "principal_or_agent": "AGENT"},
    ],
)

ROWS: list[Row] = [
    Row("one_line", [A], 8, [A], [(A, 100)]),
    Row("ordinary_repeat_false", [A, bill(2, 20, cancel=False)], 8, [A], [(A, 100)]),
    Row("ordinary_repeat_string_false", [A, bill(2, 20, cancel="false")], 8, [A], [(A, 100)]),
    Row("ordinary_repeat_number_not_true", [A, bill(2, 20, cancel=1)], 8, [A], [(A, 100)]),
    Row("ordinary_repeat_absent", [A, bill(2, 20, absent=True)], 8, [A], [(A, 100)]),
    Row("cancellable_repeat_true", [A, REPEAT], 24, [A, REPEAT], [(A, 100), (REPEAT, 200)]),
    Row(
        "cancellable_repeat_string_true",
        [A, bill(2, 20, "200", "16", cancel="true")],
        24,
        [A, bill(2, 20, "200", "16", cancel="true")],
        [(A, 100), (bill(2, 20, "200", "16", cancel="true"), 200)],
    ),
    Row(
        "different_line_identity",
        [A, bill(2, 20, "200", "16", line="2")],
        24,
        [A, bill(2, 20, "200", "16", line="2")],
        [(A, 100), (bill(2, 20, "200", "16", line="2"), 200)],
    ),
    Row("same_ids_two_contracts", [A, OTHER_CONTRACT], 28, [A, OTHER_CONTRACT], [(A, 100)]),
    Row(
        "tax_member_contract_filter",
        [A, OTHER_CONTRACT],
        20,
        [OTHER_CONTRACT],
        [(OTHER_CONTRACT, 250)],
        contract=C2,
        tax_contract=C2,
    ),
    Row("original_before_since_ordinary_update", [A, UPDATE], 8, [A], [], since=10),
    Row(
        "original_before_since_mismatched_amount",
        [A, BAD_AMOUNT],
        8,
        [A],
        [],
        since=10,
        flags=[(BAD_AMOUNT, True, False)],
    ),
    Row(
        "original_before_since_cancellable_repeat",
        [A, REPEAT],
        24,
        [A, REPEAT],
        [(REPEAT, 200)],
        since=10,
    ),
    Row(
        "obligation_filter_after_identity",
        [A, OTHER_KEY],
        8,
        [A],
        [],
        keys=("L2",),
        flags=[(OTHER_KEY, False, True)],
    ),
    Row(
        "original_attribution_retained",
        [A, OTHER_KEY],
        8,
        [A],
        [(A, 100)],
        keys=("L1",),
        flags=[(OTHER_KEY, False, True)],
    ),
    Row(
        "null_original_attributed_update_is_not_new_line",
        [ANON, ATTRIBUTED],
        8,
        [ANON],
        [],
        keys=("L1",),
        flags=[(ATTRIBUTED, False, False)],
    ),
    Row(
        "null_update_does_not_remove_original",
        [A, NULL_UPDATE],
        8,
        [A],
        [(A, 100)],
        keys=("L1",),
        flags=[(NULL_UPDATE, False, False)],
    ),
    Row("at_before_update", [A, REPEAT], 8, [A], [(A, 100)], at=19),
    Row("at_inclusive_update", [A, REPEAT], 24, [A, REPEAT], [(A, 100), (REPEAT, 200)], at=20),
    Row(
        "before_strict_position",
        [A, REPEAT],
        8,
        [A],
        [(A, 100), (REPEAT, 200)],
        at=20,
        before=REPEAT,
        collected_total=24,
    ),
    Row(
        "before_same_date_record_order",
        [SAME_DAY_A, SAME_DAY_B],
        8,
        [SAME_DAY_A],
        [(SAME_DAY_A, 100), (SAME_DAY_B, 200)],
        at=20,
        before=SAME_DAY_B,
        collected_total=24,
    ),
    Row("since_inclusive_original", [A, UPDATE], 8, [A], [(A, 100)], since=5),
    Row("all_future_excluded", [REPEAT], 0, [], [], at=19),
    Row("tax_lines_take_precedence", [TAX_LINES], 8, [TAX_LINES], [(TAX_LINES, 100)]),
]


def _state(events: Sequence[EventView]) -> SimpleNamespace:
    stream = tuple(sorted(events, key=lambda e: e.order_key))
    contracts = {
        e.contract_key: SimpleNamespace(
            header=SimpleNamespace(contracting_entity_code=bundles.ENTITY_CODE)
        )
        for e in stream
    }
    canonical = SimpleNamespace(events=stream, measure_events=stream, contracts=contracts)
    return SimpleNamespace(
        identified=SimpleNamespace(
            canonical=canonical, member_contract_keys=tuple(sorted(contracts))
        )
    )


@pytest.mark.parametrize("row", ROWS, ids=[row.name for row in ROWS])
def test_05h_consumers_agree_with_the_kernel_identity(row: Row) -> None:
    st = _state(row.events)
    stream = st.identified.canonical.events
    ctx = book_context()
    at = date(2026, 1, row.at)
    members = (
        set(st.identified.member_contract_keys) if row.tax_contract is None else {row.tax_contract}
    )
    collected = row.tax_total if row.collected_total is None else row.collected_total
    assert taxes.collected_tax(stream, members, at) == Fraction(collected)
    excluded = taxes.excluded(ctx, st, at, row.before, contract_key=row.tax_contract)
    assert sum((item.amount for item in excluded), Fraction(0)) == Fraction(row.tax_total)
    assert [item.event.event_key for item in excluded] == [e.event_key for e in row.tax_sources]
    found = specialist.invoices(st, row.contract, row.keys, date(2026, 1, row.since), at)
    assert [(e.event_key, amount) for e, amount in found] == [
        (e.event_key, Fraction(amount)) for e, amount in row.invoices
    ]
    if row.flags is not None:
        updates = [
            (item.event.event_key, item.amount_mismatch, item.obligation_mismatch)
            for item in billing_identity.iter_billing_lines(stream)
            if item.is_status_update
        ]
        assert updates == [(e.event_key, a, o) for e, a, o in row.flags]
