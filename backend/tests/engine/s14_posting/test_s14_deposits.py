"""JET-01b part targets from the stage 02 deposit measures (ENGINE_SPEC S02-R-08; ENGINE_SPEC_B
Table 14-A rows JET-01b receipt, criteria met, refund and 25-7 revenue; S14-R-25; lane L5-5,
L4-1-Q-15, CHK-021; D-91 gaps (iv), (x); END-4b).

Stage 02 folds the deposit ledger of a ``NOT_A_CONTRACT`` contract into EMOD-12 cumulative targets,
and the templates and amount classes of the JET-01b parts exist, but no stage 14 producer read the
targets, so a receipt posted nothing and the ``DEPOSIT_LIABILITY`` lines never reached the
subledger. The world is CHK-021: USD 20.00 received each month from January 2026 while the contract
fails Step 1, criteria met on 30 June, and one refund stands in for a termination refund. END-4b
binds the 25-7 revenue measure too: the part posts per ``IN_SCOPE_606`` obligation from the stage
09 ``deposit_revenue_share`` targets (EVENT at an event, TIME for the ``deposit_revenue_time_share``
of a dated point), the s13 and s14 part sets read one constant, and a foreign-currency release is
split over the obligations by the attribution weights (D-91 FX2: [75,333, 37,667] of 113,000). No
database.
"""

from __future__ import annotations

from fractions import Fraction

import erev_engine
import pytest
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import s13_books
from erev_engine.stages.s09_recognition import DEPOSIT_SHARE_MEASURE, DEPOSIT_TIME_SHARE_MEASURE
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s14_posting import (
    DEPOSIT_PART_MEASURES,
    DEPOSIT_REVENUE_MEASURE,
    DEPOSIT_REVENUE_PART,
    PartInputs,
)
from erev_engine.stages.s14_posting.targets import part_targets
from erev_engine.stages.state import Target
from support import bundles, intent_totals
from support import cpc_worlds as cpc
from support import step1_worlds as w
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT_KEY}@{ENTITY}"
PERIODS = [f"FY2026-P{month:02d}" for month in range(1, 7)]


def _target(measure: str, period: str, amount: str) -> Target:
    node = f"{measure}:{SUBJECT}:{period}"
    return Target(BookCode.ASC606, ENTITY, SUBJECT, measure, period, None, usd(amount), None, node)


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


OBLIGATION = f"{CONTRACT_KEY}/POB-01"


def _share(measure: str, period: str, amount: str, subject: str = OBLIGATION) -> Target:
    node = f"{measure}:{subject}:{period}"
    return Target(BookCode.ASC606, ENTITY, subject, measure, period, None, usd(amount), None, node)


def _allocated_state() -> FxState:
    """An allocated state with one 1,200.00 point-in-time obligation of ``K-01`` (END-4b: the
    amended test runs on an allocated state so the 25-7 part can name its obligations)."""
    goods = obligation(
        "POB-01",
        [segment(Fraction(1200), usd("1200.00"), start=None, end=None, measure="POINT_IN_TIME")],
        method="POINT_IN_TIME",
        convention=None,
    )
    return FxState(
        allocated=allocated_state([goods]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=(),
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def test_jet_01b_parts_from_the_deposit_measures() -> None:
    """CHK-021 with a 25-7 recognition in May (END-4b, amended on an allocated state): the receipt,
    criteria met and refund parts as before; the 25-7 revenue part per obligation from the stage 09
    share, EVENT when the recognition happened at an event (no time share) and TIME for the
    ``deposit_revenue_time_share`` of a dated point; the s13 and s14 part sets read one constant;
    a non-zero ``deposit_to_revenue_cum`` raises no rc guard (D-91 gaps (x))."""
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    deposits = (
        *(_target("deposit_received_cum", p, f"{20 * n}.00") for n, p in enumerate(PERIODS, 1)),
        *(_target("deposit_to_contract_liability_cum", p, "0.00") for p in PERIODS[:5]),
        _target("deposit_to_contract_liability_cum", PERIODS[5], "120.00"),
        _target("deposit_refunded_cum", PERIODS[2], "0.00"),
        # The liability is not a JET-01b part amount of this producer; the 25-7 revenue is.
        _target("deposit_liability", PERIODS[4], "100.00"),
        _target("deposit_to_revenue_cum", PERIODS[3], "0.00"),
        _target("deposit_to_revenue_cum", PERIODS[4], "20.00"),
        _target("deposit_to_revenue_cum", PERIODS[5], "20.00"),
    )
    shares = (
        _share(DEPOSIT_SHARE_MEASURE, PERIODS[3], "0.00"),
        _share(DEPOSIT_TIME_SHARE_MEASURE, PERIODS[3], "0.00"),
        _share(DEPOSIT_SHARE_MEASURE, PERIODS[4], "20.00"),
        _share(DEPOSIT_TIME_SHARE_MEASURE, PERIODS[4], "0.00"),  # recognised at an event: EVENT
        _share(DEPOSIT_SHARE_MEASURE, PERIODS[5], "20.00"),
        _share(DEPOSIT_TIME_SHARE_MEASURE, PERIODS[5], "20.00"),  # re-dated to a close: TIME
    )
    parts = part_targets(
        ctx, _allocated_state(), PartInputs(deposits=deposits, deposit_revenue=shares)
    )
    found = {
        (part.part, part.period_key): (part.amount_txn, part.amount_functional) for part in parts
    }
    assert found[("JET-01b receipt", "FY2026-P05")] == (10000, 10000)
    assert found[("JET-01b receipt", "FY2026-P06")] == (12000, 12000)
    assert found[("JET-01b criteria met", "FY2026-P05")] == (0, 0)
    assert found[("JET-01b criteria met", "FY2026-P06")] == (12000, 12000)
    assert found[("JET-01b refund", "FY2026-P03")] == (0, 0)
    assert found[(DEPOSIT_REVENUE_PART, "FY2026-P04")] == (0, 0)
    assert found[(DEPOSIT_REVENUE_PART, "FY2026-P05")] == (2000, 2000)
    assert {part.part for part in parts} == {
        "JET-01b receipt",
        "JET-01b criteria met",
        "JET-01b refund",
        DEPOSIT_REVENUE_PART,
    }
    receipt = next(p for p in parts if (p.part, p.period_key) == ("JET-01b receipt", "FY2026-P06"))
    assert (receipt.subject_key, receipt.entity, receipt.time_txn) == (SUBJECT, ENTITY, 0)
    assert receipt.value_inputs == ((f"deposit_received_cum:{SUBJECT}:FY2026-P06", 1),)
    may = next(p for p in parts if (p.part, p.period_key) == (DEPOSIT_REVENUE_PART, "FY2026-P05"))
    assert (may.subject_key, may.entity, may.time_txn, may.time_functional) == (
        OBLIGATION,
        ENTITY,
        0,
        0,
    )
    assert may.value_inputs == ((f"{DEPOSIT_SHARE_MEASURE}:{OBLIGATION}:FY2026-P05", 1),)
    june = next(p for p in parts if (p.part, p.period_key) == (DEPOSIT_REVENUE_PART, "FY2026-P06"))
    assert (june.amount_txn, june.time_txn, june.time_functional) == (2000, 2000, 2000)
    assert june.node_ids == (
        f"{DEPOSIT_SHARE_MEASURE}:{OBLIGATION}:FY2026-P06",
        f"{DEPOSIT_TIME_SHARE_MEASURE}:{OBLIGATION}:FY2026-P06",
    )
    # One constant binds both part sets (D-91 gaps (x)): stage 13 filters with the stage 14 set.
    assert DEPOSIT_PART_MEASURES == {
        "deposit_received_cum",
        "deposit_to_contract_liability_cum",
        "deposit_refunded_cum",
        DEPOSIT_REVENUE_MEASURE,
    }
    assert not hasattr(s13_books, "_DEPOSIT_PARTS_BOUND")  # the rc constant and guard are gone


def test_jet_01b_25_7_revenue_without_its_attribution_fails_closed() -> None:
    """A non-zero recognition whose stage 09 shares are absent, or whose shares do not sum to it,
    raises ``ENGINE_INVARIANT_VIOLATED`` (S14-R-25); a zero recognition without shares binds no
    part."""
    ctx = book_context(bundles.entity(months=6), book_code="ASC606", currency="USD")
    target = _target("deposit_to_revenue_cum", PERIODS[4], "20.00")
    with pytest.raises(EngineError) as raised:
        part_targets(ctx, _allocated_state(), PartInputs(deposits=(target,)))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    short = (_share(DEPOSIT_SHARE_MEASURE, PERIODS[4], "19.00"),)
    with pytest.raises(EngineError):
        part_targets(ctx, _allocated_state(), PartInputs(deposits=(target,), deposit_revenue=short))
    zero = _target("deposit_to_revenue_cum", PERIODS[4], "0.00")
    assert part_targets(ctx, _allocated_state(), PartInputs(deposits=(zero,))) == ()


def test_fx2_foreign_deposit_release_remeasured_and_split_by_the_attribution_weights() -> None:
    """FX2 (D-91 gaps (iv), the FX-CHK-084-B rates 1.1000 receipt, 1.1200 January closing, 1.1300
    settlement): EUR 1,000.00 received 10 January by a USD entity, two goods L1 2,000.00 and L2
    1,000.00 (weights 2 : 1), the 25-7(c) point 15 February. Release 100,000 transaction / 113,000
    functional; JET-10d 2,000 at the January close (110,000 → 112,000) and 1,000 at settlement
    (112,000 → 113,000), total 3,000; the two-obligation split [66,667, 33,333] transaction and
    [75,333, 37,667] functional, the functional split over the attribution weights."""
    value = w.eur_deposit()
    command = erev_engine.compute(value)
    (book,) = command.books
    assert w.journal(book) == [
        ("FY2026-P01", "DEPOSIT", "EVENT", "BILLING_CLEARING", "D", 100000, 110000, None),
        ("FY2026-P01", "DEPOSIT", "EVENT", "DEPOSIT_LIABILITY", "C", 100000, 110000, None),
        ("FY2026-P02", "FX_REMEASUREMENT", "EVENT", "DEPOSIT_LIABILITY", "C", 0, 1000, None),
        ("FY2026-P02", "FX_REMEASUREMENT", "EVENT", "FX_GAIN_LOSS", "D", 0, 1000, None),
    ]
    assert [
        (
            r.period_key,
            r.columns["deposit_liability_txn"],
            r.columns["deposit_liability_functional"],
        )
        for r in book.balances
    ] == [
        ("FY2026-P01", 100000, 112000),
        ("FY2026-P02", 0, 0),
    ]
    release_output = intent_totals.close_pass(value, [command], "CLOSE_RELEASE")
    (release,) = release_output.books
    assert w.journal(release) == [
        ("FY2026-P01", "FX_REMEASUREMENT", "TIME", "DEPOSIT_LIABILITY", "C", 0, 2000, None),
        ("FY2026-P01", "FX_REMEASUREMENT", "TIME", "FX_GAIN_LOSS", "D", 0, 2000, None),
        ("FY2026-P02", "REVENUE_RECOGNITION", "TIME", "DEPOSIT_LIABILITY", "D", 33333, 37667, None),
        ("FY2026-P02", "REVENUE_RECOGNITION", "TIME", "DEPOSIT_LIABILITY", "D", 66667, 75333, None),
        ("FY2026-P02", "REVENUE_RECOGNITION", "TIME", "REVENUE", "C", 33333, 37667, None),
        ("FY2026-P02", "REVENUE_RECOGNITION", "TIME", "REVENUE", "C", 66667, 75333, None),
    ]
    by_obligation = {
        item.dimensions["obligation_key"]: (item.amount_txn, item.amount_functional)
        for intent in release.posting_intents
        if intent.entry_kind == "REVENUE_RECOGNITION"
        for item in intent.lines
        if item.account_role == "REVENUE"
    }
    assert by_obligation == {"L1": (66667, 75333), "L2": (33333, 37667)}
    fx_pass = intent_totals.close_pass(value, [command, release_output], "FX_REMEASUREMENT")
    assert (
        fx_pass.books[0].posting_intents == ()
    )  # the release pass already posted the January close
    assert cpc.trace_mismatches(book.trace) == [] and cpc.trace_mismatches(release.trace) == []
