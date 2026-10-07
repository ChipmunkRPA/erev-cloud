"""Persist the engine's immutable layer movements with natural-key lineage (T-CON-18)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.money import format_exact, minor_to_decimal
from sqlalchemy import insert

from erev_api.db import new_id
from erev_api.db.tables import fx_layer_movement
from erev_api.domain.contracts import bundles
from erev_api.uow import UnitOfWork


def persist(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book: BookOutput,
    version_id: UUID,
) -> list[UUID]:
    if not book.fx_layer_movements:
        return []
    rates = bundles.fx_rate_ids(uow.session, bundle)
    pinned = {rate.rate_key: rate for rate in bundle.fx_rates}
    events = {
        event.event_key: found.events[(event.contract_key, event.stream_version)]
        for event in bundle.events
        if (event.contract_key, event.stream_version) in found.events
    }
    rows: list[dict[str, Any]] = []
    for movement in book.fx_layer_movements:
        values = movement.columns
        owner = found.contracts.get(str(values.get("contract_key")))
        if owner is None:
            raise ValueError(f"FX layer {values['layer_key']} names no owning contract")
        txn, functional = str(values["txn_currency"]), str(values["functional_currency"])
        rate_key = values.get("rate_key")
        rate_id = None
        if rate_key is not None:
            key = str(rate_key)
            if (
                key not in rates
                or key not in pinned
                or pinned[key].version_key != values.get("version_key")
            ):
                raise ValueError(f"FX layer {values['layer_key']} names an unpinned rate")
            rate_id = rates[key][0]
        elif txn != functional:
            raise ValueError(f"FX layer {values['layer_key']} lacks its foreign-currency rate")
        rate = values["rate"]
        txn_amount, functional_amount = values["amount_txn"], values["amount_functional"]
        if not isinstance(rate, Fraction):
            raise ValueError("FX layer rate must be an exact Fraction")
        if any(type(amount) is not int for amount in (txn_amount, functional_amount)):
            raise ValueError("FX layer amounts must be integer minor units")
        source_key = values.get("source_key")
        # Time-driven and estimate-driven movements can have a synthetic source key. Their
        # immutable calculation trace is the lineage; source_event_id only names a real event.
        source_id = events.get(str(source_key)) if source_key is not None else None
        row = {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "contract_version_id": version_id,
            "contract_id": owner["id"],
            "book_code": book.book_code,
            "entity_id": found.entities[str(values["entity"])]["id"],
            **{
                key: values[key]
                for key in ("layer_key", "movement_kind", "balance_role", "effective_date")
            },
            "txn_currency": txn,
            "functional_currency": functional,
            "amount_txn": minor_to_decimal(int(str(txn_amount)), bundle.currencies[txn].minor_unit),
            "amount_functional": minor_to_decimal(
                int(str(functional_amount)), bundle.currencies[functional].minor_unit
            ),
            "fx_rate_id": rate_id,
            "rate": Decimal(format_exact(rate, places=12)),
            "source_event_id": source_id,
            "trace_node_id": movement.trace_nodes["amount_functional"],
            "created_at": uow.now,
            "created_by": uow.principal.id,
            "created_by_kind": uow.principal.kind.value,
        }
        rows.append(row)
    uow.session.execute(insert(fx_layer_movement), rows)
    return [row["id"] for row in rows]
