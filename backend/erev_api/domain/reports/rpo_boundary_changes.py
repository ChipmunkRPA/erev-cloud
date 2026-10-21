"""Dated fixed allocation movements measured by the original modification engine."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from erev_engine.trace import Trace

from erev_api.problems import Problem


@dataclass(frozen=True, slots=True)
class Change:
    day: date
    event: str
    kind: str
    amount: Decimal


def history(trace: Trace) -> dict[str, tuple[Change, ...]]:
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise Problem("validation-failed", "RPO boundary trace repeats a node identity.")
    found: dict[str, list[Change]] = {}
    for node in trace.nodes:
        if not node.measure.startswith("fixed_boundary_change@"):
            continue
        try:
            prefix, subject, period = node.id.split(":")
            event = prefix.removeprefix("fixed_boundary_change@")
            after = nodes[f"fixed_boundary_after@{event}:{subject}:-"]
            before = nodes[f"fixed_boundary_before@{event}:{subject}:-"]
            values = [Decimal(item.value) for item in (node, before, after)]
            if (
                prefix != node.measure
                or period != "-"
                or node.formula_id != "rec.activity_sum.v1"
                or node.inputs != (after.id, before.id)
                or node.params.get("signs") != "+,-"
                or any(item.formula_id != "rec.allocation.v1" for item in (before, after))
                or any(item.currency != node.currency for item in (before, after))
                or any(item.params.get("as_of") != node.params["as_of"] for item in (before, after))
                or any(not value.is_finite() for value in values)
                or values[0] != values[2] - values[1]
            ):
                raise ValueError("Inconsistent boundary evidence")
            change = Change(
                date.fromisoformat(node.params["as_of"]),
                event,
                node.params["event_type"],
                values[0],
            )
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise Problem(
                "validation-failed", "RPO boundary allocation evidence is invalid."
            ) from exc
        found.setdefault(subject, []).append(change)
    return {
        subject: tuple(sorted(changes, key=lambda item: (item.day, item.event)))
        for subject, changes in found.items()
    }
