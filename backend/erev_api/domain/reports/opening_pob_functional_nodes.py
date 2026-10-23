"""Original functional POB openings, with document-level coverage rather than net-only proof."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from erev_api.domain.reports import tie_outs
from erev_engine.trace import TraceNode

ZERO = Decimal(0)


def read(
    nodes: Mapping[str, TraceNode],
    *,
    subject: str,
    period: tie_outs.PeriodRef,
    txn_currency: str,
    currency: str,
    billed: Decimal,
    revenue: Decimal,
) -> tuple[Decimal, Decimal, list[str]]:
    documents = {}
    prefix = "billing_document_attributed@"
    all_documents = [node for identity, node in nodes.items() if identity.startswith(prefix)]
    if not all_documents:
        raise tie_outs.invalid(
            "currency_view", "Functional POB billing sources require recomputation."
        )
    line_nodes = [
        node for identity, node in nodes.items() if identity.startswith("billing_line_attributed@")
    ]
    partitioned = {node.params["document_key"] for node in line_nodes}
    all_documents = [
        node for node in all_documents if node.id.split(":")[0][len(prefix) :] not in partitioned
    ]
    all_documents.extend(line_nodes)
    for node in all_documents:
        measure, owner, _ = node.id.split(":")
        if owner == subject and date.fromisoformat(node.params["as_of"]) <= period.end:
            if node.currency != txn_currency:
                raise tie_outs.invalid("currency_view", "Original billing currency differs.")
            documents[measure.split("@", 1)[1]] = node
    if sum((Decimal(node.value) for node in documents.values()), ZERO) != billed:
        raise tie_outs.invalid(
            "currency_view", "Original document attribution does not cover opening billing."
        )
    activity = {}
    for identity, node in nodes.items():
        if not identity.startswith("billing_obligation_activity_functional:"):
            continue
        if (
            node.params.get("obligation_subject") != subject
            or identity.rsplit(":", 1)[1] > period.key
        ):
            continue
        key = node.params["source_key"]
        if key in activity or node.currency != currency:
            raise tie_outs.invalid(
                "currency_view", "Functional billing has duplicate or inconsistent sources."
            )
        activity[key] = node
    if set(activity) != set(documents):
        raise tie_outs.invalid(
            "currency_view", "Functional billing lacks complete original document coverage."
        )
    functional_billing = ZERO
    inputs: list[str] = []
    for key, document in documents.items():
        node = activity[key]
        sign = node.params.get("sign")
        if sign not in {"1", "-1"} or Decimal(document.value) * Decimal(sign) < 0:
            raise tie_outs.invalid("currency_view", "Functional billing source sign differs.")
        functional_billing += Decimal(node.value) * Decimal(sign)
        inputs.extend((document.id, node.id))
    candidates = [
        node
        for identity, node in nodes.items()
        if identity.startswith(f"revenue_functional:{subject}:")
        and identity.rsplit(":", 1)[1] <= period.key
    ]
    functional_revenue = ZERO
    if candidates:
        node = max(candidates, key=lambda item: item.id.rsplit(":", 1)[1])
        scale = tie_outs.minor_unit(txn_currency)
        if (
            node.currency != currency
            or node.params.get("txn_currency") != txn_currency
            or node.params.get("txn_minor_unit") != str(scale)
            or Decimal(node.params["amount_txn"]) / (10**scale) != revenue
        ):
            raise tie_outs.invalid(
                "currency_view", "Functional revenue does not cover opening revenue."
            )
        functional_revenue = Decimal(node.value)
        inputs.append(node.id)
    elif revenue != 0:
        raise tie_outs.invalid("currency_view", "Functional opening revenue sources are missing.")
    return functional_billing, functional_revenue, inputs
