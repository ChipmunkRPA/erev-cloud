"""Atomic evidence dependencies for catalogue REPORT_RUN jobs.

Public registration remains a separate framework gate. This module creates the source pack
inside the report command transaction and retains its identity before queue dispatch.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.session import of_session_tenant
from erev_api.db.tables import evidence_pack, job, legal_entity, report_run
from erev_api.domain.reports import (
    evidence_catalogue,
    evidence_commands,
    evidence_sample_commands,
    evidence_sample_sources,
    evidence_sources,
)
from erev_api.domain.reports.builders import ADAPTER, SourceBinding
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn, ContractSamplePackCreateIn
from erev_api.uow import UnitOfWork

CODES = frozenset({"period_evidence_pack", "contract_sample_pack"})
KEY = "catalogue_evidence"


def source(run: Mapping[str, Any]) -> evidence_catalogue.CatalogueEvidence:
    """Validate the entire report/source identity without authorizing a public read."""
    try:
        binding = SourceBinding.from_stored(run["source_binding"])
        if binding is None or binding.strategy != ADAPTER or binding.report_version != 1:
            raise ValueError("source contract")
        bound = evidence_catalogue.CatalogueEvidence.model_validate(binding.evidence[KEY])
        if (
            run["report_version"] != 1
            or bound.tenant_id != run["tenant_id"]
            or bound.report_code != run["report_code"]
            or bound.output_format != run["output_format"]
            or set(bound.entity_ids) != set(run["entity_ids"])
            or bound.known_at != run["known_at"]
            or binding.cutoff != bound.known_at
        ):
            raise ValueError("report identity")
        params = run["parameters"]
        if binding.evidence.get("catalogue_parameters") != params:
            raise ValueError("bound parameters")
        if isinstance(bound.request, ClosePackCreateIn):
            if (
                run["period_lock_id"] != bound.request.period_lock_id
                or params.get("period_lock_id") != str(bound.request.period_lock_id)
                or params.get("entity_codes") != [bound.request.entity_code]
                or params.get("book") != bound.request.book
                or run["book_code"] != bound.request.book
                or params.get("period_key") != bound.request.period_key
            ):
                raise ValueError("close selectors")
        elif (
            run["period_lock_id"] is not None
            or params.get("contract_external_ids") != bound.request.contract_external_ids
            or params.get("as_of") != bound.request.as_of.isoformat()
            or run["as_of_date"] != bound.request.as_of
        ):
            raise ValueError("sample selectors")
        return bound
    except (ValueError, KeyError, TypeError) as error:
        raise Problem(
            "validation-failed", "The catalogue report has inconsistent evidence sources."
        ) from error


def prepare(uow: UnitOfWork, run: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare immutable report fields before INSERT, atomically with source creation."""
    if (
        uow.principal.kind != PrincipalKind.USER
        or run["report_code"] not in CODES
        or run["report_version"] != 1
        or run["status"] != "QUEUED"
        or (run["created_by"], run["created_by_kind"]) != (uow.principal.id, "USER")
    ):
        raise Problem("invalid-transition", "Only the requesting user can attach queued evidence.")
    if run["source_binding"] is not None:
        bound = source(run)
        evidence_catalogue.authorize(uow, bound)
        return {key: run[key] for key in ("source_binding", "entity_ids", "parameters")}
    request: ClosePackCreateIn | ContractSamplePackCreateIn
    entities: tuple[UUID, ...]
    params = dict(run["parameters"])
    if run["report_code"] == "period_evidence_pack":
        request = ClosePackCreateIn.model_validate(
            {
                "kind": "CLOSE",
                "entity_code": params["entity_codes"][0],
                "book": params["book"],
                "period_key": params["period_key"],
                "period_lock_id": params["period_lock_id"],
            }
        )
        pack_id, _ = evidence_commands.create_close(uow, request)
        close = evidence_sources.load_close(uow, pack_id)
        entities = (close.entity_id,)
    else:
        if run["known_at"] != uow.now:
            raise Problem(
                "validation-failed",
                "New sample evidence requires the creation cutoff; "
                "reruns preserve their original cutoff.",
            )
        sample_request = ContractSamplePackCreateIn.model_validate(
            {
                "kind": "CONTRACT_SAMPLE",
                "contract_external_ids": params["contract_external_ids"],
                "as_of": params["as_of"],
            }
        )
        pack_id, _ = evidence_sample_commands.create(uow, sample_request)
        sample = evidence_sample_sources.load(uow, pack_id)
        entities = sample.scope.source_entity_ids
        request = sample_request
    if not set(entities) <= set(run["entity_ids"]):
        raise Problem(
            "validation-failed",
            "The complete evidence source extends beyond the requested report entities.",
        )
    bound = evidence_catalogue.bind(
        uow,
        pack_id,
        request=request,
        entity_ids=entities,
        known_at=run["known_at"],
        output_format=run["output_format"],
    )
    params["entity_codes"] = list(
        uow.session.scalars(
            select(legal_entity.c.code)
            .where(legal_entity.c.tenant_id == bound.tenant_id, legal_entity.c.id.in_(entities))
            .order_by(legal_entity.c.code)
        )
    )
    binding = SourceBinding(
        cutoff=bound.known_at,
        versions={},
        labels={},
        row_keys=frozenset(),
        strategy=ADAPTER,
        report_version=1,
        evidence={KEY: bound.model_dump(mode="json"), "catalogue_parameters": params},
    ).to_stored()
    values = {"source_binding": binding, "entity_ids": list(entities), "parameters": params}
    source({**run, **values})
    return values


def ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
    """Wait for the exact source job without consuming a report execution attempt."""
    row = (
        session.execute(
            select(report_run).where(
                of_session_tenant(report_run),
                report_run.c.id == UUID(str(params["report_run_id"])),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["report_code"] not in CODES:
        return True
    if row["job_id"] != job_id:
        raise Problem("invalid-transition", "The catalogue report job identity differs.")
    if row["status"] in {"SUCCEEDED", "FAILED"}:
        return True
    bound = source(dict(row))
    pack = (
        session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == bound.tenant_id,
                evidence_pack.c.id == bound.pack_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    child = (
        session.execute(
            select(job).where(
                job.c.tenant_id == bound.tenant_id,
                job.c.id == bound.job_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        pack is None
        or child is None
        or (
            pack["job_id"] != bound.job_id
            or pack["kind"] != bound.request.kind
            or sha256_hex(pack["source_binding"]) != bound.source_binding_sha256
            or (child["kind"], child["subject_type"], child["subject_id"])
            != ("EVIDENCE_PACK", "evidence_pack", bound.pack_id)
            or child["params"].get("evidence_pack_id") != str(bound.pack_id)
            or pack["status"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}
            or child["state"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}
        )
    ):
        raise Problem("invalid-transition", "The bound evidence dependency failed or changed.")
    if child["state"] == "SUCCEEDED" and pack["status"] != "SUCCEEDED":
        raise Problem("invalid-transition", "Completed evidence job has no completed pack.")
    return bool(child["state"] == pack["status"] == "SUCCEEDED")
