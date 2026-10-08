"""Queue readiness for retained CLOSE sources; never selects or creates replacement reports.

This callback reads as the worker, not as a public authorization boundary. The
completion handler must still reauthorize and verify every source/output.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import evidence_pack, job, report_run
from erev_api.domain.reports import evidence_verification
from erev_api.domain.reports.evidence_sources import QueuedCloseSources, checked_row
from erev_api.problems import Problem


def close_ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
    """Wait only for the exact saved report jobs; terminal/missing sources fail the parent."""
    try:
        pack_id = UUID(str(params["evidence_pack_id"]))
    except (KeyError, ValueError, TypeError) as error:
        raise Problem("validation-failed", "The evidence job has no valid pack id.") from error
    row = (
        session.execute(
            select(evidence_pack).where(
                of_session_tenant(evidence_pack),
                evidence_pack.c.id == pack_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["kind"] != "CLOSE" or row["job_id"] != job_id:
        raise Problem("validation-failed", "The evidence job does not match a retained CLOSE pack.")
    bound = checked_row(dict(row))
    if row["status"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}:
        raise Problem("invalid-transition", "The evidence pack cannot be resumed.")
    parent = session.execute(
        select(job.c.kind, job.c.subject_type, job.c.subject_id).where(
            of_session_tenant(job),
            job.c.id == job_id,
        )
    ).one_or_none()
    if parent is None or tuple(parent) != ("EVIDENCE_PACK", "evidence_pack", pack_id):
        raise Problem("validation-failed", "The evidence job subject differs from its pack.")
    sources = (
        session.execute(
            select(
                report_run.c.id,
                report_run.c.job_id,
                report_run.c.status,
                job.c.state,
                job.c.kind,
                job.c.subject_type,
                job.c.subject_id,
            )
            .select_from(
                report_run.join(
                    job,
                    and_(
                        job.c.tenant_id == report_run.c.tenant_id,
                        job.c.id == report_run.c.job_id,
                    ),
                )
            )
            .where(
                of_session_tenant(report_run),
                report_run.c.id.in_([report.run_id for report in bound.supporting_reports]),
            )
        )
        .mappings()
        .all()
    )
    if {source["id"]: source["job_id"] for source in sources} != {
        source.run_id: source.job_id for source in bound.supporting_reports
    }:
        raise Problem("validation-failed", "A retained supporting report job is missing.")
    ready = True
    if isinstance(bound, QueuedCloseSources):
        ready = (
            evidence_verification.completed(
                session,
                job_id=bound.audit_verification_job_id,
                lock_id=bound.request.period_lock_id,
                pack_id=bound.pack_id,
            )
            is not None
        )
    for source in sources:
        if (
            source["job_id"] == job_id
            or source["kind"] != "REPORT_RUN"
            or source["subject_type"] != "report_run"
            or source["subject_id"] != source["id"]
        ):
            raise Problem("validation-failed", "A retained report job has a different subject.")
        if source["state"] not in {"QUEUED", "RUNNING", "SUCCEEDED"} or source["status"] not in {
            "QUEUED",
            "RUNNING",
            "SUCCEEDED",
        }:
            raise Problem(
                "validation-failed", "A retained supporting report failed or was cancelled."
            )
        if source["state"] == "SUCCEEDED" and source["status"] != "SUCCEEDED":
            raise Problem(
                "validation-failed", "A finished supporting job has no successful report."
            )
        if source["state"] != "SUCCEEDED":
            ready = False
    return ready
