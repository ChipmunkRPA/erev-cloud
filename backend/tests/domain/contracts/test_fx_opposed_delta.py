"""A role delta whose transaction and functional amounts differ in sign, on the ledger
(ENG-S14R10-FX-SIGN-1; supervisor ruling R-44 (a); ENGINE_SPEC_B S14-R-04, S14-R-10, S14-R-15,
S14-R-18, S14-R-28, S14-INV-01, S14-INV-02, S14-INV-09; 04 T-SL-04 ``amount_functional``,
``dr_cr``, ``ck_subledger_line__amounts``, ``ck_subledger_line__fx``; T-SL-09; DB-06).

The database half of ``tests/engine/s14_posting/test_s14_fx_sign_witness.py``, through the public
events route in the world of ``test_fx_remeasurement_recompute.py``: AVM-UK keeps GBP books, the
contract ``NS-SO-UK-7001`` is in USD (200 sensor gateways at USD 450.00, point in time per unit);
USD to GBP spot 0.8000 (1 July 2026), July average 0.8100.

- 10 July: 120 units delivered and computed. Revenue USD 54,000.00 is an asset layer at the July
  average: Dr CONTRACT_LIABILITY / Cr REVENUE 54,000.00 / 43,740.00.
- One request (approved by a second person, BUILD_SPEC CTR-6) then records an invoice of USD
  54,000.00 — dated 5 July, before the delivery, or 20
  July, after it — and one more unit on 21 July. The invoice is layered at spot (43,200.00) before
  July's revenue relieves it; the unit is an asset layer at the average (364.50). Target
  54,450.00 / 43,564.50; less posted: +450.00 USD and −175.50 GBP.

Before ruling R-44 the computation of that request was refused (decision L2-5-Q-34). It now posts
four rows: per role a transaction row (functional amount 0) and a functional row (transaction
amount 0), each on the side of its own amount, all four with the rate stamp of the delta.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import fx_rate, subledger_line, subledger_posting_seal
from erev_api.domain.journals import summarise
from erev_api.enums import JournalRunGrain
from sqlalchemy import and_, select
from support.factories import computed
from support.worlds import approved_manual_events
from test_fx_remeasurement_recompute import BOOK, World, app, delivered, world

__all__ = ["app", "world"]  # the fixtures of the world

KIND = "REVENUE_RECOGNITION"
CL, REVENUE = "CONTRACT_LIABILITY", "REVENUE"
OBLIGATION = "NS-SO-UK-7001/O1"

# (chain sequence, role, side, transaction amount, functional amount, stamped rate)
Row = tuple[int, str, str, Decimal, Decimal, Decimal]


def _rows(found: World, contract_id: UUID) -> list[Row]:
    """The contract's revenue rows in posting order, each with the rate stamped on it."""
    seal = subledger_posting_seal
    rows = found.place.rows(
        select(
            seal.c.chain_seq,
            subledger_line.c.account_role,
            subledger_line.c.dr_cr,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
            fx_rate.c.rate,
        )
        .select_from(
            subledger_line.join(
                seal,
                and_(
                    seal.c.tenant_id == subledger_line.c.tenant_id,
                    seal.c.subledger_posting_id == subledger_line.c.subledger_posting_id,
                ),
            ).join(
                fx_rate,
                and_(
                    fx_rate.c.tenant_id == subledger_line.c.tenant_id,
                    fx_rate.c.id == subledger_line.c.fx_rate_id,
                ),
            )
        )
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.book_code == BOOK,
            subledger_line.c.entry_kind == KIND,
        )
    )
    return sorted(
        (
            int(row["chain_seq"]),
            str(row["account_role"]),
            str(row["dr_cr"]),
            Decimal(row["amount_txn"]),
            Decimal(row["amount_functional"]),
            Decimal(row["rate"]),
        )
        for row in rows
    )


def _journal(
    found: World, contract_id: UUID, from_seq: int, to_seq: int
) -> list[tuple[str, Decimal, Decimal, Decimal, Decimal]]:
    """The journal lines the run of chain sequence (``from_seq``, ``to_seq``] summarises for July
    (S14-R-16, S14-R-18): (role, debit and credit in the transaction currency, debit and credit
    in the functional currency)."""
    (scope,) = found.place.rows(
        select(subledger_line.c.entity_id, subledger_line.c.period_id)
        .where(subledger_line.c.contract_id == contract_id, subledger_line.c.entry_kind == KIND)
        .distinct()
    )
    context = DbContext(tenant_id=found.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        lines = summarise.detail_lines(
            session,
            summarise.detail_statement(
                entity_id=UUID(str(scope["entity_id"])),
                book_code=BOOK,
                period_id=UUID(str(scope["period_id"])),
                from_seq=from_seq,
                to_seq=to_seq,
            ),
        )
        codes = summarise.dimension_codes(session)
    kept, _ = summarise.summarise(
        lines,
        grain=JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS,
        dimension_codes=codes,
    )
    return sorted(
        (
            line.account_role,
            line.debit_txn,
            line.credit_txn,
            line.debit_functional,
            line.credit_functional,
        )
        for line in kept
    )


def _events(invoice_date: str) -> list[dict[str, Any]]:
    """The invoice of USD 54,000.00 dated ``invoice_date`` and one more unit on 21 July."""
    return [
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": invoice_date,
            "payload": {
                "invoice_number": "INV-UK-7000",
                "line_external_id": "INV-UK-7000-1",
                "obligation_key": "O1",
                "amount": {"amount": "54000.00", "currency": "USD"},
                "issue_date": invoice_date,
            },
        },
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-07-21",
            "payload": {"obligation_key": "O1", "quantity": "1", "trigger": "DELIVERY"},
        },
    ]


@pytest.mark.parametrize("invoice_date", ["2026-07-05", "2026-07-20"])
def test_eng_s14r10_fx_sign_1_an_opposed_delta_posts_four_rows(
    world: World, invoice_date: str
) -> None:
    contract_id, group_id = delivered(world)  # 120 units on 10 July, computed; stream head 3
    average = Decimal("0.81")
    first = _rows(world, contract_id)
    assert [row[1:] for row in first] == [
        (CL, "D", Decimal("54000.00"), Decimal("43740.00"), average),
        (REVENUE, "C", Decimal("-54000.00"), Decimal("-43740.00"), average),
    ]

    # BUILD_SPEC CTR-6: the request holds a delivery a person records, so it waits whole —
    # the invoice with it — and Priya's approval appends both and computes once.
    recorded = approved_manual_events(
        world.place, world.priya, contract_id, *_events(invoice_date), evidence_file_ids=[]
    )
    assert recorded["computation"]["status"] == "SUCCEEDED", recorded["computation"]

    # One entry of four rows. The generated dr_cr is the side of the row's own non-zero amount;
    # every row carries the stamp of the delta, the July average (the latest effective date of its
    # references, D-88 L7-6-Q-1), so ck_subledger_line__fx holds on the transaction rows too.
    added = [row for row in _rows(world, contract_id) if row not in first]
    assert [row[1:] for row in added] == [
        (CL, "C", Decimal("0.00"), Decimal("-175.50"), average),
        (CL, "D", Decimal("450.00"), Decimal("0.00"), average),
        (REVENUE, "C", Decimal("-450.00"), Decimal("0.00"), average),
        (REVENUE, "D", Decimal("0.00"), Decimal("175.50"), average),
    ]
    assert len({row[0] for row in added}) == 1  # one sealed posting (DB-06)
    assert sum(row[3] for row in added) == 0 and sum(row[4] for row in added) == 0

    # The read-back is the target, 54,450.00 / 43,564.50, and the group computed again over its
    # own postings posts nothing (S14-INV-02).
    bundle, output, _ = computed(world.place, group_id)
    posted = {
        item.account_role: (item.amount_txn, item.amount_functional)
        for item in bundle.posted
        if item.entry_kind == KIND and item.subject_key == OBLIGATION
    }
    assert posted == {CL: (5445000, 4356450), REVENUE: (-5445000, -4356450)}
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _rows(world, contract_id) == [*first, *added]

    # Journal summarisation nets a role's rows per currency (S14-R-18). A run over both postings
    # holds one ordinary line per account; a run over the second posting alone holds the line
    # with a transaction debit and a functional credit, which T-SL-09 admits.
    first_seq, second_seq = first[0][0], added[0][0]
    zero = Decimal(0)
    assert _journal(world, contract_id, first_seq - 1, second_seq) == [
        (CL, Decimal("54450.00"), zero, Decimal("43564.50"), zero),
        (REVENUE, zero, Decimal("54450.00"), zero, Decimal("43564.50")),
    ]
    assert _journal(world, contract_id, first_seq, second_seq) == [
        (CL, Decimal("450.00"), zero, zero, Decimal("175.50")),
        (REVENUE, zero, Decimal("450.00"), Decimal("175.50"), zero),
    ]
