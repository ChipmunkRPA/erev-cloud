"""The frozen-source portion of an RPS-16 CLOSE pack, not a complete pack builder.

Read all twelve E-64 datasets through the existing as-locked reader. Verify their
aggregate manifest against the lock, then export CSV through the declared-column
formula guard. Source hashes and delivered hashes are distinct when escaping changes
bytes. No live report builder or fallback may supply a missing frozen dataset.
"""

from __future__ import annotations

from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import lock_snapshot, period_lock
from erev_api.domain.close.snapshots import DatasetFile, manifest_of
from erev_api.domain.reports import locked, snapshots
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


def collect_locked(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    """Return certification, snapshot identities and guarded CSVs, or refuse the whole read.

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
    lock = (
        uow.session.execute(
            select(period_lock).where(
                period_lock.c.tenant_id == selection.tenant_id,
                period_lock.c.id == scope.lock_id,
            )
        )
        .mappings()
        .one()
    )
    rows = (
        uow.session.execute(
            select(lock_snapshot).where(
                lock_snapshot.c.tenant_id == selection.tenant_id,
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
        manifest_hash = manifest_of(datasets)
    except ValueError as error:
        raise Problem(
            "validation-failed", "The lock does not hold all twelve snapshot kinds."
        ) from error
    if manifest_hash != lock["snapshot_manifest_sha256"]:
        raise Problem(
            "validation-failed", "The snapshot manifest does not match the selected lock."
        )
    by_kind = {str(row["snapshot_kind"]): row for row in rows}
    if set(by_kind) != set(locked.SNAPSHOT_KIND_BY_REPORT.values()):
        raise Problem("validation-failed", "A frozen snapshot has no evidence report mapping.")
    files = []
    identities: list[dict[str, Any]] = []
    for report_code, kind in sorted(locked.SNAPSHOT_KIND_BY_REPORT.items()):
        frozen = locked.locked_dataset(uow, report_code=report_code, lock_id=scope.lock_id)
        # Require the same report row-key contract as ordinary as-locked output.
        locked.report_data(frozen)
        columns = snapshots.declared_kinds(kind, locked.headers_of(frozen), frozen.control_totals)
        content, output_hash = locked.export_csv(frozen, columns)
        path = PATHS.get(report_code, f"reports/{report_code}.csv")
        row = by_kind[kind]
        files.append(PackFile(path, content, report_run_id=row["report_run_id"]))
        identities.append(
            {
                "snapshot_id": row["id"],
                "snapshot_kind": kind,
                "report_code": report_code,
                "report_run_id": row["report_run_id"],
                "file_id": frozen.file_id,
                "file_sha256": frozen.file_sha256,
                "row_count": frozen.row_count,
                "control_totals": dict(frozen.control_totals),
                "path": path,
                "export_sha256": output_hash,
            }
        )
    identity = {
        "period_lock_id": scope.lock_id,
        "entity_id": scope.entity_id,
        "entity_code": scope.entity_code,
        "book": scope.book_code,
        "period_id": scope.period_id,
        "period_key": scope.period_key,
        "cutoff_known_at": selection.lock_known_at,
        "snapshot_manifest_sha256": manifest_hash,
    }
    files.extend(
        (
            PackFile(
                "certification.json",
                canonical_bytes({**identity, "certification": lock["certification"]}),
            ),
            PackFile("lock/snapshots.json", canonical_bytes({**identity, "snapshots": identities})),
        )
    )
    return tuple(files)
