"""Build upgrade validation output solely from a verified frozen attempt dataset."""

from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.domain.contracts.upgrade_report import upgrade_validation_report
from erev_api.domain.reports.builders import RETAINED, ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.validation_sources import read_for_report
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "upgrade_validation"
BINDING: Final = "validation_dataset"
COLUMNS: Final = (
    Column("group_id", "Combination group", "code"),
    Column("selection", "Selection", "code"),
    Column("strata", "Books and methods", "text"),
    Column("source_computation_id", "Source computation", "code"),
    Column("orchestration_state", "Replay job status", "code"),
    Column("outcome", "Comparison outcome", "code"),
    Column("reason", "Reason or changed path", "text"),
    Column("expected_output_sha256", "Source value or output hash", "text"),
    Column("actual_output_sha256", "Candidate value or output hash", "text"),
    Column("normalised_expected_sha256", "Normalized source hash", "text"),
    Column("normalised_actual_sha256", "Normalized candidate hash", "text"),
    Column("M", "Monetary changes", "integer"),
    Column("P", "Posting changes", "integer"),
    Column("T", "Trace changes", "integer"),
    Column("R", "Representation changes", "integer"),
)


def _invalid() -> Problem:
    return Problem("validation-failed", "The validation report source binding is invalid.")


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    """Reauthorize on every build; bind source evidence rather than caching report output.

    The worker must populate requester from its persisted job initiator's current grants.
    A direct caller uses its own principal. No implicit SYSTEM reader is granted here.
    """
    if (
        params.report_code != CODE
        or params.report_version != 1
        or params.period_lock_id is not None
        or params.filters
        or params.output_format not in {None, "JSON", "CSV", "XLSX"}
    ):
        raise _invalid()
    try:
        attempt_id = UUID(str(params.parameters["release_validation_attempt_id"]))
    except (KeyError, ValueError, TypeError) as error:
        raise _invalid() from error
    bound = None
    file_id = None
    digest = None
    if params.binding is not None:
        if (
            params.binding.strategy != RETAINED
            or params.binding.report_version != params.report_version
        ):
            raise _invalid()
        bound = params.binding.evidence.get(BINDING)
        if (
            not isinstance(bound, dict)
            or set(bound) != {"version", "attempt_id", "file_id", "sha256", "required_entity_ids"}
            or type(bound["version"]) is not int
            or bound["version"] != 1
            or bound["attempt_id"] != str(attempt_id)
            or not isinstance(bound["sha256"], str)
        ):
            raise _invalid()
        try:
            file_id = UUID(bound["file_id"])
        except (ValueError, TypeError, AttributeError) as error:
            raise _invalid() from error
        digest = bound["sha256"]
    cutoff = params.known_at if params.binding is None else params.binding.cutoff
    source = read_for_report(
        uow,
        attempt_id,
        entity_ids=params.entity_ids,
        known_at=cutoff,
        expected_file_id=file_id,
        expected_sha256=digest,
        requester=None if params.requester is None else params.requester.principal,
    )
    evidence = {
        "version": 1,
        "attempt_id": str(attempt_id),
        "file_id": str(source.file_id),
        "sha256": source.sha256,
        "required_entity_ids": [str(item) for item in source.required_entity_ids],
    }
    if bound is not None and bound != evidence:
        raise _invalid()
    try:
        report = upgrade_validation_report(source.content)
        rows = []
        for row in report.rows:
            values: dict[str, Any] = {"row_key": row["row_key"]}
            for column in COLUMNS:
                value = row[column.key]
                if column.kind == "integer":
                    if type(value) is not int:
                        raise _invalid()
                elif value is not None and not isinstance(value, str):
                    value = canonical_bytes(value).decode("utf-8")
                values[column.key] = value
            rows.append(values)
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid() from error
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
        params.sources.record_evidence(BINDING, evidence)
    return ReportData(
        COLUMNS, tuple(rows), {**report.control_totals, "dataset_sha256": source.sha256}
    )
