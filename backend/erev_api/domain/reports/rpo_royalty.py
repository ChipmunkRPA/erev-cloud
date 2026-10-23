"""Original royalty amounts still awaiting recognition; fixed guarantees are not included."""

from datetime import date
from decimal import Decimal

from erev_engine.trace import Trace

from erev_api.problems import Problem


def history(trace: Trace) -> dict[str, dict[date, Decimal]]:
    result: dict[str, dict[date, Decimal]] = {}
    for node in trace.nodes:
        if node.measure != "royalty_remaining_at_date":
            continue
        try:
            _, subject, slot = node.id.split(":")
            day = date.fromisoformat(node.params["as_of"])
            value = Decimal(node.value)
            expected = Decimal(node.params["allocated"]).scaleb(-int(node.params["minor_unit"]))
            if (
                slot != day.isoformat()
                or node.formula_id != "rec.realised_allocation.v1"
                or not value.is_finite()
                or value < 0
                or value != expected
                or day in result.get(subject, {})
            ):
                raise ValueError("inconsistent royalty remainder")
        except (KeyError, ValueError, ArithmeticError) as error:
            raise Problem(
                "validation-failed", "Original royalty exemption evidence is inconsistent."
            ) from error
        result.setdefault(subject, {})[day] = value
        if node.params.get("royalty_bearing") == "false":
            if value != 0:
                raise Problem(
                    "validation-failed", "A non-royalty obligation has royalty remainder."
                )
            result[subject][date.min] = Decimal(0)
    return result


def cap(points: dict[date, Decimal], day: date) -> Decimal:
    if date.min in points:
        return Decimal(0)
    if day not in points:
        raise Problem(
            "validation-failed",
            "Original royalty remainder is unavailable at the RPO date; recompute the contract.",
        )
    return points[day]
