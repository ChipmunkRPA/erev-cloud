"""Durable post-lock preparation using the EVIDENCE_PACK job's PREPARE_CLOSE mode.

The lock transaction queues only this job. It reads committed approval/freeze evidence,
then atomically creates the bound pack and source jobs. The preparation job row serializes
creation; its child's immutable parent_job_id identifies the result across commit/crash retry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import evidence_pack, job, period_lock, period_state_transition
from erev_api.domain.reports import evidence_commands, locked
from erev_api.domain.reports.evidence_sources import checked_row
from erev_api.enums import BookCode, PrincipalKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, handler_params
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn

MODE = "PREPARE_CLOSE"


def selected_lock(session: Session, job_id: UUID, params: Mapping[str, Any]) -> locked.LockScope:
    """Validate the persisted job, lock and period-state association before granting capability."""
    try:
        lock_id = UUID(str(params["period_lock_id"]))
    except (KeyError, ValueError, TypeError) as error:
        raise Problem("validation-failed", "The preparation job has no valid lock id.") from error
    if dict(params) != {"mode": MODE, "period_lock_id": str(lock_id)}:
        raise Problem("validation-failed", "The preparation job has unsupported selectors.")
    current = session.execute(
        select(job.c.kind, job.c.subject_type, job.c.subject_id, job.c.params).where(
            of_session_tenant(job), job.c.id == job_id
        )
    ).one_or_none()
    state_id = session.execute(
        select(period_state_transition.c.period_state_id)
        .select_from(
            period_lock.join(
                period_state_transition,
                and_(
                    period_state_transition.c.tenant_id == period_lock.c.tenant_id,
                    period_state_transition.c.id == period_lock.c.period_state_transition_id,
                ),
            )
        )
        .where(of_session_tenant(period_lock), period_lock.c.id == lock_id)
    ).scalar_one_or_none()
    scope = locked.lock_scope(session, lock_id)
    if (
        current is None
        or current.kind != "EVIDENCE_PACK"
        or current.subject_type != "period_state"
        or state_id is None
        or current.subject_id != state_id
        or dict(handler_params(current.params)) != dict(params)
        or scope is None
        or scope.kind != "LOCK"
    ):
        raise Problem("validation-failed", "The preparation job does not match a retained lock.")
    return scope


def retained_pack(session: Session, job_id: UUID, scope: locked.LockScope) -> UUID | None:
    rows = (
        session.execute(
            select(
                evidence_pack, job.c.kind.label("job_kind"), job.c.subject_type, job.c.subject_id
            )
            .select_from(
                evidence_pack.join(
                    job,
                    and_(
                        job.c.tenant_id == evidence_pack.c.tenant_id,
                        job.c.id == evidence_pack.c.job_id,
                    ),
                )
            )
            .where(of_session_tenant(evidence_pack), job.c.parent_job_id == job_id)
            .limit(2)
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise Problem("validation-failed", "The preparation job has multiple retained packs.")
    row = rows[0]
    bound = checked_row(dict(row))
    if (
        row["job_kind"] != "EVIDENCE_PACK"
        or row["subject_type"] != "evidence_pack"
        or row["subject_id"] != row["id"]
        or bound.request.period_lock_id != scope.lock_id
        or bound.entity_id != scope.entity_id
        or bound.period_id != scope.period_id
        or bound.request.book.value != scope.book_code
    ):
        raise Problem("validation-failed", "The retained preparation result has a different scope.")
    return UUID(str(row["id"]))


def prepare(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    if jc.principal.kind != PrincipalKind.SYSTEM:
        raise Problem("forbidden")
    with jc.unit_of_work() as uow:
        current = uow.session.execute(
            select(job.c.state, job.c.cancel_requested_at)
            .where(of_session_tenant(job), job.c.id == jc.job_id)
            .with_for_update()
        ).one_or_none()
        if current is None or current.state != "RUNNING":
            raise Problem("invalid-transition", "The preparation job is not running.")
        scope = selected_lock(uow.session, jc.job_id, params)
        pack_id = retained_pack(uow.session, jc.job_id, scope)
        if pack_id is None:
            if current.cancel_requested_at is not None:
                uow.commit()
                return JobOutcome(state="SUCCEEDED", result={"counts": {"packs": 0}})
            permissions = evidence_commands.PERMISSIONS
            uow.ctx = replace(
                uow.ctx,
                principal=replace(
                    uow.principal,
                    permissions=permissions,
                    entity_scope=(scope.entity_id,),
                    permission_scopes={p: frozenset({scope.entity_id}) for p in permissions},
                ),
            )
            pack_id, _ = evidence_commands.create_close(
                uow,
                ClosePackCreateIn(
                    kind="CLOSE",
                    entity_code=scope.entity_code,
                    book=BookCode(scope.book_code),
                    period_key=scope.period_key,
                    period_lock_id=scope.lock_id,
                ),
                parent_job_id=jc.job_id,
            )
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": f"/api/v1/evidence-packs/{pack_id}", "counts": {"packs": 1}},
    )
