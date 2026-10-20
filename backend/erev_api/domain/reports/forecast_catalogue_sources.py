"""Full, format-specific forecast snapshots for catalogue exports.

Reads the original publication through current scenario lineage and permissions. Unlike the
revenue-only comparison reader, this reader requires export access for CSV/XLSX and validates
all five sections. It never recaptures current scenario state or changes disclosure format.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import select

from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import report_run
from erev_api.domain.forecast import history
from erev_api.domain.reports import forecast_exports, forecast_saved, requester
from erev_api.domain.reports.forecast_capture import Section
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.outputs.manifest import dataset_document
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class SavedOutput:
    forecast: history.SavedForecast
    report_id: UUID
    dataset_file_id: UUID
    dataset_sha256: str
    output_format: Literal["JSON", "CSV", "XLSX"]
    document: dict[str, Any]
    sections: tuple[Section, ...]
    entities: dict[str, UUID]


def sections(document: dict[str, Any]) -> tuple[Section, ...]:
    """Decode typed values and round-trip the exact public datasets before rendering."""
    try:
        result = []
        if len(document["sections"]) != len(forecast_exports.KEYS):
            raise ValueError("section population")
        for index, (section, key) in enumerate(
            zip(document["sections"], forecast_exports.KEYS, strict=True), start=1
        ):
            if section["number"] != index or len(section["tables"]) != 1:
                raise ValueError("section identity")
            table = section["tables"][0]
            dataset = table["dataset"]
            if (
                table["key"] != key
                or table["basis"] != "FORECAST"
                or table["omitted"]
                or sha256_hex(dataset) != table["source_sha256"]
                or dataset["report"]["code"] != "forecast_outputs"
                or dataset["report"]["version"] != 1
                or dataset["report"]["name"] != section["title"]
                or dataset["parameters"] != document["parameters"]
                or dataset["tie_out_results"] != []
            ):
                raise ValueError("dataset identity")
            columns = tuple(Column(**column) for column in dataset["columns"])
            rows = []
            for original in dataset["rows"]:
                row = dict(original)
                for column in columns:
                    value = row.get(column.key)
                    if value is not None and column.kind == "date":
                        row[column.key] = date.fromisoformat(value)
                    elif value is not None and column.kind == "timestamp":
                        row[column.key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if row[column.key].tzinfo is None:
                            raise ValueError("naive timestamp")
                rows.append(row)
            data = ReportData(columns, tuple(rows), dataset["control_totals"])
            if (
                data.row_count != dataset["row_count"]
                or len({row["row_key"] for row in rows}) != len(rows)
                or canonical_bytes(
                    dataset_document(dataset["report"], document["parameters"], data)
                )
                != canonical_bytes(dataset)
            ):
                raise ValueError("dataset population or representation")
            result.append(Section(key, section["title"], data))
        if document["row_count"] != 5 or document["rows"] != [
            {"row_key": section.key, "title": section.title, "rows": section.data.row_count}
            for section in result
        ]:
            raise ValueError("section index")
        return tuple(result)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise Problem(
            "precondition-failed", "The saved forecast sections failed verification."
        ) from error


def read(
    uow: UnitOfWork, forecast_run_id: UUID, *, output_format: Literal["JSON", "CSV", "XLSX"]
) -> SavedOutput:
    if output_format not in {"JSON", "CSV", "XLSX"}:
        raise Problem("precondition-failed", "Unsupported forecast output format.")
    saved = history.resolve(uow, forecast_run_id)
    entity_ids = tuple(UUID(str(value)) for value in saved.run["parameters"]["entity_ids"])
    requester.require_export(uow.principal, output_format, entity_ids)
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
        rows = (
            uow.session.execute(
                select(report_run).where(
                    report_run.c.tenant_id == saved.forecast_tenant_id,
                    report_run.c.id.in_(saved.run["report_run_ids"]),
                    report_run.c.report_code == "forecast_outputs",
                    report_run.c.output_format == output_format,
                    report_run.c.status == "SUCCEEDED",
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            raise Problem(
                "precondition-failed",
                "Choose a format retained by this forecast run; its publication must be unique.",
            )
        row = dict(rows[0])
        evidence = (row["source_binding"] or {}).get("evidence", {})
        if (
            evidence.get("forecast_run_id") != str(forecast_run_id)
            or row["parameters"].get("forecast_run_id") != str(forecast_run_id)
            or set(row["entity_ids"]) != set(entity_ids)
            or row["book_code"] != saved.run["parameters"]["book_code"]
            or row["report_version"] != 1
            or row["period_lock_id"] is not None
        ):
            raise Problem(
                "precondition-failed", "The forecast publication differs from its parent."
            )
        file_id = evidence.get("forecast_dataset_file_id")
        if file_id is None and output_format == "JSON":
            file_id = row["output_file_id"]
        if file_id is None:
            raise Problem("precondition-failed", "The forecast format has no retained dataset.")
        try:
            identity = UUID(str(file_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise Problem(
                "precondition-failed", "Invalid retained forecast dataset identity."
            ) from error
        metadata, stream = open_file(uow.session, identity, files=uow.files, keyring=uow.keyring)
        with stream:
            content = stream.read(512 * 1024 * 1024 + 1)
        digest = hashlib.sha256(content).hexdigest()
        if (
            len(content) > 512 * 1024 * 1024
            or metadata["size_bytes"] != len(content)
            or metadata["tenant_id"] != saved.forecast_tenant_id
            or metadata["purpose"] != FilePurpose.REPORT_OUTPUT
            or metadata["media_type"] != "application/json"
            or metadata["sha256"] != digest
            or row["output_sha256"] != digest
        ):
            raise Problem(
                "precondition-failed", "The saved forecast dataset failed file verification."
            )
        try:
            document = json.loads(content)
            if canonical_bytes(document) != content or document["parameters"] != row["parameters"]:
                raise ValueError("canonical envelope")
            if (
                datetime.fromisoformat(document["known_at"].replace("Z", "+00:00"))
                != row["known_at"]
            ):
                raise ValueError("cutoff")
            children = evidence["children"]
            if {key: sha256_hex(value) for key, value in children.items()} != document[
                "source_evidence_sha256"
            ]:
                raise ValueError("source evidence")
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise Problem(
                "precondition-failed", "The saved forecast envelope failed verification."
            ) from error
        forecast_saved._revenue(document, saved, evidence)
        entities = forecast_saved._entities(document, saved, evidence)
        if sorted(entities) != sorted(document["entity_codes"]):
            raise Problem(
                "precondition-failed", "The forecast entity codes differ from retained scope."
            )
        decoded = sections(document)
        return SavedOutput(
            saved, row["id"], identity, digest, output_format, document, decoded, entities
        )
    finally:
        set_tenant_context(uow.session, original)
