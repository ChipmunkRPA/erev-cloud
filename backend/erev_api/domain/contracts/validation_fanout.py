"""Bind one durable replay job to each frozen selection before dispatch (RCP-29)."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from erev_api.controls.release import current_release
from erev_api.db.tables import (
    contract_computation,
    job,
    release_validation,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.enums import JobKind
from erev_api.jobs.registry import RELEASE_PARAM, SCHEDULER_LOCK_PARAM, defer, ensure_dispatched
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .replay_verify import Trigger
from .validation_attempts import start


@dataclass(frozen=True, slots=True)
class Fanout:
    job_ids: tuple[UUID, ...]
    created: int
    recovery_requested: int


def enqueue(
    uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID, trigger: Trigger = "UPGRADE_VALIDATE"
) -> Fanout:
    """Start/check the frozen attempt and bind all jobs in the caller's transaction.

    Retries reuse their jobs and never redraw the sample. Only a QUEUED job without a task
    pointer requests after-commit recovery; stranded tasks keep the scheduler's retry budget.
    """
    if trigger not in {"REPLAY_VERIFY", "UPGRADE_VALIDATE"}:
        raise Problem("validation-failed", "Unknown replay trigger.")
    # Takes the validation/attempt locks and checks the full-population fingerprint, also on retry.
    start(uow, validation_id=validation_id, attempt_id=attempt_id)
    release = current_release()
    target = uow.session.scalar(
        select(release_validation.c.engine_release_id).where(
            release_validation.c.tenant_id == uow.principal.tenant_id,
            release_validation.c.id == validation_id,
        )
    )
    if release is None or release.id != target:
        raise Problem("release-mismatch")
    groups = (
        uow.session.execute(
            select(release_validation_group)
            .where(
                release_validation_group.c.tenant_id == uow.principal.tenant_id,
                release_validation_group.c.release_validation_attempt_id == attempt_id,
            )
            .order_by(release_validation_group.c.combination_group_id)
            .with_for_update(key_share=True)
        )
        .mappings()
        .all()
    )
    bindings = []
    for group in groups:
        group_id = group["combination_group_id"]
        params = {
            "release_validation_attempt_id": str(attempt_id),
            "combination_group_id": str(group_id),
            "trigger": trigger,
        }
        lock = f"verify:{uow.principal.tenant_id}:{group_id}"
        child_id = group["child_job_id"]
        if child_id is None:
            if (
                group["orchestration_state"] != "PENDING"
                or group["accepted_verification_id"] is not None
            ):
                raise Problem(
                    "invalid-transition", "Only an unassigned pending selection can receive a job."
                )
        else:
            child = (
                uow.session.execute(
                    select(job).where(
                        job.c.tenant_id == uow.principal.tenant_id, job.c.id == child_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                child is None
                or child["kind"] != "REPLAY_VERIFY"
                or child["subject_type"] != "combination_group"
                or child["subject_id"] != group_id
                or child["queue"] != "compute"
                or child["params"]
                != {**params, RELEASE_PARAM: str(release.id), SCHEDULER_LOCK_PARAM: lock}
            ):
                raise Problem(
                    "validation-failed", "The existing job does not match the frozen selection."
                )
        bindings.append((group, params, lock))
    created = recovery = 0
    jobs = []
    for group, params, lock in bindings:
        child_id = group["child_job_id"]
        if child_id is not None:
            recovery += int(ensure_dispatched(uow, child_id))
            jobs.append(child_id)
            continue
        created_job = defer(
            uow,
            JobKind.REPLAY_VERIFY,
            params,
            subject_type="combination_group",
            subject_id=group["combination_group_id"],
            lock=lock,
        )
        child_id = created_job["id"]
        apply(
            uow.session,
            "release_validation_group",
            group["id"],
            to_status=None,
            expected_status="PENDING",
            expected_row_version=group["row_version"],
            set_values={
                "child_job_id": child_id,
                "row_version": group["row_version"] + 1,
                "updated_at": uow.now,
                "updated_by": uow.principal.id,
                "updated_by_kind": uow.principal.kind.value,
            },
        )
        members = (
            None
            if group["source_computation_id"] is None
            else uow.session.scalar(
                select(contract_computation.c.stream_heads).where(
                    contract_computation.c.tenant_id == uow.principal.tenant_id,
                    contract_computation.c.id == group["source_computation_id"],
                )
            )
        )
        uow.audit(
            action="release_validation_group.enqueue",
            object_type="release_validation_group",
            object_id=group["id"],
            contract_ids=tuple(UUID(key) for key in members or {}),
            before={"child_job_id": None},
            after={"child_job_id": child_id},
        )
        jobs.append(child_id)
        created += 1
    return Fanout(tuple(jobs), created, recovery)
