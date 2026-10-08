"""Independent legacy modification read-back, including signed deltas (CTL-002)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any
from uuid import uuid5

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_event,
    obligation,
    product,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import Applied, ApplyContext, Plan


def _number(value: Any) -> str:
    with localcontext() as ctx:
        ctx.prec = 80
        number = Decimal(str(value or 0))
        return format(number.normalize(), "f") if number else "0"


def _ordered(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def _line(value: Mapping[str, Any]) -> dict[str, Any]:
    money = value.get("consideration_delta") or {}
    return {
        "obligation": value.get("obligation_key"),
        "product": value.get("product_code"),
        "action": value.get("action"),
        "amount": _number(money.get("amount")),
        "currency": money.get("currency"),
        "quantity": _number(value.get("quantity_delta")),
        "start": value.get("start_date"),
        "end": value.get("end_date"),
        "stratification": value.get("stratification"),
        "ssp_label": value.get("ssp_version_label"),
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Read amended prices and quantities independently of the emitter's line builder."""
    first = plan.rows[0]
    name = str(first.normalized[columns.CONTRACT])
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
    events = list(
        session.execute(
            select(contract_event).where(
                contract_event.c.contract_id == current["id"],
                contract_event.c.import_upload_id == context.import_upload_id,
                contract_event.c.event_type == "CONTRACT_AMENDED",
            )
        ).mappings()
    )
    event_ids = [event["id"] for event in events]
    obligations = list(
        session.execute(
            select(obligation, product.c.code.label("product_code"))
            .join(
                product,
                and_(
                    product.c.tenant_id == obligation.c.tenant_id,
                    product.c.id == obligation.c.product_id,
                ),
            )
            .where(obligation.c.contract_id == current["id"])
        ).mappings()
    )
    prior_keys = {
        str(row["obligation_key"])
        for row in obligations
        if row["created_by_event_id"] not in event_ids
    }
    # Published reference labels are read directly, not from the emitter's catalogue.
    versions = {
        str(label): value
        for label, value in session.execute(
            select(ssp_book_version.c.legacy_version_label, ssp_book_version.c.id)
            .join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
            .where(ssp_book.c.code == "LEGACY-SKU-SSP", ssp_book_version.c.status == "APPROVED")
        ).all()
    }
    lines = []
    added = []
    basis = {}
    for row in plan.rows:
        values = row.normalized
        key = str(values[columns.POB])
        label = values.get(columns.SSP_VERSION)
        lines.append(
            _line(
                {
                    "obligation_key": key,
                    "product_code": values.get(columns.SKU),
                    "action": "CHANGE" if key in prior_keys else "ADD",
                    "consideration_delta": {
                        "amount": values.get(columns.MOD_BILLING),
                        "currency": currency,
                    },
                    "quantity_delta": values.get(columns.MOD_QTY),
                    "start_date": values.get(columns.MOD_START),
                    "end_date": values.get(columns.MOD_END),
                    "stratification": values.get(columns.STRATIFICATION),
                    "ssp_version_label": label,
                }
            )
        )
        basis[key] = {
            "ssp_book_version_id": str(versions[label]) if label in versions else None,
            "is_override": False,
            "justification": None,
        }
        if key not in prior_keys:
            added.append({"obligation": key, "product": values.get(columns.SKU)})
    treatment = {
        "prospective": "LEGACY_PROSPECTIVE",
        "retrospective": "LEGACY_RETROSPECTIVE",
        "pob_price_change": "LEGACY_POB_VC",
    }[str(context.parameters["mode"])]
    expected = {
        "events": [
            {
                "effective_date": str(context.parameters["effective_date"]),
                "source_record_id": str(context.record_ids[first.id]),
                "approval": str(context.approval_request_id),
                "targeted": True,
                "modification_id": str(uuid5(context.import_upload_id, name)),
                "treatments": dict.fromkeys(
                    prior_keys | {str(row.normalized[columns.POB]) for row in plan.rows}, treatment
                ),
                "lines": _ordered(lines),
                "ssp_basis": basis,
            }
        ],
        "added": _ordered(added),
    }
    targeted = {key for kind, key in applied.targets if kind == "contract_event"}
    actual = {
        "events": [
            {
                "effective_date": str(event["effective_date"]),
                "source_record_id": str(event["source_record_id"]),
                "approval": str(event["approval_request_id"]),
                "targeted": event["id"] in targeted,
                "modification_id": event["payload"].get("modification_id"),
                "treatments": event["payload"].get("treatments"),
                "lines": _ordered([_line(line) for line in event["payload"].get("lines", [])]),
                "ssp_basis": {
                    key: {
                        "ssp_book_version_id": value.get("ssp_book_version_id"),
                        "is_override": value.get("is_override", False),
                        "justification": value.get("justification"),
                    }
                    for key, value in event["payload"].get("ssp_basis", {}).items()
                },
            }
            for event in events
        ],
        "added": _ordered(
            [
                {"obligation": row["obligation_key"], "product": row["product_code"]}
                for row in obligations
                if row["created_by_event_id"] in event_ids
            ]
        ),
    }
    return expected, actual
