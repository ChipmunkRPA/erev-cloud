"""Read original event-position TP changes and per-obligation catch-ups from a verified trace."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.trace import Trace, reevaluate


@dataclass(frozen=True)
class Amounts:
    tp_change: Decimal
    catch_up: dict[str, Decimal]
    node_ids: tuple[str, ...]


def read(
    trace: Trace,
    *,
    event_key: str,
    contract_key: str,
    obligation_keys: Iterable[str],
    currency: str,
) -> Amounts | None:
    """None denotes an older trace without event TP evidence; inconsistent evidence is an error."""
    measure = f"modification_tp_change@{event_key}"
    candidates = [node for node in trace.nodes if node.measure == measure]
    if not candidates:
        return None
    nodes = {node.id: node for node in trace.nodes}
    if len(candidates) != 1 or len(nodes) != len(trace.nodes):
        raise ValueError("Modification event has ambiguous calculation nodes.")
    if dict(reevaluate(trace)) != {node.id: node.value for node in trace.nodes}:
        raise ValueError("Modification calculation trace does not reproduce.")
    tp = candidates[0]
    if tp.currency != currency or tp.formula_id != "rec.activity_sum.v1":
        raise ValueError("Modification event price has another currency or formula.")
    catch_up = {}
    ids = [tp.id]
    for key in obligation_keys:
        node_id = f"catch_up@{event_key}:{obligation_subject_key(contract_key, key)}:-"
        node = nodes.get(node_id)
        if node is None:
            continue  # missing evidence is an empty measure, never a manufactured zero
        if node.currency != currency or node.measure != f"catch_up@{event_key}":
            raise ValueError("Modification catch-up has another currency or event.")
        catch_up[key] = Decimal(node.value)
        ids.append(node.id)
    return Amounts(Decimal(tp.value), catch_up, tuple(ids))
