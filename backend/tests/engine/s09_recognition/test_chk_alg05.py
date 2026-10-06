"""POLICIES ALG-05 §2.6 numeric checks and PT-02 through the whole engine (ENC-8).

CHK-050 to CHK-053 (material rights: exercise under CONTINUATION and MODIFICATION, voucher
redemption and expiry, GT-15 policies, loyalty points) and CHK-111 (credit rollover) are asserted
on the answer-key worlds that carry them, computed DB-free through ``erev_engine.compute`` at the
named checkpoints (DG-AK-40). The figures are the POLICIES §2.6.5 and §5.2 tables; the answer
keys themselves are unchanged. No database.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext

import erev_engine
import pytest
from erev_engine.bundle import BookOutput
from erev_engine.money import DECIMAL_CONTEXT
from support.answer_keys.loader import load_all
from support.answer_keys.runners import _build_checkpoint_bundles

pytestmark: list[pytest.MarkDecorator] = []


def _book(key_id: str, checkpoint: str) -> BookOutput:
    """The ASC606 book output of ``checkpoint`` of the key's single combination group."""
    loaded = load_all(ids=[key_id])[0]
    found = next(cp for cp in _build_checkpoint_bundles(loaded) if cp.name == checkpoint)
    (bundle,) = found.bundles
    with localcontext(DECIMAL_CONTEXT):
        output = erev_engine.compute(bundle)
    return next(book for book in output.books if book.book_code == "ASC606")


def _obligations(book: BookOutput) -> Mapping[str, Mapping[str, object]]:
    return {str(ob.columns["obligation_key"]): ob.columns for ob in book.obligation_versions}


def _money(columns: Mapping[str, object], name: str) -> Decimal:
    value = columns[name]
    assert isinstance(value, int)
    return Decimal(value).scaleb(-2)


def _exact(columns: Mapping[str, object], name: str, places: int) -> Decimal:
    value = columns[name]
    numerator, denominator = value.numerator, value.denominator  # type: ignore[attr-defined]
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal(1).scaleb(-places))


def test_chk_050_exercise_recognition() -> None:
    """CHK-050 (EX-06-E): allocation P1 750.00, P2 166.67, MR 83.33. CONTINUATION recognises P3
    383.33 at transfer (allocation 83.33 + 300.00) with P2 unchanged; MODIFICATION pools 550.00 to
    P2 183.33 and P3 366.67 with no catch-up."""
    inception = _obligations(_book("MR-CHK-050-CONTINUATION", "inception"))
    assert [_money(inception[k], "allocated_amount") for k in ("L1-P1", "L2-P2", "L3-MR")] == [
        Decimal("750.00"),
        Decimal("166.67"),
        Decimal("83.33"),
    ]
    continuation = _obligations(_book("MR-CHK-050-CONTINUATION", "after-exercise"))
    assert _money(continuation["L4-P3"], "allocated_amount") == Decimal("383.33")
    assert _money(continuation["L2-P2"], "allocated_amount") == Decimal("166.67")
    assert _money(continuation["L3-MR"], "allocated_amount") == Decimal("0.00")
    modification = _obligations(_book("MR-CHK-050-MODIFICATION", "after-exercise"))
    assert _money(modification["L2-P2"], "allocated_amount") == Decimal("183.33")
    assert _money(modification["L4-P3"], "allocated_amount") == Decimal("366.67")
    assert _money(modification["L1-P1"], "revenue_cum") == Decimal("750.00")
    assert all(
        _money(columns, "catch_up_cum") == Decimal("0.00") for columns in modification.values()
    )


def test_chk_051_voucher_redemption_and_expiry() -> None:
    """CHK-051 (FASB Example 49): the voucher's allocation 10.71 joins the 30.00 paid on
    redemption, revenue 40.71 on the optioned product; the expiry alternative recognises 10.71 on
    the voucher itself (JET-08; S06-R-25)."""
    redeem = _obligations(_book("MR-CHK-051-S2-EX49-REDEEM", "after-redemption"))
    assert _money(redeem["L3-REDEEM"], "revenue_cum") == Decimal("40.71")
    assert _money(redeem["L2-VOUCHER"], "allocated_amount") == Decimal("0.00")
    expiry_book = _book("MR-CHK-051-S2-EX49-EXPIRY", "after-expiry")
    expiry = _obligations(expiry_book)
    voucher = expiry["L2-VOUCHER"]
    assert (
        _money(voucher, "allocated_amount"),
        _money(voucher, "revenue_cum"),
        _money(voucher, "remaining_allocation"),
    ) == (Decimal("10.71"), Decimal("10.71"), Decimal("0.00"))
    assert str(voucher["satisfaction_status"]) == "SATISFIED"
    assert expiry_book.contract_version is not None
    assert _money(expiry_book.contract_version.columns, "revenue_cum") == Decimal("100.00")
    intents = [
        intent
        for intent in expiry_book.posting_intents
        if intent.subject_key == "C-EX49/L2-VOUCHER" and intent.entry_kind == "REVENUE_RECOGNITION"
    ]
    assert [
        (i.posting_period_key, [(ln.side, ln.account_role, ln.amount_txn) for ln in i.lines])
        for i in intents
    ] == [("FY2026-P01", [("D", "CONTRACT_LIABILITY", 1071), ("C", "REVENUE", 1071)])]


def test_chk_052_gt15_policies() -> None:
    """CHK-052 (golden GT-15, Contract 3 at 2023-09-15): MODIFICATION gives POB #5 1,268.1139,
    POB #1 678.0182 and TP 2,600.00; CONTINUATION gives POB #5 1,833.7676, POB #1 334.3408,
    POB #2 306.8265 and POB #3 125.0651 with no catch-up and TP 2,600.00."""
    modification_book = _book("MR-CHK-052-GT15-MODIFICATION", "gt15-end-september")
    modification = _obligations(modification_book)
    assert _exact(modification["POB #5"], "allocated_exact", 4) == Decimal("1268.1139")
    assert _exact(modification["POB #1"], "allocated_exact", 4) == Decimal("678.0182")
    assert modification_book.contract_version is not None
    assert _money(modification_book.contract_version.columns, "transaction_price") == Decimal(
        "2600.00"
    )
    continuation_book = _book("MR-CHK-052-GT15-CONTINUATION", "end-september-continuation")
    continuation = _obligations(continuation_book)
    assert [
        _exact(continuation[k], "allocated_exact", 4)
        for k in ("POB #5", "POB #1", "POB #2", "POB #3")
    ] == [
        Decimal("1833.7676"),
        Decimal("334.3408"),
        Decimal("306.8265"),
        Decimal("125.0651"),
    ]
    # The exercise adds no catch-up under CONTINUATION: the legacy July and August boundaries of
    # GT-13 and GT-14 carry the same catch-ups in both worlds, and only MODIFICATION adds the
    # POB #3 catch-up of +32.14 (POLICIES CHK-052).
    for key in ("POB #1", "POB #2", "POB #4", "POB #5"):
        assert _money(continuation[key], "catch_up_cum") == _money(
            modification[key], "catch_up_cum"
        )
    assert _money(modification["POB #3"], "catch_up_cum") - _money(
        continuation["POB #3"], "catch_up_cum"
    ) == Decimal("32.14")
    assert continuation_book.contract_version is not None
    assert _money(continuation_book.contract_version.columns, "transaction_price") == Decimal(
        "2600.00"
    )


def test_chk_053_loyalty_points() -> None:
    """CHK-053 (FASB Example 52; S09-R-31): allocation 91,324.20 / 8,675.80; points revenue P1
    4,109.59 and cumulative P2 7,602.50 = round(X × 8,500 ÷ 9,700) with X = 100,000 × 9,500 ÷
    109,500 (D-11a); remaining points allocation 4,566.21 and 1,073.30."""
    p1 = _obligations(_book("MR-CHK-053-S2-EX52", "end-p1"))
    assert _money(p1["L1-SALES"], "allocated_amount") == Decimal("91324.20")
    points = p1["L2-POINTS"]
    assert (
        _money(points, "allocated_amount"),
        _money(points, "revenue_cum"),
        _money(points, "remaining_allocation"),
    ) == (Decimal("8675.80"), Decimal("4109.59"), Decimal("4566.21"))
    p2 = _obligations(_book("MR-CHK-053-S2-EX52", "end-p2"))["L2-POINTS"]
    assert (_money(p2, "revenue_cum"), _money(p2, "remaining_allocation")) == (
        Decimal("7602.50"),
        Decimal("1073.30"),
    )


def test_chk_111_credit_rollover() -> None:
    """CHK-111 (PT-02; POL-241): Year 1 revenue 70,000.00 plus breakage 7,777.78, revenue_cum
    77,777.78 and liability 22,222.22. Renewed: Year 2 adds 20,000.00 plus 2,222.22 to
    100,000.00. Not renewed: the 22,222.22 is recognised at lapse, revenue_cum 100,000.00."""
    year_1 = _obligations(_book("BRK-CHK-111-RENEWED", "end-year-1"))["L1-CREDITS"]
    assert (_money(year_1, "revenue_cum"), _money(year_1, "remaining_allocation")) == (
        Decimal("77777.78"),
        Decimal("22222.22"),
    )
    renewed = _book("BRK-CHK-111-RENEWED", "end-year-2")
    assert renewed.contract_version is not None
    assert _money(renewed.contract_version.columns, "revenue_cum") == Decimal("100000.00")
    year_2 = [line for line in renewed.schedules if line.subject_key == "C-CREDITS/L1-CREDITS"]
    by_type = {(line.period_key, str(line.line_type)): line.amount for line in year_2}
    assert by_type[("FY2027-P12", "NORMAL")] == 2_000_000
    assert by_type[("FY2027-P12", "BREAKAGE")] == 222_222
    assert by_type[("FY2026-P12", "BREAKAGE")] == 777_778
    lapsed = _book("BRK-CHK-111-LAPSED", "at-lapse")
    assert lapsed.contract_version is not None
    assert _money(lapsed.contract_version.columns, "revenue_cum") == Decimal("100000.00")
    lapse_lines = {
        (line.period_key, str(line.line_type)): line.amount
        for line in lapsed.schedules
        if line.subject_key == "C-CREDITS/L1-CREDITS"
    }
    assert lapse_lines[("FY2027-P01", "BREAKAGE")] == 2_222_222
