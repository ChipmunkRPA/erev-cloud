"""S10-R-07 invoice-line identity: the kernel helper and its consumers (D-91; EKC-6).

``erev_engine.billing_identity`` is the one home of the S10-R-07 decision (D-91 "One identity
rule, one home"): identity (contract, ``invoice_number``, ``line_external_id``) at contract scope
over an ENG-06 stream; a repeat whose ``is_cancellable`` is not true is a status update of the
first line and adds no billing; a repeat flagged cancellable is another line. The rc consumers
(stage 04 financing ``_judged_points``, stage 09 ``returns``, stage 10 ``classification``) read
``iter_billing_lines``; the 05h consumers (stage 04 ``taxes.excluded`` / ``taxes.collected_tax``
and ``specialist.invoices``; D-91 C606-05h, lane ENG-B4) read the kept-lines view ``kept_lines``.
``test_four_consumers_agree`` asserts every consumer agrees on every matrix row.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from erev_engine import billing_identity
from erev_engine.billing_identity import (
    BillingLine,
    is_cancellable,
    iter_billing_lines,
    kept_lines,
    line_identity,
)
from erev_engine.stages.s04_transaction_price import financing, specialist, taxes
from erev_engine.stages.s10_billing_balances import classification
from erev_engine.stages.state import EventView
from support.recognition import allocated_state, book_context, event_view, obligation, segment, usd

C1, C2 = "C-ID-1", "C-ID-2"
JAN10, JAN20 = date(2026, 1, 10), date(2026, 1, 20)
INVOICE = {
    "invoice_number": "INV-1",
    "line_external_id": "INV-1-1",
    "amount": Decimal("1000.00"),
    "tax_amount": Decimal("100.00"),
    "issue_date": JAN10,
}


def _line(
    version: int,
    when: date = JAN10,
    *,
    contract: str = C1,
    cancellable: object = True,
    absent: bool = False,
    **changes: object,
) -> EventView:
    payload: dict[str, object] = {**INVOICE, **changes}
    if not absent:
        payload["is_cancellable"] = cancellable
    keys = [str(payload["obligation_key"])] if "obligation_key" in payload else []
    return event_view(contract, version, "BILLING_RECORDED", when, payload, obligation_keys=keys)


LINE = _line(3)
# (row, events, lines the identity rule recognises over the whole stream)
MATRIX: list[tuple[str, list[EventView], int]] = [
    ("line", [LINE], 1),
    ("repeat_false", [LINE, _line(4, JAN20, cancellable=False)], 1),
    ("repeat_string_false", [LINE, _line(4, JAN20, cancellable="false")], 1),
    ("repeat_absent", [LINE, _line(4, JAN20, absent=True)], 1),
    ("repeat_true", [LINE, _line(4, JAN20, cancellable=True)], 2),
    ("repeat_string_true", [LINE, _line(4, JAN20, cancellable="true")], 2),
    ("different_line_id", [LINE, _line(4, JAN20, line_external_id="INV-1-2")], 2),
    ("other_contract", [LINE, _line(3, JAN10, contract=C2)], 2),
]
ROWS = {row: (events, lines) for row, events, lines in MATRIX}


def test_is_cancellable_reads_only_the_true_literals() -> None:
    """``True`` and ``"true"`` are cancellable; ``false``, ``"false"``, absent and numbers are not
    (04:2648 default ``false``; L2-4-Q-8)."""
    assert is_cancellable(_line(3, cancellable=True))
    assert is_cancellable(_line(3, cancellable="true"))
    assert not is_cancellable(_line(3, cancellable=False))
    assert not is_cancellable(_line(3, cancellable="false"))
    assert not is_cancellable(_line(3, absent=True))
    assert not is_cancellable(_line(3, cancellable=1))
    assert not is_cancellable(_line(3, cancellable="True"))


def test_line_identity_is_contract_invoice_and_line() -> None:
    assert line_identity(LINE) == (C1, "INV-1", "INV-1-1")
    assert line_identity(_line(3, contract=C2)) == (C2, "INV-1", "INV-1-1")
    bare = event_view(C1, 9, "BILLING_RECORDED", JAN10, {"amount": Decimal("1")})
    assert line_identity(bare) == (C1, "", "")
    # The payload obligation_key is not part of the identity (S10-R-07).
    assert line_identity(_line(3, obligation_key="L1")) == line_identity(LINE)


@pytest.mark.parametrize(("row", "events", "lines"), MATRIX, ids=[row for row, _, _ in MATRIX])
def test_billing_identity_matrix(row: str, events: Sequence[EventView], lines: int) -> None:
    """The helper yields every ``BILLING_RECORDED`` once: ``lines`` lines, the rest status updates
    of their first line, in stream order."""
    items = list(iter_billing_lines(events))
    assert len(items) == len(events)
    assert sum(1 for item in items if not item.is_status_update) == lines
    for item in items:
        assert item.line is (item.event if not item.is_status_update else events[0])
        assert item.identity == line_identity(item.event)
        assert not item.amount_mismatch and not item.obligation_mismatch
    if row.startswith("repeat_") and lines == 1:
        update = items[1]
        assert update.is_status_update and update.line is LINE


@pytest.mark.parametrize(("row", "events", "lines"), MATRIX, ids=[row for row, _, _ in MATRIX])
def test_kept_lines_view_excludes_status_updates(
    row: str, events: Sequence[EventView], lines: int
) -> None:
    """``kept_lines`` is the ENGINE_SPEC_B §9.2.7 view: the events ``iter_billing_lines`` yields as
    lines, in order, and nothing else (a mismatched update is excluded like a same-amount one)."""
    kept = list(kept_lines(events))
    assert kept == [item.event for item in iter_billing_lines(events) if not item.is_status_update]
    assert len(kept) == lines
    mismatched = _line(9, JAN20, cancellable=False, amount=Decimal("1.00"), obligation_key="L9")
    assert list(kept_lines([*events, mismatched])) == kept
    assert list(kept_lines(events, contract_key=C2)) == [e for e in kept if e.contract_key == C2]
    assert list(kept_lines(events, before=events[0])) == []


def test_iter_billing_lines_filters_by_contract_and_position_and_skips_other_events() -> None:
    other = event_view(C1, 5, "CREDIT_MEMO_RECORDED", JAN20, {"amount": Decimal("1")})
    events = [LINE, other, _line(6, JAN20, cancellable=False), _line(3, contract=C2)]
    assert [item.event.contract_key for item in iter_billing_lines(events)] == [C1, C1, C2]
    assert [item.event.event_key for item in iter_billing_lines(events, contract_key=C2)] == [
        f"{C2}/EV-000003"
    ]
    # ``before`` keeps the events whose ENG-06 order key precedes the position's.
    before = _line(6, JAN20, cancellable=False)
    assert [item.event.event_key for item in iter_billing_lines(events, before=before)] == [
        f"{C1}/EV-000003",
        f"{C2}/EV-000003",
    ]
    assert list(iter_billing_lines([], contract_key=C1)) == []


def test_status_update_mismatches_are_reported_not_validated() -> None:
    """A different amount is an ``amount_mismatch``; a non-null ``obligation_key`` different from
    the first line's non-null key is an ``obligation_mismatch``; null on either side is no change
    (D-91 C606-01 (3)). The helper raises nothing: stage 10 owns the finding."""
    line = _line(3, obligation_key="L1")

    def update(**changes: object) -> BillingLine[EventView]:
        (_, item) = iter_billing_lines([line, _line(4, JAN20, cancellable=False, **changes)])
        assert item.is_status_update and item.line is line
        return item

    assert (update(obligation_key="L1").amount_mismatch, update().obligation_mismatch) == (
        False,
        False,
    )
    assert update(obligation_key="L1", amount=Decimal("900.00")).amount_mismatch
    assert update(obligation_key="L1", amount="1000.00").amount_mismatch is False  # same value
    assert update(obligation_key="L2").obligation_mismatch  # a → b
    assert update().obligation_mismatch is False  # key → null: no change
    (_, null_to_key) = iter_billing_lines(
        [LINE, _line(4, JAN20, cancellable=False, obligation_key="L1")]
    )
    assert null_to_key.obligation_mismatch is False  # null → key: no change
    malformed = _line(4, JAN20, cancellable=False, amount=None)
    (_, item) = iter_billing_lines([line, malformed])
    assert item.amount_mismatch  # an unreadable amount never equals the first line's


# --- Four consumers on the matrix (D-91 "One identity rule, one home") ---------------------------


def _pob_state(events: Sequence[EventView]) -> SimpleNamespace:
    """The ``st.identified.canonical`` view the stage 04 consumers read: the ENG-06 events and,
    for financing's billing-mode lookup (D-91 05g), each contract's contracting entity."""
    ordered = tuple(sorted(events, key=lambda ev: ev.order_key))
    entity = next(iter(book_context().entities))
    contracts = {
        ev.contract_key: SimpleNamespace(header=SimpleNamespace(contracting_entity_code=entity))
        for ev in ordered
    }
    return SimpleNamespace(
        identified=SimpleNamespace(canonical=SimpleNamespace(events=ordered, contracts=contracts))
    )


def _helper(events: Sequence[EventView]) -> int:
    return sum(
        1
        for item in iter_billing_lines(sorted(events, key=lambda e: e.order_key))
        if not item.is_status_update
    )


def _financing(events: Sequence[EventView]) -> int:
    """S04-R-10a points per contract: each line is one 1,000.00 point per date; the rows never
    net two lines on one date, so the point count is the line count... except that two lines on
    one date sum, so the amount is compared instead: Σ points ÷ 1,000."""
    st = _pob_state(events)
    ctx = book_context()  # DEFAULT preset: ERP billing, every line a point at its effective date
    total = Fraction(0)
    for contract in sorted({ev.contract_key for ev in events}):
        derived = financing._judged_points(ctx, st, contract, None)
        assert derived.payment_source == "BILLING_RECORDED"
        total += sum((amount for _, amount in derived.points), Fraction(0))
    return int(total / 1000)


def _classification(events: Sequence[EventView]) -> int:
    ctx = book_context()
    obligations = [
        obligation(
            "L1",
            [
                segment(
                    Fraction(10000), usd("10000.00"), start=JAN10, end=JAN10, quantity=Fraction(100)
                )
            ],
            contract_key=contract,
            method="UNITS_DELIVERED",
            convention=None,
            quantity=Fraction(100),
        )
        for contract in sorted({ev.contract_key for ev in events})
    ]
    st = allocated_state(obligations, events=events, inception=JAN10, statuses=((JAN10, "ACTIVE"),))
    classified = classification.classify(ctx, st)
    assert classified.findings == ()
    return sum(len(doc.lines) for doc in classified.documents if doc.kind == classification.INVOICE)


def _taxes(events: Sequence[EventView]) -> int:
    members = {ev.contract_key for ev in events}
    ordered = sorted(events, key=lambda e: e.order_key)
    return int(
        taxes.collected_tax(ordered, members, date(2026, 12, 31)) / 100
    )  # 100.00 of tax a line


def _specialist(events: Sequence[EventView]) -> int:
    st = _pob_state(events)
    return sum(
        len(specialist.invoices(st, contract, (), date(2026, 1, 1), date(2026, 12, 31)))
        for contract in sorted({ev.contract_key for ev in events})
    )


CONSUMERS = {
    "helper": _helper,
    "financing": _financing,
    "classification": _classification,
    "taxes": _taxes,
    "specialist": _specialist,
}


@pytest.mark.parametrize(
    ("consumer", "row"),
    [pytest.param(consumer, row, id=f"{consumer}-{row}") for consumer in CONSUMERS for row in ROWS],
)
def test_four_consumers_agree(consumer: str, row: str) -> None:
    """Row by row, every consumer counts the lines the kernel helper recognises: one for every
    not-true repeat; two for ``True`` / ``"true"``, a different line id and a second contract. The
    taxes rows ``repeat_true``, ``repeat_string_true`` and ``other_contract`` and the specialist
    rows ``repeat_true`` and ``repeat_string_true`` were ``xfail(strict=True)`` until the 05h
    alignment (D-91 C606-05h)."""
    events, lines = ROWS[row]
    assert CONSUMERS[consumer](events) == lines


def test_consumers_share_one_module() -> None:
    """Every consumer imports the kernel helper rather than mirroring the rule (D-91): the rc
    consumers read ``iter_billing_lines``; the 05h consumers read the kept-lines view
    ``kept_lines`` (ENGINE_SPEC_B §9.2.7) and no longer hold the ``seen`` mirror."""
    import inspect

    from erev_engine.stages.s09_recognition import returns

    for module in (financing, returns, classification):
        source = inspect.getsource(module)
        assert "billing_identity.iter_billing_lines" in source, module.__name__
        assert 'in (True, "true")' not in source, module.__name__
    for module in (taxes, specialist):
        source = inspect.getsource(module)
        assert "billing_identity.kept_lines" in source, module.__name__
        assert "seen: set[tuple[str, str]]" not in source, module.__name__
        assert 'in (True, "true")' not in source, module.__name__
    assert dataclasses.is_dataclass(billing_identity.BillingLine)
