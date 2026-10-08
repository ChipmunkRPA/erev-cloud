"""Retain reviewed accounting judgement citations for error-correction reopens.

Historical rows remain nullable and unchanged. Downgrade refuses to discard any citation,
including rows outside the migration role's tenant context, using physical CHECK validation.
"""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "period_reopen_basis",
        sa.Column("period_state_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("judgement_record_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_period_reopen_basis__state", ["tenant_id", "period_state_id"], None)],
    )
    for column, target in (
        ("period_state_id", "period_state"),
        ("entity_id", "legal_entity"),
        ("judgement_record_id", "judgement_record"),
    ):
        ops.add_tenant_fk("period_reopen_basis", column, target)
    ops.apply_class("period_reopen_basis", "IM-M")
    ops.enable_rls("period_reopen_basis", "RLS-TE", entity_column="entity_id")
    ops.execute("ALTER TABLE erev.period_lock ADD COLUMN judgement_record_id uuid")
    ops.add_tenant_fk("period_lock", "judgement_record_id", "judgement_record")
    ops.execute("""
        ALTER TABLE erev.period_lock ADD CONSTRAINT ck_period_lock__judgement_kind
        CHECK (judgement_record_id IS NULL OR
               (kind::text = 'REOPEN'
                AND reason_code::text IS NOT DISTINCT FROM 'ERROR_CORRECTION'))
    """)


def downgrade() -> None:
    # CHECK validation scans all physical rows despite FORCE RLS. Failure rolls the whole
    # migration back, retaining both columns and their evidence without changing RLS or roles.
    for table, column in (
        ("period_reopen_basis", "judgement_record_id"),
        ("period_lock", "judgement_record_id"),
    ):
        guard = f"ck_{table}__0137_no_citations"
        ops.execute(
            f"ALTER TABLE erev.{table} ADD CONSTRAINT {guard} CHECK ({column} IS NULL) NOT VALID"
        )
        ops.execute(f"ALTER TABLE erev.{table} VALIDATE CONSTRAINT {guard}")
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT {guard}")
    ops.execute("ALTER TABLE erev.period_lock DROP COLUMN judgement_record_id")
    ops.drop_tenant_table("period_reopen_basis")
