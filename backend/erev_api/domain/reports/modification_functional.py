"""Original functional catch-ups when one event owns the complete recognition-period flow.

This is a calculation amount, not a posting delta or a spot equivalent. Mixed event/normal
periods require finer native evidence and remain unavailable, even if their net totals match.
"""

from dataclasses import dataclass
from decimal import Decimal

from erev_engine.trace import Trace

from . import functional_revenue_activity


@dataclass(frozen=True)
class FunctionalCatchUp:
    amount: Decimal
    currency: str
    period_key: str
    node_ids: tuple[str, ...]


def read(
    trace: Trace,
    *,
    event_key: str,
    subject: str,
    entity: str,
    transaction_currency: str,
    functional_currency: str,
) -> FunctionalCatchUp | None:
    """Require an exclusive original cause, not merely equality with a period's net change."""
    nodes = {node.id: node for node in trace.nodes}
    event_id = f"catch_up@{event_key}:{subject}:-"
    event = nodes.get(event_id)
    if event is None:
        return None
    prefix = f"revenue_by_cause:{subject}/MODIFICATION:"
    candidates = [
        node for node in trace.nodes if node.id.startswith(prefix) and event_id in node.inputs
    ]
    if len(candidates) != 1:
        return None
    cause = candidates[0]
    period = cause.id.removeprefix(prefix)
    if cause.inputs != (event_id,):
        return None
    if any(
        node.id.startswith(f"revenue_by_cause:{subject}/")
        and node.id.endswith(":" + period)
        and node.id != cause.id
        for node in trace.nodes
    ):
        return None
    if (
        event.currency != transaction_currency
        or cause.currency != transaction_currency
        or cause.formula_id != "rec.decompose.sequential.v1"
        or cause.params.get("cause") != "MODIFICATION"
        or Decimal(cause.value) != Decimal(event.value)
    ):
        raise ValueError("Modification functional cause differs from its original event.")
    # Missing historical activity is unavailable, rather than a synthetic zero/spot amount.
    if not any(
        node.measure == "revenue_activity_functional"
        and node.params.get("obligation_subject") == subject
        and node.id.endswith(":" + period)
        for node in trace.nodes
    ):
        return None
    activities = functional_revenue_activity.read(
        trace,
        obligation_subject=subject,
        entity_code=entity,
        period_key=period,
        transaction_currency=transaction_currency,
        functional_currency=functional_currency,
    )
    # Agent gross relief and calendar-projected targets are not this event's net revenue.
    if any(
        item.recognition_source_node != f"revenue_cum:{subject}:{period}" for item in activities
    ):
        return None
    if sum((item.transaction_amount for item in activities), Decimal(0)) != Decimal(event.value):
        return None
    return FunctionalCatchUp(
        sum((item.functional_amount for item in activities), Decimal(0)),
        functional_currency,
        period,
        tuple(sorted({event.id, cause.id, *(item.node_id for item in activities)})),
    )
