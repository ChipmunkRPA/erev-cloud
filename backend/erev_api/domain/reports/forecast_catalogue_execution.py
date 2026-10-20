"""REPORT_RUN rendering from an immutable, authorized forecast publication."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from erev_api.domain.reports import forecast_catalogue, framework
from erev_api.domain.reports.builders import SourceBinding
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def build(
    uow: UnitOfWork, run: Mapping[str, Any], definition: Mapping[str, Any], style: str
) -> tuple[ReportData, framework._Rendered, dict[str, Any]]:
    saved = forecast_catalogue.read(uow, run)
    stamp = framework._run_stamp(uow.session, run, definition, output_sha256="", style=style)
    # Historical codes belong to the selected publication, even after a code is renamed.
    stamp = replace(stamp, entity_codes=tuple(saved.document["entity_codes"]))
    exported = forecast_catalogue.render(uow, run, stamp)
    data = ReportData(
        (Column("title", "Section", "text"), Column("rows", "Rows", "integer")),
        tuple(saved.document["rows"]),
        saved.document["control_totals"],
    )
    binding = SourceBinding.from_stored(run["source_binding"])
    if binding is None:
        raise Problem("precondition-failed", "The forecast publication is not bound.")
    retained = replace(
        binding,
        dataset={"output_sha256": exported.dataset_sha256, "format": saved.output_format},
    ).to_stored()
    return (
        data,
        framework._Rendered(
            exported.content,
            exported.dataset_sha256,
            exported.media_type,
            exported.extension,
            exported.manifest,
        ),
        retained,
    )
