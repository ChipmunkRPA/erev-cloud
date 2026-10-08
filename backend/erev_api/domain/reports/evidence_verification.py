"""Resolve one bound audit job result; never choose a tenant's latest verification."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import audit_chain_verification, job
from erev_api.jobs.registry import handler_params
from erev_api.problems import Problem


def completed(session: Session, *, job_id: UUID, lock_id: UUID, pack_id: UUID) -> UUID | None:
    """None means still pending; failed, mismatched or missing results refuse."""
    row = (
        session.execute(select(job).where(of_session_tenant(job), job.c.id == job_id))
        .mappings()
        .one_or_none()
    )
    if row is None or (
        row["kind"] != "AUDIT_CHAIN_VERIFY"
        or row["subject_type"] != "evidence_pack"
        or row["subject_id"] != pack_id
        or handler_params(row["params"]) != {"trigger": "ON_DEMAND", "period_lock_id": str(lock_id)}
    ):
        raise Problem(
            "validation-failed", "The retained audit job does not match the selected lock."
        )
    if row["state"] in {"QUEUED", "RUNNING"}:
        return None
    if row["state"] != "SUCCEEDED":
        raise Problem(
            "validation-failed", "The retained audit verification failed or was cancelled."
        )
    try:
        verification_id = UUID(str(row["result"]["verification_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise Problem(
            "validation-failed", "The audit job has no exact verification result."
        ) from error
    verified = (
        session.execute(
            select(audit_chain_verification).where(
                of_session_tenant(audit_chain_verification),
                audit_chain_verification.c.id == verification_id,
                audit_chain_verification.c.job_id == job_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        verified is None
        or verified["result"] != "PASS"
        or verified["trigger"] != "ON_DEMAND"
        or verified["digest_file_id"] is None
    ):
        raise Problem("validation-failed", "The audit job has no matching passing verification.")
    return verification_id
