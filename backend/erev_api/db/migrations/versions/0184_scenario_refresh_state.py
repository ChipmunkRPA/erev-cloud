"""Persist forecast refresh identity and lifecycle in the production workspace."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None

TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['FAILED', 'SUCCEEDED']::text[]) THEN
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
   WHERE n.key <> ALL (ARRAY['finished_at', 'problem', 'row_version', 'started_at', 'status', 'target_content_sha256', 'target_input_set_id', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.finished_at IS NOT NULL AND NEW.finished_at IS DISTINCT FROM OLD.finished_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: finished_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.target_content_sha256 IS NOT NULL AND NEW.target_content_sha256 IS DISTINCT FROM OLD.target_content_sha256 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: target_content_sha256 of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.target_input_set_id IS NOT NULL AND NEW.target_input_set_id IS DISTINCT FROM OLD.target_input_set_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: target_input_set_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['QUEUED>FAILED', 'QUEUED>RUNNING', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    ops.create_tenant_table(
        "scenario_refresh",
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("source_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source_input_set_id", sa.Uuid(), nullable=False),
        sa.Column("source_content_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("target_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.run_status"),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column("target_input_set_id", sa.Uuid()),
        sa.Column("target_content_sha256", ops.NamedType("erev.sha256")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("problem", JSONB()),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_scenario_refresh__different_target", "source_tenant_id <> target_tenant_id")],
        unique=[
            (
                "ux_scenario_refresh__active",
                ["tenant_id", "scenario_id"],
                "status IN ('QUEUED', 'RUNNING')",
            ),
            ("ux_scenario_refresh__target", ["tenant_id", "target_tenant_id"], None),
            ("ux_scenario_refresh__job", ["tenant_id", "job_id"], None),
        ],
    )
    for column, target in (
        ("scenario_id", "scenario"),
        ("tenant_snapshot_id", "tenant_snapshot"),
        ("job_id", "job"),
    ):
        ops.add_tenant_fk("scenario_refresh", column, target)
    ops.apply_class(
        "scenario_refresh",
        "IM-S",
        update_columns=(
            "status",
            "target_input_set_id",
            "target_content_sha256",
            "started_at",
            "finished_at",
            "problem",
            "updated_at",
            "updated_by",
            "updated_by_kind",
            "row_version",
        ),
    )
    ops.enable_rls("scenario_refresh", "RLS-T")
    ops.create_trigger(
        "scenario_refresh", "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.scenario_refresh) THEN
        RAISE EXCEPTION 'Forecast refresh evidence exists; downgrade refused';
      END IF;
    END $$""")
    ops.drop_tenant_table("scenario_refresh")
