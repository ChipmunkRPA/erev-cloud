"""JET-03 invoice and JET-04c part targets in ``ENGINE`` mode (ENGINE_SPEC_B Table 14-A; POLICIES
JET-03 CHK-023 and JET-04c CHK-138; lane L5-3, L4-3-Q-19, L5-3-Q-12).

Stage 10 published unconditional billing per ``<contract>@<entity>`` only, while Table 14-A owns
JET-03 per obligation and the stage 13 binding keeps obligation subjects, so ``ENGINE`` mode posted
no receivable. No producer read the receivable contra. The part test builds its inputs by hand; the
compute tests run the CHK-023 and CHK-138 answer-key worlds without a database.
"""

from __future__ import annotations

from typing import cast

import erev_engine
from erev_engine.bundle import BookOutput, OutputBundle
from erev_engine.enums import BookCode
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import part_targets
from erev_engine.stages.state import Target
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT_KEY}@{ENTITY}"


def _state() -> FxState:
    return FxState(
        allocated=allocated_state([]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=(),
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _computed(key_id: str, name: str) -> BookOutput:
    """The book output of the key's single group at checkpoint ``name``."""
    family = key_id.split("-", 1)[0].lower()
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = next(c for c in _build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    output = cast(OutputBundle, erev_engine.compute(bundle))
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    return book


def _lines(book: BookOutput, period_key: str) -> dict[tuple[str, str, str], int]:
    """Σ transaction amounts per (entry kind, side, role) of the intents posted in the period."""
    found: dict[tuple[str, str, str], int] = {}
    for intent in book.posting_intents:
        if intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            key = (intent.entry_kind, line.side, line.account_role)
            found[key] = found.get(key, 0) + line.amount_txn
    return found


def test_jet_04c_part_from_the_receivable_contra() -> None:
    ctx = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    contra = tuple(
        Target(
            BookCode.ASC606,
            ENTITY,
            SUBJECT,
            "receivable_contra",
            period,
            None,
            usd(amount),
            None,
            f"receivable_contra:{SUBJECT}:{period}",
        )
        for period, amount in (("FY2026-P01", "0.00"), ("FY2026-P02", "600000.00"))
    )
    parts = part_targets(ctx, _state(), PartInputs(receivable_contra=contra))
    found = {(p.part, p.period_key): (p.subject_key, p.amount_txn, p.time_txn) for p in parts}
    assert found == {
        ("JET-04c", "FY2026-P01"): (SUBJECT, 0, 0),
        ("JET-04c", "FY2026-P02"): (SUBJECT, usd("600000.00"), 0),
    }
    second = next(p for p in parts if p.period_key == "FY2026-P02")
    assert second.value_inputs == ((f"receivable_contra:{SUBJECT}:FY2026-P02", 1),)


def test_chk_138_engine_mode_posts_the_receivable_and_its_contra() -> None:
    # JET-03 Dr AR 1,000,000.00 / Cr CL; JET-02 Dr CL 400,000.00; JET-04c Dr CL 600,000.00 / Cr RC.
    key_id = "JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA"
    march = _lines(_computed(key_id, "march-close"), "FY2026-P03")
    assert march[("BILLING", "D", "ACCOUNTS_RECEIVABLE")] == usd("1000000.00")
    assert march[("BILLING", "C", "CONTRACT_LIABILITY")] == usd("1000000.00")
    assert march[("RECEIVABLE_CONTRA", "D", "CONTRACT_LIABILITY")] == usd("600000.00")
    assert march[("RECEIVABLE_CONTRA", "C", "RECEIVABLE_CONTRA")] == usd("600000.00")


def test_chk_023_engine_mode_invoice_carries_its_tax() -> None:
    # JET-03 Dr AR 1,080.00 / Cr CL 1,000.00, Cr SALES_TAX_PAYABLE 80.00 (POL-045).
    key_id = "JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING"
    january = _lines(_computed(key_id, "january-close"), "FY2026-P01")
    assert january[("BILLING", "D", "ACCOUNTS_RECEIVABLE")] == usd("1080.00")
    assert january[("BILLING", "C", "CONTRACT_LIABILITY")] == usd("1000.00")
    assert january[("BILLING", "C", "SALES_TAX_PAYABLE")] == usd("80.00")
