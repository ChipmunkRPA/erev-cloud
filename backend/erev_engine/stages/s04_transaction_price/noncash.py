"""Stage 04 noncash consideration.

ENGINE_SPEC S04-R-18 (606-10-32-21 to 32-24; ASU 2025-07); §4.4 trace node
``noncash_asset_recognised_cum:<contract>@<entity>:<period>`` and formula ``tp.noncash.v1``;
POLICIES POL-048, JET-17 (CHK-135); 04 API-S-NoncashConsideration. Private to stage 04. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import NoncashInput
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.s04_transaction_price import specialist
from erev_engine.stages.state import BookContext, EventView, Quota1, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA",
    "RECEIVED",
    "RECOGNISED",
    "Item",
    "Noncash",
    "emit",
    "measure",
    "recognised",
    "targets",
]

FORMULA: Final = "tp.noncash.v1"
POLICY: Final = "noncash.measurement_date"  # POL-048
MEMBER: Final = "noncash_consideration"
RECOGNISED: Final = "noncash_asset_recognised_cum"
RECEIVED: Final = "noncash_received_cum"  # carrying amount of noncash receipts (JET-17 receipt)
ZERO: Final = Fraction(0)


@dataclass(frozen=True, slots=True)
class Item:
    """One noncash promise of the list in force (API-S-NoncashConsideration)."""

    contract_key: str
    index: int  # position in the list in force
    units: Fraction
    fair_value_per_unit: Fraction  # at ``measurement_date``
    measurement_date: date
    variability: str  # FORM | PERFORMANCE (606-10-32-23)
    asset_type: str | None
    posted: int  # round(units × fair value), minor units
    source_event_key: str | None


@dataclass(frozen=True, slots=True)
class Noncash:
    """The noncash member at a position (S04-R-18)."""

    items: tuple[Item, ...]
    exact: Fraction  # Σ round(units × fair value), currency units
    policies: Mapping[str, str]  # contract key -> resolved POL-048 literal


def measure(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    *,
    contract_key: str | None = None,
) -> Noncash:
    """S04-R-18: ``noncash`` = Σ round(units × fair value per unit) of the list in force.

    The list is the ``noncash_consideration`` member of the latest booking or amendment payload
    carrying it, else the header projection (S01-R-20). Each item carries the fair value at its
    POL-048 measurement date (contract inception in the ASC606 book, FORCED); the engine holds no
    other price source, so the resolved literal is recorded, not re-measured (L2-2-Q-25).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    found: list[Item] = []
    policies: dict[str, str] = {}
    for key in st.identified.member_contract_keys:
        if contract_key is not None and key != contract_key:
            continue
        header = st.identified.canonical.contracts[key].header
        value, source = specialist.in_force(st, key, MEMBER, at, before)
        items: Sequence[object]
        if value is None:
            items = header.noncash_consideration
        elif isinstance(value, list | tuple):
            items = value
        else:
            raise ValueError(f"{key}: noncash_consideration is not a list (CV-45)")
        listed = [_item(key, index, item, source, minor_unit) for index, item in enumerate(items)]
        if listed:
            entity = header.contracting_entity_code
            policies[key] = str(ctx.policies.value(POLICY, contract=key, entity=entity))
        found.extend(listed)
    exact = sum((Fraction(item.posted, scale) for item in found), ZERO)
    return Noncash(tuple(found), exact, MappingProxyType(policies))


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject_key: str,
    quota: Quota1,
    item: Noncash,
) -> str:
    """Node ``noncash_consideration_amount`` (§4.4; ``tp.noncash.v1``); its id."""
    listed = item.items
    inputs: list[str | SourceRef] = [
        _source(entry, entry.units * entry.fair_value_per_unit) for entry in listed
    ]
    params = {
        "fair_values": ",".join(format_exact(entry.fair_value_per_unit) for entry in listed),
        "measurement_dates": ",".join(entry.measurement_date.isoformat() for entry in listed),
        "policies": ",".join(item.policies[entry.contract_key] for entry in listed),
        "signs": ",".join("+" for _ in listed),
        "units": ",".join(format_exact(entry.units) for entry in listed),
        "variability": ",".join(entry.variability for entry in listed),
    }
    return tb.node(
        measure=measure_name,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=FORMULA,
        inputs=inputs,
        params=params,
        exact=quota.exact,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )


def recognised(
    ctx: BookContext, st: PobState, contract_key: str, t: date
) -> tuple[Quota1, Fraction, tuple[Item, ...]]:
    """S04-R-18 target at ``t``: (round(fair value × units whose right is unconditional), the
    completed ratio, the items in force).

    The unconditional units are units × the increments completed: Σ delivered units ÷ Σ quantity of
    the contract's fixed-consideration obligations, at most 1 (L2-2-Q-26).
    """
    items = measure(ctx, st, t, None, contract_key=contract_key).items
    lines = specialist.fixed_lines(st, contract_key)
    ledger = st.identified.canonical.ledger
    quantity = sum((ob.quantity for ob in lines), ZERO)
    delivered = sum((ledger.at(ob.subject_key, on=t).delivered_cum for ob in lines), ZERO)
    completed = ZERO if quantity == 0 else min(Fraction(1), delivered / quantity)
    exact = sum((entry.units * entry.fair_value_per_unit * completed for entry in items), ZERO)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    return Quota1(exact, round_half_up(exact, minor_unit)), completed, items


def targets(ctx: BookContext, st: PobState, tb: TraceBuilder) -> tuple[Target, ...]:
    """EMOD-23: ``noncash_asset_recognised_cum`` per contract with noncash consideration and period
    end of the contracting entity (JET-17 owner), from the contract inception through the
    horizon."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    end = specialist.stream_end(ctx, st)
    found: list[Target] = []
    for contract_key in st.identified.member_contract_keys:
        if not measure(ctx, st, end, None, contract_key=contract_key).items:
            continue
        header = st.identified.canonical.contracts[contract_key].header
        entity = header.contracting_entity_code
        subject = contract_entity_subject_key(contract_key, entity)
        for period in specialist.periods(ctx, entity, header.inception_date):
            quota, completed, items = recognised(ctx, st, contract_key, period.end_date)
            node_id = tb.node(
                measure=RECOGNISED,
                subject_key=subject,
                period_key=period.period_key,
                value=quota.posted,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=FORMULA,
                inputs=[_source(entry, entry.units * entry.fair_value_per_unit) for entry in items],
                params={"completed": format_exact(completed)},
                exact=quota.exact,
                narrative_key=FORMULA.rsplit(".v", 1)[0],
            )
            found.append(
                Target(
                    book_code=ctx.book_code,
                    entity=entity,
                    subject_key=subject,
                    measure=RECOGNISED,
                    period_key=period.period_key,
                    cause=None,
                    value=quota.posted,
                    exact=quota.exact,
                    node_id=node_id,
                )
            )
            receipts = _received(st, contract_key, period.end_date)
            carrying = sum((round_half_up(amount, minor_unit) for _, amount in receipts), 0)
            received_id = tb.node(
                measure=RECEIVED,
                subject_key=subject,
                period_key=period.period_key,
                value=carrying,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=FORMULA,
                inputs=[
                    SourceRef("contract_event", event.event_key, {"value": format_exact(amount)})
                    for event, amount in receipts
                ],
                params={},
                narrative_key=FORMULA.rsplit(".v", 1)[0],
            )
            found.append(
                Target(
                    book_code=ctx.book_code,
                    entity=entity,
                    subject_key=subject,
                    measure=RECEIVED,
                    period_key=period.period_key,
                    cause=None,
                    value=carrying,
                    exact=None,
                    node_id=received_id,
                )
            )
    return tuple(found)


def _received(st: PobState, contract_key: str, t: date) -> tuple[tuple[EventView, Fraction], ...]:
    """The carrying amount of each noncash receipt of the contract dated on or before ``t``: 04
    §16.3 ``PAYMENT_RECEIVED`` with ``form = NONCASH``, whose ``amount`` is the carrying amount of
    the units received (JET-17 receipt; lane L5-5)."""
    return tuple(
        (event, payload_fraction(event.payload, "amount") or ZERO)
        for event in st.identified.canonical.measure_events
        if event.event_type == "PAYMENT_RECEIVED"
        and event.contract_key == contract_key
        and event.effective_date <= t
        and payload_text(event.payload, "form") == "NONCASH"
    )


def _item(contract_key: str, index: int, item: object, source: str | None, minor_unit: int) -> Item:
    if isinstance(item, NoncashInput):
        units = to_fraction(item.units)
        fair = to_fraction(item.fair_value_per_unit)
        on = item.measurement_date
        variability = item.variability
        asset_type = item.asset_type
    elif isinstance(item, Mapping):
        found_units = payload_fraction(item, "units")
        found_fair = payload_fraction(item, "fair_value_per_unit")
        found_on = payload_date(item, "measurement_date")
        found_variability = payload_text(item, "variability")
        if found_units is None or found_fair is None or found_on is None:
            raise ValueError(f"{contract_key}: a noncash item needs units, fair value and date")
        units, fair, on = found_units, found_fair, found_on
        variability = found_variability or "FORM"
        asset_type = payload_text(item, "asset_type")
    else:
        raise ValueError(f"{contract_key}: a noncash item is not an object (CV-45)")
    posted = round_half_up(units * fair, minor_unit)
    return Item(contract_key, index, units, fair, on, variability, asset_type, posted, source)


def _source(entry: Item, value: Fraction) -> SourceRef:
    detail = {"line": str(entry.index), "value": format_exact(value)}
    return SourceRef("contract_event", entry.source_event_key or entry.contract_key, detail)
