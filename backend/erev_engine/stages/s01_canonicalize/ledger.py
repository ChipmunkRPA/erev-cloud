"""Stage 01 quantity ledger and ledger trace (ENGINE_SPEC §1.5 S01-R-16, S01-R-17, S01-R-19).

``BILLING_RECORDED`` lines enter ``billed_cum`` under the S10-R-07 identity of the kernel helper
``erev_engine.billing_identity`` (supervisor ruling, production continuation, reopening the D-91
post-rc item "the ``_fold`` / s01 ledger exclusion of status updates from billed"): the events of
the ordered stream are classified before any subject or contract-stream attribution, a status
update (a repeated identity whose ``is_cancellable`` is not true) adds nothing, a repeat flagged
cancellable is another line and identity is contract-scoped. Private to stage 01. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import billing_identity
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize.convert import (
    contract_subject_key,
    obligation_subject_key,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.state import EventView, Finding, LedgerPoint, LedgerStep, QuantityLedger
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA_ID",
    "LEDGER_EVENT_TYPES",
    "LedgerBuild",
    "build",
    "emit_trace",
    "referenced_cover",
    "subject_of",
]

FORMULA_ID: Final = "ingest.ledger_sum.v1"
NARRATIVE_KEY: Final = "ingest.ledger_sum"
# Measure events that move the ledger (S01-R-16).
LEDGER_EVENT_TYPES: Final = frozenset(
    {
        "BILLING_RECORDED",
        "COST_INCURRED",
        "CREDIT_MEMO_RECORDED",
        "DELIVERY_RECORDED",
        "MILESTONE_ACHIEVED",
        "PAYMENT_RECEIVED",
        "PROGRESS_RECORDED",
        "RETURN_RECORDED",
        "USAGE_REPORTED",
    }
)
# 04 §16.3: these payloads require obligation_key.
_OBLIGATION_EVENT_TYPES: Final = frozenset(
    {
        "DELIVERY_RECORDED",
        "MILESTONE_ACHIEVED",
        "PROGRESS_RECORDED",
        "RETURN_RECORDED",
        "USAGE_REPORTED",
    }
)


@dataclass(frozen=True, slots=True)
class LedgerBuild:
    ledger: QuantityLedger
    findings: tuple[Finding, ...]
    # subject key -> (event source, signed quantity): deliveries (+) and returns (−), ENG-06 order
    movements: Mapping[str, tuple[tuple[SourceRef, Fraction], ...]]


def subject_of(event: EventView) -> str:
    """The ledger subject of a measure event (S01-R-16).

    The obligation named by ``payload.obligation_key`` or by a single ``obligation_keys`` member;
    unreferenced billing, credits and payments, and every payment, accrue on the contract.
    """
    if event.event_type != "PAYMENT_RECEIVED":
        obligation = payload_text(event.payload, "obligation_key")
        if obligation is not None:
            return obligation_subject_key(event.contract_key, obligation)
        if len(event.obligation_subject_keys) == 1:
            return event.obligation_subject_keys[0]
        if event.event_type in _OBLIGATION_EVENT_TYPES:
            raise ValueError(f"{event.event_key}: {event.event_type} names no obligation (§16.3)")
    return contract_subject_key(event.contract_key)


def _required(event: EventView, name: str) -> Fraction:
    value = payload_fraction(event.payload, name)
    if value is None:
        raise ValueError(f"{event.event_key}: payload member {name} is required (§16.3)")
    return value


def _apply(point: LedgerPoint, event: EventView) -> LedgerPoint | None:
    """The point after ``event``; ``None`` when the event does not move the ledger."""
    replace = dataclasses.replace
    key = event.event_key
    match event.event_type:
        case "DELIVERY_RECORDED":
            q = _required(event, "quantity")
            return replace(point, delivered_cum=point.delivered_cum + q, last_event_key=key)
        case "RETURN_RECORDED":
            q = _required(event, "quantity")
            return replace(point, returned_cum=point.returned_cum + q, last_event_key=key)
        case "COST_INCURRED":
            if event.payload.get("purpose") != "PROGRESS_INPUT":
                return None
            amount = _required(event, "amount")
            return replace(point, costs_cum=point.costs_cum + amount, last_event_key=key)
        case "PROGRESS_RECORDED":
            ratio = _required(event, "cumulative_progress_ratio")
            hours = payload_fraction(event.payload, "hours_to_date")
            return replace(
                point,
                output_ratio=ratio,
                hours_cum=point.hours_cum if hours is None else hours,
                last_event_key=key,
            )
        case "MILESTONE_ACHIEVED":
            weight = _required(event, "cumulative_weight")
            return replace(point, milestone_weight_cum=weight, last_event_key=key)
        case "USAGE_REPORTED":
            q = _required(event, "quantity")
            return replace(
                point, usage_quantity_cum=point.usage_quantity_cum + q, last_event_key=key
            )
        case "BILLING_RECORDED":
            amount = _required(event, "amount")
            return replace(point, billed_cum=point.billed_cum + amount, last_event_key=key)
        case "CREDIT_MEMO_RECORDED":
            amount = _required(event, "amount")
            return replace(point, credited_cum=point.credited_cum + amount, last_event_key=key)
        case "PAYMENT_RECEIVED":
            amount = _required(event, "amount")
            return replace(point, paid_cum=point.paid_cum + amount, last_event_key=key)
    return None


def referenced_cover(
    points: Mapping[str, LedgerPoint], contract: str, subject: str, vc_lines: frozenset[str]
) -> Fraction:
    """The unreferenced billing a referenced credit memo of ``subject`` may still draw on (D-87
    L6-5-Q-15, overruling the second sentence of L4-3-Q-11): the contract subject's billing less its
    credits (the unreferenced credits), less the excess of the other obligations' referenced credits
    over their referenced billing, which drew on the same billing first. Never negative; parity VC
    lines stay out (L6-2-Q-4)."""
    unreferenced = points.get(contract, LedgerPoint.zero())
    drawn = sum(
        (
            max(Fraction(0), point.credited_cum - point.billed_cum)
            for other, point in points.items()
            if other != subject and other.startswith(f"{contract}/") and other not in vc_lines
        ),
        Fraction(0),
    )
    return max(Fraction(0), unreferenced.billed_cum - unreferenced.credited_cum - drawn)


def _finding(code: str, subject: str, event: EventView, **detail: Fraction) -> Finding:
    values = {name: format_exact(value) for name, value in detail.items()}
    return Finding(
        code, "ERROR", subject, {"event_key": event.event_key, **values}, 1, event.event_key
    )


def build(
    measure: Sequence[EventView],
    booked: Mapping[str, Fraction],
    changed: frozenset[str],
    vc_lines: frozenset[str] = frozenset(),
    right_to_invoice: frozenset[str] = frozenset(),
) -> LedgerBuild:
    """Fold the measure events into the ledger and collect its findings (S01-R-16, S01-R-17).

    ``booked`` maps obligation subject keys to booked quantities; ``changed`` holds obligations
    with a quantity-changing boundary, which stage 06 checks instead (S06-R-08).
    ``right_to_invoice`` holds the obligations whose template method is ``RIGHT_TO_INVOICE``: their
    booked quantity is a rate line, so S01-R-17 over-delivery does not apply to them (D-87
    L6-5-Q-16; ENC-6) — a genuine unit over-delivery elsewhere still fires. ``vc_lines`` holds
    the parity VC lines (S03-R-18): ``REFUND_EXCEEDS_BILLED`` covers non-VC billing only (04 table
    15.4-A #25; DEV-022), so a credit on a VC line is not checked, and the billing and credits of a
    VC line stay out of the stream an unreferenced credit draws on. A referenced credit draws on its
    obligation's referenced billing and then on ``referenced_cover`` (D-87 L6-5-Q-15). Every
    independent finding is collected (CV-42). A ``BILLING_RECORDED`` that the kernel classifies as
    an S10-R-07 status update over the whole stream (``billing_identity.iter_billing_lines``,
    before any attribution) moves nothing: no point, no step, no stream, no cover (04 §16.3 "adds
    no billing anywhere in the engine"); stage 10 owns ``INVOICE_STATUS_UPDATE_MISMATCH`` for an
    update whose amount or obligation differs, so no finding is raised here.
    """
    status_updates = {
        item.event.event_key
        for item in billing_identity.iter_billing_lines(measure)
        if item.is_status_update
    }
    points: dict[str, LedgerPoint] = {}
    steps: dict[str, list[LedgerStep]] = {}
    movements: dict[str, list[tuple[SourceRef, Fraction]]] = {}
    findings: list[Finding] = []
    # (billed, credited) over every subject of a contract: the stream an unreferenced credit memo
    # draws on, because stage 10 attributes it over the contract's obligations (S10-R-01, S10-R-03).
    streams: dict[str, tuple[Fraction, Fraction]] = {}
    for event in measure:
        if event.event_type not in LEDGER_EVENT_TYPES or event.event_key in status_updates:
            continue
        subject = subject_of(event)
        before = points.get(subject, LedgerPoint.zero())
        after = _apply(before, event)
        if after is None:
            continue
        points[subject] = after
        if subject not in vc_lines:
            billed, credited = streams.get(event.contract_key, (Fraction(0), Fraction(0)))
            streams[event.contract_key] = (
                billed + after.billed_cum - before.billed_cum,
                credited + after.credited_cum - before.credited_cum,
            )
        steps.setdefault(subject, []).append(LedgerStep(event.order_key, after))
        if event.event_type == "DELIVERY_RECORDED":
            movements.setdefault(subject, []).append((event.source, _required(event, "quantity")))
            net = after.delivered_cum - after.returned_cum
            quantity = booked.get(subject)
            if (
                subject not in changed
                and subject not in right_to_invoice
                and quantity is not None
                and 0 < quantity < net
            ):
                findings.append(
                    _finding(
                        "PROGRESS_OVER_DELIVERY", subject, event, delivered=net, booked=quantity
                    )
                )
        elif event.event_type == "RETURN_RECORDED":
            movements.setdefault(subject, []).append((event.source, -_required(event, "quantity")))
            if after.returned_cum > after.delivered_cum:
                findings.append(
                    _finding(
                        "RETURN_EXCEEDS_DELIVERED",
                        subject,
                        event,
                        returned=after.returned_cum,
                        delivered=after.delivered_cum,
                    )
                )
        elif event.event_type == "CREDIT_MEMO_RECORDED" and subject not in vc_lines:
            # An unreferenced credit memo draws on the whole stream of the contract (S01-R-16 "over
            # the whole stream", S10-R-03; L4-3-Q-11). A referenced one draws first on its
            # obligation's referenced billing, then on the contract's unreferenced billing not yet
            # drawn (D-87 L6-5-Q-15).
            contract = contract_subject_key(event.contract_key)
            billed, credited = (
                streams[event.contract_key]
                if subject == contract
                else (
                    after.billed_cum + referenced_cover(points, contract, subject, vc_lines),
                    after.credited_cum,
                )
            )
            if credited > billed:
                findings.append(
                    _finding(
                        "REFUND_EXCEEDS_BILLED", subject, event, credited=credited, billed=billed
                    )
                )
    ledger = QuantityLedger(
        MappingProxyType({subject: tuple(items) for subject, items in sorted(steps.items())})
    )
    return LedgerBuild(
        ledger=ledger,
        findings=tuple(findings),
        movements=MappingProxyType(
            {subject: tuple(items) for subject, items in sorted(movements.items())}
        ),
    )


def _source(ref: SourceRef, value: Fraction) -> SourceRef:
    return SourceRef(ref.ref_type, ref.ref_id, {"value": format_exact(value)})


def emit_trace(tb: TraceBuilder, built: LedgerBuild, obligations: Iterable[str]) -> None:
    """Version-state nodes ``delivered_quantity_cum`` and ``returned_quantity_cum`` (S01-R-19).

    ``delivered_quantity_cum`` is delivered net of returns: its inputs are the delivery events at
    their quantity and the return events at the negated quantity, so ``ingest.ledger_sum.v1`` is
    the sum of the input values. ``returned_quantity_cum`` sums the return events. The node is
    book-independent; the T-CON-11 column is net only under POL-053 ``RESTORE_REMAINING_QUANTITY``
    and gross delivered otherwise, which the column publish resolves per book (D-87 L5-3-Q-5).
    """
    for subject in sorted(set(obligations)):
        point = built.ledger.at(subject)
        moves = built.movements.get(subject, ())
        tb.node(
            measure="delivered_quantity_cum",
            subject_key=subject,
            period_key=None,
            value=point.delivered_cum - point.returned_cum,
            currency=None,
            minor_unit=None,
            formula_id=FORMULA_ID,
            inputs=[_source(ref, quantity) for ref, quantity in moves],
            narrative_key=NARRATIVE_KEY,
        )
        tb.node(
            measure="returned_quantity_cum",
            subject_key=subject,
            period_key=None,
            value=point.returned_cum,
            currency=None,
            minor_unit=None,
            formula_id=FORMULA_ID,
            inputs=[_source(ref, -quantity) for ref, quantity in moves if quantity < 0],
            narrative_key=NARRATIVE_KEY,
        )
