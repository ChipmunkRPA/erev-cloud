"""Verify actual functional revenue flows before assigning them to report causes.

This reads a caller-verified stored trace. It proves the selected period's complete flow
population against its cumulative revenue target; it does not identify modification events
inside a period-aggregated source or treat a single-rate equivalent as posted revenue.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.trace import Trace, TraceNode, reevaluate


class RevenueActivityUnavailable(ValueError):
    """Missing or inconsistent original functional activity prevents attribution."""


@dataclass(frozen=True, slots=True)
class Activity:
    node_id: str
    source_key: str
    entity_code: str
    obligation_subject: str
    effective_date: date
    kind: str
    transaction_currency: str
    transaction_amount: Decimal
    functional_currency: str
    functional_amount: Decimal
    signed_piece_ids: tuple[tuple[str, int], ...]
    recognition_source_node: str | None = None


def _pieces(node: TraceNode) -> tuple[tuple[str, int], ...]:
    signs = node.params.get("signs", "").split("|") if node.inputs else []
    if node.formula_id != "fx.revenue_functional.v1" or len(signs) != len(node.inputs):
        raise RevenueActivityUnavailable("Revenue activity lacks its signed functional inputs.")
    if any(sign not in {"1", "-1"} for sign in signs) or any(
        not isinstance(value, str) for value in node.inputs
    ):
        raise RevenueActivityUnavailable("Revenue activity has unsupported functional inputs.")
    return tuple((str(value), int(sign)) for value, sign in zip(node.inputs, signs, strict=True))


def _transaction(node: TraceNode, currency: str) -> Decimal:
    if (
        node.params["txn_currency"] != currency
        or int(node.params["txn_minor_unit"]) != ISO_4217[currency].minor_unit
    ):
        raise RevenueActivityUnavailable("Revenue activity transaction currency differs.")
    return Decimal(int(node.params["amount_txn"])).scaleb(-ISO_4217[currency].minor_unit)


def read(
    trace: Trace,
    *,
    obligation_subject: str,
    entity_code: str,
    period_key: str,
    transaction_currency: str,
    functional_currency: str,
) -> tuple[Activity, ...]:
    """Return original flows only when both money totals and exact source multiplicities agree."""
    try:
        return _read(
            trace,
            obligation_subject,
            entity_code,
            period_key,
            transaction_currency,
            functional_currency,
        )
    except RevenueActivityUnavailable:
        raise
    except (KeyError, ValueError, ArithmeticError, EngineError) as error:
        raise RevenueActivityUnavailable(
            "Functional revenue activity cannot be reconstructed."
        ) from error


def _read(
    trace: Trace, subject: str, entity: str, period: str, txn: str, functional: str
) -> tuple[Activity, ...]:
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes) or dict(reevaluate(trace)) != {
        node.id: node.value for node in trace.nodes
    }:
        raise RevenueActivityUnavailable("Revenue calculation trace does not reproduce.")
    target = nodes[f"revenue_functional:{subject}:{period}"]
    if target.currency != functional:
        raise RevenueActivityUnavailable("Revenue target functional currency differs.")
    expected = Counter(_pieces(target))
    previous = [
        (node_id, sign)
        for node_id, sign in expected
        if nodes[node_id].measure == "revenue_functional"
    ]
    if len(previous) > 1:
        raise RevenueActivityUnavailable("Revenue target has ambiguous prior cumulative inputs.")
    before_txn = before_functional = Decimal(0)
    if previous:
        node_id, sign = previous[0]
        prior = nodes[node_id]
        if (
            sign != 1
            or expected[(node_id, sign)] != 1
            or prior.currency != functional
            or not node_id.startswith(f"revenue_functional:{subject}:")
        ):
            raise RevenueActivityUnavailable("Revenue target has another prior cumulative scope.")
        before_txn, before_functional = _transaction(prior, txn), Decimal(prior.value)
        del expected[(node_id, sign)]
    found = []
    actual: Counter[tuple[str, int]] = Counter()
    for node in trace.nodes:
        if (
            node.measure != "revenue_activity_functional"
            or node.params.get("obligation_subject") != subject
            or not node.id.endswith(":" + period)
        ):
            continue
        params = node.params
        kind, source = params["flow_kind"], params["source_key"]
        if (
            kind not in {"REVENUE", "NEGATIVE_REVENUE"}
            or node.currency != functional
            or params["entity"] != entity
            or node.id != f"revenue_activity_functional:{source}#{kind}@{subject}:{period}"
        ):
            raise RevenueActivityUnavailable("Revenue activity identity or currency differs.")
        amount = _transaction(node, txn)
        sign = 1 if kind == "REVENUE" else -1
        pieces = _pieces(node)
        if sign * amount <= 0 or any(piece_sign != sign for _, piece_sign in pieces):
            raise RevenueActivityUnavailable("Revenue activity direction differs from its inputs.")
        if any(nodes[node_id].currency != functional for node_id, _ in pieces):
            raise RevenueActivityUnavailable("Revenue activity piece currency differs.")
        recognition_source = params.get("recognition_source_node")
        if recognition_source is not None and nodes[recognition_source].currency != txn:
            raise RevenueActivityUnavailable("Recognition source transaction currency differs.")
        actual.update(pieces)
        found.append(
            Activity(
                node.id,
                source,
                params["entity"],
                subject,
                date.fromisoformat(params["effective_date"]),
                kind,
                txn,
                amount,
                functional,
                Decimal(node.value),
                pieces,
                recognition_source,
            )
        )
    if (
        actual != expected
        or sum((item.transaction_amount for item in found), Decimal(0))
        != _transaction(target, txn) - before_txn
        or sum((item.functional_amount for item in found), Decimal(0))
        != Decimal(target.value) - before_functional
    ):
        raise RevenueActivityUnavailable(
            "Revenue activities do not reconcile to the original period target."
        )
    return tuple(sorted(found, key=lambda item: (item.effective_date, item.node_id)))
