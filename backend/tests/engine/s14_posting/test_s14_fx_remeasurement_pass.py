"""JET-10 at period end: compute, then the ``FX_REMEASUREMENT`` close pass (L6-5; D-85a, L6-2-Q-2).

ENGINE_SPEC_B Table 14-A and S14-R-05 class the period-end JET-10a, 10a′, 10b and 10d amounts as
``TIME`` amounts of the ``FX_REMEASUREMENT`` pass, and 05 RCP-08(b) has the close run post them
over the posted compute intents, before ``NETTING_RECLASS``. Stage 12 measures the remeasurement
(§12.2.3), but ``compute`` posts only ``EVENT`` amounts, so no checkpoint held the FX line. These
tests run the answer-key worlds without a database: ``compute`` posts no period-end remeasurement,
and the pass over its intents gives the keys' figures.
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

FX = "FX_REMEASUREMENT"
CL, GAIN_LOSS = "CONTRACT_LIABILITY", "FX_GAIN_LOSS"
FX_081 = "FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE"
FX_082 = "FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22"
LATE_181 = "LATE-POL-181-FX-LATE-DELIVERY-AT-EFFECTIVE-DATE-RATES"

Line = tuple[str, str, str, str, int, int]  # (period, entry kind, class, role, txn, functional)


def _runs(key_id: str, name: str) -> tuple[OutputBundle, OutputBundle, str]:
    """``compute`` and the ``FX_REMEASUREMENT`` pass over its intents for checkpoint ``name``."""
    loaded = load(ANSWER_KEY_ROOT / key_id.split("-", 1)[0].lower() / f"{key_id}.yaml")
    checkpoint = next(c for c in _build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    command = cast(OutputBundle, erev_engine.compute(bundle))
    with decimal.localcontext(DECIMAL_CONTEXT):
        remeasured = intent_totals.close_pass(bundle, [command], FX)
    return command, remeasured, checkpoint.book


def _fx_lines(output: OutputBundle, book_code: str, periods: tuple[str, ...]) -> list[Line]:
    """Signed amounts (debit positive) of the book's ``FX_REMEASUREMENT`` intents in ``periods``."""
    (book,) = [item for item in output.books if item.book_code == book_code]
    return sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
            line.amount_functional if line.side == "D" else -line.amount_functional,
        )
        for intent in book.posting_intents
        if intent.entry_kind == FX and intent.posting_period_key in periods
        for line in intent.lines
    )


def test_l6_5_fx_pass_posts_the_jet_10b_override_remeasurement() -> None:
    """FX-CHK-082 `asc606-january-close`: under the POL-163 override the open EUR 11,000.00 at the
    January closing 1.1200 is USD 12,320.00 against carrying 12,090.00, so the pass posts JET-10b
    Dr FX_GAIN_LOSS 230.00 / Cr CONTRACT_LIABILITY 230.00 (S12-R-10; CHK-082). Compute posts
    none."""
    command, remeasured, book = _runs(FX_082, "asc606-january-close")
    assert _fx_lines(command, book, ("FY2026-P01",)) == []
    assert _fx_lines(remeasured, book, ("FY2026-P01",)) == [
        ("FY2026-P01", FX, "TIME", CL, 0, -23000),
        ("FY2026-P01", FX, "TIME", GAIN_LOSS, 0, 23000),
    ]


def test_l6_5_fx_pass_posts_the_jet_10a_asset_remeasurement() -> None:
    """FX-CHK-081 `february-close`: asset layers remeasured to the closing rate, JET-10a Dr
    CONTRACT_LIABILITY / Cr FX_GAIN_LOSS 10.00 in January (1,110.00 to 1,120.00) and 30.00 in
    February (2,250.00 to 2,280.00; S12-R-09; CHK-081). Compute posts none."""
    command, remeasured, book = _runs(FX_081, "february-close")
    periods = ("FY2026-P01", "FY2026-P02")
    assert _fx_lines(command, book, periods) == []
    assert _fx_lines(remeasured, book, periods) == [
        ("FY2026-P01", FX, "TIME", CL, 0, 1000),
        ("FY2026-P01", FX, "TIME", GAIN_LOSS, 0, -1000),
        ("FY2026-P02", FX, "TIME", CL, 0, 3000),
        ("FY2026-P02", FX, "TIME", GAIN_LOSS, 0, -3000),
    ]


def test_l6_5_locked_period_remeasurement_lands_untagged_in_the_first_open_period() -> None:
    """LATE-POL-181 `february-close`: January is locked when the late delivery arrives. POLICIES
    ALG-09 step 5 and S12-R-13: the replay revalues the asset layer at the January average 1.1100
    (USD 5,550.00), the January remeasurement is not reposted, and the cumulative difference to the
    February closing 1.1400 (150.00) posts in February without origin. Compute carries the revenue
    relief with origin FY2026-P01 and no remeasurement; the pass posts JET-10a 150.00 untagged."""
    command, remeasured, book = _runs(LATE_181, "february-close")
    periods = ("FY2026-P01", "FY2026-P02")
    assert _fx_lines(command, book, periods) == []
    (compute_book,) = [item for item in command.books if item.book_code == book]
    carried = sum(
        line.amount_functional if line.side == "D" else -line.amount_functional
        for intent in compute_book.posting_intents
        if intent.origin_period_key == "FY2026-P01"
        for line in intent.lines
        if line.account_role == CL
    )
    assert carried == 555000
    assert _fx_lines(remeasured, book, periods) == [
        ("FY2026-P02", FX, "TIME", CL, 0, 15000),
        ("FY2026-P02", FX, "TIME", GAIN_LOSS, 0, -15000),
    ]
    (pass_book,) = [item for item in remeasured.books if item.book_code == book]
    origins = {i.origin_period_key for i in pass_book.posting_intents if i.entry_kind == FX}
    assert origins == {None}
