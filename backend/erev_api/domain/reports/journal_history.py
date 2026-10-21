"""Committed journal run and batch revisions used by historical report readers."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import ScalarSelect

from erev_api.db.tables import journal_run, report_source_revision
from erev_api.problems import Problem


def run_state_at(cutoff: datetime) -> ScalarSelect[str]:
    revision = report_source_revision.alias("historical_journal_run")
    return (
        select(revision.c.document["state"].astext)
        .where(
            revision.c.tenant_id == journal_run.c.tenant_id,
            revision.c.source_kind == "journal_run",
            revision.c.source_id == journal_run.c.id,
            revision.c.recorded_at <= cutoff,
            func.erev.source_commit_time("report_source_revision", revision.c.id) <= cutoff,
        )
        .order_by(revision.c.revision_no.desc())
        .limit(1)
        .correlate(journal_run)
        .scalar_subquery()
    )


def _latest(session: Session, kind: str, ids: set[UUID], cutoff: datetime) -> dict[UUID, Any]:
    revision = report_source_revision
    query = (
        select(revision.c.id, revision.c.source_id, revision.c.document)
        .where(
            revision.c.source_kind == kind,
            revision.c.source_id.in_(ids),
            revision.c.recorded_at <= cutoff,
            func.erev.source_commit_time("report_source_revision", revision.c.id) <= cutoff,
        )
        .distinct(revision.c.source_id)
        .order_by(revision.c.source_id, revision.c.revision_no.desc())
    )
    return {row["source_id"]: dict(row) for row in session.execute(query).mappings()}


def restore(
    session: Session, rows: Sequence[Mapping[str, Any]], cutoff: datetime, *, batch_key: str
) -> list[dict[str, Any]]:
    """Replace mutable fields with the latest committed revision, preserving row identity."""
    if not rows:
        return []
    runs = _latest(session, "journal_run", {UUID(str(row["run_id"])) for row in rows}, cutoff)
    batches = _latest(session, "journal_batch", {UUID(str(row[batch_key])) for row in rows}, cutoff)
    result = []
    for original in rows:
        run = runs.get(UUID(str(original["run_id"])))
        batch = batches.get(UUID(str(original[batch_key])))
        if run is None or batch is None:
            raise Problem(
                "historical-evidence-unavailable", "Journal lifecycle history is missing."
            )
        document = run["document"]
        row = dict(original)
        for key in (
            "state",
            "updated_at",
            "approved_at",
            "exported_at",
            "acknowledged_at",
            "cancelled_at",
            "functional_currency",
            "total_debit_functional",
        ):
            target = "run_" + key
            if target not in row:
                continue
            value = document.get(key)
            if value is not None and key.endswith("_at"):
                value = datetime.fromisoformat(value)
            if value is not None and key == "total_debit_functional":
                value = Decimal(value)
            row[target] = value
        for target, key in (
            ("approval_request_id", "approval_request_id"),
            ("run_job_id", "job_id"),
        ):
            if target in row:
                value = document.get(key)
                row[target] = None if value is None else UUID(value)
        if "batch_external_id" in row:
            row["batch_external_id"] = batch["document"]["external_id"]
        stamp = batch["document"].get("acknowledged_at")
        row["batch_acknowledged_at"] = None if stamp is None else datetime.fromisoformat(stamp)
        row["_run_revision_id"] = str(run["id"])
        row["_batch_revision_id"] = str(batch["id"])
        result.append(row)
    return result
