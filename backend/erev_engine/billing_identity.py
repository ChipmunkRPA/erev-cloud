"""S10-R-07 invoice-line identity at contract scope over an ENG-06 event sequence (D-91).

One identity rule, one home (D-91 "One identity rule, one home"): every consumer of billing lines
(stage 10 ``billed_cum``, stage 09 ALG-06 units billed, the stage 04 S04-R-10a payment points
and, since the 05h alignment, the stage 04 S04-R-20 taxes and the S04-R-15 / S04-R-16 incentive
invoices; D-91 C606-05h) reads the same decision from this module; ``first_updates`` and
``unconditional_source`` / ``unconditional_date`` carry the S10-R-06 date of a cancellable
``ENGINE`` line for stage 10, stage 09 and stage 04 alike (D-91 05g; one home, lane ENG-C6). The
identity of a ``BILLING_RECORDED`` line is (contract key, ``invoice_number``,
``line_external_id``) (ENGINE_SPEC_B S10-R-07; the payload ``obligation_key`` is not part of it).
Over an ENG-06 ordered
stream the first-seen event of an
identity is the line; a repeat whose ``is_cancellable`` is not true (``false``, ``"false"`` or
absent: the 04 billing-document column defaults to ``false``, 04:2648; L2-4-Q-8) is a status
update of that line, which adds no billing anywhere in the engine (04 §16.3 ``BILLING_RECORDED``
row, 04:5588); a repeat
flagged cancellable is another line (stage 10 parity; D-91 C606-01 (2), C606-05e). A status update
is recorded with its first line, an ``amount_mismatch`` when its amount differs from the first
line's and an ``obligation_mismatch`` when both name an obligation and the keys differ (a null
``obligation_key`` on either side means no change, D-91 C606-01 (3)). This module validates no
amount and raises no finding: stage 10 owns ``INVOICE_STATUS_UPDATE_MISMATCH`` (04 table 15.4-B).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Final, Protocol

from erev_engine.money import to_fraction

__all__ = [
    "BILLING_RECORDED",
    "BillingEvent",
    "BillingLine",
    "first_updates",
    "is_cancellable",
    "iter_billing_lines",
    "kept_lines",
    "line_identity",
    "unconditional_date",
    "unconditional_source",
]

BILLING_RECORDED: Final = "BILLING_RECORDED"

Identity = tuple[str, str, str]  # (contract key, invoice_number, line_external_id)


class BillingEvent(Protocol):
    """The members of a canonical event this module reads (stages ``EventView``)."""

    @property
    def event_key(self) -> str: ...

    @property
    def contract_key(self) -> str: ...

    @property
    def event_type(self) -> str: ...

    @property
    def effective_date(self) -> date: ...

    @property
    def payload(self) -> Mapping[str, object]: ...

    @property
    def order_key(self) -> tuple[date, int, str]: ...


@dataclass(frozen=True, slots=True)
class BillingLine[E: BillingEvent]:
    """One ``BILLING_RECORDED`` event classified under S10-R-07.

    ``line`` is the first-seen event of the identity: the event itself for a line, the line it
    updates for a status update. ``amount_mismatch``, ``obligation_mismatch`` and ``tax_mismatch``
    are set on a status update only; a same-amount update with no obligation change is the line's
    unconditional source in ``ENGINE`` mode (S10-R-06; D-89 L7-6-Q-9) whatever its tax: a tax
    difference is stage 10's ``INVOICE_STATUS_UPDATE_TAX_MISMATCH`` (``WARNING``, no value effect;
    D-97 (27)).
    """

    event: E
    is_status_update: bool
    line: E
    amount_mismatch: bool = False
    obligation_mismatch: bool = False
    tax_mismatch: bool = False  # D-97 (27): the update's tax_amount differs (absent reads 0)

    @property
    def identity(self) -> Identity:
        """(contract key, ``invoice_number``, ``line_external_id``) of the event."""
        return line_identity(self.event)


def _text(payload: Mapping[str, object], member: str) -> str:
    value = payload.get(member)
    return "" if value is None else str(value)


def line_identity(event: BillingEvent) -> Identity:
    """(contract key, ``invoice_number`` or ``""``, ``line_external_id`` or ``""``)."""
    return (
        event.contract_key,
        _text(event.payload, "invoice_number"),
        _text(event.payload, "line_external_id"),
    )


def is_cancellable(event: BillingEvent) -> bool:
    """True only for the payload literal ``True`` or ``"true"``.

    ``false``, ``"false"`` and an absent member are not true (the 04 default is ``false``;
    L2-4-Q-8). Numbers never count as a flag.
    """
    value = event.payload.get("is_cancellable")
    return value is True or (isinstance(value, str) and value == "true")


def _amount(payload: Mapping[str, object]) -> Fraction | None:
    value = payload.get("amount")
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        return None
    try:
        return to_fraction(value)
    except ValueError:
        return None


def _tax(payload: Mapping[str, object]) -> Fraction | None:
    """``tax_amount`` as a Fraction; absent or null reads 0 (04 §16.3: the receivable is ``amount``
    + ``tax_amount``); an unparsable value is ``None``."""
    value = payload.get("tax_amount")
    if value is None or value == "":
        return Fraction(0)
    return _amount({"amount": value})


def _obligation_mismatch(update: BillingEvent, line: BillingEvent) -> bool:
    updated = _text(update.payload, "obligation_key")
    original = _text(line.payload, "obligation_key")
    return updated != "" and original != "" and updated != original


def iter_billing_lines[E: BillingEvent](
    events: Iterable[E],
    *,
    contract_key: str | None = None,
    before: BillingEvent | None = None,
) -> Iterator[BillingLine[E]]:
    """Classify the ``BILLING_RECORDED`` events of ``events``, in the order given (ENG-06).

    ``contract_key`` keeps one contract's events; ``before`` keeps the events whose ENG-06 order
    key precedes that event's. Identities are tracked at contract scope over the whole sequence,
    before any per-obligation or per-date filter a consumer applies afterwards (S09-R-23a;
    S04-R-10a). Every event is yielded once: a line, or a status update with its first line.
    """
    first: dict[Identity, E] = {}
    for event in events:
        if event.event_type != BILLING_RECORDED:
            continue
        if contract_key is not None and event.contract_key != contract_key:
            continue
        if before is not None and not event.order_key < before.order_key:
            continue
        identity = line_identity(event)
        line = first.get(identity)
        if line is None or is_cancellable(event):
            first.setdefault(identity, event)
            yield BillingLine(event, False, event)
            continue
        first_amount, amount = _amount(line.payload), _amount(event.payload)
        first_tax, tax = _tax(line.payload), _tax(event.payload)
        yield BillingLine(
            event,
            True,
            line,
            amount_mismatch=first_amount is None or amount is None or first_amount != amount,
            obligation_mismatch=_obligation_mismatch(event, line),
            tax_mismatch=first_tax is None or tax is None or first_tax != tax,
        )


def kept_lines[E: BillingEvent](
    events: Iterable[E],
    *,
    contract_key: str | None = None,
    before: BillingEvent | None = None,
) -> Iterator[E]:
    """The kept lines of ``events``: every non-update occurrence, in the order given (ENGINE_SPEC_B
    §9.2.7 ``units_billed_or_paid``; S04-R-10a).

    Not "one line per identity": the first-seen event of an identity and every repeat flagged
    cancellable are each a kept line (D-91 C606-01 (2)). Status-update records are excluded,
    mismatched or not, so their amounts never enter a base; a consumer that dates a cancellable
    line by its valid matching update (stage 09 ``ENGINE`` mode, stage 10) reads those updates,
    with their first line and mismatch flags, from ``iter_billing_lines`` over the same stream and
    the applied receipts from the stream itself. Filtering to kept lines alone discards that
    eligibility evidence.
    """
    for item in iter_billing_lines(events, contract_key=contract_key, before=before):
        if not item.is_status_update:
            yield item.event


def first_updates[E: BillingEvent](
    events: Iterable[E],
    *,
    contract_key: str | None = None,
    before: BillingEvent | None = None,
) -> dict[str, E]:
    """The first valid status update of each identity, keyed by the event key of the FIRST-SEEN
    line it updates (``BillingLine.line``): a same-amount, same-obligation noncancellable repeat
    (S10-R-07 "never changes the first line's attribution"; the supervisor's first-line ruling,
    D-92). A mismatched update dates nothing (stage 10 owns the finding); a repeat flagged
    cancellable is another line and appears in no value here. The S10-R-06 consumers (stage 10
    ``classification``, stage 09 ``returns``, stage 04 financing under S04-R-10a, D-91 05g) read
    this map with the receipts applied to the invoice to date a cancellable ENGINE-mode line
    (``unconditional_date``)."""
    found: dict[str, E] = {}
    for item in iter_billing_lines(events, contract_key=contract_key, before=before):
        if item.is_status_update and not item.amount_mismatch and not item.obligation_mismatch:
            found.setdefault(item.line.event_key, item.event)
    return found


def unconditional_source[E: BillingEvent](
    line: E,
    *,
    update: E | None,
    receipts: Iterable[E] = (),
) -> E | None:
    """The event that sets the S10-R-06 unconditional date of a cancellable line in ``ENGINE``
    mode (ENGINE_SPEC_B §10.2.2): the earliest, by (effective date, ENG-06 order key), of the cash
    receipts applied to its invoice and its first valid status update (``first_updates``); the
    line itself when that event is not after the line (the L2-4-Q-11 line-date floor); ``None``
    while memo-only (no update, no applied receipt), when the line adds no billing anywhere. The
    one home of the date for stage 10 ``classification`` (``Line.unconditional_source``), stage 09
    ``returns`` (the ``unconditional_source`` detail) and stage 04 financing
    (``unconditional_date``; D-91 05g). A noncancellable line, and every line in ``ERP`` mode, is
    unconditional at its
    effective date; the consumer decides the mode with ``stages.state.billing_mode_at``."""
    candidates = list(receipts)
    if update is not None:
        candidates.append(update)
    if not candidates:
        return None
    first = min(candidates, key=lambda event: (event.effective_date, event.order_key))
    return line if first.effective_date <= line.effective_date else first


def unconditional_date(
    line: BillingEvent,
    *,
    update: BillingEvent | None,
    receipts: Iterable[BillingEvent] = (),
) -> date | None:
    """The S10-R-06 unconditional date of a cancellable line in ``ENGINE`` mode: the effective
    date of ``unconditional_source`` (never before the line's own date); ``None`` while
    memo-only."""
    source = unconditional_source(line, update=update, receipts=receipts)
    return None if source is None else source.effective_date
