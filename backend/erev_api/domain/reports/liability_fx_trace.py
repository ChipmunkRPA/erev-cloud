"""Resolve signed cumulative liability FX targets into retained source layers.

A target is not a journal delta. Callers must subtract the prior target and the
attributed posted history before using this projection as a period movement.
No proportional allocation, live rate lookup or residual bucket is permitted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_engine.trace import Trace


class InvalidLiabilityTrace(ValueError):
    """The retained target cannot be explained by its retained liability layers."""


@dataclass(frozen=True, slots=True)
class LayerSource:
    movement_id: UUID
    contract_id: UUID
    layer_key: str
    effective_date: date
    closing: bool
    amount: Decimal
    created_on: date | None = None


@dataclass(frozen=True, slots=True)
class Target:
    node_id: str
    currency: str
    sources: tuple[LayerSource, ...]

    @property
    def amount(self) -> Decimal:
        return sum((item.amount for item in self.sources), Decimal(0))

    def by_owner(self) -> dict[UUID, Decimal]:
        result: dict[UUID, Decimal] = {}
        for item in self.sources:
            result[item.contract_id] = result.get(item.contract_id, Decimal(0)) + item.amount
        return result


def project(
    trace: Trace,
    node_id: str,
    movements: Sequence[Mapping[str, Any]],
    *,
    currency: str,
) -> Target:
    """Expand a retained S14 role target through S12's signed cumulative sums.

    Only persisted liability remeasurements may terminate the graph. Each sum
    reconciles independently, so an omitted/corrupt child cannot hide in a net
    zero root. Zero targets with no sources are valid; unknown formulas are not.
    The caller scopes movements to the same immutable version and entity.
    """
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise InvalidLiabilityTrace("Duplicate calculation node identity.")
    leaves: dict[str, Mapping[str, Any]] = {}
    for item in movements:
        if (
            item["balance_role"] != "CONTRACT_LIABILITY"
            or item["movement_kind"] != "LIABILITY_LAYER_REMEASURED"
        ):
            continue
        key = str(item["trace_node_id"])
        if key in leaves:
            raise InvalidLiabilityTrace("Duplicate liability movement trace identity.")
        leaves[key] = item
    root = nodes.get(node_id)
    if root is None or root.formula_id != "post.role_target.v1":
        raise InvalidLiabilityTrace("Liability posting target is unavailable.")
    active: set[str] = set()
    cached: dict[str, dict[str, Decimal]] = {}

    def visit(key: str) -> dict[str, Decimal]:
        if key in active:
            raise InvalidLiabilityTrace("Cycle in liability FX calculation.")
        if key in cached:
            return cached[key]
        node = nodes.get(key)
        if node is None or node.currency != currency:
            raise InvalidLiabilityTrace("Liability FX node is missing or has another currency.")
        amount = Decimal(node.value)
        if not amount.is_finite():
            raise InvalidLiabilityTrace("Non-finite liability FX target.")
        leaf = leaves.get(key)
        if leaf is not None:
            if (
                str(leaf["functional_currency"]).strip() != currency
                or Decimal(leaf["amount_functional"]) != amount
            ):
                raise InvalidLiabilityTrace("Liability movement differs from its retained trace.")
            result = {key: amount}
        else:
            if node.formula_id not in {"post.role_target.v1", "fx.gain_loss.sum.v1"}:
                raise InvalidLiabilityTrace(
                    "Liability target has an unattributed calculation source."
                )
            # Split targets need their explicit apportionment semantics; treating
            # them as an ordinary signed sum would silently change ownership.
            if set(node.params) - {"signs", "time", "amount_functional", "minor_unit"}:
                raise InvalidLiabilityTrace(
                    "Liability target requires unsupported split attribution."
                )
            signs = node.params.get("signs", "").split("|") if node.inputs else []
            if len(signs) != len(node.inputs) or any(sign not in {"1", "-1"} for sign in signs):
                raise InvalidLiabilityTrace("Liability target has invalid input signs.")
            active.add(key)
            result = {}
            for child, sign in zip(node.inputs, signs, strict=True):
                if not isinstance(child, str):
                    raise InvalidLiabilityTrace(
                        "Liability target contains an unresolved source reference."
                    )
                for source, value in visit(child).items():
                    result[source] = result.get(source, Decimal(0)) + int(sign) * value
            active.remove(key)
        if sum(result.values(), Decimal(0)) != amount:
            raise InvalidLiabilityTrace("Liability target differs from its signed layer sources.")
        cached[key] = result
        return result

    values = visit(node_id)
    return Target(
        node_id,
        currency,
        tuple(
            LayerSource(
                UUID(str(leaves[key]["id"])),
                UUID(str(leaves[key]["contract_id"])),
                str(leaves[key]["layer_key"]),
                leaves[key]["effective_date"],
                nodes[key].formula_id == "fx.remeasure.closing.v1",
                amount,
                leaves[key].get("created_on"),
            )
            for key, amount in sorted(values.items())
        ),
    )


@dataclass(frozen=True, slots=True)
class LayerDelta:
    contract_id: UUID
    layer_key: str
    effective_date: date
    closing: bool
    amount: Decimal
    created_on: date | None = None


@dataclass(frozen=True, slots=True)
class PostingDelta:
    node_id: str
    currency: str
    movements: tuple[LayerDelta, ...]
    source_ids: tuple[UUID, ...]
    paid_line_ids: tuple[UUID, ...] = ()
    evidence: tuple[tuple[UUID, str], ...] = ()

    @property
    def amount(self) -> Decimal:
        return sum((item.amount for item in self.movements), Decimal(0))


def posting_delta(
    trace: Trace,
    node_id: str,
    movements: Sequence[Mapping[str, Any]],
    *,
    currency: str,
    minor_unit: int,
    paid: Sequence[LayerDelta],
) -> PostingDelta:
    """Apply S14's target/prior/paid equation to source-layer amounts.

    ``paid`` must be the attributed ledger population selected by the retained
    delta's posted source (including carried locked periods). Its total must
    equal that source. This function never invents ownership for an aggregate
    paid amount. Both target time components and the final delta are checked.
    """
    from erev_engine.trace import SourceRef

    nodes = {node.id: node for node in trace.nodes}
    node = nodes.get(node_id)
    if node is None or node.formula_id != "post.delta.v1" or node.currency != currency:
        raise InvalidLiabilityTrace("Liability posting delta is unavailable.")
    previous = node.params.get("previous")
    basis = node.params.get("class")
    if previous not in {"true", "false"} or basis not in {"TIME", "EVENT", "ALL"}:
        raise InvalidLiabilityTrace("Unknown liability posting delta basis.")
    count = 3 if previous == "true" else 2
    if len(node.inputs) != count or any(not isinstance(item, str) for item in node.inputs[:-1]):
        raise InvalidLiabilityTrace("Invalid liability posting delta sources.")
    source = node.inputs[-1]
    if (
        not isinstance(source, SourceRef)
        or source.ref_type != "source_record"
        or not source.ref_id.startswith("posted/")
    ):
        raise InvalidLiabilityTrace("Liability delta has no retained posted source.")
    expected_paid = Decimal(source.detail.get("value", "NaN"))
    if (
        not expected_paid.is_finite()
        or any(not item.amount.is_finite() for item in paid)
        or sum((item.amount for item in paid), Decimal(0)) != expected_paid
    ):
        raise InvalidLiabilityTrace(
            "Attributed posted layers differ from the retained paid amount."
        )
    sources: set[UUID] = set()
    values: dict[tuple[UUID, str, date, bool, date | None], Decimal] = {}

    def add(item: LayerSource | LayerDelta, sign: int) -> None:
        key = (item.contract_id, item.layer_key, item.effective_date, item.closing, item.created_on)
        values[key] = values.get(key, Decimal(0)) + sign * item.amount

    for index, target_id in enumerate(node.inputs[:-1]):
        assert isinstance(target_id, str)
        target = project(trace, target_id, movements, currency=currency)
        time = sum((item.amount for item in target.sources if item.closing), Decimal(0))
        held_time = Decimal(node.params.get("time" if index == 0 else "time_previous", "NaN"))
        if not held_time.is_finite() or time != held_time.scaleb(-minor_unit):
            raise InvalidLiabilityTrace(
                "Liability TIME sources differ from the retained posting component."
            )
        for item in target.sources:
            sources.add(item.movement_id)
            if basis == "ALL" or (item.closing if basis == "TIME" else not item.closing):
                add(item, 1 if index == 0 else -1)
    for paid_item in paid:
        add(paid_item, -1)
    result = PostingDelta(
        node_id,
        currency,
        tuple(
            LayerDelta(*key[:4], amount, key[4])
            for key, amount in sorted(values.items(), key=lambda item: tuple(map(str, item[0])))
            if amount
        ),
        tuple(sorted(sources, key=str)),
    )
    if not Decimal(node.value).is_finite() or result.amount != Decimal(node.value):
        raise InvalidLiabilityTrace(
            "Liability source deltas differ from the retained journal delta."
        )
    return result


def from_pass(
    document: Mapping[str, Any],
    *,
    delta_node_id: str,
    entity_code: str,
    owners: Mapping[str, UUID],
    paid: Sequence[LayerDelta],
) -> PostingDelta:
    """Attribute a verified close-pass document using retained FX movement owners.

    ``owners`` maps the authorized group's natural contract keys to persistent
    identities. Movement identities are scoped to this immutable evidence record;
    they do not pretend to be contract-version movement rows.
    """
    from uuid import uuid5

    from erev_engine import upgrade
    from erev_engine.canonical import canonical_bytes
    from erev_engine.money import minor_to_decimal

    from erev_api.explain.store import trace_from_row

    bundle = upgrade.decode_input(canonical_bytes(document["input"]))
    entity = next((item for item in bundle.entities if item.code == entity_code), None)
    if entity is None:
        raise InvalidLiabilityTrace("The close-pass input does not include this entity.")
    currency = entity.functional_currency
    trace = trace_from_row({"id": document["id"], **document["trace_record"]})
    evidence_id = UUID(str(document["id"]))
    creations = {
        (item["columns"]["contract_key"], item["columns"]["layer_key"]): item["columns"]
        for item in document["book_output"]["fx_layer_movements"]
        if item["columns"]["entity"] == entity_code
        and item["columns"]["movement_kind"] == "LIABILITY_LAYER_CREATED"
    }
    movements = []
    for item in document["book_output"]["fx_layer_movements"]:
        values = item["columns"]
        if (
            values["entity"] != entity_code
            or values["movement_kind"] != "LIABILITY_LAYER_REMEASURED"
        ):
            continue
        owner = owners.get(values["contract_key"])
        if owner is None or values["contract_key"] not in bundle.group.member_contract_keys:
            raise InvalidLiabilityTrace("Liability source has no authorized member owner.")
        creation = creations.get((values["contract_key"], values["layer_key"]))
        if creation is None:
            raise InvalidLiabilityTrace("Liability remeasurement has no retained creation source.")
        node_id = item["trace_nodes"]["amount_functional"]
        movements.append(
            {
                **values,
                "id": uuid5(evidence_id, node_id),
                "contract_id": owner,
                "trace_node_id": node_id,
                "effective_date": date.fromisoformat(values["effective_date"]),
                "created_on": date.fromisoformat(creation["effective_date"]),
                "amount_functional": minor_to_decimal(
                    values["amount_functional"], bundle.currencies[currency].minor_unit
                ),
            }
        )
    result = posting_delta(
        trace,
        delta_node_id,
        movements,
        currency=currency,
        minor_unit=bundle.currencies[currency].minor_unit,
        paid=paid,
    )
    return replace(result, evidence=((evidence_id, str(document["sha256"])),))
