"""Signed revenue sources from retained S12 cumulative calculation traces.

These are cumulative sources, not posted movements. A caller must reconcile the
original target, prior target and paid history before presenting posting deltas.
The source owner is independent of the obligation that recognizes the revenue.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.trace import Trace


class InvalidRevenueTrace(ValueError):
    """Revenue cannot be reproduced from its retained signed sources."""


def input_classes(
    params: Mapping[str, str], count: int, transaction: Fraction, time: Fraction
) -> tuple[bool | None, ...]:
    """Read source classes; None requires exact TIME and finer original source evidence."""
    if "input_classes" not in params:
        if time and time != transaction:
            raise InvalidRevenueTrace(
                "Mixed revenue TIME allocation needs retained component sources."
            )
        return (bool(time),) * count
    classes = params["input_classes"].split("|") if count else []
    if (
        len(classes) != count
        or any(value not in {"TIME", "EVENT", "MIXED"} for value in classes)
        or "time_functional" not in params
        or (not count and params["input_classes"])
    ):
        raise InvalidRevenueTrace(
            "Revenue input classes lack unambiguous retained component sources."
        )
    for index, value in enumerate(classes):
        if value == "MIXED":
            input_time(params, count, index)
    return tuple(None if value == "MIXED" else value == "TIME" for value in classes)


def input_time(params: Mapping[str, str], count: int, index: int) -> tuple[int, int]:
    """Exact signed input TIME amounts retained by S14, in each currency's minor units."""
    try:
        transaction = params["input_time_txn"].split("|")
        functional = params["input_time_functional"].split("|")
        if len(transaction) != count or len(functional) != count:
            raise ValueError("Input count differs.")
        return int(transaction[index]), int(functional[index])
    except (KeyError, ValueError, IndexError) as error:
        raise InvalidRevenueTrace("Mixed input lacks unambiguous retained TIME amounts.") from error


@dataclass(frozen=True, slots=True)
class RevenueSource:
    movement_id: UUID
    contract_id: UUID
    layer_key: str
    movement_kind: str
    amount: Fraction
    effective_date: date | None = None
    source_key: str | None = None
    coefficient: int = 1


_ALLOWED = {
    ("CONTRACT_LIABILITY", "LIABILITY_LAYER_CONSUMED"): {
        "fx.layer.consume.fifo.v1",
        "fx.layer.consume.pro_rata.v1",
        "fx.settlement.spot.v1",
    },
    ("CONTRACT_LIABILITY", "LIABILITY_LAYER_CREATED"): {"fx.layer.create.v1"},
    ("CONTRACT_ASSET", "ASSET_LAYER_CREATED"): {"fx.asset_layer.create.v1"},
    ("CONTRACT_ASSET", "ASSET_LAYER_SETTLED"): {"fx.settlement.spot.v1"},
}


def project(
    trace: Trace,
    node_id: str,
    movements: Sequence[Mapping[Any, Any]],
    *,
    currency: str,
) -> tuple[RevenueSource, ...]:
    """Expand positive relief/asset creation and negative settlement/creation.

    Only signed revenue cumulative nodes may combine leaves. Every intermediate
    sum must reproduce its own value, including zero totals with opposing owners.
    Scope and immutable computation provenance are checked by the caller.
    """
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise InvalidRevenueTrace("Duplicate revenue trace node.")
    leaves: dict[str, Mapping[Any, Any]] = {}
    identities: set[UUID] = set()
    for row in movements:
        if (row["balance_role"], row["movement_kind"]) not in _ALLOWED:
            continue
        key = str(row["trace_node_id"])
        if key in leaves or row["id"] in identities:
            raise InvalidRevenueTrace("Duplicate revenue movement identity.")
        leaves[key] = row
        identities.add(row["id"])
    root = nodes.get(node_id)
    if root is None or root.formula_id != "fx.revenue_functional.v1":
        raise InvalidRevenueTrace("Original revenue cumulative target is unavailable.")
    active: set[str] = set()
    cache: dict[str, dict[str, int]] = {}

    def visit(key: str) -> dict[str, int]:
        if key in active:
            raise InvalidRevenueTrace("Cyclic revenue calculation source.")
        if key in cache:
            return cache[key]
        node = nodes.get(key)
        if node is None or node.currency != currency:
            raise InvalidRevenueTrace("Missing revenue source or mismatched currency.")
        amount = Fraction(node.value)
        if key in leaves:
            row = leaves[key]
            if (
                node.formula_id not in _ALLOWED[(row["balance_role"], row["movement_kind"])]
                or str(row["functional_currency"]).strip() != currency
                or Fraction(row["amount_functional"]) != amount
                or amount < 0
            ):
                raise InvalidRevenueTrace("Revenue movement differs from its retained trace.")
            values = {key: 1}
        else:
            if (
                node.formula_id != "fx.revenue_functional.v1"
                or "signs" not in node.params
                or set(node.params) - {"signs", "minor_unit"}
            ):
                raise InvalidRevenueTrace("Revenue has an unattributed calculation source.")
            signs = node.params["signs"].split("|") if node.inputs else []
            if len(signs) != len(node.inputs) or any(sign not in {"1", "-1"} for sign in signs):
                raise InvalidRevenueTrace("Invalid revenue input signs.")
            active.add(key)
            values = {}
            for child, sign in zip(node.inputs, signs, strict=True):
                if not isinstance(child, str):
                    raise InvalidRevenueTrace("Revenue source must name a retained node.")
                for leaf, value in visit(child).items():
                    values[leaf] = values.get(leaf, 0) + int(sign) * value
            active.remove(key)
        if (
            sum(
                (
                    value * Fraction(leaves[leaf]["amount_functional"])
                    for leaf, value in values.items()
                ),
                Fraction(0),
            )
            != amount
        ):
            raise InvalidRevenueTrace("Signed revenue sources do not reproduce the target.")
        cache[key] = values
        return values

    return tuple(
        RevenueSource(
            movement_id=UUID(str(leaves[key]["id"])),
            contract_id=UUID(str(leaves[key]["contract_id"])),
            layer_key=str(leaves[key]["layer_key"]),
            movement_kind=str(leaves[key]["movement_kind"]),
            amount=coefficient * Fraction(leaves[key]["amount_functional"]),
            effective_date=leaves[key].get("effective_date"),
            source_key=leaves[key].get("source_key"),
            coefficient=coefficient,
        )
        for key, coefficient in sorted(visit(node_id).items())
    )


@dataclass(frozen=True, slots=True)
class RevenueMovement:
    contract_id: UUID
    layer_key: str
    movement_kind: str
    effective_date: date | None
    source_key: str | None
    time: bool
    amount: Fraction


def split_single_origin(
    sources: Sequence[RevenueSource],
    *,
    total: Fraction,
    time: Fraction,
) -> tuple[RevenueMovement, ...]:
    """Split exact TIME/EVENT amounts only when every source has the same provenance."""
    identities = {
        (item.contract_id, item.layer_key, item.movement_kind, item.effective_date, item.source_key)
        for item in sources
    }
    if len(identities) != 1:
        raise InvalidRevenueTrace("Mixed input requires unique original source attribution.")
    identity = next(iter(identities))
    return tuple(
        RevenueMovement(*identity, is_time, amount)
        for is_time, amount in ((True, time), (False, total - time))
        if amount
    )


def split_mixed_sources(
    sources: Sequence[RevenueSource],
    *,
    params: Mapping[str, str],
    count: int,
    index: int,
    subject: str,
    sign: int,
    transaction_amounts: Mapping[UUID, Fraction],
    time_txn: Fraction,
    time_functional: Fraction,
    view: str,
) -> tuple[RevenueMovement, ...]:
    """Use retained period classes without allocating a mixed period across its owners."""
    if sign not in {-1, 1} or view not in {"transaction", "functional"}:
        raise InvalidRevenueTrace("Invalid mixed source projection.")
    identities = {
        (item.contract_id, item.layer_key, item.movement_kind, item.effective_date, item.source_key)
        for item in sources
    }
    if len(identities) == 1:
        total = sign * sum(
            (
                item.coefficient * transaction_amounts[item.movement_id]
                if view == "transaction"
                else item.amount
                for item in sources
            ),
            Fraction(0),
        )
        return split_single_origin(
            sources, total=total, time=time_txn if view == "transaction" else time_functional
        )
    try:
        inputs = json.loads(params["input_period_classes"])
        if not isinstance(inputs, list) or len(inputs) != count:
            raise ValueError("Invalid input count.")
        periods = inputs[index]
        if not isinstance(periods, dict) or any(
            not isinstance(key, str) or value not in {"TIME", "EVENT", "MIXED"}
            for key, value in periods.items()
        ):
            raise ValueError("Invalid period classes.")
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise InvalidRevenueTrace("Mixed sources lack retained period classifications.") from error
    movements = []
    found_time_txn = found_time_functional = Fraction(0)
    for item in sources:
        prefix = subject + "@"
        key = item.source_key
        if key is None or not key.startswith(prefix):
            raise InvalidRevenueTrace("Mixed source does not name its original recognition period.")
        period = key[len(prefix) :]
        classification = periods.get(period)
        if classification not in {"TIME", "EVENT"}:
            raise InvalidRevenueTrace("Mixed recognition period requires finer source attribution.")
        is_time = classification == "TIME"
        transaction = sign * item.coefficient * transaction_amounts[item.movement_id]
        functional = sign * item.amount
        if is_time:
            found_time_txn += transaction
            found_time_functional += functional
        movements.append(
            RevenueMovement(
                item.contract_id,
                item.layer_key,
                item.movement_kind,
                item.effective_date,
                item.source_key,
                is_time,
                transaction if view == "transaction" else functional,
            )
        )
    if found_time_txn != time_txn or found_time_functional != time_functional:
        raise InvalidRevenueTrace("Period sources differ from retained TIME in either currency.")
    return tuple(movements)


@dataclass(frozen=True, slots=True)
class RevenuePostingDelta:
    movements: tuple[RevenueMovement, ...]
    source_ids: tuple[UUID, ...]

    @property
    def amount(self) -> Fraction:
        return sum((item.amount for item in self.movements), Fraction(0))


@dataclass(frozen=True, slots=True)
class RevenueTarget:
    amount: Fraction
    time_amount: Fraction
    movements: tuple[RevenueMovement, ...]
    source_ids: tuple[UUID, ...]


def split_role_target(
    trace: Trace,
    node_id: str,
    movements: Sequence[Mapping[Any, Any]],
    *,
    currency: str,
    txn_scale: int,
    functional_scale: int,
    view: str,
) -> RevenueTarget:
    """Replay the original split formula; attribute only a uniquely owned revenue input."""
    from erev_engine.formulas import FORMULAS

    nodes = {node.id: node for node in trace.nodes}
    node = nodes[node_id]
    if node.formula_id != "post.role_target.v1" or len(node.inputs) != 1:
        raise InvalidRevenueTrace("Split revenue requires one original revenue input.")
    child = node.inputs[0]
    if (
        not isinstance(child, str)
        or not child.startswith(("revenue_cum:", "agent_gross_billing_cum:"))
        or child not in nodes
    ):
        raise InvalidRevenueTrace("Split revenue requires its original cumulative input.")
    functional = "revenue_functional:" + child.split(":", 1)[1]
    sources = project(trace, functional, movements, currency=currency)
    if (
        len(
            {
                (
                    item.contract_id,
                    item.layer_key,
                    item.movement_kind,
                    item.effective_date,
                    item.source_key,
                )
                for item in sources
            }
        )
        != 1
    ):
        raise InvalidRevenueTrace("Split revenue requires unique original source attribution.")
    raw = {item["id"]: item for item in movements}
    transaction = sum(
        (item.coefficient * Fraction(raw[item.movement_id]["amount_txn"]) for item in sources),
        Fraction(0),
    )
    if transaction != Fraction(nodes[child].value):
        raise InvalidRevenueTrace("Split revenue transaction sources do not reconcile.")
    functional_total = sum((item.amount for item in sources), Fraction(0))
    try:
        if int(node.params["minor_unit"]) != txn_scale:
            raise ValueError("Wrong transaction scale.")
        formula = FORMULAS["post.role_target.v1"]
        transaction_share = formula([transaction], node.params)
        functional_share = formula(
            [functional_total],
            {
                **node.params,
                "minor_unit": str(functional_scale),
            },
        )
        if (
            transaction_share != Fraction(node.value)
            or functional_share != Fraction(node.params["amount_functional"]) / 10**functional_scale
        ):
            raise ValueError("Split amounts do not reproduce.")
        time_txn = Fraction(node.params["time"]) / 10**txn_scale
        time_functional = Fraction(node.params["time_functional"]) / 10**functional_scale
        (classification,) = input_classes(node.params, 1, transaction_share, time_txn)
        if classification is not None:
            if (time_txn, time_functional) != (
                (transaction_share, functional_share)
                if classification
                else (Fraction(0), Fraction(0))
            ):
                raise ValueError("Split TIME classification differs from its target.")
        else:
            retained_txn, retained_functional = input_time(node.params, 1, 0)
            if (time_txn, time_functional) != (
                Fraction(retained_txn, 10**txn_scale),
                Fraction(retained_functional, 10**functional_scale),
            ):
                raise ValueError("Split TIME amounts differ from their retained input.")
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise InvalidRevenueTrace(
            "Original split revenue formula or TIME evidence does not reconcile."
        ) from error
    if view not in {"transaction", "functional"}:
        raise InvalidRevenueTrace("Invalid split revenue currency view.")
    amount = transaction_share if view == "transaction" else functional_share
    time = time_txn if view == "transaction" else time_functional
    return RevenueTarget(
        amount,
        time,
        split_single_origin(sources, total=amount, time=time),
        tuple(sorted((item.movement_id for item in sources), key=str)),
    )


def posting_delta(
    current: RevenueTarget,
    previous: RevenueTarget | None,
    *,
    basis: str,
    paid: Sequence[RevenueMovement],
    expected_paid: Fraction,
    expected_delta: Fraction,
) -> RevenuePostingDelta:
    """Apply target − prior target − paid to independently verified source facts.

    All amounts are ledger-signed in one currency. Callers obtain the target
    amounts, TIME components and paid population from original computation and
    posting evidence. Ordinary S14 revenue nodes are in transaction currency;
    functional callers must verify the separately retained functional amounts.
    This function neither converts currencies nor infers source ownership.
    """
    if basis not in {"TIME", "EVENT", "ALL"}:
        raise InvalidRevenueTrace("Unknown revenue posting delta basis.")
    if not isinstance(expected_paid, Fraction) or not isinstance(expected_delta, Fraction):
        raise InvalidRevenueTrace("Revenue delta amounts must be exact.")
    if any(not isinstance(item.amount, Fraction) for item in paid):
        raise InvalidRevenueTrace("Paid revenue attribution must use exact amounts.")
    if sum((item.amount for item in paid), Fraction(0)) != expected_paid:
        raise InvalidRevenueTrace("Attributed history differs from the retained paid amount.")
    if any(basis != "ALL" and item.time != (basis == "TIME") for item in paid):
        raise InvalidRevenueTrace("Paid revenue attribution uses a different posting basis.")
    values: dict[tuple[UUID, str, str, date | None, str | None, bool], Fraction] = {}
    source_ids: set[UUID] = set()

    def add(item: RevenueMovement, sign: int) -> None:
        key = (
            item.contract_id,
            item.layer_key,
            item.movement_kind,
            item.effective_date,
            item.source_key,
            item.time,
        )
        values[key] = values.get(key, Fraction(0)) + sign * item.amount

    for target, sign in ((current, 1), (previous, -1)):
        if target is None:
            continue
        if (
            not isinstance(target.amount, Fraction)
            or not isinstance(target.time_amount, Fraction)
            or any(not isinstance(item.amount, Fraction) for item in target.movements)
            or sum((item.amount for item in target.movements), Fraction(0)) != target.amount
        ):
            raise InvalidRevenueTrace("Revenue sources do not reproduce the retained target.")
        time_amount = sum((item.amount for item in target.movements if item.time), Fraction(0))
        if time_amount != target.time_amount:
            raise InvalidRevenueTrace("Revenue TIME sources differ from the retained component.")
        source_ids.update(target.source_ids)
        for item in target.movements:
            if basis == "ALL" or item.time == (basis == "TIME"):
                add(item, sign)
    for item in paid:
        add(item, -1)
    result = RevenuePostingDelta(
        tuple(
            RevenueMovement(*key, amount)
            for key, amount in sorted(values.items(), key=lambda pair: tuple(map(str, pair[0])))
            if amount
        ),
        tuple(sorted(source_ids, key=str)),
    )
    if result.amount != expected_delta:
        raise InvalidRevenueTrace("Revenue source deltas differ from the retained journal delta.")
    return result
