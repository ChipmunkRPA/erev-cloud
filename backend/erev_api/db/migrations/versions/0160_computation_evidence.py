"""Retain typed computation evidence in the producing transaction (T-CON-25)."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for purpose in ("COMPUTATION_INPUT", "COMPUTATION_OUTPUT"):
        ops.add_enum_value("file_purpose", purpose)
    ops.create_tenant_table(
        "computation_evidence",
        sa.Column("contract_computation_id", sa.Uuid(), nullable=False),
        sa.Column("input_file_id", sa.Uuid(), nullable=False),
        sa.Column("input_file_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("input_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("output_file_id", sa.Uuid(), nullable=False),
        sa.Column("output_file_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("output_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("book_codes", sa.dialects.postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("codec", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("ledger_cutoff", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("previous_computation_id", sa.Uuid(), nullable=True),
        sa.Column("captured", sa.Text(), nullable=False),
        sa.Column("backfill_verification_id", sa.Uuid(), nullable=True),
        include_id=False,
        primary_key=["tenant_id", "contract_computation_id"],
        standard_sets=["SC-C"],
        checks=[
            # Verified backfill needs T-CON-26 and is not admitted by this revision.
            (
                "ck_computation_evidence__capture",
                "captured = 'AT_COMPUTATION' AND backfill_verification_id IS NULL",
            ),
            ("ck_computation_evidence__output", "output_file_sha256 = output_sha256"),
            (
                "ck_computation_evidence__objects",
                "jsonb_typeof(codec) = 'object' AND jsonb_typeof(ledger_cutoff) = 'object'",
            ),
        ],
    )
    for column in ("contract_computation_id", "previous_computation_id"):
        ops.add_tenant_fk("computation_evidence", column, "contract_computation")
    for column in ("input_file_id", "output_file_id"):
        ops.add_tenant_fk("computation_evidence", column, "file_object")
    ops.apply_class("computation_evidence", "IM-A")
    ops.enable_rls("computation_evidence", "RLS-T")


def downgrade() -> None:
    # Never silently erase the historical evidence required for replay.
    ops.execute(
        "ALTER TABLE erev.computation_evidence ADD CONSTRAINT "
        "ck_computation_evidence__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.computation_evidence VALIDATE CONSTRAINT ck_computation_evidence__empty"
    )
    ops.drop_tenant_table("computation_evidence")
    for purpose in ("COMPUTATION_OUTPUT", "COMPUTATION_INPUT"):
        ops.remove_enum_value("file_purpose", purpose)
