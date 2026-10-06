"""T-MIG-01 to T-MIG-03 repository (BUILD_SPEC LMG-1, LMG-3; 04 §17 T-MIG-01 to T-MIG-03; PRD
BR-MIG-01, ERR-19, SM-12; REQ-MIG-001, REQ-MIG-003, REQ-MIG-004).

Functions over the request's ``UnitOfWork`` in SQLAlchemy Core (DG-LAY-05) — the one place the
migration jobs, routes and promotion read and write the three tables:

- ``create_batch``: a T-MIG-01 row numbered from series ``MIGRATION`` (KRN-NUM); an active batch
  (status not ``FAILED`` / ``CANCELLED``) with the same source digest and mode is refused with 409
  ``duplicate-import``, ``errors[0].rule_id = IMPORT_FILE_DUPLICATE`` and the ERR-19 copy
  (BR-MIG-01) — by the pre-read, and, when the INSERT loses the race on
  ``ux_migration_batch__source`` (SQLSTATE 23505), by a rollback-safe re-read of the winning batch
  inside a savepoint (Codex TMIG-R2, D-98 candidate 52); no other error is mapped to it;
- ``get_batch`` (404 ``not-found``) and ``list_batches``;
- ``transition``: one DB-03 change along E-76 through ``erev_api.db.transitions.apply`` (Python
  validation before any SQL, DG-SM-02), SC-M stamped from the principal;
- ``insert_legacy_rows``: T-MIG-02 rows from ``LegacyRow`` values — all 71 columns as stored text,
  the canonical SHA-256 per row, the label fixed (D-31 mode a; REQ-MIG-001);
- ``insert_reconciliation_lines``: T-MIG-03 rows from ``reconciliation.Line`` values; every line
  outside tolerance without a deviation reference must carry its exception item (04 T-MIG-03
  ``ck_migration_reconciliation_line__exception``), validated over the whole set before any SQL
  (Codex TMIG-R1); the table is IM-A, so a batch holds one set — a second set is refused with 409
  ``invalid-transition``;
- ``reconciliation_rows`` (the RPT-41 ``rows_reader`` shape) and ``legacy_rows`` (API-R-48
  ``GET /migrations/{id}/legacy-rows``);
- the ``MIGRATION_IMPORT`` capture writer ``insert_population`` (T-MIG-04 / T-MIG-05 from a
  ``capture.Capture``; one set per batch, 409 for a second) and the ``MIGRATION_RECONCILE`` readers
  (LMG-3): ``legacy_records`` (the legacy side), ``comparison_population`` (the batch's captured
  eRev population from T-MIG-04 — ``None`` when nothing is captured; nothing here selects a latest
  live version), ``population_obligation_versions`` (the T-MIG-05 rows of exactly the bound
  versions, shaped as ``obligation_version`` rows) and ``trace_nodes`` (the bound version's OWN
  calc-trace mirror from T-MIG-04, checked against the bound ``calc_trace_id``, book and hash).

Nothing here opens a database beyond the session; the SQLite copy is read by ``legacy_db``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.exc import DBAPIError

from erev_api import numbering
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    exception_item,
    migrated_legacy_row,
    migration_batch,
    migration_population_obligation,
    migration_population_version,
    migration_reconciliation_line,
)
from erev_api.db.tables.migration import LEGACY_ROW_LABEL, POPULATION_BOOK
from erev_api.domain.migration.capture import Capture
from erev_api.domain.migration.exact_values import ExactSourceError, NodeLookup
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.migration.population import ComparisonPopulation, VersionRef
from erev_api.domain.migration.reconciliation import Line, LineKey, exact_decimal
from erev_api.enums import MigrationMode, MigrationStatus
from erev_api.explain.store import TraceIntegrityError, trace_from_row
from erev_api.problems import Problem, ProblemError, from_db_error
from erev_api.uow import UnitOfWork

__all__ = [
    "ALREADY_RECONCILED_COPY",
    "CUTOVER_MODE_COPY",
    "EXCEPTION_LINK_COPY",
    "SOURCE_INDEX",
    "DUPLICATE_COPY",
    "DUPLICATE_RULE",
    "INACTIVE",
    "SERIES",
    "TABLE",
    "count_legacy_rows",
    "create_batch",
    "duplicate_problem",
    "exception_numbers",
    "get_batch",
    "insert_legacy_rows",
    "ALREADY_CAPTURED_COPY",
    "FOREIGN_CAPTURE_COPY",
    "captured_operation",
    "comparison_population",
    "verify_capture_evidence",
    "verify_input_evidence",
    "insert_population",
    "insert_reconciliation_lines",
    "legacy_records",
    "legacy_row_values",
    "legacy_rows",
    "line_values",
    "list_batches",
    "population_obligation_versions",
    "reconciliation_rows",
    "trace_nodes",
    "transition",
]

SERIES: Final = "MIGRATION"  # 04 T-PLT-26 series (prefix MIG-)
TABLE: Final = "migration_batch"
DUPLICATE_RULE: Final = "IMPORT_FILE_DUPLICATE"  # PRD ERR-19; BR-MIG-01
DUPLICATE_COPY: Final = "This legacy database was already imported in migration {number} on {date}."
CUTOVER_MODE_COPY: Final = (
    "A replay migration takes no cutover date; an opening-balance migration receives its cutover "
    "at import."  # T-MIG-01 CHECK (rev 1.60; D-98 candidate 128)
)
ALREADY_CAPTURED_COPY: Final = (
    "This migration already holds its captured comparison population; a batch is captured once "
    "(04 T-MIG-04, IM-A)."
)
FOREIGN_CAPTURE_COPY: Final = (
    "This migration holds a capture that is not its own operation's ({what}); the import refuses "
    "rather than adopt, re-run or overwrite it (04 T-MIG-01 rev 1.60)."
)
ALREADY_RECONCILED_COPY: Final = (
    "This migration already holds its reconciliation lines; reconcile again through a new "
    "migration."
)
EXCEPTION_LINK_COPY: Final = (
    "A difference above tolerance without a deviation reference needs its exception item."
)
INACTIVE: Final = (MigrationStatus.FAILED.value, MigrationStatus.CANCELLED.value)
SOURCE_INDEX: Final = "ux_migration_batch__source"  # 04 T-MIG-01 partial unique index


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _touch(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def duplicate_problem(number: str, created_at: datetime) -> Problem:
    """409 ``duplicate-import`` with the ERR-19 copy naming the earlier migration (BR-MIG-01)."""
    copy = DUPLICATE_COPY.format(number=number, date=created_at.date().isoformat())
    return Problem(
        "duplicate-import",
        copy,
        errors=[ProblemError(field="source_file_id", rule_id=DUPLICATE_RULE, message=copy)],
    )


def create_batch(
    uow: UnitOfWork,
    *,
    mode: MigrationMode,
    source_file_id: UUID,
    source_sha256: str,
    cutover_date: date | None = None,
    sandbox_tenant_id: UUID | None = None,
) -> dict[str, Any]:
    """Insert an ``UPLOADED`` T-MIG-01 row and return its values (04 T-MIG-01; SCREENS_B §10.2).

    A REPLAY batch never carries a cutover (the table CHECK); an OPENING_BALANCES batch is
    created without one and receives the user-confirmed date once at ``/import`` (D-98 candidate
    128); an active batch with the same source digest and mode is refused (BR-MIG-01; REQ-MIG-004).
    """
    # D-98 candidate 128 (04 T-MIG-01 rev 1.60): an OPENING_BALANCES batch is created WITHOUT a
    # cutover — the user-confirmed date is bound once at /import; REPLAY never carries one
    if mode is MigrationMode.REPLAY and cutover_date is not None:
        raise Problem(
            "validation-failed",
            "1 field needs attention.",
            errors=[
                ProblemError(field="cutover_date", rule_id="T-MIG-01", message=CUTOVER_MODE_COPY)
            ],
        )
    session = uow.session
    tenant_id = uow.principal.tenant_id
    existing = _active_duplicate(session, tenant_id, source_sha256, mode)
    if existing is not None:
        raise duplicate_problem(str(existing.migration_no), existing.created_at)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_no": numbering.next_number(uow, SERIES),
        "mode": mode.value,
        "status": MigrationStatus.UPLOADED.value,
        "source_file_id": source_file_id,
        "source_sha256": source_sha256,
        "cutover_date": cutover_date,
        "sandbox_tenant_id": sandbox_tenant_id,
        "profile": None,
        "import_upload_ids": [],
        "registry_version_id": None,
        "reconciliation_id": None,
        "reconciliation_report_run_id": None,
        "approval_request_id": None,
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "problem": None,
        **_created(uow),
        **_touch(uow),
    }
    savepoint = session.begin_nested()
    try:
        session.execute(insert(migration_batch).values(**values))
    except DBAPIError as error:
        savepoint.rollback()  # the outer transaction stays usable for the re-read
        if _lost_source_race(error):
            winner = _active_duplicate(session, tenant_id, source_sha256, mode)
            if winner is not None:
                raise duplicate_problem(str(winner.migration_no), winner.created_at) from error
        problem = from_db_error(error)
        if problem is None:
            raise
        raise problem from error
    savepoint.commit()
    return values


def _active_duplicate(
    session: Any, tenant_id: UUID, source_sha256: str, mode: MigrationMode
) -> Any:
    """The earliest active batch of the tenant with this source digest and mode, or None."""
    return session.execute(
        select(migration_batch.c.migration_no, migration_batch.c.created_at)
        .where(
            migration_batch.c.tenant_id == tenant_id,
            migration_batch.c.source_sha256 == source_sha256,
            migration_batch.c.mode == mode.value,
            migration_batch.c.status.not_in(INACTIVE),
        )
        .order_by(migration_batch.c.created_at)
    ).first()


def _lost_source_race(error: DBAPIError) -> bool:
    """True for the one error the duplicate refusal covers: a unique violation (SQLSTATE 23505)
    on ``ux_migration_batch__source``; anything else is not a duplicate."""
    origin = error.orig
    if getattr(origin, "sqlstate", None) != "23505":
        return False
    constraint = getattr(getattr(origin, "diag", None), "constraint_name", None)
    return constraint == SOURCE_INDEX or SOURCE_INDEX in str(origin)


def get_batch_in_session(session: Any, batch_id: UUID) -> Mapping[str, Any]:
    """The T-MIG-01 row, or 404 ``not-found`` (a row another tenant owns is not visible); the
    read-route form over a read-only tenant session (API-R-48 ``GET`` routes, DG-CMD-13)."""
    row = (
        session.execute(select(migration_batch).where(migration_batch.c.id == batch_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found", "Migration not found.")
    return dict(row)


def get_batch(uow: UnitOfWork, batch_id: UUID) -> Mapping[str, Any]:
    """The T-MIG-01 row, or 404 ``not-found`` (a row another tenant owns is not visible)."""
    return get_batch_in_session(uow.session, batch_id)


def list_batches(uow: UnitOfWork) -> list[Mapping[str, Any]]:
    """Every T-MIG-01 row of the tenant, newest first (API-R-48 ``GET /migrations``)."""
    rows = (
        uow.session.execute(
            select(migration_batch).order_by(
                migration_batch.c.created_at.desc(), migration_batch.c.migration_no.desc()
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def transition(
    uow: UnitOfWork,
    batch_id: UUID,
    *,
    to_status: MigrationStatus | None,
    expected_status: MigrationStatus,
    expected_row_version: int | None = None,
    **set_values: Any,
) -> Mapping[str, Any]:
    """One DB-03 change of the batch along E-76 (PRD SM-12), SC-M stamped: ``to_status`` None
    changes listed columns only. Python validation raises 409 ``invalid-transition`` before any
    SQL; a status mismatch at the database is 409 too (``transitions.apply``)."""
    return transitions.apply(
        uow.session,
        TABLE,
        batch_id,
        to_status=None if to_status is None else to_status.value,
        set_values={**set_values, **_touch(uow)},
        expected_status=expected_status.value,
        expected_row_version=expected_row_version,
    )


def legacy_row_values(uow: UnitOfWork, batch_id: UUID, row: LegacyRow) -> dict[str, Any]:
    """The T-MIG-02 values of one ``Contract_Live`` row: the 71 columns keyed by their legacy names
    with the stored text, the canonical SHA-256, the fixed label (REQ-MIG-001; D-31 mode a)."""
    return {
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "migration_batch_id": batch_id,
        "source_rowid": row.source_rowid,
        "contract_external_id": row.contract_external_id,
        "obligation_key": row.obligation_key,
        "product_code": row.product_code,
        "current_period": row.current_period,
        "processing_time_log": row.processing_time_log,
        "record_unique_id": row.record_unique_id,
        "legacy_row": dict(row.values),
        "legacy_row_sha256": row.sha256,
        "contract_id": None,
        "obligation_id": None,
        "label": LEGACY_ROW_LABEL,
        **_created(uow),
    }


def insert_legacy_rows(uow: UnitOfWork, batch_id: UUID, rows: Iterable[LegacyRow]) -> int:
    """Insert every row of the copy as a T-MIG-02 row; returns the count (24 for WLD-F-15)."""
    values = [legacy_row_values(uow, batch_id, row) for row in rows]
    if values:
        uow.session.execute(insert(migrated_legacy_row), values)
    return len(values)


def count_legacy_rows(uow: UnitOfWork, batch_id: UUID) -> int:
    count = uow.session.execute(
        select(func.count())
        .select_from(migrated_legacy_row)
        .where(migrated_legacy_row.c.migration_batch_id == batch_id)
    ).scalar_one()
    return int(count)


def line_values(
    uow: UnitOfWork, batch_id: UUID, line: Line, exception_items: Mapping[LineKey, UUID]
) -> dict[str, Any]:
    """The T-MIG-03 values of one line: exact decimals (``erev.exact``), the exception item of an
    unexplained difference by the line's identity ``Line.key`` — (contract, obligation, measure),
    never the display key (04 T-MIG-03 ``exception_item_id``; Codex RPT41-ID-1)."""
    return {
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "migration_batch_id": batch_id,
        "contract_external_id": line.contract_external_id,
        "obligation_key": line.obligation_key,
        "measure": line.measure,
        "source_value": exact_decimal(line.source_value),
        "erev_value": exact_decimal(line.erev_value),
        "difference": exact_decimal(line.difference),
        "tolerance": exact_decimal(line.tolerance),
        "is_within_tolerance": line.is_within_tolerance,
        "deviation_ref": line.deviation_ref,
        "exception_item_id": exception_items.get(line.key) if line.needs_exception else None,
        **_created(uow),
    }


def insert_reconciliation_lines(
    uow: UnitOfWork,
    batch_id: UUID,
    lines: Iterable[Line],
    *,
    exception_items: Mapping[LineKey, UUID] | None = None,
) -> int:
    """Insert the batch's T-MIG-03 lines once. Every line outside tolerance without a deviation
    reference must map to its exception item by ``Line.key`` (04 T-MIG-03; Codex TMIG-R1) — the
    whole set is validated before any SQL and refused as a whole; a batch that already holds lines
    is refused too (the table is IM-A: nothing is updated or deleted)."""
    items = {} if exception_items is None else exception_items
    population = tuple(lines)
    # an absent key and a None value are both a missing link (Mapping[str, UUID]; Codex retest)
    missing = [
        line.row_key for line in population if line.needs_exception and items.get(line.key) is None
    ]
    if missing:
        raise Problem(
            "validation-failed",
            f"{len(missing)} line(s) need attention.",
            errors=[
                ProblemError(
                    field=f"lines[{row_key}].exception_item_id",
                    rule_id="T-MIG-03",
                    message=EXCEPTION_LINK_COPY,
                )
                for row_key in missing
            ],
        )
    existing = uow.session.execute(
        select(func.count())
        .select_from(migration_reconciliation_line)
        .where(migration_reconciliation_line.c.migration_batch_id == batch_id)
    ).scalar_one()
    if int(existing) > 0:
        raise Problem(
            "invalid-transition",
            ALREADY_RECONCILED_COPY,
            errors=[
                ProblemError(
                    field="migration_id", rule_id="T-MIG-03", message=ALREADY_RECONCILED_COPY
                )
            ],
        )
    values = [line_values(uow, batch_id, line, items) for line in population]
    if values:
        uow.session.execute(insert(migration_reconciliation_line), values)
    return len(values)


def reconciliation_rows(uow: UnitOfWork, batch_id: UUID) -> list[Mapping[str, Any]]:
    """The batch's T-MIG-03 rows in report order (contract, contract level first, measure) — the
    ``rows_reader`` shape of RPT-41 (``builders.migration_reconciliation.lines_from_rows``)."""
    return reconciliation_rows_in_session(uow.session, batch_id)


def reconciliation_rows_in_session(session: Any, batch_id: UUID) -> list[Mapping[str, Any]]:
    """``reconciliation_rows`` over a session (the API-R-48 ``/reconciliation-lines`` read)."""
    rows = (
        session.execute(
            select(migration_reconciliation_line)
            .where(migration_reconciliation_line.c.migration_batch_id == batch_id)
            .order_by(
                migration_reconciliation_line.c.contract_external_id,
                migration_reconciliation_line.c.obligation_key.nulls_first(),
                migration_reconciliation_line.c.measure,
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def legacy_rows(
    uow: UnitOfWork, batch_id: UUID, *, after_rowid: int | None = None, limit: int = 500
) -> list[Mapping[str, Any]]:
    """The batch's T-MIG-02 rows in SQLite ``rowid`` order, a page at a time (API-R-48
    ``/legacy-rows``; DG-LST cursor = the last ``source_rowid``)."""
    return legacy_rows_in_session(uow.session, batch_id, after_rowid=after_rowid, limit=limit)


def legacy_rows_in_session(
    session: Any, batch_id: UUID, *, after_rowid: int | None = None, limit: int = 500
) -> list[Mapping[str, Any]]:
    """``legacy_rows`` over a session (the API-R-48 ``/legacy-rows`` read)."""
    statement = select(migrated_legacy_row).where(
        migrated_legacy_row.c.migration_batch_id == batch_id
    )
    if after_rowid is not None:
        statement = statement.where(migrated_legacy_row.c.source_rowid > after_rowid)
    rows = (
        session.execute(statement.order_by(migrated_legacy_row.c.source_rowid).limit(limit))
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def exception_numbers(uow: UnitOfWork, ids: Iterable[UUID]) -> dict[UUID, str]:
    """``exception_no`` of the visible exception items named by ``ids`` (RPT-41 "Exception"
    column, SCREENS_B §5.6.7); an id without a visible row is absent from the result."""
    return exception_numbers_in_session(uow.session, ids)


def exception_numbers_in_session(session: Any, ids: Iterable[UUID]) -> dict[UUID, str]:
    """``exception_numbers`` over a session (the API-R-48 ``/reconciliation-lines`` read)."""
    wanted = sorted({UUID(str(value)) for value in ids})
    if not wanted:
        return {}
    rows = (
        session.execute(
            select(exception_item.c.id, exception_item.c.exception_no).where(
                exception_item.c.id.in_(wanted)
            )
        )
        .mappings()
        .all()
    )
    return {UUID(str(row["id"])): str(row["exception_no"]) for row in rows}


def legacy_records(uow: UnitOfWork, batch_id: UUID) -> tuple[LegacyRow, ...]:
    """The batch's T-MIG-02 rows as ``LegacyRow`` values (the stored 71 columns, SQLite rowid) in
    rowid order — the legacy side of the reconciliation (``legacy_db.latest_rows`` selects the
    latest version per record key)."""
    rows = (
        uow.session.execute(
            select(migrated_legacy_row.c.source_rowid, migrated_legacy_row.c.legacy_row)
            .where(migrated_legacy_row.c.migration_batch_id == batch_id)
            .order_by(migrated_legacy_row.c.source_rowid)
        )
        .mappings()
        .all()
    )
    return tuple(LegacyRow(int(row["source_rowid"]), dict(row["legacy_row"])) for row in rows)


def _population_version_values(uow: UnitOfWork, batch_id: UUID, version: Any) -> dict[str, Any]:
    return {
        **_created(uow),
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "migration_batch_id": batch_id,
        "contract_version_id": version.contract_version_id,
        "version_no": version.version_no,
        "book_code": version.book_code,
        "combination_group_id": version.combination_group_id,
        "status_in_book": version.status_in_book,
        "contract_computation_id": version.contract_computation_id,
        "input_sha256": version.input_sha256,
        "output_sha256": version.output_sha256,
        "engine_version": version.engine_version,
        "engine_release_id": version.engine_release_id,
        "known_at": version.known_at,
        "bundle_known_at": version.bundle_known_at,
        "cutover_date": version.cutover_date,
        "payload_migration_batch_id": version.payload_migration_batch_id,
        "opening_event_id": version.opening_event_id,
        "opening_event_key": version.opening_event_key,
        "opening_event_binding_sha256": version.opening_event_binding_sha256,
        "members": [
            {
                "contract_id": str(member.contract_id),
                "contract_external_id": member.contract_external_id,
            }
            for member in version.members
        ],
        "expected_output_captured": version.expected_output_captured,
        "obligation_version_ids": list(version.obligation_version_ids),
        "capture_operation_id": version.capture_operation_id,
        "calc_trace_id": version.calc_trace_id,
        "format_version": version.format_version,
        "node_count": version.node_count,
        "root_measures": dict(version.root_measures),
        "trace_sha256": version.trace_sha256,
        "trace": dict(version.trace),
        "input_evidence": dict(version.input_evidence),
        "input_evidence_sha256": version.input_evidence_sha256,
    }


def _population_obligation_values(
    uow: UnitOfWork, batch_id: UUID, population_version_id: UUID, item: Any
) -> dict[str, Any]:
    return {
        **_created(uow),
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "migration_batch_id": batch_id,
        "population_version_id": population_version_id,
        "capture_operation_id": item.capture_operation_id,
        "contract_version_id": item.contract_version_id,
        "obligation_version_id": item.obligation_version_id,
        "contract_id": item.contract_id,
        "contract_external_id": item.contract_external_id,
        "obligation_key": item.obligation_key,
        "obligation_kind": item.obligation_kind,
        "original_allocated_exact": item.original_allocated_exact,
        "remaining_quantity": item.remaining_quantity,
        "billed_cum": item.billed_cum,
        "revenue_cum": item.revenue_cum,
        "remaining_allocation": item.remaining_allocation,
        "position_obligation": item.position_obligation,
        "netting_reclass_amount": item.netting_reclass_amount,
        "trace_nodes": dict(item.trace_nodes),
        "row": dict(item.row),
        "row_sha256": item.row_sha256,
    }


def insert_population(uow: UnitOfWork, batch_id: UUID, capture: Capture) -> tuple[int, int]:
    """Store the import dry run's capture as T-MIG-04 / T-MIG-05 rows (IM-A): one set per batch —
    a second set is refused with 409 ``invalid-transition`` (``ALREADY_CAPTURED_COPY``) before any
    SQL writes. Returns (versions, obligations) inserted."""
    existing = uow.session.execute(
        select(func.count())
        .select_from(migration_population_version)
        .where(migration_population_version.c.migration_batch_id == batch_id)
    ).scalar_one()
    if int(existing) > 0:
        raise Problem(
            "invalid-transition",
            ALREADY_CAPTURED_COPY,
            errors=[
                ProblemError(
                    field="migration_id", rule_id="T-MIG-04", message=ALREADY_CAPTURED_COPY
                )
            ],
        )
    version_rows = [
        _population_version_values(uow, batch_id, version) for version in capture.versions
    ]
    ids = {row["contract_version_id"]: row["id"] for row in version_rows}
    obligation_rows = [
        _population_obligation_values(uow, batch_id, ids[item.contract_version_id], item)
        for item in capture.obligations
    ]
    if version_rows:
        uow.session.execute(insert(migration_population_version), version_rows)
    if obligation_rows:
        uow.session.execute(insert(migration_population_obligation), obligation_rows)
    return len(version_rows), len(obligation_rows)


def comparison_population(uow: UnitOfWork, batch: Mapping[str, Any]) -> ComparisonPopulation | None:
    """The batch's captured comparison population from T-MIG-04 (``population.
    ComparisonPopulation``), or ``None`` while nothing is captured — the import's dry run supplies
    it (mode (a), ``capture``; the capture is DURABLE, D-98 candidate 122: a savepoint-only dry run
    whose rows are gone after rollback is not a capture); mode (b) is the LMG-4 replay slice. This
    reader never selects a latest live version in the population's place; the job refuses by name
    when it returns ``None``. A stored row that does not bind raises ``PopulationError`` at the
    reader boundary — the job names it."""
    batch_id = UUID(str(batch["id"]))
    rows = (
        uow.session.execute(
            select(migration_population_version)
            .where(migration_population_version.c.migration_batch_id == batch_id)
            .order_by(migration_population_version.c.contract_version_id)
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    refs = tuple(
        VersionRef(
            contract_ids=frozenset(
                UUID(str(member["contract_id"])) for member in (row["members"] or [])
            ),
            contract_version_id=UUID(str(row["contract_version_id"])),
            calc_trace_id=UUID(str(row["calc_trace_id"])),
            book_code=str(row["book_code"]),
            obligation_version_ids=frozenset(
                UUID(str(value)) for value in (row["obligation_version_ids"] or [])
            ),
            cutover_date=row["cutover_date"],
            payload_migration_batch_id=UUID(str(row["payload_migration_batch_id"])),
            trace_sha256=str(row["trace_sha256"]),
            expected_output_captured=bool(row["expected_output_captured"]),
            members={
                UUID(str(member["contract_id"])): str(member["contract_external_id"])
                for member in (row["members"] or [])
            },
            capture_batch_id=batch_id,
        )
        for row in rows
    )
    return ComparisonPopulation(
        batch_id=batch_id,
        mode=MigrationMode(str(batch["mode"])),
        cutover_date=batch.get("cutover_date"),
        book_code=POPULATION_BOOK,
        versions=refs,
    )


def population_obligation_versions(
    uow: UnitOfWork, population: ComparisonPopulation
) -> list[dict[str, Any]]:
    """The T-MIG-05 rows of exactly the population's bound contract versions (by
    ``contract_version_id``; no knowledge-time or version-number selection), shaped as the
    ``obligation_version`` rows ``exact_values.erev_values`` reads (``id`` = the captured
    ``obligation_version_id``; ``book_code`` = the capture's book) after ``population.bind`` has
    checked them."""
    wanted = [ref.contract_version_id for ref in population.versions]
    parents = _capture_parents(uow, population)
    table = migration_population_obligation
    rows = (
        uow.session.execute(
            select(table)
            .where(
                table.c.migration_batch_id == population.batch_id,
                table.c.contract_version_id.in_(wanted),
            )
            .order_by(table.c.contract_external_id, table.c.obligation_key)
        )
        .mappings()
        .all()
    )
    shaped: list[dict[str, Any]] = []
    seen: set[UUID] = set()
    for row in rows:
        _bind_child(dict(row), parents, population.batch_id)
        child_id = UUID(str(row["obligation_version_id"]))
        if child_id in seen:
            raise ExactSourceError(
                f"captured obligation version {child_id} is supplied twice in the capture"
            )
        seen.add(child_id)
        _check_row_representation(dict(row))
        shaped.append(
            {
                "id": row["obligation_version_id"],
                "contract_version_id": row["contract_version_id"],
                "contract_id": row["contract_id"],
                "book_code": population.book_code,
                "contract_external_id": row["contract_external_id"],
                "obligation_key": row["obligation_key"],
                "obligation_kind": row["obligation_kind"],
                "original_allocated_exact": row["original_allocated_exact"],
                "remaining_quantity": row["remaining_quantity"],
                "billed_cum": row["billed_cum"],
                "revenue_cum": row["revenue_cum"],
                "remaining_allocation": row["remaining_allocation"],
                "position_obligation": row["position_obligation"],
                "netting_reclass_amount": row["netting_reclass_amount"],
                "trace_nodes": dict(row["trace_nodes"] or {}),
            }
        )
    return shaped


def _capture_parents(
    uow: UnitOfWork, population: ComparisonPopulation
) -> dict[UUID, Mapping[str, Any]]:
    """The T-MIG-04 rows of the population's bound versions IN THIS BATCH, by contract version —
    the durable parents every T-MIG-05 row must belong to (Codex 0533 R2b)."""
    table = migration_population_version
    rows = (
        uow.session.execute(
            select(
                table.c.id,
                table.c.contract_version_id,
                table.c.migration_batch_id,
                table.c.capture_operation_id,
            ).where(
                table.c.migration_batch_id == population.batch_id,
                table.c.contract_version_id.in_(
                    [ref.contract_version_id for ref in population.versions]
                ),
            )
        )
        .mappings()
        .all()
    )
    return {UUID(str(row["contract_version_id"])): dict(row) for row in rows}


def _bind_child(
    row: Mapping[str, Any], parents: Mapping[UUID, Mapping[str, Any]], batch_id: UUID
) -> None:
    """A T-MIG-05 row belongs to its durable parent, batch and operation — checked before those
    columns are dropped from the read shape (Codex 0533 R2b)."""
    label = f"captured obligation version {row['obligation_version_id']}"
    parent = parents.get(UUID(str(row["contract_version_id"])))
    if parent is None:
        raise ExactSourceError(f"{label}: no captured parent version in this batch")
    if UUID(str(row["population_version_id"])) != UUID(str(parent["id"])):
        raise ExactSourceError(
            f"{label}: population_version_id {row['population_version_id']} is not its parent "
            f"{parent['id']}"
        )
    if UUID(str(row["migration_batch_id"])) != batch_id:
        raise ExactSourceError(f"{label}: migration_batch_id is not the population's batch")
    if str(row["capture_operation_id"]) != str(parent["capture_operation_id"]):
        raise ExactSourceError(
            f"{label}: capture_operation_id {row['capture_operation_id']} is not the parent's "
            f"{parent['capture_operation_id']}"
        )


_ROW_MEASURES: Final = (
    "original_allocated_exact",
    "remaining_quantity",
    "billed_cum",
    "revenue_cum",
    "remaining_allocation",
    "position_obligation",
    "netting_reclass_amount",
)


def _check_row_representation(row: Mapping[str, Any]) -> None:
    """Two representations, one truth (04 T-MIG-05 rev 1.60; Codex 0422 (g)): the typed measure
    columns must equal the canonical ``row`` values and ``row_sha256`` must be the hash of ``row``,
    and the identity columns must agree — before any measure is extracted. A disagreement fails
    closed (``ExactSourceError`` → the job's DG-PAR-05 refusal)."""
    from decimal import Decimal

    from erev_api.domain.migration.capture import canonical_row

    document = dict(row["row"] or {})
    _, digest = canonical_row(document)
    label = f"captured obligation version {row['obligation_version_id']}"
    if digest != str(row["row_sha256"]):
        raise ExactSourceError(f"{label}: row_sha256 does not match its canonical row")
    for column in _ROW_MEASURES:
        stored = document.get(column)
        typed = row[column]
        if stored is None or typed is None or Decimal(str(stored)) != Decimal(str(typed)):
            raise ExactSourceError(
                f"{label}: {column} {typed!r} disagrees with the retained row {stored!r}"
            )
    for column in ("id", "contract_version_id", "contract_id", "obligation_key", "obligation_kind"):
        stored = document.get(column)
        typed = row["obligation_version_id"] if column == "id" else row[column]
        if str(stored) != str(typed):
            raise ExactSourceError(
                f"{label}: {column} {typed!r} disagrees with the retained row {stored!r}"
            )
    if dict(document.get("trace_nodes") or {}) != dict(row["trace_nodes"] or {}):
        raise ExactSourceError(f"{label}: trace_nodes disagree with the retained row")


def trace_nodes(uow: UnitOfWork, ref: VersionRef) -> NodeLookup:
    """The node lookup of a bound version's OWN calc trace from its T-MIG-04 mirror: the row of
    ``ref.contract_version_id`` whose ``calc_trace_id`` is the bound one in the bound book, rebuilt
    through ``explain.store.trace_from_row`` (hash-checked against the mirrored ``trace_sha256``,
    DG-KRN-EXP-05). A version that records no trace, no stored row, another trace id, another book
    or a hash mismatch fails closed (``ExactSourceError``) — a same-named node of another trace is
    not evidence for this version, and missing evidence never becomes 0."""
    version_id = ref.contract_version_id
    if ref.calc_trace_id is None:
        raise ExactSourceError(f"contract version {version_id} records no calc trace")
    table = migration_population_version
    statement = select(table).where(table.c.contract_version_id == version_id)
    if ref.capture_batch_id is not None:  # scoped to the same capture (Codex 0533 R2b)
        statement = statement.where(table.c.migration_batch_id == ref.capture_batch_id)
    row = uow.session.execute(statement).mappings().one_or_none()
    if row is None:
        raise ExactSourceError(f"contract version {version_id} has no captured calc trace")
    if UUID(str(row["calc_trace_id"])) != ref.calc_trace_id:
        raise ExactSourceError(
            f"captured calc trace {row['calc_trace_id']} of contract version {version_id} is not "
            f"the bound calc trace {ref.calc_trace_id}"
        )
    if str(row["book_code"]) != ref.book_code:
        raise ExactSourceError(
            f"captured calc trace of contract version {version_id} is in book {row['book_code']}, "
            f"not the bound {ref.book_code}"
        )
    if ref.trace_sha256 is not None and str(row["trace_sha256"]) != ref.trace_sha256:
        raise ExactSourceError(
            f"captured calc trace of contract version {version_id} carries hash "
            f"{row['trace_sha256']}, not the bound {ref.trace_sha256}"
        )
    try:
        trace = trace_from_row(
            {
                "id": row["calc_trace_id"],
                "format_version": row["format_version"],
                "engine_version": row["engine_version"],
                "trace": row["trace"],
                "root_measures": row["root_measures"],
                "trace_sha256": row["trace_sha256"],
            }
        )
    except TraceIntegrityError as error:
        raise ExactSourceError(str(error)) from error
    if ref.trace_sha256 is not None and trace.sha256() != ref.trace_sha256:
        raise ExactSourceError(
            f"the rebuilt calc trace of contract version {version_id} does not hash to the bound "
            f"{ref.trace_sha256}"
        )
    by_id = {node.id: node for node in trace.nodes}
    return by_id.get


def verify_input_evidence(row: Mapping[str, Any]) -> None:
    """Codex 0515 R1: the retained T-CON-25 input evidence of a T-MIG-04 row must be the producing
    bundle — re-encoded it reproduces ``input_evidence_sha256``, decoded it hashes (CV-25) to
    ``input_sha256``, its ``known_at`` is ``bundle_known_at``, its member keys are the row's
    ``members``, and its ``OPENING_BALANCE_ESTABLISHED`` event names this batch and cutover.
    Missing, tampered or mismatched evidence fails closed (``ExactSourceError``)."""
    from erev_engine.canonical import canonical_bytes
    from erev_engine.upgrade import decode_input, raw_digest

    label = f"contract version {row['contract_version_id']}"
    document = row.get("input_evidence")
    if not document:
        raise ExactSourceError(f"{label}: no input evidence is retained")
    encoded = canonical_bytes(document)
    if raw_digest(encoded) != str(row["input_evidence_sha256"]):
        raise ExactSourceError(
            f"{label}: the input evidence does not hash to input_evidence_sha256"
        )
    try:
        bundle = decode_input(encoded)
    except (ValueError, TypeError, KeyError) as error:
        raise ExactSourceError(f"{label}: the input evidence does not decode: {error}") from error
    if bundle.sha256() != str(row["input_sha256"]):
        raise ExactSourceError(f"{label}: the decoded bundle does not hash to input_sha256")
    if bundle.known_at != row["bundle_known_at"]:
        raise ExactSourceError(f"{label}: the decoded bundle's known_at is not bundle_known_at")
    members = {str(member["contract_external_id"]) for member in (row["members"] or [])}
    if set(bundle.group.member_contract_keys) != members:
        raise ExactSourceError(
            f"{label}: the decoded bundle's members are not the captured members"
        )
    opening = [
        event
        for event in bundle.events
        if event.event_type == "OPENING_BALANCE_ESTABLISHED"
        and str(event.payload.get("migration_batch_id")) == str(row["payload_migration_batch_id"])
        and str(event.payload.get("cutover_date")) == row["cutover_date"].isoformat()
    ]
    if len(opening) != 1:
        raise ExactSourceError(
            f"{label}: the decoded bundle carries {len(opening)} OPENING_BALANCE_ESTABLISHED "
            "events naming this migration and cutover; exactly one is the admitted input"
        )
    # Codex 0605 R1: the declared event UUID is bound to THIS logical event — the retained key
    # must be the bundle's, and the capture-time binding digest must recompute from the row's UUID
    from erev_api.domain.migration.capture import opening_event_binding

    (event,) = opening
    if str(row.get("opening_event_key")) != event.event_key:
        raise ExactSourceError(
            f"{label}: opening_event_key {row.get('opening_event_key')!r} is not the bundle's "
            f"opening event {event.event_key!r}"
        )
    binding = opening_event_binding(
        UUID(str(row["opening_event_id"])), event.event_key, str(event.payload_sha256)
    )
    if binding != str(row.get("opening_event_binding_sha256")):
        raise ExactSourceError(
            f"{label}: opening_event_id {row['opening_event_id']} is not the event the capture "
            "bound (opening_event_binding_sha256 mismatch)"
        )


def verify_capture_evidence(uow: UnitOfWork, population: ComparisonPopulation) -> None:
    """Every bound version's retained input evidence verified (``verify_input_evidence``) — the
    reconcile's step between binding and extraction; the job maps a failure to DG-PAR-05."""
    table = migration_population_version
    rows = (
        uow.session.execute(
            select(table).where(
                table.c.migration_batch_id
                == population.batch_id,  # the unique key: batch + version
                table.c.contract_version_id.in_(
                    [ref.contract_version_id for ref in population.versions]
                ),
            )
        )
        .mappings()
        .all()
    )
    found: dict[UUID, dict[str, Any]] = {}
    for mapping in rows:
        version_id = UUID(str(mapping["contract_version_id"]))
        if version_id in found:  # Codex 0605 R2b: ambiguity is refused, never collapsed
            raise ExactSourceError(
                f"contract version {version_id}: the capture holds more than one evidence row in "
                "this batch"
            )
        found[version_id] = dict(mapping)
    for ref in population.versions:
        evidence_row = found.get(ref.contract_version_id)
        if evidence_row is None:
            raise ExactSourceError(
                f"contract version {ref.contract_version_id}: no captured row to verify"
            )
        if UUID(str(evidence_row["calc_trace_id"])) != ref.calc_trace_id:
            raise ExactSourceError(
                f"contract version {ref.contract_version_id}: the evidence row is not the bound "
                "capture (calc_trace_id differs)"
            )
        verify_input_evidence(evidence_row)


def captured_operation(uow: UnitOfWork, batch: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The stored capture of the batch's own operation, validated for same-operation recovery
    (04 T-MIG-01 note rev 1.60; Codex 0422 lifecycle): every T-MIG-04 / T-MIG-05 row carries the
    batch's ``capture_operation_id``, the population binds to the batch (``check_batch``), every
    T-MIG-05 row agrees with its retained row and hash, and every bound version's trace mirror
    rebuilds to its captured hash. Returns the counts ``{"captured_versions", "captured_obligation_
    versions"}`` when complete; ``None`` when nothing is captured; raises ``Problem`` (409
    ``invalid-transition``) for a foreign, conflicting or incomplete capture."""
    operation = batch.get("capture_operation_id")
    population = comparison_population(uow, batch)
    if population is None:
        return None
    if operation is None:
        raise Problem("invalid-transition", FOREIGN_CAPTURE_COPY.format(what="no operation id"))
    for table in (migration_population_version, migration_population_obligation):
        operations = {
            str(value)
            for value in uow.session.execute(
                select(table.c.capture_operation_id).where(
                    table.c.migration_batch_id == UUID(str(batch["id"]))
                )
            ).scalars()
        }
        if table is migration_population_obligation and not operations:
            continue  # a capture of empty outputs has no child rows (D-98-78)
        if operations != {str(operation)}:
            raise Problem(
                "invalid-transition",
                FOREIGN_CAPTURE_COPY.format(
                    what=f"{table.name} operations {sorted(operations)} vs {operation}"
                ),
            )
    population.check_batch(batch)
    rows = population_obligation_versions(uow, population)  # validates each row's representation
    bound = population.bind(rows)
    for ref in population.versions:
        trace_nodes(uow, ref)  # rebuild + hash check against the bound hash
    verify_capture_evidence(uow, population)  # the retained input evidence (Codex 0515 R1)
    return {
        "captured_versions": len(population.versions),
        "captured_obligation_versions": len(bound),
    }
