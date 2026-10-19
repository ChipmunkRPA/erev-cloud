"""Reassess replay evidence and population before publication or final acceptance."""

from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import (
    computation_verification as verification,
)
from erev_api.db.tables import (
    job,
    release_validation,
    release_validation_attempt,
)
from erev_api.db.tables import (
    release_validation_group as selection,
)
from erev_api.enums import ValidationGroupOrchestrationState as State
from erev_api.enums import VerificationOutcome
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .release_validation import Aggregate, GroupResult, aggregate
from .validation_population import read


def assess(uow: UnitOfWork, *, validation_id: UUID, attempt_id: UUID) -> Aggregate:
    """Return a decision from stored facts, without completing or enabling the validation.

    Hold the parent/attempt locks through the caller's transaction, as result writers do.
    Completed attempts are reassessed from current population/job facts, never a cached
    publication decision. This does not attach/verify reports or enable the release. Final
    acceptance must call it in its own transaction and fence concurrent population writers.
    Job rows are read without locking: cancellation takes the job lock before parents.
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
    if (
        parent["status"] != "RUNNING"
        or attempt["status"] not in {"RUNNING", "COMPLETE", "INCOMPLETE"}
        or parent["effective_level"] not in {"MINOR", "MAJOR"}
        or parent["enabled_at"] is not None
        or parent["accepted_attempt_id"] is not None
    ):
        raise Problem("invalid-transition")
    completed = attempt["status"] in {"COMPLETE", "INCOMPLETE"}
    if completed and (attempt["dataset_file_id"] is None or attempt["dataset_sha256"] is None):
        raise Problem("validation-failed", "The completed attempt has no retained dataset.")
    if (
        attempt["population"].get("fingerprint_version") != 1
        or attempt["population"].get("fingerprint") != read(uow).fingerprint()
    ):
        raise Problem("validation-failed", "The frozen validation population changed.")
    rows = (
        uow.session.execute(
            select(
                selection,
                job.c.state.label("job_state"),
                job.c.kind.label("job_kind"),
                job.c.subject_id.label("job_group"),
                job.c.subject_type.label("job_subject"),
                verification.c.id.label("result_id"),
                verification.c.outcome,
                verification.c.job_id.label("result_job"),
                verification.c.combination_group_id.label("result_group"),
                verification.c.release_validation_attempt_id.label("result_attempt"),
                verification.c.source_computation_id.label("result_source"),
                verification.c.process_engine_release_id.label("result_release"),
            )
            .select_from(
                selection.outerjoin(
                    job,
                    (job.c.tenant_id == selection.c.tenant_id)
                    & (job.c.id == selection.c.child_job_id),
                ).outerjoin(
                    verification,
                    (verification.c.tenant_id == selection.c.tenant_id)
                    & (verification.c.id == selection.c.accepted_verification_id),
                )
            )
            .where(
                selection.c.tenant_id == tenant,
                selection.c.release_validation_attempt_id == attempt_id,
            )
            .order_by(selection.c.combination_group_id)
        )
        .mappings()
        .all()
    )
    population = attempt["population"]
    expected_open = population.get("open_activity")
    expected_sampled = population.get("sampled")
    if (
        type(expected_open) is not int
        or type(expected_sampled) is not int
        or expected_open < 0
        or expected_sampled < 0
        or len(rows) != expected_open + expected_sampled
        or sum(row["selection"] == "OPEN_ACTIVITY" for row in rows) != expected_open
    ):
        raise Problem("validation-failed", "The frozen selection is incomplete.")
    facts = []
    for row in rows:
        state = State(row["orchestration_state"])
        outcome = None
        if row["child_job_id"] is None:
            if state != State.PENDING or row["accepted_verification_id"] is not None:
                raise Problem("validation-failed", "The selection has no bound replay job.")
        elif (
            row["job_state"] is None
            or row["job_kind"] != "REPLAY_VERIFY"
            or row["job_subject"] != "combination_group"
            or row["job_group"] != row["combination_group_id"]
        ):
            raise Problem("validation-failed", "The selection has an invalid replay job.")
        if row["accepted_verification_id"] is not None:
            if (
                row["result_id"] is None
                or row["result_job"] != row["child_job_id"]
                or row["result_group"] != row["combination_group_id"]
                or row["result_attempt"] != attempt_id
                or row["result_source"] != row["source_computation_id"]
                or row["result_release"] != parent["engine_release_id"]
                or state != State.COMPLETE
            ):
                raise Problem("validation-failed", "The accepted replay evidence is not bound.")
            outcome = VerificationOutcome(row["outcome"])
        # Acceptance precedes the worker's terminal job update. Do not pass in that window.
        if row["job_state"] == "QUEUED":
            state = State.PENDING
        elif row["job_state"] == "RUNNING":
            state = State.RUNNING
        elif row["job_state"] == "FAILED":
            state = State.FAILED_EXHAUSTED
        elif row["job_state"] == "CANCELLED":
            state = State.CANCELLED
        elif row["job_state"] in {"SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"}:
            state = State.COMPLETE
        facts.append(GroupResult(state, outcome))
    decision = aggregate(parent["effective_level"], facts)
    if completed and (
        decision.status is None
        or (decision.status == "INCOMPLETE") != (attempt["status"] == "INCOMPLETE")
    ):
        raise Problem("validation-failed", "The attempt completion disagrees with its replay jobs.")
    return decision
