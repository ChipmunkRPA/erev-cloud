"""Read group acquisition changes from authenticated original computation objects.

The caller must verify the original input/output file hashes and version binding first.
This reader preserves the complete member population; it does not allocate group netting.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from erev_engine.bundle import InputBundle
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject

from . import tie_outs

ROLES = {"CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE"}


def read(
    bundle: InputBundle,
    output: Mapping[str, Any],
    *,
    book: str,
    entity: str,
    period: tie_outs.PeriodRef,
    functional: bool,
) -> dict[str, Any] | None:
    """None means no original revision-27 snapshot; never recompute historical evidence."""
    if (bundle.evidence_revision or 0) < 27:
        return None
    if (
        output.get("input_sha256") != bundle.sha256()
        or output.get("engine_version") != bundle.engine_version
    ):
        raise tie_outs.invalid("currency_view", "Acquisition native computation identity differs.")
    books = [item for item in output["books"] if item["book_code"] == book]
    entities = [item for item in bundle.entities if item.code == entity]
    if len(books) != 1 or len(entities) != 1:
        raise tie_outs.invalid("currency_view", "Acquisition native book/entity is unavailable.")
    original = books[0]
    currency = entities[0].functional_currency if functional else bundle.group.transaction_currency
    view = (
        "FUNCTIONAL"
        if functional and currency != bundle.group.transaction_currency
        else "TRANSACTION"
    )
    rows = [
        item
        for item in original.get("disclosure_rollforwards", ())
        if item["entity"] == entity and item["period_key"] == period.key and item["view"] == view
    ]
    if not rows:
        return None
    if len(rows) != 1:
        raise tie_outs.invalid("currency_view", "Acquisition native snapshot is ambiguous.")
    row = rows[0]
    sources = row.get("acquisition_sources")
    if sources is None:
        return None
    if (
        row["currency"] != currency
        or row["minor_unit"] != bundle.currencies[currency].minor_unit
        or row["unit"] != group_entity_subject_key(bundle.group.group_key, entity)
        or row["closing_date"] != period.end.isoformat()
        or date.fromisoformat(row["opening_date"]).toordinal() + 1 != period.start.toordinal()
    ):
        raise tie_outs.invalid("currency_view", "Acquisition native snapshot scope differs.")
    nodes = {node["id"] for node in original["trace"]["nodes"]}
    events = {event.event_key: event for event in bundle.events}
    voided = {
        event.supersedes_event_key for event in bundle.events if event.event_type == "EVENT_VOIDED"
    }
    totals = dict.fromkeys(ROLES, 0)
    for source in sources:
        amounts = source["amounts"]
        if set(amounts) != ROLES or any(type(value) is not int for value in amounts.values()):
            raise tie_outs.invalid("currency_view", "Acquisition native amounts are invalid.")
        day = date.fromisoformat(source["effective_date"])
        if not period.start <= day <= period.end:
            raise tie_outs.invalid("currency_view", "Acquisition source lies outside its period.")
        if view == "TRANSACTION":
            event = events.get(source.get("event_key"))
            if (
                source.get("kind") != "ORIGINAL_CUTOVER_EVENT"
                or event is None
                or event.event_key in voided
                or event.event_type != "OPENING_BALANCE_ESTABLISHED"
                or event.payload.get("reason") != "BUSINESS_COMBINATION"
                or str(event.payload.get("cutover_date")) != source["effective_date"]
                or not source.get("subjects")
                or any(
                    contract_key_from_subject(subject) != event.contract_key
                    for subject in source["subjects"]
                )
            ):
                raise tie_outs.invalid("currency_view", "Acquisition native event source differs.")
        else:
            movements = [
                move
                for move in original["fx_layer_movements"]
                if move["columns"]["entity"] == entity
                and move["columns"]["layer_key"] == source["layer_key"]
                and move["columns"]["source_key"] == source["source_key"]
                and move["columns"]["movement_kind"] == source["movement_kind"]
                and move["columns"]["effective_date"] == source["effective_date"]
                and move["trace_nodes"]["amount_functional"] == source["trace_node_id"]
            ]
            if (
                source.get("kind") != "ORIGINAL_FX_MOVEMENT"
                or len(movements) != 1
                or source["trace_node_id"] not in nodes
            ):
                raise tie_outs.invalid("currency_view", "Acquisition native FX source differs.")
            movement = movements[0]["columns"]
            sign = (
                -1
                if source["movement_kind"] in {"ASSET_LAYER_SETTLED", "LIABILITY_LAYER_CONSUMED"}
                else 1
            )
            if (
                movement["rate_key"] != source["rate_key"]
                or movement["functional_currency"] != currency
                or sum(amounts.values()) != sign * movement["amount_functional"]
            ):
                raise tie_outs.invalid("currency_view", "Acquisition native FX amount differs.")
        for role, amount in amounts.items():
            totals[role] += amount
    if any(totals[role] != row["lines"][role]["BUSINESS_COMBINATIONS"] for role in ROLES):
        raise tie_outs.invalid("currency_view", "Acquisition native sources do not reconcile.")
    return {
        "unit": row["unit"],
        "entity": entity,
        "period_key": period.key,
        "currency": currency,
        "minor_unit": row["minor_unit"],
        "view": view,
        "members": sorted(bundle.group.member_contract_keys),
        "amounts": totals,
        "sources": sources,
    }
