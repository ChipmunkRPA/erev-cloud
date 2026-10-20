"""Atomic creation of human-requested CHANGE and ACCESS packs."""

from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert

from erev_api.db import new_id
from erev_api.db.tables import evidence_pack
from erev_api.domain.platform.jobs import job_out_of
from erev_api.domain.reports import evidence_register_sources as sources
from erev_api.enums import JobKind, PrincipalKind
from erev_api.numbering import next_number
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut
from erev_api.schemas.evidence_packs import AccessPackCreateIn, ChangePackCreateIn
from erev_api.uow import UnitOfWork


def create(
    uow: UnitOfWork, request: ChangePackCreateIn | AccessPackCreateIn
) -> tuple[UUID, JobOut]:
    if (
        uow.principal.kind != PrincipalKind.USER
        or not sources.PERMISSIONS <= uow.principal.permissions
    ):
        raise Problem("forbidden")
    bound = sources.prepare(uow, request)
    identity = new_id()
    number = next_number(uow, "EVIDENCE_PACK")
    parent = uow.defer(
        JobKind.EVIDENCE_PACK,
        {"evidence_pack_id": str(identity)},
        subject_type="evidence_pack",
        subject_id=identity,
    )
    actor = uow.principal
    uow.session.execute(
        insert(evidence_pack).values(
            tenant_id=actor.tenant_id,
            id=identity,
            pack_no=number,
            status="QUEUED",
            job_id=parent["id"],
            **bound.pack_values(),
            created_at=uow.now,
            created_by=actor.id,
            created_by_kind=actor.kind.value,
            updated_at=uow.now,
            updated_by=actor.id,
            updated_by_kind=actor.kind.value,
        )
    )
    sources.retain(uow, identity, bound)
    uow.audit(
        action="evidence.create",
        object_type="evidence_pack",
        object_id=identity,
        contract_ids=[],
        after={
            "pack_no": number,
            "kind": request.kind,
            "status": "QUEUED",
            "job_id": parent["id"],
            "source_binding_sha256": sha256_hex(bound.model_dump(mode="json")),
        },
    )
    return identity, job_out_of(uow.session, parent["id"])
