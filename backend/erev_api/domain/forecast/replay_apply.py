"""Transactional import execution for a refresh worker replaying one input at a time."""

from typing import Any
from uuid import UUID

from erev_api.domain.contracts import events
from erev_api.domain.imports import commit, diff, upload, validate
from erev_api.enums import ImportStatus
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendIn
from erev_api.schemas.imports import ImportCreateIn, ImportSubmitIn
from erev_api.uow import UnitOfWork


def apply_file(
    uow: UnitOfWork,
    body: ImportCreateIn,
    *,
    quarantine: bool,
    parent_job_id: UUID | None = None,
    mapping_snapshot: dict[str, Any] | None = None,
) -> UUID:
    """Validate, preview, commit and compute before the caller advances to its next input.

    The worker has already copied the source file into this target workspace and supplies
    the source reader's retained mapping snapshot when the import used a profile.
    Every ordinary template validation and permission check still applies.
    A failed stage rolls back facts, input sequence, files registered by these stages and audit
    buffers. The caller commits this step with its durable replay cursor in the same transaction.
    """
    with uow.savepoint():
        identity = upload.create_inline_import(
            uow, body=body, quarantine=quarantine, mapping_snapshot=mapping_snapshot
        )
        if not validate.start_validation(uow, identity):
            raise Problem("invalid-transition", "The replay import could not start validation.")
        outcome = validate.validate_upload(uow, identity, defer_diff=False)
        if outcome is None or outcome.status is not ImportStatus.VALIDATED:
            raise Problem("validation-failed", "The replayed forecast file failed validation.")
        if not diff.start_diff(uow, identity):
            raise Problem("invalid-transition", "The replay import could not start its preview.")
        if diff.compute_diff(uow, identity) is None:
            raise Problem("validation-failed", "The replayed forecast file has no preview.")
        commit.submit_import(uow, import_id=identity, body=ImportSubmitIn(), defer_commit=False)
        if not commit.start_commit(uow, identity):
            raise Problem("invalid-transition", "The replay import could not start its commit.")
        if (
            commit.commit_upload(uow, identity, parent_job_id=parent_job_id, inline_compute=True)
            is None
        ):
            raise Problem("invalid-transition", "The replay import did not commit.")
        return identity


def apply_command(
    uow: UnitOfWork, *, contract_id: UUID, input_set_id: UUID, body: EventAppendIn
) -> events.Recorded:
    """Apply one retained command and compute before advancing the replay cursor.

    Current contract heads are locked by the ordinary event command: a fresh production copy
    need not share the original scenario's stream version. Payload and evidence checks, scoped
    event permission and draft input capture all use that same command path.
    """
    with uow.savepoint():
        return events.record_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=None,
            body=body,
            forecast_event_set_id=input_set_id,
            inline_compute=True,
        )
