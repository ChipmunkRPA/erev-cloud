"""T-AI-01: immutable proposal evidence and SM-11 lifecycle (AIX-1)."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None

UPDATE_COLUMNS = (
    "accepted_at",
    "accepted_by",
    "accepted_command",
    "accepted_object_id",
    "accepted_object_type",
    "field_decisions",
    "problem",
    "rejected_at",
    "rejected_by",
    "rejection_reason",
    "row_version",
    "status",
    "updated_at",
    "updated_by",
    "updated_by_kind",
)

TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['accepted', 'expired', 'failed', 'rejected']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['accepted_at', 'accepted_by', 'accepted_command', 'accepted_object_id', 'accepted_object_type', 'field_decisions', 'problem', 'rejected_at', 'rejected_by', 'rejection_reason', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_at IS NOT NULL AND NEW.accepted_at IS DISTINCT FROM OLD.accepted_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_by IS NOT NULL AND NEW.accepted_by IS DISTINCT FROM OLD.accepted_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_command IS NOT NULL AND NEW.accepted_command IS DISTINCT FROM OLD.accepted_command THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_command of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_object_id IS NOT NULL AND NEW.accepted_object_id IS DISTINCT FROM OLD.accepted_object_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_object_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_object_type IS NOT NULL AND NEW.accepted_object_type IS DISTINCT FROM OLD.accepted_object_type THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_object_type of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.field_decisions IS NOT NULL AND NEW.field_decisions IS DISTINCT FROM OLD.field_decisions THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: field_decisions of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.problem IS NOT NULL AND NEW.problem IS DISTINCT FROM OLD.problem THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: problem of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.rejected_at IS NOT NULL AND NEW.rejected_at IS DISTINCT FROM OLD.rejected_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: rejected_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.rejected_by IS NOT NULL AND NEW.rejected_by IS DISTINCT FROM OLD.rejected_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: rejected_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.rejection_reason IS NOT NULL AND NEW.rejection_reason IS DISTINCT FROM OLD.rejection_reason THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: rejection_reason of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['proposed>accepted', 'proposed>expired', 'proposed>rejected']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    ops.create_enum(
        "ai_proposal_kind",
        ("CONTRACT_EXTRACTION", "NUMBER_EXPLANATION", "ANOMALY_FLAG", "QA_ANSWER"),
    )
    ops.create_enum("ai_proposal_status", ("proposed", "accepted", "rejected", "expired", "failed"))
    ops.create_tenant_table(
        "ai_proposal",
        sa.Column("kind", ops.NamedType("erev.ai_proposal_kind"), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.ai_proposal_status"),
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column("subject_type", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("file_object_id", sa.Uuid(), nullable=True),
        sa.Column("document_text_file_id", sa.Uuid(), nullable=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("citations", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ai_model_log_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_command", sa.Text(), nullable=True),
        sa.Column("field_decisions", JSONB(), nullable=True),
        sa.Column("accepted_object_type", sa.Text(), nullable=True),
        sa.Column("accepted_object_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", ops.NamedType("erev.memo"), nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("problem", JSONB(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_ai_proposal__citations", "jsonb_typeof(citations) = 'array'"),
            ("ck_ai_proposal__expiry", "expires_at > created_at"),
            ("ck_ai_proposal__subject", "(subject_type IS NULL) = (subject_id IS NULL)"),
            (
                "ck_ai_proposal__accepted",
                "(status = 'accepted' AND accepted_command IS NOT NULL AND field_decisions "
                "IS NOT NULL AND accepted_object_type IS NOT NULL AND accepted_object_id IS "
                "NOT NULL AND accepted_by IS NOT NULL AND accepted_at IS NOT NULL) OR "
                "(status <> 'accepted' AND accepted_command IS NULL AND field_decisions IS "
                "NULL AND accepted_object_type IS NULL AND accepted_object_id IS NULL AND "
                "accepted_by IS NULL AND accepted_at IS NULL)",
            ),
            (
                "ck_ai_proposal__rejected",
                "(status = 'rejected' AND rejected_by IS NOT NULL AND rejected_at IS NOT "
                "NULL AND rejection_reason IS NOT NULL) OR (status <> 'rejected' AND "
                "rejected_by IS NULL AND rejected_at IS NULL AND rejection_reason IS NULL)",
            ),
            ("ck_ai_proposal__failure", "(status = 'failed') = (problem IS NOT NULL)"),
            (
                "ck_ai_proposal__decisions",
                "field_decisions IS NULL OR CASE WHEN jsonb_typeof(field_decisions) = 'array' "
                "THEN jsonb_array_length(field_decisions) > 0 ELSE false END",
            ),
        ],
        indexes=[("ix_ai_proposal__status", ["tenant_id", "kind", "status", "created_at"], None)],
    )
    ops.add_tenant_fk("ai_proposal", "ai_model_log_id", "ai_model_log")
    ops.add_tenant_fk("ai_proposal", "file_object_id", "file_object")
    ops.add_tenant_fk("ai_proposal", "document_text_file_id", "file_object")
    ops.add_global_fk("ai_proposal", "accepted_by", "app_user")
    ops.add_global_fk("ai_proposal", "rejected_by", "app_user")
    ops.apply_class("ai_proposal", "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls("ai_proposal", "RLS-T")
    ops.create_trigger(
        "ai_proposal", "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    ops.drop_tenant_table("ai_proposal")
    ops.drop_enum("ai_proposal_status")
    ops.drop_enum("ai_proposal_kind")
