"""RPT-45 contract headers and code labels from database-captured source revisions."""

import json
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.db.tables import report_source_revision as revision
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_contracts"
EVIDENCE: Final = "extract_contracts_v1"
COMMIT_EVIDENCE: Final = "extract_contracts_commit_visibility_v1"
# Frozen v1 columns; schema evolution requires an explicit dataset version change.
COLUMNS: Final = (
    Column("id", "id", "text"),
    Column("contract_no", "contract_no", "text"),
    Column("external_id", "external_id", "text"),
    Column("customer_id", "customer_id", "text"),
    Column("contracting_entity_id", "contracting_entity_id", "text"),
    Column("transaction_currency", "transaction_currency", "text"),
    Column("inception_date", "inception_date", "date"),
    Column("status", "status", "text"),
    Column("combination_group_id", "combination_group_id", "text"),
    Column("head_stream_version", "head_stream_version", "integer"),
    Column("latest_computation_id", "latest_computation_id", "text"),
    Column("signature_date", "signature_date", "date"),
    Column("document_ref", "document_ref", "text"),
    Column("payment_terms", "payment_terms", "text"),
    Column("termination_party", "termination_party", "text"),
    Column("termination_has_penalty", "termination_has_penalty", "boolean"),
    Column("termination_notice_days", "termination_notice_days", "integer"),
    Column("has_commercial_substance", "has_commercial_substance", "boolean"),
    Column("region", "region", "text"),
    Column("channel", "channel", "text"),
    Column("contract_type", "contract_type", "text"),
    Column("memo_1", "memo_1", "text"),
    Column("memo_2", "memo_2", "text"),
    Column("memo_3", "memo_3", "text"),
    Column("custom_attributes", "custom_attributes", "text"),
    Column("activation_checklist", "activation_checklist", "text"),
    Column("activated_at", "activated_at", "timestamp"),
    Column("completed_at", "completed_at", "timestamp"),
    Column("terminated_at", "terminated_at", "timestamp"),
    Column("voided_at", "voided_at", "timestamp"),
    Column("renewal_of_contract_id", "renewal_of_contract_id", "text"),
    Column("portfolio_id", "portfolio_id", "text"),
    Column("scope_605_35", "scope_605_35", "boolean"),
    Column("source_system", "source_system", "text"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "text"),
    Column("created_by_kind", "created_by_kind", "text"),
    Column("updated_at", "updated_at", "timestamp"),
    Column("updated_by", "updated_by", "text"),
    Column("updated_by_kind", "updated_by_kind", "text"),
    Column("row_version", "row_version", "integer"),
    Column("acceptance_clause", "acceptance_clause", "boolean"),
    Column("side_letter", "side_letter", "boolean"),
    Column("customer_code", "customer_code", "text"),
    Column("contracting_entity_code", "contracting_entity_code", "text"),
)


def _latest(
    uow: UnitOfWork, kind: str, cutoff: datetime, ids: list[UUID]
) -> dict[str, dict[str, Any]]:
    query = (
        select(
            revision,
            func.erev.source_commit_time("report_source_revision", revision.c.id).label(
                "_committed_server_at"
            ),
        )
        .where(
            revision.c.tenant_id == uow.principal.tenant_id,
            revision.c.source_kind == kind,
            revision.c.source_id.in_(ids),
            revision.c.recorded_at <= cutoff,
            func.erev.source_commit_time("report_source_revision", revision.c.id) <= cutoff,
        )
        .distinct(revision.c.source_id)
        .order_by(revision.c.source_id, revision.c.revision_no.desc())
    )
    return {str(r["source_id"]): dict(r) for r in uow.session.execute(query).mappings()}


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_contracts has no lock dataset.")
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    mode = params.parameters.get("mode", "FULL")
    since = instant(params, "known_since")
    if mode not in {"FULL", "INCREMENTAL"}:
        raise tie_outs.invalid("mode", "Choose Full or Incremental.")
    if mode == "INCREMENTAL" and (since is None or since >= cutoff):
        raise tie_outs.invalid("known_since", "Enter a time before the source time.")
    commit_visibility = params.binding is None or COMMIT_EVIDENCE in params.binding.evidence
    if commit_visibility:
        tie_outs.record_evidence(params, COMMIT_EVIDENCE, True)
    if params.binding is None:
        # First revisions distinguish a genuinely later creation from an imported baseline
        # whose earlier header is unknown. Never silently omit an uncovered old contract.
        first = (
            uow.session.execute(
                select(
                    revision,
                    func.erev.source_commit_time("report_source_revision", revision.c.id).label(
                        "_committed_server_at"
                    ),
                ).where(
                    revision.c.tenant_id == uow.principal.tenant_id,
                    revision.c.source_kind == "contract",
                    revision.c.entity_id.in_(params.entity_ids),
                    revision.c.revision_no == 1,
                )
            )
            .mappings()
            .all()
        )
        ids = []
        for initial in first:
            if initial["_committed_server_at"] is None or initial["_committed_server_at"] > cutoff:
                if initial["is_baseline"] and (
                    datetime.fromisoformat(initial["document"]["created_at"]) <= cutoff
                ):
                    raise Problem(
                        "invalid-transition", "Contract history does not cover source time."
                    )
                continue
            ids.append(initial["source_id"])
        headers = _latest(uow, "contract", cutoff, ids)
        selected = list(headers.values())
        customers = _latest(
            uow, "customer_code", cutoff, [UUID(r["document"]["customer_id"]) for r in selected]
        )
        entities = _latest(
            uow,
            "entity_code",
            cutoff,
            [UUID(r["document"]["contracting_entity_id"]) for r in selected],
        )
        records = []
        for item in selected:
            doc = item["document"]
            customer = customers.get(doc["customer_id"])
            entity = entities.get(doc["contracting_entity_id"])
            if customer is None or entity is None:
                raise Problem(
                    "invalid-transition", "Contract label history does not cover source time."
                )
            committed = max(
                item["_committed_server_at"],
                customer["_committed_server_at"],
                entity["_committed_server_at"],
            )
            if mode == "INCREMENTAL" and since is not None and committed <= since:
                continue
            records.append(
                json.loads(
                    canonical_bytes(
                        redact_contacts(
                            {
                                **doc,
                                "customer_code": customer["document"]["code"],
                                "contracting_entity_code": entity["document"]["code"],
                                "_revision_at": item["recorded_at"],
                                "_committed_server_at": committed,
                            }
                        )
                    )
                )
            )
        tie_outs.record_evidence(params, EVIDENCE, records)
    else:
        records = tie_outs.bound_evidence(params, EVIDENCE)
    scope = {str(entity) for entity in params.entity_ids}
    rows: list[dict[str, Any]] = []
    for record in records:
        if record["contracting_entity_id"] not in scope:
            raise Problem("forbidden", "Retained contract exceeds report entity scope.")
        row = {col.key: record[col.key] for col in COLUMNS}
        for col in COLUMNS:
            if row[col.key] is None:
                continue
            if col.kind == "timestamp":
                row[col.key] = datetime.fromisoformat(row[col.key])
            elif col.kind == "date":
                row[col.key] = date.fromisoformat(row[col.key])
        window_stamp = row["created_at"]
        if commit_visibility:
            if not record.get("_committed_server_at"):
                raise Problem("invalid-transition", "Retained contract commit evidence is missing.")
            window_stamp = datetime.fromisoformat(record["_committed_server_at"])
        if (
            window_stamp > cutoff
            or datetime.fromisoformat(record["_revision_at"]) > cutoff
            or (mode == "INCREMENTAL" and since is not None and window_stamp <= since)
        ):
            raise Problem("invalid-transition", "Retained contract lies outside extract window.")
        for key in ("custom_attributes", "activation_checklist"):
            if row[key] is not None:
                row[key] = canonical_bytes(redact_contacts(row[key])).decode()
        row["row_key"] = f"contract:{row['id']}"
        rows.append(row)
    rows.sort(key=lambda row: (row["external_id"], row["id"]))
    return ReportData(COLUMNS, tuple(rows), {"row_count": len(rows)})
