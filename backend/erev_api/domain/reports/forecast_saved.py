"""Read an immutable forecast revenue table after its workspace has been refreshed.

This internal reader returns only the revenue section. It does not grant access to archived
report downloads or export-only disclosure sections of the saved document.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import report_run
from erev_api.domain.forecast import history
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class SavedRevenue:
    forecast: history.SavedForecast
    report_run_id: UUID
    dataset_sha256: str
    revenue: dict[str, Any]


def read(uow: UnitOfWork, forecast_run_id: UUID) -> SavedRevenue:
    saved = history.resolve(uow, forecast_run_id)
    original = uow.principal.db_context
    try:
        set_tenant_context(
            uow.session,
            DbContext(
                tenant_id=saved.forecast_tenant_id,
                user_id=original.user_id,
                entity_scope=original.entity_scope,
            ),
        )
        candidates = uow.session.execute(
            select(report_run)
            .where(
                report_run.c.id.in_(saved.run["report_run_ids"]),
                report_run.c.report_code == "forecast_outputs",
                report_run.c.status == "SUCCEEDED",
            )
            .order_by(report_run.c.created_at, report_run.c.id)
        ).mappings()
        for row in candidates:
            evidence = (row["source_binding"] or {}).get("evidence", {})
            if evidence.get("forecast_run_id") != str(forecast_run_id):
                raise Problem("precondition-failed", "The saved forecast report parent differs.")
            file_id = evidence.get("forecast_dataset_file_id")
            if file_id is None and row["output_format"] == "JSON":
                file_id = row["output_file_id"]
            if file_id is None:
                continue  # Legacy file-only forecasts did not retain their canonical data.
            _, stream = open_file(
                uow.session, UUID(str(file_id)), files=uow.files, keyring=uow.keyring
            )
            with stream:
                content = stream.read()
            if hashlib.sha256(content).hexdigest() != row["output_sha256"]:
                raise Problem("precondition-failed", "The saved forecast dataset digest differs.")
            document = json.loads(content)
            revenue = _revenue(document, saved, evidence)
            return SavedRevenue(saved, row["id"], row["output_sha256"], revenue)
        raise Problem("precondition-failed", "The saved forecast has no retained revenue dataset.")
    finally:
        set_tenant_context(uow.session, original)


def _revenue(
    document: dict[str, Any], saved: history.SavedForecast, evidence: dict[str, Any]
) -> dict[str, Any]:
    try:
        params = saved.run["parameters"]
        if (
            document["schema_version"] != 1
            or document["scenario"]["id"] != str(saved.scenario_id)
            or document["event_set"]["id"] != str(saved.run["forecast_event_set_id"])
            or document["event_set"]["sha256"] != evidence["event_set_sha256"]
            or document["parameters"]["forecast_run_id"] != str(saved.run["id"])
            or document["book"] != params["book_code"]
            or document["parameters"]["currency_view"] != params.get("currency_view", "transaction")
            or set(document["entity_periods"]) != set(params["entity_ids"])
            or document["horizon_periods"] != params["horizon_periods"]
        ):
            raise ValueError("scope")
        tables = [
            table
            for section in document["sections"]
            for table in section["tables"]
            if table["key"] == "revenue"
        ]
        if len(tables) != 1 or tables[0]["omitted"]:
            raise ValueError("revenue")
        table = tables[0]
        dataset = table["dataset"]
        if sha256_hex(dataset) != table["source_sha256"]:
            raise ValueError("revenue digest")
        return dict(dataset)
    except (KeyError, TypeError, ValueError) as error:
        raise Problem("precondition-failed", "The saved forecast revenue scope differs.") from error
