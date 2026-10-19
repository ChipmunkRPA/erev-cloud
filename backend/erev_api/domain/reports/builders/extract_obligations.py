"""RPT-46 latest per-contract obligation versions, without disclosure-status filtering."""

import json
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import contract, obligation_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.register_support import instant
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

CODE: Final = "extract_obligations"
EVIDENCE: Final = "extract_obligations_v1"
# Frozen v1 columns: future schema changes must explicitly version the export contract.
COLUMNS: Final = (
    Column("id", "id", "text"),
    Column("contract_version_id", "contract_version_id", "text"),
    Column("obligation_id", "obligation_id", "text"),
    Column("contract_id", "contract_id", "text"),
    Column("combination_group_id", "combination_group_id", "text"),
    Column("book_code", "book_code", "text"),
    Column("version_no", "version_no", "integer"),
    Column("previous_obligation_version_id", "previous_obligation_version_id", "text"),
    Column("obligation_key", "obligation_key", "text"),
    Column("legacy_record_key", "legacy_record_key", "text"),
    Column("product_id", "product_id", "text"),
    Column("product_code", "product_code", "text"),
    Column("sku_number", "sku_number", "text"),
    Column("stratification", "stratification", "text"),
    Column("obligation_kind", "obligation_kind", "text"),
    Column("distinctness", "distinctness", "text"),
    Column("series_increment_unit", "series_increment_unit", "text"),
    Column("pob_template_version_id", "pob_template_version_id", "text"),
    Column("scope_flag", "scope_flag", "text"),
    Column("satisfaction_pattern", "satisfaction_pattern", "text"),
    Column("over_time_criterion", "over_time_criterion", "text"),
    Column("recognition_method", "recognition_method", "text"),
    Column("ratable_convention", "ratable_convention", "text"),
    Column("principal_agent", "principal_agent", "text"),
    Column("licence_nature", "licence_nature", "text"),
    Column("warranty_type", "warranty_type", "text"),
    Column("start_date", "start_date", "date"),
    Column("end_date", "end_date", "date"),
    Column("contracting_entity_id", "contracting_entity_id", "text"),
    Column("performing_entity_id", "performing_entity_id", "text"),
    Column("txn_currency", "txn_currency", "text"),
    Column("memo_1", "memo_1", "text"),
    Column("memo_2", "memo_2", "text"),
    Column("memo_3", "memo_3", "text"),
    Column("account_overrides", "account_overrides", "text"),
    Column("legacy_deferred_revenue_account", "legacy_deferred_revenue_account", "text"),
    Column("legacy_unbilled_ar_account", "legacy_unbilled_ar_account", "text"),
    Column("legacy_revenue_account", "legacy_revenue_account", "text"),
    Column("original_quantity", "original_quantity", "decimal"),
    Column("original_stated_price", "original_stated_price", "decimal"),
    Column("quantity", "quantity", "decimal"),
    Column("stated_price", "stated_price", "decimal"),
    Column("ssp_book_version_id", "ssp_book_version_id", "text"),
    Column("ssp_entry_id", "ssp_entry_id", "text"),
    Column("ssp_range_id", "ssp_range_id", "text"),
    Column("ssp_method", "ssp_method", "text"),
    Column("ssp_version_label", "ssp_version_label", "text"),
    Column("ssp_unit_list_price", "ssp_unit_list_price", "decimal"),
    Column("ssp_midpoint_discount_ratio", "ssp_midpoint_discount_ratio", "decimal"),
    Column("ssp_range_ratio", "ssp_range_ratio", "decimal"),
    Column("ssp_override_approval_request_id", "ssp_override_approval_request_id", "text"),
    Column("original_ssp_mid", "original_ssp_mid", "decimal"),
    Column("original_ssp_high", "original_ssp_high", "decimal"),
    Column("original_ssp_low", "original_ssp_low", "decimal"),
    Column("original_ssp_selected", "original_ssp_selected", "decimal"),
    Column("original_ssp_in_range", "original_ssp_in_range", "boolean"),
    Column("original_total_contract_price", "original_total_contract_price", "decimal"),
    Column("original_total_contract_ssp", "original_total_contract_ssp", "decimal"),
    Column("original_allocated_amount", "original_allocated_amount", "decimal"),
    Column("original_allocated_exact", "original_allocated_exact", "decimal"),
    Column("original_unit_ssp", "original_unit_ssp", "decimal"),
    Column("original_unit_revenue_rate", "original_unit_revenue_rate", "decimal"),
    Column("allocation_weight", "allocation_weight", "decimal"),
    Column("allocated_amount", "allocated_amount", "decimal"),
    Column("allocated_exact", "allocated_exact", "decimal"),
    Column("allocation_adjustment", "allocation_adjustment", "decimal"),
    Column("unit_ssp", "unit_ssp", "decimal"),
    Column("remaining_unit_revenue_rate", "remaining_unit_revenue_rate", "decimal"),
    Column("delivered_quantity_cum", "delivered_quantity_cum", "decimal"),
    Column("returned_quantity_cum", "returned_quantity_cum", "decimal"),
    Column("progress_ratio", "progress_ratio", "decimal"),
    Column("revenue_cum", "revenue_cum", "decimal"),
    Column("billed_cum", "billed_cum", "decimal"),
    Column("ssp_delivered_cum", "ssp_delivered_cum", "decimal"),
    Column("catch_up_cum", "catch_up_cum", "decimal"),
    Column("catch_up_modification_cum", "catch_up_modification_cum", "decimal"),
    Column("catch_up_tp_change_cum", "catch_up_tp_change_cum", "decimal"),
    Column("catch_up_estimate_cum", "catch_up_estimate_cum", "decimal"),
    Column("pre_standard_revenue_cum", "pre_standard_revenue_cum", "decimal"),
    Column("delivered_quantity", "delivered_quantity", "decimal"),
    Column("revenue_amount", "revenue_amount", "decimal"),
    Column("billed_amount", "billed_amount", "decimal"),
    Column("ssp_delivered", "ssp_delivered", "decimal"),
    Column("catch_up_amount", "catch_up_amount", "decimal"),
    Column("pre_standard_revenue_amount", "pre_standard_revenue_amount", "decimal"),
    Column("remaining_quantity", "remaining_quantity", "decimal"),
    Column("remaining_ssp", "remaining_ssp", "decimal"),
    Column("remaining_allocation", "remaining_allocation", "decimal"),
    Column("remaining_billing", "remaining_billing", "decimal"),
    Column("scheduled_amount", "scheduled_amount", "decimal"),
    Column("awaiting_trigger_amount", "awaiting_trigger_amount", "decimal"),
    Column("position_obligation", "position_obligation", "decimal"),
    Column("position_contract_entity", "position_contract_entity", "decimal"),
    Column("netting_reclass_amount", "netting_reclass_amount", "decimal"),
    Column("netting_reclass_role", "netting_reclass_role", "text"),
    Column("satisfaction_status", "satisfaction_status", "text"),
    Column("satisfied_date", "satisfied_date", "date"),
    Column("hold_types", "hold_types", "text"),
    Column("modification_boundary_no", "modification_boundary_no", "integer"),
    Column("last_modification_id", "last_modification_id", "text"),
    Column("gross_amount_memo", "gross_amount_memo", "decimal"),
    Column("effective_date", "effective_date", "date"),
    Column("previous_effective_date", "previous_effective_date", "date"),
    Column("created_at", "created_at", "timestamp"),
    Column("created_by", "created_by", "text"),
    Column("created_by_kind", "created_by_kind", "text"),
    Column("contract_external_id", "contract_external_id", "text"),
)
JSON_FIELDS: Final = ("account_overrides", "hold_types")


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "extract_obligations has no lock dataset.")
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
                *(obligation_version.c[col.key] for col in COLUMNS[:-1]),
                contract.c.external_id.label("contract_external_id"),
            )
            .join(
                contract,
                (
                    (contract.c.tenant_id == obligation_version.c.tenant_id)
                    & (contract.c.id == obligation_version.c.contract_id)
                ),
            )
            .where(
                obligation_version.c.tenant_id == tenant,
                obligation_version.c.book_code == params.book_code,
                obligation_version.c.contracting_entity_id.in_(params.entity_ids),
                contract.c.contracting_entity_id.in_(params.entity_ids),
                obligation_version.c.created_at <= cutoff,
                tie_outs.read_from(
                    obligation_version.c.contract_id,
                    obligation_version.c.contract_version_id,
                    book_code=params.book_code,
                    cutoff=cutoff,
                    created_cutoff=cutoff,
                    statuses=None,
                ),
            )
        )
        if mode == "INCREMENTAL":
            query = query.where(obligation_version.c.created_at > since)
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
        if record["contracting_entity_id"] not in scope:
            raise Problem("forbidden", "The retained obligation exceeds the report entity scope.")
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
                "invalid-transition", "Retained obligation lies outside the extract window."
            )
        for key in JSON_FIELDS:
            row[key] = canonical_bytes(redact_contacts(row[key])).decode()
        row["row_key"] = f"obligation_version:{row['id']}"
        amounts = sums.setdefault(
            row["txn_currency"],
            {
                "allocated_amount": Decimal(0),
                "revenue_cum": Decimal(0),
            },
        )
        with localcontext() as context:
            context.prec = 80
            for key in amounts:
                amounts[key] += Decimal(row[key])
        rows.append(row)
    rows.sort(key=lambda row: (row["contract_external_id"], row["obligation_key"], row["id"]))
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
