"""RPS-16 stored re-lock evidence (BR-CLS-07), verified against both frozen closes.

The current lock points to a REOPEN, not directly to the LOCK compared by the stored
diff. Resolve that history within the same tenant/entity/book/period, verify both
complete frozen sources, and compare the saved canonical diff with the existing
CLO-7 comparator over those bytes. Deliver the original saved bytes, never silently
replace a missing or incorrect diff with a newly generated report.

This supplies stored close-comparison evidence. The separate
``variance_between_closes`` report and complete pack workflow remain required.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import period_lock
from erev_api.domain.close import relock_diff
from erev_api.domain.reports import evidence_close, locked
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection, resolve
from erev_api.enums import FilePurpose, LockKind
from erev_api.files.store import open_file
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.uow import UnitOfWork


def _prior(uow: UnitOfWork, current: evidence_close.FrozenClose) -> UUID | None:
    parent = current.record["previous_lock_id"]
    if parent is None:
        return None
    seen = {current.scope.lock_id}
    reopened = False
    while parent is not None and parent not in seen:
        seen.add(parent)
        row = (
            uow.session.execute(
                select(period_lock).where(
                    period_lock.c.tenant_id == uow.principal.tenant_id,
                    period_lock.c.id == parent,
                    period_lock.c.entity_id == current.scope.entity_id,
                    period_lock.c.book_code == current.scope.book_code,
                    period_lock.c.period_id == current.scope.period_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem(
                "validation-failed", "The re-lock history is incomplete or outside its scope."
            )
        if row["kind"] == LockKind.LOCK and reopened:
            return UUID(str(row["id"]))
        if row["kind"] != LockKind.REOPEN:
            break
        reopened = True
        parent = row["previous_lock_id"]
    raise Problem("validation-failed", "The re-lock history does not lead to a prior close.")


def _side(source: evidence_close.FrozenClose) -> relock_diff.LockSide:
    return relock_diff.LockSide(
        lock_id=source.scope.lock_id,
        snapshot_manifest_sha256=source.record["snapshot_manifest_sha256"],
        certification=source.record["certification"],
        datasets={
            report.dataset.kind: relock_diff.DatasetSide(
                kind=report.dataset.kind,
                file_sha256=report.dataset.file_sha256,
                row_count=report.dataset.row_count,
                content=report.dataset.content,
            )
            for report in source.reports
        },
    )


def collect(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    """Original stored diff and its bound lock/file identities; empty for a genuine first lock."""
    current = evidence_close.read_locked(uow, selection)
    prior_id = _prior(uow, current)
    file_id = current.record["diff_report_file_id"]
    if prior_id is None:
        if file_id is not None:
            raise Problem("validation-failed", "A first close unexpectedly names a re-lock diff.")
        return ()
    if file_id is None:
        raise Problem("validation-failed", "The re-lock has no stored comparison file.")
    scope = locked.lock_scope(uow.session, prior_id)
    if scope is None:
        raise Problem("not-found")
    previous = evidence_close.read_locked(
        uow,
        resolve(
            uow,
            ClosePackCreateIn.model_validate(
                {
                    "kind": "CLOSE",
                    "entity_code": scope.entity_code,
                    "book": scope.book_code,
                    "period_key": scope.period_key,
                    "period_lock_id": prior_id,
                }
            ),
        ),
    )
    row, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read()
    if (
        row["purpose"] != FilePurpose.REPORT_OUTPUT
        or row["media_type"] != relock_diff.MEDIA_TYPE
        or len(content) != row["size_bytes"]
        or hashlib.sha256(content).hexdigest() != row["sha256"]
    ):
        raise Problem(
            "validation-failed", "The stored re-lock comparison file failed verification."
        )
    try:
        expected = relock_diff.encode(relock_diff.diff(_side(previous), _side(current)))
    except relock_diff.RelockDiffRefusal as error:
        raise Problem("validation-failed", "The frozen closes cannot be compared.") from error
    if content != expected:
        raise Problem(
            "validation-failed", "The stored re-lock comparison differs from its frozen sources."
        )
    return (
        PackFile("relock/stored_comparison.json", content),
        PackFile(
            "relock/sources.json",
            canonical_bytes(
                {
                    "previous_lock_id": prior_id,
                    "period_lock_id": current.scope.lock_id,
                    "previous_snapshot_manifest_sha256": previous.record[
                        "snapshot_manifest_sha256"
                    ],
                    "snapshot_manifest_sha256": current.record["snapshot_manifest_sha256"],
                    "diff_report_file_id": file_id,
                    "diff_report_sha256": row["sha256"],
                    "format": relock_diff.FORMAT,
                }
            ),
        ),
    )
