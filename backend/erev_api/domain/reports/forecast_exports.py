"""RPT-39 typed JSON, five-sheet XLSX and section CSV archive rendering.

The caller supplies the admitted scenario/publication identity and run stamp. This adapter does
not publish report runs or recalculate forecasts. Saved source evidence is never put in exports.
"""

import hashlib
import io
import zipfile
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports.forecast_capture import Captured
from erev_api.domain.reports.outputs import Column, ReportData, RunStamp, manifest, utc_text, xlsx
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.problems import Problem

KEYS = ("revenue", "billing", "balances", "rpo", "journals")


@dataclass(frozen=True)
class Identity:
    scenario_id: UUID
    scenario_name: str
    event_set_id: UUID
    event_set_name: str
    event_set_version: int
    event_set_sha256: str


@dataclass(frozen=True)
class Export:
    content: bytes
    media_type: str
    extension: str
    dataset: bytes
    dataset_sha256: str


def document(captured: Captured, identity: Identity, stamp: RunStamp) -> dict[str, Any]:
    """Build a public dataset envelope without exposing raw retained evidence."""
    if (
        stamp.report_code != "forecast_outputs"
        or stamp.report_version != 1
        or stamp.book != captured.book
        or stamp.entity_codes != captured.entity_codes
        or tuple(section.key for section in captured.sections) != KEYS
        or any(section.data.tie_out_results for section in captured.sections)
        or not captured.entity_periods
        or any(source.cutoff != captured.known_at for source in captured.sources.values())
        or not identity.scenario_name.strip()
        or not identity.event_set_name.strip()
        or identity.event_set_version < 1
        or len(identity.event_set_sha256) != 64
        or any(c not in "0123456789abcdef" for c in identity.event_set_sha256)
    ):
        raise Problem("validation-failed", "Forecast export scope or publication metadata differs.")
    horizons = tuple(captured.entity_periods.values())
    keys = tuple(p.key for p in horizons[0])
    if not keys or any(tuple(p.key for p in horizon) != keys for horizon in horizons):
        raise Problem("validation-failed", "Forecast export horizons differ.")
    return {
        "schema_version": 1,
        "report": manifest.report_reference(stamp.report_code, stamp.report_name, 1),
        "parameters": dict(stamp.parameters),
        "entity_codes": list(captured.entity_codes),
        "book": captured.book,
        "known_at": utc_text(captured.known_at),
        "scenario": {"id": str(identity.scenario_id), "name": identity.scenario_name},
        "event_set": {
            "id": str(identity.event_set_id),
            "name": identity.event_set_name,
            "version": identity.event_set_version,
            "sha256": identity.event_set_sha256,
        },
        "horizon_periods": list(keys),
        "entity_periods": {
            str(entity): [
                {"key": p.key, "name": p.name, "start": p.start, "end": p.end} for p in horizon
            ]
            for entity, horizon in captured.entity_periods.items()
        },
        "source_evidence_sha256": {
            key: sha256_hex(source.to_stored()) for key, source in captured.sources.items()
        },
        **manifest.dataset_document(
            manifest.report_reference(stamp.report_code, stamp.report_name, 1),
            stamp.parameters,
            ReportData(
                (Column("title", "Section", "text"), Column("rows", "Rows", "integer")),
                tuple(
                    {"row_key": section.key, "title": section.title, "rows": section.data.row_count}
                    for section in captured.sections
                ),
                {},
            ),
        ),
        "forecast": {
            "scenario_name": identity.scenario_name,
            "event_set_name": identity.event_set_name,
            "event_set_version": identity.event_set_version,
            "horizon_periods": list(keys),
            "known_at": utc_text(captured.known_at),
        },
        "sections": [
            {
                "number": index,
                "title": section.title,
                "interim_required": False,
                "tables": [
                    {
                        "key": section.key,
                        "basis": "FORECAST",
                        "omitted": False,
                        "notes": [],
                        "source_run_id": None,
                        "source_sha256": sha256_hex(
                            manifest.dataset_document(
                                manifest.report_reference(stamp.report_code, section.title, 1),
                                stamp.parameters,
                                section.data,
                            )
                        ),
                        "dataset": manifest.dataset_document(
                            manifest.report_reference(stamp.report_code, section.title, 1),
                            stamp.parameters,
                            section.data,
                        ),
                    }
                ],
            }
            for index, section in enumerate(captured.sections, start=1)
        ],
        "tie_out_results": [],
    }


def render(captured: Captured, identity: Identity, stamp: RunStamp, *, format: str) -> Export:
    """Export exactly the captured visibility basis; no conversion to another output election."""
    if format not in {"JSON", "XLSX", "CSV"}:
        raise Problem("validation-failed", "Forecast outputs supports XLSX, CSV and JSON.")
    if captured.output_format != format:
        raise Problem("validation-failed", "Recapture forecast sources for this output format.")
    data = document(captured, identity, stamp)
    dataset = canonical_bytes(data)
    digest = hashlib.sha256(dataset).hexdigest()
    stamp = replace(stamp, output_sha256=digest)
    if format == "JSON":
        return Export(dataset, manifest.MEDIA_TYPE, "json", dataset, digest)
    horizon = data["horizon_periods"]
    notes = (
        f"Scenario {identity.scenario_name}",
        f"Event set {identity.event_set_name} v{identity.event_set_version}",
        f"Horizon {horizon[0]} – {horizon[-1]}",
        f"Known at {utc_text(captured.known_at)}",
    )
    if format == "XLSX":
        sections = tuple(
            xlsx.WorkbookSection(
                section.key,
                section.title,
                section.data,
                stamp,
                notes,
            )
            for section in captured.sections
        )
        content = xlsx.render_xlsx_pack(sections, stamp)
        return Export(content, xlsx.MEDIA_TYPE, "xlsx", dataset, digest)
    buffer = io.BytesIO()
    files = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, section in enumerate(captured.sections, start=1):
            content = csv_output.render_csv(section.data)
            name = f"{index:02d}-{section.key}.csv"
            # Fixed ZIP metadata makes identical inputs byte reproducible.
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
            files.append(
                manifest.manifest_document(
                    stamp=stamp,
                    data=section.data,
                    file_name=name,
                    media_type="text/csv",
                    content=content,
                )
            )
        envelope = {
            "dataset_sha256": digest,
            "report": data["report"],
            "scenario": data["scenario"],
            "event_set": data["event_set"],
            "horizon_periods": horizon,
            "known_at": data["known_at"],
            "files": files,
        }
        archive.writestr(
            zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0)),
            canonical_bytes(envelope),
        )
    return Export(buffer.getvalue(), "application/zip", "zip", dataset, digest)
