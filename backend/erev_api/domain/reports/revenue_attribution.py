"""Replay ordinary revenue lines from original functional targets and paid history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid5

from erev_engine import upgrade
from erev_engine.canonical import canonical_bytes
from erev_engine.money import minor_to_decimal
from erev_engine.trace import SourceRef
from sqlalchemy import select

from erev_api.db.tables import contract, legal_entity, period, subledger_line
from erev_api.domain.close.pass_evidence import LINE_FIELDS, _line_values, read_for_line
from erev_api.domain.reports import revenue_trace
from erev_api.domain.reports.fx_paid_periods import paid_origins
from erev_api.explain.store import trace_from_row
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class Attribution:
    delta: revenue_trace.RevenuePostingDelta
    paid_line_ids: tuple[UUID, ...]
    evidence: tuple[tuple[UUID, str], ...]
    layer_dates: tuple[tuple[UUID, str, date], ...]
    view: str


def read(
    uow: UnitOfWork,
    line_id: UUID,
    *,
    view: str = "functional",
    _active: frozenset[UUID] = frozenset(),
    _cache: dict[UUID, Attribution] | None = None,
) -> Attribution:
    """Authorize each original computation and recurse through its sealed cutoff.

    Ordinary unsplit revenue targets are supported. Mixed TIME/EVENT functional
    allocation requires its own retained sources. Close histories must retain their
    original revenue paid population.
    Missing history never becomes a residual or a guessed owner.
    """
    if view not in {"transaction", "functional"}:
        raise ValueError("Revenue attribution currency view is invalid.")
    if line_id in _active:
        raise ValueError("Cycle in retained revenue history.")
    cache = {} if _cache is None else _cache
    if line_id in cache:
        if cache[line_id].view != view:
            raise ValueError("Revenue attribution cache mixes currency views.")
        return cache[line_id]
    row = (
        uow.session.execute(
            select(subledger_line, legal_entity.c.code.label("entity_code"), period.c.period_key)
            .join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
            .join(period, period.c.id == subledger_line.c.period_id)
            .where(subledger_line.c.id == line_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ValueError("Revenue line is not visible.")
    line = dict(row)
    document = read_for_line(uow, line_id, revenue=True)
    if document is None:
        raise ValueError("Revenue line lacks original computation evidence.")
    bundle = upgrade.decode_input(canonical_bytes(document["input"]))
    trace = trace_from_row({"id": document["id"], **document["trace_record"]})
    nodes = {node.id: node for node in trace.nodes}
    entity = next(item for item in bundle.entities if item.code == line["entity_code"])
    currency = entity.functional_currency
    scale = bundle.currencies[currency].minor_unit
    txn_scale = bundle.currencies[str(line["txn_currency"]).strip()].minor_unit
    period_ends = {item.period_key: item.end_date for item in entity.periods}
    owner_rows = uow.session.execute(
        select(contract.c.external_id, contract.c.id).where(
            contract.c.external_id.in_(bundle.group.member_contract_keys)
        )
    ).all()
    owners: dict[str, UUID] = {str(row[0]): row[1] for row in owner_rows}
    if set(owners) != set(bundle.group.member_contract_keys):
        raise ValueError("Revenue source membership is incomplete.")
    candidates = [
        node
        for node in trace.nodes
        if (
            node.formula_id == "post.delta.v1"
            and node.inputs
            and node.inputs[0] == line["trace_node_id"]
            and node.id.endswith(":" + line["period_key"])
            and node.currency == str(line["txn_currency"]).strip()
            and Fraction(node.value) == Fraction(line["amount_txn"])
        )
    ]
    if len(candidates) != 1:
        raise ValueError("Revenue line does not identify one retained posting delta.")
    delta = candidates[0]
    previous = delta.params.get("previous")
    basis = delta.params.get("class")
    if previous not in {"true", "false"} or basis not in {"ALL", "TIME", "EVENT"}:
        raise ValueError("Unknown retained revenue posting basis.")
    if len(delta.inputs) != (3 if previous == "true" else 2):
        raise ValueError("Revenue posting delta has incomplete sources.")
    original = delta.inputs[-1]
    if (
        not isinstance(original, SourceRef)
        or original.ref_type != "source_record"
        or not original.ref_id.startswith("posted/")
    ):
        raise ValueError("Revenue posting delta lacks its original paid population.")
    source_period = original.ref_id.rsplit("/", 2)[-2]
    target_period = str(delta.inputs[0]).rsplit(":", 1)[-1]
    if target_period != source_period:
        raise ValueError("Revenue paid population differs from the original target period.")
    expected_ref = (
        f"posted/{line['book_code']}/{entity.code}/{line['subject_key']}/"
        f"{line['entry_kind']}/REVENUE/{target_period}/{basis}"
    )
    if original.ref_id != expected_ref:
        raise ValueError("Revenue history does not name the original role and posting basis.")
    raw = []
    layer_dates: dict[tuple[UUID, str], date] = {}
    for item in document["book_output"]["fx_layer_movements"]:
        values = item["columns"]
        if values["entity"] != entity.code:
            continue
        owner = owners.get(values["contract_key"])
        if owner is None:
            raise ValueError("Revenue layer has no authorized original owner.")
        if values["movement_kind"] in {"LIABILITY_LAYER_CREATED", "ASSET_LAYER_CREATED"}:
            layer_identity = (owner, values["layer_key"])
            created = date.fromisoformat(values["effective_date"])
            if layer_identity in layer_dates and layer_dates[layer_identity] != created:
                raise ValueError("Revenue layer has conflicting creation dates.")
            layer_dates[layer_identity] = created
        node_id = item["trace_nodes"]["amount_functional"]
        raw.append(
            {
                **values,
                "id": uuid5(UUID(document["id"]), node_id),
                "contract_id": owner,
                "trace_node_id": node_id,
                "effective_date": date.fromisoformat(values["effective_date"]),
                "amount_functional": minor_to_decimal(values["amount_functional"], scale),
                "amount_txn": minor_to_decimal(values["amount_txn"], txn_scale),
            }
        )

    raw_by_id = {item["id"]: item for item in raw}

    def target(key: Any) -> revenue_trace.RevenueTarget:
        if not isinstance(key, str) or key not in nodes:
            raise ValueError("Revenue target is not retained.")
        node = nodes[key]
        expected_prefix = f"posting_target:{line['subject_key']}/{line['entry_kind']}/REVENUE:"
        if (
            node.formula_id != "post.role_target.v1"
            or not key.startswith(expected_prefix)
            or set(node.params) - {"signs", "time", "amount_functional", "minor_unit"}
            or node.currency != str(line["txn_currency"]).strip()
        ):
            raise ValueError("Revenue requires an unsplit original role target.")
        amount = Fraction(node.params["amount_functional"]) / (10**scale)
        txn = Fraction(node.value)
        if view == "transaction":
            amount = txn
        time_txn = Fraction(node.params["time"]) / (
            10 ** bundle.currencies[str(line["txn_currency"]).strip()].minor_unit
        )
        if time_txn and time_txn != txn:
            raise ValueError("Mixed revenue TIME allocation needs retained component sources.")
        is_time = bool(time_txn)
        signs = node.params["signs"].split("|") if node.inputs else []
        if len(signs) != len(node.inputs) or any(sign not in {"1", "-1"} for sign in signs):
            raise ValueError("Invalid revenue target signs.")
        parts = []
        identities: set[UUID] = set()
        transaction = Fraction(0)
        for child, sign in zip(node.inputs, signs, strict=True):
            if (
                not isinstance(child, str)
                or not child.startswith("revenue_cum:")
                or child not in nodes
            ):
                raise ValueError("Revenue target requires original component attribution.")
            transaction += int(sign) * Fraction(nodes[child].value)
            functional = child.replace("revenue_cum:", "revenue_functional:", 1)
            if functional not in nodes:
                subject, key_period = child.split(":", 1)[1].rsplit(":", 1)
                prior_sources = [
                    candidate
                    for candidate in nodes
                    if (
                        candidate.startswith(f"revenue_functional:{subject}:")
                        and period_ends[candidate.rsplit(":", 1)[-1]] <= period_ends[key_period]
                    )
                ]
                if Fraction(nodes[child].value) or prior_sources:
                    raise ValueError("Functional revenue target has missing original sources.")
                continue
            for part in revenue_trace.project(trace, functional, raw, currency=currency):
                identities.add(part.movement_id)
                parts.append(
                    revenue_trace.RevenueMovement(
                        part.contract_id,
                        part.layer_key,
                        part.movement_kind,
                        part.effective_date,
                        part.source_key,
                        is_time,
                        int(sign)
                        * (
                            part.amount
                            if view == "functional"
                            else part.coefficient
                            * Fraction(raw_by_id[part.movement_id]["amount_txn"])
                        ),
                    )
                )
        if transaction != txn:
            raise ValueError("Revenue target transaction sources do not reconcile.")
        return revenue_trace.RevenueTarget(
            amount,
            amount if is_time else Fraction(0),
            tuple(parts),
            tuple(sorted(identities, key=str)),
        )

    current = target(delta.inputs[0])
    before = target(delta.inputs[1]) if previous == "true" else None
    if Fraction(delta.params["time"]) != Fraction(nodes[str(delta.inputs[0])].params["time"]):
        raise ValueError("Revenue delta TIME component differs from its target.")
    prior_time = (
        Fraction(0) if before is None else Fraction(nodes[str(delta.inputs[1])].params["time"])
    )
    if Fraction(delta.params["time_previous"]) != prior_time:
        raise ValueError("Revenue delta TIME history differs from its prior target.")
    origins = paid_origins(
        entity.periods,
        book=str(line["book_code"]),
        target=source_period,
        previous=None if before is None else str(delta.inputs[1]).rsplit(":", 1)[-1],
        basis=basis,
    )
    paid: list[revenue_trace.RevenueMovement] = []
    paid_txn = Fraction(0)
    paid_functional = Fraction(0)
    paid_ids: set[UUID] = set()
    evidence = {(UUID(document["id"]), document["sha256"])}
    seen: set[UUID] = set()
    for saved in document["posted_lines"]:
        identity = UUID(saved["id"])
        if identity in seen:
            raise ValueError("Duplicate retained revenue history line.")
        seen.add(identity)
        if (
            saved["entity_id"] != str(line["entity_id"])
            or saved["book_code"] != str(line["book_code"])
            or saved["subject_key"] != line["subject_key"]
            or saved["entry_kind"] != line["entry_kind"]
            or saved["account_role"] != "REVENUE"
            or saved["txn_currency"] != str(line["txn_currency"]).strip()
            or saved["functional_currency"] != currency
            or (basis != "ALL" and saved["posting_class"] != basis)
            or (saved["origin_key"] or saved["period_key"]) not in origins
        ):
            continue
        if UUID(saved["contract_id"]) not in owners.values():
            raise ValueError("Revenue history changes original member ownership.")
        actual = (
            uow.session.execute(select(subledger_line).where(subledger_line.c.id == identity))
            .mappings()
            .one_or_none()
        )
        if actual is None or canonical_bytes(_line_values(dict(actual))) != canonical_bytes(
            {field: saved[field] for field in LINE_FIELDS}
        ):
            raise ValueError("Retained revenue history differs from the authorized ledger.")
        found = read(uow, identity, view=view, _active=_active | {line_id}, _cache=cache)
        paid.extend(found.delta.movements)
        paid_ids.update((identity, *found.paid_line_ids))
        evidence.update(found.evidence)
        for owner, layer, created in found.layer_dates:
            if (owner, layer) in layer_dates and layer_dates[(owner, layer)] != created:
                raise ValueError("Revenue history changes original layer creation date.")
            layer_dates[(owner, layer)] = created
        paid_txn += Fraction(saved["amount_txn"])
        paid_functional += Fraction(saved["amount_functional"])
    if paid_txn != Fraction(original.detail["value"]):
        raise ValueError("Revenue history differs from the retained transaction paid amount.")
    result = revenue_trace.posting_delta(
        current,
        before,
        basis=basis,
        paid=paid,
        expected_paid=paid_functional if view == "functional" else paid_txn,
        expected_delta=Fraction(
            line["amount_functional" if view == "functional" else "amount_txn"]
        ),
    )
    answer = Attribution(
        result,
        tuple(sorted(paid_ids, key=str)),
        tuple(sorted(evidence, key=str)),
        tuple((owner, layer, created) for (owner, layer), created in sorted(layer_dates.items())),
        view,
    )
    cache[line_id] = answer
    return answer


def for_control(
    uow: UnitOfWork,
    control_id: UUID,
    *,
    view: str = "functional",
    cache: dict[UUID, Attribution] | None = None,
) -> tuple[UUID, Attribution]:
    """Resolve a revenue control debit to the revenue credit in its exact entry."""
    control = (
        uow.session.execute(select(subledger_line).where(subledger_line.c.id == control_id))
        .mappings()
        .one()
    )
    lines = (
        uow.session.execute(
            select(subledger_line).where(
                subledger_line.c.subledger_posting_id == control["subledger_posting_id"],
                subledger_line.c.entry_no == control["entry_no"],
                subledger_line.c.book_code == control["book_code"],
                subledger_line.c.entity_id == control["entity_id"],
                subledger_line.c.contract_id == control["contract_id"],
                subledger_line.c.account_role == "REVENUE",
            )
        )
        .mappings()
        .all()
    )
    if control["account_role"] != "CONTRACT_LIABILITY" or len(lines) != 1:
        raise ValueError("Revenue control has no unique retained revenue counterpart.")
    revenue = lines[0]
    if any(revenue[name] != -control[name] for name in ("amount_txn", "amount_functional")):
        raise ValueError("Revenue and control amounts differ within the original entry.")
    return revenue["id"], read(uow, revenue["id"], view=view, _cache=cache)
