"""Stage 09 returns: a status update dates the identity's first-seen line only (policy edge A).

The supervisor's reading of S10-R-07 and D-91 C606-01 (2), implemented for stage 10 in bf79c60:
a noncancellable status update applies to the identity's FIRST-SEEN line; a repeat flagged
cancellable is a new line that stays memo-only until a receipt applied to its invoice. Stage 09's
ALG-06 step 3 (S09-R-23a) kept its ``first_update`` map by identity, so every cancellable
occurrence of the identity took the update as its S10-R-06 source and entered units billed: with a
1,000.00 memo line on 10 January, a cancellable 400.00 repeat of the identity on 15 January and a
valid 1,000.00 update on 20 January (no payment) stage 10 billed 1,000.00 while stage 09 counted 14
units, a refund liability of 1,400.00 and a 1,400.00 January credit (2,000.00 for a same-amount
repeat), silently (replay and journals balance). Codex's frozen probe
``2026-09-19-b4-returns-first-line-independent-probe.py`` (sha 85cea8e2…) holds the four worlds;
the oracles here are the lane's (``.run/l9/d91-b4/derive.py`` §J): 100 products at 100.00, E 20,
Y 0, revenue 8,000.00; RL = min(E, U_b) × 100.00 with U_b = billed ÷ 100. World: the frozen
RET-CHK-029-S3-EX22-STATUS-UPDATE ``end-of-january`` checkpoint with ``billing.posting`` switched
per case (and POL-123 to match, as ENG-B1's functional tests do). No database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from erev_engine.bundle import InputBundle
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    net_posted,
    period_balance,
    with_events,
    with_policy,
)

KEY = ("ret", "RET-CHK-029-S3-EX22-STATUS-UPDATE", "end-of-january")
JAN_15 = date(2026, 1, 15)
P01 = "FY2026-P01"
BASIS = {"ERP": "ERP_POSTED_INVOICES", "ENGINE": "UNCONDITIONAL_INVOICES_ONLY"}


def _world(mode: str, repeat: str | None) -> InputBundle:
    bundle = with_policy(checkpoint_bundle(*KEY), "billing.posting", mode)
    if any(p.code == "balance.position_invoice_basis" for b in bundle.books for p in b.policies):
        bundle = with_policy(bundle, "balance.position_invoice_basis", BASIS[mode])
    if repeat is None:
        return bundle
    line = first_billing(bundle)  # the cancellable 1,000.00 line of 10 January
    return with_events(
        bundle, billing_after(bundle, line, JAN_15, cancellable=True, amount=Decimal(repeat))
    )


@pytest.mark.parametrize(
    ("mode", "repeat", "billed", "units"),
    [
        pytest.param("ENGINE", None, 100_000, "10", id="engine_original"),
        pytest.param("ENGINE", "400.00", 100_000, "10", id="engine_repeat_400"),
        pytest.param("ENGINE", "1000.00", 100_000, "10", id="engine_repeat_1000"),
        pytest.param("ERP", "400.00", 140_000, "14", id="erp_repeat_400_control"),
    ],
)
def test_returns_count_the_first_seen_line_dated_by_its_update(
    mode: str, repeat: str | None, billed: int, units: str
) -> None:
    """ENGINE: the 20 January update dates the 10 January line alone; a cancellable repeat of the
    identity (400.00 or the same 1,000.00) stays memo-only with no receipt, so stage 10 and stage
    09 agree on 1,000.00 billed, 10 units, a refund liability of 1,000.00 and a 1,000.00 January
    credit (on 271e3f4 stage 09 counted 14 units / 1,400.00 and 20 units / 2,000.00). ERP: every
    line counts at its date, so the 400.00 repeat is billing: 1,400.00, 14 units, 1,400.00."""
    book = compute_book(_world(mode, repeat))
    assert book.contract_version is not None
    columns = book.contract_version.columns
    assert (columns["billed_cum"], columns["revenue_cum"]) == (billed, 800_000)
    assert period_balance(book, P01, "refund_liability_txn") == billed
    (node,) = [
        n
        for n in book.trace.nodes
        if n.measure == "return_units_billed" and n.id.endswith(f":{P01}")
    ]
    assert node.value == units
    assert net_posted(book, "REFUND_LIABILITY", P01) == billed
