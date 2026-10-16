"""Scheduler lifecycle for one frozen release-validation group (REPLAY_VERIFY)."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import (
    contract_computation,
    job,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.enums import JobKind, VerificationOutcome
from erev_api.jobs.context import JobContext, JobLost, try_unit_lock
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .replay_execution import execute_running
from .replay_sources import execution_identity
from .replay_verify import Trigger


def _bound(
    uow: UnitOfWork, job_id: UUID
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]] | None:
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    tenant_id = uow.principal.tenant_id
    selected = uow.session.execute(
        select(
            release_validation_group.c.id,
            release_validation_group.c.release_validation_attempt_id,
            release_validation_attempt.c.release_validation_id,
        )
        .join(
            job,
            (job.c.tenant_id == release_validation_group.c.tenant_id)
            & (job.c.id == release_validation_group.c.child_job_id),
        )
        .join(
            release_validation_attempt,
            (release_validation_attempt.c.tenant_id == release_validation_group.c.tenant_id)
            & (
                release_validation_attempt.c.id
                == release_validation_group.c.release_validation_attempt_id
            ),
        )
        .where(
            release_validation_group.c.tenant_id == tenant_id,
            job.c.id == job_id,
            job.c.kind == "REPLAY_VERIFY",
            job.c.subject_type == "combination_group",
            job.c.subject_id == release_validation_group.c.combination_group_id,
        )
    ).one_or_none()
    if selected is None:
        return None
    rows = []
    for table, row_id in (
        (release_validation, selected.release_validation_id),
        (release_validation_attempt, selected.release_validation_attempt_id),
        (release_validation_group, selected.id),
    ):
        row = (
            uow.session.execute(
                select(table)
                .where(table.c.tenant_id == tenant_id, table.c.id == row_id)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one()
        )
        rows.append(dict(row))
    parent, attempt, group = rows
    if group["child_job_id"] != job_id:
        return None
    return parent, attempt, group


def _move(uow: UnitOfWork, group: Mapping[str, Any], state: str) -> None:
    if group["orchestration_state"] == state:
        return
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
    apply(
        uow.session,
        "release_validation_group",
        group["id"],
        to_status=state,
        expected_status=group["orchestration_state"],
        expected_row_version=group["row_version"],
        set_values={
            "row_version": group["row_version"] + 1,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="release_validation_group.orchestrate",
        object_type="release_validation_group",
        object_id=group["id"],
        contract_ids=tuple(UUID(key) for key in members or {}),
        before={"orchestration_state": group["orchestration_state"]},
        after={"orchestration_state": state},
    )


def _terminal(uow: UnitOfWork, job_id: UUID, state: str) -> None:
    bound = _bound(uow, job_id)
    if bound is not None and bound[2]["orchestration_state"] in {"PENDING", "RUNNING", "RETRYABLE"}:
        _move(uow, bound[2], state)


def failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    # failure_problem supplies the authoritative job instance, even when params are malformed.
    prefix = "/api/v1/jobs/"
    instance = str(problem.get("instance", ""))
    if not instance.startswith(prefix):
        raise Problem("validation-failed", "Replay failure is missing its job identity.")
    job_id = UUID(instance[len(prefix) :])
    row = uow.session.execute(
        select(job.c.state, job.c.kind).where(
            job.c.tenant_id == uow.principal.tenant_id, job.c.id == job_id
        )
    ).one_or_none()
    if row is None or row.state != "FAILED" or row.kind != "REPLAY_VERIFY":
        return
    # The registry holds the job row; never wait on a worker that may need that row to commit.
    if not try_unit_lock(uow.session, job_id):
        raise Problem("lock-conflict")
    _terminal(uow, job_id, "FAILED_EXHAUSTED")


def guard_cancel(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    # cancel_job already holds the job row. Nonblocking acquisition avoids lock inversion.
    if not try_unit_lock(uow.session, job_id):
        raise Problem("lock-conflict")
    bound = _bound(uow, job_id)
    if bound is not None and bound[2]["accepted_verification_id"] is not None:
        raise Problem("invalid-transition", "The replay result has already been accepted.")


def cancelled(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    if not try_unit_lock(uow.session, job_id):
        raise Problem("lock-conflict")
    _terminal(uow, job_id, "CANCELLED")


def _cancel_running(context: JobContext) -> JobOutcome:
    with context.unit_of_work() as uow:
        execution_identity(uow, context)
        _terminal(uow, context.job_id, "CANCELLED")
        uow.commit()
    return JobOutcome("SUCCEEDED", {"cancelled": True})


@task(
    JobKind.REPLAY_VERIFY,
    retry=RetryPolicy(max_attempts=3),
    on_failure=failed,
    failure_hook_required=True,
    on_cancel=cancelled,
    cancel_guard=guard_cancel,
)
def replay(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    try:
        attempt_id = UUID(str(params["release_validation_attempt_id"]))
        group_id = UUID(str(params["combination_group_id"]))
        trigger: Trigger = params["trigger"]
        if trigger not in {"REPLAY_VERIFY", "UPGRADE_VALIDATE"}:
            raise ValueError("trigger")
    except (KeyError, ValueError, TypeError) as error:
        raise Problem(
            "validation-failed", "Replay requires its frozen attempt, group and trigger."
        ) from error
    if context.cancel_requested():
        return _cancel_running(context)
    with context.unit_of_work() as uow:
        _, process = execution_identity(uow, context)
        bound = _bound(uow, context.job_id)
        if bound is None:
            raise Problem("not-found")
        parent, attempt, group = bound
        if (
            attempt["id"] != attempt_id
            or group["combination_group_id"] != group_id
            or parent["engine_release_id"] != process.engine_release_id
        ):
            raise Problem("validation-failed", "Replay job does not match its frozen selection.")
        if group["accepted_verification_id"] is None:
            if parent["status"] != "RUNNING" or attempt["status"] != "RUNNING":
                raise Problem("invalid-transition")
            if group["orchestration_state"] not in {"PENDING", "RETRYABLE", "RUNNING"}:
                raise Problem("invalid-transition")
            _move(uow, group, "RUNNING")
        uow.commit()
    try:
        result = execute_running(context, attempt_id=attempt_id, group_id=group_id, trigger=trigger)
    except JobLost:
        if context.cancel_requested():
            return _cancel_running(context)
        raise
    except Exception:
        if context.cancel_requested():
            return _cancel_running(context)
        with context.unit_of_work() as uow:
            bound = _bound(uow, context.job_id)
            if bound is not None and bound[2]["orchestration_state"] == "RUNNING":
                _move(uow, bound[2], "RETRYABLE")
            uow.commit()
        raise
    if context.cancel_requested():
        return _cancel_running(context)
    if result.outcome is VerificationOutcome.ERROR:
        with context.unit_of_work() as uow:
            bound = _bound(uow, context.job_id)
            if bound is not None and bound[2]["orchestration_state"] == "RUNNING":
                _move(uow, bound[2], "RETRYABLE")
            uow.commit()
        raise RuntimeError("Replay execution failed; error evidence retained for retry.")
    return JobOutcome(
        "SUCCEEDED"
        if result.outcome in {VerificationOutcome.MATCH, VerificationOutcome.NO_SOURCE}
        else "SUCCEEDED_WITH_EXCEPTIONS",
        {"verification_id": str(result.row_id), "outcome": result.outcome.value},
    )
