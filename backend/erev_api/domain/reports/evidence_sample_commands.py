"""Create a contract sample and its retained rendering inputs in one transaction."""

from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import engine_release, evidence_pack, legal_entity
from erev_api.domain.platform.jobs import job_out_of
from erev_api.domain.reports import evidence_sample_sources, framework
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.outputs import RunStamp
from erev_api.enums import JobKind, PrincipalKind
from erev_api.numbering import next_number
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut
from erev_api.schemas.evidence_packs import ContractSamplePackCreateIn
from erev_api.uow import UnitOfWork


def create(uow: UnitOfWork, request: ContractSamplePackCreateIn) -> tuple[UUID, JobOut]:
    if uow.principal.kind != PrincipalKind.USER or not PERMISSIONS <= uow.principal.permissions:
        raise Problem("forbidden")
    bound = evidence_sample_sources.prepare(uow, request)
    pack_id = new_id()
    pack_no = next_number(uow, "EVIDENCE_PACK")
    release = (
        uow.session.execute(
            select(engine_release).where(engine_release.c.id == framework._release_id(uow.session))
        )
        .mappings()
        .one()
    )
    codes = tuple(
        uow.session.execute(
            select(legal_entity.c.code)
            .where(
                legal_entity.c.tenant_id == uow.principal.tenant_id,
                legal_entity.c.id.in_(bound.scope.source_entity_ids),
            )
            .order_by(legal_entity.c.code)
        ).scalars()
    )
    stamp = RunStamp(
        report_code="contract_sample_pack",
        report_name="Contract sample evidence pack",
        report_version=1,
        report_run_no=pack_no,
        parameters={},
        entity_codes=codes,
        book=None,
        as_of=request.as_of.isoformat(),
        source="Retained contract sample sources",
        engine_version=release["engine_version"],
        build_sha=release["build_sha"],
        run_by=str(uow.principal.id),
        run_at=uow.now,
        output_sha256=bound.manifest_sha256,
    )
    bound = bound.model_copy(update={"render_stamp": stamp})
    parent = uow.defer(
        JobKind.EVIDENCE_PACK,
        {"evidence_pack_id": str(pack_id)},
        subject_type="evidence_pack",
        subject_id=pack_id,
    )
    actor = uow.principal
    uow.session.execute(
        insert(evidence_pack).values(
            tenant_id=actor.tenant_id,
            id=pack_id,
            pack_no=pack_no,
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
    evidence_sample_sources.retain(uow, pack_id, bound)
    uow.audit(
        action="evidence.create",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=list(bound.scope.sampled_contract_ids),
        after={
            "pack_no": pack_no,
            "kind": "CONTRACT_SAMPLE",
            "status": "QUEUED",
            "job_id": parent["id"],
            "source_binding_sha256": sha256_hex(bound.model_dump(mode="json")),
        },
    )
    return pack_id, job_out_of(uow.session, parent["id"])
