"""Independent persisted monetary and quantity checks for legacy progress (CTL-002)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_event, source_invoice, source_invoice_line
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import Applied, ApplyContext, Plan

FINANCIAL_EVENTS = (
    "BILLING_RECORDED",
    "CREDIT_MEMO_RECORDED",
    "PRE_STANDARD_REVENUE_RECORDED",
    "DELIVERY_RECORDED",
    "RETURN_RECORDED",
)


def _number(value: Any, scale: int | None = None) -> str | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        number = Decimal(str(value))
        if scale is not None:
            number = number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
        return format(number.normalize(), "f") if number else "0"


def _ordered(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Aggregate source cells independently, then check events and signed source invoices."""
    name = plan.rows[0].normalized[columns.CONTRACT]
    current = (
        session.execute(
            select(contract.c.id, contract.c.transaction_currency).where(
                contract.c.external_id == name
            )
        )
        .mappings()
        .one()
    )
    currency = str(current["transaction_currency"]).strip()
    effective = str(context.parameters["effective_date"])
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    with localcontext() as ctx:
        ctx.prec = 80
        for row in sorted(plan.rows, key=lambda row: row.row_number):
            values = row.normalized
            key = (str(values[columns.POB]), str(values[columns.SKU]))
            group = groups.setdefault(
                key,
                {
                    "record": str(context.record_ids[row.id]),
                    "billing": Decimal(0),
                    "revenue": Decimal(0),
                    "delivery": Decimal(0),
                },
            )
            for column, member in (
                (columns.BILLING, "billing"),
                (columns.PRE_STANDARD, "revenue"),
                (columns.DELIVERY, "delivery"),
            ):
                group[member] += Decimal(str(values[column]))
    expected_events: list[Mapping[str, Any]] = []
    expected_documents: list[Mapping[str, Any]] = []
    for (pob, product), group in groups.items():
        number = f"{context.import_upload_id}:{name}:{pob}"
        common = {
            "obligation": pob,
            "source_record_id": group["record"],
            "effective_date": effective,
            "targeted": True,
        }
        for member, positive, negative in (
            ("billing", "BILLING_RECORDED", "CREDIT_MEMO_RECORDED"),
            ("revenue", "PRE_STANDARD_REVENUE_RECORDED", "PRE_STANDARD_REVENUE_RECORDED"),
            ("delivery", "DELIVERY_RECORDED", "RETURN_RECORDED"),
        ):
            value = group[member]
            if not value:
                continue
            kind = positive if value > 0 else negative
            expected_events.append(
                {
                    **common,
                    "type": kind,
                    "amount": _number(value if member == "revenue" else value.copy_abs())
                    if member != "delivery"
                    else None,
                    "currency": currency if member != "delivery" else None,
                    "quantity": _number(value.copy_abs()) if member == "delivery" else None,
                    "document": number if member == "billing" else None,
                    "issue_date": effective if member == "billing" else None,
                    "invoice_linked": True if kind == "BILLING_RECORDED" else None,
                }
            )
        if group["billing"]:
            amount = _number(group["billing"], 4)
            expected_documents.append(
                {
                    "number": number,
                    "currency": currency,
                    "kind": "INVOICE" if group["billing"] > 0 else "CREDIT_MEMO",
                    "source_record_id": group["record"],
                    "issue_date": effective,
                    "amount": amount,
                    "lines": [
                        {
                            "number": number,
                            "contract": name,
                            "obligation": pob,
                            "product": product,
                            "amount": amount,
                            "tax_lines": [],
                        }
                    ],
                }
            )
    invoices = list(
        session.execute(
            select(source_invoice).where(
                source_invoice.c.source_record_id.in_(
                    list(context.record_ids[row.id] for row in plan.rows)
                )
            )
        ).mappings()
    )
    lines = session.execute(
        select(source_invoice_line).where(
            source_invoice_line.c.source_invoice_id.in_([invoice["id"] for invoice in invoices])
        )
    ).mappings()
    by_invoice: dict[Any, list[Mapping[str, Any]]] = {}
    for line in lines:
        by_invoice.setdefault(line["source_invoice_id"], []).append(
            {
                "number": line["line_external_id"],
                "contract": line["contract_ref"],
                "obligation": line["obligation_ref"],
                "product": line["product_code"],
                "amount": _number(line["amount"], 4),
                "tax_lines": line["tax_lines"],
            }
        )
    actual_documents = [
        {
            "number": invoice["external_invoice_id"],
            "currency": str(invoice["currency"]).strip(),
            "kind": str(invoice["document_kind"]),
            "source_record_id": str(invoice["source_record_id"]),
            "issue_date": str(invoice["issue_date"]),
            "amount": _number(invoice["total_amount"], 4),
            "lines": _ordered(by_invoice.get(invoice["id"], [])),
        }
        for invoice in invoices
    ]
    ids_by_number = {
        str(invoice["external_invoice_id"]): str(invoice["id"]) for invoice in invoices
    }
    targeted = {key for kind, key in applied.targets if kind == "contract_event"}
    events = session.execute(
        select(contract_event).where(
            contract_event.c.contract_id == current["id"],
            contract_event.c.import_upload_id == context.import_upload_id,
            contract_event.c.event_type.in_(FINANCIAL_EVENTS),
        )
    ).mappings()
    actual_events = []
    for event in events:
        payload = event["payload"]
        kind = str(event["event_type"])
        number = payload.get("invoice_number") or payload.get("credit_memo_number")
        money = payload.get("amount") or {}
        actual_events.append(
            {
                "obligation": payload.get("obligation_key"),
                "source_record_id": str(event["source_record_id"]),
                "effective_date": str(event["effective_date"]),
                "targeted": event["id"] in targeted,
                "type": kind,
                "amount": _number(money.get("amount")),
                "currency": money.get("currency"),
                "quantity": _number(payload.get("quantity")),
                "document": number,
                "issue_date": payload.get("issue_date"),
                "invoice_linked": (
                    payload.get("source_invoice_id") is not None
                    and payload.get("source_invoice_id") == ids_by_number.get(str(number))
                )
                if kind == "BILLING_RECORDED"
                else None,
            }
        )
    return (
        {"events": _ordered(expected_events), "documents": _ordered(expected_documents)},
        {"events": _ordered(actual_events), "documents": _ordered(actual_documents)},
    )
