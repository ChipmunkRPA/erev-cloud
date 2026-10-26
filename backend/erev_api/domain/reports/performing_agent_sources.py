"""Net commission amount and complete original contractor sources, without layer quotas."""

from collections.abc import Mapping
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from sqlalchemy import select

from erev_api.db.tables import subledger_line
from erev_api.domain.close.pass_evidence import LINE_FIELDS, _line_values
from erev_api.domain.reports.fx_paid_periods import paid_origins
from erev_api.uow import UnitOfWork
from erev_engine.canonical import canonical_bytes
from erev_engine.trace import Trace, TraceNode

if TYPE_CHECKING:
    from .revenue_attribution import AmountProof


def proof(
    uow: UnitOfWork,
    line: Mapping[str, Any],
    document: Mapping[str, Any],
    trace: Trace,
    owners: Mapping[str, UUID],
    delta: TraceNode,
    *,
    view: str,
    active: frozenset[UUID],
    periods: Any,
    txn_scale: int,
    functional_scale: int,
) -> "AmountProof":
    from .revenue_attribution import AmountProof, SourceIdentity, _read

    nodes = {n.id: n for n in trace.nodes}
    basis = delta.params["class"]
    current = nodes[str(delta.inputs[0])]
    previous = nodes[str(delta.inputs[1])] if delta.params["previous"] == "true" else None
    roots: set[str] = set()

    def amount(node: TraceNode | None) -> Fraction:
        if node is None:
            return Fraction(0)
        if node.formula_id != "post.role_target.v1":
            raise ValueError("Agent commission target has no original role calculation")
        signs = node.params["signs"].split("|") if node.inputs else []
        if len(signs) != len(node.inputs) or any(s not in {"1", "-1", "0"} for s in signs):
            raise ValueError("Agent commission target has unsupported input signs")
        total = Fraction(0)
        for child, sign in zip(node.inputs, signs, strict=True):
            if not isinstance(child, str) or child not in nodes:
                raise ValueError("Agent commission input is unavailable")
            if sign != "0":
                if not child.startswith("ic_pair_txn:"):
                    raise ValueError("Agent commission target has a non-pair input")
                total += int(sign) * Fraction(nodes[child].value)
                counterpart = "ic_pair_functional_contracting:" + child.split(":", 1)[1]
                if counterpart not in nodes:
                    raise ValueError("Agent commission lacks original contractor carrying")
                roots.add(counterpart)
        if total != Fraction(node.value):
            raise ValueError("Agent commission pair totals differ from original revenue")
        value = (
            Fraction(node.params["amount_functional"]) / 10**functional_scale
            if view == "functional"
            else Fraction(node.value)
        )
        time = (
            Fraction(
                node.params.get(
                    "time_functional",
                    node.params["amount_functional"] if Fraction(node.params["time"]) else "0",
                )
            )
            / 10**functional_scale
            if view == "functional"
            else Fraction(node.params["time"]) / 10**txn_scale
        )
        return value if basis == "ALL" else time if basis == "TIME" else value - time

    expected = amount(current) - amount(previous)
    origins = paid_origins(
        periods,
        book=str(line["book_code"]),
        target=str(current.id).rsplit(":", 1)[-1],
        previous=None if previous is None else previous.id.rsplit(":", 1)[-1],
        basis=basis,
    )
    evidence = {(UUID(document["id"]), document["sha256"])}
    paid_ids: set[UUID] = set()
    identities: dict[UUID, SourceIdentity] = {}
    layer_dates: dict[tuple[UUID, str], date] = {}
    seen: set[UUID] = set()
    for saved in document["posted_lines"]:
        identity = UUID(saved["id"])
        if identity in seen:
            raise ValueError("Duplicate retained agent commission history")
        seen.add(identity)
        if any(
            saved[k] != str(line[k])
            for k in ("entity_id", "book_code", "subject_key", "entry_kind", "account_role")
        ):
            continue
        if (saved["origin_key"] or saved["period_key"]) not in origins or (
            basis != "ALL" and saved["posting_class"] != basis
        ):
            continue
        actual = (
            uow.session.execute(select(subledger_line).where(subledger_line.c.id == identity))
            .mappings()
            .one_or_none()
        )
        if actual is None or canonical_bytes(_line_values(dict(actual))) != canonical_bytes(
            {k: saved[k] for k in LINE_FIELDS}
        ):
            raise ValueError("Agent commission paid history differs from the authorized ledger")
        held = _read(uow, identity, view=view, _active=active | {line["id"]}, _amounts_only=True)
        if not isinstance(held, AmountProof):
            raise ValueError("Agent commission history has no amount proof")
        paid_ids.update((identity, *held.paid_line_ids))
        evidence.update(held.evidence)
        identities.update((s.movement_id, s) for s in held.sources)
        layer_dates.update(((owner, layer), day) for owner, layer, day in held.layer_dates)
        expected -= Fraction(saved["amount_functional" if view == "functional" else "amount_txn"])
    if expected != Fraction(line["amount_functional" if view == "functional" else "amount_txn"]):
        raise ValueError("Agent commission differs from original paired targets and paid history")

    # A net share spanning several original layers has no determined member/layer
    # quota. Keep the original graph's entire source membership instead.
    reached = set()
    pending = list(roots)
    while pending:
        key = pending.pop()
        if key in reached:
            continue
        reached.add(key)
        node = nodes.get(key)
        if node is None:
            raise ValueError("Agent commission source graph is incomplete")
        pending.extend(child for child in node.inputs if isinstance(child, str))
    for item in document["book_output"]["fx_layer_movements"]:
        values = item["columns"]
        owner = owners.get(values["contract_key"])
        if owner is None:
            raise ValueError("Agent commission source owner is unavailable")
        node_id = item["trace_nodes"]["amount_functional"]
        if node_id in reached:
            identity = uuid5(UUID(document["id"]), node_id)
            identities[identity] = SourceIdentity(
                identity,
                owner,
                values["layer_key"],
                values["movement_kind"],
                date.fromisoformat(values["effective_date"]),
                values.get("source_key"),
            )
        if values["movement_kind"] in {"ASSET_LAYER_CREATED", "LIABILITY_LAYER_CREATED"}:
            layer_dates[(owner, values["layer_key"])] = date.fromisoformat(values["effective_date"])
    if expected and not identities:
        raise ValueError("Agent commission has no original contractor source set")
    used_layers = {(s.contract_id, s.layer_key) for s in identities.values()}
    if not used_layers <= layer_dates.keys():
        raise ValueError("Agent commission source-layer dates are incomplete")
    return AmountProof(
        expected,
        tuple(sorted(paid_ids, key=str)),
        tuple(sorted(evidence, key=str)),
        view,
        tuple(identities[k] for k in sorted(identities, key=str)),
        tuple((owner, layer, layer_dates[owner, layer]) for owner, layer in sorted(used_layers)),
        tuple(sorted(set(owners.values()), key=str)),
    )
