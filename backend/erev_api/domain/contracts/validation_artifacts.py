"""Retain one immutable validation dataset after every selected job is terminal."""

import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import (
    computation_verification,
    job,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .upgrade_report import AttemptFacts, GroupDatasetRow, build_validation_dataset
from .validation_aggregation import assess


@dataclass(frozen=True, slots=True)
class Dataset:
    file_id: UUID
    sha256: str


def _invalid() -> Problem:
    return Problem(
        "validation-failed", "The retained validation evidence is incomplete or invalid."
    )


def _read(uow: UnitOfWork, file_id: UUID, digest: str | None = None) -> dict[str, Any]:
    meta, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read()
    if (
        meta["purpose"] != "VALIDATION_DATASET"
        or meta["media_type"] != "application/json"
        or meta["size_bytes"] != len(content)
        or meta["sha256"] != hashlib.sha256(content).hexdigest()
        or (digest is not None and digest != meta["sha256"])
    ):
        raise _invalid()
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or canonical_bytes(payload) != content:
            raise _invalid()
    except (ValueError, TypeError, UnicodeError) as error:
        raise _invalid() from error
    return payload


def differences(uow: UnitOfWork, row: Mapping[str, Any]) -> tuple[Mapping[str, object], ...]:
    """Read a comparison's retained rows, binding metadata, envelope and summary to its result."""
    summary = row["difference_summary"]
    file_id = row["difference_file_id"]
    compared = row["trigger"] == "UPGRADE_VALIDATE" and row["outcome"] in {"MATCH", "DIFFERENCES"}
    if summary is None:
        if file_id is not None or compared:
            raise _invalid()
        return ()
    if file_id is None or not compared or not row["engine_executed"]:
        raise _invalid()
    payload = _read(uow, file_id)
    expected = {
        "difference_format": 1,
        "verification_id": str(row["id"]),
        "release_validation_attempt_id": str(row["release_validation_attempt_id"]),
        "combination_group_id": str(row["combination_group_id"]),
        "source_computation_id": str(row["source_computation_id"]),
        "process_engine_release_id": str(row["process_engine_release_id"]),
        "job_id": str(row["job_id"]),
        "task_id": row["task_id"],
        "attempt": row["attempt"],
        "summary": summary,
    }
    if (
        set(payload) != {*expected, "differences"}
        or any(payload[key] != value for key, value in expected.items())
        or type(payload["difference_format"]) is not int
        or type(payload["task_id"]) is not int
        or type(payload["attempt"]) is not int
        or not isinstance(payload["differences"], list)
    ):
        raise _invalid()
    rows = payload["differences"]
    counts = dict.fromkeys(("M", "P", "T", "R"), 0)
    paths = []
    for item in rows:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "category", "before", "after"}
            or not isinstance(item["path"], str)
            or not isinstance(item["category"], str)
            or item["category"] not in counts
        ):
            raise _invalid()
        counts[item["category"]] += 1
        if item["category"] == "R":
            paths.append(item["path"])
    if summary != {**counts, "changed_r_paths": paths}:
        raise _invalid()
    return tuple(rows)


def retain(uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID) -> Dataset:
    """Finish the attempt with a frozen dataset in the caller's transaction; never enable it.

    Retries read the original file. A fresh dataset requires terminal jobs and an unchanged
    full population. Parent/attempt locks serialize publishers, result writers and supersession.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden", "Release validation requires the complete tenant population.")
    tenant = uow.principal.tenant_id
    parent = (
        uow.session.execute(
            select(release_validation)
            .where(
                release_validation.c.tenant_id == tenant, release_validation.c.id == validation_id
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    attempt = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(
                release_validation_attempt.c.tenant_id == tenant,
                release_validation_attempt.c.id == attempt_id,
                release_validation_attempt.c.release_validation_id == validation_id,
            )
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    if parent is None or attempt is None:
        raise Problem("not-found")
    facts = AttemptFacts(
        attempt_id,
        validation_id,
        attempt["attempt_no"],
        parent["effective_level"],
        parent["engine_release_id"],
        parent["source_engine_release_id"],
        attempt["seed"],
        attempt["population"],
        tuple(attempt["required_entity_ids"]),
    )
    if attempt["dataset_file_id"] is not None:
        if attempt["status"] not in {"COMPLETE", "INCOMPLETE", "SUPERSEDED"}:
            raise _invalid()
        payload = _read(uow, attempt["dataset_file_id"], attempt["dataset_sha256"])
        expected_attempt = json.loads(build_validation_dataset(facts, ())[0])["attempt"]
        if (
            type(payload.get("dataset_format")) is not int
            or payload["dataset_format"] != 1
            or payload.get("attempt") != expected_attempt
            or not isinstance(payload.get("groups"), list)
        ):
            raise _invalid()
        return Dataset(attempt["dataset_file_id"], attempt["dataset_sha256"])
    decision = assess(uow, validation_id=validation_id, attempt_id=attempt_id)
    if decision.status is None:
        raise Problem("invalid-transition", "Selected replay jobs are still running.")
    selected = (
        uow.session.execute(
            select(release_validation_group, job.c.state.label("job_state"))
            .join(
                job,
                (job.c.tenant_id == release_validation_group.c.tenant_id)
                & (job.c.id == release_validation_group.c.child_job_id),
            )
            .where(
                release_validation_group.c.tenant_id == tenant,
                release_validation_group.c.release_validation_attempt_id == attempt_id,
            )
            .order_by(release_validation_group.c.combination_group_id)
        )
        .mappings()
        .all()
    )
    groups = []
    for group in selected:
        query = select(computation_verification).where(
            computation_verification.c.tenant_id == tenant,
            computation_verification.c.release_validation_attempt_id == attempt_id,
            computation_verification.c.combination_group_id == group["combination_group_id"],
            computation_verification.c.job_id == group["child_job_id"],
        )
        pointer = group["accepted_verification_id"]
        if pointer is not None:
            query = query.where(computation_verification.c.id == pointer)
        found = (
            uow.session.execute(
                query.order_by(
                    computation_verification.c.attempt.desc(),
                    computation_verification.c.task_id.desc(),
                ).limit(1)
            )
            .mappings()
            .one_or_none()
        )
        row: Mapping[str, Any] = dict(found) if found is not None else {}
        if (pointer is not None and found is None) or (
            found is not None
            and (
                row["source_computation_id"] != group["source_computation_id"]
                or row["process_engine_release_id"] != parent["engine_release_id"]
                or (pointer is None and row["outcome"] != "ERROR")
            )
        ):
            raise _invalid()
        state = {
            "FAILED": "FAILED_EXHAUSTED",
            "CANCELLED": "CANCELLED",
            "SUCCEEDED": "COMPLETE",
            "SUCCEEDED_WITH_EXCEPTIONS": "COMPLETE",
        }.get(group["job_state"])
        if state is None:
            raise Problem("invalid-transition")
        groups.append(
            GroupDatasetRow(
                group["combination_group_id"],
                group["selection"],
                tuple(tuple(pair) for pair in group["strata"]),
                group["source_computation_id"],
                state,
                row.get("outcome"),
                row.get("reason")
                or (None if pointer else ("NO_USABLE_RESULT" if state == "COMPLETE" else state)),
                row.get("expected_output_sha256"),
                row.get("actual_output_sha256"),
                row.get("normalised_expected_sha256"),
                row.get("normalised_actual_sha256"),
                row.get("difference_summary"),
                differences(uow, row) if found is not None else (),
            )
        )
    content, digest = build_validation_dataset(facts, groups)
    artifact = store_file(
        uow,
        purpose=FilePurpose.VALIDATION_DATASET,
        stream=io.BytesIO(content),
        original_filename=f"{attempt_id}-validation.json",
        media_type="application/json",
    )
    if artifact["sha256"] != digest or artifact["size_bytes"] != len(content):
        raise _invalid()
    status = "INCOMPLETE" if decision.status == "INCOMPLETE" else "COMPLETE"
    apply(
        uow.session,
        "release_validation_attempt",
        attempt_id,
        to_status=status,
        expected_status="RUNNING",
        expected_row_version=attempt["row_version"],
        set_values={
            "dataset_file_id": artifact["id"],
            "dataset_sha256": digest,
            "row_version": attempt["row_version"] + 1,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="release_validation_attempt.dataset",
        object_type="release_validation_attempt",
        object_id=attempt_id,
        before={"status": "RUNNING", "dataset_file_id": None},
        after={"status": status, "dataset_file_id": artifact["id"], "dataset_sha256": digest},
    )
    return Dataset(artifact["id"], digest)
