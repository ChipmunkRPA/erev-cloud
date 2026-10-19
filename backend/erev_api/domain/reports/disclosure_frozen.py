"""Reconstruct a disclosure pack from its seven immutable lock snapshots only.

No current business rows, policy resolution, builders or child output files are used. Original
report metadata authenticates the snapshot attachments; all displayed inputs come from E-65.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import disclosure_snapshot, period_lock, report_run
from erev_api.domain.reports import (
    disclosure_assembly,
    disclosure_inputs,
    disclosure_plan,
    disclosure_snapshots,
    locked,
)
from erev_api.domain.reports.evidence_archive import MAX_PAYLOAD_BYTES
from erev_api.domain.reports.outputs import RunStamp
from erev_api.problems import Problem


@dataclass(frozen=True)
class FrozenDisclosure:
    pack: disclosure_assembly.Pack
    stamps: Mapping[UUID, RunStamp]
    facts: Mapping[str, Any]
    snapshot_ids: tuple[UUID, ...]
    origin_run_id: UUID


def read(
    session: Session, run: Mapping[str, Any], *, allow_unattached: bool = False
) -> FrozenDisclosure:
    """Internal reader; admission/worker must separately authorize the requesting principal."""
    try:
        return _read(session, run, allow_unattached=allow_unattached)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise Problem(
            "validation-failed", "The frozen disclosure evidence is inconsistent."
        ) from error


def _read(session: Session, run: Mapping[str, Any], *, allow_unattached: bool) -> FrozenDisclosure:
    if run["report_code"] != "disclosure_pack" or run["report_version"] != 1:
        raise ValueError("report")
    scope = locked.assert_run_matches(session, run)
    lock = (
        session.execute(
            select(period_lock).where(
                period_lock.c.tenant_id == run["tenant_id"],
                period_lock.c.id == scope.lock_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        lock is None
        or lock["kind"] != "LOCK"
        or lock["cutoff_known_at"] != run["known_at"]
        or scope.book_code not in {"ASC606", "IFRS15"}
    ):
        raise ValueError("lock cutoff")
    rows = list(
        session.execute(
            select(disclosure_snapshot).where(
                disclosure_snapshot.c.tenant_id == run["tenant_id"],
                disclosure_snapshot.c.period_lock_id == scope.lock_id,
            )
        ).mappings()
    )
    kinds = [kind.value for kind in disclosure_snapshots.KINDS]
    if len(rows) != 7 or {row["disclosure_kind"] for row in rows} != set(kinds):
        raise Problem(
            "validation-failed", "The lock does not hold seven complete disclosure snapshots."
        )
    by_kind = {row["disclosure_kind"]: row for row in rows}
    rows = [by_kind[kind] for kind in kinds]
    origin_ids = {row["report_run_id"] for row in rows}
    if len(origin_ids) != 1:
        raise ValueError("mixed origin")
    origin_row = (
        session.execute(
            select(report_run).where(
                report_run.c.tenant_id == run["tenant_id"],
                report_run.c.id == next(iter(origin_ids)),
            )
        )
        .mappings()
        .one_or_none()
    )
    origin = None if origin_row is None else dict(origin_row)
    ids = tuple(row["id"] for row in rows)
    if (
        origin is None
        or origin["status"] != "SUCCEEDED"
        or origin["report_code"] != "disclosure_pack"
        or origin["report_version"] != 1
        or origin["job_id"] is not None
        or origin["period_lock_id"] != scope.lock_id
        or origin["known_at"] != run["known_at"]
        or origin["entity_ids"] != [scope.entity_id]
        or origin["book_code"] != scope.book_code
        or tuple(origin["disclosure_snapshot_ids"]) != ids
    ):
        raise ValueError("origin attachment")
    locked.assert_run_matches(session, origin)
    size = 0
    children = []
    policies = rows[0]["data"]["policies"]
    policy_sha256 = sha256_hex(policies)
    for row, kind in zip(rows, kinds, strict=True):
        document = row["data"]
        size += len(canonical_bytes(document))
        if (
            size > MAX_PAYLOAD_BYTES
            or sha256_hex(document) != row["data_sha256"]
            or row["entity_id"] != scope.entity_id
            or row["book_code"] != scope.book_code
            or row["period_id"] != scope.period_id
            or document["kind"] != kind
            or document["policies"] != policies
            or document["policy_sha256"] != policy_sha256
        ):
            raise ValueError("snapshot scope or digest")
        children.extend(document["children"])
        if kind == "EXPEDIENTS_USED":
            children.extend(document["supporting_children"])
    expected = [
        f"{code}:{basis}"
        for code in disclosure_plan.SECTIONS
        for basis in (
            ("PERIOD", "QUARTER_TO_DATE") if origin["parameters"].get("quarter") else ("PERIOD",)
        )
        if basis == "PERIOD" or code not in disclosure_plan.POINT_IN_TIME
    ]
    if len(children) != len(expected) or {child["key"] for child in children} != set(expected):
        raise ValueError("child population")
    by_key = {child["key"]: child for child in children}
    facts = {
        "version": 2,
        **disclosure_inputs.scope(origin),
        "children": [by_key[key] for key in expected],
        "policies": policies,
        "policy_sha256": policy_sha256,
    }
    original_pack, _, _ = disclosure_inputs.from_facts(origin, facts, synchronous=True)
    documents = disclosure_snapshots.documents_for(origin, original_pack, facts, scope.period_id)
    documents["EXPEDIENTS_USED"]["supporting_children"] = [
        child for child in facts["children"] if not child["sections"]
    ]
    if any(row["data"] != documents[kind] for row, kind in zip(rows, kinds, strict=True)):
        raise ValueError("snapshot document")
    quarter = run["parameters"].get("quarter", False)
    if not isinstance(quarter, bool) or (quarter and not origin["parameters"].get("quarter")):
        raise ValueError("quarter inputs unavailable")
    selected = [child for child in facts["children"] if quarter or child["basis"] == "PERIOD"]
    requested = {**facts, **disclosure_inputs.scope(run), "children": selected}
    pack, stamps, retained = disclosure_inputs.from_facts(run, requested, synchronous=True)
    if (not allow_unattached or run.get("disclosure_snapshot_ids")) and tuple(
        run.get("disclosure_snapshot_ids") or ()
    ) != ids:
        raise ValueError("requested snapshot attachment")
    return FrozenDisclosure(pack, stamps, retained, ids, origin["id"])
