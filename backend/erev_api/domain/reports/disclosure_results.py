"""Wait-state and verified JSON inputs for disclosure section assembly.

A pending child never becomes an empty section. Read only the attached run outputs,
not a fresh execution of today's builders, and authorize before opening any files.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports import disclosure_children, framework
from erev_api.domain.reports.disclosure_plan import ChildSource
from erev_api.domain.reports.evidence_archive import MAX_PAYLOAD_BYTES
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.outputs.manifest import dataset_bytes
from erev_api.enums import FilePurpose
from erev_api.files.store import lock_readable, open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class CompletedChild:
    source: ChildSource
    data: ReportData
    run: Mapping[str, Any]
    output_sha256: str


@dataclass(frozen=True)
class Collected:
    pending: tuple[UUID, ...]
    children: tuple[CompletedChild, ...]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Disclosure child output: {detail}")


def decode(content: bytes, row: Mapping[str, Any], source: ChildSource) -> ReportData:
    """Check original output identity, canonical envelope and normalized parameter binding."""
    if (
        hashlib.sha256(content).hexdigest() != row["output_sha256"]
        or sha256_hex(row["parameters"]) != source.parameters_sha256
    ):
        raise _refuse("the output or parameter digest differs from the child binding.")
    try:
        document = json.loads(content)
        report = document["report"]
        if (
            report["code"] != row["report_code"]
            or report["version"] != row["report_version"]
            or document["parameters"] != row["parameters"]
            or document["row_count"] != row["row_count"]
            or document["control_totals"] != row["control_totals"]
            or document["tie_out_results"] != row["tie_out_results"]
            or canonical_bytes(document) != content
        ):
            raise ValueError("envelope")
        columns = tuple(Column(**column) for column in document["columns"])
        records = []
        for original in document["rows"]:
            record = dict(original)
            for column in columns:
                value = record.get(column.key)
                if value is not None and column.kind == "date":
                    record[column.key] = date.fromisoformat(value)
                elif value is not None and column.kind == "timestamp":
                    record[column.key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if record[column.key].tzinfo is None:
                        raise ValueError("naive timestamp")
            records.append(record)
        data = ReportData(
            columns, tuple(records), document["control_totals"], tuple(document["tie_out_results"])
        )
        if (
            data.row_count != document["row_count"]
            or len({r["row_key"] for r in data.rows}) != data.row_count
            or dataset_bytes(report, row["parameters"], data) != content
        ):
            raise ValueError("dataset")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise _refuse("the saved JSON dataset is inconsistent or malformed.") from error
    return data


def collect(uow: UnitOfWork, parent_id: UUID) -> Collected:
    """Ensure children, return pending IDs, or verify the complete finished population."""
    sources = disclosure_children.ensure(uow, parent_id)
    rows = {}
    for source in sources:
        row = framework.run_row(uow.session, uow.principal, source.run_id, "report.run")
        if row["status"] == "FAILED":
            raise _refuse(f"child {source.key} failed; the parent cannot publish a complete pack.")
        if row["status"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}:
            raise _refuse("an attached child has an unsupported state.")
        rows[source.run_id] = row
    pending = tuple(s.run_id for s in sources if rows[s.run_id]["status"] != "SUCCEEDED")
    if pending:
        return Collected(pending, ())
    completed = []
    total_size = 0
    for source in sources:
        row = rows[source.run_id]
        file_id = row["output_file_id"]
        if file_id is None:
            raise _refuse("a completed child has no output file.")
        lock_readable(uow.session, (file_id,))
        metadata, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
        with stream:
            content = stream.read(MAX_PAYLOAD_BYTES - total_size + 1)
        total_size += len(content)
        digest = hashlib.sha256(content).hexdigest()
        if (
            total_size > MAX_PAYLOAD_BYTES
            or metadata["purpose"] != FilePurpose.REPORT_OUTPUT
            or metadata["media_type"] != "application/json"
            or metadata["size_bytes"] != len(content)
            or metadata["sha256"] != digest
        ):
            raise _refuse("the child file metadata or contents failed verification.")
        data = decode(content, row, source)
        completed.append(CompletedChild(source, data, dict(row), digest))
    return Collected((), tuple(completed))
