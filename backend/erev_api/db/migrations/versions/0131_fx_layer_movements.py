"""Persist immutable, tenant/entity-scoped engine layer movements (T-CON-18)."""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0131"
down_revision = "0128"
branch_labels = None
depends_on = None

TABLE = "fx_layer_movement"
KINDS = (
    "LIABILITY_LAYER_CREATED",
    "LIABILITY_LAYER_CONSUMED",
    "ASSET_LAYER_CREATED",
    "ASSET_LAYER_SETTLED",
    "ASSET_LAYER_REMEASURED",
    "LIABILITY_LAYER_REMEASURED",
)


def upgrade() -> None:
    ops.create_enum("fx_layer_movement_kind", KINDS)
    ops.create_tenant_table(
        TABLE,
        sa.Column("contract_version_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("layer_key", sa.Text(), nullable=False),
        sa.Column("movement_kind", ops.NamedType("erev.fx_layer_movement_kind"), nullable=False),
        sa.Column("balance_role", ops.NamedType("erev.account_role"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("txn_currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("amount_txn", ops.NamedType("erev.money"), nullable=False),
        sa.Column("functional_currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("amount_functional", ops.NamedType("erev.money"), nullable=False),
        sa.Column("fx_rate_id", sa.Uuid(), nullable=True),
        sa.Column("rate", ops.NamedType("erev.fx_rate_value"), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("trace_node_id", sa.Text(), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_fx_layer_movement__foreign_rate",
                "txn_currency = functional_currency OR fx_rate_id IS NOT NULL",
            ),
            (
                "ck_fx_layer_movement__role",
                "balance_role IN ('CONTRACT_LIABILITY',"
                "'CONTRACT_ASSET','UNBILLED_RECEIVABLE','ACCOUNTS_RECEIVABLE',"
                "'REFUND_LIABILITY','DEPOSIT_LIABILITY','CONSIDERATION_PAYABLE')",
            ),
            (
                "ck_fx_layer_movement__liability_kinds",
                "movement_kind NOT IN "
                "('LIABILITY_LAYER_CREATED','LIABILITY_LAYER_CONSUMED','LIABILITY_LAYER_REMEASURED')"
                " OR balance_role IN ('CONTRACT_LIABILITY','REFUND_LIABILITY',"
                "'DEPOSIT_LIABILITY','CONSIDERATION_PAYABLE')",
            ),
            (
                "ck_fx_layer_movement__asset_kinds",
                "movement_kind NOT IN "
                "('ASSET_LAYER_CREATED','ASSET_LAYER_SETTLED','ASSET_LAYER_REMEASURED')"
                " OR balance_role IN ('CONTRACT_ASSET','UNBILLED_RECEIVABLE',"
                "'ACCOUNTS_RECEIVABLE')",
            ),
        ],
        indexes=[
            ("ix_fx_layer_movement__version", ["tenant_id", "contract_version_id"], None),
            (
                "ix_fx_layer_movement__layer",
                ["tenant_id", "contract_id", "book_code", "layer_key"],
                None,
            ),
        ],
    )
    for column, target in (
        ("contract_version_id", "contract_version"),
        ("contract_id", "contract"),
        ("entity_id", "legal_entity"),
        ("fx_rate_id", "fx_rate"),
        ("source_event_id", "contract_event"),
    ):
        ops.add_tenant_fk(TABLE, column, target)
    for column in ("txn_currency", "functional_currency"):
        ops.add_global_fk(TABLE, column, "currency", target_column="code")
    ops.apply_class(TABLE, "IM-A")
    ops.enable_rls(TABLE, "RLS-TE", entity_column="entity_id")


def downgrade() -> None:
    ops.drop_tenant_table(TABLE)
    ops.drop_enum("fx_layer_movement_kind")
