"""Validated original event-position evidence for ordered RPO boundaries."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from erev_engine.trace import SourceRef, Trace

from erev_api.problems import Problem


@dataclass(frozen=True)
class Point:
    day: date
    record_seq: int
    event_type: str
    fixed: Decimal
    realised: Decimal
    revenue: Decimal


def history(trace: Trace) -> dict[str, dict[tuple[str, str], Point]]:
    """Return complete triples only; malformed/partial original evidence is unreadable."""
    members: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    metadata: dict[tuple[str, str, str], tuple[date, int, str]] = {}
    try:
        for node in trace.nodes:
            if not node.measure.startswith("rpo_position_"):
                continue
            event, side = node.params["event_key"], node.params["side"]
            member = node.measure.removeprefix("rpo_position_").split("@", 1)[0]
            measure, subject, slot = node.id.split(":")
            key = subject, event, side
            meta = (
                date.fromisoformat(node.params["as_of"]),
                int(node.params["record_seq"]),
                node.params["event_type"],
            )
            value = Decimal(node.value)
            role = f"rpo_position_{member}_{side}"
            source = node.inputs[0] if len(node.inputs) == 1 else None
            if (
                member not in {"fixed", "realised", "revenue"}
                or side not in {"before", "after"}
                or measure != node.measure
                or measure != f"rpo_position_{member}@{event}@{side}"
                or slot != "-"
                or node.formula_id != "rec.activity_sum.v1"
                or node.params["role"] != role
                or not value.is_finite()
                or not isinstance(source, SourceRef)
                or source.ref_type != "contract_event"
                or source.ref_id != event
                or source.detail.get("role") != role
                or Decimal(source.detail["value"]) != value
                or member in members.get(key, {})
                or metadata.get(key, meta) != meta
            ):
                raise ValueError("Inconsistent original event position")
            members.setdefault(key, {})[member] = value
            metadata[key] = meta
        result: dict[str, dict[tuple[str, str], Point]] = {}
        for (subject, event, side), amounts in members.items():
            if set(amounts) != {"fixed", "realised", "revenue"}:
                raise ValueError("Incomplete original event position")
            day, seq, kind = metadata[subject, event, side]
            result.setdefault(subject, {})[event, side] = Point(
                day, seq, kind, amounts["fixed"], amounts["realised"], amounts["revenue"]
            )
        return result
    except (KeyError, ValueError, InvalidOperation) as exc:
        raise Problem("validation-failed", "Invalid original RPO event-position evidence.") from exc
