"""Onboarding differences per S07-R-07 role family, posted once at the cutover (ENGINE_SPEC S07-R-07
rev 1.17; ENGINE_SPEC_B S14-R-26 rev 1.18, S10-R-03 rev 1.16; 04 table 15.4-C rev 1.25; lane
ENG-C5 phase 2, readiness row ONB-DIFF-ROLES; D-97 (11) completion).

Under RECOMPUTE_FROM_INCEPTION the ERP holds the imported cutover balances while the engine
recomputes from inception; the difference per role key at the cutover posts once with
``reason_code = ONBOARDING_DIFFERENCE`` and the recomputed cumulative is deemed posted from then
on. Fail-first on the pre-code head 50be60d (`.run/eng-c5p2/fail-first-overlay-50be60d.log`): the
revenue difference was refused (interim containment), the ENGINE billing difference and the
deposit difference posted nothing, and the mapping module did not exist. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from decimal import Decimal

import erev_engine
import pytest
from erev_engine.errors import EngineError
from support import bundles, intent_totals
from support import cpc_worlds as cpc
from support import onboarding_worlds as w

REASON = "ONBOARDING_DIFFERENCE"


def _book(value, code: str):
    (book,) = [item for item in erev_engine.compute(value).books if item.book_code == code]
    return book


def _by_reason(book, reason: str):
    return sorted(
        (
            i.posting_period_key,
            i.origin_period_key or "",
            i.posting_class,
            ln.account_role,
            ln.side,
            ln.amount_txn,
        )
        for i in book.posting_intents
        if i.reason_code == reason
        for ln in i.lines
    )


def test_revenue_difference_posts_once_at_the_cutover() -> None:
    """Revenue family: CHK-121's ASC606 book (RECOMPUTE) with an imported revenue of 100,000.00
    against the recomputed 120,000.00: the difference 20,000.00 posts Dr CONTRACT_LIABILITY / Cr
    REVENUE dated the cutover, in FY2026-P01 with origin FY2025-P12 (the cutover period is
    closed), reason ONBOARDING_DIFFERENCE; January's 10,000.00 posts as usual; the contract
    liability at January is 240,000 − (100,000 + 20,000 + 10,000) = 110,000.00; a repeat compute
    posts nothing new; the IFRS15 book (fair value from 0) has no difference."""
    payload = w.opening_payload(revenue_cum="100000.00", remaining_allocation="140000.00")
    value = w.chk_121(payload=payload)
    first = erev_engine.compute(value)
    (book,) = [b for b in first.books if b.book_code == "ASC606"]
    assert _by_reason(book, REASON) == [
        ("FY2026-P01", "FY2025-P12", "EVENT", "CONTRACT_LIABILITY", "D", 2000000),
        ("FY2026-P01", "FY2025-P12", "EVENT", "REVENUE", "C", 2000000),
    ]
    assert _by_reason(book, "LATE_EVENT") == []
    assert cpc.role_net(book, "REVENUE") == {"FY2026-P01": -3000000}
    assert cpc.balance(book, "FY2026-P01", "contract_liability_txn") == 11000000
    assert cpc.trace_mismatches(book.trace) == []
    (ifrs,) = [b for b in first.books if b.book_code == "IFRS15"]
    assert _by_reason(ifrs, REASON) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    for repeat in erev_engine.compute(posted).books:
        assert repeat.posting_intents == ()


def test_engine_billing_difference_posts_through_jet_03() -> None:
    """ENGINE billing family: under POL-004 ENGINE the acquiree's invoice of 240,000.00 (1 June
    2025) is recomputed, not replaced (S10-R-03 rev 1.16), so billed_cum is 240,000.00 from the
    cutover while the imported billed_cum is 200,000.00: the difference 40,000.00 posts JET-03
    Dr ACCOUNTS_RECEIVABLE / Cr CONTRACT_LIABILITY at the cutover (into FY2026-P01, origin
    FY2025-P12); no other JET-03 line posts for the pre-cutover invoice; a repeat compute posts
    nothing new."""
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
    payload = w.opening_payload(billed_cum="200000.00")
    value = w.chk_121(policies={"billing.posting": "ENGINE"}, extra=[invoice], payload=payload)
    first = erev_engine.compute(value)
    (book,) = [b for b in first.books if b.book_code == "ASC606"]
    assert _by_reason(book, REASON) == [
        ("FY2026-P01", "FY2025-P12", "EVENT", "ACCOUNTS_RECEIVABLE", "D", 4000000),
        ("FY2026-P01", "FY2025-P12", "EVENT", "CONTRACT_LIABILITY", "C", 4000000),
    ]
    receivable = [line for line in w.journal(book, "ACCOUNTS_RECEIVABLE") if line[1] == "BILLING"]
    assert [line[5] for line in receivable] == [4000000]
    assert cpc.node_values(book, "billed_cum")[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "240000.00"
    assert cpc.trace_mismatches(book.trace) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    for repeat in erev_engine.compute(posted).books:
        assert repeat.posting_intents == ()


def test_deposit_difference_posts_through_jet_01b_receipt() -> None:
    """Deposits family: a deposit of 1,200.00 received 15 February 2026 while NOT_A_CONTRACT, the
    cutover 30 June 2026 (RECOMPUTE, the deposit member imported as an explicit 0): the receipt's
    own JET-01b
    posting in the closed pre-cutover period is deemed posted and the difference 1,200.00 posts
    once — Dr BILLING_CLEARING (UNAPPLIED_CASH) / Cr DEPOSIT_LIABILITY — dated the cutover, in
    FY2026-P07 with origin FY2026-P06; a repeat compute posts nothing new."""
    value = w.deposit_recompute()
    first = erev_engine.compute(value)
    (book,) = first.books
    assert _by_reason(book, REASON) == [
        ("FY2026-P07", "FY2026-P06", "EVENT", "BILLING_CLEARING", "D", 120000),
        ("FY2026-P07", "FY2026-P06", "EVENT", "DEPOSIT_LIABILITY", "C", 120000),
    ]
    assert [i for i in book.posting_intents if i.reason_code != REASON] == []
    assert cpc.balance(book, "FY2026-P07", "deposit_liability_txn") == 120000
    assert cpc.trace_mismatches(book.trace) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    (repeat,) = erev_engine.compute(posted).books
    assert repeat.posting_intents == ()


def test_zero_differences_and_opening_balances_mode_post_nothing_extra() -> None:
    """Controls: CHK-121's payload (imported = recomputed) posts no ONBOARDING_DIFFERENCE line in
    either book, and the IFRS15 book (OPENING_BALANCES_AT_CUTOVER) never does; the compute-time
    refusal is a finding, never an input error (EngineError carries the finding's code)."""
    for book in erev_engine.compute(w.chk_121()).books:
        assert _by_reason(book, REASON) == []
    assert issubclass(EngineError, Exception)


def _blocking(value) -> tuple[str, list[dict[str, object]]]:
    """(the CV-15 code raised, the findings in its detail) of a compute that fails closed."""
    with pytest.raises(EngineError) as info:
        erev_engine.compute(value)
    found = info.value.detail.get("findings")
    findings = json.loads(found) if isinstance(found, str) else found
    return info.value.code, list(findings)


def test_mid_period_cutover_is_refused_closed() -> None:
    """S07-R-01 rev 1.18 (D-98 candidate 22): a cutover of 15 June 2026 is not the end of
    FY2026-P06, so stage 07 records ONBOARDING_CUTOVER_NOT_PERIOD_END bound to the contract and
    the opening event, CV-15 raises that code and nothing is computed; the period-end cutover of
    the same world computes (`test_deposit_difference_posts_through_jet_01b_receipt`)."""
    code, findings = _blocking(w.deposit_recompute(cutover=date(2026, 6, 15)))
    assert code == "ONBOARDING_CUTOVER_NOT_PERIOD_END"
    assert [
        (f["code"], f["severity"], f["subject_key"], f["event_key"], f["detail"])
        for f in findings
        if f["code"] == code
    ] == [
        (
            code,
            "ERROR",
            "C-DEP-ONB",
            "C-DEP-ONB/EV-000005",
            {
                "cutover_date": "2026-06-15",
                "entity": bundles.ENTITY_CODE,
                "period_end": "2026-06-30",
                "period_key": "FY2026-P06",
                "rule": "S07-R-01",
            },
        )
    ]


def test_absent_deposit_member_with_recomputed_deposits_is_refused_closed() -> None:
    """S07-R-07 rev 1.18 (D-98 candidate 22): the payload omits deposit_liability while the
    recomputed pre-cutover deposit is 1,200.00 — never read as 0: stage 14 records
    ONBOARDING_MEMBER_MISSING on the deposit's `<contract>@<entity>` subject (member, part,
    recomputed) and CV-15 raises it; an explicit 0 posts the whole deposit
    (`test_deposit_difference_posts_through_jet_01b_receipt`) and a payload without the member
    computes when no deposit was recomputed (the CHK-121 worlds)."""
    code, findings = _blocking(w.deposit_recompute(deposit_member=None))
    assert code == "ONBOARDING_MEMBER_MISSING"
    assert [
        (f["code"], f["severity"], f["subject_key"], f["event_key"], f["detail"])
        for f in findings
        if f["code"] == code
    ] == [
        (
            code,
            "ERROR",
            f"C-DEP-ONB@{bundles.ENTITY_CODE}",
            "C-DEP-ONB/EV-000005",
            {
                "cutover_date": "2026-06-30",
                "member": "deposit_liability",
                "part": "JET-01b receipt",
                "recomputed": "120000",
                "rule": "S07-R-07",
            },
        )
    ]


@pytest.mark.parametrize(("imported", "net_difference"), [("200000.00", 0), ("190000.00", 1000000)])
def test_pre_cutover_engine_credit_memo_conserves_the_net_billing_difference(
    imported: str, net_difference: int
) -> None:
    """P2-Q-2 (D-98 candidate 22): the imported billed_cum is net of credit memos and maps to the
    JET-03 invoice part while the credit-memo part imports 0; both parts post on the same role key
    (Dr ACCOUNTS_RECEIVABLE against CONTRACT_LIABILITY), so the S07-R-07 difference is measured on
    the net role target — an ENGINE invoice of 240,000.00 and a credit memo of 40,000.00 before the
    cutover against an imported 200,000.00 post nothing, and against 190,000.00 post the net
    10,000.00 once; billed_cum stays the recomputed net; a repeat compute posts nothing new. A
    proof of the net conservation ruled acceptable at rc, passing on the pre-ruling engine as
    well."""
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
    memo = bundles.event(
        w.CONTRACT,
        5,
        "CREDIT_MEMO_RECORDED",
        date(2025, 8, 1),
        {
            "credit_memo_number": "CM-ACQ-1",
            "credited_invoice_number": "INV-ACQ-1",
            "obligation_key": w.OBLIGATION,
            "amount": Decimal("40000.00"),
            "issue_date": date(2025, 8, 1),
        },
        obligation_keys=[w.OBLIGATION],
    )
    payload = w.opening_payload(billed_cum=imported)
    value = w.chk_121(
        policies={"billing.posting": "ENGINE"}, extra=[invoice, memo], payload=payload
    )
    first = erev_engine.compute(value)
    (book,) = [b for b in first.books if b.book_code == "ASC606"]
    lines = _by_reason(book, REASON)
    expected = [
        ("FY2026-P01", "FY2025-P12", "EVENT", "ACCOUNTS_RECEIVABLE", "D", net_difference),
        ("FY2026-P01", "FY2025-P12", "EVENT", "CONTRACT_LIABILITY", "C", net_difference),
    ]
    assert lines == (sorted(expected) if net_difference else [])
    assert net_difference == 20000000 - int(Decimal(imported) * 100)
    assert cpc.node_values(book, "billed_cum")[f"billed_cum:{w.SUBJECT}:FY2026-P01"] == "200000.00"
    assert cpc.trace_mismatches(book.trace) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    for repeat in erev_engine.compute(posted).books:
        assert repeat.posting_intents == ()


def test_deemed_posted_family_posts_no_onboarding_difference() -> None:
    """Codex C5-PH2-R1 (S14-R-26 rev 1.17): the CHK-121 ASC606 world with a consideration-payable
    promise of 1,000.00 dated 1 January 2025 (JET-14, a family outside S07-R-07) posts no
    ONBOARDING_DIFFERENCE at all — the family is deemed posted at the cutover, not treated as an
    imported 0 — while January 2026 still posts Dr CONTRACT_LIABILITY / Cr REVENUE 10,000.00 and a
    repeat compute posts nothing new. Fail-first on 54707ad: an extra Dr CUSTOMER_INCENTIVE_ASSET /
    Cr CONSIDERATION_PAYABLE 1,000.00 with reason ONBOARDING_DIFFERENCE in FY2026-P01."""
    value = w.chk_121(
        books=("ASC606",),
        payables=(cpc.payable("1000.00", on=date(2025, 1, 1), keys=(w.OBLIGATION,)),),
        accounts=cpc.CPC_ACCOUNTS,
    )
    first = erev_engine.compute(value)
    (book,) = first.books
    assert _by_reason(book, REASON) == []
    assert [
        line for line in w.journal(book, "CONSIDERATION_PAYABLE", "CUSTOMER_INCENTIVE_ASSET")
    ] == []
    plain = _book(w.chk_121(books=("ASC606",)), "ASC606")
    assert w.journal(book, "REVENUE", "CONTRACT_LIABILITY") == w.journal(
        plain, "REVENUE", "CONTRACT_LIABILITY"
    )
    assert ("FY2026-P01", "REVENUE_RECOGNITION", "EVENT", "REVENUE", "C", 1000000, "") in w.journal(
        book, "REVENUE"
    )
    assert cpc.trace_mismatches(book.trace) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(first))
    (repeat,) = erev_engine.compute(posted).books
    assert repeat.posting_intents == ()


def _engine_billing_world(billed_cum: str | None):
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
    return w.chk_121(
        books=("ASC606",),
        policies={"billing.posting": "ENGINE"},
        extra=[invoice],
        payload=w.opening_payload(billed_cum=billed_cum),
    )


def test_absent_billed_cum_with_recomputed_engine_billing_is_refused_closed() -> None:
    """D-98 candidate 35 (P2-Q-5): the payload omits billed_cum while an ENGINE invoice of
    240,000.00 is recomputed through the cutover — never read as 0: stage 14 records
    ONBOARDING_MEMBER_MISSING on the obligation (member billed_cum, part JET-03 invoice,
    recomputed 240,000.00) and CV-15 raises it; an explicit 0 posts the full difference
    Dr ACCOUNTS_RECEIVABLE / Cr CONTRACT_LIABILITY 240,000.00 once at the cutover."""
    code, findings = _blocking(_engine_billing_world(None))
    assert code == "ONBOARDING_MEMBER_MISSING"
    assert [
        (f["subject_key"], f["event_key"], f["detail"]) for f in findings if f["code"] == code
    ] == [
        (
            w.SUBJECT,  # the ENGINE-mode JET-03 invoice part is per obligation (S10-R-08)
            f"{w.CONTRACT}/EV-000003",
            {
                "cutover_date": "2025-12-31",
                "member": "billed_cum",
                "part": "JET-03 invoice",
                "recomputed": "24000000",
                "rule": "S07-R-07",
            },
        )
    ]
    explicit = _engine_billing_world("0.00")
    book = _book(explicit, "ASC606")
    assert _by_reason(book, REASON) == [
        ("FY2026-P01", "FY2025-P12", "EVENT", "ACCOUNTS_RECEIVABLE", "D", 24000000),
        ("FY2026-P01", "FY2025-P12", "EVENT", "CONTRACT_LIABILITY", "C", 24000000),
    ]
