"""API-R-48 Migrations: legacy ``ASC606.db`` import batches — list, create, read, profile, import,
reconcile, cancel, reconciliation lines, legacy rows and the static field mapping (D-98 133-A1 (b)).

04 §15.3 API-R-48, §15.2; T-MIG-01 to T-MIG-03; E-75, E-76 (PRD SM-12); SCREENS_B §10.1 to §10.3;
PRD J-20; BUILD_SPEC LMG-1 to LMG-3; lane record §25. Reads and commands need ``migration.run``
(one permission, 04 API-R-48) for ALL entities: a migration is an act on the workspace — a legacy
database holds any entity's contracts, its batch carries no entity (T-MIG-01) and its import
creates entities — so a holder of named entities is refused every route, 403 after a DENIED
event that states the scope (04 API-C-03 rev 1.243; supervisor rulings R-28 and R-115 (c); the
supervisor's ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1 (c2), answer Q2; a reader per
batch is item MIG-BATCH-ENTITY-SCOPE-1).

The command routes answer 202 API-S-Job with ``Location`` of the job (DG-KRN-JOB-09) where a job
does the work — profiling (``MIGRATION_IMPORT`` phase ``PROFILE``), importing (phase ``IMPORT``)
and reconciling (``MIGRATION_RECONCILE``) — and 200 / 201 API-S-Migration otherwise.
``POST /migrations/{id}/submit-promotion`` lands with the promotion item and the
``MIGRATION_PROMOTION`` SubjectSpec as one unit (D-98 candidate 129) and is not served here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import migration_batch
from erev_api.domain.migration import commands, field_mapping, queries, repository
from erev_api.enums import MigrationMode, MigrationStatus
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.migrations import (
    FieldMappingOut,
    FieldMappingRowOut,
    MigratedLegacyRowOut,
    MigrationCreateIn,
    MigrationImportIn,
    MigrationOut,
    MigrationReconciliationLineOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-48 Migrations"
PERMISSION: Final = commands.PERMISSION
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
MIGRATION_PATH: Final = f"{API_PREFIX}/migrations/{{migration_id}}"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
MIGRATION_LIST: Final = ListSpec(
    resource="migrations",
    sort_keys={
        "id": migration_batch.c.id,
        "migration_no": migration_batch.c.migration_no,
        "created_at": migration_batch.c.created_at,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            "status",
            migration_batch.c.status,
            "exact",
            choices=frozenset(status.value for status in MigrationStatus),
        ),
        "mode": FilterSpec(
            "mode",
            migration_batch.c.mode,
            "exact",
            choices=frozenset(mode.value for mode in MigrationMode),
        ),
        "created_from": FilterSpec("created_from", migration_batch.c.created_at, "from"),
    },
)

type ReadContext = Annotated[RequestContext, Depends(require_all_entities(PERMISSION))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def migration_etag(out: MigrationOut) -> str:
    """API-C-08: T-MIG-01 is IM-S with SC-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _job_location(job: JobOut) -> dict[str, str]:
    return {"Location": JOB_PATH.format(job_id=job.id)}


def _one(session: Session, migration_id: uuid.UUID) -> MigrationOut:
    row = repository.get_batch_in_session(session, migration_id)
    return queries.migration_outs(session, [row])[0]


def _one_in(uow: UnitOfWork, row: object) -> MigrationOut:
    return queries.migration_outs(uow.session, [row])[0]  # type: ignore[list-item]


@router.get(
    "/migrations",
    operation_id="migrations_list",
    response_model=ListOut[MigrationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def migrations_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[MigrationStatus | None, Query(description="E-76")] = None,
    mode: Annotated[MigrationMode | None, Query(description="E-75")] = None,
    created_from: Annotated[datetime | None, Query()] = None,
) -> ListOut[MigrationOut]:
    """Migrations of the workspace (SCREENS_B §10.1); sort ``id`` (default ``-id``),
    ``migration_no`` or ``created_at``; each item carries ``unexplained_count``."""

    def page(session: Session) -> tuple[ListResult, list[MigrationOut]]:
        result = paginate(session, queries.migrations_statement(), MIGRATION_LIST, params)
        return result, queries.migration_outs(session, result.items)

    result, items = queries.read(ctx, page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[MigrationOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/migrations",
    operation_id="migrations_create",
    status_code=201,
    response_model=MigrationOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "duplicate-import",
        "legacy-database-unrecognized",
        "upload-type-not-allowed",
    ),
)
def migrations_create(
    body: MigrationCreateIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Deps,
) -> Response:
    """Create an UPLOADED migration from a stored ``LEGACY_DATABASE`` file (SCREENS_B §10.2): the
    file must hold ``Contract_Live`` (ERR-20) and must not be an active migration's source already
    (ERR-19; BR-MIG-01). The opening-balances cutover is given at ``/import``."""

    def handle(uow: UnitOfWork) -> MigrationOut:
        row = commands.create_batch(uow, body, files=deps.files, keyring=deps.keyring)
        return _one_in(uow, row)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: MIGRATION_PATH.format(migration_id=out.id),
        etag=migration_etag,
    )


@router.get(
    "/migrations/field-mapping",
    operation_id="migrations_field_mapping",
    response_model=FieldMappingOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def migrations_field_mapping(ctx: ReadContext) -> FieldMappingOut:
    """The 71 rows of 04 §17.2 as data (D-98 133 AMENDMENT 1 (b); 04 rev 1.66 API-R-48): id, the
    exact legacy column name, the eRev target and the rule, in legacy order — static content under
    the migration read permission, no database row; SCREENS_B §10.3's read-only "Field mapping"
    table renders it verbatim. Declared before ``/migrations/{migration_id}`` so the literal path
    never reaches the UUID route."""
    del ctx  # the permission dependency is the whole check; the content is static
    return FieldMappingOut(
        rows=[
            FieldMappingRowOut(
                id=item.id, legacy_column=item.legacy, target=item.target, rule=str(item.rule)
            )
            for item in field_mapping.FIELD_MAPPING
        ]
    )


@router.get(
    "/migrations/{migration_id}",
    operation_id="migrations_get",
    response_model=MigrationOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def migrations_get(migration_id: uuid.UUID, response: Response, ctx: ReadContext) -> MigrationOut:
    """One migration with its profile, cutover, job and promotion references (SCREENS_B §10.3)."""
    out = queries.read(ctx, lambda session: _one(session, migration_id))
    response.headers["ETag"] = migration_etag(out)
    return out


@router.post(
    "/migrations/{migration_id}/profile",
    operation_id="migrations_profile",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def migrations_profile(
    migration_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Deps,
) -> Response:
    """Profile the stored legacy database (SCREENS_B §10.2 "Upload and profile"): UPLOADED →
    PROFILING and a ``MIGRATION_IMPORT`` job of phase ``PROFILE``; the job writes the key figures
    and moves the migration to PROFILED."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.profile_batch(uow, migration_id),
        status_code=202,
        extra_headers=_job_location,
    )


@router.post(
    "/migrations/{migration_id}/import",
    operation_id="migrations_import",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def migrations_import(
    migration_id: uuid.UUID,
    body: MigrationImportIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Deps,
) -> Response:
    """Run the import (SCREENS_B §10.3 "Confirm mapping" → "Run import"): PROFILED only; for
    OPENING_BALANCES the body carries the cutover (set once), the entity mapping and the batch
    parameters, validated against the profile; a ``MIGRATION_IMPORT`` job of phase ``IMPORT``
    stages, dry-runs and captures the population (LMG-2). REPLAY is refused until D-31 mode (b)
    exists."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.import_batch(uow, migration_id, body),
        status_code=202,
        extra_headers=_job_location,
    )


@router.post(
    "/migrations/{migration_id}/reconcile",
    operation_id="migrations_reconcile",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def migrations_reconcile(
    migration_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Deps,
) -> Response:
    """Reconcile the imported migration against its legacy rows (LMG-3): IMPORTED only; a
    ``MIGRATION_RECONCILE`` job writes the T-MIG-03 lines once and moves the migration to
    RECONCILED."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.reconcile_batch(uow, migration_id),
        status_code=202,
        extra_headers=_job_location,
    )


@router.post(
    "/migrations/{migration_id}/cancel",
    operation_id="migrations_cancel",
    response_model=MigrationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def migrations_cancel(
    migration_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Deps,
) -> Response:
    """Cancel a migration that is not PROMOTED, FAILED or CANCELLED (E-76); a queued or running
    job the caller started is cancelled with it."""

    def handle(uow: UnitOfWork) -> MigrationOut:
        return _one_in(uow, commands.cancel_batch(uow, migration_id))

    return run_command(cmd, deps, handle, etag=migration_etag)


@router.get(
    "/migrations/{migration_id}/reconciliation-lines",
    operation_id="migrations_reconciliation_lines",
    response_model=ListOut[MigrationReconciliationLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def migrations_reconciliation_lines(
    migration_id: uuid.UUID, ctx: ReadContext
) -> ListOut[MigrationReconciliationLineOut]:
    """The T-MIG-03 lines of the migration in report order (RPT-41 columns; SCREENS_B §10.3
    "Reconciliation"); empty before the reconciliation ran."""

    def page(session: Session) -> list[MigrationReconciliationLineOut]:
        repository.get_batch_in_session(session, migration_id)  # 404 before an empty list
        rows = repository.reconciliation_rows_in_session(session, migration_id)
        numbers = repository.exception_numbers_in_session(
            session, [row["exception_item_id"] for row in rows if row.get("exception_item_id")]
        )
        return [queries.reconciliation_line_out(row, numbers) for row in rows]

    return ListOut[MigrationReconciliationLineOut](items=queries.read(ctx, page), next_cursor=None)


@router.get(
    "/migrations/{migration_id}/legacy-rows",
    operation_id="migrations_legacy_rows",
    response_model=ListOut[MigratedLegacyRowOut],
    responses=problem_responses(*_READ_PROBLEMS, "not-found", "validation-failed"),
)
def migrations_legacy_rows(
    migration_id: uuid.UUID,
    ctx: ReadContext,
    cursor: Annotated[
        str | None, Query(description="the last source_rowid of the page before")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=queries.LEGACY_ROWS_PAGE)] = queries.LEGACY_ROWS_PAGE,
) -> ListOut[MigratedLegacyRowOut]:
    """The migrated ``Contract_Live`` rows (T-MIG-02) in SQLite rowid order, a page at a time; the
    cursor is the last ``source_rowid`` returned (DG-LST)."""
    after: int | None = None
    if cursor is not None:
        if not cursor.isdigit():
            raise Problem(
                "validation-failed",
                "1 field needs attention.",
                errors=[
                    ProblemError(
                        field="cursor", rule_id="API-C-09", message="cursor is a source_rowid."
                    )
                ],
            )
        after = int(cursor)

    def page(session: Session) -> ListOut[MigratedLegacyRowOut]:
        repository.get_batch_in_session(session, migration_id)  # 404 before an empty list
        rows = repository.legacy_rows_in_session(
            session, migration_id, after_rowid=after, limit=limit
        )
        return ListOut[MigratedLegacyRowOut](
            items=[queries.legacy_row_out(row) for row in rows],
            next_cursor=queries.legacy_rows_cursor(rows, limit=limit),
        )

    return queries.read(ctx, page)
