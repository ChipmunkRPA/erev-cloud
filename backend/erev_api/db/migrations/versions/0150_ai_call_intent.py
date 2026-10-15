"""Retain immutable provider-call intent and at most one linked outcome."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "ai_call_intent",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("input_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("source_sha256", ops.NamedType("erev.sha256"), nullable=False),
        standard_sets=["SC-C"],
        checks=[
            ("ck_ai_call_intent__attempt", "attempt_no BETWEEN 1 AND 3"),
            ("ck_ai_call_intent__provider", "provider IN ('fake', 'anthropic')"),
            ("ck_ai_call_intent__human", "created_by_kind = 'USER' AND created_by IS NOT NULL"),
        ],
    )
    ops.add_tenant_fk("ai_call_intent", "job_id", "job")
    ops.create_indexes(
        "ai_call_intent",
        [
            ("ux_ai_call_intent__attempt", ["tenant_id", "job_id", "attempt_no"], None),
        ],
        unique=True,
    )
    ops.apply_class("ai_call_intent", "IM-A")
    ops.enable_rls("ai_call_intent", "RLS-T")
    ops.execute("ALTER TABLE erev.ai_model_log ADD COLUMN intent_id uuid")
    ops.add_tenant_fk("ai_model_log", "intent_id", "ai_call_intent")
    ops.create_indexes(
        "ai_model_log",
        [
            ("ux_ai_model_log__intent", ["tenant_id", "intent_id"], "intent_id IS NOT NULL"),
        ],
        unique=True,
    )


def downgrade() -> None:
    # Intent evidence must not disappear even when no outcome was recorded.
    ops.execute(
        "ALTER TABLE erev.ai_call_intent ADD CONSTRAINT ck_ai_call_intent__0150_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.ai_call_intent VALIDATE CONSTRAINT ck_ai_call_intent__0150_empty")
    ops.execute("ALTER TABLE erev.ai_model_log DROP COLUMN intent_id")
    ops.drop_tenant_table("ai_call_intent")
