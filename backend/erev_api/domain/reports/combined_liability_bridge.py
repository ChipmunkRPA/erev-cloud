"""Explain member presentation transfers from retained group liability layers.

S12 presents group carrying by S10 member weights, while the layers retain their
original owners. Bridge the two independently at each endpoint and include the
known difference between a memo's issuer and its consumed layer owner. Never
calculate a transfer from a report's unexplained OTHER amount.
"""

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

ZERO = Decimal(0)
ROLE = "contract_liability"
KEY = "combined_liability_bridge_v3"
ENDPOINT_KEY = "combined_liability_bridge_v2"
LEGACY_KEY = "combined_liability_bridge_v1"


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
    foreign_members: frozenset[tuple[UUID, UUID]],
    opening_relief: Mapping[tuple[UUID, UUID, UUID], Decimal],
) -> tuple[ContractRollforward, ...]:
    evidence_key = KEY
    if params.binding is not None:
        evidence_key = next(
            key for key in (KEY, ENDPOINT_KEY, LEGACY_KEY) if key in params.binding.evidence
        )
    if evidence_key == LEGACY_KEY:
        touched = {owner for owner, _, _ in transfers}
        versions = {row.version_id for row in closing if row.contract_id in touched}
        members = {
            (row.contract_id, row.entity_id) for row in closing if row.version_id in versions
        }
    else:
        # Presentation can change when billing is added at a different historical
        # rate, even with no memo and no FX journal. Include both endpoint populations.
        members = set(foreign_members)
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
            raise tie_outs.invalid("currency_view", "Member bridge lacks its original trace.")
        nodes = {node.id: node for node in trace.nodes}
        rows = (
            session.execute(
                select(fx_layer_movement).where(
                    fx_layer_movement.c.contract_version_id == row.version_id,
                    fx_layer_movement.c.contract_id == row.contract_id,
                    fx_layer_movement.c.entity_id == row.entity_id,
                    fx_layer_movement.c.balance_role == "CONTRACT_LIABILITY",
                    fx_layer_movement.c.effective_date <= period.end,
                )
            )
            .mappings()
            .all()
        )
        carrying = ZERO
        for source in rows:
            node = nodes.get(str(source["trace_node_id"]))
            signs = {
                "LIABILITY_LAYER_CREATED": 1,
                "LIABILITY_LAYER_CONSUMED": -1,
                "LIABILITY_LAYER_REMEASURED": 1,
            }
            if (
                source["movement_kind"] not in signs
                or node is None
                or node.currency != row.currency
                or Decimal(node.value) != Decimal(source["amount_functional"])
            ):
                raise tie_outs.invalid(
                    "currency_view", "Member bridge layer differs from its trace."
                )
            carrying += signs[source["movement_kind"]] * Decimal(source["amount_functional"])
            consumed.add(source["id"])
        value = row.value(ROLE) - carrying
        identity = f"{row.version_id}:{row.contract_id}:{period.key}"
        if evidence_key != LEGACY_KEY:
            identity = f"{row.version_id}:{row.contract_id}:{row.entity_id}:{period.key}"
        facts[identity] = {
            "presented": str(row.value(ROLE)),
            "source_carrying": str(carrying),
        }
        cache[key] = value
        return value

    opening_map = {(row.contract_id, row.entity_id): row for row in opening}
    closing_map = {(row.contract_id, row.entity_id): row for row in closing}
    output = []
    conservation: dict[tuple[UUID, UUID | None, str], Decimal] = {}
    for item in items:
        if (item.contract_id, item.entity_id) not in members:
            output.append(item)
            continue
        key = (item.contract_id, item.entity_id)
        initial = bridge(opening_map.get(key), before.get(item.entity_id))
        old = opening_map.get(key)
        old_key = (item.entity_id, None if old is None else old.version_id, "opening")
        conservation[old_key] = conservation.get(old_key, ZERO) + initial
        ending = bridge(closing_map.get(key), periods[item.entity_id][-1])
        last = closing_map.get(key)
        last_key = (item.entity_id, None if last is None else last.version_id, "closing")
        conservation[last_key] = conservation.get(last_key, ZERO) + ending
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

        def adjusted(
            lines: Mapping[str, Mapping[str, Decimal]],
            amount: Decimal,
            original: Decimal | None = None,
        ) -> dict[str, dict[str, Decimal]]:
            changed = {name: dict(values) for name, values in lines.items()}
            changed["RECLASSIFICATIONS"][ROLE] += amount
            changed["OTHER"][ROLE] -= amount
            if original is not None:
                previous_opening = changed["REVENUE_FROM_OPENING"][ROLE]
                changed["REVENUE_FROM_OPENING"][ROLE] = -original
                changed["REVENUE_FROM_PERIOD_BILLINGS"][ROLE] += previous_opening + original
            return changed

        months = {}
        previous = cumulative = ZERO
        for period in periods[item.entity_id]:
            if period.id not in item.period_lines:
                continue
            cumulative += transfers.get((*key, period.id), ZERO)
            month = monthly[(item.entity_id, period.id)].get(key)
            at = bridge(month, period)
            month_key = (item.entity_id, None if month is None else month.version_id, period.key)
            conservation[month_key] = conservation.get(month_key, ZERO) + at
            current = at - initial + cumulative
            months[period.id] = adjusted(
                item.period_lines[period.id],
                current - previous,
                opening_relief.get((*key, period.id)),
            )
            previous = current
        selected_opening = [
            amount
            for (owner, entity, _), amount in opening_relief.items()
            if (owner, entity) == key
        ]
        output.append(
            replace(
                item,
                lines=adjusted(
                    item.lines, total, sum(selected_opening, ZERO) if selected_opening else None
                ),
                period_lines=months,
            )
        )
    if any(value != 0 for value in conservation.values()) or sum(transfers.values(), ZERO) != 0:
        raise tie_outs.invalid(
            "currency_view", "Member liability bridge does not conserve the full group."
        )
    evidence = {
        "endpoints": facts,
        ("source_transfers" if evidence_key == KEY else "memo_transfers"): {
            ":".join(map(str, key)): str(value) for key, value in sorted(transfers.items())
        },
    }
    if params.binding is not None and params.binding.evidence[evidence_key] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Member liability bridge differs from retained evidence."
        )
    tie_outs.require_members(params, "combined_liability_movement", consumed)
    tie_outs.record_members(params, "combined_liability_movement", consumed)
    tie_outs.record_evidence(params, evidence_key, evidence)
    return tuple(output)
