"""Boundary version-state nodes of the T-CON-11 columns a modification re-measures (D-97 (8),
supervisor ruling T1F-Q-3 (c); ENGINE_SPEC CV-50 links; dev-guide DG-KRN-EXP-01; lane ENG-T1F).

``stated_price@<event key>:<ob>:-`` (``mod.stated_price.v1``): the obligation's stated price after
the boundary: the previous stated-price node (params ``previous`` when no node holds the prior
price) plus the boundary's posted consideration change, cited as a ``SourceRef`` of the event.
``allocation_adjustment@<event key>:<ob>:-`` (``mod.allocation_adjustment.v1``): the allocation of
the FIXED segment in force after the boundary less the stated price after it (T-CON-11
``allocation_adjustment`` = ``allocated_amount`` − ``stated_price``), citing the boundary's
allocation node when one exists and the stated-price node. Emitted for every obligation whose
stated price or allocation the boundary changed, and for every obligation the boundary adds. The
inception nodes (stage 03 ``stated_price:<ob>:-``, stage 05 ``allocation_adjustment:<ob>:-``) keep
their ids and values; the assembler links the LAST boundary node, never the inception node when the
two differ. Private to stage 06 (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Final

from erev_engine.money import format_exact, round_half_up
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["ADJUSTMENT_FORMULA", "STATED_FORMULA", "emit"]

STATED_FORMULA: Final = "mod.stated_price.v1"
ADJUSTMENT_FORMULA: Final = "mod.allocation_adjustment.v1"
FIXED: Final = "FIXED"


def _fixed(ob: ObligationState) -> AllocationSegment | None:
    found = None
    for segment in ob.segments:
        if segment.component == FIXED:
            found = segment
    return found


def _previous_stated_node(
    tb: TraceBuilder, before: AllocatedState, ob: ObligationState
) -> str | None:
    """The latest stated-price node of ``ob`` before this boundary: a ``stated_price@<event>``
    node of an earlier boundary, else the stage 03 inception node."""
    for event in sorted(before.events, key=lambda item: item.order_key, reverse=True):
        node_id = f"stated_price@{event.event_key}:{ob.subject_key}:-"
        if tb.value(node_id) is not None:
            return node_id
    inception = f"stated_price:{ob.subject_key}:-"
    return inception if tb.value(inception) is not None else None


def _allocation_change(
    ctx: BookContext,
    tb: TraceBuilder,
    old: ObligationState | None,
    ob: ObligationState,
    ev: EventView,
) -> None:
    """Retain the exact fixed allocation before/after this boundary, including zero changes.

    These are engine states, not a report-side allocation of the contract price change.
    Separate dated events remain distinguishable even in the first computation.
    """
    unit = ctx.currencies[ctx.txn_currency].minor_unit
    amounts = []
    inputs = []
    for side, item in (("before", old), ("after", ob)):
        segment = None if item is None else _fixed(item)
        amount = 0 if segment is None else segment.a_posted
        amounts.append(amount)
        lineage = []
        if segment is not None and item is not None:
            if segment.event_key is not None:
                candidate = f"allocated_amount@{segment.event_key}:{ob.subject_key}:-"
                if tb.value(candidate) is not None:
                    lineage.append(candidate)
            else:
                lineage.extend(
                    key for key in item.original_allocation_nodes if tb.value(key) is not None
                )
        inputs.append(
            tb.node(
                measure=f"fixed_boundary_{side}@{ev.event_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=amount,
                currency=ctx.txn_currency,
                minor_unit=unit,
                formula_id="rec.allocation.v1",
                inputs=lineage,
                params={
                    "allocated": str(amount),
                    "as_of": ev.effective_date.isoformat(),
                    "kind": "posted",
                    "present": "false" if item is None else "true",
                    "cancelled_on": ""
                    if item is None or item.terminated_on is None
                    else item.terminated_on.isoformat(),
                    "end_date": ""
                    if item is None or item.end_date is None
                    else item.end_date.isoformat(),
                },
                exact=Fraction(amount, 10**unit),
                narrative_key="rec.allocation",
            )
        )
    tb.node(
        measure=f"fixed_boundary_change@{ev.event_key}",
        subject_key=ob.subject_key,
        period_key=None,
        value=amounts[1] - amounts[0],
        currency=ctx.txn_currency,
        minor_unit=unit,
        formula_id="rec.activity_sum.v1",
        inputs=[inputs[1], inputs[0]],
        params={
            "signs": "+,-",
            "as_of": ev.effective_date.isoformat(),
            "event_type": ev.event_type,
            "record_seq": str(ev.record_seq),
        },
        exact=Fraction(amounts[1] - amounts[0], 10**unit),
        narrative_key="rec.activity_sum",
    )


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    before: AllocatedState,
    after: AllocatedState,
    ev: EventView,
) -> None:
    """The boundary nodes of ``ev`` for every obligation it re-measured or added (see module)."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    prior = {ob.subject_key: ob for ob in before.obligations}
    for ob in after.obligations:
        old = prior.get(ob.subject_key)
        _allocation_change(ctx, tb, old, ob, ev)
        fixed = _fixed(ob)
        old_fixed = None if old is None else _fixed(old)
        stated_changed = old is None or ob.stated_price != old.stated_price
        allocation_changed = (
            old is None
            or old_fixed is None
            or fixed is None
            or fixed.a_posted != old_fixed.a_posted
            or fixed.event_key == ev.event_key
        )
        if not stated_changed and not allocation_changed:
            continue
        stated_node = _previous_stated_node(tb, before, ob)
        posted_stated = round_half_up(ob.stated_price, minor_unit)
        if stated_changed:
            node_id = f"stated_price@{ev.event_key}:{ob.subject_key}:-"
            if tb.value(node_id) is None:
                previous_exact = Fraction(0) if old is None else old.stated_price
                previous_posted = round_half_up(previous_exact, minor_unit)
                # The cited change is the POSTED change, so the posted node re-evaluates exactly
                # from the previous posted price (DG-KRN-EXP-04); the exact residue is the node's.
                change = Fraction(posted_stated - previous_posted, 10**minor_unit)
                inputs: list[str | SourceRef] = [] if stated_node is None else [stated_node]
                inputs.append(
                    SourceRef(
                        "contract_event",
                        ev.event_key,
                        {"role": "consideration_change", "value": format_exact(change)},
                    )
                )
                params = {"as_of": ev.effective_date.isoformat()}
                if stated_node is None:
                    params["previous"] = str(previous_posted)  # no node holds the prior price
                stated_node = tb.node(
                    measure=f"stated_price@{ev.event_key}",
                    subject_key=ob.subject_key,
                    period_key=None,
                    value=posted_stated,
                    currency=ctx.txn_currency,
                    minor_unit=minor_unit,
                    formula_id=STATED_FORMULA,
                    inputs=inputs,
                    params=params,
                    exact=ob.stated_price,
                    narrative_key=STATED_FORMULA.rsplit(".v", 1)[0],
                )
        if fixed is None:
            continue
        node_id = f"allocation_adjustment@{ev.event_key}:{ob.subject_key}:-"
        if tb.value(node_id) is not None:
            continue
        allocation_node = f"allocated_amount@{ev.event_key}:{ob.subject_key}:-"
        lineage: list[str | SourceRef] = []
        params = {"as_of": ev.effective_date.isoformat()}
        if tb.value(allocation_node) is not None:
            lineage.append(allocation_node)
        else:
            params["allocated"] = str(fixed.a_posted)
        if stated_node is not None:
            lineage.append(stated_node)
        else:
            params["stated_price"] = str(posted_stated)
        tb.node(
            measure=f"allocation_adjustment@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=fixed.a_posted - posted_stated,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=ADJUSTMENT_FORMULA,
            inputs=lineage,
            params=params,
            exact=fixed.x_exact - ob.stated_price,
            narrative_key=ADJUSTMENT_FORMULA.rsplit(".v", 1)[0],
        )


def emit_price_change(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    group: str,
    before: TpBuildUp,
    after: TpBuildUp,
) -> None:
    """Retain the TP change at this event position, not a computation-wide version delta."""
    minor = ctx.currencies[ctx.txn_currency].minor_unit
    inputs = []
    for side, price in (("before", before), ("after", after)):
        inputs.append(
            tb.node(
                measure=f"modification_tp_{side}@{ev.event_key}",
                subject_key=group,
                period_key=None,
                value=price.total.posted,
                currency=ctx.txn_currency,
                minor_unit=minor,
                formula_id="rec.allocation.v1",
                inputs=[],
                params={
                    "allocated": str(price.total.posted),
                    "as_of": ev.effective_date.isoformat(),
                    "kind": "posted",
                },
                exact=price.total.exact,
                narrative_key="rec.allocation",
            )
        )
    tb.node(
        measure=f"modification_tp_change@{ev.event_key}",
        subject_key=group,
        period_key=None,
        value=after.total.posted - before.total.posted,
        currency=ctx.txn_currency,
        minor_unit=minor,
        formula_id="rec.activity_sum.v1",
        inputs=[inputs[1], inputs[0]],
        params={"signs": "+,-", "as_of": ev.effective_date.isoformat()},
        exact=after.total.exact - before.total.exact,
        narrative_key="rec.activity_sum",
    )
