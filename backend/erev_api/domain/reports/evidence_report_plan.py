"""RPS-16 supporting CLOSE report requests and their normalized source bindings.

Date-range registers use the report framework's inclusive UTC-day convention.
Access/SoD use the final microsecond of the fiscal period's UTC end date. Every
source's known-at is the selected lock's freeze cutoff, including a re-lock.
The caller must persist returned bindings atomically with pack creation and reuse
them on retries. This module neither commits nor implements pack job idempotency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.tables import period, report_run
from erev_api.domain.reports import evidence_close, framework
from erev_api.domain.reports.evidence_reports import PATHS, ReportSource
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.problems import Problem
from erev_api.schemas.reports import ReportRunCreateIn
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class QueuedReport:
    source: ReportSource
    job_id: UUID


def requests(
    *,
    entity_code: str,
    book: str,
    period_key: str,
    start_date: date,
    end_date: date,
    cutoff: datetime,
) -> tuple[ReportRunCreateIn, ...]:
    period_end = datetime.combine(end_date, time.max, tzinfo=UTC)
    if start_date > end_date or cutoff.tzinfo is None or cutoff < period_end:
        raise Problem(
            "validation-failed",
            "Period-end evidence requires a completed period and a timezone-aware cutoff.",
        )
    common = {"entity_codes": [entity_code], "known_at": cutoff.astimezone(UTC).isoformat()}
    span = {"from_date": start_date.isoformat(), "to_date": end_date.isoformat()}
    selectors: dict[str, dict[str, Any]] = {
        "config_change_register": span,
        "ssp_change_log": span,
        "late_entry_report": {"book": book, "period_key": period_key},
        "user_access_listing": {"as_of": period_end.isoformat(), "include_removed": False},
        "sod_conflict_report": {"as_of": period_end.isoformat()},
    }
    if set(selectors) != set(PATHS):
        raise Problem("validation-failed", "The supporting report plan is incomplete.")
    return tuple(
        ReportRunCreateIn(
            report_code=code,
            output_format="CSV",
            parameters={**common, **selectors[code]},
        )
        for code in sorted(selectors)
    )


def plan(uow: UnitOfWork, selection: SourceSelection) -> tuple[ReportRunCreateIn, ...]:
    frozen = evidence_close.read_locked(uow, selection)
    row = (
        uow.session.execute(
            select(period).where(
                period.c.tenant_id == selection.tenant_id,
                period.c.id == frozen.scope.period_id,
            )
        )
        .mappings()
        .one()
    )
    cutoff = frozen.record["cutoff_known_at"]
    # The period table has no versioned date history. Never use later calendar edits
    # to silently redefine a historical pack's register interval.
    if row["updated_at"] > cutoff:
        raise Problem(
            "validation-failed",
            "The period changed after this close; its historical dates are unavailable.",
        )
    return requests(
        entity_code=frozen.scope.entity_code,
        book=frozen.scope.book_code,
        period_key=frozen.scope.period_key,
        start_date=row["start_date"],
        end_date=row["end_date"],
        cutoff=cutoff,
    )


def queue(uow: UnitOfWork, selection: SourceSelection) -> tuple[QueuedReport, ...]:
    """Queue through ordinary report validation/permissions; no direct report-row insertion."""
    planned = plan(uow, selection)
    queued = []
    for body in planned:
        run_id, job = framework.create_run(uow, body)
        row = (
            uow.session.execute(
                select(report_run).where(
                    report_run.c.tenant_id == selection.tenant_id,
                    report_run.c.id == run_id,
                )
            )
            .mappings()
            .one()
        )
        if (
            set(row["entity_ids"]) != set(selection.entity_ids)
            or row["known_at"] != selection.lock_known_at
        ):
            raise Problem(
                "validation-failed",
                "Report normalization changed the selected close scope or cutoff.",
            )
        queued.append(
            QueuedReport(
                ReportSource(
                    run_id=run_id,
                    report_code=body.report_code,
                    parameters_sha256=sha256_hex(row["parameters"]),
                    entity_ids=tuple(row["entity_ids"]),
                    book_code=row["book_code"],
                    as_of_date=row["as_of_date"],
                    known_at=row["known_at"],
                ),
                job.id,
            )
        )
    return tuple(queued)
