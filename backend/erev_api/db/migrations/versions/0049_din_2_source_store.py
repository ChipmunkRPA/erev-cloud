"""BUILD_SPEC item DIN-2: raw source store.

04 ids created: E-39 ``source_object_type``; T-SRC-01 ``source_record`` with
``ux_source_record__identity``, ``ix_source_record__order`` and ``ix_source_record__upload``;
T-SRC-02 ``source_order`` (04 ``ux_source_order`` named ``ux_source_order__external``, NC-16);
T-SRC-03 ``source_order_line`` (``ux_source_order_line__line``, ``ck_source_order_line__quantity``
and ``ck_source_order_line__dates``); T-SRC-04 ``source_invoice`` (``ux_source_invoice__external``,
``ix_source_invoice__number``, ``ck_source_invoice__document_kind``); T-SRC-05
``source_invoice_line`` (``ux_source_invoice_line__line``); T-SRC-06 ``source_usage``
(``ux_source_usage__external``, ``ck_source_usage__rated_currency``); T-SRC-07 ``source_payment``
(``ux_source_payment__external``, ``ck_source_payment__amount``); T-SRC-08 ``source_match``
(``ix_source_match__record``, ``ix_source_match__target``, ``ck_source_match__target_type`` and
``ck_source_match__match_method``). Every table is IM-A (``apply_class``) and RLS-T.

Foreign keys: the 04 keys of T-SRC-02, T-SRC-03 and T-SRC-05; ``source_record_id`` of T-SRC-04, 06,
07 and 08, ``customer_id`` and ``product_id`` as lineage keys (NC-06; L5-1-Q-1);
``source_record.import_upload_id`` and ``import_row_id``. Keys that name ``source_record`` from
earlier tables (DG-MIG-03): ``exception_item.source_record_id`` (0041, BS3-D-02) and
``contract_event.source_record_id`` (0038). ``source_record.sync_run_id`` waits for T-INT-02
``sync_run`` (DIN-12). No function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

# 04 §3.4 E-39 (DG-MIG-06).
SOURCE_OBJECT_TYPE = (
    "ORDER",
    "INVOICE",
    "CREDIT_MEMO",
    "USAGE",
    "PAYMENT",
    "CUSTOMER",
    "PRODUCT",
    "SSP_ROW",
    "CONTRACT_SETUP_ROW",
    "PROGRESS_ROW",
    "MODIFICATION_ROW",
    "GL_ACCOUNT",
    "FX_RATE",
    "LEGACY_CONTRACT_LIVE_ROW",
)
# 04 T-SRC-08 ``target_type`` and ``match_method``.
MATCH_TARGETS = (
    "contract",
    "obligation",
    "contract_event",
    "customer",
    "product",
    "ssp_entry",
    "gl_account",
    "fx_rate",
    "estimate_version",
    "contract_cost_asset",
)
MATCH_METHODS = ("GROUPING_FIELDS", "EXPLICIT_REFERENCE", "LEGACY_KEY", "MANUAL", "ADAPTER_MAPPING")
# The eight tables in 04 §18 dependency order.
TABLES = (
    "source_record",
    "source_order",
    "source_order_line",
    "source_invoice",
    "source_invoice_line",
    "source_usage",
    "source_payment",
    "source_match",
)
# Foreign keys of earlier tables to ``source_record``: (table, column).
EXISTING_KEYS = (
    ("exception_item", "source_record_id"),
    ("contract_event", "source_record_id"),
)


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _date(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _flag(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false"))


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _system() -> sa.Column[Any]:
    return _named("source_system", "erev.source_system", nullable=False)


def _attributes() -> sa.Column[Any]:
    return _named("custom_attributes", "jsonb", nullable=False, default="'{}'")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _finish(table: str, keys: tuple[tuple[str, str], ...]) -> None:
    for column, target in keys:
        ops.add_tenant_fk(table, column, target)
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def _create_source_record() -> None:
    table = "source_record"
    ops.create_tenant_table(
        table,
        _system(),
        _named("object_type", "erev.source_object_type", nullable=False),
        _text("external_id", nullable=False),
        _text("external_version", nullable=False),
        sa.Column("version_order", sa.BigInteger(), nullable=False),
        _named("payload", "jsonb", nullable=False),
        _named("payload_sha256", "erev.sha256", nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _uuid("import_upload_id"),
        _uuid("import_row_id"),
        _uuid("sync_run_id"),
        _text("request_id"),
        _text("idempotency_key"),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_source_record__identity",
                ["tenant_id", "source_system", "object_type", "external_id", "external_version"],
                None,
            )
        ],
        indexes=[
            (
                "ix_source_record__order",
                ["tenant_id", "source_system", "object_type", "external_id", "version_order"],
                None,
            ),
            ("ix_source_record__upload", ["tenant_id", "import_upload_id"], None),
        ],
    )
    _finish(table, (("import_upload_id", "import_upload"), ("import_row_id", "import_row")))


def _create_source_order() -> None:
    table = "source_order"
    ops.create_tenant_table(
        table,
        _uuid("source_record_id", nullable=False),
        _system(),
        _text("external_order_id", nullable=False),
        _text("external_version", nullable=False),
        _text("order_number", nullable=False),
        _date("order_date", nullable=False),
        _text("customer_external_id", nullable=False),
        _uuid("customer_id"),
        _text("legal_entity_code"),
        _named("transaction_currency", "erev.currency_code", nullable=False),
        _text("po_number"),
        _text("amendment_reason"),
        _text("parent_order_external_id"),
        _named("grouping_values", "jsonb", nullable=False),
        _text("payment_terms"),
        _date("signature_date"),
        _text("document_ref"),
        _named("termination_rights", "jsonb", nullable=True),
        _attributes(),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_source_order__external",
                ["tenant_id", "source_system", "external_order_id", "external_version"],
                None,
            )
        ],
    )
    _finish(table, (("source_record_id", "source_record"), ("customer_id", "customer")))


def _create_source_order_line() -> None:
    table = "source_order_line"
    ops.create_tenant_table(
        table,
        _uuid("source_order_id", nullable=False),
        _text("line_external_id", nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        _text("product_code", nullable=False),
        _uuid("product_id"),
        _text("stratification"),
        _named("quantity", "erev.exact", nullable=False),
        _named("unit_list_price", "erev.exact", nullable=True),
        _named("unit_price", "erev.exact", nullable=True),
        _named("total_price", "erev.money", nullable=False),
        _date("start_date"),
        _date("end_date"),
        _text("selling_entity_code"),
        _text("performing_entity_code"),
        _text("ssp_version_label"),
        _named("account_codes", "jsonb", nullable=False, default="'{}'"),
        _date("effective_date"),
        _text("memo_1"),
        _text("memo_2"),
        _text("memo_3"),
        _flag("is_usage_line"),
        _text("bundle_parent_line_external_id"),
        _named("scope_flag", "erev.scope_flag", nullable=False, default="'IN_SCOPE_606'"),
        _named("out_of_scope_amount", "erev.money", nullable=True),
        _attributes(),
        standard_sets=["SC-C"],
        checks=[
            ("ck_source_order_line__quantity", "quantity <> 0"),
            (
                "ck_source_order_line__dates",
                "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            ),
        ],
        unique=[
            (
                "ux_source_order_line__line",
                ["tenant_id", "source_order_id", "line_external_id"],
                None,
            )
        ],
    )
    _finish(table, (("source_order_id", "source_order"), ("product_id", "product")))


def _create_source_invoice() -> None:
    table = "source_invoice"
    ops.create_tenant_table(
        table,
        _uuid("source_record_id", nullable=False),
        _system(),
        _text("external_invoice_id", nullable=False),
        _text("external_version", nullable=False),
        _text("invoice_number", nullable=False),
        _text("document_kind", nullable=False),
        _date("issue_date", nullable=False),
        _date("due_date"),
        _flag("is_cancellable"),
        _text("customer_external_id"),
        _uuid("customer_id"),
        _text("legal_entity_code", nullable=False),
        _named("currency", "erev.currency_code", nullable=False),
        _named("total_amount", "erev.money", nullable=False),
        _named("tax_amount", "erev.money", nullable=False, default="0"),
        _text("credited_invoice_external_id"),
        _attributes(),
        standard_sets=["SC-C"],
        checks=[("ck_source_invoice__document_kind", "document_kind IN ('INVOICE','CREDIT_MEMO')")],
        unique=[
            (
                "ux_source_invoice__external",
                ["tenant_id", "source_system", "external_invoice_id", "external_version"],
                None,
            )
        ],
        indexes=[("ix_source_invoice__number", ["tenant_id", "invoice_number"], None)],
    )
    _finish(table, (("source_record_id", "source_record"), ("customer_id", "customer")))


def _create_source_invoice_line() -> None:
    table = "source_invoice_line"
    ops.create_tenant_table(
        table,
        _uuid("source_invoice_id", nullable=False),
        _text("line_external_id", nullable=False),
        _text("order_line_external_id"),
        _text("contract_ref"),
        _text("obligation_ref"),
        _text("product_code"),
        _named("quantity", "erev.exact", nullable=True),
        _named("amount", "erev.money", nullable=False),
        _named("tax_lines", "jsonb", nullable=False, default="'[]'"),
        _date("service_period_start"),
        _date("service_period_end"),
        _attributes(),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_source_invoice_line__line",
                ["tenant_id", "source_invoice_id", "line_external_id"],
                None,
            )
        ],
    )
    _finish(table, (("source_invoice_id", "source_invoice"),))


def _create_source_usage() -> None:
    table = "source_usage"
    ops.create_tenant_table(
        table,
        _uuid("source_record_id", nullable=False),
        _system(),
        _text("external_usage_id", nullable=False),
        _text("external_version", nullable=False),
        _date("usage_date", nullable=False),
        _date("usage_period_start"),
        _date("usage_period_end"),
        _text("order_line_external_id"),
        _text("contract_ref"),
        _text("obligation_ref"),
        _text("product_code"),
        _text("metric", nullable=False),
        _named("quantity", "erev.exact", nullable=False),
        _named("rated_amount", "erev.money", nullable=True),
        _named("currency", "erev.currency_code", nullable=True),
        _flag("is_royalty_statement"),
        _attributes(),
        standard_sets=["SC-C"],
        checks=[("ck_source_usage__rated_currency", "(rated_amount IS NULL) = (currency IS NULL)")],
        unique=[
            (
                "ux_source_usage__external",
                ["tenant_id", "source_system", "external_usage_id", "external_version"],
                None,
            )
        ],
    )
    _finish(table, (("source_record_id", "source_record"),))


def _create_source_payment() -> None:
    table = "source_payment"
    ops.create_tenant_table(
        table,
        _uuid("source_record_id", nullable=False),
        _system(),
        _text("external_payment_id", nullable=False),
        _text("external_version", nullable=False),
        _date("receipt_date", nullable=False),
        _text("customer_external_id"),
        _text("legal_entity_code", nullable=False),
        _named("currency", "erev.currency_code", nullable=False),
        _named("amount", "erev.money", nullable=False),
        sa.Column(
            "applied_invoice_external_ids",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        _text("contract_ref"),
        _attributes(),
        standard_sets=["SC-C"],
        checks=[("ck_source_payment__amount", "amount <> 0")],
        unique=[
            (
                "ux_source_payment__external",
                ["tenant_id", "source_system", "external_payment_id", "external_version"],
                None,
            )
        ],
    )
    _finish(table, (("source_record_id", "source_record"),))


def _create_source_match() -> None:
    table = "source_match"
    ops.create_tenant_table(
        table,
        _uuid("source_record_id", nullable=False),
        _text("target_type", nullable=False),
        _uuid("target_id", nullable=False),
        _text("match_method", nullable=False),
        _named("match_detail", "jsonb", nullable=False, default="'{}'"),
        standard_sets=["SC-C"],
        checks=[
            ("ck_source_match__target_type", f"target_type IN ({_in(MATCH_TARGETS)})"),
            ("ck_source_match__match_method", f"match_method IN ({_in(MATCH_METHODS)})"),
        ],
        indexes=[
            ("ix_source_match__record", ["tenant_id", "source_record_id", "created_at"], None),
            ("ix_source_match__target", ["tenant_id", "target_type", "target_id"], None),
        ],
    )
    _finish(table, (("source_record_id", "source_record"),))


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("source_object_type", SOURCE_OBJECT_TYPE)
    _create_source_record()
    _create_source_order()
    _create_source_order_line()
    _create_source_invoice()
    _create_source_invoice_line()
    _create_source_usage()
    _create_source_payment()
    _create_source_match()
    for table, column in EXISTING_KEYS:
        ops.add_tenant_fk(table, column, "source_record")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table, column in reversed(EXISTING_KEYS):
        stem = column.removesuffix("_id")
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__{stem}")
    for table in reversed(TABLES):
        ops.drop_tenant_table(table)
    ops.drop_enum("source_object_type")
