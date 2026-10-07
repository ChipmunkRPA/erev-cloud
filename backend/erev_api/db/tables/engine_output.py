"""Computed state tables (04 §6 T-CON-07 to T-CON-09, T-CON-11 and §7 T-ENG-01 to T-ENG-03;
BUILD_SPEC CTR-2).

Created by revision 0039. ``computation.persist`` is their only writer (DG-CMD-10); every table is
IM-A, so a computation adds rows and never changes one.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    Date,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _timestamp
from erev_api.db.tables.reference import (
    account_role,
    book_code_type,
    distinctness,
    licence_nature,
    obligation_kind,
    over_time_criterion,
    principal_agent,
    ratable_convention,
    recognition_method,
    satisfaction_pattern,
    ssp_method,
    warranty_type,
)
from erev_api.db.types import ExactType, FxRateType, MoneyType
from erev_api.enums import (
    ComputationStatus,
    ComputationTrigger,
    ContractStatus,
    FxLayerMovementKind,
    HoldType,
    SatisfactionStatus,
    ScheduleKind,
    ScheduleLineType,
    ScopeFlag,
)

# E-17 of revision 0038, bound here again so that this module does not depend on
# ``tables.contracts`` while ``tables/__init__`` is importing.
contract_status: Final = _enum(ContractStatus, "contract_status")
# Created by revision 0039 (CTR-2): E-22, E-27, E-28, E-45, E-77, E-87, E-88.
satisfaction_status: Final = _enum(SatisfactionStatus, "satisfaction_status")
schedule_kind: Final = _enum(ScheduleKind, "schedule_kind")
schedule_line_type: Final = _enum(ScheduleLineType, "schedule_line_type")
hold_type: Final = _enum(HoldType, "hold_type")
scope_flag: Final = _enum(ScopeFlag, "scope_flag")
computation_trigger: Final = _enum(ComputationTrigger, "computation_trigger")
computation_status: Final = _enum(ComputationStatus, "computation_status")


def _money(name: str, *, nullable: bool = False, zero: bool = False) -> Column[object]:
    default = text("0") if zero else None
    return Column(name, MoneyType(), nullable=nullable, server_default=default)


def _exact(name: str, *, nullable: bool = False, zero: bool = False) -> Column[object]:
    default = text("0") if zero else None
    return Column(name, ExactType(), nullable=nullable, server_default=default)


# T-CON-07: one engine invocation over a combination group (IM-A, RLS-T).
contract_computation: Final = Table(
    "contract_computation",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("stream_heads", JSONB(), nullable=False),
    _timestamp("known_at", nullable=False),
    Column("trigger", computation_trigger, nullable=False),
    Column("engine_release_id", Uuid(), nullable=False),
    Column("engine_version", Text(), nullable=False),
    Column("input_sha256", CHAR(64), nullable=False),
    Column("pinned_refs", JSONB(), nullable=False),
    Column("status", computation_status, nullable=False),
    Column("problem", JSONB(none_as_null=True), nullable=True),
    Column("duration_ms", Integer(), nullable=False),
    Column("job_id", Uuid(), nullable=True),
    Column("close_run_id", Uuid(), nullable=True),
    *_sc_c(),
    # 04 rev 1.302 (revision 0129): the cutoff the computation's bundle admitted by —
    # what ``computation.behind_its_group`` reads of a head. NULL before the column.
    _timestamp("cutoff_at"),
)

# T-CON-08: immutable computed version of a combination group for one book (IM-A, RLS-T); DB-17
# ``tg_contract_version__allocation``.
contract_version: Final = Table(
    "contract_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("contract_computation_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("version_no", Integer(), nullable=False),
    Column("previous_version_id", Uuid(), nullable=True),
    _timestamp("known_at", nullable=False),
    Column("cause_event_ids", ARRAY(Uuid()), nullable=False),
    Column("output_sha256", CHAR(64), nullable=False),
    Column("calc_trace_id", Uuid(), nullable=False),
    Column("transaction_currency", CHAR(3), nullable=False),
    Column("status_in_book", contract_status, nullable=False),
    Column("status_reason_in_book", Text(), nullable=True),
    _money("transaction_price"),
    _money("fixed_consideration"),
    _money("vc_constrained_amount", zero=True),
    _money("vc_excluded_amount", zero=True),
    _money("expected_returns_amount", zero=True),
    _money("consideration_payable_amount", zero=True),
    _money("financing_adjustment_amount", zero=True),
    _money("noncash_consideration_amount", zero=True),
    _money("sales_tax_excluded_amount", zero=True),
    _money("out_of_scope_amount", zero=True),
    _exact("total_ssp"),
    _money("revenue_cum"),
    _money("billed_cum"),
    _money("net_position"),
    _money("rpo_amount"),
    _money("scheduled_amount"),
    _money("awaiting_trigger_amount"),
    Column("modification_boundary_no", Integer(), nullable=False, server_default=text("0")),
    Column("pinned_policies", JSONB(), nullable=False),
    *_sc_c(),
)

# T-CON-09: labelled balances per member contract and entity at a version (IM-A, RLS-TE on
# ``entity_id``).
contract_version_balance: Final = Table(
    "contract_version_balance",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    Column("functional_currency", CHAR(3), nullable=False),
    _money("revenue_cum_txn"),
    _money("billed_cum_txn"),
    _money("net_position_txn"),
    _money("contract_liability_txn", zero=True),
    _money("contract_liability_functional", zero=True),
    _money("contract_liability_current_txn", zero=True),
    _money("contract_asset_txn", zero=True),
    _money("contract_asset_functional", zero=True),
    _money("contract_asset_current_txn", zero=True),
    _money("unbilled_receivable_txn", zero=True),
    _money("unbilled_receivable_functional", zero=True),
    _money("accounts_receivable_txn", zero=True),
    _money("accounts_receivable_functional", zero=True),
    _money("refund_liability_txn", zero=True),
    _money("refund_liability_functional", zero=True),
    _money("return_asset_txn", zero=True),
    _money("return_asset_functional", zero=True),
    _money("deposit_liability_txn", zero=True),
    _money("deposit_liability_functional", zero=True),
    _money("customer_incentive_asset_txn", zero=True),
    _money("consideration_payable_txn", zero=True),
    _money("cost_asset_carrying_txn", zero=True),
    _money("loss_provision_txn", zero=True),
    *_sc_c(),
    # D-87 L6-5-Q-18 (revision 0053): added after the standard columns of 0039.
    _money("consideration_payable_functional", zero=True),
    _money("customer_incentive_asset_functional", zero=True),
)

# T-CON-11: full state of one obligation at one contract version and book (IM-A, RLS-T).
obligation_version: Final = Table(
    "obligation_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("obligation_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("version_no", Integer(), nullable=False),
    Column("previous_obligation_version_id", Uuid(), nullable=True),
    Column("obligation_key", Text(), nullable=False),
    Column("legacy_record_key", Text(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("product_code", Text(), nullable=False),
    Column("sku_number", Text(), nullable=True),
    Column("stratification", Text(), nullable=False, server_default=text("''")),
    Column("obligation_kind", obligation_kind, nullable=False),
    Column("distinctness", distinctness, nullable=False),
    Column("series_increment_unit", Text(), nullable=True),
    Column("pob_template_version_id", Uuid(), nullable=False),
    Column("scope_flag", scope_flag, nullable=False, server_default=text("'IN_SCOPE_606'")),
    Column("satisfaction_pattern", satisfaction_pattern, nullable=False),
    Column("over_time_criterion", over_time_criterion, nullable=False),
    Column("recognition_method", recognition_method, nullable=False),
    Column("ratable_convention", ratable_convention, nullable=True),
    Column("principal_agent", principal_agent, nullable=False),
    Column("licence_nature", licence_nature, nullable=False),
    Column("warranty_type", warranty_type, nullable=False),
    Column("start_date", Date(), nullable=True),
    Column("end_date", Date(), nullable=True),
    Column("contracting_entity_id", Uuid(), nullable=False),
    Column("performing_entity_id", Uuid(), nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    Column("memo_1", Text(), nullable=True),
    Column("memo_2", Text(), nullable=True),
    Column("memo_3", Text(), nullable=True),
    Column("account_overrides", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("legacy_deferred_revenue_account", Text(), nullable=True),
    Column("legacy_unbilled_ar_account", Text(), nullable=True),
    Column("legacy_revenue_account", Text(), nullable=True),
    _exact("original_quantity"),
    _money("original_stated_price"),
    _exact("quantity"),
    _money("stated_price"),
    Column("ssp_book_version_id", Uuid(), nullable=True),
    Column("ssp_entry_id", Uuid(), nullable=True),
    Column("ssp_range_id", Uuid(), nullable=True),
    Column("ssp_method", ssp_method, nullable=True),
    Column("ssp_version_label", Text(), nullable=True),
    _exact("ssp_unit_list_price", nullable=True),
    _exact("ssp_midpoint_discount_ratio", nullable=True),
    _exact("ssp_range_ratio", nullable=True),
    Column("ssp_override_approval_request_id", Uuid(), nullable=True),
    _exact("original_ssp_mid", nullable=True),
    _exact("original_ssp_high", nullable=True),
    _exact("original_ssp_low", nullable=True),
    _exact("original_ssp_selected"),
    Column("original_ssp_in_range", Boolean(), nullable=True),
    _money("original_total_contract_price"),
    _exact("original_total_contract_ssp"),
    _money("original_allocated_amount"),
    _exact("original_allocated_exact"),
    _exact("original_unit_ssp", nullable=True),
    _exact("original_unit_revenue_rate", nullable=True),
    _exact("allocation_weight"),
    _money("allocated_amount"),
    _exact("allocated_exact"),
    _money("allocation_adjustment"),
    _exact("unit_ssp", nullable=True),
    _exact("remaining_unit_revenue_rate", nullable=True),
    _exact("delivered_quantity_cum", zero=True),
    _exact("returned_quantity_cum", zero=True),
    _exact("progress_ratio", zero=True),
    _money("revenue_cum", zero=True),
    _money("billed_cum", zero=True),
    _exact("ssp_delivered_cum", zero=True),
    _money("catch_up_cum", zero=True),
    _money("catch_up_modification_cum", zero=True),
    _money("catch_up_tp_change_cum", zero=True),
    _money("catch_up_estimate_cum", zero=True),
    _money("pre_standard_revenue_cum", zero=True),
    _exact("delivered_quantity", zero=True),
    _money("revenue_amount", zero=True),
    _money("billed_amount", zero=True),
    _exact("ssp_delivered", zero=True),
    _money("catch_up_amount", zero=True),
    _money("pre_standard_revenue_amount", zero=True),
    _exact("remaining_quantity"),
    _exact("remaining_ssp"),
    _money("remaining_allocation"),
    _money("remaining_billing"),
    _money("scheduled_amount", zero=True),
    _money("awaiting_trigger_amount", zero=True),
    _money("position_obligation"),
    _money("position_contract_entity"),
    _money("netting_reclass_amount", zero=True),
    Column("netting_reclass_role", account_role, nullable=True),
    Column("satisfaction_status", satisfaction_status, nullable=False),
    Column("satisfied_date", Date(), nullable=True),
    Column("hold_types", ARRAY(hold_type), nullable=False, server_default=text("'{}'")),
    Column("modification_boundary_no", Integer(), nullable=False, server_default=text("0")),
    Column("last_modification_id", Uuid(), nullable=True),
    _money("gross_amount_memo", nullable=True),
    Column("effective_date", Date(), nullable=False),
    Column("previous_effective_date", Date(), nullable=True),
    Column("trace_nodes", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    *_sc_c(),
)

# T-ENG-01: header of a versioned schedule produced by a contract version (IM-A, RLS-T).
schedule: Final = Table(
    "schedule",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("schedule_kind", schedule_kind, nullable=False),
    Column("currency", CHAR(3), nullable=False),
    Column("line_count", Integer(), nullable=False),
    _money("total_amount"),
    *_sc_c(),
)

# T-ENG-02: planned amount per subject, period and line type (IM-A, RLS-TE on ``entity_id``,
# PT-MPE).
schedule_line: Final = Table(
    "schedule_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("period_end_date", Date(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("schedule_id", Uuid(), nullable=False),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("line_type", schedule_line_type, nullable=False),
    _money("amount"),
    _money("cumulative_amount"),
    _exact("cumulative_exact"),
    _exact("quantity", nullable=True),
    Column("currency", CHAR(3), nullable=False),
    Column("is_released_at_close", Boolean(), nullable=False),
    Column("trace_node_id", Text(), nullable=False),
    _timestamp("created_at", nullable=False, now_default=True),
)

# T-ENG-03: the calculation DAG behind a contract version (IM-A, RLS-T).
calc_trace: Final = Table(
    "calc_trace",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("combination_group_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("format_version", SmallInteger(), nullable=False, server_default=text("1")),
    Column("engine_version", Text(), nullable=False),
    Column("trace_sha256", CHAR(64), nullable=False),
    Column("node_count", Integer(), nullable=False),
    Column("root_measures", JSONB(), nullable=False),
    Column("trace", JSONB(), nullable=False),
    *_sc_c(),
)


# T-CON-18: movements of one immutable computation version; revision 0131.
fx_layer_movement: Final = Table(
    "fx_layer_movement",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("layer_key", Text(), nullable=False),
    Column("movement_kind", _enum(FxLayerMovementKind, "fx_layer_movement_kind"), nullable=False),
    Column("balance_role", account_role, nullable=False),
    Column("effective_date", Date(), nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    _money("amount_txn"),
    Column("functional_currency", CHAR(3), nullable=False),
    _money("amount_functional"),
    Column("fx_rate_id", Uuid(), nullable=True),
    Column("rate", FxRateType(), nullable=True),
    Column("source_event_id", Uuid(), nullable=True),
    Column("trace_node_id", Text(), nullable=True),
    *_sc_c(),
)
