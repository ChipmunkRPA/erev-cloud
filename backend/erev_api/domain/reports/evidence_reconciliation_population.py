"""Required reconciliation population at a frozen close, including approved omissions.

Separate from statement/signature verification in evidence_reconciliations. Complete
pack assembly must invoke both. Never use today's policy, checklist result or latest
reconciliation generation to fill a historical gap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import reconciliation
from erev_api.domain.close import gates, reconciliations
from erev_api.domain.reports import evidence_certification, evidence_close
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.enums import BookCode, ChecklistStatus
from erev_api.problems import Problem
from erev_api.registry.resolve import resolve
from erev_api.uow import UnitOfWork


def checked_population(
    required: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    gate: evidence_certification.SavedGate,
    *,
    reviewed_members: Sequence[str] = (),
) -> dict[str, Any]:
    """Missing required kinds need a reviewed missing/unreviewed member, never a count alone."""
    by_kind = {str(row["kind"]): row["id"] for row in rows}
    if len(by_kind) != len(rows) or len({row["id"] for row in rows}) != len(rows):
        raise Problem("validation-failed", "The lock has duplicate reconciliations of one kind.")
    absent = sorted(set(required) - by_kind.keys())
    if gate.status is ChecklistStatus.PASSED and gate.count != 0:
        raise Problem("validation-failed", "A passed reconciliation gate has unresolved findings.")
    if absent:
        covered = set()
        for member in reviewed_members:
            pieces = member.split(":")
            if len(pieces) == 3 and pieces[0] == "reconciliation" and pieces[2] == "missing":
                covered.add(pieces[1])
            elif len(pieces) == 4 and pieces[0] == "reconciliation" and pieces[3] == "unreviewed":
                try:
                    UUID(pieces[2])
                except ValueError:
                    continue
                covered.add(pieces[1])
        if (
            gate.status is not ChecklistStatus.WAIVED
            or gate.count is None
            or gate.count < len(absent)
            or not set(absent).issubset(covered)
        ):
            raise Problem(
                "validation-failed",
                "Required reconciliations are absent without matching waiver evidence.",
            )
    return {
        "required_kinds": sorted(required),
        "certified": [
            {"kind": kind, "reconciliation_id": by_kind[kind]} for kind in sorted(by_kind)
        ],
        "waived_absent_kinds": absent,
    }


def collect(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    if reconciliations.READ_PERMISSION not in uow.principal.permissions:
        raise Problem("forbidden")
    if selection.lock is None:
        raise Problem("validation-failed", "A CLOSE source selection is required.")
    require_for_entity(uow.ctx, reconciliations.READ_PERMISSION, selection.lock.entity_id)
    frozen = evidence_close.read_locked(uow, selection)
    scope, record = frozen.scope, frozen.record
    saved = evidence_certification.verified_gates(
        record["certification"], locked_at=record["created_at"]
    )
    gate = next(row for row in saved if row.gate_check_code == gates.RECONCILIATIONS_GENERATED)
    policy = resolve(
        uow.session,
        gates.REQUIRE_RECONCILIATIONS,
        book_code=BookCode(scope.book_code),
        entity_id=scope.entity_id,
        known_at=record["cutoff_known_at"],
    )
    if type(policy.value) is not bool:
        raise Problem("validation-failed", "The historical reconciliation policy is not boolean.")
    rows = (
        uow.session.execute(
            select(reconciliation)
            .where(
                reconciliation.c.tenant_id == selection.tenant_id,
                reconciliation.c.period_lock_id == scope.lock_id,
            )
            .order_by(reconciliation.c.id)
        )
        .mappings()
        .all()
    )
    if any(
        (row["entity_id"], str(row["book_code"]), row["period_id"])
        != (scope.entity_id, scope.book_code, scope.period_id)
        or row["status"] not in {"CERTIFIED", "REOPENED"}
        or row["certified_at"] is None
        or row["certified_at"] > record["created_at"]
        for row in rows
    ):
        raise Problem(
            "validation-failed", "The reconciliation population is outside its certified close."
        )
    waiver = (
        evidence_certification.waiver_proof(uow, frozen, gate)
        if gate.status is ChecklistStatus.WAIVED
        else None
    )
    population = checked_population(
        gates.REQUIRED_KINDS if policy.value else (),
        [dict(row) for row in rows],
        gate,
        reviewed_members=() if waiver is None else waiver["basis"]["subject"]["members"],
    )
    return (
        PackFile(
            "reconciliations/population.json",
            canonical_bytes(
                {
                    "period_lock_id": scope.lock_id,
                    "known_at": record["cutoff_known_at"],
                    "policy": {
                        "code": policy.code,
                        "value": policy.value,
                        "level": policy.level,
                        "source_id": policy.source_id,
                    },
                    "gate": gate.model_dump(mode="json"),
                    **population,
                    "waiver": waiver,
                }
            ),
        ),
    )
