"""API-R-48 reads: the API-S-Migration mapping, the list statement, the reconciliation lines and
the legacy-row cursor (04 §15.3 API-R-48; SCREENS_B §10.1 to §10.3; BUILD_SPEC LMG-1, LMG-3;
lane record §25).

``migration_outs`` maps T-MIG-01 rows to ``MigrationOut`` with the SCREENS_B §10.1 list figure
``unexplained_count`` — the batch's T-MIG-03 lines outside tolerance without a deviation reference
(``reconciliation.control_totals``' predicate; an exception link explains nothing; BR-MIG-02:
promotion needs zero) — read in one grouped query per page. Reads run in a read-only tenant
session (DG-CMD-13).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import migration_batch, migration_reconciliation_line
from erev_api.domain.migration import reconciliation
from erev_api.domain.platform import approval_queries
from erev_api.enums import PrincipalKind
from erev_api.schemas.common import ActorOut, ProblemOut
from erev_api.schemas.migrations import (
    MigratedLegacyRowOut,
    MigrationOut,
    MigrationProfileOut,
    MigrationReconciliationLineOut,
)

__all__ = [
    "LEGACY_ROWS_PAGE",
    "legacy_row_out",
    "legacy_rows_cursor",
    "migration_out",
    "migration_outs",
    "migrations_statement",
    "read",
    "reconciliation_line_out",
    "unexplained_counts",
]

LEGACY_ROWS_PAGE: Final = 500  # API-R-48 ``/legacy-rows``: one page of T-MIG-02 rows (DG-LST)


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def migrations_statement() -> Select[Any]:
    """``GET /migrations``; the list filters apply through the resource's ``ListSpec``."""
    return select(migration_batch)


def unexplained_counts(session: Session, batch_ids: Sequence[UUID]) -> dict[UUID, int]:
    """Per batch, the T-MIG-03 lines outside tolerance WITHOUT a deviation reference — the
    ``reconciliation.control_totals`` predicate (SCREENS_B §10.1 "Unexplained differences";
    BR-MIG-02). An exception link does not explain a difference: a line with an exception item but
    no deviation counts and blocks promotion (Codex 0727)."""
    wanted = sorted({UUID(str(value)) for value in batch_ids})
    if not wanted:
        return {}
    line = migration_reconciliation_line
    rows = session.execute(
        select(line.c.migration_batch_id, func.count())
        .where(
            line.c.migration_batch_id.in_(wanted),
            line.c.is_within_tolerance.is_(False),
            line.c.deviation_ref.is_(None),
        )
        .group_by(line.c.migration_batch_id)
    ).all()
    counts = dict.fromkeys(wanted, 0)
    for batch_id, count in rows:
        counts[UUID(str(batch_id))] = int(count)
    return counts


def _actor(row: Mapping[str, Any], names: Mapping[Any, str]) -> ActorOut:
    user_id = row["created_by"]
    return ActorOut(
        id=None if user_id is None else UUID(str(user_id)),
        kind=PrincipalKind(str(getattr(row["created_by_kind"], "value", row["created_by_kind"]))),
        display_name=names.get(user_id, "System"),
    )


def _profile(value: Mapping[str, Any] | None) -> MigrationProfileOut | None:
    if value is None:
        return None
    # ``columns`` is the profile's own detail (legacy_db.LegacyProfile.as_json); the API-S shape
    # carries the key figures SCREENS_B §10.3 shows
    return MigrationProfileOut.model_validate(
        {key: value[key] for key in MigrationProfileOut.model_fields if key in value}
    )


def migration_out(
    row: Mapping[str, Any], *, names: Mapping[Any, str], unexplained: int | None
) -> MigrationOut:
    """API-S-Migration of one T-MIG-01 row."""
    problem = row.get("problem")
    return MigrationOut(
        id=UUID(str(row["id"])),
        migration_no=str(row["migration_no"]),
        mode=row["mode"],
        status=row["status"],
        source_file_id=UUID(str(row["source_file_id"])),
        source_sha256=str(row["source_sha256"]).strip(),
        cutover_date=row.get("cutover_date"),
        sandbox_tenant_id=row.get("sandbox_tenant_id"),
        profile=_profile(row.get("profile")),
        import_upload_ids=[UUID(str(value)) for value in (row.get("import_upload_ids") or [])],
        registry_version_id=row.get("registry_version_id"),
        reconciliation_report_run_id=row.get("reconciliation_report_run_id"),
        approval_request_id=row.get("approval_request_id"),
        job_id=row.get("job_id"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        problem=None if problem is None else ProblemOut.model_validate(problem),
        unexplained_count=unexplained,
        row_version=int(row["row_version"]),
        created_by=_actor(row, names),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def migration_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[MigrationOut]:
    """API-S-Migration of each T-MIG-01 row of a page, with ``unexplained_count``."""
    if not rows:
        return []
    names = approval_queries.display_names(session, [row["created_by"] for row in rows])
    counts = unexplained_counts(session, [UUID(str(row["id"])) for row in rows])
    return [
        migration_out(row, names=names, unexplained=counts.get(UUID(str(row["id"])), 0))
        for row in rows
    ]


def _exact(value: Any) -> str:
    """A stored T-MIG-03 ``erev.exact`` value as 04 API-C-06 states it and RPT-41 shows it:
    decimal text with trailing zeros trimmed and no exponent
    (``reconciliation.exact_decimal_text``). ``str`` of the stored ``Decimal`` is not that text:
    a zero of NUMERIC(38,18) reads ``0E-18``, which the response model refuses — so every batch
    with a line that reconciles answered 500."""
    return reconciliation.exact_decimal_text(Fraction(value))


def reconciliation_line_out(
    row: Mapping[str, Any], exception_numbers: Mapping[UUID, str]
) -> MigrationReconciliationLineOut:
    """One T-MIG-03 line (``GET /migrations/{id}/reconciliation-lines``; RPT-41 columns)."""
    exception_id = row.get("exception_item_id")
    return MigrationReconciliationLineOut(
        id=UUID(str(row["id"])),
        contract_external_id=str(row["contract_external_id"]),
        obligation_key=row.get("obligation_key"),
        measure=row["measure"],
        source_value=_exact(row["source_value"]),
        erev_value=_exact(row["erev_value"]),
        difference=_exact(row["difference"]),
        tolerance=_exact(row["tolerance"]),
        is_within_tolerance=bool(row["is_within_tolerance"]),
        deviation_ref=row.get("deviation_ref"),
        exception_item_id=None if exception_id is None else UUID(str(exception_id)),
        exception_no=(
            None if exception_id is None else exception_numbers.get(UUID(str(exception_id)))
        ),
    )


def legacy_row_out(row: Mapping[str, Any]) -> MigratedLegacyRowOut:
    """One T-MIG-02 row (``GET /migrations/{id}/legacy-rows``): the 71 legacy columns as stored."""
    return MigratedLegacyRowOut(
        id=UUID(str(row["id"])),
        source_rowid=int(row["source_rowid"]),
        contract_external_id=str(row["contract_external_id"]),
        obligation_key=str(row["obligation_key"]),
        product_code=str(row["product_code"]),
        current_period=row.get("current_period"),
        processing_time_log=str(row["processing_time_log"]),
        record_unique_id=str(row["record_unique_id"]),
        legacy_row=dict(row["legacy_row"]),
        legacy_row_sha256=str(row["legacy_row_sha256"]).strip(),
        contract_id=row.get("contract_id"),
        obligation_id=row.get("obligation_id"),
        label=row["label"],
    )


def legacy_rows_cursor(rows: Sequence[Mapping[str, Any]], *, limit: int) -> str | None:
    """The ``next_cursor`` of a legacy-rows page: the last ``source_rowid`` when the page is full
    (the next page starts after it; DG-LST), else None."""
    if len(rows) < limit:
        return None
    return str(int(rows[-1]["source_rowid"]))
