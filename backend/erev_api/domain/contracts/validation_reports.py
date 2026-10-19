"""Attach verified report evidence once, without accepting or enabling a release."""

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select

from erev_api.db.tables import (
    approval_request,
    job,
    release_validation,
    release_validation_attempt,
    report_run,
)
from erev_api.db.transitions import apply
from erev_api.domain.reports.builders.upgrade_validation import CODE, build
from erev_api.domain.reports.framework import report_params
from erev_api.domain.reports.requester import require_export
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class ReportWitness:
    validation_id: UUID
    attempt_id: UUID
    report_id: UUID
    parent_version: int
    attempt_version: int
    before: dict[str, Any]
    after: dict[str, Any]
    differences: bool


def attach(uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID, report_id: UUID) -> UUID:
    """Verify and attach a finished report once in the caller's transaction."""
    _check(
        uow, validation_id=validation_id, attempt_id=attempt_id, report_id=report_id, attach=True
    )
    return report_id


def verify_attached(
    uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID, report_id: UUID
) -> ReportWitness:
    """Read retained bytes before taking the population fence; bind subsequent locked checks.

    No row is written or locked here. Acceptance must compare both versions under its locks.
    Report and dataset evidence are immutable once attached.
    """
    return _check(
        uow, validation_id=validation_id, attempt_id=attempt_id, report_id=report_id, attach=False
    )


def _check(
    uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID, report_id: UUID, attach: bool
) -> ReportWitness:
    if attach and uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    tenant = uow.principal.tenant_id

    def held(query: Select[Any]) -> Select[Any]:
        return query.with_for_update(key_share=True) if attach else query

    parent = (
        uow.session.execute(
            held(
                select(release_validation).where(
                    release_validation.c.tenant_id == tenant,
                    release_validation.c.id == validation_id,
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    attempt = (
        uow.session.execute(
            held(
                select(release_validation_attempt).where(
                    release_validation_attempt.c.tenant_id == tenant,
                    release_validation_attempt.c.id == attempt_id,
                    release_validation_attempt.c.release_validation_id == validation_id,
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if parent is None or attempt is None:
        raise Problem("not-found")
    existing = attempt["report_run_id"]
    if not attach and existing is None:
        raise Problem("invalid-transition", "Attach the verified report before acceptance.")
    if existing is not None and existing != report_id:
        raise Problem("invalid-transition", "The validation attempt already has a report.")
    if existing is None and (
        attempt["status"] not in {"COMPLETE", "INCOMPLETE"}
        or parent["status"] != "RUNNING"
        or parent["enabled_at"] is not None
        or parent["accepted_attempt_id"] is not None
    ):
        raise Problem("invalid-transition")
    run = (
        uow.session.execute(
            select(report_run, job.c.state.label("job_state"), job.c.kind.label("job_kind"))
            .join(
                job, (job.c.tenant_id == report_run.c.tenant_id) & (job.c.id == report_run.c.job_id)
            )
            .where(report_run.c.tenant_id == tenant, report_run.c.id == report_id)
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise Problem("not-found")
    if (
        run["status"] != "SUCCEEDED"
        or run["job_state"] not in {"SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"}
        or run["job_kind"] != "REPORT_RUN"
        or run["report_code"] != CODE
        or run["parameters"].get("release_validation_attempt_id") != str(attempt_id)
        or run["source_binding"] is None
        or run["output_file_id"] is None
    ):
        raise Problem("invalid-transition", "A completed report for this attempt is required.")
    require_export(uow.principal, run["output_format"], run["entity_ids"])
    # The builder rechecks current permission and the exact retained attempt/file/hash binding.
    try:
        params = report_params(dict(run))
    except (ValueError, TypeError, KeyError) as error:
        raise Problem("validation-failed", "The report source binding is invalid.") from error
    data = build(uow, params)
    if (
        params.binding is None
        or params.binding.dataset
        != {"output_sha256": run["output_sha256"], "format": run["output_format"]}
        or params.binding.row_keys != frozenset(str(row["row_key"]) for row in data.rows)
    ):
        raise Problem("validation-failed", "The report output binding differs from its source.")
    if data.row_count != run["row_count"] or dict(data.control_totals) != run["control_totals"]:
        raise Problem("validation-failed", "The report totals differ from its retained source.")
    metadata, stream = open_file(
        uow.session, run["output_file_id"], files=uow.files, keyring=uow.keyring
    )
    with stream:
        content = stream.read()
    if (
        metadata["purpose"] != "REPORT_OUTPUT"
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != run["output_sha256"]
        or hashlib.sha256(content).hexdigest() != run["output_sha256"]
    ):
        raise Problem("validation-failed", "The retained report output failed integrity checks.")
    witness = ReportWitness(
        validation_id,
        attempt_id,
        report_id,
        parent["row_version"],
        attempt["row_version"],
        {
            "report_run_id": str(report_id),
            "rows": [
                {"row_key": row["row_key"], "value": row.get("expected_output_sha256")}
                for row in data.rows
            ],
        },
        {
            "report_run_id": str(report_id),
            "dataset_sha256": attempt["dataset_sha256"],
            "rows": [
                {"row_key": row["row_key"], "value": row.get("actual_output_sha256")}
                for row in data.rows
            ],
        },
        any(row.get("outcome") == "DIFFERENCES" for row in data.rows),
    )
    if existing is not None:
        return witness
    apply(
        uow.session,
        "release_validation_attempt",
        attempt_id,
        to_status=None,
        expected_status=attempt["status"],
        expected_row_version=attempt["row_version"],
        set_values={
            "report_run_id": report_id,
            "row_version": attempt["row_version"] + 1,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="release_validation_attempt.report",
        object_type="release_validation_attempt",
        object_id=attempt_id,
        before={"report_run_id": None},
        after={"report_run_id": report_id},
    )
    return witness


def verify_approval_evidence(
    uow: UnitOfWork, *, attempt_id: UUID, request_id: UUID
) -> ReportWitness:
    """Verify frozen files inside the authorized approval callback, before its population fence.

    The approval engine has checked the decider against every frozen entity. The approved
    request is the authority here; report export permissions are not an additional approval
    requirement. This function cannot authorize a pending request or another subject.
    """
    request = (
        uow.session.execute(
            select(approval_request).where(
                approval_request.c.id == request_id,
                approval_request.c.subject_type == "ENGINE_RELEASE_VALIDATION",
                approval_request.c.subject_id == attempt_id,
                approval_request.c.status == "APPROVED",
            )
        )
        .mappings()
        .one_or_none()
    )
    attempt = (
        uow.session.execute(
            select(release_validation_attempt).where(
                release_validation_attempt.c.id == attempt_id,
                release_validation_attempt.c.approval_request_id == request_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if request is None or attempt is None:
        raise Problem("forbidden")
    parent = (
        uow.session.execute(
            select(release_validation).where(
                release_validation.c.id == attempt["release_validation_id"],
            )
        )
        .mappings()
        .one()
    )
    run = (
        uow.session.execute(
            select(report_run).where(
                report_run.c.id == attempt["report_run_id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        run is None
        or run["status"] != "SUCCEEDED"
        or run["report_code"] != CODE
        or run["parameters"].get("release_validation_attempt_id") != str(attempt_id)
        or attempt["dataset_file_id"] is None
        or attempt["dataset_sha256"] is None
    ):
        raise Problem("validation-failed", "The approved report evidence is incomplete.")
    for file_id, expected, purpose in (
        (attempt["dataset_file_id"], attempt["dataset_sha256"], "VALIDATION_DATASET"),
        (run["output_file_id"], run["output_sha256"], "REPORT_OUTPUT"),
    ):
        metadata, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
        with stream:
            content = stream.read()
        if (
            metadata["purpose"] != purpose
            or metadata["size_bytes"] != len(content)
            or metadata["sha256"] != expected
            or hashlib.sha256(content).hexdigest() != expected
        ):
            raise Problem(
                "validation-failed", "The approved report evidence failed integrity checks."
            )
    return ReportWitness(
        parent["id"],
        attempt_id,
        run["id"],
        parent["row_version"],
        attempt["row_version"],
        {},
        {},
        True,
    )
