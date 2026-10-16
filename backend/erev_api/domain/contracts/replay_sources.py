"""Load the frozen source of a running replay job without reconstructing historical inputs.

Reads do not lock the business population through engine execution. The result writer must
recheck the attempt, selection and source head under its locks before accepting any result.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import (
    computation_evidence,
    contract_computation,
    contract_version,
    job,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.enums import FilePurpose, JobKind
from erev_api.files.store import open_file
from erev_api.jobs.context import JobContext
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .release_validation import ExecutionToken
from .replay_verify import EvidenceFacts, ProcessFacts, SourceFacts, Trigger


@dataclass(frozen=True, slots=True)
class FrozenReplay:
    attempt_id: UUID
    group_id: UUID
    token: ExecutionToken
    process: ProcessFacts
    source: SourceFacts | None
    evidence: EvidenceFacts | None


def _file(uow: UnitOfWork, row: Mapping[Any, Any], side: str) -> tuple[bytes, bool]:
    meta, stream = open_file(
        uow.session, row[f"{side}_file_id"], files=uow.files, keyring=uow.keyring
    )
    with stream:
        content = stream.read()
    purpose = FilePurpose.COMPUTATION_INPUT if side == "input" else FilePurpose.COMPUTATION_OUTPUT
    return content, (
        meta["purpose"] == purpose
        and meta["media_type"] == "application/json"
        and meta["size_bytes"] == len(content)
        and meta["sha256"] == row[f"{side}_file_sha256"]
    )


def execution_identity(uow: UnitOfWork, context: JobContext) -> tuple[ExecutionToken, ProcessFacts]:
    """Bind every replay read, including completed-result retries, to its live execution."""
    runtime = context.runtime.attempt
    process = context.runtime.engine_release
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    if (
        context.kind is not JobKind.REPLAY_VERIFY
        or context.tenant_id != uow.principal.tenant_id
        or runtime is None
        or runtime.job_id != context.job_id
        or runtime.tenant_id != context.tenant_id
        or context.task_id is None
        or context.attempt is None
        or process is None
    ):
        raise Problem("validation-failed", "Replay requires a persisted execution identity.")
    runtime.enter(uow, context.clock)
    if (
        uow.session.scalar(
            select(job.c.kind).where(
                job.c.tenant_id == context.tenant_id, job.c.id == context.job_id
            )
        )
        != "REPLAY_VERIFY"
    ):
        raise Problem("not-found")
    return (
        ExecutionToken(context.job_id, context.task_id, context.attempt),
        ProcessFacts(process.id, process.engine_version),
    )


def load(
    uow: UnitOfWork,
    *,
    context: JobContext,
    attempt_id: UUID,
    group_id: UUID,
    trigger: Trigger,
) -> FrozenReplay:
    """Authorize the persisted execution before opening either encrypted evidence file.

    Missing retained files/evidence remain missing. Runtime mismatch is returned without
    opening files so verify() preserves runtime-first refusal. Infrastructure/decryption errors
    propagate; they must never be converted into an empty or rebuilt successful computation.
    """
    token, process_facts = execution_identity(uow, context)
    if trigger not in {"REPLAY_VERIFY", "UPGRADE_VALIDATE"}:
        raise Problem("validation-failed", "Unknown replay trigger.")
    tenant_id = uow.principal.tenant_id
    selected = uow.session.execute(
        select(release_validation_group.c.source_computation_id)
        .select_from(
            release_validation_group.join(
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
            .join(
                job,
                (job.c.tenant_id == release_validation_group.c.tenant_id)
                & (job.c.id == release_validation_group.c.child_job_id),
            )
        )
        .where(
            release_validation_group.c.tenant_id == tenant_id,
            release_validation_group.c.release_validation_attempt_id == attempt_id,
            release_validation_group.c.combination_group_id == group_id,
            release_validation_group.c.orchestration_state == "RUNNING",
            release_validation_attempt.c.status == "RUNNING",
            release_validation.c.status == "RUNNING",
            release_validation.c.engine_release_id == process_facts.engine_release_id,
            job.c.id == context.job_id,
            job.c.kind == "REPLAY_VERIFY",
            job.c.state == "RUNNING",
            job.c.procrastinate_job_id == context.task_id,
        )
    ).one_or_none()
    if selected is None:
        raise Problem("not-found")
    if selected.source_computation_id is None:
        return FrozenReplay(attempt_id, group_id, token, process_facts, None, None)
    source_row = (
        uow.session.execute(
            select(contract_computation).where(
                contract_computation.c.tenant_id == tenant_id,
                contract_computation.c.id == selected.source_computation_id,
                contract_computation.c.combination_group_id == group_id,
                contract_computation.c.status == "SUCCEEDED",
            )
        )
        .mappings()
        .one_or_none()
    )
    if source_row is None:
        raise Problem(
            "validation-failed", "The frozen source is not a successful group computation."
        )
    hashes = dict(
        uow.session.execute(
            select(contract_version.c.book_code, contract_version.c.output_sha256).where(
                contract_version.c.tenant_id == tenant_id,
                contract_version.c.contract_computation_id == selected.source_computation_id,
            )
        )
        .tuples()
        .all()
    )
    source = SourceFacts(
        source_row["id"],
        group_id,
        source_row["engine_release_id"],
        source_row["engine_version"],
        source_row["input_sha256"],
        hashes,
        source_row["cutoff_at"],
    )
    result = FrozenReplay(attempt_id, group_id, token, process_facts, source, None)
    if trigger == "REPLAY_VERIFY" and source.engine_version != process_facts.engine_version:
        return result
    evidence = (
        uow.session.execute(
            select(computation_evidence).where(
                computation_evidence.c.tenant_id == tenant_id,
                computation_evidence.c.contract_computation_id == source.computation_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None:
        return result
    try:
        input_bytes, input_valid = _file(uow, evidence, "input")
    except FileNotFoundError:
        return result
    except Problem as error:
        if error.slug == "not-found":
            return result
        raise
    # Keep the input facts even if output is missing: an input integrity incident takes
    # precedence over unavailable output. Empty bytes here are explicitly marked absent.
    output_present = True
    try:
        output_bytes, output_valid = _file(uow, evidence, "output")
    except FileNotFoundError:
        output_bytes, output_valid, output_present = b"", False, False
    except Problem as error:
        if error.slug != "not-found":
            raise
        output_bytes, output_valid, output_present = b"", False, False
    facts = EvidenceFacts(
        input_bytes,
        evidence["input_file_sha256"],
        output_bytes,
        evidence["output_file_sha256"],
        evidence["output_sha256"],
        tuple(evidence["book_codes"]),
        evidence["codec"],
        input_metadata_valid=input_valid and evidence["input_sha256"] == source.input_sha256,
        output_metadata_valid=output_valid,
        output_present=output_present,
    )
    return FrozenReplay(attempt_id, group_id, token, process_facts, source, facts)
