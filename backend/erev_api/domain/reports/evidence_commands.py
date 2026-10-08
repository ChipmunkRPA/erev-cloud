"""Transactional creation of retained first-close packs (RPS-16).

The API/idempotency boundary owns commit. Creation selects a completed audit
verification once unless its caller supplies an explicit ID. It never verifies
in a separate transaction; all report jobs, numbering and pack state roll back
with the caller. Other pack kinds and re-lock variance remain pending.
"""

from __future__ import annotations

from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert

from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id
from erev_api.db.tables import evidence_pack
from erev_api.domain.platform.jobs import job_out_of
from erev_api.domain.reports import (
    evidence_audit,
    evidence_certification,
    evidence_journals,
    evidence_reconciliation_population,
    evidence_reconciliations,
    evidence_relock,
    evidence_selection,
    evidence_sources,
)
from erev_api.enums import JobKind
from erev_api.numbering import next_number
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.uow import UnitOfWork

PERMISSIONS = frozenset(
    {"report.run", "report.export", "audit.read", "contract.read", "evidence.export"}
)


def create_close(
    uow: UnitOfWork, request: ClosePackCreateIn, *, verification_id: UUID | None = None
) -> tuple[UUID, JobOut]:
    """Create the bound pack and its six jobs, atomically in the caller's transaction."""
    if not PERMISSIONS <= uow.principal.permissions:
        raise Problem("forbidden")
    selection = evidence_selection.resolve(uow, request)
    for entity_id in selection.entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity_id)
    if evidence_relock.collect(uow, selection):
        raise Problem(
            "validation-failed", "Re-lock packs require the variance-between-closes report."
        )
    # Authorize every retained reference as the requester before a SYSTEM worker is queued.
    # These collectors also refuse unprovable approval/journal/reconciliation evidence early.
    evidence_certification.collect(uow, selection)
    evidence_journals.collect(uow, selection)
    evidence_reconciliations.collect(uow, selection)
    evidence_reconciliation_population.collect(uow, selection)
    if verification_id is None:
        verification_id = evidence_audit.select_completed(uow, selection)
    bound = evidence_sources.prepare_close(uow, request, verification_id=verification_id)
    pack_id = new_id()
    pack_no = next_number(uow, "EVIDENCE_PACK")
    parent = uow.defer(
        JobKind.EVIDENCE_PACK,
        {"evidence_pack_id": str(pack_id)},
        subject_type="evidence_pack",
        subject_id=pack_id,
    )
    principal = uow.principal
    uow.session.execute(
        insert(evidence_pack).values(
            tenant_id=principal.tenant_id,
            id=pack_id,
            pack_no=pack_no,
            status="QUEUED",
            job_id=parent["id"],
            **bound.pack_values(),
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action="evidence.create",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=[],
        after={
            "pack_no": pack_no,
            "kind": "CLOSE",
            "status": "QUEUED",
            "entity_id": bound.entity_id,
            "period_id": bound.period_id,
            "book_code": request.book.value,
            "period_lock_id": request.period_lock_id,
            "job_id": parent["id"],
            "audit_verification_id": verification_id,
            "report_run_ids": bound.pack_values()["report_run_ids"],
            "source_binding_sha256": sha256_hex(bound.model_dump(mode="json")),
        },
    )
    return pack_id, job_out_of(uow.session, parent["id"])
