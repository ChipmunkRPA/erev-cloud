"""Stamped contract-sample evidence chapters from the verified retained source archive.

These are evidence workpapers: exact values, document indexes and source paths, not a
new revenue calculation. Binary documents remain separate files in the resulting ZIP.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from typing import Any
from uuid import UUID

from erev_api.domain.reports import evidence_archive, evidence_sample_sources
from erev_api.domain.reports.evidence_archive import Archive, PackFile
from erev_api.domain.reports.outputs import Column, ReportData, RunStamp
from erev_api.domain.reports.outputs.pdf import render_pdf_chapters
from erev_api.domain.reports.outputs.xlsx import (
    WorkbookChapter,
    WorkbookSection,
    render_xlsx_chapters,
)
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

MAX_ROWS = 250_000
CELL_CHARS = 8_000
COLUMNS = (
    Column("pointer", "Source field (JSON pointer)", "text"),
    Column("part", "Value part", "integer"),
    Column("value", "Exact JSON value", "text"),
)
CHAPTERS = (
    ("selection", "Sample and source population"),
    ("events", "Contract events"),
    ("versions", "Versions and group members"),
    ("allocations", "Allocation walk and calculation trace"),
    ("schedules", "Recognition schedules"),
    ("journals", "Journal lines and sampled contributions"),
    ("approvals", "Approval requests and decisions"),
    ("audit", "Linked audit slice"),
    ("documents", "Source document index"),
)


def _chapter(path: str) -> str:
    if path.startswith("contracts/") and path.endswith("/events.json"):
        return "events"
    if path.startswith("computations/"):
        name = path.rsplit("/", 1)[-1]
        if name in {"version.json", "members.json"}:
            return "versions"
        if name in {"allocations.json", "trace.json"}:
            return "allocations"
        if name == "schedule.json":
            return "schedules"
    return {
        "sample/selection.json": "selection",
        "sample/scope.json": "selection",
        "sample/source_records.json": "selection",
        "sample/computations.json": "versions",
        "sample/journals.json": "journals",
        "sample/approvals.json": "approvals",
        "sample/audit.json": "audit",
        "sample/documents.json": "documents",
    }.get(path, "")


def _rows(value: Any) -> tuple[dict[str, Any], ...]:
    """Lossless leaf traversal; empty containers, nulls and long values remain explicit."""
    rows: list[dict[str, Any]] = []
    pending = [("", value)]
    while pending:
        pointer, item = pending.pop()
        if isinstance(item, dict) and item:
            pending.extend(
                (pointer + "/" + key.replace("~", "~0").replace("/", "~1"), item[key])
                for key in reversed(sorted(item))
            )
            continue
        if isinstance(item, list) and item:
            pending.extend((f"{pointer}/{i}", item[i]) for i in reversed(range(len(item))))
            continue
        # JSON escapes preserve controls and Unicode even in the PDF's standard font.
        # Amount strings stay exact; no float conversion or cross-currency aggregation.
        text = json.dumps(item, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        for offset in range(0, len(text), CELL_CHARS):
            rows.append(
                {
                    "row_key": str(len(rows)),
                    "pointer": json.dumps(pointer, ensure_ascii=True)[1:-1],
                    "part": offset // CELL_CHARS + 1,
                    "value": text[offset : offset + CELL_CHARS],
                }
            )
            if len(rows) > MAX_ROWS:
                raise Problem("validation-failed", "The sample exceeds the rendered row limit.")
    return tuple(rows)


def _overview(path: str, value: Any, stamp: RunStamp) -> WorkbookSection | None:
    """Readable accounting grids precede the complete field-by-field evidence appendix."""
    records: list[dict[str, Any]]
    keys: tuple[str, ...]
    if path.endswith("/schedule.json"):
        records = value["lines"]
        keys = (
            "contract_id",
            "book_code",
            "period_end_date",
            "line_type",
            "amount",
            "currency",
            "trace_node_id",
        )
    elif path.endswith("/allocations.json"):
        records = value
        keys = (
            "contract_id",
            "obligation_key",
            "quantity",
            "stated_price",
            "ssp_method",
            "unit_ssp",
            "allocation_weight",
            "allocated_amount",
            "txn_currency",
        )
    elif path == "sample/journals.json":
        records = [
            {
                **item["line"],
                "run_state_as_of": item["run_state_as_of"],
                "sample_contribution": item["sample_contribution"],
            }
            for item in value["lines"]
        ]
        keys = (
            "id",
            "entity_id",
            "book_code",
            "gl_account_code",
            "debit_txn",
            "credit_txn",
            "txn_currency",
            "debit_functional",
            "credit_functional",
            "functional_currency",
            "run_state_as_of",
            "sample_contribution",
        )
    elif path == "sample/documents.json":
        records = value["attachments"]
        keys = ("subject_type", "subject_id", "original_filename", "path", "sha256")
    elif path.startswith("contracts/") and path.endswith("/events.json"):
        records = value["events"]
        keys = ("id", "event_type", "effective_date", "recorded_at", "source_payload_sha256")
    else:
        return None
    # Actual retained schema governs which display columns exist; complete fields follow.
    keys = tuple(key for key in keys if any(key in row for row in records))
    if not keys:
        return None
    rows = tuple(
        {
            "row_key": str(i),
            **{
                key: json.dumps(row.get(key), ensure_ascii=True, separators=(",", ":"))
                if isinstance(row.get(key), (dict, list))
                else (
                    json.dumps(row[key], ensure_ascii=True)[1:-1]
                    if isinstance(row.get(key), str)
                    else row.get(key)
                )
                for key in keys
            },
        }
        for i, row in enumerate(records)
    )
    return WorkbookSection(
        key=path + "/overview",
        title="Accounting detail: " + path,
        data=ReportData(
            tuple(Column(key, key.replace("_", " "), "text") for key in keys),
            rows,
            {"records": len(rows)},
        ),
        stamp=stamp,
        notes=("Exact source amounts; currencies and state must be read together.",),
    )


def chapters(source: Archive, stamp: RunStamp) -> tuple[WorkbookChapter, ...]:
    """Verify the ZIP before rendering; never silently skip an unknown evidence section."""
    evidence_archive.verify(source.content, expected_manifest_sha256=source.manifest_sha256)
    groups: dict[str, list[WorkbookSection]] = {key: [] for key, _ in CHAPTERS}
    total_rows = 0
    with zipfile.ZipFile(io.BytesIO(source.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for entry in manifest["files"]:
            path = entry["path"]
            if path.startswith("documents/") and path.endswith("/content"):
                continue  # represented by the document index; preserved in the output ZIP
            group = _chapter(path)
            if not group:
                raise Problem("validation-failed", "Unknown contract sample evidence section.")
            value = json.loads(archive.read(path))
            rows = _rows(value)
            total_rows += len(rows)
            if total_rows > MAX_ROWS:
                raise Problem("validation-failed", "The sample exceeds the rendered row limit.")
            section_stamp = replace(stamp, output_sha256=entry["sha256"])
            overview = _overview(path, value, section_stamp)
            if overview is not None:
                groups[group].append(overview)
            groups[group].append(
                WorkbookSection(
                    key=path,
                    title=path,
                    data=ReportData(COLUMNS, rows, {"rendered_field_parts": len(rows)}),
                    stamp=section_stamp,
                    notes=(
                        "Source SHA-256 is the hash of the retained JSON file shown above.",
                        "Values use JSON notation; join numbered parts before decoding escapes.",
                        "Money stays exact text with source currency; no totals are inferred.",
                    ),
                )
            )
    result: list[WorkbookChapter] = []
    for key, title in CHAPTERS:
        tables = groups[key]
        if not tables:
            tables.append(
                WorkbookSection(
                    key=f"empty/{key}",
                    title=title,
                    data=ReportData(COLUMNS, (), {}),
                    stamp=stamp,
                    notes=("No retained records in this section at the sample cutoff.",),
                )
            )
        result.append(WorkbookChapter(key, title, tuple(tables)))
    return tuple(result)


def assemble(uow: UnitOfWork, pack_id: UUID, stamp: RunStamp) -> Archive:
    """Reauthorize retained sources and add stamped PDF/XLSX without recollecting facts."""
    bound = evidence_sample_sources.load(uow, pack_id)
    source = evidence_sample_sources.read(uow, bound)
    stamp = replace(
        stamp,
        report_code="contract_sample_pack",
        report_name="Contract sample evidence pack",
        report_version=1,
        as_of=bound.scope.request.as_of.isoformat(),
        book=None,
        source="Retained contract sample sources",
        output_sha256=source.manifest_sha256,
        parameters={
            "contract_external_ids": bound.scope.request.contract_external_ids,
            "known_at": bound.scope.known_at.isoformat(),
            "source_manifest_sha256": source.manifest_sha256,
            "schedule_basis": "Includes future planned periods in retained versions",
            "journal_basis": "Whole lines plus sampled contribution; cancellation state at cutoff",
            "audit_basis": "Linked audit slice; not a full-chain verification",
        },
    )
    sections = chapters(source, stamp)
    with zipfile.ZipFile(io.BytesIO(source.content)) as archive:
        files = [
            PackFile(entry["path"], archive.read(entry["path"]))
            for entry in source.manifest_document()["files"]
        ]
    files.extend(
        (
            PackFile("reports/contract_sample.pdf", render_pdf_chapters(sections, stamp)),
            PackFile("reports/contract_sample.xlsx", render_xlsx_chapters(sections, stamp)),
        )
    )
    return evidence_archive.build(files)
