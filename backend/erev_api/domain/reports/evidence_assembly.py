"""Assemble a first-close evidence ZIP from retained, individually verified sources.

This is a read-only assembly boundary, not the EVIDENCE_PACK job or download API.
Re-lock assembly remains refused until the required driver-variance report exists;
the stored raw comparison alone does not meet that requirement.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.auth.dependencies import require_for_entity
from erev_api.domain.reports import (
    evidence_archive,
    evidence_audit,
    evidence_certification,
    evidence_close,
    evidence_journals,
    evidence_reconciliation_population,
    evidence_reconciliations,
    evidence_relock,
    evidence_reports,
    evidence_selection,
    evidence_sources,
    locked,
)
from erev_api.domain.reports.evidence_archive import Archive, PackFile
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

# All first-close sections of T-RPT-04. Reconciliation statements are variable in
# number; their index, population proof and signatures are checked by their readers.
REQUIRED_PATHS = frozenset(
    {
        "certification.json",
        "lock/snapshots.json",
        "lock/approvals.json",
        "lock/source_binding.json",
        "journals/batch_register.json",
        "reconciliations/index.json",
        "reconciliations/population.json",
        "audit/chain_digest.json",
        "audit/sources.json",
        *(
            evidence_close.PATHS.get(code, f"reports/{code}.csv")
            for code in locked.SNAPSHOT_KIND_BY_REPORT
        ),
        *(
            f"{prefix}.{suffix}"
            for prefix in evidence_reports.PATHS.values()
            for suffix in ("csv", "manifest.json", "source.json")
        ),
    }
)


def checked_archive(files: Sequence[PackFile], *, report_run_ids: set[UUID]) -> Archive:
    """Refuse missing sections or unbound report identities before producing any ZIP."""
    if not REQUIRED_PATHS.issubset(file.path for file in files):
        raise Problem("validation-failed", "The close pack is missing required evidence sections.")
    if {file.report_run_id for file in files if file.report_run_id is not None} != report_run_ids:
        raise Problem(
            "validation-failed", "The close pack's report population differs from its binding."
        )
    try:
        return evidence_archive.build(files)
    except evidence_archive.InvalidArchive as error:
        raise Problem(
            "validation-failed", f"The close pack cannot be assembled: {error}"
        ) from error


def assemble_close(uow: UnitOfWork, pack_id: UUID) -> Archive:
    """Reauthorize/read all retained sources; no queuing, new verification, storage or commit."""
    if "report.export" not in uow.principal.permissions:
        raise Problem("forbidden")
    bound = evidence_sources.load_close(uow, pack_id)
    require_for_entity(uow.ctx, "report.export", bound.entity_id)
    selected = evidence_selection.resolve(uow, bound.request)
    frozen = evidence_close.read_locked(uow, selected)
    if evidence_relock.collect(uow, selected):
        raise Problem(
            "validation-failed",
            "Re-lock pack assembly requires the variance-between-closes report.",
        )
    files = [
        *evidence_close.frozen_payloads(frozen),
        *evidence_certification.collect(uow, selected),
        *evidence_journals.collect(uow, selected),
        *evidence_reconciliations.collect(uow, selected),
        *evidence_reconciliation_population.collect(uow, selected),
        *evidence_audit.collect(uow, selected, verification_id=bound.audit_verification_id),
    ]
    for report in bound.supporting_reports:
        files.extend(evidence_reports.collect(uow, report.source()))
    files.append(
        PackFile("lock/source_binding.json", canonical_bytes(bound.model_dump(mode="json")))
    )
    return checked_archive(files, report_run_ids=set(bound.pack_values()["report_run_ids"]))
