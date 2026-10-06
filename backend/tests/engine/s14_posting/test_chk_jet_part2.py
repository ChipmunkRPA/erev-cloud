"""JET template checks, part 2: contract costs, loss, consideration payable, warranties, noncash,
financing, concessions and terminations (BUILD_SPEC END-12; POLICIES §2.3 JET-04, JET-09 to JET-14,
JET-16, JET-17 with CHK-130 to CHK-138, §5.3 CHK-112, ALG-07 CHK-070, ALG-08 §2.9.3 CHK-084;
ENGINE_SPEC_B §14.2, §14.8; lane ENG-C8).

Each check runs the CHK answer-key world through the public path — ``erev_engine.compute`` and the
runner's close passes (FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS; RCP-08) — and names the
template lines by their Table 14-A identity, the T-CON-09 balances and the T-CON-08 columns the
item body states; every entry balances in both currencies (S14-INV-01). Oracles are read, never
edited. The JET-05c concession leaf (AD-14 / AD-15) is not asserted here. No database (DG-TST-18).
"""

from __future__ import annotations

from support.jet_lines import Line, Posted, per_year, run_checkpoint
from support.recognition import usd

CL, REVENUE, AR, RL = "CONTRACT_LIABILITY", "REVENUE", "ACCOUNTS_RECEIVABLE", "REFUND_LIABILITY"
OBTAIN, FULFIL, COST_CLEARING = (
    "COST_TO_OBTAIN_ASSET",
    "COST_TO_FULFILL_ASSET",
    "CONTRACT_COST_CLEARING",
)
AMORT, IMPAIR = "CONTRACT_COST_AMORTIZATION", "CONTRACT_COST_IMPAIRMENT"
LOSS_EXPENSE, LOSS_PROVISION = "LOSS_EXPENSE", "LOSS_PROVISION"
INCENTIVE, PAYABLE = "CUSTOMER_INCENTIVE_ASSET", "CONSIDERATION_PAYABLE"
WTY_EXPENSE, WTY_PROVISION = "WARRANTY_EXPENSE", "WARRANTY_PROVISION"
NONCASH, CLEARING = "NONCASH_CONSIDERATION_ASSET", "BILLING_CLEARING"
INTEREST_EXPENSE, INTEREST_INCOME, CONTRA = (
    "INTEREST_EXPENSE",
    "INTEREST_INCOME",
    "RECEIVABLE_CONTRA",
)
DUE_TO, DUE_FROM, FX = "INTERCOMPANY_DUE_TO", "INTERCOMPANY_DUE_FROM", "FX_GAIN_LOSS"
RECOGNITION, BILLING, REFUND = "REVENUE_RECOGNITION", "BILLING", "REFUND_LIABILITY"
CAPITALIZATION, AMORTIZATION, IMPAIRMENT = (
    "CONTRACT_COST_CAPITALIZATION",
    "CONTRACT_COST_AMORTIZATION",
    "CONTRACT_COST_IMPAIRMENT",
)
LOSS, CPC, WARRANTY, NONCASH_KIND = (
    "LOSS_PROVISION",
    "CONSIDERATION_PAYABLE",
    "WARRANTY_ACCRUAL",
    "NONCASH_CONSIDERATION",
)
FINANCING, RC_KIND, IC, FX_KIND = (
    "FINANCING_INTEREST",
    "RECEIVABLE_CONTRA",
    "INTERCOMPANY",
    "FX_REMEASUREMENT",
)

CHK_130 = "JE-CHK-130-S8-CONTRACT-COSTS-EX2-AMORTISATION"
CHK_131 = "JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL"
CHK_131_EXPEDIENT = "JE-CHK-131-S8-EXPEDIENT-ONE-YEAR-COMMISSION-EXPENSED"
CHK_132 = "JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE"
CHK_133 = "CPC-CHK-133-S3-EX32"
CHK_134 = "POB-CHK-134-S2-WARRANTY-OWN"
CHK_135 = "NCC-CHK-135-S3-EX31"
CHK_136 = "JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION"
CHK_136_ANNUAL = "SFC-CHK-136-S3-EX29-ANNUAL"
CHK_137 = "SFC-CHK-137-S3-EX28-CASEB"
CHK_138 = "JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA"
CHK_112 = "MOD-CHK-112"
CHK_070 = "ENT-CHK-070-INTERCOMPANY-PAIR-PERFORMING-ENTITY"
CHK_084_A = "FX-CHK-084-A-REFUND-LIABILITY-REMEASURED"


def _line(kind: str, side: str, role: str, purpose: str = "", counterparty: str = "") -> Line:
    return (kind, side, role, purpose, counterparty)


def _months(year: int) -> list[str]:
    return [f"FY{year}-P{month:02d}" for month in range(1, 13)]


def _yearly(posted: Posted, years: range, line: Line) -> dict[str, int]:
    return per_year(
        {period: posted.txn(period) for year in years for period in _months(year)}, line
    )


def test_chk_130_commission_amortisation() -> None:
    """CHK-130: on 1 January 2026 JET-09a Dr COST_TO_OBTAIN_ASSET 10,000.00 / Cr
    CONTRACT_COST_CLEARING 10,000.00 and JET-09a′ Dr COST_TO_FULFILL_ASSET 140,000.00 / Cr
    CONTRACT_COST_CLEARING 140,000.00 (one CONTRACT_COST_CAPITALIZATION entry kind; POLICIES
    JET-09a); JET-09b amortises the commission over 84 months — 119.05 in January and 1,428.57 a
    year in years 1, 2, 3, 5, 6 and 7 with 1,428.58 in year 4 (the rounding residue of 10,000.00 ÷
    84) — and the fulfilment asset 1,666.67 a month, 20,000.00 a year; carrying 148,214.28 at
    31 January 2026 and 0.00 at the end of 2032 (S11-R-06, S11-R-07; CHK-130)."""
    january = run_checkpoint(CHK_130, "january-2026")
    assert january.txn("FY2026-P01") == {
        _line(AMORTIZATION, "C", FULFIL): usd("1666.67"),
        _line(AMORTIZATION, "C", OBTAIN): usd("119.05"),
        _line(AMORTIZATION, "D", AMORT): usd("1785.72"),
        _line(CAPITALIZATION, "C", COST_CLEARING): usd("150000.00"),
        _line(CAPITALIZATION, "D", FULFIL): usd("140000.00"),
        _line(CAPITALIZATION, "D", OBTAIN): usd("10000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("8333.33"),
        _line(RECOGNITION, "D", CL): usd("8333.33"),
    }
    subject = "C-JE-130@US01"
    assert january.balance(subject, "FY2026-P01", "cost_asset_carrying_txn") == usd("148214.28")
    final = run_checkpoint(CHK_130, "year-end-2032")
    assert _yearly(final, range(2026, 2033), _line(AMORTIZATION, "C", OBTAIN)) == {
        "FY2026": usd("1428.57"),
        "FY2027": usd("1428.57"),
        "FY2028": usd("1428.57"),
        "FY2029": usd("1428.58"),
        "FY2030": usd("1428.57"),
        "FY2031": usd("1428.57"),
        "FY2032": usd("1428.57"),
    }
    assert _yearly(final, range(2026, 2033), _line(AMORTIZATION, "C", FULFIL)) == {
        f"FY{year}": usd("20000.00") for year in range(2026, 2033)
    }
    assert final.balance(subject, "FY2032-P12", "cost_asset_carrying_txn") == 0
    for year, carrying in (
        (2026, "128571.43"),
        (2027, "107142.86"),
        (2028, "85714.29"),
        (2029, "64285.71"),
        (2030, "42857.14"),
        (2031, "21428.57"),
    ):
        assert final.balance(subject, f"FY{year}-P12", "cost_asset_carrying_txn") == usd(carrying)
    final.entries_balance()


def test_chk_131_impairment_and_reversal_lines() -> None:
    """CHK-131: commission 40,000.00 capitalised (JET-09a); Year 1 JET-09b 10,000.00 and JET-09c
    impairment Dr CONTRACT_COST_IMPAIRMENT 15,000.00 / Cr COST_TO_OBTAIN_ASSET 15,000.00, carrying
    15,000.00; Year 2 JET-09b 5,000.00, carrying 10,000.00 in the ASC606 book, which never
    reverses (S11-INV-03). The IFRS15 book reverses in Year 2: JET-09d Dr COST_TO_OBTAIN_ASSET
    10,000.00 / Cr CONTRACT_COST_IMPAIRMENT 10,000.00 with carrying 20,000.00 (POL-144
    REQUIRED_CAPPED; IFRS 15.104). The one-year expedient case capitalises nothing (POL-140
    APPLY; carrying 0.00)."""
    period_1 = run_checkpoint(CHK_131, "asc606-period-1")
    assert period_1.txn("FY2026-P01") == {
        _line(AMORTIZATION, "C", OBTAIN): usd("10000.00"),
        _line(AMORTIZATION, "D", AMORT): usd("10000.00"),
        _line(CAPITALIZATION, "C", COST_CLEARING): usd("40000.00"),
        _line(CAPITALIZATION, "D", OBTAIN): usd("40000.00"),
        _line(IMPAIRMENT, "C", OBTAIN): usd("15000.00"),
        _line(IMPAIRMENT, "D", IMPAIR): usd("15000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("100000.00"),
        _line(RECOGNITION, "D", CL): usd("100000.00"),
    }
    subject = "C-JE-131@US01"
    assert period_1.balance(subject, "FY2026-P01", "cost_asset_carrying_txn") == usd("15000.00")
    asc_2 = run_checkpoint(CHK_131, "asc606-period-2")
    assert asc_2.txn("FY2026-P02") == {
        _line(AMORTIZATION, "C", OBTAIN): usd("5000.00"),
        _line(AMORTIZATION, "D", AMORT): usd("5000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("100000.00"),
        _line(RECOGNITION, "D", CL): usd("100000.00"),
    }
    assert asc_2.balance(subject, "FY2026-P02", "cost_asset_carrying_txn") == usd("10000.00")
    ifrs_2 = run_checkpoint(CHK_131, "ifrs15-period-2")
    assert ifrs_2.book_code == "IFRS15"
    assert ifrs_2.txn("FY2026-P02") == {
        _line(AMORTIZATION, "C", OBTAIN): usd("5000.00"),
        _line(AMORTIZATION, "D", AMORT): usd("5000.00"),
        _line(IMPAIRMENT, "C", IMPAIR): usd("10000.00"),
        _line(IMPAIRMENT, "D", OBTAIN): usd("10000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("100000.00"),
        _line(RECOGNITION, "D", CL): usd("100000.00"),
    }
    assert ifrs_2.balance(subject, "FY2026-P02", "cost_asset_carrying_txn") == usd("20000.00")
    ifrs_2.entries_balance()
    expedient = run_checkpoint(CHK_131_EXPEDIENT, "january-close")
    assert {kind for kind, *_ in expedient.txn("FY2026-P01")} == {RECOGNITION}
    assert expedient.balance("C-JE-131X@US01", "FY2026-P01", "cost_asset_carrying_txn") == 0


def test_chk_132_loss_provision_lines() -> None:
    """CHK-132: Year 2 JET-12 Dr LOSS_EXPENSE 30,000.00 / Cr LOSS_PROVISION 30,000.00 in the
    CLOSE_RELEASE pass (TIME; compute posts none for an open period, RCP-08(a)); Year 3 release
    Dr LOSS_PROVISION 30,000.00 / Cr LOSS_EXPENSE 30,000.00; provision at the end of Years 1 to 3
    0.00 / 30,000.00 / 0.00 (S11-R-14; D-92 (3))."""
    subject = "C-JE-132@US01"
    year_1 = run_checkpoint(CHK_132, "year-end-2026")
    assert {kind for kind, *_ in year_1.txn("FY2026-P12")} <= {RECOGNITION}
    assert year_1.balance(subject, "FY2026-P12", "loss_provision_txn") == 0
    year_2 = run_checkpoint(CHK_132, "year-end-2027")
    assert (
        year_2.txn("FY2027-P12", outputs=year_2.outputs[:1]).get(_line(LOSS, "D", LOSS_EXPENSE))
        is None
    )
    assert year_2.txn("FY2027-P12") == {
        _line(LOSS, "C", LOSS_PROVISION): usd("30000.00"),
        _line(LOSS, "D", LOSS_EXPENSE): usd("30000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("200000.00"),
        _line(RECOGNITION, "D", CL): usd("200000.00"),
    }
    (provision,) = [i for i in year_2.intents("FY2027-P12") if i.entry_kind == LOSS]
    assert provision.posting_class == "TIME"
    assert year_2.balance(subject, "FY2027-P12", "loss_provision_txn") == usd("30000.00")
    year_3 = run_checkpoint(CHK_132, "year-end-2028")
    assert year_3.txn("FY2028-P12") == {
        _line(LOSS, "C", LOSS_EXPENSE): usd("30000.00"),
        _line(LOSS, "D", LOSS_PROVISION): usd("30000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("300000.00"),
        _line(RECOGNITION, "D", CL): usd("300000.00"),
    }
    assert year_3.balance(subject, "FY2028-P12", "loss_provision_txn") == 0
    year_3.entries_balance()


def test_chk_133_consideration_payable_lines() -> None:
    """CHK-133 (FASB Example 32): at inception JET-14 promised Dr CUSTOMER_INCENTIVE_ASSET
    1,500,000.00 / Cr CONSIDERATION_PAYABLE 1,500,000.00; in month 1 JET-02 Dr CONTRACT_LIABILITY
    2,000,000.00 / Cr REVENUE 2,000,000.00 and the JET-14 release Dr REVENUE 200,000.00 / Cr
    CUSTOMER_INCENTIVE_ASSET 200,000.00 (one CONSIDERATION_PAYABLE entry kind, roles netted:
    incentive asset Dr 1,300,000.00); net revenue 1,800,000.00; incentive asset 1,300,000.00
    (S04-R-14 to S04-R-16; POLICIES JET-14)."""
    inception = run_checkpoint(CHK_133, "at-inception")
    assert inception.txn("FY2026-P01") == {
        _line(CPC, "C", PAYABLE): usd("1500000.00"),
        _line(CPC, "D", INCENTIVE): usd("1500000.00"),
    }
    month_1 = run_checkpoint(CHK_133, "end-of-month-1")
    assert month_1.txn("FY2026-P01") == {
        _line(CPC, "C", PAYABLE): usd("1500000.00"),
        _line(CPC, "D", INCENTIVE): usd("1300000.00"),
        _line(CPC, "D", REVENUE): usd("200000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("2000000.00"),
        _line(RECOGNITION, "D", CL): usd("2000000.00"),
    }
    subject = "C-EX32@US01"
    assert month_1.balance(subject, "FY2026-P01", "customer_incentive_asset_txn") == usd(
        "1300000.00"
    )
    assert month_1.balance(subject, "FY2026-P01", "consideration_payable_txn") == usd("1500000.00")
    assert month_1.version("revenue_cum") == usd("1800000.00")
    month_1.entries_balance()


def test_chk_134_assurance_warranty_accrual() -> None:
    """CHK-134: at delivery JET-16 accrual Dr WARRANTY_EXPENSE 200.00 / Cr WARRANTY_PROVISION
    200.00 beside JET-02 9,545.45 (S04-R-19; POL-022; POLICIES JET-16)."""
    delivered = run_checkpoint(CHK_134, "after-delivery")
    assert delivered.txn("FY2026-P01") == {
        _line(RECOGNITION, "C", REVENUE): usd("9545.45"),
        _line(RECOGNITION, "D", CL): usd("9545.45"),
        _line(WARRANTY, "C", WTY_PROVISION): usd("200.00"),
        _line(WARRANTY, "D", WTY_EXPENSE): usd("200.00"),
    }
    assert delivered.balance("C-WTY@US01", "FY2026-P01", "contract_liability_txn") == usd("954.55")
    delivered.entries_balance()


def test_chk_135_noncash_consideration_lines() -> None:
    """CHK-135 (FASB Example 31): each week's service makes the right to the shares unconditional,
    JET-17 unconditional Dr NONCASH_CONSIDERATION_ASSET 1,000.00 / Cr CONTRACT_LIABILITY 1,000.00
    and JET-02 Dr CONTRACT_LIABILITY 1,000.00 / Cr REVENUE 1,000.00; on receipt JET-17 receipt Dr
    BILLING_CLEARING (INVESTMENTS) 1,000.00 / Cr NONCASH_CONSIDERATION_ASSET 1,000.00. January's
    NONCASH_CONSIDERATION entry nets the four weeks and the one receipt (S04-R-18; POL-048;
    POLICIES JET-17)."""
    january = run_checkpoint(CHK_135, "end-of-january")
    assert january.txn("FY2026-P01") == {
        _line(NONCASH_KIND, "C", CL): usd("4000.00"),
        _line(NONCASH_KIND, "D", CLEARING, "INVESTMENTS"): usd("1000.00"),
        _line(NONCASH_KIND, "D", NONCASH): usd("3000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("4000.00"),
        _line(RECOGNITION, "D", CL): usd("4000.00"),
    }
    assert usd("4000.00") - usd("1000.00") == usd("3000.00")
    assert january.version("revenue_cum") == usd("4000.00")
    assert january.balance("C-EX31@US01", "FY2026-P01", "contract_liability_txn") == 0
    january.entries_balance()


def test_chk_136_advance_payment_accretion() -> None:
    """CHK-136 (FASB Example 29): JET-11b Dr INTEREST_EXPENSE / Cr CONTRACT_LIABILITY. MONTHLY
    (POL-047): year 1 246.71 (month 1 20.00, month 12 21.13), year 2 261.93 (month 24 22.43);
    contract liability 4,246.71 then 4,508.64; revenue at transfer 4,508.64. ANNUAL: 240.00 and
    254.40; contract liability 4,240.00 then 4,494.40; revenue 4,494.40 (S04-R-12, S04-R-13;
    POLICIES JET-11, CHK-136)."""
    year_1 = run_checkpoint(CHK_136, "year-1-close")
    assert year_1.txn("FY2026-P01") == {
        _line(FINANCING, "C", CL): usd("20.00"),
        _line(FINANCING, "D", INTEREST_EXPENSE): usd("20.00"),
    }
    assert year_1.txn("FY2026-P12")[_line(FINANCING, "D", INTEREST_EXPENSE)] == usd("21.13")
    assert _yearly(year_1, range(2026, 2027), _line(FINANCING, "D", INTEREST_EXPENSE)) == {
        "FY2026": usd("246.71")
    }
    assert year_1.balance("C-JE-136@US01", "FY2026-P12", "contract_liability_txn") == usd("4246.71")
    year_2 = run_checkpoint(CHK_136, "year-2-close")
    assert _yearly(year_2, range(2027, 2028), _line(FINANCING, "D", INTEREST_EXPENSE)) == {
        "FY2027": usd("261.93")
    }
    assert year_2.txn("FY2027-P12")[_line(FINANCING, "D", INTEREST_EXPENSE)] == usd("22.43")
    assert year_2.balance("C-JE-136@US01", "FY2027-P12", "contract_liability_txn") == usd("4508.64")
    transfer = run_checkpoint(CHK_136, "transfer")
    assert transfer.txn("FY2028-P01") == {
        _line(RECOGNITION, "C", REVENUE): usd("4508.64"),
        _line(RECOGNITION, "D", CL): usd("4508.64"),
    }
    assert transfer.version("revenue_cum") == usd("4508.64")
    transfer.entries_balance()
    annual = run_checkpoint(CHK_136_ANNUAL, "transfer")
    assert _yearly(annual, range(2026, 2028), _line(FINANCING, "D", INTEREST_EXPENSE)) == {
        "FY2026": usd("240.00"),
        "FY2027": usd("254.40"),
    }
    assert annual.balance("C-FIN-ADV-A@US01", "FY2026-P12", "contract_liability_txn") == usd(
        "4240.00"
    )
    assert annual.txn("FY2027-P12")[_line(RECOGNITION, "C", REVENUE)] == usd("4494.40")
    assert annual.version("revenue_cum") == usd("4494.40")


def test_chk_137_deferred_payment_month_1() -> None:
    """CHK-137 (FASB Example 28 case B): month 1 JET-02 revenue 848,346.53 (the cash selling
    price) and JET-11a Dr CONTRACT_LIABILITY 8,483.47 / Cr INTEREST_INCOME 8,483.47; the ERP
    instalment invoice of 18,871.00 posts no engine line in ERP mode (POL-004); unbilled
    receivable 837,959.00 (S04-R-12; POLICIES JET-11a, CHK-137)."""
    month_1 = run_checkpoint(CHK_137, "end-of-month-1")
    assert month_1.txn("FY2026-P01") == {
        _line(FINANCING, "C", INTEREST_INCOME): usd("8483.47"),
        _line(FINANCING, "D", CL): usd("8483.47"),
        # JET-06 in the NETTING_RECLASS pass presents the position as an unbilled receivable.
        _line("NETTING_RECLASS", "C", CL): usd("837959.00"),
        _line("NETTING_RECLASS", "D", "UNBILLED_RECEIVABLE"): usd("837959.00"),
        _line(RECOGNITION, "C", REVENUE): usd("848346.53"),
        _line(RECOGNITION, "D", CL): usd("848346.53"),
    }
    assert usd("848346.53") + usd("8483.47") - usd("18871.00") == usd("837959.00")
    assert month_1.balance("C-FIN-B@US01", "FY2026-P01", "unbilled_receivable_txn") == usd(
        "837959.00"
    )
    assert month_1.version("revenue_cum") == usd("848346.53")
    february = {k: v for k, v in month_1.txn("FY2026-P02").items() if k[0] == FINANCING}
    assert february == {
        _line(FINANCING, "C", INTEREST_INCOME): usd("8379.59"),
        _line(FINANCING, "D", CL): usd("8379.59"),
    }
    month_1.entries_balance()


def test_chk_138_implicit_price_concession_lines() -> None:
    """CHK-138 (FASB Example 2): ENGINE mode JET-03 Dr ACCOUNTS_RECEIVABLE 1,000,000.00 / Cr
    CONTRACT_LIABILITY 1,000,000.00; JET-02 Dr CONTRACT_LIABILITY 400,000.00 / Cr REVENUE
    400,000.00; JET-04c Dr CONTRACT_LIABILITY 600,000.00 / Cr RECEIVABLE_CONTRA 600,000.00; revenue
    400,000.00; net receivable 400,000.00; contract liability 0.00; no credit-loss line (S04-R-09;
    S10-R-18; POLICIES JET-04c)."""
    march = run_checkpoint(CHK_138, "march-close")
    assert march.txn("FY2026-P03") == {
        _line(BILLING, "C", CL): usd("1000000.00"),
        _line(BILLING, "D", AR): usd("1000000.00"),
        _line(RC_KIND, "C", CONTRA): usd("600000.00"),
        _line(RC_KIND, "D", CL): usd("600000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("400000.00"),
        _line(RECOGNITION, "D", CL): usd("400000.00"),
    }
    subject = "C-JE-138@US01"
    assert march.balance(subject, "FY2026-P03", "accounts_receivable_txn") == usd("1000000.00")
    assert march.balance(subject, "FY2026-P03", "contract_liability_txn") == 0
    assert march.version("revenue_cum") == usd("400000.00")
    assert usd("1000000.00") - usd("600000.00") == usd("400000.00")
    march.entries_balance()


def test_chk_112_termination_journal_lines() -> None:
    """CHK-112: at the June 2027 termination JET-04b Dr CONTRACT_LIABILITY 60,000.00 / Cr
    REFUND_LIABILITY 60,000.00; JET-09e accelerates the remaining commission 18,000.00 beside the
    month's 1,000.00 of JET-09b, Dr CONTRACT_COST_AMORTIZATION 19,000.00 / Cr COST_TO_OBTAIN_ASSET
    19,000.00 (S11-R-13; POL-145); June revenue 10,000.00; final revenue 180,000.00; cost asset
    0.00. After the ERP credit memo JET-04b reverses: Dr REFUND_LIABILITY 60,000.00 / Cr
    CONTRACT_LIABILITY 60,000.00; position 0.00 (POLICIES §5.3 PT-03)."""
    termination = run_checkpoint(CHK_112, "at-termination")
    assert termination.txn("FY2027-P06") == {
        _line(AMORTIZATION, "C", OBTAIN): usd("19000.00"),
        _line(AMORTIZATION, "D", AMORT): usd("19000.00"),
        _line(REFUND, "C", RL): usd("60000.00"),
        _line(REFUND, "D", CL): usd("60000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("10000.00"),
        _line(RECOGNITION, "D", CL): usd("10000.00"),
    }
    assert usd("18000.00") + usd("1000.00") == usd("19000.00")
    subject = "C-TERM@US01"
    assert termination.balance(subject, "FY2027-P06", "refund_liability_txn") == usd("60000.00")
    assert termination.balance(subject, "FY2027-P06", "cost_asset_carrying_txn") == 0
    assert termination.version("revenue_cum") == usd("180000.00")
    after = run_checkpoint(CHK_112, "after-credit-memo")
    assert after.txn("FY2027-P07") == {
        _line(REFUND, "C", CL): usd("60000.00"),
        _line(REFUND, "D", RL): usd("60000.00"),
    }
    assert after.balance(subject, "FY2027-P07", "refund_liability_txn") == 0
    assert after.version("net_position") == 0
    assert after.version("revenue_cum") == usd("180000.00")
    after.entries_balance()


def test_chk_112_acceleration_carries_its_reason_code() -> None:
    """S14-R-27 (D-98 candidate 19; S11-R-13; Table 14-A JET-09e): at the June 2027 termination
    the acceleration 18,000.00 is its own CONTRACT_COST_AMORTIZATION entry with
    reason_code TERMINATION_ACCELERATION beside the month's amortisation entry 1,000.00 without
    a reason (S14-R-12: the reason code is an entry member); both are EVENT postings of their own
    period; the role totals of the period are the 19,000.00 posted before (S15-R-17). The
    acceleration lines cite the JET-09e variant target node (§14.6; S14-R-13) and the two lines of
    one role carry distinct line keys (S14-R-15)."""
    termination = run_checkpoint(CHK_112, "at-termination")
    amortisation = [
        intent for intent in termination.intents("FY2027-P06") if intent.entry_kind == AMORTIZATION
    ]
    assert sorted((intent.reason_code or "", intent.posting_class) for intent in amortisation) == [
        ("", "EVENT"),
        ("TERMINATION_ACCELERATION", "EVENT"),
    ]
    by_reason = {intent.reason_code: intent for intent in amortisation}
    accelerated, monthly = by_reason["TERMINATION_ACCELERATION"], by_reason[None]
    assert accelerated.origin_period_key is None and monthly.origin_period_key is None
    assert {(line.side, line.account_role, line.amount_txn) for line in accelerated.lines} == {
        ("D", AMORT, usd("18000.00")),
        ("C", OBTAIN, usd("18000.00")),
    }
    assert {(line.side, line.account_role, line.amount_txn) for line in monthly.lines} == {
        ("D", AMORT, usd("1000.00")),
        ("C", OBTAIN, usd("1000.00")),
    }
    assert termination.txn("FY2027-P06")[_line(AMORTIZATION, "D", AMORT)] == usd("19000.00")
    for line in accelerated.lines:
        assert line.trace_node_id.endswith("/TERMINATION_ACCELERATION:FY2027-P06")
    for line in monthly.lines:
        assert line.trace_node_id.endswith("/UNTAGGED:FY2027-P06")
    keys = {line.line_key for intent in amortisation for line in intent.lines}
    assert len(keys) == 4
    assert termination.version("revenue_cum") == usd("180000.00")
    termination.entries_balance()


def test_chk_112_late_placed_acceleration_keeps_late_event() -> None:
    """S14-R-27 with S08-R-08: when June 2027 is already closed at the termination, the
    acceleration and the month's amortisation carry into July as ONE CONTRACT_COST_AMORTIZATION
    entry with reason_code LATE_EVENT and origin FY2027-P06 (the late-placed acceleration is not
    re-tagged), Dr CONTRACT_COST_AMORTIZATION 19,000.00 / Cr COST_TO_OBTAIN_ASSET 19,000.00; no
    intent of the run carries TERMINATION_ACCELERATION; the totals equal the open-period run."""
    late = run_checkpoint(CHK_112, "after-credit-memo", states={"FY2027-P06": "closed"})
    july = [intent for intent in late.intents("FY2027-P07") if intent.entry_kind == AMORTIZATION]
    (carry,) = july
    assert (carry.reason_code, carry.origin_period_key, carry.posting_class) == (
        "LATE_EVENT",
        "FY2027-P06",
        "EVENT",
    )
    assert {(line.side, line.account_role, line.amount_txn) for line in carry.lines} == {
        ("D", AMORT, usd("19000.00")),
        ("C", OBTAIN, usd("19000.00")),
    }
    assert late.intents("FY2027-P06") == []
    for output in late.outputs:
        for book in output.books:
            for intent in book.posting_intents:
                assert intent.reason_code != "TERMINATION_ACCELERATION", intent.entry_key
    open_run = run_checkpoint(CHK_112, "at-termination")
    assert late.txn("FY2027-P07")[_line(AMORTIZATION, "D", AMORT)] == usd("19000.00")
    assert open_run.txn("FY2027-P06")[_line(AMORTIZATION, "D", AMORT)] == usd("19000.00")
    assert late.balance("C-TERM@US01", "FY2027-P07", "cost_asset_carrying_txn") == 0
    late.entries_balance()


def test_chk_070_intercompany_lines() -> None:
    """CHK-070 (ALG-07): the contracting entity US01 posts JET-02 Dr CONTRACT_LIABILITY 60,000.00 /
    Cr REVENUE 60,000.00 for its own obligation and JET-13 contracting Dr CONTRACT_LIABILITY
    20,000.00 / Cr INTERCOMPANY_DUE_TO 20,000.00 (counterparty UK01) for the obligation UK01
    performs; UK01 posts JET-13 performing Dr INTERCOMPANY_DUE_FROM 20,000.00 (counterparty US01)
    / Cr REVENUE 20,000.00. Each entity's entries balance and the counterparty is set exactly on
    the intercompany roles (S12-R-15, S12-R-16; S14-INV-05)."""
    p1 = run_checkpoint(CHK_070, "end-of-p1")
    assert p1.txn("FY2026-P01", entity="US01") == {
        _line(IC, "C", DUE_TO, "", "UK01"): usd("20000.00"),
        _line(IC, "D", CL): usd("20000.00"),
        _line(RECOGNITION, "C", REVENUE): usd("60000.00"),
        _line(RECOGNITION, "D", CL): usd("60000.00"),
    }
    assert p1.txn("FY2026-P01", entity="UK01") == {
        _line(IC, "C", REVENUE): usd("20000.00"),
        _line(IC, "D", DUE_FROM, "", "US01"): usd("20000.00"),
    }
    for intent in p1.intents("FY2026-P01"):
        for line in intent.lines:
            assert (line.counterparty_entity is not None) == (
                line.account_role in {DUE_TO, DUE_FROM}
            ), (intent.entity, line.account_role)
    assert p1.balance("C-ENT-070@US01", "FY2026-P01", "contract_liability_txn") == usd("20000.00")
    assert p1.version("revenue_cum") == usd("80000.00")
    p1.entries_balance()


def test_chk_084_jet_10d_lines() -> None:
    """CHK-084 (a), FX-CHK-084-A: the EUR refund liability of a USD entity. March: the liability
    300.00 is created at the spot 1.10 (functional 330.00) and the FX_REMEASUREMENT pass remeasures
    it to the closing 1.12 — JET-10d loss 6.00 as a functional-only line (transaction 0.00;
    DG-AK-56).
    April: the credit memo settles 200.00 at 1.15 (settlement remeasurement, EVENT, loss 6.00) and
    the period end remeasures the remaining 100.00 at 1.11 (gain 4.00, TIME). May: the last 100.00
    settles at 1.10 (loss 2.00, EVENT). Revenue in USD 10,670.00 + 110.00 = 10,780.00 (S12-R-19,
    S12-R-20; POLICIES JET-10d, ALG-08 §2.9.3)."""
    march = run_checkpoint(CHK_084_A, "march-close")
    assert march.functional("FY2026-P03") == {
        _line(FX_KIND, "C", RL): usd("6.00"),
        _line(FX_KIND, "D", FX): usd("6.00"),
        _line(REFUND, "C", RL): usd("330.00"),
        _line(REFUND, "D", CL): usd("330.00"),
        _line(RECOGNITION, "C", REVENUE): usd("10670.00"),
        _line(RECOGNITION, "D", CL): usd("10670.00"),
    }
    assert march.txn("FY2026-P03").get(_line(FX_KIND, "D", FX)) is None  # functional-only
    (period_end,) = [i for i in march.intents("FY2026-P03") if i.entry_kind == FX_KIND]
    assert period_end.posting_class == "TIME"
    may = run_checkpoint(CHK_084_A, "may-close")
    april_fx = {k: v for k, v in may.functional("FY2026-P04").items() if k[0] == FX_KIND}
    assert april_fx == {
        _line(FX_KIND, "C", FX): usd("4.00"),
        _line(FX_KIND, "C", RL): usd("6.00"),
        _line(FX_KIND, "D", FX): usd("6.00"),
        _line(FX_KIND, "D", RL): usd("4.00"),
    }
    assert {i.posting_class for i in may.intents("FY2026-P04") if i.entry_kind == FX_KIND} == {
        "EVENT",
        "TIME",
    }
    may_fx = {k: v for k, v in may.functional("FY2026-P05").items() if k[0] == FX_KIND}
    assert may_fx == {_line(FX_KIND, "C", RL): usd("2.00"), _line(FX_KIND, "D", FX): usd("2.00")}
    revenue = sum(
        may.functional(period).get(_line(RECOGNITION, "C", REVENUE), 0)
        for period in ("FY2026-P03", "FY2026-P04", "FY2026-P05")
    )
    assert revenue == usd("10780.00")
    may.entries_balance()
