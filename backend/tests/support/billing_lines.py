"""Answer-key worlds with added or repeated ``BILLING_RECORDED`` lines (D-91 C606-05h; stage 13).

The public ``erev_engine.compute`` tests of the S10-R-07 consumers and of the stage 13 billing
control flows start from frozen answer-key checkpoints (DG-AK-40 bundles) and append or edit
invoice lines in memory: a same-identity status update, a repeated cancellable line, a distinct
line on the same document, a line on another member contract. Nothing here reads a clock, draws a
random value or touches a database (DG-TST-18); the key files are never edited.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import cast

import erev_engine
from erev_engine.bundle import BookOutput, EventInput, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.trace import reevaluate
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

__all__ = [
    "billing_after",
    "checkpoint_bundle",
    "compute_book",
    "first_billing",
    "journal",
    "net_posted",
    "period_balance",
    "replace_payload",
    "with_events",
    "with_policy",
]

BILLING = "BILLING_RECORDED"


def checkpoint_bundle(family: str, key_id: str, name: str) -> InputBundle:
    """The one bundle of checkpoint ``name`` of the key ``family/key_id`` (DG-AK-40)."""
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = next(c for c in runners._build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    return cast(InputBundle, bundle)


def first_billing(bundle: InputBundle, contract_key: str | None = None) -> EventInput:
    """The first ``BILLING_RECORDED`` of the bundle (of ``contract_key`` when named)."""
    return next(
        e
        for e in bundle.events
        if e.event_type == BILLING and (contract_key is None or e.contract_key == contract_key)
    )


def billing_after(
    bundle: InputBundle,
    base: EventInput,
    on: date,
    *,
    contract_key: str | None = None,
    cancellable: object | None = None,
    drop: Iterable[str] = (),
    **changes: object,
) -> EventInput:
    """A ``BILLING_RECORDED`` on ``on`` copying ``base``'s payload with ``changes``.

    ``cancellable`` sets ``is_cancellable`` (``True``, ``"true"``, ``False``, ``"false"``);
    ``None`` keeps ``base``'s flag; a member named in ``drop`` is removed (an absent flag). The
    event takes the next CV-22 stream version of its contract and the next record sequence of the
    bundle, so it sorts last among the events of its date (ENG-06).
    """
    contract = base.contract_key if contract_key is None else contract_key
    payload: dict[str, object] = {k: v for k, v in base.payload.items() if k not in set(drop)}
    payload.update(changes)
    if cancellable is not None:
        payload["is_cancellable"] = cancellable
    version = max(
        (e.stream_version for e in bundle.events if e.contract_key == contract), default=0
    )
    seq = max(e.record_seq for e in bundle.events) + 1
    key = payload.get("obligation_key")
    return dataclasses.replace(
        base,
        event_key=f"{contract}/EV-{version + 1:06d}",
        contract_key=contract,
        stream_version=version + 1,
        record_seq=seq,
        effective_date=on,
        recorded_at=datetime(on.year, on.month, on.day, 17, tzinfo=UTC),
        obligation_keys=(str(key),) if isinstance(key, str) else (),
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )


def with_events(bundle: InputBundle, *extra: EventInput) -> InputBundle:
    """``bundle`` with ``extra`` appended in ENG-06 order.

    Records are re-sequenced in that order with non-decreasing record times, so an added line dated
    before later events of the stream is not a late event (S08-R-10 ``OUT_OF_ORDER``); the CV-22
    event keys are kept. ``known_at`` covers every record.
    """
    ordered = sorted(
        (*bundle.events, *extra), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
    )
    events: list[EventInput] = []
    recorded_at = min(e.recorded_at for e in ordered)
    for seq, event in enumerate(ordered, start=1):
        recorded_at = max(recorded_at, event.recorded_at)
        events.append(dataclasses.replace(event, record_seq=seq, recorded_at=recorded_at))
    known_at = max([bundle.known_at, *(e.recorded_at for e in events)])
    return dataclasses.replace(bundle, events=tuple(events), known_at=known_at)


def replace_payload(bundle: InputBundle, event_key: str, **changes: object) -> InputBundle:
    """``bundle`` with the payload of ``event_key`` updated by ``changes`` (hash refreshed)."""
    events = []
    found = False
    for event in bundle.events:
        if event.event_key == event_key:
            payload = {**event.payload, **changes}
            event = dataclasses.replace(event, payload=payload, payload_sha256=sha256_hex(payload))
            found = True
        events.append(event)
    if not found:
        raise KeyError(event_key)
    return dataclasses.replace(bundle, events=tuple(events))


def with_policy(bundle: InputBundle, code: str, value: str) -> InputBundle:
    """Every resolved row of policy ``code`` set to ``value`` in every book (pin P: all periods)."""
    books = []
    seen = False
    for book in bundle.books:
        rows = []
        for row in book.policies:
            if row.code == code:
                row = dataclasses.replace(row, value=value)
                seen = True
            rows.append(row)
        books.append(dataclasses.replace(book, policies=tuple(rows)))
    if not seen:
        raise KeyError(code)
    return dataclasses.replace(bundle, books=tuple(books))


def compute_book(
    bundle: InputBundle, book_code: str = "ASC606", *, warnings: Sequence[str] = ()
) -> BookOutput:
    """The book of a public compute: exactly the expected WARNING diagnostics (``warnings``, by
    code, in CV-43 order; none by default) and every trace node re-evaluates (PROP:P14)."""
    output = cast(OutputBundle, erev_engine.compute(bundle))
    assert [item.code for item in output.diagnostics] == list(warnings), output.diagnostics
    assert all(item.severity == "WARNING" for item in output.diagnostics)
    (book,) = [item for item in output.books if item.book_code == book_code]
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}
    return book


def journal(book: BookOutput, entry_kind: str, period: str) -> list[tuple[str, str, int]]:
    """(account role, side, transaction minor units) of ``entry_kind`` in ``period``, sorted."""
    return sorted(
        (line.account_role, line.side, line.amount_txn)
        for intent in book.posting_intents
        if intent.entry_kind == entry_kind and intent.posting_period_key == period
        for line in intent.lines
    )


def net_posted(book: BookOutput, role: str, period: str, *, credit: bool = True) -> int:
    """Net amount posted to ``role`` in ``period`` (credit positive by default; minor units)."""
    total = 0
    for intent in book.posting_intents:
        if intent.posting_period_key != period:
            continue
        for line in intent.lines:
            if line.account_role != role:
                continue
            sign = 1 if (line.side == "C") == credit else -1
            total += sign * line.amount_txn
    return total


def period_balance(book: BookOutput, period: str, column: str) -> int:
    """Σ of ``column`` over the T-CON-09 balance rows of ``period`` (minor units)."""
    rows = [row for row in book.balances if row.period_key == period]
    assert rows, period
    return sum(int(cast(int, row.columns.get(column, 0)) or 0) for row in rows)
