"""Execute one RUNNING frozen selection, with no database transaction held during the engine.

The scheduler adapter owns PENDING/RETRYABLE transitions and retry/failure/cancellation policy.
This service returns ERROR evidence without accepting it; callers must not treat it as success.
"""

import time
from dataclasses import dataclass
from uuid import UUID

from erev_engine import compute
from sqlalchemy import select

from erev_api.db.tables import (
    computation_verification,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.enums import VerificationOutcome
from erev_api.jobs.context import JobContext, JobLost
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from . import replay_sources, verification_store
from .replay_verify import Engine, Trigger, no_source, verify


@dataclass(frozen=True, slots=True)
class ReplayResult:
    row_id: UUID
    outcome: VerificationOutcome
    accepted: bool


def _existing(
    uow: UnitOfWork, context: JobContext, attempt_id: UUID, group_id: UUID, trigger: Trigger
) -> ReplayResult | None:
    token, process = replay_sources.execution_identity(uow, context)
    selection = (
        uow.session.execute(
            select(release_validation_group)
            .join(
                release_validation_attempt,
                (release_validation_attempt.c.tenant_id == release_validation_group.c.tenant_id)
                & (
                    release_validation_attempt.c.id
                    == release_validation_group.c.release_validation_attempt_id
                ),
            )
            .join(
                release_validation,
                (release_validation.c.tenant_id == release_validation_attempt.c.tenant_id)
                & (release_validation.c.id == release_validation_attempt.c.release_validation_id),
            )
            .where(
                release_validation_group.c.tenant_id == context.tenant_id,
                release_validation_group.c.release_validation_attempt_id == attempt_id,
                release_validation_group.c.combination_group_id == group_id,
                release_validation_group.c.child_job_id == context.job_id,
                release_validation.c.engine_release_id == process.engine_release_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if selection is None:
        raise Problem("not-found")
    accepted_id = selection["accepted_verification_id"]
    conditions = [
        computation_verification.c.tenant_id == context.tenant_id,
        computation_verification.c.release_validation_attempt_id == attempt_id,
        computation_verification.c.combination_group_id == group_id,
    ]
    if accepted_id is not None:
        conditions.append(computation_verification.c.id == accepted_id)
    else:
        conditions.extend(
            [
                computation_verification.c.job_id == token.job_id,
                computation_verification.c.task_id == token.task_id,
            ]
        )
    prior = (
        uow.session.execute(select(computation_verification).where(*conditions))
        .mappings()
        .one_or_none()
    )
    if prior is None:
        if accepted_id is not None:
            raise Problem("validation-failed", "The accepted replay result is missing.")
        return None
    if (
        prior["source_computation_id"] != selection["source_computation_id"]
        or prior["process_engine_release_id"] != process.engine_release_id
        or prior["process_engine_version"] != process.engine_version
        or prior["trigger"] != trigger
        or (
            accepted_id is None
            and (prior["attempt"] != token.attempt or prior["outcome"] != "ERROR")
        )
        or (
            accepted_id is not None
            and (selection["orchestration_state"] != "COMPLETE" or prior["outcome"] == "ERROR")
        )
    ):
        raise Problem(
            "validation-failed", "The stored replay result does not match this execution."
        )
    return ReplayResult(prior["id"], VerificationOutcome(prior["outcome"]), accepted_id is not None)


def execute_running(
    context: JobContext,
    *,
    attempt_id: UUID,
    group_id: UUID,
    trigger: Trigger,
    engine: Engine = compute,
) -> ReplayResult:
    """Load, execute and persist once; committed results are reused before file or engine access."""
    if trigger not in {"REPLAY_VERIFY", "UPGRADE_VALIDATE"}:
        raise Problem("validation-failed", "Unknown replay trigger.")
    with context.unit_of_work() as uow:
        prior = _existing(uow, context, attempt_id, group_id, trigger)
        if prior is not None:
            uow.commit()
            return prior
        frozen = replay_sources.load(
            uow, context=context, attempt_id=attempt_id, group_id=group_id, trigger=trigger
        )
        uow.commit()
    began = time.monotonic()
    if frozen.source is None:
        result = no_source(
            trigger=trigger,
            group_id=group_id,
            process=frozen.process,
            token=frozen.token,
            attempt_id=attempt_id,
        )
    else:
        result = verify(
            trigger=trigger,
            source=frozen.source,
            evidence=frozen.evidence,
            process=frozen.process,
            engine=engine,
            token=frozen.token,
            attempt_id=attempt_id,
        )
    duration_ms = max(0, int((time.monotonic() - began) * 1000))
    with context.unit_of_work() as uow:
        saved = verification_store.persist(uow, result, context=context, duration_ms=duration_ms)
        if saved.result == "fenced":
            raise JobLost(context.job_id)
        # A competing delivery can have committed first. Read that persisted outcome rather
        # than reporting a locally computed outcome that the writer did not insert.
        row = uow.session.execute(
            select(computation_verification.c.id, computation_verification.c.outcome).where(
                computation_verification.c.tenant_id == context.tenant_id,
                computation_verification.c.id == (saved.accepted_id or saved.row_id),
            )
        ).one()
        uow.commit()
    return ReplayResult(row.id, VerificationOutcome(row.outcome), saved.accepted_id is not None)
