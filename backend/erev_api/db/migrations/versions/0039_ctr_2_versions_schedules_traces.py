"""BUILD_SPEC item CTR-2: computed versions, schedules and calculation traces.

04 ids created: E-22 ``satisfaction_status``, E-27 ``schedule_kind``, E-28 ``schedule_line_type``,
E-87 ``computation_trigger`` and E-88 ``computation_status``; and, because T-CON-11 names them and
no earlier revision created them, E-45 ``hold_type`` and E-77 ``scope_flag`` (L3-1-Q-20).

- T-CON-07 ``contract_computation`` (IM-A, RLS-T): ``ux_contract_computation__idempotent``,
  ``ix_contract_computation__group``, the checks ``ck_contract_computation__duration`` and
  ``ck_contract_computation__problem``, and the foreign keys to ``combination_group``,
  ``engine_release`` and ``job``.
- T-ENG-03 ``calc_trace`` (IM-A, RLS-T): ``ux_calc_trace__version``, ``ix_calc_trace__sha``, the
  check ``ck_calc_trace__node_count``, the foreign key to ``combination_group`` and the deferrable
  foreign key to ``contract_version`` (the version names its trace and the trace its version).
- T-CON-08 ``contract_version`` (IM-A, RLS-T): ``ux_contract_version__no``,
  ``ux_contract_version__computation``, ``ix_contract_version__known``, the 04 check
  ``ck_contract_version__status_reason`` and the checks ``__version_no``, ``__expected_returns``,
  ``__consideration_payable`` and ``__modification_boundary_no``; the foreign keys to the group,
  the computation, itself and ``calc_trace``; DB-17 ``tg_contract_version__allocation``
  (``EREV-ALC-001``).
- T-CON-09 ``contract_version_balance`` (IM-A, RLS-TE on ``entity_id``): the 04 key
  ``ux_contract_version_balance`` named ``ux_contract_version_balance__member`` (NC-16), the
  non-negative checks of every labelled balance and the foreign keys to the version, ``contract``,
  ``legal_entity`` and ``currency``.
- T-CON-11 ``obligation_version`` (IM-A, RLS-T): the 04 key ``ux_obligation_version`` named
  ``ux_obligation_version__obligation_in_version`` (NC-16), ``ix_obligation_version__obligation``,
  ``ix_obligation_version__contract``, the checks ``ck_obligation_version__progress_ratio`` and the
  DB-17 identity ``ck_obligation_version__allocation``, and the foreign keys to the version, the
  obligation, the contract, the group, itself, ``product``, ``pob_template_version``,
  ``legal_entity``, ``currency``, ``ssp_book_version``, ``ssp_entry``, ``ssp_range`` and
  ``approval_request``.
- T-ENG-01 ``schedule`` (IM-A, RLS-T): the 04 key ``ux_schedule`` named ``ux_schedule__kind``, the
  check ``ck_schedule__line_count`` and the foreign keys to the version, the group and ``currency``.
- T-ENG-02 ``schedule_line`` (IM-A, RLS-TE on ``entity_id``, PT-MPE): monthly partitions from
  2018-01 to 2032-12 and the default partition (DG-MIG-10); the 04 key ``ux_schedule_line`` named
  ``ux_schedule_line__subject_period``, ``ix_schedule_line__contract``,
  ``ix_schedule_line__release``, the 04 check ``ck_schedule_line__subject_type`` and the foreign
  keys to the schedule, the version, ``contract``, ``legal_entity``, ``period`` and ``currency``.

The foreign keys ``contract.latest_computation_id`` and ``combination_group.head_computation_id``
that revision 0038 left to this revision are added here (DG-MIG-03). The checks and foreign keys
04 does not name are L3-1-Q-20; ``obligation_version.last_modification_id`` references a table of a
later revision. One function is added (DB-17).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

# 04 §3.4 E-22, E-27, E-28, E-45, E-77, E-87, E-88 (DG-MIG-06).
SATISFACTION_STATUS = ("UNSATISFIED", "PARTIALLY_SATISFIED", "SATISFIED", "CANCELLED")
SCHEDULE_KIND = (
    "REVENUE",
    "COST_AMORTIZATION",
    "FINANCING_INTEREST",
    "BILLING_PLAN",
    "LOSS_PROVISION_RELEASE",
)
SCHEDULE_LINE_TYPE = (
    "NORMAL",
    "CATCH_UP",
    "TP_CHANGE",
    "BREAKAGE",
    "ROYALTY",
    "RETURN",
    "MODIFICATION",
    "OPENING_BALANCE",
)
HOLD_TYPE = ("recognition", "journal_export")
SCOPE_FLAG = (
    "IN_SCOPE_606",
    "LEASE_842",
    "INSURANCE_944",
    "FINANCIAL_INSTRUMENT",
    "GUARANTEE_460",
    "CONTRIBUTION_958_605",
    "NONFINANCIAL_ASSET_610_20",
    "ALTERNATIVE_REVENUE_980_605",
    "COLLABORATION_808",
)
COMPUTATION_TRIGGER = (
    "COMMAND",
    "REPLAY_VERIFY",
    "RESTATE",
    "UPGRADE_VALIDATE",
    "FX_REPUBLISH",
    "POLICY_RERUN",
    "CLOSE_RELEASE",
    "MIGRATION",
)
COMPUTATION_STATUS = ("SUCCEEDED", "FAILED", "QUARANTINED")
# 04 T-CON-08 ``status_reason_in_book`` (rev 1.2; ENGINE_SPEC OQ-A-24).
STATUS_REASONS = (
    "BOOKED",
    "ACTIVATED",
    "NOT_PROBABLE",
    "NO_COMMERCIAL_SUBSTANCE",
    "MUTUAL_TERMINATION_UNPERFORMED",
    "CRITERIA_MET",
    "EVENT_25_7_A",
    "EVENT_25_7_B",
    "EVENT_25_7_C",
    "TERMINATED",
    "VOIDED",
)
# 04 T-CON-09: "labelled balances are non-negative; same rule for every balance column below".
BALANCE_COLUMNS = (
    "contract_liability_txn",
    "contract_liability_functional",
    "contract_liability_current_txn",
    "contract_asset_txn",
    "contract_asset_functional",
    "contract_asset_current_txn",
    "unbilled_receivable_txn",
    "unbilled_receivable_functional",
    "accounts_receivable_txn",
    "accounts_receivable_functional",
    "refund_liability_txn",
    "refund_liability_functional",
    "return_asset_txn",
    "return_asset_functional",
    "deposit_liability_txn",
    "deposit_liability_functional",
    "customer_incentive_asset_txn",
    "consideration_payable_txn",
    "cost_asset_carrying_txn",
    "loss_provision_txn",
)

# DB-17 V1 (04 §14.1 rev 1.2): at commit, the obligation versions of a contract version allocate the
# transaction price less consideration payable (a non-positive amount, so it is added back).
ALLOCATION_BODY = """
DECLARE
  allocated numeric;
BEGIN
  SELECT coalesce(sum(o.allocated_amount), 0) INTO allocated
    FROM erev.obligation_version o
   WHERE o.tenant_id = NEW.tenant_id AND o.contract_version_id = NEW.id;
  IF allocated IS DISTINCT FROM NEW.transaction_price - NEW.consideration_payable_amount THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-ALC-001: obligation versions of contract version %s allocate %s, not '
                       'transaction_price %s less consideration_payable_amount %s',
                       NEW.id, allocated, NEW.transaction_price, NEW.consideration_payable_amount);
  END IF;
  RETURN NULL;
END
"""


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _money(name: str, *, nullable: bool = False, zero: bool = False) -> sa.Column[Any]:
    return _named(name, "erev.money", nullable=nullable, default="0" if zero else None)


def _exact(name: str, *, nullable: bool = False, zero: bool = False) -> sa.Column[Any]:
    return _named(name, "erev.exact", nullable=nullable, default="0" if zero else None)


def _integer(name: str, *, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=server_default)


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def _date(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _literals(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _currency_fk(table: str, column: str) -> None:
    ops.add_global_fk(table, column, "currency", target_column="code")


def _create_contract_computation() -> None:
    ops.create_tenant_table(
        "contract_computation",
        _uuid("combination_group_id", nullable=False),
        _named("stream_heads", "jsonb", nullable=False),
        _timestamp("known_at", nullable=False),
        _named("trigger", "erev.computation_trigger", nullable=False),
        _uuid("engine_release_id", nullable=False),
        _text("engine_version", nullable=False),
        _named("input_sha256", "erev.sha256", nullable=False),
        _named("pinned_refs", "jsonb", nullable=False),
        _named("status", "erev.computation_status", nullable=False),
        _named("problem", "jsonb", nullable=True),
        _integer("duration_ms"),
        _uuid("job_id"),
        _uuid("close_run_id"),
        standard_sets=["SC-C"],
        checks=[
            ("ck_contract_computation__duration", "duration_ms >= 0"),
            ("ck_contract_computation__problem", "(status = 'SUCCEEDED') = (problem IS NULL)"),
        ],
        unique=[
            (
                "ux_contract_computation__idempotent",
                ["tenant_id", "combination_group_id", "input_sha256", "engine_version"],
                "status = 'SUCCEEDED'",
            )
        ],
        indexes=[
            (
                "ix_contract_computation__group",
                ["tenant_id", "combination_group_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("contract_computation", "combination_group_id", "combination_group")
    ops.add_global_fk("contract_computation", "engine_release_id", "engine_release")
    ops.add_tenant_fk("contract_computation", "job_id", "job")
    ops.apply_class("contract_computation", "IM-A")
    ops.enable_rls("contract_computation", "RLS-T")
    ops.add_tenant_fk("contract", "latest_computation_id", "contract_computation")
    ops.add_tenant_fk("combination_group", "head_computation_id", "contract_computation")


def _create_calc_trace() -> None:
    ops.create_tenant_table(
        "calc_trace",
        _uuid("contract_version_id", nullable=False),
        _uuid("combination_group_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        sa.Column("format_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        _text("engine_version", nullable=False),
        _named("trace_sha256", "erev.sha256", nullable=False),
        _integer("node_count"),
        _named("root_measures", "jsonb", nullable=False),
        _named("trace", "jsonb", nullable=False),
        standard_sets=["SC-C"],
        checks=[("ck_calc_trace__node_count", "node_count >= 0")],
        unique=[("ux_calc_trace__version", ["tenant_id", "contract_version_id"], None)],
        indexes=[("ix_calc_trace__sha", ["tenant_id", "trace_sha256"], None)],
    )
    ops.add_tenant_fk("calc_trace", "combination_group_id", "combination_group")
    ops.apply_class("calc_trace", "IM-A")
    ops.enable_rls("calc_trace", "RLS-T")


def _create_contract_version() -> None:
    ops.create_tenant_table(
        "contract_version",
        _uuid("combination_group_id", nullable=False),
        _uuid("contract_computation_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _integer("version_no"),
        _uuid("previous_version_id"),
        _timestamp("known_at", nullable=False),
        _named("cause_event_ids", "uuid[]", nullable=False),
        _named("output_sha256", "erev.sha256", nullable=False),
        _uuid("calc_trace_id", nullable=False),
        _named("transaction_currency", "erev.currency_code", nullable=False),
        _named("status_in_book", "erev.contract_status", nullable=False),
        _text("status_reason_in_book"),
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
        _integer("modification_boundary_no", default="0"),
        _named("pinned_policies", "jsonb", nullable=False),
        standard_sets=["SC-C"],
        checks=[
            ("ck_contract_version__version_no", "version_no >= 1"),
            (
                "ck_contract_version__status_reason",
                f"status_reason_in_book IN ({_literals(STATUS_REASONS)})",
            ),
            ("ck_contract_version__expected_returns", "expected_returns_amount <= 0"),
            ("ck_contract_version__consideration_payable", "consideration_payable_amount <= 0"),
            ("ck_contract_version__modification_boundary_no", "modification_boundary_no >= 0"),
        ],
        unique=[
            (
                "ux_contract_version__no",
                ["tenant_id", "combination_group_id", "book_code", "version_no"],
                None,
            ),
            (
                "ux_contract_version__computation",
                ["tenant_id", "contract_computation_id", "book_code"],
                None,
            ),
        ],
        indexes=[
            (
                "ix_contract_version__known",
                ["tenant_id", "combination_group_id", "book_code", "known_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("contract_version", "combination_group_id", "combination_group")
    ops.add_tenant_fk("contract_version", "contract_computation_id", "contract_computation")
    ops.add_tenant_fk("contract_version", "previous_version_id", "contract_version")
    _currency_fk("contract_version", "transaction_currency")
    ops.apply_class("contract_version", "IM-A")
    ops.enable_rls("contract_version", "RLS-T")
    ops.create_trigger(
        "contract_version",
        "allocation",
        ALLOCATION_BODY,
        timing="AFTER",
        events="INSERT",
        deferrable=True,
    )
    # A version names its trace and the trace its version, so both keys are checked at commit.
    for table, constraint, column, target in (
        ("contract_version", "fk_contract_version__calc_trace", "calc_trace_id", "calc_trace"),
        (
            "calc_trace",
            "fk_calc_trace__contract_version",
            "contract_version_id",
            "contract_version",
        ),
    ):
        ops.execute(
            f"ALTER TABLE erev.{table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (tenant_id, {column}) REFERENCES erev.{target} (tenant_id, id) "
            "ON DELETE RESTRICT ON UPDATE RESTRICT DEFERRABLE INITIALLY DEFERRED"
        )


def _create_contract_version_balance() -> None:
    ops.create_tenant_table(
        "contract_version_balance",
        _uuid("contract_version_id", nullable=False),
        _uuid("contract_id", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _named("txn_currency", "erev.currency_code", nullable=False),
        _named("functional_currency", "erev.currency_code", nullable=False),
        _money("revenue_cum_txn"),
        _money("billed_cum_txn"),
        _money("net_position_txn"),
        *(_money(name, zero=True) for name in BALANCE_COLUMNS),
        standard_sets=["SC-C"],
        checks=[
            (f"ck_contract_version_balance__{name}", f"{name} >= 0") for name in BALANCE_COLUMNS
        ],
        unique=[
            (
                "ux_contract_version_balance__member",
                ["tenant_id", "contract_version_id", "contract_id", "entity_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("contract_version_balance", "contract_version_id", "contract_version")
    ops.add_tenant_fk("contract_version_balance", "contract_id", "contract")
    ops.add_tenant_fk("contract_version_balance", "entity_id", "legal_entity")
    _currency_fk("contract_version_balance", "txn_currency")
    _currency_fk("contract_version_balance", "functional_currency")
    ops.apply_class("contract_version_balance", "IM-A")
    ops.enable_rls("contract_version_balance", "RLS-TE", entity_column="entity_id")


def _create_obligation_version() -> None:
    ops.create_tenant_table(
        "obligation_version",
        _uuid("contract_version_id", nullable=False),
        _uuid("obligation_id", nullable=False),
        _uuid("contract_id", nullable=False),
        _uuid("combination_group_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _integer("version_no"),
        _uuid("previous_obligation_version_id"),
        _text("obligation_key", nullable=False),
        _text("legacy_record_key", nullable=False),
        _uuid("product_id", nullable=False),
        _text("product_code", nullable=False),
        _text("sku_number"),
        sa.Column("stratification", sa.Text(), nullable=False, server_default=sa.text("''")),
        _named("obligation_kind", "erev.obligation_kind", nullable=False),
        _named("distinctness", "erev.distinctness", nullable=False),
        _text("series_increment_unit"),
        _uuid("pob_template_version_id", nullable=False),
        _named("scope_flag", "erev.scope_flag", nullable=False, default="'IN_SCOPE_606'"),
        _named("satisfaction_pattern", "erev.satisfaction_pattern", nullable=False),
        _named("over_time_criterion", "erev.over_time_criterion", nullable=False),
        _named("recognition_method", "erev.recognition_method", nullable=False),
        _named("ratable_convention", "erev.ratable_convention", nullable=True),
        _named("principal_agent", "erev.principal_agent", nullable=False),
        _named("licence_nature", "erev.licence_nature", nullable=False),
        _named("warranty_type", "erev.warranty_type", nullable=False),
        _date("start_date"),
        _date("end_date"),
        _uuid("contracting_entity_id", nullable=False),
        _uuid("performing_entity_id", nullable=False),
        _named("txn_currency", "erev.currency_code", nullable=False),
        _text("memo_1"),
        _text("memo_2"),
        _text("memo_3"),
        _named("account_overrides", "jsonb", nullable=False, default="'{}'::jsonb"),
        _text("legacy_deferred_revenue_account"),
        _text("legacy_unbilled_ar_account"),
        _text("legacy_revenue_account"),
        _exact("original_quantity"),
        _money("original_stated_price"),
        _exact("quantity"),
        _money("stated_price"),
        _uuid("ssp_book_version_id"),
        _uuid("ssp_entry_id"),
        _uuid("ssp_range_id"),
        _named("ssp_method", "erev.ssp_method", nullable=True),
        _text("ssp_version_label"),
        _exact("ssp_unit_list_price", nullable=True),
        _exact("ssp_midpoint_discount_ratio", nullable=True),
        _exact("ssp_range_ratio", nullable=True),
        _uuid("ssp_override_approval_request_id"),
        _exact("original_ssp_mid", nullable=True),
        _exact("original_ssp_high", nullable=True),
        _exact("original_ssp_low", nullable=True),
        _exact("original_ssp_selected"),
        sa.Column("original_ssp_in_range", sa.Boolean(), nullable=True),
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
        _named("netting_reclass_role", "erev.account_role", nullable=True),
        _named("satisfaction_status", "erev.satisfaction_status", nullable=False),
        _date("satisfied_date"),
        _named("hold_types", "erev.hold_type[]", nullable=False, default="'{}'"),
        _integer("modification_boundary_no", default="0"),
        _uuid("last_modification_id"),
        _money("gross_amount_memo", nullable=True),
        _date("effective_date", nullable=False),
        _date("previous_effective_date"),
        _named("trace_nodes", "jsonb", nullable=False, default="'{}'::jsonb"),
        standard_sets=["SC-C"],
        checks=[
            ("ck_obligation_version__version_no", "version_no >= 1"),
            ("ck_obligation_version__progress_ratio", "progress_ratio >= 0"),
            (
                "ck_obligation_version__allocation",
                "allocated_amount = revenue_cum + scheduled_amount + awaiting_trigger_amount",
            ),
            ("ck_obligation_version__modification_boundary_no", "modification_boundary_no >= 0"),
        ],
        unique=[
            (
                "ux_obligation_version__obligation_in_version",
                ["tenant_id", "contract_version_id", "obligation_id"],
                None,
            )
        ],
        indexes=[
            (
                "ix_obligation_version__obligation",
                ["tenant_id", "obligation_id", "book_code", "version_no"],
                None,
            ),
            (
                "ix_obligation_version__contract",
                ["tenant_id", "contract_id", "book_code", "version_no"],
                None,
            ),
        ],
    )
    table = "obligation_version"
    ops.add_tenant_fk(table, "contract_version_id", "contract_version")
    ops.add_tenant_fk(table, "obligation_id", "obligation")
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_tenant_fk(table, "combination_group_id", "combination_group")
    ops.add_tenant_fk(table, "previous_obligation_version_id", "obligation_version")
    ops.add_tenant_fk(table, "product_id", "product")
    ops.add_tenant_fk(table, "pob_template_version_id", "pob_template_version")
    ops.add_tenant_fk(table, "contracting_entity_id", "legal_entity")
    ops.add_tenant_fk(table, "performing_entity_id", "legal_entity")
    _currency_fk(table, "txn_currency")
    ops.add_tenant_fk(table, "ssp_book_version_id", "ssp_book_version")
    ops.add_tenant_fk(table, "ssp_entry_id", "ssp_entry")
    ops.add_tenant_fk(table, "ssp_range_id", "ssp_range")
    ops.add_tenant_fk(table, "ssp_override_approval_request_id", "approval_request")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def _create_schedule() -> None:
    ops.create_tenant_table(
        "schedule",
        _uuid("contract_version_id", nullable=False),
        _uuid("combination_group_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _named("schedule_kind", "erev.schedule_kind", nullable=False),
        _named("currency", "erev.currency_code", nullable=False),
        _integer("line_count"),
        _money("total_amount"),
        standard_sets=["SC-C"],
        checks=[("ck_schedule__line_count", "line_count >= 0")],
        unique=[("ux_schedule__kind", ["tenant_id", "contract_version_id", "schedule_kind"], None)],
    )
    ops.add_tenant_fk("schedule", "contract_version_id", "contract_version")
    ops.add_tenant_fk("schedule", "combination_group_id", "combination_group")
    _currency_fk("schedule", "currency")
    ops.apply_class("schedule", "IM-A")
    ops.enable_rls("schedule", "RLS-T")


def _create_schedule_line() -> None:
    ops.create_tenant_table(
        "schedule_line",
        _date("period_end_date", nullable=False),
        _uuid("id", nullable=False),
        _uuid("schedule_id", nullable=False),
        _uuid("contract_version_id", nullable=False),
        _uuid("contract_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _text("subject_type", nullable=False),
        _uuid("subject_id", nullable=False),
        _uuid("entity_id", nullable=False),
        _uuid("period_id", nullable=False),
        _named("line_type", "erev.schedule_line_type", nullable=False),
        _money("amount"),
        _money("cumulative_amount"),
        _exact("cumulative_exact"),
        _exact("quantity", nullable=True),
        _named("currency", "erev.currency_code", nullable=False),
        sa.Column("is_released_at_close", sa.Boolean(), nullable=False),
        _text("trace_node_id", nullable=False),
        _timestamp("created_at", nullable=False, now_default=True),
        include_id=False,
        partition_by="period_end_date",
        primary_key=["tenant_id", "period_end_date", "id"],
        checks=[
            (
                "ck_schedule_line__subject_type",
                "subject_type IN ('obligation', 'contract_cost_asset', 'contract')",
            )
        ],
        unique=[
            (
                "ux_schedule_line__subject_period",
                [
                    "tenant_id",
                    "period_end_date",
                    "schedule_id",
                    "subject_id",
                    "line_type",
                    "period_id",
                ],
                None,
            )
        ],
        indexes=[
            ("ix_schedule_line__contract", ["tenant_id", "contract_id", "period_end_date"], None),
            (
                "ix_schedule_line__release",
                [
                    "tenant_id",
                    "period_end_date",
                    "period_id",
                    "book_code",
                    "entity_id",
                    "is_released_at_close",
                ],
                None,
            ),
        ],
    )
    ops.create_monthly_partitions("schedule_line")
    table = "schedule_line"
    ops.add_tenant_fk(table, "schedule_id", "schedule")
    ops.add_tenant_fk(table, "contract_version_id", "contract_version")
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    _currency_fk(table, "currency")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("satisfaction_status", SATISFACTION_STATUS)
    ops.create_enum("schedule_kind", SCHEDULE_KIND)
    ops.create_enum("schedule_line_type", SCHEDULE_LINE_TYPE)
    ops.create_enum("hold_type", HOLD_TYPE)
    ops.create_enum("scope_flag", SCOPE_FLAG)
    ops.create_enum("computation_trigger", COMPUTATION_TRIGGER)
    ops.create_enum("computation_status", COMPUTATION_STATUS)
    _create_contract_computation()
    _create_calc_trace()
    _create_contract_version()
    _create_contract_version_balance()
    _create_obligation_version()
    _create_schedule()
    _create_schedule_line()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("schedule_line")
    ops.drop_tenant_table("schedule")
    ops.drop_tenant_table("obligation_version")
    ops.drop_tenant_table("contract_version_balance")
    ops.execute("ALTER TABLE erev.calc_trace DROP CONSTRAINT fk_calc_trace__contract_version")
    ops.drop_tenant_table("contract_version")
    ops.drop_tenant_table("calc_trace")
    ops.execute(
        "ALTER TABLE erev.combination_group DROP CONSTRAINT fk_combination_group__head_computation"
    )
    ops.execute("ALTER TABLE erev.contract DROP CONSTRAINT fk_contract__latest_computation")
    ops.drop_tenant_table("contract_computation")
    ops.drop_enum("computation_status")
    ops.drop_enum("computation_trigger")
    ops.drop_enum("scope_flag")
    ops.drop_enum("hold_type")
    ops.drop_enum("schedule_line_type")
    ops.drop_enum("schedule_kind")
    ops.drop_enum("satisfaction_status")
