"""JET-06 after a modification catch-up: compute, then the ``NETTING_RECLASS`` close pass (L6-2;
L5-3-Q-6, L5-5-Q-3; D-85).

ENGINE_SPEC_B Table 14-A and S14-R-05 class JET-06 and its reversal as ``TIME`` amounts of the
``NETTING_RECLASS`` pass, and 05 RCP-08(b) has the close run post them over the posted compute
intents (S14-R-07: the reversal of t negates the reclass posted for t − 1). POLICIES JET-06 posts
both at every period end in both modes. The answer keys assert those lines at period-end
checkpoints, so the engine runner computed only the ``COMMAND`` half. These tests run the answer-key
worlds without a database: ``compute`` posts no reclass, and the pass over its intents gives the
keys' figures.
"""

from __future__ import annotations

import decimal
from typing import cast

import erev_engine
from erev_engine.bundle import OutputBundle
from erev_engine.money import DECIMAL_CONTEXT
from support import intent_totals
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

RECLASS, REVERSAL = "NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"
CL, UR, REVENUE = "CONTRACT_LIABILITY", "UNBILLED_RECEIVABLE", "REVENUE"
RETRO_GT10 = "MOD-LEGACY-RETRO-GT10"
LATE_091 = "LATE-CHK-091-TC-JE-11-EVENTS-RECORDED-OUT-OF-ORDER"

Line = tuple[str, str, str, str, str, int]  # (period, entry kind, class, obligation, role, signed)


def _runs(key_id: str, name: str) -> tuple[OutputBundle, OutputBundle, str]:
    """``compute`` and the ``NETTING_RECLASS`` pass over its intents for checkpoint ``name``."""
    family = key_id.split("-", 1)[0].lower()
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = next(c for c in _build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    command = cast(OutputBundle, erev_engine.compute(bundle))
    with decimal.localcontext(DECIMAL_CONTEXT):
        reclass = intent_totals.close_pass(bundle, [command], RECLASS)
    return command, reclass, checkpoint.book


def _lines(output: OutputBundle, book_code: str, periods: tuple[str, ...]) -> list[Line]:
    """Signed transaction amounts (debit positive) of the book's intents in ``periods``, sorted."""
    (book,) = [item for item in output.books if item.book_code == book_code]
    return sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            intent.subject_key.rsplit("/", 1)[-1],
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
        )
        for intent in book.posting_intents
        if intent.posting_period_key in periods
        for line in intent.lines
    )


def _net(lines: list[Line]) -> dict[str, int]:
    found: dict[str, int] = {}
    for *_, role, amount in lines:
        found[role] = found.get(role, 0) + amount
    return found


def test_s14_r05_compute_posts_no_reclass_after_the_retrospective_catch_up() -> None:
    command, _, book = _runs(RETRO_GT10, "end-may-after-retrospective")
    (output_book,) = [item for item in command.books if item.book_code == book]
    kinds = {intent.entry_kind for intent in output_book.posting_intents}
    assert kinds & {RECLASS, REVERSAL} == set()
    # The 15 May catch-up relief only: Dr 21002 23.86 / Cr 5001 13.37, Cr 5003 10.49.
    assert _lines(command, book, ("FY2023-P05",)) == [
        ("FY2023-P05", "REVENUE_RECOGNITION", "EVENT", "POB %231", CL, 1337),
        ("FY2023-P05", "REVENUE_RECOGNITION", "EVENT", "POB %231", REVENUE, -1337),
        ("FY2023-P05", "REVENUE_RECOGNITION", "EVENT", "POB %233", CL, 1049),
        ("FY2023-P05", "REVENUE_RECOGNITION", "EVENT", "POB %233", REVENUE, -1049),
    ]


def test_s14_r07_reclass_pass_after_the_retrospective_catch_up() -> None:
    command, reclass, book = _runs(RETRO_GT10, "end-may-after-retrospective")
    assert _lines(reclass, book, ("FY2023-P04", "FY2023-P05")) == [
        # April: reversal of March (58.85, 46.15), reclass of NP −85.00 (47.64, 37.36).
        ("FY2023-P04", RECLASS, "TIME", "POB %231", CL, -4764),
        ("FY2023-P04", RECLASS, "TIME", "POB %231", UR, 4764),
        ("FY2023-P04", RECLASS, "TIME", "POB %233", CL, -3736),
        ("FY2023-P04", RECLASS, "TIME", "POB %233", UR, 3736),
        ("FY2023-P04", REVERSAL, "TIME", "POB %231", CL, 5885),
        ("FY2023-P04", REVERSAL, "TIME", "POB %231", UR, -5885),
        ("FY2023-P04", REVERSAL, "TIME", "POB %233", CL, 4615),
        ("FY2023-P04", REVERSAL, "TIME", "POB %233", UR, -4615),
        # May: reclass of NP −108.86 after the catch-up (61.01, 47.85), reversal of April.
        ("FY2023-P05", RECLASS, "TIME", "POB %231", CL, -6101),
        ("FY2023-P05", RECLASS, "TIME", "POB %231", UR, 6101),
        ("FY2023-P05", RECLASS, "TIME", "POB %233", CL, -4785),
        ("FY2023-P05", RECLASS, "TIME", "POB %233", UR, 4785),
        ("FY2023-P05", REVERSAL, "TIME", "POB %231", CL, 4764),
        ("FY2023-P05", REVERSAL, "TIME", "POB %231", UR, -4764),
        ("FY2023-P05", REVERSAL, "TIME", "POB %233", CL, 3736),
        ("FY2023-P05", REVERSAL, "TIME", "POB %233", UR, -3736),
    ]
    # With the compute intents, May nets to the key: UR Dr 23.86; CL nets to zero.
    may = _lines(command, book, ("FY2023-P05",)) + _lines(reclass, book, ("FY2023-P05",))
    assert _net(may) == {CL: 0, REVENUE: -2386, UR: 2386}


def test_s14_r07_reversal_opens_the_next_period_late_chk_091() -> None:
    command, reclass, book = _runs(LATE_091, "february-view")
    assert _lines(command, book, ("FY2023-P02",)) == []
    # January reclass Dr 15002 / Cr 21002 58.85, then Dr 21002 / Cr 15002 58.85 on 1 February.
    assert _lines(reclass, book, ("FY2023-P01", "FY2023-P02")) == [
        ("FY2023-P01", RECLASS, "TIME", "POB %231", CL, -5885),
        ("FY2023-P01", RECLASS, "TIME", "POB %231", UR, 5885),
        ("FY2023-P02", REVERSAL, "TIME", "POB %231", CL, 5885),
        ("FY2023-P02", REVERSAL, "TIME", "POB %231", UR, -5885),
    ]
