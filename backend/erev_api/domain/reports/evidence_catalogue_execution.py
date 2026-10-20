"""Build a catalogue evidence artifact from its exact, authorized retained source."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from erev_api.domain.reports import evidence_catalogue, evidence_catalogue_jobs, framework
from erev_api.domain.reports.builders import SourceBinding
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def build(
    uow: UnitOfWork, run: Mapping[str, Any]
) -> tuple[ReportData, framework._Rendered, dict[str, Any]]:
    bound = evidence_catalogue_jobs.source(run)
    artifact = evidence_catalogue.read(uow, bound)
    key = str(bound.pack_id)
    data = ReportData(
        columns=(
            Column("pack_id", "Evidence pack", "text"),
            Column("format", "Format", "text"),
            Column("bytes", "Bytes", "integer"),
            Column("sha256", "SHA-256", "text"),
        ),
        rows=(
            {
                "row_key": key,
                "pack_id": key,
                "format": bound.output_format,
                "bytes": len(artifact.content),
                "sha256": artifact.sha256,
            },
        ),
        control_totals={"artifacts": 1, "bytes": len(artifact.content)},
    )
    binding = SourceBinding.from_stored(run["source_binding"])
    if binding is None:
        raise Problem("validation-failed", "Catalogue evidence sources are missing.")
    retained = replace(
        binding,
        row_keys=frozenset({key}),
        dataset={
            "output_sha256": artifact.sha256,
            "format": bound.output_format,
        },
    ).to_stored()
    return (
        data,
        framework._Rendered(
            content=artifact.content,
            sha256=artifact.sha256,
            media_type=artifact.media_type,
            extension=artifact.extension,
            manifest=artifact.manifest,
        ),
        retained,
    )
