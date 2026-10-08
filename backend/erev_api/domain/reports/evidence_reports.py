"""RPS-16 saved supporting report outputs, bound to explicit orchestrator selections.

This reader does not choose report parameters, create runs or imply pack completeness.
The pack builder must persist the expected normalized selectors and cutoff when it
creates each source run. Original guarded CSV and IPE manifest bytes travel together.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports import framework
from erev_api.domain.reports.evidence_archive import MAX_PAYLOAD_BYTES, PackFile
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

PATHS = {
    "ssp_change_log": "registers/ssp_change_log",
    "config_change_register": "registers/config_change_register",
    "late_entry_report": "registers/late_entries",
    "user_access_listing": "access/user_access_listing",
    "sod_conflict_report": "access/sod_conflict_report",
}


@dataclass(frozen=True, slots=True)
class ReportSource:
    run_id: UUID
    report_code: str
    parameters_sha256: str
    entity_ids: tuple[UUID, ...]
    book_code: str | None
    as_of_date: date | None
    known_at: datetime


def check_binding(row: Mapping[str, Any], source: ReportSource) -> None:
    if (
        source.report_code not in PATHS
        or row["id"] != source.run_id
        or row["report_code"] != source.report_code
        or sha256_hex(row["parameters"]) != source.parameters_sha256
        or set(row["entity_ids"]) != set(source.entity_ids)
        or row["book_code"] != source.book_code
        or row["as_of_date"] != source.as_of_date
        or row["known_at"] != source.known_at
        or row["period_lock_id"] is not None
        or row["output_format"] != "CSV"
        or row["status"] != "SUCCEEDED"
        or row["output_file_id"] is None
        or row["manifest_file_id"] is None
    ):
        raise Problem("validation-failed", "A supporting report differs from its bound source.")


def check_manifest(content: bytes, row: Mapping[str, Any], output: bytes) -> None:
    try:
        manifest = json.loads(content)
        if (
            manifest["report"]["code"] != row["report_code"]
            or manifest["report"]["version"] != row["report_version"]
            or manifest["report_run_no"] != row["report_run_no"]
            or manifest["parameters"] != row["parameters"]
            or manifest["book"] != row["book_code"]
            or manifest["row_count"] != row["row_count"]
            or manifest["control_totals"] != row["control_totals"]
            or manifest["tie_out_results"] != row["tie_out_results"]
            or manifest["sha256"] != row["output_sha256"]
            or manifest["sha256"] != hashlib.sha256(output).hexdigest()
            or manifest["file"]["media_type"] != "text/csv"
            or manifest["file"]["bytes"] != len(output)
            or canonical_bytes(manifest) != content
        ):
            raise ValueError("manifest differs")
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        raise Problem(
            "validation-failed", "The supporting report manifest is inconsistent."
        ) from error


def _file(uow: UnitOfWork, file_id: UUID, media_type: str) -> tuple[bytes, str]:
    metadata, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(MAX_PAYLOAD_BYTES + 1)
    digest = hashlib.sha256(content).hexdigest()
    if (
        len(content) > MAX_PAYLOAD_BYTES
        or metadata["purpose"] != FilePurpose.REPORT_OUTPUT
        or metadata["media_type"] != media_type
        or len(content) != metadata["size_bytes"]
        or digest != metadata["sha256"]
    ):
        raise Problem("validation-failed", "The supporting report file failed verification.")
    return content, digest


def collect(uow: UnitOfWork, source: ReportSource) -> tuple[PackFile, ...]:
    if framework.EXPORT_PERMISSION not in uow.principal.permissions:
        raise Problem("forbidden")
    row = framework.run_row(uow.session, uow.principal, source.run_id, framework.EXPORT_PERMISSION)
    framework.require_report(
        uow.ctx, str(row["report_code"]), run_id=source.run_id, keyring=uow.keyring
    )
    check_binding(row, source)
    output, digest = _file(uow, row["output_file_id"], "text/csv")
    if digest != row["output_sha256"]:
        raise Problem("validation-failed", "The supporting report output differs from its run.")
    manifest, manifest_hash = _file(uow, row["manifest_file_id"], "application/json")
    check_manifest(manifest, row, output)
    path = PATHS[source.report_code]
    return (
        PackFile(f"{path}.csv", output, report_run_id=source.run_id),
        PackFile(f"{path}.manifest.json", manifest, report_run_id=source.run_id),
        PackFile(
            f"{path}.source.json",
            canonical_bytes(
                {
                    "report_run_id": source.run_id,
                    "report_code": source.report_code,
                    "known_at": source.known_at,
                    "parameters_sha256": source.parameters_sha256,
                    "entity_ids": sorted(source.entity_ids, key=str),
                    "book": source.book_code,
                    "as_of": source.as_of_date,
                    "output_file_id": row["output_file_id"],
                    "output_sha256": digest,
                    "manifest_file_id": row["manifest_file_id"],
                    "manifest_sha256": manifest_hash,
                }
            ),
            report_run_id=source.run_id,
        ),
    )
