"""Independent monetary read-back for legacy contract setup imports (CTL-002)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_event,
    estimate,
    estimate_version,
    import_upload,
    source_order,
    source_order_line,
    tenant,
)
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import Applied, ApplyContext, Plan


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


def _booking_line(line: Mapping[str, Any]) -> dict[str, Any]:
    price = line.get("total_price") or {}
    return {
        "obligation": line.get("obligation_key"),
        "product": line.get("product_code"),
        "quantity": _number(line.get("quantity")),
        "amount": _number(price.get("amount")),
        "currency": price.get("currency"),
        "unit_price": _number(line.get("unit_price")),
        "scope_flag": line.get("scope_flag") or "IN_SCOPE_606",
        "out_of_scope_amount": line.get("out_of_scope_amount"),
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Verify booked and source-order prices, and the approved VC amounts they generate."""
    currency = str(
        session.execute(
            select(tenant.c.reporting_currency)
            .join(import_upload, import_upload.c.tenant_id == tenant.c.id)
            .where(import_upload.c.id == context.import_upload_id)
        ).scalar_one()
    ).strip()
    first = plan.rows[0]
    name = first.normalized[columns.CONTRACT]
    record_id = str(context.record_ids[first.id])
    expected_lines = [
        _booking_line(
            {
                "obligation_key": row.normalized[columns.POB],
                "product_code": row.normalized[columns.SKU],
                "quantity": row.normalized[columns.QUANTITY],
                "total_price": {"amount": row.normalized[columns.PRICE], "currency": currency},
            }
        )
        for row in plan.rows
    ]
    bookings = list(
        session.execute(
            select(contract_event, contract.c.transaction_currency, contract.c.external_id)
            .join(
                contract,
                and_(
                    contract.c.tenant_id == contract_event.c.tenant_id,
                    contract.c.id == contract_event.c.contract_id,
                ),
            )
            .where(
                contract_event.c.id.in_(
                    [key for kind, key in applied.targets if kind == "contract_event"]
                ),
                contract_event.c.import_upload_id == context.import_upload_id,
                contract_event.c.event_type == "CONTRACT_BOOKED",
            )
        ).mappings()
    )
    # A split setup appends to the approved draft. Reconstruct its prior lines from
    # immutable earlier events, never from the replacement event's current payload.
    prior_lines: list[Mapping[str, Any]] = []
    if len(bookings) == 1:
        booking = bookings[0]
        prior = session.execute(
            select(contract_event.c.payload)
            .where(
                contract_event.c.contract_id == booking["contract_id"],
                contract_event.c.event_type == "CONTRACT_BOOKED",
                contract_event.c.stream_version < booking["stream_version"],
            )
            .order_by(contract_event.c.stream_version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is not None:
            prior_lines = [_booking_line(line) for line in prior["lines"]]
    expected_booking = {
        "contract": name,
        "currency": currency,
        "payload_currency": currency,
        "source_record_id": record_id,
        "lines": _ordered([*prior_lines, *expected_lines]),
    }
    actual_bookings = [
        {
            "contract": row["external_id"],
            "currency": str(row["transaction_currency"]).strip(),
            "payload_currency": row["payload"]["transaction_currency"],
            "source_record_id": str(row["source_record_id"]),
            "lines": _ordered([_booking_line(line) for line in row["payload"]["lines"]]),
        }
        for row in bookings
    ]
    orders = list(
        session.execute(
            select(source_order).where(
                source_order.c.external_version == str(context.import_upload_id),
                source_order.c.external_order_id == name,
            )
        ).mappings()
    )
    expected_order_lines = [
        {
            "obligation": row.normalized[columns.POB],
            "product": row.normalized[columns.SKU],
            "quantity": _number(row.normalized[columns.QUANTITY], 18),
            "amount": _number(row.normalized[columns.PRICE], 4),
        }
        for row in plan.rows
    ]
    actual_orders = []
    for order in orders:
        lines = session.execute(
            select(source_order_line).where(source_order_line.c.source_order_id == order["id"])
        ).mappings()
        actual_orders.append(
            {
                "contract": order["external_order_id"],
                "currency": str(order["transaction_currency"]).strip(),
                "source_record_id": str(order["source_record_id"]),
                "lines": _ordered(
                    [
                        {
                            "obligation": line["line_external_id"],
                            "product": line["product_code"],
                            "quantity": _number(line["quantity"], 18),
                            "amount": _number(line["total_price"], 4),
                        }
                        for line in lines
                    ]
                ),
            }
        )
    versions = list(
        session.execute(
            select(
                estimate_version,
                estimate.c.element_code,
                estimate.c.direction,
                estimate.c.method,
                estimate.c.estimate_kind,
                estimate.c.allocation_target,
                contract_event.c.id.label("event_id"),
                contract_event.c.payload.label("event_payload"),
            )
            .select_from(
                contract_event.join(
                    estimate_version,
                    and_(
                        estimate_version.c.tenant_id == contract_event.c.tenant_id,
                        estimate_version.c.id == contract_event.c.estimate_version_id,
                    ),
                ).join(
                    estimate,
                    and_(
                        estimate.c.tenant_id == estimate_version.c.tenant_id,
                        estimate.c.id == estimate_version.c.estimate_id,
                        estimate.c.contract_id == contract_event.c.contract_id,
                    ),
                )
            )
            .where(
                contract_event.c.import_upload_id == context.import_upload_id,
                contract_event.c.contract_id.in_([row["contract_id"] for row in bookings]),
                contract_event.c.event_type == "ESTIMATE_CHANGED",
            )
        ).mappings()
    )
    by_code = {version["element_code"]: version for version in versions}
    created = {key for kind, key in applied.targets if kind == "estimate"}
    inception = min(str(row.normalized[columns.CURRENT_PERIOD]) for row in plan.rows)
    expected_vc = []
    for row in plan.rows:
        if row.normalized[columns.STRATIFICATION] != "VC":
            continue
        code = f"VC-{row.normalized[columns.POB]}"
        price = Decimal(str(row.normalized[columns.PRICE]))
        current = by_code.get(code)
        settings = {
            "direction": "DECREASE" if price < 0 else "INCREASE",
            "method": "ENTERED_AMOUNT",
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "allocation_target": "CONTRACT",
        }
        # Existing elements keep their settings under IM-A; newly created elements
        # must carry the source-derived defaults, including the consideration sign.
        if current is not None and current["estimate_id"] not in created:
            settings = {key: str(current[key]) for key in settings}
        expected_vc.append(
            {
                "element": code,
                **settings,
                "amount": _number(abs(price), 4),
                "currency": currency,
                "effective_date": inception,
                "status": "APPROVED",
                "approval": str(context.approval_request_id),
                "event_linked": True,
            }
        )
    actual_vc = [
        {
            "element": v["element_code"],
            **{
                key: str(v[key])
                for key in ("direction", "method", "estimate_kind", "allocation_target")
            },
            "amount": _number(v["constrained_amount"], 4),
            "currency": str(v["currency"]).strip(),
            "effective_date": str(v["effective_date"]),
            "status": str(v["status"]),
            "approval": str(v["approval_request_id"]),
            "event_linked": list(v["applied_event_ids"]) == [v["event_id"]]
            and str(v["event_payload"].get("estimate_version_id")) == str(v["id"]),
        }
        for v in versions
    ]
    return (
        {
            "bookings": [expected_booking],
            "orders": [
                {
                    "contract": name,
                    "currency": currency,
                    "source_record_id": record_id,
                    "lines": _ordered(expected_order_lines),
                }
            ],
            "vc_versions": _ordered(expected_vc),
        },
        {"bookings": actual_bookings, "orders": actual_orders, "vc_versions": _ordered(actual_vc)},
    )
