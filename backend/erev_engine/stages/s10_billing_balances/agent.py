"""Stage 10 agent gross relief and supplier share (D-87 L4-3-Q-24; POLICIES JET-02 agent row).

For an agent obligation (S03-R-09 ``gross_to_net``) performed by its contracting entity, at each
stage 09 ``revenue_cum`` period end t (D-87 L4-3-Q-24 (c)):

- G_t = the net billing on the obligation (stage 10 attribution, credit memos included) dated on or
  before its latest JET-02 transfer up to t, 0 before the first transfer;
- relief = max(G_t, R_t), with R_t the stage 09 ``revenue_cum``;
- S_t = max(0, G_t − R_t), the supplier share posted to ``BILLING_CLEARING`` (``AP_SUPPLIER``).

A JET-02 transfer is a measure event that moves a progress measure of the obligation's ledger
(delivered units, costs, hours, output, milestone weight or usage); a period in which
``revenue_cum`` rises without such an event transfers at its end (``CLOSE_RELEASE``). Nodes:
``agent_gross_billing_cum:<ob>:<period>`` (``bil.attribution.v1`` mode ``sum`` over the documents
counted) and, when S_t > 0, ``supplier_share_cum:<ob>:<period>`` (``pos.obligation.v1`` mode
``difference``: G_t − R_t). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.enums import PrincipalAgent
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import classification
from erev_engine.stages.s10_billing_balances.billing import ATTRIBUTION_FORMULA, Billed
from erev_engine.stages.s10_billing_balances.position import series
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    LedgerPoint,
    ObligationState,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "GROSS_MEASURE",
    "RELIEF_MEASURE",
    "SUPPLIER_MEASURE",
    "AgentRelief",
    "is_agent",
    "measure",
    "version_relief",
]

GROSS_MEASURE: Final = "agent_gross_billing_cum"  # G_t
RELIEF_MEASURE: Final = "agent_relief_cum"  # max(G_t, R_t)
SUPPLIER_MEASURE: Final = "supplier_share_cum"  # S_t
_POSITION_FORMULA: Final = "pos.obligation.v1"
_PROGRESS: Final = (
    "delivered_cum",
    "costs_cum",
    "hours_cum",
    "output_ratio",
    "milestone_weight_cum",
    "usage_quantity_cum",
)


@dataclass(frozen=True, slots=True)
class AgentRelief:
    """The agent relief of one book (D-87 L4-3-Q-24 (c))."""

    # agent_relief_cum at every stage 09 period end; supplier_share_cum where S_t > 0
    targets: tuple[Target, ...]
    # subject key -> (period end, S_t, node or None), ascending by end
    supplier: Mapping[str, tuple[tuple[date, int, str | None], ...]]
    transfers: Mapping[str, tuple[date, ...]]  # subject key -> JET-02 transfer dates, ascending


def is_agent(ob: ObligationState) -> bool:
    """An agent obligation with a stage 03 basis, performed by its contracting entity (JET-02)."""
    return (
        ob.principal_agent == PrincipalAgent.AGENT
        and ob.gross_to_net is not None
        and ob.performing_entity == ob.contracting_entity
    )


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def measure(
    ctx: BookContext, recognition: RecognitionState, billed: Billed, tb: TraceBuilder
) -> AgentRelief:
    """Relief max(G_t, R_t) and S_t of every agent obligation at its stage 09 period ends."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    revenue = series(ctx, recognition.revenue_targets)
    targets: list[Target] = []
    supplier: dict[str, tuple[tuple[date, int, str | None], ...]] = {}
    transfers: dict[str, tuple[date, ...]] = {}
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        if not is_agent(ob):
            continue
        items = revenue.get(("revenue_cum", ob.subject_key), ())
        dates = _transfers(st, ob, items)
        transfers[ob.subject_key] = dates
        rows: list[tuple[date, int, str | None]] = []
        for end, target in items:
            transfer = _latest(dates, end)
            gross_id, gross = _gross(ctx, tb, billed, ob, transfer, end, target.period_key, mu)
            if gross <= target.value:
                targets.append(dataclasses.replace(target, measure=RELIEF_MEASURE))
                rows.append((end, 0, None))
                continue
            supplier_id = tb.node(
                measure=SUPPLIER_MEASURE,
                subject_key=ob.subject_key,
                period_key=target.period_key,
                value=gross - target.value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=_POSITION_FORMULA,
                inputs=[gross_id, target.node_id],
                params={"as_of": end.isoformat(), "mode": "difference"},
                narrative_key=_narrative(_POSITION_FORMULA),
            )
            targets.append(
                dataclasses.replace(
                    target, measure=RELIEF_MEASURE, value=gross, exact=None, node_id=gross_id
                )
            )
            targets.append(
                dataclasses.replace(
                    target,
                    measure=SUPPLIER_MEASURE,
                    value=gross - target.value,
                    exact=None,
                    node_id=supplier_id,
                )
            )
            rows.append((end, gross - target.value, supplier_id))
        supplier[ob.subject_key] = tuple(rows)
    return AgentRelief(
        targets=tuple(targets),
        supplier=MappingProxyType(supplier),
        transfers=MappingProxyType(transfers),
    )


def version_relief(
    ctx: BookContext,
    billed: Billed,
    tb: TraceBuilder,
    relief: AgentRelief,
    ob: ObligationState,
    as_of: date,
    revenue: tuple[int, Fraction, str | None],
) -> tuple[int, Fraction, str | None] | None:
    """(relief, exact, node) of an agent obligation at the version date: G at ``as_of`` when it
    exceeds R, else R as given; None for any other obligation (D-87 L4-3-Q-24 (d))."""
    if not is_agent(ob):
        return None
    mu = classification.minor_unit(ctx)
    transfer = _latest(relief.transfers.get(ob.subject_key, ()), as_of)
    gross_id, gross = _gross(ctx, tb, billed, ob, transfer, as_of, None, mu)
    if gross > revenue[0]:
        return gross, Fraction(gross, 10**mu), gross_id
    return revenue


def _transfers(
    st: AllocatedState, ob: ObligationState, items: Sequence[tuple[date, Target]]
) -> tuple[date, ...]:
    """The JET-02 transfer dates of one obligation, ascending."""
    found: set[date] = set()
    previous = LedgerPoint.zero()
    for step in st.ledger.steps.get(ob.subject_key, ()):
        if any(getattr(step.point, name) != getattr(previous, name) for name in _PROGRESS):
            found.add(step.order_key[0])
        previous = step.point
    start: date | None = None
    before = 0
    for end, target in items:
        moved = any((start is None or start < day) and day <= end for day in found)
        if target.value > before and not moved:
            found.add(end)
        start, before = end, target.value
    return tuple(sorted(found))


def _latest(dates: Sequence[date], t: date) -> date | None:
    """The latest transfer on or before ``t``, None before the first."""
    found: date | None = None
    for day in dates:
        if day > t:
            break
        found = day
    return found


def _gross(
    ctx: BookContext,
    tb: TraceBuilder,
    billed: Billed,
    ob: ObligationState,
    transfer: date | None,
    as_of: date,
    period_key: str | None,
    mu: int,
) -> tuple[str, int]:
    """(node, G): the signed attributed billing of the documents dated on or before ``transfer``."""
    inputs: list[str | SourceRef] = []
    total = 0
    if transfer is not None:
        for attribution in billed.attributions:
            document = attribution.document
            if document.effective_date > transfer:
                continue
            amount = attribution.signed().get(ob.subject_key, 0)
            if amount == 0:
                continue
            detail = {"member": "amount", "value": money.format_money(amount, mu)}
            inputs.append(SourceRef("contract_event", document.key, detail))
            total += amount
    params = {"as_of": as_of.isoformat(), "mode": "sum"}
    if transfer is not None:
        params["transfer_date"] = transfer.isoformat()
    node_id = tb.node(
        measure=GROSS_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=total,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=ATTRIBUTION_FORMULA,
        inputs=inputs,
        params=params,
        narrative_key=_narrative(ATTRIBUTION_FORMULA),
    )
    return node_id, total
