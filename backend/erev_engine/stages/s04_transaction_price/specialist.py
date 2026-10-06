"""Stage 04 specialist targets: shared helpers and the assurance-type warranty accrual.

ENGINE_SPEC §4.1 (specialist targets for EMOD-18, EMOD-21, EMOD-22, EMOD-23; Table 0.11-A),
S04-R-19 (JET-16; CHK-134), §4.4 trace node ``warranty_accrual_cum:<ob>:<period>`` and formula
``tp.warranty_accrual.v1``; S01-R-20 (contract terms in force); CV-12 and CV-13 (periods through
the horizon). ``financing``, ``customer_consideration`` and ``noncash`` build their own targets
with these helpers, and ``run`` assembles ``SpecialistTargets``. ``invoices`` reads the S10-R-07
kept lines from the kernel helper ``erev_engine.billing_identity`` (ENGINE_SPEC_B S10-R-07; D-91
C606-05h). Private to stage 04. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import billing_identity, dates
from erev_engine.bundle import PeriodInput
from erev_engine.enums import ScopeFlag
from erev_engine.money import format_exact, round_half_up
from erev_engine.stages.s01_canonicalize import member_in_force, payload_fraction, payload_text
from erev_engine.stages.s03_pob_builder import PobDraft, PobState, WarrantyAccrual
from erev_engine.stages.state import BookContext, EventView, Quota1, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "IN_TP",
    "WARRANTY",
    "WARRANTY_FORMULA",
    "fixed_lines",
    "in_force",
    "invoices",
    "latest_status",
    "periods",
    "stream_end",
    "warranty_accrual_cum",
    "warranty_targets",
]

# S04-R-03: flags whose obligations carry fixed consideration (PT-09 keeps LEASE_842).
IN_TP: Final = frozenset({ScopeFlag.IN_SCOPE_606, ScopeFlag.LEASE_842})
WARRANTY: Final = "warranty_accrual_cum"
WARRANTY_FORMULA: Final = "tp.warranty_accrual.v1"
_BOOKED: Final = "CONTRACT_BOOKED"


def fixed_lines(st: PobState, contract_key: str | None = None) -> tuple[PobDraft, ...]:
    """Obligations carrying fixed consideration (S04-R-03), of one contract when named."""
    return tuple(
        ob
        for ob in st.obligations
        if ob.scope_flag in IN_TP
        and not ob.is_vc_line
        and (contract_key is None or ob.contract_key == contract_key)
    )


def in_force(
    st: PobState, contract_key: str, member: str, at: date, before: EventView | None
) -> tuple[object | None, str | None]:
    """(value, source event key) of a booking payload member in force (S01-R-20).

    The value is the member of the latest ``CONTRACT_BOOKED`` or ``CONTRACT_AMENDED`` payload of
    the contract effective on or before ``at`` and preceding ``before``, else ``None`` (the header
    projection applies). The source is that event, else the contract's booking event.
    """
    events = [
        event
        for event in st.identified.canonical.events
        if before is None or event.order_key < before.order_key
    ]
    value = member_in_force(events, contract_key, member, at)
    source: str | None = None
    for event in events:
        if event.contract_key != contract_key or event.effective_date > at:
            continue
        if value is not None and member in event.payload:
            source = event.event_key
        elif source is None and event.event_type == _BOOKED:
            source = event.event_key
    return value, source


def latest_status(st: PobState, contract_key: str) -> str:
    """The status of the contract's latest segment in the book (``DRAFT`` without one)."""
    segments = st.identified.timelines.get(contract_key, ())
    return segments[-1].status if segments else "DRAFT"


def stream_end(ctx: BookContext, st: PobState) -> date:
    """The latest horizon end date of the book's entities, else the group inception (CV-13)."""
    found = st.inception_date
    for code, key in ctx.horizon.items():
        calendar = ctx.entities.get(code)
        if calendar is None:
            continue
        for period in calendar.periods:
            if period.period_key == key and period.end_date > found:
                found = period.end_date
    return found


def periods(ctx: BookContext, entity: str, start: date) -> tuple[PeriodInput, ...]:
    """The periods of ``entity`` from the one containing ``start`` through the horizon (CV-13).

    A start before the first period begins with the first period; a start after the horizon gives
    no period. An entity absent from the bundle raises ``ValueError`` (CV-12).
    """
    calendar = ctx.entities.get(entity)
    if calendar is None:
        raise ValueError(f"entity {entity} is absent from the bundle (CV-12)")
    horizon_key = ctx.horizon.get(entity)
    if horizon_key is None or not calendar.periods:
        return ()
    horizon = next((p for p in calendar.periods if p.period_key == horizon_key), None)
    if horizon is None:
        raise ValueError(f"horizon period {horizon_key} is absent from the calendar (CV-13)")
    begin = max(start, min(p.start_date for p in calendar.periods))
    if begin > horizon.end_date:
        return ()
    return dates.covering_periods(calendar.periods, begin, horizon.end_date)


def invoices(
    st: PobState, contract_key: str, keys: Sequence[str], since: date, at: date
) -> tuple[tuple[EventView, Fraction], ...]:
    """(event, amount) of the contract's ``BILLING_RECORDED`` lines effective in [since, at].

    The lines are the kernel's S10-R-07 kept lines at contract scope
    (``billing_identity.kept_lines`` over ``st.identified.canonical.events`` for ``contract_key``,
    classified over the whole stream before the window and the obligation filter; D-91 C606-05h):
    the first-seen event of an identity (contract key, ``invoice_number``, ``line_external_id``)
    and every repeat flagged cancellable (D-91 C606-01 (2)); a repeat whose ``is_cancellable`` is
    not true (``false``, ``"false"`` or absent, the 04 default) is a status update and is never an
    invoice here, wherever it falls in the window, and never re-attributes (a mismatch is stage
    10's ``INVOICE_STATUS_UPDATE_MISMATCH``); a line of another contract never counts. A kept line
    counts when its ``obligation_key`` is one of ``keys``, or always when ``keys`` is empty.
    """
    found: list[tuple[EventView, Fraction]] = []
    kept = billing_identity.kept_lines(st.identified.canonical.events, contract_key=contract_key)
    for event in kept:
        if not since <= event.effective_date <= at:
            continue
        if keys and payload_text(event.payload, "obligation_key") not in keys:
            continue
        found.append((event, payload_fraction(event.payload, "amount") or Fraction(0)))
    return tuple(found)


def warranty_accrual_cum(
    ctx: BookContext, st: PobState, accrual: WarrantyAccrual, t: date
) -> tuple[Quota1, Fraction]:
    """S04-R-19: (round(c × units transferred through ``t``), units), with the units of the ledger
    (deliveries less returns). A definition without a cost rate accrues 0 (S03-R-08)."""
    point = st.identified.canonical.ledger.at(accrual.subject_key, on=t)
    units = point.delivered_cum - point.returned_cum
    cost = accrual.assurance_cost_per_unit
    exact = Fraction(0) if cost is None else cost * units
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    return Quota1(exact, round_half_up(exact, minor_unit)), units


def warranty_targets(ctx: BookContext, st: PobState, tb: TraceBuilder) -> tuple[Target, ...]:
    """EMOD-21: ``warranty_accrual_cum`` per accrual definition with a cost rate and period end of
    the performing entity (JET-16 owner), from the group inception through the horizon."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    drafts = {ob.subject_key: ob for ob in st.obligations}
    found: list[Target] = []
    for accrual in st.warranty_accruals:
        ob = drafts.get(accrual.subject_key)
        cost = accrual.assurance_cost_per_unit
        if ob is None or cost is None:
            continue
        entity = ob.performing_entity
        for period in periods(ctx, entity, st.inception_date):
            quota, units = warranty_accrual_cum(ctx, st, accrual, period.end_date)
            point = st.identified.canonical.ledger.at(accrual.subject_key, on=period.end_date)
            inputs: list[str | SourceRef] = []
            if point.last_event_key is not None:
                detail = {"value": format_exact(units)}
                inputs.append(SourceRef("contract_event", point.last_event_key, detail))
            node_id = tb.node(
                measure=WARRANTY,
                subject_key=accrual.subject_key,
                period_key=period.period_key,
                value=quota.posted,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=WARRANTY_FORMULA,
                inputs=inputs,
                params={
                    "cost_per_unit": format_exact(cost),
                    "product_code": accrual.product_code,
                    "units": format_exact(units),
                },
                exact=quota.exact,
                narrative_key=WARRANTY_FORMULA.rsplit(".v", 1)[0],
            )
            found.append(
                Target(
                    book_code=ctx.book_code,
                    entity=entity,
                    subject_key=accrual.subject_key,
                    measure=WARRANTY,
                    period_key=period.period_key,
                    cause=None,
                    value=quota.posted,
                    exact=quota.exact,
                    node_id=node_id,
                )
            )
    return tuple(found)
