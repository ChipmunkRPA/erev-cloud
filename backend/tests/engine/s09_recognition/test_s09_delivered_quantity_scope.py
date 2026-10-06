"""T-CON-11 ``delivered_quantity_cum`` by POL-053 ``returns.returned_units_scope`` (D-87 L5-3-Q-5).

``delivered_quantity_cum`` is delivered − returned only when the obligation's resolved POL-053 is
``RESTORE_REMAINING_QUANTITY``; under ``REDUCE_CONTRACT_QUANTITY`` it is gross delivered
(606-10-55-23, 55-27). ``returned_quantity_cum`` and the revenue formulas are unchanged. Before the
fix the column was always net, so ``RET-JS-03`` published 384 after 16 returns against the keyed
400, while ``RET-CHK-061-GT08`` (``RESTORE_REMAINING_QUANTITY``, golden Contract 1) keeps 0.0.

The worlds are the answer keys, built by the engine runner; no database.
"""

from __future__ import annotations

from typing import cast

import erev_engine
from erev_engine.bundle import BookOutput, InputBundle, OutputBundle
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles


def _columns(path: str, name: str, subject_key: str) -> tuple[object, object]:
    checkpoint = next(
        c for c in _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / path)) if c.name == name
    )
    (bundle,) = checkpoint.bundles
    output = cast(OutputBundle, erev_engine.compute(cast(InputBundle, bundle)))
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    (version,) = [
        v for v in cast(BookOutput, book).obligation_versions if v.subject_key == subject_key
    ]
    return version.columns["delivered_quantity_cum"], version.columns["returned_quantity_cum"]


def test_l7_5_delivered_quantity_is_gross_under_reduce_contract_quantity() -> None:
    # RET-CHK-029-S3-EX22 (REDUCE_CONTRACT_QUANTITY): 100 transferred, 2 returned.
    assert _columns("ret/RET-CHK-029-S3-EX22.yaml", "end-of-february", "C-RET/L1-PROD") == (100, 2)
    # RET-JS-03 (POL-053 by default REDUCE_CONTRACT_QUANTITY): 400 transferred, 16 returned.
    assert _columns(
        "ret/RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET.yaml", "window-expired", "JS-03/L1-MACHINES"
    ) == (400, 16)


def test_l7_5_delivered_quantity_is_net_under_restore_remaining_quantity() -> None:
    # RET-CHK-061-GT08 (RESTORE_REMAINING_QUANTITY): 3 delivered, 3 returned on 30 April.
    assert _columns("ret/RET-CHK-061-GT08.yaml", "end-april", "Contract 1/POB %231") == (0, 3)
