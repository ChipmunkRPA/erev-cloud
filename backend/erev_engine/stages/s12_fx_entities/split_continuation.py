"""Effective foreign split scopes, with original source layers and gross carry-forward."""

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any, cast

from erev_engine import dates, money
from erev_engine.combination_membership import validate_partition
from erev_engine.split_fx_layers import OpenLayer, allocate
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s12_fx_entities.layers import (
    CONTRACT_ASSET,
    CONTRACT_LIABILITY,
    ControlFlow,
    Layer,
    Piece,
    UnitBook,
)
from erev_engine.stages.s12_fx_entities.rates import RateView, to_functional
from erev_engine.stages.state import AllocatedState, EventView, Target


@dataclass
class Credit:
    key: str
    source: str
    contract: str
    created: date
    quantity: int
    functional: int
    node: str
    rate: RateView


class SplitManager:
    def __init__(self, book: UnitBook, state: AllocatedState, balances: Any) -> None:
        self.book, self.state, self.source = book, state, balances
        self.membership = {c.header.external_id: state.group_code for c in state.contracts}
        self.scopes: dict[str, str] = {}
        self.origins: dict[str, tuple[str, date]] = {}
        self.credit_of: dict[str, str] = {}
        self.credits: list[Credit] = []
        self.positions: dict[str, int] = defaultdict(int)
        self.position_inputs: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self.active = state.group_code
        self.before: set[str] = set()
        self.member_shares: list[Target] = []
        self.applied_flows: list[ControlFlow] = []
        self.applied = False
        self.parents: dict[str, str] = {}

    def begin(self, flow: ControlFlow) -> None:
        self.active = self.membership[flow.contract_key]
        self.before = set(self.book.layers)

    def eligible(self, role: str) -> list[Layer]:
        return [
            layer
            for key, layer in self.book.layers.items()
            if layer.role == role
            and layer.txn_open > 0
            and self.scopes.get(key, self.state.group_code) == self.active
        ]

    def finish(self, flow: ControlFlow, when: date, pieces: list[Piece]) -> None:
        self.applied_flows.append(flow)
        self.positions[flow.contract_key] += flow.amount if flow.side == "CREDIT" else -flow.amount
        if pieces:
            self.position_inputs[flow.contract_key].extend(
                (
                    piece.node_id,
                    (flow.amount if flow.side == "CREDIT" else -flow.amount) if i == 0 else 0,
                )
                for i, piece in enumerate(pieces)
            )
        credit = None
        if flow.side == "CREDIT":
            node = self.book.tb.node(
                measure="fx_split_credit_basis",
                subject_key=flow.flow_key,
                period_key=None,
                value=sum(p.amount for p in pieces),
                currency=self.book.fn,
                minor_unit=self.book.mu_fn,
                formula_id="rec.activity_sum.v1",
                inputs=[p.node_id for p in pieces],
                params={"signs": ",".join("+" for _ in pieces)},
                narrative_key="rec.activity_sum",
            )
            credit = Credit(
                flow.flow_key,
                flow.source_key,
                flow.contract_key,
                when,
                flow.amount,
                sum(p.amount for p in pieces),
                node,
                self.book.rates.spot(when),
            )
            self.credits.append(credit)
        for key in self.book.layers.keys() - self.before:
            layer = self.book.layers[key]
            if layer.role not in {CONTRACT_ASSET, CONTRACT_LIABILITY}:
                continue
            self.scopes[key] = self.active
            self.origins[key] = (flow.source_key, when)
            if layer.role == CONTRACT_LIABILITY and credit is not None:
                self.credit_of[key] = credit.key

    def quantity_node(self, key: str, parts: list[tuple[str, int]], period: str) -> str:
        return self.book.tb.node(
            measure="fx_split_open_quantity",
            subject_key=key,
            period_key=period,
            value=sum(amount for _, amount in parts),
            currency=self.book.txn,
            minor_unit=self.book.mu_txn,
            formula_id="fx.split_open_txn.v1",
            inputs=[node for node, _ in parts],
            params={"transaction_deltas": "|".join(str(amount) for _, amount in parts)},
            narrative_key="fx.split_open_txn",
        )

    def carrying_node(self, layer: Layer, event: EventView) -> tuple[str, str]:
        moves = [m for m in self.book.movements if m.layer_key == layer.key]
        signs = {
            "LIABILITY_LAYER_CREATED": 1,
            "ASSET_LAYER_CREATED": 1,
            "LIABILITY_LAYER_CONSUMED": -1,
            "ASSET_LAYER_SETTLED": -1,
            "LIABILITY_LAYER_REMEASURED": 1,
            "ASSET_LAYER_REMEASURED": 1,
        }
        value = sum(signs[m.movement_kind] * m.amount_functional for m in moves)
        if value != layer.fn_carrying:
            raise ValueError("Split original layer carrying does not reconcile")
        period = self.book.period(event.effective_date).period_key
        fn = self.book.tb.node(
            measure="fx_split_original_carrying",
            subject_key=layer.key + "@" + event.event_key,
            period_key=period,
            value=value,
            currency=self.book.fn,
            minor_unit=self.book.mu_fn,
            formula_id="rec.activity_sum.v1",
            inputs=[m.trace_node_id for m in moves],
            params={"signs": ",".join("+" if signs[m.movement_kind] > 0 else "-" for m in moves)},
            narrative_key="rec.activity_sum",
        )
        txn_parts = [
            (m.trace_node_id, signs[m.movement_kind] * m.amount_txn)
            for m in moves
            if not m.movement_kind.endswith("REMEASURED")
        ]
        if sum(v for _, v in txn_parts) != layer.txn_open:
            raise ValueError("Split original layer quantity does not reconcile")
        txn = self.quantity_node(layer.key + "@" + event.event_key, txn_parts, period)
        return fn, txn

    def revalue(self, layers: list[Layer], event: EventView) -> None:
        spot = self.book.rates.spot(event.effective_date)
        period = self.book.period(event.effective_date)
        for layer in layers:
            if layer.role == CONTRACT_LIABILITY and not self.book.cl_monetary(
                event.effective_date, layer.contract_key
            ):
                continue
            target = to_functional(layer.txn_open, spot, self.book.mu_txn, self.book.mu_fn)
            delta = target - layer.fn_carrying
            if not delta:
                continue
            node = self.book.tb.node(
                measure="fx_split_asset_remeasured",
                subject_key=layer.key + "@" + event.event_key,
                period_key=period.period_key,
                value=delta,
                currency=self.book.fn,
                minor_unit=self.book.mu_fn,
                formula_id="fx.remeasure.closing.v1",
                inputs=spot.inputs(),
                params={
                    **self.book.conversion_params(layer.txn_open, spot, event.effective_date),
                    "carrying_before": str(layer.fn_carrying),
                },
                narrative_key="fx.remeasure.closing",
            )
            self.book.move(
                layer.key,
                layer.role,
                "ASSET_LAYER_REMEASURED"
                if layer.role == CONTRACT_ASSET
                else "LIABILITY_LAYER_REMEASURED",
                event.effective_date,
                layer.txn_open,
                delta,
                spot,
                event.event_key,
                "SETTLEMENT",
                node,
            )
            self.book.remeasured(
                "JET-10a" if layer.role == CONTRACT_ASSET else "JET-10b",
                layer.role,
                Piece(node, delta, spot, layer.key),
            )
            layer.fn_carrying = target

    def restore(self, quantity: int, scope: str, event: EventView) -> list[Layer]:
        if not quantity:
            return []
        available = []
        for credit in self.credits:
            used = sum(
                layer.txn_open
                for key, layer in self.book.layers.items()
                if layer.role == CONTRACT_LIABILITY and self.credit_of.get(key) == credit.key
            )
            if used > credit.quantity:
                raise ValueError("Historical credit source is overallocated")
            available.append(credit.quantity - used)
        if sum(available) < quantity:
            raise ValueError("Newly exposed split liabilities lack original credit sources")
        policy = str(
            self.book.ctx.policies.value(
                "fx.cl_layer_consumption",
                entity=self.book.entity,
                period=self.book.period(event.effective_date).period_key,
            )
        )
        if policy == "PRO_RATA":
            takes = money.largest_remainder(
                quantity, [Fraction(v) for v in available], [c.key for c in self.credits]
            )
        else:
            left = quantity
            takes = []
            for capacity in available:
                take = min(left, capacity)
                takes.append(take)
                left -= take
        result = []
        for credit, capacity, take in zip(self.credits, available, takes, strict=True):
            if not take:
                continue
            before = credit.quantity - capacity
            fn = money.cumulative_posted(
                Fraction(credit.functional, 10**self.book.mu_fn),
                credit.functional,
                Fraction(before + take, credit.quantity),
                self.book.mu_fn,
            ) - money.cumulative_posted(
                Fraction(credit.functional, 10**self.book.mu_fn),
                credit.functional,
                Fraction(before, credit.quantity),
                self.book.mu_fn,
            )
            for role in (CONTRACT_LIABILITY, CONTRACT_ASSET):
                key = self.book.new_key(role, event.event_key + "~restore~" + credit.key)
                node = self.book.tb.node(
                    measure="fx_split_restored",
                    subject_key=key,
                    period_key=self.book.period(event.effective_date).period_key,
                    value=fn,
                    currency=self.book.fn,
                    minor_unit=self.book.mu_fn,
                    formula_id="fx.split_restore.v1",
                    inputs=[credit.node],
                    params={
                        "original_quantity": str(credit.quantity),
                        "previous_quantity": str(before),
                        "take": str(take),
                        "amount_txn": str(take),
                        "effective_date": event.effective_date.isoformat(),
                        "original_created_on": credit.created.isoformat(),
                        "original_source_key": credit.source,
                        "rate": credit.rate.text,
                        "txn_minor_unit": str(self.book.mu_txn),
                    },
                    narrative_key="fx.split_restore",
                )
                layer = Layer(
                    key, role, None, take, take, fn, fn, credit.rate, node, credit.contract
                )
                self.book.layers[key] = layer
                self.scopes[key] = scope
                self.origins[key] = (credit.source, credit.created)
                if role == CONTRACT_LIABILITY:
                    self.credit_of[key] = credit.key
                self.book.move(
                    key,
                    role,
                    "LIABILITY_LAYER_CREATED"
                    if role == CONTRACT_LIABILITY
                    else "ASSET_LAYER_CREATED",
                    event.effective_date,
                    take,
                    fn,
                    credit.rate,
                    event.event_key,
                    None,
                    node,
                )
                result.append(layer)
        return result

    def split(self, event: EventView) -> None:
        destinations = {
            str(k): str(v)
            for k, v in cast(
                Mapping[str, object], event.payload["prospective_split_destinations"]
            ).items()
        }
        scope = validate_partition(self.membership, destinations)
        quotas: dict[str, int] = defaultdict(int)
        for member, destination in destinations.items():
            quotas[destination] += self.positions[member]
        pool = [
            layer
            for key, layer in self.book.layers.items()
            if layer.txn_open > 0
            and layer.role in {CONTRACT_ASSET, CONTRACT_LIABILITY}
            and self.scopes.get(key, self.state.group_code) == scope
        ]
        desired = {
            CONTRACT_LIABILITY: {k: max(0, v) for k, v in quotas.items()},
            CONTRACT_ASSET: {k: max(0, -v) for k, v in quotas.items()},
        }
        present = {
            role: sum(source_layer.txn_open for source_layer in pool if source_layer.role == role)
            for role in desired
        }
        extra = sum(desired[CONTRACT_LIABILITY].values()) - present[CONTRACT_LIABILITY]
        if extra < 0 or sum(desired[CONTRACT_ASSET].values()) - present[CONTRACT_ASSET] != extra:
            raise ValueError("Split destinations do not reconcile with original control positions")
        self.revalue(pool, event)
        restored = self.restore(extra, scope, event)
        self.revalue(restored, event)
        pool.extend(restored)
        period = self.book.period(event.effective_date).period_key
        for role, targets in desired.items():
            own = sorted(
                (source_layer for source_layer in pool if source_layer.role == role),
                key=lambda source_layer: (self.origins[source_layer.key][1], source_layer.key),
            )
            if not own:
                continue
            bases = {layer.key: self.carrying_node(layer, event) for layer in own}
            quota_nodes = []
            for destination in sorted(targets):
                selected = [
                    member for member in destinations if destinations[member] == destination
                ]
                parts = [part for member in selected for part in self.position_inputs[member]]
                np_node = self.quantity_node(
                    event.event_key + "@" + destination + "#" + role, parts, period
                )
                quota_nodes.append(
                    self.book.tb.node(
                        measure="fx_split_destination_quantity",
                        subject_key=event.event_key + "@" + destination + "#" + role,
                        period_key=period,
                        value=targets[destination],
                        currency=self.book.txn,
                        minor_unit=self.book.mu_txn,
                        formula_id="fx.split_position.v1",
                        inputs=[np_node],
                        params={"role": role},
                        narrative_key="fx.split_position",
                    )
                )
            originals = [
                OpenLayer(
                    source_layer.key,
                    source_layer.contract_key,
                    self.origins[source_layer.key][0],
                    self.origins[source_layer.key][1],
                    source_layer.created_node,
                    source_layer.rate,
                    source_layer.txn_open,
                    source_layer.fn_carrying,
                )
                for source_layer in own
            ]
            shares = allocate(originals, targets, effective_date=event.effective_date)
            by_layer = defaultdict(list)
            for share in shares:
                by_layer[share.original.layer_key].append(share)
            for row, layer in enumerate(own):
                fn_node, txn_node = bases[layer.key]
                original_quantity, original_fn = layer.txn_open, layer.fn_carrying
                moved = self.book.tb.node(
                    measure="fx_split_transferred",
                    subject_key=layer.key + "@" + event.event_key,
                    period_key=period,
                    value=original_fn,
                    currency=self.book.fn,
                    minor_unit=self.book.mu_fn,
                    formula_id="rec.activity_sum.v1",
                    inputs=[fn_node],
                    params={"signs": "+"},
                    narrative_key="rec.activity_sum",
                )
                self.book.move(
                    layer.key,
                    role,
                    "LIABILITY_LAYER_CONSUMED"
                    if role == CONTRACT_LIABILITY
                    else "ASSET_LAYER_SETTLED",
                    event.effective_date,
                    original_quantity,
                    original_fn,
                    layer.rate,
                    event.event_key,
                    None,
                    moved,
                )
                layer.txn_open = layer.fn_carrying = 0
                share_nodes = []
                for col, destination in enumerate(sorted(targets)):
                    amount = next(
                        (s.txn_open for s in by_layer[layer.key] if s.destination == destination), 0
                    )
                    share_nodes.append(
                        self.book.tb.node(
                            measure="fx_split_quantity_share",
                            subject_key=layer.key + "@" + event.event_key + "#" + destination,
                            period_key=period,
                            value=amount,
                            currency=self.book.txn,
                            minor_unit=self.book.mu_txn,
                            formula_id="fx.split_quota.v1",
                            inputs=[bases[source_layer.key][1] for source_layer in own]
                            + quota_nodes,
                            params={
                                "rows": str(len(own)),
                                "row": str(row),
                                "column": str(col),
                                "keys": json.dumps(sorted(targets)),
                            },
                            narrative_key="fx.split_quota",
                        )
                    )
                for share in by_layer[layer.key]:
                    index = sorted(targets).index(share.destination)
                    key = self.book.new_key(
                        role, layer.key + "~split~" + event.event_key + "~" + share.destination
                    )
                    node = self.book.tb.node(
                        measure="fx_split_layer_created",
                        subject_key=key,
                        period_key=period,
                        value=share.fn_carrying,
                        currency=self.book.fn,
                        minor_unit=self.book.mu_fn,
                        formula_id="alloc.largest_remainder.v1",
                        inputs=[fn_node, *share_nodes],
                        params={
                            "index": str(index),
                            "keys": ",".join(
                                str(i).zfill(len(str(len(targets)))) for i in range(len(targets))
                            ),
                            "amount_txn": str(share.txn_open),
                            "effective_date": event.effective_date.isoformat(),
                            "original_created_on": self.origins[layer.key][1].isoformat(),
                            "original_source_key": self.origins[layer.key][0],
                            "origin_layer_key": layer.key,
                            "rate": layer.rate.text,
                            "txn_minor_unit": str(self.book.mu_txn),
                        },
                        narrative_key="alloc.largest_remainder",
                    )
                    child = Layer(
                        key,
                        role,
                        None,
                        share.txn_open,
                        share.txn_open,
                        share.fn_carrying,
                        share.fn_carrying,
                        layer.rate,
                        node,
                        layer.contract_key,
                    )
                    self.book.layers[key] = child
                    self.parents[key] = layer.key
                    self.scopes[key] = share.destination
                    self.origins[key] = self.origins[layer.key]
                    if layer.key in self.credit_of:
                        self.credit_of[key] = self.credit_of[layer.key]
                    self.book.move(
                        key,
                        role,
                        "LIABILITY_LAYER_CREATED"
                        if role == CONTRACT_LIABILITY
                        else "ASSET_LAYER_CREATED",
                        event.effective_date,
                        share.txn_open,
                        share.fn_carrying,
                        layer.rate,
                        event.event_key,
                        None,
                        node,
                    )
        self.membership.update(destinations)
        self.applied = True

    def capture(self, period: dates.PeriodLike) -> None:
        if not self.applied or self.book.fn == self.book.txn:
            return
        members = [
            t
            for t in self.source.member_balances
            if t.entity == self.book.entity
            and t.period_key == period.period_key
            and t.measure == "contract_liability"
        ]
        groups = defaultdict(list)
        names = {
            contract_entity_subject_key(member, self.book.entity): member
            for member in self.membership
        }
        for target in members:
            groups[self.membership[names[target.subject_key]]].append(target)
        for scope, own in groups.items():
            layers = [
                source_layer
                for key, source_layer in self.book.layers.items()
                if source_layer.role == CONTRACT_LIABILITY
                and source_layer.txn_open
                and self.scopes.get(key, self.state.group_code) == scope
            ]
            if sum(source_layer.txn_open for source_layer in layers) != sum(t.value for t in own):
                raise ValueError("Destination FX layers differ from native member liabilities")
            amount = sum(source_layer.fn_carrying for source_layer in layers)
            inputs = [
                m.trace_node_id
                for m in self.book.movements
                if m.layer_key in {source_layer.key for source_layer in layers}
            ]
            signs = {
                "LIABILITY_LAYER_CREATED": "+",
                "LIABILITY_LAYER_CONSUMED": "-",
                "LIABILITY_LAYER_REMEASURED": "+",
            }
            basis = self.book.tb.node(
                measure="fx_split_destination_carrying",
                subject_key=self.state.group_code + "/split/" + scope + "@" + self.book.entity,
                period_key=period.period_key,
                value=amount,
                currency=self.book.fn,
                minor_unit=self.book.mu_fn,
                formula_id="rec.activity_sum.v1",
                inputs=inputs,
                params={
                    "signs": ",".join(
                        signs[m.movement_kind]
                        for m in self.book.movements
                        if m.layer_key in {source_layer.key for source_layer in layers}
                    )
                },
                narrative_key="rec.activity_sum",
            )
            keys = [t.subject_key for t in own]
            shares = (
                money.largest_remainder(amount, [Fraction(t.value) for t in own], keys)
                if amount
                else [0] * len(own)
            )
            total_targets = []
            for index, (target, share) in enumerate(zip(own, shares, strict=True)):
                node = self.book.tb.node(
                    measure="split_contract_liability_functional",
                    subject_key=target.subject_key,
                    period_key=period.period_key,
                    value=share,
                    currency=self.book.fn,
                    minor_unit=self.book.mu_fn,
                    formula_id="alloc.largest_remainder.v1" if amount else "rec.activity_sum.v1",
                    inputs=[basis, *[t.node_id for t in own]] if amount else [],
                    params={"index": str(index), "keys": ",".join(keys)}
                    if amount
                    else {"signs": ""},
                    narrative_key="alloc.largest_remainder" if amount else "rec.activity_sum",
                )
                total_targets.append(
                    Target(
                        self.book.ctx.book_code,
                        self.book.entity,
                        target.subject_key,
                        "split_contract_liability_functional",
                        period.period_key,
                        None,
                        share,
                        None,
                        node,
                    )
                )

            self.member_shares.extend(total_targets)
            current = [
                t
                for t in self.source.member_balances
                if t.measure == "contract_liability_current"
                and (t.entity, t.period_key) == (self.book.entity, period.period_key)
                and t.subject_key in keys
            ]
            if len(current) != len(own):
                raise ValueError("Split current classification lacks complete member quantities")
            from .current_layers import classify

            snapshots: list[dict[str, Any]] = [
                {
                    "layer_key": source_layer.key,
                    "txn_open": source_layer.txn_open,
                    "functional_carrying": source_layer.fn_carrying,
                    "monetary": self.book.cl_monetary(period.end_date, source_layer.contract_key),
                    "movements": [
                        {
                            "kind": m.movement_kind,
                            "amount_txn": m.amount_txn,
                            "amount_functional": m.amount_functional,
                        }
                        for m in self.book.movements
                        if m.layer_key == source_layer.key
                    ],
                }
                for source_layer in layers
            ]
            policy = str(
                self.book.ctx.policies.value(
                    "fx.cl_layer_consumption", entity=self.book.entity, period=period.period_key
                )
            )
            # Select the same transaction portions as revenue relief, then value
            # each source under its own retained historical/monetary policy.
            qty = sum(t.value for t in current)
            selection = classify(
                snapshots, qty, policy=policy, minor_unit=self.book.mu_fn, monetary=True
            )
            selected = {p["layer_key"]: int(p["current_txn"]) for p in selection}
            value = sum(
                int(
                    classify(
                        [source_layer],
                        selected[source_layer["layer_key"]],
                        policy="FIFO",
                        minor_unit=self.book.mu_fn,
                        monetary=source_layer["monetary"],
                    )[0]["current_functional"]
                )
                for source_layer in snapshots
            )
            current_basis = self.book.tb.node(
                measure="fx_split_destination_current",
                subject_key=self.state.group_code + "/split/" + scope + "@" + self.book.entity,
                period_key=period.period_key,
                value=value,
                currency=self.book.fn,
                minor_unit=self.book.mu_fn,
                formula_id="fx.split_current.v1",
                inputs=[t.node_id for t in current] + inputs,
                params={
                    "quantity_count": str(len(current)),
                    "policy": policy,
                    "txn_minor_unit": str(self.book.mu_txn),
                    "layers": json.dumps(snapshots, sort_keys=True, separators=(",", ":")),
                },
                narrative_key="fx.split_current",
            )
            allocations = (
                money.largest_remainder(value, [Fraction(t.value) for t in total_targets], keys)
                if value
                else [0] * len(own)
            )
            for index, (target, share) in enumerate(zip(own, allocations, strict=True)):
                node = self.book.tb.node(
                    measure="split_contract_liability_current_functional",
                    subject_key=target.subject_key,
                    period_key=period.period_key,
                    value=share,
                    currency=self.book.fn,
                    minor_unit=self.book.mu_fn,
                    formula_id="alloc.largest_remainder.v1" if value else "rec.activity_sum.v1",
                    inputs=[current_basis, *[t.node_id for t in total_targets]] if value else [],
                    params={"index": str(index), "keys": ",".join(keys)}
                    if value
                    else {"signs": ""},
                    narrative_key="alloc.largest_remainder" if value else "rec.activity_sum",
                )
                self.member_shares.append(
                    Target(
                        self.book.ctx.book_code,
                        self.book.entity,
                        target.subject_key,
                        "split_contract_liability_current_functional",
                        period.period_key,
                        None,
                        share,
                        None,
                        node,
                    )
                )
