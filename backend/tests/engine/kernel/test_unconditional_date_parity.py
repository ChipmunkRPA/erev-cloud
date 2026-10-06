"""S10-R-06 unconditional date: one kernel home for stages 04, 09 and 10 (D-91 05g; lane ENG-C6).

``billing_identity.first_updates`` names the first valid status update of each first-seen line and
``unconditional_source`` / ``unconditional_date`` the event and date at which a cancellable
``ENGINE``-mode line becomes unconditional (ENGINE_SPEC_B §10.2.2: the earliest of the receipts
applied to its invoice and that update, never before the line, ``None`` while memo-only). Stage 10
``classification`` (``Line.unconditional_date`` / ``unconditional_source``), stage 09
``returns._billing`` (the counted lines and their ``unconditional_source`` detail) and stage 04
``financing._judged_points`` (the S04-R-10a point date) read them. This module pins the kernel rows
and the cross-stage parity across repeated updates, eligibility boundaries and historical
(pre-cutoff) positions. Stage 04 leaves the parity by design where a cash receipt exists: the D-87
receipts-first fallback makes the receipts the points (D-91 05g "receipts and invoice points are
never combined").
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from erev_engine import billing_identity
from erev_engine.stages.s04_transaction_price import financing
from erev_engine.stages.s09_recognition import progress_events, returns
from erev_engine.stages.s10_billing_balances import classification
from erev_engine.stages.state import BookContext, EventView
from support.recognition import allocated_state, book_context, event_view, obligation, segment, usd

C1 = "C-UD-1"
JAN5, JAN10, JAN15 = date(2026, 1, 5), date(2026, 1, 10), date(2026, 1, 15)
JAN20, JAN25, JAN30, JAN31 = (
    date(2026, 1, 20),
    date(2026, 1, 25),
    date(2026, 1, 30),
    date(2026, 1, 31),
)
INVOICE = {
    "invoice_number": "INV-1",
    "line_external_id": "INV-1-1",
    "obligation_key": "L1",
    "amount": Decimal("1000.00"),
    "issue_date": JAN10,
}


def _bill(version: int, when: date, *, cancellable: bool = True, **changes: object) -> EventView:
    payload: dict[str, object] = {**INVOICE, **changes, "is_cancellable": cancellable}
    return event_view(C1, version, "BILLING_RECORDED", when, payload, obligation_keys=["L1"])


def _receipt(version: int, when: date, applied: Sequence[str] = ("INV-1",)) -> EventView:
    payload = {
        "amount": Decimal("1000.00"),
        "form": "CASH",
        "receipt_reference": f"RCPT-{version}",
        "receipt_date": when,
        "applied_invoice_numbers": list(applied),
    }
    return event_view(C1, version, "PAYMENT_RECEIVED", when, payload)


def _engine(ctx: BookContext) -> BookContext:
    """The book with POL-004 ``ENGINE`` and the derived POL-123 basis in every period (pin P)."""
    policies = []
    for policy in ctx.policies.all():
        if policy.code == "billing.posting":
            policy = dataclasses.replace(policy, value="ENGINE")
        elif policy.code == "balance.position_invoice_basis":
            policy = dataclasses.replace(policy, value="UNCONDITIONAL_INVOICES_ONLY")
        policies.append(policy)
    return dataclasses.replace(ctx, policies=type(ctx.policies)(tuple(policies)))


CTX = _engine(book_context())
ENTITY = next(iter(CTX.entities))

LINE = _bill(3, JAN10)  # the cancellable 1,000.00 line of 10 January
UPDATE = _bill(5, JAN20, cancellable=False)  # its same-amount noncancellable update, 20 January
MISMATCH = _bill(4, JAN15, cancellable=False, amount=Decimal("900.00"))  # dates nothing
LATE_UPDATE = _bill(6, JAN25, cancellable=False)
REPEAT = _bill(4, JAN20, cancellable=True)  # the same identity still cancellable: another line
UPDATE_AFTER_REPEAT = _bill(5, JAN25, cancellable=False)  # dates the FIRST-SEEN line only (D-92)
EARLY_RECEIPT = _receipt(2, JAN5)  # applied before the line: the L2-4-Q-11 floor
LATE_RECEIPT = _receipt(7, JAN30)
TIE_RECEIPT = _receipt(8, JAN20)  # the update's date; the lower ENG-06 order key wins

# world -> (events, expected unconditional date per kept line, expected source event per line)
WORLDS: dict[str, tuple[list[EventView], dict[str, date | None], dict[str, EventView | None]]] = {
    "memo_only": ([LINE], {LINE.event_key: None}, {LINE.event_key: None}),
    "update_after_line": ([LINE, UPDATE], {LINE.event_key: JAN20}, {LINE.event_key: UPDATE}),
    "mismatch_then_valid_update": (
        [LINE, MISMATCH, LATE_UPDATE],
        {LINE.event_key: JAN25},
        {LINE.event_key: LATE_UPDATE},
    ),
    "repeat_cancellable_then_update": (
        [LINE, REPEAT, UPDATE_AFTER_REPEAT],
        {LINE.event_key: JAN25, REPEAT.event_key: None},
        {LINE.event_key: UPDATE_AFTER_REPEAT, REPEAT.event_key: None},
    ),
    "receipt_before_line": ([EARLY_RECEIPT, LINE], {LINE.event_key: JAN10}, {LINE.event_key: LINE}),
    "receipt_after_and_update": (
        [LINE, UPDATE, LATE_RECEIPT],
        {LINE.event_key: JAN20},
        {LINE.event_key: UPDATE},
    ),
    "receipt_only_after": (
        [LINE, LATE_RECEIPT],
        {LINE.event_key: JAN30},
        {LINE.event_key: LATE_RECEIPT},
    ),
    "tie_same_date": (
        [LINE, UPDATE, TIE_RECEIPT],
        {LINE.event_key: JAN20},
        {LINE.event_key: UPDATE},
    ),
}
NO_RECEIPT_WORLDS = [
    name
    for name, (events, _, _) in WORLDS.items()
    if all(ev.event_type != "PAYMENT_RECEIVED" for ev in events)
]
BOUNDARIES = [
    JAN10,
    date(2026, 1, 19),
    JAN20,
    date(2026, 1, 24),
    JAN25,
    date(2026, 1, 29),
    JAN30,
    JAN31,
]


def _ordered(events: Sequence[EventView]) -> tuple[EventView, ...]:
    return tuple(sorted(events, key=lambda ev: ev.order_key))


def _kernel(events: Sequence[EventView]) -> dict[str, EventView | None]:
    ordered = _ordered(events)
    updates = billing_identity.first_updates(ordered, contract_key=C1)
    receipts = [
        ev
        for ev in ordered
        if ev.event_type == "PAYMENT_RECEIVED"
        and "INV-1" in (ev.payload.get("applied_invoice_numbers") or ())
    ]
    return {
        line.event_key: billing_identity.unconditional_source(
            line, update=updates.get(line.event_key), receipts=receipts
        )
        for line in billing_identity.kept_lines(ordered, contract_key=C1)
    }


def _state(events: Sequence[EventView]):  # noqa: ANN202 - the AllocatedState of support.recognition
    ob = obligation(
        "L1",
        [segment(Fraction(10000), usd("10000.00"), start=JAN10, end=JAN10, quantity=Fraction(100))],
        contract_key=C1,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )
    return allocated_state([ob], events=events, inception=JAN5, statuses=((JAN5, "ACTIVE"),))


def _stage10(events: Sequence[EventView]) -> dict[str, tuple[date | None, str | None]]:
    classified = classification.classify(CTX, _state(events))
    return {
        line.event.event_key: (
            line.unconditional_date,
            None if line.unconditional_source is None else line.unconditional_source.event_key,
        )
        for document in classified.documents
        if document.kind == classification.INVOICE
        for line in document.lines
    }


def _stage09(
    events: Sequence[EventView], d: date, position: progress_events.Position | None = None
) -> tuple[dict[str, str | None], int]:
    st = _state(events)
    billing = returns._billing(CTX, st, st.contracts[0], st.obligations[0], d, position)
    counted = {line.ref_id: line.detail.get("unconditional_source") for line in billing.lines}
    return counted, billing.memo_only_lines


def _stage04(
    events: Sequence[EventView], before: EventView | None = None
) -> financing.JudgedPoints:
    ordered = _ordered(events)
    header = SimpleNamespace(contracting_entity_code=ENTITY)
    st = SimpleNamespace(
        identified=SimpleNamespace(
            canonical=SimpleNamespace(
                events=ordered, contracts={C1: SimpleNamespace(header=header)}
            )
        )
    )
    return financing._judged_points(CTX, st, C1, before)


@pytest.mark.parametrize("world", list(WORLDS))
def test_kernel_dates_and_sources(world: str) -> None:
    """Row by row: the first valid update (a mismatched repeat dates nothing; a repeat flagged
    cancellable is another line the update never dates), the receipts applied to the invoice, the
    earliest by (date, ENG-06 order) with the line-date floor, ``None`` while memo-only."""
    events, expected_dates, expected_sources = WORLDS[world]
    sources = _kernel(events)
    assert {key: None if src is None else src.event_key for key, src in sources.items()} == {
        key: None if src is None else src.event_key for key, src in expected_sources.items()
    }
    ordered = _ordered(events)
    updates = billing_identity.first_updates(ordered, contract_key=C1)
    for line in billing_identity.kept_lines(ordered, contract_key=C1):
        receipts = [ev for ev in ordered if ev.event_type == "PAYMENT_RECEIVED"]
        assert (
            billing_identity.unconditional_date(
                line, update=updates.get(line.event_key), receipts=receipts
            )
            == expected_dates[line.event_key]
        )


@pytest.mark.parametrize("world", list(WORLDS))
def test_stage10_reads_the_kernel_date_and_source(world: str) -> None:
    events, expected_dates, expected_sources = WORLDS[world]
    assert _stage10(events) == {
        key: (expected_dates[key], None if src is None else src.event_key)
        for key, src in expected_sources.items()
    }


@pytest.mark.parametrize("world", list(WORLDS))
def test_stage09_counts_a_line_from_the_kernel_date(world: str) -> None:
    """At every boundary date the counted lines are exactly those whose kernel date is ≤ d, with
    the kernel's source in the detail when it is not the line; a memo-only line is counted in
    ``memo_only_lines`` once the line itself is admitted."""
    events, expected_dates, expected_sources = WORLDS[world]
    lines = {ev.event_key: ev for ev in events if ev.event_type == "BILLING_RECORDED"}
    for d in BOUNDARIES:
        counted, memo_only = _stage09(events, d)
        eligible = {
            key
            for key, on in expected_dates.items()
            if on is not None and on <= d and lines[key].effective_date <= d
        }
        assert set(counted) == eligible, (d, counted)
        for key in eligible:
            source = expected_sources[key]
            assert counted[key] == (
                None if source is None or source.event_key == key else source.event_key
            ), (d, key)
        assert memo_only == sum(
            1 for key, on in expected_dates.items() if on is None and lines[key].effective_date <= d
        ), d


@pytest.mark.parametrize("world", NO_RECEIPT_WORLDS)
def test_stage04_dates_its_points_by_the_kernel(world: str) -> None:
    """Without receipts the S04-R-10a points are the kept lines at their kernel dates (netted per
    date) and ``memo_only`` names every line without one."""
    events, expected_dates, _ = WORLDS[world]
    derived = _stage04(events)
    assert derived.payment_source == "BILLING_RECORDED"
    dated = sorted(on for on in expected_dates.values() if on is not None)
    assert [on for on, _ in derived.points] == dated
    assert all(amount == Fraction(1000) for _, amount in derived.points)
    assert set(derived.memo_only) == {key for key, on in expected_dates.items() if on is None}


@pytest.mark.parametrize("world", [name for name in WORLDS if name not in NO_RECEIPT_WORLDS])
def test_stage04_leaves_the_parity_where_a_receipt_exists(world: str) -> None:
    """D-87 receipts-first: a cash receipt makes the receipts the points, whatever the kernel date
    of the line (D-91 05g: never combined).;
    stage 10 and stage 09 still date the line by the kernel."""
    events, expected_dates, _ = WORLDS[world]
    derived = _stage04(events)
    assert derived.payment_source == "PAYMENT_RECEIVED"
    assert [on for on, _ in derived.points] == sorted(
        ev.effective_date for ev in events if ev.event_type == "PAYMENT_RECEIVED"
    )
    assert derived.memo_only == ()
    assert {key: on for key, (on, _) in _stage10(events).items()} == expected_dates


def test_historical_position_before_the_update_is_memo_only() -> None:
    """The pre-cutoff position: with the events strictly before the update, stage 04 has no point
    and one memo-only line; stage 09 at the same position counts nothing; including the update
    restores the 20 January date in both."""
    events = [LINE, UPDATE]
    before = _stage04(events, before=UPDATE)
    assert before.points == () and before.memo_only == (LINE.event_key,)
    after = _stage04(events)
    assert after.points == ((JAN20, Fraction(1000)),) and after.memo_only == ()
    strictly_before = progress_events.Position(UPDATE.order_key, inclusive=False)
    assert _stage09(events, JAN31, strictly_before)[0] == {}
    inclusive = progress_events.Position(UPDATE.order_key, inclusive=True)
    assert _stage09(events, JAN31, inclusive)[0] == {LINE.event_key: UPDATE.event_key}
    assert _stage10(events)[LINE.event_key] == (JAN20, UPDATE.event_key)


def test_one_home_for_the_unconditional_date() -> None:
    """Stages 04, 09 and 10 read the kernel's ``first_updates`` and ``unconditional_source`` /
    ``unconditional_date``; no stage keeps the earliest-candidate mirror."""
    mirror = "min(found, key=lambda event: (event.effective_date, event.order_key))"
    for module in (classification, returns):
        source = inspect.getsource(module)
        assert "billing_identity.first_updates(" in source, module.__name__
        assert "billing_identity.unconditional_source(" in source, module.__name__
        assert mirror not in source, module.__name__
    source = inspect.getsource(financing)
    assert "billing_identity.first_updates(" in source
    assert "billing_identity.unconditional_date(" in source
    assert mirror not in source
