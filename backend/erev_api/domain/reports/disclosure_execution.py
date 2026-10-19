"""Build disclosure artifacts and retained provenance for atomic REPORT_RUN publication.

Public registration and retained rerun reconstruction remain separate admission gates.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

from erev_engine.canonical import canonical_bytes, sha256_hex

from erev_api.domain.reports import disclosure_assembly, disclosure_workbook, framework
from erev_api.domain.reports.builders import RETAINED, SourceCollector
from erev_api.domain.reports.outputs import Column, ReportData, manifest, pdf, xlsx
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def build(
    uow: UnitOfWork, run: Mapping[str, Any], definition: Mapping[str, Any], style: str
) -> tuple[ReportData, framework._Rendered, dict[str, Any]]:
    if run["source_binding"] is not None:
        raise Problem("invalid-transition", "Retained disclosure rerun reconstruction is pending.")
    if run["report_version"] != 1 or run["period_lock_id"] is not None:
        raise Problem("validation-failed", "Unsupported disclosure version or frozen source.")
    pack = disclosure_assembly.prepare(uow, run["id"])
    if not isinstance(pack, disclosure_assembly.Pack):
        raise Problem("invalid-transition", "Disclosure inputs have not completed.")
    stamp = framework._run_stamp(uow.session, run, definition, output_sha256="", style=style)
    child_stamps = {}
    inputs = []
    for child in pack.children:
        child_definition = framework.definition_row(
            uow.session, child.run["report_code"], child.run["report_version"]
        )
        if child_definition is None:
            raise Problem("validation-failed", "A disclosure source definition is unavailable.")
        child_stamps[child.source.run_id] = framework._run_stamp(
            uow.session,
            child.run,
            child_definition,
            output_sha256=child.output_sha256,
            style=style,
        )
        inputs.append(
            {
                "key": child.source.key,
                "run_id": str(child.source.run_id),
                "job_id": str(child.source.job_id),
                "sections": list(child.source.sections),
                "basis": child.source.basis,
                "parameters_sha256": child.source.parameters_sha256,
                "output_sha256": child.output_sha256,
                "dataset": manifest.dataset_document(
                    manifest.report_reference(
                        child.run["report_code"],
                        child_definition["name"],
                        child.run["report_version"],
                    ),
                    child.run["parameters"],
                    child.data,
                ),
            }
        )
    chapters = disclosure_workbook.chapters(pack, stamp, child_stamps)
    xlsx.validate_chapters(chapters)
    rows = []
    sections = []
    for section, chapter in zip(pack.sections, chapters, strict=True):
        tables = []
        for source, table in zip(section.tables, chapter.tables, strict=True):
            rows.append(
                {
                    "row_key": source.key,
                    "chapter": section.number,
                    "title": table.title,
                    "basis": source.basis,
                    "omitted": source.omitted,
                    "rows": table.data.row_count,
                    "source_run_id": None
                    if source.source_run_id is None
                    else str(source.source_run_id),
                    "source_sha256": source.source_sha256,
                }
            )
            tables.append(
                {
                    "key": source.key,
                    "basis": source.basis,
                    "omitted": source.omitted,
                    "notes": list(source.notes),
                    "source_run_id": rows[-1]["source_run_id"],
                    "source_sha256": source.source_sha256,
                    "dataset": manifest.dataset_document(
                        manifest.report_reference(
                            table.stamp.report_code, table.title, table.stamp.report_version
                        ),
                        table.stamp.parameters,
                        table.data,
                    ),
                }
            )
        sections.append(
            {
                "number": section.number,
                "title": section.title,
                "interim_required": section.interim_required,
                "tables": tables,
            }
        )
    # Include supporting child tie-outs even when their table is omitted or not displayed.
    # The public aggregate exposes results, not suppressed source amounts/expectations.
    ties = tuple(
        {"code": f"{child.source.key}:{tie['code']}", "result": tie["result"]}
        for child in pack.children
        for tie in child.data.tie_out_results
    )
    data = ReportData(
        (
            Column("chapter", "Chapter", "integer"),
            Column("title", "Table", "text"),
            Column("basis", "Basis", "code"),
            Column("omitted", "Omitted", "boolean"),
            Column("rows", "Rows", "integer"),
            Column("source_run_id", "Source run", "code"),
            Column("source_sha256", "Source SHA-256", "code"),
        ),
        tuple(rows),
        {
            "chapters": 7,
            "tables": len(rows),
            "children": len(inputs),
            "omitted_tables": sum(row["omitted"] for row in rows),
        },
        ties,
    )
    report = manifest.report_reference("disclosure_pack", definition["name"], 1)
    document = {
        **manifest.dataset_document(report, run["parameters"], data),
        "sections": sections,
        "schema_version": 1,
    }
    dataset = canonical_bytes(document)
    digest = hashlib.sha256(dataset).hexdigest()
    from dataclasses import replace

    stamp = replace(stamp, output_sha256=digest)
    if run["output_format"] == "JSON":
        rendered = framework._Rendered(dataset, digest, manifest.MEDIA_TYPE, manifest.EXTENSION)
    elif run["output_format"] == "XLSX":
        rendered = framework._Rendered(
            disclosure_workbook.render(pack, stamp, child_stamps),
            digest,
            xlsx.MEDIA_TYPE,
            xlsx.EXTENSION,
        )
    elif run["output_format"] == "PDF":
        rendered = framework._Rendered(
            pdf.render_pdf_chapters(disclosure_workbook.chapters(pack, stamp, child_stamps), stamp),
            digest,
            pdf.MEDIA_TYPE,
            pdf.EXTENSION,
        )
    else:
        raise Problem("validation-failed", "Disclosure packs support JSON, XLSX and PDF.")
    facts = {
        "version": 1,
        "tenant_id": str(run["tenant_id"]),
        "entity_ids": [str(identity) for identity in run["entity_ids"]],
        "book": run["book_code"],
        "known_at": run["known_at"].isoformat(),
        "parameters": dict(run["parameters"]),
        "children": inputs,
        "policies": dict(pack.policy_facts),
        "policy_sha256": pack.policy_sha256,
    }
    collector = SourceCollector()
    collector.record_cutoff(run["known_at"])
    collector.record_evidence("disclosure_inputs", facts)
    collector.record_evidence("disclosure_inputs_sha256", sha256_hex(facts))
    binding = collector.binding(
        row_keys=[str(row["row_key"]) for row in rows],
        strategy=RETAINED,
        report_version=1,
        dataset={"output_sha256": digest, "format": run["output_format"]},
    ).to_stored()
    return data, rendered, binding
