"""JSON datasets and CSV manifests (04 §16.9, T-RPT-02 ``manifest_file_id``; SCREENS_B RV-07;
03 REQ-RPT-002, REQ-RPT-024; dev-guide DG-KRN-CAN; BUILD_SPEC RPS-2).

``dataset_bytes`` is the canonical JSON of a run's data: the report reference, every parameter,
the columns, the rows as ``GET /report-runs/{id}/data`` returns them, the row count, the control
totals and the tie-out results. It holds nothing volatile, so a rerun with the same parameters
reproduces the bytes; it is the output of a JSON run.

``manifest_bytes`` is the JSON manifest of a CSV output: the file's name, media type, size and
``sha256`` (the SHA-256 of the CSV bytes), ``row_count``, ``control_totals``, tie-out results and
the run stamp (report, run number, parameters, entity codes, source, engine release, user, time).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Final

from erev_engine.canonical import canonical_bytes

from erev_api.domain.reports.outputs import ReportData, RunStamp, json_rows, utc_text

MEDIA_TYPE: Final = "application/json"
EXTENSION: Final = "json"
MANIFEST_SUFFIX: Final = ".manifest.json"


def report_reference(code: str, name: str, version: int) -> dict[str, Any]:
    """API-S-ReportRun ``report``: ``{code, version, name}``."""
    return {"code": code, "name": name, "version": version}


def dataset_document(
    report: Mapping[str, Any], parameters: Mapping[str, Any], data: ReportData
) -> dict[str, Any]:
    return {
        "report": dict(report),
        "parameters": dict(parameters),
        "columns": [
            {"key": column.key, "header": column.header, "kind": column.kind}
            for column in data.columns
        ],
        "rows": json_rows(data),
        "row_count": data.row_count,
        "control_totals": dict(data.control_totals),
        "tie_out_results": [dict(item) for item in data.tie_out_results],
    }


def dataset_bytes(
    report: Mapping[str, Any], parameters: Mapping[str, Any], data: ReportData
) -> bytes:
    """The canonical JSON bytes of the run's dataset."""
    return canonical_bytes(dataset_document(report, parameters, data))


def manifest_document(
    *, stamp: RunStamp, data: ReportData, file_name: str, media_type: str, content: bytes
) -> dict[str, Any]:
    return {
        "report": report_reference(stamp.report_code, stamp.report_name, stamp.report_version),
        "report_run_no": stamp.report_run_no,
        "parameters": dict(stamp.parameters),
        "entity_codes": list(stamp.entity_codes),
        "book": stamp.book,
        "as_of": stamp.as_of,
        "source": stamp.source,
        "engine_release": {"engine_version": stamp.engine_version, "build_sha": stamp.build_sha},
        "run_by": stamp.run_by,
        "run_at": utc_text(stamp.run_at),
        "file": {"name": file_name, "media_type": media_type, "bytes": len(content)},
        "row_count": data.row_count,
        "control_totals": dict(data.control_totals),
        "tie_out_results": [dict(item) for item in data.tie_out_results],
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def manifest_bytes(
    *, stamp: RunStamp, data: ReportData, file_name: str, media_type: str, content: bytes
) -> bytes:
    """The canonical JSON bytes of the manifest of ``content``."""
    return canonical_bytes(
        manifest_document(
            stamp=stamp, data=data, file_name=file_name, media_type=media_type, content=content
        )
    )
