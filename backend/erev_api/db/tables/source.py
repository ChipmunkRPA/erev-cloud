"""Raw source store (04 §11 SRC: T-SRC-01 to T-SRC-08; BUILD_SPEC DIN-2).

Revision 0049 (DIN-2) creates the eight tables, E-39 ``source_object_type`` and the foreign keys
that name ``source_record`` (DG-MIG-03). Every table is IM-A (append-only), RLS-T, PT-N and
AUD-FACT.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import CHAR, BigInteger, Boolean, Column, Date, Integer, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _timestamp
from erev_api.db.types import ExactType, MoneyType
from erev_api.enums import ScopeFlag, SourceObjectType, SourceSystem

# Existing types named here, as ``tables.engine_output`` names ``contract_status``, so that this
# module does not depend on sibling modules while ``tables/__init__`` is importing: E-38 (0028),
# E-45 ``scope_flag`` (0039).
source_system: Final = _enum(SourceSystem, "source_system")
scope_flag: Final = _enum(ScopeFlag, "scope_flag")
# Created by revision 0049 (DIN-2): E-39.
source_object_type: Final = _enum(SourceObjectType, "source_object_type")


def _money(name: str, *, nullable: bool = False, zero: bool = False) -> Column[object]:
    default = text("0") if zero else None
    return Column(name, MoneyType(), nullable=nullable, server_default=default)


def _exact(name: str, *, nullable: bool = False) -> Column[object]:
    return Column(name, ExactType(), nullable=nullable)


def _attributes() -> Column[object]:
    return Column(
        "custom_attributes", JSONB(none_as_null=True), nullable=False, server_default="{}"
    )


# T-SRC-01: the immutable raw payload of any channel, keyed by source identity and version.
source_record: Final = Table(
    "source_record",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_system", source_system, nullable=False),
    Column("object_type", source_object_type, nullable=False),
    Column("external_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=False),
    Column("version_order", BigInteger(), nullable=False),
    Column("payload", JSONB(none_as_null=True), nullable=False),
    Column("payload_sha256", CHAR(64), nullable=False),
    _timestamp("received_at", nullable=False, now_default=True),
    Column("import_upload_id", Uuid(), nullable=True),
    Column("import_row_id", Uuid(), nullable=True),
    Column("sync_run_id", Uuid(), nullable=True),
    Column("request_id", Text(), nullable=True),
    Column("idempotency_key", Text(), nullable=True),
    *_sc_c(),
)

# T-SRC-02: a normalized order or contract header.
source_order: Final = Table(
    "source_order",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_record_id", Uuid(), nullable=False),
    Column("source_system", source_system, nullable=False),
    Column("external_order_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=False),
    Column("order_number", Text(), nullable=False),
    Column("order_date", Date(), nullable=False),
    Column("customer_external_id", Text(), nullable=False),
    Column("customer_id", Uuid(), nullable=True),
    Column("legal_entity_code", Text(), nullable=True),
    Column("transaction_currency", CHAR(3), nullable=False),
    Column("po_number", Text(), nullable=True),
    Column("amendment_reason", Text(), nullable=True),
    Column("parent_order_external_id", Text(), nullable=True),
    Column("grouping_values", JSONB(none_as_null=True), nullable=False),
    Column("payment_terms", Text(), nullable=True),
    Column("signature_date", Date(), nullable=True),
    Column("document_ref", Text(), nullable=True),
    Column("termination_rights", JSONB(none_as_null=True), nullable=True),
    _attributes(),
    *_sc_c(),
)

# T-SRC-03: a normalized order line; one legacy Contract Setup row.
source_order_line: Final = Table(
    "source_order_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_order_id", Uuid(), nullable=False),
    Column("line_external_id", Text(), nullable=False),
    Column("line_no", Integer(), nullable=False),
    Column("product_code", Text(), nullable=False),
    Column("product_id", Uuid(), nullable=True),
    Column("stratification", Text(), nullable=True),
    _exact("quantity"),
    _exact("unit_list_price", nullable=True),
    _exact("unit_price", nullable=True),
    _money("total_price"),
    Column("start_date", Date(), nullable=True),
    Column("end_date", Date(), nullable=True),
    Column("selling_entity_code", Text(), nullable=True),
    Column("performing_entity_code", Text(), nullable=True),
    Column("ssp_version_label", Text(), nullable=True),
    Column("account_codes", JSONB(none_as_null=True), nullable=False, server_default="{}"),
    Column("effective_date", Date(), nullable=True),
    Column("memo_1", Text(), nullable=True),
    Column("memo_2", Text(), nullable=True),
    Column("memo_3", Text(), nullable=True),
    Column("is_usage_line", Boolean(), nullable=False, server_default=text("false")),
    Column("bundle_parent_line_external_id", Text(), nullable=True),
    Column("scope_flag", scope_flag, nullable=False, server_default=text("'IN_SCOPE_606'")),
    _money("out_of_scope_amount", nullable=True),
    _attributes(),
    *_sc_c(),
)

# T-SRC-04: a normalized invoice or credit memo header.
source_invoice: Final = Table(
    "source_invoice",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_record_id", Uuid(), nullable=False),
    Column("source_system", source_system, nullable=False),
    Column("external_invoice_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=False),
    Column("invoice_number", Text(), nullable=False),
    Column("document_kind", Text(), nullable=False),
    Column("issue_date", Date(), nullable=False),
    Column("due_date", Date(), nullable=True),
    Column("is_cancellable", Boolean(), nullable=False, server_default=text("false")),
    Column("customer_external_id", Text(), nullable=True),
    Column("customer_id", Uuid(), nullable=True),
    Column("legal_entity_code", Text(), nullable=False),
    Column("currency", CHAR(3), nullable=False),
    _money("total_amount"),
    _money("tax_amount", zero=True),
    Column("credited_invoice_external_id", Text(), nullable=True),
    _attributes(),
    *_sc_c(),
)

# T-SRC-05: an invoice or credit memo line with its contract and obligation reference.
source_invoice_line: Final = Table(
    "source_invoice_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_invoice_id", Uuid(), nullable=False),
    Column("line_external_id", Text(), nullable=False),
    Column("order_line_external_id", Text(), nullable=True),
    Column("contract_ref", Text(), nullable=True),
    Column("obligation_ref", Text(), nullable=True),
    Column("product_code", Text(), nullable=True),
    _exact("quantity", nullable=True),
    _money("amount"),
    Column("tax_lines", JSONB(none_as_null=True), nullable=False, server_default="[]"),
    Column("service_period_start", Date(), nullable=True),
    Column("service_period_end", Date(), nullable=True),
    _attributes(),
    *_sc_c(),
)

# T-SRC-06: a normalized usage record or royalty statement line.
source_usage: Final = Table(
    "source_usage",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_record_id", Uuid(), nullable=False),
    Column("source_system", source_system, nullable=False),
    Column("external_usage_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=False),
    Column("usage_date", Date(), nullable=False),
    Column("usage_period_start", Date(), nullable=True),
    Column("usage_period_end", Date(), nullable=True),
    Column("order_line_external_id", Text(), nullable=True),
    Column("contract_ref", Text(), nullable=True),
    Column("obligation_ref", Text(), nullable=True),
    Column("product_code", Text(), nullable=True),
    Column("metric", Text(), nullable=False),
    _exact("quantity"),
    _money("rated_amount", nullable=True),
    Column("currency", CHAR(3), nullable=True),
    Column("is_royalty_statement", Boolean(), nullable=False, server_default=text("false")),
    _attributes(),
    *_sc_c(),
)

# T-SRC-07: a normalized cash receipt.
source_payment: Final = Table(
    "source_payment",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_record_id", Uuid(), nullable=False),
    Column("source_system", source_system, nullable=False),
    Column("external_payment_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=False),
    Column("receipt_date", Date(), nullable=False),
    Column("customer_external_id", Text(), nullable=True),
    Column("legal_entity_code", Text(), nullable=False),
    Column("currency", CHAR(3), nullable=False),
    _money("amount"),
    Column(
        "applied_invoice_external_ids",
        ARRAY(Text()),
        nullable=False,
        server_default=text("'{}'::text[]"),
    ),
    Column("contract_ref", Text(), nullable=True),
    _attributes(),
    *_sc_c(),
)

# T-SRC-08: the result of matching a source record to internal objects (a re-match inserts).
source_match: Final = Table(
    "source_match",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("source_record_id", Uuid(), nullable=False),
    Column("target_type", Text(), nullable=False),
    Column("target_id", Uuid(), nullable=False),
    Column("match_method", Text(), nullable=False),
    Column("match_detail", JSONB(none_as_null=True), nullable=False, server_default="{}"),
    *_sc_c(),
)

# T-CON-02: the source records that established or changed a contract (IM-A, RLS-T; revision 0050,
# BUILD_SPEC DIN-4). It lives with the source tables it names, as the lane file scope places it.
contract_source_link: Final = Table(
    "contract_source_link",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("source_record_id", Uuid(), nullable=False),
    Column("link_role", Text(), nullable=False),
    Column("contract_event_id", Uuid(), nullable=True),
    *_sc_c(),
)
