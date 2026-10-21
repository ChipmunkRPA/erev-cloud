"""Member asset presentation from original carrying and signed return settlements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_layer_movement
from erev_api.domain.reports import tie_outs
from erev_api.explain import store

if TYPE_CHECKING:
    from .builders import ReportParams
    from .builders.contract_balance_rollforward import ContractRollforward

KEY = "combined_asset_bridge_v3"
BILLING_KEY = "combined_asset_bridge_v2"
LEGACY_KEY = "combined_asset_bridge_v1"
ZERO = Decimal(0)
ROLE = "contract_asset"


def apply(
    session: Session,
    params: ReportParams,
    items: Sequence[ContractRollforward],
    *,
    opening: Sequence[tie_outs.BalanceRow],
    closing: Sequence[tie_outs.BalanceRow],
    before: Mapping[UUID, tie_outs.PeriodRef | None],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    monthly: Mapping[tuple[UUID, UUID], Mapping[tuple[UUID, UUID], tie_outs.BalanceRow]],
    transfers: Mapping[tuple[UUID, UUID, UUID], Decimal],
    billing_assets: Mapping[tuple[UUID, UUID, UUID], Decimal],
) -> tuple[ContractRollforward, ...]:
    evidence_key = (
        KEY
        if params.binding is None
        else next(key for key in (KEY, BILLING_KEY, LEGACY_KEY) if key in params.binding.evidence)
    )
    touched = {(owner, entity) for owner, entity, _ in transfers}
    if evidence_key == KEY:
        # Zero is evidence too: a memo can consume only liability layers while
        # member presentation makes the local FIFO path classify it as an asset.
        group_members: dict[tuple[UUID, UUID], set[UUID]] = {}
        for row in (*opening, *closing):
            group_members.setdefault((row.version_id, row.entity_id), set()).add(row.contract_id)
        combined = {
            (owner, entity)
            for (_, entity), owners in group_members.items()
            if len(owners) > 1
            for owner in owners
        }
        touched.update(
            (owner, entity) for owner, entity, _ in billing_assets if (owner, entity) in combined
        )
    versions = {
        (row.version_id, row.entity_id)
        for row in (*opening, *closing)
        if (row.contract_id, row.entity_id) in touched
    }
    members = {
        (row.contract_id, row.entity_id)
        for row in (*opening, *closing)
        if (row.version_id, row.entity_id) in versions
    }
    consumed: set[UUID] = set()
    facts: dict[str, Any] = {}
    cache: dict[tuple[UUID, UUID, UUID, str], Decimal] = {}

    def bridge(row: tie_outs.BalanceRow | None, period: tie_outs.PeriodRef | None) -> Decimal:
        if row is None or period is None:
            return ZERO
        key = (row.version_id, row.contract_id, row.entity_id, period.key)
        if key in cache:
            return cache[key]
        trace = store.load_trace(session, row.version_id)
        if trace is None:
            raise tie_outs.invalid("currency_view", "Member asset bridge lacks its original trace.")
        nodes = {node.id: node for node in trace.nodes}
        rows = (
            session.execute(
                select(fx_layer_movement).where(
                    fx_layer_movement.c.contract_version_id == row.version_id,
                    fx_layer_movement.c.contract_id == row.contract_id,
                    fx_layer_movement.c.entity_id == row.entity_id,
                    fx_layer_movement.c.balance_role == "CONTRACT_ASSET",
                    fx_layer_movement.c.effective_date <= period.end,
                )
            )
            .mappings()
            .all()
        )
        carrying = ZERO
        signs = {"ASSET_LAYER_CREATED": 1, "ASSET_LAYER_SETTLED": -1, "ASSET_LAYER_REMEASURED": 1}
        for source in rows:
            node = nodes.get(str(source["trace_node_id"]))
            if (
                source["movement_kind"] not in signs
                or node is None
                or node.currency != row.currency
                or Decimal(node.value) != Decimal(source["amount_functional"])
            ):
                raise tie_outs.invalid(
                    "currency_view", "Member asset layer differs from its trace."
                )
            carrying += signs[source["movement_kind"]] * Decimal(source["amount_functional"])
            consumed.add(source["id"])
        # The engine's asset layers support both contract assets and unbilled
        # receivables; the existing rollforward separately presents that reclass.
        presented = row.value(ROLE) + row.value("unbilled_receivable")
        value = presented - carrying
        facts[":".join(map(str, key))] = {
            "presented": str(presented),
            "source_carrying": str(carrying),
        }
        cache[key] = value
        return value

    opening_map = {(row.contract_id, row.entity_id): row for row in opening}
    closing_map = {(row.contract_id, row.entity_id): row for row in closing}
    conservation: dict[tuple[UUID, UUID | None, str], Decimal] = {}

    def endpoint(
        row: tie_outs.BalanceRow | None, period: tie_outs.PeriodRef | None, entity: UUID, label: str
    ) -> Decimal:
        amount = bridge(row, period)
        key = (entity, None if row is None else row.version_id, label)
        conservation[key] = conservation.get(key, ZERO) + amount
        return amount

    def adjusted(
        lines: Mapping[str, Mapping[str, Decimal]],
        amount: Decimal,
        billed_asset: Decimal | None = None,
    ) -> dict[str, dict[str, Decimal]]:
        changed = {name: dict(values) for name, values in lines.items()}
        changed["RECLASSIFICATIONS"][ROLE] += amount
        changed["OTHER"][ROLE] -= amount
        if evidence_key in {KEY, BILLING_KEY} and billed_asset is not None:
            # An invoice can settle another member's asset even when the issuer
            # has none. Use the original asset amount, never the residual OTHER.
            shift = billed_asset - changed["BILLINGS"][ROLE]
            changed["BILLINGS"][ROLE] += shift
            changed["BILLINGS"]["contract_liability"] += shift
            changed["OTHER"][ROLE] -= shift
            changed["OTHER"]["contract_liability"] -= shift
        return changed

    output = []
    for item in items:
        key = (item.contract_id, item.entity_id)
        if key not in members:
            output.append(item)
            continue
        initial = endpoint(
            opening_map.get(key), before.get(item.entity_id), item.entity_id, "opening"
        )
        ending = endpoint(
            closing_map.get(key), periods[item.entity_id][-1], item.entity_id, "closing"
        )
        total = (
            ending
            - initial
            + sum(
                (
                    value
                    for (owner, entity, _), value in transfers.items()
                    if (owner, entity) == key
                ),
                ZERO,
            )
        )
        months = {}
        previous = cumulative = ZERO
        for period in periods[item.entity_id]:
            if period.id not in item.period_lines:
                continue
            cumulative += transfers.get((*key, period.id), ZERO)
            at = endpoint(
                monthly[(item.entity_id, period.id)].get(key), period, item.entity_id, period.key
            )
            current = at - initial + cumulative
            months[period.id] = adjusted(
                item.period_lines[period.id],
                current - previous,
                billing_assets.get((*key, period.id)),
            )
            previous = current
        asset_values = [
            value for (owner, entity, _), value in billing_assets.items() if (owner, entity) == key
        ]
        output.append(
            replace(
                item,
                lines=adjusted(
                    item.lines, total, sum(asset_values, ZERO) if asset_values else None
                ),
                period_lines=months,
            )
        )
    if any(conservation.values()) or sum(transfers.values(), ZERO) != 0:
        raise tie_outs.invalid(
            "currency_view", "Member asset bridge does not conserve the full group."
        )
    evidence = {
        "endpoints": facts,
        "source_transfers": {
            ":".join(map(str, key)): str(value) for key, value in sorted(transfers.items())
        },
    }
    if evidence_key in {KEY, BILLING_KEY}:
        evidence["billing_assets"] = {
            ":".join(map(str, key)): str(value) for key, value in sorted(billing_assets.items())
        }
    if params.binding is not None and params.binding.evidence[evidence_key] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Member asset bridge differs from retained evidence."
        )
    tie_outs.require_members(params, "combined_asset_movement", consumed)
    tie_outs.record_members(params, "combined_asset_movement", consumed)
    tie_outs.record_evidence(params, evidence_key, evidence)
    return tuple(output)
