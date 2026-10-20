"""Original event-specific estimate allocations for mixed RPO change causes."""

from collections.abc import Mapping
from decimal import Decimal

from erev_engine.trace import Trace

from erev_api.problems import Problem


def allocations(trace: Trace, events: frozenset[str]) -> Mapping[str, Decimal] | None:
    """Return complete reconciled estimate-event shares, or no usable decomposition.

    Measurement-only and inception estimates may have no routed price delta; their
    absence is not proof of a zero allocation change.
    """
    if not events:
        return None
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise Problem("validation-failed", "RPO allocation trace repeats a node identity.")
    result: dict[str, Decimal] = {}
    for event in sorted(events):
        deltas = [node for node in trace.nodes if node.measure == f"tp_delta@{event}"]
        if len(deltas) != 1:
            return None
        delta = deltas[0]
        amount = Decimal(delta.value)
        if not amount.is_finite():
            raise Problem("validation-failed", "RPO estimate delta is not finite.")
        total = Decimal(0)
        subjects: set[str] = set()
        for share in trace.nodes:
            if share.measure != f"tp_share@{event}":
                continue
            parts = share.id.split(":")
            value = Decimal(share.value)
            if (
                len(parts) != 3
                or parts[2] != "-"
                or parts[1] in subjects
                or share.inputs != (delta.id,)
                or share.currency != delta.currency
                or not value.is_finite()
            ):
                raise Problem(
                    "validation-failed", "RPO estimate shares have invalid source evidence."
                )
            subjects.add(parts[1])
            total += value
            result[parts[1]] = result.get(parts[1], Decimal(0)) + value
        if total != amount:
            return None
    return result
