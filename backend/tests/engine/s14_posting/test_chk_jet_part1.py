"""JET template checks, part 1: deposits, sales tax, cancellable invoices, rebates and catch-ups
(BUILD_SPEC END-11; POLICIES §2.3 JET-01b, JET-02, JET-03, JET-04a, JET-04b, JET-06 with CHK-021,
CHK-023 to CHK-026; POL-004, POL-123; ENGINE_SPEC_B §14.2; lane ENG-C8).

Each check runs the CHK answer-key world through the public path — ``erev_engine.compute`` and the
runner's close passes (FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS; RCP-08) — and names the
template lines by their Table 14-A identity (entry kind, side, role, clearing purpose), the
T-CON-09 balances and the T-CON-08 version columns the item body states. Every entry balances in
both currencies (S14-INV-01). The keys' oracles are read, never edited. No database (DG-TST-18).
"""

from __future__ import annotations

from support.jet_lines import Line, run_checkpoint
from support.recognition import usd

CL, REVENUE, AR, TAX = "CONTRACT_LIABILITY", "REVENUE", "ACCOUNTS_RECEIVABLE", "SALES_TAX_PAYABLE"
DL, CLEARING, RL, CA = "DEPOSIT_LIABILITY", "BILLING_CLEARING", "REFUND_LIABILITY", "CONTRACT_ASSET"
DEPOSIT, RECOGNITION, BILLING = "DEPOSIT", "REVENUE_RECOGNITION", "BILLING"
REFUND, RECLASS, REVERSAL = "REFUND_LIABILITY", "NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"

CHK_021 = "JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY"
CHK_023 = "JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING"
CHK_024_A = "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE"
CHK_024_B = "JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE"
CHK_025 = "JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY"
CHK_026 = "JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP"


def _line(kind: str, side: str, role: str, purpose: str = "") -> Line:
    return (kind, side, role, purpose, "")


def test_chk_021_deposit_to_contract_liability() -> None:
    """CHK-021: receipts of 20.00 in months 1 to 6 while NOT_A_CONTRACT, each JET-01b receipt Dr
    BILLING_CLEARING (UNAPPLIED_CASH) 20.00 / Cr DEPOSIT_LIABILITY 20.00 (EVENT); deposit liability
    100.00 at month 5 and 120.00 at month 6 before the criteria are met. At the end of month 6
    JET-01b criteria met Dr DEPOSIT_LIABILITY 120.00 / Cr CONTRACT_LIABILITY 120.00, then JET-02 Dr
    CONTRACT_LIABILITY 120.00 / Cr REVENUE 120.00; closing deposit liability 0.00, contract
    liability 0.00, revenue 120.00 (S02-R-08; POLICIES JET-01b)."""
    may = run_checkpoint(CHK_021, "may-close")
    subject = "C-JE-021@US01"
    for month in range(1, 6):
        period = f"FY2026-P0{month}"
        assert may.txn(period) == {
            _line(DEPOSIT, "C", DL): usd("20.00"),
            _line(DEPOSIT, "D", CLEARING, "UNAPPLIED_CASH"): usd("20.00"),
        }, period
    assert may.balance(subject, "FY2026-P05", "deposit_liability_txn") == usd("100.00")
    assert may.balance(subject, "FY2026-P05", "contract_liability_txn") == 0
    assert may.version("revenue_cum") == 0
    june = run_checkpoint(CHK_021, "june-close-after-criteria-met")
    # The June receipt (Cr DEPOSIT_LIABILITY 20.00) and the criteria-met transfer (Dr
    # DEPOSIT_LIABILITY 120.00) are JET-01b parts of one DEPOSIT entry, so the role nets to Dr
    # DEPOSIT_LIABILITY 100.00 (S14-R-12; the key's block); the six receipts transfer in full.
    assert june.txn("FY2026-P06") == {
        _line(DEPOSIT, "C", CL): usd("120.00"),
        _line(DEPOSIT, "D", CLEARING, "UNAPPLIED_CASH"): usd("20.00"),
        _line(DEPOSIT, "D", DL): usd("100.00"),
        _line(RECOGNITION, "C", REVENUE): usd("120.00"),
        _line(RECOGNITION, "D", CL): usd("120.00"),
    }
    assert usd("120.00") - usd("20.00") == usd("100.00")
    assert june.balance(subject, "FY2026-P06", "deposit_liability_txn") == 0
    assert june.balance(subject, "FY2026-P06", "contract_liability_txn") == 0
    assert june.version("revenue_cum") == usd("120.00")
    # Compute posts the EVENT lines; no close pass adds a deposit or revenue line.
    assert june.txn("FY2026-P06", outputs=june.outputs[1:]) == {}
    june.entries_balance()


def test_chk_023_sales_tax_engine_billing() -> None:
    """CHK-023: in ENGINE mode (POL-004) the invoice posts JET-03 Dr ACCOUNTS_RECEIVABLE 1,080.00 /
    Cr CONTRACT_LIABILITY 1,000.00, Cr SALES_TAX_PAYABLE 80.00 (POL-045 ASSESS_EACH_TAX; the tax
    is a split credit, S14-R-01), then JET-02 Dr CONTRACT_LIABILITY 1,000.00 / Cr REVENUE 1,000.00;
    the receivable carries the tax (1,080.00)."""
    january = run_checkpoint(CHK_023, "january-close")
    assert january.txn("FY2026-P01") == {
        _line(BILLING, "C", CL): usd("1000.00"),
        _line(BILLING, "C", TAX): usd("80.00"),
        _line(BILLING, "D", AR): usd("1080.00"),
        _line(RECOGNITION, "C", REVENUE): usd("1000.00"),
        _line(RECOGNITION, "D", CL): usd("1000.00"),
    }
    (invoice,) = [i for i in january.intents("FY2026-P01") if i.entry_kind == BILLING]
    assert [(line.side, line.account_role) for line in invoice.lines] == [
        ("D", AR),
        ("C", CL),
        ("C", TAX),
    ]
    assert january.balance("C-JE-023@US01", "FY2026-P01", "accounts_receivable_txn") == usd(
        "1080.00"
    )
    assert january.balance("C-JE-023@US01", "FY2026-P01", "contract_liability_txn") == 0
    assert january.version("revenue_cum") == usd("1000.00")
    january.entries_balance()


def test_chk_024_cancellable_and_noncancellable_invoices() -> None:
    """CHK-024. Case A (cancellable, ENGINE mode): the 31 January invoice is memo-only — no JET-03
    line and receivable 0.00 at 31 January; on the 1 March receipt JET-03 Dr ACCOUNTS_RECEIVABLE
    1,000.00 / Cr CONTRACT_LIABILITY 1,000.00 (S10-R-06); on 31 March JET-02 1,000.00. Case B
    (noncancellable from 31 January): JET-03 posts on 31 January with receivable and contract
    liability of 1,000.00 each; JET-02 1,000.00 on 31 March (POLICIES JET-03; POL-123)."""
    a_january = run_checkpoint(CHK_024_A, "january-close")
    assert a_january.txn("FY2026-P01") == {}
    assert a_january.balance("C-JE-024-A@US01", "FY2026-P01", "accounts_receivable_txn") == 0
    assert a_january.balance("C-JE-024-A@US01", "FY2026-P01", "contract_liability_txn") == 0
    a_receipt = run_checkpoint(CHK_024_A, "receipt-1-march")
    assert a_receipt.txn("FY2026-P03") == {
        _line(BILLING, "C", CL): usd("1000.00"),
        _line(BILLING, "D", AR): usd("1000.00"),
    }
    assert a_receipt.balance("C-JE-024-A@US01", "FY2026-P03", "contract_liability_txn") == usd(
        "1000.00"
    )
    a_march = run_checkpoint(CHK_024_A, "march-close")
    assert a_march.txn("FY2026-P03") == {
        _line(BILLING, "C", CL): usd("1000.00"),
        _line(BILLING, "D", AR): usd("1000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("1000.00"),
        _line(RECOGNITION, "D", CL): usd("1000.00"),
    }
    assert a_march.txn("FY2026-P01") == {}
    assert a_march.version("revenue_cum") == usd("1000.00")
    a_march.entries_balance()
    b_january = run_checkpoint(CHK_024_B, "january-close")
    assert b_january.txn("FY2026-P01") == {
        _line(BILLING, "C", CL): usd("1000.00"),
        _line(BILLING, "D", AR): usd("1000.00"),
    }
    assert b_january.balance("C-JE-024-B@US01", "FY2026-P01", "accounts_receivable_txn") == usd(
        "1000.00"
    )
    assert b_january.balance("C-JE-024-B@US01", "FY2026-P01", "contract_liability_txn") == usd(
        "1000.00"
    )
    b_march = run_checkpoint(CHK_024_B, "march-close")
    assert b_march.txn("FY2026-P03") == {
        _line(RECOGNITION, "C", REVENUE): usd("1000.00"),
        _line(RECOGNITION, "D", CL): usd("1000.00"),
    }
    assert b_march.balance("C-JE-024-B@US01", "FY2026-P03", "contract_liability_txn") == 0
    b_march.entries_balance()


def test_chk_025_volume_rebate_refund_liability() -> None:
    """CHK-025: Q1 JET-02 Dr CONTRACT_LIABILITY 7,500.00 / Cr REVENUE 7,500.00. Q2: JET-02 for the
    500 units at the revised unit allocation of 90.00 is 45,000.00 and JET-04a for the 75 Q1 units
    is Dr REVENUE 750.00 / Cr CONTRACT_LIABILITY 750.00; JET-04a has no target of its own, so the
    REVENUE_RECOGNITION entry carries the net relief 44,250.00 (S14-R-02, S14-R-03); JET-04b with
    the refund-liability target 5,750.00 is Dr CONTRACT_LIABILITY 5,750.00 / Cr REFUND_LIABILITY
    5,750.00. End of Q2: revenue 51,750.00 (Q2 44,250.00), refund liability 5,750.00, position
    0.00 (ALG-06; POLICIES JET-04)."""
    q1 = run_checkpoint(CHK_025, "q1-close")
    assert q1.txn("FY2026-P02") == {
        _line(RECOGNITION, "C", REVENUE): usd("7500.00"),
        _line(RECOGNITION, "D", CL): usd("7500.00"),
    }
    assert q1.version("revenue_cum") == usd("7500.00")
    q2 = run_checkpoint(CHK_025, "q2-close")
    assert q2.txn("FY2026-P05") == {
        _line(REFUND, "C", RL): usd("5750.00"),
        _line(REFUND, "D", CL): usd("5750.00"),
        _line(RECOGNITION, "C", REVENUE): usd("44250.00"),
        _line(RECOGNITION, "D", CL): usd("44250.00"),
    }
    assert usd("45000.00") - usd("750.00") == usd("44250.00")
    assert q2.version("revenue_cum") == usd("51750.00")
    assert q2.balance("C-JE-025@US01", "FY2026-P06", "refund_liability_txn") == usd("5750.00")
    # The position is nil once the 5,750.00 rebate sits in the refund liability (the key's row).
    assert q2.balance("C-JE-025@US01", "FY2026-P06", "contract_liability_txn") == 0
    assert q2.balance("C-JE-025@US01", "FY2026-P06", "contract_asset_txn") == 0
    q2.entries_balance()


def test_chk_026_bonus_catch_up_lines() -> None:
    """CHK-026 (CHK-100 extended): the Year 2 January bonus catch-up of 60,000.00 posts through the
    JET-02 target, Dr CONTRACT_LIABILITY 60,000.00 / Cr REVENUE 60,000.00 (JET-04a, S14-R-02), and
    the NETTING_RECLASS pass presents it as a contract asset: reclass Dr CONTRACT_ASSET 62,000.00 /
    Cr CONTRACT_LIABILITY 62,000.00 with the reversal of December's 2,000.00, so January nets to
    Dr CONTRACT_ASSET 60,000.00 / Cr REVENUE 60,000.00 (the key's block). Year 2 close: JET-02
    progress revenue 1,062,000.00 in December; Year 2 revenue 1,122,000.00; contract asset
    124,000.00 (POLICIES JET-02, JET-04, JET-06; the key's remaining stop is the stage 15
    ``revenue_prior_period`` trace node, outside stage 14)."""
    january = run_checkpoint(CHK_026, "year-2-january-catch-up")
    assert january.txn("FY2027-P01") == {
        _line(RECLASS, "C", CL): usd("62000.00"),
        _line(RECLASS, "D", CA): usd("62000.00"),
        _line(REVERSAL, "C", CA): usd("2000.00"),
        _line(REVERSAL, "D", CL): usd("2000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("60000.00"),
        _line(RECOGNITION, "D", CL): usd("60000.00"),
    }
    assert january.txn("FY2027-P01", outputs=january.outputs[:1]) == {
        _line(RECOGNITION, "C", REVENUE): usd("60000.00"),
        _line(RECOGNITION, "D", CL): usd("60000.00"),
    }
    assert january.balance("C-JE-026@US01", "FY2027-P01", "contract_asset_txn") == usd("62000.00")
    close = run_checkpoint(CHK_026, "year-2-close")
    assert close.txn("FY2027-P12") == {
        _line(RECLASS, "C", CL): usd("124000.00"),
        _line(RECLASS, "D", CA): usd("124000.00"),
        _line(REVERSAL, "C", CA): usd("62000.00"),
        _line(REVERSAL, "D", CL): usd("62000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("1062000.00"),
        _line(RECOGNITION, "D", CL): usd("1062000.00"),
    }
    year_2 = sum(
        close.txn(f"FY2027-P{month:02d}").get(_line(RECOGNITION, "C", REVENUE), 0)
        for month in range(1, 13)
    )
    assert year_2 == usd("1122000.00")
    assert close.version("revenue_cum") == usd("2124000.00")
    assert close.balance("C-JE-026@US01", "FY2027-P12", "contract_asset_txn") == usd("124000.00")
    close.entries_balance()
