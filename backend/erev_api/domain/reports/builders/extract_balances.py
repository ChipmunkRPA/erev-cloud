"""RPT-51 contract balances from latest per-contract versions, scoped by balance entity."""

import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import contract, contract_version_balance, legal_entity
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_balances"
EVIDENCE: Final = "extract_balances_v1"
# Frozen v1 columns: future schema changes must explicitly version the export contract.
COLUMNS: Final = (
    Column("id", "id", "text"),
    Column("contract_version_id", "contract_version_id", "text"),
    Column("contract_id", "contract_id", "text"),
    Column("entity_id", "entity_id", "text"),
    Column("book_code", "book_code", "text"),
    Column("txn_currency", "txn_currency", "text"),
    Column("functional_currency", "functional_currency", "text"),
    Column("revenue_cum_txn", "revenue_cum_txn", "decimal"),
    Column("billed_cum_txn", "billed_cum_txn", "decimal"),
    Column("net_position_txn", "net_position_txn", "decimal"),
    Column("contract_liability_txn", "contract_liability_txn", "decimal"),
    Column("contract_liability_functional", "contract_liability_functional", "decimal"),
    Column("contract_liability_current_txn", "contract_liability_current_txn", "decimal"),
    Column("contract_asset_txn", "contract_asset_txn", "decimal"),
    Column("contract_asset_functional", "contract_asset_functional", "decimal"),
    Column("contract_asset_current_txn", "contract_asset_current_txn", "decimal"),
    Column("unbilled_receivable_txn", "unbilled_receivable_txn", "decimal"),
    Column("unbilled_receivable_functional", "unbilled_receivable_functional", "decimal"),
    Column("accounts_receivable_txn", "accounts_receivable_txn", "decimal"),
    Column("accounts_receivable_functional", "accounts_receivable_functional", "decimal"),
    Column("refund_liability_txn", "refund_liability_txn", "decimal"),
    Column("refund_liability_functional", "refund_liability_functional", "decimal"),
    Column("return_asset_txn", "return_asset_txn", "decimal"),
    Column("return_asset_functional", "return_asset_functional", "decimal"),
    Column("deposit_liability_txn", "deposit_liability_txn", "decimal"),
    Column("deposit_liability_functional", "deposit_liability_functional", "decimal"),
    Column("customer_incentive_asset_txn", "customer_incentive_asset_txn", "decimal"),
    Column("consideration_payable_txn", "consideration_payable_txn", "decimal"),
    Column("cost_asset_carrying_txn", "cost_asset_carrying_txn", "decimal"),
    Column("loss_provision_txn", "loss_provision_txn", "decimal"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "text"),
    Column("created_by_kind", "created_by_kind", "text"),
    Column("consideration_payable_functional", "consideration_payable_functional", "decimal"),
    Column("customer_incentive_asset_functional", "customer_incentive_asset_functional", "decimal"),
    Column("contract_external_id", "contract_external_id", "text"),
    Column("entity_code", "entity_code", "text"),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_balances has no lock dataset.")
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
                *(contract_version_balance.c[col.key] for col in COLUMNS[:-2]),
                contract.c.external_id.label("contract_external_id"),
                legal_entity.c.code.label("entity_code"),
            )
            .join(
                contract,
                (
                    (contract.c.tenant_id == contract_version_balance.c.tenant_id)
                    & (contract.c.id == contract_version_balance.c.contract_id)
                ),
            )
            .join(
                legal_entity,
                (legal_entity.c.tenant_id == contract_version_balance.c.tenant_id)
                & (legal_entity.c.id == contract_version_balance.c.entity_id),
            )
            .where(
                contract_version_balance.c.tenant_id == tenant,
                contract_version_balance.c.book_code == params.book_code,
                contract_version_balance.c.entity_id.in_(params.entity_ids),
                contract_version_balance.c.created_at <= cutoff,
                tie_outs.read_from(
                    contract_version_balance.c.contract_id,
                    contract_version_balance.c.contract_version_id,
                    book_code=params.book_code,
                    cutoff=cutoff,
                    created_cutoff=cutoff,
                    statuses=None,
                ),
            )
        )
        if mode == "INCREMENTAL":
            query = query.where(contract_version_balance.c.created_at > since)
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
            raise Problem("forbidden", "The retained balance exceeds the report entity scope.")
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
            raise Problem("invalid-transition", "Retained balance lies outside the extract window.")
        row["row_key"] = f"balance:{row['id']}"
        amounts = sums.setdefault(
            row["functional_currency"],
            {
                "contract_liability_functional": Decimal(0),
                "contract_asset_functional": Decimal(0),
                "unbilled_receivable_functional": Decimal(0),
            },
        )
        with localcontext() as context:
            context.prec = 80
            for key in amounts:
                amounts[key] += Decimal(row[key])
        rows.append(row)
    rows.sort(key=lambda row: (row["contract_external_id"], row["entity_code"], row["id"]))
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
