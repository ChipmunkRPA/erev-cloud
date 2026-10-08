"""RPS-16 reconciliations belonging to a selected close, including retained signed history.

Use the write-once period_lock_id, never the latest generation. Human signatures bind
the production signing snapshot; automatic certification binds the recorded CTL-026
execution and rule IDs. Reopening changes current status but not this certified content.
The index states the actual population; pack completeness/waiver evidence is a separate
assembly requirement, not inferred from an empty or nonempty list here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import contract, control_execution, reconciliation, signoff
from erev_api.domain.close import reconciliations
from erev_api.domain.reports import evidence_close
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def certification_basis(
    row: Mapping[str, Any],
    statement: Mapping[str, Any],
    signatures: Sequence[Mapping[str, Any]],
    executions: Sequence[Mapping[str, Any]],
    *,
    locked_at: datetime,
) -> dict[str, Any]:
    """Verify the saved certification evidence; no approval or replacement signature is made."""
    certified_at = row["certified_at"]
    if (
        row["status"] not in {"CERTIFIED", "REOPENED"}
        or certified_at is None
        or certified_at > locked_at
    ):
        raise Problem("validation-failed", "A lock-bound reconciliation lacks valid certification.")
    content_hash = sha256_hex(statement)
    rule_id, version_id = row["auto_certify_rule_id"], row["auto_certify_rule_set_version_id"]
    if rule_id is not None or version_id is not None:
        if rule_id is None or version_id is None or signatures or len(executions) != 1:
            raise Problem(
                "validation-failed", "Automatic reconciliation certification is incomplete."
            )
        execution = executions[0]
        detail = execution["detail"]
        rule = detail.get("rule") if isinstance(detail, Mapping) else None
        if (
            execution["tenant_id"] != row["tenant_id"]
            or execution["control_id"] != "CTL-026"
            or execution["run_ref_type"] != "RECONCILIATION_RUN"
            or execution["run_ref_id"] != row["id"]
            or execution["entity_id"] != row["entity_id"]
            or execution["book_code"] != row["book_code"]
            or execution["period_id"] != row["period_id"]
            or execution["result"] != "PASS"
            or execution["population_count"] != 1
            or execution["exception_count"] != 0
            or execution["executed_at"] > certified_at
            or not isinstance(rule, Mapping)
            or detail.get("auto_certified") is not True
            or rule.get("rule_id") != str(rule_id)
            or rule.get("rule_set_version_id") != str(version_id)
        ):
            raise Problem(
                "validation-failed",
                "Automatic certification evidence does not match its reconciliation.",
            )
        return {
            "kind": "AUTO_CERTIFICATION",
            "snapshot_sha256": content_hash,
            "control_execution": dict(execution),
        }
    preparers = [s for s in signatures if s["role"] == "PREPARER"]
    reviewers = [s for s in signatures if s["role"] == "REVIEWER"]
    if (
        len(preparers) != 1
        or len(reviewers) != 1
        or preparers[0]["signer_id"] == reviewers[0]["signer_id"]
    ):
        raise Problem(
            "validation-failed",
            "The reconciliation lacks distinct preparer and reviewer sign-offs.",
        )
    if preparers[0]["signed_at"] > reviewers[0]["signed_at"]:
        raise Problem("validation-failed", "The reconciliation review precedes its preparation.")
    for signature in signatures:
        if (
            signature["tenant_id"] != row["tenant_id"]
            or signature["subject_type"] != "reconciliation"
            or signature["subject_id"] != row["id"]
            or signature["subject_content_sha256"] != content_hash
            or signature["mfa_verified_at"] > signature["signed_at"]
            or signature["signed_at"] > certified_at
        ):
            raise Problem(
                "validation-failed",
                "A reconciliation sign-off does not match its certified statement.",
            )
    return {
        "kind": "SIGNOFFS",
        "snapshot_sha256": content_hash,
        "signoffs": [dict(s) for s in signatures],
    }


def _require_referenced_contracts(uow: UnitOfWork, statement: Mapping[str, Any]) -> None:
    """A signed statement cannot be redacted without invalidating its hash; refuse instead."""
    try:
        named = {
            UUID(str(item["contract_id"]))
            for item in statement["items"]
            if item["contract_id"] is not None
        } | {
            UUID(str(item["id"]))
            for total in statement["totals"] or []
            for item in (total.get("not_stated") or {}).get("contracts") or []
        }
    except (KeyError, TypeError, ValueError) as error:
        raise Problem(
            "validation-failed", "A signed statement has invalid contract references."
        ) from error
    if not named:
        return
    query = select(contract.c.id).where(
        contract.c.tenant_id == uow.principal.tenant_id, contract.c.id.in_(named)
    )
    allowed = uow.principal.permission_scopes.get(reconciliations.READ_PERMISSION, frozenset())
    if allowed != "*":
        query = query.where(contract.c.contracting_entity_id.in_(allowed))
    if set(uow.session.execute(query).scalars()) != named:
        raise Problem("not-found")


def collect(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    """Export every reconciliation certified by this lock, or refuse an inconsistent population."""
    if reconciliations.READ_PERMISSION not in uow.principal.permissions:
        raise Problem("forbidden")
    if selection.lock is None:
        raise Problem("validation-failed", "A CLOSE source selection is required.")
    require_for_entity(uow.ctx, reconciliations.READ_PERMISSION, selection.lock.entity_id)
    frozen = evidence_close.read_locked(uow, selection)
    scope = frozen.scope
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
    files = []
    for row in rows:
        if (row["entity_id"], str(row["book_code"]), row["period_id"]) != (
            scope.entity_id,
            scope.book_code,
            scope.period_id,
        ):
            raise Problem(
                "validation-failed", "A reconciliation is bound to a lock outside its scope."
            )
        statement = reconciliations.stored_snapshot(uow.session, dict(row))
        _require_referenced_contracts(uow, statement)
        signatures = [
            dict(s)
            for s in uow.session.execute(
                select(signoff)
                .where(
                    signoff.c.tenant_id == selection.tenant_id,
                    signoff.c.subject_type == "reconciliation",
                    signoff.c.subject_id == row["id"],
                )
                .order_by(signoff.c.signed_at, signoff.c.id)
            ).mappings()
        ]
        executions = [
            dict(e)
            for e in uow.session.execute(
                select(control_execution)
                .where(
                    control_execution.c.tenant_id == selection.tenant_id,
                    control_execution.c.control_id == "CTL-026",
                    control_execution.c.run_ref_type == "RECONCILIATION_RUN",
                    control_execution.c.run_ref_id == row["id"],
                )
                .order_by(control_execution.c.executed_at, control_execution.c.id)
            ).mappings()
        ]
        basis = certification_basis(
            dict(row), statement, signatures, executions, locked_at=frozen.record["created_at"]
        )
        files.append(
            PackFile(
                f"reconciliations/{row['id']}.json",
                canonical_bytes(
                    {
                        "reconciliation_id": row["id"],
                        "period_lock_id": scope.lock_id,
                        "certified_at": row["certified_at"],
                        "status_at_lock": "CERTIFIED",
                        "statement": statement,
                        "certification_basis": basis,
                    }
                ),
                report_run_id=row["report_run_id"],
            )
        )
    files.append(
        PackFile(
            "reconciliations/index.json",
            canonical_bytes(
                {
                    "period_lock_id": scope.lock_id,
                    "count": len(rows),
                    "reconciliation_ids": [row["id"] for row in rows],
                }
            ),
        )
    )
    return tuple(files)
