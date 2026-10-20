"""Cross-member liability relief checked against original posted revenue sources.

Retained liability reliefs must reproduce the full recipient/period posting.
Source-proven reversals may reduce original consumed layers. Own-member asset creation
can accompany cross-member liability relief. Mixed TIME allocation, close-pass-only
and foreign-owner asset histories still require additional presentation;
no difference is apportioned or inferred from the report's OTHER amount.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_layer_movement
from erev_api.domain.reports import revenue_trace, tie_outs
from erev_api.explain import store
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from .builders import ReportParams
    from .builders.contract_balance_rollforward import Entry
    from .revenue_attribution import Attribution

KEY = "revenue_layer_transfers_v1"
ZERO = Decimal(0)
type Amounts = dict[tuple[UUID, UUID, UUID], Decimal]


def read(
    session: Session,
    params: ReportParams,
    rows: Mapping[tuple[UUID, UUID], tie_outs.BalanceRow],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    posted: Mapping[tuple[UUID, UUID], list[Entry]],
    *,
    uow: UnitOfWork | None = None,
) -> tuple[Amounts, Amounts, Amounts]:
    groups: dict[tuple[UUID, UUID], list[tie_outs.BalanceRow]] = defaultdict(list)
    for row in rows.values():
        groups[(row.version_id, row.entity_id)].append(row)
    transfers: Amounts = defaultdict(Decimal)
    opening: Amounts = {}
    liability: Amounts = {}
    consumed: set[UUID] = set()
    evidence: dict[str, Any] = {}
    signed_key = "revenue_signed_sources_v1"
    signed = params.binding is None or signed_key in params.binding.evidence
    signed_evidence: dict[str, Any] = {}
    signed_members: set[UUID] = set()
    delta_key = "revenue_posted_sources_v1"
    verify_postings = uow is not None and (
        params.binding is None or delta_key in params.binding.evidence
    )
    posted_evidence: dict[str, Any] = {}
    posted_ids: set[UUID] = set()
    attribution_cache: dict[UUID, Attribution] = {}
    for (version, entity), members in groups.items():
        if len(members) < 2 or not periods[entity]:
            continue
        owners = {row.external_id: row.contract_id for row in members}
        trace = store.load_trace(session, version)
        if trace is None:
            raise tie_outs.invalid("currency_view", "Combined revenue lacks its original trace.")
        nodes = {node.id: node for node in trace.nodes}
        movement_rows = (
            session.execute(
                select(fx_layer_movement).where(
                    fx_layer_movement.c.contract_version_id == version,
                    fx_layer_movement.c.entity_id == entity,
                    fx_layer_movement.c.contract_id.in_(list(owners.values())),
                    fx_layer_movement.c.movement_kind.in_(
                        (
                            "LIABILITY_LAYER_CONSUMED",
                            "LIABILITY_LAYER_CREATED",
                            "ASSET_LAYER_CREATED",
                            "ASSET_LAYER_SETTLED",
                        )
                    ),
                )
            )
            .mappings()
            .all()
        )
        creations = {
            (item["contract_id"], item["layer_key"]): item
            for item in movement_rows
            if item["movement_kind"] == "LIABILITY_LAYER_CREATED"
        }
        amounts: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        original: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        sources: dict[tuple[UUID, UUID], set[UUID]] = defaultdict(set)
        retained_reliefs: dict[tuple[UUID, UUID, UUID, str], Decimal] = defaultdict(Decimal)
        cross = []
        affected: set[UUID] = set()
        verified_revenue: dict[str, dict[UUID, revenue_trace.RevenueSource]] = {}
        for movement in movement_rows:
            node = nodes.get(str(movement["trace_node_id"]))
            if (
                movement["movement_kind"] != "LIABILITY_LAYER_CONSUMED"
                or node is None
                or "#REVENUE@" not in node.id
            ):
                continue
            at = next(
                (
                    item
                    for item in periods[entity]
                    if item.start <= movement["effective_date"] <= item.end
                ),
                None,
            )
            subject = node.id.split("#REVENUE@", 1)[1].rsplit(":", 1)[0]
            recognizer = owners.get(contract_key_from_subject(subject))
            # A return in the selected range can settle sources consumed before
            # the range. Discover that relationship without moving prior relief
            # into the current-period totals. Original posting replay verifies it.
            if (
                recognizer is not None
                and recognizer != movement["contract_id"]
                and movement["effective_date"] <= periods[entity][-1].end
                and (
                    params.binding is None
                    or "combined_liability_bridge_v5" in params.binding.evidence
                )
            ):
                affected.add(recognizer)
            if at is None:
                continue
            creation = creations.get((movement["contract_id"], movement["layer_key"]))
            creation_node = None if creation is None else nodes.get(str(creation["trace_node_id"]))
            if (
                recognizer is None
                or node.currency != str(movement["functional_currency"]).strip()
                or Decimal(node.value) != Decimal(movement["amount_functional"])
                or Decimal(movement["amount_functional"]) < 0
                or creation is None
                or creation_node is None
                or creation_node.currency != node.currency
                or Decimal(creation_node.value) != Decimal(creation["amount_functional"])
                or creation["effective_date"] > movement["effective_date"]
            ):
                raise tie_outs.invalid(
                    "currency_view", "Revenue relief differs from its retained owner/amount."
                )
            if signed:
                # Verify the consumed layer as part of the complete signed revenue
                # target, including asset creation and negative-revenue source pieces.
                target = f"revenue_functional:{subject}:{at.key}"
                if target not in verified_revenue:
                    try:
                        verified_revenue[target] = {
                            source.movement_id: source
                            for source in revenue_trace.project(
                                trace, target, movement_rows, currency=node.currency
                            )
                        }
                    except revenue_trace.InvalidRevenueTrace as error:
                        raise tie_outs.invalid("currency_view", str(error)) from error
                retained = verified_revenue[target].get(movement["id"])
                if retained is None or retained.amount != Decimal(movement["amount_functional"]):
                    raise tie_outs.invalid(
                        "currency_view",
                        "Relief is not a positive source of the retained revenue target.",
                    )
                signed_evidence[f"{version}:{entity}:{target}"] = [
                    {
                        "movement_id": str(source.movement_id),
                        "contract_id": str(source.contract_id),
                        "layer_key": source.layer_key,
                        "movement_kind": source.movement_kind,
                        "amount": str(source.amount),
                    }
                    for source in verified_revenue[target].values()
                ]
                signed_members.update(verified_revenue[target])
            source_key = (recognizer, at.id)
            amount = Decimal(movement["amount_functional"])
            amounts[source_key] += amount
            sources[source_key].update((movement["id"], creation["id"]))
            if creation["effective_date"] < periods[entity][0].start:
                original[source_key] += amount
            owner = UUID(str(movement["contract_id"]))
            retained_reliefs[(recognizer, at.id, owner, movement["layer_key"])] += amount
            if owner != recognizer:
                cross.append((owner, recognizer, at.id, amount))
        # Check all periods for affected recipients so the opening/new revenue
        # classification covers their entire range, including own-layer reliefs.
        for recognizer in {recipient for _, recipient, _, _ in cross} | affected:
            for at in periods[entity]:
                source_key = (recognizer, at.id)
                entries = [
                    entry
                    for entry in posted.get((recognizer, entity), ())
                    if entry.period_id == at.id and entry.flow.is_revenue
                ]
                verify_period = verify_postings and all(
                    entry.entry_kind == "REVENUE_RECOGNITION" for entry in entries
                )
                signed_liability = Fraction(0)
                if verify_period:
                    from .revenue_attribution import for_control

                    assert uow is not None
                    posted_reliefs: dict[tuple[UUID, str], Fraction] = defaultdict(Fraction)
                    for entry in entries:
                        if entry.line_id is None:
                            raise tie_outs.invalid(
                                "currency_view", "Revenue lacks a posted control line."
                            )
                        try:
                            revenue_id, result = for_control(
                                uow, entry.line_id, cache=attribution_cache
                            )
                        except ValueError as error:
                            raise tie_outs.invalid("currency_view", str(error)) from error
                        if result.delta.amount != -entry.flow.amount:
                            raise tie_outs.invalid(
                                "currency_view",
                                "Retained revenue delta differs from the report flow.",
                            )
                        for part in result.delta.movements:
                            if part.movement_kind == "LIABILITY_LAYER_CONSUMED":
                                posted_reliefs[(part.contract_id, part.layer_key)] -= part.amount
                                signed_liability -= part.amount
                            elif part.amount and (
                                part.contract_id == recognizer
                                and part.movement_kind
                                in {
                                    "ASSET_LAYER_CREATED",
                                    "ASSET_LAYER_SETTLED",
                                    "LIABILITY_LAYER_CREATED",
                                }
                            ):
                                if part.movement_kind == "LIABILITY_LAYER_CREATED":
                                    signed_liability -= part.amount
                            elif part.amount:
                                raise tie_outs.invalid(
                                    "currency_view",
                                    "Revenue requires foreign-owner asset or liability "
                                    "source presentation.",
                                )
                        posted_ids.update((revenue_id, *result.paid_line_ids))
                        posted_evidence[str(entry.line_id)] = {
                            "revenue_line_id": str(revenue_id),
                            "paid_line_ids": list(map(str, result.paid_line_ids)),
                            "sources": [str(identity) for identity in result.delta.source_ids],
                            "evidence": [
                                [str(identity), digest] for identity, digest in result.evidence
                            ],
                            "movements": [
                                {
                                    "owner": str(item.contract_id),
                                    "layer": item.layer_key,
                                    "kind": item.movement_kind,
                                    "amount": str(item.amount),
                                    "date": None
                                    if item.effective_date is None
                                    else item.effective_date.isoformat(),
                                    "source": item.source_key,
                                    "time": item.time,
                                }
                                for item in result.delta.movements
                            ],
                        }
                    expected_reliefs = {
                        (owner, layer): amount
                        for (recipient, period_id, owner, layer), amount in retained_reliefs.items()
                        if recipient == recognizer and period_id == at.id and amount
                    }
                    if {
                        key: amount for key, amount in posted_reliefs.items() if amount
                    } != expected_reliefs:
                        raise tie_outs.invalid(
                            "currency_view",
                            "Posted revenue owners differ from the retained relief history.",
                        )
                total = sum((entry.flow.amount for entry in entries), ZERO)
                # A verified posting can also create the recognizer's own asset.
                # Its full revenue delta reconciles above; only liability consumption
                # must equal the final retained relief population. Asset creation is
                # never relabelled as opening-liability relief or a member transfer.
                if not verify_period and (
                    total != amounts[source_key] or any(entry.flow.amount < 0 for entry in entries)
                ):
                    raise tie_outs.invalid(
                        "currency_view",
                        "Cross-member revenue requires retained posting-delta replay.",
                    )
                opening[(recognizer, entity, at.id)] = original[source_key]
                liability[(recognizer, entity, at.id)] = (
                    Decimal(signed_liability.numerator) / Decimal(signed_liability.denominator)
                    if verify_period
                    else amounts[source_key]
                )
                consumed.update(sources[source_key])
                evidence[f"{version}:{entity}:{recognizer}:{at.id}"] = {
                    "amount": str(total),
                    "opening_relief": str(original[source_key]),
                    "lines": sorted(str(entry.line_id) for entry in entries),
                    "movements": sorted(map(str, sources[source_key])),
                }
        for owner, recognizer, period_id, amount in cross:
            transfers[(owner, entity, period_id)] -= amount
            transfers[(recognizer, entity, period_id)] += amount
    if params.binding is not None and params.binding.evidence[KEY] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Revenue layer transfers differ from retained evidence."
        )
    if signed:
        if params.binding is not None and params.binding.evidence[signed_key] != signed_evidence:
            raise tie_outs.invalid(
                "currency_view", "Signed revenue sources differ from retained evidence."
            )
        tie_outs.require_members(params, "revenue_signed_layer", signed_members)
        tie_outs.record_members(params, "revenue_signed_layer", signed_members)
        tie_outs.record_evidence(params, signed_key, signed_evidence)
    if verify_postings:
        if params.binding is not None and params.binding.evidence[delta_key] != posted_evidence:
            raise tie_outs.invalid(
                "currency_view", "Posted revenue sources differ from retained evidence."
            )
        tie_outs.require_members(params, "revenue_paid_line", posted_ids)
        tie_outs.record_members(params, "revenue_paid_line", posted_ids)
        tie_outs.record_evidence(params, delta_key, posted_evidence)
    tie_outs.require_members(params, "revenue_transfer_layer", consumed)
    tie_outs.record_members(params, "revenue_transfer_layer", consumed)
    tie_outs.record_evidence(params, KEY, evidence)
    return dict(transfers), opening, liability
