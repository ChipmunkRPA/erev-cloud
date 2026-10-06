"""Public compute: the S10-R-07 identity in the 05h consumers, in money (D-91 C606-05h; ENG-B4).

``erev_engine.compute`` on frozen answer-key checkpoints with invoice lines appended in memory
(``support.billing_lines``). Expected figures are derived from the rules in
``.run/l9/d91-b4/derive.py`` (recorded in the lane record), not read from any probe: S04-R-20 Σ tax
of kept lines dated on or before d_v; S04-R-15 / S04-R-16 ordinary release min(R, ρ × invoiced) with
ρ = R ÷ committed purchases and invoiced the kept invoice lines of the related obligation in the
window; the contract version's ``revenue_cum`` net of the JET-14 release; S10-R-07 identity at
contract scope, a repeat flagged cancellable a new line, a status update adding nothing and a
changed amount refused (CV-15). Every compute re-evaluates its trace and balances its journals.
No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.errors import EngineError
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    journal,
    net_posted,
    period_balance,
    replace_payload,
    with_events,
)

TAX = ("je", "JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING", "january-close")
CPC = ("cpc", "CPC-CHK-133-S3-EX32", "end-of-month-1")
COMBINED = ("stp1", "STP1-S1-COMBINATION-OWN", "end-of-january")
JAN_15, JAN_31, FEB_10 = date(2026, 1, 15), date(2026, 1, 31), date(2026, 2, 10)
P01, P02 = "FY2026-P01", "FY2026-P02"
AR, CL, TAX_PAYABLE, REVENUE = (
    "ACCOUNTS_RECEIVABLE",
    "CONTRACT_LIABILITY",
    "SALES_TAX_PAYABLE",
    "REVENUE",
)
INCENTIVE_ASSET = "CUSTOMER_INCENTIVE_ASSET"
JET_03 = "BILLING"  # the E-29 entry kind of the JET-03 invoice posting


def _columns(book: BookOutput) -> dict[str, object]:
    assert book.contract_version is not None
    return dict(book.contract_version.columns)


def _balanced(book: BookOutput) -> None:
    for intent in book.posting_intents:
        debit = sum(line.amount_txn for line in intent.lines if line.side == "D")
        credit = sum(line.amount_txn for line in intent.lines if line.side == "C")
        assert debit == credit, intent.entry_kind


# --- S04-R-20 taxes: JE-CHK-023 (ENGINE, USD, January) --------------------------------------------


def _tax_world(**repeat: object) -> InputBundle:
    base = checkpoint_bundle(*TAX)
    if not repeat:
        return base
    return with_events(base, billing_after(base, first_billing(base), JAN_15, **repeat))


@pytest.mark.parametrize(
    ("repeat", "tax"),
    [
        pytest.param({}, 8_000, id="original"),
        pytest.param({"cancellable": False}, 8_000, id="update_false"),
        pytest.param({"cancellable": "false"}, 8_000, id="update_string_false"),
        pytest.param({"drop": ("is_cancellable",)}, 8_000, id="update_absent_flag"),
        pytest.param(
            {"cancellable": False, "tax_amount": Decimal("99.00")}, 8_000, id="update_other_tax"
        ),
        pytest.param({"cancellable": True}, 16_000, id="repeat_true"),
        pytest.param({"cancellable": "true"}, 16_000, id="repeat_string_true"),
        pytest.param(
            {"cancellable": True, "line_external_id": "INV-TAX-0001-2"}, 16_000, id="other_line_id"
        ),
    ],
)
def test_sales_tax_memo_counts_kept_lines_and_jet_03_posts_eligible_lines(
    repeat: dict[str, object], tax: int
) -> None:
    """``sales_tax_excluded_amount`` 80.00 for the line alone and for every status update (a
    changed ``tax_amount`` on an update changes nothing); 160.00 for a cancellable repeat (``true``
    or ``"true"``) or another line id. JET-03 posts the unconditional line only (Dr AR 1,080.00 /
    Cr CL 1,000.00 / Cr SALES_TAX_PAYABLE 80.00); ``billed_cum`` 1,000.00; revenue 1,000.00; the
    price never holds the tax (S04-R-20). The cancellable rows also need the stage 13 per-line
    control flows (S12-INV-03). A changed ``tax_amount`` on an update is now announced by the
    WARNING ``INVOICE_STATUS_UPDATE_TAX_MISMATCH`` (D-97 (27)) and still changes nothing."""
    warnings = ["INVOICE_STATUS_UPDATE_TAX_MISMATCH"] if "tax_amount" in repeat else []
    book = compute_book(_tax_world(**repeat), warnings=warnings)
    columns = _columns(book)
    assert (columns["sales_tax_excluded_amount"], columns["billed_cum"]) == (tax, 100_000)
    assert (columns["transaction_price"], columns["revenue_cum"]) == (100_000, 100_000)
    assert journal(book, JET_03, P01) == [
        (AR, "D", 108_000),
        (CL, "C", 100_000),
        (TAX_PAYABLE, "C", 8_000),
    ]
    assert net_posted(book, REVENUE, P01) == 100_000
    assert period_balance(book, P01, "accounts_receivable_txn") == 108_000
    _balanced(book)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"amount": Decimal("900.00")}, id="amount"),
        pytest.param({"obligation_key": "L2-OTHER"}, id="obligation_key"),
    ],
)
def test_tax_world_mismatched_update_fails_closed(changes: dict[str, object]) -> None:
    """A status update with another amount, or naming another obligation, is
    ``INVOICE_STATUS_UPDATE_MISMATCH`` (stage 10, CV-15): the compute stops (S10-R-07)."""
    with pytest.raises(EngineError) as info:
        compute_book(_tax_world(cancellable=False, **changes))
    assert info.value.code == "INVOICE_STATUS_UPDATE_MISMATCH"


# --- S04-R-15 / S04-R-16 ordinary release: CPC-CHK-133 (S3 EX32) ----------------------------------


def _cpc_world(on: date = JAN_31, **repeat: object) -> InputBundle:
    base = checkpoint_bundle(*CPC)
    if not repeat:
        return base
    return with_events(base, billing_after(base, first_billing(base), on, **repeat))


@pytest.mark.parametrize(
    ("repeat", "release", "revenue", "billed"),
    [
        pytest.param({}, 20_000_000, 180_000_000, 200_000_000, id="original"),
        pytest.param(
            {"cancellable": False}, 20_000_000, 180_000_000, 200_000_000, id="update_false"
        ),
        pytest.param(
            {"drop": ("is_cancellable",)},
            20_000_000,
            180_000_000,
            200_000_000,
            id="update_absent_flag",
        ),
        pytest.param(
            {"cancellable": True, "amount": Decimal("1000000.00")},
            30_000_000,
            170_000_000,
            300_000_000,
            id="repeat_true_1_000_000",
        ),
        pytest.param(
            {"cancellable": "true", "amount": Decimal("1000000.00")},
            30_000_000,
            170_000_000,
            300_000_000,
            id="repeat_string_true_1_000_000",
        ),
    ],
)
def test_incentive_release_reads_kept_invoice_lines(
    repeat: dict[str, object], release: int, revenue: int, billed: int
) -> None:
    """ρ = 1,500,000 ÷ 15,000,000 = 0.1 (COMMITTED_PURCHASES). The 2,000,000.00 January invoice
    alone or with a status update releases 200,000.00 (net revenue 1,800,000.00, incentive asset
    1,300,000.00). A same-identity repeat flagged cancellable for 1,000,000.00 is another invoice
    (D-91 C606-01 (2)): invoiced 3,000,000.00, release 300,000.00, net revenue 1,700,000.00, asset
    1,200,000.00; ``billed_cum`` 3,000,000.00. The January journal's net revenue agrees."""
    book = compute_book(_cpc_world(**repeat))
    columns = _columns(book)
    assert (columns["revenue_cum"], columns["billed_cum"]) == (revenue, billed)
    assert columns["consideration_payable_amount"] == -150_000_000
    assert net_posted(book, REVENUE, P01) == revenue
    assert period_balance(book, P01, "customer_incentive_asset_txn") == 150_000_000 - release
    (node,) = [
        n
        for n in book.trace.nodes
        if n.measure == "incentive_release_ordinary_cum" and n.id.endswith(f":{P01}")
    ]
    assert node.value == f"{Decimal(release) / 100:.2f}"
    _balanced(book)


def test_incentive_release_mismatched_update_fails_closed() -> None:
    with pytest.raises(EngineError) as info:
        compute_book(_cpc_world(cancellable=False, amount=Decimal("1000000.00")))
    assert info.value.code == "INVOICE_STATUS_UPDATE_MISMATCH"


def test_incentive_release_cutoff_a_february_repeat_leaves_january_unchanged() -> None:
    """The cancellable 1,000,000.00 repeat dated 10 February: January keeps release 200,000.00 and
    net revenue 1,800,000.00; February's release movement is 100,000.00 (Dr REVENUE / Cr
    CUSTOMER_INCENTIVE_ASSET), the asset 1,200,000.00 at 28 February; the version reads the
    cumulative 3,000,000.00 billed and 1,700,000.00 net revenue."""
    book = compute_book(_cpc_world(FEB_10, cancellable=True, amount=Decimal("1000000.00")))
    columns = _columns(book)
    assert (columns["revenue_cum"], columns["billed_cum"]) == (170_000_000, 300_000_000)
    assert net_posted(book, REVENUE, P01) == 180_000_000
    assert net_posted(book, REVENUE, P02) == -10_000_000
    assert net_posted(book, INCENTIVE_ASSET, P02, credit=True) == 10_000_000
    assert period_balance(book, P01, "customer_incentive_asset_txn") == 130_000_000
    assert period_balance(book, P02, "customer_incentive_asset_txn") == 120_000_000
    _balanced(book)


# --- Contract scope in a combined group: STP1-S1-COMBINATION-OWN ---------------------------------


def test_combined_contracts_reusing_invoice_ids_are_two_lines() -> None:
    """Two combined contracts (G-PKG-1). C-COMB-1's INV-CMB-1 / INV-CMB-1-1 90,000.00 carries
    9,000.00 of tax; C-COMB-2 is invoiced 30,000.00 on 25 January under the SAME invoice number
    and line id with 3,000.00 of tax. The identity is contract-scoped (S10-R-07), so the group's
    ``sales_tax_excluded_amount`` at 31 January is 12,000.00 (1,200,000 minor; on 0c853cb the taxes
    mirror merged the ids: 9,000.00), ``billed_cum`` 120,000.00 against revenue 100,000.00 (the
    licence): the group nets to a contract liability of 20,000.00 and no contract asset (ALG-02)."""
    base = checkpoint_bundle(*COMBINED)
    first = first_billing(base, "C-COMB-1")
    base = replace_payload(base, first.event_key, tax_amount=Decimal("9000.00"))
    second = billing_after(
        base,
        first_billing(base, "C-COMB-1"),
        date(2026, 1, 25),
        contract_key="C-COMB-2",
        obligation_key="C2-SVC",
        amount=Decimal("30000.00"),
        tax_amount=Decimal("3000.00"),
        issue_date=date(2026, 1, 25),
    )
    book = compute_book(with_events(base, second))
    columns = _columns(book)
    assert (columns["sales_tax_excluded_amount"], columns["billed_cum"]) == (1_200_000, 12_000_000)
    assert (columns["transaction_price"], columns["revenue_cum"]) == (15_000_000, 10_000_000)
    assert period_balance(book, P01, "contract_liability_txn") == 2_000_000
    assert period_balance(book, P01, "contract_asset_txn") == 0
    _balanced(book)
