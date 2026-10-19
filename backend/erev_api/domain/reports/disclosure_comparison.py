"""Period/QTD presentation using semantic identities, never positional row matching."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from erev_engine.canonical import sha256_hex

from erev_api.domain.reports.outputs import Column, ReportData, RunStamp, manifest
from erev_api.domain.reports.outputs.xlsx import WorkbookChapter, WorkbookSection
from erev_api.problems import Problem

BASIS = "PERIOD_AND_QUARTER"
IDENTITIES = {
    "disaggregation": ("dimension_code", "dimension_value", "timing_code", "currency"),
    "contract_balance_rollforward": ("section", "line_code", "contract_external_id", "currency"),
    "revenue_from_opening_liability": (
        "section",
        "entity_code",
        "contract_external_id",
        "currency",
    ),
    "revenue_from_prior_period_obligations": (
        "entity_code",
        "contract_external_id",
        "obligation_key",
        "currency",
    ),
    "rpo_rollforward": ("section", "line_code", "contract_external_id", "currency"),
    "contract_cost_rollforward": ("section", "entity_code", "cost_kind", "line_code", "currency"),
}


def compare(code: str, period: ReportData, quarter: ReportData) -> ReportData:
    """Align stable codes and currencies; preserve absent populations as blank, not zero."""
    identity = IDENTITIES[code]

    def columns(data: ReportData) -> tuple[Column, ...]:
        # Disaggregation already carries an exact range total; its monthly buckets differ by range.
        return tuple(
            c
            for c in data.columns
            if not (code == "disaggregation" and c.key.startswith("period:"))
        )

    fields = columns(period)
    if fields != columns(quarter) or not set(identity) <= {c.key for c in fields}:
        raise Problem("validation-failed", "Disclosure comparison schemas differ.")

    def indexed(data: ReportData) -> dict[str, Mapping[str, Any]]:
        result = {}
        for row in data.rows:
            key = sha256_hex([row.get(field) for field in identity])
            if key in result:
                raise Problem(
                    "validation-failed", "Disclosure comparison row identity is duplicated."
                )
            result[key] = row
        return result

    left, right = indexed(period), indexed(quarter)
    keys = list(dict.fromkeys((*left, *right)))
    paired = {
        c.key
        for c in fields
        if c.key not in identity
        and (
            c.kind in {"money", "decimal", "integer"}
            or any(
                left[key].get(c.key) != right[key].get(c.key) for key in left.keys() & right.keys()
            )
        )
    }
    output_columns: list[Column] = []
    for column in fields:
        if column.key in paired:
            output_columns.extend(
                (
                    replace(column, key=f"period:{column.key}", header=f"Period — {column.header}"),
                    replace(
                        column,
                        key=f"quarter:{column.key}",
                        header=f"Quarter to date — {column.header}",
                    ),
                )
            )
        else:
            output_columns.append(column)
    output_columns.extend(
        (
            Column("period_present", "Period row present", "boolean"),
            Column("quarter_present", "Quarter row present", "boolean"),
        )
    )
    rows = []
    for key in keys:
        a, b = left.get(key), right.get(key)
        row: dict[str, Any] = {
            "row_key": key,
            "period_present": a is not None,
            "quarter_present": b is not None,
        }
        for column in fields:
            if column.key in paired:
                row[f"period:{column.key}"] = None if a is None else a.get(column.key)
                row[f"quarter:{column.key}"] = None if b is None else b.get(column.key)
            else:
                source = a if a is not None else b
                assert source is not None
                row[column.key] = source.get(column.key)
        rows.append(row)
    return ReportData(
        tuple(output_columns),
        tuple(rows),
        {"period": dict(period.control_totals), "quarter": dict(quarter.control_totals)},
        tuple(
            {**tie, "code": f"{basis}:{tie['code']}"}
            for basis, data in (("PERIOD", period), ("QUARTER_TO_DATE", quarter))
            for tie in data.tie_out_results
        ),
    )


def comparisons(chapter: WorkbookChapter, stamp: RunStamp) -> tuple[WorkbookSection, ...]:
    """Add comparison summaries while retaining both individually stamped source tables."""
    by_key = {table.key: table for table in chapter.tables}
    result = []
    for period in chapter.tables:
        code, _, basis = period.key.partition(":")
        quarter = by_key.get(f"{code}:QUARTER_TO_DATE")
        if basis != "PERIOD" or quarter is None or code not in IDENTITIES:
            continue
        if period.omitted != quarter.omitted:
            raise Problem("validation-failed", "Disclosure comparison elections differ.")
        data = compare(code, period.data, quarter.data)
        if period.omitted:
            data = ReportData(data.columns, (), {})
        title = f"{period.title} — Period and quarter to date"
        digest = sha256_hex(
            manifest.dataset_document(
                manifest.report_reference("disclosure_pack", title, 1),
                stamp.parameters,
                data,
            )
        )
        result.append(
            WorkbookSection(
                f"{code}:{BASIS}",
                title,
                data,
                replace(
                    stamp,
                    report_name=title,
                    output_sha256=digest,
                    source=f"{period.stamp.report_run_no}; {quarter.stamp.report_run_no}",
                ),
                (
                    "Period and quarter to date; absent source rows remain blank.",
                    f"Period source: {period.stamp.report_run_no}; "
                    f"SHA-256 {period.stamp.output_sha256}",
                    f"Quarter source: {quarter.stamp.report_run_no}; "
                    f"SHA-256 {quarter.stamp.output_sha256}",
                    *(
                        tuple(note for note in period.notes if not note.startswith("Pack run "))
                        if period.omitted
                        else ()
                    ),
                ),
                period.omitted,
            )
        )
    return tuple(result)


def with_comparisons(
    chapters: tuple[WorkbookChapter, ...], stamp: RunStamp
) -> tuple[WorkbookChapter, ...]:
    return tuple(
        replace(chapter, tables=(*comparisons(chapter, stamp), *chapter.tables))
        for chapter in chapters
    )
