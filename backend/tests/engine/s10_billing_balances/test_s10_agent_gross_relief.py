"""JET-02 agent gross relief (D-87 L4-3-Q-24; POLICIES JET-02 agent row, D-76; OQ-AKI-05).

The engine relieved an agent obligation's contract liability by the retained revenue only, kept
``gross_amount_memo`` at the line price, refused FIXED_FEE and SUPPLIER_COST in stage 14 and raised
for an AGENT product without a reviewed record (POB-S2-EX45-AGENT-AGENT, POB-WM-01, POB-WM-05). By
the ruling: (a) the runner supplies the REVIEWED FIXED_FEE record at the line total price; (b) the
memo is the obligation's billing net of credit memos; (c) G_t is the net billing dated on or before
the latest JET-02 transfer up to t, relief = max(G_t, R_t) and S_t = max(0, G_t − R_t); (d) the
position is billed − (R_t + S_t); (e) FIXED_FEE and SUPPLIER_COST split by (R_t, S_t). These tests
run the answer-key worlds without a database.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.enums import PrincipalAgent
from erev_engine.errors import EngineError
from erev_engine.stages.s14_posting import targets
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _Assembler, assert_checkpoints, run_engine
from support.recognition import obligation, segment

AP = "BILLING_CLEARING:AP_SUPPLIER"
WM_05 = "POB-WM-05-HOTEL-MERCHANT-VERSUS-AGENCY"


def _period_key(as_of: date) -> str:
    return f"FY{as_of.year}-P{as_of.month:02d}"  # monthly calendars from January


def _outputs(key_id: str) -> dict[str, tuple[str, OutputBundle]]:
    """Checkpoint name -> (period key, the output of every bundle of the checkpoint, merged)."""
    loaded = load(ANSWER_KEY_ROOT / "pob" / f"{key_id}.yaml")
    out: dict[str, tuple[str, OutputBundle]] = {}
    for checkpoint in _Assembler(loaded).checkpoints():
        outputs = [
            cast(OutputBundle, erev_engine.compute(cast(InputBundle, bundle)))
            for bundle in checkpoint.bundles
        ]
        books = tuple(book for output in outputs for book in output.books)
        merged = dataclasses.replace(outputs[0], books=books)
        out[checkpoint.name] = (_period_key(checkpoint.as_of), merged)
    return out


def _balance(output: OutputBundle, contract: str, period_key: str, column: str) -> object:
    (row,) = [
        item
        for book in output.books
        if book.book_code == "ASC606"
        for item in book.balances
        if item.subject_key.startswith(f"{contract}@") and item.period_key == period_key
    ]
    return row.columns[column]


def _obligation(output: OutputBundle, subject_key: str, column: str) -> object:
    (row,) = [
        item
        for book in output.books
        if book.book_code == "ASC606"
        for item in book.obligation_versions
        if item.subject_key == subject_key
    ]
    return row.columns[column]


def test_l7_6_runner_supplies_the_reviewed_fixed_fee_record_of_an_agent_product() -> None:
    """(a): WM-05 names no PRINCIPAL_AGENT record; EX45 names its own, so it gets none."""
    assembler = _Assembler(load(ANSWER_KEY_ROOT / "pob" / f"{WM_05}.yaml"))
    records = {
        (header.external_id, record.subject_key): dict(record.outcome)
        for checkpoint in assembler.checkpoints()[:1]
        for bundle in checkpoint.bundles
        for header in cast(InputBundle, bundle).contracts
        for record in header.judgements
        if record.topic == "PRINCIPAL_AGENT"
    }
    outcome = {
        "conclusion": "AGENT",
        "gross_to_net_basis": "FIXED_FEE",
        "obligation_key": "L1-STAYS",
    }
    assert records == {
        ("WM-05-AGENCY", "WM-05-AGENCY/L1-STAYS"): {**outcome, "amount": "8000.00"},
        ("WM-05-MERCHANT", "WM-05-MERCHANT/L1-STAYS"): {**outcome, "amount": "19200.00"},
    }
    notes = [note for note in assembler.notes if "L4-3-Q-24" in note]
    assert len(notes) == 2
    assert any("WM-05-MERCHANT L1-STAYS" in note and "amount 19200.00" in note for note in notes)
    ex45 = _Assembler(load(ANSWER_KEY_ROOT / "pob" / "POB-S2-EX45-AGENT-AGENT.yaml"))
    assert not [note for note in ex45.notes if "L4-3-Q-24" in note]


def test_l7_6_agent_position_nets_the_gross_billing_up_to_the_latest_transfer() -> None:
    """(b) to (d): the merchant prepayment stays a liability until the stay transfers, then G
    120,000.00 relieves R 19,200.00 and S 100,800.00; the agency commission earned before its
    invoice has G 0, so relief is R 8,000.00 and the unbilled receivable 8,000.00."""
    outputs = _outputs(WM_05)
    period, feb = outputs["prepaid-before-stay"]
    assert _balance(feb, "WM-05-MERCHANT", period, "contract_liability_txn") == 12_000_000
    period, march = outputs["check-in-month"]
    assert _balance(march, "WM-05-MERCHANT", period, "contract_liability_txn") == 0
    assert _balance(march, "WM-05-AGENCY", period, "contract_liability_txn") == 0
    assert _balance(march, "WM-05-AGENCY", period, "unbilled_receivable_txn") == 800_000
    merchant = "WM-05-MERCHANT/L1-STAYS"
    assert _obligation(march, merchant, "gross_amount_memo") == 12_000_000
    assert _obligation(march, merchant, "position_obligation") == 0
    assert _obligation(march, "WM-05-AGENCY/L1-STAYS", "gross_amount_memo") == 0
    assert _obligation(march, "WM-05-AGENCY/L1-STAYS", "position_obligation") == -800_000
    period, april = outputs["commission-invoiced"]
    assert _balance(april, "WM-05-AGENCY", period, "unbilled_receivable_txn") == 0
    assert _obligation(april, "WM-05-AGENCY/L1-STAYS", "gross_amount_memo") == 800_000


def test_l7_6_fixed_fee_and_supplier_cost_split_by_retained_and_supplier() -> None:
    """(e): weights (R_t, S_t) = (relief − S_t, S_t); nil relief takes the revenue side only;
    COMMISSION_RATE keeps (ρ, 1 − ρ) (EX-14-A)."""
    base = obligation(
        "L1",
        [segment(Fraction(150000), 15_000_000, start=date(2026, 1, 1), end=date(2026, 3, 31))],
        method="UNITS_DELIVERED",
    )
    for basis in ("FIXED_FEE", "SUPPLIER_COST"):
        ob = dataclasses.replace(
            base,
            principal_agent=PrincipalAgent.AGENT,
            gross_to_net={"amount": "150000", "basis": basis},
        )
        assert targets._agent_weights(ob, 30_000_000, 25_500_000) == (
            ("REVENUE", Fraction(4_500_000)),
            (AP, Fraction(25_500_000)),
        )
        assert targets._agent_weights(ob, 0, 0) == (("REVENUE", Fraction(1)), (AP, Fraction(0)))
        with pytest.raises(EngineError, match="supplier share"):
            targets._agent_weights(ob, 100, 101)
    rate = dataclasses.replace(
        base,
        principal_agent=PrincipalAgent.AGENT,
        gross_to_net={"gross_to_net_basis": "COMMISSION_RATE", "rate": "0.15"},
    )
    assert targets._agent_weights(rate, 33_333, 0) == (
        ("REVENUE", Fraction(3, 20)),
        (AP, Fraction(17, 20)),
    )


@pytest.mark.parametrize(
    "key_id",
    [
        "POB-S2-EX45-AGENT-AGENT",
        "POB-WM-01-THIRD-PARTY-COMMISSIONS-NET",
        WM_05,
    ],
)
def test_l7_6_agent_keys_reproduce(key_id: str) -> None:
    """The ruling's check figures: EX45 revenue 50.00 and AP 450.00; WM-01 AP 255,000.00 in
    January and 314,500.00 in March; WM-05 AP 100,800.00 in March and agency UR 8,000.00."""
    loaded = load(ANSWER_KEY_ROOT / "pob" / f"{key_id}.yaml")
    assert_checkpoints(loaded, run_engine(loaded))
