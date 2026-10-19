"""Read-only dependency gate for disclosure parents, before a worker attempt is spent."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, select
from sqlalchemy.orm import Session

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import job, report_run
from erev_api.domain.reports.disclosure_plan import POINT_IN_TIME, SECTIONS
from erev_api.problems import Problem


def ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
    parent = (
        session.execute(
            select(report_run).where(
                of_session_tenant(report_run),
                report_run.c.id == UUID(str(params["report_run_id"])),
            )
        )
        .mappings()
        .one_or_none()
    )
    if parent is None or parent["report_code"] != "disclosure_pack":
        return True  # Other report handlers retain their existing admission/failure behavior.
    if parent["job_id"] != job_id:
        raise Problem("invalid-transition", "Disclosure parent job binding differs.")
    if parent["status"] in {"SUCCEEDED", "FAILED"}:
        return True  # Let the normal terminal-run handler settle this delivery.
    if parent["period_lock_id"] is not None:
        from erev_api.domain.reports.disclosure_frozen import read

        read(session, dict(parent))
        return True
    if parent["source_binding"] is not None:
        from erev_api.domain.reports.disclosure_inputs import rebuild

        rebuild(dict(parent))
        return True  # Retained inputs do not depend on live child jobs/files remaining available.
    ids = tuple(parent["child_report_run_ids"])
    expected = tuple(
        code
        for code in SECTIONS
        for basis in (("PERIOD", "QUARTER") if parent["parameters"].get("quarter") else ("PERIOD",))
        if basis == "PERIOD" or code not in POINT_IN_TIME
    )
    if len(ids) != len(expected) or len(set(ids)) != len(ids):
        raise Problem("invalid-transition", "Disclosure dependencies are incomplete or duplicated.")
    rows = {
        row["id"]: row
        for row in session.execute(
            select(report_run, job.c.state.label("job_state"))
            .select_from(
                report_run.outerjoin(
                    job,
                    and_(
                        job.c.tenant_id == report_run.c.tenant_id,
                        job.c.id == report_run.c.job_id,
                        job.c.kind == "REPORT_RUN",
                        job.c.subject_type == "report_run",
                        job.c.subject_id == report_run.c.id,
                        job.c.params["report_run_id"].astext == report_run.c.id.cast(String),
                    ),
                )
            )
            .where(of_session_tenant(report_run), report_run.c.id.in_(ids))
        ).mappings()
    }
    waiting = False
    for identity, code in zip(ids, expected, strict=True):
        child = rows.get(identity)
        if child is None or (
            child["report_code"] != code
            or child["entity_ids"] != parent["entity_ids"]
            or child["book_code"] != parent["book_code"]
            or child["known_at"] != parent["known_at"]
            or (child["created_by"], child["created_by_kind"])
            != (parent["created_by"], parent["created_by_kind"])
            or child["job_state"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}
            or child["status"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}
        ):
            raise Problem("invalid-transition", "A disclosure dependency failed or is unavailable.")
        if child["job_state"] == "SUCCEEDED" and child["status"] != "SUCCEEDED":
            raise Problem(
                "invalid-transition", "A completed disclosure job has no completed report."
            )
        if child["status"] != "SUCCEEDED" or child["job_state"] != "SUCCEEDED":
            waiting = True
    return not waiting
