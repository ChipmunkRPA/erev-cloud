"""EVIDENCE_PACK worker: retained first-close and contract-sample lifecycle.

PREPARE_CLOSE performs the durable post-lock handoff before the bound build. Samples
reauthorize the active human requester. CHANGE/ACCESS remain unavailable.
Public commands are separate; no worker capability is a caller permission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import evidence_pack, job
from erev_api.db.transitions import apply
from erev_api.domain.reports import evidence_notifications, evidence_preparation
from erev_api.domain.reports.evidence_readiness import close_ready
from erev_api.domain.reports.evidence_sources import checked_row
from erev_api.domain.reports.evidence_storage import finish_close
from erev_api.enums import JobKind, PrincipalKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CAPABILITIES = frozenset(
    {"report.run", "report.export", "evidence.export", "audit.read", "contract.read"}
)


def _id(params: Mapping[str, Any]) -> UUID | None:
    try:
        return UUID(str(params["evidence_pack_id"]))
    except (KeyError, ValueError, TypeError):
        return None


def _pack(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> Mapping[str, Any] | None:
    row = (
        uow.session.execute(
            select(evidence_pack)
            .where(
                of_session_tenant(evidence_pack),
                evidence_pack.c.id == _id(params),
                evidence_pack.c.job_id == job_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _stop(uow: UnitOfWork, row: Mapping[str, Any], *, reason: str) -> None:
    if row["status"] not in {"QUEUED", "RUNNING"}:
        return
    apply(
        uow.session,
        "evidence_pack",
        row["id"],
        to_status="FAILED",
        expected_status=str(row["status"]),
        set_values={
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="evidence.stop",
        object_type="evidence_pack",
        object_id=row["id"],
        contract_ids=row["contract_ids"],
        before={"status": row["status"]},
        after={"status": "FAILED"},
        detail={"reason": reason},
    )


def pack_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    # FailureHook does not receive the job id. Select only the pack's own FAILED job,
    # including its immutable subject/params binding; a malformed foreign job cannot stop it.
    parent_id = uow.session.execute(
        select(job.c.id)
        .select_from(
            job.join(
                evidence_pack,
                and_(
                    evidence_pack.c.tenant_id == job.c.tenant_id,
                    evidence_pack.c.job_id == job.c.id,
                ),
            )
        )
        .where(
            of_session_tenant(job),
            evidence_pack.c.id == _id(params),
            job.c.kind == "EVIDENCE_PACK",
            job.c.state == "FAILED",
            job.c.subject_type == "evidence_pack",
            job.c.subject_id == evidence_pack.c.id,
            job.c.params["evidence_pack_id"].astext == str(_id(params)),
        )
    ).scalar_one_or_none()
    if parent_id is not None:
        row = _pack(uow, params, parent_id)
        if row is not None:
            _stop(uow, row, reason=str(problem.get("type", "job-failed")))


def guard_cancel(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    if params.get("mode") == evidence_preparation.MODE:
        scope = evidence_preparation.selected_lock(uow.session, job_id, params)
        if evidence_preparation.retained_pack(uow.session, job_id, scope) is not None:
            raise Problem("invalid-transition", "The close pack has already been queued.")
        return
    row = _pack(uow, params, job_id)
    if row is not None and row["status"] == "SUCCEEDED":
        raise Problem("invalid-transition", "The evidence pack has already completed.")


def pack_cancelled(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    row = _pack(uow, params, job_id)
    if row is not None:
        _stop(uow, row, reason="cancelled")


@task(
    JobKind.EVIDENCE_PACK,
    retry=RetryPolicy(max_attempts=3),
    ready=close_ready,
    on_failure=pack_failed,
    failure_hook_required=True,
    on_cancel=pack_cancelled,
    cancel_guard=guard_cancel,
)
def build_pack(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    if params.get("mode") == evidence_preparation.MODE:
        return evidence_preparation.prepare(jc, params)
    if jc.principal.kind != PrincipalKind.SYSTEM:
        raise Problem("forbidden")
    with jc.unit_of_work() as uow:
        # Same order as cancellation: job, then pack. The commit fence also prevents
        # cancellation during encrypted retention and the final subject transition.
        current = (
            uow.session.execute(
                select(job)
                .where(
                    of_session_tenant(job),
                    job.c.id == jc.job_id,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if current is None or current["state"] != "RUNNING":
            raise Problem("invalid-transition", "The evidence job is not running.")
        row = _pack(uow, params, jc.job_id)
        if row is None or row["kind"] not in {"CLOSE", "CONTRACT_SAMPLE"}:
            raise Problem("validation-failed", "This evidence job has no supported retained pack.")
        if current["cancel_requested_at"] is not None:
            _stop(uow, row, reason="cancelled")
            uow.commit()
            return JobOutcome(state="SUCCEEDED", result={"counts": {"packs": 0}})
        if not close_ready(uow.session, jc.job_id, params):
            raise Problem("invalid-transition", "The retained report jobs are not ready.")
        if row["kind"] == "CONTRACT_SAMPLE":
            from erev_api.domain.ai.access import AIAccessRefused, job_requester
            from erev_api.domain.reports import evidence_sample_storage

            if (row["created_by"], row["created_by_kind"]) != (
                current["created_by"],
                current["created_by_kind"],
            ):
                raise Problem(
                    "validation-failed", "The sample job requester differs from its pack."
                )
            try:
                requester = job_requester(jc, uow.session, kind=JobKind.EVIDENCE_PACK)
            except AIAccessRefused as error:
                raise Problem(
                    "forbidden", "The sample requester is no longer authorized."
                ) from error
            uow.ctx = replace(uow.ctx, principal=requester)
            if row["status"] == "QUEUED":
                apply(
                    uow.session,
                    "evidence_pack",
                    row["id"],
                    to_status="RUNNING",
                    expected_status="QUEUED",
                    set_values={},
                )
            retained_sample = evidence_sample_storage.finish(uow, row["id"])
            uow.commit()
            return JobOutcome(
                state="SUCCEEDED",
                result={
                    "href": f"/api/v1/evidence-packs/{row['id']}",
                    "counts": {
                        "packs": 1,
                        "files": len(retained_sample.archive.manifest_document()["files"]),
                    },
                },
            )
        bound = checked_row(row)
        # An internal worker capability is restricted to the immutable selected entity.
        # Public creation/download must authorize their actual caller independently.
        entity_scope = frozenset({bound.entity_id})
        uow.ctx = replace(
            uow.ctx,
            principal=replace(
                uow.principal,
                permissions=CAPABILITIES,
                entity_scope=(bound.entity_id,),
                permission_scopes={permission: entity_scope for permission in CAPABILITIES},
            ),
        )
        if row["status"] == "QUEUED":
            apply(
                uow.session,
                "evidence_pack",
                row["id"],
                to_status="RUNNING",
                expected_status="QUEUED",
                set_values={},
            )
        retained = finish_close(uow, row["id"])
        if row["status"] != "SUCCEEDED":
            evidence_notifications.completed(
                uow, pack_id=row["id"], preparation_id=current["parent_job_id"]
            )
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": f"/api/v1/evidence-packs/{row['id']}",
            "counts": {"packs": 1, "files": len(retained.archive.manifest_document()["files"])},
        },
    )
