"""Dated targeted-VC quotas from retained allocation traces.

Amounts come only from posted allocation/share nodes. Immutable estimate identities
and their allocation-criteria evidence determine whether a later version share is targeted VC;
a generic transaction-price share is never enough to exclude fixed consideration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject
from erev_engine.trace import Trace
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, estimate, estimate_version
from erev_api.problems import Problem


@dataclass(frozen=True, slots=True)
class Point:
    effective: date
    amount: Decimal
    node_id: str


def targeted_versions(session: Session, contract_ids: Sequence[UUID]) -> dict[str, bool]:
    rows = session.execute(
        select(
            contract.c.external_id,
            estimate.c.element_code,
            estimate_version.c.version_no,
            estimate.c.allocation_criteria_evidence,
            estimate.c.allocation_target,
        )
        .select_from(
            estimate_version.join(
                estimate,
                (estimate.c.id == estimate_version.c.estimate_id)
                & (estimate.c.tenant_id == estimate_version.c.tenant_id),
            ).join(
                contract,
                (contract.c.id == estimate.c.contract_id)
                & (contract.c.tenant_id == estimate.c.tenant_id),
            )
        )
        .where(estimate.c.contract_id.in_(contract_ids))
    ).mappings()
    found = {}
    for row in rows:
        key = obligation_subject_key(str(row["external_id"]), str(row["element_code"]))
        found[f"{key}@v{row['version_no']}"] = row["allocation_target"] == "OBLIGATIONS" and row[
            "allocation_criteria_evidence"
        ] not in (None, "")
    return found


def history(
    trace: Trace, *, inception: Mapping[str, date], targeted: Mapping[str, bool]
) -> dict[str, tuple[Point, ...]]:
    """Per obligation, signed inception quotas and later allocated deltas."""
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise Problem("validation-failed", "RPO quota trace contains duplicate identities.")
    points: dict[str, list[Point]] = {}
    for node in trace.nodes:
        if not node.measure.startswith(("targeted_vc_allocated@", "tp_share@")):
            continue
        parts = node.id.split(":")
        if len(parts) != 3 or parts[2] != "-":
            raise Problem("validation-failed", "RPO quota trace has an invalid subject.")
        subject = parts[1]
        owner = contract_key_from_subject(subject)
        if owner not in inception:
            continue
        if node.measure.startswith("targeted_vc_allocated@"):
            effective = inception[owner]
        else:
            parents = [
                nodes[value]
                for value in node.inputs
                if isinstance(value, str)
                and value in nodes
                and nodes[value].measure.startswith("tp_delta@")
            ]
            if len(parents) != 1:
                raise Problem("validation-failed", "RPO quota share has no unique price delta.")
            version = parents[0].params.get("v_new")
            if version is None or version not in targeted:
                raise Problem(
                    "validation-failed", "RPO quota share lacks its retained estimate version."
                )
            if not targeted[version]:
                continue
            effective = date.fromisoformat(node.params["as_of"])
        amount = Decimal(node.value)
        if not amount.is_finite():
            raise Problem("validation-failed", "RPO quota contains a non-finite amount.")
        points.setdefault(subject, []).append(Point(effective, amount, node.id))
    return {
        key: tuple(sorted(values, key=lambda point: (point.effective, point.node_id)))
        for key, values in points.items()
    }


def cap(points: Sequence[Point], at: date) -> Decimal:
    return max(
        Decimal(0), sum((point.amount for point in points if point.effective <= at), Decimal(0))
    )
