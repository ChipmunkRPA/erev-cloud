"""Assemble an actual-vs-forecast dataset from immutable, authorized source captures."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports import forecast_actuals_saved, forecast_saved
from erev_api.domain.reports.forecast_comparison import Revenue, compare
from erev_api.domain.reports.forecast_dimensions import actual_rows, forecast_rows
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Comparison:
    data: ReportData
    evidence: dict[str, Any]


def read(
    uow: UnitOfWork,
    forecast_run_id: UUID,
    *,
    row_dimension: Literal["CONTRACT", "REVENUE_CATEGORY"] = "CONTRACT",
    from_period_key: str | None = None,
    to_period_key: str | None = None,
) -> Comparison:
    forecast = forecast_saved.read(uow, forecast_run_id)
    actuals = forecast_actuals_saved.read(uow, forecast_run_id)
    if (
        forecast.forecast.actuals_snapshot_id != actuals.forecast.actuals_snapshot_id
        or forecast.forecast.actuals_cutoff != actuals.forecast.actuals_cutoff
    ):
        raise Problem("precondition-failed", "The scenario refreshed during comparison; try again.")
    category = row_dimension == "REVENUE_CATEGORY"
    predicted = forecast_rows(forecast, require_category=category)
    posted = actual_rows(actuals, require_category=category)
    parameters = forecast.forecast.run["parameters"]
    data = compare(
        predicted,
        posted,
        horizon=parameters["horizon_periods"],
        entity_ids=tuple(UUID(entity) for entity in parameters["entity_ids"]),
        actuals_known_at=actuals.forecast.actuals_cutoff,
        row_dimension=row_dimension,
        from_period_key=from_period_key,
        to_period_key=to_period_key,
    )
    # Retain pre-aggregation facts and both source digests for the report framework adapter.
    evidence = json.loads(
        canonical_bytes(
            {
                "schema_version": 1,
                "tenant_id": str(uow.principal.tenant_id),
                "forecast_run_id": forecast_run_id,
                "forecast_report_id": forecast.report_run_id,
                "forecast_dataset_sha256": forecast.dataset_sha256,
                "actuals_capture_id": actuals.capture_id,
                "actuals_dataset_sha256": actuals.dataset_sha256,
                "actuals_snapshot_id": actuals.forecast.actuals_snapshot_id,
                "actuals_cutoff": actuals.forecast.actuals_cutoff,
                "last_refreshed_at": actuals.forecast.last_refreshed_at,
                "book_code": parameters["book_code"],
                "currency_view": parameters.get("currency_view", "transaction"),
                "entity_ids": parameters["entity_ids"],
                "horizon_periods": parameters["horizon_periods"],
                "forecast_rows": [asdict(row) for row in predicted],
                "actual_rows": [asdict(row) for row in posted],
                "selection": {
                    "row_dimension": row_dimension,
                    "from_period_key": from_period_key,
                    "to_period_key": to_period_key,
                },
            }
        )
    )
    return Comparison(data, evidence)


def rebuild(
    facts: dict[str, Any],
    *,
    expected_sha256: str,
    tenant_id: UUID,
    forecast_run_id: UUID,
    entity_ids: tuple[UUID, ...],
    book_code: str | None,
    currency_view: str,
    selection: dict[str, Any],
    known_at: datetime,
) -> ReportData:
    try:
        if (
            sha256_hex(facts) != expected_sha256
            or facts["schema_version"] != 1
            or facts["tenant_id"] != str(tenant_id)
            or facts["forecast_run_id"] != str(forecast_run_id)
            or set(facts["entity_ids"]) != {str(entity) for entity in entity_ids}
            or (book_code is not None and facts["book_code"] != book_code)
            or facts["currency_view"] != currency_view
            or facts["selection"] != selection
            or datetime.fromisoformat(facts["actuals_cutoff"]) > known_at
        ):
            raise ValueError("scope")
        horizon = facts["horizon_periods"]
        populations = []
        for key in ("forecast_rows", "actual_rows"):
            population = []
            for row in facts[key]:
                if row["entity_id"] not in facts["entity_ids"] or row["period_key"] not in horizon:
                    raise ValueError("fact scope")
                population.append(
                    Revenue(
                        UUID(row["entity_id"]),
                        row["contract_external_id"],
                        row["revenue_category"],
                        row["period_key"],
                        row["currency"],
                        Decimal(row["amount"]),
                    )
                )
            populations.append(population)
        return compare(
            populations[0],
            populations[1],
            horizon=horizon,
            entity_ids=entity_ids,
            actuals_known_at=datetime.fromisoformat(facts["actuals_cutoff"]),
            row_dimension=selection["row_dimension"],
            from_period_key=selection["from_period_key"],
            to_period_key=selection["to_period_key"],
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise Problem(
            "validation-failed", "The forecast comparison source binding is invalid."
        ) from error
