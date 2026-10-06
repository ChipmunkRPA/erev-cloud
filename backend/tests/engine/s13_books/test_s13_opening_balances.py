"""Opening-balance flows through stages 10, 13 and 14 (ENGINE_SPEC S07-R-05, S07-R-08; ENGINE_SPEC_B
S10-R-03, S14-R-26 rev 1.11; BUILD_SPEC ENB-9; CHK-121; lane ENG-C5).

The ERP already holds the cutover balances, so the stage 07 baseline is deemed posted: no period
ending on or before the cutover emits an intent, the first open period posts the movement only, and
``billed_cum`` carries the baseline from the cutover date so the position is a contract liability.
Measured on the base 3f6a75e (``.run/eng-c5/probe-flow-base.jsonl``): FY2026-P01 carried
Dr CONTRACT_LIABILITY / Cr REVENUE 120,000.00 with origin FY2025-P12 and ``billed_cum`` was 0, so
the position was an asset of 130,000.00 (7,500.00 in IFRS15). Figures: ``.run/eng-c5/derive.py``.
No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import erev_engine
import pytest
from erev_engine.stages import STAGES, s01_canonicalize, s13_books
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s12_fx_entities.layers import ASSET_ROLES
from erev_engine.trace import TraceBuilder
from support import bundles, intent_totals
from support import cpc_worlds as cpc
from support import onboarding_worlds as w

P01 = ("FY2026-P01", "REVENUE_RECOGNITION", "EVENT")


def _book(value, code: str):
    (book,) = [item for item in erev_engine.compute(value).books if item.book_code == code]
    return book


def test_chk_121_asc606_january_relieves_the_opening_liability() -> None:
    """ASC606 (as if originated): the baseline 120,000.00 through the cutover is deemed posted;
    FY2026-P01 posts Dr CONTRACT_LIABILITY / Cr REVENUE 10,000.00 only (no FY2025-P12 carry);
    ``billed_cum`` is 240,000.00 from the cutover; the contract liability at January is 110,000."""
    book = _book(w.chk_121(), "ASC606")
    assert w.journal(book) == [
        (*P01, "CONTRACT_LIABILITY", "D", 1000000, ""),
        (*P01, "REVENUE", "C", 1000000, ""),
    ]
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 11000000
    assert cpc.balance(book, "FY2026-P01", "contract_asset_txn") == 0
    billed = cpc.node_values(book, "billed_cum")
    assert billed[f"billed_cum:{w.SUBJECT}:FY2025-P12"] == "240000.00"
    assert billed[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "240000.00"
    assert billed[f"billed_cum:{w.SUBJECT}:FY2025-P11"] == "0.00"  # before the cutover: the ledger
    assert cpc.trace_mismatches(book.trace) == []


def test_chk_121_ifrs15_january_relieves_the_fair_value_liability() -> None:
    """IFRS15 (fair value IFRS 3): 90,000.00 recognised from 0 over the remaining 12 months; the
    baseline billed is the fair-value share, so January posts 7,500.00 against 82,500.00."""
    book = _book(w.chk_121(), "IFRS15")
    assert w.journal(book) == [
        (*P01, "CONTRACT_LIABILITY", "D", 750000, ""),
        (*P01, "REVENUE", "C", 750000, ""),
    ]
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 8250000
    assert cpc.balance(book, "FY2026-P01", "contract_asset_txn") == 0
    assert cpc.node_values(book, "billed_cum")[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "90000.00"
    assert cpc.trace_mismatches(book.trace) == []


def test_chk_121_year_end_2026_settles_both_books() -> None:
    """At 2026-12-31 each open month posted its movement (10,000.00 / 7,500.00), FY2026-P12
    included, and the contract liability is 0 in both books; no line carries FY2025-P12."""
    value = w.chk_121(as_of=date(2026, 12, 31))
    for code, monthly in (("ASC606", 1000000), ("IFRS15", 750000)):
        book = _book(value, code)
        lines = w.journal(book)
        assert [item for item in lines if item[6]] == []  # no closed-period carry
        assert [item for item in lines if item[0] == "FY2026-P12"] == [
            ("FY2026-P12", "REVENUE_RECOGNITION", "EVENT", "CONTRACT_LIABILITY", "D", monthly, ""),
            ("FY2026-P12", "REVENUE_RECOGNITION", "EVENT", "REVENUE", "C", monthly, ""),
        ]
        assert cpc.role_net(book, "REVENUE") == {f"FY2026-P{m:02d}": -monthly for m in range(1, 13)}
        assert cpc.balance(book, "FY2026-P12", "contract_liability_txn") == 0
        assert cpc.balance(book, "FY2026-P12", "contract_asset_txn") == 0


def test_chk_121_cutover_posts_nothing_and_a_repeat_compute_posts_nothing_new() -> None:
    """A compute known at the cutover posts nothing (the ERP holds the balances; FY2025-P12 is
    closed and its target is the baseline); a compute with January's intents posted adds nothing."""
    at_cutover = w.chk_121(as_of=date(2025, 12, 31))
    for code in ("ASC606", "IFRS15"):
        assert _book(at_cutover, code).posting_intents == ()
    value = w.chk_121()
    first = erev_engine.compute(value)
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    for book in erev_engine.compute(posted).books:
        assert book.posting_intents == ()


def test_chk_121_pre_cutover_invoice_lines_are_replaced_by_the_baseline() -> None:
    """S10-R-03 rev 1.11: the acquiree's invoice of 240,000.00 (ERP, 1 June 2025) is in the ledger
    and in the baseline; from the cutover the baseline replaces it, so ``billed_cum`` stays
    240,000.00 (not 480,000.00), the net position ties (S12-INV-03) and January posts 10,000.00."""
    invoice = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        date(2025, 6, 1),
        {
            "invoice_number": "INV-ACQ-1",
            "line_external_id": "INV-ACQ-1-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal("240000.00"),
            "issue_date": date(2025, 6, 1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    book = _book(w.chk_121(extra=[invoice]), "ASC606")
    billed = cpc.node_values(book, "billed_cum")
    assert billed[f"billed_cum:{w.SUBJECT}:FY2025-P06"] == "240000.00"  # the ledger line
    assert billed[f"billed_cum:{w.SUBJECT}:FY2025-P12"] == "240000.00"  # the baseline replaces it
    assert billed[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "240000.00"
    assert w.journal(book, "REVENUE", "CONTRACT_LIABILITY", "CONTRACT_ASSET") == [
        (*P01, "CONTRACT_LIABILITY", "D", 1000000, ""),
        (*P01, "REVENUE", "C", 1000000, ""),
    ]
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 11000000
    assert cpc.trace_mismatches(book.trace) == []


def _prior_invoice(amount: str, recorded: datetime | None = None):
    invoice = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        date(2025, 6, 1),
        {
            "invoice_number": "INV-ACQ-1",
            "line_external_id": "INV-ACQ-1-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal(amount),
            "issue_date": date(2025, 6, 1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    return invoice if recorded is None else dataclasses.replace(invoice, recorded_at=recorded)


@pytest.mark.parametrize("prior", ["240000.00", "300000.00"])
def test_c5_r1_ifrs15_remaining_billing_is_not_double_counted_by_a_prior_invoice(prior) -> None:
    """C5-R1 (Codex PRODUCTION-C5-OPENING-REVIEW-d1f45c4): IFRS15 with the acquiree's invoice of
    ``prior`` dated 1 June 2025 in the ledger and the payload's remaining billing 0. The baseline
    90,000.00 replaces the pre-cutover line in ``billed_cum`` and in the billing before the
    OPENING_BALANCE boundary alike, so T-CON-11 ``remaining_billing`` is 0 (d1f45c4 gave 240,000 /
    300,000: lines + baseline before the boundary); January's 7,500.00 / 82,500.00 are unchanged."""
    book = _book(w.chk_121(extra=[_prior_invoice(prior)]), "IFRS15")
    (version,) = book.obligation_versions
    assert version.columns["remaining_billing"] == 0
    assert version.columns["billed_cum"] == 9000000
    node = next(n for n in book.trace.nodes if n.measure == "remaining_billing")
    assert (node.value, node.params["billed_before"], node.params["plan"]) == (
        "0.00",
        "9000000",
        "0",
    )
    assert w.journal(book) == [
        (*P01, "CONTRACT_LIABILITY", "D", 750000, ""),
        (*P01, "REVENUE", "C", 750000, ""),
    ]
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 8250000
    assert cpc.trace_mismatches(book.trace) == []


def test_c5_r1_monotonic_record_times_reproduce_the_same_figures() -> None:
    """The record-order control of the review: events 1 to 3 and the prior invoice recorded on
    1 January 2026 at 12:00:01 to 12:00:04 UTC (strictly increasing, before the 31 January
    known_at) keep their effective dates; both books give the same journals, balances and
    remaining billing."""
    value = w.chk_121(extra=[_prior_invoice("240000.00")])
    stamped = tuple(  # the bundle order (effective date) is kept; record times follow the stream
        dataclasses.replace(
            event, recorded_at=datetime(2026, 1, 1, 12, 0, event.stream_version, tzinfo=UTC)
        )
        for event in value.events
    )
    variant = dataclasses.replace(value, events=stamped)
    for code, monthly, liability in (("ASC606", 1000000, 11000000), ("IFRS15", 750000, 8250000)):
        book = _book(variant, code)
        assert w.journal(book) == [
            (*P01, "CONTRACT_LIABILITY", "D", monthly, ""),
            (*P01, "REVENUE", "C", monthly, ""),
        ]
        assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == liability
        (version,) = book.obligation_versions
        assert version.columns["remaining_billing"] == 0


def test_chk_121_stage_12_layers_tie_to_the_net_position_in_both_books() -> None:
    """S12-INV-03 with the baseline counted (the condition on the `_opening_flows` sibling beside
    ENG-B4's `_control_flows`): in both books, at the cutover period end and at January, Σ open
    CONTRACT_LIABILITY layers − Σ open asset layers equals the stage 10 net position that counts
    the baseline in B_u (ASC606 240,000 − 120,000 = 120,000.00 then 110,000.00; IFRS15 90,000.00
    then 82,500.00); no S12-INV-03 finding; the opening flow is the only control-role credit."""
    value = w.chk_121()
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=erev_engine.ENGINE_VERSION))
    expected = {
        "ASC606": {"FY2025-P12": 12000000, "FY2026-P01": 11000000},
        "IFRS15": {"FY2025-P12": 9000000, "FY2026-P01": 8250000},
    }
    seen: set[str] = set()
    for result in s13_books.run_books(cb, STAGES):
        fx = result.states["12"]
        balances = result.states["10"]
        assert isinstance(fx, FxState) and isinstance(balances, BalanceState)
        positions = {t.period_key: t.value for t in balances.positions}
        for period, net_position in expected[str(result.book)].items():
            assert positions[period] == net_position
            layers = [item for item in fx.layer_balances if item.period_key == period]
            liability = sum(
                item.txn_open for item in layers if item.balance_role == "CONTRACT_LIABILITY"
            )
            assets = sum(item.txn_open for item in layers if item.balance_role in ASSET_ROLES)
            assert liability - assets == net_position
        assert [f for f in fx.findings if f.detail.get("rule") == "S12-INV-03"] == []
        # The opening flow: the ERP's billing at the cutover (240,000 / 90,000), which settles the
        # relief's asset layer first and opens the liability layer at the net position (S12-R-03).
        source = f"{w.CONTRACT}@{w.ENTITY}@2025-12-31/opening_billed_cum"
        opening = [m for m in fx.layer_movements if m.source_key == source]
        assert {m.effective_date.isoformat() for m in opening} == {"2025-12-31"}
        assert sum(m.amount_txn for m in opening) == (
            24000000 if str(result.book) == "ASC606" else 9000000
        )
        created = [m for m in opening if m.movement_kind == "LIABILITY_LAYER_CREATED"]
        assert [(m.balance_role, m.amount_txn) for m in created] == [
            ("CONTRACT_LIABILITY", expected[str(result.book)]["FY2025-P12"])
        ]
        seen.add(str(result.book))
    assert seen == {"ASC606", "IFRS15"}


def test_d97_13_jet_03_engine_billing_after_a_baseline_counts_post_cutover_invoices_only() -> None:
    """D-97 (13): under POL-004 `billing.posting = ENGINE` the baseline never enters JET-03. Three
    controls tied to the opening and control flows: (a) cutover only — no JET-03 line, January as
    before; (b) a later ENGINE invoice of 1,000.00 on 15 January 2026 posts JET-03 Dr
    ACCOUNTS_RECEIVABLE / Cr CONTRACT_LIABILITY 1,000.00 only (billed_cum 241,000.00, contract
    liability 111,000.00), no 240,000.00; (c) a repeat compute with (b) posted adds nothing."""
    engine = {"billing.posting": "ENGINE"}
    only = _book(w.chk_121(policies=engine), "ASC606")
    assert w.journal(only, "ACCOUNTS_RECEIVABLE") == []
    assert w.journal(only, "REVENUE", "CONTRACT_LIABILITY") == [
        (*P01, "CONTRACT_LIABILITY", "D", 1000000, ""),
        (*P01, "REVENUE", "C", 1000000, ""),
    ]
    later = bundles.event(
        w.CONTRACT,
        4,
        "BILLING_RECORDED",
        date(2026, 1, 15),
        {
            "invoice_number": "INV-2026-1",
            "line_external_id": "INV-2026-1-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal("1000.00"),
            "issue_date": date(2026, 1, 15),
        },
        obligation_keys=[w.OBLIGATION],
    )
    value = w.chk_121(policies=engine, extra=[later])
    first = erev_engine.compute(value)
    (book,) = [b for b in first.books if b.book_code == "ASC606"]
    receivable = w.journal(book, "ACCOUNTS_RECEIVABLE")
    assert [(line[0], line[4], line[5]) for line in receivable] == [("FY2026-P01", "D", 100000)]
    assert [line for line in w.journal(book) if line[5] == 24000000] == []
    assert cpc.node_values(book, "billed_cum")[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "241000.00"
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 11100000
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    for repeat in erev_engine.compute(posted).books:
        assert repeat.posting_intents == ()
