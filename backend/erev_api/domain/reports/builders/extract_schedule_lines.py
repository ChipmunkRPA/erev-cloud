"""RPT-48 schedule detail from latest per-contract versions, scoped by line entity."""

import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import contract, period, schedule_line
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_schedule_lines"
EVIDENCE: Final = "extract_schedule_lines_v1"
# Frozen v1 columns: future schema changes must explicitly version the export contract.
COLUMNS: Final = (
    Column("period_end_date", "period_end_date", "date"),
    Column("id", "id", "text"),
    Column("schedule_id", "schedule_id", "text"),
    Column("contract_version_id", "contract_version_id", "text"),
    Column("contract_id", "contract_id", "text"),
    Column("book_code", "book_code", "text"),
    Column("subject_type", "subject_type", "text"),
    Column("subject_id", "subject_id", "text"),
    Column("entity_id", "entity_id", "text"),
    Column("period_id", "period_id", "text"),
    Column("line_type", "line_type", "text"),
    Column("amount", "amount", "decimal"),
    Column("cumulative_amount", "cumulative_amount", "decimal"),
    Column("cumulative_exact", "cumulative_exact", "decimal"),
    Column("quantity", "quantity", "decimal"),
    Column("currency", "currency", "text"),
    Column("is_released_at_close", "is_released_at_close", "boolean"),
    Column("trace_node_id", "trace_node_id", "text"),
    Column("created_at", "created_at", "timestamp"),
    Column("contract_external_id", "contract_external_id", "text"),
    Column("period_key", "period_key", "text"),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_schedule_lines has no lock dataset.")
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
        # Restrict candidates before choosing latest, so an after-cutoff computation cannot
        # displace an earlier version whose source event timestamp happens to be identical.
        query = (
            select(
                *(schedule_line.c[col.key] for col in COLUMNS[:-2]),
                contract.c.external_id.label("contract_external_id"),
                period.c.period_key,
            )
            .join(
                contract,
                (
                    (contract.c.tenant_id == schedule_line.c.tenant_id)
                    & (contract.c.id == schedule_line.c.contract_id)
                ),
            )
            .join(
                period,
                (period.c.tenant_id == schedule_line.c.tenant_id)
                & (period.c.id == schedule_line.c.period_id),
            )
            .where(
                schedule_line.c.tenant_id == tenant,
                schedule_line.c.book_code == params.book_code,
                schedule_line.c.entity_id.in_(params.entity_ids),
                schedule_line.c.created_at <= cutoff,
                tie_outs.read_from(
                    schedule_line.c.contract_id,
                    schedule_line.c.contract_version_id,
                    book_code=params.book_code,
                    cutoff=cutoff,
                    created_cutoff=cutoff,
                    statuses=None,
                ),
            )
        )
        if mode == "INCREMENTAL":
            query = query.where(schedule_line.c.created_at > since)
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
    for record in records:
        if record["entity_id"] not in scope:
            raise Problem(
                "forbidden", "The retained schedule line exceeds the report entity scope."
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
        if (
            row["book_code"] != params.book_code
            or row["created_at"] > cutoff
            or (mode == "INCREMENTAL" and since is not None and row["created_at"] <= since)
        ):
            raise Problem(
                "invalid-transition", "Retained schedule line lies outside the extract window."
            )
        row["row_key"] = f"schedule_line:{row['period_end_date'].isoformat()}:{row['id']}"
        amounts = sums.setdefault(row["currency"], {"amount": Decimal(0)})
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
            "by_currency": {
                currency: {key: str(value) for key, value in amounts.items()}
                for currency, amounts in sorted(sums.items())
            },
        },
    )
