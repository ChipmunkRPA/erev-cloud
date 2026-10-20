"""Immutable forecast publication selection for ordinary catalogue jobs.

A catalogue report re-exports the selected completed forecast. It does not rerun the
forecast engine. Public registration follows admission, worker and read-access integration.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_api.domain.reports import forecast_catalogue_sources as sources
from erev_api.domain.reports import forecast_exports
from erev_api.domain.reports.builders import ADAPTER, SourceBinding
from erev_api.domain.reports.outputs import RunStamp
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE = "forecast_outputs"
KEY = "catalogue_forecast"


def _identity(saved: sources.SavedOutput) -> dict[str, Any]:
    return {
        "forecast_run_id": str(saved.forecast.run["id"]),
        "forecast_tenant_id": str(saved.forecast.forecast_tenant_id),
        "report_run_id": str(saved.report_id),
        "dataset_file_id": str(saved.dataset_file_id),
        "dataset_sha256": saved.dataset_sha256,
        "output_format": saved.output_format,
    }


def read(uow: UnitOfWork, run: Mapping[str, Any]) -> sources.SavedOutput:
    """Reauthorize and require exactly the originally selected publication on every use."""
    try:
        binding = SourceBinding.from_stored(run["source_binding"])
        if binding is None or binding.strategy != ADAPTER or binding.report_version != 1:
            raise ValueError("binding")
        identity = binding.evidence[KEY]
        if (
            run["tenant_id"] != uow.principal.tenant_id
            or run["report_code"] != CODE
            or run["report_version"] != 1
            or run["period_lock_id"] is not None
            or binding.cutoff != run["known_at"]
            or binding.evidence["catalogue_parameters"] != run["parameters"]
            or identity["forecast_run_id"] != run["parameters"]["forecast_run_id"]
            or identity["output_format"] != run["output_format"]
        ):
            raise ValueError("report identity")
        saved = sources.read(
            uow, UUID(identity["forecast_run_id"]), output_format=run["output_format"]
        )
        if (
            _identity(saved) != identity
            or set(saved.entities.values()) != set(run["entity_ids"])
            or saved.document["book"] != run["book_code"]
            or saved.document["parameters"] != run["parameters"]
            or datetime.fromisoformat(saved.document["known_at"].replace("Z", "+00:00"))
            != binding.cutoff
        ):
            raise ValueError("retained publication")
        return saved
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise Problem("precondition-failed", "The bound forecast publication differs.") from error


def prepare(uow: UnitOfWork, run: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the completed publication's cutoff and scope before report INSERT."""
    if (
        uow.principal.kind != PrincipalKind.USER
        or run["tenant_id"] != uow.principal.tenant_id
        or run["report_code"] != CODE
        or run["report_version"] != 1
        or run["status"] != "QUEUED"
        or run["period_lock_id"] is not None
        or (run["created_by"], run["created_by_kind"]) != (uow.principal.id, "USER")
    ):
        raise Problem("invalid-transition", "Only the requesting user can bind a forecast report.")
    if run["source_binding"] is not None:
        read(uow, run)
        return {key: run[key] for key in ("source_binding", "parameters", "known_at")}
    saved = sources.read(
        uow, UUID(str(run["parameters"]["forecast_run_id"])), output_format=run["output_format"]
    )
    params = dict(saved.document["parameters"])
    requested = run["parameters"]
    if (
        set(saved.entities.values()) != set(run["entity_ids"])
        or saved.document["book"] != run["book_code"]
        or sorted(requested["entity_codes"]) != sorted(saved.entities)
        or requested.get("currency_view", "transaction")
        != params.get("currency_view", "transaction")
    ):
        raise Problem(
            "validation-failed", "Select the forecast's complete entity, book and currency scope."
        )
    cutoff = datetime.fromisoformat(saved.document["known_at"].replace("Z", "+00:00"))
    if requested.get("known_at_basis") == "historical" and run["known_at"] != cutoff:
        raise Problem("validation-failed", "The selected forecast has a different saved cutoff.")
    binding = SourceBinding(
        cutoff=cutoff,
        versions={},
        labels={},
        row_keys=frozenset(forecast_exports.KEYS),
        strategy=ADAPTER,
        report_version=1,
        evidence={KEY: _identity(saved), "catalogue_parameters": params},
    )
    values = {"source_binding": binding.to_stored(), "parameters": params, "known_at": cutoff}
    read(uow, {**run, **values})
    return values


def render(uow: UnitOfWork, run: Mapping[str, Any], stamp: RunStamp) -> forecast_exports.Export:
    """Render all five verified sections using only the bound format's saved visibility."""
    saved = read(uow, run)
    return forecast_exports.render_document(
        saved.document, saved.sections, stamp, format=saved.output_format
    )
