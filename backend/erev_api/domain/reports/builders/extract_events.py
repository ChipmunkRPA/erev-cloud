"""RPT-52 event dataset v1: scoped, inclusive source cutoff and exclusive incremental start.

Retain redacted source records, not rendered output, for same-source rebuilds. The fixed
column list prevents a database migration from silently changing the published dataset schema.
"""

import json
from datetime import date, datetime
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.db.tables import contract_event
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_events"
EVIDENCE: Final = "extract_events_v1"
COMMIT_EVIDENCE: Final = "extract_events_commit_visibility_v1"
COLUMNS: Final = (
    Column("id", "id", "code"),
    Column("contract_id", "contract_id", "code"),
    Column("contracting_entity_id", "contracting_entity_id", "code"),
    Column("stream_version", "stream_version", "integer"),
    Column("event_type", "event_type", "code"),
    Column("schema_version", "schema_version", "integer"),
    Column("effective_date", "effective_date", "date"),
    Column("recorded_at", "recorded_at", "timestamp"),
    Column("record_seq", "record_seq", "integer"),
    Column("origin", "origin", "text"),
    Column("is_manual", "is_manual", "boolean"),
    Column("obligation_ids", "obligation_ids", "text"),
    Column("payload", "payload", "text"),
    Column("payload_sha256", "payload_sha256", "code"),
    Column("idempotency_key", "idempotency_key", "text"),
    Column("supersedes_event_id", "supersedes_event_id", "code"),
    Column("approval_request_id", "approval_request_id", "code"),
    Column("modification_id", "modification_id", "code"),
    Column("estimate_version_id", "estimate_version_id", "code"),
    Column("manual_adjustment_id", "manual_adjustment_id", "code"),
    Column("import_upload_id", "import_upload_id", "code"),
    Column("source_record_id", "source_record_id", "code"),
    Column("sync_run_id", "sync_run_id", "code"),
    Column("request_id", "request_id", "text"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "code"),
    Column("created_by_kind", "created_by_kind", "code"),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_events has no lock dataset.")
    # Extract watermarks use the requested instant, never the later worker transaction time.
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
        committed = func.erev.source_commit_time("contract_event", contract_event.c.id)
        query = select(
            *(contract_event.c[column.key] for column in COLUMNS),
            committed.label("_committed_server_at"),
        ).where(
            contract_event.c.tenant_id == uow.principal.tenant_id,
            contract_event.c.contracting_entity_id.in_(params.entity_ids),
            contract_event.c.recorded_at <= cutoff,
            committed <= cutoff,
        )
        if mode == "INCREMENTAL":
            query = query.where(committed > since)
        records = [
            json.loads(canonical_bytes(redact_contacts(dict(row))))
            for row in uow.session.execute(query).mappings()
        ]
        tie_outs.record_evidence(params, EVIDENCE, records)
    else:
        records = tie_outs.bound_evidence(params, EVIDENCE)
    scope = {str(entity) for entity in params.entity_ids}
    rows: list[dict[str, Any]] = []
    for record in records:
        if record["contracting_entity_id"] not in scope:
            raise Problem("forbidden", "The retained extract exceeds the report entity scope.")
        row = {column.key: record[column.key] for column in COLUMNS}
        for column in COLUMNS:
            if row[column.key] is None:
                continue
            if column.kind == "timestamp":
                row[column.key] = datetime.fromisoformat(row[column.key])
            elif column.kind == "date":
                row[column.key] = date.fromisoformat(row[column.key])
        window_stamp = row["recorded_at"]
        if commit_visibility:
            if not record.get("_committed_server_at"):
                raise Problem("invalid-transition", "Retained event commit evidence is missing.")
            window_stamp = datetime.fromisoformat(record["_committed_server_at"])
        if (
            row["recorded_at"] > cutoff
            or window_stamp > cutoff
            or (mode == "INCREMENTAL" and since is not None and window_stamp <= since)
        ):
            raise Problem("invalid-transition", "Retained event lies outside the extract window.")
        row["payload"] = canonical_bytes(redact_contacts(row["payload"])).decode()
        row["obligation_ids"] = canonical_bytes(row["obligation_ids"]).decode()
        row["row_key"] = f"event:{row['id']}"
        rows.append(row)
    rows.sort(key=lambda row: (row["recorded_at"], row["record_seq"], row["id"]))
    return ReportData(COLUMNS, tuple(rows), {"row_count": len(rows)})
