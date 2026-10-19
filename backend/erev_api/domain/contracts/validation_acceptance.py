"""Finalize frozen release validation and apply independent approval atomically."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from erev_api.approvals import engine as approvals
from erev_api.approvals import preview, subjects
from erev_api.db.tables import (
    combination_group,
    computation_verification,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.enums import ApprovalSubjectType
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from . import processing_seed, validation_aggregation, validation_fence, validation_reports

SUBJECT = ApprovalSubjectType.ENGINE_RELEASE_VALIDATION


def _rows(
    uow: UnitOfWork, validation_id: UUID, attempt_id: UUID
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    tenant = uow.principal.tenant_id
    parent = (
        uow.session.execute(
            select(release_validation)
            .where(
                release_validation.c.tenant_id == tenant,
                release_validation.c.id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    attempt = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(
                release_validation_attempt.c.tenant_id == tenant,
                release_validation_attempt.c.id == attempt_id,
                release_validation_attempt.c.release_validation_id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if parent is None or attempt is None:
        raise Problem("not-found")
    return dict(parent), dict(attempt)


def _stamps(uow: UnitOfWork, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_version": row["row_version"] + 1,
        "updated_at": uow.now,
        "updated_by": uow.principal.id,
        "updated_by_kind": uow.principal.kind.value,
    }


def _move(
    uow: UnitOfWork, parent: Mapping[str, Any], target: str, *, attempt_id: UUID | None = None
) -> None:
    values = _stamps(uow, parent)
    if target in {"PASSED", "APPROVED"}:
        values.update(accepted_attempt_id=attempt_id, enabled_at=uow.now)
    apply(
        uow.session,
        "release_validation",
        parent["id"],
        to_status=target,
        expected_status=parent["status"],
        expected_row_version=parent["row_version"],
        set_values=values,
    )
    uow.audit(
        action="release_validation.finalize",
        object_type="release_validation",
        object_id=parent["id"],
        before={"status": parent["status"]},
        after={"status": target, "accepted_attempt_id": attempt_id},
    )


def _same(
    witness: validation_reports.ReportWitness, parent: Mapping[str, Any], attempt: Mapping[str, Any]
) -> None:
    if (
        parent["row_version"] != witness.parent_version
        or attempt["row_version"] != witness.attempt_version
        or attempt["report_run_id"] != witness.report_id
    ):
        raise Problem("lock-conflict", "Validation changed while its report was verified; retry.")


def finalize(uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID, report_id: UUID) -> str:
    """Use a verified attached report, recheck population, and finalize in this transaction.

    The caller commits. No remote file work occurs under the population fence. MAJOR
    differences submit an independent SYSTEM-prepared request; they never auto-enable.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    witness = validation_reports.verify_attached(
        uow, validation_id=validation_id, attempt_id=attempt_id, report_id=report_id
    )
    # Retain a real before/after report snapshot before acquiring the population fence.
    # A rejected transaction leaves no referenced preview; no file I/O is done under the fence.
    initial = uow.session.execute(
        select(release_validation.c.status, release_validation.c.effective_level).where(
            release_validation.c.id == validation_id
        )
    ).one()
    retained = None
    if initial.status == "RUNNING" and initial.effective_level == "MAJOR" and witness.differences:
        retained = preview.store_preview(uow, before=witness.before, after=witness.after)
    with uow.as_system():
        validation_fence.hold(uow)
        parent, attempt = _rows(uow, validation_id, attempt_id)
        _same(witness, parent, attempt)
        latest = uow.session.scalar(
            select(release_validation_attempt.c.id)
            .where(release_validation_attempt.c.release_validation_id == validation_id)
            .order_by(release_validation_attempt.c.attempt_no.desc())
            .limit(1)
        )
        if latest != attempt_id or attempt["status"] == "SUPERSEDED":
            raise Problem("invalid-transition", "Only the current attempt can be finalized.")
        if parent["status"] in {"PASSED", "APPROVED"}:
            if parent["accepted_attempt_id"] != attempt_id:
                raise Problem("invalid-transition")
            processing_seed.seed(uow, validation_id=validation_id)
            return str(parent["status"])
        if parent["status"] in {"FAILED", "INCOMPLETE", "REJECTED"}:
            return str(parent["status"])
        if parent["status"] == "PENDING_APPROVAL":
            if attempt["approval_request_id"] is None:
                raise Problem(
                    "validation-failed", "The pending validation has no approval request."
                )
            return "PENDING_APPROVAL"
        if attempt["status"] not in {"COMPLETE", "INCOMPLETE"}:
            raise Problem("invalid-transition", "Retain the completed attempt before acceptance.")
        decision = validation_aggregation.assess(
            uow, validation_id=validation_id, attempt_id=attempt_id
        )
        if decision.status is None:
            raise Problem("invalid-transition", "Replay jobs are not terminal.")
        target = decision.status.value
        _move(uow, parent, target, attempt_id=attempt_id if target == "PASSED" else None)
        if target == "PASSED":
            processing_seed.seed(uow, validation_id=validation_id)
        elif target == "PENDING_APPROVAL":
            if retained is None:
                raise Problem("validation-failed", "The approval preview is missing.")
            request = approvals.submit(
                uow,
                subject_type=SUBJECT,
                subject_id=attempt_id,
                summary=f"Review engine release validation attempt {attempt['attempt_no']}",
                auto_approval=False,
                impact_preview=approvals.ImpactPreview(
                    before=witness.before,
                    after=witness.after,
                    retained_file_id=retained["id"],
                    retained_sha256=retained["sha256"],
                ),
            )
            apply(
                uow.session,
                "release_validation_attempt",
                attempt_id,
                to_status=None,
                expected_status=attempt["status"],
                expected_row_version=attempt["row_version"],
                set_values={"approval_request_id": request["id"], **_stamps(uow, attempt)},
            )
            uow.audit(
                action="release_validation_attempt.submit",
                object_type="release_validation_attempt",
                object_id=attempt_id,
                after={"approval_request_id": request["id"]},
            )
        return target


def _approval_source(uow: UnitOfWork, attempt_id: UUID, request_id: UUID) -> Mapping[str, Any]:
    row = (
        uow.session.execute(
            select(release_validation_attempt).where(release_validation_attempt.c.id == attempt_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["approval_request_id"] != request_id or row["report_run_id"] is None:
        raise approvals.StaleBasis()
    return dict(row)


def _approved(uow: UnitOfWork, attempt_id: UUID, request_id: UUID) -> None:
    source = _approval_source(uow, attempt_id, request_id)
    witness = validation_reports.verify_approval_evidence(
        uow, attempt_id=attempt_id, request_id=request_id
    )
    with uow.as_system():
        validation_fence.hold(uow)
        parent, attempt = _rows(uow, source["release_validation_id"], attempt_id)
        try:
            _same(witness, parent, attempt)
            decision = validation_aggregation.assess(
                uow, validation_id=parent["id"], attempt_id=attempt_id, for_approval=True
            )
        except Problem as error:
            if error.slug == "lock-conflict":
                raise
            raise approvals.StaleBasis() from error
        if decision.status != "PENDING_APPROVAL" or attempt["approval_request_id"] != request_id:
            raise approvals.StaleBasis()
        _move(uow, parent, "APPROVED", attempt_id=attempt_id)
        processing_seed.seed(uow, validation_id=parent["id"])
        # Seed against the reviewed population before changing its dirty flags.
        groups = (
            select(release_validation_group.c.combination_group_id)
            .join(
                computation_verification,
                (computation_verification.c.tenant_id == release_validation_group.c.tenant_id)
                & (
                    computation_verification.c.id
                    == release_validation_group.c.accepted_verification_id
                ),
            )
            .where(
                release_validation_group.c.release_validation_attempt_id == attempt_id,
                computation_verification.c.outcome == "DIFFERENCES",
            )
        )
        uow.session.execute(
            update(combination_group)
            .where(
                combination_group.c.id.in_(groups),
                combination_group.c.dirty_since.is_(None),
            )
            .values(
                dirty_since=uow.now,
                row_version=combination_group.c.row_version + 1,
                updated_at=uow.now,
                updated_by=uow.principal.id,
                updated_by_kind=uow.principal.kind.value,
            )
        )


def _closed(uow: UnitOfWork, attempt_id: UUID, request_id: UUID, *, rejected: bool) -> None:
    source = _approval_source(uow, attempt_id, request_id)
    with uow.as_system():
        validation_fence.hold(uow)
        parent, attempt = _rows(uow, source["release_validation_id"], attempt_id)
        if parent["status"] != "PENDING_APPROVAL" or parent["accepted_attempt_id"] is not None:
            raise approvals.StaleBasis()
        _move(uow, parent, "REJECTED" if rejected else "INCOMPLETE")


subjects.register_lifecycle(
    SUBJECT,
    subjects.SubjectLifecycle(
        on_approved=_approved,
        on_rejected=lambda uow, subject, request: _closed(uow, subject, request, rejected=True),
        on_voided=lambda uow, subject, request: _closed(uow, subject, request, rejected=False),
    ),
)
