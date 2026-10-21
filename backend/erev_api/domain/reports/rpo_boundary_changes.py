"""Dated fixed allocation movements measured by the original modification engine."""

from collections.abc import Mapping
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
    created: bool = False
    record_seq: int | None = None
    before: Decimal | None = None
    after: Decimal | None = None
    cancelled_on: date | None = None
    prior_end: date | None = None


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
            created = before.params.get("present") == "false"
            sequence = node.params.get("record_seq")
            record_seq = None if sequence is None else int(sequence)
            if created and (values[1] != 0 or record_seq is None):
                raise ValueError("Creation must have an absent zero before-state and event order")
            if record_seq is not None and record_seq < 1:
                raise ValueError("Invalid event sequence")
            change = Change(
                date.fromisoformat(node.params["as_of"]),
                event,
                node.params["event_type"],
                values[0],
                created,
                record_seq,
                values[1],
                values[2],
                date.fromisoformat(after.params["cancelled_on"])
                if after.params.get("cancelled_on")
                else None,
                date.fromisoformat(before.params["end_date"])
                if before.params.get("end_date")
                else None,
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


def complete(
    boundaries: Mapping[str, tuple[Change, ...]], subject: str, events: frozenset[str]
) -> bool:
    """Require every boundary since original creation; absence before creation is evidenced.

    A zero allocation alone never proves absence. Earlier missing subject boundaries are
    accepted only when the engine explicitly retained its creation and the missing event's
    order is independently present on another obligation from that same computation.
    """
    changes = boundaries.get(subject, ())
    missing = events - {item.event for item in changes}
    if not events:
        return False
    if not missing:
        return True
    created = [item for item in changes if item.created and item.record_seq is not None]
    if len(created) != 1:
        return False
    first = created[0]
    assert first.record_seq is not None
    creation_order = (first.day, first.record_seq, first.event)
    order: dict[str, tuple[date, int, str]] = {}
    for items in boundaries.values():
        for item in items:
            if item.record_seq is None:
                continue
            key = (item.day, item.record_seq, item.event)
            if item.event in order and order[item.event] != key:
                raise Problem("validation-failed", "RPO boundary event order is inconsistent.")
            order[item.event] = key
    return all(event in order and order[event] < creation_order for event in missing)


def cancellation(changes: tuple[Change, ...]) -> Change | None:
    found = [
        item
        for item in changes
        if item.kind == "CONTRACT_TERMINATED" and item.cancelled_on == item.day
    ]
    return found[0] if len(found) == 1 else None
