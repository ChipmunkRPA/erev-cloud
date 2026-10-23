"""Net posted amounts with complete original source sets, without invented layer shares."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from erev_engine.money import format_exact
from sqlalchemy import select

from erev_api.db.tables import contract
from erev_api.domain.reports.revenue_attribution import verify_component
from erev_api.uow import UnitOfWork

EVIDENCE = "bbr_revenue_source_sets_v1"


def capture(uow: UnitOfWork, line_id: UUID) -> dict[str, Any]:
    transaction = verify_component(uow, line_id, view="transaction")
    functional = verify_component(uow, line_id, view="functional")
    if transaction.sources != functional.sources:
        raise ValueError("Revenue currency views disagree on original source membership.")
    owner_ids = {item.contract_id for item in functional.sources}
    entities = {
        identity: entity
        for identity, entity in uow.session.execute(
            select(contract.c.id, contract.c.contracting_entity_id).where(
                contract.c.id.in_(owner_ids)
            )
        ).all()
    }
    if set(entities) != owner_ids:
        raise ValueError("Original source owners are not all visible.")
    return {
        "source_entity_ids": sorted({str(identity) for identity in entities.values()}),
        "basis": "aggregate_net_with_source_set",
        "amount_txn": format_exact(transaction.amount),
        "amount_functional": format_exact(functional.amount),
        "sources": [asdict(item) for item in functional.sources],
        "paid_line_ids": functional.paid_line_ids,
        "evidence": functional.evidence,
    }


def details(saved: dict[str, Any]) -> list[str]:
    if saved["basis"] == "unavailable":
        return ["Original source set unavailable: " + saved["reason"]]
    if saved["basis"] != "aggregate_net_with_source_set":
        raise ValueError("Unknown retained revenue source presentation.")
    result = [
        "Net revenue total with complete original source set. "
        "Sources describe provenance; no per-layer net amounts are assigned.",
        f"Original signed ledger amounts: transaction {saved['amount_txn']}; "
        f"functional {saved['amount_functional']}.",
    ]
    for source in saved["sources"]:
        result.append(
            f"Source {source['movement_id']}: contract {source['contract_id']}; "
            f"layer {source['layer_key']}; {source['movement_kind']}; "
            f"effective {source['effective_date']}; original key {source['source_key'] or 'none'}."
        )
    result.extend(f"Prior posting: {identity}" for identity in saved["paid_line_ids"])
    result.extend(
        f"Calculation evidence: {identity}; SHA-256 {digest}"
        for identity, digest in saved["evidence"]
    )
    return result
