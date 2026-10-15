"""T-AI-02 immutable configuration evidence for AI calls (AIX-1)."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "ai_model_log",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_template_id", sa.Text(), nullable=False),
        sa.Column("prompt_template_version", sa.Text(), nullable=False),
        sa.Column("parameters", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("input_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("response_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_ai_model_log__provider", "provider IN ('fake','anthropic')"),
            (
                "ck_ai_model_log__outcome",
                "outcome IN ('SUCCESS','ERROR','TIMEOUT','BUDGET_EXCEEDED','DISABLED')",
            ),
            (
                "ck_ai_model_log__counts",
                "input_tokens >= 0 AND output_tokens >= 0 AND latency_ms >= 0",
            ),
        ],
        indexes=[("ix_ai_model_log__created", ["tenant_id", "created_at"], None)],
    )
    ops.apply_class("ai_model_log", "IM-A")
    ops.enable_rls("ai_model_log", "RLS-T")


def downgrade() -> None:
    ops.drop_tenant_table("ai_model_log")
