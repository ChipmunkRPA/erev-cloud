"""The dispatch recount as a pure rule (item JRN-DISPATCH-RECOUNT-1; independent security review,
finding N2 (a); 05 ADP-31; 04 T-SL-07): ``export.recount`` compares the lines a dispatch is about
to send with the batch's stored ``line_count`` and totals — the figures the run was approved with
— and names every difference. The relay's refusal is witnessed in
``tests/domain/journals/test_export.py``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from erev_api.domain.journals import export
from erev_api.domain.journals.ports import ChunkLine, JournalChunk

EXTERNAL_ID = "erev:acme-test:JR-000001:1:1"


def _line(line_no: int, account: str, debit: str, credit: str, rate: str = "1") -> ChunkLine:
    return ChunkLine(
        je_no="JE-AVM-UK-000001",
        line_no=line_no,
        account_code=account,
        account_name=f"Account {account}",
        account_role="REVENUE" if account.startswith("4") else "CONTRACT_LIABILITY",
        debit=Decimal(debit),
        credit=Decimal(credit),
        debit_functional=Decimal(debit) * Decimal(rate),
        credit_functional=Decimal(credit) * Decimal(rate),
        dimensions={},
        memo="AVM-UK Jul 2026 revenue recognition",
        source_references="NS-SO-UK-7001",
    )


def _chunk(*lines: ChunkLine) -> JournalChunk:
    return JournalChunk(
        external_id=EXTERNAL_ID,
        run_no="JR-000001",
        batch_no=1,
        chunk_no=1,
        entity_code="AVM-UK",
        posting_period="FY2026-P07",
        period_end_date=date(2026, 7, 31),
        txn_currency="USD",
        functional_currency="GBP",
        lines=lines,
    )


# The batch as calculated and approved: two lines, USD 54,000.00 measured at GBP 43,740.00.
APPROVED: dict[str, Any] = {
    "line_count": 2,
    "total_debit_txn": Decimal("54000.0000"),
    "total_credit_txn": Decimal("54000.0000"),
    "total_debit_functional": Decimal("43740.0000"),
    "total_credit_functional": Decimal("43740.0000"),
}
LINES = (
    _line(1, "2100", "54000.00", "0", "0.81"),
    _line(2, "4000", "0", "54000.00", "0.81"),
)


def test_the_lines_approved_are_sent() -> None:
    assert export.recount(APPROVED, _chunk(*LINES)) is None


def test_a_line_added_after_the_approval_is_named() -> None:
    """A balanced pair slipped into the batch changes the count and all four totals."""
    added = (_line(3, "2100", "0", "900.00", "0.81"), _line(4, "4000", "900.00", "0", "0.81"))
    assert export.recount(APPROVED, _chunk(*LINES, *added)) == (
        f"Batch {EXTERNAL_ID} differs from what was calculated and approved: lines 4, stored 2; "
        "transaction debits 54900.00 USD, stored 54000.00; "
        "transaction credits 54900.00 USD, stored 54000.00; "
        "functional debits 44469.00 GBP, stored 43740.00; "
        "functional credits 44469.00 GBP, stored 43740.00. Nothing was sent."
    )


def test_a_line_that_lost_its_partner_is_named() -> None:
    """One line gone: the count and one side of each currency."""
    assert export.recount(APPROVED, _chunk(LINES[0])) == (
        f"Batch {EXTERNAL_ID} differs from what was calculated and approved: lines 1, stored 2; "
        "transaction credits 0.00 USD, stored 54000.00; "
        "functional credits 0.00 GBP, stored 43740.00. Nothing was sent."
    )


def test_a_functional_amount_alone_is_enough() -> None:
    """The same count and transaction totals with other functional amounts: the functional totals
    are part of what was approved, and of what an ERP adapter states (05 ADP-10 rev 1.92)."""
    other_rate = (
        _line(1, "2100", "54000.00", "0", "0.84"),
        _line(2, "4000", "0", "54000.00", "0.84"),
    )
    assert export.recount(APPROVED, _chunk(*other_rate)) == (
        f"Batch {EXTERNAL_ID} differs from what was calculated and approved: "
        "functional debits 45360.00 GBP, stored 43740.00; "
        "functional credits 45360.00 GBP, stored 43740.00. Nothing was sent."
    )
