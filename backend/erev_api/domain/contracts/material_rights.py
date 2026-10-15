"""Read immutable T-CON-14 terms at a record cut and translate them for the engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_engine.bundle import MaterialRightInput
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from sqlalchemy import and_, select, true
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_event, estimate, material_right, obligation
from erev_api.schemas.obligations import MaterialRightOut


def _rows(
    session: Session, contract_ids: Sequence[UUID], *, known_at: datetime | None
) -> list[Mapping[str, Any]]:
    if not contract_ids:
        return []
    statement = (
        select(material_right, obligation.c.obligation_key, estimate.c.element_code)
        .select_from(
            material_right.join(
                contract,
                and_(
                    contract.c.tenant_id == material_right.c.tenant_id,
                    contract.c.id == material_right.c.contract_id,
                ),
            )
            .join(
                obligation,
                and_(
                    obligation.c.tenant_id == material_right.c.tenant_id,
                    obligation.c.id == material_right.c.obligation_id,
                ),
            )
            .outerjoin(
                estimate,
                and_(
                    estimate.c.tenant_id == material_right.c.tenant_id,
                    estimate.c.id == material_right.c.likelihood_estimate_id,
                ),
            )
        )
        .where(
            material_right.c.contract_id.in_(contract_ids),
            true() if known_at is None else material_right.c.created_at <= known_at,
        )
        .order_by(material_right.c.contract_id, obligation.c.obligation_key)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def inputs(
    session: Session, contract_keys: Mapping[UUID, str], *, known_at: datetime
) -> dict[UUID, tuple[MaterialRightInput, ...]]:
    found: dict[UUID, list[MaterialRightInput]] = {}
    for row in _rows(session, sorted(contract_keys), known_at=known_at):
        contract_id = UUID(str(row["contract_id"]))
        element_code = row["element_code"]
        if row["likelihood_estimate_id"] is not None and element_code is None:
            raise ValueError("A material-right likelihood estimate is missing.")
        found.setdefault(contract_id, []).append(
            MaterialRightInput(
                obligation_key=str(row["obligation_key"]),
                option_type=str(row["option_type"]),
                incremental_discount_ratio=row["incremental_discount_ratio"],
                is_discount_available_without_contract=bool(
                    row["is_discount_available_without_contract"]
                ),
                expected_purchase_amount=row["expected_purchase_amount"],
                entered_ssp_amount=row["entered_ssp_amount"],
                currency=str(row["currency"]).strip(),
                ssp_method=str(row["ssp_method"]),
                expiry_date=row["expiry_date"],
                likelihood_estimate_key=None
                if element_code is None
                else obligation_subject_key(contract_keys[contract_id], str(element_code)),
                is_legacy_quantity_ssp_dollars=bool(row["is_legacy_quantity_ssp_dollars"]),
            )
        )
    return {key: tuple(values) for key, values in found.items()}


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def outputs(
    session: Session, contract_ids: Sequence[UUID], *, known_at: datetime | None, as_of: date
) -> dict[UUID, MaterialRightOut]:
    rows = _rows(session, contract_ids, known_at=known_at)
    if not rows:
        return {}
    events = list(
        session.execute(
            select(contract_event)
            .where(
                contract_event.c.contract_id.in_(sorted({row["contract_id"] for row in rows})),
                true() if known_at is None else contract_event.c.recorded_at <= known_at,
                contract_event.c.event_type.in_(
                    [
                        "MATERIAL_RIGHT_EXERCISED",
                        "MATERIAL_RIGHT_EXPIRED",
                        "EVENT_VOIDED",
                        "CONTRACT_VOIDED",
                    ]
                ),
            )
            .order_by(contract_event.c.effective_date, contract_event.c.record_seq)
        ).mappings()
    )
    # As in S01-R-12, a known void removes its target, including from earlier effective cuts.
    removed = {
        event["supersedes_event_id"] for event in events if event["event_type"] == "EVENT_VOIDED"
    }
    voided_contracts = {
        event["contract_id"]
        for event in events
        if event["event_type"] == "CONTRACT_VOIDED" and event["id"] not in removed
    }
    statuses: dict[tuple[UUID, str], tuple[str, date]] = {}
    for event in events:
        kind = str(event["event_type"])
        if kind not in {"MATERIAL_RIGHT_EXERCISED", "MATERIAL_RIGHT_EXPIRED"}:
            continue
        if (
            event["id"] in removed
            or event["contract_id"] in voided_contracts
            or event["effective_date"] > as_of
        ):
            continue
        key = (event["contract_id"], str(event["payload"]["obligation_key"]))
        statuses[key] = (
            "EXERCISED" if kind == "MATERIAL_RIGHT_EXERCISED" else "EXPIRED",
            event["effective_date"],
        )
    result = {}
    for row in rows:
        status, status_date = statuses.get(
            (row["contract_id"], str(row["obligation_key"])), ("OPEN", None)
        )
        result[UUID(str(row["obligation_id"]))] = MaterialRightOut(
            option_type=str(row["option_type"]),
            incremental_discount_ratio=_decimal(row["incremental_discount_ratio"]),
            expected_purchase_amount=_decimal(row["expected_purchase_amount"]),
            entered_ssp_amount=_decimal(row["entered_ssp_amount"]),
            expiry_date=row["expiry_date"],
            ssp_method=str(row["ssp_method"]),
            likelihood_estimate_id=row["likelihood_estimate_id"],
            status=status,
            status_date=status_date,
        )
    return result
