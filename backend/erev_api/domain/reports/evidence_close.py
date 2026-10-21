"""The frozen-source portion of an RPS-16 CLOSE pack, not a complete pack builder.

Read all twelve E-64 datasets through the existing as-locked reader. Verify their
aggregate manifest against the lock, then export CSV through the declared-column
formula guard. Source hashes and delivered hashes are distinct when escaping changes
bytes. No live report builder or fallback may supply a missing frozen dataset.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import lock_snapshot, period_lock
from erev_api.domain.close.snapshots import DatasetFile, manifest_of
from erev_api.domain.reports import locked, snapshot_views, snapshots
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection, resolve
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.uow import UnitOfWork

# T-RPT-04: use its specified prefixes where a frozen source exists. Other required
# evidence (batch register, reconciliations, access, audit, relock, etc.) is collected
# separately. These additional frozen reports retain their own catalogue names.
PATHS: Final = {
    "je_population": "journals/je_population.csv",
    "out_of_period_register": "registers/out_of_period.csv",
    "modification_register": "registers/modification_register.csv",
    "manual_adjustment_register": "registers/manual_adjustment_register.csv",
}


@dataclass(frozen=True, slots=True)
class FrozenReport:
    report_code: str
    snapshot_id: UUID
    report_run_id: UUID | None
    dataset: locked.LockedDataset


@dataclass(frozen=True, slots=True)
class FrozenClose:
    scope: locked.LockScope
    record: Mapping[str, Any]
    reports: tuple[FrozenReport, ...]


def read_locked(uow: UnitOfWork, selection: SourceSelection) -> FrozenClose:
    """Read and verify the complete frozen source, also used by re-lock verification.

    Recheck permissions and the selected lock in this transaction before opening any
    files. The job integration must use an explicitly scoped reader; SYSTEM is not a
    substitute for authorization. A later reopen never substitutes a newer lock.
    """
    scope = selection.lock
    if scope is None or selection.tenant_id != uow.principal.tenant_id or selection.contract_ids:
        raise Problem("validation-failed", "A CLOSE source selection is required.")
    checked = resolve(
        uow,
        ClosePackCreateIn.model_validate(
            {
                "kind": "CLOSE",
                "entity_code": scope.entity_code,
                "book": scope.book_code,
                "period_key": scope.period_key,
                "period_lock_id": scope.lock_id,
            }
        ),
    )
    if (
        checked.lock != scope
        or checked.entity_ids != selection.entity_ids
        or checked.lock_known_at != selection.lock_known_at
    ):
        raise Problem("validation-failed", "The stored CLOSE selection differs from its lock.")
    return _read_frozen(uow, scope)


def read_for_report(uow: UnitOfWork, lock_id: UUID) -> FrozenClose:
    """Verified frozen figures under report.run; no audit/access evidence is exposed.

    Pack collection still uses read_locked and its additional audit.read check.
    Workers must provide the actual authorized requester, not SYSTEM.
    """
    principal = uow.principal
    grant = principal.permission_scopes.get("report.run")
    if "report.run" not in principal.permissions or not grant:
        raise Problem("forbidden")
    scope = locked.lock_scope(uow.session, lock_id)
    if scope is None or (grant != "*" and scope.entity_id not in grant):
        raise Problem("not-found")
    refusal = locked.froze_nothing(uow.session, scope)
    if refusal is not None:
        raise Problem("validation-failed", refusal)
    return _read_frozen(uow, scope)


def _read_frozen(uow: UnitOfWork, scope: locked.LockScope) -> FrozenClose:
    lock = (
        uow.session.execute(
            select(period_lock).where(
                period_lock.c.tenant_id == uow.principal.tenant_id,
                period_lock.c.id == scope.lock_id,
            )
        )
        .mappings()
        .one()
    )
    rows = (
        uow.session.execute(
            select(lock_snapshot).where(
                lock_snapshot.c.tenant_id == uow.principal.tenant_id,
                lock_snapshot.c.period_lock_id == scope.lock_id,
            )
        )
        .mappings()
        .all()
    )
    datasets = [
        DatasetFile(
            kind=str(row["snapshot_kind"]),
            file_id=row["file_id"],
            file_sha256=row["file_sha256"],
            row_count=row["row_count"],
            control_totals=dict(row["control_totals"]),
        )
        for row in rows
    ]
    try:
        manifest_hash = manifest_of(datasets, allow_legacy=True)
    except ValueError as error:
        raise Problem(
            "validation-failed", "The lock does not hold a complete supported snapshot manifest."
        ) from error
    if manifest_hash != lock["snapshot_manifest_sha256"]:
        raise Problem(
            "validation-failed", "The snapshot manifest does not match the selected lock."
        )
    by_kind = {str(row["snapshot_kind"]): row for row in rows}
    if not set(by_kind) <= set(locked.SNAPSHOT_KIND_BY_REPORT.values()):
        raise Problem("validation-failed", "A frozen snapshot has no evidence report mapping.")
    reports = []
    for report_code, kind in sorted(locked.SNAPSHOT_KIND_BY_REPORT.items()):
        if kind not in by_kind:
            continue  # A verified historical manifest need not contain a later dataset kind.
        frozen = locked.locked_dataset(uow, report_code=report_code, lock_id=scope.lock_id)
        # Require the same report row-key contract as ordinary as-locked output.
        locked.report_data(frozen)
        row = by_kind[kind]
        reports.append(FrozenReport(report_code, row["id"], row["report_run_id"], frozen))
    return FrozenClose(scope, dict(lock), tuple(reports))


def frozen_payloads(source: FrozenClose) -> tuple[PackFile, ...]:
    """Render an already verified source; source hashes remain those of the stored raw bytes."""
    files = []
    identities: list[dict[str, Any]] = []
    for report in source.reports:
        report_code, frozen = report.report_code, report.dataset
        kind = frozen.kind
        headers, rows, controls = locked.currency_rows(frozen)
        columns = snapshots.declared_kinds(kind, headers, controls or frozen.control_totals)
        content, output_hash = locked.export_csv(frozen, columns)
        path = PATHS.get(report_code, f"reports/{report_code}.csv")
        files.append(PackFile(path, content, report_run_id=report.report_run_id))
        exports = []
        if controls is not None:
            for view in snapshot_views.VIEWS:
                view_headers, view_rows, view_controls = locked.currency_rows(frozen, view)
                view_path = path if view == "transaction" else f"reports/{view}/{report_code}.csv"
                view_kinds = snapshots.declared_kinds(kind, view_headers, view_controls or {})
                view_content, view_hash = locked.export_csv(frozen, view_kinds, view)
                if view != "transaction":
                    files.append(
                        PackFile(view_path, view_content, report_run_id=report.report_run_id)
                    )
                exports.append(
                    {
                        "currency_view": view,
                        "path": view_path,
                        "export_sha256": view_hash,
                        "row_count": len(view_rows),
                        "control_totals": view_controls,
                    }
                )
        identities.append(
            {
                "snapshot_id": report.snapshot_id,
                "snapshot_kind": kind,
                "report_code": report_code,
                "report_run_id": report.report_run_id,
                "file_id": frozen.file_id,
                "file_sha256": frozen.file_sha256,
                "row_count": frozen.row_count,
                "control_totals": dict(frozen.control_totals),
                "path": path,
                "export_sha256": output_hash,
                "export_row_count": len(rows),
                **({"currency_exports": exports} if exports else {}),
            }
        )
    scope = source.scope
    identity = {
        "period_lock_id": scope.lock_id,
        "entity_id": scope.entity_id,
        "entity_code": scope.entity_code,
        "book": scope.book_code,
        "period_id": scope.period_id,
        "period_key": scope.period_key,
        "cutoff_known_at": source.record["cutoff_known_at"],
        "snapshot_manifest_sha256": source.record["snapshot_manifest_sha256"],
    }
    files.extend(
        (
            PackFile(
                "certification.json",
                canonical_bytes({**identity, "certification": source.record["certification"]}),
            ),
            PackFile("lock/snapshots.json", canonical_bytes({**identity, "snapshots": identities})),
        )
    )
    return tuple(files)


def collect_locked(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    """Return certification, snapshot identities and guarded CSVs, or refuse the whole read."""
    return frozen_payloads(read_locked(uow, selection))
