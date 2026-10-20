"""Current source authorization for catalogue evidence metadata and downloads."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import report_run
from erev_api.domain.reports import evidence_catalogue, evidence_catalogue_jobs
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def authorize(uow: UnitOfWork, run: Mapping[str, Any]) -> bool:
    if (
        run["report_code"] == "forecast_outputs"
        and (run.get("source_binding") or {}).get("evidence", {}).get("catalogue_forecast")
        is not None
    ):
        from erev_api.domain.reports import forecast_catalogue

        forecast_catalogue.read(uow, run)
        return True
    if run["report_code"] not in evidence_catalogue_jobs.CODES:
        return False
    evidence_catalogue.authorize(uow, evidence_catalogue_jobs.source(run))
    return True


def addressed(uow: UnitOfWork, run_id: UUID) -> bool:
    row = (
        uow.session.execute(
            select(report_run).where(
                report_run.c.tenant_id == uow.principal.tenant_id,
                report_run.c.id == run_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    return False if row is None else authorize(uow, dict(row))


def visible(uow: UnitOfWork, run: Mapping[str, Any]) -> bool:
    try:
        authorize(uow, run)
    except Problem as error:
        if error.status in {403, 404}:
            return False
        raise
    return True
