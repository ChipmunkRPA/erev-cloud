"""Workbook adapter for an authorized, assembled disclosure pack."""

import hashlib
from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.reports import disclosure_expedients
from erev_api.domain.reports.disclosure_assembly import Pack
from erev_api.domain.reports.outputs import RunStamp
from erev_api.domain.reports.outputs.manifest import dataset_bytes, report_reference
from erev_api.domain.reports.outputs.xlsx import (
    WorkbookChapter,
    WorkbookSection,
    render_xlsx_chapters,
)
from erev_api.problems import Problem


def render(pack: Pack, stamp: RunStamp, child_stamps: Mapping[UUID, RunStamp]) -> bytes:
    """Preserve chapter/table boundaries and bind each table to its original output stamp.

    Period and quarter sources remain separately labelled tables here. A future
    side-by-side layout must reconcile row identities before joining their columns.
    """
    facts = pack.policy_facts
    if (
        stamp.report_code != "disclosure_pack"
        or stamp.book != facts["book"]
        or stamp.entity_codes != (facts["entity_code"],)
        or sha256_hex(facts) != pack.policy_sha256
        or tuple(section.number for section in pack.sections) != tuple(range(1, 8))
    ):
        raise Problem("validation-failed", "Disclosure workbook scope or policy evidence differs.")
    children = {child.source.run_id: child for child in pack.children}
    chapters = []
    for section in pack.sections:
        tables = []
        for table in section.tables:
            source_stamp: RunStamp | None
            if table.source_run_id is None:
                if table.source_sha256 != pack.policy_sha256 or section.number != 7:
                    raise Problem("validation-failed", "Invalid disclosure policy table source.")
                if not table.omitted and table.data != disclosure_expedients.dataset(dict(facts)):
                    raise Problem(
                        "validation-failed", "Disclosure policy table changed after assembly."
                    )
                source_stamp = replace(
                    stamp,
                    report_name=section.title,
                    source=f"Entity policies at {facts['known_at']}",
                    output_sha256=pack.policy_sha256,
                )
            else:
                child = children.get(table.source_run_id)
                source_stamp = child_stamps.get(table.source_run_id)
                if (
                    child is None
                    or source_stamp is None
                    or source_stamp.output_sha256 != table.source_sha256
                    or child.output_sha256 != table.source_sha256
                    or source_stamp.report_run_no != child.run["report_run_no"]
                    or source_stamp.report_code != child.run["report_code"]
                    or sha256_hex(source_stamp.parameters) != child.source.parameters_sha256
                    or source_stamp.book != stamp.book
                    or source_stamp.entity_codes != stamp.entity_codes
                ):
                    raise Problem("validation-failed", "A disclosure table source stamp differs.")
                original = dataset_bytes(
                    report_reference(
                        source_stamp.report_code,
                        source_stamp.report_name,
                        source_stamp.report_version,
                    ),
                    child.run["parameters"],
                    child.data,
                )
                if hashlib.sha256(original).hexdigest() != child.output_sha256 or (
                    not table.omitted and table.data != child.data
                ):
                    raise Problem(
                        "validation-failed", "Disclosure source data changed after verification."
                    )
            basis = "Quarter to date" if table.basis == "QUARTER_TO_DATE" else "Period"
            notes = (
                f"Pack run {stamp.report_run_no}",
                basis,
                *(("Interim required",) if section.interim_required else ()),
                *table.notes,
            )
            tables.append(
                WorkbookSection(
                    table.key,
                    source_stamp.report_name,
                    table.data,
                    source_stamp,
                    notes,
                    table.omitted,
                )
            )
        chapters.append(WorkbookChapter(str(section.number), section.title, tuple(tables)))
    return render_xlsx_chapters(tuple(chapters), stamp)
