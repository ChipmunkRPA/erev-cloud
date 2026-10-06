"""Stage 01 ledger: ``billed_cum`` under the S10-R-07 identity (supervisor ruling, ENG-B4).

D-91 listed "the ``_fold`` / s01 ledger exclusion of status updates from billed" as a post-rc
platform item; the supervisor's production-continuation ruling brings the engine half forward:
``ledger.build`` classifies the ``BILLING_RECORDED`` events of the ordered stream through
``erev_engine.billing_identity`` before any subject or contract-stream attribution, so a status
update (a repeated identity whose ``is_cancellable`` is not true) adds nothing to ``billed_cum``,
to the contract stream an unreferenced credit memo draws on (S01-R-16), to the referenced cover
(D-87 L6-5-Q-15) or to S01-INV-03, while a repeat flagged cancellable is a new line and a line of
another contract is a separate identity. On 0c853cb / ad75a8d every ``BILLING_RECORDED`` was
summed, so an ordinary update doubled the billing and let a credit memo pass the
``REFUND_EXCEEDS_BILLED`` guard it should fail. Stage 10 keeps ``INVOICE_STATUS_UPDATE_MISMATCH``
(a mismatched update is refused there, not here). Expectations are derived in
``.run/l9/d91-b4/derive.py`` §H; the table mirrors the shape of Codex's frozen
``2026-09-19-stage01-billing-ledger-probe.py`` with the lane's own oracles. No database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

import pytest
from erev_engine.stages.s01_canonicalize import ledger
from erev_engine.stages.s01_canonicalize.convert import obligation_subject_key
from erev_engine.stages.state import EventView
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    with_events,
)
from support.recognition import event_view

C1, C2 = "C1", "C2"
JAN_5, JAN_10, JAN_15, JAN_20 = (
    date(2026, 1, 5),
    date(2026, 1, 10),
    date(2026, 1, 15),
    date(2026, 1, 20),
)


def invoice(
    seq: int,
    *,
    contract: str = C1,
    key: str | None = "L1",
    amount: int = 100,
    cancel: object = False,
    line: str = "1",
    absent: bool = False,
) -> EventView:
    payload: dict[str, object] = {
        "invoice_number": "INV-1",
        "line_external_id": line,
        "amount": Fraction(amount),
        "issue_date": JAN_5,
    }
    if not absent:
        payload["is_cancellable"] = cancel
    if key is not None:
        payload["obligation_key"] = key
    when = JAN_5 if seq == 1 else JAN_15
    return event_view(
        contract,
        seq,
        "BILLING_RECORDED",
        when,
        payload,
        obligation_keys=[] if key is None else [key],
    )


def credit(seq: int, amount: int, *, contract: str = C1, key: str | None = "L1") -> EventView:
    payload: dict[str, object] = {
        "credit_memo_number": f"CM-{seq}",
        "amount": Fraction(amount),
        "issue_date": JAN_20,
    }
    if key is not None:
        payload["obligation_key"] = key
    return event_view(
        contract,
        seq,
        "CREDIT_MEMO_RECORDED",
        JAN_20,
        payload,
        obligation_keys=[] if key is None else [key],
    )


def excess(seq: int = 3, key: str | None = "L1", contract: str = C1) -> tuple[str, str, str]:
    subject = contract if key is None else obligation_subject_key(contract, key)
    return ("REFUND_EXCEEDS_BILLED", subject, f"{contract}/EV-{seq:06d}")


@dataclass(frozen=True)
class Row:
    name: str
    events: Sequence[EventView]
    points: dict[str, tuple[int, int]]  # subject -> (billed_cum, credited_cum) at the end
    findings: Sequence[tuple[str, str, str]] = ()


A = invoice(1)
ROWS: list[Row] = [
    Row("original", [A], {"C1/L1": (100, 0)}),
    Row("ordinary_update_false", [A, invoice(2, cancel=False)], {"C1/L1": (100, 0)}),
    Row("ordinary_update_string_false", [A, invoice(2, cancel="false")], {"C1/L1": (100, 0)}),
    Row("ordinary_update_number_one", [A, invoice(2, cancel=1)], {"C1/L1": (100, 0)}),
    Row("ordinary_update_absent", [A, invoice(2, absent=True)], {"C1/L1": (100, 0)}),
    Row(
        "cancellable_repeat_true",
        [A, invoice(2, amount=200, cancel=True), credit(3, 250)],
        {"C1/L1": (300, 250)},
    ),
    Row(
        "cancellable_repeat_string_true",
        [A, invoice(2, amount=200, cancel="true"), credit(3, 250)],
        {"C1/L1": (300, 250)},
    ),
    Row(
        "ordinary_update_does_not_increase_credit_cap",
        [A, invoice(2), credit(3, 150)],
        {"C1/L1": (100, 150)},
        [excess()],
    ),
    Row(
        "unreferenced_credit_cap",
        [invoice(1, key=None), invoice(2, key=None), credit(3, 150, key=None)],
        {"C1": (100, 150)},
        [excess(key=None)],
    ),
    Row(
        "referenced_credit_draws_real_unreferenced_cover",
        [invoice(1, key=None), invoice(2, key=None), credit(3, 150)],
        {"C1": (100, 0), "C1/L1": (0, 150)},
        [excess()],
    ),
    Row(
        "two_obligations_cannot_reuse_duplicate_cover",
        [invoice(1, key=None), invoice(2, key=None), credit(3, 70), credit(4, 50, key="L2")],
        {"C1": (100, 0), "C1/L1": (0, 70), "C1/L2": (0, 50)},
        [excess(seq=4, key="L2")],
    ),
    Row("exact_credit_cap_valid", [A, invoice(2), credit(3, 100)], {"C1/L1": (100, 100)}),
    Row(
        "different_contract_same_identity",
        [A, invoice(1, contract=C2)],
        {"C1/L1": (100, 0), "C2/L1": (100, 0)},
    ),
    Row(
        "different_line_is_new_billing",
        [A, invoice(2, line="2"), credit(3, 150)],
        {"C1/L1": (200, 150)},
    ),
    Row(
        "ordinary_update_keeps_original_attribution",
        [A, invoice(2, key="L2")],
        {"C1/L1": (100, 0), "C1/L2": (0, 0)},
    ),
]


@pytest.mark.parametrize("row", ROWS, ids=[row.name for row in ROWS])
def test_ledger_billing_follows_the_kernel_identity(row: Row) -> None:
    """``billed_cum`` and ``credited_cum`` per subject at the end of the stream, the
    ``REFUND_EXCEEDS_BILLED`` findings (code, subject, credit event), and the first line's 100 at
    10 January in every row (nothing moves history)."""
    events = tuple(sorted(row.events, key=lambda e: e.order_key))
    built = ledger.build(events, {}, frozenset())
    for subject, (billed, credited) in row.points.items():
        point = built.ledger.at(subject)
        assert (point.billed_cum, point.credited_cum) == (Fraction(billed), Fraction(credited)), (
            subject
        )
        assert point.paid_cum == 0
    assert [(f.code, f.subject_key, f.event_key) for f in built.findings] == list(row.findings)
    first = ledger.subject_of(events[0])
    assert built.ledger.at(first, on=JAN_10).billed_cum == Fraction(100)


def test_status_update_adds_no_ledger_step_and_no_stream_movement() -> None:
    """The update creates no ``LedgerStep`` (S01-INV-03 reads the steps) and the contract stream an
    unreferenced credit draws on holds the first line only (S01-R-16)."""
    events = (A, invoice(2), invoice(3, amount=200, cancel=True))
    built = ledger.build(events, {}, frozenset())
    steps = built.ledger.steps["C1/L1"]
    assert [step.point.billed_cum for step in steps] == [Fraction(100), Fraction(300)]
    assert [step.order_key[0] for step in steps] == [JAN_5, JAN_15]


def test_mismatched_update_is_excluded_here_and_left_to_stage_10() -> None:
    """A repeated identity with another amount and ``is_cancellable`` not true is a status update
    for the ledger (adds nothing, raises nothing); stage 10 owns ``INVOICE_STATUS_UPDATE_MISMATCH``
    (``test_s10_billing.py``; ``test_s14_billing_identity_functional.py``)."""
    built = ledger.build((A, invoice(2, amount=999)), {}, frozenset())
    assert built.ledger.at("C1/L1").billed_cum == Fraction(100)
    assert built.findings == ()


def test_legacy_template_world_ignores_a_status_update() -> None:
    """Legacy-template control (stage 06 ``legacy_templates._net_billed`` reads the ledger):
    MOD-LEGACY-PROS-GT12 with a same-amount noncancellable status update of its first invoice
    (100.00, INV-Contract1-POB1-2023-01-31) computes the keyed figures exactly: the version
    columns, every balance row and every posting line are unchanged, because the update adds
    nothing to the ledger's billing."""
    base = checkpoint_bundle("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")
    bill = first_billing(base)
    keyed = compute_book(base)
    book = compute_book(
        with_events(base, billing_after(base, bill, bill.effective_date, cancellable=False))
    )
    assert keyed.contract_version is not None and book.contract_version is not None
    assert dict(book.contract_version.columns) == dict(keyed.contract_version.columns)
    assert [(r.subject_key, r.period_key, dict(r.columns)) for r in book.balances] == [
        (r.subject_key, r.period_key, dict(r.columns)) for r in keyed.balances
    ]
    assert sorted(
        (i.posting_period_key, i.entry_kind, line.account_role, line.side, line.amount_txn)
        for i in book.posting_intents
        for line in i.lines
    ) == sorted(
        (i.posting_period_key, i.entry_kind, line.account_role, line.side, line.amount_txn)
        for i in keyed.posting_intents
        for line in i.lines
    )
