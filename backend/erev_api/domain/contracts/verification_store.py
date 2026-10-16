"""Atomic, task-fenced persistence of one frozen release-validation result."""

from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, fields
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import (
    combination_group,
    computation_verification,
    contract_computation,
    job,
    release_validation,
    release_validation_attempt,
    release_validation_group,
)
from erev_api.db.transitions import apply
from erev_api.enums import (
    FilePurpose,
    JobKind,
    ValidationGroupOrchestrationState,
    VerificationOutcome,
)
from erev_api.files.store import store_file
from erev_api.jobs.context import JobContext
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

from .release_validation import ExecutionToken, VerificationWrite, verification_write
from .replay_verify import VerificationRow
from .verification_lock import TransactionExecutionLock


def _invalid(detail: str) -> Problem:
    return Problem("validation-failed", detail)


class _Store:
    def __init__(self, uow: UnitOfWork, result: VerificationRow, duration_ms: int) -> None:
        self.uow = uow
        self.result = result
        self.duration_ms = duration_ms
        self.tenant_id = uow.principal.tenant_id
        self.selection: dict[str, Any] = {}
        self.attempt: dict[str, Any] = {}
        self.validation: dict[str, Any] = {}
        self.pending_pointer: UUID | None = None
        self.contract_ids: tuple[UUID, ...] = ()

    def _prepare(self, attempt_id: UUID, group_id: UUID) -> None:
        # Lock parents before children, matching selection/enablement transactions. The
        # initial lookup only identifies the parent; the locked rows are read again below.
        parent_id = self.uow.session.scalar(
            select(release_validation_attempt.c.release_validation_id).where(
                release_validation_attempt.c.tenant_id == self.tenant_id,
                release_validation_attempt.c.id == attempt_id,
            )
        )
        if parent_id is None:
            raise Problem("not-found")
        for table, row_id, destination in (
            (release_validation, parent_id, self.validation),
            (release_validation_attempt, attempt_id, self.attempt),
        ):
            found = (
                self.uow.session.execute(
                    select(table)
                    .where(table.c.tenant_id == self.tenant_id, table.c.id == row_id)
                    .with_for_update(key_share=True)
                )
                .mappings()
                .one_or_none()
            )
            if found is None:
                raise Problem("not-found")
            destination.update(found)
        selected = (
            self.uow.session.execute(
                select(release_validation_group)
                .where(
                    release_validation_group.c.tenant_id == self.tenant_id,
                    release_validation_group.c.release_validation_attempt_id == attempt_id,
                    release_validation_group.c.combination_group_id == group_id,
                )
                .with_for_update(key_share=True)
            )
            .mappings()
            .one_or_none()
        )
        if selected is None:
            raise Problem("not-found")
        self.selection.update(selected)

    def row_by_token(self, attempt_id: UUID, group_id: UUID, token: ExecutionToken) -> UUID | None:
        self._prepare(attempt_id, group_id)
        existing = self.uow.session.execute(
            select(computation_verification.c.id, computation_verification.c.attempt).where(
                computation_verification.c.tenant_id == self.tenant_id,
                computation_verification.c.release_validation_attempt_id == attempt_id,
                computation_verification.c.combination_group_id == group_id,
                computation_verification.c.job_id == token.job_id,
                computation_verification.c.task_id == token.task_id,
            )
        ).one_or_none()
        if existing is not None and existing.attempt != token.attempt:
            raise _invalid("The scheduler task already has a different attempt identity.")
        return None if existing is None else existing.id

    def accepted(self, attempt_id: UUID, group_id: UUID) -> UUID | None:
        value: UUID | None = self.selection["accepted_verification_id"]
        return value

    def still_owner(self) -> bool:
        token = self.result.token
        found = self.uow.session.scalar(
            select(job.c.id)
            .where(
                job.c.tenant_id == self.tenant_id,
                job.c.id == token.job_id,
                job.c.procrastinate_job_id == token.task_id,
                job.c.state == "RUNNING",
                job.c.kind == "REPLAY_VERIFY",
                job.c.cancel_requested_at.is_(None),
            )
            .with_for_update(key_share=True)
        )
        return found is not None

    def insert(
        self,
        attempt_id: UUID,
        group_id: UUID,
        token: ExecutionToken,
        row_id: UUID,
        outcome: VerificationOutcome,
    ) -> None:
        result = self.result
        if (
            self.attempt["status"] != "RUNNING"
            or self.validation["status"] != "RUNNING"
            or self.selection["orchestration_state"] != "RUNNING"
            or self.selection["child_job_id"] != token.job_id
            or self.selection["source_computation_id"] != result.source_computation_id
            or self.validation["engine_release_id"] != result.process_engine_release_id
        ):
            raise _invalid("The result no longer matches a running frozen validation selection.")
        head = self.uow.session.execute(
            select(combination_group.c.head_computation_id)
            .where(
                combination_group.c.tenant_id == self.tenant_id,
                combination_group.c.id == group_id,
            )
            .with_for_update(key_share=True)
        ).one_or_none()
        if head is None or head.head_computation_id != result.source_computation_id:
            raise _invalid(
                "The selected computation head changed; a new validation attempt is required."
            )
        if result.source_computation_id is not None:
            source = (
                self.uow.session.execute(
                    select(contract_computation).where(
                        contract_computation.c.tenant_id == self.tenant_id,
                        contract_computation.c.id == result.source_computation_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source is None or (
                source["status"] != "SUCCEEDED"
                or source["combination_group_id"] != group_id
                or source["engine_release_id"] != result.source_engine_release_id
                or source["engine_version"] != result.source_engine_version
                or source["input_sha256"] != result.input_sha256
            ):
                raise _invalid("The result does not identify the selected source computation.")
            self.contract_ids = tuple(UUID(key) for key in source["stream_heads"])
        values = {
            field.name: getattr(result, field.name)
            for field in fields(result)
            if field.name not in {"token", "differences"}
        }
        for name in ("source_codec", "difference_summary"):
            if values[name] is not None:
                values[name] = dict(values[name])
        if values["expected_book_codes"] is not None:
            values["expected_book_codes"] = list(values["expected_book_codes"])
        values.update(
            tenant_id=self.tenant_id,
            id=row_id,
            job_id=token.job_id,
            task_id=token.task_id,
            attempt=token.attempt,
            duration_ms=self.duration_ms,
            created_at=self.uow.now,
            created_by=self.uow.principal.id,
            created_by_kind=self.uow.principal.kind.value,
        )
        if result.difference_summary is not None:
            content = canonical_bytes(
                {
                    "difference_format": 1,
                    "verification_id": row_id,
                    "release_validation_attempt_id": attempt_id,
                    "combination_group_id": group_id,
                    "source_computation_id": result.source_computation_id,
                    "process_engine_release_id": result.process_engine_release_id,
                    "job_id": token.job_id,
                    "task_id": token.task_id,
                    "attempt": token.attempt,
                    "summary": dict(result.difference_summary),
                    "differences": [asdict(row) for row in result.differences],
                }
            )
            artifact = store_file(
                self.uow,
                purpose=FilePurpose.VALIDATION_DATASET,
                stream=io.BytesIO(content),
                original_filename=f"{row_id}-differences.json",
                media_type="application/json",
            )
            if artifact["sha256"] != hashlib.sha256(content).hexdigest() or artifact[
                "size_bytes"
            ] != len(content):
                raise _invalid("Stored difference evidence differs from the comparison.")
            values["difference_file_id"] = artifact["id"]
        self.uow.session.execute(insert(computation_verification).values(**values))

    def set_accepted(self, attempt_id: UUID, group_id: UUID, row_id: UUID) -> None:
        # The schema requires acceptance and COMPLETE together; defer both to one UPDATE.
        self.pending_pointer = row_id

    def set_orchestration(
        self,
        attempt_id: UUID,
        group_id: UUID,
        state: ValidationGroupOrchestrationState,
    ) -> None:
        if self.pending_pointer is None:
            raise RuntimeError("A completed verification needs its accepted result.")
        apply(
            self.uow.session,
            "release_validation_group",
            self.selection["id"],
            to_status=state.value,
            expected_status=self.selection["orchestration_state"],
            expected_row_version=self.selection["row_version"],
            set_values={
                "accepted_verification_id": self.pending_pointer,
                "row_version": self.selection["row_version"] + 1,
                "updated_at": self.uow.now,
                "updated_by": self.uow.principal.id,
                "updated_by_kind": self.uow.principal.kind.value,
            },
        )
        self.uow.audit(
            action="release_validation_group.verify",
            object_type="release_validation_group",
            object_id=self.selection["id"],
            contract_ids=self.contract_ids,
            before={
                "orchestration_state": self.selection["orchestration_state"],
                "accepted_verification_id": None,
            },
            after={
                "orchestration_state": state.value,
                "accepted_verification_id": self.pending_pointer,
            },
        )


def persist(
    uow: UnitOfWork,
    result: VerificationRow,
    *,
    context: JobContext,
    duration_ms: int,
) -> VerificationWrite:
    """Persist without committing; the caller commits result, pointer and job heartbeat together.

    The registry's actual execution token and process release must match the decision. This
    path never writes a computation, contract version, trace, posting or computation head.
    """
    token = result.token
    runtime_attempt = context.runtime.attempt
    process = context.runtime.engine_release
    if (
        context.kind is not JobKind.REPLAY_VERIFY
        or context.tenant_id != uow.principal.tenant_id
        or runtime_attempt is None
        or (context.job_id, context.task_id, context.attempt)
        != (token.job_id, token.task_id, token.attempt)
        or result.release_validation_attempt_id is None
    ):
        raise _invalid("Verification requires the current persisted scheduler execution identity.")
    if process is None or (process.id, process.engine_version) != (
        result.process_engine_release_id,
        result.process_engine_version,
    ):
        raise Problem("release-mismatch")
    runtime_attempt.enter(uow, context.clock)
    store = _Store(uow, result, duration_ms)
    return verification_write(
        store,
        TransactionExecutionLock(uow.session),
        attempt_id=result.release_validation_attempt_id,
        group_id=result.combination_group_id,
        token=token,
        row_id=new_id(),
        outcome=result.outcome,
        still_owner=store.still_owner,
    )
