"""RPT-47: all computed versions in a book, with their actual computation membership.

A combined version contains group totals: a partial entity selection cannot export it.
Retained inputs preserve the original member identifiers and source values on rerun.
"""

import json
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import Text, cast, select

from erev_api.db.tables import contract, contract_computation, contract_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_contract_versions"
EVIDENCE: Final = "extract_contract_versions_v1"
# Explicit order freezes v1 independently of future table additions.
KEYS: Final = (
    "id",
    "combination_group_id",
    "contract_computation_id",
    "book_code",
    "version_no",
    "previous_version_id",
    "known_at",
    "cause_event_ids",
    "output_sha256",
    "calc_trace_id",
    "transaction_currency",
    "status_in_book",
    "status_reason_in_book",
    "transaction_price",
    "fixed_consideration",
    "vc_constrained_amount",
    "vc_excluded_amount",
    "expected_returns_amount",
    "consideration_payable_amount",
    "financing_adjustment_amount",
    "noncash_consideration_amount",
    "sales_tax_excluded_amount",
    "out_of_scope_amount",
    "total_ssp",
    "revenue_cum",
    "billed_cum",
    "net_position",
    "rpo_amount",
    "scheduled_amount",
    "awaiting_trigger_amount",
    "modification_boundary_no",
    "pinned_policies",
    "created_at",
    "created_by",
    "created_by_kind",
)
DECIMALS: Final = frozenset(KEYS[13:30])
JSON_FIELDS: Final = frozenset({"cause_event_ids", "pinned_policies", "contract_external_ids"})
COLUMNS: Final = tuple(
    Column(
        key,
        key,
        "decimal"
        if key in DECIMALS
        else "integer"
        if key in {"version_no", "modification_boundary_no"}
        else "timestamp"
        if key in {"known_at", "created_at"}
        else "text",
    )
    for key in (*KEYS, "contract_external_ids")
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_contract_versions has no lock dataset.")
    if params.book_code is None:
        raise tie_outs.invalid("book", "Choose a book.")
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    mode = params.parameters.get("mode", "FULL")
    since = instant(params, "known_since")
    if mode not in {"FULL", "INCREMENTAL"}:
        raise tie_outs.invalid("mode", "Choose Full or Incremental.")
    if mode == "INCREMENTAL" and (since is None or since >= cutoff):
        raise tie_outs.invalid("known_since", "Enter a time before the source time.")
    scope = {str(entity) for entity in params.entity_ids}
    if params.binding is None:
        tenant = uow.principal.tenant_id
        relevant = (
            select(contract.c.id)
            .where(
                contract.c.tenant_id == tenant,
                contract.c.contracting_entity_id.in_(params.entity_ids),
                contract_computation.c.stream_heads.has_key(cast(contract.c.id, Text)),
            )
            .correlate(contract_computation)
            .exists()
        )
        query = (
            select(
                *(contract_version.c[key] for key in KEYS),
                contract_computation.c.stream_heads,
            )
            .join(
                contract_computation,
                (
                    (contract_computation.c.tenant_id == contract_version.c.tenant_id)
                    & (contract_computation.c.id == contract_version.c.contract_computation_id)
                ),
            )
            .where(
                contract_version.c.tenant_id == tenant,
                contract_version.c.book_code == params.book_code,
                contract_version.c.known_at <= cutoff,
                contract_version.c.created_at <= cutoff,
                relevant,
            )
        )
        if mode == "INCREMENTAL":
            query = query.where(contract_version.c.created_at > since)
        found = uow.session.execute(query).mappings().all()
        member_ids = {UUID(key) for source in found for key in source["stream_heads"]}
        members_by_id = (
            {
                str(row["id"]): row
                for row in uow.session.execute(
                    select(
                        contract.c.id,
                        contract.c.external_id,
                        contract.c.contracting_entity_id,
                    ).where(contract.c.tenant_id == tenant, contract.c.id.in_(member_ids))
                ).mappings()
            }
            if member_ids
            else {}
        )
        records = []
        for source in found:
            members = tuple(source["stream_heads"])
            contracts = [members_by_id[key] for key in members if key in members_by_id]
            entities = {str(row["contracting_entity_id"]) for row in contracts}
            if len(contracts) != len(members) or not entities <= scope:
                raise Problem("forbidden", "Select every entity of the combined contract version.")
            record = {key: source[key] for key in KEYS}
            record["contract_external_ids"] = sorted(row["external_id"] for row in contracts)
            record["entity_ids"] = sorted(entities)
            records.append(json.loads(canonical_bytes(redact_contacts(record))))
        tie_outs.record_evidence(params, EVIDENCE, records)
    else:
        records = tie_outs.bound_evidence(params, EVIDENCE)
    rows: list[dict[str, Any]] = []
    for record in records:
        if not set(record["entity_ids"]) <= scope:
            raise Problem("forbidden", "The retained version exceeds the report entity scope.")
        row = {column.key: record[column.key] for column in COLUMNS}
        for key in ("known_at", "created_at"):
            row[key] = datetime.fromisoformat(row[key])
        if (
            row["book_code"] != params.book_code
            or row["known_at"] > cutoff
            or row["created_at"] > cutoff
            or (mode == "INCREMENTAL" and since is not None and row["created_at"] <= since)
        ):
            raise Problem("invalid-transition", "Retained version lies outside the extract window.")
        for key in JSON_FIELDS:
            row[key] = canonical_bytes(redact_contacts(row[key])).decode()
        for key in DECIMALS:
            row[key] = str(row[key])
        row["row_key"] = f"version:{row['id']}"
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["created_at"],
            row["combination_group_id"],
            row["version_no"],
            row["id"],
        )
    )
    return ReportData(COLUMNS, tuple(rows), {"row_count": len(rows)})
