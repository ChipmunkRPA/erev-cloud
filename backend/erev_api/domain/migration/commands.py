"""API-R-48 command handlers: create, profile, import, reconcile and cancel a migration batch
(04 §15.3 API-R-48, §15.2 ``duplicate-import`` / ``legacy-database-unrecognized`` /
``upload-type-not-allowed`` / ``invalid-transition``; T-MIG-01 E-76 (PRD SM-12); SCREENS_B §10.2,
§10.3; PRD J-20; BUILD_SPEC LMG-1 to LMG-3; lane record §25; D-98 candidates 128 and 129).

Every handler runs inside the route's ``run_command`` unit of work: it validates, changes T-MIG-01
along E-76 through ``repository.transition`` (DB-03; a stale status is 409 ``invalid-transition``
by name), defers the job the phase needs (``MIGRATION_IMPORT`` with ``phase`` ``PROFILE`` or
``IMPORT``; ``MIGRATION_RECONCILE``) and writes the AUD-CMD audit event. The jobs themselves move
the batch on (PROFILING → PROFILED; PROFILED → IMPORTING → IMPORTED; IMPORTED → RECONCILED); a job
hyperlink is never an endpoint. ``POST /migrations/{id}/submit-promotion`` is NOT here: it lands
with the promotion item and the ``MIGRATION_PROMOTION`` SubjectSpec as one unit (D-98 candidate
129).
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.approvals.engine import submit as submit_request
from erev_api.approvals.subjects import SubjectLifecycle, register_lifecycle
from erev_api.auth.keyring import KeyRing
from erev_api.domain.migration import (
    field_mapping,
    legacy_db,
    opening_balances,
    prerequisites,
    repository,
)
from erev_api.domain.migration.jobs import PHASE_IMPORT, PHASE_PROFILE
from erev_api.domain.platform import file_access
from erev_api.domain.platform.jobs import cancel_job, job_out_of
from erev_api.enums import (
    ApprovalSubjectType,
    FilePurpose,
    JobKind,
    JobState,
    MigrationMode,
    MigrationStatus,
)
from erev_api.files import policy
from erev_api.files.store import FileStore, open_file
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut
from erev_api.schemas.migrations import (
    MigrationCreateIn,
    OpeningBalancesImportIn,
    ReplayImportIn,
)
from erev_api.uow import UnitOfWork

__all__ = [
    "CANCEL_ACTION",
    "CREATE_ACTION",
    "IMPORT_ACTION",
    "OBJECT_TYPE",
    "PERMISSION",
    "PROFILE_ACTION",
    "RECONCILE_ACTION",
    "cancel_batch",
    "create_batch",
    "import_batch",
    "profile_batch",
    "reconcile_batch",
    "recognise_stored_source",
]

PERMISSION: Final = "migration.run"  # 04 §15.3 API-R-48; T-PLT permissions MIG
OBJECT_TYPE: Final = "migration_batch"
CREATE_ACTION: Final = "migration_batch.create"
PROFILE_ACTION: Final = "migration_batch.profile"
IMPORT_ACTION: Final = "migration_batch.import"
RECONCILE_ACTION: Final = "migration_batch.reconcile"
CANCEL_ACTION: Final = "migration_batch.cancel"
# 04 rev 1.72 (D-98 133 AMENDMENT 4): the SKU_SSP rows must carry zero LM-SSP-01..09 ERROR findings
# before the replay request opens
SKU_SSP_FINDINGS_COPY: Final = (
    "The legacy database's SKU_SSP table has {count} row finding(s); resolve them in the legacy "
    "database before importing."
)
REPLAY_SUMMARY: Final = "Legacy SSP replay of migration {migration_no}"


def _replay_decided(uow: UnitOfWork, batch_id: UUID, approval_request_id: UUID) -> None:
    """``MIGRATION_SSP_REPLAY`` lifecycle (04 §16.10 rev 1.72): the decision itself writes nothing —
    the import job reads the APPROVED request named in its params and approves the replayed
    ``LEGACY-SKU-SSP`` versions under it; a rejection or void simply leaves no approved request, so
    the job refuses by name (``prerequisites.apply``)."""
    del uow, batch_id, approval_request_id


register_lifecycle(
    ApprovalSubjectType.MIGRATION_SSP_REPLAY,
    SubjectLifecycle(
        on_approved=_replay_decided, on_rejected=_replay_decided, on_voided=_replay_decided
    ),
)
RULE: Final = "API-R-48"
TERMINAL: Final = frozenset(
    {MigrationStatus.PROMOTED.value, MigrationStatus.FAILED.value, MigrationStatus.CANCELLED.value}
)
# SCREENS_B §10.2 / §10.3 copy
NOT_LEGACY_PURPOSE_COPY: Final = (
    "The source must be a file uploaded with purpose LEGACY_DATABASE; file {file_id} has "
    "purpose {purpose}."
)
NOT_STATUS_COPY: Final = "The migration is {status}; {action} needs a {expected} migration."
TERMINAL_COPY: Final = "The migration is {status}; a {status} migration cannot be cancelled."
MODE_MISMATCH_COPY: Final = (
    "The import body is for mode {body_mode}; the migration was created in mode {mode}."
)
REPLAY_NOT_BUILT_COPY: Final = (
    "Replay imports (D-31 mode b) are not available yet; this migration cannot be imported."
)
CUTOVER_SET_COPY: Final = (
    "The migration's cutover date is already {existing}; it is set once and cannot change."
)
NO_PROFILE_COPY: Final = "The migration has no profile; profile it before importing."
ENTITY_UNKNOWN_COPY: Final = (
    "Entity mapping names {name!r}, which is not a selling entity of the legacy database."
)


def _refuse(detail: str, *, field: str = "migration_id") -> Problem:
    return Problem(
        "invalid-transition",
        detail,
        errors=[ProblemError(field=field, rule_id=RULE, message=detail)],
    )


def _validation(errors: list[ProblemError]) -> Problem:
    count = len(errors)
    return Problem(
        "validation-failed",
        f"{count} field{'s' if count != 1 else ''} need{'s' if count == 1 else ''} attention.",
        errors=errors,
    )


def _expect(batch: Mapping[str, Any], expected: MigrationStatus, *, action: str) -> None:
    status = str(batch["status"])
    if status != expected.value:
        raise _refuse(NOT_STATUS_COPY.format(status=status, action=action, expected=expected.value))


# ---- create -------------------------------------------------------------------------------------


def recognise_stored_source(
    uow: UnitOfWork, file_id: UUID, *, files: FileStore, keyring: KeyRing
) -> Mapping[str, Any]:
    """The stored ``file_object`` row of a legacy database: purpose ``LEGACY_DATABASE`` (else 422
    ``upload-type-not-allowed``, SCREENS_B §10.2 ERR-37 copy) and a ``Contract_Live`` table in a
    read-only spooled copy of the plaintext (else 422 ``legacy-database-unrecognized``, ERR-20;
    PRD J-20-ALT-2). The stored object is never modified (REQ-MIG-004). A file the caller may not
    read is answered as a file that does not exist, before it is opened (04 T-PLT-29 Read
    access, rev 1.151)."""
    if file_access.bound(uow.session, uow.ctx, file_id) is None:
        raise Problem("not-found")
    row, stream = open_file(uow.session, file_id, files=files, keyring=keyring)
    purpose = FilePurpose(str(getattr(row["purpose"], "value", row["purpose"])))
    if purpose is not FilePurpose.LEGACY_DATABASE:
        raise Problem(
            "upload-type-not-allowed",
            policy.LEGACY_DATABASE_DETAIL,
            errors=[
                ProblemError(
                    field="source_file_id",
                    rule_id="T-PLT-29",
                    message=NOT_LEGACY_PURPOSE_COPY.format(file_id=file_id, purpose=purpose.value),
                )
            ],
        )
    spooled = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    try:
        with spooled:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                spooled.write(chunk)
        legacy_db.recognise(Path(spooled.name))
    finally:
        Path(spooled.name).unlink(missing_ok=True)
    return row


def create_batch(
    uow: UnitOfWork, body: MigrationCreateIn, *, files: FileStore, keyring: KeyRing
) -> Mapping[str, Any]:
    """``POST /migrations`` → an UPLOADED T-MIG-01 row (SCREENS_B §10.2): the source recognised,
    the BR-MIG-01 duplicate refused by name (409 ``duplicate-import``, ERR-19), no cutover yet —
    the opening-balances cutover is set once at ``/import`` (D-98 candidate 128)."""
    stored = recognise_stored_source(uow, body.source_file_id, files=files, keyring=keyring)
    sha256 = str(stored["sha256"]).strip()
    values = repository.create_batch(
        uow, mode=body.mode, source_file_id=body.source_file_id, source_sha256=sha256
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=UUID(str(values["id"])),
        object_version="1",
        after={
            "migration_no": values["migration_no"],
            "mode": body.mode.value,
            "source_file_id": str(body.source_file_id),
            "source_sha256": sha256,
            "status": MigrationStatus.UPLOADED.value,
        },
    )
    return repository.get_batch(uow, UUID(str(values["id"])))


# ---- profile -------------------------------------------------------------------------------------


def profile_batch(uow: UnitOfWork, batch_id: UUID) -> JobOut:
    """``POST /migrations/{id}/profile`` (202): UPLOADED → PROFILING with the deferred
    ``MIGRATION_IMPORT`` job of phase ``PROFILE`` as ``job_id`` (SCREENS_B §10.2 "Upload and
    profile"); the job writes the profile and moves the batch to PROFILED."""
    batch = repository.get_batch(uow, batch_id)
    _expect(batch, MigrationStatus.UPLOADED, action="profiling")
    deferred = uow.defer(
        JobKind.MIGRATION_IMPORT,
        {"migration_id": str(batch_id), "phase": PHASE_PROFILE},
        subject_type=OBJECT_TYPE,
        subject_id=batch_id,
    )
    job_id = UUID(str(deferred["id"]))
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.PROFILING,
        expected_status=MigrationStatus.UPLOADED,
        job_id=job_id,
        started_at=uow.now,
    )
    uow.audit(
        action=PROFILE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=batch_id,
        object_version=str(int(batch["row_version"]) + 1),
        before={"status": MigrationStatus.UPLOADED.value},
        after={"status": MigrationStatus.PROFILING.value, "job_id": str(job_id)},
    )
    return job_out_of(uow.session, job_id)


# ---- import --------------------------------------------------------------------------------------


def _opening_balances_errors(
    body: OpeningBalancesImportIn, batch: Mapping[str, Any]
) -> list[ProblemError]:
    """422 errors of an OPENING_BALANCES import body against the stored profile (SCREENS_B §10.3
    "Confirm mapping"): the cutover on or before the latest legacy period, the batch parameters,
    the entity mapping naming the profile's selling entities."""
    profile = batch.get("profile")
    if not profile:
        return [ProblemError(field="migration_id", rule_id=RULE, message=NO_PROFILE_COPY)]
    errors: list[ProblemError] = []
    latest = profile.get("latest_current_period")
    latest_period = date.fromisoformat(str(latest)) if latest else None
    cutover_error = opening_balances.validate_cutover(body.cutover_date, latest_period)
    if cutover_error is not None:
        errors.append(cutover_error)
    existing = batch.get("cutover_date")
    if existing is not None and existing != body.cutover_date:
        errors.append(
            ProblemError(
                field="cutover_date",
                rule_id="T-MIG-01",
                message=CUTOVER_SET_COPY.format(existing=existing.isoformat()),
            )
        )
    errors.extend(field_mapping.validate_batch_parameters(dict(body.batch_parameters)))
    known = set(profile.get("selling_entities") or ())
    for index, mapping in enumerate(body.entity_mapping):
        if mapping.legacy_name not in known:
            errors.append(
                ProblemError(
                    field=f"entity_mapping[{index}].legacy_name",
                    rule_id="LM-CL-09",
                    message=ENTITY_UNKNOWN_COPY.format(name=mapping.legacy_name),
                )
            )
    return errors


def import_batch(
    uow: UnitOfWork, batch_id: UUID, body: OpeningBalancesImportIn | ReplayImportIn
) -> JobOut:
    """``POST /migrations/{id}/import`` (202): PROFILED only; the body's mode equals the batch's
    (422 by name); OPENING_BALANCES writes the cutover ONCE on T-MIG-01 (D-98 candidate 128) and
    defers ``MIGRATION_IMPORT`` phase ``IMPORT`` with the batch parameters and entity mapping; the
    job moves PROFILED → IMPORTING → IMPORTED itself (one import per batch, max_attempts 1). REPLAY
    is refused by name until D-31 mode (b) is built."""
    batch = repository.get_batch(uow, batch_id)
    _expect(batch, MigrationStatus.PROFILED, action="importing")
    mode = str(batch["mode"])
    if body.mode != mode:
        raise _validation(
            [
                ProblemError(
                    field="mode",
                    rule_id=RULE,
                    message=MODE_MISMATCH_COPY.format(body_mode=body.mode, mode=mode),
                )
            ]
        )
    if isinstance(body, ReplayImportIn):
        raise _refuse(REPLAY_NOT_BUILT_COPY, field="mode")
    errors = _opening_balances_errors(body, batch)
    if errors:
        raise _validation(errors)
    # 04 LM-CL-09 rev 1.64 (D-98 candidate 133): the confirmation resolves the inputs the mapping
    # does not carry for every "Will be created" entity — refused by name per entity otherwise;
    # the RESOLVED rows are what the import phase applies (captured here, with the cutover)
    resolved = prerequisites.resolve_entities(
        uow.session,
        tenant_id=uow.principal.tenant_id,
        staging=_staging_of(uow, batch, body),
        entity_mapping=[mapping.model_dump() for mapping in body.entity_mapping],
        entity_defaults=None if body.entity_defaults is None else body.entity_defaults.model_dump(),
        create_missing_entities=body.create_missing_entities,
    )
    # 04 rev 1.72 (D-98 133 AMENDMENT 4 option A2): the two ruling conditions that are not
    # AUTO_APPROVAL
    # rule facts are enforced HERE, before any request opens — zero LM-SSP-01..09 ERROR findings
    # over the
    # SKU_SSP rows (the PROFILE typed them), the content bound to the source digest (the subject
    # content
    # reads the profile) — then the MIGRATION_SSP_REPLAY request is submitted; AUTO-MIG-01 approves
    # it
    # in this transaction, and its id travels in the job params beside resolved_entities (the
    # batch's
    # approval_request_id stays reserved for promotion, D-98 129)
    profile = dict(batch.get("profile") or {})
    sku_ssp_findings = list(profile.get("sku_ssp_findings") or [])
    if sku_ssp_findings:
        raise _validation(
            [
                ProblemError(
                    field=f"sku_ssp[{int(finding['row'])}].{finding['column']}",
                    rule_id=str(finding["code"]),
                    message=str(finding["message"]),
                )
                for finding in sku_ssp_findings
            ]
        )
    replay_request = submit_request(
        uow,
        subject_type=ApprovalSubjectType.MIGRATION_SSP_REPLAY,
        subject_id=batch_id,
        summary=REPLAY_SUMMARY.format(migration_no=batch["migration_no"]),
    )
    params: dict[str, Any] = {
        "migration_id": str(batch_id),
        "phase": PHASE_IMPORT,
        "batch_parameters": dict(body.batch_parameters),
        "entity_mapping": [mapping.model_dump(mode="json") for mapping in body.entity_mapping],
        "resolved_entities": [entity.as_params() for entity in resolved],
        "create_missing_entities": body.create_missing_entities,
        "create_missing_products": body.create_missing_products,
        "ssp_replay_request_id": str(replay_request["id"]),
        "sku_ssp_sha256": str(profile.get("sku_ssp_sha256") or ""),
    }
    deferred = uow.defer(
        JobKind.MIGRATION_IMPORT, params, subject_type=OBJECT_TYPE, subject_id=batch_id
    )
    job_id = UUID(str(deferred["id"]))
    set_values: dict[str, Any] = {"job_id": job_id}
    if batch.get("cutover_date") is None:
        set_values["cutover_date"] = body.cutover_date  # set once (DB-03; 04 T-MIG-01 rev 1.60)
    repository.transition(
        uow, batch_id, to_status=None, expected_status=MigrationStatus.PROFILED, **set_values
    )
    uow.audit(
        action=IMPORT_ACTION,
        object_type=OBJECT_TYPE,
        object_id=batch_id,
        object_version=str(int(batch["row_version"]) + 1),
        before={"status": MigrationStatus.PROFILED.value, "cutover_date": None},
        after={
            "status": MigrationStatus.PROFILED.value,
            "cutover_date": body.cutover_date.isoformat(),
            "batch_parameters": dict(body.batch_parameters),
            "entity_mapping": params["entity_mapping"],
            "resolved_entities": params["resolved_entities"],
            "create_missing_products": body.create_missing_products,
            "ssp_replay_request_id": params["ssp_replay_request_id"],
            "sku_ssp_sha256": params["sku_ssp_sha256"],
            "job_id": str(job_id),
        },
    )
    return job_out_of(uow.session, job_id)


def _staging_of(
    uow: UnitOfWork, batch: Mapping[str, Any], body: OpeningBalancesImportIn
) -> opening_balances.Staging:
    """The staged contracts of the batch's stored legacy rows (T-MIG-02 when the source was already
    stored, else the profile's selling entities are the only fact): the confirmation needs the
    selling-entity texts and the SKU → template pairs. Before the import phase stores T-MIG-02 the
    rows are not in the database, so the confirmation reads the entities from the PROFILE and
    stages nothing — ``resolve_entities`` accepts a staging whose contracts carry the entity
    codes."""
    profile = dict(batch.get("profile") or {})
    entities = tuple(str(name) for name in profile.get("selling_entities") or ())
    return opening_balances.Staging(
        cutover_date=body.cutover_date,
        contracts=tuple(
            opening_balances.ContractOpening(
                external_id=f"profile:{name}",
                entity_code=name,
                inception_date=body.cutover_date,
                latest_period=body.cutover_date,
                transaction_price=Decimal(0),
                obligations=(),
                vc_elements=(),
            )
            for name in entities
        ),
        migrated_rows=int(profile.get("contract_live_rows") or 0),
        findings=(),
    )


# ---- reconcile -----------------------------------------------------------------------------------


def reconcile_batch(uow: UnitOfWork, batch_id: UUID) -> JobOut:
    """``POST /migrations/{id}/reconcile`` (202): IMPORTED only; defers ``MIGRATION_RECONCILE``,
    which writes the T-MIG-03 lines once and moves IMPORTED → RECONCILED."""
    batch = repository.get_batch(uow, batch_id)
    _expect(batch, MigrationStatus.IMPORTED, action="reconciling")
    deferred = uow.defer(
        JobKind.MIGRATION_RECONCILE,
        {"migration_id": str(batch_id)},
        subject_type=OBJECT_TYPE,
        subject_id=batch_id,
    )
    job_id = UUID(str(deferred["id"]))
    repository.transition(
        uow, batch_id, to_status=None, expected_status=MigrationStatus.IMPORTED, job_id=job_id
    )
    uow.audit(
        action=RECONCILE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=batch_id,
        object_version=str(int(batch["row_version"]) + 1),
        before={"status": MigrationStatus.IMPORTED.value},
        after={"status": MigrationStatus.IMPORTED.value, "job_id": str(job_id)},
    )
    return job_out_of(uow.session, job_id)


# ---- cancel --------------------------------------------------------------------------------------


def cancel_batch(uow: UnitOfWork, batch_id: UUID) -> Mapping[str, Any]:
    """``POST /migrations/{id}/cancel``: any non-terminal status → CANCELLED (E-76; 409 by name
    on PROMOTED / FAILED / CANCELLED). A QUEUED or RUNNING ``job_id`` the caller started gets
    ``cancel_job`` (05 JOB-05); a job another principal started is left to fail closed — its own
    DB-03 transition of the batch is refused once the batch is CANCELLED."""
    batch = repository.get_batch(uow, batch_id)
    status = str(batch["status"])
    if status in TERMINAL:
        raise _refuse(TERMINAL_COPY.format(status=status))
    job_id = batch.get("job_id")
    if job_id is not None:
        _request_job_cancel(uow, UUID(str(job_id)))
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.CANCELLED,
        expected_status=MigrationStatus(status),
        finished_at=uow.now,
    )
    uow.audit(
        action=CANCEL_ACTION,
        object_type=OBJECT_TYPE,
        object_id=batch_id,
        object_version=str(int(batch["row_version"]) + 1),
        before={"status": status},
        after={"status": MigrationStatus.CANCELLED.value},
    )
    return repository.get_batch(uow, batch_id)


def _request_job_cancel(uow: UnitOfWork, job_id: UUID) -> None:
    """Cancel the batch's job when it is still QUEUED or RUNNING and the caller started it;
    anything else (a finished job, another initiator's job) is left as it is."""
    try:
        current = job_out_of(uow.session, job_id)
    except Problem:
        return
    if current.state not in (JobState.QUEUED, JobState.RUNNING):
        return
    if current.created_by.id != uow.principal.id:
        return
    cancel_job(uow, job_id)


# ---- shared -------------------------------------------------------------------------------------


def mode_of(batch: Mapping[str, Any]) -> MigrationMode:
    return MigrationMode(str(getattr(batch["mode"], "value", batch["mode"])))
