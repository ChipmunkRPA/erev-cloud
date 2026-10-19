"""RPT-50 journal lines excluding runs cancelled as of the source cutoff."""

import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import journal_batch, journal_entry, journal_line, journal_run, period
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, je_population
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_journal_lines"
EVIDENCE: Final = "extract_journal_lines_v1"
# Frozen v1 columns: future schema changes must explicitly version the export contract.
COLUMNS: Final = (
    Column("id", "id", "text"),
    Column("journal_entry_id", "journal_entry_id", "text"),
    Column("journal_batch_id", "journal_batch_id", "text"),
    Column("line_no", "line_no", "integer"),
    Column("entity_id", "entity_id", "text"),
    Column("book_code", "book_code", "text"),
    Column("period_id", "period_id", "text"),
    Column("account_role", "account_role", "text"),
    Column("gl_account_id", "gl_account_id", "text"),
    Column("gl_account_code", "gl_account_code", "text"),
    Column("dimensions", "dimensions", "text"),
    Column("dimension_set_sha256", "dimension_set_sha256", "text"),
    Column("txn_currency", "txn_currency", "text"),
    Column("debit_txn", "debit_txn", "decimal"),
    Column("credit_txn", "credit_txn", "decimal"),
    Column("functional_currency", "functional_currency", "text"),
    Column("debit_functional", "debit_functional", "decimal"),
    Column("credit_functional", "credit_functional", "decimal"),
    Column("contract_id", "contract_id", "text"),
    Column("obligation_id", "obligation_id", "text"),
    Column("legacy_key", "legacy_key", "text"),
    Column("counterparty_entity_id", "counterparty_entity_id", "text"),
    Column("origin_period_id", "origin_period_id", "text"),
    Column("fx_rate_set_version_ids", "fx_rate_set_version_ids", "text"),
    Column("fx_rate_ids", "fx_rate_ids", "text"),
    Column("memo", "memo", "text"),
    Column("source_line_count", "source_line_count", "integer"),
    Column("source_grouping_sha256", "source_grouping_sha256", "text"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "text"),
    Column("created_by_kind", "created_by_kind", "text"),
    Column("je_no", "je_no", "text"),
    Column("run_no", "run_no", "text"),
    Column("batch_external_id", "batch_external_id", "text"),
    Column("period_key", "period_key", "text"),
)
STATE_TIMES: Final = (
    "run_updated_at",
    "run_approved_at",
    "run_exported_at",
    "run_acknowledged_at",
    "run_cancelled_at",
    "batch_acknowledged_at",
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_journal_lines has no lock dataset.")
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
    if params.binding is None:
        tenant = uow.principal.tenant_id
        query = (
            select(
                *(journal_line.c[col.key] for col in COLUMNS[:-4]),
                journal_entry.c.je_no,
                journal_run.c.run_no,
                journal_batch.c.external_id.label("batch_external_id"),
                period.c.period_key,
                journal_run.c.id.label("run_id"),
                journal_run.c.state.label("run_state"),
                *(journal_run.c[key.removeprefix("run_")].label(key) for key in STATE_TIMES[:-1]),
                journal_batch.c.acknowledged_at.label("batch_acknowledged_at"),
            )
            .select_from(journal_line)
            .join(
                journal_entry,
                (journal_entry.c.tenant_id == journal_line.c.tenant_id)
                & (journal_entry.c.id == journal_line.c.journal_entry_id)
                & (journal_entry.c.journal_batch_id == journal_line.c.journal_batch_id),
            )
            .join(
                journal_batch,
                (journal_batch.c.tenant_id == journal_line.c.tenant_id)
                & (journal_batch.c.id == journal_line.c.journal_batch_id),
            )
            .join(
                journal_run,
                (journal_run.c.tenant_id == journal_batch.c.tenant_id)
                & (journal_run.c.id == journal_batch.c.journal_run_id),
            )
            .join(
                period,
                (period.c.tenant_id == journal_line.c.tenant_id)
                & (period.c.id == journal_line.c.period_id),
            )
            .where(
                journal_line.c.tenant_id == tenant,
                journal_line.c.book_code == params.book_code,
                journal_line.c.entity_id.in_(params.entity_ids),
                journal_line.c.created_at <= cutoff,
                journal_entry.c.created_at <= cutoff,
                journal_batch.c.created_at <= cutoff,
                journal_run.c.created_at <= cutoff,
            )
        )
        if mode == "INCREMENTAL":
            query = query.where(journal_line.c.created_at > since)
        found = [dict(row) for row in uow.session.execute(query).mappings()]
        histories = je_population.transition_history(
            uow.session,
            sorted({row["run_id"] for row in found}, key=str),
            {row["journal_batch_id"]: row["run_id"] for row in found},
        )
        for row in found:
            row["_transitions"] = [item._asdict() for item in histories.get(row["run_id"], ())]
        records = json.loads(canonical_bytes(redact_contacts(found)))
        tie_outs.record_evidence(params, EVIDENCE, records)
    else:
        records = tie_outs.bound_evidence(params, EVIDENCE)
    scope = {str(entity) for entity in params.entity_ids}
    rows: list[dict[str, Any]] = []
    sums: dict[str, dict[str, Decimal]] = {}
    for record in records:
        if record["entity_id"] not in scope:
            raise Problem("forbidden", "The retained journal line exceeds the report entity scope.")
        state_input = dict(record)
        for key in STATE_TIMES:
            if state_input.get(key) is not None:
                state_input[key] = datetime.fromisoformat(state_input[key])
        transitions = tuple(
            je_population.Transition(datetime.fromisoformat(item["at"]), item["seq"], item["state"])
            for item in record["_transitions"]
        )
        if je_population.state_as_of(state_input, cutoff, transitions).cancelled:
            continue
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
        if (
            row["book_code"] != params.book_code
            or row["created_at"] > cutoff
            or (mode == "INCREMENTAL" and since is not None and row["created_at"] <= since)
        ):
            raise Problem(
                "invalid-transition", "Retained journal line lies outside the extract window."
            )
        for key in ("dimensions", "fx_rate_set_version_ids", "fx_rate_ids"):
            row[key] = canonical_bytes(redact_contacts(row[key])).decode()
        row["row_key"] = f"journal_line:{row['id']}"
        amounts = sums.setdefault(
            row["functional_currency"],
            {
                "debit_functional": Decimal(0),
                "credit_functional": Decimal(0),
            },
        )
        with localcontext() as context:
            context.prec = 80
            for key in amounts:
                amounts[key] += Decimal(row[key])
        rows.append(row)
    rows.sort(key=lambda row: (row["run_no"], row["je_no"], row["line_no"], row["id"]))
    return ReportData(
        COLUMNS,
        tuple(rows),
        {
            "row_count": len(rows),
            "by_currency": {
                currency: {key: str(value) for key, value in amounts.items()}
                for currency, amounts in sorted(sums.items())
            },
        },
    )
