"""RPS-16 saved close-gate evidence; never evaluate today's gates for a past lock.

This collector supplements certification.json with its actual approval records. It
verifies the canonical gate population and cleared states through the close domain.
Approval policy execution is the approval engine's responsibility; these checks bind
its persisted result to the lock, subject, scope and time. Full pack assembly remains
separate, including the journal batch register and reconciliation population proof.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, select

from erev_api.db.tables import (
    approval_decision,
    approval_request,
    close_checklist_item,
    close_checklist_template,
    period_state,
)
from erev_api.domain.close import certification, gates
from erev_api.domain.reports import evidence_close
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.enums import ChecklistStatus
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


class SavedGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_check_code: str
    status: ChecklistStatus
    count: int | None = Field(ge=0, strict=True)
    evaluated_at: datetime
    waiver_approval_request_id: UUID | None = None
    waived_count: int | None = Field(default=None, ge=0, strict=True)
    replayed: bool = Field(default=False, strict=True)


def verified_gates(value: Any, *, locked_at: datetime) -> tuple[SavedGate, ...]:
    """Reject missing/duplicate/uncleared gates and unbound or outgrown waivers."""
    try:
        if not isinstance(value, list):
            raise ValueError("certification must be a list")
        saved = [SavedGate.model_validate(row) for row in value]
        results = []
        for row in saved:
            if row.evaluated_at.tzinfo is None or row.evaluated_at > locked_at:
                raise ValueError("gate evaluation follows the lock or lacks a timezone")
            if row.status is ChecklistStatus.WAIVED:
                if row.waiver_approval_request_id is None:
                    raise ValueError("waiver has no approval reference")
                if (
                    row.count is not None
                    and row.waived_count is not None
                    and row.count > row.waived_count
                ):
                    raise ValueError("waiver no longer covers the gate count")
            elif row.waiver_approval_request_id is not None or row.waived_count is not None:
                raise ValueError("unwaived gate carries waiver evidence")
            results.append(
                gates.GateResult(row.gate_check_code, row.status, row.count, None, row.evaluated_at)
            )
        if certification.failing(results, at_request=False):
            raise ValueError("a certified gate has not cleared")
        by_code = {row.gate_check_code: row for row in saved}
        return tuple(by_code[code] for code in certification.CANONICAL_GATES)
    except (ValueError, TypeError, ValidationError) as error:
        raise Problem("validation-failed", f"Invalid saved close certification: {error}") from error


def _approval(
    uow: UnitOfWork,
    request_id: UUID,
    *,
    subject_type: str,
    subject_id: UUID,
    entity_id: UUID,
    locked_at: datetime,
) -> dict[str, Any]:
    request = (
        uow.session.execute(
            select(approval_request).where(
                approval_request.c.tenant_id == uow.principal.tenant_id,
                approval_request.c.id == request_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if request is None or (
        request["subject_type"] != subject_type
        or request["subject_id"] != subject_id
        or request["entity_id"] != entity_id
        or request["status"] != "APPROVED"
        or request["decided_at"] is None
        or not request["submitted_at"] <= request["decided_at"] <= locked_at
    ):
        raise Problem(
            "validation-failed", "A close certification approval is missing or mismatched."
        )
    decisions = [
        dict(row)
        for row in uow.session.execute(
            select(approval_decision)
            .where(
                approval_decision.c.tenant_id == uow.principal.tenant_id,
                approval_decision.c.approval_request_id == request_id,
            )
            .order_by(approval_decision.c.decided_at, approval_decision.c.id)
        ).mappings()
    ]
    if not decisions or any(
        row["decision"] not in {"APPROVE", "AUTO_APPROVE"}
        or row["subject_content_sha256"] != request["subject_content_sha256"]
        or not request["submitted_at"] <= row["decided_at"] <= request["decided_at"]
        for row in decisions
    ):
        raise Problem(
            "validation-failed", "A close certification approval lacks matching decisions."
        )
    return {"request": dict(request), "decisions": decisions}


def collect(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    frozen = evidence_close.read_locked(uow, selection)
    scope, record = frozen.scope, frozen.record
    saved = verified_gates(record["certification"], locked_at=record["created_at"])
    state_id = uow.session.execute(
        select(period_state.c.id).where(
            period_state.c.tenant_id == selection.tenant_id,
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period_state.c.period_id == scope.period_id,
        )
    ).scalar_one()
    lock_approval = _approval(
        uow,
        record["approval_request_id"],
        subject_type="PERIOD_LOCK",
        subject_id=state_id,
        entity_id=scope.entity_id,
        locked_at=record["created_at"],
    )
    waivers = []
    for row in saved:
        if row.waiver_approval_request_id is None:
            continue
        # Current status/result may have changed on reopen. Only stable checklist identity
        # is used; the selected lock is the authority for the historical waiver reference.
        subject_id = uow.session.execute(
            select(close_checklist_item.c.id)
            .join(
                close_checklist_template,
                and_(
                    close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                    close_checklist_template.c.id
                    == close_checklist_item.c.close_checklist_template_id,
                ),
            )
            .where(
                close_checklist_item.c.tenant_id == selection.tenant_id,
                close_checklist_item.c.entity_id == scope.entity_id,
                close_checklist_item.c.book_code == scope.book_code,
                close_checklist_item.c.period_id == scope.period_id,
                close_checklist_template.c.gate_check_code == row.gate_check_code,
            )
        ).scalar_one_or_none()
        if subject_id is None:
            raise Problem("validation-failed", "A certified waiver lacks its checklist subject.")
        waivers.append(
            {
                "gate_check_code": row.gate_check_code,
                "count": row.count,
                "waived_count": row.waived_count,
                **_approval(
                    uow,
                    row.waiver_approval_request_id,
                    subject_type="EXCEPTION_WAIVER",
                    subject_id=subject_id,
                    entity_id=scope.entity_id,
                    locked_at=record["created_at"],
                ),
            }
        )
    return (
        PackFile(
            "lock/approvals.json",
            canonical_bytes(
                {
                    "period_lock_id": scope.lock_id,
                    "lock_approval": lock_approval,
                    "waivers": waivers,
                }
            ),
        ),
    )
