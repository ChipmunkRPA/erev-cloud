"""Persist period-specific loss tests and every EAC version contributing to each test."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None

AMOUNTS = (
    "expected_consideration",
    "expected_total_costs",
    "costs_to_date",
    "revenue_to_date",
    "expected_margin",
    "provision_balance",
    "provision_movement",
)


def upgrade() -> None:
    ops.create_enum("loss_unit", ("CONTRACT", "POB"))
    table = "loss_provision_version"
    ops.create_tenant_table(
        table,
        sa.Column("contract_version_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("unit", ops.NamedType("erev.loss_unit"), nullable=False),
        sa.Column("unit_key", sa.Text(), nullable=False),
        sa.Column("obligation_id", sa.Uuid(), nullable=True),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("period_key", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("measurement_basis", sa.Text(), nullable=False),
        sa.Column("eac_estimate_version_id", sa.Uuid(), nullable=True),
        sa.Column("currency", ops.NamedType("erev.currency_code"), nullable=False),
        *(sa.Column(name, ops.NamedType("erev.money"), nullable=False) for name in AMOUNTS),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.Column("trace_nodes", ops.NamedType("jsonb"), nullable=False),
        standard_sets=["SC-C"],
        checks=[
            ("ck_loss_provision_version__unit", "(unit = 'POB') = (obligation_id IS NOT NULL)"),
            ("ck_loss_provision_version__basis", "measurement_basis IN ('ASC_605_35','IAS_37')"),
            ("ck_loss_provision_version__balance", "provision_balance >= 0"),
            ("ck_loss_provision_version__trace", "jsonb_typeof(trace_nodes) = 'object'"),
        ],
        unique=[
            (
                "ux_loss_provision_version__unit_period",
                ["tenant_id", "contract_version_id", "contract_id", "unit_key", "period_id"],
                None,
            )
        ],
    )
    for column, target in (
        ("contract_version_id", "contract_version"),
        ("contract_id", "contract"),
        ("entity_id", "legal_entity"),
        ("obligation_id", "obligation"),
        ("period_id", "period"),
        ("eac_estimate_version_id", "estimate_version"),
    ):
        ops.add_tenant_fk(table, column, target)
    ops.add_global_fk(table, "currency", "currency", target_column="code")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    table = "loss_provision_eac"
    ops.create_tenant_table(
        table,
        sa.Column("loss_provision_version_id", sa.Uuid(), nullable=False),
        sa.Column("estimate_version_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_loss_provision_eac__source",
                ["tenant_id", "loss_provision_version_id", "estimate_version_id"],
                None,
            )
        ],
    )
    for column, target in (
        ("loss_provision_version_id", "loss_provision_version"),
        ("estimate_version_id", "estimate_version"),
        ("entity_id", "legal_entity"),
    ):
        ops.add_tenant_fk(table, column, target)
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")


def downgrade() -> None:
    ops.drop_tenant_table("loss_provision_eac")
    ops.drop_tenant_table("loss_provision_version")
    ops.drop_enum("loss_unit")
