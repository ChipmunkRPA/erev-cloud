"""Original event-specific estimate allocations for mixed RPO change causes."""

from collections.abc import Mapping
from decimal import Decimal

from erev_engine.trace import SourceRef, Trace

from erev_api.problems import Problem


def allocations(trace: Trace, events: frozenset[str]) -> Mapping[str, Decimal] | None:
    """Return complete reconciled estimate-event shares, or no usable decomposition.

    An explicit measurement-only pin proves no routed allocation change. A missing
    pin or an inception estimate does not prove zero allocation change.
    """
    if not events:
        return None
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise Problem("validation-failed", "RPO allocation trace repeats a node identity.")
    result: dict[str, Decimal] = {}
    for event in sorted(events):
        deltas = [node for node in trace.nodes if node.measure == f"tp_delta@{event}"]
        if not deltas:
            pins = [node for node in trace.nodes if node.measure == f"estimate_pin@{event}"]
            if len(pins) != 1:
                return None
            pin = pins[0]
            if (
                pin.formula_id != "estimate.pin.v1"
                or pin.params.get("allocation_effect") != "MEASUREMENT"
                or len(pin.inputs) != 1
                or not isinstance(pin.inputs[0], SourceRef)
                or pin.inputs[0].ref_type != "estimate_version"
                or pin.inputs[0].ref_id != pin.params.get("v_new")
                or any(node.measure == f"tp_share@{event}" for node in trace.nodes)
            ):
                return None
            continue
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
