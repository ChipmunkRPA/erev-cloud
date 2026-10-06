"""S14-R-13a (ENGINE_SPEC_B rev 1.25; D-98 candidate 95; Codex C6-RPT-R3): every intent line of a
cumulative delta carries ``source_event_keys`` — the ENG-06-ordered keys of the events of the
delta's subject's member contracts first included in the computation — while ``source_event_key``
stays ``None`` (L2-5-Q-36). The book loop binds the set from the bundle stream before the S01-R-12
removal, so a void names itself. Fail-first on the docs head 374a38e0: ``IntentLine`` has no
``source_event_keys``.

The world is the D-98 78 / 80 voided-member world (``test_s05_voided_member``): booking,
activation, delivery, then a ``CONTRACT_VOIDED`` with a posted JET-02 history, so stage 14 emits
the VOID reversal. Standard library and the engine only; no database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import erev_engine
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import BookInput, ContractInput, EventInput, InputBundle, PostedAmountInput
from erev_engine.stages.s14_posting import intents
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
LINE_END = date(2026, 12, 31)
POB = f"{CONTRACT}/POB-01"


def _booking() -> EventInput:
    line = bundles.booking_line(
        "POB-01", quantity="1", total_price="1200.00", start=INCEPTION, end=LINE_END
    )
    return bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def _event(stream: int, event_type: str, on: date, payload: Mapping[str, object]) -> EventInput:
    obligation = payload.get("obligation_key")
    keys = [obligation] if isinstance(obligation, str) else []
    return bundles.event(CONTRACT, stream, event_type, on, payload, obligation_keys=keys)


def _bundle(
    *events: EventInput,
    contracts: Iterable[ContractInput] | None = None,
    posted: tuple[PostedAmountInput, ...] = (),
    previous_stream_heads: tuple[tuple[str, int], ...] = (),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24, books=("ASC606",))
    headers = tuple(contracts or (bundles.contract(CONTRACT, inception=INCEPTION),))
    book: BookInput = bundles.book("ASC606", preset="DEFAULT", entity=calendar)
    group = dataclasses.replace(
        bundles.group(headers, products=(bundles.product(),)),
        previous_stream_heads=previous_stream_heads,
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=group,
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=posted,
    )


WORLD = (
    _booking(),
    _event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
    _event(
        3,
        "DELIVERY_RECORDED",
        date(2026, 2, 1),
        {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "DELIVERY"},
    ),
    _event(4, "CONTRACT_VOIDED", date(2026, 3, 1), {"reason_code": "DUPLICATE", "comment": "x"}),
)


def _posted_history() -> tuple[PostedAmountInput, ...]:
    revenue_credit = PostedAmountInput(
        "ASC606",
        "US01",
        POB,
        "REVENUE_RECOGNITION",
        "REVENUE",
        None,
        None,
        "FY2026-P01",
        None,
        "EVENT",
        "USD",
        "USD",
        -120_000,
        -120_000,
    )
    receivable_debit = dataclasses.replace(
        revenue_credit,
        account_role="UNBILLED_RECEIVABLE",
        amount_txn=120_000,
        amount_functional=120_000,
    )
    return (revenue_credit, receivable_debit)


def test_s14_r13a_void_reversal_lines_carry_the_first_included_events_in_order() -> None:
    """A first computation includes every event, so the reversal's lines carry all four keys in
    ENG-06 order — the void itself included (it stays in the stream; S01-R-13) — and no single
    ``source_event_key``."""
    output = erev_engine.compute(_bundle(*WORLD, posted=_posted_history()))
    assert output.diagnostics == ()
    (book,) = output.books
    (intent,) = book.posting_intents
    assert intent.reason_code == "VOID"
    expected = tuple(f"{CONTRACT}/EV-{n:06d}" for n in (1, 2, 3, 4))
    for line in intent.lines:
        assert line.source_event_key is None  # L2-5-Q-36 kept
        assert line.source_event_keys == expected, line


def test_s14_r13a_only_events_past_the_previous_stream_head_are_first_included() -> None:
    """With events 1 and 2 already included by an earlier computation, only the delivery and the
    void are new: the set is exactly those two keys, in stream order."""
    output = erev_engine.compute(
        _bundle(*WORLD, posted=_posted_history(), previous_stream_heads=((CONTRACT, 2),))
    )
    assert output.diagnostics == ()
    (book,) = output.books
    (intent,) = book.posting_intents
    expected = (f"{CONTRACT}/EV-000003", f"{CONTRACT}/EV-000004")
    assert {line.source_event_keys for line in intent.lines} == {expected}


def test_s14_r13a_group_lineage_when_the_subject_has_no_first_included_event() -> None:
    """D-98 candidate 102b: the pure lineage rule over the subject's member contracts — its own
    first-included events when there are any (member order irrelevant, ENG-06 order kept); the
    group's first-included events when its own set is empty; empty only when the group's set is
    empty (the trigger-only case)."""
    new_events = (("B", "B/EV-000002"), ("A", "A/EV-000003"), ("B", "B/EV-000004"))
    assert intents.lineage_keys({"A"}, new_events) == ("A/EV-000003",)
    assert intents.lineage_keys({"A", "B"}, new_events) == (
        "B/EV-000002",
        "A/EV-000003",
        "B/EV-000004",
    )
    assert intents.lineage_keys({"C"}, new_events) == (
        "B/EV-000002",
        "A/EV-000003",
        "B/EV-000004",
    )  # member C had no event of its own: the group's set, in ENG-06 order
    assert intents.lineage_keys({"C"}, ()) == ()  # nothing first included at all
