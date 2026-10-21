"""Original event-date realized allocations for RPO lifecycle boundaries."""

from datetime import date
from decimal import Decimal, InvalidOperation

from erev_engine.trace import Trace

from erev_api.problems import Problem


def history(trace: Trace) -> dict[str, dict[date, Decimal]]:
    result: dict[str, dict[date, Decimal]] = {}
    for node in trace.nodes:
        if node.measure != "realised_allocation_at_date":
            continue
        try:
            measure, subject, slot = node.id.split(":")
            day = date.fromisoformat(node.params["as_of"])
            value = Decimal(node.value)
            expected = Decimal(node.params["allocated"]) / (
                Decimal(10) ** int(node.params["minor_unit"])
            )
            if (
                measure != node.measure
                or slot != day.isoformat()
                or node.formula_id != "rec.realised_allocation.v1"
                or not value.is_finite()
                or value != expected
                or day in result.get(subject, {})
            ):
                raise ValueError("Inconsistent realized boundary")
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise Problem(
                "validation-failed", "Invalid original realized-allocation date evidence."
            ) from exc
        result.setdefault(subject, {})[day] = value
    return result
