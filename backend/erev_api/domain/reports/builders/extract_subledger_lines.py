"""RPT-49 sealed subledger lines at an explicit source cutoff, scoped by line entity."""

import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.db.tables import contract, gl_account, period, subledger_line, subledger_posting_seal
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_subledger_lines"
EVIDENCE: Final = "extract_subledger_lines_v1"
COMMIT_EVIDENCE: Final = "extract_subledger_commit_visibility_v1"
# Frozen v1 columns: future schema changes must explicitly version the export contract.
COLUMNS: Final = (
    Column("period_end_date", "period_end_date", "date"),
    Column("id", "id", "text"),
    Column("subledger_posting_id", "subledger_posting_id", "text"),
    Column("book_code", "book_code", "text"),
    Column("entity_id", "entity_id", "text"),
    Column("period_id", "period_id", "text"),
    Column("origin_period_id", "origin_period_id", "text"),
    Column("is_post_reopen", "is_post_reopen", "boolean"),
    Column("effective_date", "effective_date", "date"),
    Column("recorded_at", "recorded_at", "timestamp"),
    Column("entry_no", "entry_no", "integer"),
    Column("entry_kind", "entry_kind", "text"),
    Column("account_role", "account_role", "text"),
    Column("clearing_purpose", "clearing_purpose", "text"),
    Column("gl_account_id", "gl_account_id", "text"),
    Column("dimensions", "dimensions", "text"),
    Column("dimension_set_sha256", "dimension_set_sha256", "text"),
    Column("txn_currency", "txn_currency", "text"),
    Column("amount_txn", "amount_txn", "decimal"),
    Column("functional_currency", "functional_currency", "text"),
    Column("amount_functional", "amount_functional", "decimal"),
    Column("dr_cr", "dr_cr", "text"),
    Column("fx_rate_set_version_id", "fx_rate_set_version_id", "text"),
    Column("fx_rate_id", "fx_rate_id", "text"),
    Column("fx_rate", "fx_rate", "decimal"),
    Column("fx_layer_key", "fx_layer_key", "text"),
    Column("contract_id", "contract_id", "text"),
    Column("obligation_id", "obligation_id", "text"),
    Column("contract_version_id", "contract_version_id", "text"),
    Column("contract_event_id", "contract_event_id", "text"),
    Column("schedule_line_id", "schedule_line_id", "text"),
    Column("schedule_period_end_date", "schedule_period_end_date", "date"),
    Column("contract_cost_asset_id", "contract_cost_asset_id", "text"),
    Column("counterparty_entity_id", "counterparty_entity_id", "text"),
    Column("reverses_line_id", "reverses_line_id", "text"),
    Column("reverses_period_end_date", "reverses_period_end_date", "date"),
    Column("reason_code", "reason_code", "text"),
    Column("legacy_key", "legacy_key", "text"),
    Column("calc_trace_id", "calc_trace_id", "text"),
    Column("trace_node_id", "trace_node_id", "text"),
    Column("description", "description", "text"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "text"),
    Column("created_by_kind", "created_by_kind", "text"),
    Column("subject_key", "subject_key", "text"),
    Column("recorded_server_at", "recorded_server_at", "timestamp"),
    Column("contract_external_id", "contract_external_id", "text"),
    Column("period_key", "period_key", "text"),
    Column("origin_period_key", "origin_period_key", "text"),
    Column("gl_account_code", "gl_account_code", "text"),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_subledger_lines has no lock dataset.")
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
    commit_visibility = params.binding is None or COMMIT_EVIDENCE in params.binding.evidence
    if commit_visibility:
        tie_outs.record_evidence(params, COMMIT_EVIDENCE, True)
    if params.binding is None:
        committed = func.erev.subledger_commit_time(subledger_line.c.subledger_posting_id)
        tenant = uow.principal.tenant_id
        origin = period.alias("origin_period")
        query = (
            select(
                *(subledger_line.c[col.key] for col in COLUMNS[:-4]),
                contract.c.external_id.label("contract_external_id"),
                period.c.period_key,
                origin.c.period_key.label("origin_period_key"),
                gl_account.c.code.label("gl_account_code"),
                subledger_posting_seal.c.sealed_server_at.label("_sealed_server_at"),
                committed.label("_committed_server_at"),
            )
            .select_from(subledger_line)
            .join(
                contract,
                (contract.c.tenant_id == subledger_line.c.tenant_id)
                & (contract.c.id == subledger_line.c.contract_id),
            )
            .join(
                period,
                (period.c.tenant_id == subledger_line.c.tenant_id)
                & (period.c.id == subledger_line.c.period_id),
            )
            .outerjoin(
                origin,
                (origin.c.tenant_id == subledger_line.c.tenant_id)
                & (origin.c.id == subledger_line.c.origin_period_id),
            )
            .join(
                gl_account,
                (gl_account.c.tenant_id == subledger_line.c.tenant_id)
                & (gl_account.c.id == subledger_line.c.gl_account_id),
            )
            .join(
                subledger_posting_seal,
                (subledger_posting_seal.c.tenant_id == subledger_line.c.tenant_id)
                & (
                    subledger_posting_seal.c.subledger_posting_id
                    == subledger_line.c.subledger_posting_id
                )
                & (subledger_posting_seal.c.book_code == subledger_line.c.book_code),
            )
            .where(
                subledger_line.c.tenant_id == tenant,
                subledger_line.c.book_code == params.book_code,
                subledger_line.c.entity_id.in_(params.entity_ids),
                subledger_line.c.recorded_at <= cutoff,
                subledger_line.c.recorded_server_at <= cutoff,
                subledger_posting_seal.c.sealed_server_at <= cutoff,
                committed <= cutoff,
            )
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
    sums: dict[str, dict[str, Decimal]] = {}
    grouped: dict[tuple[str, str, str, str], Decimal] = {}
    for record in records:
        if record["entity_id"] not in scope:
            raise Problem(
                "forbidden", "The retained subledger line exceeds the report entity scope."
            )
        row = {col.key: record[col.key] for col in COLUMNS}
        for col in COLUMNS:
            if row[col.key] is None:
                continue
            if col.kind == "timestamp":
                row[col.key] = datetime.fromisoformat(row[col.key])
            elif col.kind == "date":
                row[col.key] = date.fromisoformat(row[col.key])
            elif col.kind == "decimal":
                row[col.key] = str(row[col.key])
        window_stamp = row["recorded_at"]
        if commit_visibility:
            if not record.get("_committed_server_at"):
                raise Problem(
                    "invalid-transition", "Retained subledger commit evidence is missing."
                )
            window_stamp = datetime.fromisoformat(record["_committed_server_at"])
        if (
            window_stamp > cutoff
            or row["book_code"] != params.book_code
            or row["recorded_at"] > cutoff
            or row["recorded_server_at"] > cutoff
            or datetime.fromisoformat(record["_sealed_server_at"]) > cutoff
            or (mode == "INCREMENTAL" and since is not None and window_stamp <= since)
        ):
            raise Problem(
                "invalid-transition", "Retained subledger line lies outside the extract window."
            )
        row["dimensions"] = canonical_bytes(redact_contacts(row["dimensions"])).decode()
        row["row_key"] = f"subledger_line:{row['period_end_date'].isoformat()}:{row['id']}"
        amounts = sums.setdefault(row["functional_currency"], {"amount_functional": Decimal(0)})
        group = (row["entity_id"], row["book_code"], row["functional_currency"], row["period_id"])
        with localcontext() as context:
            context.prec = 80
            grouped[group] = grouped.get(group, Decimal(0)) + Decimal(row["amount_functional"])
        with localcontext() as context:
            context.prec = 80
            for key in amounts:
                amounts[key] += Decimal(row[key])
        rows.append(row)
    rows.sort(key=lambda row: (row["contract_external_id"], row["period_end_date"], row["id"]))
    return ReportData(
        COLUMNS,
        tuple(rows),
        {
            "row_count": len(rows),
            "by_entity_book_currency_period": [
                {
                    "entity_id": key[0],
                    "book_code": key[1],
                    "functional_currency": key[2],
                    "period_id": key[3],
                    "amount_functional": str(amount),
                }
                for key, amount in sorted(grouped.items())
            ],
            "by_currency": {
                currency: {key: str(value) for key, value in amounts.items()}
                for currency, amounts in sorted(sums.items())
            },
        },
    )
